# -*- coding: utf-8 -*-
"""Fonte F13 - Belo Horizonte, fiscalizacao eletronica.

Portal CKAN: https://dados.pbh.gov.br/pt_BR/dataset/fiscalizacao-eletronica
Dataset id: 7ce7b0b8-0a5b-4736-9b63-8bfd5da6cfe4
O portal publica um CSV por mes, nomeado AAAAMMDD_fiscalizacao_eletronica.csv;
NAO fixamos o arquivo datado: escolhemos o de data mais recente pela API CKAN.

A coluna GEOMETRIA traz um ponto projetado (o proprio dataset orienta usar
EPSG:31983 = SIRGAS 2000 / UTM 23S). Convertemos esse ponto para graus
decimais com matematica da biblioteca padrao (sem pyproj). Aceita LOCAL.
"""
import os
import re
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_CSV = "text/csv"
UTM_ZONA = 23          # EPSG:31983 -> UTM 23S
UTM_SUL = True


class ColetorPBH(ColetorBase):

    FONTE = {
        "nome": "Belo Horizonte - Fiscalizacao eletronica",
        "organizacao": "Prefeitura de Belo Horizonte",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://prefeitura.pbh.gov.br/",
        "documentacao_url": ("https://dados.pbh.gov.br/pt_BR/dataset/"
                             "fiscalizacao-eletronica"),
        "licenca": "dados abertos municipais",
        "periodicidade_declarada": "mensal",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Fiscalizacao eletronica (CSV mensal)",
        "url_recurso": ("https://dados.pbh.gov.br/pt_BR/dataset/"
                        "fiscalizacao-eletronica"),
        "formato_origem": "csv",
        "periodicidade_segundos": 2592000,   # ~30 dias
        "status_integracao": "ok",
    }

    CKAN_BASE = "https://ckan.pbh.gov.br"
    CKAN_DATASET = "7ce7b0b8-0a5b-4736-9b63-8bfd5da6cfe4"
    URL_FALLBACK = ("https://ckan.pbh.gov.br/dataset/"
                    "7ce7b0b8-0a5b-4736-9b63-8bfd5da6cfe4/resource/"
                    "fec93c45-620a-4eb4-8ddd-23b91ecb8323/download/"
                    "20260901_fiscalizacao_eletronica.csv")

    @staticmethod
    def _chave_data(nome, url):
        s = "%s %s" % (nome or "", url or "")
        m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (0, 0, 0)

    @classmethod
    def resolver_url(cls):
        """URL do CSV mensal mais recente (API CKAN); fallback estatico."""
        try:
            from coletor.fontes import ckan
            recursos = ckan.package_show(cls.CKAN_BASE, cls.CKAN_DATASET)
        except Exception:                                  # noqa: BLE001
            return cls.URL_FALLBACK
        cand = [(cls._chave_data(r.get("name"), r.get("url")), r.get("url"))
                for r in recursos
                if (r.get("url") or "").lower().endswith(".csv")
                and "fiscalizacao_eletronica" in (r.get("name") or "").lower()]
        if not cand:
            return cls.URL_FALLBACK
        cand.sort(key=lambda par: par[0], reverse=True)
        return cand[0][1]

    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            url = origem or self.resolver_url()
            req = urllib.request.Request(
                url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                    req, timeout=config.DEFAULT_TIMEOUT) as resp:
                conteudo = resp.read()
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        registros = pl.ler_csv(conteudo)
        return conteudo, (ext or ".csv"), MIME_CSV, registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "ID_FISCALIZACAO_ELETRONICA", "id")

    def normalizar(self, idx, raw):
        ponto = pl.parse_ponto_utm(
            nz.pick(raw, "GEOMETRIA", "geometria", "Coordenadas"))
        lat = lon = None
        metodo = "publicacao PBH"
        if ponto is not None:
            lat, lon = pl.utm_para_geografico(ponto[0], ponto[1],
                                              UTM_ZONA, UTM_SUL)
            metodo = "conversao EPSG:31983 (SIRGAS2000/UTM 23S) do campo GEOMETRIA"
        else:
            lat, lon = pl.parse_coordenadas(nz.pick(raw, "Coordenadas"))
        if lat is None or lon is None:
            return None
        tipo = nz.pick(raw, "DESC_TIPO_CONTROLADOR_TRANSITO")
        return {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": metodo,
            "uf": "MG",
            "municipio_nome": "Belo Horizonte",
            "municipio_ibge": "3106200",
            "via_codigo": nz.pick(raw, "DESC_LOC_CONTROLADOR_TRANSITO"),
            "via_tipo": "municipal",
            "tipo_radar": nz.normalizar_tipo_radar(tipo),
            "numero_serie": nz.pick(raw, "NUM_SERIE_ATUAL"),
            "velocidade_leves": nz.to_float(
                nz.pick(raw, "VELOCIDADE_REGULAMENTAR")),
            "sentido": nz.normalizar_sentido(
                nz.pick(raw, "SENTIDO", "SENTIDO_FISCALIZADO")),
            "sentido_original": nz.pick(raw, "SENTIDO", "SENTIDO_FISCALIZADO"),
            "observacoes": "; ".join(x for x in (
                ("Tipo de controlador: %s" % tipo) if tipo else None,
                ("Sentido fiscalizado: %s" % raw.get("SENTIDO_FISCALIZADO"))
                if raw.get("SENTIDO_FISCALIZADO") else None,
                ("Codigo secundaria: %s" % raw.get("COD_SECUNDARIA"))
                if raw.get("COD_SECUNDARIA") else None,
            ) if x) or None,
        }
