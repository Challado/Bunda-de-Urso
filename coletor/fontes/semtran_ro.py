# -*- coding: utf-8 -*-
"""Fonte RO - SEMTRAN Porto Velho, radares fixos (fiscalizacao eletronica).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos

A pagina publica o PDF de dados do cadastro de radares fixos:
  "Dados dos Radares fixos atualizados 2026.1.pdf"
cuja URL e DESCOBERTA na propria pagina (o nome do arquivo muda a cada
versao, entao a URL datada nunca e chumbada como fonte unica; o fallback
serve apenas de rede de seguranca).

O PDF (gerado por Google Sheets) e um relatorio tabular com as colunas
reais:
  TIPO, NUMERO_SERIE, COD_FAIXA_CLIENTE, NUM_FAIXA, NOME_PISTA,
  DATA_AFERICAO, DATA_VALIDADE, POSICAO_LAT, POSICAO_LON, SIGLA
-> 85 linhas de dados (radares fixos), conforme a versao 2026.1.

LIMITES REAIS (nao escondidos):
  1. As colunas POSICAO_LAT / POSICAO_LON vem publicadas num formato
     corrompido (ex.: "-876.651.999.999.999.000"), FORA de qualquer faixa
     valida de coordenada. O conector NAO cria POSICAO_GEOGRAFICA a partir
     disso (nada e inferido): latitude/longitude ficam NULOS e o texto bruto
     e preservado em ``observacoes``.
  2. O PDF usa fontes Type0/Identity-H com subset e ToUnicode CMap. A
     extracao "best-effort" da stdlib (``planilha.ler_pdf_texto``) NAO le
     este arquivo: devolve codigos de glifo. Por isso o conector traz um
     extrator ToUnicode-aware (somente biblioteca padrao) que reconstroi o
     texto do PDF antes do parsing.

Semantica: e um cadastro de radar INSTALADO (rotulo da fonte: "Radares
fixos"), por isso vira PONTO_FISCALIZACAO tipo "fixo". Nada e inventado:
campo ausente vira NULL.

Aceita arquivo LOCAL (PDF de fixture, ou .txt com o texto ja extraido) para
testes offline.
"""
import os
import re
import zlib

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_PDF = "application/pdf"
MIME_TXT = "text/plain"

PAGINA = ("https://semtran.portovelho.ro.gov.br/pagina/"
          "fiscalizacao-eletronica-radares-fixos")
# Rede de seguranca (URL datada): a fonte real e DESCOBERTA na pagina.
URL_FALLBACK = ("https://semtran.portovelho.ro.gov.br/uploads/arquivos/"
                "Dados%20dos%20Radares%20fixos%20atualizados%202026.1.pdf")

# Colunas reais do relatorio (ordem do cabecalho -> ordem das linhas de dados,
# que tem uma coluna extra de indice no inicio).
COLUNAS = ("ID", "TIPO", "NUMERO_SERIE", "COD_FAIXA_CLIENTE", "NUM_FAIXA",
           "NOME_PISTA", "DATA_AFERICAO", "DATA_VALIDADE", "POSICAO_LAT",
           "POSICAO_LON", "SIGLA")


# --------------------------------------------------------------------------
# Extrator de texto de PDF (ToUnicode-aware, somente stdlib)
# --------------------------------------------------------------------------
def _pdf_objetos(dados):
    objs = {}
    for m in re.finditer(rb"(?m)^\s*(\d+)\s+0\s+obj\b(.*?)\bendobj", dados,
                         re.S):
        objs[int(m.group(1))] = m.group(2)
    return objs


def _pdf_stream(body):
    m = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S)
    if not m:
        return None
    bruto = m.group(1)
    if b"FlateDecode" in body[:m.start()]:
        try:
            return zlib.decompress(bruto)
        except zlib.error:
            return bruto
    return bruto


def _pdf_cmap(txt):
    """CMap ToUnicode -> dict {codigo_glifo: str unicode}."""
    mapa = {}
    for bloco in re.findall(rb"beginbfchar(.*?)endbfchar", txt, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", bloco):
            mapa[int(a, 16)] = "".join(
                chr(int(b[i:i + 4], 16)) for i in range(0, len(b), 4))
    for bloco in re.findall(rb"beginbfrange(.*?)endbfrange", txt, re.S):
        # forma array: <lo> <hi> [<u1> <u2> ...]
        for m in re.finditer(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", bloco,
                re.S):
            lo = int(m.group(1), 16)
            itens = re.findall(rb"<([0-9A-Fa-f]+)>", m.group(3))
            for i, it in enumerate(itens):
                mapa[lo + i] = "".join(
                    chr(int(it[j:j + 4], 16)) for j in range(0, len(it), 4))
        # forma simples: <lo> <hi> <destino>
        for a, b, c in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*"
                rb"<([0-9A-Fa-f]+)>", bloco):
            lo, hi, base = int(a, 16), int(b, 16), int(c, 16)
            for k in range(lo, hi + 1):
                mapa[k] = chr(base + (k - lo))
    return mapa


