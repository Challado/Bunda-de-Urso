#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria GEOGRAFICA independente do casamento de municipio por NOME.

Cruza o municipio ATRIBUIDO ao ponto (``PONTO_FISCALIZACAO.municipio_id``,
preenchido por casamento de nome do payload) contra o municipio REAL da
coordenada, obtido por PONTO-EM-POLIGONO sobre a malha municipal OFICIAL do
IBGE (API v3 de malhas, GeoJSON — WGS84, RFC 7946).

Somente biblioteca padrao (sem pip). NADA e escrito no banco de producao: o
SQLite e aberto em modo somente-leitura (URI ``?mode=ro``) e o unico arquivo
gravado e o CSV de auditoria.

Fonte da malha (publica, WGS84):
  https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}
      ?formato=application/vnd.geo+json&qualidade=intermediaria
      &intrarregiao=municipio
O ``properties.codarea`` de cada feicao e o codigo IBGE do municipio (7 digitos).
O download usa ``coletor.http.baixar`` (HTTPS publico, sem urllib solto) e vai
para um cache em ``dados/raw``; a URL-base e parametrizavel (``--url-template``),
nunca chumbada como unica opcao. Se a malha vier em outro CRS seria reprojetada,
mas a API geo+json do IBGE ja entrega WGS84 (lon/lat) — confirmado no cabecalho
do carregador.

Regra de BORDA (deterministica): ponto exatamente sobre a linha de um anel
(exterior OU buraco) conta como DENTRO do municipio.

Saida CSV (``;``): ponto_id;lat;lon;municipio_atual_cod;municipio_geo_cod;
municipio_geo_nome;uf_geo;concorda
  concorda = "S" (bate) | "N" (diverge) | "?" (ponto sem poligono na malha)
             | "" (ponto sem municipio atual — a preencher)

Uso:
  python3 tools/auditar_geografia_municipios.py [--db CAMINHO] [--saida CSV]
      [--forcar] [--url-template TEMPLATE] [--timeout S]
"""
import argparse
import csv
import os
import sqlite3
import sys


from coletor import http                        # noqa: E402
from core import config                          # noqa: E402
from core import geo_municipio as geo            # noqa: E402
from core.contexto_api import operacao_local
from core import db as dbmod
from core import caminhos  # caminhos so pela porta unica

# A geometria e o resolvedor vivem em ``core.geo_municipio`` (reutilizavel
# pelo importador).  Mantemos os nomes no namespace deste modulo para
# compatibilidade com os testes existentes.
ponto_em_anel = geo.ponto_em_anel
ponto_na_borda = geo.ponto_na_borda
parte_contem = geo.parte_contem
ponto_em_poligono = geo.ponto_em_poligono
extrair_partes = geo.extrair_partes
_bbox_partes = geo._bbox_partes
MunicipioMalha = geo.MunicipioMalha
Malha = geo.Malha
_cache_arquivo = geo._cache_arquivo
_corpo_texto = geo._corpo_texto
carregar_uf = geo.carregar_uf
carregar_malhas = geo.carregar_malhas

DB_PADRAO = caminhos.banco()
CSV_PADRAO = os.path.join(config.ROOT, "dados", "calibracao",
                          "auditoria_geografica.csv")

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO")

URL_TEMPLATE_PADRAO = ("https://servicodados.ibge.gov.br/api/v3/malhas/"
                       "estados/{uf}?formato=application/vnd.geo+json"
                       "&qualidade=intermediaria&intrarregiao=municipio")

# Os 3 fills do casamento por nome com UF divergente da fonte (pai).
CASOS_UF_DIVERGENTE = (
    ("5300108", "Brasília", "DF", "GO"),
    ("2304400", "Fortaleza", "CE", "PI"),
    ("4318507", "São José do Norte", "RS", "RJ"),
)


# ---------------------------------------------------------------------------
# A geometria (ponto-em-poligono) e o carregador das malhas agora vivem em
# ``core.geo_municipio`` e sao reexportados no topo deste modulo.
# ---------------------------------------------------------------------------
# Banco (somente leitura)
# ---------------------------------------------------------------------------
def conectar_leitura(path):
    """Abre o SQLite em modo somente-leitura; recusa conexao de escrita."""
    return dbmod.connect_readonly(path)


def carregar_municipios(conn):
    """{codigo_ibge: (uf_sigla, nome)} a partir de MUNICIPIO."""
    return {str(r["codigo_ibge"]).strip(): (r["uf_sigla"], r["nome"])
            for r in conn.execute(
                "SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO")}


SQL_PONTOS = """
SELECT p.id            AS ponto_id,
       p.municipio_id  AS municipio_id,
       g.latitude      AS latitude,
       g.longitude     AS longitude
