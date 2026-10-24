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
STATUS: IMPLEMENTADO (com contorno de WAF documentado).

O host ``geoservicos.detran.df.gov.br`` esta atras de um WAF F5/BigIP.  Para
CLIENTE NAO-NAVEGADOR ele RESETA a conexao (``Connection reset by peer``) em
``equipamentos.js`` -- mesmo repetindo os cabecalhos de um Chrome real e mesmo
com os cookies de sessao -- e tambem no resto do ``/geoserver`` (``wfs``/
``wms``/``.txt``/``.htm``).  Apenas ``lista_equipto/index.html`` responde 200, e
a resposta traz os cookies de sessao F5 (``reverse_proxy``,
``f5avra..._session_``, ``TS...``).  O ``equipamentos.js`` so passa quando o
pedido carrega a sessao que o proprio ``index.html`` recebeu.

CONTORNO (verificado em 10/10/2026): baixar com um navegador de verdade, em
DOIS passos e com um perfil persistente -- (1) abrir o ``index.html`` (o
navegador ganha os cookies F5) e (2) abrir o ``equipamentos.js`` (ja com a
sessao).  Renderizado, o ``equipamentos.js`` volta como texto (dentro de
``<pre>``) e o array completo (407 registros em 10/10/2026) e extraido.

Por isso este modulo: (a) tenta primeiro ``coletor.http.baixar`` (biblioteca
padrao, regra do projeto); (b) se o WAF resetar, cai no contorno de navegador
acima.  DEPENDENCIA DE SISTEMA: um Chromium/Chrome headless (``chromium``,
``chromium-browser`` ou ``google-chrome``) -- mesma natureza da dependencia de
``pdftotext`` de outras fontes; se ausente, levanta ``ErroFonte`` claro.
Aceita arquivo LOCAL (fixture de ``equipamentos.js``) para testes offline.
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from core import caminhos

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_JS = "application/javascript"

PADRAO_GEOSERVICOS = re.compile(
    r"https://geoservicos\.detran\.df\.gov\.br/[^\"'\s<>]+", re.I)

# Navegadores aceitos no contorno de WAF (F5 BigIP), em ordem de preferencia.
_NAVEGADORES = ("chromium", "chromium-browser", "google-chrome",
                "google-chrome-stable", "chrome")

# Mapeamento do tipo declarado pela fonte para o tipo de radar interno.
# AVANÇO DE SINAL VERMELHO nao e medidor de velocidade -> nao vira tipo.
_TIPO_RADAR = {
    "DETRAN - RADAR": "fixo",
    "DETRAN - LOMBADA ELETRÔNICA": "fixo",
}


def _achar_navegador():
    """Caminho de um Chromium/Chrome headless instalado, ou ``None``."""
    for nome in _NAVEGADORES:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return None


def _dump_dom(navegador, url, perfil, timeout=90):
    """Abre ``url`` headless (perfil dado) e devolve o DOM renderizado."""
    cmd = [navegador, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", "--no-first-run",
           "--no-default-browser-check", "--user-data-dir=%s" % perfil,
           "--virtual-time-budget=15000", "--dump-dom", url]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    return proc.stdout.decode("utf-8", "replace")


def _texto_do_pre(bruto):
    """Extrai o conteudo de ``<pre>`` (``--dump-dom`` de recurso texto)."""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", bruto or "", re.S | re.I)
    return html.unescape(m.group(1)) if m else (bruto or "")


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
        # Contorno de WAF por navegador (2 passos) quando o cliente nao passa.
        "status_integracao": "implementado",
    }

    URL_PAGINA = "https://www.detran.df.gov.br/equipamentos-eletronicos"
    URL_LISTA_FALLBACK = ("https://geoservicos.detran.df.gov.br/geoserver/"
                          "styles/lista_equipto/index.html")
    URL_DADOS_FALLBACK = ("https://geoservicos.detran.df.gov.br/geoserver/"
                          "styles/lista_equipto/equipamentos.js")

    # -- descoberta --------------------------------------------------------
    @classmethod
    def descobrir_recursos(cls, html_texto):
        """Mapeia a pagina -> {lista: URL da listagem no geoservicos}."""
        for m in PADRAO_GEOSERVICOS.finditer(html_texto or ""):
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
            texto = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            lista = cls.descobrir_recursos(texto).get("lista")
            if lista:
                return cls._url_dados(lista)
        except Exception:                                   # noqa: BLE001
            pass
        return cls.URL_DADOS_FALLBACK

    # -- contorno de WAF ---------------------------------------------------
    @classmethod
    def _texto_via_navegador(cls, dados_url):
        """Contorno do WAF F5: 2 passos (index.html -> equipamentos.js).

        Passo 1 abre o ``index.html`` num perfil persistente (o navegador
        absorve os cookies de sessao F5); passo 2 abre o ``equipamentos.js``
        nesse mesmo perfil, agora aceito.  Devolve o texto do recurso.
        """
        navegador = _achar_navegador()
        if not navegador:
            raise http.ErroFonte(
                "WAF F5 desta fonte exige navegador e nao ha Chromium/Chrome "
                "headless instalado (instale 'chromium'): %s" % dados_url)
        lista = dados_url.rsplit("/", 1)[0] + "/index.html"
        with tempfile.TemporaryDirectory(prefix="detran_df_", dir=caminhos.temporarios()) as perfil:
            _dump_dom(navegador, lista, perfil)          # passo 1: sessao F5
            bruto = _dump_dom(navegador, dados_url, perfil)   # passo 2: dados
        texto = _texto_do_pre(bruto)
        if "equipamentos" not in texto:
            raise http.ErroFonte(
                "contorno de navegador nao devolveu a lista: %s" % dados_url)
        return texto

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "r", encoding="utf-8") as f:
                texto = f.read()
        else:
            url = origem or self.resolver_url()
            if "detran.df.gov.br/equipamentos-eletronicos" in url:
                url = self.resolver_url()
            try:
                conteudo, _headers, _final = http.baixar(url)
                texto = conteudo.decode("utf-8", "replace")
            except (http.ErroFonte, OSError):
                # WAF F5 reseta cliente nao-navegador -> contorno de navegador
                texto = self._texto_via_navegador(url)
        return texto, ".js", MIME_JS, self._extrair_registros(texto)

    # -- parsing -----------------------------------------------------------
    @staticmethod
    def _extrair_registros(texto):
        """Extrai o array JSON embutido no JS (``const equipamentos = [...]``)."""
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
