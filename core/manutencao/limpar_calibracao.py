#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Limpeza das ancoras de calibracao + segmentacao por trecho consistente.

Le ``dados/calibracao/ancoras.csv`` (gerado por ``tools/gerar_calibracao.py``) e
aplica, sem inventar dado (campo ausente = ausente):

(a) filtro de caixa do Brasil -- descarta ancora cuja coordenada cai fora de
    ``lat -34.0..+5.5`` e ``lon -74.0..-28.0``. Isso captura o erro classico de
    sinal/ordem da longitude (ex.: lon=+49,465963 em GO-070, ou lat==lon).

(b) segmentacao por via -- ordena as ancoras por km; para cada par consecutivo
    calcula a distancia Haversine ``d`` (m) e o delta de km ``k``; se
    ``d > 3*k*1000 + 20000`` a geometria anda muito mais que o km, ou seja o km
    nao e consistente (outro trecho/estado na mesma ``codigo`` de via) => ABRE UM
    NOVO SEGMENTO. O numero do segmento comeca em 1 por via.

Saidas (dados gerados, nao sobrescreve codigo-fonte):
  dados/calibracao/ancoras_limpas.csv    via;segmento;km;lat;lon;ponto_id;fonte
  dados/calibracao/resumo_segmentos.csv  via;segmento;n;km_min;km_max

Uso:
  python3 tools/limpar_calibracao.py [--ancoras CSV] [--saida DIR]
