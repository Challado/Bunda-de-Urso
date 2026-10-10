# -*- coding: utf-8 -*-
"""Fonte BA - SEINFRA-BA, radares fixos e estaticos (geoarquivo oficial).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://www.ba.gov.br/infraestrutura/12046/mapas

A pagina publica, para os "Radares Fixos de Controle de Velocidade de
Responsabilidade da SEINFRA", tres representacoes do MESMO cadastro:
  - "Arquivo KML":  /infraestrutura/sites/site-seinfra/files/2026-09/
                    Mapa-Radar_15-09-2026.rar   (HTTPS)  -> dentro ha o KML
                    ``Mapa-Radar_15-09-2026.kml``
  - "Tabela":       /infraestrutura/sites/site-seinfra/files/2026-09/
                    Lista-Radar_15-09-2026.pdf  (HTTPS)
  - "Pagina WEB":   http://sit.infraestrutura.ba.gov.br/maparadar/ (HTTP puro)

E, para os "Radares Estaticos de Responsabilidade da SEINFRA":
  - "Arquivo KML":  http://sit.infraestrutura.ba.gov.br/docs/download/mapas/
                    radar-estatico-4CIA.zip     (HTTP puro)
                    -> dentro ha ``radar-estatico-2024.kml``

LIMITES REAIS (nao escondidos):
  1. O "Arquivo KML" dos FIXOS e um RAR (v5). A biblioteca padrao do Python
     NAO descompacta RAR; por isso o KML contido nele nao e legivel aqui.
  2. O "Arquivo KML" dos ESTATICOS (e o mapa web / GeoJSON do maparadar) so
     existe em HTTP (host 200.187.13.26 sem 443). O downloader do coletor
     (``coletor.http``) exige HTTPS, entao esse recurso nao pode ser baixado.
  3. Unico recurso HTTPS legivel com a stdlib para o cadastro de FIXOS: o PDF
     "Lista-Radar" (tabela). Por isso ele e a origem padrao da coleta, sem
     nunca chumbar a URL datada como fonte unica (a URL e descoberta na
     pagina e o fallback datado serve so de rede de seguranca).

O conector le com a stdlib: KML (``xml.etree.ElementTree``), GeoJSON
(``json``), ZIP (``zipfile`` -> KML/GeoJSON interno) e PDF-texto
(``planilha.ler_pdf_texto``). KML/GeoJSON usam ordem LONGITUDE,LATITUDE.

Semantica: as duas secoes sao de radar INSTALADO; o rotulo original da fonte
("Radares Fixos" / "Radares Estaticos" / TIPO=RADAR) fica preservado em
``observacoes``. Nada e inventado: campo ausente vira NULL.
"""
import io
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_KML = "application/vnd.google-earth.kml+xml"
MIME_GEOJSON = "application/geo+json"
MIME_PDF = "application/pdf"
MIME_ZIP = "application/zip"
MIME_TXT = "text/plain"

# A extracao de PDF concatena as colunas com espacos. Para nao deixar uma
# linha "escorregar" sobre a seguinte (ex.: serie com espaco interno
# "FSCII 7363"), primeiro cortamos o texto em blocos que comecam em
# "ID ANO RADAR" e depois parseamos cada bloco com ancoras de inicio e fim.
INICIO_LINHA = re.compile(r"(?<!\d)(?P<ID>\d{1,4})\s+(?P<ANO>\d{4})\s+RADAR\b")
PADRAO_LINHA = re.compile(
    r"^\s*(?P<ID>\d{1,4})\s+(?P<ANO>\d{4})\s+(?P<TIPO>[A-ZÀ-Ý]+)\s+"
    r"(?P<MEIO>.+?)\s+"
    r"(?P<VELOCIDADE>\d+\s*km)\s+"
    r"(?P<MUNICIPIO>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]*?)\s+"
    r"(?P<RODOVIA>BA\s?\d{1,4})\s+"
    r"(?P<KM>\d+\+\d+m)\s+"
    r"(?P<LATITUDE>-?\d+,\d+)\s+"
    r"(?P<LONGITUDE>-?\d+,\d+)\b",
    re.S)
PADRAO_MEIO = re.compile(
    r"(?P<MARCA>.+?)\s+(?P<MODELO>\S+)\s+"
    r"(?P<COD_ORGAO>[A-Z]{2,6}\d{4}\s*/\s*[A-Z]{2,6}\d{4})\s+"
    r"(?P<SERIE>.+?)\s+(?P<INMETRO>\d{7,9})\b", re.S)


