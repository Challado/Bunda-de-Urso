# -*- coding: utf-8 -*-
"""Serializador NDJSON (spec 12.2): 1a linha = meta, demais = 1 ponto/linha."""
import json

from . import json_ser


def dumps(records, meta):
    env = json_ser.envelope([], meta)
    resultado = dict(env["resultado"])
    resultado.pop("pontos", None)
    meta_line = {
        "tipo_registro": "meta",
        **{k: v for k, v in env.items() if k != "resultado"},
        "resultado": resultado,
    }
    lines = [json.dumps(meta_line, ensure_ascii=False, separators=(",", ":"),
                        default=str)]
    for p in records:
        registro = dict(p)
        registro.setdefault("tipo_registro", "ponto_fiscalizacao")
        lines.append(json.dumps(registro, ensure_ascii=False,
                                separators=(",", ":"), default=str))
    lines.append(json.dumps({
        "tipo_registro": "fechamento",
        "retornados": len(records),
    }, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n"
