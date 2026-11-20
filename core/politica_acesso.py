"""Limites e regras de acesso da instância pública."""
import fcntl
import hashlib
import hmac
import ipaddress
import json
import re
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import caminhos, config

ROTA_ENVIOS = "/api/v1/radares/envios"
ROTA_DUMP = "/api/v1/radares/download"
ROTAS_BUSCA = frozenset(("/api/v1/radares", "/api/v1/radares/busca"))
ROTAS_PAGINADAS = ROTAS_BUSCA | {"/api/v1/trechos", "/api/v1/operacoes",
                                  "/api/v1/trafego", "/api/v1/atualizacoes"}
ROTAS_REGRAS = ROTAS_PAGINADAS | {ROTA_DUMP, "/api/v1/radares/{id}",
                                  "/api/v1/equipamentos/{id}", "/api/v1/status/estados",
                                  "/api/v1/status/estados/{uf}"}


def categoria_rota(rota):
    if re.fullmatch(r"/api/v1/radares/[^/]+(?:/historico)?", rota) and rota not in ROTAS_REGRAS:
        return "/api/v1/radares/{id}"
    if re.fullmatch(r"/api/v1/equipamentos/[^/]+", rota):
        return "/api/v1/equipamentos/{id}"
    if re.fullmatch(r"/api/v1/status/estados/[^/]+", rota):
        return "/api/v1/status/estados/{uf}"
    return rota


def limite():
    return max(1, min(config.MAX_LIMITE, caminhos.inteiro("api", "limite_consulta")))


def limite_padrao():
    return min(config.DEFAULT_LIMITE, limite())


def cursor_publico():
    return max(0, min(100000, caminhos.inteiro("api", "cursor_publico_max")))


def timeout():
    return max(1, min(60, caminhos.inteiro("api", "timeout_consulta")))


def url_dump():
    return caminhos.web_inicio() + "api.pse?rota=" + ROTA_DUMP


def url_politica():
    return caminhos.web_inicio() + "politica-de-uso.html"


def chave_leitura_valida(environ):
    valor = (environ.get("HTTP_X_RADAR_LEITURA") or "").strip()
    if not valor or len(valor) > 256:
        return False
    digest = hashlib.sha256(valor.encode("utf-8")).hexdigest()
    try:
        arquivo = Path(caminhos.caminho("api", "chaves_leitura_arquivo"))
        with arquivo.open(encoding="ascii") as entrada:
            hashes = entrada.read(65537)
        if len(hashes) > 65536:
            return False
    except (OSError, ValueError):
        return False
    return any(hmac.compare_digest(digest, linha.strip().lower())
               for linha in hashes.splitlines() if re.fullmatch(r"[0-9a-fA-F]{64}", linha.strip()))


@dataclass(frozen=True)
class Regra:
    rota: str | None
    redes: tuple
    agente: re.Pattern | None
    limite_minimo: int = 0
    cursor_minimo: int = 0
    status: int = 403

    def corresponde(self, rota, ip, agente, limite, cursor):
        return (self.rota in (None, rota)
                and (not self.redes or (ip is not None and any(
                    ip.version == inicio.version and inicio <= ip <= fim for inicio, fim in self.redes)))
                and (self.agente is None or (agente and self.agente.search(agente) is not None))
                and limite >= self.limite_minimo and cursor >= self.cursor_minimo)


def _lista(texto):
    if not isinstance(texto, str) or len(texto) > 24000:
        raise ValueError("A lista deve ser JSON com até 24 mil caracteres.")
    try:
        valores = json.loads(texto)
    except ValueError:
        raise ValueError("Use uma lista JSON.") from None
    if not isinstance(valores, list):
        raise ValueError("Use uma lista JSON.")
    regras = [regra for item in valores for regra in (item if isinstance(item, list) else [item])]
    if len(regras) > 100:
        raise ValueError("A lista aceita até 100 regras.")
    return regras


def _redes(textos):
    if not isinstance(textos, list) or len(textos) > 32 or any(not isinstance(r, str) for r in textos):
        raise ValueError("Informe até 32 IPs, redes CIDR ou intervalos IP-IP.")
    redes = []
    for texto in textos:
        try:
            if "-" in texto:
                inicio, fim = (ipaddress.ip_address(ip.strip()) for ip in texto.split("-", 1))
                if inicio.version != fim.version or fim < inicio:
                    raise ValueError()
            else:
                rede = ipaddress.ip_network(texto.strip(), strict=True)
                inicio, fim = rede.network_address, rede.broadcast_address
        except ValueError:
            raise ValueError("IP, CIDR ou intervalo inválido.") from None
        redes.append((inicio, fim))
    return tuple(redes)


def _seletor(item, i, rotas, *, rota_obrigatoria):
    rota = item.get("rota")
    if (rota is not None or rota_obrigatoria) and (not isinstance(rota, str) or rota not in rotas):
        raise ValueError(f"Regra {i}: rota não suportada.")
    redes = _redes(item.get("redes", []))
    agente = item.get("user_agent_regex")
    if agente is not None:
        if not isinstance(agente, str) or not 1 <= len(agente) <= 256:
            raise ValueError(f"Regra {i}: user_agent_regex deve ter entre 1 e 256 caracteres.")
        try:
            agente = re.compile(agente)
        except re.error:
            raise ValueError(f"Regra {i}: regex de User-Agent inválida.") from None
    return rota, redes, agente


