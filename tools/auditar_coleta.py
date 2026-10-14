#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor POS-COLETA da cobertura: municipio e posicao, por fonte.

Rodado depois de cada coleta (ou por cron / heartbeat), mede por fonte:
  - pontos totais;
  - quantos com municipio resolvido (cobertura de municipio);
  - quantos com posicao geografica (cobertura de posicao).

Compara com um baseline versionado (``config/cobertura_fontes.json``) e
ALERTA quando:
  - aparece uma FONTE NOVA (coleta nova entrando); ou
  - a cobertura de municipio ou de posicao de uma fonte CAI (regressao).

Nao grava no banco. Sai com codigo 1 quando ha alerta, para o cron avisar.

Uso:
  python3 tools/auditar_coleta.py [--db CAMINHO] [--tolerancia 1.0]
  python3 tools/auditar_coleta.py --atualizar-baseline
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import ROOT                      # noqa: E402

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
BASELINE_PADRAO = os.path.join(ROOT, "config", "cobertura_fontes.json")

SQL_PONTOS = """
SELECT p.id AS ponto_id,
       p.municipio_id AS municipio_id,
       p.posicao_id   AS posicao_id,
       (SELECT f.nome
          FROM VINCULO_REGISTRO_PONTO v
          JOIN REGISTRO_FONTE r ON r.id = v.registro_id
          JOIN ARTEFATO_COLETA a ON a.id = r.artefato_id
          JOIN RECURSO_FONTE rf ON rf.id = a.recurso_id
          JOIN FONTE f ON f.id = rf.fonte_id
         WHERE v.ponto_id = p.id LIMIT 1) AS fonte
FROM PONTO_FISCALIZACAO p
"""


def medir(conn):
    """-> {fonte: {pontos, municipio, posicao, pct_municipio, pct_posicao}}."""
    por = {}
    for r in conn.execute(SQL_PONTOS):
        fonte = r["fonte"] or "(sem fonte)"
        d = por.setdefault(fonte, {"pontos": 0, "municipio": 0, "posicao": 0})
        d["pontos"] += 1
        if r["municipio_id"] is not None:
            d["municipio"] += 1
        if r["posicao_id"] is not None:
            d["posicao"] += 1
    for d in por.values():
        n = d["pontos"] or 1
        d["pct_municipio"] = round(100.0 * d["municipio"] / n, 2)
        d["pct_posicao"] = round(100.0 * d["posicao"] / n, 2)
    return por


def comparar(atual, baseline, tolerancia):
    """Lista de alertas (strings). Sem baseline: nao alerta (so informa)."""
    alertas = []
    if not baseline:
        return alertas
    for fonte, d in sorted(atual.items()):
        b = baseline.get(fonte)
        if b is None:
            alertas.append("FONTE NOVA: %s (%d pontos)" % (fonte, d["pontos"]))
            continue
        for campo in ("pct_municipio", "pct_posicao"):
            queda = b.get(campo, 0.0) - d[campo]
            if queda > tolerancia:
                alertas.append(
                    "%s: cobertura de %s caiu %.2f -> %.2f (%.2f p.p.)"
                    % (fonte, campo.replace("pct_", ""), b.get(campo, 0.0),
                       d[campo], queda))
    return alertas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monitor pos-coleta da cobertura.")
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--baseline", default=BASELINE_PADRAO)
    ap.add_argument("--tolerancia", type=float, default=1.0,
                    help="queda em p.p. que dispara alerta (padrao 1.0)")
    ap.add_argument("--atualizar-baseline", action="store_true",
                    help="grava o estado atual como novo baseline")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        atual = medir(conn)
    finally:
        conn.close()

    baseline = None
    if os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)

    if args.atualizar_baseline:
        os.makedirs(os.path.dirname(args.baseline), exist_ok=True)
        with open(args.baseline, "w", encoding="utf-8") as f:
            json.dump(atual, f, ensure_ascii=False, indent=2, sort_keys=True)
        print("baseline atualizado: %s" % args.baseline)

    alertas = comparar(atual, baseline, args.tolerancia)

    print("cobertura por fonte (%d fontes):" % len(atual))
    for fonte, d in sorted(atual.items(), key=lambda x: -x[1]["pontos"]):
        print("  %-42s pontos=%-6d municipio=%6.2f%%  posicao=%6.2f%%"
              % (fonte, d["pontos"], d["pct_municipio"], d["pct_posicao"]))
    if alertas:
        print("\nALERTAS (%d):" % len(alertas))
        for a in alertas:
            print("  ! %s" % a)
        return 1
    print("\nsem alertas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