_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
        b"(": b"(", b")": b")", b"\\": b"\\"}
_WS = re.compile(rb"[\x00\t\n\f\r ]+")


def _pdf_ler_literal(dados, i):
    """Le um literal PDF '(...)' (com escapes/aninhamento). -> (bytes, fim)."""
    i += 1
    prof = 1
    buf = bytearray()
    n = len(dados)
    while i < n:
        c = dados[i:i + 1]
        if c == b"\\":
            j = i + 1
            if j < n:
                nx = dados[j:j + 1]
                if nx.isdigit():
                    k = 0
                    oct_ = b""
                    while j < n and k < 3 and dados[j:j + 1].isdigit():
                        oct_ += dados[j:j + 1]
                        j += 1
                        k += 1
                    buf.append(int(oct_, 8) & 0xFF)
                    i = j
                    continue
                if nx in _ESC:
                    buf += _ESC[nx]
                    i = j + 1
                    continue
                if nx in (b"\n", b"\r"):
                    i = j + 1
                    if dados[i:i + 1] == b"\n":
                        i += 1
                    continue
                buf += nx
                i = j + 1
                continue
            i += 1
            continue
        if c == b"(":
            prof += 1
            buf += c
            i += 1
            continue
        if c == b")":
            prof -= 1
            if prof == 0:
                return bytes(buf), i + 1
            buf += c
            i += 1
            continue
        buf += c
        i += 1
    return bytes(buf), i


def _pdf_ler_hex(dados, i):
    j = dados.find(b">", i)
    if j < 0:
        return b"", len(dados)
    h = re.sub(rb"[^0-9A-Fa-f]", b"", dados[i + 1:j])
    if len(h) % 2:
        h += b"0"
    return bytes.fromhex(h.decode()), j + 1


def _pdf_tokens(dados):
    i = 0
    n = len(dados)
    while i < n:
        m = _WS.match(dados, i)
        if m:
            i = m.end()
            continue
        c = dados[i:i + 1]
        if c == b"(":
            s, i = _pdf_ler_literal(dados, i)
            yield ("str", s)
            continue
        if c == b"<":
            if dados[i:i + 2] == b"<<":
                i += 2
                continue
            s, i = _pdf_ler_hex(dados, i)
            yield ("str", s)
            continue
        if c == b"[":
            i += 1
            yield ("[", b"")
            continue
        if c == b"]":
            i += 1
            yield ("]", b"")
            continue
        if c == b"/":
            m = re.match(rb"/([^\s/\[\]<>(){}]+)", dados[i:])
            yield ("name", m.group(1))
            i += m.end()
            continue
        m = re.match(rb"[-+]?[0-9]*\.?[0-9]+", dados[i:])
        if m:
            yield ("num", m.group(0))
            i += m.end()
            continue
        m = re.match(rb"[A-Za-z'\"*]+", dados[i:])
        if m:
            yield ("op", m.group(0))
            i += m.end()
            continue
        i += 1


