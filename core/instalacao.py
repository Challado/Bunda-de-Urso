"""Instalacao local coordenada, chamada por api.pse e pelo instalador privado.

O servidor e descrito no radar.conf, nunca neste modulo. Nao baixa credenciais,
nao restaura o banco automaticamente e nao executa material de referencia/.
"""
import argparse
import configparser
from contextlib import closing, contextmanager, ExitStack
import datetime
import fcntl
import json
import os
from pathlib import Path
import pwd
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
from . import atualizacoes

from . import caminhos, db
from . import auditoria_instalacao as auditoria
from .contexto_api import operacao_local
from .governanca import GovernancaError

CODIGO = ("core", "coletor", "config", "sql", "web", "deploy", "tools")
ESTATICOS = {".html", ".json", ".png", ".ico", ".css", ".js", ".svg"}


@contextmanager
def _usar_conf(arquivo):
    anterior = os.environ.get("RADAR_CONF")
    os.environ["RADAR_CONF"] = str(arquivo)
    caminhos.recarregar()
    try:
        yield
    finally:
        if anterior is None:
            os.environ.pop("RADAR_CONF", None)
        else:
            os.environ["RADAR_CONF"] = anterior
        caminhos.recarregar()


@contextmanager
def _configuracao_preparada(conf, perfil=None):
    """Completa um perfil em temporario; so --aplicar grava no destino."""
    fonte = conf if conf.is_file() else Path(caminhos.conf_path())
    with _usar_conf(fonte):
        texto = fonte.read_text() if fonte.is_file() else ""
        faltantes = {}
        if perfil:
            padroes = configparser.ConfigParser(interpolation=None, strict=False)
            padroes.read_string(perfil.read_text())
            gravadas = auditoria.chaves_gravadas(texto)
            for secao in padroes.sections():
                for chave, valor in padroes.items(secao):
                    if secao != "sincronizacao" and chave in caminhos.SECOES.get(secao, ()) and (secao, chave) not in gravadas:
                        faltantes[secao, chave] = valor
            # Um banco omitido acompanha dados.dir existente. Uma chave vazia
            # existente e preservada, como nas outras opcoes do servidor.
            if ("dados", "dir") in gravadas and ("dados", "banco") in faltantes:
                faltantes["dados", "banco"] = caminhos.banco()
        from .configuracao import _editar, _validar
        _validar(faltantes)
        with tempfile.TemporaryDirectory(prefix="radar-conf-efetiva-") as pasta:
            if faltantes or not conf.is_file():
                efetiva = Path(pasta) / "radar.conf"
                efetiva.write_text(_editar(texto, faltantes))
            else:
                efetiva = conf
            with _usar_conf(efetiva):
                yield


def _diretorio(pasta, observacoes, modo=None, grupo=None):
    """Cria tambem os pais com travessia; nao altera pais preexistentes."""
    ausentes = []
    atual = pasta
    while not atual.exists():
        ausentes.append(atual)
        atual = atual.parent
    for alvo in reversed(ausentes):
        alvo.mkdir(mode=0o755)
        alvo.chmod(0o755)  # o shell do instalador usa umask 077
        observacoes.append("Diretorio criado: " + str(alvo))
    if not pasta.is_dir():
        raise RuntimeError("O destino de diretorio esta ocupado por um arquivo: " + str(pasta))
    antes = pasta.stat()
    if grupo is not None and os.geteuid() == 0 and antes.st_gid != grupo:
        os.chown(pasta, -1, grupo)
        observacoes.append("Grupo ajustado: " + str(pasta))
    if modo is not None and pasta.stat().st_mode & 0o7777 != modo:
        pasta.chmod(modo)
        observacoes.append("Permissoes ajustadas (%04o): %s" % (modo, pasta))


def _pastas_operacionais(dirs):
    from .fila_cadastros import PASTAS
    fila = Path(caminhos.fila_cadastros(dirs["dados"]))
    return tuple(dict.fromkeys((fila, *(fila / n for n in PASTAS), dirs["dados"], dirs["logs"], dirs["dados"] / "raw",
                                dirs["dados"] / "staging", dirs["dados"] / "calibracao", dirs["banco"].parent)))


def _observacoes(observacoes):
    print("\nObservacoes:")
    for aviso in observacoes or ["Nenhuma alteracao de preparacao executada."]:
        print("- " + aviso)


def _executar(cmd, **kwargs):
    inicio = time.monotonic()
    atualizacoes.evento("comando.inicio", comando=cmd)
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True,
                           timeout=120, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        ocultar = "configuracao" in cmd and "mostrar" in cmd
        atualizacoes.evento("comando.erro", comando=cmd, erro=str(exc),
                           stdout="[configuracao omitida]" if ocultar else getattr(exc, "stdout", None),
                           stderr=getattr(exc, "stderr", None),
                           codigo_comando=getattr(exc, "returncode", None),
                           duracao_comando_s=round(time.monotonic() - inicio, 3))
        raise
    # Configuracao completa pode conter URLs/chaves do administrador.
    ocultar = "configuracao" in cmd and "mostrar" in cmd
    atualizacoes.evento("comando.fim", comando=cmd, codigo_comando=r.returncode,
                       stdout="[configuracao omitida]" if ocultar else r.stdout, stderr=r.stderr,
                       duracao_comando_s=round(time.monotonic() - inicio, 3))
    return r.stdout


def _ambiente(conf):
    ambiente = {k: v for k, v in os.environ.items()
                if not k.startswith(("RADAR_", "OLLAMA_")) and
                k not in ("GATEWAY_INTERFACE", "REQUEST_METHOD", "QUERY_STRING", "PATH_INFO")}
    ambiente["RADAR_CONF"] = str(conf)
    ambiente["PYTHONDONTWRITEBYTECODE"] = "1"
    return ambiente


def _cgi(api, conf, rota, usuario=None):
    ambiente = _ambiente(conf)
    ambiente.update(REQUEST_METHOD="GET", QUERY_STRING="rota=" + rota,
                    SCRIPT_NAME="/api.pse", CONTENT_LENGTH="0")
    comando = (["runuser", "-u", usuario, "--"] if usuario else []) + [sys.executable, str(api)]
    resposta = _executar(comando, env=ambiente)
    cabecalho, corpo = resposta.split("\n\n", 1)
    if not cabecalho.startswith("Status: 200 "):
        raise RuntimeError("Teste da API falhou: " + cabecalho.splitlines()[0])
    return json.loads(corpo)


