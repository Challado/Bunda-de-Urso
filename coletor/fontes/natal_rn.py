# -*- coding: utf-8 -*-
"""Fonte RN - STTU Natal (portal institucional; sem cadastro ESTADUAL).

Pagina de entrada (catalogo, classificacao_evidencia="institucional_sem_lista"):
    https://www.natal.rn.gov.br/sttu

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (89706 bytes, sha256
   74e25fd88e756fa21a2f7b4a6273604021ab7ea06bc86f2a73bed7cf91491aef). A pagina
   e o portal da STTU (Secretaria Municipal de Mobilidade Urbana de Natal):
   informacao institucional, CMtMU, servicos de transito e documentos.

   NAO existe publicacao ESTRUTURADA de cadastro para o ESTADO: o DER-RN
   (https://www.der.rn.gov.br/) respondeu HTTP 503 em 10/10/2026. A unica
   publicacao encontrada e MUNICIPAL (Natal) e documental: a subpagina
   https://www.natal.rn.gov.br/sttu/equipamentos ("Equipamentos de
   Fiscalizacao Eletronica", HTTP 200, 88435 bytes) relaciona PDFs por
   equipamento (lombadas eletronicas, radares e radares nos cruzamentos),
   inclusive um "levantamento-tecnico". Sao documentos tecnicos avulsos (nao
   legiveis como dataset pela stdlib), restritos a capital — NAO cobrem o
   estado e NAO sao cadastro maquina-legivel.

CLASSIFICACAO/TRATAMENTO: para fins de cobertura ESTADUAL nao ha publicacao
de lista -> `sem_publicacao`; a relacao de equipamentos depende de pedido
LAI/contato a STTU (Natal) e ao DER-RN. Nenhum local de documento vira ponto:
`normalizar` devolve None (a regra "estudo tecnico nunca vira radar instalado
confirmado" e "campo ausente = NULL" se aplicam). Nada e inventado; o conector
apenas DOCUMENTA a evidencia.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = "https://www.natal.rn.gov.br/sttu"
EQUIPAMENTOS = "https://www.natal.rn.gov.br/sttu/equipamentos"
DER_RN = "https://www.der.rn.gov.br/"

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


class ColetorNatalRN(ColetorBase):

    FONTE = {
        "nome": "STTU Natal - portal institucional (sem cadastro estadual)",
        "organizacao": "STTU Natal / DER-RN",
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.natal.rn.gov.br/sttu",
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "portal STTU Natal (sem cadastro estadual de equipamentos)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # sem cadastro de lista para o estado -> LAI/contato institucional
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA
    EQUIPAMENTOS = EQUIPAMENTOS
    DER_RN = DER_RN
    MOTIVO = MOTIVO

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Lista recursos linkados (PDFs/imagens), com papel heurístico.

        O portal institucional NAO publica cadastro; ele APONTA para a
        subpagina municipal de equipamentos (documentos PDF por equipamento).
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
        """Resumo verificavel do que o portal de fato publica (sem GPS)."""
        texto = _texto(html)
        return {
            "url_pagina": cls.PAGINA,
            "link_equipamentos_municipal": bool(
                re.search(r'(?:href)="[^"]*/sttu/equipamentos"', html or "",
                          re.I)
                or re.search(r"equipamentos?\s+de\s+fiscaliza[çc][aã]o\s+"
                             r"eletr[oô]nica", texto, re.I)),
            "publica_cadastro_estadual": bool(
                re.search(r"(?:cadastro|lista)[^.]{0,40}radar[^.]{0,40}"
                          r"estadual", texto, re.I)),
            "tem_dataset_estruturado": bool(
                re.search(r'href="[^"]+\.(?:csv|json|geojson|kml|kmz|ods|'
                          r'xlsx?)"', html or "", re.I)),
            "fonte_municipal_equipamentos": cls.EQUIPAMENTOS,
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
            "link_equipamentos_municipal": ev["link_equipamentos_municipal"],
            "publica_cadastro_estadual": ev["publica_cadastro_estadual"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "fonte_municipal_equipamentos":
                ev["fonte_municipal_equipamentos"],
            "motivo": ev["motivo"],
            "recursos": self.descobrir_recursos(html),
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Portal institucional / documentos municipais NAO viram radar.

        Nao ha cadastro estruturado de equipamentos para o ESTADO (DER-RN em
        503); o que existe e municipal (Natal) e documental (PDFs tecnicos
        avulsos, sem coordenadas/tabular). Converter documento/portal em radar
        instalado violaria a regra de ouro. Nada e inventado: None.
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
