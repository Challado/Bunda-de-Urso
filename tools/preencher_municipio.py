#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill de ``PONTO_FISCALIZACAO.municipio_id`` a partir do payload bruto.

Para cada ponto sem municipio_id, recupera o nome do municipio (e a UF, quando
publicada) do payload original do REGISTRO_FONTE ligado ao ponto e resolve
contra a tabela ``MUNICIPIO`` (carga oficial do IBGE). Nada e inventado: sem
correspondencia oficial na lista, o campo permanece NULL.

Ligacao ponto -> registro (checada no banco):
  PONTO_FISCALIZACAO.id --(VINCULO_REGISTRO_PONTO)--> REGISTRO_FONTE.payload_original
  e, como reforco, POSICAO_GEOGRAFICA.registro_fonte_id.

Ordem de determinacao da UF:
  1. UF publicada no payload (chaves UF / SiglaUf / uf_sigla);
  2. UF do escopo da FONTE (sigla de 2 letras no nome do cadastro, ex.: DER-MG);
  3. nome de municipio unico no pais (so quando nao ha UF em lugar nenhum).

Tambem deriva VIA_UF (via -> UF) a partir dos municipios dos pontos.

Uso:
  python3 tools/preencher_municipio.py [--db CAMINHO] [--dry-run] [--backup]
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor.fontes import normalizacao as nz   # noqa: E402
from core import config                          # noqa: E402

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO")
_UF_RE = re.compile(r"\b(%s)\b" % "|".join(UFS))
_COD_PAREN = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def _chave_uf(k):
    return re.sub(r"[^A-Z]", "", nz.normalizar_nome_texto(k))


def extrair_municipio_uf(payload):
    """Le (municipio_nome, uf) do payload bruto. Nao inventa: devolve None."""
    try:
        d = json.loads(payload) if isinstance(payload, str) else payload
    except (ValueError, TypeError):
        return None, None
    if not isinstance(d, dict):
        return None, None
    nome = uf = None
    for k, v in d.items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip():
            continue
        ck = _chave_uf(k)
        if nome is None and ck.startswith("MUNICIPIO"):
            nome = _COD_PAREN.sub("", v.strip())
        elif uf is None and ck in ("UF", "SIGLAUF", "UFSIGLA"):
            cand = v.strip().upper()[:2]
            if cand in UFS:
                uf = cand
    return nome, uf


def uf_da_fonte(nome_fonte):
    """Deriva a UF do escopo da fonte a partir do proprio cadastro (nome)."""
    if not nome_fonte:
        return None
    m = _UF_RE.search(nz.normalizar_nome_texto(nome_fonte))
    return m.group(1) if m else None


def carregar_indice(conn):
    """Constroi { (uf, nome_norm): codigo } e { nome_norm: {ufs} }."""
    idx, global_names = {}, {}
    for r in conn.execute("SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO"):
        cod, uf, nome = r["codigo_ibge"], r["uf_sigla"], r["nome"]
        nn = nz.normalizar_nome_texto(nome)
        idx[(uf, nn)] = cod
        global_names.setdefault(nn, set()).add(uf)
    return idx, global_names


def resolver(idx, global_names, nome, uf):
    if not nome:
        return None
    nn = nz.normalizar_nome_texto(nome)
    if uf:
        return idx.get((uf, nn))
    ufs = global_names.get(nn)
    if ufs and len(ufs) == 1:
        return idx.get((next(iter(ufs)), nn))
    return None


SQL_PONTOS = """
SELECT p.id            AS ponto_id,
       f.nome          AS fonte,
       r.payload_original AS payload
FROM PONTO_FISCALIZACAO p
LEFT JOIN VINCULO_REGISTRO_PONTO v ON v.ponto_id = p.id
LEFT JOIN POSICAO_GEOGRAFICA g    ON g.id = p.posicao_id
LEFT JOIN REGISTRO_FONTE r
       ON r.id = COALESCE(v.registro_id, g.registro_fonte_id)
LEFT JOIN ARTEFATO_COLETA a ON a.id = r.artefato_id
LEFT JOIN RECURSO_FONTE rf  ON rf.id = a.recurso_id
LEFT JOIN FONTE f           ON f.id = rf.fonte_id
WHERE p.municipio_id IS NULL
ORDER BY p.id
"""


