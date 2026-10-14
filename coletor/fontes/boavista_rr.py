# -*- coding: utf-8 -*-
"""Fonte RR - Boa Vista/SMST, pagina de noticia (historica, 2024).

Pagina de entrada (catalogo, classificacao_evidencia=
"lista_localizacao_historica"):
    https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-novos-
    equipamentos-de-fiscalizacao-eletronica-para-reduzir-acidentes-em-boa-vista

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (38567 bytes). A pagina e uma NOTICIA
   de 2024 da Prefeitura de Boa Vista / SMST: relata a instalacao de "8 novos
   equipamentos" entre dezembro/2023 e janeiro/2024, elevando a capital a um
   "total de 18 radares". A lista dos locais NAO esta em texto: aparece
   imediatamente apos "Veja onde os novos radares estao instalados:" apenas
   como IMAGEM (`https://boavista.rr.gov.br/storage/2024/radar.png`,
   HTTP 200, 35095 bytes, 1132x556). O texto cita de passagem duas vias
   (Avenida Brasil / bairro Sao Bento e Avenida Carlos Pereira de Melo,
   proximo ao Igarape Carana).

CLASSIFICACAO/TRATAMENTO: noticia HISTORICA (2024), com locais publicados
apenas em figura, SEM coordenadas, SEM identificadores e SEM vigencia
confirmada. A biblioteca padrao do Python NAO le o conteudo da imagem
(raster). A regra de ouro ("trecho/local de operacao nunca vira radar
instalado confirmado") impede converter a noticia em cadastro; nao existe
recurso estruturado (CSV/JSON/KML/GeoJSON). Por isso `normalizar` devolve
None: nada e inventado. O conector DOCUMENTA a evidencia (data, contagens
declaradas, imagens/recursos) -> status PENDENTE.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = ("https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-"
          "novos-equipamentos-de-fiscalizacao-eletronica-para-reduzir-"
          "acidentes-em-boa-vista")

_RE_TOTAL = re.compile(r"total\s+de\s+(\d+)\s+radares", re.I)
_RE_NOVOS = re.compile(r"(\d+)\s+novos?\s+(?:equipamentos?|radares?)", re.I)


def _texto(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                 flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'"))
    return " ".join(txt.split())


class ColetorBoaVistaRR(ColetorBase):

    FONTE = {
        "nome": "Boa Vista SMST - Locais de radares (noticia 2024)",
        "organizacao": "Prefeitura Municipal de Boa Vista / SMST",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://boavista.rr.gov.br/",
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "noticia historica sobre instalacao de radares (2024)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # listagem de locais publicada apenas em imagem -> pendente
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Lista recursos linkados (imagens/PDFs), com papel heurístico.

        A relacao de locais e uma IMAGEM (`radar.png`); nao ha dataset.
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
            out.append({
                "url": url,
                "tipo": _tipo_recurso(url),
                "legivel_por_stdlib": not _tipo_recurso(url).startswith(
                    ("imagem", "planilha", "binario")),
            })
        return out

    @classmethod
    def evidencia(cls, html):
        """Resumo verificavel do que a noticia declara (sem inventar GPS)."""
        txt = _texto(html)
        mt = _RE_TOTAL.search(txt)
        mn = _RE_NOVOS.search(txt)
        recursos = cls.descobrir_recursos(html)
        return {
            "total_radares_declarado": int(mt.group(1)) if mt else None,
            "novos_equipamentos_declarado": int(mn.group(1)) if mn else None,
            "lista_em_imagem": any(r["tipo"] == "imagem_localizacao"
                                   for r in recursos),
            "tem_dataset_estruturado": bool(
                re.search(r'(?:src|href)="[^"]+\.(?:csv|json|geojson|kml|kmz|'
                          r'ods|xlsx?)"', html or "", re.I)),
            "recursos": recursos,
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
            "url_pagina": self.PAGINA,
            "total_radares_declarado": ev["total_radares_declarado"],
            "novos_equipamentos_declarado":
                ev["novos_equipamentos_declarado"],
            "lista_em_imagem": ev["lista_em_imagem"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "recursos": ev["recursos"],
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Noticia historica com locais apenas em imagem NAO vira radar.

        Sem coordenadas, sem identificadores, sem vigencia confirmada e com a
        relacao de locais apenas numa figura (ilegivel pela stdlib). Converter
        "local de operacao" em radar instalado confirmado violaria a regra de
        ouro. Nada e inventado: devolve None.
        """
        return None


def _tipo_recurso(url):
    s = (url or "").lower()
    if re.search(r"radar\.(?:png|jpg|jpeg)$", s) or re.search(
            r"radares?[-_/]", s):
        return "imagem_localizacao"
    if re.search(r"\.(?:png|jpg|jpeg)$", s):
        return "imagem"
    if s.endswith(".pdf"):
        return "documento_pdf"
    if re.search(r"\.(?:csv|json|geojson|kml|kmz|xlsx?|ods)$", s):
        return "planilha"
    return "binario"
