# -*- coding: utf-8 -*-
"""Downloader HTTP duro (somente biblioteca padrao: urllib/ssl/http).

Camada unica de rede do coletor.  Portada do conector de referencia
(``Downloader.checked_url``/``fetch``) para stdlib, sem ``requests``:

  - exige HTTPS publico: rejeita localhost/.local/.internal, endereco IP
    literal, credenciais embutidas (user:pass@) e porta diferente de 443;
  - segue redirecionamentos SALTO-A-SALTO com a mesma verificacao (no maximo
    5 saltos; HTTP 303 rebaixa o metodo para GET);
  - respeita ``If-None-Match`` / ``If-Modified-Since`` (HTTP 304 ->
    :class:`NaoModificado`);
  - recusa resposta 2xx com corpo vazio;
  - impoe teto de bytes (``max_bytes``; corpo maior -> :class:`ErroFonte`);
  - repete em 429/500/502/503/504 respeitando ``Retry-After`` (em segundos OU
    data HTTP, com teto de 30s) e backoff exponencial ``min(15, 2**tentativa)``
    (3 tentativas por padrao);
  - permite desligar a verificacao de certificado (``verificar_ssl=False``)
    para portais com cadeia incompleta, preservando o comportamento que ja
    existia no coletor (``fontes/ckan.py`` usava ``_CTX_TOLERANTE``).

Nada aqui roda em tempo de requisicao da API.
"""
import os
import sys

# --- anti-sombreamento da stdlib -------------------------------------------
# Quando um script de coletor/ roda POR CAMINHO (ex.: ``python3 coletor/tick.py``,
# que e como o cron chama), o proprio diretorio coletor/ entra em ``sys.path[0]``.
# Um modulo local chamado ``http.py`` passaria entao a sombrear a stdlib ``http``,
# e ``urllib.request`` (que faz ``import http.client``) quebraria com import
# circular. Garantimos que coletor/ NUNCA permanece no ``sys.path``.
_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path
               if os.path.abspath(p or os.getcwd()) != _AQUI]

import email.utils                       # noqa: E402
import ssl                               # noqa: E402
import time                              # noqa: E402
import urllib.error                      # noqa: E402
import urllib.parse                      # noqa: E402
import urllib.request                    # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from core import config                  # noqa: E402

__all__ = ("ErroFonte", "NaoModificado", "ErroRetentavel", "url_checada",
           "baixar")

# Teto de download (equivale a RADAR_MAX_BYTES da spec de coleta).
MAX_BYTES_PADRAO = config.caminhos.inteiro("coleta", "max_bytes")

# Numero de saltos de redirect permitidos (mais o request final).
_MAX_SALTOS = 5
_TAMANHO_BLOCO = 65536
# Seam de I/O: os testes substituem isto para nao tocar a rede.
_dormir = time.sleep


# --------------------------------------------------------------------------
# Excecoes
# --------------------------------------------------------------------------
class ErroFonte(RuntimeError):
    """Falha de coleta.  Nao deve ser repetida."""


class NaoModificado(ErroFonte):
    """HTTP 304: o recurso nao mudou desde a ultima coleta."""


class ErroRetentavel(ErroFonte):
    """Falha transitoria (rede, 429 ou 5xx): vale nova tentativa.

    ``espera`` guarda os segundos sugeridos pelo ``Retry-After`` (ou ``None``).
    """

    def __init__(self, mensagem, espera=None):
        super(ErroRetentavel, self).__init__(mensagem)
        self.espera = espera


# --------------------------------------------------------------------------
# Verificacao da URL
# --------------------------------------------------------------------------
def url_checada(url):
    """Valida que ``url`` e HTTPS publico; devolve a propria url.

    Rejeita: esquema != https, host ausente, credenciais embutidas, host
    interno (localhost/.local/.internal), IP literal e porta != 443.
    """
    partes = urllib.parse.urlparse(url)
    if partes.scheme != "https" or not partes.hostname \
            or partes.username or partes.password:
        raise ErroFonte(
            "Download exige URL HTTPS publica sem credenciais embutidas")
    host = partes.hostname.lower()
    if host in ("localhost", "localhost.localdomain") \
            or host.endswith((".localhost", ".local", ".internal")):
        raise ErroFonte("Host interno nao permitido na coleta")
    try:
        import ipaddress
        ipaddress.ip_address(host)
        raise ErroFonte("Endereco IP literal nao permitido na coleta")
    except ValueError:
        pass
    if partes.port not in (None, 443):
        raise ErroFonte("Porta externa nao permitida na coleta")
    return url


