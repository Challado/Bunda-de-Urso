# -*- coding: utf-8 -*-
"""Fonte estadual GO - GOINFRA, relatorio de equipamentos de monitoramento.

Pagina oficial (o link do arquivo NAO e fixo: muda a cada publicacao):
  https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/

A pagina publica um relatorio (hoje um PDF gerado pelo Google Sheets) cujo
NOME e datado, ex.: "Lista_de_Equipamento_02_10_2026.xlsx-Equipamentos-Ativos.pdf".
Este conector DESCOBRE o link mais recente na propria pagina (``resolver_url``)
em vez de chumbar a URL datada; a URL pontual fica so como ultimo recurso.

DEPENDENCIA DE SISTEMA (nao e pacote Python): a extracao do PDF usa o binario
``pdftotext`` do pacote **poppler-utils**, chamado via subprocess
(``pdftotext -layout - -`` lendo do stdin e escrevendo no stdout). O host ja
tem poppler-utils instalado; nada e instalado por este modulo. Se o binario
nao existir, ``ler_pdf_texto_layout`` levanta
:class:`coletor.http.ErroFonte` com mensagem clara. Nenhuma dependencia pip.

Todo download passa por :func:`coletor.http.baixar` (regra dura do projeto).

CONTRATO / regras aplicadas (docs/GOINFRA_IMPLEMENTAR_COLETOR.md):
  - km "469+594" -> 469.594, preservando a string original (``km_original``);
  - latitude/longitude em MICROGRAUS apenas nesta fonte (-17624721 -> -17.624721);
  - ``codigo_equipamento`` != ``numero_serie`` != ``faixa`` (identidades
    distintas, nao fundir nem multiplicar equipamento por faixa);
  - NAO fundir equipamentos por proximidade;
  - ``afericao_valida_ate`` e validade metrologica, NAO prova de operacao:
    guardada como observacao; ``situacao`` NAO e inferida dessas datas;
  - ``velocidade`` = limite regulamentado publicado (campo "Velocidade");
  - coordenada incoerente com UF/via/km vai para QUARENTENA (marcada, o
    registro e preservado); codigo publicado em duas vias diferentes gera
    CONFLITO (nao escolhemos arbitrariamente).
"""
import os
import re
import shutil
import subprocess

from core import config
from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_PDF = "application/pdf"
MIME_XLSX = ("application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet")

# Caixa aproximada do estado de Goias (para detectar coordenada incoerente).
GO_LAT_MIN, GO_LAT_MAX = -19.8, -12.0
GO_LON_MIN, GO_LON_MAX = -53.5, -45.5
# Divergencia (graus) dentro do mesmo (via, km) que caracteriza conflito de
# coordenada. ~0.05 grau no Brasil central ~ 5,5 km.
LIMITE_DIVERGENCIA_GRAUS = 0.05