def extrair_texto_pdf(conteudo):
    """Extrai o texto de um PDF com fontes Type0/Identity-H (stdlib).

    Devolve uma lista de "celulas" (linhas na ordem de leitura; cada operador
    de posicionamento Td/TD/Tm/T* inicia uma nova celula). Se o PDF NAO tiver
    CMaps ToUnicode/Type0, cai no extrator padrao da stdlib
    (``planilha.ler_pdf_texto``) e devolve o texto quebrado em linhas.
    """
    objs = _pdf_objetos(conteudo)
    mapas = {}
    for num, body in objs.items():
        m = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", body)
        if m:
            s = _pdf_stream(objs.get(int(m.group(1)), b""))
            if s:
                mapas[num] = _pdf_cmap(s)
    if not mapas:
        texto = pl.ler_pdf_texto(conteudo)
        return [l.strip() for l in texto.splitlines() if l.strip()]
    nome2obj = {}
    for _num, body in objs.items():
        fm = re.search(rb"/Font\s*<<(.*?)>>", body, re.S)
        if fm:
            for nm, on in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", fm.group(1)):
                nome2obj.setdefault(nm.decode(), int(on))
    conteudo_streams = b""
    for _num, body in objs.items():
        if b"/Type" in body and b"/Page" in body and b"/Contents" in body:
            for c in re.findall(rb"/Contents\s+(\d+)\s+0\s+R", body):
                s = _pdf_stream(objs.get(int(c), b""))
                if s:
                    conteudo_streams += s + b"\n"
    fonte = None

    def decodifica(bruto):
        if len(bruto) % 2:
            bruto += b"\x00"
        mp = mapas.get(fonte, {})
        return "".join(mp.get((bruto[i] << 8) | bruto[i + 1], "")
                       for i in range(0, len(bruto), 2))

    oper = []
    linha = []
    linhas = []
    em_array = False
    arr = []
    for tipo, valor in _pdf_tokens(conteudo_streams):
        if tipo == "[":
            em_array = True
            arr = []
            continue
        if tipo == "]":
            em_array = False
            oper.append(("arr", arr))
            continue
        if tipo in ("name", "num", "str"):
            if em_array and tipo == "str":
                arr.append(valor)
            else:
                oper.append((tipo, valor))
            continue
        if tipo == "op":
            op = valor.decode()
            if op == "Tf":
                nomes = [v for k, v in oper if k == "name"]
                if nomes:
                    fonte = nome2obj.get(nomes[-1].decode())
            elif op == "Tj":
                ss = [v for k, v in oper if k == "str"]
                if ss:
                    linha.append(decodifica(ss[-1]))
            elif op == "TJ":
                for k, v in oper:
                    if k == "arr":
                        linha.append("".join(decodifica(x) for x in v))
            elif op in ("Td", "TD", "T*", "'", '"'):
                linhas.append("".join(linha))
                linha = []
            oper = []
    linhas.append("".join(linha))
    return [l.strip() for l in linhas if l.strip()]


