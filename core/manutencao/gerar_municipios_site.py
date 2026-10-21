#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera ``web/municipios.json`` para o combo de municipio do mapa.

Baixa a lista publica de municipios do repositorio
``kelvins/municipios-brasileiros`` (JSON com ``codigo_ibge``, ``nome``,
``latitude``, ``longitude`` e ``codigo_uf``) e a de estados (``codigo_uf`` ->
sigla), e grava uma versao COMPACTA para o autocomplete da pagina:

    [{"i": <codigo_ibge>, "n": <nome>, "u": <UF>, "a": <lat>, "o": <lon>}, ...]

O download usa ``coletor.http.baixar`` (norma da casa), nao URL chumbada como
unica opcao.

Uso:
  python3 tools/gerar_municipios_site.py [--saida web/municipios.json]
"""
import argparse
import json
import os
import sys


from coletor import http                              # noqa: E402
from core.config import ROOT                          # noqa: E402
from core.contexto_api import operacao_local

BASE = ("https://raw.githubusercontent.com/kelvins/"
        "municipios-brasileiros/main/json/")
SAIDA_PADRAO = os.path.join(ROOT, "web", "municipios.json")


def _json(url):
    corpo, _h, _u = http.baixar(url, timeout=60, max_bytes=16 * 1024 * 1024)
    return json.loads(corpo.decode("utf-8-sig"))


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera o municipios.json do combo.")
    ap.add_argument("--saida", default=SAIDA_PADRAO)
    args = ap.parse_args(argv)

    municipios = _json(BASE + "municipios.json")
    estados = _json(BASE + "estados.json")
    sigla = {}
    for e in estados:
        cod = e.get("codigo_uf") or e.get("codigo")
        uf = e.get("uf") or e.get("sigla")
        if cod is not None and uf:
            sigla[int(cod)] = str(uf).upper()

    saida = []
    for m in municipios:
        cod = m.get("codigo_ibge")
        nome = (m.get("nome") or "").strip()
        cu = m.get("codigo_uf")
        uf = sigla.get(int(cu)) if cu is not None else None
        if cod is None or not nome or not uf:
            continue
        saida.append({"i": int(cod), "n": nome, "u": uf,
                      "a": m.get("latitude"), "o": m.get("longitude")})
    saida.sort(key=lambda x: x["n"])

    os.makedirs(os.path.dirname(args.saida), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    tam = os.path.getsize(args.saida)
    ufs = sorted({x["u"] for x in saida})
    print("municipios: %d | UFs: %d | arquivo: %s (%.1f KB)"
          % (len(saida), len(ufs), args.saida, tam / 1024.0))
    return 0
