# -*- coding: utf-8 -*-
"""Fonte PI - STRANS Teresina / DER-PI (noticia historica, 2019).

Pagina de entrada (catalogo, classificacao_evidencia="lista_historica"):
    https://antigo.pmt.pi.gov.br/2019/04/10/localizacao-dos-radares-sera-
    divulgada-mensalmente-no-site-da-prefeitura/

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (73238 bytes, sha256
   b2b7fab711787f32ea40a1e0920846c57427786614b3071097a84ba46c0a926e). E uma
   NOTICIA de 10/04/2019 ("Localizacao dos radares sera divulgada mensalmente
   no site da Prefeitura"). Ela descreve que Teresina tem dois tipos de radar
   ("fixos" e "estaticos"), cita o diretor da Strans (Jose Falcao) e afirma que
   "a lista com a localizacao dos radares sera divulgada mensalmente" e podera
   ser acessada no site da Prefeitura, em "Links Importantes", na aba
   "Localizacao de Radares". A noticia NAO traz a lista: ela apenas ANUNCIA o
   canal. Nao ha CSV/JSON/KML/GeoJSON.

   Fontes atuais verificadas em 10/10/2026: a STRANS
   (https://strans.teresina.pi.gov.br/) NAO respondeu (falha de conexao); o
   portal atual da Prefeitura (https://www.teresina.pi.gov.br/, HTTP 200) e o
   DER-PI (https://www.der.pi.gov.br/, HTTP 200) NAO publicam relacao de
   equipamentos. Ou seja: o unico registro publico localizado e HISTORICO
   (2019).

CLASSIFICACAO/TRATAMENTO: e uma noticia HISTORICA (2019) que ANUNCIA a
divulgacao da lista (sem publica-la), SEM coordenadas, SEM identificadores e
SEM vigencia confirmada. Conforme a regra "trecho/local de operacao nunca vira
radar instalado confirmado", `normalizar` devolve None. Motivo registrado:
`pendente_lai` (dado atual depende de pedido LAI a STRANS/DER-PI). Nada e
inventado; o conector apenas DOCUMENTA a evidencia.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = ("https://antigo.pmt.pi.gov.br/2019/04/10/"
          "localizacao-dos-radares-sera-divulgada-mensalmente-no-site-da-"
          "prefeitura/")
DER_PI = "https://www.der.pi.gov.br/"
PMT_ATUAL = "https://www.teresina.pi.gov.br/"

MOTIVO = "pendente_lai"

_CHAVE_TIPO = (("estatic", "estatico"), ("fix", "fixo"))

_MESES = {
    "janeiro": "01", "fevereiro": "02", "marco": "03", "março": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10", "novembro": "11",
    "dezembro": "12",
}

_RE_DATA = re.compile(
    r"\b(\d{1,2})\s+de\s+([A-Za-z\u00c0-\u00ff]+)\s+de\s+(\d{4})\b")


def _texto(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                 flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'"))
    return " ".join(txt.split())


class ColetorTeresinaPI(ColetorBase):

    FONTE = {
        "nome": "STRANS Teresina - Localizacao de radares (noticia 2019)",
        "organizacao": "STRANS Teresina / DER-PI",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": PMT_ATUAL,
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "noticia historica anunciando divulgacao da lista (2019)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # noticia historica; dado atual depende de LAI (STRANS/DER-PI)
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA
    DER_PI = DER_PI
    PMT_ATUAL = PMT_ATUAL
    MOTIVO = MOTIVO

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Lista recursos linkados (PDFs/imagens), com papel heurístico.

        A noticia NAO publica a lista de locais nem dataset; apenas anuncia que
        ela ficara no site. No maximo ha imagens/links institucionais.
        """
        if isinstance(html, bytes):
            html = html.decode("utf-8", "replace")
        out = []
        vistos = set()
        pad = r'(?:src|href)="([^"]+\.(?:pdf|png|jpg|jpeg|csv|json|geojson|' \
              r'kml|kmz|xls|xlsx|ods))"'
        for m in re.finditer(pad, html or "", re.I):
            href = m.group(1)
            url = urllib.parse.urljoin(cls.PAGINA, href)
            if url in vistos:
                continue
            vistos.add(url)
            tipo = _tipo_recurso(url)
            out.append({
                "url": url,
                "tipo": tipo,
                "legivel_por_stdlib": not tipo.startswith(
                    ("imagem", "planilha", "binario")),
            })
        return out

    @classmethod
    def evidencia(cls, html):
        """Resumo verificavel do que a noticia declara (sem inventar GPS)."""
        texto = _texto(html)
        md = _RE_DATA.search(texto)
        data = None
        if md:
            mes = _MESES.get(md.group(2).lower(), "00")
            data = "%s-%s-%s" % (md.group(3), mes, md.group(1).zfill(2))
        tipos = []
        for prefixo, canonico in _CHAVE_TIPO:
            if re.search(r"\b%s" % prefixo, texto, re.I):
                tipos.append(canonico)
        return {
            "url_pagina": cls.PAGINA,
            "data_publicacao": data,
            "tipos_radares_citados": tipos or None,
            "anuncia_divulgacao_mensal": bool(
                re.search(r"divulga[^.]{0,40}mensal", texto, re.I)),
            "aponta_aba_localizacao_radares": bool(
                re.search(r"localiza[çc][aã]o\s+de\s+radares", texto, re.I)),
            "publica_lista_na_pagina": bool(
                re.search(r"(?:lista|rela[çc][aã]o)[^.]{0,30}radar[^.]{0,30}"
                          r"(?:rua|avenida|km|rodovia|bairro)", texto, re.I)),
            "tem_dataset_estruturado": bool(
                re.search(r'href="[^"]+\.(?:csv|json|geojson|kml|kmz|ods|'
                          r'xlsx?)"', html or "", re.I)),
            "motivo": cls.MOTIVO,
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
        ev = self.evidencia(html)
        registro = {
            "url_pagina": ev["url_pagina"],
            "data_publicacao": ev["data_publicacao"],
            "tipos_radares_citados": ev["tipos_radares_citados"],
            "anuncia_divulgacao_mensal": ev["anuncia_divulgacao_mensal"],
            "aponta_aba_localizacao_radares":
                ev["aponta_aba_localizacao_radares"],
            "publica_lista_na_pagina": ev["publica_lista_na_pagina"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "motivo": ev["motivo"],
            "recursos": self.descobrir_recursos(html),
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Noticia historica que ANUNCIA a lista NAO vira radar.

        A pagina nao contem a relacao de equipamentos (apenas anuncia que ela
        ficara no site), sem coordenadas, identificadores nem vigencia
        confirmada. Converter "local de operacao"/anuncio em radar instalado
        violaria a regra de ouro. Nada e inventado: None.
        """
        return None


def _tipo_recurso(url):
    s = (url or "").lower()
    if s.endswith(".pdf"):
        return "documento_pdf"
    if re.search(r"\.(?:png|jpg|jpeg)$", s):
        return "imagem"
    if re.search(r"\.(?:csv|json|geojson|kml|kmz|xlsx?|ods)$", s):
        return "planilha"
    return "binario"
