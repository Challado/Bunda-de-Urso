# -*- coding: utf-8 -*-
"""Fonte MA - Detran-MA, fiscalizacao eletronica de velocidade.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582

A pagina declara: "Para consultar a lista completa dos medidores de velocidade
instalados e em operacao nas rodovias maranhenses...". O link
"Fiscalizacao Eletronica" aponta para um PDF na SGP
(``sgp5.detran.ma.gov.br/uploads/midias/<hash>.pdf``) que e a relacao oficial
dos radares instalados/em operacao, com uma linha por equipamento/sentido:

  CODIGO EQUIPAMENTO | Nº DE SERIE | MARCA / MODELO | ENDERECO | SENTIDO |
  MUNICIPIO | TIPO | VELOCIDADE | INMETRO | LATITUDE | LONGITUDE

O ``TIPO`` e declarado pela propria fonte (hoje sempre "FIXO"); ele e
preservado, nao inferido. As coordenadas publicadas viram posicao; nada e
inventado -- campo ausente fica NULL.

A pagina tambem traz uma tabela "Estudos Tecnicos" (um PDF de levantamento
tecnico por local). Esses estudos NAO viram pontos: sao documentos de local,
sem coordenada, e um "local/trecho" nunca vira radar instalado confirmado
(spec). Eles sao apenas listados em ``descobrir_recursos`` (sem criar GPS).

A URL do PDF NAO e chumbada: ela e descoberta na propria pagina (o fallback
apenas cobre falha de rede). O texto do PDF e lido com ``pdftotext`` (poppler)
quando disponivel e, na ausencia dele, com o leitor stdlib
``planilha.ler_pdf_texto``. Aceita arquivo LOCAL (fixture/testes).
"""
import os
import re
import subprocess
import urllib.parse
from html import unescape

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_PDF = "application/pdf"
MIME_TXT = "text/plain"

# Linha do relatorio de fiscalizacao eletronica. O texto extraido pode chegar
# "colado" (leitor stdlib) ou espacado (pdftotext -layout); por isso usamos
# \s+ entre campos e nunca ancoramos a linha.
PADRAO_LINHA = re.compile(
    r"(?P<codigo>MA\d{3}[RL])\s+(?P<serie>\S+)\s+"
    r"(?P<fabricante>\S+)\s*/\s*(?P<modelo>\S+)\s+"
    r"(?P<endereco>MA\s+\d+\s*-\s*KM\s*\d+\s*\+\s*\d+\s*-\s*.*?)\s+"
    r"(?P<sentido>[A-ZÀ-Ý]+/[A-ZÀ-Ý]+)\s+"
    r"(?P<municipio>.*?)\s+"
    r"(?P<tipo>FIXO|PORT[AÁ]TIL|M[ÓO]VEL)\s+"
    r"(?P<velocidade>\d+)\s*Km/h\s+"
    r"(?P<inmetro>[\d.]+)\s+"
    r"(?P<latitude>-?\d+\.\d+)[°º]\s*(?P<longitude>-?\d+\.\d+)[°º]",
    re.I | re.S)

# "MA 203 - KM 012 + 400 - ..." -> via MA-203, km 12.4
PADRAO_ENDERECO = re.compile(
    r"^(?P<via>[A-Z]{2})\s*(?P<num>\d+)\s*-\s*KM\s*"
    r"(?P<km>\d+)\s*\+\s*(?P<metros>\d+)", re.I)

PADRAO_ANCORA = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
# Linha da tabela "Estudos Tecnicos": <td>LOCAL</td><td><a href="...pdf">
PADRAO_ESTUDO = re.compile(
    r"<td[^>]*>\s*(?P<local>[^<]*?MA\s*\d+[^<]*?)</td>\s*"
    r"<td[^>]*>\s*<a\b[^>]*href=\"(?P<url>[^\"]+\.pdf)\"", re.I | re.S)


def _sem_acento(texto):
    import unicodedata
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _limpar(texto):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", texto or ""))).strip()


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


