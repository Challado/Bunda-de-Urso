# -*- coding: utf-8 -*-
"""Fonte F18 - Cariacica (ES), mapa de radares + documentos.

Pagina de entrada (catalogo):
    https://cariacica.es.gov.br/pagina/ler/861/mapa-radares

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  https://cariacica.es.gov.br/pagina/ler/861/mapa-radares  ->  HTTP 200.
  A pagina embute um mapa do Google My Maps:
      <a href="https://www.google.com/maps/d/u/0/embed?mid=1mhWiOBdxJ...&...">
      Consulte no mapa</a>
  e lista ESTUDOS TECNICOS em PDF (et-*.pdf) + "Planilha - Faixas
  monitoradas" (faixas-monitoradas.pdf).

  O mapa do My Maps tem exportacao KML publica padrao:
      https://www.google.com/maps/d/kml?mid=<MID>&forcekml=1
  que devolve KML (HTTP 200, text/xml) com a pasta "Radares" e 13 Placemarks
  pontuais; cada <description> traz os atributos do equipamento
  (Codigo, Equipament, Modelo, Marca, tipo, km, metro, Bairro, Via, Class,
  tipo_pista, limite, data_aferi, Empresa, num_inmetr, Qtdd_faixa,
  Qtdd_Radar). Estes sao os radares de fiscalizacao eletronica de velocidade
  do municipio -> PONTO_FISCALIZACAO (tipo fixo).

  Os PDFs (estudos tecnicos / faixas monitoradas) NAO sao legiveis de forma
  estruturada com a biblioteca padrao (o `planilha.ler_pdf_texto` devolve
  vazio/ilegivel nestas versoes); ficam apenas relacionados como documentos,
  nunca convertidos em pontos inventados.

O MID do mapa e DESCOBERTO na pagina oficial (nunca chumbado). Aceita arquivo
LOCAL (KML de fixture) para testes offline.
"""
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_KML = "application/vnd.google-earth.kml+xml"
_BASE_DOCS = "https://cariacica.es.gov.br"


def _local(tag):
    return tag.split("}")[-1]


def _limpa_prefixo(v):
    """Remove prefixos numericos tipo "1: " de valores do My Maps."""
    if v is None:
        return None
    s = re.sub(r"^\s*\d+\s*:\s*", "", str(v)).strip()
    return s or None


