#!/bin/sh
# O instalador coloca radar-api.pse ao lado. Somente essa entrada le o .conf.
set -eu
umask 002
exec "${RADAR_PYTHON:-/usr/bin/python3}" "$(dirname "$0")/radar-api.pse" cron tick "$@"
