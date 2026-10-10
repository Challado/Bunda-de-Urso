# -*- coding: utf-8 -*-
"""Esqueleto funcional DIF - Data Interchange Format (spec 12.6).

Uma linha DIF por ponto, mesma ordem de 32 colunas do TXT; arrays/objetos em
celula string JSON. Convencao de NULL documentada: celula string com o
literal \\N (tipo 1), distinguivel de uma string real que contenha \\N apenas
quando o valor real for exatamente \\N (nesse caso a celula vem com \\.README).
Na pratica o consumidor trata "\\N" como ausente.
"""
from . import campos

_NULL_LITERAL = "\\N"


def _pair(v):
    if v is None:
        return '1,"%s"' % _NULL_LITERAL
    if isinstance(v, bool):
        return '1,"%s"' % ("true" if v else "false")
    if isinstance(v, (list, dict)):
        return "1," + _quote(campos.json_cell(v))
    if isinstance(v, (int,)):
        return "0,%d" % v
    if isinstance(v, float):
        return "0,%s" % repr(v)
    return "1," + _quote(str(v))


def _quote(s):
    return '"' + s.replace('"', '""') + '"'


def dumps(records, meta):
    linhas = []
    linhas.append("TABLE")
    linhas.append("0,%d" % len(campos.TXT_COLUMNS))
    linhas.append('"RADAR_BRASIL"')
    linhas.append("VECTORS")
    linhas.append("0,%d" % (len(records) + 1))
    linhas.append('""')
    linhas.append("TUPLES")
    linhas.append("0,%d" % len(campos.TXT_COLUMNS))
    linhas.append('""')
    linhas.append("DATA")
    linhas.append("0,0")
    linhas.append('""')
    # linha de cabecalho (nomes das colunas, todas string)
    linhas.append(",".join('1,"%s"' % c for c in campos.TXT_COLUMNS))
    for p in records:
        linhas.append("-1,0")
        linhas.append(",".join(_pair(c) for c in campos.build_cells(p)))
    linhas.append("-1,0")
    linhas.append("EOD")
    return "\n".join(linhas) + "\n"
