# -*- coding: utf-8 -*-
"""Leitores de arquivo com a biblioteca padrao (sem dependencias externas).

Suporta:
  - XLSX (zipfile + xml.etree, honrando a referencia de coluna das celulas);
  - CSV (csv com deteccao simples de delimitador);
  - HTML com tabelas (html.parser);
  - PDF simples: extracao "best-effort" de texto (zlib + operadores Tj/TJ).

Tambem oferece utilitarios de coordenada: par lat/lon em varios formatos e
conversao UTM (SIRGAS 2000 / zona 23S e demais) para graus decimais.

Nada aqui acessa a rede: recebe bytes ja carregados pelo conector.
"""
import csv
import io
import math
import re
import zipfile
import zlib
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# --------------------------------------------------------------------------
# XLSX
# --------------------------------------------------------------------------
def _indice_coluna(ref):
    """'AB12' -> 27 (indice 0-based); None se nao houver letras."""
    m = re.match(r"([A-Z]+)", (ref or "").upper())
    if not m:
        return None
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _abas(workbook_xml, rels_xml):
    rels = ET.fromstring(rels_xml)
    alvo = {}
    for r in rels:
        t = r.get("Target") or ""
        alvo[r.get("Id")] = t
    wb = ET.fromstring(workbook_xml)
    out = []
    for sh in wb.iter(_NS + "sheet"):
        nome = sh.get("name")
        t = alvo.get(sh.get(_RNS + "id"), "")
        if t.startswith("/"):
            t = t[1:]
        elif not t.startswith("xl/"):
            t = "xl/" + t.lstrip("/")
        out.append((nome, t))
    return out


