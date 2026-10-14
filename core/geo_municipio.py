# -*- coding: utf-8 -*-
"""Resolvedor GEOGRAFICO de municipio por ponto-em-poligono (stdlib puro).

Cruza uma coordenada (lat/lon WGS84) contra a malha municipal OFICIAL do IBGE
(API v3 de malhas, GeoJSON RFC 7946, lon/lat) e devolve o ``codigo_ibge`` do
municipio que contem o ponto.  E a base independente do casamento por NOME:
serve de FALLBACK no importador e de auditoria do que o nome ja resolveu.

Nada e inventado e nada depende de rede em tempo de requisicao da API:

  - a malha e carregada, nesta ordem de preferencia, de:
      1. ``RADAR_MALHA`` (variavel de ambiente, caminho explicito);
      2. a malha SIMPLIFICADA versionada em
         ``config/ibge_malha_municipios.geojson.gz`` (git);
      3. o cache local ``dados/raw/ibge_malha_municipios_<UF>.geojson``
         (gitignored);
      4. download ao vivo pela API oficial do IBGE via ``coletor.http.baixar``
         (grava no cache de ``dados/raw``); use ``atualizar_malha()`` para
         forcar.
  - coordenada fora de faixa (|lat|>90, |lon|>180) ou (0,0) nunca consulta a
    malha: devolve ``None`` (mesma regra do importador).

Regra de BORDA (deterministica): ponto exatamente sobre a linha de um anel
(exterior OU buraco) conta como DENTRO do municipio.  A API geo+json do IBGE
entrega WGS84 (lon/lat) — nao ha reprojecao.
"""
import gzip
import json
import os
import threading

from core import config

__all__ = (
    "UFS", "URL_TEMPLATE_PADRAO", "MALHA_VERSIONADA",
    "ponto_em_anel", "ponto_na_borda", "parte_contem", "ponto_em_poligono",
    "extrair_partes", "MunicipioMalha", "Malha",
    "carregar_uf", "carregar_malhas", "carregar_malha", "carregar_malha_geo",
    "atualizar_malha", "coordenada_valida", "municipio_por_coordenada",
)

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO")

URL_TEMPLATE_PADRAO = ("https://servicodados.ibge.gov.br/api/v3/malhas/"
                       "estados/{uf}?formato=application/vnd.geo+json"
                       "&qualidade=intermediaria&intrarregiao=municipio")

# Malha SIMPLIFICADA versionada no repositorio (ver tools/construir_malha.py).
MALHA_VERSIONADA = os.path.join(config.ROOT, "config",
                                "ibge_malha_municipios.geojson.gz")

# Precisao usada ao gravar a malha simplificada (graus; ~11 m em latitude).
CASAS_DECIMAIS = 4


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
            cod = (feature or {}).get("id")
        if cod is None:
            return False
        cod = str(cod).strip()
        partes = extrair_partes((feature or {}).get("geometry") or {})
        if not partes or not cod:
            return False
        mun = MunicipioMalha(cod, uf or props.get("uf"), partes)
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


