# -*- coding: utf-8 -*-
"""Caminhos e variaveis de ambiente do Radar Brasil.

Tudo e resolvido a partir da raiz do repositorio; nada depende de rede em
tempo de requisicao da API.
"""
import os

# Raiz do repositorio = diretorio pai de core/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SQL_DIR = os.path.join(ROOT, "sql")
SCHEMA_SQLITE = os.path.join(SQL_DIR, "schema.sqlite.sql")
SCHEMA_POSTGRES = os.path.join(SQL_DIR, "schema.postgres.sql")

# Diretorio de dados (banco local + cache de arquivos baixados).
# NUNCA versionado (.gitignore cobre dados/ e *.sqlite).
DATA_DIR = os.environ.get("RADAR_DATA_DIR", os.path.join(ROOT, "dados"))
RAW_DIR = os.path.join(DATA_DIR, "raw")        # cache imutavel por sha256
STAGING_DIR = os.path.join(DATA_DIR, "staging")  # banco em construcao
DB_PATH = os.environ.get("RADAR_DB", os.path.join(DATA_DIR, "radar.sqlite3"))

# Contrato/API
API_VERSION = "1.0"
SCHEMA_VERSION = "1.0"
DEFAULT_RAIO = 1000
MIN_RAIO = 1
MAX_RAIO = 50000
DEFAULT_LIMITE = 100
MIN_LIMITE = 1
MAX_LIMITE = 1000

# Geodesia
EARTH_RADIUS_M = 6371008.8   # raio medio WGS84 (spec 9.2)

# Coletor
DEFAULT_TIMEOUT = 30          # segundos
DEFAULT_TENTATIVAS = 3
USER_AGENT = "RadarBrasil/1.0 (+https://github.com/Challado/Bunda-de-Urso)"


def ensure_dirs():
    for d in (DATA_DIR, RAW_DIR, STAGING_DIR):
        os.makedirs(d, exist_ok=True)
