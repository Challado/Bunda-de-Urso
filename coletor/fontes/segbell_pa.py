# -*- coding: utf-8 -*-
"""Fonte PA - SEGBEL Belem, portarias de ativacao/desativacao de radares.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://seguranca.belem.pa.gov.br/portarias-de-ativacao-e-desativacao-de-radares/

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  A pagina publica uma LISTA DE DOCUMENTOS (oito portarias de 2022 da
  SEMOB/SEGBEL Belem, cada uma um PDF) mais um "Mapa de Radares" (PDF de
  2020). Cada portaria DESATIVA ou INSTALA/ATIVA um lote de radares:
    - Portaria 0473/2022 - Instalacao/Ativacao - Perkons - 1o Lote
    - Portaria 0510/2022 - Desativacao - Fiscaltech
    - Portaria 0512/2022 - Ativacao - Perkons
    - Portaria 0534/2022 - Desativacao - Fiscaltech
    - Portaria 0536/2022 - Desativacao - Fiscaltech
    - Portaria 0537/2022 - Instalacao/Ativacao - Perkons - 3o Lote
    - Portaria 0666/2022 - Desativacao - Fiscaltech
    - Portaria 0677/2022 - Ativacao - Perkons - 4o Lote

  Os PDFs de portaria CONTEM tabelas de equipamentos (numero de serie,
  codigo SEMOB, endereco, as vezes velocidade maxima). MAS a pagina NAO
  publica um cadastro consolidado e vigente de radares.

CLASSIFICACAO/TRATAMENTO: o que existe de estruturado aqui e o proprio ato
administrativo (ativacao / desativacao / instalacao), com numero, data,
operadora e lote. A especificacao v1.1 NAO possui entidade de destino para
"ato/portaria de ativacao/desativacao" (as tabelas cobrem ponto,
equipamento, trecho, documento de ponto e verificacao metrologica). Por
isso o conector DESCOBRE e CLASSIFICA os documentos e NUNCA converte a
listagem de equipamentos de dentro de uma portaria em cadastro: seria
"cadastro inventado". `normalizar` devolve None (nada e inventado).

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re
import urllib.parse

from coletor import http
from coletor.base import ColetorBase

MIME_HTML = "text/html; charset=utf-8"

PAGINA = ("https://seguranca.belem.pa.gov.br/"
          "portarias-de-ativacao-e-desativacao-de-radares/")

_RE_NUMERO = re.compile(r"Portaria\s*N[ºo°]?\s*(\d+)\s*/\s*(\d{4})", re.I)
_RE_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_LOTE = re.compile(r"(\d)\s*[ºo°]?\s*LOTE", re.I)
_OPERADORAS = ("Perkons", "Fiscaltech", "Fiscal Tech")


def _operadora(texto):
    t = (texto or "").lower()
    for nome in _OPERADORAS:
        if nome.lower() in t or nome.lower().replace(" ", "") in \
                t.replace(" ", ""):
            return nome
    return None


def _acao(texto):
    t = (texto or "").lower()
    if "desativ" in t:
        return "desativacao"
    if "ativ" in t or "instala" in t:
        return "ativacao"
    return "documento"


_RE_AFERICAO = re.compile(r"(?:R\d{4,5}|FSC\w*)[-_ ]?CE[MV]?\d{2,3}", re.I)


def _tipo_documento(titulo, url):
    s = "%s %s" % (titulo or "", url or "")
    if re.search(r"(?i)mapa", s):
        return "mapa_radares"
    if _RE_AFERICAO.search(s):
        return "certificado_afericao"
    return "documento"


class ColetorSEGBELPA(ColetorBase):

    FONTE = {
        "nome": ("SEGBEL Belem - Portarias de ativacao e desativacao de "
                 "radares"),
        "organizacao": ("Secretaria Municipal de Seguranca e Coordenacao "
                        "Municipal (SEGBEL) - Belem/PA"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://seguranca.belem.pa.gov.br/",
        "documentacao_url": PAGINA,
        "licenca": "documento oficial publicado",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Portarias de ativacao/desativacao de radares (lista de PDFs)",
        "url_recurso": PAGINA,
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,    # ~30 dias (verificacao)
        # so atos administrativos (ativacao/desativacao); sem cadastro
        # consolidado e sem entidade de destino para o ato -> pendente.
        "status_integracao": "pendente",
    }

    PAGINA = PAGINA

    @classmethod
    def resolver_url(cls):
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_documentos(cls, html):
        """Lista (verbo->registro) das portarias e do mapa publicados."""
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
            titulo = re.sub(r"\[novo\]\s*$", "", titulo, flags=re.I).strip()
            out.append(cls._registro_documento(url, titulo, href))
        return out

    @classmethod
    def _registro_documento(cls, url, titulo, href):
        if not re.search(r"(?i)portaria", titulo or ""):
            return {
                "url": url,
                "titulo": titulo or None,
                "tipo": _tipo_documento(titulo, url),
                "acao": None,
                "numero": None,
                "ano": None,
                "operadora": None,
                "lote": None,
                "data_publicacao": None,
            }
        mn = _RE_NUMERO.search(titulo or "")
        numero = mn.group(1) if mn else None
        ano = mn.group(2) if mn else None
        if ano is None:
            m4 = re.search(r"/(\d{4})/", url or "")
            ano = m4.group(1) if m4 else None
        md = _RE_DATA.search(titulo or "")
        data = ("%s-%s-%s" % (md.group(3), md.group(2).zfill(2),
                              md.group(1).zfill(2))) if md else None
        ml = _RE_LOTE.search(titulo or "")
        return {
            "url": url,
            "titulo": titulo or None,
            "tipo": "portaria",
            "acao": _acao("%s %s" % (titulo or "", href or "")),
            "numero": numero,
            "ano": ano,
            "operadora": _operadora("%s %s" % (titulo or "", href or "")),
            "lote": (ml.group(1) + "o") if ml else None,
            "data_publicacao": data,
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
        return (conteudo, ".html", MIME_HTML,
                self.descobrir_documentos(html))

    def identificador(self, raw):
        if raw.get("numero") and raw.get("ano"):
            return "Portaria %s/%s" % (raw["numero"], raw["ano"])
        return raw.get("url")

    # -- normalizar -------------------------------------------------------
    def normalizar(self, idx, raw):
        """ATO administrativo (ativacao/desativacao) nao vira radar.

        A especificacao v1.1 nao tem entidade para portaria de
        ativacao/desativacao; a listagem de equipamentos de dentro de uma
        portaria NAO e transposta para cadastro (seria "cadastro
        inventado"). O documento fica preservado como evidencia bruta
        (REGISTRO_FONTE). Devolver None mantem a regra "ausente = NULL;
        nao confirmavel = a confirmar".
        """
        return None
