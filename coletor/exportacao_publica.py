"""Exportacao XLSX de pagina publica por Chromium, inclusive downloads blob:.

Usa CDP local e biblioteca padrao; nao depende de Node, Playwright ou IA.
Perfil temporario, sem login/cookies pessoais. Nao resolve CAPTCHA. Toda
navegacao externa usa o proxy herdado; o socket local controla nosso processo.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse

from coletor import http
from core import config, atualizacoes


def _url_diagnostico(url):
    """Caminho publico basta; consultas podem carregar tokens de redirecionamento."""
    partes = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((partes.scheme, partes.hostname or "", partes.path, "", ""))


def _encerrar_navegador(proc, cdp):
    """Espera o navegador e encerra filhos antes de remover o perfil temporario."""
    if cdp:
        try:
            if proc.poll() is None:
                cdp.prazo = time.monotonic() + 2
                cdp.chamar("Browser.close")
        except (OSError, http.ErroFonte):
            pass  # A conexao pode fechar justamente porque Browser.close funcionou.
        finally:
            cdp.sock.close()
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # O launcher pode ja ter terminado deixando renderizadores vivos. Todos
    # pertencem a sessao exclusiva criada abaixo, sem atingir outros navegadores.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=5)


class _CDP:
    def __init__(self, porta, caminho, prazo):
        self.prazo, self.sequencia, self.eventos = prazo, 0, []
        self.falhas, self.excecoes = [], []
        self.sock = socket.create_connection(("127.0.0.1", porta), timeout=10)
        nonce = base64.b64encode(os.urandom(16)).decode()
        pedido = ("GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n"
                  "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
                  "Sec-WebSocket-Version: 13\r\n\r\n" % (caminho, porta, nonce))
        self.sock.sendall(pedido.encode())
        resposta = bytearray()
        while not resposta.endswith(b"\r\n\r\n"):
            resposta.extend(self._ler(1))
            if len(resposta) > 16384:
                raise http.ErroFonte("Resposta CDP local invalida")
        esperado = base64.b64encode(hashlib.sha1((nonce +
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not resposta.startswith(b"HTTP/1.1 101 ") or esperado not in resposta:
            self.sock.close()
            raise http.ErroFonte("Chromium nao aceitou o controle CDP local")

    def _ler(self, tamanho):
        saida = bytearray()
        while len(saida) < tamanho:
            restante = self.prazo - time.monotonic()
            if restante <= 0:
                raise http.ErroFonte("Tempo esgotado na exportacao publica")
            self.sock.settimeout(restante)
            bloco = self.sock.recv(tamanho - len(saida))
            if not bloco:
                raise http.ErroFonte("Chromium encerrou a conexao CDP")
            saida.extend(bloco)
        return bytes(saida)

    def _enviar(self, dados, opcode=1):
        mascara = os.urandom(4)
        tamanho = len(dados)
        cabecalho = bytes([0x80 | opcode])
        if tamanho < 126:
            cabecalho += bytes([0x80 | tamanho])
        elif tamanho < 65536:
            cabecalho += bytes([0x80 | 126]) + struct.pack("!H", tamanho)
        else:
            cabecalho += bytes([0x80 | 127]) + struct.pack("!Q", tamanho)
        self.sock.sendall(cabecalho + mascara + bytes(
            v ^ mascara[i % 4] for i, v in enumerate(dados)))

    def _receber(self):
        acumulado = bytearray()
        while True:
            a, b = self._ler(2)
            opcode, tamanho = a & 15, b & 127
            if tamanho == 126:
                tamanho = struct.unpack("!H", self._ler(2))[0]
            elif tamanho == 127:
                tamanho = struct.unpack("!Q", self._ler(8))[0]
            if tamanho + len(acumulado) > 8 * 1024 * 1024:
                raise http.ErroFonte("Resposta CDP excede o limite")
            mascara = self._ler(4) if b & 128 else None
            dados = self._ler(tamanho)
            if mascara:
                dados = bytes(v ^ mascara[i % 4] for i, v in enumerate(dados))
            if opcode == 8:
                raise http.ErroFonte("Chromium fechou o controle da exportacao")
            if opcode == 9:
                self._enviar(dados, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise http.ErroFonte("Mensagem CDP inesperada")
            acumulado.extend(dados)
            if a & 128:
                return json.loads(acumulado)

    def chamar(self, metodo, parametros=None, sessao=None):
        self.sequencia += 1
        pedido = {"id": self.sequencia, "method": metodo, "params": parametros or {}}
        if sessao:
            pedido["sessionId"] = sessao
        self._enviar(json.dumps(pedido).encode())
        while True:
            mensagem = self._receber()
            if mensagem.get("id") == self.sequencia:
                if mensagem.get("error"):
                    raise http.ErroFonte("Falha no navegador: " + str(mensagem["error"].get("message")))
                return mensagem.get("result", {})
            metodo, params = mensagem.get("method"), mensagem.get("params", {})
            if metodo == "Network.responseReceived":
                resposta = params.get("response", {})
                if params.get("type") == "Document":
                    self.eventos.append({"frameId": params.get("frameId"), "status": resposta.get("status"),
                                         "url": _url_diagnostico(resposta.get("url", ""))})
                    self.eventos[:] = self.eventos[-12:]
                if resposta.get("status", 0) >= 400:
                    self.falhas.append({"tipo": params.get("type"), "status": resposta["status"],
                                        "url": _url_diagnostico(resposta.get("url", ""))})
            elif metodo == "Network.loadingFailed":
                self.falhas.append({"tipo": params.get("type"), "erro": params.get("errorText"),
                                    "cancelado": params.get("canceled", False)})
            elif metodo == "Runtime.exceptionThrown":
                detalhes = params.get("exceptionDetails", {})
                self.excecoes.append(atualizacoes.limpar(detalhes.get("exception", {}).get("description") or detalhes.get("text")))
            self.falhas[:] = self.falhas[-12:]
            self.excecoes[:] = self.excecoes[-8:]


_EXPORTAR = r"""(() => {
 const corpo=(document.body?.innerText||'').slice(0,4000).toLowerCase();
 const contexto={titulo:document.title,url:location.origin+location.pathname,pronto:document.readyState};
 if (/verify you are human|confirme que voc[eê] [eé] humano|access denied|captcha|request rejected|requested url was rejected/.test(corpo))
   return {...contexto,bloqueio:true};
 const candidatos=[...document.querySelectorAll('button,a,[role="button"],[role="menuitem"],input[type="button"],input[type="submit"]')]
  .filter(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden' && !e.disabled && e.getAttribute('aria-disabled')!=='true')
  .map(e=>({e,t:[e.innerText,e.value,e.title,e.getAttribute('aria-label'),e.getAttribute('download'),
    e.getAttribute('mattooltip'),e.getAttribute('data-original-title'),e.getAttribute('data-tooltip'),e.className,
    ...[...e.querySelectorAll('i,span,svg,img,mat-icon')].flatMap(x=>[x.getAttribute('class'),x.getAttribute('alt'),x.getAttribute('title')])]
    .filter(Boolean).join(' ').replace(/\s+/g,' ').slice(0,300)}))
  .filter(x=>/excel|\.xlsx|exportar|exporta[cç][aã]o|\bexport\b|baixar|download|file_download|save_alt|get_app/i.test(x.t))
  .filter(x=>!/pdf|\.csv|\bjson\b|imprimir/i.test(x.t) || /excel|xlsx/i.test(x.t))
  .sort((a,b)=>Number(/excel|xlsx/i.test(b.t))-Number(/excel|xlsx/i.test(a.t)));
 window.__radarExportados=window.__radarExportados||new WeakMap();
 const agora=Date.now();
 const alvo=candidatos.find(x=>{const p=window.__radarExportados.get(x.e);return !p || (p.n<4 && agora-p.quando>=4000)});
 const controles=candidatos.slice(0,12).map(x=>x.t);
 if(!alvo)return {...contexto,aguardando:true,controles};
 const n=(window.__radarExportados.get(alvo.e)?.n||0)+1;
 window.__radarExportados.set(alvo.e,{n,quando:agora});
 try {alvo.e.click();return {...contexto,clicou:true,rotulo:alvo.t,tentativa:n,controles}}
 catch(e){return {...contexto,erroClique:String(e),rotulo:alvo.t,tentativa:n,controles}}
})()"""


def _contextos_exportacao(cdp, sessao, prazo, anexos):
    """A exportacao pode estar num iframe, inclusive com processo separado."""
    contextos = [(sessao, None)]
    arvore = cdp.chamar("Page.getFrameTree", sessao=sessao).get("frameTree", {})
    pendentes = list(arvore.get("childFrames", []))
    while pendentes and len(contextos) < 8 and time.monotonic() < prazo:
        ramo = pendentes.pop(0)
        pendentes.extend(ramo.get("childFrames", []))
        try:
            mundo = cdp.chamar("Page.createIsolatedWorld", {
                "frameId": ramo["frame"]["id"], "worldName": "radar-exportacao"}, sessao)
            contextos.append((sessao, mundo["executionContextId"]))
        except http.ErroFonte:
            # Iframes de outra origem podem pertencer a outro processo CDP.
            continue
    alvos = cdp.chamar("Target.getTargets").get("targetInfos", [])
    for alvo in alvos:
        if alvo.get("type") != "iframe" or len(contextos) >= 8:
            continue
        if alvo["targetId"] not in anexos:
            anexo = cdp.chamar("Target.attachToTarget", {"targetId": alvo["targetId"], "flatten": True})
            anexos[alvo["targetId"]] = anexo["sessionId"]
            cdp.chamar("Runtime.enable", sessao=anexo["sessionId"])
            cdp.chamar("Network.enable", sessao=anexo["sessionId"])
        contextos.append((anexos[alvo["targetId"]], None))
    return contextos


def baixar_xlsx(url, timeout=None):
    """Abre somente a pagina publica e aciona sua exportacao Excel visivel."""
    http.url_checada(url)
    navegador = next((shutil.which(n) for n in (
        "chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
        if shutil.which(n)), None)
    if not navegador:
        raise http.ErroFonte("Exportacao publica requer Chromium/Chrome; instale chromium ou use --arquivo com o XLSX exportado")
    prazo = time.monotonic() + (timeout or max(60, config.DEFAULT_TIMEOUT * 3))
    with tempfile.TemporaryDirectory(prefix="radar-exportacao-") as pasta:
        perfil, downloads = Path(pasta) / "perfil", Path(pasta) / "downloads"
        downloads.mkdir()
        cmd = [navegador, "--headless=new", "--no-sandbox", "--disable-gpu",
               "--disable-background-networking", "--disable-extensions", "--disable-sync",
               "--no-first-run", "--no-default-browser-check", "--remote-debugging-address=127.0.0.1",
               "--remote-debugging-port=0", "--user-data-dir=" + str(perfil), "about:blank"]
        proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                 or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
        if proxy:
            cmd.insert(-1, "--proxy-server=" + proxy)
        stderr = tempfile.TemporaryFile()
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True)
        cdp = None
        diagnostico = {}
        try:
            porta_arquivo = perfil / "DevToolsActivePort"
            while not porta_arquivo.exists():
                if proc.poll() is not None or time.monotonic() >= prazo:
                    raise http.ErroFonte("Chromium nao iniciou a exportacao publica")
                time.sleep(0.1)
            porta, caminho = porta_arquivo.read_text().splitlines()[:2]
            cdp = _CDP(int(porta), caminho, prazo)
            cdp.chamar("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
            alvo = cdp.chamar("Target.createTarget", {"url": "about:blank"})["targetId"]
            sessao = cdp.chamar("Target.attachToTarget", {"targetId": alvo, "flatten": True})["sessionId"]
            cdp.chamar("Network.enable", sessao=sessao)
            cdp.chamar("Page.enable", sessao=sessao)
            cdp.chamar("Runtime.enable", sessao=sessao)
            navegacao = cdp.chamar("Page.navigate", {"url": url}, sessao)
            if navegacao.get("errorText"):
                raise http.ErroFonte("Navegacao publica falhou: " + navegacao["errorText"])
            proximo_clique, proximo_contexto = 0, 0
            contextos = [(sessao, None)]
            anexos = {}
            while time.monotonic() < prazo:
                if any(a.stat().st_size > http.MAX_BYTES_PADRAO for a in downloads.iterdir() if a.is_file()):
                    raise http.ErroFonte("Download da planilha excede o limite de coleta")
                for arquivo in downloads.glob("*.xlsx"):
                    if arquivo.is_file() and arquivo.stat().st_size > 0:
                        if arquivo.stat().st_size > http.MAX_BYTES_PADRAO:
                            raise http.ErroFonte("Planilha exportada excede o limite de coleta")
                        return arquivo.read_bytes()
                for evento in cdp.eventos:
                    status = evento["status"]
                    if status >= 400 and evento.get("frameId") == navegacao.get("frameId"):
                        raise http.ErroFonte("Pagina publica respondeu HTTP %d: %s" % (status, url))
                if time.monotonic() >= proximo_clique:
                    if time.monotonic() >= proximo_contexto:
                        contextos = _contextos_exportacao(cdp, sessao, prazo, anexos)
                        proximo_contexto = time.monotonic() + 5
                    for contexto_sessao, contexto_id in contextos:
                        parametros = {"expression": _EXPORTAR, "returnByValue": True}
                        if contexto_id is not None:
                            parametros["contextId"] = contexto_id
                        try:
                            resultado = cdp.chamar("Runtime.evaluate", parametros, contexto_sessao)
                        except http.ErroFonte as exc:
                            if any(t in str(exc) for t in ("Cannot find context", "Execution context was destroyed", "No frame with given", "Session with given id not found")):
                                atualizacoes.evento("exportacao.contexto_alterado", aviso=str(exc))
                                proximo_contexto = 0
                                continue
                            raise
                        valor = resultado.get("result", {}).get("value") or {}
                        diagnostico[valor.get("url", str(contexto_id))] = valor or {"excecao": resultado.get("exceptionDetails")}
                        if valor.get("bloqueio") and contexto_sessao == sessao and contexto_id is None:
                            raise http.ErroFonte("Pagina bloqueou acesso ou solicitou verificacao humana; exportacao interrompida")
                        if valor.get("clicou") or valor.get("erroClique"):
                            atualizacoes.evento("exportacao.clique", diagnostico=valor)
                    proximo_clique = time.monotonic() + 0.5
                time.sleep(0.1)
            raise http.ErroFonte("Pagina nao disponibilizou exportacao XLSX no prazo: " + url)
        except Exception as exc:
            stderr.seek(0)
            navegador_stderr = stderr.read().decode("utf-8", "replace")
            detalhe = {"pagina": diagnostico, "falhas_rede": cdp.falhas if cdp else [],
                       "erros_javascript": cdp.excecoes if cdp else [], "stderr_navegador": navegador_stderr}
            atualizacoes.evento("exportacao.erro", erro=str(exc), diagnostico=detalhe)
            if isinstance(exc, http.ErroFonte):
                raise http.ErroFonte(str(exc) + "; diagnostico=" + json.dumps(atualizacoes.limpar(detalhe), ensure_ascii=False)) from exc
            raise
        finally:
            _encerrar_navegador(proc, cdp)
            stderr.close()
