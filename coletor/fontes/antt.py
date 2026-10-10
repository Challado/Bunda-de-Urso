# -*- coding: utf-8 -*-
"""Fonte F02/F03 - ANTT, radares nas rodovias concedidas.

Conjunto: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17
As URLs publicadas variam por edicao mensal (nao fixar a URL de um arquivo
mensal). Aceita arquivo LOCAL (fixture/tests sem rede) ou baixa via urllib.
"""
import csv
import io
import json
import os
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


class ColetorANTT(ColetorBase):

    FONTE = {
        "nome": "ANTT - Dados dos radares em rodovias concedidas",
        "organizacao": "Agencia Nacional de Transportes Terrestres",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/antt/pt-br",
        "documentacao_url": ("https://dados.antt.gov.br/dataset/"
                             "79d287f4-f5ca-4385-a17c-f61f53831f17"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "mensal",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "dados-dos-radares (JSON/CSV por edicao)",
        "url_recurso": ("https://dados.antt.gov.br/dataset/"
                        "79d287f4-f5ca-4385-a17c-f61f53831f17"),
        "formato_origem": "json|csv",
        "periodicidade_segundos": 2592000,   # ~30 dias
        "status_integracao": "ok",
    }

    # -- resolucao de URL -------------------------------------------------
    CKAN_BASE = "https://dados.antt.gov.br"
    CKAN_DATASET = "79d287f4-f5ca-4385-a17c-f61f53831f17"
    URL_FALLBACK = ("https://dados.antt.gov.br/dataset/"
                    "79d287f4-f5ca-4385-a17c-f61f53831f17/resource/"
                    "eaace43a-aedf-4f69-949e-5001ae54173b/download/"
                    "dados-dos-radares6_2026.json")

    @classmethod
    def resolver_url(cls):
        """URL direta da edicao mais nova (API CKAN); fallback fixo.

        A URL de um arquivo mensal muda a cada edicao; por isso nao fixamos
        a URL no codigo: perguntamos ao portal qual e o recurso mais recente.
        """
        try:
            from coletor.fontes import ckan
            url = ckan.url_do_mais_novo(
                cls.CKAN_BASE, cls.CKAN_DATASET, "JSON",
                r"dados-dos-radares(\d+)_(\d{4})", ckan.versao_numerica())
            if url:
                return url
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        """origem: caminho local OU url. Retorna (bytes, ext, mime, registros)."""
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower() or ".json"
        else:
            conteudo = self._baixar(origem or self.RECURSO["url_recurso"])
            ext = ".json"
        if ext == ".csv" or self._parece_csv(conteudo):
            registros = self._parse_csv(conteudo)
            ext = ".csv"
            mime = "text/csv"
        else:
            registros = self._parse_json(conteudo)
            ext = ".json"
            mime = "application/json"
        return conteudo, ext, mime, registros

    def _baixar(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=config.DEFAULT_TIMEOUT) as resp:
            return resp.read()

    @staticmethod
    def _parece_csv(conteudo):
        amostra = conteudo[:64].lstrip()
        return not amostra.startswith((b"{", b"["))

    @staticmethod
    def _parse_json(conteudo):
        dados = json.loads(conteudo.decode("utf-8-sig"))
        if isinstance(dados, dict):
            for chave in ("features", "dados", "data", "records", "radar",
                          "radares", "items"):
                if isinstance(dados.get(chave), list):
                    return dados[chave]
            # dict de dicts
            return [v for v in dados.values() if isinstance(v, dict)]
        return dados

    @staticmethod
    def _parse_csv(conteudo):
        texto = conteudo.decode("utf-8-sig")
        # descobre delimitador simples
        primeira = texto.splitlines()[0] if texto.splitlines() else ""
        delim = ";" if primeira.count(";") >= primeira.count(",") else ","
        return list(csv.DictReader(io.StringIO(texto), delimiter=delim))

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "Codigo", "Código", "codigo", "id", "Id",
                       "ID", "codigoRadar")

    def normalizar(self, idx, raw):
        lat = nz.to_float(nz.pick(raw, "Latitude", "latitude", "lat"))
        lon = nz.to_float(nz.pick(raw, "Longitude", "longitude", "lon", "lng"))
        if lat is None or lon is None:
            # coordenada ausente: preservar payload, nao posicionar
            return None
        rodovia = nz.pick(raw, "Rodovia", "rodovia", "BR", "via")
        d = {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "precisao_metros": nz.to_float(nz.pick(raw, "Precisao", "precisao")),
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao ANTT",
            "uf": nz.pick(raw, "UF", "Uf", "uf", "Estado"),
            "municipio_nome": nz.pick(raw, "Municipio", "Município",
                                      "municipio", "cidade"),
            "municipio_ibge": nz.pick(raw, "CodigoIBGE", "codigo_ibge",
                                      "ibge", "CodIBGE"),
            "via_codigo": rodovia,
            "km": nz.to_float(nz.pick(raw, "Km", "KM", "km", "Quilometro")),
            "tipo_pista": nz.pick(raw, "Pista", "pista", "Faixa"),
            "situacao": nz.normalizar_situacao(
                nz.pick(raw, "Situacao", "Situação", "situacao", "status")),
            "tipo_radar": nz.normalizar_tipo_radar(
                nz.pick(raw, "Tipo", "tipo", "TipoRadar", "Equipamento")),
            "numero_serie": nz.pick(raw, "NumeroSerie", "numero_serie",
                                    "Serie", "serie"),
            "fabricante": nz.pick(raw, "Fabricante", "fabricante", "Marca"),
            "modelo": nz.pick(raw, "Modelo", "modelo"),
            "velocidade_leves": nz.to_float(
                nz.pick(raw, "VelocidadeLeves", "velocidade_leves",
                        "velocidade_leve", "VelLeves", "Velocidade")),
            "velocidade_pesados": nz.to_float(
                nz.pick(raw, "VelocidadePesados", "velocidade_pesados",
                        "velocidade_pesado", "VelPesados",
                        "VelocidadePesado")),
            "sentido": nz.normalizar_sentido(nz.pick(raw, "Sentido", "sentido")),
            "sentido_original": nz.pick(raw, "Sentido", "sentido"),
            "observacoes": nz.pick(raw, "Observacao", "Observação",
                                   "Concessionaria", "concessionaria"),
        }
        return d
