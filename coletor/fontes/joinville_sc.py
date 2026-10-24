# -*- coding: utf-8 -*-
"""Fonte F19 - Joinville DETRANS (SC), estudos tecnicos de fiscalizacao.

Pagina de entrada (catalogo):
    https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  ...eventos/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-
  e-lombadas/  ->  HTTP 200, text/html.  A pagina NAO publica dataset
  estruturado: ela relaciona (115 ancoras unicas) ESTUDOS TECNICOS em PDF,
  por equipamento/local, alem de dois PDFs de "Atualizacao Bienal dos Locais
  de Fiscalizacao com Radares ..." (2026/08) e os estudos anteriores em
  /2024/09/.

  Os PDFs sao codificados por mapa de fontes (cmap): a extracao de texto
  "best-effort" da biblioteca padrao (`planilha.ler_pdf_texto`) devolve
  conteudo vazio/ilegivel nestas versoes -- confirmado em 10/10/2026.  Logo
  NAO existe recurso estruturado real de radares nesta fonte.

CLASSIFICACAO: os documentos sao ESTUDO_TECNICO, NAO cadastro de radar. A
especificacao v1.1 NAO possui entidade de destino para estudos tecnicos
(as tabelas cobrem ponto, equipamento, trecho, documento de ponto e
verificacao metrologica).  Por isso este conector DESCOBRE e preserva os
documentos publicados e NUNCA cria ponto/trecho/radar a partir deles
(`normalizar` devolve None): sem recurso estruturado real, nada e inventado.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.fontes.documental import ColetorDocumental

MIME_HTML = "text/html; charset=utf-8"


class ColetorJoinville(ColetorDocumental):

    MARCADORES_DOCUMENTAIS = ('estudos tecnicos', 'radar|fiscalizacao')
    DESCRICAO_COLETA = 'Estudos técnicos de Joinville; documentos não são cadastros de radares.'

    FONTE = {
        "nome": "Joinville DETRANS - Estudos tecnicos de fiscalizacao eletronica",
        "organizacao": "Prefeitura Municipal de Joinville (DETRANS)",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.joinville.sc.gov.br/",
        "documentacao_url": ("https://www.joinville.sc.gov.br/publicacoes/"
                             "estudos-tecnicos-equipamentos-de-fiscalizacao-"
                             "eletronica-radares-e-lombadas/"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "estudos-tecnicos (lista de PDFs por equipamento/local)",
        "url_recurso": ("https://www.joinville.sc.gov.br/publicacoes/"
                        "estudos-tecnicos-equipamentos-de-fiscalizacao-"
                        "eletronica-radares-e-lombadas/"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # sem recurso estruturado de radar: apenas estudos tecnicos em PDF
        "status_integracao": "pendente",
    }

    PAGINA = RECURSO["url_recurso"]

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_documentos(cls, html):
        """Lista (url, titulo, categoria, ano_mes) dos PDFs publicados."""
        if isinstance(html, bytes):
            html = html.decode("utf-8", "replace")
        out = []
        vistos = set()
        for m in re.finditer(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>',
                             html or "", re.S | re.I):
            href = m.group(1)
            url = urllib.parse.urljoin(cls.PAGINA, href)
            if url in vistos:
                continue
            vistos.add(url)
            titulo = " ".join(re.sub(r"<[^>]+>", "", m.group(2)).split())
            out.append({
                "url": url,
                "titulo": titulo or None,
                "categoria": _categoria(url, titulo),
                "ano_mes": _ano_mes(url),
            })
        return out

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(str(ref)):
            with open(ref, "rb") as f:
                return f.read()
        return http.baixar(ref)[0]

    def carregar(self, origem):
        alvo = origem or self.PAGINA
        conteudo = self._ler(alvo)
        html = conteudo.decode("utf-8", "replace") \
            if isinstance(conteudo, bytes) else conteudo
        return (conteudo, ".html", MIME_HTML,
                self.descobrir_documentos(html))

    def identificador(self, raw):
        return raw.get("url")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """ESTUDO_TECNICO nao vira ponto/trecho/radar (spec v1.1 sem entidade).

        A fonte nao publica recurso estruturado de radares: os documentos
        ficam preservados como evidencia bruta (REGISTRO_FONTE), mas NUNCA
        sao convertidos em cadastro de radar. Devolver None mantem a regra
        "ausente = NULL; nao confirmavel = a confirmar".
        """
        return None


def _categoria(url, titulo):
    s = ("%s %s" % (url or "", titulo or "")).lower()
    if "atualizacao-bienal" in s.replace("ç", "c").replace("ã", "a"):
        return "atualizacao_bienal_locais_fiscalizacao"
    if "estudo-tecnico" in s:
        if "redutor" in s:
            return "estudo_tecnico_redutor"
        if "controlador" in s:
            return "estudo_tecnico_controlador"
        return "estudo_tecnico"
    return "documento"


def _ano_mes(url):
    m = re.search(r"/uploads/(\d{4})/(\d{2})/", url or "")
    return ("%s-%s" % (m.group(1), m.group(2))) if m else None
