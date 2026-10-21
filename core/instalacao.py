"""Instalacao local coordenada, chamada por api.pse e pelo instalador privado.

O servidor e descrito no radar.conf, nunca neste modulo. Nao baixa credenciais,
nao restaura o banco automaticamente e nao executa material de referencia/.
"""
import argparse
from contextlib import closing
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time

from . import caminhos, db
from . import auditoria_instalacao as auditoria
from .contexto_api import operacao_local
from .governanca import GovernancaError

CODIGO = ("core", "coletor", "config", "sql", "web", "deploy", "tools")
ESTATICOS = {".html", ".json", ".png", ".ico", ".css", ".js", ".svg"}


def _executar(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          timeout=120, **kwargs).stdout


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
    if dirs["codigo"].exists() and not (dirs["codigo"] / "core").is_dir():
        raise RuntimeError("Destino do codigo ocupado por outra aplicacao.")
    if not dirs["banco"].is_file():
        raise RuntimeError("O banco configurado nao existe. Este instalador atualiza o servidor existente e nao cria base vazia.")
    # Nao permite montar uma arvore de configuracao publica por link.
    if dirs["web"].is_dir():
        for item in dirs["web"].rglob("*"):
            if item.is_symlink():
                raise RuntimeError("Revise o link existente no webroot antes de instalar: " + str(item))
    return dirs


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


def _permissoes(arvore, gid, gravavel=False):
    for item in [arvore, *arvore.rglob("*")]:
        if item.is_symlink():
            raise RuntimeError("Symlink inesperado: " + str(item))
        if os.geteuid() == 0:
            os.chown(item, 0, gid)
        item.chmod((0o2770 if gravavel else 0o755) if item.is_dir() else
                   (0o660 if gravavel else 0o644))


def _cron_tick(texto, wrapper):
    linhas = []
    for linha in texto.splitlines():
        # Troca somente a linha ativa que chama exatamente este wrapper.
        if auditoria.comando_coletor(linha, wrapper):
            continue
        linhas.append(linha)
    # O wrapper nao contem caminhos variaveis de dados ou log.
    linhas.append("* * * * * " + str(wrapper))
    return "\n".join(linhas) + "\n"


