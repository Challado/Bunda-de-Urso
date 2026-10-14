#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida TODOS os JSON versionados: parseiam e nao tem chave repetida.

JSON invalido derruba configuracao em runtime; chave repetida e pior: o
interpretador fica com a ULTIMA e ninguem ve que a primeira foi descartada.

    python3 .github/scripts/verificar_json.py
"""
import json
import sys

from comum import RAIZ, terminar, versionados


def sem_repeticao(pares):
    vistos = set()
    for chave, _ in pares:
        if chave in vistos:
            raise ValueError("chave repetida: %r" % chave)
        vistos.add(chave)
    return dict(pares)


def main():
    problemas = []
    arquivos = [f for f in versionados() if f.lower().endswith(".json")]
    for rel in arquivos:
        try:
            with (RAIZ / rel).open(encoding="utf-8") as fh:
                json.load(fh, object_pairs_hook=sem_repeticao)
        except (ValueError, UnicodeDecodeError, OSError) as e:
            problemas.append("%s: %s" % (rel, e))

    print("JSON conferidos: %d" % len(arquivos))
    return terminar(problemas, "Todos os JSON versionados estao validos e sem chave repetida.")


if __name__ == "__main__":
    sys.exit(main())
