#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regra do dono: nada escreve direto no banco por fora do app.

  * O painel (web/) fala com a API, NUNCA com o SQLite -- nenhuma tela abre
    conexao nem menciona sqlite;
  * No nucleo do servico (core/, coletor/) quem abre conexao e so core/db.py;
  * tools/ e isento: roda a mao, fora do servico (manutencao offline).

    python3 .github/scripts/verificar_banco.py
"""
import re
import sys

from comum import RAIZ, terminar, versionados

CONEXAO = re.compile(r"sqlite3\.connect\s*\(")
MENCIONA_SQLITE = re.compile(r"\bsqlite3\b")


def main():
    problemas = []
    for rel in versionados():
        if not rel.endswith((".py", ".pse", ".html")):
            continue
        try:
            texto = (RAIZ / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        if rel.startswith("web/"):
            if MENCIONA_SQLITE.search(texto):
                problemas.append("%s: o painel nao pode falar com o SQLite (so API)" % rel)
            continue

        if rel.startswith(("core/", "coletor/")) and rel != "core/db.py":
            if CONEXAO.search(texto):
                problemas.append("%s: abre conexao propria (o unico caminho e core/db.py)" % rel)

    return terminar(
        problemas,
        "Nada escreve direto no banco fora do caminho unico (core/db.py); o painel so usa a API.")


if __name__ == "__main__":
    sys.exit(main())
