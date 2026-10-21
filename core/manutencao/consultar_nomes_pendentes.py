#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pendentes de municipio: resolve por aproximacao e, no que sobrar, PERGUNTA
ao MODELO LOCAL (ollama). O modelo apenas PROPÕE; quem decide e o cadastro
oficial do IBGE (validacao deterministica). Nada e inventado.

Por que assim
-------------
Um modelo de linguagem erra codigo IBGE com facilidade (medido: o gemma4
respondeu ``5106105`` para Poxoreu/MT, cujo codigo real e ``5106109``). Por
isso a consulta ao modelo serve so para AMPLIAR o texto candidato; o candidato
volta e e conferido contra a lista oficial (exato ou aproximado com margem).
Se nao fechar, fica NULL e vai para revisao humana.

Fluxo, por (uf, nome) distinto pendente
---------------------------------------
1. casamento aproximado deterministico (``core.casamento_municipio``);
2. se falhar, pergunta ao ollama o nome oficial + UF (JSON);
3. valida a sugestao contra MUNICIPIO (exato ou aproximado com margem);
4. confiante -> proposta (CSV e, com ``--aplicar``, o
   ``config/correcoes_municipio.csv`` reaplicavel);
   nao confiante -> ``revisar_humano``.

Uso:
  python3 tools/consultar_nomes_pendentes.py            # so reporta
  sudo python3 tools/consultar_nomes_pendentes.py --aplicar
  --modelo gemma4:26b --ollama http://127.0.0.1:11434 --limite 200
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request


from core import config                                     # noqa: E402
from core import correcoes_municipio as corr                # noqa: E402
from core import casamento_municipio as cm                  # noqa: E402
from core.manutencao.preencher_municipio import (                     # noqa: E402
    SQL_PONTOS, extrair_municipio_uf, uf_da_fonte)
from core.contexto_api import operacao_local
from core import db as dbmod
from core import caminhos  # caminhos so pela porta unica

DB_PADRAO = caminhos.banco()
OLLAMA_PADRAO = caminhos.valor("assistente", "url")[0]
MODELO_PADRAO = caminhos.valor("assistente", "modelo")[0]
CSV_PADRAO = os.path.join(config.ROOT, "dados", "calibracao",
                          "nomes_pendentes.csv")

PROMPT = (
    "Voce resolve nomes de municipios brasileiros. Dado um nome como a fonte "
    "publicou, responda o NOME OFICIAL do municipio (como no IBGE) e a sigla "
    "da UF. Responda SOMENTE um JSON: "
    '{"municipio": "<nome oficial>", "uf": "<2 letras>"}. '
    "Se nao tiver certeza, responda "
    '{"municipio": "", "uf": ""}.\n'
    "Nome publicado: %s\nUF declarada pela fonte: %s\n"
)


def pendentes(conn):
    """-> {(uf, nome): {"pontos": [ids], "fonte": nome_fonte}}."""
    grupos = {}
    for r in conn.execute(SQL_PONTOS):
        nome, uf = extrair_municipio_uf(r["payload"])
        if not nome:
            continue
        if not uf:
            uf = uf_da_fonte(r["fonte"])
        chave = (uf or "", nome)
        g = grupos.setdefault(chave, {"pontos": [], "fonte": r["fonte"]})
        g["pontos"].append(r["ponto_id"])
    return grupos


