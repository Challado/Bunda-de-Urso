# -*- coding: utf-8 -*-
"""Fonte MT - Cuiaba/SEMOB, pagina de noticia (historica, 2015).

Pagina de entrada (catalogo, classificacao_evidencia="lista_historica"):
    https://www.cuiaba.mt.gov.br/noticias/comeca-campanha-de-esclarecimento-
    sobre-a-fiscalizacao-eletronica

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (46117 bytes). A pagina e uma NOTICIA
   de 23/11/2015 ("Comeca campanha de esclarecimento sobre a fiscalizacao
   eletronica"), que descreve, em texto corrido, a instalacao de
   equipamentos: "15 pontos", "30 novos equipamentos", "14 radares fixos,
   3 lombadas eletronicas e 13 avancos semaforicos", e cita nove ruas/avenidas
   com a velocidade maxima. NAO existe dataset estruturado (o unico download
   da pagina e um PDF de "processo seletivo", sem relacao com radares); ha
   apenas um link generico para o portal de "Dados Abertos" da
   transparencia.

CLASSIFICACAO/TRATAMENTO: e uma noticia HISTORICA (2015), com locais
descritos de forma textual/narrativa, SEM coordenadas, SEM identificadores
de equipamento e SEM vigencia confirmada. Conforme a regra "trecho/local de
operacao nunca vira radar instalado confirmado", nada aqui e convertido em
cadastro: `normalizar` devolve None. O conector apenas DOCUMENTA a
evidencia (data da publicacao, contagens declaradas, vias citadas) e os
poucos documentos da pagina, preservando o achado. Sem recurso estruturado
real -> status PENDENTE.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.fontes.documental import ColetorDocumental

MIME_HTML = "text/html; charset=utf-8"

PAGINA = ("https://www.cuiaba.mt.gov.br/noticias/"
          "comeca-campanha-de-esclarecimento-sobre-a-fiscalizacao-eletronica")

_RE_DATA = re.compile(
    r"\b(\d{1,2})\s+de\s+([A-Za-z\u00c0-\u00ff]+)\s+de\s+(\d{4})\b")
_RE_EQUIP = re.compile(
    r"(\d+)\s+(radares?\s+fixos?|lombadas?\s+eletr[oô]nicas?|"
    r"avan[çc]os?\s+semaf[oó]ricos?)", re.I)

_CHAVE_EQUIP = (
    ("radar", "radar_fixo"),
    ("lombada", "lombada_eletronica"),
    ("avan", "avanco_semaforico"),
)

_MESES = {
    "janeiro": "01", "fevereiro": "02", "marco": "03", "março": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10", "novembro": "11",
    "dezembro": "12",
}


def _texto(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                 flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'"))
    return " ".join(txt.split())


class ColetorCuiabaMT(ColetorDocumental):

    MARCADORES_DOCUMENTAIS = ('fiscalizacao eletronica', 'radar')
    DESCRICAO_COLETA = 'Notícia histórica de Cuiabá; cadastro atual pendente.'

    FONTE = {
        "nome": "Cuiaba SEMOB - Fiscalizacao eletronica (noticia 2015)",
        "organizacao": "Prefeitura de Cuiaba / SEMOB",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.cuiaba.mt.gov.br/",
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "noticia historica sobre fiscalizacao eletronica (2015)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # noticia historica, sem cadastro estruturado vigente -> pendente
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_documentos(cls, html):
        """Lista os documentos (PDFs) linkados na pagina.

        A pagina NAO publica relacao de radares; o unico PDF e um documento
        avulso de "processo seletivo", sem relacao com fiscalizacao.
        """
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
                "tipo": _tipo_documento(url, titulo),
            })
        return out

    @classmethod
    def evidencia(cls, html):
        """Resumo verificavel do que a pagina declara (sem inventar GPS)."""
        txt = _texto(html)
        md = _RE_DATA.search(txt)
        data = None
        if md:
            mes = _MESES.get(md.group(2).lower(), "00")
            data = "%s-%s-%s" % (md.group(3), mes, md.group(1).zfill(2))
        contagens = {}
        for m in _RE_EQUIP.finditer(txt):
            bruto = m.group(2).lower()
            chave = None
            for prefixo, canonico in _CHAVE_EQUIP:
                if prefixo in bruto:
                    chave = canonico
                    break
            if chave is None:
                continue
            contagens[chave] = max(contagens.get(chave, 0), int(m.group(1)))
        return {
            "data_publicacao": data,
            "contagens_declaradas": contagens or None,
            "tem_dataset_estruturado": bool(
                re.search(r'href="[^"]+\.(?:csv|json|geojson|kml|kmz|ods|'
                          r'xlsx?)"', html or "", re.I)),
            "url_dados_abertos": _url_dados_abertos(html),
        }

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
        docs = self.descobrir_documentos(html)
        ev = self.evidencia(html)
        registro = {
            "url_pagina": self.PAGINA,
            "data_publicacao": ev["data_publicacao"],
            "contagens_declaradas": ev["contagens_declaradas"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "url_dados_abertos": ev["url_dados_abertos"],
            "documentos": docs,
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Noticia historica NAO vira radar (sem coordenadas nem vigencia).

        A pagina descreve locais em texto, mas sem coordenadas, sem
        identificadores e sem confirmacao de vigencia (publicacao de 2015);
        converter "local de operacao" em radar instalado confirmado violaria
        a regra de ouro. Nada e inventado: devolver None mantem "ausente =
        NULL; nao confirmavel = a confirmar".
        """
        return None


def _tipo_documento(url, titulo):
    s = ("%s %s" % (url or "", titulo or "")).lower()
    if re.search(r"(?i)radar|fiscaliza|cadastro|equipament", s):
        return "documento_fiscalizacao"
    return "documento"


def _url_dados_abertos(html):
    m = re.search(r'href="([^"]*transparencia[^"]*dados-abertos[^"]*)"',
                  html or "", re.I)
    return m.group(1) if m else None
