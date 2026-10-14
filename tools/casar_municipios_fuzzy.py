#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Casamento aproximado (fuzzy + fonetico) dos municipios que ficaram NULL.

Sobraram em ``PONTO_FISCALIZACAO.municipio_id`` os pontos cujo nome de
municipio publicado pela fonte NAO bate exatamente com a lista oficial do
IBGE (ex.: ``POXOREO`` x *Poxoreu*, ``SAO LUIS DO PARAITINGA`` x *Sao Luiz do
Paraitinga*, ``CARIRI DE TOCANTINS`` x *Cariri do Tocantins*). Este utilitario
faz o casamento aproximado e PREENCHE apenas quando ha confianca.

Algoritmo
---------
1. Normaliza o nome: NFKD sem acento, maiusculas, espacos colapsados,
   pontuacao removida e conectivos (DE/DA/DO/DAS/DOS/E) descartados.
2. Compara contra ``MUNICIPIO`` com ``difflib.SequenceMatcher`` (ratio) e uma
   chave fonetica simples adaptada do portugues (colapsa equivalentes:
   S/Z/X, C/K/Q, G/J, V/F, H/W/Y mudos).
3. ESCOPO: primeiro dentro da UF do payload (ou, na falta dela, da UF tirada
   do nome da fonte); sem candidato confiavel na UF, tenta NACIONALMENTE
   apenas quando o nome for unico (sem empate, com margem). Excecao: se a
   propria UF tem o alvo acrescido de qualificador (``TUNAS`` -> *Tunas do
   Parana*), nao se cruza a UF (a fonte so omitiu o qualificador).
4. PREENCHE somente quando confiante: ``ratio >= 0.85`` E margem ``>= 0.05``
   sobre o segundo colocado (leitura conservadora: o item "ratio >= 0.90" da
   regra tambem exige que nao exista quasi-empate). Nada e inventado: sem
   confianca o campo permanece NULL.

Saida (para conferencia do Lucas):
  dados/calibracao/municipios_duvidosos.csv
      nome_fonte;uf_fonte;melhor_candidato;uf_candidato;score;motivo
      (traz os NAO casados e tambem os casados com UF divergente da fonte)

Uso:
  python3 tools/casar_municipios_fuzzy.py --dry-run     # so mede e reporta
  sudo python3 tools/casar_municipios_fuzzy.py          # aplica (backup antes)
"""
import argparse
import csv
import difflib
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor.fontes import normalizacao as nz                  # noqa: E402
from core.config import ROOT                                   # noqa: E402
from tools.preencher_municipio import (                         # noqa: E402
    extrair_municipio_uf, uf_da_fonte, SQL_PONTOS)

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
CSV_PADRAO = os.path.join(ROOT, "dados", "calibracao",
                          "municipios_duvidosos.csv")

# conectivos descartados na normalizacao
from core.casamento_municipio import (                         # noqa: E402
    CONECTIVOS, LIMIAR, MARGEM, FAIXAS, _faixa, Indice, avaliar,
    chave_fonetica, normalizar, resolver, score)


def processar(conn, aplicar=True):
    indice = Indice.do_banco(conn)
    res = {
        "total": 0, "sem_nome": 0, "preenchidos": 0, "nao_preenchidos": 0,
        "por_faixa": {rot: 0 for _, _, rot in FAIXAS},
        "por_escopo": {"uf": 0, "nacional": 0},
        "uf_divergente": 0, "na_uf_divergente": 0,
        "duvidosos": [], "atualizacoes": [], "exemplos": {},
    }
    EXEMPLOS = {"POXOREO", "SAO LUIS PARAITINGA", "CARIRI TOCANTINS",
                "BRASILIA", "BOA VISTA"}
    for r in conn.execute(SQL_PONTOS):
        res["total"] += 1
        nome, uf = extrair_municipio_uf(r["payload"])
        if not nome:
            res["sem_nome"] += 1
            continue
        if not uf:
            uf = uf_da_fonte(r["fonte"])
        d = resolver(indice, nome, uf)
        if d is None:
            res["sem_nome"] += 1
            continue
        if normalizar(nome) in EXEMPLOS and normalizar(nome) not in res["exemplos"]:
            res["exemplos"][normalizar(nome)] = dict(d, nome_fonte=nome, uf_fonte=uf)
        if d["preenche"]:
            res["preenchidos"] += 1
            res["por_faixa"][_faixa(d["score"])] += 1
            res["por_escopo"][d["escopo"]] += 1
            res["atualizacoes"].append((d["codigo"], r["ponto_id"]))
            if d["motivo"] == "uf_divergente":
                res["uf_divergente"] += 1
                res["duvidosos"].append((nome, uf, d["cand_nome"], d["cand_uf"],
                                         d["score"], "uf_divergente"))
        else:
            res["nao_preenchidos"] += 1
            res["duvidosos"].append((nome, uf, d["cand_nome"], d["cand_uf"],
                                     d["score"], d["motivo"]))
    if aplicar and res["atualizacoes"]:
        conn.executemany(
            "UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?",
            res["atualizacoes"])
        conn.commit()
    return res


def escrever_csv(caminho, duvidosos):
    """CSV de conferencia: uma linha por decisao distinta (sem repetir pontos)."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    vistos = set()
    linhas = []
    for nome, uf, cand, cand_uf, sc, motivo in duvidosos:
        chave = (nome or "", uf or "", cand or "", cand_uf or "", motivo)
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append((motivo, nome or "", uf or "", cand or "", cand_uf or "",
                       "%.3f" % sc if sc else ""))
    linhas.sort()
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nome_fonte", "uf_fonte", "melhor_candidato",
                    "uf_candidato", "score", "motivo"])
        for _m, nome, uf, cand, cand_uf, sc in linhas:
            w.writerow([nome, uf, cand, cand_uf, sc, _m])
    return caminho, len(linhas)


