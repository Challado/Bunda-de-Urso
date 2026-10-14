#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Varredura de segredos e de arquivos sensiveis versionados.

Duas frentes:
  1. CONTEUDO: padroes de alta confianca (tokens do GitHub, AWS, Google,
     Slack, Telegram; chaves privadas; JWT) em qualquer arquivo versionado;
  2. NOMES: arquivos que NUNCA devem entrar no git (.env, config.php, *.pem,
     *.key, credencial de conta de servico).

    python3 .github/scripts/verificar_segredos.py
"""
import re
import sys

from comum import RAIZ, terminar, versionados

PADROES = [
    ("token do GitHub",
     re.compile(r"\b(?:gh[porsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("chave da AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("chave do Google", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("token do Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("token de bot do Telegram", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b")),
    ("chave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
]

NOMES = [
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)config\.php$"),
    re.compile(r"\.(?:pem|key|p12|pfx)$", re.I),
    re.compile(r"(^|/)id_(?:rsa|ed25519)$"),
    re.compile(r"conta[-_]servico.*\.json$", re.I),
    re.compile(r"(^|/)credentials\.json$", re.I),
    re.compile(r"(^|/)secrets\.env$"),
]


def e_binario(dados):
    return b"\x00" in dados[:8000]


def main():
    problemas = []
    arquivos = versionados()
    for rel in arquivos:
        for padrao in NOMES:
            if padrao.search(rel):
                problemas.append("%s: arquivo sensivel versionado" % rel)
                break
        try:
            dados = (RAIZ / rel).read_bytes()
        except OSError as e:
            problemas.append("%s: nao consegui ler (%s)" % (rel, e))
            continue
        if e_binario(dados):
            continue
        texto = dados.decode("utf-8", "replace")
        for rotulo, padrao in PADROES:
            for m in padrao.finditer(texto):
                linha = texto.count("\n", 0, m.start()) + 1
                problemas.append("%s:%d: possivel %s" % (rel, linha, rotulo))

    print("arquivos versionados conferidos: %d" % len(arquivos))
    return terminar(problemas, "Nenhum segredo de alto sinal e nenhum arquivo sensivel versionado.")


if __name__ == "__main__":
    sys.exit(main())
