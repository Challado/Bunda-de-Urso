# -*- coding: utf-8 -*-
"""Fonte SE - DER-SE, localizacao de radares e lombadas fixas.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://der.se.gov.br/localizacao-de-radares-fixos/

A pagina ("Localizacao dos Radares e Lombadas Fixas") publica, em dois iframes,
duas planilhas do Google publicadas na web (docs.google.com/spreadsheets/d/e/
<pacote>/pubhtml?gid=<gid>):
  - title="radares" -> a lista a coletar (Localizacao dos Radares e Lombadas
    Fixas);
  - title="cameras" -> Cameras de Monitoramento (nao e radar de velocidade).

A URL publicada NAO e datada e e descoberta no HTML; a exportacao CSV do mesmo
documento e obtida trocando ``pubhtml`` por ``pub`` e acrescentando
``&output=csv``. Colunas reais:

  CODIGO EQUIPAMENTO | RODOVIA | MUNICIPIO | VELOCIDADE | Localizacao do Radares

A coluna "Localizacao do Radares" traz um link do Google Maps com a coordenada
embutida (``?query=<lat>,<lon>``); ela e extraida da URL -- nada e inventado.
Linhas sem coordenada ficam SEM posicao (preservadas), nao viram GPS artificial.

A pagina declarа que a secao e de "Radares e Lombadas Fixas", logo o tipo e
fixo. Aceita arquivo LOCAL (CSV de fixture) para testes offline.
"""
import csv
import io
import os
import re
import urllib.parse
from html import unescape

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_CSV = "text/csv"

PADRAO_IFRAME = re.compile(r"<iframe\b([^>]*)>", re.I)
PADRAO_COORD = re.compile(r"query=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
PADRAO_MUNICIPIO_COD = re.compile(r"^(?P<nome>.*?)\s*\(\d+\)\s*$")


class ColetorDERSE(ColetorBase):

    FONTE = {
        "nome": "DER-SE - Localizacao de radares e lombadas fixas",
        "organizacao": ("Departamento Estadual de Infraestrutura Rodoviaria "
                        "de Sergipe (DER-SE)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://der.se.gov.br/",
        "documentacao_url": "https://der.se.gov.br/localizacao-de-radares-fixos/",
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Radares e lombadas fixas (planilha publicada / CSV)",
        "url_recurso": "https://der.se.gov.br/localizacao-de-radares-fixos/",
        "formato_origem": "csv",
        "periodicidade_segundos": 2592000,     # ~30 dias
        "status_integracao": "ok",
    }

    URL_PAGINA = "https://der.se.gov.br/localizacao-de-radares-fixos/"
    PACOTE = ("2PACX-1vTsjvD1KDfkk7ZInL2TE0d3zM9j_7MOS34BoeRgiV23xKbSLjFy"
              "O2n9KWnqRuv_mYUnSYpJsbsQYS1F")
    GID_RADARES = "1987757175"
    # Rede de seguranca (formato CSV do mesmo documento publicado).
    URL_FALLBACK = ("https://docs.google.com/spreadsheets/d/e/%s/pub"
                    "?gid=%s&single=true&output=csv"
                    % (PACOTE, GID_RADARES))

    # -- descoberta --------------------------------------------------------
    @staticmethod
    def _csv_de_pubhtml(url):
        """.../pubhtml?gid=NNN&single=true -> .../pub?gid=NNN&...&output=csv."""
        if "pubhtml" not in url:
            return None
        base = url.split("?", 1)
        query = base[1] if len(base) > 1 else ""
        partes = [p for p in query.split("&") if p and not p.startswith("output=")]
        if not any(p.startswith("gid=") for p in partes):
            return None
        partes.append("output=csv")
        return "%s?%s" % (base[0].replace("pubhtml", "pub"), "&".join(partes))

    @classmethod
    def descobrir_recursos(cls, html):
        """Mapa {radares, cameras} -> CSV, a partir dos iframes da pagina."""
        achados = {}
        for m in PADRAO_IFRAME.finditer(html):
            attrs = m.group(1)
            src = re.search(r'src="([^"]+)"', attrs, re.I)
            title = re.search(r'title="([^"]*)"', attrs, re.I)
            if not src:
                continue
            url = unescape(src.group(1))
            if "docs.google.com/spreadsheets" not in url:
                continue
            csv_url = cls._csv_de_pubhtml(url)
            if not csv_url:
                continue
            rotulo = (title.group(1) if title else "").lower()
            if "camera" in rotulo or "monitora" in rotulo:
                achados.setdefault("cameras", csv_url)
            elif "radar" in rotulo or "lombada" in rotulo:
                achados.setdefault("radares", csv_url)
            else:
                achados.setdefault("outros", csv_url)
        return achados

    @classmethod
    def resolver_url(cls):
        """CSV da planilha de radares descoberta na pagina; fallback fixo."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            url = cls.descobrir_recursos(html).get("radares")
            if url:
                return url
        except Exception:                                   # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
        else:
            url = origem or self.resolver_url()
            if "der.se.gov.br" in url and "spreadsheets" not in url:
                url = self.resolver_url()
            conteudo, _headers, _final = http.baixar(url)
        return conteudo, ".csv", MIME_CSV, self._parse_csv(conteudo)

    @staticmethod
    def _parse_csv(conteudo):
        texto = conteudo.decode("utf-8-sig") if isinstance(conteudo, bytes) \
            else conteudo
        registros = []
        for row in csv.DictReader(io.StringIO(texto)):
            # normaliza cabecalhos que quebram linha (ex.: "CODIGO \nEQUIPAMENTO")
            registros.append({re.sub(r"\s+", " ", (k or "")).strip(): v
                              for k, v in row.items() if k is not None})
        return registros

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "CÓDIGO EQUIPAMENTO", "CODIGO EQUIPAMENTO",
                       "Código Equipamento")

    @staticmethod
    def _municipio(valor):
        v = (valor or "").strip()
        if not v:
            return None
        m = PADRAO_MUNICIPIO_COD.match(v)
        return (m.group("nome").strip() if m else v) or None

    @staticmethod
    def _coord(linha):
        """Coordenada embutida no link do Google Maps ('?query=lat,lon')."""
        m = PADRAO_COORD.search(linha or "")
        if not m:
            return None, None
        lat, lon = nz.to_float(m.group(1)), nz.to_float(m.group(2))
        if lat is None or lon is None or not (-90 <= lat <= 90
                                              and -180 <= lon <= 180):
            return None, None
        return lat, lon

    def normalizar(self, idx, raw):
        lat, lon = self._coord(nz.pick(raw, "Localização do Radares",
                                       "Localizacao do Radares"))
        via = (nz.pick(raw, "RODOVIA") or "").strip().upper() or None
        if via:
            via = re.sub(r"\s+", "-", via)
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao DER-SE (localizacao de radares e "
                                "lombadas fixas)"),
            "uf": "SE",
            "municipio_nome": self._municipio(nz.pick(raw, "MUNICÍPIO",
                                                      "MUNICIPIO", "Município")),
            "via_codigo": via,
            "via_tipo": "estadual" if via else None,
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            # a secao publicada e de "Radares e Lombadas Fixas"
            "tipo_radar": "fixo",
            "numero_serie": None,
            "fabricante": None,
            "modelo": None,
            "velocidade_geral": nz.to_velocidade(nz.pick(raw, "VELOCIDADE")),
            "sentido": None,
            "sentido_original": None,
            "observacoes": ("Publicado em 'Localizacao dos Radares e Lombadas "
                            "Fixas' (DER-SE)") if lat is None else None,
        }