# ---------------------------------------------------------------------------
# Linha de dados do relatorio (layout do pdftotext -layout).
#
# Ordem real das colunas:
#   Tipo | Cod. Equipamento | Faixa | Sentido-CD | Numero de Serie | Local |
#   Complemento(KM xxx+yyyM) | Sentido(descritivo) | Municipio | Codigo SRE |
#   Latitude | Longitude | Velocidade | Data Autorizacao | Data Ativo |
#   Data venc. Afer | Lote | Nota de Instalacao | No SEI | ESTUDO TECNICO
#
# O Complemento varia na publicacao: "KM 225+332M", "000+005", "406+080M",
# "8 + 84M", "0,001", "KM 255,530m" ou AUSENTE. O codigo SRE aparece como
# "060EGO0230", "156GO0140" (sem letra) ou "050UGO1120".
# ---------------------------------------------------------------------------
PADRAO_LINHA = re.compile(
    r"^\s*(?P<tipo>RADAR FIXO|LOMBADA ELET\w*)\s+"
    r"(?P<cod>[0-9A-Za-z]+)\s+"
    r"(?P<faixa>\d{1,2}[A-Z])\s+"
    r"(?P<sentido_cd>Crescente|Decrescente)\s+"
    r"(?P<serie>[0-9A-Za-z][0-9A-Za-z.\-/]*)\s+"
    r"(?P<local>GO\s*-\s*\d+)\s+"
    r"(?:(?:\d+\s+)?(?:(?:KM)\s*)?"
    r"(?:(?P<km>\d+)\s*\+\s*(?P<metros>\d+)|(?P<km_decimal>\d+[.,]\d+))"
    r"\s*[mM]?\s+)?"
    r"(?P<meio>.*?)\s+"
    r"(?P<sre>\d{3}[A-Z]{0,3}GO\d+)\s+"
    r"(?P<lat>-?\d+)\s+(?P<lon>-?\d+)\s+(?P<velocidade>\d+)\s+"
    r"(?P<data_autorizacao>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<data_ativo>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<afericao_valida_ate>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<lote>Lote\s+\d+\s*-\s*\d+)\s+"
    r"(?P<nota_instalacao>\d+)\s+"
    r"(?P<sei>\d+)\s+"
    r"(?P<estudo_tecnico>ET\w+)\s*$", re.I)

PADRAO_ANCORA = re.compile(
    r"href=\"([^\"]+\.(?:pdf|xlsx|xls|csv))\"", re.I)


# ---------------------------------------------------------------------------
# Extracao de texto do PDF via poppler-utils
# ---------------------------------------------------------------------------
def pdftotext_disponivel():
    return shutil.which("pdftotext") is not None