def ler_xlsx(conteudo, aba=None):
    """Retorna a aba pedida (por nome) ou a primeira como lista de linhas.

    Cada linha e uma lista de str na ordem das colunas (celulas vazias
    preenchidas com ""), usando a referencia A1 de cada celula -- por isso
    celulas ausentes NAO deslocam as demais.
    """
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    nomes = z.namelist()
    compartilhadas = []
    if "xl/sharedStrings.xml" in nomes:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root:
            compartilhadas.append(
                "".join(t.text or "" for t in si.iter(_NS + "t")))
    abas = _abas(z.read("xl/workbook.xml"),
                 z.read("xl/_rels/workbook.xml.rels"))
    alvo = None
    for nome, caminho in abas:
        if aba is None or (nome or "").strip() == aba:
            alvo = caminho
            break
    if alvo is None and abas:
        alvo = abas[0][1]

    root = ET.fromstring(z.read(alvo))
    linhas = []
    for row in root.iter(_NS + "row"):
        por_col = {}
        sequencia = 0
        for c in row:
            ci = _indice_coluna(c.get("r"))
            if ci is None:
                ci = sequencia
            sequencia = ci + 1
            t = c.get("t")
            v = c.find(_NS + "v")
            isv = c.find(_NS + "is")
            if t == "inlineStr" and isv is not None:
                txt = "".join(x.text or "" for x in isv.iter(_NS + "t"))
            elif v is not None:
                txt = v.text
                if t == "s" and txt is not None:
                    try:
                        txt = compartilhadas[int(txt)]
                    except (ValueError, IndexError):
                        pass
            else:
                txt = None
            por_col[ci] = "" if txt is None else str(txt)
        largura = (max(por_col) + 1) if por_col else 0
        linhas.append([por_col.get(i, "") for i in range(largura)])
    return linhas


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def ler_csv(conteudo):
    """Lista de dicts (cabecalho na primeira linha). Detecta ';' ou ','."""
    texto = conteudo.decode("utf-8-sig") if isinstance(conteudo, bytes) \
        else conteudo
    linhas = texto.splitlines()
    primeira = linhas[0] if linhas else ""
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=delim))


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
class _ColetorTabelas(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabelas = []
        self._tab = None
        self._linha = None
        self._cel = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tab = []
        elif tag == "tr" and self._tab is not None:
            self._linha = []
        elif tag in ("td", "th") and self._linha is not None:
            # HTML permite omitir </td>; o DER-ES publica assim o codigo.
            if self._cel is not None:
                self.handle_endtag("td")
            self._cel = []
        elif tag == "br" and self._cel is not None:
            self._cel.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cel is not None:
            self._linha.append("".join(self._cel).strip())
            self._cel = None
        elif tag == "tr" and self._linha is not None:
            if self._cel is not None:
                self.handle_endtag("td")
            self._tab.append(self._linha)
            self._linha = None
        elif tag == "table" and self._tab is not None:
            self.tabelas.append(self._tab)
            self._tab = None

    def handle_data(self, data):
        if self._cel is not None:
            self._cel.append(data)


def ler_tabelas_html(conteudo):
    """Lista de tabelas; cada tabela e uma lista de linhas de celulas str."""
    texto = conteudo.decode("utf-8", "replace") if isinstance(conteudo, bytes) \
        else conteudo
    p = _ColetorTabelas()
    p.feed(texto)
    return p.tabelas


# --------------------------------------------------------------------------
# PDF (best-effort, apenas texto de streams simples)
# --------------------------------------------------------------------------
def ler_pdf_texto(conteudo):
    """Extrai o texto mostrado por operadores Tj/TJ de PDFs com stream
    FlateDecode/sem filtro. Suficiente para relatorios tabulares simples."""
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("latin-1", "replace")
    pedacos = []
    for bruto in re.findall(rb"stream\r?\n(.*?)endstream", conteudo, re.S):
        try:
            dados = zlib.decompress(bruto)
        except Exception:                                  # noqa: BLE001
            dados = bruto
        if b"BT" not in dados and b"Tj" not in dados and b"TJ" not in dados:
            continue
        for frag in re.finditer(
                rb"\[(?:[^\[\]\\]|\\.)*\]\s*TJ|\((?:[^()\\]|\\.)*\)\s*Tj",
                dados, re.S):
            txt = "".join(
                p[1:-1].decode("latin-1")
                for p in re.findall(rb"\((?:[^()\\]|\\.)*\)", frag.group(0)))
            if txt:
                pedacos.append(txt)
    return " ".join(pedacos)


# --------------------------------------------------------------------------
# Linhas -> dicts com cabecalho
# --------------------------------------------------------------------------
def dicts_de_linhas(linhas, cabecalho=None):
    """Converte linhas (listas) em dicts usando a primeira linha nao vazia
    como cabecalho, ou o cabecalho informado."""
    if cabecalho is None:
        for ln in linhas:
            if any(str(x).strip() for x in ln):
                cabecalho = [str(x).strip() for x in ln]
                linhas = linhas[linhas.index(ln) + 1:]
                break
        else:
            return []
    out = []
    for ln in linhas:
        if not any(str(x).strip() for x in ln):
            continue
        d = {}
        for j, h in enumerate(cabecalho):
            if not h:
                continue
            d[h] = ln[j] if j < len(ln) else ""
        out.append(d)
    return out


# --------------------------------------------------------------------------
# Coordenadas
# --------------------------------------------------------------------------
def _numero(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\u2212", "-").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_coordenadas(texto):
    """Aceita 'lat / lon' (decimal BR) ou 'lat, lon' (decimal ponto).

    Retorna (lat, lon) ou (None, None) quando ausente/invalido.
    """
    if texto is None:
        return None, None
    s = str(texto).strip().replace("\u2212", "-")
    if not s:
        return None, None
    if "/" in s:
        a, _, b = s.partition("/")
    elif "," in s:
        partes = s.split(",")
        if len(partes) == 2:
            a, b = partes
        else:
            a, b = s.rsplit(",", 1)
    else:
        return None, None
    lat, lon = _numero(a), _numero(b)
    if lat is None or lon is None:
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None
    return lat, lon


def parse_ponto_utm(texto):
    """Extrai (easting, northing) de 'POINT (E N)' ou 'E N'."""
    if texto is None:
        return None
    m = re.search(r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)",
                  str(texto), re.I)
    if not m:
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*$",
                     str(texto))
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def utm_para_geografico(easting, northing, zona, hemisferio_sul=True):
    """Conversao inversa UTM -> (lat, lon) em graus (WGS84/SIRGAS2000).

    Implementacao pela serie de Snyder, sem dependencias. Usada quando a
    fonte publica a coordenada projetada com CRS documentado.
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    k0 = 0.9996
    e0 = 500000.0
    n0 = 10000000.0 if hemisferio_sul else 0.0
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = easting - e0
    y = northing - n0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = ep2 * math.cos(phi1) ** 2
    t1 = math.tan(phi1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2)
        * d ** 6 / 720)
    lon0 = math.radians(zona * 6 - 183)
    lon = lon0 + (d
                  - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2
                     + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def serial_excel_para_iso(serial):
    """Converte o numero de serie de data do Excel em 'YYYY-MM-DD'."""
    n = _numero(serial)
    if n is None or n < 1 or n > 60000:
        return None
    import datetime
    base = datetime.date(1899, 12, 30)
    try:
        return (base + datetime.timedelta(days=int(n))).isoformat()
    except (ValueError, OverflowError):
        return None
