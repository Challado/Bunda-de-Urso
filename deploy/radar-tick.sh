#!/bin/sh
# Radar Brasil — passada do coletor (o cron chama a cada minuto).
#
# Instalado FORA do checkout, num diretorio do cron (root:www-data 750).
# NENHUM caminho fixo aqui: tudo vem de /etc/radar-brasil/radar.conf
# (ou do arquivo indicado em RADAR_CONF). Sem o arquivo, usa o checkout que
# estiver ao lado deste script.
#
# O tick decide sozinho o que esta vencido pelo intervalo de cada fonte.
set -eu
umask 002

CONF="${RADAR_CONF:-/etc/radar-brasil/radar.conf}"
PY="${RADAR_PYTHON:-/usr/bin/python3}"

conf_get() {  # conf_get <secao> <chave>
    [ -r "$CONF" ] || return 0
    awk -v secao="$1" -v chave="$2" '
        /^[[:space:]]*[#;]/ { next }
        /^[[:space:]]*\[/ {
            s = $0
            sub(/^[[:space:]]*\[/, "", s)
            sub(/\].*$/, "", s)
            gsub(/[[:space:]]/, "", s)
            atual = tolower(s)
            next
        }
        {
            i = index($0, "=")
            if (!i) next
            k = substr($0, 1, i - 1)
            v = substr($0, i + 1)
            gsub(/^[[:space:]]+/, "", k); gsub(/[[:space:]]+$/, "", k)
            gsub(/^[[:space:]]+/, "", v); gsub(/[[:space:]]+$/, "", v)
            if (atual == tolower(secao) && tolower(k) == tolower(chave)) { print v; exit }
        }' "$CONF"
}

HOME_DIR="${RADAR_BRASIL_HOME:-$(conf_get instalacao home)}"
DADOS="${RADAR_DATA_DIR:-$(conf_get dados dir)}"
BANCO="${RADAR_DB:-$(conf_get dados banco)}"
WEBRAIZ="${RADAR_WEB_ROOT:-$(conf_get web raiz)}"

if [ -z "$HOME_DIR" ]; then
    HOME_DIR="$(cd "$(dirname "$0")" && pwd)/radar"
fi
[ -n "$DADOS" ] || DADOS="$HOME_DIR/dados"
[ -n "$BANCO" ] || BANCO="$DADOS/radar.sqlite3"
[ -n "$WEBRAIZ" ] || WEBRAIZ="$HOME_DIR/web"

if [ ! -f "$WEBRAIZ/api.pse" ]; then
    echo "radar-tick: api.pse nao encontrado em $WEBRAIZ (confira [web] raiz ou [instalacao] home em $CONF)" >&2
    exit 78
fi

export RADAR_BRASIL_HOME="$HOME_DIR" RADAR_DATA_DIR="$DADOS" RADAR_DB="$BANCO"

exec "$PY" "$WEBRAIZ/api.pse" tick "$@"