# --------------------------------------------------------------------------
# Camada de transporte (seam patchavel pelos testes: ``_abrir``)
# --------------------------------------------------------------------------
class _SemSeguirRedirect(urllib.request.HTTPRedirectHandler):
    """Nao segue redirect automaticamente: cada salto e verificado aqui."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENERS = {}


def _criar_opener(verificar_ssl):
    if verificar_ssl:
        contexto = ssl.create_default_context()
    else:
        contexto = ssl.create_default_context()
        contexto.check_hostname = False
        contexto.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        _SemSeguirRedirect(),
        urllib.request.HTTPSHandler(context=contexto))


def _abrir(req, timeout, verificar_ssl):
    """Executa UM request (sem seguir redirect).  Ponto de I/O do modulo."""
    opener = _OPENERS.get(verificar_ssl)
    if opener is None:
        opener = _criar_opener(verificar_ssl)
        _OPENERS[verificar_ssl] = opener
    return opener.open(req, timeout=timeout)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _espera_retry_after(valor):
    """Segundos indicados por Retry-After (inteiro OU data HTTP); teto 30s."""
    if not valor:
        return None
    try:
        return max(0, min(30, int(float(str(valor).strip()))))
    except (TypeError, ValueError):
        pass
    try:
        quando = email.utils.parsedate_to_datetime(str(valor).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    if quando is None:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    delta = (quando - datetime.now(timezone.utc)).total_seconds()
    return max(0, min(30, delta))


def _ler_corpo(resp, limite):
    """Le o corpo em blocos; aborta (ErroFonte) se passar de ``limite``."""
    pedacos = []
    total = 0
    while True:
        bloco = resp.read(_TAMANHO_BLOCO)
        if not bloco:
            break
        total += len(bloco)
        if total > limite:
            raise ErroFonte(
                "Download acima do limite de %d bytes" % limite)
        pedacos.append(bloco)
    return b"".join(pedacos)


def _fechar(resp):
    try:
        resp.close()
    except Exception:                                       # noqa: BLE001
        pass


def _status_de(resp):
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(resp, "code", 200)
    return status


# --------------------------------------------------------------------------
# baixar
# --------------------------------------------------------------------------
def _uma_tentativa(url, etag, last_modified, method, data, timeout, limite,
                   verificar_ssl, headers=None):
    cabecalhos = {
        "User-Agent": config.USER_AGENT,
        "Accept": ("application/json,text/csv,text/html,application/xml,"
                   "application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet,application/octet-stream;q=0.8"),
    }
    cabecalhos.update(headers or {})
    if etag:
        cabecalhos["If-None-Match"] = etag
    if last_modified:
        cabecalhos["If-Modified-Since"] = last_modified
    if data is not None and method.upper() not in ("GET", "HEAD"):
        cabecalhos.setdefault("Content-Type",
                              "application/x-www-form-urlencoded")
    metodo = method
    corpo_envio = data
    alvo = url
    for _salto in range(_MAX_SALTOS + 1):
        url_checada(alvo)
        if urllib.parse.urlsplit(alvo).netloc != urllib.parse.urlsplit(url).netloc:
            cabecalhos.pop("X-PowerBI-ResourceKey", None)
        req = urllib.request.Request(alvo, data=corpo_envio, method=metodo,
                                     headers=cabecalhos)
        try:
            resp = _abrir(req, timeout, verificar_ssl)
        except urllib.error.HTTPError as exc:
            status = exc.code
            recebidos = exc.headers if exc.headers is not None else {}
            _fechar(exc)
            alvo, metodo, corpo_envio = _tratar_erro_http(
                status, recebidos, alvo, metodo, corpo_envio)
            continue
        except urllib.error.URLError as exc:
            raise ErroRetentavel("Falha de rede em %s: %s" % (alvo, exc.reason))
        except (TimeoutError, OSError) as exc:
            raise ErroRetentavel("Falha de rede em %s: %s" % (alvo, exc))
        try:
            status = _status_de(resp)
            if status == 304:
                raise NaoModificado("HTTP 304 em %s" % alvo)
            if status in (301, 302, 303, 307, 308):
                recebidos = getattr(resp, "headers", None) or {}
                alvo, metodo, corpo_envio = _tratar_erro_http(
                    status, recebidos, alvo, metodo, corpo_envio)
                continue
            if status >= 400:
                raise ErroFonte("HTTP %d em %s" % (status, alvo))
            corpo = _ler_corpo(resp, limite)
            if not corpo:
                raise ErroFonte("HTTP %d com corpo vazio em %s"
                                % (status, alvo))
            amostra = corpo[:4096].lstrip().lower()
            if amostra.startswith((b"<html", b"<!doctype html")) and any(
                    trecho in amostra for trecho in (b"<title>request rejected</title>",
                        b"the requested url was rejected", b"<title>access denied</title>")):
                raise ErroFonte("HTTP %d com pagina de bloqueio de acesso, em vez do recurso publico: %s" % (status, alvo))
            try:
                devolvidos = dict(resp.headers) if resp.headers else {}
            except (TypeError, ValueError):
                devolvidos = {}
            return corpo, devolvidos, alvo
        finally:
            _fechar(resp)
    raise ErroFonte("Mais de cinco redirecionamentos HTTP a partir de %s"
                    % url)


def _tratar_erro_http(status, recebidos, alvo, metodo, corpo_envio):
    """Decide o que fazer com um status nao-2xx; devolve (alvo, metodo, corpo).

    Para redirecionamentos devolve o novo alvo; caso contrario levanta a
    excecao apropriada.
    """
    if status in (301, 302, 303, 307, 308):
        destino = recebidos.get("Location") if hasattr(recebidos, "get") \
            else None
        if not destino:
            raise ErroFonte("Redirect %d sem Location em %s" % (status, alvo))
        novo = urllib.parse.urljoin(alvo, destino)
        url_checada(novo)
        if status == 303:
            metodo = "GET"
            corpo_envio = None
        return novo, metodo, corpo_envio
    if status == 304:
        raise NaoModificado("HTTP 304 em %s" % alvo)
    if status in (429, 500, 502, 503, 504):
        espera = _espera_retry_after(
            recebidos.get("Retry-After") if hasattr(recebidos, "get") else None)
        raise ErroRetentavel("HTTP %d em %s" % (status, alvo), espera)
    raise ErroFonte("HTTP %d em %s" % (status, alvo))


def baixar(url, etag=None, last_modified=None, method="GET", data=None,
           timeout=None, max_bytes=None, verificar_ssl=True, headers=None):
    """Baixa ``url`` e devolve ``(corpo, headers, url_final)``.

    Repete em falhas transitorias (429/5xx/rede) ate 3 tentativas, respeitando
    ``Retry-After`` e backoff exponencial.  HTTP 304 levanta
    :class:`NaoModificado`; qualquer outra falha levanta :class:`ErroFonte`.
    """
    url_checada(url)
    # Somente cabecalhos de publicacao publica; nao aceita cookies/credenciais.
    permitidos = {"accept": "Accept", "content-type": "Content-Type",
                  "x-powerbi-resourcekey": "X-PowerBI-ResourceKey"}
    extras = {}
    for chave, valor in (headers or {}).items():
        if chave.lower() not in permitidos or not isinstance(valor, str) or "\n" in valor or "\r" in valor:
            raise ErroFonte("Cabecalho HTTP nao permitido")
        extras[permitidos[chave.lower()]] = valor
    limite = int(max_bytes) if max_bytes is not None else MAX_BYTES_PADRAO
    tempo = float(timeout) if timeout is not None \
        else float(config.DEFAULT_TIMEOUT)
    tentativas = max(1, int(getattr(config, "DEFAULT_TENTATIVAS", 3)))
    ultimo = None
    for tentativa in range(tentativas):
        try:
            return _uma_tentativa(url, etag, last_modified, method, data,
                                  tempo, limite, verificar_ssl, extras)
        except NaoModificado:
            raise
        except ErroRetentavel as exc:
            from core import atualizacoes
            atualizacoes.registrar("http", {"etapa": "tentativa.erro", "url": url,
                                           "tentativa": tentativa + 1, "max_tentativas": tentativas,
                                           "erro": str(exc), "tipo": type(exc).__name__})
            atualizacoes.evento("http.erro", url=url, tentativa=tentativa + 1, erro=str(exc))
            ultimo = exc
            if tentativa == tentativas - 1:
                break
            espera = exc.espera if exc.espera is not None \
                else min(15, 2 ** tentativa)
            _dormir(espera)
        except ErroFonte as exc:
            from core import atualizacoes
            atualizacoes.registrar("http", {"etapa": "tentativa.erro", "url": url,
                                           "tentativa": tentativa + 1, "erro": str(exc), "tipo": type(exc).__name__})
            atualizacoes.evento("http.erro", url=url, tentativa=tentativa + 1, erro=str(exc))
            raise
    raise ErroFonte("HTTP falhou apos %d tentativas: %s"
                    % (tentativas, ultimo)) from ultimo
