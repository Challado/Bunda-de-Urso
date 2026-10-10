# -*- coding: utf-8 -*-
"""Serializadores do Radar Brasil (spec 12).

Todos partem da MESMA projecao canonica do ponto, garantindo paridade entre
json / ndjson / xml / txt (e os esqueletos edifact/dif).
"""
from . import json_ser
from . import ndjson_ser
from . import xml_ser
from . import txt_ser
from . import edifact_ser
from . import dif_ser

# formato -> (funcao, content_type)
_REGISTRY = {
    "json": (json_ser.dumps, "application/json; charset=utf-8"),
    "ndjson": (ndjson_ser.dumps, "application/x-ndjson; charset=utf-8"),
    "xml": (xml_ser.dumps, "application/xml; charset=utf-8"),
    "txt": (txt_ser.dumps, "text/plain; charset=utf-8"),
    "edi": (edifact_ser.dumps, "application/EDIFACT; charset=utf-8"),
    "edifact": (edifact_ser.dumps, "application/EDIFACT; charset=utf-8"),
    "dif": (dif_ser.dumps, "text/plain; charset=utf-8"),
}

FORMATOS = ("json", "ndjson", "xml", "txt", "edi", "edifact", "dif")


def is_valido(formato):
    return formato in _REGISTRY


def content_type(formato):
    return _REGISTRY[formato][1]


def serialize(formato, records, meta, delimitador="|"):
    """Retorna (content_type, corpo_como_str_unicode)."""
    if formato not in _REGISTRY:
        raise ValueError("formato invalido: %s" % formato)
    funcao, ctype = _REGISTRY[formato]
    if formato == "txt":
        body = funcao(records, meta, delimitador=delimitador)
    elif formato == "dif":
        body = funcao(records, meta)
    else:
        body = funcao(records, meta)
    return ctype, body
