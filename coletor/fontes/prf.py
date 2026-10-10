# -*- coding: utf-8 -*-
"""Fontes F05/F06/F07 - PRF (Policia Rodoviaria Federal).

As paginas gov.br da PRF publicam o conteudo como TABELA HTML embutida na
propria pagina (nao ha arquivo de dataset para baixar).  Por isso o coletor
le a pagina e extrai as tabelas com html.parser da stdlib (sem BeautifulSoup
nem lxml); urllib tambem e stdlib.  Nada aqui roda em tempo de requisicao da
API.

Evidencia coletada em 10/10/2026 (curl -sSL -A "RadarBrasil/1.0"):

  F05 radares fixos
    https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
    HTTP 200.  A pagina NAO traz a tabela no HTML: embute dois iframes
      <iframe title="MAPA DE RADARES FIXOS" src="https://mapas-html.vercel.app/">
      <iframe title="TABELA DE RADARES FIXOS" src="https://mapas-html.vercel.app/tabela.html">
    O app do iframe monta a tabela em JavaScript a partir de um Google Apps
    Script referenciado na pagina do mapa
      https://script.google.com/macros/s/AKfycbw.../exec  (JSON)
    Este coletor segue o iframe MAPA -> extrai a URL do Apps Script -> baixa
    o JSON de registros (application/json, HTTP 200, ~1590 registros com
    IDENTIFICADOR/LATITUDE/LONGITUDE).  Tambem aceita, para testes, uma
    tabela HTML estatica (parseada com html.parser).

  F06 radares portateis
    https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/lista-de-radares
    HTTP 200.  TRES <table> static; a maior tem 270 linhas de dados com as
    colunas "IDENTIFICADOR DO EQUIPAMENTO" e "Nº DE SÉRIE".  NAO ha posicao
    nem hora: e identificador administrativo + numero de serie (spec F06).

  F07 trechos criticos
    https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/trechos-criticos
    HTTP 200.  A pagina lista, em <a>, varias planilhas publicadas do Google
    ("Lista valida de ... a ...").  A mais recente e a "Lista valida a partir
    de 03/10/2026".  A planilha publicada (pubhtml) hoje e renderizada por
    JavaScript (widget), sem tabela estatica; o dado e obtido pela exportacao
    CSV que a propria publicacao disponibiliza (output=csv), lida com o
    modulo csv da stdlib.  Colunas: ESTADO (UF), RODOVIA (BR), KM INICIAL,
    KM FINAL -> TRECHO_ELEGIVEL (T30), nunca operacao confirmada.
"""
import csv
import io
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


# --------------------------------------------------------------------------
# utilidades de download e de parsing HTML (stdlib)
# --------------------------------------------------------------------------

def _baixar(url):
    """GET simples com o User-Agent do projeto (so no coletor)."""
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.DEFAULT_TIMEOUT) as resp:
        return resp.read()


def _limpa(texto):
    return " ".join(texto.split())