def contar(conn, cond=""):
    return conn.execute(
        "SELECT COUNT(*) FROM PONTO_FISCALIZACAO %s" % cond).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Casamento aproximado (fuzzy/fonetico) de municipio.")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite")
    ap.add_argument("--saida", default=CSV_PADRAO,
                    help="CSV de municipios duvidosos")
    ap.add_argument("--dry-run", action="store_true",
                    help="mede e reporta sem gravar no banco")
    ap.add_argument("--sem-backup", action="store_true",
                    help="nao faz backup antes de gravar (nao recomendado)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    aplicar = not args.dry_run
    if aplicar and not args.sem_backup:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = "%s.bak.%s" % (args.db, ts)
        shutil.copy2(args.db, destino)
        print("backup: %s" % destino)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        antes = contar(conn, "WHERE municipio_id IS NOT NULL")
        res = processar(conn, aplicar=aplicar)
        depois = contar(conn, "WHERE municipio_id IS NOT NULL")
    finally:
        conn.close()

    csv_path, n_duv = escrever_csv(args.saida, res["duvidosos"])
    total_pontos = antes + res["total"]

    print("modo: %s" % ("dry-run (nada gravado)" if args.dry_run
                        else "aplicado"))
    print("pontos com municipio NULL analisados: %d" % res["total"])
    print("  sem nome de municipio no payload: %d" % res["sem_nome"])
    print("  preenchidos agora: %d" % res["preenchidos"])
    for _, _, rot in FAIXAS:
        print("      score %-10s %5d" % (rot, res["por_faixa"][rot]))
    print("      escopo: na UF=%d, nacional=%d (uf_divergente=%d)"
          % (res["por_escopo"]["uf"], res["por_escopo"]["nacional"],
             res["uf_divergente"]))
    print("  permanecem NULL (nao confiavel): %d" % res["nao_preenchidos"])
    print("PONTO_FISCALIZACAO com municipio: %d -> %d (de %d; %d ainda NULL)"
          % (antes, depois, total_pontos, total_pontos - depois))
    print("CSV duvidosos: %s (%d decisoes distintas)" % (csv_path, n_duv))
    print("--- exemplos ---")
    for chave in ("POXOREO", "SAO LUIS PARAITINGA", "CARIRI TOCANTINS",
                  "BRASILIA", "BOA VISTA"):
        e = res["exemplos"].get(chave)
        if not e:
            continue
        print("  %-22s uf_fonte=%-4s -> %s/%s score=%.3f margem=%.3f "
              "escopo=%s %s"
              % (chave, e["uf_fonte"] or "-", e["cand_nome"] or "-",
                 e["cand_uf"] or "-", e["score"], e["margem"], e["escopo"],
                 "PREENCHE" if e["preenche"] else "NULL (%s)" % e["motivo"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
