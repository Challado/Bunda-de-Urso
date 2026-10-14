# -*- coding: utf-8 -*-
"""Agenda de coleta: qual conector roda, de quanto em quanto tempo.

Cada FONTE tem o seu proprio intervalo (em segundos), configuravel aqui ou
sobreposto por um JSON opcional (coletor/agenda.json) sem mexer no codigo.

O tick (coletor/tick.py) NAO coleta tudo a cada passada: ele so dispara as
fontes vencidas. E o que da o "cada um com o seu tempo" pedido.

url_direta = None -> a origem e resolvida dinamicamente pelo conector
(resolver_url). url_direta preenchido -> origem fixa (ex.: sigla/token que o
proprio conector entende).
"""
import json
import os

from coletor.fontes.antt import ColetorANTT
from coletor.fontes.recife import ColetorRecife
from coletor.fontes.dnit import ColetorDNIT
from coletor.fontes.dersp import ColetorDERSP
from coletor.fontes.derpr import ColetorDERPR
from coletor.fontes.dermg import ColetorDERMG
from coletor.fontes.pbh import ColetorPBH
from coletor.fontes.prf import (ColetorPRFFixos, ColetorPRFPortateis,
                                ColetorPRFTrechos)
from coletor.fontes.osm import ColetorOSM
from coletor.fontes.inmetro import ColetorINMETRO

HORA = 3600
DIA = 86400
SEMANA = 604800

AGENDA_PADRAO = {
    # -- ja em producao -------------------------------------------------
    "antt": {
        "rotulo": "ANTT - radares em rodovias concedidas",
        "conector": ColetorANTT,
        "intervalo_s": HORA,
        "url_direta": None,
        "ativo": True,
    },
    "recife": {
        "rotulo": "Recife - equipamentos de fiscalizacao",
        "conector": ColetorRecife,
        "intervalo_s": DIA,
        "url_direta": None,
        "ativo": True,
    },
    # -- estaduais / municipais (arquivo legivel) -----------------------
    "dnit": {
        "rotulo": "DNIT - controle de velocidade (PNCV)",
        "conector": ColetorDNIT,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "dersp": {
        "rotulo": "DER-SP - radares estaduais",
        "conector": ColetorDERSP,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "derpr": {
        "rotulo": "DER-PR - fiscalizacao fixa e portatil",
        "conector": ColetorDERPR,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "dermg": {
        "rotulo": "DER-MG - localizacao de radares",
        "conector": ColetorDERMG,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "pbh": {
        "rotulo": "Belo Horizonte - fiscalizacao eletronica",
        "conector": ColetorPBH,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    # -- PRF (federal) --------------------------------------------------
    "prf_fixos": {
        "rotulo": "PRF - radares fixos",
        "conector": ColetorPRFFixos,
        "intervalo_s": DIA,
        "url_direta": None,
        "ativo": True,
    },
    "prf_portateis": {
        "rotulo": "PRF - lista de radares portateis",
        "conector": ColetorPRFPortateis,
        "intervalo_s": DIA,
        "url_direta": None,
        "ativo": True,
    },
    "prf_trechos": {
        "rotulo": "PRF - trechos criticos (elegiveis)",
        "conector": ColetorPRFTrechos,
        "intervalo_s": DIA,
        "url_direta": None,
        "ativo": True,
    },
    # -- metrologia (INMETRO) — todas as UFs numa execucao --------------
    "inmetro": {
        "rotulo": "INMETRO/PSIE - instrumentos verificados (26 UFs)",
        "conector": ColetorINMETRO,
        "intervalo_s": SEMANA,
        "url_direta": "TODAS",
        "ativo": True,
    },
    # -- complementar (nao oficial) — opt-in ----------------------------
    "osm": {
        "rotulo": "OpenStreetMap/Overpass - radares (complementar)",
        "conector": ColetorOSM,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": False,        # complementar: ligar so quando quiser
    },
}

# Teto do backoff apos erro consecutivo (multiplicador sobre intervalo_s).
BACKOFF_TETO = 8
# Espera minima apos erro, em segundos (evita retentar a cada minuto).
BACKOFF_MINIMO_S = 300

ARQUIVO_AGENDA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "agenda.json")


def carregar_agenda(arquivo=None):
    """Agenda efetiva: padrao, sobreposto por agenda.json se existir."""
    agenda = {}
    for chave, cfg in AGENDA_PADRAO.items():
        item = dict(cfg)
        item["chave"] = chave
        agenda[chave] = item
    caminho = arquivo or ARQUIVO_AGENDA
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            sobre = json.load(f)
        for chave, cfg in (sobre or {}).items():
            if chave in agenda:
                agenda[chave].update(cfg)
            else:
                agenda[chave] = dict(cfg, chave=chave)
    return agenda
