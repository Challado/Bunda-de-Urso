# -*- coding: utf-8 -*-
"""Resolvedor de coordenada por referenciamento linear rodoviario (km -> lat/lon).

Interpola a coordenada de um km entre as DUAS ancoras vizinhas da MESMA via,
tendo como ancoras os nossos proprios pontos oficiais que ja trazem km +
coordenada (ver ``tools/gerar_calibracao.py`` / ``dados/calibracao/ancoras.csv``).

Garantias (regras da tarefa):

  * NUNCA mistura vias diferentes — cada via tem a sua propria lista de ancoras;
  * km fora do intervalo coberto pelas ancoras => ``status='fora_de_faixa'``
    (nao extrapola em silencio);
  * via com menos de 2 ancoras => ``status='sem_calibracao'``;
  * resultado de interpolacao => ``qualidade='inferida'``, ``metodo='linear_km'``.

Sem dependencias externas (somente stdlib). NAO grava nada no banco.
"""
import csv
import os

from .geo import haversine_m

# Caminho padrao do arquivo de ancoras gerado por tools/gerar_calibracao.py.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_ANCORAS_PADRAO = os.path.join(_RAIZ, "dados", "calibracao", "ancoras.csv")

QUALIDADE_INFERIDA = "inferida"
METODO = "linear_km"

STATUS_OK = "ok"
STATUS_FORA = "fora_de_faixa"
STATUS_SEM = "sem_calibracao"


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


def _norm_via(via):
    if via is None:
        return None
    via = str(via).strip()
    return via or None


def carregar_ancoras(caminho=None):
    """Le o CSV de ancoras e devolve ``{via: [ancora, ...]}`` ordenado por km.

    Cada ancora e um dict com ``km, lat, lon, ponto_id, uf, fonte``. Linhas sem
    via, km, lat ou lon sao descartadas (campo ausente = ausente; nao inventa).
    """
    caminho = caminho or CAMINHO_ANCORAS_PADRAO
    por_via = {}
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            via = _norm_via(row.get("via"))
            km = _float_ou_none(row.get("km"))
            lat = _float_ou_none(row.get("lat"))
            lon = _float_ou_none(row.get("lon"))
            if via is None or km is None or lat is None or lon is None:
                continue
            ancora = {
                "km": km,
                "lat": lat,
                "lon": lon,
                "ponto_id": _int_ou_none(row.get("ponto_id")),
                "uf": (row.get("uf") or "").strip() or None,
                "fonte": (row.get("fonte") or "").strip() or None,
            }
            por_via.setdefault(via, []).append(ancora)
    for via in por_via:
        por_via[via].sort(key=_chave_ordem)
    return por_via


def _chave_ordem(a):
    pid = a.get("ponto_id")
    return (a["km"], -1 if pid is None else pid)


def _resumo(status, via, km, n, qualidade=None, lat=None, lon=None,
            antes=None, depois=None):
    return {
        "status": status,
        "via": via,
        "km": km,
        "qualidade": qualidade,
        "metodo": METODO,
        "lat": lat,
        "lon": lon,
        "ancora_antes": antes,
        "ancora_depois": depois,
        "n_ancoras_via": n,
    }


def resolver(via, km, calibracao=None):
    """Resolve ``(via, km)`` em ``{lat, lon, ...}`` por interpolacao linear.

    ``calibracao`` e o dict ``{via: [ancoras]}`` (ex.: de ``carregar_ancoras``).
    Se ``None``, carrega ``dados/calibracao/ancoras.csv``.

    Retorna dict com ``status``:

      * ``'ok'``            -> lat/lon preenchidos (``qualidade='inferida'``);
      * ``'fora_de_faixa'`` -> km fora do intervalo das ancoras (lat/lon None);
      * ``'sem_calibracao'``-> via desconhecida ou com menos de 2 ancoras.

    Em todos os casos devolve ``via``, ``km``, ``metodo``, ``n_ancoras_via`` e
    (quando aplicavel) ``ancora_antes``/``ancora_depois``.
    """
    if calibracao is None:
        calibracao = carregar_ancoras()

    via = _norm_via(via)
    if km is None:
        raise ValueError("km obrigatorio")
    try:
        km = float(km)
    except (TypeError, ValueError):
        raise ValueError("km deve ser numerico: %r" % (km,))

    ancoras = list(calibracao.get(via) or []) if via is not None else []
    ancoras.sort(key=_chave_ordem)
    n = len(ancoras)

    if via is None or n < 2:
        return _resumo(STATUS_SEM, via, km, n)

    primeira = ancoras[0]
    ultima = ancoras[-1]

    if km < primeira["km"] or km > ultima["km"]:
        antes = None
        depois = None
        for a in ancoras:
            if a["km"] <= km:
                antes = a
            else:
                depois = a
                break
        return _resumo(STATUS_FORA, via, km, n, antes=antes, depois=depois)

    # Par de ancoras que contem o km (km dentro de [primeira, ultima]).
    antes = ancoras[0]
    depois = ancoras[-1]
    for i in range(n - 1):
        a = ancoras[i]
        b = ancoras[i + 1]
        if a["km"] <= km <= b["km"]:
            antes, depois = a, b
            break

    dkm = depois["km"] - antes["km"]
    t = 0.0 if dkm == 0 else (km - antes["km"]) / dkm
    lat = antes["lat"] + t * (depois["lat"] - antes["lat"])
    lon = antes["lon"] + t * (depois["lon"] - antes["lon"])

    return _resumo(STATUS_OK, via, km, n, qualidade=QUALIDADE_INFERIDA,
                   lat=lat, lon=lon, antes=antes, depois=depois)


def erro_m(resultado, lat, lon):
    """Erro Haversine (m) entre um resultado resolvido e a coordenada real."""
    if resultado.get("lat") is None or resultado.get("lon") is None:
        return None
    return haversine_m(resultado["lat"], resultado["lon"], lat, lon)