@lru_cache(maxsize=16)
def ler_liberacoes(texto):
    regras = []
    for i, item in enumerate(_lista(texto), 1):
        if not isinstance(item, dict) or set(item) - {"rota", "redes", "user_agent_regex"}:
            raise ValueError(f"Liberação {i}: use os campos documentados.")
        rota, redes, agente = _seletor(item, i, ROTAS_REGRAS | {ROTA_ENVIOS}, rota_obrigatoria=True)
        if not (redes or agente):
            raise ValueError(f"Liberação {i}: informe IP, regex de User-Agent ou ambos.")
        regras.append(Regra(rota, redes, agente))
    return tuple(regras)


@lru_cache(maxsize=16)
def ler_bloqueios(texto):
    regras = []
    chaves = {"rota", "redes", "user_agent_regex", "limite_minimo", "cursor_minimo", "status"}
    for i, item in enumerate(_lista(texto), 1):
        if not isinstance(item, dict) or set(item) - chaves:
            raise ValueError(f"Bloqueio {i}: use os campos documentados.")
        rota, redes, agente = _seletor(item, i, ROTAS_REGRAS | {ROTA_ENVIOS}, rota_obrigatoria=False)
        minimo, cursor = (item.get(k, 0) for k in ("limite_minimo", "cursor_minimo"))
        if any(type(n) is not int or not 0 <= n <= 2**31 - 1 for n in (minimo, cursor)):
            raise ValueError(f"Bloqueio {i}: os mínimos devem ser inteiros não negativos.")
        if not (redes or agente or (minimo and cursor)):
            raise ValueError(f"Bloqueio {i}: informe rede, User-Agent ou os dois mínimos.")
        status = item.get("status", 403)
        if type(status) is not int or status not in (403, 429):
            raise ValueError(f"Bloqueio {i}: use status 403 ou 429.")
        regras.append(Regra(rota, redes, agente, minimo, cursor, status))
    return tuple(regras)


def _ip(endereco):
    try:
        return ipaddress.ip_address(endereco)
    except ValueError:
        return None


def liberado(rota, endereco, agente):
    regras = ler_liberacoes(caminhos.valor("abuso", "liberacoes")[0])
    ip, agente = _ip(endereco), (agente or "")[:512]
    return any(regra.corresponde(rota, ip, agente, 0, 0) for regra in regras)


def bloqueio(rota, endereco, agente, limite_pedido, cursor):
    regras = ler_bloqueios(caminhos.valor("abuso", "bloqueios")[0])
    ip, agente = _ip(endereco), (agente or "")[:512]
    return next((regra.status for regra in regras if regra.corresponde(
        rota, ip, agente, limite_pedido, cursor)), None)


def _medir_pagina(indice, maximo, janela):
    """Contador entre processos CGI, particionado e limitado em disco."""
    pasta = Path(caminhos.dentro_dados("abuso", "contadores de acesso"))
    pasta.mkdir(parents=True, mode=0o770, exist_ok=True)
    agora = int(time.time())
    expira = (agora // janela + 1) * janela
    arq = pasta / (indice[:2] + ".json")
    fd = os.open(arq.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    with os.fdopen(fd) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with arq.open(encoding="ascii") as entrada:
                estado = json.loads(entrada.read(65536))
        except FileNotFoundError:
            estado = {}
        contagens = estado["contagens"] if estado.get("expira") == expira else {}
        if contagens.get(indice, 0) >= maximo or (indice not in contagens and len(contagens) >= 256):
            return max(1, expira - agora)
        contagens[indice] = contagens.get(indice, 0) + 1
        with NamedTemporaryFile(mode="w", encoding="ascii", dir=pasta, delete=False) as saida:
            temporario = Path(saida.name)
            try:
                json.dump({"expira": expira, "contagens": contagens}, saida, separators=(",", ":"))
                saida.close()
                os.replace(temporario, arq)
            finally:
                temporario.unlink(missing_ok=True)
    return 0


def excesso_paginas(environ, endereco, limite_pedido, chave_valida):
    if limite_pedido < max(1, caminhos.inteiro("abuso", "pagina_grande_min")):
        return 0
    maximo = max(0, min(10000, caminhos.inteiro("abuso", "max_paginas_grandes")))
    if not maximo:
        return 0
    ip = _ip(endereco)
    if chave_valida:
        identidade = "chave " + environ["HTTP_X_RADAR_LEITURA"].strip()
    elif ip is not None:
        rede = ipaddress.ip_network((ip, 24 if ip.version == 4 else 64), strict=False)
        identidade = "rede " + str(rede)
    else:
        return 0
    indice = hashlib.sha256(identidade.encode()).hexdigest()
    janela = max(60, min(86400, caminhos.inteiro("abuso", "janela_segundos")))
    return _medir_pagina(indice, maximo, janela)
