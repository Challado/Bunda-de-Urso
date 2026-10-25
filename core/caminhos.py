# -*- coding: utf-8 -*-
"""Porta unica dos caminhos da instalacao.

Todo caminho de instalacao (codigo, banco, dados brutos, calibracao, web, logs
e espelho de dados) e resolvido AQUI. Nenhum modulo, conector, script de
manutencao, entrada CGI ou arquivo de deploy decide caminho por conta propria.

Somente RADAR_CONF seleciona o arquivo; sem ela usa CONF_PADRAO junto aos
scripts. Todos os parametros vem desse arquivo, com padroes documentados para
chaves ausentes. Outras variaveis de ambiente nao alteram a configuracao.
Banco, logs, cache, fila, tokens, chaves e malhas ficam dentro de dados.dir.

Nunca escreva caminho absoluto de producao no codigo. Se precisar de um
caminho, peca a esta porta. O verificador
``.github/scripts/verificar_caminhos.py`` reprova quem desobedecer.
"""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_LEGADO = ContextVar("radar_migracao_local", default=False)


@contextmanager
def migracao_local():
    """Somente o instalador local pode ler destinos antigos para migra-los."""
    token = _LEGADO.set(True)
    try:
        yield
    finally:
        _LEGADO.reset(token)


# Raiz do checkout = diretorio pai de core/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONF_PADRAO = os.path.join(ROOT, "radar.conf")
CONF_ENV = "RADAR_CONF"

# (secao, chave) -> variavel de ambiente que tem precedencia.
_ENV = {}  # Somente RADAR_CONF seleciona o arquivo; valores vem do .conf.

# Secoes/chaves conhecidas -- usado pelo exemplo, pelo verificador e pelo help.
SECOES = {
    "instalacao": ("home",),
    "dados": ("dir", "banco"),
    "web": ("raiz", "url", "origem"),
    "logs": ("dir",),
    "sincronizacao": ("clone", "remoto"),
    "api": ("token_arquivo", "max_body", "proxies_confiaveis"),
    "coleta": ("max_bytes", "timeout", "tentativas", "espera_atualizacao"),
    "geografia": ("malha",),
    "cadastro": ("max_itens", "max_bytes", "max_pendentes", "lote", "tentativas", "retencao_dias"),
    "assistente": ("habilitado", "provedor", "url", "modelo", "chave_arquivo",
                   "timeout", "max_entrada", "max_saida_tokens", "max_chamadas",
                   "documentos", "correspondencias", "auditoria", "diagnostico", "explicacoes", "municipios"),
    "governanca": ("raio_correspondencia_m", "raio_zona_sombra_m",
                   "submissao_limite", "submissao_janela_segundos",
                   "sessao_ttl_segundos", "gov_iteracoes"),
}
# Apenas valores de instalacao. Segredos continuam em arquivos separados.
PADROES = {
    ("web", "origem"): "",
    ("api", "max_body"): "8388608",
    ("api", "proxies_confiaveis"): "",
    ("coleta", "max_bytes"): "52428800",
    ("coleta", "timeout"): "30",
    ("coleta", "tentativas"): "3",
    ("coleta", "espera_atualizacao"): "300",
    ("geografia", "malha"): "",
    ("cadastro", "max_itens"): "100",
    ("cadastro", "max_bytes"): "262144",
    ("cadastro", "max_pendentes"): "10000",
    ("cadastro", "lote"): "20",
    ("cadastro", "tentativas"): "5",
    ("cadastro", "retencao_dias"): "30",
    ("assistente", "url"): "http://127.0.0.1:11434",
    ("assistente", "modelo"): "gemma4:26b",
    ("assistente", "habilitado"): "0",
    ("assistente", "provedor"): "ollama",
    ("assistente", "chave_arquivo"): "",
    ("assistente", "timeout"): "20",
    ("assistente", "max_entrada"): "20000",
    ("assistente", "max_saida_tokens"): "1024",
    ("assistente", "max_chamadas"): "10",
    ("governanca", "raio_correspondencia_m"): "150",
    ("governanca", "raio_zona_sombra_m"): "1000",
    ("governanca", "submissao_limite"): "20",
    ("governanca", "submissao_janela_segundos"): "3600",
    ("governanca", "sessao_ttl_segundos"): "28800",
    ("governanca", "gov_iteracoes"): "200000",
}
for _funcao_ia in ("documentos", "correspondencias", "auditoria", "diagnostico", "explicacoes", "municipios"):
    PADROES[("assistente", _funcao_ia)] = "1"

_CACHE = {"chave": None, "valores": {}, "problemas": []}


def conf_path():
    """Caminho do arquivo de configuracao em uso."""
    return os.path.abspath((os.environ.get(CONF_ENV) or "").strip() or CONF_PADRAO)


