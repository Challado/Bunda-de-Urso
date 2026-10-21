"""Leitura e gravacao do radar.conf usadas exclusivamente pela entrada API.

Nao recebe nome de arquivo do cliente, nao revela tokens, nao move dados.
Gravacao exige revisao atual, trava entre processos e substituicao atomica.
"""
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.parse

from . import caminhos
from .governanca import GovernancaError
from .contexto_api import operacao_local

CAMINHOS = {("instalacao", "home"), ("dados", "dir"), ("dados", "banco"),
            ("web", "raiz"), ("logs", "dir"), ("sincronizacao", "clone"),
            ("api", "token_arquivo"), ("geografia", "malha")}
CAMINHOS.add(("assistente", "chave_arquivo"))
NUMEROS = {**{("governanca", k): (1, 1000000000)
              for k in caminhos.SECOES["governanca"]},
           ("api", "max_body"): (1024, 67108864),
           ("coleta", "max_bytes"): (1024, 1073741824),
           ("coleta", "timeout"): (1, 300),
           ("coleta", "tentativas"): (1, 10),
           ("coleta", "espera_atualizacao"): (1, 3600),
           ("governanca", "gov_iteracoes"): (200000, 2000000)}
NUMEROS.update({("assistente", k): limites for k, limites in {
    "habilitado": (0, 1), "timeout": (1, 60), "max_entrada": (1000, 60000),
    "max_saida_tokens": (128, 4096), "max_chamadas": (1, 100),
    **{k: (0, 1) for k in ("documentos", "correspondencias", "auditoria", "diagnostico", "explicacoes", "municipios")},
}.items()})
NUMEROS.update({("cadastro", k): limites for k, limites in {
    "max_itens": (1, 1000), "max_bytes": (1024, 1048576), "max_pendentes": (1, 100000),
    "lote": (1, 1000), "tentativas": (1, 20), "retencao_dias": (1, 365),
}.items()})
EDITAVEIS_WEB = set(NUMEROS) | {("api", "proxies_confiaveis"),
                              ("assistente", "provedor"), ("assistente", "url"), ("assistente", "modelo")}


def _erro(status, codigo, mensagem):
    raise GovernancaError(status, codigo, mensagem)


def link_aponta_configuracao(link, arquivo):
    try:
        return link.is_symlink() and link.resolve(strict=True) == arquivo.resolve(strict=True)
    except (OSError, RuntimeError):
        return False


def _arquivo(web=False):
    arq = Path(caminhos.conf_path()).absolute()
    if arq.is_symlink() or not arq.is_file():
        _erro(503, "configuracao_indisponivel",
              "Instale um radar.conf regular antes de configurar pelo painel.")
    if arq.stat().st_size > 65536:
        _erro(503, "configuracao_invalida", "radar.conf excede 64 KiB.")
    if web:
        link = Path(caminhos.web_raiz()) / "radar.conf"
        if not link_aponta_configuracao(link, arq):
            _erro(503, "configuracao_indisponivel", "Execute o instalador para preparar o link radar.conf do painel.")
        # A escrita atomica substitui o destino em /etc, preservando o link.
        arq = link.resolve(strict=True)
    return arq


