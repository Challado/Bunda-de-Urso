#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constroi a MALHA municipal SIMPLIFICADA versionada no repositorio.

Le as malhas por UF do cache oficial (``dados/raw/ibge_malha_municipios_<UF>``,
baixadas por ``core.geo_municipio`` da API v3 do IBGE) e grava UMA
FeatureCollection simplificada em
``config/ibge_malha_municipios.geojson.gz`` (git):

  - mantem apenas ``properties.codarea`` (codigo IBGE de 7 digitos) e ``uf``;
  - arredonda cada coordenada para ``CASAS_DECIMAIS`` (~11 m): nao muda a
    qual jurisdicao um ponto pertence, salvo a menos de ~11 m de uma divisa;
  - compacta o JSON (sem espacos) e comprime com gzip.

Uso:
  python3 tools/construir_malha.py [--destino CAMINHO] [--casas N] [--forcar]
"""
import argparse
import glob
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config                          # noqa: E402
from core import geo_municipio as geo            # noqa: E402

DESTINO_PADRAO = geo.MALHA_VERSIONADA


def _arredonda(v, casas):
    return round(float(v), casas)


def simplificar_feature(feature, uf, casas):
    props = (feature or {}).get("properties") or {}
    cod = props.get("codarea")
    geom = (feature or {}).get("geometry") or {}
    if cod is None or geom.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    tipo = geom["type"]
    coords = geom.get("coordinates") or []
    if tipo == "Polygon":
        novos = [[[_arredonda(p[0], casas), _arredonda(p[1], casas)]
                  for p in anel] for anel in coords]
        if not novos:
            return None
        out = {"type": "Polygon", "coordinates": novos}
    else:
        novos = []
        for poligono in coords:
            aneis = [[[_arredonda(p[0], casas), _arredonda(p[1], casas)]
                      for p in anel] for anel in poligono]
            if aneis:
                novos.append(aneis)
        if not novos:
            return None
        out = {"type": "MultiPolygon", "coordinates": novos}
    return {"type": "Feature",
            "properties": {"codarea": str(cod).strip(),
                           "uf": (uf or props.get("uf"))},
            "geometry": out}


def construir(cache_dir, destino, casas=geo.CASAS_DECIMAIS, forcar=False):
    ufs = geo.UFS
    features = []
    for uf in ufs:
        caminho = geo._cache_arquivo(cache_dir, uf)
        if not os.path.exists(caminho):
            print("AVISO: sem cache para %s (%s)" % (uf, caminho),
                  file=sys.stderr)
            continue
        with open(caminho, "r", encoding="utf-8") as f:
            fc = json.load(f)
        for feat in fc.get("features", []) or []:
            s = simplificar_feature(feat, uf, casas)
            if s is not None:
                features.append(s)
    if not features:
        return None, 0
    colecao = {"type": "FeatureCollection", "features": features}
    texto = json.dumps(colecao, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with gzip.GzipFile(destino, "wb", mtime=0) as gz:
        gz.write(texto)
    return destino, len(features)


def _tamanho(caminho):
    return os.path.getsize(caminho) if os.path.exists(caminho) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Malha municipal simplificada.")
    ap.add_argument("--cache", default=config.RAW_DIR, help="cache das malhas")
    ap.add_argument("--destino", default=DESTINO_PADRAO,
                    help="arquivo .geojson.gz de saida")
    ap.add_argument("--casas", type=int, default=geo.CASAS_DECIMAIS,
                    help="casas decimais (default %d)" % geo.CASAS_DECIMAIS)
    ap.add_argument("--forcar", action="store_true",
                    help="rebaixa as malhas antes de simplificar")
    args = ap.parse_args(argv)

    if args.forcar:
        geo.atualizar_malha()

    bruto = sum(_tamanho(geo._cache_arquivo(args.cache, uf)) for uf in geo.UFS)
    destino, n = construir(args.cache, args.destino, casas=args.casas)
    if destino is None:
        print("ERRO: nenhuma feicao municipal para simplificar", file=sys.stderr)
        return 2
    # tamanho descomprimido (para o relatorio)
    with gzip.open(destino, "rb") as gz:
        cru = len(gz.read())
    print("municipios simplificados: %d" % n)
    print("cache por UF (bruto):      %.2f MB" % (bruto / 1048576.0))
    print("simplificado (descompact): %.2f MB" % (cru / 1048576.0))
    print("versionado (gzip):         %.2f MB -> %s"
          % (_tamanho(destino) / 1048576.0, destino))
    return 0


if __name__ == "__main__":
    sys.exit(main())
