# -*- coding: utf-8 -*-
"""Fonte F17 - DAER-RS, locais de fiscalizacao com radar PORTATIL.

Pagina de entrada (catalogo): https://www.daer.rs.gov.br/radares-moveis

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  https://www.daer.rs.gov.br/radares-moveis  ->  HTTP 200, text/html.
  A pagina NAO publica a lista em si: ela cita a Resolucao CONTRAN 798/2020 e
  aponta para o Comando Rodoviario da Brigada Militar (CRBM/CPRv BM):
      <a href="https://crbm.bm.rs.gov.br/radar-movel">Confira a localizacao
      dos radares moveis</a>, atualizada sempre as tercas-feiras.

  https://crbm.bm.rs.gov.br/radar-movel  ->  301/redirect ->
  https://cprvbm.rs.gov.br/radar-movel  (HTTP 200).  A pagina traz os botoes
  "1o/2o/3o BPRv BM" e "Lista de Equipamentos"; os pontos de fiscalizacao sao
  planilhas publicadas no Google Sheets (export?format=pdf).  O MESMO ID de
  planilha pode ser exportado em CSV pela propria publicacao, e esse CSV traz
  o cabecalho:
      No ord, Fracao fiscalizadora, Rodovia, Km inicial, Km final,
      Perimetro, Velocidade regulamentada
  e o periodo de vigencia ("Periodo: De 1o a 31 de outubro de 2026.").

FILTRO: cada linha e um TRECHO/LOCAL elegivel para fiscalizacao com medidor
PORTATIL (rodovia + km inicial/final). NUNCA e radar fixo instalado nem
operacao pontual confirmada -> TRECHO_ELEGIVEL com
``radar_instalado_confirmado = None``.

A URL das planilhas e DESCOBERTA na pagina oficial (nunca chumbada). Aceita
arquivo LOCAL (CSV de fixture) e lista de URLs para testes offline.
"""
import csv
import io
import os
import re
import unicodedata
import urllib.parse

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