# --------------------------------------------------------------------------
# Conector
# --------------------------------------------------------------------------
class ColetorSEMTRANRO(ColetorBase):

    FONTE = {
        "nome": "SEMTRAN Porto Velho - Fiscalizacao eletronica (radares fixos)",
        "organizacao": ("Secretaria Municipal de Transportes e Mobilidade "
                        "(SEMTRAN) - Porto Velho/RO"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://semtran.portovelho.ro.gov.br/",
        "documentacao_url": PAGINA,
        "licenca": "documento oficial publicado",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Dados dos Radares fixos (PDF atualizado)",
        "url_recurso": PAGINA,
        "formato_origem": "pdf",
        "periodicidade_segundos": 2592000,   # ~30 dias
        # cadastro oficial, porem as coordenadas publicadas sao inutilizaveis
        "status_integracao": "parcial",
    }

    PAGINA = PAGINA
    URL_FALLBACK = URL_FALLBACK

    # -- descoberta (offline-testavel) ------------------------------------
    @staticmethod
    def _candidato(href):
        h = (href or "").lower()
        if ".pdf" not in h:
            return None
        if "radar" not in h and "fiscalizacao-eletronica" not in h:
            return None
        # evita a Carta de Servicos / outros PDFs administrativos
        if "carta" in h and "servico" in h:
            return None
        return href

    @classmethod
    def descobrir_url_arquivo(cls, html):
        """Escolhe o PDF de dados dos radares na pagina (o mais recente)."""
        if isinstance(html, bytes):
            html = html.decode("utf-8", "replace")
        urls = []
        for m in re.finditer(r'href="([^"]+\.pdf)"', html or "", re.I):
            cand = cls._candidato(m.group(1))
            if cand:
                urls.append(cand)
        # prioriza "dados ... atualizad" (arquivo de dados atualizado)
        def chave(u):
            s = u.lower()
            return (("dados" in s and "atualiz" in s),
                    "dados" in s,
                    "fiscalizacao-eletronica" in s,
                    len(s))
        if urls:
            return sorted(set(urls), key=chave, reverse=True)[0]
        return cls.URL_FALLBACK

    @classmethod
    def resolver_url(cls):
        """Segue a pagina oficial e descobre a URL atual do PDF de dados."""
        try:
            html = http.baixar(cls.PAGINA)[0]
        except Exception:                                  # noqa: BLE001
            return cls.URL_FALLBACK
        return cls.descobrir_url_arquivo(html)

    # -- carregar ---------------------------------------------------------
    def carregar(self, origem):
        """origem: caminho local OU None/URL.

        Uma origem remota (a propria URL da pagina) dispara a DESCOBERTA do
        PDF de dados; so um link direto terminado em ".pdf" e usado tal e
        qual. Nunca tratamos a URL da pagina como se fosse o PDF.
        """
        local = bool(origem) and os.path.exists(str(origem))
        if local:
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            alvo = str(origem or "")
            if alvo.lower().split("?")[0].endswith(".pdf"):
                url = origem
            else:
                url = self.resolver_url()
            conteudo, _headers, _url_final = http.baixar(url)
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext == ".txt" or (ext != ".pdf" and conteudo[:4] != b"%PDF"):
            celulas = [l.strip() for l in
                       conteudo.decode("utf-8", "replace").splitlines()
                       if l.strip()]
            return conteudo, ext or ".txt", MIME_TXT, \
                self.extrair_registros(celulas)
        celulas = extrair_texto_pdf(conteudo)
        return conteudo, ".pdf", MIME_PDF, self.extrair_registros(celulas)

    # -- parsing ----------------------------------------------------------
    @classmethod
    def extrair_registros(cls, celulas):
        """Reconstroi as linhas do relatorio a partir das celulas extraidas."""
        registros = []
        i = 0
        n = len(celulas)
        while i < n - 1:
            if re.fullmatch(r"\d{1,4}", celulas[i] or "") and \
                    re.fullmatch(r"FSC\d*", celulas[i + 1] or ""):
                linha = celulas[i:i + len(COLUNAS)]
                if len(linha) == len(COLUNAS):
                    registros.append(dict(zip(COLUNAS, linha)))
                    i += len(COLUNAS)
                    continue
            i += 1
        return registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return (nz.pick(raw, "COD_FAIXA_CLIENTE", "NUMERO_SERIE")
                or None)

    @staticmethod
    def _coordenada(texto):
        """Coordenada publicada FORA de faixa NAO vira GPS (None).

        A fonte publica POSICAO_LAT/POSICAO_LON num formato corrompido; por
        isso o valor so e aceito quando esta, de fato, numa faixa valida.
        """
        val = nz.to_float(texto)
        return val

    def normalizar(self, idx, raw):
        lat = self._coordenada(nz.pick(raw, "POSICAO_LAT"))
        lon = self._coordenada(nz.pick(raw, "POSICAO_LON"))
        if lat is None or not (-90.0 <= lat <= 90.0):
            lat = None
        if lon is None or not (-180.0 <= lon <= 180.0):
            lon = None
        obs = "; ".join(x for x in (
            ("Tipo na fonte: %s" % raw.get("TIPO")) if raw.get("TIPO") else None,
            ("Cod. faixa: %s" % raw.get("COD_FAIXA_CLIENTE"))
            if raw.get("COD_FAIXA_CLIENTE") else None,
            ("Faixa: %s" % raw.get("NUM_FAIXA")) if raw.get("NUM_FAIXA")
            else None,
            ("Sigla: %s" % raw.get("SIGLA")) if raw.get("SIGLA") else None,
            ("Data de afericao: %s" % raw.get("DATA_AFERICAO"))
            if raw.get("DATA_AFERICAO") else None,
            ("Data de validade: %s" % raw.get("DATA_VALIDADE"))
            if raw.get("DATA_VALIDADE") else None,
            ("POSICAO_LAT publicada (fora de faixa, nao georreferenciada): %s"
             % raw.get("POSICAO_LAT")) if raw.get("POSICAO_LAT") else None,
            ("POSICAO_LON publicada (fora de faixa, nao georreferenciada): %s"
             % raw.get("POSICAO_LON")) if raw.get("POSICAO_LON") else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao SEMTRAN Porto Velho (dados dos "
                                "radares fixos, 2026.1)"),
            "uf": "RO",
            "municipio_nome": "Porto Velho",
            "municipio_ibge": "1100205",
            "via_codigo": nz.pick(raw, "NOME_PISTA"),
            "via_tipo": "municipal",
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            "tipo_radar": "fixo",
            "numero_serie": nz.pick(raw, "NUMERO_SERIE"),
            "fabricante": None,
            "modelo": None,
            "sentido": None,
            "sentido_original": None,
            "observacoes": obs,
        }