def _aplicar(origem, dirs, usuario_web, laboratorio, cron, origem_http=None):
    if not laboratorio and os.geteuid() != 0:
        raise RuntimeError("Execute como root para aplicar no servidor.")
    conta = pwd.getpwnam(usuario_web)
    grupo = conta.pw_gid
    agora = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = dirs["dados"] / "backups" / "instalacao" / agora
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    indice = []
    wrapper = dirs["codigo"].parent / "radar-tick.sh"
    entrada_cron = wrapper.with_name("radar-api.pse")
    logrotate = (laboratorio / "etc" if laboratorio else Path("/etc")) / "logrotate.d" / "openclaw-radar"
    sudoers = (laboratorio / "etc" if laboratorio else Path("/etc")) / "sudoers.d" / "radar-configuracao"
    with open(dirs["dados"] / "instalacao.lock", "a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for alvo in (dirs["codigo"], dirs["web"], dirs["conf"], wrapper, entrada_cron,
                         logrotate, sudoers, Path(str(dirs["conf"]) + ".painel")):
                alvo.parent.mkdir(parents=True, exist_ok=True)
                _guardar(alvo, backup, indice)
            (backup / "restauracao.json").write_text(json.dumps(indice, indent=2))
            # Pausa novas chamadas CGI e tick durante a troca coordenada.
            dirs["web"].mkdir(parents=True, exist_ok=True)
            (dirs["web"] / "api.pse").write_text(
                "#!" + sys.executable + "\nprint('Status: 503 Service Unavailable\\r\\nRetry-After: 30\\r\\nContent-Type: text/plain\\r\\n\\r\\nAtualizacao em andamento.')\n")
            (dirs["web"] / "api.pse").chmod(0o755)
            wrapper.write_text("#!/bin/sh\n# Atualizacao coordenada em andamento.\nexit 0\n")
            wrapper.chmod(0o755)
            with open(dirs["dados"] / "tick.lock", "a") as tick:
                _esperar_coletor(tick)
                with closing(db.connect_readonly(dirs["banco"])) as fonte:
                    if fonte.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("Integridade do banco reprovada; nada sera atualizado.")
                    if fonte.execute("PRAGMA foreign_key_check").fetchone() is not None:
                        raise RuntimeError("Banco com referencias invalidas; nenhuma atualizacao foi aplicada.")
                    with closing(db.connect(backup / "radar.sqlite3")) as copia:
                        fonte.backup(copia)
                        copia.execute("PRAGMA journal_mode=DELETE")
                (backup / "radar.sqlite3").chmod(0o600)
                _instalar_arquivos(origem, dirs, grupo, usuario_web, backup, origem_http)
                _instalar_helper(dirs, usuario_web, sudoers, laboratorio)
                logrotate.write_text(auditoria.render_logrotate(origem, dirs["logs"]))
                logrotate.chmod(0o644)
                api = dirs["web"] / "api.pse"
                # Inicializacao/migracoes continuam passando pela mesma entrada.
                _executar([sys.executable, str(api), "ferramenta", "inicializar_banco"],
                          env=_ambiente(dirs["conf"]))
                _cgi(api, dirs["conf"], "/health/ready")
                _cgi(api, dirs["conf"], "/api/v1/ajuda")
                _executar([sys.executable, str(api), "configuracao", "mostrar"], env=_ambiente(dirs["conf"]))
                shutil.copy2(origem / "deploy" / "api.pse", entrada_cron)
                entrada_cron.write_text(entrada_cron.read_text().replace("#!/usr/bin/env python3", "#!" + sys.executable, 1).replace(
                    'CONF_PADRAO = "/etc/radar-brasil/radar.conf"', 'CONF_PADRAO = ' + repr(str(dirs["conf"])), 1))
                entrada_cron.chmod(0o755)
                shutil.copy2(origem / "deploy" / "radar-tick.sh", wrapper)
                # O interpretador testado e fixado apenas no bootstrap do cron.
                wrapper.write_text(wrapper.read_text().replace(
                    '${RADAR_PYTHON:-/usr/bin/python3}', '${RADAR_PYTHON:-' + sys.executable + '}'))
                wrapper.chmod(0o755)
            if not laboratorio:
                # Testa as permissoes reais do usuario CGI, nao somente root.
                _executar(["runuser", "-u", usuario_web, "--", sys.executable,
                           str(dirs["web"] / "api.pse"), "configuracao", "mostrar"],
                          env=_ambiente(dirs["conf"]))
                _cgi(dirs["web"] / "api.pse", dirs["conf"], "/health/ready", usuario=usuario_web)
            if cron and not laboratorio:
                atual = auditoria.ler_crontab()
                (backup / "crontab-anterior.txt").write_text(atual)
                esperado = _cron_tick(atual, wrapper)
                _executar(["crontab", "-"], input=esperado)
                if auditoria.ler_crontab() != esperado:
                    raise RuntimeError("Crontab gravado diverge do esperado.")
            relatorio = _diagnosticar(origem, dirs, usuario_web, laboratorio, cron, final=True)
            relatorio["backup"] = str(backup)
            (backup / "checagem-final.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
            if not relatorio["sucesso"]:
                raise RuntimeError("Checagem final reprovada; consulte checagem-final.json no backup.")
            (backup / "CONCLUIDO").write_text(agora + "\n")
            print("Instalacao concluida. Backup: " + str(backup))
        except BaseException:
            _restaurar(indice)
            if not laboratorio and (backup / "crontab-anterior.txt").is_file():
                _recuperar_cron(backup / "crontab-anterior.txt", wrapper)
            print("Falha: codigo, web, wrappers e conf restaurados. Banco preservado; backup em " + str(backup), file=sys.stderr)
            raise
    return relatorio


def _instalar_arquivos(origem, dirs, grupo, usuario_web, backup, origem_http=None):
    nova = Path(tempfile.mkdtemp(prefix=".radar-novo-", dir=dirs["codigo"].parent))
    try:
        for pasta in CODIGO:
            shutil.copytree(origem / pasta, nova / pasta,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for nome in ("README.md", "LICENSE"):
            shutil.copy2(origem / nome, nova / nome)
        bootstrap_local = nova / "web" / "api.pse"
        bootstrap_local.write_text(bootstrap_local.read_text().replace(
            'CONF_PADRAO = "/etc/radar-brasil/radar.conf"', 'CONF_PADRAO = ' + repr(str(dirs["conf"])), 1))
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
        if not conf.exists():
            shutil.copy2(caminhos.conf_path(), conf)
        # Migra parametros antigos de governanca sem substituir opcoes do .conf.
        antigo = backup / "item-00" / "config" / "governanca.json"
        existentes = auditoria.chaves_gravadas(conf.read_text())
        if antigo.is_file():
            valores = json.loads(antigo.read_text())
            faltantes = {k.lower(): str(v) for k, v in valores.items()
                         if k.lower() in caminhos.SECOES["governanca"] and
                         ("governanca", k.lower()) not in existentes}
            if faltantes:
                with conf.open("a") as saida:
                    saida.write("\n[governanca]\n")
                    for k, v in faltantes.items():
                        saida.write(k + " = " + v + "\n")
        # Completa o esquema novo sem substituir valores ou chaves vazias do servidor.
        from .configuracao import _editar
        if origem_http and ("web", "origem") not in auditoria.chaves_gravadas(conf.read_text()):
            conf.write_text(_editar(conf.read_text(), {("web", "origem"): origem_http}))
        faltantes = auditoria.opcoes_faltantes(conf.read_text())
        if faltantes:
            conf.write_text(_editar(conf.read_text(), faltantes))
        caminhos.recarregar()
        if os.geteuid() == 0:
            os.chown(conf.parent, 0, 0)
            os.chown(conf, 0, 0)
        conf.parent.chmod(0o755)
        conf.chmod(0o644)
        for nome in ("dados", "logs"):
            dirs[nome].mkdir(parents=True, exist_ok=True)
        for pasta in (dirs["dados"], dirs["logs"], dirs["dados"] / "raw",
                      dirs["dados"] / "staging", dirs["dados"] / "calibracao",
                      dirs["banco"].parent):
            pasta.mkdir(parents=True, exist_ok=True)
            if os.geteuid() == 0:
                os.chown(pasta, -1, grupo)
            pasta.chmod(0o2770)
        for arquivo in [dirs["banco"], *dirs["banco"].parent.glob(dirs["banco"].name + "-*")]:
            if os.geteuid() == 0:
                os.chown(arquivo, -1, grupo)
            arquivo.chmod(0o660)
        for arquivo in (origem / "web").iterdir():
            if arquivo.is_file() and arquivo.suffix in ESTATICOS:
                shutil.copy2(arquivo, dirs["web"] / arquivo.name)
        projeto = dirs["web"] / "projeto.json"
        descritor = json.loads(projeto.read_text())
        descritor["url"] = caminhos.web_url()
        projeto.write_text(json.dumps(descritor, ensure_ascii=False, indent=2) + "\n")
        # O .pse do deploy e o unico Python publicado no webroot.
        shutil.copy2(origem / "deploy" / "api.pse", dirs["web"] / "api.pse")
        api = dirs["web"] / "api.pse"
        api.write_text(api.read_text().replace("#!/usr/bin/env python3", "#!" + sys.executable, 1).replace(
            'CONF_PADRAO = "/etc/radar-brasil/radar.conf"', 'CONF_PADRAO = ' + repr(str(dirs["conf"])), 1))
        for arquivo in dirs["web"].iterdir():
            if arquivo.is_file() and arquivo.suffix in (".py", ".pyc"):
                raise RuntimeError("Remova fontes Python antigos do webroot antes de instalar: " + arquivo.name)
        _permissoes(dirs["web"], grupo)
        api.chmod(0o755)
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


def _instalar_helper(dirs, usuario, sudoers, laboratorio):
    # O CGI nao ganha escrita na pasta /etc nem permissao geral de root.
    # O comando autorizado so salva as chaves operacionais validadas pela API.
    comando = [sys.executable, str(dirs["codigo"] / "web" / "api.pse"),
               "configuracao", "salvar-web", "--conf", str(dirs["conf"])]
    if any(not re.fullmatch(r"[A-Za-z0-9_./-]+", parte) for parte in [usuario, *comando]):
        raise RuntimeError("Caminho ou usuario incompativel com a regra restrita do sudoers.")
    conteudo = usuario + " ALL=(root) NOPASSWD: NOSETENV: " + " ".join(comando) + "\n"
    if not laboratorio:
        if not shutil.which("sudo") or not shutil.which("visudo"):
            raise RuntimeError("Instale sudo/visudo para habilitar o salvamento seguro pelo painel.")
        if os.stat(sys.executable).st_uid != 0 or os.stat(sys.executable).st_mode & 0o022:
            raise RuntimeError("O interpretador do helper deve pertencer a root e nao permitir escrita por terceiros.")
        with tempfile.NamedTemporaryFile(mode="w", dir=sudoers.parent, delete=False) as arquivo:
            arquivo.write(conteudo)
            candidato = Path(arquivo.name)
        try:
            candidato.chmod(0o440)
            _executar(["visudo", "-cf", str(candidato)])
            candidato.replace(sudoers)
        finally:
            candidato.unlink(missing_ok=True)
    else:
        # Laboratorio nao configura sudo nem anuncia o painel como habilitado.
        sudoers.unlink(missing_ok=True)
        sudoers.write_text("# Simulacao da regra de producao:\n# " + conteudo)
    sudoers.chmod(0o440)
    if not laboratorio:
        arq = dirs["conf"]
        revisao = hashlib.sha256(arq.read_bytes()).hexdigest()
        _executar(["runuser", "-u", usuario, "--", "sudo", "-n", "--", *comando],
                  input=json.dumps({"revisao": revisao, "alteracoes": {}}))
        Path(str(arq) + ".painel").write_text("Gravacao restrita pela API administrativa.\n")
        Path(str(arq) + ".painel").chmod(0o644)


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description="Atualiza a instalacao descrita no radar.conf; padrao: simular.")
    parser.add_argument("--conf", required=True, type=Path)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--aplicar", action="store_true")
    parser.add_argument("--usuario-web", default="www-data")
    parser.add_argument("--laboratorio", type=Path, help="restringe destinos a esta pasta e nao altera cron do sistema")
    parser.add_argument("--sem-cron", action="store_true")
    parser.add_argument("--origem-http", help="origem inicial da consulta HTTP; usada somente se web.origem ainda nao existe")
    modo.add_argument("--verificar", action="store_true", help="audita a instalacao atual, sem copiar arquivos")
    parser.add_argument("--relatorio", type=Path, help="salva a checagem em JSON no arquivo indicado")
    modo.add_argument("--restaurar", type=Path, help="restaura codigo/web/configuracao de um backup; nunca restaura banco automaticamente")
    args = parser.parse_args(argv)
    try:
        origem = Path(caminhos.ROOT)
        lab = args.laboratorio.resolve() if args.laboratorio else None
        dirs = _validar_layout(origem, args.conf.absolute(), lab)
        if args.restaurar:
            return _recuperar(args.restaurar, dirs, lab)
        print(json.dumps({"acao": "aplicar" if args.aplicar else "simular",
                          "destinos": {k: str(v) for k, v in dirs.items()},
                          "usuario_web": args.usuario_web,
                          "cron_tick": not args.sem_cron and not bool(lab)}, indent=2))
        if args.aplicar:
            if not lab and os.geteuid() != 0:
                raise RuntimeError("Execute com sudo para aplicar no servidor.")
            if args.origem_http:
                from .configuracao import _validar
                _validar({("web", "origem"): args.origem_http})
            if not lab:
                _preparar_servicos()
            plano = _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron)
            precisa = plano["atualizacao_necessaria"] or any(c["estado"] in ("erro", "atualizar") for c in plano["checagens"])
            relatorio = None if precisa else _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron, final=True)
            if relatorio is not None and relatorio["sucesso"]:
                relatorio["acao"] = "sem_alteracoes"
                print("Instalacao ja atualizada; checagens aprovadas, sem nova copia ou backup.")
            else:
                relatorio = _aplicar(origem, dirs, args.usuario_web, lab, not args.sem_cron, args.origem_http)
            resultado = 0
        else:
            relatorio = _diagnosticar(origem, dirs, args.usuario_web, lab, not args.sem_cron,
                                     final=args.verificar)
            resultado = 0 if not args.verificar or relatorio["sucesso"] else 1
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        if args.relatorio:
            args.relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
        if not args.aplicar:
            print("Checagem concluida. Nenhum arquivo da instalacao foi alterado.")
        return resultado
    except (OSError, ValueError, KeyError, RuntimeError, GovernancaError, subprocess.SubprocessError) as exc:
        print("Instalacao recusada: " + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr[:2000], file=sys.stderr)
        return 1


