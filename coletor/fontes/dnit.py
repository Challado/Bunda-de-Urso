# -*- coding: utf-8 -*-
"""Fonte F04 - DNIT, Controle de Velocidade / PNCV.

Portal: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
O portal publica, por edicao, um dicionario (PDF) e uma planilha (XLSX/CSV)
cujo NOME muda a cada publicacao (ex.: cgpert___pncv___07_2026.xlsx). Por isso
NAO fixamos a URL do arquivo datado: perguntamos a API CKAN qual e o recurso
mais recente. Aceita arquivo LOCAL (fixtures/testes sem rede) ou URL.
"""
import json
import math
import os
import re

from core import config
from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_XLSX = ("application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet")


class ColetorDNIT(ColetorBase):

    FONTE = {
        "nome": "DNIT - Controle de velocidade (PNCV)",
        "organizacao": "Departamento Nacional de Infraestrutura de Transportes",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/dnit/pt-br",
        "documentacao_url": ("https://servicos.dnit.gov.br/dadosabertos/"
                             "dataset/controle-de-velocidade"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "irregular (edicoes por periodo)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "PNCV - controle de velocidade (XLSX/CSV por edicao)",
        "url_recurso": ("https://servicos.dnit.gov.br/dadosabertos/"
                        "dataset/controle-de-velocidade"),
        "formato_origem": "xlsx|csv",
        "dicionario_url": ("https://servicos.dnit.gov.br/dadosabertos/dataset/"
                           "afb1da02-221b-462b-a3e1-1b11dffb495b/resource/"
                           "fd23a83c-30ac-4bb3-b7a4-7fdc67c8f4a0/download/"
                           "dicionario-de-dados-controle-de-velocidade.pdf"),
        "periodicidade_segundos": 2592000,   # ~30 dias
        "status_integracao": "ok",
    }

    CKAN_BASE = "https://servicos.dnit.gov.br/dadosabertos"
    CKAN_DATASET = "afb1da02-221b-462b-a3e1-1b11dffb495b"
    URL_FALLBACK = ("https://servicos.dnit.gov.br/dadosabertos/dataset/"
                    "afb1da02-221b-462b-a3e1-1b11dffb495b/resource/"
                    "32ece134-15bf-40be-9582-d8889e71062e/download/"
                    "cgpert___pncv___07_2026.xlsx")

    # -- resolucao de URL -------------------------------------------------
    @staticmethod
    def _chave_data(nome, url):
        """(ano, mes, dia) extraido do nome/url; (0,0,0) se nao houver data."""
        s = "%s %s" % (nome or "", url or "")
        m = re.search(r"(\d{2})_(\d{2})_(\d{4})", s)     # dd_mm_yyyy
        if m:
            return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.search(r"(\d{2})_(\d{4})", s)             # mm_yyyy
        if m:
            return (int(m.group(2)), int(m.group(1)), 0)
        return (0, 0, 0)

    @classmethod
    def resolver_url(cls):
        """URL da planilha mais recente (XLSX; senao CSV); fallback fixo."""
        try:
            from coletor.fontes import ckan
            recursos = ckan.package_show(cls.CKAN_BASE, cls.CKAN_DATASET)
        except Exception:                                  # noqa: BLE001
            return cls.URL_FALLBACK
        for extensao in (".xlsx", ".csv"):
            cand = [(cls._chave_data(r.get("name"), r.get("url")),
                     r.get("url"))
                    for r in recursos
                    if (r.get("url") or "").lower().endswith(extensao)]
            if cand:
                cand.sort(key=lambda par: par[0], reverse=True)
                return cand[0][1]
        return cls.URL_FALLBACK

    def _baixar(self, url):
        corpo, _headers, _url_final = http.baixar(url)
        return corpo

    # -- carregar ---------------------------------------------------------
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
        registros = pl.ler_csv(conteudo)
        return conteudo, ".csv", "text/csv", registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "Código Identificação", "Codigo Identificacao",
                       "Código do Equipamento", "Codigo do Equipamento",
                       "codigo", "Codigo")

    @staticmethod
    def _via(rodovia):
        r = (rodovia or "").strip()
        if not r:
            return None
        if r.upper().startswith("BR"):
            return r.upper().replace(" ", "-")
        return "BR-" + r

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
            nz.pick(raw, "Coordenadas (Lat/Long)", "Coordenadas", "coordenadas"))
        multas = "Código do Equipamento" in raw and "Coordenadas" in raw
        if multas:
            # Formato confirmado nos 1.631 codigos comuns aos dois XLSX.
            lat, lon = lon, lat
        if multas and lat is not None and lon is not None and not (-34 <= lat <= 6 and -74 <= lon <= -34):
            raise ValueError("Coordenadas DNIT Multas fora do formato longitude/latitude brasileiro")
        if (lat is None or lon is None) and not multas:
            # sem coordenada: preserva o registro bruto, nao posiciona
            return None
        fab, mod = self._marca_modelo(
            nz.pick(raw, "Marca / Modelo", "Marca/Modelo"))
        observacoes = "; ".join(x for x in (
            ("Tipo: %s" % raw.get("Tipo")) if raw.get("Tipo") else None,
            ("Faixas: %s" % raw.get("Faixas")) if raw.get("Faixas") else None,
            ("Contrato: %s" % (raw.get("Contrato")
                               or raw.get("Edital / Lote (Operadora)")))
            if (raw.get("Contrato") or raw.get("Edital / Lote (Operadora)"))
            else None,
            ("Cod. ET: %s" % raw.get("Cód. ET")) if raw.get("Cód. ET") else None,
            ("Cod. EV: %s" % raw.get("Cód. EV")) if raw.get("Cód. EV") else None,
        ) if x)
        serie = str(nz.pick(raw, "Nº de Série", "Nº de Serie") or "").strip()
        serie = serie if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", serie) and serie != "0" else None
        numero = str(nz.pick(raw, "Registro INMETRO") or "").strip()
        numero = str(int(numero)) if serie and re.fullmatch(r"\d+", numero) and int(numero) > 0 else None
        return {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao DNIT (Multas)" if multas else "publicacao DNIT (PNCV)",
            "complementar_cadastro_oficial": True,
            "numero_serie": serie,
            "numero_inmetro": numero,
            "uf": nz.pick(raw, "UF", "Uf", "uf"),
            "municipio_nome": nz.pick(raw, "Município", "Municipio", "municipio"),
            "via_codigo": self._via(nz.pick(raw, "Rodovia", "rodovia")),
            "via_tipo": "federal",
            "km": nz.to_float(nz.pick(raw, "Km", "KM", "km")),
            "tipo_pista": nz.pick(raw, "Faixas"),
            "tipo_radar": "fixo",
            "fabricante": fab,
            "modelo": mod,
            "sentido": None,
            "sentido_original": None,
            "observacoes": observacoes or None,
        }


