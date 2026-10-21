#!/bin/sh
# Radar Brasil — passada do coletor (o cron chama a cada minuto).
#
# Instalado em /home/openclaw/bin/radar-tick.sh (root:www-data 750).
# O tick decide sozinho o que esta vencido pelo intervalo de cada fonte.
umask 002

RADAR_DATA_DIR=/var/lib/radar-brasil
RADAR_DB=/var/lib/radar-brasil/radar.sqlite3
export RADAR_DATA_DIR RADAR_DB

exec /usr/bin/python3 /home/openclaw/bin/radar/web/api.pse tick "$@"
