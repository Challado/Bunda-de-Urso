# -*- coding: utf-8 -*-
"""Mapa oficial da STRANS Teresina e leitura dos artefatos históricos.

O leitor atual descobre o KML do mapa na página da Prefeitura. O leitor
histórico preserva a interpretação da notícia de 2019 que anunciava a lista.
"""
from html import unescape
from pathlib import Path
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes.cariacica_es import ColetorCariacica, MIME_KML, _parse_coords
from coletor.fontes.documental import ColetorDocumental

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


class ColetorTeresinaHistorico(ColetorDocumental):

    MARCADORES_DOCUMENTAIS = ('teresina', 'radar')
    DESCRICAO_COLETA = 'Notícia histórica da STRANS Teresina; cadastro atual pendente.'

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


class ColetorTeresinaPI(ColetorBase):
    """Lê os pontos do mapa publicado pela STRANS na página da Prefeitura."""

    PAGINA = "https://www.teresina.pi.gov.br/strans/localizacao-de-radares/"
    FONTE = {
        "nome": "STRANS Teresina - Localizacao de radares",
        "organizacao": "STRANS Teresina",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.teresina.pi.gov.br/strans/",
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Mapa de fiscalizacao eletronica (KML)",
        "url_recurso": PAGINA,
        "formato_origem": "kml",
        "periodicidade_segundos": 604800,
        "status_integracao": "ok",
    }

    _KML = {"k": "http://www.opengis.net/kml/2.2"}
    _IFRAME = re.compile(r"""<iframe\b[^>]*\ssrc\s*=\s*(['"])(.*?)\1""", re.I | re.S)

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    @classmethod
    def _url_kml(cls, pagina):
        for _, url in cls._IFRAME.findall(pagina.decode("utf-8", "replace")):
            partes = urllib.parse.urlsplit(unescape(url))
            if partes.scheme != "https" or partes.netloc != "www.google.com":
                continue
            if not re.fullmatch(r"/maps/d/(?:u/\d+/)?embed", partes.path):
                continue
            mid = urllib.parse.parse_qs(partes.query).get("mid", [""])[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{15,100}", mid):
                return ColetorCariacica.URL_KML % mid
        raise http.ErroFonte("A página da STRANS não publicou o mapa de radares em Google My Maps.")

    @classmethod
    def _registros(cls, conteudo):
        if b"<!DOCTYPE" in conteudo.upper():
            raise http.ErroFonte("KML da STRANS com DOCTYPE não permitido.")
        try:
            raiz = ET.fromstring(conteudo)
        except ET.ParseError as exc:
            raise http.ErroFonte("KML inválido da STRANS.") from exc
        nome_mapa = raiz.findtext("k:Document/k:name", "", cls._KML)
        if "strans" not in nome_mapa.casefold():
            raise http.ErroFonte("O KML publicado não foi identificado como o mapa da STRANS.")
        registros = []
        for ponto in raiz.findall(".//k:Placemark", cls._KML):
            titulo = ponto.findtext("k:name", "", cls._KML)
            linhas = [linha.strip().removeprefix("-").strip()
                      for linha in titulo.splitlines() if linha.strip()]
            lat, lon = _parse_coords(ponto.findtext("k:Point/k:coordinates", namespaces=cls._KML))
            registros.append({
                "codigo": linhas[0] if linhas else None,
                "endereco": linhas[1] if len(linhas) >= 2 else None,
                "latitude": lat,
                "longitude": lon,
                "detalhes": linhas[2:],
                "descricao": ponto.findtext("k:description", "", cls._KML).strip(),
            })
        if not registros:
            raise http.ErroFonte("O mapa da STRANS não trouxe marcações de equipamentos.")
        return registros

    def carregar(self, origem):
        if origem and Path(origem).is_file():
            conteudo = Path(origem).read_bytes()
        else:
            url = origem or self.PAGINA
            partes = urllib.parse.urlsplit(url)
            if partes.netloc != "www.google.com" or partes.path != "/maps/d/kml":
                url = self._url_kml(http.baixar(url)[0])
            conteudo = http.baixar(url)[0]
        return conteudo, ".kml", MIME_KML, self._registros(conteudo)

    def identificador(self, raw):
        return raw["codigo"]

    def normalizar(self, idx, raw):
        codigo = raw["codigo"]
        if (not re.fullmatch(r"T[A-Z0-9]*\d[A-Z0-9]*", codigo or "", re.I)
                or not raw["endereco"] or raw["latitude"] is None or raw["longitude"] is None):
            raise ValueError("Marcação da STRANS sem código, endereço ou coordenada de ponto.")
        detalhes = [linha for linha in raw["detalhes"] if linha]
        sentidos = set()
        for linha in detalhes:
            sentido = re.fullmatch(
                r"(NORTE|SUL|LESTE|OESTE)\s*[-/]\s*(NORTE|SUL|LESTE|OESTE)"
                r"(?:\s+(?:FAIXA\s*)?\d*\s*)?", linha, re.I)
            if sentido:
                sentidos.add(" - ".join(sentido.groups()).upper())
        sentido_original = " / ".join(sorted(sentidos)) or None
        descricao = raw["descricao"]
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": codigo.upper(),
            "tipo_identificador": "codigo_equipamento",
            "latitude": raw["latitude"],
            "longitude": raw["longitude"],
            "qualidade": "oficial",
            "metodo_obtencao": "Mapa oficial da STRANS Teresina (KML)",
            "uf": "PI",
            "municipio_nome": "Teresina",
            "municipio_ibge": "2211001",
            "via_codigo": raw["endereco"],
            "via_tipo": "municipal",
            "sentido": nz.normalizar_sentido(sentido_original),
            "sentido_original": sentido_original,
            "situacao": "inativo" if "furtado" in descricao.casefold() else None,
            "observacoes": " · ".join(filter(None, (descricao, *detalhes))) or None,
        }
