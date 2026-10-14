# -*- coding: utf-8 -*-
"""Fonte DF - Detran-DF, relacao de medidores de velocidade / fiscalizacao.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://www.detran.df.gov.br/equipamentos-eletronicos

A pagina ("Equipamentos Eletronicos", art. 6o/7o/9o da Resolucao CONTRAN no
798/2020) aponta para o unico endereco da "Relacao de todos os medidores de
velocidade existentes DETRAN-DF":

  https://geoservicos.detran.df.gov.br/geoserver/styles/lista_equipto/index.html

Esse endereco e uma pagina estatica que carrega o arquivo de dados

  https://geoservicos.detran.df.gov.br/geoserver/styles/lista_equipto/equipamentos.js

com um array ``equipamentos`` (colunas reais):

  identificacao | tipo | numero_serie | local_instalacao | levantamento_estudo

``tipo`` assume tres valores: ``DETRAN - RADAR`` (radar de velocidade),
``DETRAN - LOMBADA ELETRÔNICA`` (medidor de velocidade tipo lombada) e
``AVANÇO DE SINAL VERMELHO`` (fiscalizacao de avanco de sinal -- NAO e medidor
de velocidade).  A lista NAO traz coordenadas: a posicao geografica fica NULL
(nada e inventado a partir do texto do "local_instalacao").

--------------------------------------------------------------------------------
STATUS: PARCIAL -- o recurso EXISTE (lista estruturada, ~407 registros em
10/10/2026) mas NAO e baixavel por cliente nao-navegador.  O host
``geoservicos.detran.df.gov.br`` e protegido por um WAF F5/BigIP que RESETA a
conexao (``Connection reset by peer``) para as extensoes ``.js``/``.txt``/
``.htm`` -- inclusive o arquivo de dados ``equipamentos.js`` -- enquanto serve
``.html`` e ``.pdf`` normalmente.  Verificado em 10/10/2026:

  * ``curl`` / ``python urllib`` / ``openssl s_client`` -> connection reset em
    ``equipamentos.js``; ``index.html`` responde 200;
  * um navegador real (Chromium gerenciado) carrega ``equipamentos.js`` (200) e
    renderiza a tabela completa.

Como o coletor so usa ``coletor.http.baixar`` (biblioteca padrao), a coleta ao
vivo FALHA e o erro e propagado (``ErroFonte``/``ErroRetentavel``) -- nao ha
fallback silencioso.  O modulo permanece util para: (a) validar o
descobrimento e o parse contra fixtures reais; (b) voltar a funcionar se a
politica do WAF mudar ou se um proxy autorizado for usado.  Aceita arquivo
LOCAL (fixture de ``equipamentos.js``) para testes offline.
"""
import json
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_JS = "application/javascript"

PADRAO_GEOSERVICOS = re.compile(
    r"https://geoservicos\.detran\.df\.gov\.br/[^\"'\s<>]+", re.I)

# Mapeamento do tipo declarado pela fonte para o tipo de radar interno.
# AVANÇO DE SINAL VERMELHO nao e medidor de velocidade -> nao vira tipo.
_TIPO_RADAR = {
    "DETRAN - RADAR": "fixo",
    "DETRAN - LOMBADA ELETRÔNICA": "fixo",
}


