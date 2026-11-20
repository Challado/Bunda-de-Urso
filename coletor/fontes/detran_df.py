# -*- coding: utf-8 -*-
"""Coleta a relação pública de equipamentos do Detran-DF.

A entrada é a página oficial da listagem. O coletor lê o cadastro publicado
no HTML ou em seu arquivo de dados. O leitor de JavaScript e o fluxo por
Chromium continuam disponíveis para a publicação e os artefatos antigos.
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit

from core import caminhos

from coletor import http, politica_http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_JS = "application/javascript"

HOST_LISTA = "geoservicos.detran.df.gov.br"
DIRETORIO_LISTA = "/geoserver/styles/lista_equipto/"
URL_LISTA = "https://" + HOST_LISTA + DIRETORIO_LISTA + "index.html"
_DADOS = re.compile(r"\b(?:const|let|var)\s+equipamentos\s*=\s*", re.I)
_SCRIPT = re.compile(r"""<script\b[^>]*?\bsrc\s*=\s*(['"])(.*?)\1""", re.I | re.S)


# Navegadores aceitos no contorno de WAF (F5 BigIP), em ordem de preferencia.
_NAVEGADORES = ("chromium", "chromium-browser", "google-chrome",
                "google-chrome-stable", "chrome")

# Mapeamento do tipo declarado pela fonte para o tipo de radar interno.
# AVANÇO DE SINAL VERMELHO nao e medidor de velocidade -> nao vira tipo.
_TIPO_RADAR = {
    "DETRAN - RADAR": "fixo",
    "DETRAN - LOMBADA ELETRÔNICA": "fixo",
}


def _achar_navegador():
    """Caminho de um Chromium/Chrome headless instalado, ou ``None``."""
    for nome in _NAVEGADORES:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return None


def _dump_dom(navegador, url, perfil, timeout=90):
    """Abre ``url`` headless (perfil dado) e devolve o DOM renderizado."""
    opcoes = politica_http.ajustes(url, timeout=timeout, max_bytes=http.MAX_BYTES_PADRAO)
    timeout = opcoes["timeout"]
    cmd = [navegador, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", "--no-first-run",
           "--no-default-browser-check", "--user-data-dir=%s" % perfil,
           "--virtual-time-budget=15000", "--dump-dom", url]
    if not opcoes["verificar_ssl"]:
        cmd.insert(-1, "--ignore-certificate-errors")
    if opcoes["user_agent"]:
        cmd.insert(-1, "--user-agent=" + opcoes["user_agent"])
    from core import atualizacoes

    atualizacoes.evento("navegador.consulta", url=url, fonte=opcoes["fonte"], timeout=timeout,
                       max_bytes=opcoes["max_bytes"], modo_user_agent=opcoes["modo_user_agent"],
                       verificar_ssl=opcoes["verificar_ssl"])
    # O Chromium ainda usa os diretórios XDG para o Crashpad, mesmo com
    # --user-data-dir. A conta do cron pode não ter uma home gravável.
    ambiente = dict(os.environ, XDG_CONFIG_HOME=os.path.join(perfil, "config"),
                    XDG_CACHE_HOME=os.path.join(perfil, "cache"))
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, env=ambiente)
    except subprocess.TimeoutExpired as exc:
        raise http.ErroFonte('Navegador excedeu %s segundos ao abrir %s' % (timeout, url)) from exc
    if proc.returncode:
        detalhe = proc.stderr.decode('utf-8', 'replace').strip()[-2000:]
        raise http.ErroFonte('Navegador terminou com codigo %s em %s: %s' % (proc.returncode, url, detalhe))
    if len(proc.stdout) > opcoes["max_bytes"]:
        raise http.ErroFonte("Conteúdo do navegador excede o limite de coleta")
    if not proc.stdout.strip():
        raise http.ErroFonte('Navegador nao produziu conteudo em %s' % url)
    return proc.stdout.decode("utf-8", "replace")


def _texto_do_pre(bruto):
    """Extrai o conteudo de ``<pre>`` (``--dump-dom`` de recurso texto)."""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", bruto or "", re.S | re.I)
    return html.unescape(m.group(1)) if m else (bruto or "")


class ColetorDetranDF(ColetorBase):

    FONTE = {
        "nome": "Detran-DF - Relacao de medidores de velocidade",
        "organizacao": ("Departamento de Transito do Distrito Federal "
                        "(Detran-DF)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "distrital",
        "natureza": "oficial",
        "url_institucional": "https://www.detran.df.gov.br/",
        "documentacao_url": "https://www.detran.df.gov.br/equipamentos-eletronicos",
        "licenca": "pagina institucional publica (Resolucao CONTRAN 798/2020)",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Lista de equipamentos eletronicos de fiscalizacao (JS)",
        "url_recurso": URL_LISTA,
        "formato_origem": "js",
        "periodicidade_segundos": 2592000,     # ~30 dias
        # Contorno de WAF por navegador (2 passos) quando o cliente nao passa.
        "status_integracao": "implementado",
    }

    URL_PAGINA = "https://www.detran.df.gov.br/equipamentos-eletronicos"
    URL_LISTA_FALLBACK = URL_LISTA
    URL_DADOS_FALLBACK = urljoin(URL_LISTA, "equipamentos.js")

    @classmethod
    def resolver_url(cls):
        return cls.URL_LISTA_FALLBACK

    def garantir_referencias(self):
        fonte_id, recurso_id = super().garantir_referencias()
        self.conn.execute(
            "UPDATE RECURSO_FONTE SET url_recurso=? WHERE id=? AND url_recurso IN (?,?)",
            (self.URL_LISTA_FALLBACK, recurso_id, self.URL_PAGINA, self.URL_DADOS_FALLBACK))
        self.conn.commit()
        return fonte_id, recurso_id

    @staticmethod
    def _pagina(url):
        caminho = urlsplit(url).path.lower()
        return caminho.endswith(("/", ".html", ".htm"))

    @classmethod
    def _url_dados(cls, lista, texto):
        """Segue arquivos de equipamentos publicados na própria página."""
        arquivos = []
        for _, endereco in _SCRIPT.findall(texto):
            url = urljoin(lista, html.unescape(endereco))
            destino = urlsplit(url)
            nome = destino.path.rsplit("/", 1)[-1].lower()
            if (destino.scheme == "https" and destino.netloc == HOST_LISTA
                    and destino.path.startswith(DIRETORIO_LISTA)
                    and re.fullmatch(r"(?:dados[-_])?equip(?:amentos|tos)[\w.-]*\.(?:js|json)", nome)):
                arquivos.append(url)
        return list(dict.fromkeys(arquivos)) or [urljoin(lista, "equipamentos.js")]

    @classmethod
    def _ler_publicacao(cls, origem, obter):
        texto, url = obter(origem)
        if cls._extrair_registros(texto):
            return texto

        titulo = re.search(r"<title[^>]*>(.*?)</title>", texto, re.I | re.S)
        detalhe = " ".join(html.unescape(titulo[1]).split())[:100] if titulo else "sem lista de equipamentos"
        if re.search(r"request rejected|acesso negado|requisi[cç][aã]o negada", detalhe, re.I):
            raise http.ErroFonte(f"Detran-DF devolveu página de bloqueio ({detalhe}): {url}")

        destino = urlsplit(url)
        if cls._pagina(url) and destino.netloc == HOST_LISTA and destino.path.startswith(DIRETORIO_LISTA):
            for recurso in cls._url_dados(url, texto):
                try:
                    return cls._ler_arquivo(recurso, obter)
                except (http.ErroFonte, OSError) as exc:
                    detalhe = str(exc)
        raise http.ErroFonte(f"Detran-DF não devolveu uma lista válida ({detalhe}): {url}")

    @classmethod
    def _ler_arquivo(cls, recurso, obter):
        dados, url = obter(recurso)
        if not cls._extrair_registros(dados):
            raise http.ErroFonte(f"Arquivo de equipamentos sem registros válidos: {url}")
        return dados

    @classmethod
    def _texto_via_navegador(cls, url):
        navegador = _achar_navegador()
        if not navegador:
            raise http.ErroFonte("Chromium/Chrome indisponível para ler a publicação do Detran-DF")
        with tempfile.TemporaryDirectory(prefix="detran_df_", dir=caminhos.temporarios()) as perfil:
            def obter(endereco):
                return _texto_do_pre(_dump_dom(navegador, endereco, perfil)), endereco

            if not cls._pagina(url):
                obter(urljoin(url, "index.html"))
            return cls._ler_publicacao(url, obter)

    def carregar(self, origem):
        if origem and os.path.isfile(origem):
            with open(origem, encoding="utf-8-sig") as arquivo:
                texto = arquivo.read()
        else:
            url = self.resolver_url() if not origem or origem == self.URL_PAGINA else origem

            def obter(endereco):
                corpo, _, destino = http.baixar(endereco)
                return corpo.decode("utf-8-sig", "replace"), destino

            try:
                texto = self._ler_publicacao(url, obter)
            except (http.ErroFonte, OSError) as erro_http:
                try:
                    texto = self._texto_via_navegador(url)
                except (http.ErroFonte, OSError) as erro_browser:
                    raise http.ErroFonte(f"Download HTTP falhou: {erro_http}; navegador falhou: {erro_browser}") from erro_browser
        registros = self._extrair_registros(texto)
        if not registros:
            raise http.ErroFonte("Fonte Detran-DF sem lista válida de equipamentos")
        inicio = texto.lstrip()[:1]
        ext, mime = {"<": (".html", "text/html"), "{": (".json", "application/json"),
                     "[": (".json", "application/json")}.get(inicio, (".js", MIME_JS))
        return texto, ext, mime, registros

    @staticmethod
    def _extrair_registros(texto):
        """Lê o array publicado sem interpretar código JavaScript."""
        if not texto:
            return []
        texto = texto.lstrip()
        declaracao = _DADOS.search(texto)
        if declaracao:
            texto = texto[declaracao.end():]
        if not texto.startswith(("[", "{")):
            return []
        try:
            dados, _ = json.JSONDecoder().raw_decode(texto)
        except ValueError:
            return []
        if isinstance(dados, dict):
            dados = dados.get("equipamentos")
        if isinstance(dados, list) and all(
                isinstance(r, dict) and r.get("identificacao") and "tipo" in r for r in dados):
            return dados
        return []

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "identificacao")

    @staticmethod
    def _tipo_radar(tipo):
        if not tipo:
            return None
        return _TIPO_RADAR.get(tipo.strip().upper())

    def normalizar(self, idx, raw):
        tipo = (nz.pick(raw, "tipo") or "").strip()
        local = nz.pick(raw, "local_instalacao")
        estudo = nz.pick(raw, "levantamento_estudo")
        obs = "; ".join(x for x in (
            ("Tipo na fonte: %s" % tipo) if tipo else None,
            ("Local: %s" % local) if local else None,
            ("Levantamento/estudo: %s" % estudo) if estudo else None,
            ("Nao e medidor de velocidade (avanco de sinal)")
            if tipo.upper().startswith("AVANÇO") else None,
        ) if x) or None
        return {
            "identificador": self.identificador(raw),
            "tipo_identificador": "codigo_equipamento",
            # a lista do Detran-DF NAO traz coordenadas
            "latitude": None,
            "longitude": None,
            "qualidade": "oficial",
            "metodo_obtencao": ("publicacao Detran-DF (relacao de medidores de "
                                "velocidade / equipamentos de fiscalizacao)"),
            "uf": "DF",
            "municipio_nome": None,
            "via_codigo": None,
            "via_tipo": None,
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            "tipo_radar": self._tipo_radar(tipo),
            "numero_serie": nz.pick(raw, "numero_serie"),
            "fabricante": None,
            "modelo": None,
            "velocidade_geral": None,
            "sentido": None,
            "sentido_original": None,
            "observacoes": obs,
        }
