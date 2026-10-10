# -*- coding: utf-8 -*-
"""Fonte AL - DER-AL (canal institucional, sem publicacao de lista).

Pagina de entrada (catalogo, classificacao_evidencia="institucional_sem_lista"):
    https://alagoasdigital.al.gov.br/orgao/49

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (43169 bytes, sha256
   0f29a802e59c0b8ea89f2a7de241d44ae3bb0312e8275db8e67123bddb0c2599). A pagina
   e o CANAL INSTITUCIONAL do DER-AL (Departamento de Estradas de Rodagem de
   Alagoas) no portal Alagoas Digital: descreve competencia ("rodovias
   estaduais sao por ele fiscalizadas"), compromissos de qualidade e os
   servicos/contatos (Protocolo Geral do DER, Secao de Processamento de Multas
   e Divisao de Faixa de Dominio). NAO publica relacao de radares/lombadas,
   nem documento com localizacao de equipamentos, nem dataset (CSV/JSON/KML).

   O dominio proprio do orgao (https://www.der.al.gov.br/) NAO respondeu em
   10/10/2026 (falha de conexao / sem TLS util). O DMT de Maceio
   (https://maceio.al.gov.br/secretarias-e-orgaos/dmtt) tambem e apenas
   institucional (define atribuicoes; sem lista de equipamentos) e cobre
   somente a capital, nao o estado.

CLASSIFICACAO/TRATAMENTO: nao ha publicacao de lista. Fonte apenas
institucional -> `sem_publicacao`; a relacao de equipamentos depende de
pedido LAI / contato institucional com DER-AL (e/ou DMT Maceio para a
capital). Nada e convertido em ponto (`normalizar` devolve None): nada
inventado. O conector apenas DOCUMENTA a evidencia.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = "https://alagoasdigital.al.gov.br/orgao/49"
URL_INSTITUCIONAL = "https://www.der.al.gov.br/"
DMT_MACEIO = "https://maceio.al.gov.br/secretarias-e-orgaos/dmtt"

MOTIVO = "sem_publicacao"


def _texto(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                 flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'"))
    return " ".join(txt.split())


class ColetorDerAL(ColetorBase):

    FONTE = {
        "nome": "DER-AL - canal institucional (sem lista de equipamentos)",
        "organizacao": "DER-AL / DMT Maceio",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": URL_INSTITUCIONAL,
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "canal institucional DER-AL (sem publicacao de lista)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # nao ha lista publicada -> depende de LAI/contato institucional
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA
    URL_INSTITUCIONAL = URL_INSTITUCIONAL
    DMT_MACEIO = DMT_MACEIO
    MOTIVO = MOTIVO

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Lista recursos linkados (PDFs/imagens) na pagina institucional.

        A pagina NAO publica relacao de equipamentos: no maximo documentos
        institucionais. Sem dataset de localizacao.
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
        """Resumo verificavel do que a pagina de fato publica (sem GPS)."""
        texto = _texto(html)
        return {
            "url_pagina": cls.PAGINA,
            "orgao_identificado": bool(
                re.search(r"Departamento de Estradas de Rodagem", texto, re.I)),
            "fiscaliza_rodovias_estaduais": bool(
                re.search(r"rodovias\s+estaduais[^.]{0,40}fiscalizad", texto,
                          re.I)
                or re.search(r"fiscalizad[^.]{0,40}rodovias\s+estaduais",
                             texto, re.I)),
            "publica_lista_equipamentos": bool(
                re.search(r"(?:lista|rela[cç][aã]o|cadastro)[^.]{0,40}"
                          r"(?:radar|lombada|equipament|velocidad)", texto,
                          re.I)),
            "tem_dataset_estruturado": bool(
                re.search(r'href="[^"]+\.(?:csv|json|geojson|kml|kmz|ods|'
                          r'xlsx?)"', html or "", re.I)),
            "fonte_municipal_maceio": cls.DMT_MACEIO,
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
            "orgao_identificado": ev["orgao_identificado"],
            "fiscaliza_rodovias_estaduais": ev["fiscaliza_rodovias_estaduais"],
            "publica_lista_equipamentos": ev["publica_lista_equipamentos"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "fonte_municipal_maceio": ev["fonte_municipal_maceio"],
            "motivo": ev["motivo"],
            "recursos": self.descobrir_recursos(html),
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Canal institucional SEM lista NAO vira radar.

        Nao ha relacao de equipamentos publicada (nem dataset); a fonte apenas
        descreve competencias/servicos do orgao. Converter texto institucional
        em radar instalado violaria a regra de ouro. Nada e inventado: None.
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