def _validar_layout(origem, conf, laboratorio):
    if sys.version_info < (3, 13):
        raise RuntimeError("Use Python 3.13 ou superior (RADAR_PYTHON).")
    if db.sqlite3.sqlite_version_info < (3, 35, 0):
        raise RuntimeError("Use SQLite 3.35 ou superior no Python da instalacao.")
    if caminhos.problemas():
        raise RuntimeError("Corrija os avisos do radar.conf: " + "; ".join(caminhos.problemas()))
    pares = dict(caminhos._ler_conf()[0])
    for par in (("instalacao", "home"), ("dados", "dir"), ("dados", "banco"),
                ("web", "raiz"), ("logs", "dir")):
        if not pares.get(par) or not Path(pares[par]).is_absolute():
            raise RuntimeError("Configure um caminho absoluto em %s.%s." % par)
    dirs = {"codigo": Path(caminhos.home()), "dados": Path(caminhos.data_dir()),
            "banco": Path(caminhos.banco()), "web": Path(caminhos.web_raiz()),
            "logs": Path(caminhos.log_dir()), "conf": conf}
    if dirs["codigo"] == origem or dirs["codigo"] in origem.parents:
        raise RuntimeError("Baixe o codigo numa pasta temporaria fora da instalacao atual.")
    for nome, destino in dirs.items():
        if destino.is_symlink() or destino == Path("/"):
            raise RuntimeError("Destino deve ser regular, sem symlink: " + nome)
        if laboratorio and not destino.resolve().is_relative_to(laboratorio):
            raise RuntimeError("No laboratorio todos os destinos devem ficar dentro da pasta informada: " + nome)
    if any(c.isspace() or c in "%#'\"\\" for c in str(dirs["codigo"].parent)):
        raise RuntimeError("O diretorio dos wrappers de cron nao pode conter espacos ou metacaracteres.")
    if dirs["codigo"].parent == dirs["conf"].parent:
        raise RuntimeError("A configuracao deve ter uma pasta exclusiva fora dos executaveis.")
    for nome in ("codigo", "dados", "logs", "conf", "banco"):
        if dirs[nome].resolve().is_relative_to(dirs["web"].resolve()):
            raise RuntimeError("Codigo, dados, logs e configuracao devem ficar fora do webroot.")
    for nome in ("dados", "web", "logs", "conf", "banco"):
        if dirs[nome].resolve().is_relative_to(dirs["codigo"].resolve()):
            raise RuntimeError("Dados/configuracao/web devem ficar fora da arvore substituida do codigo.")
    for nome in CODIGO:
        if not (origem / nome).is_dir():
            raise RuntimeError("Checkout incompleto: " + nome)
    if not (origem / "core" / "configuracao.py").is_file():
        raise RuntimeError("Versao anterior ao suporte de configuracao pela API.")
    if dirs["codigo"].is_dir() and not (dirs["codigo"] / "core").is_dir():
        reconhecido = any((dirs["codigo"] / nome).exists() for nome in ("VERSAO", "coletor", "deploy"))
        if any(dirs["codigo"].iterdir()) and not reconhecido:
            raise RuntimeError("Destino do codigo ocupado por outra aplicacao.")
    if not dirs["banco"].is_file():
        raise RuntimeError("O banco configurado nao existe. Este instalador atualiza o servidor existente e nao cria base vazia.")
    # A configuracao e o relatorio publico podem ter links conhecidos. Nunca
    # autorizar outros destinos apenas porque o nome parece um arquivo de status.
    if dirs["web"].is_dir():
        for item in dirs["web"].rglob("*"):
            if item.is_symlink() and item != dirs["web"] / "radar.conf" and not _link_status_publico(item, dirs["web"]):
                raise RuntimeError("Revise o link existente no webroot antes de instalar: " + str(item))
    return dirs


def _link_status_publico(item, web):
    """Aceita o relatorio persistente, inclusive via link na pasta do aplicativo."""
    if item != web / "status-atualizacoes.json":
        return False
    try:
        alvo = item.resolve()
        # Durante a troca atomica da arvore, o link do aplicativo ainda sera
        # recriado por publicar_link(). Aceita esse destino conhecido ausente.
        return alvo == Path(caminhos.status_atualizacoes()).resolve() or (
            alvo == Path(caminhos.link_atualizacoes()) and not alvo.exists())
    except (OSError, RuntimeError):
        return False


def _guardar(caminho, backup, indice):
    """Copia um alvo antes da alteracao e registra como reverte-lo."""
    destino = backup / ("item-%02d" % len(indice))
    existe = caminho.exists()
    if existe:
        if caminho.is_dir():
            shutil.copytree(caminho, destino, symlinks=True)
        else:
            shutil.copy2(caminho, destino)
    indice.append({"alvo": str(caminho), "copia": str(destino), "existia": existe})


def _restaurar(indice):
    for item in reversed(indice):
        alvo, copia = Path(item["alvo"]), Path(item["copia"])
        if alvo.is_dir() and not alvo.is_symlink():
            shutil.rmtree(alvo)
        elif alvo.exists() or alvo.is_symlink():
            alvo.unlink()
        if item["existia"]:
            if copia.is_dir():
                shutil.copytree(copia, alvo, symlinks=True)
            else:
                shutil.copy2(copia, alvo)


def _permissoes(arvore, gid, gravavel=False, link_configuracao=False):
    for item in [arvore, *arvore.rglob("*")]:
        if item.is_symlink():
            if link_configuracao and (item == arvore / "radar.conf" or _link_status_publico(item, arvore)):
                continue
            raise RuntimeError("Symlink inesperado: " + str(item))
        if os.geteuid() == 0:
            os.chown(item, 0, gid)
        item.chmod((0o2770 if gravavel else 0o755) if item.is_dir() else
                   (0o660 if gravavel else 0o644))