def resolver_via_uf(conn):
    """Popula VIA_UF a partir do municipio (->UF) dos pontos. Devolve n linhas."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO VIA_UF (via_id, uf_sigla) "
        "SELECT DISTINCT p.via_id, m.uf_sigla "
        "FROM PONTO_FISCALIZACAO p "
        "JOIN MUNICIPIO m ON m.codigo_ibge = p.municipio_id "
        "WHERE p.via_id IS NOT NULL AND p.municipio_id IS NOT NULL")
    conn.commit()
    return cur.rowcount


def backfill(conn, aplicar=True):
    idx, global_names = carregar_indice(conn)
    total = preenchidos = sem_match = sem_dado = 0
    por_fonte = {}
    atualizacoes = []
    for r in conn.execute(SQL_PONTOS):
        total += 1
        nome, uf = extrair_municipio_uf(r["payload"])
        if nome and not uf:
            uf = uf_da_fonte(r["fonte"])
        cod = resolver(idx, global_names, nome, uf)
        if cod:
            preenchidos += 1
            atualizacoes.append((cod, r["ponto_id"]))
            por_fonte[r["fonte"]] = por_fonte.get(r["fonte"], 0) + 1
        elif not nome:
            sem_dado += 1
        else:
            sem_match += 1
    if aplicar and atualizacoes:
        conn.executemany(
            "UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?",
            atualizacoes)
        conn.commit()
    return {"total": total, "preenchidos": preenchidos,
            "sem_match": sem_match, "sem_dado": sem_dado,
            "por_fonte": por_fonte}


def contar(conn, tabela, cond=""):
    return conn.execute(
        "SELECT COUNT(*) FROM %s %s" % (tabela, cond)).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Backfill de municipio_id a partir do payload bruto.")
    ap.add_argument("--db", default=config.DB_PATH, help="banco SQLite")
    ap.add_argument("--dry-run", action="store_true",
                    help="mede sem gravar (usa o proprio banco)")
    ap.add_argument("--backup", action="store_true",
                    help="copia o banco para <db>.bak.<timestamp> antes de gravar")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    if args.backup and not args.dry_run:
        ts = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = "%s.bak.%s" % (args.db, ts)
        shutil.copy2(args.db, destino)
        print("backup: %s" % destino)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        p_antes = contar(conn, "PONTO_FISCALIZACAO",
                         "WHERE municipio_id IS NOT NULL")
        res = backfill(conn, aplicar=not args.dry_run)
        p_depois = contar(conn, "PONTO_FISCALIZACAO",
                          "WHERE municipio_id IS NOT NULL")
        via_uf = None
        if not args.dry_run:
            via_uf = resolver_via_uf(conn)
        n_mun = contar(conn, "MUNICIPIO")
        n_via_uf = contar(conn, "VIA_UF")
        n_vias_uf = conn.execute(
            "SELECT COUNT(DISTINCT via_id) FROM VIA_UF").fetchone()[0]
        n_via = contar(conn, "VIA")
    finally:
        conn.close()

    print("modo: %s" % ("dry-run (nada gravado)" if args.dry_run else "aplicado"))
    print("pontos sem municipio analisados: %d" % res["total"])
    print("  preenchidos: %d" % res["preenchidos"])
    print("  sem nome no payload: %d" % res["sem_dado"])
    print("  nome sem correspondencia oficial: %d" % res["sem_match"])
    print("PONTO_FISCALIZACAO com municipio: %d -> %d" % (p_antes, p_depois))
    print("MUNICIPIO: %d" % n_mun)
    print("VIA_UF: %d (%s)" % (n_via_uf,
          "novas %d" % via_uf if via_uf is not None else "nao alterado"))
    print("VIAs c/ UF (distintas): %d de %d" % (n_vias_uf, n_via))
    print("--- preenchidos por fonte ---")
    for f, n in sorted(res["por_fonte"].items(), key=lambda kv: -kv[1]):
        print("  %-66s %6d" % ((f or "?")[:66], n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
