"""Limites e identificação das consultas externas, por fonte e URL."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import json
import random
import re
from urllib.parse import urlsplit

from core import caminhos

LIMITES = {"timeout": (1, 3600), "tentativas": (1, 10), "max_bytes": (1, 1073741824)}
AGENTES = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
)
_CONTEXTO = ContextVar("consulta_fonte", default=(None, None))


@contextmanager
def fonte(chave):
    """Mantém a política da fonte na descoberta, no download e nas retentativas."""
    contexto = _CONTEXTO.set((chave, random.choice(AGENTES)))
    try:
        yield
    finally:
        _CONTEXTO.reset(contexto)


@lru_cache(maxsize=8)
def ler_regras(texto):
    """Valida as regras compartilhadas pelo painel e pelo coletor."""
    try:
        dados = json.loads(texto or "[]")
    except ValueError as exc:
        raise ValueError("As regras de consultas devem ser uma lista JSON.") from exc
    if not isinstance(dados, list):
        raise ValueError("As regras de consultas devem ser uma lista JSON.")
    chaves = set()
    parametros = {"user_agent", "verificar_ssl", *LIMITES}
    permitidos = {"fonte", "url", *parametros}
    for n, regra in enumerate(dados, start=1):
        rotulo = f"Regra de consulta {n}"
        if not isinstance(regra, dict) or set(regra) - permitidos:
            raise ValueError(f"{rotulo}: há um campo desconhecido.")
        chave = regra.get("fonte", "")
        if not isinstance(chave, str) or not re.fullmatch(r"\*|[a-z0-9_-]{1,80}", chave):
            raise ValueError(f"{rotulo}: informe a fonte ou * para todas.")
        prefixo = regra.get("url", "")
        if not isinstance(prefixo, str) or len(prefixo) > 2048 or re.search(r"\s|[\x00-\x1f\x7f]", prefixo):
            raise ValueError(f"{rotulo}: informe uma URL HTTPS sem espaços.")
        if prefixo:
            url = urlsplit(prefixo)
            if (url.scheme != "https" or not url.hostname or url.username is not None
                    or url.password is not None or url.fragment):
                raise ValueError(f"{rotulo}: use uma URL HTTPS sem credenciais ou fragmento.")
        if (chave, prefixo) in chaves:
            raise ValueError(f"{rotulo}: já existe uma regra para esta fonte e URL.")
        chaves.add((chave, prefixo))
        if not set(regra) & parametros:
            raise ValueError(f"{rotulo}: informe ao menos um parâmetro.")
        for campo, (minimo, maximo) in LIMITES.items():
            if campo in regra and (type(regra[campo]) is not int or not minimo <= regra[campo] <= maximo):
                raise ValueError(f"{rotulo}: {campo} deve ficar entre {minimo} e {maximo}.")
        if "verificar_ssl" in regra and type(regra["verificar_ssl"]) is not bool:
            raise ValueError(f"{rotulo}: verificar_ssl deve ser true ou false.")
        agente = regra.get("user_agent", "sistema")
        if not isinstance(agente, str) or not re.fullmatch(r"[ -~]{1,512}", agente) or agente != agente.strip():
            raise ValueError(f"{rotulo}: use um User-Agent de até 512 caracteres ASCII em uma linha.")
    return dados


def _corresponde(url, prefixo):
    if not prefixo:
        return True
    alvo, regra = urlsplit(url), urlsplit(prefixo)
    if alvo.scheme != regra.scheme or alvo.netloc.lower() != regra.netloc.lower():
        return False
    consulta = alvo.path + ("?" + alvo.query if alvo.query else "")
    inicio = regra.path + ("?" + regra.query if regra.query else "")
    return consulta.startswith(inicio)


def ajustes(url, **padroes):
    """Combina os padrões do transporte com as regras mais específicas."""
    if padroes.get("verificar_ssl") is None:
        padroes["verificar_ssl"] = caminhos.inteiro("coleta", "verificar_ssl") == 1
    chave, agente_aleatorio = _CONTEXTO.get()
    regras = ler_regras(caminhos.valor("consultas", "regras")[0])
    aplicaveis = [r for r in regras if r["fonte"] in ("*", chave) and _corresponde(url, r.get("url", ""))]
    for regra in sorted(aplicaveis, key=lambda r: (len(r.get("url", "")), r["fonte"] == chave)):
        padroes.update({k: v for k, v in regra.items() if k not in ("fonte", "url")})
    agente = padroes.get("user_agent", "sistema")
    if agente == "sistema":
        padroes["user_agent"] = None
    elif agente == "aleatorio":
        padroes["user_agent"] = agente_aleatorio or random.choice(AGENTES)
    padroes["modo_user_agent"] = agente if agente in ("sistema", "aleatorio") else "personalizado"
    padroes["fonte"] = chave
    return padroes
