# -*- coding: utf-8 -*-
"""Fonte CE - AMC Fortaleza, equipamentos de fiscalizacao eletronica.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://mapas.fortaleza.ce.gov.br/mapa/538/equipamentos-de-fiscalizacao-eletronica

A pagina publica quatro exportacoes do MESMO conjunto (camada
``MOBILIDADE_URBANA:vw_dados_abertos_equip_fisc_eletronica_2026``):
  - GeoJSON: .../api/download/geojson/538
  - KML:     .../api/download/kml/538
  - Shape:   .../api/download/shape/538
  - CSV:     .../api/download/csv/538
Basta trocar a extensao do link no HTML; a URL NAO e datada.

Fonte adicional oficial (portal de dados abertos, CKAN):
  https://dados.fortaleza.ce.gov.br/dataset/fiscalizacao-eletronica
  recurso GeoJSON "Fiscalizacao Eletronica".

Colunas reais (GeoJSON propriedades): id, sitio, status, finalidade,
endereco, viasentido, bairro, regional, dataativacao, datadesativacao,
faixas_via, faixas_fis, temcontagem, fonte, ano, src_codif.
Geometria: MultiPoint em WGS84 (EPSG:4326), ordem LONGITUDE,LATITUDE.

Semantica: ``finalidade`` hoje so traz "Fiscalizacao" — a fonte NAO declara
fixo/portatil/movel, entao ``tipo_radar`` fica "desconhecido" (nada inventado)
e o texto original e preservado em ``observacoes``. ``status`` vira a situacao
canonica ("Ativo" -> ativo). Nenhuma posicao e inferida de endereco.
"""
import json
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_GEOJSON = "application/geo+json"
MIME_CSV = "text/csv"

