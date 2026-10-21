"""Extracao estrita de rodovia/km publicados, sem estimar coordenadas."""
import re
from decimal import Decimal

_UFS = 'AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO'
_VIA = re.compile(r'\b(BR|' + _UFS + r')\s*[-–]?\s*(\d{2,3})\b', re.I)
_KM = re.compile(r'\bKM\s*(\d{1,4})(?:(?:\s*\+\s*(\d{3}))|[.,](\d{3}))(?!\d|[.,+]\d)', re.I)


def extrair(valor):
    """Uma rodovia e um marco com metros explicitos; ambiguos devolvem None."""
    texto = str(valor or '')
    vias, kms = list(_VIA.finditer(texto)), list(_KM.finditer(texto))
    if len(vias) != 1 or len(kms) != 1:
        return None
    # Intervalos e referencia a outro km nao representam uma unica instalacao.
    if len(re.findall(r'\bKM\b|\bKM(?=\d)', texto, re.I)) != 1:
        return None
    fim = texto[kms[0].end():]
    if re.match(r'\s*(?:M\b)?\s*(?:A\b|AT[EÉ]\b|[-–])\s*\d', fim, re.I):
        return None
    via = vias[0].group(1).upper() + '-' + vias[0].group(2).zfill(3)
    km = Decimal(kms[0].group(1)) + Decimal(kms[0].group(2) or kms[0].group(3)) / 1000
    return via, float(km)
