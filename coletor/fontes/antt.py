# -*- coding: utf-8 -*-
"""Fonte F02/F03 - ANTT, radares nas rodovias concedidas.

Conjunto: https://dados.antt.gov.br/dataset/radar
A coleta acompanha as atividades do conjunto para descobrir a edição atual.
"""
import csv
from html.parser import HTMLParser
import io
import json
import os
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from core import atualizacoes
from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import ckan, normalizacao as nz


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.urls.append(href)


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
    URL_ATIVIDADES = CKAN_BASE + "/dataset/activity/radar"
    URL_CATALOGO = CKAN_BASE + "/dataset/radar"
    _DATASET_PATH = r"/dataset/(?:radar|" + CKAN_DATASET + r")"
    _DOWNLOAD = re.compile(_DATASET_PATH + r"/resource/[^/]+/download/[^/]+")
    _REVISAO = re.compile(_DATASET_PATH + r"/history/[\da-f-]{36}/?", re.I)
    _ARQUIVO = re.compile(r"dados[-_ ]+dos[-_ ]+radares(?:[-_. ]*(\d+)[-_ ]+(\d{4}))?",
                         re.I)

    @classmethod
    def resolver_url(cls):
        """Origem estável da agenda. Descoberta e download entram na mesma execução."""
        return cls.URL_ATIVIDADES

    @classmethod
    def _url_oficial(cls, href, pagina):
        if not isinstance(href, str) or not href.strip():
            return None
        try:
            url = urljoin(pagina, href.strip())
            p = urlsplit(url)
            if p.scheme in ("http", "https") and p.netloc.lower() == urlsplit(cls.CKAN_BASE).netloc:
                return p._replace(scheme="https", fragment="").geturl()
        except ValueError:
            return None
        return None

    @classmethod
    def _links_da_pagina(cls, pagina):
        corpo, _, url_final = http.baixar(pagina, timeout=12)
        parser = _Links()
        parser.feed(corpo.decode("utf-8", "replace"))
        parser.close()
        return [url for href in parser.urls if (url := cls._url_oficial(href, url_final))]

    @classmethod
    def _recursos_atividade(cls):
        links = cls._links_da_pagina(cls.URL_ATIVIDADES)
        # O CKAN lista as atividades da mais recente para a mais antiga.
        # Versões do portal usam /history/<id> ou ?activity_id=<id>.
        for link in links:
            p = urlsplit(link)
            if cls._REVISAO.fullmatch(p.path) or (
                    re.fullmatch(cls._DATASET_PATH + r"/?", p.path)
                    and parse_qs(p.query).get("activity_id")):
                return [{"url": url} for url in cls._links_da_pagina(link)]
        return [{"url": url} for url in links]

    @classmethod
    def _urls_da_edicao(cls, recursos):
        arquivos = []
        for recurso in recursos:
            if not isinstance(recurso, dict):
                continue
            url = cls._url_oficial(recurso.get("url"), cls.URL_CATALOGO)
            if not url:
                continue
            caminho = unquote(urlsplit(url).path)
            if not cls._DOWNLOAD.fullmatch(caminho):
                continue
            nome, ext = os.path.splitext(caminho.rsplit("/", 1)[-1])
            edicao = cls._ARQUIVO.fullmatch(nome)
            if ext.lower() not in (".json", ".csv") or not edicao:
                continue
            numero, ano = edicao.groups()
            data = recurso.get("last_modified") or recurso.get("created") or ""
            arquivos.append(((int(ano or 0), int(numero or 0)), ext.lower(), str(data), url))
        if not arquivos:
            return []
        atual = max(item[0] for item in arquivos)
        urls = []
        for formato in (".json", ".csv"):
            opcoes = [(data, url) for edicao, ext, data, url in arquivos if edicao == atual and ext == formato]
            if opcoes:
                urls.append(max(opcoes, key=lambda item: item[0])[1])
        return urls

    @classmethod
    def _descobrir_edicao(cls):
        origens = (
            ("atividades", cls._recursos_atividade),
            ("api_ckan", lambda: ckan.package_show(cls.CKAN_BASE, cls.CKAN_DATASET, timeout=12)),
            ("catalogo", lambda: [{"url": url} for url in cls._links_da_pagina(cls.URL_CATALOGO)]),
        )
        falhas = []
        for metodo, consultar in origens:
            try:
                urls = cls._urls_da_edicao(consultar())
                if not urls:
                    raise http.ErroFonte("Nenhum arquivo JSON ou CSV da série de radares encontrado")
            except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as exc:
                falhas.append(f"{metodo}: {exc}")
                atualizacoes.evento("antt.descoberta_erro", metodo=metodo, erro=str(exc))
            else:
                atualizacoes.evento("antt.edicao_descoberta", metodo=metodo, urls=urls)
                return metodo, urls
        raise http.ErroFonte("ANTT: não foi possível descobrir a edição atual. " + " | ".join(falhas))

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        """origem: caminho local OU url. Retorna (bytes, ext, mime, registros)."""
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            return self._ler(conteudo, os.path.splitext(origem)[1].lower())
        if not origem or origem.rstrip("/") in (self.URL_ATIVIDADES, self.URL_CATALOGO, self.RECURSO["url_recurso"]):
            metodo, urls = self._descobrir_edicao()
        else:
            metodo, urls = "url_informada", [origem]
        falhas = []
        for url in urls:
            if hasattr(self, "_diario_coleta"):
                self._diario_coleta.update(origem=url, metodo_descoberta=metodo, urls_edicao=urls)
            try:
                conteudo = self._baixar(url)
                if conteudo.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"<"):
                    raise http.ErroFonte("O endereço devolveu uma página HTML no lugar do arquivo de dados")
                resultado = self._ler(conteudo, os.path.splitext(urlsplit(url).path)[1].lower())
                registros = resultado[3]
                if (not isinstance(registros, list) or any(not isinstance(r, dict) for r in registros)
                        or not any(nz.pick(r, "latitude", "lat") is not None
                                   and nz.pick(r, "longitude", "lon", "lng") is not None
                                   for r in registros)):
                    raise http.ErroFonte("Arquivo sem registros no formato de radares da ANTT")
                return resultado
            except (http.ErroFonte, ValueError, csv.Error) as exc:
                falhas.append(f"{url}: {exc}")
                atualizacoes.evento("antt.download_erro", url=url, erro=str(exc))
        raise http.ErroFonte("ANTT: falha ao ler a edição selecionada. " + " | ".join(falhas))

    def _ler(self, conteudo, ext):
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
        corpo, _headers, _url_final = http.baixar(url)
        return corpo

    @staticmethod
    def _parece_csv(conteudo):
        amostra = conteudo.removeprefix(b"\xef\xbb\xbf").lstrip()
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
            "km": nz.to_float(nz.pick(raw, "Km", "KM", "km", "Quilometro", "km_m")),
            "tipo_pista": nz.pick(raw, "Pista", "pista", "Faixa", "tipo_de_pista"),
            "situacao": nz.normalizar_situacao(
                nz.pick(raw, "Situacao", "Situação", "situacao", "status")),
            "tipo_radar": self._tipo(nz.pick(raw, "Tipo", "tipo", "TipoRadar", "Equipamento", "tipo_de_radar")),
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

    @staticmethod
    def _tipo(valor):
        # Nesta publicacao, controlador/redutor designam equipamentos fixos.
        if str(valor or '').strip().lower() in ('controlador', 'redutor', 'lombada eletronica', 'lombada eletrônica'):
            return 'fixo'
        return nz.normalizar_tipo_radar(valor)