class _ExtratorTabelas(HTMLParser):
    """Extrai tabelas HTML (linhas/celulas) e iframes de uma pagina.

    Sem dependencia externa: usa html.parser da stdlib (regra da tarefa).
    Celulas preservam o texto visivel; nao interpretamos CSS nem JS.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabelas = []          # lista de tabelas; tabela = lista de linhas
        self.iframes = []          # [(title, src)]
        self.ancoras = []          # [(href, texto)]
        self._tabela = None
        self._linha = None
        self._celula = None
        self._ancora = None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "table":
            self._tabela = []
        elif tag == "tr" and self._tabela is not None:
            self._linha = []
        elif tag in ("td", "th") and self._linha is not None:
            self._celula = []
        elif tag == "iframe":
            self.iframes.append((_limpa(d.get("title") or ""),
                                 (d.get("src") or "").strip()))
        elif tag == "a":
            self._ancora = [d.get("href") or "", []]
        elif tag == "br" and self._celula is not None:
            self._celula.append(" ")

    def handle_data(self, data):
        if self._celula is not None:
            self._celula.append(data)
        if self._ancora is not None:
            self._ancora[1].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celula is not None:
            self._linha.append(_limpa("".join(self._celula)))
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            self._tabela.append(self._linha)
            self._linha = None
        elif tag == "table" and self._tabela is not None:
            self.tabelas.append(self._tabela)
            self._tabela = None
        elif tag == "a" and self._ancora is not None:
            self.ancoras.append((self._ancora[0], _limpa("".join(self._ancora[1]))))
            self._ancora = None


def _tabela_para_dicts(linhas):
    """Primeira linha nao vazia = cabecalho; demais = registros (dict)."""
    linhas = [l for l in linhas if any((c or "").strip() for c in l)]
    if not linhas:
        return []
    cabecalho = [(c or "").strip() for c in linhas[0]]
    registros = []
    for linha in linhas[1:]:
        if not any((c or "").strip() for c in linha):
            continue
        registros.append({cabecalho[i]: (linha[i] if i < len(linha) else "")
                          for i in range(len(cabecalho)) if cabecalho[i]})
    return registros


def _maior_tabela(tabelas):
    if not tabelas:
        return []
    return _tabela_para_dicts(max(tabelas, key=len))


def _parece_json(conteudo):
    amostra = conteudo[:64].lstrip()
    return amostra.startswith((b"{", b"["))


def _parece_html(conteudo):
    return conteudo[:128].lstrip().lower().startswith((b"<", b"<!"))


def _url_csv_publicada(url):
    """Converte uma URL pubhtml do Google Sheets na exportacao CSV."""
    u = url.replace("/pubhtml", "/pub")
    if "output=" not in u:
        u += ("&" if "?" in u else "?") + "output=csv"
    return u


def _eh_planilha_google(url):
    """True se a URL ja e uma publicacao do Google Sheets (pub/pubhtml)."""
    u = (url or "").lower()
    return "docs.google.com/spreadsheets" in u or \
        u.endswith("/pubhtml") or "/pubhtml?" in u or "/pub?" in u


# --------------------------------------------------------------------------
# F05 - radares fixos
# --------------------------------------------------------------------------

class ColetorPRFFixos(ColetorBase):

    FONTE = {
        "nome": "PRF - Radares fixos",
        "organizacao": "Policia Rodoviaria Federal",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/prf/pt-br",
        "documentacao_url": ("https://www.gov.br/prf/pt-br/assuntos/"
                             "fiscalizacao-de-velocidade/radares-fixos"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "continuada",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "radares-fixos (pagina + mapa/tabela embutidos)",
        "url_recurso": ("https://www.gov.br/prf/pt-br/assuntos/"
                        "fiscalizacao-de-velocidade/radares-fixos"),
        "formato_origem": "html|json",
        "periodicidade_segundos": 604800,   # ~7 dias
        "status_integracao": "ok",
    }

    URL_PAGINA = RECURSO["url_recurso"]
    IFRAME_MAPA = "MAPA DE RADARES FIXOS"
    TITULO = "publicacao PRF (mapa de radares fixos)"

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial onde o mapa/tabela de fixos esta embutido."""
        return cls.URL_PAGINA

    # -- descoberta do recurso de dados (JSON do Apps Script) --------------
    @staticmethod
    def _url_dados_mapa(iframes):
        """Acha o iframe do mapa, baixa-o e extrai a URL do Apps Script."""
        src = None
        for titulo, href in iframes:
            if "MAPA" in titulo.upper() and href:
                src = href
                break
        if src is None:
            for _, href in iframes:
                if href:
                    src = href
                    break
        if not src:
            return None
        html = _baixar(src).decode("utf-8", "replace")
        m = re.search(r"appsScriptUrl\s*=\s*'([^']+)'", html)
        if not m:
            m = re.search(r'appsScriptUrl\s*=\s*"([^"]+)"', html)
        return m.group(1) if m else None

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        """origem: caminho local (json/html) OU URL. Retorna 4-tupla."""
        alvo = origem or self.URL_PAGINA
        local = bool(origem) and os.path.exists(origem)
        conteudo = self._ler(alvo)

        # 1) dados ja em JSON (Apps Script / fixture)
        if _parece_json(conteudo):
            return (conteudo, ".json", "application/json",
                    self._parse_json(conteudo))

        html = conteudo.decode("utf-8", "replace")

        # 2) tabela HTML estatica (ex.: tabela embutida em fixture)
        ext = _ExtratorTabelas()
        ext.feed(html)
        if ext.tabelas:
            return (conteudo, ".html", "text/html; charset=utf-8",
                    _maior_tabela(ext.tabelas))

        # 3) pagina gov.br com iframes -> segue o mapa -> Apps Script (JSON)
        if ext.iframes and not local:
            dados_url = self._url_dados_mapa(ext.iframes)
            if dados_url:
                dados = self._ler(dados_url)
                return (dados, ".json", "application/json",
                        self._parse_json(dados))

        return (conteudo, ".html", "text/html; charset=utf-8", [])

    def _ler(self, ref):
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        return _baixar(ref)

    @staticmethod
    def _parse_json(conteudo):
        dados = __import__("json").loads(conteudo.decode("utf-8-sig"))
        if isinstance(dados, dict):
            for chave in ("records", "dados", "data", "radares", "items"):
                if isinstance(dados.get(chave), list):
                    return dados[chave]
            return [v for v in dados.values() if isinstance(v, dict)]
        return dados

    def identificador(self, raw):
        return nz.pick(raw, "IDENTIFICADOR", "Identificador", "id")

    # -- normalizar --------------------------------------------------------
    def normalizar(self, idx, raw):
        ident = self.identificador(raw)
        lat = nz.to_float(nz.pick(raw, "LATITUDE", "Latitude", "latitude"))
        lon = nz.to_float(nz.pick(raw, "LONGITUDE", "Longitude", "longitude"))
        if not ident and lat is None and lon is None:
            return None

        uf = nz.pick(raw, "UF", "Uf", "uf")
        municipio = nz.pick(raw, "MUNICÍPIO", "MUNICÍPIO", "Municipio",
                            "Município", "municipio")
        br = nz.pick(raw, "BR")
        br = re.sub(r"(?i)^br\s*[-\s]?", "", str(br)).strip() if br else None
        km = nz.to_float(nz.pick(raw, "LOCAL", "KM", "Km", "km"))
        tipo_equip = nz.pick(raw, "TIPO EQUIPAMENTO", "Tipo")
        concessionaria = nz.pick(raw, "CONCESSIONÁRIA", "Concessionária")
        estado = nz.pick(raw, "ESTADO")
        marca = nz.pick(raw, "MARCA", "Marca")
        modelo = nz.pick(raw, "MODELO", "Modelo")
        codigo_equip = nz.pick(raw, "EQUIPAMENTO")
        faixas = nz.to_int(nz.pick(raw, "FAIXAS"))
        vel_leve = nz.to_float(nz.pick(raw, "VELOCIDADE LEVE",
                                       "VelocidadeLeves"))
        vel_pesado = nz.to_float(nz.pick(raw, "VELOCIDADE PESADO"))
        sentido_txt = nz.pick(raw, "SENTIDO", "Sentido")
        validade = nz.pick(raw, "VALIDADE DO CERTIFICADO",
                           "Validade Certificado")
        estudo = nz.pick(raw, "Estudo Técnico", "Estudo Tecnico")

        d = {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": ident,
            "tipo_identificador": "codigo_equipamento",
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial" if (lat is not None and lon is not None)
                         else "desconhecida",
            "metodo_obtencao": self.TITULO,
            "uf": uf,
            "municipio_nome": municipio,
            "via_codigo": ("BR-%s" % br) if br else None,
            "km": km,
            "situacao": nz.normalizar_situacao(estado),
            "situacao_original": estado,
            "tipo_radar": "fixo",
            "funcao_equipamento": _funcao_equipamento(tipo_equip),
            "sigla_equipamento_original": tipo_equip,
            "fabricante": marca,
            "modelo": modelo,
            "numero_serie": None,
            "velocidade_leves": vel_leve,
            "velocidade_pesados": vel_pesado,
            "sentido": nz.normalizar_sentido(sentido_txt),
            "sentido_original": sentido_txt,
            "quantidade_faixas_declarada": faixas,
            "observacoes": _obs_fixos(concessionaria, codigo_equip,
                                      validade, estudo),
        }
        return d


