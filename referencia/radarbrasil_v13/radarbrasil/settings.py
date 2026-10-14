"""Configuração sem depender de python-dotenv (systemd EnvironmentFile)."""
import os
from pathlib import Path

def env(name, default):
    return os.environ.get(name, str(default))

DATABASE_URL = env('RADAR_DATABASE_URL', 'sqlite:///./radarbrasil.sqlite3')
CACHE_DIR = Path(env('RADAR_CACHE_DIR', './cache'))
LOG_DIR = Path(env('RADAR_LOG_DIR', './logs'))
CONFIG_FILE = Path(env('RADAR_CONFIG', './config/sources.json'))
REQUEST_TIMEOUT = float(env('RADAR_REQUEST_TIMEOUT', 45))
CONNECT_TIMEOUT = float(env('RADAR_CONNECT_TIMEOUT', 12))
MAX_BYTES = int(env('RADAR_MAX_BYTES', 50 * 1024 * 1024))
USER_AGENT = env('RADAR_USER_AGENT', 'RadarBrasil/1.0 (contact: admin@example.org)')
MAX_RADIUS = int(env('RADAR_MAX_RADIUS', 50000))
MAX_RESULTS = int(env('RADAR_MAX_RESULTS', 1000))
WARNING_HOURS = int(env('RADAR_CACHE_WARNING_HOURS', 24))
CRITICAL_HOURS = int(env('RADAR_CACHE_CRITICAL_HOURS', 168))
ADMIN_TOKEN = env('RADAR_ADMIN_TOKEN', '')
MAX_POST_BODY = int(env('RADAR_HTTP_MAX_BODY', 65536))
