# -*- coding: utf-8 -*-
"""Serializador TXT (spec 12.4): 1 linha por ponto, 32 colunas fixas,
delimitador trocavel, NULL=\\N, JSON compacto na celula, escape CSV.

Sem cabecalho no corpo, sem blocos. Corpo vazio quando nao ha pontos
(a decisao 'sem cobertura' e do nucleo HTTP, nao do serializador).
"""
from . import campos

# Delimitadores proibidos por serem inseguros/ambiguos.
_PROIBIDOS = {"\r", "\n", "\x00", '"'}


def validar_delimitador(d):
    if d is None or d == "":
        return "|"
    if not isinstance(d, str):
        raise ValueError("delimitador invalido")
    if len(d) != 1:
        raise ValueError("delimitador deve ter exatamente 1 caractere")
    if d in _PROIBIDOS:
        raise ValueError("delimitador inseguro: %r" % d)
    return d


def _celula_texto(v):
    """Converte um valor canonico em texto de celula (None = NULL)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return campos.json_cell(v)
    return str(v)


def formatar_celula(v, delim):
    """NULL -> \\N (sem aspas); string literal \\N -> '"\\N"'; CR/LF escapados;
    celula com delimiter/aspas fica entre aspas duplas com escape duplicado."""
    texto = _celula_texto(v)
    if texto is None:
        return "\\N"
    # Escapa CR/LF internos para nao quebrar o registro.
    texto = texto.replace("\r", "\\r").replace("\n", "\\n")
    precisa_aspas = (delim in texto) or ('"' in texto) or (texto == "\\N")
    if precisa_aspas:
        return '"' + texto.replace('"', '""') + '"'
    return texto


def dumps(records, meta, delimitador="|"):
    delim = validar_delimitador(delimitador)
    linhas = []
    for p in records:
        celulas = campos.build_cells(p)
        linhas.append(delim.join(formatar_celula(c, delim) for c in celulas))
    if not linhas:
        return ""
    return "\n".join(linhas) + "\n"
