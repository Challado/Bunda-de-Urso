#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o CSV REAPLICAVEL de correcoes de municipio (config/).

Duas fontes de correcao, ambas por ``ponto_id -> codigo_ibge``:

  1. os pontos sem municipio mas COM coordenada, resolvidos por
     ponto-em-poligono na malha OFICIAL do IBGE (``core.geo_municipio``);
  2. os pontos dos casos de UF divergente CONFIRMADOS pela geografia
     (Brasilia/GO->DF, Fortaleza/PI->CE) — idempotentes, so documentam.

Pontos sem municipio e sem resolucao geografica (coordenada implausivel ou
fora das malhas — agua) NAO entram no CSV de correcoes: vao para
``config/municipios_ressalvas.csv`` como pendencia explicita (nada e
inventado).

Uso:
  python3 tools/gerar_correcoes_municipio.py [--db CAMINHO]
      [--saida config/correcoes_municipio.csv]
      [--ressalvas config/municipios_ressalvas.csv]
"""
import argparse
import csv
import os
import sqlite3
import sys


from core import config                          # noqa: E402
from core import correcoes_municipio as corr      # noqa: E402
from core import geo_municipio as geo             # noqa: E402
from core.contexto_api import operacao_local
from core import db as dbmod

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
SAIDA_PADRAO = corr.CAMINHO_PADRAO
RESSALVAS_PADRAO = os.path.join(config.ROOT, "config",
                                "municipios_ressalvas.csv")

# Casos de UF divergente do casamento por nome, CONFIRMADOS pela geografia.
# (codigo_ibge, nome, uf_certa, uf_da_fonte)
CASOS_UF_DIVERGENTE = (
    ("5300108", "Brasília", "DF", "GO"),
    ("2304400", "Fortaleza", "CE", "PI"),
    ("4318507", "São José do Norte", "RS", "RJ"),
)

SQL_SEM_MUNICIPIO = """
SELECT p.id AS ponto_id, g.latitude AS lat, g.longitude AS lon
FROM PONTO_FISCALIZACAO p
JOIN POSICAO_GEOGRAFICA g ON g.id = p.posicao_id
WHERE p.municipio_id IS NULL
ORDER BY p.id
"""

# Todos os pontos COM coordenada: usado para achar as ressalvas (coordenada
# implausivel ou ponto fora de qualquer municipio — agua/limite).
SQL_COM_COORDENADA = """
SELECT p.id AS ponto_id, p.municipio_id AS municipio_id,
       g.latitude AS lat, g.longitude AS lon
