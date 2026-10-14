#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carrega a lista OFICIAL de municipios do IBGE na tabela MUNICIPIO.

Baixa somente via ``coletor.http.baixar`` (HTTPS publico, sem urllib solto) e
popula ``MUNICIPIO (codigo_ibge, uf_sigla, nome)``. Idempotente: usa
``INSERT OR IGNORE`` e nunca altera o schema.

O endpoint padrao e a API publica de localidades do IBGE
(https://servicodados.ibge.gov.br/api/v1/localidades/municipios), mas a URL e
parametrizavel (``--url``) — nada fica chumbado como unica opcao. As UFs ja
vem do seed de dominios (``core.db.init_db``); a FK MUNICIPIO.uf_sigla -> UF
e satisfeita por ele.

Uso:
  python3 tools/carregar_municipios_ibge.py [--db CAMINHO] [--url URL]
"""
import argparse
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor import http                        # noqa: E402
from core import config                          # noqa: E402
from core import db as dbmod                     # noqa: E402

URL_PADRAO = ("https://servicodados.ibge.gov.br/api/v1/localidades/"
              "municipios?view=nivelado")


def corpo_json(corpo, headers=None):
    """Decodifica o corpo HTTP do IBGE (com ou sem gzip) em objetos Python."""
    if corpo[:2] == b"\x1f\x8b":
        corpo = gzip.decompress(corpo)
    return json.loads(corpo.decode("utf-8"))


def _uf_de(item):
    """Extrai a sigla da UF das duas formas do endpoint de localidades."""
    uf = item.get("UF-sigla")
    if uf:
        return str(uf).strip().upper()
    micro = item.get("microrregiao") or {}
    meso = micro.get("mesorregiao") or {}
    uf = (meso.get("UF") or {}).get("sigla")
    return str(uf).strip().upper() if uf else None


def extrair_municipios(itens):
    """Normaliza a lista do IBGE para (codigo_ibge, uf_sigla, nome)."""
    out = []
    vistos = set()
    for item in itens:
        cod = item.get("municipio-id") or item.get("id")
        nome = item.get("municipio-nome") or item.get("nome")
        uf = _uf_de(item)
        if cod is None or not nome or not uf:
            continue
        cod = str(cod).strip().zfill(7)
        if cod in vistos:
            continue
        vistos.add(cod)
        out.append((cod, uf, nome))
    return out


def carregar(conn, municipios):
    """INSERT OR IGNORE na MUNICIPIO; devolve quantos foram inseridos."""
    inseridos = 0
    for cod, uf, nome in municipios:
        cur = conn.execute(
            "INSERT OR IGNORE INTO MUNICIPIO (codigo_ibge, uf_sigla, nome) "
            "VALUES (?, ?, ?)", (cod, uf, nome))
        inseridos += cur.rowcount
    conn.commit()
    return inseridos


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Carrega a lista oficial de municipios do IBGE em MUNICIPIO.")
    ap.add_argument("--db", default=config.DB_PATH, help="banco SQLite")
    ap.add_argument("--url", default=URL_PADRAO,
                    help="URL do endpoint de municipios (default: IBGE)")
    args = ap.parse_args(argv)

    try:
        corpo, headers, url_final = http.baixar(args.url, timeout=60)
    except http.ErroFonte as exc:
        print("ERRO no download: %s" % exc, file=sys.stderr)
        return 2

    municipios = extrair_municipios(corpo_json(corpo, headers))
    if not municipios:
        print("ERRO: nenhum municipio extraido de %s" % url_final,
              file=sys.stderr)
        return 3

    conn = dbmod.connect(args.db)
    try:
        dbmod.init_db(conn)            # garante UFs (FK) e schema
        antes = dbmod.scalar(conn, "SELECT COUNT(*) FROM MUNICIPIO")
        inseridos = carregar(conn, municipios)
        depois = dbmod.scalar(conn, "SELECT COUNT(*) FROM MUNICIPIO")
    finally:
        conn.close()

    print("fonte: %s" % url_final)
    print("municipios no arquivo: %d" % len(municipios))
    print("MUNICIPIO antes: %d" % antes)
    print("inseridos agora: %d" % inseridos)
    print("MUNICIPIO depois: %d" % depois)
    return 0


if __name__ == "__main__":
    sys.exit(main())
