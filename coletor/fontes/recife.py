# -*- coding: utf-8 -*-
"""Fonte F12 - Recife, equipamentos de monitoramento e fiscalizacao de
transito (CSV + dicionario JSON). Aceita arquivo local para testes.
"""
import csv
import io
import os
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


class ColetorRecife(ColetorBase):

    FONTE = {
        "nome": "Recife - Equipamentos de fiscalizacao de transito",
        "organizacao": "Prefeitura do Recife",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://dados.recife.pe.gov.br/",
        "documentacao_url": ("https://dados.recife.pe.gov.br/dataset/"
                             "equipamentos-de-monitoramento-e-fiscalizacao-de-transito"),
        "licenca": "dados abertos municipais",
        "periodicidade_declarada": "anual",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "equipamentos-de-monitoramento (CSV)",
        "url_recurso": ("https://dados.recife.pe.gov.br/dataset/"
                        "equipamentos-de-monitoramento-e-fiscalizacao-de-transito"),
        "formato_origem": "csv",
        "periodicidade_segundos": 31536000,   # ~365 dias
        "status_integracao": "ok",
    }

    # -- resolucao de URL -------------------------------------------------
    CKAN_BASE = "https://dados.recife.pe.gov.br"
    CKAN_DATASET = "9acffb30-ed06-4b16-84ff-710478f18760"
    URL_FALLBACK = ("https://dados.recife.pe.gov.br/dataset/"
                    "9acffb30-ed06-4b16-84ff-710478f18760/resource/"
                    "36c2b47b-f439-4895-8b65-3f3dda36a4a7/download/"
                    "lista-de-equipamentos-de-fiscalizacao-de-transito.csv")

    @classmethod
    def resolver_url(cls):
        """URL direta da lista de fiscalizacao (API CKAN); fallback fixo."""
        try:
            from coletor.fontes import ckan
            url = ckan.url_do_mais_novo(cls.CKAN_BASE, cls.CKAN_DATASET, "CSV",
                                        r"fiscalizacao-de-transito")
            if url:
                return url
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower() or ".csv"
        else:
            req = urllib.request.Request(
                origem or self.RECURSO["url_recurso"],
                headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=config.DEFAULT_TIMEOUT) as resp:
                conteudo = resp.read()
            ext = ".csv"
        registros = self._parse_csv(conteudo)
        return conteudo, ext, "text/csv", registros

    @staticmethod
    def _parse_csv(conteudo):
        texto = conteudo.decode("utf-8-sig")
        linhas = texto.splitlines()
        primeira = linhas[0] if linhas else ""
        delim = ";" if primeira.count(";") >= primeira.count(",") else ","
        return list(csv.DictReader(io.StringIO(texto), delimiter=delim))

    def identificador(self, raw):
        return nz.pick(raw, "identificacao_equipamento", "id", "Id", "ID",
                       "codigo", "Codigo")

    def normalizar(self, idx, raw):
        lat = nz.to_float(nz.pick(raw, "latitude", "Latitude", "lat"))
        lon = nz.to_float(nz.pick(raw, "longitude", "Longitude", "lon", "lng"))
        if lat is None or lon is None:
            return None
        logradouro = nz.pick(raw, "local_instalacao", "endereco", "Endereco",
                             "logradouro", "local", "Local")
        tipo_txt = nz.pick(raw, "tipo_equipamento", "tipo", "Tipo",
                           "equipamento", "Equipamento")
        d = {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao Prefeitura do Recife",
            "uf": "PE",
            "municipio_nome": "Recife",
            "municipio_ibge": "2611606",
            "via_codigo": logradouro,
            "via_tipo": "municipal",
            "tipo_pista": nz.pick(raw, "faixa", "Faixa", "pista"),
            "situacao": nz.normalizar_situacao(
                nz.pick(raw, "situacao", "Situacao", "status")),
            "tipo_radar": nz.normalizar_tipo_radar(tipo_txt),
            "numero_serie": nz.pick(raw, "numero_serie_fabricante",
                                    "numero_serie", "serie", "Serie"),
            "fabricante": nz.pick(raw, "fabricante", "Fabricante"),
            "modelo": nz.pick(raw, "modelo", "Modelo"),
            # Recife publica UMA velocidade fiscalizada (sem separar leve/pesado)
            "velocidade_geral": nz.to_velocidade(
                nz.pick(raw, "velocidade_fiscalizada", "velocidade",
                        "Velocidade", "velocidade_limite")),
            "sentido": nz.normalizar_sentido(
                nz.pick(raw, "sentido_fiscalizacao", "sentido", "Sentido")),
            "sentido_original": nz.pick(raw, "sentido_fiscalizacao", "sentido",
                                        "Sentido"),
            "observacoes": nz.pick(raw, "bairro", "Bairro"),
        }
        return d