FROM PONTO_FISCALIZACAO p
JOIN POSICAO_GEOGRAFICA g ON g.id = p.posicao_id
ORDER BY p.id
"""


def auditar(conn, malha):
    """Gera as linhas da auditoria (dict por ponto com coordenada)."""
    muns = carregar_municipios(conn)
    linhas = []
    for r in conn.execute(SQL_PONTOS):
        lat = r["latitude"]
        lon = r["longitude"]
        atual = r["municipio_id"]
        atual = str(atual).strip() if atual is not None else None
        geo = malha.localizar(lon, lat)
        geo_uf, geo_nome = muns.get(geo, (None, None)) if geo else (None, None)
        if atual and geo:
            concorda = "S" if atual == geo else "N"
        elif atual and not geo:
            concorda = "?"
        else:
            concorda = ""
        linhas.append({
            "ponto_id": r["ponto_id"],
            "lat": lat,
            "lon": lon,
            "municipio_atual_cod": atual or "",
            "municipio_geo_cod": geo or "",
            "municipio_geo_nome": geo_nome or "",
            "uf_geo": geo_uf or "",
            "concorda": concorda,
        })
    return linhas, muns


# ---------------------------------------------------------------------------
# Saida
# ---------------------------------------------------------------------------
CABECALHO = ("ponto_id", "lat", "lon", "municipio_atual_cod",
             "municipio_geo_cod", "municipio_geo_nome", "uf_geo", "concorda")


def escrever_csv(caminho, linhas):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CABECALHO)
        for r in linhas:
            w.writerow([r[c] for c in CABECALHO])
    return caminho


def _descreve(cod, muns):
    if not cod:
        return "-"
    uf, nome = muns.get(cod, (None, None))
    if nome:
        return "%s/%s (%s)" % (nome, uf, cod)
    return "cod=%s" % cod


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Auditoria geografica (nome x malha IBGE) dos pontos.")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite (producao)")
    ap.add_argument("--saida", default=CSV_PADRAO, help="CSV de saida")
    ap.add_argument("--forcar", action="store_true",
                    help="ignora o cache e rebaixa as malhas")
    ap.add_argument("--url-template", default=URL_TEMPLATE_PADRAO,
                    help="template da URL da malha (default: API v3 do IBGE)")
    ap.add_argument("--timeout", type=float, default=60.0,
                    help="timeout por UF em segundos")
    ap.add_argument("--uf", action="append", default=None,
                    help="limita a UFs (repetivel); default: as 27")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    ufs = tuple(args.uf) if args.uf else UFS
    print("carregando malhas do IBGE (%d UFs)..." % len(ufs))
    malha, origem, erros = carregar_malhas(
        ufs, config.RAW_DIR, args.url_template, forcar=args.forcar,
        timeout=args.timeout)
    novos = sum(1 for v in origem.values() if v == "cache")
    print("malha: %d municipios; %d UFs do cache, %d baixadas"
          % (len(malha), novos, len(origem) - novos - len(erros)))
    for uf, motivo in erros:
        print("  AVISO UF %s: %s" % (uf, motivo), file=sys.stderr)
    if len(malha) == 0:
        print("ERRO: nenhuma malha municipal carregada", file=sys.stderr)
        return 3

    conn = conectar_leitura(args.db)
    try:
        linhas, muns = auditar(conn, malha)
    finally:
        conn.close()

    caminho = escrever_csv(args.saida, linhas)

    total = len(linhas)
    com_atual = [r for r in linhas if r["municipio_atual_cod"]]
    concordam = [r for r in com_atual if r["concorda"] == "S"]
    discordam = [r for r in com_atual if r["concorda"] == "N"]
    sem_geo = [r for r in com_atual if r["concorda"] == "?"]
    sem_atual = [r for r in linhas if not r["municipio_atual_cod"]]

    print("")
    print("=== AUDITORIA GEOGRAFICA (nome x malha IBGE) ===")
    print("pontos auditados (com coordenada): %d" % total)
    print("  com municipio atual:   %d" % len(com_atual))
    print("  sem municipio atual:   %d (a preencher)" % len(sem_atual))
    base = len(concordam) + len(discordam)
    if base:
        print("CONCORDANCIA (nome == geografia): %d/%d = %.2f%%"
              % (len(concordam), base, 100.0 * len(concordam) / base))
    print("  discordantes:          %d" % len(discordam))
    print("  fora da malha carregada: %d" % len(sem_geo))
    print("CSV: %s" % caminho)

    if discordam:
        print("")
        print("--- DISCORDANTES (top 60) ---")
        for r in discordam[:60]:
            print("  ponto %-7s %s -> GEO %s"
                  % (r["ponto_id"],
                     _descreve(r["municipio_atual_cod"], muns),
                     _descreve(r["municipio_geo_cod"], muns)))
        if len(discordam) > 60:
            print("  ... (+%d no CSV)" % (len(discordam) - 60))

    print("")
    print("--- 3 fills com UF divergente (nome) x GEOGRAFIA ---")
    for cod, nome, uf_certa, uf_fonte in CASOS_UF_DIVERGENTE:
        grupo = [r for r in linhas if r["municipio_atual_cod"] == cod]
        confirmados = sum(1 for r in grupo if r["concorda"] == "S")
        divergentes = [r for r in grupo if r["concorda"] == "N"]
        sem = sum(1 for r in grupo if r["concorda"] == "?")
        veredito = ("CONFIRMA" if divergentes == [] and confirmados > 0
                    else "NAO CONFIRMA" if divergentes else "SEM DADOS")
        print("  %s/%s (fonte %s) cod=%s: %d pontos | na geografia %d, "
              "fora %d, sem poligono %d -> %s"
              % (nome, uf_certa, uf_fonte, cod, len(grupo), confirmados,
                 len(divergentes), sem, veredito))
        for r in divergentes[:5]:
            print("      ponto %s -> GEO %s"
                  % (r["ponto_id"], _descreve(r["municipio_geo_cod"], muns)))

    print("")
    print("--- 70 pontos SEM municipio (geografia atribui) ---")
    for r in sem_atual:
        print("  ponto %-7s (%.5f, %.5f) -> %s"
              % (r["ponto_id"], r["lat"], r["lon"],
                 _descreve(r["municipio_geo_cod"], muns)))
    return 0
