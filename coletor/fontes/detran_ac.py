# -*- coding: utf-8 -*-
"""Fonte AC - Detran-AC / DERACRE (portal institucional, sem cadastro atual).

Pagina de entrada (catalogo, classificacao_evidencia="institucional_sem_lista"):
    https://www.detran.ac.gov.br/

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):
   HTTP 200, text/html; charset=UTF-8 (232212 bytes, sha256
   9345c18b345c0320ae256a843ef5a62a687d0d8401168dfa2114d4d21434bf89). O portal
   do Detran-AC publica apenas SERVICOS institucionais e de consulta. Os unicos
   itens relacionados a fiscalizacao eletronica sao servicos de CONSULTA de
   autos ja lavrados ("Consulta de Imagens de autos de radar") e a pagina de
   "Convenios de Fiscalizacao de Transito"
   (https://www.detran.ac.gov.br/infracoes-multas/convenios-de-fiscalizacao-
   de-transito/ , HTTP 200, 213663 bytes, sha256 751853ba51ffc594...) — que
   trata de acordos de fiscalizacao, NAO de um cadastro de equipamentos.

   O UNICO registro publico conhecido de equipamentos e HISTORICO: a materia de
   2013 da agencia de noticias do estado
   (https://agencia.ac.gov.br/detran-anuncia-retorno-da-fiscalizacao-
   eletronica/). Em 10/10/2026 essa URL responde HTTP 503 com uma pagina
   "Portal temporariamente fora do ar" (portal em manutencao), portanto NAO e
   fonte consultavel; e, mesmo quando no ar, e uma noticia de 2013 que NAO
   comprova operacao/cadastro em 2026.

CLASSIFICACAO/TRATAMENTO: nao ha publicacao ESTRUTURADA de cadastro de
equipamentos (CSV/JSON/KML/GeoJSON) nem lista tabular; so ha dado historico
(2013) e servicos de consulta. Conforme a regra "campo ausente = NULL; nao
confirmavel = a confirmar" e "trecho/local de operacao nunca vira radar
instalado confirmado", nada e convertido em ponto: `normalizar` devolve None.
Motivo registrado: `pendente_lai` (dado atual depende de pedido LAI ao
Detran-AC / DERACRE). O conector apenas DOCUMENTA a evidencia.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = "https://www.detran.ac.gov.br/"
CONVENIOS = ("https://www.detran.ac.gov.br/infracoes-multas/"
             "convenios-de-fiscalizacao-de-transito/")
NOTICIA_HISTORICA = ("https://agencia.ac.gov.br/"
                     "detran-anuncia-retorno-da-fiscalizacao-eletronica/")

MOTIVO = "pendente_lai"


def _texto(html):
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "",
                 flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&quot;", '"').replace("&#39;", "'"))
    return " ".join(txt.split())


class ColetorDetranAC(ColetorBase):

    FONTE = {
        "nome": "Detran-AC - portal institucional (sem cadastro de radares)",
        "organizacao": "Detran-AC / DERACRE",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.detran.ac.gov.br/",
        "documentacao_url": PAGINA,
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "portal institucional Detran-AC (sem lista de equipamentos)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # somente dado historico (2013) -> dado atual depende de LAI
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA
    CONVENIOS = CONVENIOS
    NOTICIA_HISTORICA = NOTICIA_HISTORICA
    MOTIVO = MOTIVO

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Lista recursos linkados (PDFs/imagens), com papel heurístico.

        O portal NAO publica cadastro: no maximo servicos de consulta e
        convenios. Nao ha dataset de localizacao de equipamentos.
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
            "publica_consulta_de_autos_radar": bool(
                re.search(r"consulta\s+de\s+imagens\s+de\s+autos\s+de\s+radar",
                          texto, re.I)),
            "publica_convenios_fiscalizacao": bool(
                re.search(r"conv[eê]nio[s]?\s+de\s+fiscaliza[çc][aã]o", texto,
                          re.I)),
            "tem_cadastro_equipamentos": bool(
                re.search(r"(?:cadastro|lista)[^.]{0,40}radar", texto, re.I)),
            "tem_dataset_estruturado": bool(
                re.search(r'href="[^"]+\.(?:csv|json|geojson|kml|kmz|ods|'
                          r'xlsx?)"', html or "", re.I)),
            "referencia_historica": cls.NOTICIA_HISTORICA,
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
            "publica_consulta_de_autos_radar":
                ev["publica_consulta_de_autos_radar"],
            "publica_convenios_fiscalizacao":
                ev["publica_convenios_fiscalizacao"],
            "tem_cadastro_equipamentos": ev["tem_cadastro_equipamentos"],
            "tem_dataset_estruturado": ev["tem_dataset_estruturado"],
            "referencia_historica": ev["referencia_historica"],
            "motivo": ev["motivo"],
            "recursos": self.descobrir_recursos(html),
        }
        return (conteudo, ".html", MIME_HTML, [registro])

    def identificador(self, raw):
        return raw.get("url_pagina")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """Portal institucional SEM cadastro NAO vira radar.

        Nao ha relacao de equipamentos (apenas servicos de consulta e
        convenios) e o unico registro publico e historico (2013), sem
        coordenadas/identificadores/vigencia. Converter "servico/noticia" em
        radar instalado violaria a regra de ouro. Nada e inventado: None.
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
