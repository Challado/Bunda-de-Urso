# -*- coding: utf-8 -*-
"""Parametros do Radar Brasil.

Caminhos NAO sao decididos aqui: vem da porta unica ``core.caminhos``
(ambiente -> /etc/radar-brasil/radar.conf -> padrao do checkout). Este modulo
apenas reexporta o que o resto do codigo ja conhece e guarda os parametros que
nao sao caminho. Nada depende de rede em tempo de requisicao da API.
"""
import os

from core import caminhos

# Raiz do repositorio = diretorio pai de core/
ROOT = caminhos.ROOT

SQL_DIR = os.path.join(ROOT, "sql")
SCHEMA_SQLITE = os.path.join(SQL_DIR, "schema.sqlite.sql")
SCHEMA_POSTGRES = os.path.join(SQL_DIR, "schema.postgres.sql")

# Diretorio de dados (banco local + cache de arquivos baixados).
# NUNCA versionado (.gitignore cobre dados/ e *.sqlite).
DATA_DIR = caminhos.data_dir()
RAW_DIR = caminhos.bruto()          # cache imutavel por sha256
STAGING_DIR = caminhos.staging()    # banco em construcao
DB_PATH = caminhos.banco()

# Contrato/API
API_VERSION = "1.0"
SCHEMA_VERSION = "1.0"
DEFAULT_RAIO = 1000
MIN_RAIO = 1
MAX_RAIO = 1000000     # 1000 km: consulta/zoom de area ampla (era 50000 = 50 km)
DEFAULT_LIMITE = 100
MIN_LIMITE = 1
MAX_LIMITE = 1000

# Ingestao (escrita) via API: token NUNCA no codigo. Resolvido, nesta ordem:
#   1. variavel de ambiente RADAR_API_TOKEN;
#   2. arquivo indicado por RADAR_API_TOKEN_FILE;
#   3. arquivo padrao /etc/radar-brasil/api_token (se existir).
# Sem token configurado a escrita fica DESABILITADA e a API responde 401.
API_TOKEN_ENV = "RADAR_API_TOKEN"
API_TOKEN_FILE_ENV = "RADAR_API_TOKEN_FILE"
API_TOKEN_FILE_PADRAO = caminhos.token_arquivo()


def token_ingestao():
    """Token de escrita configurado (env -> arquivo), ou "" se nao houver."""
    tok = (os.environ.get(API_TOKEN_ENV) or "").strip()
    if tok:
        return tok
    for caminho in [caminhos.token_arquivo()]:
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                texto = f.read().strip()
        except OSError:
            continue
        if texto:
            return texto
    return ""


# Ingestao via API: tamanho maximo do corpo aceito (protege o CGI).
API_MAX_BODY = caminhos.inteiro("api", "max_body")

# ---------------------------------------------------------------------------
# Governanca da ingestao: parametros operacionais no radar.conf.
# A senha inicial entra pelo CLI; nao pertence ao arquivo de configuracao.
# ---------------------------------------------------------------------------

def _carregar_governanca():
    """Valores operacionais pertencem ao radar.conf, nao ao checkout."""
    return {chave: caminhos.inteiro("governanca", chave.lower())
            for chave in (k.upper() for k in caminhos.SECOES["governanca"])}


_GOV = _carregar_governanca()
RAIO_CORRESPONDENCIA_M = _GOV["RAIO_CORRESPONDENCIA_M"]
RAIO_ZONA_SOMBRA_M = _GOV["RAIO_ZONA_SOMBRA_M"]
SUBMISSAO_LIMITE = _GOV["SUBMISSAO_LIMITE"]
SUBMISSAO_JANELA_SEGUNDOS = _GOV["SUBMISSAO_JANELA_SEGUNDOS"]
SESSAO_TTL_SEGUNDOS = _GOV["SESSAO_TTL_SEGUNDOS"]
GOV_ITERACOES = max(200000, _GOV["GOV_ITERACOES"])

# Geodesia
EARTH_RADIUS_M = 6371008.8   # raio medio WGS84 (spec 9.2)

# Coletor
DEFAULT_TIMEOUT = caminhos.inteiro("coleta", "timeout")
DEFAULT_TENTATIVAS = caminhos.inteiro("coleta", "tentativas")
USER_AGENT = "RadarBrasil/1.0 (+https://github.com/Challado/Bunda-de-Urso)"

##-- BUNDITA DE URSO #{12} -- Cabecalhos de cliente so podem identificar IP quando enviados por proxy confiavel. ##
TRUSTED_PROXIES = tuple(p.strip() for p in caminhos.valor(
    "api", "proxies_confiaveis")[0].split(",") if p.strip())

# Descricao curta do limite de raio, para mensagens/ajuda (mantidas em sincronia).
RAIO_FAIXA_TXT = "%d..%d" % (MIN_RAIO, MAX_RAIO)


def ensure_dirs():
    """Cria (idempotente) os diretorios de dados resolvidos pela porta unica."""
    for diretorio in (DATA_DIR, RAW_DIR, STAGING_DIR):
        os.makedirs(diretorio, exist_ok=True)
