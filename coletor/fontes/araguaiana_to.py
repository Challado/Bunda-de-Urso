# -*- coding: utf-8 -*-
"""Fonte TO - ASTT Araguaina, medidores de velocidade (lista de enderecos).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://www.araguaina.to.gov.br/servicos/medidores-de-velocidade-lista-de-enderecos

A Agencia Municipal de Seguranca, Transporte e Transito (ASTT) disponibiliza a
"Lista de Enderecos dos Radares, com a relacao atualizada dos pontos onde ha
equipamentos de fiscalizacao eletronica instalados no municipio". O link de
download aponta para um PDF (``/documentos/equipamentos_araguaina.pdf``), cuja
URL e descoberta na pagina (o fallback apenas cobre falha de rede).

O PDF traz uma linha por FAIXA, com colunas reais:

  ITEM | TIPO | CODIGO DO PROCESS. | Nº DE SERIE | Nº DE FAIXAS |
  LOCAL DE IMPLANTAÇÃO | SENTIDO | REGUL. | VIA | COORDENADAS

Cada equipamento (par CODIGO DO PROCESS. + Nº DE SERIE) pode cobrir mais de
uma faixa (FAIXA 1, 2, 3...). Agrupamos as linhas por equipamento para produzir
UM ponto por equipamento, preservando o numero de faixas e os sentidos
declarados. O tipo na fonte (CEV/REV/CEM) e a velocidade regulamentada (REGUL.)
sao preservados; nada e inventado -- campo ausente fica NULL.

Coordenadas ilegiveis na fonte (ex.: "-7.158.138" / "-7199534") NAO viram GPS
artificial: o ponto e preservado SEM posicao. O texto do PDF e lido com
``pdftotext`` (poppler) quando disponivel e, na ausencia dele, com o leitor
stdlib ``planilha.ler_pdf_texto``. Aceita arquivo LOCAL (fixture/testes).
"""
import os
import re
import subprocess

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_PDF = "application/pdf"
MIME_TXT = "text/plain"

# Uma linha por faixa. Aceita o texto "colado" (stdlib) e o espacado
# (pdftotext -layout).
PADRAO_LINHA = re.compile(
    r"(?P<item>\d{1,3})\s*(?P<tipo>CEV|REV|CEM)\s*(?P<processo>ARAGU\d+)"
    r"\s*(?P<serie>R\d+)\s*FAIXA\s*(?P<faixa>\d+)\s*"
    r"(?P<local>.+?)\s*"
    r"(?P<sentido>NOROESTE|NORDESTE|SUDOESTE|SUDESTE|NORTE|SUL|LESTE|OESTE)?"
    r"\s*(?P<regul>\d{2})\s*(?P<via>\d{2})?\s*"
    r"(?P<latitude>-?\d[\d.]*)\s+(?P<longitude>-?\d[\d.]*)", re.S)

PADRAO_ANCORA = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)


