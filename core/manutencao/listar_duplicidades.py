#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lista propostas por escopo em JSON; nao gera, decide ou aplica alteracoes."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys


from core import dedup
from core.contexto_api import operacao_local
from core import db as dbmod


##-- BUNDITA DE URSO #{26} -- Revisar local e instrumento na mesma lista sem indicar escopo induzia unificacoes incorretas. ##
def listar(caminho, escopo, limite=50, cursor=0, diagnosticos=False):
    if escopo not in ("ponto", "equipamento", "ambos"):
        raise ValueError("indique escopo: ponto, equipamento ou ambos")
    if not 1 <= limite <= 1000 or cursor < 0:
        raise ValueError("limite deve estar entre 1 e 1000; cursor deve ser nao negativo")
    conn = dbmod.connect(Path(caminho).resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = dedup.candidatos(conn, estado="pendente", escopo=escopo,
                               incluir_diagnosticos=diagnosticos)
        pagina = rows[cursor:cursor + limite]
        for row in pagina:
            row["evidencias_resumo"] = json.loads(row["evidencias_resumo"])
        return {"regra": dedup.VERSAO_REGRA_PADRAO, "escopo": escopo,
                "inclui_diagnosticos": diagnosticos, "total": len(rows), "retornados": len(pagina),
                "proximo_cursor": cursor + limite if cursor + limite < len(rows) else None,
                "candidatos": pagina}
    finally:
        conn.close()


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--escopo", choices=("ponto", "equipamento", "ambos"), required=True)
    parser.add_argument("--limite", type=int, default=50)
    parser.add_argument("--cursor", type=int, default=0)
    parser.add_argument("--diagnosticos", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(listar(args.db, args.escopo, args.limite, args.cursor, args.diagnosticos),
                     ensure_ascii=False, indent=2))
    return 0
