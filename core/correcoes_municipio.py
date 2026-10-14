# -*- coding: utf-8 -*-
"""Correcoes de municipio REAPLICAVEIS (ponto_id -> codigo_ibge).

Le um CSV versionado (``config/correcoes_municipio.csv``) e aplica
``UPDATE PONTO_FISCALIZACAO SET municipio_id = ? WHERE id = ?`` de forma
IDEMPOTENTE: reaplicar o mesmo arquivo nao altera nada (o valor ja esta igual).
Nada e inventado — linha cujo ponto ou codigo IBGE nao exista e apenas contada
como ignorada, sem tocar no banco.

Formato do CSV (``;``), com cabecalho::

    ponto_id;codigo_ibge;motivo

Linhas em branco ou iniciadas por ``#`` sao ignoradas (comentarios).
"""
import csv
import io
import logging
import os

from core import db as dbmod

log = logging.getLogger(__name__)

COLUNAS = ("ponto_id", "codigo_ibge", "motivo")
CAMINHO_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "correcoes_municipio.csv")


def carregar_correcoes(caminho=None):
    """Le o CSV de correcoes -> lista de dicts {ponto_id, codigo_ibge, motivo}.

    Aceita comentarios (``#``) e linhas em branco.  Nao valida contra o banco
    (isso e feito na aplicacao), mas ignora linhas sem ``ponto_id`` ou
    ``codigo_ibge``.
    """
    caminho = caminho or CAMINHO_PADRAO
    with open(caminho, "r", encoding="utf-8-sig") as f:
        linhas = [ln for ln in f
                  if ln.strip() and not ln.lstrip().startswith("#")]
    correcoes = []
    for row in csv.DictReader(io.StringIO("".join(linhas)), delimiter=";"):
        ponto = (row.get("ponto_id") or "").strip()
        codigo = (row.get("codigo_ibge") or "").strip()
        if not ponto or not codigo:
            continue
        correcoes.append({
            "ponto_id": ponto,
            "codigo_ibge": codigo,
            "motivo": (row.get("motivo") or "").strip(),
        })
    return correcoes


def _indice(conn, sql):
    return {str(r[0]) for r in conn.execute(sql)}


def aplicar_correcoes(conn, correcoes, dry_run=False):
    """Aplica as correcoes; devolve estatisticas.  Idempotente.

    Chaves do retorno: total, alterados, ja_corretos, ponto_inexistente,
    codigo_desconhecido, duplicados.
    """
    pontos = _indice(conn, "SELECT id FROM PONTO_FISCALIZACAO")
    municipios = _indice(conn, "SELECT codigo_ibge FROM MUNICIPIO")
    atual = {str(r[0]): (str(r[1]) if r[1] is not None else None)
             for r in conn.execute(
                 "SELECT id, municipio_id FROM PONTO_FISCALIZACAO")}
    est = {"total": len(correcoes), "alterados": 0, "ja_corretos": 0,
           "ponto_inexistente": 0, "codigo_desconhecido": 0, "duplicados": 0}
    vistos = set()
    for c in correcoes:
        pid = c["ponto_id"]
        cod = c["codigo_ibge"]
        chave = (pid, cod)
        if chave in vistos:
            est["duplicados"] += 1
            continue
        vistos.add(chave)
        if pid not in pontos:
            est["ponto_inexistente"] += 1
            continue
        if cod not in municipios:
            est["codigo_desconhecido"] += 1
            continue
        if atual.get(pid) == cod:
            est["ja_corretos"] += 1
            continue
        if not dry_run:
            conn.execute(
                "UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?",
                (cod, int(pid)))
        est["alterados"] += 1
    if not dry_run:
        conn.commit()
    return est


def reaplicar(conn, caminho=None, dry_run=False):
    """Carrega o CSV e aplica (atalho).  Retorna (correcoes, stats)."""
    correcoes = carregar_correcoes(caminho)
    return correcoes, aplicar_correcoes(conn, correcoes, dry_run=dry_run)


def resolver_via_uf(conn):
    """Deriva VIA_UF (via -> UF) dos municipios dos pontos.  Idempotente."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO VIA_UF (via_id, uf_sigla) "
        "SELECT DISTINCT p.via_id, m.uf_sigla "
        "FROM PONTO_FISCALIZACAO p "
        "JOIN MUNICIPIO m ON m.codigo_ibge = p.municipio_id "
        "WHERE p.via_id IS NOT NULL AND p.municipio_id IS NOT NULL")
    conn.commit()
    return cur.rowcount
