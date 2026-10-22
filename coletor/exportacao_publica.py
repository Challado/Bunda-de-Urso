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
import socket
import struct
import subprocess
import tempfile
import time

from coletor import http
from core import config


class _CDP:
    def __init__(self, porta, caminho, prazo):
        self.prazo, self.sequencia, self.eventos = prazo, 0, []
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
            # Somente a ultima resposta DOCUMENTO importa, sem acumular rede/segredos.
            if mensagem.get("method") == "Network.responseReceived" and mensagem.get("params", {}).get("type") == "Document":
                self.eventos[:] = [mensagem]


_EXPORTAR = r"""(() => {
 const corpo=(document.body?.innerText||'').slice(0,3000).toLowerCase();
 if (/verify you are human|confirme que voc[eê] [eé] humano|access denied|captcha/.test(corpo))
   return {bloqueio:true};
 const candidatos=[...document.querySelectorAll('button,a,[role="button"],input[type="button"]')]
  .filter(e=>e.getClientRects().length && !e.disabled)
  .map(e=>({e,t:[e.innerText,e.value,e.title,e.getAttribute('aria-label'),e.getAttribute('download'),e.className,
    ...[...e.querySelectorAll('i,span,svg')].map(x=>x.getAttribute('class'))].filter(Boolean).join(' ')}))
  .filter(x=>/excel|\.xlsx|exportar|exporta[cç][aã]o|\bexport\b/i.test(x.t))
  .sort((a,b)=>Number(/excel|xlsx/i.test(b.t))-Number(/excel|xlsx/i.test(a.t)));
 window.__radarExportados=window.__radarExportados||[];
 const alvo=candidatos.find(x=>!window.__radarExportados.includes(x.t));
 if(!alvo)return {aguardando:true};
 window.__radarExportados.push(alvo.t); alvo.e.click(); return {clicou:true};
})()"""


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
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
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
            navegacao = cdp.chamar("Page.navigate", {"url": url}, sessao)
            if navegacao.get("errorText"):
                raise http.ErroFonte("Navegacao publica falhou: " + navegacao["errorText"])
            proximo_clique = 0
            while time.monotonic() < prazo:
                for arquivo in downloads.glob("*.xlsx"):
                    if arquivo.is_file() and arquivo.stat().st_size > 0:
                        if arquivo.stat().st_size > http.MAX_BYTES_PADRAO:
                            raise http.ErroFonte("Planilha exportada excede o limite de coleta")
                        return arquivo.read_bytes()
                for evento in cdp.eventos:
                    status = evento["params"]["response"]["status"]
                    if status >= 400:
                        raise http.ErroFonte("Pagina publica respondeu HTTP %d: %s" % (status, url))
                if time.monotonic() >= proximo_clique:
                    resultado = cdp.chamar("Runtime.evaluate", {
                        "expression": _EXPORTAR, "returnByValue": True}, sessao)
                    valor = resultado.get("result", {}).get("value", {})
                    if valor.get("bloqueio"):
                        raise http.ErroFonte("Pagina solicitou verificacao humana; exportacao interrompida")
                    proximo_clique = time.monotonic() + (5 if valor.get("clicou") else 0.5)
                time.sleep(0.1)
            raise http.ErroFonte("Pagina nao disponibilizou exportacao XLSX no prazo: " + url)
        finally:
            if cdp:
                cdp.sock.close()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
