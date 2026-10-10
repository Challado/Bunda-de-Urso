# -*- coding: utf-8 -*-
"""Agenda de coleta: qual conector roda, de quanto em quanto tempo.

Cada FONTE tem o seu proprio intervalo (em segundos), configuravel aqui ou
sobreposto por um JSON opcional (coletor/agenda.json) sem mexer no codigo.

O tick (coletor/tick.py) NAO coleta tudo a cada passada: ele so dispara as
fontes vencidas. E o que da o "cada um com o seu tempo" pedido.
"""
import json
import os

from coletor.fontes.antt import ColetorANTT
from coletor.fontes.recife import ColetorRecife

# Intervalo padrao por fonte (segundos) e URL direta do arquivo.
# url_direta = None -> a origem publicada e uma pagina de dataset, nao um
# arquivo estavel; o tick pula a fonte ao vivo (use --arquivo para ingestao
# manual) em vez de baixar HTML e gravar lixo.
AGENDA_PADRAO = {
    "antt": {
        "rotulo": "ANTT - radares em rodovias concedidas",
        "conector": ColetorANTT,
        "intervalo_s": 3600,        # 1x/hora
        "url_direta": None,
        "ativo": True,
    },
    "recife": {
        "rotulo": "Recife - equipamentos de fiscalizacao",
        "conector": ColetorRecife,
        "intervalo_s": 86400,       # 1x/dia
        "url_direta": None,
        "ativo": True,
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
