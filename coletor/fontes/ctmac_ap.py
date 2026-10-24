# -*- coding: utf-8 -*-
"""Fonte AP - CTMac Macapa, radares (lista de locais HISTORICA).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026; publicada 20/06/2022):
  https://macapa.ap.gov.br/radares-de-macapa-passam-a-ter-velocidade-maxima-permitida-de-60-km-h-a-partir-desta-terca-21/

A pagina (noticia oficial da Prefeitura/CTMac) publica a "Localizacao dos
radares": 17 enderecos/cruzamentos urbanos da capital. Publicacao de 2022
(ha outra, ainda mais antiga, de 01/03/2022), SEM coordenada geografica,
SEM dataset, PDF, CSV, GeoJSON e SEM portal de dados abertos
(dados.macapa.ap.gov.br inexistente). O unico mapa embutido na pagina marca a
sede da Prefeitura (Av. Fab, 840), nao os radares.

CLASSIFICACAO (catalogo): lista_localizacao_HISTORICA -- NAO comprova a
situacao atual (equipamentos mudam; a propria materia altera a velocidade de
50 para 60 km/h). Nada atual foi localizado. Por isso este conector DESCOBRE e
PRESERVA a lista historica como evidencia bruta (REGISTRO_FONTE), mas
``normalizar`` devolve None: NENHUM ponto/radar "atual" e criado a partir de
dado de 2022 (regra "ausente = NULL; nao confirmavel = a confirmar").

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import html
import os
import re

from coletor import http
from coletor.fontes.documental import ColetorDocumental

MIME_HTML = "text/html; charset=utf-8"

_ROTULO = re.compile(r"(?is)<strong>\s*Localiza[^<]*</strong>")
_INICIO = "Localiza"


def _texto(fragmento):
    if isinstance(fragmento, bytes):
        fragmento = fragmento.decode("utf-8", "replace")
    t = re.sub(r"(?is)<[^>]+>", " ", fragmento or "")
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


class ColetorCtmacAP(ColetorDocumental):

    MARCADORES_DOCUMENTAIS = ('macapa', 'radar')
    DESCRICAO_COLETA = 'Lista histórica de Macapá; operação atual dos radares não confirmada.'

    FONTE = {
        "nome": "CTMac Macapa - Radares (lista de locais, historica)",
        "organizacao": ("Companhia de Transito e Transporte de Macapa "
                        "(CTMac)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://macapa.ap.gov.br/",
        "documentacao_url": ("https://macapa.ap.gov.br/radares-de-macapa-"
                             "passam-a-ter-velocidade-maxima-permitida-de-60-"
                             "km-h-a-partir-desta-terca-21/"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "historico (2022)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "localizacao dos radares (lista HTML, 2022)",
        "url_recurso": ("https://macapa.ap.gov.br/radares-de-macapa-passam-a-"
                        "ter-velocidade-maxima-permitida-de-60-km-h-a-partir-"
                        "desta-terca-21/"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        # dado historico (2022): nao gera cadastro atual; sem coordenadas.
        "status_integracao": "pendente",
    }

    PAGINA = RECURSO["url_recurso"]

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (lista em HTML; nao ha arquivo datado)."""
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def extrair_locais(cls, html_):
        """Lista de {ordem, texto} dos locais publicados (separados por <br>).

        O rotulo "Localizacao dos radares" e o primeiro item ficam no MESMO
        paragrafo; quebramos por <br> e descartamos o rotulo.
        """
        if isinstance(html_, bytes):
            html_ = html_.decode("utf-8", "replace")
        ini = (html_ or "").find(_INICIO)
        if ini < 0:
            return []
        abertura = html_.rfind("<p", 0, ini)
        fechamento = html_.find("</p>", ini)
        if abertura < 0 or fechamento < 0:
            return []
        interno = _ROTULO.sub(" ", html_[abertura:fechamento])
        registros = []
        for parte in re.split(r"(?i)<br\s*/?>", interno):
            texto = _texto(parte).strip().rstrip(";.").strip()
            if not texto or _INICIO in texto or len(texto) < 5:
                continue
            registros.append({"ordem": len(registros) + 1, "texto": texto})
        return registros

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(str(ref)):
            with open(ref, "rb") as f:
                return f.read()
        return http.baixar(ref)[0]

    def carregar(self, origem):
        alvo = origem or self.PAGINA
        conteudo = self._ler(alvo)
        return (conteudo, ".html", MIME_HTML,
                self.extrair_locais(conteudo))

    def identificador(self, raw):
        return None

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Dado HISTORICO de 2022: nao vira cadastro/radar atual.

        O endereco e preservado em REGISTRO_FONTE (evidencia bruta), mas nao e
        convertido em PONTO_FISCALIZACAO: a publicacao nao comprova a situacao
        atual e nao traz coordenada. Devolver None mantem "nao confirmavel =
        a confirmar" (nada inventado).
        """
        return None
