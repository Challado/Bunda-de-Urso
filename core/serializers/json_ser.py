# -*- coding: utf-8 -*-
"""Serializador JSON (spec 11, 12.1)."""
import json


def envelope(records, meta):
    """Envelope comum a todos os formatos estruturados."""
    consulta = meta.get("consulta", {})
    resultado = dict(meta.get("resultado", {}))
    resultado["pontos"] = records
    env = {
        "sucesso": meta.get("sucesso", True),
        "versao_api": meta.get("versao_api"),
        "versao_esquema": meta.get("versao_esquema"),
        "consultado_em": meta.get("consultado_em"),
        "consulta": consulta,
        "resultado": resultado,
        "cobertura": meta.get("cobertura", {}),
        "base": meta.get("base", {}),
    }
    if meta.get("erro"):
        env["erro"] = meta["erro"]
    return env


def dumps(records, meta):
    return json.dumps(envelope(records, meta), ensure_ascii=False,
                      separators=(",", ":"), default=str)
