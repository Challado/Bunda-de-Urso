#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Invariantes de estrutura do repositorio.

  * arquivos que o projeto precisa ter existem;
  * nenhum artefato de build/execucao entrou no git (__pycache__, .pyc,
    bancos, .DS_Store, logs).

    python3 .github/scripts/verificar_estrutura.py
"""
import re
import sys

from comum import RAIZ, terminar, versionados

OBRIGATORIOS = [
    "README.md",
    "LICENSE",
    "web/api.pse",
    "web/index.html",
    "web/nucleo.py",
    "core/db.py",
    "core/caminhos.py",
    "deploy/radar.conf.exemplo",
    "deploy/conf_radar.py",
    "docs/CONFIGURACAO.md",
    "sql/schema.sqlite.sql",
    "sql/schema.postgres.sql",
    "sql/migracoes/0001_governanca.sqlite.sql",
    "sql/migracoes/0001_governanca.postgres.sql",
    ".github/workflows/testes.yml",
    ".github/scripts/comum.py",
    ".github/scripts/rodar_suite.py",
    ".github/scripts/verificar_sql.py",
    ".github/scripts/verificar_json.py",
    ".github/scripts/verificar_segredos.py",
    ".github/scripts/verificar_web.py",
    ".github/scripts/verificar_banco.py",
    ".github/scripts/verificar_caminhos.py",
    ".github/scripts/verificar_estrutura.py",
]

ARTEFATOS = [
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"\.py[co]$"),
    re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"\.(?:db|sqlite|sqlite3)$", re.I),
    re.compile(r"\.log$", re.I),
    re.compile(r"(^|/)(?:\.venv|venv)/"),
    re.compile(r"^dados/"),
]


def main():
    problemas = []
    arquivos = versionados()

    for rel in OBRIGATORIOS:
        if not (RAIZ / rel).exists():
            problemas.append("falta arquivo obrigatorio: %s" % rel)

    for rel in arquivos:
        for padrao in ARTEFATOS:
            if padrao.search(rel):
                problemas.append("artefato versionado (nao deveria): %s" % rel)
                break

    print("obrigatorios=%d  versionados=%d" % (len(OBRIGATORIOS), len(arquivos)))
    return terminar(problemas, "Estrutura integra: arquivos essenciais presentes e nenhum artefato versionado.")


if __name__ == "__main__":
    sys.exit(main())
