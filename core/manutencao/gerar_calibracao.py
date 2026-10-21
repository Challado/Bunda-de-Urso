#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera a calibracao (ancoras km->coordenada) a partir do banco de producao.

Le SOMENTE (``mode=ro``) os nossos pontos oficiais que tem km + coordenada e
agrupa por ``VIA.codigo``. Nao inventa dado: ponto sem km ou sem coordenada e
descartado.

Saidas (nao sobrescreve codigo-fonte, apenas dados gerados):
  dados/calibracao/ancoras.csv   via;uf;km;lat;lon;ponto_id;fonte   (ordem via,km)
  dados/calibracao/resumo_vias.csv  via;n_ancoras;km_min;km_max

Uso:
  python3 tools/gerar_calibracao.py [--db CAMINHO] [--saida DIR]
"""
import argparse
import csv
import os
import sqlite3
import sys


from core.config import ROOT  # noqa: E402
from core.contexto_api import operacao_local
from core import db as dbmod

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
SAIDA_PADRAO = os.path.join(ROOT, "dados", "calibracao")

SQL = """
SELECT v.codigo            AS via,
       m.uf_sigla          AS uf,
       p.km                AS km,
       g.latitude          AS lat,
       g.longitude         AS lon,
       p.id                AS ponto_id,
       g.metodo_obtencao   AS fonte
FROM PONTO_FISCALIZACAO p
JOIN POSICAO_GEOGRAFICA g ON g.id = p.posicao_id
JOIN VIA v               ON v.id = p.via_id
LEFT JOIN MUNICIPIO m    ON m.codigo_ibge = p.municipio_id
WHERE p.km IS NOT NULL AND p.via_id IS NOT NULL
  AND g.latitude IS NOT NULL AND g.longitude IS NOT NULL
ORDER BY v.codigo, p.km, p.id
"""


def conectar_ro(caminho):
    """Abre o banco em modo SOMENTE LEITURA (URI mode=ro)."""
    uri = "file:%s?mode=ro" % os.path.abspath(caminho)
    con = dbmod.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _limpa(txt):
    """Remove separador do CSV de campos de texto livre (nao inventa)."""
    if txt is None:
        return ""
    return str(txt).replace(";", ",").replace("\n", " ").strip()


def coletar(con):
    return con.execute(SQL).fetchall()


def escrever(linhas, saida_dir):
    os.makedirs(saida_dir, exist_ok=True)
    cam_ancoras = os.path.join(saida_dir, "ancoras.csv")
    cam_resumo = os.path.join(saida_dir, "resumo_vias.csv")

    por_via = {}
    with open(cam_ancoras, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "uf", "km", "lat", "lon", "ponto_id", "fonte"])
        for r in linhas:
            via = r["via"]
            km = float(r["km"])
            w.writerow([via, _limpa(r["uf"]), repr(km), repr(float(r["lat"])),
                        repr(float(r["lon"])), r["ponto_id"], _limpa(r["fonte"])])
            por_via.setdefault(via, []).append(km)

    with open(cam_resumo, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "n_ancoras", "km_min", "km_max"])
        for via in sorted(por_via):
            kms = por_via[via]
            w.writerow([via, len(kms), repr(min(kms)), repr(max(kms))])

    return cam_ancoras, cam_resumo, por_via


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera ancoras de calibracao (km->coord).")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite (somente leitura)")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help="diretorio de saida")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    con = conectar_ro(args.db)
    try:
        linhas = coletar(con)
    finally:
        con.close()

    cam_ancoras, cam_resumo, por_via = escrever(linhas, args.saida)

    total = len(linhas)
    n_vias = len(por_via)
    ge2 = sum(1 for k in por_via.values() if len(k) >= 2)
    ge3 = sum(1 for k in por_via.values() if len(k) >= 3)

    print("ancoras.csv:        %s (%d ancoras)" % (cam_ancoras, total))
    print("resumo_vias.csv:    %s (%d vias)" % (cam_resumo, n_vias))
    print("vias com >=2 ancoras: %d" % ge2)
    print("vias com >=3 ancoras: %d" % ge3)
    return 0
