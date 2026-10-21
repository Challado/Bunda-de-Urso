#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validacao leave-one-out do resolvedor km->coordenada (por segmento).

Para cada (via, segmento) com >=3 ancoras, retira-se UMA ancora de cada vez e
resolve-se o km dela usando SO as ancoras restantes daquele segmento — ou seja o
trecho e conhecido, medindo a precisao alcancavel pelo interpolador. Mede-se o
erro Haversine (m) contra a coordenada real que ficou de fora. Agrega por
(via, segmento) e no geral.

Saidas (default):
  dados/calibracao/validacao_limpa.csv  via;segmento;n;erro_mediano_m;erro_p90_m;erro_max_m
  resumo geral + top 10 vias no stdout.

Uso:
  python3 tools/validar_georesolver.py [--ancoras CSV] [--db CAMINHO]
                                       [--saida DIR] [--nome ARQUIVO.csv]
"""
import argparse
import csv
import math
import os
import sqlite3
import sys


from core import georesolver  # noqa: E402
from core.config import ROOT  # noqa: E402
from core.geo import haversine_m  # noqa: E402
from core.contexto_api import operacao_local
from core import db as dbmod
from core import caminhos  # caminhos so pela porta unica

DB_PADRAO = caminhos.banco()
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


def validar_segmento(via, segmento, ancoras):
    """Leave-one-out de um segmento. Retorna lista de erros (m).

    A resolucao usa apenas as ancoras restantes DESTE segmento (calibracao
    sintetica ``{via: resto}``), garantindo que o trecho e conhecido.
    """
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
    """Agrega os erros leave-one-out por (via, segmento)."""
    por_seg = {}
    for via, ancoras in calibracao.items():
        segmentos = georesolver.agrupar_segmentos(ancoras)
        for seg, arr in segmentos.items():
            if len(arr) < 3:
                continue
            erros = validar_segmento(via, seg, arr)
            if erros:
                por_seg[(via, seg)] = erros
    return por_seg


def classificar_ponto(db, calibracao):
    """Dos pontos com km no banco, quantos cascateiam em cada status."""
    if not os.path.exists(db):
        return None
    uri = "file:%s?mode=ro" % os.path.abspath(db)
    con = dbmod.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT v.codigo AS via, p.km AS km "
            "FROM PONTO_FISCALIZACAO p JOIN VIA v ON v.id = p.via_id "
            "WHERE p.km IS NOT NULL").fetchall()
    finally:
        con.close()

    info = {"total": 0, "ok": 0, "ambiguo": 0, "fora_de_faixa": 0,
            "sem_calibracao": 0}
    for r in rows:
        info["total"] += 1
        res = georesolver.resolver(r["via"], r["km"], calibracao)
        info[res["status"]] = info.get(res["status"], 0) + 1
    return info


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(description="Validacao leave-one-out do georesolver.")
    ap.add_argument("--ancoras", default=georesolver.CAMINHO_ANCORAS_PADRAO,
                    help="CSV de ancoras (default: ancoras_limpas.csv)")
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--saida", default=SAIDA_PADRAO)
    ap.add_argument("--nome", default="validacao_limpa.csv",
                    help="nome do CSV de saida dentro de --saida")
    args = ap.parse_args(argv)

    if not os.path.exists(args.ancoras):
        print("ERRO: ancoras nao encontradas: %s (rode tools/limpar_calibracao.py)"
              % args.ancoras, file=sys.stderr)
        return 2

    calibracao = georesolver.carregar_ancoras(args.ancoras)
    por_seg = coletar_erros(calibracao)

    os.makedirs(args.saida, exist_ok=True)
    cam = os.path.join(args.saida, args.nome)
    todos = []
    with open(cam, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "segmento", "n", "erro_mediano_m",
                    "erro_p90_m", "erro_max_m"])
        for (via, seg) in sorted(por_seg, key=lambda k: (-len(por_seg[k]), k)):
            erros = por_seg[(via, seg)]
            todos.extend(erros)
            w.writerow([via, seg, len(erros),
                        "%.3f" % percentil(erros, 0.5),
                        "%.3f" % percentil(erros, 0.9),
                        "%.3f" % max(erros)])

    print("validacao: %s" % cam)
    print("segmentos testados (>=3 ancoras): %d" % len(por_seg))
    print("pontos leave-one-out: %d" % len(todos))
    if todos:
        print("ERRO GERAL (m): mediana=%.1f  p90=%.1f  max=%.1f"
              % (percentil(todos, 0.5), percentil(todos, 0.9), max(todos)))

    # Ranking por via (agrega os segmentos da mesma via) — top 10 por n.
    por_via = {}
    for (via, seg), erros in por_seg.items():
        por_via.setdefault(via, []).extend(erros)

    print("\nTop 10 vias por n de pontos leave-one-out:")
    print("%-12s %6s %12s %12s %12s" % ("via", "n", "mediano_m", "p90_m", "max_m"))
    rank = sorted(por_via, key=lambda v: (-len(por_via[v]), v))[:10]
    for via in rank:
        erros = por_via[via]
        print("%-12s %6d %12.1f %12.1f %12.1f"
              % (via, len(erros), percentil(erros, 0.5),
                 percentil(erros, 0.9), max(erros)))

    info = classificar_ponto(args.db, calibracao)
    if info:
        print("\nPontos com km no banco: %d" % info["total"])
        print("  ok (interpolaveis):    %d" % info["ok"])
        print("  ambiguos:              %d" % info.get("ambiguo", 0))
        print("  fora de faixa:         %d" % info["fora_de_faixa"])
        print("  sem calibracao:        %d" % info["sem_calibracao"])
    return 0