def ler_pdf_texto_layout(conteudo):
    """Texto do PDF preservando o layout de colunas (pdftotext -layout).

    Le os bytes do PDF pelo stdin e devolve o texto pelo stdout. Levanta
    :class:`coletor.http.ErroFonte` se o poppler-utils nao estiver instalado
    ou o PDF for invalido.
    """
    exe = shutil.which("pdftotext")
    if not exe:
        raise http.ErroFonte(
            "pdftotext (poppler-utils) ausente: instale poppler-utils para "
            "ler o PDF da GOINFRA; nenhum pacote Python resolve isso")
    proc = subprocess.run(
        [exe, "-layout", "-", "-"],
        input=conteudo if isinstance(conteudo, bytes) else conteudo.encode(
            "utf-8", "replace"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise http.ErroFonte(
            "pdftotext falhou (codigo %d): %s"
            % (proc.returncode, proc.stderr.decode("utf-8", "replace")[:300]))
    return proc.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Descoberta de URL na pagina oficial
# ---------------------------------------------------------------------------
def _chave_data(texto):
    """(ano, mes, dia) extraido do nome/url; (0,0,0) quando nao houver."""
    s = texto or ""
    m = re.search(r"(\d{2})_(\d{2})_(\d{4})", s)       # dd_mm_yyyy
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{2})_(\d{4})", s)               # mm_yyyy
    if m:
        return (int(m.group(2)), int(m.group(1)), 0)
    m = re.search(r"/(\d{4})/(\d{2})/", s)             # /yyyy/mm/
    if m:
        return (int(m.group(1)), int(m.group(2)), 0)
    return (0, 0, 0)


def descobrir_url_recurso(html):
    """URL do relatorio de equipamentos mais recente dentro do HTML.

    Prefere arquivos cujo caminho cite "equipamento"; empata pela data (nome
    ou pasta). Devolve None quando a pagina nao expoe arquivo baixavel.
    Retorna tambem a lista de todas as ancoras de arquivo (evidencia).
    """
    if not html:
        return None, []
    urls = [m.group(1).replace("&amp;", "&")
            for m in PADRAO_ANCORA.finditer(html)]
    if not urls:
        return None, []
    equipamentos = [u for u in urls if "equipamento" in u.lower()]
    candidatos = equipamentos or urls
    candidatos = sorted(candidatos, key=_chave_data, reverse=True)
    return candidatos[0], urls


# ---------------------------------------------------------------------------
# Parsing da tabela
# ---------------------------------------------------------------------------
def _km_decimal(m):
    if m.get("km") is not None and m.get("metros") is not None:
        try:
            return int(m["km"]) + int(m["metros"]) / 1000.0
        except ValueError:
            return None
    if m.get("km_decimal"):
        s = m["km_decimal"].replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _km_original(m):
    if m.get("km") is not None and m.get("metros") is not None:
        return "%s+%s" % (m["km"], m["metros"])
    if m.get("km_decimal"):
        return m["km_decimal"]
    return None


def _dividir_meio(meio):
    """Coluna do meio = Sentido(descritivo) + Municipio.

    Separa por 2+ espacos: a ultima celula e o municipio; o resto e o texto
    de sentido descritivo (pode estar vazio).
    """
    celulas = [c for c in re.split(r"\s{2,}", (meio or "").strip()) if c]
    if not celulas:
        return None, None
    municipio = celulas[-1]
    descricao = " ".join(celulas[:-1]) if len(celulas) > 1 else None
    return descricao, municipio


def extrair_registros(texto):
    """Converte o texto extraido do PDF em lista de dicts (campos brutos)."""
    if not texto:
        return []
    registros = []
    for linha in texto.replace("\f", "\n").splitlines():
        m = PADRAO_LINHA.match(linha)
        if not m:
            continue
        d = m.groupdict()
        descricao, municipio = _dividir_meio(d.pop("meio"))
        d["sentido_descrito"] = descricao
        d["municipio"] = municipio
        registros.append(d)
    return registros


# ---------------------------------------------------------------------------
# Analise: conflitos e quarentena (nunca descartar em silencio)
# ---------------------------------------------------------------------------
def _via(local):
    return re.sub(r"\s+", "", (local or "")).upper() or None


def _coord(r):
    lat = int(r["lat"]) / 1e6
    lon = int(r["lon"]) / 1e6
    return lat, lon


def analisar(registros):
    """Anota cada registro com ``_conflito``/``_quarentena`` (str ou None).

    - QUARENTENA: coordenada fora da caixa de GO, latitude == longitude
      (dado degenerado) ou fora do conjunto homogeneo do mesmo (via, km).
    - CONFLITO: o mesmo ``codigo_equipamento`` publicado em vias diferentes
      (ex.: 174L5R129 em GO-050 e GO-174) -> nao escolhemos uma das linhas.

    Devolve ``(registros, conflitos, quarentenas)``; tambem muta os dicts.
    """
    for r in registros:
        r.setdefault("_conflito", None)
        r.setdefault("_quarentena", None)

    # 1) quarentena por caixa / degeneracao
    for r in registros:
        lat, lon = _coord(r)
        if abs(lat - lon) < 1e-9:
            r["_quarentena"] = ("latitude igual a longitude (%.6f)" % lat)
        elif not (GO_LAT_MIN <= lat <= GO_LAT_MAX
                  and GO_LON_MIN <= lon <= GO_LON_MAX):
            r["_quarentena"] = ("coordenada fora da UF GO: %.6f,%.6f" % (lat, lon))

    # 2) conflito: mesmo codigo em vias diferentes
    por_codigo = {}
    for r in registros:
        por_codigo.setdefault(r["cod"], []).append(r)
    conflitos = {}
    for cod, grupo in por_codigo.items():
        vias = sorted({_via(r["local"]) for r in grupo})
        if len(vias) > 1:
            motivo = ("codigo %s publicado em vias distintas: %s"
                      % (cod, ", ".join(v for v in vias if v)))
            conflitos[cod] = motivo
            for r in grupo:
                r["_conflito"] = motivo

    # 3) quarentena por divergencia dentro do mesmo (via, km)
    por_trecho = {}
    for r in registros:
        chave = (_via(r["local"]), _km_decimal(r))
        if chave[0] is not None and chave[1] is not None:
            por_trecho.setdefault(chave, []).append(r)
    quarentenas_extra = {}
    for chave, grupo in por_trecho.items():
        coords = [(_coord(r)) for r in grupo]
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        if (max(lats) - min(lats) > LIMITE_DIVERGENCIA_GRAUS
                or max(lons) - min(lons) > LIMITE_DIVERGENCIA_GRAUS):
            motivo = ("coordenadas divergentes no mesmo trecho %s km %s "
                      "(variacao %.3f/%.3f graus)"
                      % (chave[0], chave[1],
                         max(lats) - min(lats), max(lons) - min(lons)))
            quarentenas_extra[chave] = motivo
            for r in grupo:
                if not r["_quarentena"]:
                    r["_quarentena"] = motivo

    quarentenas = [r for r in registros if r["_quarentena"]]
    return registros, conflitos, quarentenas


# ---------------------------------------------------------------------------
# Conector
# ---------------------------------------------------------------------------
class ColetorGOINFRA(ColetorBase):

    FONTE = {
        "nome": "GOINFRA - Equipamentos de monitoramento (GO)",
        "organizacao": ("Agencia Goiana de Infraestrutura e Transportes "
                        "(GOINFRA)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://goias.gov.br/goinfra/",
        "documentacao_url": ("https://goias.gov.br/goinfra/"
                             "relatorio-de-equipamentos-de-monitoramento-"
                             "da-goinfra/"),
        "licenca": "documento oficial publicado",
        "periodicidade_declarada": "irregular (por publicacao datada)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Relatorio de equipamentos de monitoramento (PDF/XLSX)",
        "url_recurso": ("https://goias.gov.br/goinfra/"
                        "relatorio-de-equipamentos-de-monitoramento-da-"
                        "goinfra/"),
        "formato_origem": "pdf|xlsx|csv",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        "status_integracao": "ok",
    }

    URL_PAGINA = RECURSO["url_recurso"]
    # Ultimo recurso (NAO e a fonte de verdade): versao de 02/10/2026.
    URL_FALLBACK = ("https://goias.gov.br/goinfra/wp-content/uploads/sites/"
                    "77/2026/10/Lista_de_Equipamento_02_10_2026.xlsx-"
                    "Equipamentos-Ativos.pdf")

    # -- resolucao de URL -------------------------------------------------
    @classmethod
    def resolver_url(cls):
        """URL do relatorio mais recente descoberta na pagina; fallback fixo."""
        try:
            html = http.baixar(cls.URL_PAGINA)[0]
            url, _todas = descobrir_url_recurso(html.decode("utf-8", "replace"))
            if url:
                return url
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        return http.baixar(ref)[0]

    def carregar(self, origem):
        """origem: caminho local (PDF/XLSX/CSV/txt) OU URL. 4-tupla."""
        local = bool(origem) and os.path.exists(origem)
        ref = origem or self.resolver_url()
        if local:
            ext = os.path.splitext(ref)[1].lower()
            conteudo = self._ler(ref)
        else:
            conteudo, _headers, _url_final = http.baixar(ref)
            ext = os.path.splitext(ref.split("?")[0])[1].lower()

        if ext in (".txt", ".text"):
            texto = conteudo.decode("utf-8", "replace")
            registros = extrair_registros(texto)
            analisar(registros)
            return conteudo, ".txt", "text/plain; charset=utf-8", registros
        if conteudo[:2] == b"PK" or ext in (".xlsx", ".xls"):
            registros = pl.dicts_de_linhas(pl.ler_xlsx(conteudo))
            return conteudo, ".xlsx", MIME_XLSX, registros
        if ext == ".csv":
            return (conteudo, ".csv", "text/csv; charset=utf-8",
                    pl.ler_csv(conteudo))
        # padrao: PDF
        texto = ler_pdf_texto_layout(conteudo)
        registros = extrair_registros(texto)
        analisar(registros)
        return conteudo, ".pdf", MIME_PDF, registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "cod")

    def normalizar(self, idx, raw):
        cod = nz.pick(raw, "cod")
        lat, lon = None, None
        if raw.get("lat") is not None and raw.get("lon") is not None:
            try:
                lat = int(raw["lat"]) / 1e6
                lon = int(raw["lon"]) / 1e6
            except (TypeError, ValueError):
                lat, lon = None, None
        if not cod and lat is None and lon is None:
            return None

        conflito = raw.get("_conflito")
        quarentena = raw.get("_quarentena")
        # coordenada incoerente nao vira posicao confiavel: qualidade
        # "conflitante" (dominio QUALIDADE_POSICAO) = quarentena, sem
        # descartar o registro nem a coordenada publicada.
        qualidade = "conflitante" if (conflito or quarentena) else "oficial"

        obs = self._observacoes(raw, conflito, quarentena)
        return {
            "identificador": cod,
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": qualidade,
            "metodo_obtencao": "publicacao GOINFRA (relatorio de equipamentos)",
            "uf": "GO",
            "municipio_nome": raw.get("municipio"),
            "via_codigo": _via(raw.get("local")),
            "via_tipo": "estadual",
            "km": _km_decimal(raw),
            "tipo_pista": raw.get("faixa"),
            "situacao": None,   # afericao nao prova operacao (contrato)
            "tipo_radar": self._tipo_radar(raw.get("tipo")),
            "numero_serie": raw.get("serie"),
            "fabricante": None,
            "modelo": None,
            "velocidade_geral": nz.to_velocidade(raw.get("velocidade")),
            "sentido": nz.normalizar_sentido(raw.get("sentido_cd")),
            "sentido_original": raw.get("sentido_cd"),
            "observacoes": obs or None,
        }

    @staticmethod
    def _tipo_radar(tipo):
        t = (tipo or "").lower()
        if "radar" in t or "lombada" in t:
            return "fixo"
        return "desconhecido"

    @staticmethod
    def _observacoes(raw, conflito, quarentena):
        km_orig = _km_original(raw)
        partes = []
        if quarentena:
            partes.append("QUARENTENA: %s" % quarentena)
        if conflito:
            partes.append("CONFLITO: %s" % conflito)
        if raw.get("tipo"):
            partes.append("Tipo: %s" % raw["tipo"])
        if raw.get("faixa"):
            partes.append("Faixa: %s" % raw["faixa"])
        if km_orig:
            partes.append("KM original: %s" % km_orig)
        if raw.get("sentido_descrito"):
            partes.append("Sentido descrito: %s" % raw["sentido_descrito"])
        if raw.get("sre"):
            partes.append("Codigo SRE: %s" % raw["sre"])
        if raw.get("lote"):
            partes.append("Lote: %s" % raw["lote"])
        if raw.get("nota_instalacao"):
            partes.append("Nota de instalacao: %s" % raw["nota_instalacao"])
        if raw.get("sei"):
            partes.append("No SEI: %s" % raw["sei"])
        if raw.get("estudo_tecnico"):
            partes.append("Estudo tecnico: %s" % raw["estudo_tecnico"])
        if raw.get("data_autorizacao"):
            partes.append("Data autorizacao: %s" % raw["data_autorizacao"])
        if raw.get("data_ativo"):
            partes.append("Data ativo: %s" % raw["data_ativo"])
        if raw.get("afericao_valida_ate"):
            partes.append("Afericao valida ate: %s (validade metrologica)"
                          % raw["afericao_valida_ate"])
        if raw.get("velocidade"):
            partes.append("Velocidade publicada: %s km/h" % raw["velocidade"])
        return "; ".join(partes)