PADRAO_MULTIPOINT = re.compile(
    r"(?:MULTI)?POINT\s*\(\s*\(?\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def _lon_lat_geometria(geom):
    """GeoJSON: coordinates[0] = [lon, lat]. Devolve (lon, lat)."""
    if not isinstance(geom, dict):
        return None, None
    tipo = geom.get("type")
    coords = geom.get("coordinates")
    if tipo == "Point":
        par = coords
    elif tipo in ("MultiPoint", "LineString"):
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


def _data_compacta(v):
    """'20221116' / 20221116.0 -> '2022-11-16'; outro -> None (nao inventa)."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:\.0+)?$", s)
    if not m:
        return None
    ano, mes, dia = m.group(1), m.group(2), m.group(3)
    if not (1 <= int(mes) <= 12 and 1 <= int(dia) <= 31):
        return None
    return "%s-%s-%s" % (ano, mes, dia)


class ColetorAMCCE(ColetorBase):

    FONTE = {
        "nome": "AMC Fortaleza - Equipamentos de fiscalizacao eletronica",
        "organizacao": ("Autarquia Municipal de Transito e Cidadania (AMC) - "
                        "Fortaleza"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://mapas.fortaleza.ce.gov.br/",
        "documentacao_url": ("https://mapas.fortaleza.ce.gov.br/mapa/538/"
                             "equipamentos-de-fiscalizacao-eletronica"),
        "licenca": "dados abertos municipais",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Equipamentos de fiscalizacao eletronica (GeoJSON)",
        "url_recurso": "https://mapas.fortaleza.ce.gov.br/api/download/geojson/538",
        "formato_origem": "geojson",
        "periodicidade_segundos": 2592000,   # ~30 dias
        "status_integracao": "ok",
    }

    URL_PAGINA = ("https://mapas.fortaleza.ce.gov.br/mapa/538/"
                  "equipamentos-de-fiscalizacao-eletronica")
    API_GEOJSON = "https://mapas.fortaleza.ce.gov.br/api/download/geojson/538"
    API_CSV = "https://mapas.fortaleza.ce.gov.br/api/download/csv/538"

    # -- descoberta --------------------------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Mapa formato -> URL dos endpoints /api/download/<fmt>/538."""
        achados = {}
        for url, fmt in re.findall(
                r'(https?://[^"\']+/api/download/(geojson|csv|kml|shape)/538)',
                html, re.I):
            achados.setdefault(fmt.lower(), url)
        return achados

    @classmethod
    def resolver_url(cls):
        """URL do GeoJSON descoberta na pagina; fallback = endpoint estavel."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            achados = cls.descobrir_recursos(html)
            if achados.get("geojson"):
                return achados["geojson"]
            if achados.get("csv"):
                return achados["csv"]
        except Exception:                                  # noqa: BLE001
            pass
        return cls.API_GEOJSON

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
        amostra = conteudo[:64].lstrip()
        if amostra[:1] in (b"{", b"[") or ext in (".geojson", ".json"):
            registros = self._parse_geojson(conteudo)
            return conteudo, ext or ".geojson", MIME_GEOJSON, registros
        # CSV (exportacao alternativa do mesmo endpoint)
        from coletor.fontes import planilha as pl
        registros = self._parse_csv(pl.ler_csv(conteudo))
        return conteudo, ext or ".csv", MIME_CSV, registros

    @staticmethod
    def _parse_geojson(conteudo):
        if isinstance(conteudo, (bytes, bytearray)):
            conteudo = conteudo.decode("utf-8-sig")
        dados = json.loads(conteudo)
        feats = dados.get("features") if isinstance(dados, dict) else dados
        registros = []
        for f in (feats or []):
            if not isinstance(f, dict):
                continue
            props = dict(f.get("properties") or {})
            lon, lat = _lon_lat_geometria(f.get("geometry") or f)
            if lon is not None and lat is not None:
                props["LONGITUDE"] = lon
                props["LATITUDE"] = lat
            registros.append(props)
        return registros

    @staticmethod
    def _parse_csv(linhas):
        registros = []
        for row in linhas:
            lon = lat = None
            geom = nz.pick(row, "the_geom", "geometry")
            if geom:
                m = PADRAO_MULTIPOINT.search(str(geom))
                if m:
                    lon, lat = nz.to_float(m.group(1)), nz.to_float(m.group(2))
            row = dict(row)
            if lon is not None and lat is not None:
                row["LONGITUDE"] = lon
                row["LATITUDE"] = lat
            registros.append(row)
        return registros

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "sitio", "Sitio", "id", "ID", "fid")

    def normalizar(self, idx, raw):
        lat = nz.to_float(nz.pick(raw, "LATITUDE", "latitude", "Latitude"))
        lon = nz.to_float(nz.pick(raw, "LONGITUDE", "longitude", "Longitude"))
        if lat is None or lon is None:
            return None
        finalidade = nz.pick(raw, "finalidade", "Finalidade")
        status = nz.pick(raw, "status", "Status")
        endereco = nz.pick(raw, "endereco", "Endereco", "Endereço")
        bairro = nz.pick(raw, "bairro", "Bairro")
        regional = nz.pick(raw, "regional", "Regional")
        viasentido = nz.pick(raw, "viasentido", "ViaSentido")
        faixa_via = nz.pick(raw, "faixas_via", "faixasVias")
        faixa_fis = nz.pick(raw, "faixas_fis", "faixasFisicas")
        tem_cont = nz.pick(raw, "temcontagem", "temContagem")
        ativacao = _data_compacta(nz.pick(raw, "dataativacao", "dataAtivacao"))
        desativacao = _data_compacta(nz.pick(raw, "datadesativacao",
                                             "dataDesativacao"))
        fonte = nz.pick(raw, "fonte", "Fonte")
        observacoes = "; ".join(x for x in (
            ("Finalidade: %s" % finalidade) if finalidade else None,
            ("Endereco: %s" % endereco) if endereco else None,
            ("Bairro: %s" % bairro) if bairro else None,
            ("Regional: %s" % regional) if regional else None,
            ("Faixas via: %s" % faixa_via) if faixa_via not in (None, "")
            else None,
            ("Faixas fisicas: %s" % faixa_fis) if faixa_fis not in (None, "")
            else None,
            ("Tem contagem: %s" % tem_cont) if tem_cont else None,
            ("Ativacao: %s" % ativacao) if ativacao else None,
            ("Desativacao: %s" % desativacao) if desativacao else None,
            ("Fonte: %s" % fonte) if fonte else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "cadastro_local",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao AMC Fortaleza (GeoJSON)",
            "uf": "CE",
            "municipio_nome": "Fortaleza",
            "municipio_ibge": "2304400",
            "via_codigo": viasentido or endereco,
            "via_tipo": "municipal",
            "km": None,
            "tipo_pista": None,
            "situacao": nz.normalizar_situacao(status),
            "situacao_original": status,
            # a fonte NAO declara fixo/portatil: nada e inventado.
            "tipo_radar": nz.normalizar_tipo_radar(finalidade),
            "numero_serie": None,
            "fabricante": None,
            "modelo": None,
            "sentido": None,
            "sentido_original": None,
            "observacoes": observacoes,
        }
