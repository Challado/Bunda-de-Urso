#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integridade do front (web/): recursos, viewport e contrato com a API.

  1. todo href/src LOCAL existe no disco (link/asset quebrado = 404 em prod);
  2. toda pagina tem <meta name="viewport"> (tem de funcionar em celular,
     tablet e PC);
  3. toda rota /api/... que o front chama e atendida pelo nucleo web/nucleo.py;
  4. nada de http:// inseguro nem endereco local fixo no front.

    python3 .github/scripts/verificar_web.py
"""
import re
import sys

from comum import RAIZ, terminar

WEB = RAIZ / "web"
ATRIBUTO = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']')
LITERAL = re.compile(r'["\'](/api/[^"\']*)["\']')
VIA_QUERY = re.compile(r"rota=(/api/[^&\"']+)")
PLACEHOLDER = re.compile(r"\{[^}]*\}")
PULAR = ("#", "http://", "https://", "mailto:", "tel:", "javascript:", "data:")


def paginas():
    return sorted(WEB.glob("*.html"))


def padroes_api():
    """Rotas que o nucleo realmente atende (literais + /health/...)."""
    texto = (WEB / "nucleo.py").read_text(encoding="utf-8")
    caminhos = set(LITERAL.findall(texto))
    caminhos |= set(re.findall(r'"(/health/[^"]*)"', texto))
    return sorted(caminhos)


def regex_da_rota(padrao):
    partes, i = [], 0
    for m in PLACEHOLDER.finditer(padrao):
        partes.append(re.escape(padrao[i:m.start()]))
        partes.append("[^/]+")
        i = m.end()
    partes.append(re.escape(padrao[i:]))
    return re.compile("^" + "".join(partes) + "/?$")


def estatico(padrao):
    return PLACEHOLDER.split(padrao)[0].rstrip("/") or "/"


def servida(rota, padroes):
    """A rota do front e atendida? Aceita a rota inteira ou o prefixo que o JS
    concatena com um id depois (ex.: ``/api/v1/gestao/radar/`` + id)."""
    for p in padroes:
        if regex_da_rota(p).match(rota):
            return True
        base = estatico(p)
        if rota == base or base.startswith(rota + "/"):
            return True
    return False


def main():
    problemas = []
    padroes = padroes_api()
    if not padroes:
        return terminar(["nao extrai rota nenhuma de web/nucleo.py (parser quebrado)"], "")

    for pagina in paginas() + sorted(WEB.glob("*.js")):
        texto = pagina.read_text(encoding="utf-8")
        nome = pagina.name

        if pagina.suffix == '.html' and 'name="viewport"' not in texto:
            problemas.append('%s: falta <meta name="viewport">' % nome)

        for alvo in ATRIBUTO.findall(texto):
            if alvo.startswith(PULAR):
                continue
            limpo = alvo.split("#")[0].split("?")[0]
            if limpo and not (pagina.parent / limpo).exists():
                problemas.append("%s: recurso local inexistente: %s" % (nome, alvo))

        if "http://" in texto:
            problemas.append("%s: usa http:// (conteudo inseguro)" % nome)
        if "localhost" in texto or "127.0.0.1" in texto:
            problemas.append("%s: endereco local fixo no front" % nome)

        rotas = set(LITERAL.findall(texto)) | set(VIA_QUERY.findall(texto))
        for rota in rotas:
            if not servida(rota.rstrip("/") or "/", padroes):
                problemas.append("%s: chama rota nao atendida pela API: %s" % (nome, rota))

    print("paginas=%d  rotas declaradas na API=%d" % (len(paginas()), len(padroes)))
    return terminar(problemas, "Front integro: recursos no lugar, viewport ok e rotas batem com a API.")


if __name__ == "__main__":
    sys.exit(main())
