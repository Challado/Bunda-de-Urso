#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Caminhos: ninguem decide instalacao por conta propria.

O codigo pergunta a ``core.caminhos`` (RADAR_CONF ou constante -> radar.conf
-> padroes documentados). Caminho absoluto de instalacao escrito na mao e o que
faz um script "mudar de diretorio" sem ninguem pedir: reprova aqui.

Ignorados de proposito:
  * ``referencia/``      -- material de terceiros arquivado, nao executa;
  * ``docs/``            -- documentacao (pode e deve citar caminho real);
  * ``tests/``           -- fixture de teste, doesn't ship;
  * ``deploy/radar.conf.exemplo`` -- e o MODELO da configuracao; mostrar os
    caminhos de producao ali e o proposito do arquivo.
"""
import re
import sys

from comum import RAIZ, terminar

PASTAS = ("core/", "coletor/", "web/", "tools/", "deploy/", ".github/scripts/")
SUFIXOS = (".py", ".pse", ".sh", ".html", ".json", ".service", ".conf", ".logrotate")
EXCECOES = {
    ".github/scripts/verificar_caminhos.py": "padroes de deteccao, nao caminhos usados pelo aplicativo",
    "deploy/radar.conf.exemplo": "modelo da configuracao: mostra os caminhos reais",
    "web/projeto.json": "URL publica da consulta (nao e caminho de arquivo)",
}

# Prefixos de instalacao que ja apareceram espalhados pelo codigo.
PROIBIDOS = (
    (r"/var/lib/radar[-_]?brasil", "banco/dados de instalacao"),
    (r"/var/log/radar[-_]?brasil", "logs de instalacao"),
    (r"/var/log/openclaw", "logs de instalacao"),
    (r"/opt/radar[-_]?brasil", "instalacao em /opt"),
    (r"/home/openclaw", "instalacao em /home"),
    (r"/var/www/html", "webroot de instalacao"),
    (r"/openclaw/", "instalacao em /openclaw"),
    (r"/srv/radar", "instalacao em /srv"),
)


def analisar(rel, texto):
    problemas = []
    for numero, linha in enumerate(texto.splitlines(), 1):
        if rel.endswith(".json"):
            # JSON pode citar URL/rota publica; so o que parece caminho de disco.
            if not re.search(r"\"/(var|opt|home|srv|openclaw)/", linha):
                continue
        for padrao, motivo in PROIBIDOS:
            achado = re.search(padrao, linha)
            if achado:
                problemas.append(
                    "%s:%d: caminho fixo '%s' (%s) — use core.caminhos "
                    "ou radar.conf" % (rel, numero, achado.group(0), motivo))
                break
    return problemas


def main():
    problemas = []
    arquivos = {p.relative_to(RAIZ).as_posix() for pasta in PASTAS
                for p in (RAIZ / pasta).rglob("*") if p.is_file()}
    for rel in sorted(arquivos):
        if rel in EXCECOES:
            continue
        if not rel.startswith(PASTAS) or not rel.endswith(SUFIXOS):
            continue
        caminho = RAIZ / rel
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        problemas.extend(analisar(rel, texto))
    return terminar(problemas, "Caminhos: core.caminhos usa somente o radar.conf selecionado.")


if __name__ == "__main__":
    sys.exit(main())
