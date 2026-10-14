#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roda a suite inteira e EXIGE um piso de testes.

"Verde vazio" e a cagada classica: um erro de coleta (import quebrado, path
errado) faz o unittest rodar 0 testes e sair com sucesso. Aqui isso reprova.

    python3 .github/scripts/rodar_suite.py
"""
import sys
import unittest

from comum import RAIZ

PISO = 600  # hoje sao 618; o piso pega coleta quebrada, nao engessa o numero


def main():
    sys.path.insert(0, str(RAIZ))
    suite = unittest.TestLoader().discover(start_dir=str(RAIZ / "tests"))
    resultado = unittest.TextTestRunner(verbosity=1).run(suite)

    total = resultado.testsRun
    pulados = [t.id() for t, _ in resultado.skipped]
    print("\ntestes=%d  falhas=%d  erros=%d  pulados=%d"
          % (total, len(resultado.failures), len(resultado.errors), len(pulados)))

    problemas = []
    if resultado.failures or resultado.errors:
        problemas.append("%d falha(s) e %d erro(s) na suite"
                         % (len(resultado.failures), len(resultado.errors)))
    if total < PISO:
        problemas.append("a suite rodou so %d testes (piso=%d): coleta quebrada?"
                         % (total, PISO))
    if problemas:
        for p in problemas:
            print("::error::%s" % p)
        return 1

    for nome in pulados:
        print("::warning::teste pulado: %s" % nome)
    print("Suite OK: %d testes, nenhuma falha (piso %d)." % (total, PISO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