def _local(tag):
    return tag.rsplit("}", 1)[-1] if tag else tag


def _coordenadas_kml(texto):
    """'lon,lat[,alt]' -> (lon, lat) em float. KML usa LON,LAT."""
    if not texto:
        return None, None
    partes = str(texto).strip().split(",")
    if len(partes) < 2:
        return None, None
    lon = nz.to_float(partes[0])
    lat = nz.to_float(partes[1])
    if lat is None or lon is None:
        return None, None
    return lon, lat


def _lon_lat_geometria(geom):
    """GeoJSON: coordinates[0] = [lon, lat]. Devolve (lon, lat)."""
    if not isinstance(geom, dict):
        return None, None
    coords = geom.get("coordinates")
    if geom.get("type") == "Feature":
        return _lon_lat_geometria(geom.get("geometry"))
    if geom.get("type") in ("Point",):
        par = coords
    elif geom.get("type") in ("MultiPoint", "LineString"):
        par = coords[0] if coords else None
    else:
        par = coords[0] if coords and isinstance(coords[0], (list, tuple)) \
            else coords
    if not isinstance(par, (list, tuple)) or len(par) < 2:
        return None, None
    lon = nz.to_float(par[0])
    lat = nz.to_float(par[1])
    if lon is None or lat is None:
        return None, None
    return lon, lat


def _via_ba(rodovia):
    """'BA131' -> 'BA-131' (mesmo formato canonico de via dos outros DER)."""
    r = (rodovia or "").strip().upper()
    if not r:
        return None
    m = re.match(r"^([A-Z]{2})\s*-?\s*(\d+)$", r)
    if m:
        return "%s-%s" % (m.group(1), m.group(2))
    return r