class ColetorDetranDF(ColetorBase):

    FONTE = {
        "nome": "Detran-DF - Relacao de medidores de velocidade",
        "organizacao": ("Departamento de Transito do Distrito Federal "
                        "(Detran-DF)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "distrital",
        "natureza": "oficial",
        "url_institucional": "https://www.detran.df.gov.br/",
        "documentacao_url": "https://www.detran.df.gov.br/equipamentos-eletronicos",
        "licenca": "pagina institucional publica (Resolucao CONTRAN 798/2020)",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Lista de equipamentos eletronicos de fiscalizacao (JS)",
        "url_recurso": "https://www.detran.df.gov.br/equipamentos-eletronicos",
        "formato_origem": "js",
        "periodicidade_segundos": 2592000,     # ~30 dias
        # PARCIAL: o arquivo de dados e servido apenas a navegadores (WAF F5).
        "status_integracao": "parcial",
    }

    URL_PAGINA = "https://www.detran.df.gov.br/equipamentos-eletronicos"
    URL_LISTA_FALLBACK = ("https://geoservicos.detran.df.gov.br/geoserver/"
                          "styles/lista_equipto/index.html")
    URL_DADOS_FALLBACK = ("https://geoservicos.detran.df.gov.br/geoserver/"
                          "styles/lista_equipto/equipamentos.js")

    # -- descoberta --------------------------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Mapeia a pagina -> {lista: URL da listagem no geoservicos}."""
        for m in PADRAO_GEOSERVICOS.finditer(html or ""):
            url = m.group(0)
            if "lista_equipto" in url:
                return {"lista": url}
        return {}

    @staticmethod
    def _url_dados(lista_url):
        """.../lista_equipto/index.html -> .../lista_equipto/equipamentos.js."""
        base = lista_url.split("?", 1)[0]
        if "/" in base:
            base = base.rsplit("/", 1)[0]
        return base + "/equipamentos.js"

    @classmethod
    def resolver_url(cls):
        """URL do arquivo de dados descoberta na pagina; fallback fixo."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            lista = cls.descobrir_recursos(html).get("lista")
            if lista:
                return cls._url_dados(lista)
        except Exception:                                   # noqa: BLE001
            pass
        return cls.URL_DADOS_FALLBACK

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "r", encoding="utf-8") as f:
                texto = f.read()
        else:
            url = origem or self.resolver_url()
            if "detran.df.gov.br/equipamentos-eletronicos" in url:
                url = self.resolver_url()
            # WAF F5: cliente nao-navegador leva "connection reset" aqui.
            conteudo, _headers, _final = http.baixar(url)
            texto = conteudo.decode("utf-8", "replace")
        return texto, ".js", MIME_JS, self._extrair_registros(texto)

    # -- parsing -----------------------------------------------------------
    @staticmethod
    def _extrair_registros(texto):
        """Extrai o array JSON embutido no JS (``const equipamentos = [...];``)."""
        if not texto:
            return []
        ini, fim = texto.find("["), texto.rfind("]")
        if ini < 0 or fim < ini:
            return []
        try:
            dados = json.loads(texto[ini:fim + 1])
        except ValueError:
            return []
        return dados if isinstance(dados, list) else []

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "identificacao")

    @staticmethod
    def _tipo_radar(tipo):
        if not tipo:
            return None
        return _TIPO_RADAR.get(tipo.strip().upper())

    def normalizar(self, idx, raw):
        tipo = (nz.pick(raw, "tipo") or "").strip()
        local = nz.pick(raw, "local_instalacao")
        estudo = nz.pick(raw, "levantamento_estudo")
        obs = "; ".join(x for x in (
            ("Tipo na fonte: %s" % tipo) if tipo else None,
            ("Local: %s" % local) if local else None,
            ("Levantamento/estudo: %s" % estudo) if estudo else None,
            ("Nao e medidor de velocidade (avanco de sinal)")
            if tipo.upper().startswith("AVANÇO") else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            # a lista do Detran-DF NAO traz coordenadas
            "latitude": None,
            "longitude": None,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao Detran-DF (relacao de medidores de "
                                "velocidade / equipamentos de fiscalizacao)"),
            "uf": "DF",
            "municipio_nome": None,
            "via_codigo": None,
            "via_tipo": None,
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            "tipo_radar": self._tipo_radar(tipo),
            "numero_serie": nz.pick(raw, "numero_serie"),
            "fabricante": None,
            "modelo": None,
            "velocidade_geral": None,
            "sentido": None,
            "sentido_original": None,
            "observacoes": obs,
        }
