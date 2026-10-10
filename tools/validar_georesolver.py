#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validacao leave-one-out do resolvedor km->coordenada.

Para cada via com >=3 ancoras oficiais, retira-se UMA ancora de cada vez e
resolve-se o km dela com o resto da calibracao; mede-se o erro Haversine (m)
contra a coordenada real que ficou de fora. Agrega por via (mediana/p90/max)
e no geral.

Saidas:
  dados/calibracao/validacao.csv   via;n;erro_mediano_m;erro_p90_m;erro_max_m
  resumo geral + top 10 vias no stdout.

Uso:
  python3 tools/validar_georesolver.py [--ancoras CSV] [--db CAMINHO] [--saida DIR]
"""
import argparse
import csv
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import georesolver  # noqa: E402
from core.config import ROOT  # noqa: E402
from core.geo import haversine_m  # noqa: E402

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
SAIDA_PADRAO = os.path.join(ROOT, "dados", "calibracao")


def percentil(valores, p):
    """Percentil por interpolacao linear (mesmo metodo do numpy)."""
    if not valores:
        return None
    s = sorted(valores)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p
    f = int(math.floor(k))
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def validar_via(via, ancoras):
    """Leave-one-out de uma via. Retorna lista de erros (m)."""
    erros = []
    n = len(ancoras)
    if n < 3:
        return erros
    for i, alvo in enumerate(ancoras):
        resto = ancoras[:i] + ancoras[i + 1:]
        if len(resto) < 2:
            continue
        res = georesolver.resolver(via, alvo["km"], {via: resto})
        if res["status"] != georesolver.STATUS_OK:
            continue
        erros.append(haversine_m(res["lat"], res["lon"],
                                 alvo["lat"], alvo["lon"]))
    return erros


def coletar_erros(calibracao):
    por_via = {}
    for via, ancoras in calibracao.items():
        if len(ancoras) >= 3:
            erros = validar_via(via, ancoras)
            if erros:
                por_via[via] = erros
    return por_via


def contar_resolviveis(db, calibracao):
    """Dos pontos com km no banco, quantos caem na faixa calibrada de uma via."""
    if not os.path.exists(db):
        return None
    uri = "file:%s?mode=ro" % os.path.abspath(db)
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT v.codigo AS via, p.km AS km "
            "FROM PONTO_FISCALIZACAO p JOIN VIA v ON v.id = p.via_id "
            "WHERE p.km IS NOT NULL").fetchall()
    finally:
        con.close()

    total = resolvivel = sem_cal = fora = 0
    for r in rows:
        total += 1
        via = (r["via"] or "").strip() or None
        ancoras = calibracao.get(via) if via else None
        if not ancoras or len(ancoras) < 2:
            sem_cal += 1
            continue
        kms = [a["km"] for a in ancoras]
        km = float(r["km"])
        if km < min(kms) or km > max(kms):
            fora += 1
            continue
        resolvivel += 1
    return {"total": total, "resolvivel": resolvivel,
            "sem_calibracao": sem_cal, "fora_de_faixa": fora}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validacao leave-one-out do georesolver.")
    ap.add_argument("--ancoras", default=georesolver.CAMINHO_ANCORAS_PADRAO)
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--saida", default=SAIDA_PADRAO)
    args = ap.parse_args(argv)

    if not os.path.exists(args.ancoras):
        print("ERRO: ancoras nao encontradas: %s (rode tools/gerar_calibracao.py)"
              % args.ancoras, file=sys.stderr)
        return 2

    calibracao = georesolver.carregar_ancoras(args.ancoras)
    por_via = coletar_erros(calibracao)

    os.makedirs(args.saida, exist_ok=True)
    cam = os.path.join(args.saida, "validacao.csv")
    todos = []
    with open(cam, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "n", "erro_mediano_m", "erro_p90_m", "erro_max_m"])
        for via in sorted(por_via, key=lambda v: (-len(por_via[v]), v)):
            erros = por_via[via]
            todos.extend(erros)
            w.writerow([via, len(erros),
                        "%.3f" % percentil(erros, 0.5),
                        "%.3f" % percentil(erros, 0.9),
                        "%.3f" % max(erros)])

    print("validacao.csv: %s" % cam)
    print("vias testadas (>=3 ancoras): %d" % len(por_via))
    print("pontos leave-one-out: %d" % len(todos))
    if todos:
        print("ERRO GERAL (m): mediana=%.1f  p90=%.1f  max=%.1f"
              % (percentil(todos, 0.5), percentil(todos, 0.9), max(todos)))

    print("\nTop 10 vias por n de ancoras:")
    print("%-12s %6s %12s %12s %12s" % ("via", "n", "mediano_m", "p90_m", "max_m"))
    rank = sorted(por_via, key=lambda v: (-len(por_via[v]), v))[:10]
    for via in rank:
        erros = por_via[via]
        print("%-12s %6d %12.1f %12.1f %12.1f"
              % (via, len(erros), percentil(erros, 0.5),
                 percentil(erros, 0.9), max(erros)))

    info = contar_resolviveis(args.db, calibracao)
    if info:
        print("\nPontos com km no banco: %d" % info["total"])
        print("  resolviveis pela calibracao atual: %d" % info["resolvivel"])
        print("  sem calibracao (<2 ancoras na via): %d" % info["sem_calibracao"])
        print("  fora de faixa: %d" % info["fora_de_faixa"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