def carregar_uf(uf, cache_dir, url_template=None, forcar=False, timeout=None):
    """Devolve a FeatureCollection da malha da UF (do cache ou baixando)."""
    if url_template is None:
        url_template = URL_TEMPLATE_PADRAO
    caminho = _cache_arquivo(cache_dir, uf)
    if os.path.exists(caminho) and not forcar and os.path.getsize(caminho) > 0:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f), "cache"
    from coletor import http                    # import tardio: evita ciclo
    url = url_template.format(uf=uf)
    corpo, _headers, url_final = http.baixar(url, timeout=timeout)
    texto = _corpo_texto(corpo)
    fc = json.loads(texto)
    os.makedirs(cache_dir, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return fc, url_final


def carregar_malhas(ufs, cache_dir, url_template=None, forcar=False,
                    timeout=None):
    """Carrega todas as UFs; devolve (Malha, {uf: origem|None}, [erros])."""
    from coletor import http                     # noqa: F401 (import tardio)
    malha = Malha()
    origem = {}
    erros = []
    for uf in ufs:
        try:
            fc, de = carregar_uf(uf, cache_dir, url_template, forcar=forcar,
                                 timeout=timeout)
        except Exception as exc:                 # noqa: BLE001
            origem[uf] = None
            erros.append((uf, str(exc)))
            continue
        n = malha.adicionar_featurecollection(fc, uf=uf)
        origem[uf] = de
        if n == 0:
            erros.append((uf, "nenhuma feicao municipal extraida"))
    return malha, origem, erros


def carregar_malha_geo(caminho):
    """Carrega uma malha de um arquivo .geojson ou .geojson.gz -> Malha."""
    abrir = gzip.open if str(caminho).endswith(".gz") else open
    with abrir(caminho, "rb") as f:
        fc = json.loads(f.read().decode("utf-8"))
    malha = Malha()
    malha.adicionar_featurecollection(fc)
    return malha


def carregar_malha(ufs=None, forcar=False, cache_dir=None, timeout=None,
                   url_template=None):
    """Carrega a malha municipal completa (WGS84).

    Precedencia: ``RADAR_MALHA`` > malha versionada (config/) > cache
    ``dados/raw`` > download ao vivo.  ``forcar=True`` ignora cache versionado
    e baixa da API para ``dados/raw`` (nao reescreve o arquivo versionado).
    """
    ufs = tuple(ufs) if ufs else UFS
    if cache_dir is None:
        cache_dir = config.RAW_DIR
    env = os.environ.get("RADAR_MALHA")
    if env and os.path.exists(env) and not forcar:
        return carregar_malha_geo(env)
    if (not forcar and not env and os.path.exists(MALHA_VERSIONADA)
            and tuple(ufs) == UFS):
        return carregar_malha_geo(MALHA_VERSIONADA)
    malha, _origem, erros = carregar_malhas(
        ufs, cache_dir, url_template, forcar=forcar, timeout=timeout)
    if len(malha) == 0 and erros:
        raise RuntimeError("nenhuma malha municipal carregada: %s"
                           % "; ".join("%s=%s" % e for e in erros))
    return malha


def atualizar_malha(ufs=None, timeout=None, url_template=None):
    """Forca o download da malha da API do IBGE para o cache dados/raw."""
    return carregar_malha(ufs=ufs, forcar=True, timeout=timeout,
                          url_template=url_template)


# ---------------------------------------------------------------------------
# Resolucao por coordenada
# ---------------------------------------------------------------------------
def coordenada_valida(lat, lon):
    """True se (lat, lon) e uma coordenada utilizavel (nunca 0,0)."""
    if lat is None or lon is None:
        return False
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return True


_MALHA_LOCK = threading.Lock()
_MALHA_SINGLETON = {"malha": None, "chave": None}


def _malha_padrao():
    """Malha compartilhada (carregada 1x por processo)."""
    with _MALHA_LOCK:
        if _MALHA_SINGLETON["malha"] is None:
            _MALHA_SINGLETON["malha"] = carregar_malha()
        return _MALHA_SINGLETON["malha"]


def reset_malha():
    """Descarta a malha em memoria (usado por testes e apos atualizar)."""
    with _MALHA_LOCK:
        _MALHA_SINGLETON["malha"] = None
        _MALHA_SINGLETON["chave"] = None


def municipio_por_coordenada(lat, lon, malha=None):
    """Codigo IBGE do municipio que contem (lat, lon); None se nao houver.

    Nao inventa: coordenada invalida, ponto em agua/fora das malhas ou falha
    de carga de malha devolvem ``None`` (o chamador decide o que fazer).
    """
    if not coordenada_valida(lat, lon):
        return None
    try:
        m = malha if malha is not None else _malha_padrao()
    except Exception:                            # noqa: BLE001
        return None
    if m is None or len(m) == 0:
        return None
    return m.localizar(float(lon), float(lat))


def municipio_uf_por_coordenada(lat, lon, malha=None):
    """(codigo_ibge, uf) do municipio que contem (lat, lon); (None, None)
    quando nada contem.

    Igual a :func:`municipio_por_coordenada`, mas tambem devolve a UF da
    malha. Nao inventa: coordenada invalida, ponto em agua/fora das malhas
    ou falha de carga devolvem ``(None, None)``.
    """
    if not coordenada_valida(lat, lon):
        return None, None
    try:
        m = malha if malha is not None else _malha_padrao()
    except Exception:                            # noqa: BLE001
        return None, None
    if m is None or len(m) == 0:
        return None, None
    codigo = m.localizar(float(lon), float(lat))
    if codigo is None:
        return None, None
    mun = m.por_cod.get(codigo)
    return codigo, (getattr(mun, "uf", None) if mun is not None else None)