def perguntar_modelo(base, modelo, nome, uf, timeout=90):
    """-> dict {"municipio","uf"} proposto pelo modelo local (ou None)."""
    corpo = json.dumps({
        "model": modelo,
        "prompt": PROMPT % (nome, uf or "(nao informada)"),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/api/generate", data=corpo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    try:
        saida = json.loads(dados.get("response", "") or "{}")
    except ValueError:
        return None
    if not isinstance(saida, dict):
        return None
    return saida


def validar_sugestao(conn, sugestao):
    """Confere a sugestao do modelo contra o cadastro IBGE (deterministico).

    -> (codigo, uf, score, motivo) ou (None, None, score, motivo).
    """
    if not sugestao:
        return None, None, 0.0, "sem_sugestao"
    nome = (sugestao.get("municipio") or "").strip()
    uf = (sugestao.get("uf") or "").strip().upper()[:2] or None
    if not nome:
        return None, None, 0.0, "modelo_sem_resposta"
    # 1) exato (nome + uf) na lista oficial
    alvo = cm.normalizar(nome)
    for r in conn.execute(
            "SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO"
            + (" WHERE uf_sigla=?" if uf else ""), (uf,) if uf else ()):
        if cm.normalizar(r["nome"]) == alvo:
            return r["codigo_ibge"], r["uf_sigla"], 1.0, "exato"
    # 2) aproximado (com margem) contra a lista oficial
    indice = cm.Indice.do_banco(conn)
    d = cm.resolver(indice, nome, uf)
    if d and d.get("preenche"):
        return d["codigo"], d["cand_uf"], d["score"], "aproximado"
    return None, None, (d["score"] if d else 0.0), "nao_confirmado"


def analisar(conn, grupos, base, modelo, limite, consultar=True):
    """-> lista de propostas {nome_fonte, uf_fonte, origem, ...}."""
    indice = cm.Indice.do_banco(conn)
    propostas = []
    for (uf, nome), g in sorted(grupos.items(),
                                key=lambda x: -len(x[1]["pontos"])):
        if limite and len(propostas) >= limite:
            break
        d = cm.resolver(indice, nome, uf)
        if d and d.get("preenche"):
            propostas.append({
                "nome_fonte": nome, "uf_fonte": uf, "origem": "aproximacao",
                "municipio": d["cand_nome"], "uf_sug": d["cand_uf"],
                "codigo": d["codigo"], "score": d["score"],
                "motivo": d["motivo"], "pontos": g["pontos"],
            })
            continue
        sugestao = (perguntar_modelo(base, modelo, nome, uf)
                    if consultar else None)
        codigo, uf_sug, score, motivo = validar_sugestao(conn, sugestao)
        propostas.append({
            "nome_fonte": nome, "uf_fonte": uf,
            "origem": "modelo_validado" if codigo else "revisar_humano",
            "municipio": (sugestao or {}).get("municipio", ""),
            "uf_sug": uf_sug or (sugestao or {}).get("uf", ""),
            "codigo": codigo, "score": score,
            "motivo": motivo + ("|ollama_off" if (sugestao is None and
                                                 consultar) else ""),
            "pontos": g["pontos"],
        })
    return propostas


def escrever_csv(caminho, propostas):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nome_fonte", "uf_fonte", "origem", "municipio_sugerido",
                    "uf_sugerida", "codigo_ibge", "score", "motivo",
                    "pontos"])
        for p in propostas:
            w.writerow([p["nome_fonte"], p["uf_fonte"], p["origem"],
                        p["municipio"], p["uf_sug"], p["codigo"] or "",
                        "%.3f" % p["score"] if p["score"] else "",
                        p["motivo"], len(p["pontos"])])
    return caminho


def aplicar(propostas, db, csv_correcoes=corr.CAMINHO_PADRAO):
    """Grava as propostas confiaveis no CSV reaplicavel e aplica no banco."""
    linhas = [p for p in propostas if p["codigo"]]
    if not linhas:
        print("nada confiavel para aplicar.")
        return 0
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = "%s.bak.%s" % (db, ts)
    shutil.copy2(db, destino)
    print("backup: %s" % destino)
    with open(csv_correcoes, "a", encoding="utf-8") as f:
        for p in linhas:
            for pid in p["pontos"]:
                f.write("%s;%s;%s\n" % (pid, p["codigo"], p["origem"]))
    conn = dbmod.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        res = corr.aplicar_correcoes(conn, corr.carregar_correcoes(csv_correcoes))
    finally:
        conn.close()
    return res


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Resolve pendentes por aproximacao e consulta ao modelo.")
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--ollama", default=OLLAMA_PADRAO)
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    ap.add_argument("--saida", default=CSV_PADRAO)
    ap.add_argument("--limite", type=int, default=0,
                    help="maximo de decisoes distintas a processar (0=todas)")
    ap.add_argument("--sem-modelo", action="store_true",
                    help="nao consulta o ollama (so aproximacao deterministica)")
    ap.add_argument("--aplicar", action="store_true",
                    help="grava o confiavel no CSV reaplicavel e aplica")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    conn = dbmod.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        grupos = pendentes(conn)
        if args.limite:
            grupos = dict(list(grupos.items())[:args.limite])
        propostas = analisar(conn, grupos, args.ollama, args.modelo,
                             args.limite, consultar=not args.sem_modelo)
    finally:
        conn.close()

    caminho = escrever_csv(args.saida, propostas)
    n_aprox = sum(1 for p in propostas if p["origem"] == "aproximacao")
    n_mod = sum(1 for p in propostas if p["origem"] == "modelo_validado")
    n_rev = sum(1 for p in propostas if p["origem"] == "revisar_humano")
    print("decisoes distintas pendentes: %d" % len(propostas))
    print("  resolvidas por aproximacao:  %d" % n_aprox)
    print("  resolvidas pelo modelo+IBGE: %d" % n_mod)
    print("  para revisao humana:         %d" % n_rev)
    print("CSV: %s" % caminho)
    for p in propostas[:12]:
        print("  [%-15s] %-32s uf=%-3s -> %s/%s %s"
              % (p["origem"], p["nome_fonte"][:32], p["uf_fonte"] or "-",
                 p["codigo"] or "-", p["uf_sug"] or "-", p["motivo"]))
    if args.aplicar:
        res = aplicar(propostas, args.db)
        if res:
            print("aplicado: %s" % res)
    return 0