class ColetorDNITEquipamentos(ColetorDNIT):
    """Outra publicacao do MESMO orgao e codigo: fonte comum, recurso separado.

    A API publica fornece o GeoJSON usado pelo portal para gerar seu XLSX.
    Baixa os dados diretamente por HTTP, sem navegador. Tambem aceita os
    arquivos GeoJSON e XLSX do operador. Nao substitui a planilha PNCV.
    """
    PAGINA = "https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao"
    URL_API = "https://servicos.dnit.gov.br/services-sior/portal-multas/pncv/equipamentos"
    RECURSO = {
        # Nome preservado: e parte da chave do recurso ja instalado no banco.
        "nome": "DNIT Multas - Equipamentos de fiscalizacao (exportacao XLSX)",
        "url_recurso": URL_API, "formato_origem": "geojson|xlsx",
        "periodicidade_segundos": 604800, "status_integracao": "ok",
    }

    @classmethod
    def resolver_url(cls):
        return cls.URL_API

    def garantir_referencias(self):
        fonte_id, recurso_id = super().garantir_referencias()
        campos = ("url_recurso", "formato_origem", "status_integracao")
        valores = tuple(self.RECURSO[c] for c in campos)
        atual = self.conn.execute(
            "SELECT url_recurso, formato_origem, status_integracao "
            "FROM RECURSO_FONTE WHERE id=?", (recurso_id,)).fetchone()
        if tuple(atual) != valores:
            self.conn.execute(
                "UPDATE RECURSO_FONTE SET url_recurso=?, formato_origem=?, "
                "status_integracao=? WHERE id=?", valores + (recurso_id,))
            self.conn.commit()
        return fonte_id, recurso_id

    def carregar(self, origem):
        if origem and os.path.isfile(origem):
            with open(origem, "rb") as arquivo:
                corpo = arquivo.read()
        else:
            url = self.URL_API if not origem or origem.rstrip("/") == self.PAGINA else origem
            corpo = self._baixar(url)
        if not corpo.startswith(b"PK"):
            registros = self._ler_geojson(corpo)
            return corpo, ".geojson", "application/geo+json", registros
        linhas = pl.ler_xlsx(corpo)
        esperadas = {"Código do Equipamento", "Equipamento", "UF", "Município",
                     "Rodovia", "Km", "Coordenadas", "Registro INMETRO", "Nº de Série"}
        if not linhas or len(linhas[0]) != len(esperadas) or set(linhas[0]) != esperadas:
            raise ValueError("DNIT Multas alterou o cabecalho da exportacao")
        registros = pl.dicts_de_linhas(linhas)
        self._validar_codigos(registros)
        return corpo, ".xlsx", MIME_XLSX, registros

    def _validar_codigos(self, registros):
        codigos = [str(self.identificador(r) or "").strip().upper() for r in registros]
        if not registros or not all(codigos) or len(set(codigos)) != len(codigos):
            raise ValueError("Publicacao DNIT vazia ou com codigos ausentes/ambiguos")

    def _ler_geojson(self, corpo):
        try:
            documento = json.loads(corpo.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("API DNIT nao retornou GeoJSON valido") from exc
        if not isinstance(documento, dict) or documento.get("type") != "FeatureCollection" \
                or not isinstance(documento.get("features"), list):
            raise ValueError("API DNIT alterou a estrutura FeatureCollection")
        registros = documento["features"]
        campos = {"codigo", "tipoNome", "uf", "municipio", "rodovia", "km", "inmetro", "serie"}
        for indice, registro in enumerate(registros, 1):
            if not isinstance(registro, dict) or registro.get("type") != "Feature":
                raise ValueError("API DNIT: registro %d nao e Feature" % indice)
            propriedades = registro.get("properties")
            geometria = registro.get("geometry")
            if not isinstance(propriedades, dict) or not campos.issubset(propriedades):
                raise ValueError("API DNIT: campos obrigatorios ausentes no registro %d" % indice)
            if not isinstance(geometria, dict) or geometria.get("type") != "Point":
                raise ValueError("API DNIT: geometria Point ausente no registro %d" % indice)
            coordenadas = geometria.get("coordinates")
            if not isinstance(coordenadas, list) or len(coordenadas) < 2 \
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in coordenadas[:2]):
                raise ValueError("API DNIT: coordenadas invalidas no registro %d" % indice)
            lon, lat = coordenadas[:2]
            if not (-34 <= lat <= 6 and -74 <= lon <= -34):
                raise ValueError("API DNIT: coordenadas fora do Brasil no registro %d" % indice)
        self._validar_codigos(registros)
        return registros  # Feature original preservada no REGISTRO_FONTE.

    def identificador(self, raw):
        if raw.get("type") == "Feature":
            return raw["properties"].get("codigo")
        return super().identificador(raw)

    def normalizar(self, idx, raw):
        if raw.get("type") == "Feature":
            propriedades = raw["properties"]
            lon, lat = raw["geometry"]["coordinates"][:2]
            # Mesma projecao de downloadTable() no portal. So a normalizacao
            # usa essas colunas; o payload original continua integral no banco.
            raw = {
                "Código do Equipamento": propriedades["codigo"],
                "Equipamento": propriedades["tipoNome"],
                "UF": propriedades["uf"], "Município": propriedades["municipio"],
                "Rodovia": propriedades["rodovia"], "Km": propriedades["km"],
                "Coordenadas": "%s, %s" % (lon, lat),
                "Registro INMETRO": propriedades["inmetro"],
                "Nº de Série": propriedades["serie"],
            }
        return super().normalizar(idx, raw)