FROM PONTO_FISCALIZACAO p
JOIN POSICAO_GEOGRAFICA g ON g.id = p.posicao_id
ORDER BY p.id
"""


def _motivo_ressalva(lat, lon):
    lat = float(lat)
    lon = float(lon)
    if lon > 0:
        return "coordenada_implausivel_lon_positiva"
    if abs(lat - lon) < 1e-9:
        return "coordenada_implausivel_lat_igual_lon"
    return "fora_da_malha_ibge_agua_ou_limite"


def _classificar_ressalva(lat, lon):
    """Motivo da ressalva, ou None se a coordenada e plausivel.

    Coordenada plausivel = faixa valida, nao (0,0) e longitude negativa
    (todo o Brasil esta a oeste de Greenwich).
    """
    if not geo.coordenada_valida(lat, lon):
        return "coordenada_fora_de_faixa"
    if float(lon) > 0:
        return "coordenada_implausivel_lon_positiva"
    if abs(float(lat) - float(lon)) < 1e-9:
        return "coordenada_implausivel_lat_igual_lon"
    return None


def gerar(conn, malha=None, uf_divergentes=CASOS_UF_DIVERGENTE):
    """Devolve (correcoes, ressalvas).

    - correcoes: pontos sem municipio resolvidos pela malha (real fix) +
      pontos dos casos de UF divergente CONFIRMADOS pela geografia (auditados:
      tem coordenada e a malha confirma o municipio — idempotentes).
    - ressalvas: pontos com coordenada que a malha NAO consegue localizar
      (coordenada implausivel ou agua/limite). Nao viram correcao.
    """
    correcoes = []
    ressalvas = []
    codigos_uf = {cod for cod, _n, _u, _f in uf_divergentes}
    resolvidos = {}                      # ponto_id -> codigo (malha)
    for r in conn.execute(SQL_COM_COORDENADA):
        pid = str(r["ponto_id"])
        lat, lon = r["lat"], r["lon"]
        cod = geo.municipio_por_coordenada(lat, lon, malha=malha)
        resolvidos[pid] = cod
        if cod is None:
            ressalvas.append({
                "ponto_id": pid,
                "lat": lat, "lon": lon,
                "municipio_atual": r["municipio_id"] or "",
                "motivo": _classificar_ressalva(lat, lon)
                          or "fora_da_malha_ibge_agua_ou_limite"})

    # 1) pontos NULL que a malha resolve (real correcao)
    for r in conn.execute(SQL_SEM_MUNICIPIO):
        pid = str(r["ponto_id"])
        cod = resolvidos.get(pid) or geo.municipio_por_coordenada(
            r["lat"], r["lon"], malha=malha)
        if cod:
            correcoes.append({"ponto_id": pid, "codigo_ibge": cod,
                              "motivo": "malha_ibge"})

    # 2) UF divergente CONFIRMADO pela geografia (so os auditados c/ coordenada)
    for cod in sorted(codigos_uf):
        for r in conn.execute(
                "SELECT p.id AS id, p.municipio_id AS mun "
                "FROM PONTO_FISCALIZACAO p "
                "JOIN POSICAO_GEOGRAFICA g ON g.id = p.posicao_id "
                "WHERE p.municipio_id=? ORDER BY p.id", (cod,)):
            pid = str(r["id"])
            if resolvidos.get(pid) == cod:
                correcoes.append({"ponto_id": pid, "codigo_ibge": cod,
                                  "motivo": "uf_divergente_confirmada"})

    correcoes.sort(key=lambda c: int(c["ponto_id"]))
    ressalvas.sort(key=lambda c: int(c["ponto_id"]))
    return correcoes, ressalvas


def _abrir_leitura(path):
    conn = dbmod.connect("file:%s?mode=ro" % path, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("SELECT 1")
    return conn


def escrever_csv(caminho, linhas, colunas, comentario=None):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        if comentario:
            for ln in comentario.splitlines():
                f.write("# %s\n" % ln)
        w = csv.DictWriter(f, fieldnames=list(colunas), delimiter=";",
                           lineterminator="\n")
        w.writeheader()
        for ln in linhas:
            w.writerow({k: ln.get(k, "") for k in colunas})
    return caminho


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Gera as correcoes de municipio (reaplicaveis).")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help="CSV de correcoes")
    ap.add_argument("--ressalvas", default=RESSALVAS_PADRAO,
                    help="CSV de pendencias (nao resolviveis)")
    ap.add_argument("--sem-malha", action="store_true",
                    help="nao carrega a malha (so lista as ressalvas)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    malha = None if args.sem_malha else geo.carregar_malha()
    conn = _abrir_leitura(args.db)
    try:
        correcoes, ressalvas = gerar(conn, malha=malha)
    finally:
        conn.close()

    escrever_csv(args.saida, correcoes, corr.COLUNAS,
                 comentario="correcoes de municipio (ponto_id -> codigo_ibge); "
                            "reaplicavel e idempotente")
    escrever_csv(args.ressalvas, ressalvas,
                 ("ponto_id", "lat", "lon", "municipio_atual", "motivo"),
                 comentario="pontos com coordenada que a malha OFICIAL do IBGE "
                            "nao localiza (coordenada implausivel ou "
                            "agua/limite); nada e inventado")

    from collections import Counter
    print("correcoes: %d -> %s" % (len(correcoes), args.saida))
    print("  por motivo: %s"
          % dict(Counter(c["motivo"] for c in correcoes)))
    print("  por municipio: %s"
          % dict(Counter(c["codigo_ibge"] for c in correcoes)))
    print("ressalvas: %d -> %s" % (len(ressalvas), args.ressalvas))
    print("  por motivo: %s" % dict(Counter(r["motivo"] for r in ressalvas)))
    return 0
