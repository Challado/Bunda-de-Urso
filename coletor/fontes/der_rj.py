# -*- coding: utf-8 -*-
"""Fonte F16 - DER-RJ, radares PORTATEIS por local (trecho elegivel).

Pagina institucional: https://sgitp.der.rj.gov.br/radares-portateis

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  https://sgitp.der.rj.gov.br/radares-portateis  ->  HTTP 200, text/html
  A propria pagina publica, em HTML estatico, DUAS tabelas:
    (1) LOCAIS: POSTO, CIA, RODOVIA, KM, LOCAL, MUNICIPIO,
        TIPO DE FISCALIZACAO, SENTIDO CRESCENTE, SENTIDO DECRESCENTE,
        VELOCIDADE DE FISCALIZACAO, ESTUDO TECNICO, STATUS  (41 linhas)
    (2) EQUIPAMENTOS (medidores portateis): INSTRUMENTO, MODELO, INMETRO,
        NUMERO DE SERIE, STATUS
  O titulo declara "Radares Portateis em Operacao das 06h as 22h".

FILTRO: a tabela de LOCAIS e uma lista de TRECHOS/LOCAIS passiveis de
fiscalizacao com medidor PORTATIL (rodovia/km/municipio/sentido/velocidade).
Isto NUNCA e um radar fixo instalado: cada linha entra como TRECHO_ELEGIVEL,
com ``radar_instalado_confirmado = None``. A tabela de equipamentos apenas
lista os medidores portateis (identificador + serie + INMETRO); NAO traz
posicao, por isso nao vira ponto posicionado.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_HTML = "text/html; charset=utf-8"

# cabecalhos que identificam a tabela de LOCAIS (trechos) de radares portateis
_COL_RODOVIA = ("RODOVIA",)
_COL_KM = ("KM",)
_COL_MUNICIPIO = ("MUNICIPIO", "MUNICÍPIO")
_COL_TIPO = ("TIPO DE FISCALIZA", "TIPO DEFISCALIZA", "TIPO")
_COL_VEL = ("VELOCIDADE",)


def _norm_header(texto):
    """Chave de cabecalho sem acento/maiuscula para casar colunas."""
    import unicodedata
    t = unicodedata.normalize("NFD", (texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip().upper()


def _casa(cabecalho, chaves):
    for chave in chaves:
        if _norm_header(chave) in cabecalho:
            return True
    return False


class ColetorDERRJ(ColetorBase):

    FONTE = {
        "nome": "DER-RJ - Radares portateis (locais de fiscalizacao)",
        "organizacao": "Departamento de Estradas de Rodagem do Rio de Janeiro",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.der.rj.gov.br/",
        "documentacao_url": "https://sgitp.der.rj.gov.br/radares-portateis",
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "radares-portateis (tabela HTML de locais por rodovia/km)",
        "url_recurso": "https://sgitp.der.rj.gov.br/radares-portateis",
        "formato_origem": "html",
        "periodicidade_segundos": 604800,     # ~semanal (verificacao do local)
        # recurso e lista de LOCAIS de radar PORTATIL (trecho elegivel), nao
        # cadastro de radar fixo instalado.
        "status_integracao": "parcial",
    }

    URL_PAGINA = RECURSO["url_recurso"]
    JANELA = "Radares Portateis em Operacao das 06h as 22h"

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (HTML estatico, sem arquivo datado)."""
        return cls.URL_PAGINA

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        corpo, _headers, _url_final = http.baixar(ref)
        return corpo

    def carregar(self, origem):
        alvo = origem or self.URL_PAGINA
        conteudo = self._ler(alvo)
        return (conteudo, ".html", MIME_HTML,
                self.extrair_locais(conteudo))

    # -- parsing ----------------------------------------------------------
    @classmethod
    def extrair_locais(cls, conteudo):
        """Acha a tabela de LOCAIS (rodovia/km) e devolve os registros (dict)."""
        tabelas = pl.ler_tabelas_html(conteudo)
        for tabela in tabelas:
            if not tabela:
                continue
            cabecalho = [_norm_header(c) for c in tabela[0]]
            if _casa(cabecalho, _COL_RODOVIA) and _casa(cabecalho, _COL_KM):
                return _dicts(tabela)
        return []

    @staticmethod
    def extrair_equipamentos(conteudo):
        """Tabela de EQUIPAMENTOS (medidores portateis), quando presente."""
        for tabela in pl.ler_tabelas_html(conteudo):
            if not tabela:
                continue
            cabecalho = [_norm_header(c) for c in tabela[0]]
            if _casa(cabecalho, ("INSTRUMENTO",)) or (
                    _casa(cabecalho, ("NUMERO DE SERIE", "NÚMERO DE SÉRIE"))
                    and _casa(cabecalho, ("INMETRO",))):
                return _dicts(tabela)
        return []

    # -- normalizar -------------------------------------------------------
    @staticmethod
    def _rodovia(v):
        r = (v or "").strip()
        if not r or r == "-":
            return None
        r = re.sub(r"(?i)^([A-Z]{2,3})\s*-?\s*(\d{2,4})$",
                   lambda m: "%s-%s" % (m.group(1).upper(), m.group(2)), r)
        return r.replace(" ", "-").upper()

    def identificador(self, raw):
        rod = self._rodovia(nz.pick(raw, "RODOVIA", "Rodovia"))
        km = nz.pick(raw, "KM", "Km")
        local = nz.pick(raw, "LOCAL", "Local")
        if rod and km:
            return ("%s KM %s" % (rod, km)).strip()
        return rod or local or None

    def normalizar(self, idx, raw):
        rodovia = self._rodovia(nz.pick(raw, "RODOVIA", "Rodovia"))
        if not rodovia:
            return None
        km = nz.to_float(nz.pick(raw, "KM", "Km"))
        municipio = nz.pick(raw, "MUNICIPIO", "MUNICÍPIO", "Municipio")
        local = nz.pick(raw, "LOCAL", "Local")
        tipo_fisc = nz.pick(raw, "TIPO DE FISCALIZACAO", "TIPO DEFISCALIZACAO",
                            "TIPO DE FISCALIZAÇÃO")
        vel_txt = nz.pick(raw, "VELOCIDADE DE FISCALIZACAO",
                          "VELOCIDADE DEFISCALIZACAO",
                          "VELOCIDADE DE FISCALIZAÇÃO")
        cresc = nz.pick(raw, "SENTIDO CRESCENTE")
        decresc = nz.pick(raw, "SENTIDO DECRESCENTE")
        posto = nz.pick(raw, "POSTO")
        cia = nz.pick(raw, "CIA")
        status = nz.pick(raw, "STATUS")
        obs = "; ".join(x for x in (
            ("Posto: %s" % posto) if posto else None,
            ("CIA: %s" % cia) if cia else None,
            ("Local: %s" % local) if local else None,
            ("Tipo de fiscalizacao: %s" % tipo_fisc) if tipo_fisc else None,
            ("Sentido crescente: %s" % cresc) if cresc else None,
            ("Sentido decrescente: %s" % decresc) if decresc else None,
            ("Velocidade de fiscalizacao: %s" % vel_txt) if vel_txt else None,
            ("Janela declarada: %s" % self.JANELA),
            ("Status na fonte: %s" % status) if status else None,
            ("radar PORTATIL: local passivel de fiscalizacao; nao e"
             " radar fixo instalado"),
        ) if x)
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "trecho_elegivel",
            "indicador": "pode_haver_fiscalizacao",
            # TRECHO_ELEGIVEL de radar PORTATIL nunca e radar instalado (spec).
            "radar_instalado_confirmado": None,
            "uf": "RJ",
            "municipio_nome": municipio,
            "via_codigo": rodovia,
            "via_tipo": "estadual",
            "km_inicio": km,
            "km_fim": km,
            "sentido": None,
            "criterio_inclusao": ("local de fiscalizacao com radar portatil "
                                  "publicado pelo DER-RJ"),
            "situacao": "vigente",
            "metodo_obtencao": "publicacao DER-RJ (radares portateis - locais)",
            "observacoes": obs or None,
        }


def _dicts(tabela):
    """Tabela (lista de linhas) -> lista de dicts; ignora linhas vazias."""
    linhas = [l for l in tabela if any((c or "").strip() for c in l)]
    if not linhas:
        return []
    cabecalho = [(c or "").strip() for c in linhas[0]]
    out = []
    for linha in linhas[1:]:
        if not any((c or "").strip() for c in linha):
            continue
        out.append({cabecalho[i]: (linha[i] if i < len(linha) else "")
                    for i in range(len(cabecalho)) if cabecalho[i]})
    return out