"""
import argparse
import csv
import os
import sys


from core.config import ROOT  # noqa: E402
from core.geo import haversine_m  # noqa: E402
from core.contexto_api import operacao_local

ANCORAS_PADRAO = os.path.join(ROOT, "dados", "calibracao", "ancoras.csv")
SAIDA_PADRAO = os.path.join(ROOT, "dados", "calibracao")

# Caixa geografica que engloba o Brasil (folga generosa).
LAT_MIN, LAT_MAX = -34.0, 5.5
LON_MIN, LON_MAX = -74.0, -28.0

# Regra de segmentacao: distancia permitida entre ancoras vizinhas de km.
FATOR_GEOMETRIA = 3.0        # 1 km de via nunca "anda" mais de 3 km no plano
FOLGA_M = 20000.0            # folga fixa (reancoragem de GPS, curvas amplas)


def _float_ou_none(v):
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _int_ou_none(v):
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def dentro_da_caixa(lat, lon):
    """True se (lat, lon) esta dentro da caixa do Brasil."""
    return (LAT_MIN <= lat <= LAT_MAX) and (LON_MIN <= lon <= LON_MAX)


def aplicar_filtro(registros):
    """Separa as ancoras em (mantidas, descartes).

    ``registros`` e uma lista de dicts com ``via, km, lat, lon, ponto_id, fonte``
    (tipos ja convertidos). ``descartes`` e ``{motivo: n}`` com motivos
    ``campo_ausente``, ``fora_lat`` e ``fora_lon``.
    """
    mantidas = []
    descartes = {"campo_ausente": 0, "fora_lat": 0, "fora_lon": 0}
    for r in registros:
        if r["via"] is None or r["km"] is None or r["lat"] is None or r["lon"] is None:
            descartes["campo_ausente"] += 1
            continue
        if not (LAT_MIN <= r["lat"] <= LAT_MAX):
            descartes["fora_lat"] += 1
            continue
        if not (LON_MIN <= r["lon"] <= LON_MAX):
            descartes["fora_lon"] += 1
            continue
        mantidas.append(r)
    return mantidas, descartes


def segmentar(ancoras):
    """Divide as ancoras (ja filtradas) em segmentos de km consistente.

    ``ancoras`` deve estar ordenada por km (e ponto_id). Retorna lista de
    listas (cada sublista e um segmento, na ordem do km).
    """
    segmentos = []
    atual = []
    anterior = None
    for a in ancoras:
        if anterior is None:
            atual.append(a)
        else:
            k = a["km"] - anterior["km"]
            d = haversine_m(anterior["lat"], anterior["lon"], a["lat"], a["lon"])
            if d > FATOR_GEOMETRIA * k * 1000.0 + FOLGA_M:
                segmentos.append(atual)
                atual = [a]
            else:
                atual.append(a)
        anterior = a
    if atual:
        segmentos.append(atual)
    return segmentos


def _chave_ordem(a):
    pid = a["ponto_id"]
    return (a["km"], -1 if pid is None else pid)


def ler_ancoras(caminho):
    """Le o CSV bruto de ancoras devolvendo lista de dicts (com tipos)."""
    regs = []
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            regs.append({
                "via": (row.get("via") or "").strip() or None,
                "km": _float_ou_none(row.get("km")),
                "lat": _float_ou_none(row.get("lat")),
                "lon": _float_ou_none(row.get("lon")),
                "ponto_id": _int_ou_none(row.get("ponto_id")),
                "fonte": (row.get("fonte") or "").strip() or None,
            })
    return regs


def _f(x):
    return repr(float(x))


def escrever(mantidas, saida_dir):
    """Escreve ancoras_limpas.csv e resumo_segmentos.csv; devolve estatisticas."""
    os.makedirs(saida_dir, exist_ok=True)
    cam_limpas = os.path.join(saida_dir, "ancoras_limpas.csv")
    cam_resumo = os.path.join(saida_dir, "resumo_segmentos.csv")

    por_via = {}
    for r in mantidas:
        por_via.setdefault(r["via"], []).append(r)

    n_segmentos = 0
    n_vias = 0
    with open(cam_limpas, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "segmento", "km", "lat", "lon", "ponto_id", "fonte"])
        for via in sorted(por_via):
            n_vias += 1
            ancoras = sorted(por_via[via], key=_chave_ordem)
            segmentos = segmentar(ancoras)
            for seg_i, seg in enumerate(segmentos, start=1):
                n_segmentos += 1
                for a in seg:
                    w.writerow([via, seg_i, _f(a["km"]), _f(a["lat"]),
                                _f(a["lon"]), a["ponto_id"], a["fonte"] or ""])

    with open(cam_resumo, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["via", "segmento", "n", "km_min", "km_max"])
        for via in sorted(por_via):
            ancoras = sorted(por_via[via], key=_chave_ordem)
            segmentos = segmentar(ancoras)
            for seg_i, seg in enumerate(segmentos, start=1):
                kms = [a["km"] for a in seg]
                w.writerow([via, seg_i, len(seg), _f(min(kms)), _f(max(kms))])

    return cam_limpas, cam_resumo, n_vias, n_segmentos


@operacao_local
def main(argv=None):
    ap = argparse.ArgumentParser(description="Limpa e segmenta as ancoras de calibracao.")
    ap.add_argument("--ancoras", default=ANCORAS_PADRAO,
                    help="CSV bruto de ancoras (default: dados/calibracao/ancoras.csv)")
    ap.add_argument("--saida", default=SAIDA_PADRAO, help="diretorio de saida")
    args = ap.parse_args(argv)

    if not os.path.exists(args.ancoras):
        print("ERRO: ancoras nao encontradas: %s (rode tools/gerar_calibracao.py)"
              % args.ancoras, file=sys.stderr)
        return 2

    regs = ler_ancoras(args.ancoras)
    mantidas, descartes = aplicar_filtro(regs)
    cam_limpas, cam_resumo, n_vias, n_segmentos = escrever(mantidas, args.saida)

    total = len(regs)
    desc_total = sum(descartes.values())
    print("ancoras de origem:  %d" % total)
    print("descartadas (caixa do Brasil): %d  (fora_lat=%d, fora_lon=%d, campo_ausente=%d)"
          % (desc_total, descartes["fora_lat"], descartes["fora_lon"],
             descartes["campo_ausente"]))
    print("ancoras limpas:     %d" % len(mantidas))
    print("vias:               %d" % n_vias)
    print("segmentos:          %d" % n_segmentos)
    print("ancoras_limpas.csv:    %s" % cam_limpas)
    print("resumo_segmentos.csv:  %s" % cam_resumo)
    return 0