def _revisao(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _permissao_auxiliar(fd, grupo):
    # O shell de root pode usar umask 077. Lock, backup e auditoria precisam
    # continuar gravaveis pelo CGI depois de uma edicao local.
    if os.geteuid() == 0 or os.fstat(fd).st_uid == os.geteuid():
        os.fchown(fd, -1, grupo)
        os.fchmod(fd, 0o660)


def consultar(web=False):
    arq = _arquivo(web)
    conteudo = arq.read_bytes()
    valores, _ = caminhos._ler_conf()
    efetivos = {(i["secao"], i["chave"]): i["valor"] for i in caminhos.resumo()}
    efetivos[("api", "token_arquivo")] = caminhos.token_arquivo()
    itens = []
    for secao, chaves in caminhos.SECOES.items():
        if secao == "sincronizacao":
            continue  # configuracao legada de operacao externa ao aplicativo
        for chave in chaves:
            par = secao, chave
            valor, origem = caminhos.valor(secao, chave)
            itens.append({"secao": secao, "chave": chave,
                          "valor": valores.get(par, ""),
                          "efetivo": efetivos.get(par, valor), "origem": origem,
                          "ambiente": caminhos._ENV.get(par),
                          "editavel": not web or par in EDITAVEIS_WEB,
                          "tipo": "numero" if par in NUMEROS else "texto"})
    return {"sucesso": True, "arquivo": str(arq),
            "revisao": _revisao(conteudo), "itens": itens,
            "gravavel": os.access(arq, os.R_OK | os.W_OK) and os.access(arq.parent, os.W_OK | os.X_OK),
            "problemas": caminhos.problemas()}


def _validar(valores):
    for par, texto in valores.items():
        if not isinstance(texto, str) or len(texto) > 2048 or any(
                ord(c) < 32 or ord(c) == 127 for c in texto):
            _erro(422, "valor_invalido", "Use texto de uma linha, ate 2048 caracteres.")
        if texto != texto.strip() or '"' in texto or "'" in texto:
            _erro(422, "valor_invalido", "Nao use aspas ou espacos nas extremidades.")
        if texto and par in CAMINHOS and not os.path.isabs(texto):
            _erro(422, "caminho_invalido", "Use caminhos absolutos ao editar pela API.")
        if texto and par in NUMEROS:
            minimo, maximo = NUMEROS[par]
            if not texto.isdecimal() or not minimo <= int(texto) <= maximo:
                _erro(422, "numero_invalido", "%s.%s: use %d..%d." % (*par, minimo, maximo))
        if par == ("assistente", "provedor") and texto not in ("", "ollama", "openai_compativel"):
            _erro(422, "provedor_invalido", "Use ollama ou openai_compativel.")
        if texto and par == ("api", "proxies_confiaveis"):
            try:
                for rede in texto.split(","):
                    ipaddress.ip_network(rede.strip(), strict=False)
            except ValueError:
                _erro(422, "proxy_invalido", "Informe IPs ou redes CIDR separados por virgula.")
        if texto and par in (("web", "url"), ("web", "origem"), ("sincronizacao", "remoto"), ("assistente", "url")):
            url = urllib.parse.urlsplit(texto)
            if url.username or url.password or url.query or url.fragment:
                _erro(422, "url_invalida", "URLs de configuracao nao podem conter credenciais ou parametros.")
            if par == ("web", "url"):
                if not texto.startswith("/") or texto.startswith("//"):
                    _erro(422, "url_invalida", "O prefixo web deve comecar com uma barra.")
            elif url.scheme not in ("https", "ssh", "http") or not url.netloc:
                _erro(422, "url_invalida", "Informe uma URL https, ssh ou http valida.")
            if par == ("web", "origem") and (url.scheme not in ("http", "https") or url.path not in ("", "/")):
                _erro(422, "url_invalida", "A origem web deve conter somente http(s)://host[:porta].")
            if par == ("assistente", "url") and url.scheme not in ("http", "https"):
                _erro(422, "url_invalida", "O assistente exige uma URL HTTP(S).")
    if any(par in valores for par in (("assistente", "provedor"), ("assistente", "url"))):
        provedor = valores.get(("assistente", "provedor")) or caminhos.valor("assistente", "provedor")[0]
        endereco = valores.get(("assistente", "url")) or caminhos.valor("assistente", "url")[0]
        url = urllib.parse.urlsplit(endereco)
        if provedor == "openai_compativel" and url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            _erro(422, "url_invalida", "A API externa exige HTTPS; HTTP e aceito somente para testes em localhost.")


def _editar(texto, alteracoes):
    """Preserva comentarios e valores existentes; acrescenta somente o pedido."""
    pendentes = dict(alteracoes)
    linhas, secao = [], None
    for linha in texto.splitlines(keepends=True):
        limpo = linha.strip()
        if limpo.startswith("[") and limpo.endswith("]"):
            secao = limpo[1:-1].strip().lower()
        elif limpo and not limpo.startswith(("#", ";")) and "=" in limpo:
            chave = limpo.split("=", 1)[0].strip().lower()
            par = secao, chave
            if par in pendentes:
                linha = "%s = %s\n" % (chave, pendentes.pop(par))
        linhas.append(linha)
    for secao in caminhos.SECOES:
        novos = [(chave, valor) for (s, chave), valor in pendentes.items() if s == secao]
        if novos:
            linhas.append("\n[%s]\n" % secao)
            linhas.extend("%s = %s\n" % item for item in novos)
    return "".join(linhas)


def _validar_destinos(alteracoes):
    # Evita perder o acesso por uma edicao acidental. Nunca cria/move o banco.
    consultas = {("instalacao", "home"): caminhos.home,
                 ("dados", "dir"): caminhos.data_dir,
                 ("dados", "banco"): caminhos.banco,
                 ("web", "raiz"): caminhos.web_raiz,
                 ("logs", "dir"): caminhos.log_dir}
    efetivos = {par: alteracoes.get(par) or obter() for par, obter in consultas.items()}
    existentes = caminhos._ler_conf()[0]
    if ("dados", "dir") in alteracoes and not alteracoes[("dados", "dir")]:
        efetivos[("dados", "dir")] = os.path.join(caminhos.ROOT, "dados")
    if (("dados", "banco") in alteracoes and not alteracoes[("dados", "banco")]) or (
            ("dados", "dir") in alteracoes and not existentes.get(("dados", "banco")) and
            ("dados", "banco") not in alteracoes):
        efetivos[("dados", "banco")] = os.path.join(efetivos[("dados", "dir")], "radar.sqlite3")
    efetivos[("api", "token_arquivo")] = alteracoes.get(("api", "token_arquivo")) or caminhos.token_arquivo()
    for par, texto in efetivos.items():
        if par not in alteracoes and not (par == ("dados", "banco") and ("dados", "dir") in alteracoes):
            continue
        destino = Path(texto)
        if not destino.exists():
            _erro(422, "destino_ausente", "%s.%s: prepare o destino no servidor antes de salvar." % par)
        if par == ("dados", "banco") and not destino.is_file():
            _erro(422, "destino_invalido", "O banco deve ser um arquivo existente.")
        if par in (("dados", "dir"), ("web", "raiz"), ("logs", "dir")) and not destino.is_dir():
            _erro(422, "destino_invalido", "O destino deve ser um diretorio existente.")
        if par == ("instalacao", "home") and not (destino / "core" / "entrada_api.py").is_file():
            _erro(422, "destino_invalido", "O destino do codigo deve conter core/entrada_api.py.")
        if par == ("web", "raiz") and not (destino / "api.pse").is_file():
            _erro(422, "destino_invalido", "O webroot deve conter api.pse.")
    web = Path(efetivos[("web", "raiz")]).resolve()
    for par in (("dados", "dir"), ("dados", "banco"), ("api", "token_arquivo")):
        texto = efetivos.get(par, caminhos.token_arquivo())
        if Path(texto).resolve().is_relative_to(web):
            _erro(422, "destino_publico", "Dados e segredos devem ficar fora do webroot.")
    if ("instalacao", "home") in alteracoes and not alteracoes[("instalacao", "home")]:
        _erro(422, "destino_invalido", "O caminho do codigo nao pode ser apagado pelo painel.")


def salvar(dados, autor="local", web=False):
    if not isinstance(dados, dict) or set(dados) != {"revisao", "alteracoes"}:
        _erro(422, "configuracao_invalida", "Informe revisao e alteracoes.")
    if not isinstance(dados["revisao"], str) or not isinstance(dados["alteracoes"], dict):
        _erro(422, "configuracao_invalida", "Revisao ou alteracoes invalidas.")
    alteracoes = {}
    for nome, valor in dados["alteracoes"].items():
        if not isinstance(nome, str) or "." not in nome:
            _erro(422, "chave_invalida", "Informe secao.chave.")
        secao, chave = nome.split(".", 1)
        if secao == "sincronizacao":
            _erro(422, "configuracao_externa", "O envio privado pertence ao servidor, fora das configuracoes do aplicativo.")
        if chave not in caminhos.SECOES.get(secao, ()):
            _erro(422, "chave_invalida", "Chave de configuracao desconhecida.")
        if web and (secao, chave) not in EDITAVEIS_WEB:
            _erro(403, "configuracao_local", "Caminhos, destinos e credenciais so podem ser alterados pela API local do servidor.")
        alteracoes[(secao, chave)] = valor
    _validar(alteracoes)
    arq = _arquivo(web)
    try:
        # Lock persistente: jamais remover, pois isso criaria travas independentes.
        fd = os.open(str(arq) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
        with os.fdopen(fd, "a") as trava:
            _permissao_auxiliar(trava.fileno(), arq.stat().st_gid)
            fcntl.flock(trava, fcntl.LOCK_EX)
            anterior = arq.read_bytes()
            if _revisao(anterior) != dados["revisao"]:
                _erro(409, "configuracao_alterada", "Outro administrador alterou o arquivo. Recarregue antes de salvar.")
            caminhos.recarregar()
            if caminhos.problemas():
                _erro(422, "configuracao_invalida", "Corrija os avisos do radar.conf antes de salvar pelo painel.")
            for par in alteracoes:
                if caminhos.valor(*par)[1].startswith("ambiente"):
                    _erro(409, "configuracao_sobreposta", "Remova a variavel de ambiente que sobrepoe %s.%s." % par)
            _validar_destinos(alteracoes)
            novo = _editar(anterior.decode("utf-8"), alteracoes).encode("utf-8")
            if novo == anterior:
                return consultar(web)
            info = arq.stat()
            fd, temporario = tempfile.mkstemp(prefix=".radar-", dir=arq.parent)
            try:
                with os.fdopen(fd, "wb") as saida:
                    os.fchmod(saida.fileno(), stat.S_IMODE(info.st_mode))
                    os.fchown(saida.fileno(), -1, info.st_gid)
                    saida.write(novo)
                    saida.flush()
                    os.fsync(saida.fileno())
                backup = arq.with_name("radar.conf.anterior")
                if backup.is_symlink():
                    _erro(422, "configuracao_invalida", "Backup nao pode ser link simbolico.")
                # Backup e metadados da alteracao nao ficam no webroot.
                fd_b = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o660)
                with os.fdopen(fd_b, "wb") as b:
                    _permissao_auxiliar(b.fileno(), info.st_gid)
                    b.write(anterior)
                    b.flush()
                    os.fsync(b.fileno())
                auditoria = {"quando": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             "autor": autor, "revisao_anterior": dados["revisao"],
                             "revisao_nova": _revisao(novo),
                             "chaves": sorted(dados["alteracoes"])}
                fd_a = os.open(str(arq) + ".auditoria.jsonl", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o660)
                with os.fdopen(fd_a, "a", encoding="utf-8") as registro:
                    _permissao_auxiliar(registro.fileno(), info.st_gid)
                    registro.write(json.dumps(auditoria, ensure_ascii=False) + "\n")
                    registro.flush()
                    os.fsync(registro.fileno())
                os.replace(temporario, arq)
                pasta = os.open(arq.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(pasta)
                finally:
                    os.close(pasta)
            finally:
                if os.path.exists(temporario):
                    os.unlink(temporario)
    except PermissionError:
        _erro(503, "configuracao_sem_permissao", "Execute o instalador para habilitar a gravacao da configuracao pelo painel.")
    caminhos.recarregar()
    resultado = consultar(web)
    resultado["mensagem"] = "Configuracao salva. Vale nas proximas chamadas da API e do cron; caminhos nao movem arquivos."
    return resultado


def verificar_gravacao_web():
    arq = _arquivo(web=True)
    if not os.access(arq, os.R_OK | os.W_OK):
        _erro(503, "configuracao_sem_permissao", "O usuario do CGI precisa ler e gravar radar.conf.")
    try:
        with tempfile.NamedTemporaryFile(prefix=".radar-teste-", dir=arq.parent) as teste:
            teste.write(b"verificacao de gravacao\n")
            teste.flush()
            os.fsync(teste.fileno())
    except PermissionError:
        _erro(503, "configuracao_sem_permissao", "O usuario do CGI precisa criar arquivos na pasta da configuracao.")
    return {"sucesso": True, "arquivo": str(arq), "gravavel": True}


@operacao_local
def main(argv):
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Configuracao pela entrada unica api.pse")
    parser.add_argument("acao", choices=("mostrar", "salvar", "salvar-web", "verificar-web", "verificar", "instalar", "exemplo"), nargs="?", default="mostrar")
    parser.add_argument("--conf", help="arquivo de configuracao local")
    args = parser.parse_args(argv)
    if args.conf:
        os.environ["RADAR_CONF"] = args.conf
        caminhos.recarregar()
    try:
        if args.acao == "instalar":
            from deploy.conf_radar import instalar
            return instalar()
        if args.acao == "exemplo":
            print((Path(caminhos.ROOT) / "deploy" / "radar.conf.exemplo").read_text())
            return 0
        if args.acao == "verificar":
            from deploy.conf_radar import verificar
            return verificar()
        if args.acao == "verificar-web":
            print(json.dumps(verificar_gravacao_web(), ensure_ascii=False))
            return 0
        res = (salvar(json.load(sys.stdin), web=args.acao == "salvar-web",
                      autor="painel" if args.acao == "salvar-web" else "local")
               if args.acao in ("salvar", "salvar-web") else consultar())
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except GovernancaError as exc:
        if args.acao == "salvar-web":
            print(json.dumps({"status": exc.status, "codigo": exc.codigo, "mensagem": exc.mensagem}))
        else:
            print(exc.mensagem, file=sys.stderr)
        return 1
