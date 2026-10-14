# -*- coding: utf-8 -*-
"""Resolvedor de coordenada por referenciamento linear rodoviario (km -> lat/lon).

Interpola a coordenada de um km entre as DUAS ancoras vizinhas do MESMO segmento
da via, tendo como ancoras os nossos proprios pontos oficiais que ja trazem km +
coordenada (ver ``tools/gerar_calibracao.py`` / ``tools/limpar_calibracao.py``).

Os dados limpos (``dados/calibracao/ancoras_limpas.csv``) trazem a coluna
``segmento``: o km de uma mesma ``codigo`` de via (ex.: BR-101) pode nao ser
consistente ao longo de todo o tracado (trechos/estados diferentes usam a
mesma numeracao). Um segmento e um trecho em que o km varia de forma coerente
com a geometria.

Garantias (regras da tarefa):

  * NUNCA mistura vias diferentes — cada via tem a sua propria lista de ancoras;
  * dado ``(via, km)``:
      - EXATAMENTE UM segmento cobre o km => interpola (``status='ok'``,
        ``qualidade='inferida'``, ``metodo='linear_km'``, inclui ``segmento``);
      - MAIS DE UM segmento cobre o km => ``status='ambiguo'`` (nao escolhe,
        nao extrapola);
      - NENHUM segmento cobre o km => ``status='fora_de_faixa'``;
      - via desconhecida ou com menos de 2 ancoras => ``status='sem_calibracao'``.

Sem dependencias externas (somente stdlib). NAO grava nada no banco.
"""
import csv
import os

from .geo import haversine_m

# Caminho padrao do arquivo de ancoras LIMPO (gerado por tools/limpar_calibracao.py),
# que ja traz a coluna ``segmento``. O arquivo bruto de tools/gerar_calibracao.py
# (sem ``segmento``) tambem pode ser carregado: todas as ancoras caem no segmento 1.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_ANCORAS_PADRAO = os.path.join(
    _RAIZ, "dados", "calibracao", "ancoras_limpas.csv")
# Arquivo bruto (sem limpeza/segmentacao), mantido para comparacao/reproducao.
CAMINHO_ANCORAS_BRUTO = os.path.join(
    _RAIZ, "dados", "calibracao", "ancoras.csv")

QUALIDADE_INFERIDA = "inferida"
METODO = "linear_km"

STATUS_OK = "ok"
STATUS_AMBIGUO = "ambiguo"
STATUS_FORA = "fora_de_faixa"
STATUS_SEM = "sem_calibracao"

SEGMENTO_PADRAO = 1


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

    Cada ancora e um dict com ``km, lat, lon, ponto_id, uf, fonte, segmento``.
    A coluna ``segmento`` e opcional: quando ausente (CSV bruto), vale 1. Linhas
    sem via, km, lat ou lon sao descartadas (campo ausente = ausente; nao inventa).
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
            seg = _int_ou_none(row.get("segmento"))
            if seg is None:
                seg = SEGMENTO_PADRAO
            ancora = {
                "km": km,
                "lat": lat,
                "lon": lon,
                "ponto_id": _int_ou_none(row.get("ponto_id")),
                "uf": (row.get("uf") or "").strip() or None,
                "fonte": (row.get("fonte") or "").strip() or None,
                "segmento": seg,
            }
            por_via.setdefault(via, []).append(ancora)
    for via in por_via:
        por_via[via].sort(key=_chave_ordem)
    return por_via


def _chave_ordem(a):
    pid = a.get("ponto_id")
    return (a["km"], -1 if pid is None else pid)


def _segmento_de(a):
    seg = a.get("segmento")
    return SEGMENTO_PADRAO if seg is None else seg


def agrupar_segmentos(ancoras):
    """Agrupa uma lista de ancoras por ``segmento`` -> ``{seg: [ancoras...]}``."""
    segs = {}
    for a in ancoras:
        segs.setdefault(_segmento_de(a), []).append(a)
    for seg in segs:
        segs[seg].sort(key=_chave_ordem)
    return segs


def _resumo(status, via, km, n, qualidade=None, lat=None, lon=None,
            antes=None, depois=None, segmento=None, segmentos=None):
    return {
        "status": status,
        "via": via,
        "km": km,
        "qualidade": qualidade,
        "metodo": METODO,
        "lat": lat,
        "lon": lon,
        "segmento": segmento,
        "segmentos": segmentos,
        "ancora_antes": antes,
        "ancora_depois": depois,
        "n_ancoras_via": n,
    }


def resolver(via, km, calibracao=None):
    """Resolve ``(via, km)`` em ``{lat, lon, ...}`` por interpolacao linear.

    ``calibracao`` e o dict ``{via: [ancoras]}`` (ex.: de ``carregar_ancoras``).
    Se ``None``, carrega ``dados/calibracao/ancoras_limpas.csv``.

    Retorna dict com ``status``:

      * ``'ok'``             -> lat/lon preenchidos (``qualidade='inferida'``),
                                com o ``segmento`` usado;
      * ``'ambiguo'``        -> mais de um segmento cobre o km (lat/lon None);
      * ``'fora_de_faixa'``  -> nenhum segmento cobre o km (lat/lon None);
      * ``'sem_calibracao'`` -> via desconhecida ou com menos de 2 ancoras.

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
    n = len(ancoras)

    if via is None or n < 2:
        return _resumo(STATUS_SEM, via, km, n)

    segmentos = agrupar_segmentos(ancoras)
    cobrem = [(seg, arr) for seg, arr in segmentos.items()
              if arr[0]["km"] <= km <= arr[-1]["km"]]

    if len(cobrem) == 1:
        seg, arr = cobrem[0]
        antes, depois = _par(arr, km)
        dkm = depois["km"] - antes["km"]
        t = 0.0 if dkm == 0 else (km - antes["km"]) / dkm
        lat = antes["lat"] + t * (depois["lat"] - antes["lat"])
        lon = antes["lon"] + t * (depois["lon"] - antes["lon"])
        return _resumo(STATUS_OK, via, km, n, qualidade=QUALIDADE_INFERIDA,
                       lat=lat, lon=lon, antes=antes, depois=depois,
                       segmento=seg)

    if len(cobrem) > 1:
        return _resumo(STATUS_AMBIGUO, via, km, n,
                       segmentos=[s for s, _ in cobrem])

    antes, depois = _extremidades(ancoras, km)
    return _resumo(STATUS_FORA, via, km, n, antes=antes, depois=depois)


def _par(arr, km):
    """Par de ancoras do segmento (ordenado) que contem ``km``."""
    antes = arr[0]
    depois = arr[-1]
    for i in range(len(arr) - 1):
        a = arr[i]
        b = arr[i + 1]
        if a["km"] <= km <= b["km"]:
            antes, depois = a, b
            break
    return antes, depois


def _extremidades(ancoras, km):
    """Ancora imediatamente antes e depois de ``km`` (lista global ordenada)."""
    antes = None
    depois = None
    for a in ancoras:
        if a["km"] <= km:
            antes = a
        else:
            depois = a
            break
    return antes, depois


def erro_m(resultado, lat, lon):
    """Erro Haversine (m) entre um resultado resolvido e a coordenada real."""
    if resultado.get("lat") is None or resultado.get("lon") is None:
        return None
    return haversine_m(resultado["lat"], resultado["lon"], lat, lon)