class ColetorCariacica(ColetorBase):

    FONTE = {
        "nome": "Cariacica - Mapa de radares de fiscalizacao eletronica",
        "organizacao": "Prefeitura Municipal de Cariacica",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://cariacica.es.gov.br/",
        "documentacao_url": "https://cariacica.es.gov.br/pagina/ler/861/mapa-radares",
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "mapa de radares (Google My Maps exportado em KML)",
        "url_recurso": "https://cariacica.es.gov.br/pagina/ler/861/mapa-radares",
        "formato_origem": "html|kml",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        "status_integracao": "ok",
    }

    PAGINA = RECURSO["url_recurso"]
    URL_KML = "https://www.google.com/maps/d/kml?mid=%s&forcekml=1"
    PASTA_DOCS = "/uploads/files/servicos/mapa-de-radares/"

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (o KML vem por descoberta do MID)."""
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @staticmethod
    def descobrir_mid(html):
        """Extrai o MID do mapa My Maps embutido na pagina."""
        m = re.search(r"/maps/d/(?:u/\d+/)?embed\?[^\"']*?mid=([A-Za-z0-9_-]+)",
                      html or "")
        if m:
            return m.group(1)
        m = re.search(r"mid=([A-Za-z0-9_-]{15,})", html or "")
        return m.group(1) if m else None

    @classmethod
    def descobrir_documentos(cls, html):
        """Links dos PDFs de estudos tecnicos / faixas publicados na pagina."""
        out = []
        vistos = set()
        for m in re.finditer(r'href="([^"]+)"[^>]*>(.*?)</a>', html or "",
                             re.S | re.I):
            href = m.group(1)
            if ".pdf" not in href.lower() or cls.PASTA_DOCS not in href:
                continue
            url = urllib.parse.urljoin(_BASE_DOCS, href)
            if url in vistos:
                continue
            vistos.add(url)
            texto = " ".join(re.sub(r"<[^>]+>", "", m.group(2)).split())
            out.append({"url": url, "titulo": texto or None})
        return out

    @classmethod
    def resolver_kml(cls):
        """Segue a pagina oficial, descobre o MID e devolve a URL do KML."""
        try:
            html = http.baixar(cls.PAGINA)[0].decode("utf-8", "replace")
        except Exception:                                  # noqa: BLE001
            return None
        mid = cls.descobrir_mid(html)
        return cls.URL_KML % mid if mid else None

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(str(ref)):
            with open(ref, "rb") as f:
                return f.read()
        return http.baixar(ref)[0]

    def carregar(self, origem):
        """origem: caminho local (KML) OU None/URL da pagina oficial.

        O recurso de dados e o KML descoberto na pagina oficial; por isso uma
        ORIGEM remota sempre dispara a descoberta (nunca tratamos a URL da
        pagina como se fosse o KML). Retorna 4-tupla.
        """
        if origem and os.path.exists(str(origem)):
            conteudo = self._ler(origem)
        else:
            url = self.resolver_kml()
            conteudo = self._ler(url) if url else b""
        return (conteudo, ".kml", MIME_KML, self._parse_kml(conteudo))

    # -- parsing KML ------------------------------------------------------
    @classmethod
    def _parse_kml(cls, conteudo):
        if not conteudo:
            return []
        if b"<!DOCTYPE" in conteudo[:4096]:
            # KML oficial nao usa DTD; recusa expansao de entidade (XXE).
            raise http.ErroFonte("KML com DOCTYPE nao permitido")
        try:
            root = ET.fromstring(conteudo)
        except ET.ParseError as exc:
            raise http.ErroFonte("KML invalido: %s" % exc)
        registros = []
        for item in root.iter():
            if _local(item.tag) != "Placemark":
                continue
            nome = desc = coords = None
            for el in item.iter():
                if _local(el.tag) == "name" and nome is None:
                    nome = el.text
                elif _local(el.tag) == "description" and desc is None:
                    desc = el.text
                elif _local(el.tag) == "coordinates" and coords is None:
                    coords = el.text
            lat, lon = _parse_coords(coords)
            atributos = _parse_descricao(desc)
            registros.append({
                "nome": (nome or "").strip() or None,
                "lat": lat,
                "lon": lon,
                "atributos": atributos,
            })
        return registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        at = raw.get("atributos") or {}
        return (nz.pick(at, "Codigo", "Equipament", "id")
                or raw.get("nome"))

    def normalizar(self, idx, raw):
        at = raw.get("atributos") or {}
        lat, lon = raw.get("lat"), raw.get("lon")
        # ponto de mapa sem coordenada nao vira registro posicionado
        if lat is None or lon is None:
            return None
        via = raw.get("nome") or nz.pick(at, "nome")
        fabricante = _limpa_prefixo(nz.pick(at, "Marca"))
        modelo = _limpa_prefixo(nz.pick(at, "Modelo"))
        velocidade = nz.to_velocidade(nz.pick(at, "limite"))
        obs = "; ".join(x for x in (
            ("Id na fonte: %s" % at.get("id")) if at.get("id") else None,
            ("Tipo de via: %s" % at.get("tipo")) if at.get("tipo") else None,
            ("Classificacao: %s" % at.get("Class")) if at.get("Class") else None,
            ("Bairro: %s" % at.get("Bairro")) if at.get("Bairro") else None,
            ("Quantidade de faixas: %s" % at.get("Qtdd_faixa"))
            if at.get("Qtdd_faixa") else None,
            ("Quantidade de radares: %s" % at.get("Qtdd_Radar"))
            if at.get("Qtdd_Radar") else None,
            ("Tipo de pista: %s" % at.get("tipo_pista"))
            if at.get("tipo_pista") else None,
            ("Data de afericao: %s" % at.get("data_aferi"))
            if at.get("data_aferi") else None,
            ("Empresa: %s" % at.get("Empresa")) if at.get("Empresa") else None,
            ("Registro INMETRO: %s" % at.get("num_inmetr"))
            if at.get("num_inmetr") else None,
            ("Codigo de equipamento: %s" % at.get("Equipament"))
            if at.get("Equipament") else None,
        ) if x)
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao Prefeitura de Cariacica (mapa de "
                                "radares - Google My Maps/KML)"),
            "uf": "ES",
            "municipio_nome": "Cariacica",
            "via_codigo": via,
            "via_tipo": "municipal",
            "km": nz.to_float(nz.pick(at, "km")),
            "tipo_pista": at.get("tipo_pista"),
            "situacao": None,
            "tipo_radar": "fixo",
            "fabricante": fabricante,
            "modelo": modelo,
            "numero_serie": None,
            "velocidade_geral": velocidade,
            "sentido": None,
            "sentido_original": None,
            "observacoes": obs or None,
        }


def _parse_coords(texto):
    """KML usa 'lon,lat[,alt]' -> devolve (lat, lon)."""
    if not texto:
        return None, None
    partes = texto.strip().split(",")
    if len(partes) < 2:
        return None, None
    try:
        lon = float(partes[0])
        lat = float(partes[1])
    except (TypeError, ValueError):
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    return lat, lon


def _parse_descricao(desc):
    """'chave: valor<br>chave: valor' -> dict."""
    if not desc:
        return {}
    texto = re.sub(r"<br\s*/?>", "\n", desc)
    texto = re.sub(r"<[^>]+>", " ", texto)
    out = {}
    for linha in texto.splitlines():
        if ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        chave = chave.strip()
        valor = valor.strip()
        if chave and valor:
            out[chave] = valor
    return out