class ColetorDetranMA(ColetorBase):

    FONTE = {
        "nome": "Detran-MA - Fiscalizacao eletronica de velocidade",
        "organizacao": "Departamento Estadual de Transito do Maranhao (Detran-MA)",
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.detran.ma.gov.br/",
        "documentacao_url": ("https://www.detran.ma.gov.br/inicio/paginas/"
                             "Pagina.xhtml?id=23582"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Fiscalizacao eletronica (lista de radares instalados, PDF)",
        "url_recurso": ("https://www.detran.ma.gov.br/inicio/paginas/"
                        "Pagina.xhtml?id=23582"),
        "formato_origem": "pdf",
        "periodicidade_segundos": 2592000,     # ~30 dias
        "status_integracao": "ok",
    }

    URL_PAGINA = ("https://www.detran.ma.gov.br/inicio/paginas/"
                  "Pagina.xhtml?id=23582")
    # Rede de seguranca (URL de midia, nao datada); a fonte real e a pagina.
    URL_FALLBACK = ("https://sgp5.detran.ma.gov.br/uploads/midias/"
                    "uf4n8qryt82xiqdp8nu5mv5i1ocvry.pdf")

    # -- descoberta --------------------------------------------------------
    @classmethod
    def descobrir_recursos(cls, html):
        """Mapeia a pagina -> {fiscalizacao_pdf, estudos:[{local,url}]}.

        Offline-testavel: recebe o HTML ja decodificado. O PDF de fiscalizacao
        e o link cujo rotulo menciona "fiscaliza"; os estudos sao a tabela
        "Estudos Tecnicos" (nao viram pontos).
        """
        achados = {"fiscalizacao_pdf": None, "estudos": []}
        for m in PADRAO_ESTUDO.finditer(html):
            achados["estudos"].append({
                "local": _limpar(m.group("local")),
                "url": urllib.parse.urljoin(cls.URL_PAGINA,
                                            unescape(m.group("url"))),
            })
        for m in PADRAO_ANCORA.finditer(html):
            href = unescape(m.group(1))
            rotulo = _sem_acento(_limpar(m.group(2))).lower()
            if href.lower().endswith(".pdf") and "fiscaliza" in rotulo:
                achados["fiscalizacao_pdf"] = urllib.parse.urljoin(
                    cls.URL_PAGINA, href)
                break
        if not achados["fiscalizacao_pdf"]:
            # heuristica: primeiro PDF em sgp*.detran.ma.gov.br
            for m in PADRAO_ANCORA.finditer(html):
                href = unescape(m.group(1))
                if href.lower().endswith(".pdf") and "sgp" in href.lower():
                    achados["fiscalizacao_pdf"] = urllib.parse.urljoin(
                        cls.URL_PAGINA, href)
                    break
        return achados

    @classmethod
    def resolver_url(cls):
        """URL do PDF de fiscalizacao descoberta na pagina; fallback fixo."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            url = cls.descobrir_recursos(html).get("fiscalizacao_pdf")
            if url:
                return url
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
            if "detran.ma.gov.br" in url and "/midias/" not in url:
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
        """Reconhece as linhas do relatorio (dedup de repeticoes exatas)."""
        if not texto:
            return []
        vistos = {}
        for m in PADRAO_LINHA.finditer(texto):
            d = m.groupdict()
            d["endereco"] = re.sub(r"\s+", " ", d["endereco"]).strip()
            d["municipio"] = re.sub(r"\s+", " ", d["municipio"]).strip()
            chave = (d["codigo"], d["serie"], d["endereco"], d["sentido"],
                     d["latitude"], d["longitude"])
            vistos.setdefault(chave, d)
        return list(vistos.values())

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "codigo")

    @staticmethod
    def _via_km(endereco):
        m = PADRAO_ENDERECO.match(endereco or "")
        if not m:
            return None, None
        via = "%s-%s" % (m.group("via").upper(), m.group("num"))
        km = int(m.group("km")) + int(m.group("metros")) / 1000.0
        return via, km

    def normalizar(self, idx, raw):
        lat = nz.to_float(raw.get("latitude"))
        lon = nz.to_float(raw.get("longitude"))
        if lat is None or lon is None or not (-90 <= lat <= 90
                                              and -180 <= lon <= 180):
            lat = lon = None
        via, km = self._via_km(raw.get("endereco"))
        sentido_original = nz.pick(raw, "sentido")
        tipo = nz.pick(raw, "tipo")
        observacoes = "; ".join(x for x in (
            ("Tipo na fonte: %s" % tipo) if tipo else None,
            ("Endereco: %s" % raw.get("endereco")) if raw.get("endereco")
            else None,
            ("INMETRO: %s" % raw.get("inmetro")) if raw.get("inmetro") else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao Detran-MA (fiscalizacao "
                                "eletronica - lista de radares instalados)"),
            "uf": "MA",
            "municipio_nome": nz.pick(raw, "municipio"),
            "via_codigo": via,
            "via_tipo": "estadual" if via else None,
            "km": km,
            "tipo_pista": None,
            "situacao": None,
            # TIPO declarado pela fonte (hoje sempre "FIXO"): preservado.
            "tipo_radar": nz.normalizar_tipo_radar(tipo),
            "numero_serie": nz.pick(raw, "serie"),
            "fabricante": nz.pick(raw, "fabricante"),
            "modelo": nz.pick(raw, "modelo"),
            "velocidade_geral": nz.to_velocidade(
                nz.pick(raw, "velocidade")),
            "sentido": nz.normalizar_sentido(sentido_original),
            "sentido_original": sentido_original,
            "observacoes": observacoes,
        }
