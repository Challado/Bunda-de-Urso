# -*- coding: utf-8 -*-
"""Serializador XML (spec 12.3): UTF-8, nomes estaveis, xsi:nil para nulos."""
import xml.etree.ElementTree as ET

XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("xsi", XSI)

_SCALARS = (str, int, float, bool)


def _fill(parent, valor):
    if isinstance(valor, dict):
        for k, v in valor.items():
            if isinstance(v, list):
                container = ET.SubElement(parent, k)
                for item in v:
                    child = ET.SubElement(container, "item")
                    _fill(child, item)
            else:
                child = ET.SubElement(parent, k)
                _fill(child, v)
    elif isinstance(valor, list):
        for item in valor:
            child = ET.SubElement(parent, "item")
            _fill(child, item)
    elif valor is None:
        parent.set("{%s}nil" % XSI, "true")
    else:
        parent.text = "true" if valor is True else (
            "false" if valor is False else str(valor))


def dumps(records, meta):
    root = ET.Element("radar_brasil")
    root.set("versao_api", str(meta.get("versao_api")))
    root.set("versao_esquema", str(meta.get("versao_esquema")))
    root.set("sucesso", "true" if meta.get("sucesso", True) else "false")
    ET.SubElement(root, "consultado_em").text = str(meta.get("consultado_em"))

    _fill(ET.SubElement(root, "consulta"), meta.get("consulta", {}))
    _fill(ET.SubElement(root, "cobertura"), meta.get("cobertura", {}))
    _fill(ET.SubElement(root, "base"), meta.get("base", {}))

    resultado = ET.SubElement(root, "resultado")
    for k, v in meta.get("resultado", {}).items():
        if k == "pontos":
            continue
        child = ET.SubElement(resultado, k)
        _fill(child, v)
    pontos = ET.SubElement(resultado, "pontos")
    for p in records:
        _fill(ET.SubElement(pontos, "ponto"), p)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")
