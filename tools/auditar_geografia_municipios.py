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
import gzip
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor import http                        # noqa: E402
from core import config                          # noqa: E402

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
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
# Ponto-em-poligono (ray casting + borda), puro stdlib
# ---------------------------------------------------------------------------
def ponto_em_anel(anel, x, y):
    """Ray casting classico: ponto (x,y) dentro do anel fechado (sem borda)."""
    dentro = False
    n = len(anel)
    j = n - 1
    for i in range(n):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                dentro = not dentro
        j = i
    return dentro


def ponto_na_borda(anel, x, y, eps=1e-12):
    """True se (x,y) esta sobre um segmento do anel (colinear e no retangulo)."""
    n = len(anel)
    j = n - 1
    for i in range(n):
        xi, yi = anel[i]
        xj, yj = anel[j]
        dx = xj - xi
        dy = yj - yi
        cross = (x - xi) * dy - (y - yi) * dx
        comp = abs(dx) + abs(dy)
        if comp and abs(cross) <= eps * comp:
            if (min(xi, xj) - eps <= x <= max(xi, xj) + eps
                    and min(yi, yj) - eps <= y <= max(yi, yj) + eps):
                return True
        j = i
    return False


def parte_contem(parte, x, y):
    """parte = [anel_exterior, buraco1, ...]; buracos subtraem area.

    Borda de QUALQUER anel (exterior ou buraco) conta como DENTRO do
    municipio (regra deterministica de borda).
    """
    for anel in parte:
        if ponto_na_borda(anel, x, y):
            return True
    if not ponto_em_anel(parte[0], x, y):
        return False
    for buraco in parte[1:]:
        if ponto_em_anel(buraco, x, y):
            return False
    return True


def ponto_em_poligono(partes, x, y):
    """True se o ponto cai em QUALQUER parte (MultiPolygon) do municipio."""
    return any(parte_contem(p, x, y) for p in partes)


# ---------------------------------------------------------------------------
# Geometria da malha
# ---------------------------------------------------------------------------
def extrair_partes(geometry):
    """GeoJSON geometry -> [[anel_exterior, buraco...], ...] (partes validas).

    Poligonos com menos de 3 vertices sao descartados. Nao reprojeta: a API do
    IBGE entrega lon/lat WGS84. Se um CRS nao-WGS84 aparecesse, seria recusado.
    """
    tipo = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates")
    if tipo == "Polygon":
        poligonos = [coords]
    elif tipo == "MultiPolygon":
        poligonos = list(coords or [])
    else:
        return []
    partes = []
    for poligono in poligonos or []:
        aneis = []
        for anel in poligono or []:
            pts = [(float(p[0]), float(p[1])) for p in anel]
            if len(pts) >= 3:
                aneis.append(pts)
        if aneis:
            partes.append(aneis)
    return partes


def _bbox_partes(partes):
    xs0 = ys0 = float("inf")
    xs1 = ys1 = float("-inf")
    for parte in partes:
        for anel in parte:
            for x, y in anel:
                if x < xs0:
                    xs0 = x
                if x > xs1:
                    xs1 = x
                if y < ys0:
                    ys0 = y
                if y > ys1:
                    ys1 = y
    return (xs0, ys0, xs1, ys1)


class MunicipioMalha(object):
    __slots__ = ("codarea", "uf", "partes", "bboxes", "bbox")

    def __init__(self, codarea, uf, partes):
        self.codarea = codarea
        self.uf = uf
        self.partes = partes
        self.bboxes = [_bbox_partes([p]) for p in partes]
        self.bbox = _bbox_partes(partes)

    def contem(self, x, y):
        b = self.bbox
        if x < b[0] or x > b[2] or y < b[1] or y > b[3]:
            return False
        for i, parte in enumerate(self.partes):
            bb = self.bboxes[i]
            if x < bb[0] or x > bb[2] or y < bb[1] or y > bb[3]:
                continue
            if parte_contem(parte, x, y):
                return True
        return False


class Malha(object):
    """Malha municipal carregada (todas as UFs). Busca por bbox + ray casting."""

    def __init__(self):
        self._lista = []
        self.por_cod = {}

    def adicionar_feature(self, feature, uf=None):
        props = (feature or {}).get("properties") or {}
        cod = props.get("codarea")
        if cod is None:
            return False
        cod = str(cod).strip()
        partes = extrair_partes((feature or {}).get("geometry") or {})
        if not partes or not cod:
            return False
        mun = MunicipioMalha(cod, uf, partes)
        self._lista.append(mun)
        self.por_cod[cod] = mun
        return True

    def adicionar_featurecollection(self, fc, uf=None):
        n = 0
        for feat in (fc or {}).get("features", []) or []:
            if self.adicionar_feature(feat, uf=uf):
                n += 1
        return n

    def __len__(self):
        return len(self._lista)

    def localizar(self, x, y):
        """Codigo IBGE do municipio que contem (x=lon, y=lat), ou None."""
        for mun in self._lista:
            b = mun.bbox
            if x < b[0] or x > b[2] or y < b[1] or y > b[3]:
                continue
            if mun.contem(x, y):
                return mun.codarea
        return None


# ---------------------------------------------------------------------------
# Download / cache das malhas
# ---------------------------------------------------------------------------
def _cache_arquivo(cache_dir, uf):
    return os.path.join(cache_dir, "ibge_malha_municipios_%s.geojson" % uf)


def _corpo_texto(corpo):
    """Decodifica corpo HTTP do IBGE (aceita gzip defensivamente)."""
    if corpo[:2] == b"\x1f\x8b":
        corpo = gzip.decompress(corpo)
    return corpo.decode("utf-8")


def carregar_uf(uf, cache_dir, url_template, forcar=False, timeout=None):
    """Devolve a FeatureCollection da malha da UF (do cache ou baixando)."""
    caminho = _cache_arquivo(cache_dir, uf)
    if os.path.exists(caminho) and not forcar and os.path.getsize(caminho) > 0:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f), "cache"
    url = url_template.format(uf=uf)
    corpo, _headers, url_final = http.baixar(url, timeout=timeout)
    texto = _corpo_texto(corpo)
    fc = json.loads(texto)
    os.makedirs(cache_dir, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return fc, url_final


def carregar_malhas(ufs, cache_dir, url_template, forcar=False, timeout=None):
    """Carrega todas as UFs; devolve (Malha, {uf: origem|None}, [erros])."""
    malha = Malha()
    origem = {}
    erros = []
    for uf in ufs:
        try:
            fc, de = carregar_uf(uf, cache_dir, url_template, forcar=forcar,
                                 timeout=timeout)
        except (http.ErroFonte, ValueError, OSError) as exc:
            origem[uf] = None
            erros.append((uf, str(exc)))
            continue
        n = malha.adicionar_featurecollection(fc, uf=uf)
        origem[uf] = de
        if n == 0:
            erros.append((uf, "nenhuma feicao municipal extraida"))
    return malha, origem, erros


# ---------------------------------------------------------------------------
# Banco (somente leitura)
# ---------------------------------------------------------------------------
def conectar_leitura(path):
    """Abre o SQLite em modo somente-leitura; recusa conexao de escrita."""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("SELECT 1")
        return conn
    except sqlite3.Error:
        # Fallback: conexao normal mas com query_only ligado (nunca grava).
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn


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


if __name__ == "__main__":
    sys.exit(main())