def existe_conf():
    """True se ha arquivo de configuracao legivel."""
    return os.path.isfile(conf_path())


def _ler_conf():
    """Le o arquivo (INI simples) com cache por caminho+mtime.

    Devolve ``{(secao, chave): valor}`` e a lista de problemas encontrados.
    Arquivo ausente, ilegivel ou linha torta NAO derrubam nada: viram
    problema (visivel em ``problemas()``) e a resolucao segue para o padrao.
    """
    caminho = conf_path()
    try:
        mtime = os.stat(caminho).st_mtime_ns
    except OSError:
        mtime = None
    chave = (caminho, mtime)
    if _CACHE["chave"] == chave:
        return _CACHE["valores"], _CACHE["problemas"]

    valores = {}
    problemas = []
    secao = None
    if mtime is not None:
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                for numero, linha in enumerate(f, 1):
                    texto = linha.strip()
                    if not texto or texto[0] in "#;":
                        continue
                    if texto.startswith("[") and texto.endswith("]"):
                        secao = texto[1:-1].strip().lower()
                        if secao not in SECOES:
                            problemas.append(
                                "%s:%d: secao desconhecida [%s]"
                                % (caminho, numero, secao))
                        continue
                    if "=" not in texto:
                        problemas.append(
                            "%s:%d: linha sem '=' (ignorada)"
                            % (caminho, numero))
                        continue
                    nome, valor = texto.split("=", 1)
                    nome = nome.strip().lower()
                    valor = valor.strip().strip('"').strip("'")
                    if secao is None:
                        problemas.append(
                            "%s:%d: chave antes de qualquer secao"
                            % (caminho, numero))
                        continue
                    if (secao, nome) in (("instalacao", "usuario"), ("instalacao", "grupo")) and _LEGADO.get():
                        continue
                    if secao in SECOES and nome not in SECOES[secao]:
                        problemas.append(
                            "%s:%d: chave desconhecida [%s] %s"
                            % (caminho, numero, secao, nome))
                    if (secao, nome) in valores:
                        problemas.append("%s:%d: chave repetida [%s] %s"
                                         % (caminho, numero, secao, nome))
                    valores[(secao, nome)] = valor
        except OSError as exc:
            problemas.append("%s: nao foi possivel ler (%s)" % (caminho, exc))

    _CACHE.update({"chave": chave, "valores": valores, "problemas": problemas})
    return valores, problemas


def recarregar():
    """Descarta o cache -- o proximo acesso rele o arquivo."""
    _CACHE.update({"chave": None, "valores": {}, "problemas": []})


def problemas():
    """Problemas do arquivo de configuracao (linhas ignoradas, secao errada)."""
    return list(_ler_conf()[1])


def _base_conf():
    return os.path.dirname(os.path.abspath(conf_path())) or "/"


def _absoluto(valor, origem):
    """Expande ~ e resolve caminho relativo (contra a pasta do .conf)."""
    texto = os.path.expanduser(str(valor).strip())
    if not os.path.isabs(texto):
        base = _base_conf() if origem not in ("padrao", "") else os.getcwd()
        texto = os.path.join(base, texto)
    return os.path.normpath(texto)


def valor(secao, chave, padrao="", env=None):
    """Valor do arquivo selecionado ou padrao; ambiente nao sobrepoe valores."""
    conf, _ = _ler_conf()
    do_arquivo = conf.get((secao, chave))
    if do_arquivo:
        return do_arquivo, conf_path()
    return PADROES.get((secao, chave), padrao), "padrao"


def inteiro(secao, chave):
    try:
        return int(valor(secao, chave)[0])
    except (TypeError, ValueError):
        return int(PADROES[(secao, chave)])


def dentro_dados(texto, secao="arquivo", base=None):
    """Resolve dados relativos a dados.dir e impede escapes, inclusive por links."""
    raiz = Path(base or data_dir()).resolve()
    valor_ = os.path.expanduser(str(texto).strip())
    candidato = Path(valor_)
    if not candidato.is_absolute():
        candidato = raiz / candidato
        if _LEGADO.get():
            anterior = Path(_base_conf()) / valor_
            if not candidato.exists() and anterior.exists():
                candidato = anterior
    destino = candidato.resolve()
    if not _LEGADO.get() and (destino == raiz or not destino.is_relative_to(raiz)):
        raise ValueError(secao + ": o destino deve ficar dentro de [dados] dir.")
    return str(destino)


def token_arquivo():
    return caminho("api", "token_arquivo", "api_token")


