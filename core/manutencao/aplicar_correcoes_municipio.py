#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplica (re)aplicavelmente as correcoes de municipio no banco.

Le ``config/correcoes_municipio.csv`` (``ponto_id -> codigo_ibge``) e faz o
UPDATE idempotente em ``PONTO_FISCALIZACAO.municipio_id``.  Depois deriva
``VIA_UF`` (via -> UF) a partir dos municipios.  Nada e inventado: ponto ou
codigo inexistente sao contados e ignorados.

Uso:
  python3 tools/aplicar_correcoes_municipio.py [--db CAMINHO] [--csv CAMINHO]
      [--dry-run] [--backup]
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys


from core import config                          # noqa: E402
from core import correcoes_municipio as corr      # noqa: E402
from core.contexto_api import operacao_local
from core import db as dbmod
from core import caminhos  # caminhos so pela porta unica

DB_PADRAO = caminhos.banco()


def contar(conn, sql):
    return conn.execute(sql).fetchone()[0]


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Aplica as correcoes de municipio (idempotente).")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite")
    ap.add_argument("--csv", default=corr.CAMINHO_PADRAO, help="CSV de correcoes")
    ap.add_argument("--dry-run", action="store_true", help="nao grava nada")
    ap.add_argument("--backup", action="store_true",
                    help="copia o banco para <db>.bak.<ts> antes de gravar")
    ap.add_argument("--sem-via-uf", action="store_true",
                    help="nao derivar VIA_UF apos aplicar")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2
    if not os.path.exists(args.csv):
        print("ERRO: CSV nao encontrado: %s" % args.csv, file=sys.stderr)
        return 3

    if args.backup and not args.dry_run:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = "%s.bak.%s" % (args.db, ts)
        shutil.copy2(args.db, destino)
        print("backup: %s" % destino)

    conn = dbmod.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:                                   # pragma: no cover
        pass
    try:
        antes = contar(conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO "
                             "WHERE municipio_id IS NOT NULL")
        correcoes = corr.carregar_correcoes(args.csv)
        est = corr.aplicar_correcoes(conn, correcoes, dry_run=args.dry_run)
        depois = contar(conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO "
                              "WHERE municipio_id IS NOT NULL")
        via_uf = 0
        if not args.dry_run and not args.sem_via_uf:
            via_uf = corr.resolver_via_uf(conn)
    finally:
        conn.close()

    print("modo: %s" % ("dry-run (nada gravado)" if args.dry_run else "aplicado"))
    print("correcoes no CSV:            %d" % est["total"])
    print("  alterados agora:           %d" % est["alterados"])
    print("  ja corretos (idempotente): %d" % est["ja_corretos"])
    print("  ponto inexistente:         %d" % est["ponto_inexistente"])
    print("  codigo desconhecido:       %d" % est["codigo_desconhecido"])
    print("  duplicados:                %d" % est["duplicados"])
    print("PONTO_FISCALIZACAO com municipio: %d -> %d" % (antes, depois))
    if not args.dry_run and not args.sem_via_uf:
        print("VIA_UF: +%d" % via_uf)
    return 0