def _norm(texto):
    t = unicodedata.normalize("NFD", (texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip().upper()


def _extrair_ids_planilha(html):
    """IDs de Google Sheets referenciados na pagina, sem repetir."""
    ids = []
    for m in re.finditer(
            r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})", html):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _url_csv(id_planilha):
    return ("https://docs.google.com/spreadsheets/d/%s/export?format=csv"
            % id_planilha)


class ColetorDAERRS(ColetorBase):

    FONTE = {
        "nome": "DAER-RS - Locais de fiscalizacao com radar portatil",
        "organizacao": ("Departamento Autonomo de Estradas de Rodagem / "
                        "Comando Rodoviario da Brigada Militar (CRBM/CPRv BM)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.daer.rs.gov.br/",
        "documentacao_url": "https://www.daer.rs.gov.br/radares-moveis",
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "semanal (atualizada as tercas-feiras)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "radares-moveis (planilhas de locais publicadas pelo CRBM/CPRv)",
        "url_recurso": "https://www.daer.rs.gov.br/radares-moveis",
        "formato_origem": "html|csv",
        "periodicidade_segundos": 604800,     # ~7 dias (declarado semanal)
        "status_integracao": "parcial",       # locais elegiveis, nao operacao
    }

    PAGINA = RECURSO["url_recurso"]
    # pagina institucional do CRBM/CPRv (fallback do 1o salto de descoberta)
    PAGINA_CRBM = "https://cprvbm.rs.gov.br/radar-movel"

    @classmethod
    def resolver_url(cls):
        """URLs CSV das planilhas oficiais (DAER -> CRBM/CPRv BM -> Sheets).

        O tick entrega o retorno de ``resolver_url()`` direto ao
        ``sincronizar``/``carregar``, que aceita uma LISTA de URLs.  Devolver
        aqui a pagina de entrada faria o ``carregar`` tratar o HTML como CSV
        (0 linhas).  Por isso ja resolvemos as planilhas; se nenhuma for
        descoberta, levantamos ``ErroFonte`` para o tick registrar erro em vez
        de um "0 registros" silencioso.
        """
        urls = cls.resolver_planilhas()
        if not urls:
            raise http.ErroFonte(
                "nao foi possivel descobrir as planilhas de radares moveis "
                "do CRBM/CPRv BM (%s)" % cls.PAGINA)
        return urls

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def descobrir_pagina_cprv(cls, html):
        """1o salto: link do DAER para a pagina do CRBM/CPRv BM."""
        for m in re.finditer(r'href="([^"]+)"', html or ""):
            href = m.group(1)
            if "radar-movel" in href.lower() and (
                    "crbm" in href.lower() or "cprv" in href.lower()
                    or "bm.rs.gov.br" in href.lower()):
                return urllib.parse.urljoin(cls.PAGINA, href)
        return None

    @classmethod
    def descobrir_planilhas(cls, html):
        """2o salto: URLs CSV (export) das planilhas publicadas na pagina."""
        return [_url_csv(i) for i in _extrair_ids_planilha(html or "")]

    @classmethod
    def resolver_planilhas(cls):
        """Segue DAER -> CRBM/CPRv e devolve as URLs CSV das planilhas."""
        try:
            html = http.baixar(cls.PAGINA)[0].decode("utf-8", "replace")
        except Exception:                                  # noqa: BLE001
            return []
        destino = cls.descobrir_pagina_cprv(html) or cls.PAGINA_CRBM
        try:
            html2 = http.baixar(destino)[0].decode("utf-8", "replace")
        except Exception:                                  # noqa: BLE001
            return []
        return cls.descobrir_planilhas(html2)

    # -- leitura ----------------------------------------------------------
    @staticmethod
    def _ler_local(ref):
        with open(ref, "rb") as f:
            return f.read()

    def carregar(self, origem):
        """origem: caminho local (CSV), lista de URLs CSV, ou None (descoberta).

        Retorna (conteudo, ".csv", "text/csv", registros).
        """
        if origem and isinstance(origem, (list, tuple)):
            urls = list(origem)
            partes = [http.baixar(u)[0] for u in urls]
            conteudo = b"\n".join(partes)
        elif origem and os.path.exists(str(origem)):
            conteudo = self._ler_local(origem)
        else:
            urls = [origem] if origem else self.resolver_planilhas()
            partes = [http.baixar(u)[0] for u in urls] if urls else []
            conteudo = b"\n".join(partes)
        registros = self._parse_csv(conteudo)
        return conteudo, ".csv", "text/csv", registros

    # -- parsing ----------------------------------------------------------
    @classmethod
    def _parse_csv(cls, conteudo):
        """Acha o cabecalho "No ord ... Velocidade regulamentada" em cada
        bloco da planilha (o CSV traz linhas de titulo antes da tabela)."""
        texto = conteudo.decode("utf-8-sig", "replace") \
            if isinstance(conteudo, bytes) else conteudo
        linhas = list(csv.reader(io.StringIO(texto)))
        registros = []
        cab_idx = None
        cabecalho = None
        periodo = None
        unidade = None
        for linha in linhas:
            juntas = _norm(" ".join(linha))
            if not any((c or "").strip() for c in linha):
                continue
            if periodo is None and juntas.startswith("PERIODO"):
                periodo = " ".join(c.strip() for c in linha if c.strip())
            if unidade is None and re.match(r"^(CRBM|CPRV)", juntas) \
                    and re.search(r"\d", juntas):
                unidade = " ".join(c.strip() for c in linha if c.strip())
            if cab_idx is None and "RODOVIA" in juntas and "KM INICIAL" in juntas:
                cab_idx = [_norm(c) for c in linha]
                cabecalho = [c.strip() for c in linha]
                continue
            if cab_idx is not None:
                if not any((c or "").strip() for c in linha):
                    # fim do bloco: volta a procurar o proximo cabecalho
                    cab_idx = None
                    continue
                d = _registro(cab_idx, cabecalho, linha)
                if d is not None:
                    if periodo:
                        d["periodo"] = periodo
                    if unidade:
                        d["unidade"] = unidade
                    registros.append(d)
        return _dedup(registros)

    # -- normalizar -------------------------------------------------------
    @staticmethod
    def _rodovia(v):
        r = (v or "").strip()
        if not r:
            return None
        m = re.match(r"^([A-Za-z]{2,3})\s*-?\s*(\d{1,4})$", r)
        if m:
            return "%s-%s" % (m.group(1).upper(), m.group(2))
        return r.upper().replace(" ", "-")

    def identificador(self, raw):
        rod = self._rodovia(nz.pick(raw, "rodovia", "Rodovia"))
        ki = nz.pick(raw, "km_inicial", "Km inicial")
        kf = nz.pick(raw, "km_final", "Km final")
        if rod:
            return "%s KM %s-%s" % (rod, ki, kf)
        return None

    def normalizar(self, idx, raw):
        rodovia = self._rodovia(nz.pick(raw, "rodovia", "Rodovia"))
        if not rodovia:
            return None
        km_i = nz.to_float(nz.pick(raw, "km_inicial", "Km inicial"))
        km_f = nz.to_float(nz.pick(raw, "km_final", "Km final"))
        # A planilha lista o mesmo segmento nos DOIS sentidos (ex.: 218->268 e
        # 268->218). O TRECHO_ELEGIVEL exige km_fim >= km_inicio; preservamos o
        # trecho (min/max) e a DIRECAO no campo `sentido` -- sem inventar nada.
        sentido = None
        if km_i is not None and km_f is not None:
            if km_f < km_i:
                km_i, km_f = km_f, km_i
                sentido = "decrescente"
            elif km_f > km_i:
                sentido = "crescente"
            else:
                sentido = "ambos"
        fracao = nz.pick(raw, "fracao", "Fracao fiscalizadora",
                         "Fração fiscalizadora")
        perimetro = nz.pick(raw, "perimetro", "Perímetro")
        vel = nz.pick(raw, "velocidade", "Velocidade regulamentada")
        periodo = nz.pick(raw, "periodo")
        unidade = nz.pick(raw, "unidade")
        obs = "; ".join(x for x in (
            ("Unidade: %s" % unidade) if unidade else None,
            ("Fracao fiscalizadora: %s" % fracao) if fracao else None,
            ("Perimetro: %s" % perimetro) if perimetro else None,
            ("Velocidade regulamentada: %s" % vel) if vel else None,
            ("Periodo: %s" % periodo) if periodo else None,
            ("radar PORTATIL: local elegivel; nao e operacao confirmada nem"
             " radar fixo instalado"),
        ) if x)
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "trecho_elegivel",
            "indicador": "pode_haver_fiscalizacao",
            "radar_instalado_confirmado": None,
            "uf": "RS",
            "via_codigo": rodovia,
            "via_tipo": "estadual",
            "km_inicio": km_i,
            "km_fim": km_f,
            "sentido": sentido,
            "sentido_original": None,
            "criterio_inclusao": ("local passivel de fiscalizacao com radar "
                                  "portatil (CRBM/CPRv BM - Res. CONTRAN "
                                  "798/2020)"),
            "situacao": "vigente",
            "metodo_obtencao": ("publicacao CRBM/CPRv BM (DAER-RS: radares "
                                "moveis)"),
            "observacoes": obs or None,
        }


# --------------------------------------------------------------------------
# helpers de parsing
# --------------------------------------------------------------------------
_CANONICO = (
    ("rodovia", ("RODOVIA",)),
    ("km_inicial", ("KM INICIAL",)),
    ("km_final", ("KM FINAL",)),
    ("perimetro", ("PERIMETRO",)),
    ("velocidade", ("VELOCIDADE REGULAMENTADA", "VELOCIDADE")),
    ("fracao", ("FRACAO FISCALIZADORA", "FISCALIZADORA")),
)


def _registro(cab_norm, cabecalho, linha):
    """Mapeia uma linha para {canonico: valor} usando o cabecalho normalizado."""
    valores = {}
    for i, chave in enumerate(cab_norm):
        valores[chave] = linha[i] if i < len(linha) else ""
    d = {}
    for canonico, chaves in _CANONICO:
        for chave in chaves:
            if chave in valores and valores[chave].strip():
                d[canonico] = valores[chave].strip()
                break
    # so linhas com rodovia recasaveis contam
    if not d.get("rodovia"):
        return None
    return d


def _dedup(registros):
    vistos = set()
    out = []
    for d in registros:
        chave = (d.get("rodovia"), d.get("km_inicial"), d.get("km_final"),
                 d.get("fracao"), d.get("velocidade"))
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append(d)
    return out
