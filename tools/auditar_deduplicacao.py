#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compara a geracao vigente numa copia temporaria; o banco informado e read-only."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import consultas, db, dedup
from core.identidade import VisaoCanonica


def _resumo(conn):
    regras = {}
    for row in conn.execute("""
            SELECT r.versao, c.estado, c.evidencias_resumo
            FROM CANDIDATO_DUPLICIDADE c
            JOIN REGRA_DEDUPLICACAO r ON r.id=c.regra_id ORDER BY c.id"""):
        regra = regras.setdefault(row[0], {"total": 0, "por_estado": collections.Counter(),
                                          "por_nivel": collections.Counter()})
        regra["total"] += 1
        regra["por_estado"][row[1]] += 1
        regra["por_nivel"][json.loads(row[2]).get("nivel", "desconhecido")] += 1
    return regras


##-- BUNDITA DE URSO #{20} -- Reduzir candidatos nao comprova conservar os registros e as marcacoes originais. ##
def _inventario(conn):
    saida = {}
    for tabela in ("REGISTRO_FONTE", "POSICAO_GEOGRAFICA", "PONTO_FISCALIZACAO",
                   "EQUIPAMENTO", "FAIXA_FISCALIZACAO", "INSTALACAO",
                   "LIMITE_VELOCIDADE", "REGIME_FISCALIZACAO", "VERIFICACAO_METROLOGICA"):
        assinatura = hashlib.sha256()
        total = 0
        for row in conn.execute("SELECT * FROM %s ORDER BY id" % tabela):
            assinatura.update(json.dumps(list(row), ensure_ascii=False, default=repr).encode("utf-8"))
            assinatura.update(b"\n")
            total += 1
        saida[tabela] = {"registros": total, "sha256": assinatura.hexdigest()}
    return saida


def _conservacao_consulta(conn):
    visao = VisaoCanonica(conn)
    clausulas, params = consultas._filtros_extra({"incluir_inativos": True}, conn)
    where = ["pos.latitude IS NOT NULL", "pos.longitude IS NOT NULL"] + clausulas
    rows = db.query_all(conn, consultas._PONTO_SQL + " WHERE " + " AND ".join(where), params)
    perdas, explicitas = [], 0
    for row in rows:
        projetada = consultas._linha_canonica(conn, row, visao)
        if projetada is None:
            # Uma exclusao/moderacao explicita do mesmo local nao e perda acidental.
            canonico = visao.canonico("ponto", row["ponto_id"])
            sql = consultas._PONTO_SQL + " WHERE p.id=?"
            original = db.query_one(conn, sql, (canonico,))
            if clausulas:
                sql += " AND " + " AND ".join(clausulas)
            visivel = db.query_one(conn, sql, [canonico] + params)
            if canonico != row["ponto_id"] and original is not None and visivel is None:
                explicitas += 1
                continue
        if projetada is None or any(projetada[k] != row[k] for k in ("latitude", "longitude")):
            perdas.append("P-%d" % row["ponto_id"])
    return {"marcacoes_com_gps_examinadas": len(rows),
            "ocultacoes_explicitas_de_aliases": explicitas,
            "marcacoes_nao_representadas": perdas}


##-- BUNDITA DE URSO #{4} -- Comparar uma nova regra nao deve sobrescrever fila historica ou banco de producao. ##
def auditar(caminho):
    origem = Path(caminho).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="bundita-auditoria-") as pasta:
        copia = db.connect(str(Path(pasta, "radar.sqlite3")))
        try:
            fonte = sqlite3.connect(origem.as_uri() + "?mode=ro", uri=True)
            try:
                fonte.backup(copia)
            finally:
                fonte.close()
            antes = _resumo(copia)
            inventario_antes = _inventario(copia)
            resultado = dedup.gerar_candidatos(copia)
            inventario_depois = _inventario(copia)
            return {
                "regra": dedup.VERSAO_REGRA_PADRAO,
                "antes": antes, "depois": _resumo(copia),
                "registros": resultado["total_registros"],
                "candidatos_criados": len(resultado["criados"]),
                "candidatos_existentes": len(resultado["existentes"]),
                "fila_vigente_pendente": len(dedup.candidatos(copia, estado="pendente")),
                "decisoes_aplicadas_nesta_auditoria": 0,
                "conservacao": {
                    "inventario_original_inalterado": inventario_antes == inventario_depois,
                    "antes": inventario_antes, "depois": inventario_depois,
                    **_conservacao_consulta(copia),
                },
            }
        finally:
            copia.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="banco existente, aberto somente para leitura")
    args = parser.parse_args(argv)
    resultado = auditar(args.db)
    print(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))
    conservacao = resultado["conservacao"]
    return int(not conservacao["inventario_original_inalterado"] or bool(conservacao["marcacoes_nao_representadas"]))


if __name__ == "__main__":
    raise SystemExit(main())
