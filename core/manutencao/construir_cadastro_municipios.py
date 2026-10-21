#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constroi o CADASTRO DE REFERENCIA de municipios do IBGE (versionado).

Gera ``config/municipios_ibge.json`` — lista OFICIAL de municipios (codigo
IBGE de 7 digitos, nome, uf_sigla e o centroide da malha), para o importador
consultar como referencia independente.  Fontes:

  - lista oficial: API de localidades do IBGE (``coletor.http.baixar``);
  - centroide: calculado (media ponderada por area) sobre a malha municipal
    OFICIAL — nunca um valor "de IA".  Municipio sem malha fica sem centroide.

O arquivo e deterministicamente ordenado por ``codigo_ibge``.  Alem de gravar,
o script CRUZA o cadastro com a tabela ``MUNICIPIO`` do banco (se existir) e com
os ``codarea`` da malha, e imprime as divergencias (nada e corrigido aqui).

Uso:
  python3 tools/construir_cadastro_municipios.py [--db CAMINHO] [--saida JSON]
      [--url URL] [--sem-centroide]
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone


from coletor import http                          # noqa: E402
from core import config                           # noqa: E402
from core import geo_municipio as geo             # noqa: E402
from core.manutencao.carregar_municipios_ibge import (      # noqa: E402
    corpo_json, extrair_municipios, URL_PADRAO)
from core.contexto_api import operacao_local
from core import db as dbmod
from core import caminhos  # caminhos so pela porta unica

SAIDA_PADRAO = os.path.join(config.ROOT, "config", "municipios_ibge.json")
DB_PADRAO = caminhos.banco()


# ---------------------------------------------------------------------------
# Centroide da malha (media ponderada por area; stdlib puro)
# ---------------------------------------------------------------------------
def _centroide_anel(anel):
    """(cx, cy, area_absoluta) do anel pelo teorema de Green, ou None."""
    a = cx = cy = 0.0
    n = len(anel)
    for i in range(n - 1):
        x0, y0 = anel[i]
        x1, y1 = anel[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-15:
        return None
    return (cx / (6.0 * a), cy / (6.0 * a), abs(a))


def _bbox_centro(parte):
    xs = [p[0] for p in parte[0]]
    ys = [p[1] for p in parte[0]]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def centroide_municipio(mun):
    """Centroide (lon, lat) da malha; cai no centro da bbox se area ~0."""
    soma_a = 0.0
    soma_x = 0.0
    soma_y = 0.0
    maior_area = -1.0
    maior_parte = None
    for parte in mun.partes:
        c = _centroide_anel(parte[0])
        if c is None:
            continue
        cx, cy, area = c
        soma_a += area
        soma_x += cx * area
        soma_y += cy * area
        if area > maior_area:
            maior_area = area
            maior_parte = parte
    if soma_a > 0:
        return (soma_x / soma_a, soma_y / soma_a)
    if maior_parte is not None:
        return _bbox_centro(maior_parte)
    return None


# ---------------------------------------------------------------------------
# Construcao
# ---------------------------------------------------------------------------
def construir(municipios, malha=None):
    """Lista de dicts de municipio (ordenada por codigo), com centroide se houver."""
    out = []
    for cod, uf, nome in municipios:
        item = {"codigo_ibge": cod, "nome": nome, "uf_sigla": uf}
        if malha is not None:
            mun = malha.por_cod.get(cod)
            if mun is not None:
                cen = centroide_municipio(mun)
                if cen is not None:
                    item["centroide_lon"] = round(cen[0], 6)
                    item["centroide_lat"] = round(cen[1], 6)
        out.append(item)
    out.sort(key=lambda m: m["codigo_ibge"])
    return out


def _cruzar_db(caminho_db, cadastro):
    if not caminho_db or not os.path.exists(caminho_db):
        return None
    try:
        conn = dbmod.connect("file:%s?mode=ro" % caminho_db, uri=True)
        conn.row_factory = sqlite3.Row
        db = {r["codigo_ibge"]: (r["uf_sigla"], r["nome"])
              for r in conn.execute(
                  "SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO")}
        conn.close()
    except sqlite3.Error:
        return None
    api = {m["codigo_ibge"]: (m["uf_sigla"], m["nome"]) for m in cadastro}
    so_db = sorted(set(db) - set(api))
    so_api = sorted(set(api) - set(db))
    return {"db": len(db), "api": len(api), "so_db": so_db, "so_api": so_api}


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Cadastro de referencia de municipios do IBGE.")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help="JSON de saida")
    ap.add_argument("--url", default=URL_PADRAO, help="endpoint de municipios")
    ap.add_argument("--db", default=DB_PADRAO, help="banco p/ cruzar (opcional)")
    ap.add_argument("--sem-centroide", action="store_true",
                    help="nao consulta a malha (so codigo/nome/uf)")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args(argv)

    try:
        corpo, _h, url_final = http.baixar(args.url, timeout=args.timeout)
    except http.ErroFonte as exc:
        print("ERRO no download da lista do IBGE: %s" % exc, file=sys.stderr)
        return 2
    municipios = extrair_municipios(corpo_json(corpo))
    if not municipios:
        print("ERRO: nenhum municipio extraido de %s" % url_final,
              file=sys.stderr)
        return 3

    malha = None
    if not args.sem_centroide:
        try:
            malha = geo.carregar_malha()
            print("malha: %d municipios" % len(malha))
        except Exception as exc:                  # noqa: BLE001
            print("AVISO: sem malha (%s); cadastro fica so com nome/uf" % exc,
                  file=sys.stderr)

    cadastro = construir(municipios, malha)
    doc = {
        "fonte": {
            "lista": url_final,
            "malha": geo.URL_TEMPLATE_PADRAO if malha is not None else None,
            "centroide": ("media ponderada por area sobre a malha municipal "
                          "oficial do IBGE (None quando nao ha malha)"
                          if malha is not None else None),
        },
        "gerado_em_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "total": len(cadastro),
        "municipios": cadastro,
    }
    os.makedirs(os.path.dirname(args.saida), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")

    com_centro = sum(1 for m in cadastro if "centroide_lat" in m)
    print("lista IBGE: %d municipios (de %s)" % (len(cadastro), url_final))
    print("com centroide: %d" % com_centro)
    print("arquivo: %s (%.2f MB)"
          % (args.saida, os.path.getsize(args.saida) / 1048576.0))
    if malha is not None:
        sem_malha = sorted(set(m["codigo_ibge"] for m in cadastro)
                           - set(malha.por_cod))
        if sem_malha:
            print("sem malha municipal (%d): %s"
                  % (len(sem_malha), ", ".join(sem_malha)))
    cruz = _cruzar_db(args.db, cadastro)
    if cruz:
        print("cruzamento com MUNICIPIO do banco: db=%d api=%d"
              % (cruz["db"], cruz["api"]))
        if cruz["so_db"]:
            print("  so no banco: %s" % ", ".join(cruz["so_db"]))
        if cruz["so_api"]:
            print("  so na API: %s" % ", ".join(cruz["so_api"]))
        if not cruz["so_db"] and not cruz["so_api"]:
            print("  conjuntos identicos (codigo a codigo)")
    return 0
