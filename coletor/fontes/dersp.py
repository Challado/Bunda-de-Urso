# -*- coding: utf-8 -*-
"""Fonte F08 - DER-SP, radares estaduais.

Portal CKAN: https://dadosabertos.sp.gov.br/dataset/radar
Recurso: planilha XLSX estatica (radares.xlsx) no site do DER-SP, cuja URL e
descoberta pelo dataset CKAN (sem chumbar o arquivo). Ha tambem um LINK para o
sistema de pesquisa (PesquisaRadar.aspx), que NAO e arquivo baixavel.
Aceita arquivo LOCAL (fixtures/testes) ou URL.
"""
import os
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_XLSX = ("application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet")


class ColetorDERSP(ColetorBase):

    FONTE = {
        "nome": "DER-SP - Radares estaduais",
        "organizacao": "Departamento de Estradas de Rodagem de Sao Paulo",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.der.sp.gov.br/",
        "documentacao_url": "https://dadosabertos.sp.gov.br/dataset/radar",
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Radares (XLSX) e sistema de pesquisa",
        "url_recurso": "https://dadosabertos.sp.gov.br/dataset/radar",
        "formato_origem": "xlsx",
        "periodicidade_segundos": 604800,   # semanal (verificacao)
        "status_integracao": "ok",
    }

    CKAN_BASE = "https://dadosabertos.sp.gov.br"
    CKAN_DATASET = "radar"
    URL_FALLBACK = ("https://dersp.der.sp.gov.br/WebSite/Arquivos/DadosAbertos/"
                    "AtivosRodoviarios/Radar/radares.xlsx")

    @classmethod
    def resolver_url(cls):
        """URL do XLSX publicado no dataset CKAN; fallback estatico."""
        try:
            from coletor.fontes import ckan
            recursos = ckan.package_show(cls.CKAN_BASE, cls.CKAN_DATASET)
        except Exception:                                  # noqa: BLE001
            return cls.URL_FALLBACK
        for r in recursos:
            url = r.get("url") or ""
            if url.lower().endswith(".xlsx"):
                return url
        return cls.URL_FALLBACK

    def _baixar(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=config.DEFAULT_TIMEOUT) as resp:
            return resp.read()

    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            url = origem or self.resolver_url()
            conteudo = self._baixar(url)
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        if conteudo[:2] == b"PK" or ext == ".xlsx":
            registros = pl.dicts_de_linhas(pl.ler_xlsx(conteudo))
            return conteudo, ".xlsx", MIME_XLSX, registros
        return conteudo, ".csv", "text/csv", pl.ler_csv(conteudo)

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "Código", "Codigo", "codigo")

    @staticmethod
    def _via(rodovia):
        r = (rodovia or "").strip()
        if not r:
            return None
        return r.upper().replace(" ", "-")

    @staticmethod
    def _marca_modelo(texto):
        if not texto:
            return None, None
        partes = str(texto).split("/", 1)
        fab = partes[0].strip() or None
        mod = partes[1].strip() if len(partes) > 1 else None
        return fab, mod

    def normalizar(self, idx, raw):
        lat, lon = pl.parse_coordenadas(
            nz.pick(raw, "Coordenadas", "coordenadas"))
        if lat is None or lon is None:
            return None
        fab, mod = self._marca_modelo(nz.pick(raw, "Marca/Modelo", "Marca / Modelo"))
        observacoes = "; ".join(x for x in (
            ("Tipo: %s" % raw.get("Tipo")) if raw.get("Tipo") else None,
            ("Tipo da Rodovia: %s" % raw.get("Tipo da Rodovia"))
            if raw.get("Tipo da Rodovia") else None,
            ("Faixas: %s" % raw.get("Faixas")) if raw.get("Faixas") else None,
            ("Operadora: %s" % raw.get("Operadora")) if raw.get("Operadora") else None,
            ("Inicio Operacao: %s"
             % pl.serial_excel_para_iso(raw.get("Início Operação")))
            if pl.serial_excel_para_iso(raw.get("Início Operação")) else None,
            ("Cancelamento: %s" % raw.get("Cancelamento"))
            if raw.get("Cancelamento") else None,
        ) if x)
        return {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao DER-SP",
            "uf": "SP",
            "municipio_nome": nz.pick(raw, "Município", "Municipio", "municipio"),
            "via_codigo": self._via(nz.pick(raw, "Rodovia", "rodovia")),
            "via_tipo": "estadual",
            "km": nz.to_float(nz.pick(raw, "Km", "km")),
            "tipo_pista": nz.pick(raw, "Tipo da Rodovia"),
            "tipo_radar": "fixo",
            "fabricante": fab,
            "modelo": mod,
            "sentido": None,
            "sentido_original": nz.pick(raw, "Faixas"),
            "observacoes": observacoes or None,
        }