def _cron_tick(texto, wrapper):
    linhas = []
    for linha in texto.splitlines():
        # Troca somente a linha ativa que chama exatamente este wrapper.
        if auditoria.comando_coletor(linha, wrapper) or auditoria.comando_fila(linha):
            continue
        linhas.append(linha)
    # O wrapper nao contem caminhos variaveis de dados ou log.
    linhas.append("* * * * * " + shlex.quote(str(wrapper)))
    linhas.append("* * * * * " + shlex.quote(str(wrapper.with_name("radar-api.pse"))) + " cron fila")
    return "\n".join(linhas) + "\n"


def _aplicar(origem, dirs, usuario_web, laboratorio, cron, origem_http=None, observacoes=None):
    if not laboratorio and os.geteuid() != 0:
        raise RuntimeError("Execute como root para aplicar no servidor.")
    conta = pwd.getpwnam(usuario_web)
    grupo = conta.pw_gid
    observacoes = observacoes if observacoes is not None else []
    for pasta in _pastas_operacionais(dirs):
        _diretorio(pasta, observacoes, modo=0o2770, grupo=grupo)
    agora = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = dirs["dados"] / "backups" / "instalacao" / agora
    _diretorio(backup.parent, observacoes, modo=0o700)
    _diretorio(backup, observacoes, modo=0o700)
    atualizacoes.evento("backup.inicio", backup=str(backup))
    indice = []
    relatorio = None
    wrapper = dirs["codigo"].parent / "radar-tick.sh"
    entrada_cron = wrapper.with_name("radar-api.pse")
    logrotate = (laboratorio / "etc" if laboratorio else Path("/etc")) / "logrotate.d" / "openclaw-radar"
    sudoers_antigo = (laboratorio / "etc" if laboratorio else Path("/etc")) / "sudoers.d" / "radar-configuracao"
    nginx_alterado = False
    cron_anterior = None
    with open(dirs["dados"] / "instalacao.lock", "a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for alvo in (dirs["codigo"], dirs["web"], dirs["conf"], wrapper, entrada_cron,
                         logrotate, Path(str(dirs["conf"]) + ".painel")):
                _diretorio(alvo.parent, observacoes)
                _guardar(alvo, backup, indice)
            if sudoers_antigo.exists():
                _guardar(sudoers_antigo, backup, indice)
            if not laboratorio:
                from .protecao_configuracao import planejar
                plano_nginx = planejar(caminhos.web_url(), dirs["web"], caminhos.valor("web", "origem")[0], raiz_local=True)
                for arquivo, anterior, novo in plano_nginx:
                    if arquivo.read_text() != anterior:
                        raise RuntimeError("A configuracao do nginx mudou durante a preparacao.")
                    _guardar(arquivo, backup, indice)
                    indice[-1]["tipo"] = "nginx"
                    arquivo.write_text(novo)
                    nginx_alterado = True
                    observacoes.append("Nginx: acesso HTTP direto a radar.conf bloqueado em " + str(arquivo))
            (backup / "restauracao.json").write_text(json.dumps(indice, indent=2))
            atualizacoes.evento("backup.arquivos", arquivos=indice)
            if nginx_alterado:
                _executar(["nginx", "-t"])
                _executar(["systemctl", "reload", "nginx"])
            # Pausa novas chamadas CGI e tick durante a troca coordenada.
            dirs["web"].mkdir(parents=True, exist_ok=True)
            (dirs["web"] / "api.pse").write_text(
                "#!" + sys.executable + "\nprint('Status: 503 Service Unavailable\\r\\nRetry-After: 30\\r\\nContent-Type: text/plain\\r\\n\\r\\nAtualizacao em andamento.')\n")
            (dirs["web"] / "api.pse").chmod(0o755)
            wrapper.write_text("#!/bin/sh\n# Atualizacao coordenada em andamento.\nexit 0\n")
            wrapper.chmod(0o755)
            with ExitStack() as locks:
                tick = locks.enter_context(open(dirs["dados"] / "tick.lock", "a"))
                _esperar_coletor(tick)
                fila = locks.enter_context(open(Path(caminhos.fila_cadastros(dirs["dados"])) / "processador.lock", "a"))
                os.fchmod(fila.fileno(), 0o660)
                _esperar_coletor(fila)
                with closing(db.connect_readonly(dirs["banco"])) as fonte:
                    if fonte.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("Integridade do banco reprovada; nada sera atualizado.")
                    if fonte.execute("PRAGMA foreign_key_check").fetchone() is not None:
                        raise RuntimeError("Banco com referencias invalidas; nenhuma atualizacao foi aplicada.")
                    with closing(db.connect(backup / "radar.sqlite3")) as copia:
                        fonte.backup(copia)
                        copia.execute("PRAGMA journal_mode=DELETE")
                (backup / "radar.sqlite3").chmod(0o600)
                atualizacoes.evento("backup.banco", integridade="ok", banco_backup=str(backup / "radar.sqlite3"))
                atualizacoes.evento("instalar.arquivos")
                _instalar_arquivos(origem, dirs, grupo, usuario_web, backup, origem_http, observacoes)
                atualizacoes.publicar_link()
                atualizacoes.evento("instalar.configuracao")
                _instalar_configuracao_web(dirs, grupo, observacoes)
                if sudoers_antigo.exists():
                    sudoers_antigo.unlink()
                    observacoes.append("Regra sudoers antiga removida: " + str(sudoers_antigo))
                Path(str(dirs["conf"]) + ".painel").unlink(missing_ok=True)
                conteudo = auditoria.render_logrotate(origem, dirs["logs"])
                if not logrotate.is_file() or logrotate.read_text() != conteudo:
                    observacoes.append("Regra do logrotate %s: %s" % ("atualizada" if logrotate.is_file() else "criada", logrotate))
                logrotate.write_text(conteudo)
                logrotate.chmod(0o644)
                atualizacoes.evento("instalar.logrotate", arquivo_logrotate=str(logrotate), conteudo=conteudo)
                api = dirs["web"] / "api.pse"
                # Inicializacao/migracoes continuam passando pela mesma entrada.
                _executar([sys.executable, str(api), "ferramenta", "inicializar_banco"],
                          env=_ambiente(dirs["conf"]))
                reconciliacao = _executar([sys.executable, str(api), "ferramenta", "reconciliar_equipamentos", "--aplicar"],
                                          env=_ambiente(dirs["conf"]))
                observacoes.append("Identidade dos equipamentos: " + reconciliacao.strip())
                _cgi(api, dirs["conf"], "/health/ready")
                _cgi(api, dirs["conf"], "/api/v1/ajuda")
                _executar([sys.executable, str(api), "configuracao", "mostrar"], env=_ambiente(dirs["conf"]))
                shutil.copy2(origem / "deploy" / "api.pse", entrada_cron)
                entrada_cron.write_text(auditoria.bootstrap(entrada_cron.read_text(), dirs["conf"]))
                entrada_cron.chmod(0o755)
                shutil.copy2(origem / "deploy" / "radar-tick.sh", wrapper)
                # O interpretador testado e fixado apenas no bootstrap do cron.
                wrapper.write_text(wrapper.read_text().replace(
                    '${RADAR_PYTHON:-/usr/bin/python3}', '${RADAR_PYTHON:-' + sys.executable + '}'))
                wrapper.chmod(0o755)
                observacoes.append("Entradas da API e do coletor atualizadas: %s; %s" % (entrada_cron, wrapper))
            if not laboratorio:
                # Testa as permissoes reais do usuario CGI, nao somente root.
                _executar(["runuser", "-u", usuario_web, "--", sys.executable,
                           str(dirs["web"] / "api.pse"), "configuracao", "mostrar"],
                          env=_ambiente(dirs["conf"]))
                _cgi(dirs["web"] / "api.pse", dirs["conf"], "/health/ready", usuario=usuario_web)
            if cron and not laboratorio:
                from .raiz_web import _transferir_crons
                cron_anterior = _transferir_crons(backup, dirs["codigo"].parent, dirs["web"], usuario_web, dirs["conf"])
                observacoes.append("Coleta e fila transferidas do root para o crontab de " + usuario_web + "; outras rotinas preservadas.")
            relatorio = _diagnosticar(origem, dirs, usuario_web, laboratorio, cron, final=True)
            relatorio["backup"] = str(backup)
            relatorio["observacoes"] = list(observacoes)
            atualizacoes.evento("checagem.final", relatorio=relatorio)
            (backup / "checagem-final.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
            if not relatorio["sucesso"]:
                raise RuntimeError("Checagem final reprovada; consulte checagem-final.json no backup.")
            (backup / "CONCLUIDO").write_text(agora + "\n")
            print("Instalacao concluida. Backup: " + str(backup))
        except BaseException as exc:
            atualizacoes.evento("recuperacao.inicio", erro=str(exc))
            if not _esquema_compativel_com_backup(backup, dirs["banco"]):
                mensagem = ("Esquema do banco migrado: codigo atualizado preservado para manter compatibilidade. "
                            "Corrija a checagem final e reaplique o instalador. Backup: " + str(backup))
                observacoes.append(mensagem)
                relatorio = relatorio or {"sucesso": False, "backup": str(backup)}
                relatorio.update(erro=str(exc), observacoes=list(observacoes), recuperacao_automatica=False)
                (backup / "checagem-final.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
                print(mensagem, file=sys.stderr)
                atualizacoes.evento("recuperacao.nao_aplicada", recuperacao_automatica=False, observacoes=observacoes)
                raise
            _restaurar(indice)
            atualizacoes.publicar_link()
            if nginx_alterado:
                _executar(["nginx", "-t"])
                _executar(["systemctl", "reload", "nginx"])
            if not laboratorio and cron_anterior is not None:
                for nome in cron_anterior:
                    _recuperar_cron(backup / ("crontab-" + nome + "-anterior.txt"), wrapper, nome)
            observacoes.append("Falha: arquivos anteriores recuperados; banco preservado. Pastas preparadas podem permanecer.")
            relatorio = relatorio or {"sucesso": False, "erro": str(exc), "backup": str(backup)}
            relatorio.update(observacoes=list(observacoes), recuperacao_automatica=True)
            (backup / "checagem-final.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
            print("Falha: codigo, web, wrappers e conf restaurados. Banco preservado; backup em " + str(backup), file=sys.stderr)
            atualizacoes.evento("recuperacao.fim", recuperacao_automatica=True, relatorio=relatorio)
            raise
    return relatorio


def _instalar_arquivos(origem, dirs, grupo, usuario_web, backup, origem_http=None, observacoes=None):
    observacoes = observacoes if observacoes is not None else []
    nova = Path(tempfile.mkdtemp(prefix=".radar-novo-", dir=dirs["codigo"].parent))
    try:
        for pasta in CODIGO:
            shutil.copytree(origem / pasta, nova / pasta,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for nome in ("README.md", "LICENSE"):
            shutil.copy2(origem / nome, nova / nome)
        bootstrap_local = nova / "web" / "api.pse"
        bootstrap_local.write_text(auditoria.fixar_conf(bootstrap_local.read_text(), dirs["conf"]))
        _executar([sys.executable, "-m", "compileall", "-q", str(nova)])
        _permissoes(nova, grupo)
        versao = _executar(["git", "-C", str(origem), "rev-parse", "HEAD"]).strip()
        (nova / "VERSAO").write_text(versao + "\n")
        (nova / "VERSAO").chmod(0o644)
        anterior = dirs["codigo"].with_name(".radar-anterior-" + backup.name)
        if dirs["codigo"].exists():
            dirs["codigo"].rename(anterior)
        nova.rename(dirs["codigo"])
        if anterior.exists():
            # Ja foi copiado para o backup; so remove a arvore duplicada antiga.
            shutil.rmtree(anterior)
        conf = dirs["conf"]
        efetivos = caminhos._ler_conf()[0]
        if not conf.exists():
            shutil.copy2(caminhos.conf_path(), conf)
            observacoes.append("Configuracao criada a partir do perfil: " + str(conf))
        else:
            from .configuracao import _editar
            gravadas = auditoria.chaves_gravadas(conf.read_text())
            novas = {par: valor for par, valor in efetivos.items() if par not in gravadas and par[0] != "sincronizacao"}
            if novas:
                conf.write_text(_editar(conf.read_text(), novas))
                observacoes.extend("Opcao acrescentada do perfil: %s.%s = %s" % (*par, valor) for par, valor in novas.items())
        # Migra parametros antigos de governanca sem substituir opcoes do .conf.
        antigo = backup / "item-00" / "config" / "governanca.json"
        existentes = auditoria.chaves_gravadas(conf.read_text())
        if antigo.is_file():
            valores = json.loads(antigo.read_text())
            faltantes = {k.lower(): str(v) for k, v in valores.items()
                         if k.lower() in caminhos.SECOES["governanca"] and
                         ("governanca", k.lower()) not in existentes}
            if faltantes:
                observacoes.extend("Opcao preservada da configuracao antiga: governanca." + k for k in faltantes)
                with conf.open("a") as saida:
                    saida.write("\n[governanca]\n")
                    for k, v in faltantes.items():
                        saida.write(k + " = " + v + "\n")
        # Completa o esquema novo sem substituir valores ou chaves vazias do servidor.
        from .configuracao import _editar
        if origem_http and ("web", "origem") not in auditoria.chaves_gravadas(conf.read_text()):
            conf.write_text(_editar(conf.read_text(), {("web", "origem"): origem_http}))
            observacoes.append("Opcao acrescentada: web.origem (origem HTTP inicial).")
        faltantes = auditoria.opcoes_faltantes(conf.read_text())
        if faltantes:
            conf.write_text(_editar(conf.read_text(), faltantes))
            observacoes.extend("Opcao acrescentada com valor padrao: %s.%s = %s" % (*par, valor or "(vazio)") for par, valor in faltantes.items())
        # Os subprocessos e a rotacao devem consultar o arquivo definitivo.
        os.environ["RADAR_CONF"] = str(conf)
        caminhos.recarregar()
        if os.geteuid() == 0:
            os.chown(conf.parent, 0, 0)
            os.chown(conf, 0, 0)
        # Permissoes para salvamento direto pelo CGI sao preparadas em seguida.
        for pasta in _pastas_operacionais(dirs):
            _diretorio(pasta, observacoes, modo=0o2770, grupo=grupo)
        _permissoes(Path(caminhos.fila_cadastros(dirs["dados"])), grupo, gravavel=True)
        for arquivo in [dirs["banco"], *dirs["banco"].parent.glob(dirs["banco"].name + "-*")]:
            if os.geteuid() == 0:
                os.chown(arquivo, -1, grupo)
            arquivo.chmod(0o660)
        recursos=dirs['web']/'resources'
        if recursos.exists():
            shutil.rmtree(recursos)
        shutil.copytree(origem/'web/resources',recursos)
        for arquivo in recursos.iterdir():
            legado=dirs['web']/arquivo.name
            if arquivo.name!='projeto.json' and legado.is_file():
                legado.unlink()
        shutil.copy2(recursos/'projeto.json',dirs['web']/'projeto.json')
        projeto = dirs["web"] / "projeto.json"
        descritor = json.loads(projeto.read_text())
        descritor["url"] = caminhos.web_url()
        projeto.write_text(json.dumps(descritor, ensure_ascii=False, indent=2) + "\n")
        (recursos/'projeto.json').write_text(projeto.read_text())
        # O .pse do deploy e o unico Python publicado no webroot.
        shutil.copy2(origem / "deploy" / "api.pse", dirs["web"] / "api.pse")
        api = dirs["web"] / "api.pse"
        api.write_text(auditoria.bootstrap(api.read_text(), dirs["conf"]))
        for arquivo in dirs["web"].iterdir():
            if arquivo.is_file() and arquivo.suffix in (".py", ".pyc"):
                raise RuntimeError("Remova fontes Python antigos do webroot antes de instalar: " + arquivo.name)
        _permissoes(dirs["web"], grupo, link_configuracao=True)
        api.chmod(0o755)
        observacoes.append("Codigo e paginas instalados na revisao " + versao + ".")
    finally:
        if nova.exists():
            shutil.rmtree(nova)


def _esperar_coletor(trava):
    limite = time.monotonic() + caminhos.inteiro("coleta", "espera_atualizacao")
    aviso = 0
    while True:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            agora = time.monotonic()
            if agora >= limite:
                raise RuntimeError("O coletor nao terminou no prazo de coleta.espera_atualizacao; arquivos anteriores serao recuperados.")
            if agora >= aviso:
                print("Aguardando a coleta em andamento terminar, sem interrompe-la...", flush=True)
                aviso = agora + 15
            time.sleep(min(1, limite - agora))


def _instalar_configuracao_web(dirs, grupo, observacoes):
    from .configuracao import link_aponta_configuracao
    conf = dirs["conf"]
    _diretorio(conf.parent, observacoes, modo=0o2770, grupo=grupo)
    if os.geteuid() == 0:
        os.chown(conf, 0, grupo)
    conf.chmod(0o660)
    for sufixo in (".lock", ".anterior", ".auditoria.jsonl"):
        arquivo = Path(str(conf) + sufixo)
        if arquivo.is_symlink():
            raise RuntimeError("Arquivo auxiliar de configuracao nao pode ser symlink: " + str(arquivo))
        if arquivo.exists():
            if os.geteuid() == 0:
                os.chown(arquivo, -1, grupo)
            arquivo.chmod(0o660)
    link = dirs["web"] / "radar.conf"
    if not link_aponta_configuracao(link, conf):
        link.unlink(missing_ok=True)
        link.symlink_to(conf)
        observacoes.append("Link da configuracao criado/corrigido: %s -> %s" % (link, conf))
    observacoes.append("Configuracao gravavel pelo grupo do CGI: pasta 2770; radar.conf 0660.")


def _verificar_gravacao(dirs, usuario=None):
    comando = (["runuser", "-u", usuario, "--"] if usuario else []) + [
        sys.executable, str(dirs["web"] / "api.pse"), "configuracao", "verificar-web"]
    resultado = json.loads(_executar(comando, env=_ambiente(dirs["conf"])))
    if not resultado.get("sucesso"):
        raise RuntimeError("O usuario do CGI nao conseguiu preparar a gravacao da configuracao.")


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description="Atualiza a instalacao descrita no radar.conf; padrao: simular.")
    parser.add_argument("--conf", required=True, type=Path)
    parser.add_argument("--migrar-raiz-web", action="store_true",
                        help="reune codigo, configuracao e dados na raiz web configurada")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--usuario-web", default="www-data")
    parser.add_argument("--laboratorio", type=Path, help="restringe destinos a esta pasta e nao altera cron do sistema")
    parser.add_argument("--sem-cron", action="store_true")
    parser.add_argument("--origem-http", help="origem inicial da consulta HTTP; usada somente se web.origem ainda nao existe")
    parser.add_argument("--perfil-conf", type=Path, help="perfil inicial: completa somente chaves ausentes, sem substituir o radar.conf")
    parser.add_argument("--pacote-preparado", action="append", default=[], help=argparse.SUPPRESS)
    modo.add_argument("--verificar", action="store_true", help="audita a instalacao atual, sem copiar arquivos")
    parser.add_argument("--relatorio", type=Path, help="salva a checagem em JSON no arquivo indicado")
    modo.add_argument("--restaurar", type=Path, help="restaura codigo/web/configuracao de um backup; nunca restaura banco automaticamente")
    args = parser.parse_args(argv)
    observacoes = ["Dependencia preparada pelo instalador: " + pacote for pacote in args.pacote_preparado]
    try:
        with _usar_conf(args.conf.absolute()):
            local = (Path(caminhos.home()).resolve() == Path(caminhos.web_raiz()).resolve()
                     and args.conf.absolute() == Path(caminhos.web_raiz()) / "radar.conf")
            if args.migrar_raiz_web or local:
                from .raiz_web import executar
                return executar(args, observacoes)
        with _configuracao_preparada(args.conf.absolute(), args.perfil_conf):
            # A simulacao continua sem gravar nem mesmo arquivos de diagnostico.
            if not (args.aplicar or args.restaurar):
                return _instalar(args, observacoes)
            _validar_layout(Path(caminhos.ROOT), args.conf.absolute(),
                            args.laboratorio.resolve() if args.laboratorio else None)
            _diretorio(Path(caminhos.log_dir()), observacoes)
            with atualizacoes.acompanhar("instalacao", modo="restaurar" if args.restaurar else "aplicar",
                                        bootstrap_id=os.environ.get("RADAR_BOOTSTRAP_ID"),
                                        conf=str(args.conf.absolute())) as registro:
                resultado = _instalar(args, observacoes)
                atualizacoes.publicar_link()
                registro.terminar(resultado, observacoes=observacoes)
                print("Status das atualizacoes: " + caminhos.link_atualizacoes())
                print("Log detalhado: " + caminhos.log_atualizacoes())
                return resultado
    except (OSError, ValueError, KeyError, RuntimeError, GovernancaError, subprocess.SubprocessError, configparser.Error) as exc:
        print("Instalacao recusada: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr[:2000], file=sys.stderr)
        return 1
    finally:
        _observacoes(observacoes)


def _instalar(args, observacoes):
    origem = Path(caminhos.ROOT)
    lab = args.laboratorio.resolve() if args.laboratorio else None
    dirs = _validar_layout(origem, args.conf.absolute(), lab)
    atualizacoes.evento("layout.validado", destinos={k: str(v) for k, v in dirs.items()})
    if args.restaurar:
        return _recuperar(args.restaurar, dirs, lab, args.usuario_web)
    print(json.dumps({"acao": "aplicar" if args.aplicar else "simular",
                      "destinos": {k: str(v) for k, v in dirs.items()},
                      "usuario_web": args.usuario_web,
                      "cron_tick": not args.sem_cron and not bool(lab),
                      "cron_fila": not args.sem_cron and not bool(lab)}, indent=2))
    if args.aplicar:
        if not lab and os.geteuid() != 0:
            raise RuntimeError("Execute como root para aplicar no servidor.")
        if args.origem_http:
            from .configuracao import _validar
            _validar({("web", "origem"): args.origem_http})
        if not lab:
            _preparar_servicos(observacoes)
        plano = _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron)
        atualizacoes.evento("checagem.inicial", relatorio=plano)
        precisa = plano["atualizacao_necessaria"] or any(c["estado"] in ("erro", "atualizar") for c in plano["checagens"])
        relatorio = None if precisa else _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron, final=True)
        if relatorio is not None and relatorio["sucesso"]:
            relatorio["acao"] = "sem_alteracoes"
            print("Instalacao ja atualizada; checagens aprovadas, sem nova copia ou backup.")
        else:
            relatorio = _aplicar(origem, dirs, args.usuario_web, lab, not args.sem_cron, args.origem_http, observacoes)
        resultado = 0
    else:
        relatorio = _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron,
                                 final=args.verificar)
        resultado = 0 if not args.verificar or relatorio["sucesso"] else 1
    if args.relatorio:
        pai = args.relatorio.absolute().parent
        if not pai.exists():
            _diretorio(pai, observacoes, modo=0o700)
    relatorio["observacoes"] = list(observacoes)
    if args.aplicar:
        # Atualiza o consolidado tambem com recursos que nao venceram ainda.
        # O dry-run nao consulta portais nem baixa arquivos; usa somente a API.
        _executar([sys.executable, str(dirs["web"] / "api.pse"), "tick", "--dry-run"],
                  env=_ambiente(dirs["conf"]))
    atualizacoes.evento("relatorio", relatorio=relatorio)
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    if args.relatorio:
        args.relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
    if not args.aplicar:
        print("Checagem concluida. Nenhum arquivo da instalacao foi alterado.")
    return resultado


def _esquema_compativel_com_backup(backup, banco):
    anterior = backup / "radar.sqlite3"
    if not anterior.is_file() or not banco.is_file():
        return True
    with closing(db.connect_readonly(anterior)) as velho, closing(db.connect_readonly(banco)) as atual:
        for row in velho.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            # Nomes vem do catalogo do proprio SQLite, escapados como identificadores.
            tabela = '"' + row[0].replace('"', '""') + '"'
            antigas = {r[1] for r in velho.execute('PRAGMA table_info(' + tabela + ')')}
            novas = {r[1] for r in atual.execute('PRAGMA table_info(' + tabela + ')')}
            if not antigas <= novas:
                return False
    return True


def _recuperar(backup, dirs, laboratorio, usuario_web="www-data"):
    if not laboratorio and os.geteuid() != 0:
        raise RuntimeError("Execute a recuperacao como root.")
    backup = backup.resolve(strict=True)
    raiz = (dirs["dados"] / "backups" / "instalacao").resolve()
    if backup.parent != raiz:
        raise RuntimeError("Use um backup desta instalacao, dentro de dados/backups/instalacao.")
    if not _esquema_compativel_com_backup(backup, dirs["banco"]):
        raise RuntimeError("O codigo deste backup exige colunas removidas pela migracao; banco e instalacao preservados.")
    indice = json.loads((backup / "restauracao.json").read_text())
    permitidos = {str(dirs[n]) for n in ("codigo", "web", "conf")}
    permitidos.update(str(dirs["codigo"].parent / n) for n in ("radar-tick.sh", "radar-api.pse"))
    etc = laboratorio / "etc" if laboratorio else Path("/etc")
    permitidos.update((str(etc / "logrotate.d" / "openclaw-radar"),
                       str(etc / "sudoers.d" / "radar-configuracao"), str(dirs["conf"]) + ".painel"))
    if not laboratorio:
        permitidos.update(item["alvo"] for item in indice if item.get("tipo") == "nginx"
                          and Path(item["alvo"]).is_relative_to(Path("/etc/nginx"))
                          and Path(item["alvo"]).resolve() == Path(item["alvo"]))
    if any(item["alvo"] not in permitidos or Path(item["copia"]).parent != backup for item in indice):
        raise RuntimeError("Manifesto de recuperacao invalido.")
    with open(dirs["dados"] / "instalacao.lock", "a") as trava, open(dirs["dados"] / "tick.lock", "a") as tick:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(tick, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _restaurar(indice)
        if not laboratorio and any(item.get("tipo") == "nginx" for item in indice):
            _executar(["nginx", "-t"])
            _executar(["systemctl", "reload", "nginx"])
        cron_antigo = backup / "crontab-anterior.txt"
        if not laboratorio and cron_antigo.is_file():
            _recuperar_cron(cron_antigo, dirs["codigo"].parent / "radar-tick.sh")
        if not laboratorio:
            for nome in ('root', usuario_web):
                arquivo = backup / ('crontab-' + nome + '-anterior.txt')
                if arquivo.is_file():
                    _recuperar_cron(arquivo, dirs["codigo"].parent / "radar-tick.sh", nome)
    print("Codigo, paginas, wrappers e configuracao restaurados. Banco atual preservado. Backup: " + str(backup))
    return 0


def _recuperar_cron(cron_antigo, wrapper, usuario="root"):
    atual = auditoria.ler_crontab(usuario)
    # Recupera somente a linha do coletor, preservando outros projetos.
    def chama_tick(linha):
        return auditoria.comando_coletor(linha, wrapper) or auditoria.comando_fila(linha)
    linhas = [l for l in atual.splitlines() if not chama_tick(l)]
    linhas.extend(l for l in cron_antigo.read_text().splitlines() if chama_tick(l))
    _executar(["crontab", "-u", usuario, "-"], input="\n".join(linhas) + "\n")


def _preparar_servicos(observacoes=None):
    observacoes = observacoes if observacoes is not None else []
    checagens = auditoria.ambiente_servidor()
    erros = [c for c in checagens if c["estado"] == "erro" and not c["checagem"].startswith("servico.")]
    if erros:
        raise RuntimeError("Pre-requisitos: " + "; ".join(c["checagem"] + ": " + c["detalhe"] for c in erros))
    for alternativas in (("cron.service", "crond.service"), ("nginx.service",),
                          ("fcgiwrap.socket", "fcgiwrap.service")):
        for unidade in alternativas:
            ativo = subprocess.run(["systemctl", "is-active", unidade], capture_output=True, timeout=15)
            atualizacoes.evento("servico.consulta", unidade=unidade, codigo_comando=ativo.returncode,
                               codigo_esperado=ativo.returncode in (0, 3, 4),
                               stdout=ativo.stdout, stderr=ativo.stderr)
            if ativo.returncode == 0:
                break
        else:
            for unidade in alternativas:
                r = subprocess.run(["systemctl", "start", unidade], capture_output=True, timeout=30)
                atualizacoes.evento("servico.iniciar", unidade=unidade, codigo_comando=r.returncode,
                                   stdout=r.stdout, stderr=r.stderr)
                if r.returncode == 0:
                    observacoes.append("Servico iniciado: " + unidade)
                    break
            else:
                raise RuntimeError("Nao foi possivel iniciar " + "/".join(alternativas))


def _diagnosticar(origem, dirs, usuario_web, laboratorio, cron, final=False):
    checagens = auditoria.ambiente_servidor(bool(laboratorio))
    versao = _executar(["git", "-C", str(origem), "rev-parse", "HEAD"]).strip()
    instalada = (dirs["codigo"] / "VERSAO").read_text().strip() if (dirs["codigo"] / "VERSAO").is_file() else None
    divergencias = auditoria.arquivos_divergentes(origem, dirs, CODIGO, ESTATICOS)
    checagens.append({"checagem": "arquivos_do_aplicativo", "estado": "ok" if not divergencias else "erro" if final else "atualizar",
                      "detalhe": "%d arquivo(s) ausente(s) ou diferente(s)" % len(divergencias)})
    texto = dirs["conf"].read_text() if dirs["conf"].exists() else ""
    faltantes = auditoria.opcoes_faltantes(texto)
    gravadas = auditoria.chaves_gravadas(texto)
    faltantes.update({par: valor for par, valor in caminhos._ler_conf()[0].items()
                     if par not in gravadas and par[0] != "sincronizacao"})
    checagens.append({"checagem": "radar.conf", "estado": "ok" if not faltantes else "erro" if final else "atualizar",
                      "detalhe": "novas opcoes: " + ", ".join("%s.%s" % par for par in faltantes) if faltantes else "esquema atualizado"})
    checagens.append({"checagem": "versao", "estado": "ok" if instalada == versao else "erro" if final else "atualizar",
                      "detalhe": "instalada=%s; disponivel=%s" % (instalada or "sem registro", versao)})
    grupo = pwd.getpwnam(usuario_web).pw_gid
    pastas = [str(p) for p in _pastas_operacionais(dirs)
              if not p.is_dir() or p.stat().st_mode & 0o7777 != 0o2770 or
              (os.geteuid() == 0 and p.stat().st_gid != grupo)]
    checagens.append({"checagem": "diretorios", "estado": "erro" if final and pastas else "atualizar" if pastas else "ok",
                      "detalhe": "Criar/ajustar: " + ", ".join(pastas) if pastas else "pastas operacionais e permissoes corretas"})
    if cron and not laboratorio and shutil.which("crontab"):
        from .raiz_web import _checagens_cron
        checagens.extend(_checagens_cron(dirs["codigo"].parent, dirs["web"], usuario_web, dirs["conf"], final))
    if final:
        api = dirs["web"] / "api.pse"
        try:
            cmd = ([] if laboratorio else ["runuser", "-u", usuario_web, "--"]) + [sys.executable,str(api),"fila","verificar"]
            _executar(cmd,env=_ambiente(dirs["conf"]))
            checagens.append({"checagem":"fila.recebimento", "estado":"ok", "detalhe":"gravacao duravel da fila pelo usuario CGI, sem SQLite"})
        except (OSError, subprocess.SubprocessError) as exc:
            checagens.append({"checagem":"fila.recebimento", "estado":"erro", "detalhe":str(exc), "traceback":traceback.format_exc()})
        try:
            _cgi(api, dirs["conf"], "/health/ready", usuario=None if laboratorio else usuario_web)
            _cgi(api, dirs["conf"], "/api/v1/status", usuario=None if laboratorio else usuario_web)
            checagens.append({"checagem": "api_e_banco", "estado": "ok", "detalhe": "prontidao e consulta do banco pela API"})
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            checagens.append({"checagem": "api_e_banco", "estado": "erro", "detalhe": str(exc), "traceback": traceback.format_exc()})
        origem_http = caminhos.valor("web", "origem")[0]
        if origem_http and not laboratorio:
            try:
                auditoria.verificar_http(origem_http, caminhos.web_url(), dirs["web"] / "resources/gestao.html", configuracao_privada=True)
                checagens.append({"checagem": "http.publico", "estado": "ok", "detalhe": "API e pagina acessiveis; download direto de radar.conf bloqueado"})
            except Exception as exc:
                checagens.append({"checagem": "http.publico", "estado": "erro", "detalhe": "Checagem HTTP de API, pagina e configuracao: " + str(exc)[:1000]})
        else:
            checagens.append({"checagem": "http.publico", "estado": "nao_aplicavel", "detalhe": "Laboratorio ou web.origem vazia; acesso HTTP externo nao verificado."})
        etc = laboratorio / "etc" if laboratorio else Path("/etc")
        logrotate = etc / "logrotate.d" / "openclaw-radar"
        esperado = auditoria.render_logrotate(origem, dirs["logs"])
        checagens.append({"checagem": "logrotate", "estado": "ok" if logrotate.is_file() and logrotate.read_text() == esperado else "erro",
                          "detalhe": "rotacao dos logs conforme radar.conf"})
        executaveis = (dirs["web"] / "api.pse", dirs["codigo"].parent / "radar-tick.sh", dirs["codigo"].parent / "radar-api.pse")
        checagens.append({"checagem": "permissoes", "estado": "ok" if all(os.access(p, os.X_OK) for p in executaveis)
                          and dirs["conf"].stat().st_mode & 0o777 == 0o660
                          and dirs["conf"].parent.stat().st_mode & 0o7777 == 0o2770 else "erro",
                          "detalhe": "entradas executaveis; configuracao 0660 e pasta 2770 para o CGI"})
        link = dirs["web"] / "radar.conf"
        from .configuracao import link_aponta_configuracao
        checagens.append({"checagem": "configuracao.link", "estado": "ok" if link_aponta_configuracao(link, dirs["conf"]) else "erro",
                          "detalhe": str(link) + " -> " + str(dirs["conf"])})
        try:
            _verificar_gravacao(dirs, usuario=None if laboratorio else usuario_web)
            checagens.append({"checagem": "gravacao_do_painel", "estado": "ok", "detalhe": "CGI le o link e cria arquivo na pasta da configuracao sem elevacao"})
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            checagens.append({"checagem": "gravacao_do_painel", "estado": "erro", "detalhe": str(exc), "traceback": traceback.format_exc()})
        if not laboratorio:
            checagens.append(auditoria.validar_logrotate(logrotate))
            try:
                from .protecao_configuracao import planejar
                pendencias = planejar(caminhos.web_url(), dirs["web"], origem_http)
                checagens.append({"checagem": "nginx.configuracao_privada", "estado": "erro" if pendencias else "ok",
                                  "detalhe": "link radar.conf bloqueado para acesso HTTP direto" if not pendencias else "Reaplique para proteger o link da configuracao no nginx"})
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                checagens.append({"checagem": "nginx.configuracao_privada", "estado": "erro", "detalhe": str(exc)})
    return {"sucesso": not any(c["estado"] == "erro" for c in checagens),
            "atualizacao_necessaria": bool(divergencias or faltantes or pastas or instalada != versao or any(
                c["estado"] in ("erro", "atualizar") and c["checagem"] in
                ("cron.coletor", "cron.fila", "fila.recebimento", "logrotate", "logrotate.sintaxe", "permissoes", "gravacao_do_painel", "configuracao.link", "nginx.configuracao_privada") for c in checagens)),
            "modo": "verificacao" if final else "planejamento",
            "versao_instalada": instalada, "versao_disponivel": versao,
            "arquivos_divergentes": divergencias, "checagens": checagens}