def _km_ba(v):
    """'9+500m' -> 9.5 ; '381.000000' -> 381.0 ; vazio -> None."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    m = re.match(r"^(\d+)\s*\+\s*(\d+)\s*m?$", s, re.I)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 1000.0
    return nz.to_float(s)


class ColetorSEINFRABA(ColetorBase):

    FONTE = {
        "nome": "SEINFRA-BA - Radares fixos e estaticos",
        "organizacao": "Secretaria de Infraestrutura da Bahia (SEINFRA-BA)",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.ba.gov.br/infraestrutura/",
        "documentacao_url": "https://www.ba.gov.br/infraestrutura/12046/mapas",
        "licenca": "documento oficial publicado",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Radares fixos (KML/PDF) e estaticos (KML ZIP)",
        "url_recurso": "https://www.ba.gov.br/infraestrutura/12046/mapas",
        "formato_origem": "kml|geojson|pdf",
        "periodicidade_segundos": 2592000,   # ~30 dias
        # KML dos fixos vem em RAR (stdlib nao le) e KML dos estaticos so em
        # HTTP (coletor exige HTTPS): so o PDF dos fixos e coletavel hoje.
        "status_integracao": "parcial",
    }

    URL_PAGINA = "https://www.ba.gov.br/infraestrutura/12046/mapas"
    # Rede de seguranca (URL datada): a fonte real e DESCOBERTA na pagina.
    URL_FALLBACK = ("https://www.ba.gov.br/infraestrutura/sites/site-seinfra/"
                    "files/2026-09/Lista-Radar_15-09-2026.pdf")

    # -- descoberta de recursos -------------------------------------------
    @classmethod
    def _classificar(cls, href, rotulo):
        h = href.lower()
        r = rotulo.lower()
        if h.endswith(".rar") and ("mapa-radar" in h or "kml" in r):
            return "fixos_kml"
        if h.endswith(".zip") and ("estatico" in h or "kml" in r):
            return "estaticos_kml"
        if h.endswith(".pdf") and ("lista-radar" in h or "tabela" in r or
                                   "pdf" in r):
            return "fixos_pdf"
        if h.endswith((".kml", ".geojson", ".json")):
            return "kml_direto"
        return None

    @classmethod
    def descobrir_recursos(cls, html):
        """Mapeia hrefs da pagina -> {fixos_kml, estaticos_kml, fixos_pdf,...}.

        Offline-testavel: recebe o HTML ja decodificado.
        """
        achados = {}
        for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html,
                             re.I | re.S):
            href, rotulo = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
            tipo = cls._classificar(href, rotulo)
            if tipo and tipo not in achados:
                achados[tipo] = urllib.parse.urljoin(cls.URL_PAGINA, href)
        return achados

    @classmethod
    def resolver_urls(cls, pagina=None):
        """Descobre os links atuais na pagina oficial (KML/PDF/ZIP)."""
        html = http.baixar(pagina or cls.URL_PAGINA)[0].decode("utf-8",
                                                               "replace")
        return cls.descobrir_recursos(html)

    @classmethod
    def resolver_url(cls):
        """Origem padrao da coleta: o PDF "Lista-Radar" (HTTPS, legivel).

        O KML dos fixos so existe dentro de RAR (stdlib nao descompacta) e o
        KML dos estaticos so em HTTP; o PDF e a unica origem HTTPS legivel.
        """
        try:
            urls = cls.resolver_urls()
            if urls.get("fixos_pdf"):
                return urls["fixos_pdf"]
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        local = bool(origem) and os.path.exists(origem)
        if local:
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            url = origem or self.resolver_url()
            conteudo, _headers, _url_final = http.baixar(url)
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        return self._decodificar(conteudo, ext)

    def _decodificar(self, conteudo, ext=""):
        """Detecta o formato pelo conteudo (mais confiavel que a extensao)."""
        cabeca = conteudo[:8]
        if cabeca[:4] == b"Rar!":
            raise http.ErroFonte(
                "Arquivo RAR (v5) nao suportado pela biblioteca padrao "
                "(KML dos radares fixos da SEINFRA-BA)")
        if conteudo[:2] == b"PK":
            return self._do_zip(conteudo, ext)
        if conteudo[:4] == b"%PDF":
            texto = pl.ler_pdf_texto(conteudo)
            return conteudo, ".pdf", MIME_PDF, self._parse_lista_pdf(texto)
        amostra = conteudo[:64].lstrip()
        if amostra[:1] in (b"{", b"[") or ext in (".geojson", ".json"):
            return (conteudo, ext or ".geojson", MIME_GEOJSON,
                    self._parse_geojson(conteudo))
        if amostra[:1] == b"<" or ext in (".kml", ".xml"):
            return (conteudo, ext or ".kml", MIME_KML,
                    self._parse_kml(conteudo))
        # texto ja extraido (fixture do PDF)
        texto = conteudo.decode("utf-8", "replace")
        return conteudo, ext or ".txt", MIME_TXT, self._parse_lista_pdf(texto)

    def _do_zip(self, conteudo, ext=""):
        z = zipfile.ZipFile(io.BytesIO(conteudo))
        alvo = None
        for nome in z.namelist():
            if nome.lower().endswith((".kml", ".geojson", ".json")):
                alvo = nome
                break
        if alvo is None:
            raise http.ErroFonte("ZIP sem KML/GeoJSON interno")
        interno = z.read(alvo)
        _c, _e, _m, registros = self._decodificar(
            interno, os.path.splitext(alvo)[1].lower())
        # preserva o artefato ORIGINAL (o ZIP) e devolve os registros do KML
        return conteudo, (ext or ".zip"), MIME_ZIP, registros

    # -- leitores ----------------------------------------------------------
    @classmethod
    def _parse_kml(cls, conteudo):
        """Lista de dicts; cada Placemark vira um dict (SimpleData + coords)."""
        if isinstance(conteudo, (bytes, bytearray)):
            conteudo = conteudo.decode("utf-8-sig", "replace")
        raiz = ET.fromstring(conteudo)
        registros = []
        for el in raiz.iter():
            if _local(el.tag) != "Placemark":
                continue
            registros.append(cls._placemark_dict(el))
        return registros

    @staticmethod
    def _placemark_dict(pm):
        d = {}
        for el in pm.iter():
            ln = _local(el.tag)
            if ln == "SimpleData":
                nome = el.get("name")
                if nome and nome not in d:
                    d[nome] = (el.text or "").strip()
            elif ln == "Data":
                nome = el.get("name")
                if not nome or nome in d:
                    continue
                valor = None
                for ch in el:
                    if _local(ch.tag) == "value":
                        valor = (ch.text or "").strip()
                d[nome] = valor
            elif ln == "coordinates":
                if "_coordinates" not in d:
                    d["_coordinates"] = (el.text or "").strip()
            elif ln == "name":
                if "_name" not in d and el.text:
                    d["_name"] = el.text.strip()
            elif ln == "description":
                if "_description" not in d and el.text:
                    d["_description"] = el.text.strip()
        return d

    @classmethod
    def _parse_geojson(cls, conteudo):
        if isinstance(conteudo, (bytes, bytearray)):
            conteudo = conteudo.decode("utf-8-sig")
        dados = json.loads(conteudo)
        if isinstance(dados, dict) and dados.get("type") == "FeatureCollection":
            feats = dados.get("features") or []
        elif isinstance(dados, dict) and dados.get("type") == "Feature":
            feats = [dados]
        elif isinstance(dados, list):
            feats = dados
        else:
            feats = [v for v in (dados or {}).values()
                     if isinstance(v, dict)]
        registros = []
        for f in feats:
            if not isinstance(f, dict):
                continue
            props = dict(f.get("properties") or {})
            lon, lat = _lon_lat_geometria(f.get("geometry") or f)
            if lon is not None and lat is not None:
                props.setdefault("LONGITUDE", lon)
                props.setdefault("LATITUDE", lat)
            registros.append(props)
        return registros

    @classmethod
    def _parse_lista_pdf(cls, texto):
        """Corta o texto em blocos por 'ID ANO RADAR' e parseia cada bloco."""
        if not texto:
            return []
        cortes = [m.start() for m in INICIO_LINHA.finditer(texto)]
        cortes.append(len(texto))
        registros = []
        for i in range(len(cortes) - 1):
            bloco = texto[cortes[i]:cortes[i + 1]]
            m = PADRAO_LINHA.match(bloco)
            if not m:
                continue
            d = m.groupdict()
            m2 = PADRAO_MEIO.match(d.pop("MEIO") or "")
            if m2:
                d.update(m2.groupdict())
            registros.append(d)
        return registros

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "COD_ORGAO", "COD. ORGAO", "COD__ORGAO",
                       "COD. ÓRGÃO", "Radar", "Radar ",
                       "Nº SERIE", "SERIE", "Nº_SERIE", "ID")

    @staticmethod
    def _lat_lon(raw):
        lat = nz.to_float(nz.pick(raw, "LATITUDE", "Latitude", "latitude"))
        lon = nz.to_float(nz.pick(raw, "LONGITUDE", "Longitude", "longitude"))
        if lat is None or lon is None:
            k_lon, k_lat = _coordenadas_kml(nz.pick(raw, "_coordinates"))
            lat = lat if lat is not None else k_lat
            lon = lon if lon is not None else k_lon
        return lat, lon

    def normalizar(self, idx, raw):
        lat, lon = self._lat_lon(raw)
        if lat is None or lon is None:
            return None
        estatico = bool(nz.pick(raw, "UOE", "Uoe"))
        secao = "Radares Estaticos" if estatico else "Radares Fixos"
        tipo_fonte = nz.pick(raw, "TIPO", "Tipo", "tipo")
        # A pagina rotula DUAS secoes de radar INSTALADO (fixos e estaticos).
        # O dominio TIPO_RADAR so tem fixo/portatil/movel/desconhecido, logo
        # "estatico" -> "fixo" e o rotulo original fica em observacoes.
        if tipo_fonte and "port" in str(tipo_fonte).lower():
            tipo_radar = "portatil"
        else:
            tipo_radar = "fixo"
        observacoes = "; ".join(x for x in (
            ("Tipo na fonte: %s" % tipo_fonte) if tipo_fonte else None,
            ("Secao na fonte: %s" % secao) if estatico else None,
            ("ANO: %s" % raw.get("ANO")) if raw.get("ANO") else None,
            ("INMETRO: %s" % nz.pick(raw, "INMETRO", "Nº_INMETR"))
            if nz.pick(raw, "INMETRO", "Nº_INMETR") else None,
            ("UOE: %s" % raw.get("UOE")) if raw.get("UOE") else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao SEINFRA-BA",
            "uf": "BA",
            "municipio_nome": nz.pick(raw, "MUNICIPIO", "Municipio",
                                      "Município", "municipio"),
            "via_codigo": _via_ba(nz.pick(raw, "RODOVIA", "Rodovia")),
            "via_tipo": "estadual",
            "km": _km_ba(nz.pick(raw, "KM", "Km", "km")),
            "tipo_pista": None,
            "situacao": None,
            "tipo_radar": tipo_radar,
            "numero_serie": nz.pick(raw, "Nº SERIE", "SERIE", "Nº_SERIE",
                                    "Nº SERIE "),
            "fabricante": nz.pick(raw, "MARCA", "Marca"),
            "modelo": nz.pick(raw, "MODELO", "Modelo"),
            "velocidade_geral": nz.to_velocidade(
                nz.pick(raw, "VELOCIDADE", "Velocidade")),
            "sentido": None,
            "sentido_original": None,
            "observacoes": observacoes,
        }
