#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reaplica o parser ASTT a pontos sem GPS; so escreve numa NOVA copia."""
import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coletor.fontes.araguaiana_to import ColetorASTTAraguaina
from core import governanca


def abrir_leitura(caminho):
    conn = sqlite3.connect(Path(caminho).resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


##-- BUNDITA DE URSO #{22} -- O parser corrigido nao recuperava GPS ausente em cadastros legados quando o bruto permanecia igual. ##
def planejar(conn):
    coletor = ColetorASTTAraguaina(conn=conn)
    grupos = {}
    clausulas, params = governanca.clausulas_consulta(conn)
    sql = """
            SELECT p.id ponto_id, r.id registro_id, r.hash_registro,
                   r.payload_original, f.nome fonte
            FROM PONTO_FISCALIZACAO p
            JOIN VINCULO_REGISTRO_PONTO vp ON vp.ponto_id=p.id
            JOIN REGISTRO_FONTE r ON r.id=vp.registro_id
            JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
            JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
            JOIN FONTE f ON f.id=rf.fonte_id
            WHERE p.posicao_id IS NULL
              AND vp.decisao_id IS NULL
            """
    if clausulas:
        sql += " AND " + " AND ".join(clausulas)
    for row in conn.execute(sql + " ORDER BY p.id, r.id", params):
        grupos.setdefault(row["ponto_id"], []).append(row)
    planos = []
    for pid, rows in grupos.items():
        if any(r["fonte"] != coletor.FONTE["nome"] for r in rows):
            continue
        posicoes = []
        for row in rows:
            try:
                raw = json.loads(row["payload_original"])
                if not isinstance(raw, dict):
                    continue
                dado = coletor.normalizar(0, raw)
            except (ValueError, TypeError):
                continue
            lat, lon = dado["latitude"], dado["longitude"]
            if (lat is not None and lon is not None
                    and math.isfinite(lat) and math.isfinite(lon)
                    and -90 <= lat <= 90 and -180 <= lon <= 180):
                posicoes.append((row, dado))
        # Observacoes discordantes exigem revisao; nao escolher uma coordenada.
        if not posicoes or len({(d["latitude"], d["longitude"])
                               for _, d in posicoes}) != 1:
            continue
        row, dado = posicoes[0]
        planos.append({"ponto_id": pid, "registro_id": row["registro_id"],
                       "hash_registro": row["hash_registro"],
                       "latitude": dado["latitude"], "longitude": dado["longitude"],
                       "qualidade": dado["qualidade"],
                       "metodo_obtencao": "renormalizacao_legada_22; " + dado["metodo_obtencao"]})
    return planos


def recuperar(caminho, saida=None):
    origem = Path(caminho).resolve(strict=True)
    destino = Path(saida).resolve() if saida else None
    if destino and (destino == origem or destino.exists()):
        raise ValueError("a saida precisa ser um arquivo novo, diferente da origem")
    fonte = abrir_leitura(origem)
    try:
        if destino is None:
            return {"modo": "simulacao", "recuperaveis": planejar(fonte)}
        # Publicar uma copia finalizada, sem sobrescrever um arquivo existente.
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".recuperacao-",
                                         suffix=".sqlite3", delete=False) as tmp:
            temporario = Path(tmp.name)
        try:
            copia = sqlite3.connect(temporario)
            copia.row_factory = sqlite3.Row
            try:
                fonte.backup(copia)
                copia.execute("PRAGMA journal_mode=DELETE")
                copia.execute("PRAGMA foreign_keys=ON")
                planos = planejar(copia)
                with copia:
                    for plano in planos:
                        qualidade = copia.execute(
                            "SELECT id FROM QUALIDADE_POSICAO WHERE codigo=?",
                            (plano["qualidade"],)).fetchone()[0]
                        pos = copia.execute("""
                            INSERT INTO POSICAO_GEOGRAFICA
                              (latitude,longitude,qualidade_posicao_id,metodo_obtencao,registro_fonte_id)
                            VALUES (?,?,?,?,?)""", (plano["latitude"], plano["longitude"], qualidade,
                                                  plano["metodo_obtencao"], plano["registro_id"]))
                        copia.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=? "
                                      "WHERE id=? AND posicao_id IS NULL",
                                      (pos.lastrowid, plano["ponto_id"]))
                if (copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                        or copia.execute("PRAGMA foreign_key_check").fetchone() is not None):
                    raise ValueError("a copia nao passou nas verificacoes de integridade")
            finally:
                copia.close()
            os.link(temporario, destino)
        finally:
            temporario.unlink(missing_ok=True)
        return {"modo": "copia_recuperada", "saida": str(destino), "recuperadas": planos}
    finally:
        fonte.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="origem aberta somente para leitura")
    parser.add_argument("--saida", help="novo SQLite; sem esta opcao apenas lista o plano")
    args = parser.parse_args(argv)
    print(json.dumps(recuperar(args.db, args.saida), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