def _funcao_equipamento(v):
    t = (v or "").strip().lower()
    if "control" in t:
        return "controlador"
    if "redut" in t:
        return "redutor"
    if "mist" in t:
        return "misto"
    if not t:
        return None
    return "outro"


def _obs_fixos(concessionaria, codigo, validade, estudo):
    partes = []
    if concessionaria:
        partes.append("Concessionaria: %s" % concessionaria)
    if codigo:
        partes.append("Codigo de equipamento na fonte: %s" % codigo)
    if validade:
        partes.append("Validade do certificado: %s" % validade)
    if estudo:
        partes.append("Estudo tecnico: %s" % estudo)
    return "; ".join(partes) or None


# --------------------------------------------------------------------------
# F06 - lista de radares portateis (identificador + serie; sem posicao)
# --------------------------------------------------------------------------

class ColetorPRFPortateis(ColetorBase):

    FONTE = {
        "nome": "PRF - Lista de radares portateis",
        "organizacao": "Policia Rodoviaria Federal",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/prf/pt-br",
        "documentacao_url": ("https://www.gov.br/prf/pt-br/assuntos/"
                             "fiscalizacao-de-velocidade/lista-de-radares"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "continuada",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "lista-de-radares (tabela HTML: identificador + serie)",
        "url_recurso": ("https://www.gov.br/prf/pt-br/assuntos/"
                        "fiscalizacao-de-velocidade/lista-de-radares"),
        "formato_origem": "html",
        "periodicidade_segundos": 604800,
        "status_integracao": "ok",
    }

    URL_PAGINA = RECURSO["url_recurso"]

    @classmethod
    def resolver_url(cls):
        return cls.URL_PAGINA

    def carregar(self, origem):
        alvo = origem or self.URL_PAGINA
        conteudo = self._ler(alvo)
        html = conteudo.decode("utf-8", "replace")
        ext = _ExtratorTabelas()
        ext.feed(html)
        return (conteudo, ".html", "text/html; charset=utf-8",
                _maior_tabela(ext.tabelas))

    def _ler(self, ref):
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        return _baixar(ref)

    def identificador(self, raw):
        return nz.pick(raw, "IDENTIFICADOR DO EQUIPAMENTO", "IDENTIFICADOR")

    def normalizar(self, idx, raw):
        ident = nz.pick(raw, "IDENTIFICADOR DO EQUIPAMENTO", "IDENTIFICADOR")
        serie = nz.pick(raw, "Nº DE SÉRIE", "Nº DE SERIE", "NO DE SERIE",
                        "NUMERO DE SERIE", "SÉRIE", "SERIE")
        if not ident and not serie:
            return None
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": ident,
            "tipo_identificador": "codigo_equipamento",
            # ATENCAO: identificador administrativo != numero de serie (8.2).
            # A lista NAO traz posicao/hora; posicao fica NULL de proposito.
            "numero_serie": serie,
            "latitude": None,
            "longitude": None,
            "qualidade": "desconhecida",
            "metodo_obtencao": "publicacao PRF (lista de radares portateis)",
            "tipo_radar": "portatil",
            "situacao": None,
            "observacoes": ("identificador administrativo + numero de serie; "
                            "sem posicao/hora oficial (nao posicionar)"),
            "posicao_confirmada": False,
        }