def _texto_pdf(conteudo):
    """Texto do PDF via poppler (pdftotext -layout); fallback stdlib."""
    try:
        proc = subprocess.run(["pdftotext", "-layout", "-", "-"],
                              input=conteudo, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.decode("utf-8", "replace")
    except Exception:                                       # noqa: BLE001
        pass
    return pl.ler_pdf_texto(conteudo)


def _coord(valor):
    """Coordenada estrita: um unico ponto decimal e faixa valida."""
    if valor is None:
        return None
    s = str(valor).strip().replace("°", "").replace("º", "").replace(",", ".")
    if not s or s.count(".") != 1:
        return None
    try:
        return float(s)
    except ValueError:
        return None


class ColetorASTTAraguaina(ColetorBase):

    FONTE = {
        "nome": "ASTT Araguaina - Medidores de velocidade (lista de enderecos)",
        "organizacao": ("Agencia Municipal de Seguranca, Transporte e Transito "
                        "(ASTT) - Araguaina"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.araguaina.to.gov.br/",
        "documentacao_url": ("https://www.araguaina.to.gov.br/servicos/"
                             "medidores-de-velocidade-lista-de-enderecos"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Medidores de velocidade - lista de enderecos (PDF)",
        "url_recurso": ("https://www.araguaina.to.gov.br/servicos/"
                        "medidores-de-velocidade-lista-de-enderecos"),
        "formato_origem": "pdf",
        "periodicidade_segundos": 2592000,     # ~30 dias
        "status_integracao": "ok",
    }

    URL_PAGINA = ("https://www.araguaina.to.gov.br/servicos/"
                  "medidores-de-velocidade-lista-de-enderecos")
    URL_FALLBACK = ("https://www.araguaina.to.gov.br/documentos/"
                    "equipamentos_araguaina.pdf")

    # -- descoberta --------------------------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Mapeia a pagina -> {pdf: URL do documento de equipamentos}."""
        achados = {"pdf": None}
        for m in PADRAO_ANCORA.finditer(html):
            href, rotulo = m.group(1), m.group(2)
            if href.lower().endswith(".pdf") and (
                    "documentos/" in href.lower()
                    or "equipament" in href.lower()
                    or "lista" in _sem_rotulo(rotulo)):
                achados["pdf"] = href
                break
        return achados

    @classmethod
    def resolver_url(cls):
        """URL do PDF de equipamentos descoberta na pagina; fallback fixo."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            achados = cls.descobrir_recursos(html)
            if achados.get("pdf"):
                return achados["pdf"]
        except Exception:                                   # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower() or ".pdf"
        else:
            url = origem or self.resolver_url()
            if "araguaina.to.gov.br" in url and "/documentos/" not in url:
                url = self.resolver_url()
            conteudo, _headers, _final = http.baixar(url)
            ext = ".pdf"
        if ext in (".txt", ".text"):
            texto = conteudo.decode("utf-8", "replace")
            mime = MIME_TXT
        else:
            texto = _texto_pdf(conteudo)
            mime = MIME_PDF
        return conteudo, ext, mime, self.extrair_registros(texto)

    # -- parsing -----------------------------------------------------------
    @classmethod
    def extrair_registros(cls, texto):
        """Uma linha por faixa -> agrupa por equipamento (processo + serie)."""
        if not texto:
            return []
        equipamentos = {}
        for m in PADRAO_LINHA.finditer(texto):
            d = m.groupdict()
            chave = (d["processo"], d["serie"])
            reg = equipamentos.get(chave)
            if reg is None:
                reg = {
                    "processo": d["processo"],
                    "serie": d["serie"],
                    "tipo": d["tipo"],
                    "local": d["local"].strip(),
                    "regul": d["regul"],
                    "via": d["via"],
                    "latitude": d["latitude"],
                    "longitude": d["longitude"],
                    "faixas": [],
                    "sentidos": [],
                }
                equipamentos[chave] = reg
            if d["faixa"] not in reg["faixas"]:
                reg["faixas"].append(d["faixa"])
            if d["sentido"] and d["sentido"] not in reg["sentidos"]:
                reg["sentidos"].append(d["sentido"])
        return list(equipamentos.values())

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "processo", "serie")

    @staticmethod
    def _sentido(sentidos):
        if not sentidos:
            return None
        return nz.normalizar_sentido(sentidos[0])

    def normalizar(self, idx, raw):
        lat = _coord(raw.get("latitude"))
        lon = _coord(raw.get("longitude"))
        if lat is None or not (-90 <= lat <= 90):
            lat = None
        if lon is None or not (-180 <= lon <= 180):
            lon = None
        sentidos = raw.get("sentidos") or []
        faixas = raw.get("faixas") or []
        tipo = raw.get("tipo")
        observacoes = "; ".join(x for x in (
            ("Tipo na fonte: %s" % tipo) if tipo else None,
            ("Codigo do processo: %s" % raw.get("processo"))
            if raw.get("processo") else None,
            ("Faixas: %s" % ", ".join(faixas)) if faixas else None,
            ("Sentido(s): %s" % ", ".join(sentidos)) if sentidos else None,
            ("Velocidade da via: %s" % raw.get("via")) if raw.get("via")
            else None,
            ("Coordenada ilegivel na fonte") if (lat is None or lon is None)
            else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao ASTT Araguaina (lista de enderecos "
                                "de medidores de velocidade)"),
            "uf": "TO",
            "municipio_nome": "Araguaina",
            "via_codigo": nz.pick(raw, "local"),
            "via_tipo": "municipal",
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            # equipamentos de fiscalizacao eletronica INSTALADOS -> fixo.
            "tipo_radar": "fixo",
            "numero_serie": nz.pick(raw, "serie"),
            "fabricante": None,
            "modelo": None,
            "velocidade_geral": nz.to_velocidade(nz.pick(raw, "regul")),
            "sentido": self._sentido(sentidos),
            "sentido_original": ("; ".join(sentidos) if sentidos else None),
            "observacoes": observacoes,
        }


def _sem_rotulo(texto):
    import unicodedata
    t = unicodedata.normalize("NFD", re.sub(r"<[^>]+>", " ", texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()