def _recuperar(backup, dirs, laboratorio):
    if not laboratorio and os.geteuid() != 0:
        raise RuntimeError("Execute a recuperacao como root.")
    backup = backup.resolve(strict=True)
    raiz = (dirs["dados"] / "backups" / "instalacao").resolve()
    if backup.parent != raiz:
        raise RuntimeError("Use um backup desta instalacao, dentro de dados/backups/instalacao.")
    indice = json.loads((backup / "restauracao.json").read_text())
    permitidos = {str(dirs[n]) for n in ("codigo", "web", "conf")}
    permitidos.update(str(dirs["codigo"].parent / n) for n in ("radar-tick.sh", "radar-api.pse"))
    etc = laboratorio / "etc" if laboratorio else Path("/etc")
    permitidos.update((str(etc / "logrotate.d" / "openclaw-radar"),
                       str(etc / "sudoers.d" / "radar-configuracao"), str(dirs["conf"]) + ".painel"))
    if any(item["alvo"] not in permitidos or Path(item["copia"]).parent != backup for item in indice):
        raise RuntimeError("Manifesto de recuperacao invalido.")
    with open(dirs["dados"] / "instalacao.lock", "a") as trava, open(dirs["dados"] / "tick.lock", "a") as tick:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(tick, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _restaurar(indice)
        cron_antigo = backup / "crontab-anterior.txt"
        if not laboratorio and cron_antigo.is_file():
            _recuperar_cron(cron_antigo, dirs["codigo"].parent / "radar-tick.sh")
    print("Codigo, paginas, wrappers e configuracao restaurados. Banco atual preservado. Backup: " + str(backup))
    return 0


def _recuperar_cron(cron_antigo, wrapper):
    atual = auditoria.ler_crontab()
    # Recupera somente a linha do coletor, preservando outros projetos.
    def chama_tick(linha):
        return auditoria.comando_coletor(linha, wrapper)
    linhas = [l for l in atual.splitlines() if not chama_tick(l)]
    linhas.extend(l for l in cron_antigo.read_text().splitlines() if chama_tick(l))
    _executar(["crontab", "-"], input="\n".join(linhas) + "\n")


def _preparar_servicos():
    checagens = auditoria.ambiente_servidor()
    erros = [c for c in checagens if c["estado"] == "erro" and not c["checagem"].startswith("servico.")]
    if erros:
        raise RuntimeError("Pre-requisitos: " + "; ".join(c["checagem"] + ": " + c["detalhe"] for c in erros))
    for alternativas in (("cron.service", "crond.service"), ("nginx.service",),
                          ("fcgiwrap.socket", "fcgiwrap.service")):
        for unidade in alternativas:
            ativo = subprocess.run(["systemctl", "is-active", unidade], capture_output=True, timeout=15)
            if ativo.returncode == 0:
                break
        else:
            for unidade in alternativas:
                r = subprocess.run(["systemctl", "start", unidade], capture_output=True, timeout=30)
                if r.returncode == 0:
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
    faltantes = auditoria.opcoes_faltantes(dirs["conf"].read_text() if dirs["conf"].exists() else Path(caminhos.conf_path()).read_text())
    checagens.append({"checagem": "radar.conf", "estado": "ok" if not faltantes else "erro" if final else "atualizar",
                      "detalhe": "novas opcoes: " + ", ".join("%s.%s" % par for par in faltantes) if faltantes else "esquema atualizado"})
    checagens.append({"checagem": "versao", "estado": "ok" if instalada == versao else "erro" if final else "atualizar",
                      "detalhe": "instalada=%s; disponivel=%s" % (instalada or "sem registro", versao)})
    if cron and not laboratorio and shutil.which("crontab"):
        atual = auditoria.ler_crontab()
        esperado = _cron_tick(atual, dirs["codigo"].parent / "radar-tick.sh")
        checagens.append({"checagem": "cron.coletor", "estado": "ok" if atual == esperado else "erro" if final else "atualizar",
                          "detalhe": "uma passada por minuto; rotinas externas preservadas"})
    if final:
        api = dirs["web"] / "api.pse"
        try:
            _cgi(api, dirs["conf"], "/health/ready", usuario=None if laboratorio else usuario_web)
            _cgi(api, dirs["conf"], "/api/v1/status", usuario=None if laboratorio else usuario_web)
            checagens.append({"checagem": "api_e_banco", "estado": "ok", "detalhe": "prontidao e consulta do banco pela API"})
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            checagens.append({"checagem": "api_e_banco", "estado": "erro", "detalhe": "API instalada nao passou na checagem"})
        origem_http = caminhos.valor("web", "origem")[0]
        if origem_http and not laboratorio:
            try:
                auditoria.verificar_http(origem_http, caminhos.web_url(), dirs["web"] / "gestao.html")
                checagens.append({"checagem": "http.publico", "estado": "ok", "detalhe": "API pronta e pagina atualizada acessiveis pelo nginx"})
            except Exception:
                checagens.append({"checagem": "http.publico", "estado": "erro", "detalhe": "Nao foi possivel confirmar API e pagina em web.origem + web.url; confira DNS, TLS e roteamento do nginx."})
        else:
            checagens.append({"checagem": "http.publico", "estado": "nao_aplicavel", "detalhe": "Laboratorio ou web.origem vazia; acesso HTTP externo nao verificado."})
        etc = laboratorio / "etc" if laboratorio else Path("/etc")
        logrotate = etc / "logrotate.d" / "openclaw-radar"
        esperado = auditoria.render_logrotate(origem, dirs["logs"])
        checagens.append({"checagem": "logrotate", "estado": "ok" if logrotate.is_file() and logrotate.read_text() == esperado else "erro",
                          "detalhe": "rotacao dos logs conforme radar.conf"})
        executaveis = (dirs["web"] / "api.pse", dirs["codigo"].parent / "radar-tick.sh", dirs["codigo"].parent / "radar-api.pse")
        checagens.append({"checagem": "permissoes", "estado": "ok" if all(os.access(p, os.X_OK) for p in executaveis)
                          and not dirs["conf"].stat().st_mode & 0o022 else "erro",
                          "detalhe": "entradas executaveis; configuracao sem escrita por grupo/outros"})
        if not laboratorio:
            checagens.append(auditoria.validar_logrotate(logrotate))
            try:
                arq = dirs["conf"]
                comando = [sys.executable, str(dirs["codigo"] / "web" / "api.pse"),
                           "configuracao", "salvar-web", "--conf", str(arq)]
                _executar(["runuser", "-u", usuario_web, "--", "sudo", "-n", "--", *comando],
                          input=json.dumps({"revisao": hashlib.sha256(arq.read_bytes()).hexdigest(), "alteracoes": {}}))
                checagens.append({"checagem": "gravacao_do_painel", "estado": "ok", "detalhe": "usuario CGI autorizado somente para o comando restrito"})
            except (OSError, subprocess.SubprocessError):
                checagens.append({"checagem": "gravacao_do_painel", "estado": "erro", "detalhe": "autorizacao do painel indisponivel"})
    return {"sucesso": not any(c["estado"] == "erro" for c in checagens),
            "atualizacao_necessaria": bool(divergencias or faltantes or instalada != versao),
            "modo": "verificacao" if final else "planejamento",
            "versao_instalada": instalada, "versao_disponivel": versao,
            "arquivos_divergentes": divergencias, "checagens": checagens}