# --------------------------------------------------------------------------
# F07 - trechos criticos (elegiveis para fiscalizacao portatil)
# --------------------------------------------------------------------------

class ColetorPRFTrechos(ColetorBase):

    FONTE = {
        "nome": "PRF - Trechos criticos para radar portatil",
        "organizacao": "Policia Rodoviaria Federal",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/prf/pt-br",
        "documentacao_url": ("https://www.gov.br/prf/pt-br/assuntos/"
                             "fiscalizacao-de-velocidade/trechos-criticos"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "continuada",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "trechos-criticos (planilhas publicadas)",
        "url_recurso": ("https://www.gov.br/prf/pt-br/assuntos/"
                        "fiscalizacao-de-velocidade/trechos-criticos"),
        "formato_origem": "html|csv",
        "periodicidade_segundos": 604800,
        "status_integracao": "ok",
    }

    URL_PAGINA = RECURSO["url_recurso"]
    CRITERIO = None   # preenchido pelo titulo real da publicacao

    @classmethod
    def resolver_url(cls):
        """URL da planilha mais recente ("Lista valida ...") da pagina."""
        try:
            html = _baixar(cls.URL_PAGINA).decode("utf-8", "replace")
            url = cls.descobrir_lista_url(html)
            if url:
                return url
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @staticmethod
    def descobrir_lista_url(html):
        """Percorre as ancoras e devolve a lista mais recente (maior data)."""
        ext = _ExtratorTabelas()
        ext.feed(html)
        melhor = None
        melhor_data = None
        for href, texto in ext.ancoras:
            if "docs.google.com" not in href:
                continue
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
            if not m:
                continue
            data = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if melhor_data is None or data > melhor_data:
                melhor_data = data
                melhor = href
        if melhor is None:
            return None
        return melhor.replace("&amp;", "&")

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        alvo = origem or self.URL_PAGINA
        local = bool(origem) and os.path.exists(origem)
        # resolver_url() ja pode devolver a publicacao do Google Sheets:
        # nesse caso busca direto a exportacao CSV (o pubhtml e widget JS).
        if not local and _eh_planilha_google(alvo):
            csv_bytes = self._ler(_url_csv_publicada(alvo))
            return (csv_bytes, ".csv", "text/csv; charset=utf-8",
                    _parse_csv_trechos(csv_bytes))
        conteudo = self._ler(alvo)
        if not _parece_html(conteudo):
            return (conteudo, ".csv", "text/csv; charset=utf-8",
                    _parse_csv_trechos(conteudo))
        html = conteudo.decode("utf-8", "replace")
        url = self.descobrir_lista_url(html)
        if url and not local:
            csv_bytes = self._ler(_url_csv_publicada(url))
            return (csv_bytes, ".csv", "text/csv; charset=utf-8",
                    _parse_csv_trechos(csv_bytes))
        return (conteudo, ".html", "text/html; charset=utf-8", [])

    def _ler(self, ref):
        if ref and os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        return _baixar(ref)

    def identificador(self, raw):
        uf = nz.pick(raw, "ESTADO (UF)", "ESTADO", "UF") or ""
        br = nz.pick(raw, "RODOVIA (BR)", "RODOVIA", "BR") or ""
        kmi = nz.pick(raw, "KM INICIAL") or ""
        kmf = nz.pick(raw, "KM FINAL") or ""
        return ("%s BR-%s %s-%s" % (uf, br, kmi, kmf)).strip()

    def normalizar(self, idx, raw):
        uf = nz.pick(raw, "ESTADO (UF)", "ESTADO", "UF")
        br = nz.pick(raw, "RODOVIA (BR)", "RODOVIA", "BR")
        kmi = nz.to_float(nz.pick(raw, "KM INICIAL"))
        kmf = nz.to_float(nz.pick(raw, "KM FINAL"))
        if not uf and br is None and kmi is None and kmf is None:
            return None
        via = None
        if br is not None and str(br).strip():
            via = str(br).strip()
            if not re.match(r"(?i)^br", via):
                via = "BR-%s" % via
        titulo = nz.pick(raw, "TITULO")
        return {
            "procedencia": "oficial",
            "natureza_fonte": "oficial",
            "confiabilidade": "oficial",
            "tipo_registro": "trecho_elegivel",
            "indicador": "pode_haver_fiscalizacao",
            # TRECHO ELEGIVEL nao e operacao confirmada nem ponto ativo (spec
            # F07 e 17.4 item 7): nunca marcar radar instalado.
            "radar_instalado_confirmado": None,
            "uf": uf,
            "via_codigo": via,
            "km_inicio": kmi,
            "km_fim": kmf,
            "sentido": None,
            "criterio_inclusao": titulo or self.CRITERIO,
            "situacao": "vigente",
            "metodo_obtencao": "publicacao PRF (trechos criticos)",
            "observacoes": ("trecho elegivel para fiscalizacao portatil; "
                            "nao e operacao confirmada nem radar ativo"),
        }


def _parse_csv_trechos(conteudo):
    """Le a planilha publicada: acha o cabecalho e devolve registros (dict).

    A exportacao traz linhas de titulo/espacos antes do cabecalho real
    "ESTADO (UF),RODOVIA (BR),KM INICIAL,KM FINAL".  O titulo e preservado
    em cada registro (campo TITULO) como evidencia do criterio de inclusao.
    """
    texto = conteudo.decode("utf-8-sig", "replace")
    linhas = list(csv.reader(io.StringIO(texto)))
    titulo = None
    cab_idx = None
    for i, linha in enumerate(linhas):
        juntas = [c.strip().upper() for c in linha]
        if any(juntas) and titulo is None and not any(
                "ESTADO" in c for c in juntas):
            titulo = " ".join(c.strip() for c in linha if c.strip())
        if any("ESTADO" in c for c in juntas) and any(
                ("RODOVIA" in c or "BR" == c) for c in juntas):
            cab_idx = i
            break
    if cab_idx is None:
        return []
    cabecalho = [c.strip() for c in linhas[cab_idx]]
    registros = []
    for linha in linhas[cab_idx + 1:]:
        if not any((c or "").strip() for c in linha):
            continue
        d = {cabecalho[i]: (linha[i] if i < len(linha) else "")
             for i in range(len(cabecalho)) if cabecalho[i]}
        if titulo:
            d["TITULO"] = titulo
        registros.append(d)
    return registros
