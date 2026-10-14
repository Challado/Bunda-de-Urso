# -*- coding: utf-8 -*-
"""Esqueleto funcional UN/EDIFACT (spec 12.5).

Envelope UNB/UNZ + UNH/UNT validos, com contagens e escaping corretos.
'Segmento' de dados: usa FTX (texto livre) para o bloco de consulta e um
segmento de projeto RAD0 (documentado - NAO e segmento padronizado) por
ponto, carregando as 32 colunas como componentes. O mapeamento e o guia de
implementacao ficam documentados aqui; nao se afirma que RAD0 seja do
diretorio UN/EDIFACT.
"""
import datetime

from . import campos

# Separadores UN/EDIFACT
SEG = "'"        # terminador de segmento
ELEM = "+"       # separador de elemento
COMP = ":"       # separador de componente
RELEASE = "?"    # caractere de escape


def _esc(s):
    """Escapa separadores reservados do EDIFACT."""
    if s is None:
        s = ""
    s = str(s)
    for ch in (RELEASE, SEG, ELEM, COMP):
        s = s.replace(ch, RELEASE + ch)
    return s


def _comp(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return _esc(campos.json_cell(v))
    if isinstance(v, bool):
        return "true" if v else "false"
    return _esc(v)


def dumps(records, meta):
    agora = datetime.datetime.utcnow()
    dt = agora.strftime("%y%m%d:%H%M")
    ref = agora.strftime("%y%m%d%H%M%S")
    segs = []
    segs.append("UNB" + ELEM.join([
        "UNOC" + COMP + "3",
        "RADARBRASIL" + COMP + "ZZ",
        "RECEPTOR" + COMP + "ZZ",
        dt, ref]))
    segs.append("UNH" + ELEM + ref + ELEM + "GENRAL" + COMP + "D" + COMP +
                "96A" + COMP + "UN")
    segs.append("BGM" + ELEM + "RADAR_BRASIL" + ELEM + ref)
    segs.append("DTM" + ELEM + "137" + COMP + str(meta.get("consultado_em")))
    n_seg = len(segs) + 1  # + UNT
    for p in records:
        celulas = campos.build_cells(p)
        comps = [str(i + 1) for i in range(len(campos.TXT_COLUMNS))]
        segs.append("RAD0" + ELEM + ELEM.join(
            _comp(c) for c in celulas))
        n_seg += 1
    segs.append("UNT" + ELEM + str(n_seg) + ELEM + ref)
    segs.append("UNZ" + ELEM + "1" + ELEM + ref)
    return SEG.join(segs) + SEG + "\n"
