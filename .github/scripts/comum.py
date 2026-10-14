# -*- coding: utf-8 -*-
"""Utilidades comuns dos verificadores do CI (stdlib pura, sem dependencia).

Cada verificador em .github/scripts/ e um script independente que sai com 0
(tudo certo) ou 1 (achou problema), imprimindo linhas ``::error::`` que o
GitHub Actions transforma em anotacao no arquivo/linha.
"""
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def versionados():
    """Arquivos versionados, relativos a raiz do repositorio."""
    saida = subprocess.run(
        ["git", "ls-files"], cwd=str(RAIZ),
        capture_output=True, text=True, check=True)
    return [linha for linha in saida.stdout.splitlines() if linha.strip()]


def erro(mensagem, arquivo=None):
    if arquivo:
        print("::error file=%s::%s" % (arquivo, mensagem))
    else:
        print("::error::%s" % mensagem)


def terminar(problemas, mensagem_ok):
    """Imprime a lista de problemas e devolve o codigo de saida."""
    if problemas:
        print("\n%d problema(s) encontrado(s):" % len(problemas))
        for p in problemas:
            print("  - %s" % p)
        for p in problemas:
            erro(p)
        return 1
    print(mensagem_ok)
    return 0