def caminho(secao, chave, padrao="", env=None):
    """Igual a ``valor()``, porem devolvendo caminho absoluto normalizado."""
    bruto, origem = valor(secao, chave, padrao, env)
    if not bruto:
        bruto = padrao
    if not bruto:
        return ""
    if (secao, chave) in {("dados", "banco"), ("logs", "dir"), ("api", "token_arquivo"),
                          ("assistente", "chave_arquivo"), ("geografia", "malha"), ("sincronizacao", "clone")}:
        return dentro_dados(bruto, secao + "." + chave)
    return _absoluto(bruto, origem)


# ---------------------------------------------------------------------------
# Caminhos usados pelo aplicativo
# ---------------------------------------------------------------------------
def home():
    """Raiz do codigo instalado (onde ficam core/, coletor/, web/, sql/)."""
    return caminho("instalacao", "home", ROOT)


def data_dir():
    """Diretorio de dados (banco + arquivos brutos + calibracao)."""
    return caminho("dados", "dir", os.path.join(ROOT, "dados"))


def banco():
    """Banco SQLite de producao (ou de trabalho, sem configuracao)."""
    bruto, _ = valor("dados", "banco", "radar.sqlite3")
    # Aceita o caminho absoluto antigo somente se continuar dentro de dados.dir;
    # novas gravacoes de configuracao armazenam apenas o nome do arquivo.
    if not _LEGADO.get() and not os.path.isabs(bruto) and ("/" in bruto or "\\" in bruto or bruto in (".", "..")):
        raise ValueError("dados.banco: informe somente o nome do arquivo dentro de dados.dir.")
    return dentro_dados(bruto, "dados.banco")


def bruto():
    """Cache imutavel de arquivos baixados (um por sha256)."""
    return dentro_dados("raw", "raw")


def staging():
    """Banco em construcao, antes da publicacao atomica."""
    return dentro_dados("staging", "staging")


def calibracao():
    """Ancoras km->coordenada geradas a partir do banco."""
    return dentro_dados("calibracao", "calibracao")


def log_dir():
    """Diretorio dos logs do radar (tick, dados-sync)."""
    return caminho("logs", "dir", "logs")


def web_raiz():
    """Webroot servido pelo nginx/fcgiwrap."""
    return caminho("web", "raiz", os.path.join(ROOT, "web"))


def web_url():
    """Prefixo publico da consulta (usado por links e projeto.json)."""
    return valor("web", "url", "/")[0]


def web_inicio():
    """Pagina publica real, sem depender de aliases ou redirecionamentos."""
    return web_url().rstrip('/') + '/'


def sync_clone():
    """Clone local do repositorio privado de dados (vazio = nao configurado)."""
    return caminho("sincronizacao", "clone", "")


def sync_remoto():
    """URL do repositorio privado de dados (vazio = nao configurado)."""
    return valor("sincronizacao", "remoto", "")[0]


# ---------------------------------------------------------------------------
# Diagnostico
# ---------------------------------------------------------------------------
def resumo():
    """Lista ordenada de dicionarios com valor efetivo e origem de cada chave."""
    itens = [
        ("instalacao", "home", home()),
        ("dados", "dir", data_dir()),
        ("dados", "banco", banco()),
        ("web", "raiz", web_raiz()),
        ("web", "url", web_url()),
        ("logs", "dir", log_dir()),
        ("sincronizacao", "clone", sync_clone()),
        ("sincronizacao", "remoto", sync_remoto()),
    ]
    saida = []
    for secao, chave, efetivo in itens:
        _, origem = valor(secao, chave)
        saida.append({"secao": secao, "chave": chave,
                      "valor": efetivo, "origem": origem})
    return saida


def ensure_dirs():
    """Cria os diretorios de dados necessarios (idempotente)."""
    for caminho_dir in (data_dir(), bruto(), staging(), calibracao()):
        os.makedirs(caminho_dir, exist_ok=True)


def fila_cadastros(dados_dir=None):
    """Fila confinada ao diretorio de dados definido pelo radar.conf."""
    return dentro_dados("fila-cadastros", "fila", base=dados_dir)


def status_atualizacoes():
    """Estado persistente em dados.dir, preservado durante atualizacoes."""
    return dentro_dados("atualizacoes/status.json", "status")


def log_atualizacoes():
    return os.path.join(log_dir(), "atualizacoes.log")


def link_atualizacoes():
    return os.path.join(home(), "status-atualizacoes.json")


def temporarios():
    """Temporarios operacionais privados, inclusive perfis do navegador e OCR."""
    pasta = dentro_dados("temporarios", "temporarios")
    os.makedirs(pasta, mode=0o770, exist_ok=True)
    return pasta


def validar_operacionais():
    """Todos os destinos de dados sao conferidos antes de atender requisicoes."""
    banco()
    log_dir()
    token_arquivo()
    caminho("assistente", "chave_arquivo", "assistente_chave")
    caminho("geografia", "malha")
    sync_clone()
