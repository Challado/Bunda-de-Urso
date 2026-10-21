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
from coletor.fontes.goinfra import ColetorGOINFRA
from coletor.fontes.seinfra_ba import ColetorSEINFRABA
from coletor.fontes.amc_ce import ColetorAMCCE
from coletor.fontes.der_rj import ColetorDERRJ
from coletor.fontes.daer_rs import ColetorDAERRS
from coletor.fontes.cariacica_es import ColetorCariacica
from coletor.fontes.joinville_sc import ColetorJoinville
from coletor.fontes.immu_am import ColetorIMMUAM
from coletor.fontes.agetran_ms import ColetorAgetranMS
from coletor.fontes.semob_pb import ColetorSemobPB
from coletor.fontes.ctmac_ap import ColetorCtmacAP
from coletor.fontes.cuiaba_mt import ColetorCuiabaMT
from coletor.fontes.semtran_ro import ColetorSEMTRANRO
from coletor.fontes.segbell_pa import ColetorSEGBELPA
from coletor.fontes.boavista_rr import ColetorBoaVistaRR
from coletor.fontes.detran_df import ColetorDetranDF
from coletor.fontes.detran_ma import ColetorDetranMA
from coletor.fontes.der_se import ColetorDERSE
from coletor.fontes.araguaiana_to import ColetorASTTAraguaina
from coletor.fontes.detran_ac import ColetorDetranAC
from coletor.fontes.der_al import ColetorDerAL
from coletor.fontes.natal_rn import ColetorNatalRN
from coletor.fontes.teresina_pi import ColetorTeresinaPI
from coletor.fontes.base_lwb import ColetorBaseLWB

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
        # Pos-coleta: le o payload recem-coletado e grava a VERIFICACAO_
        # METROLOGICA (idempotente) -> instrumento novo ja entra com o atestado.
        "pos_coleta": "core.manutencao.carregar_verificacao_metrologica:carregar_do_banco",
    },
    # -- 27 UFs, ondas 1-3: conectores com cadastro real (dados) --------
    "goinfra": {
        "rotulo": "GOINFRA - GO, equipamentos de monitoramento",
        "conector": ColetorGOINFRA,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "seinfra_ba": {
        "rotulo": "SEINFRA-BA - radares fixos e estaticos",
        "conector": ColetorSEINFRABA,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "amc_ce": {
        "rotulo": "AMC Fortaleza/CE - fiscalizacao eletronica",
        "conector": ColetorAMCCE,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "der_rj": {
        "rotulo": "DER-RJ - radares portateis (trechos elegiveis)",
        "conector": ColetorDERRJ,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "daer_rs": {
        "rotulo": "DAER-RS/CRBM - radares moveis (trechos elegiveis)",
        "conector": ColetorDAERRS,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "cariacica_es": {
        "rotulo": "Cariacica/ES - mapa de radares",
        "conector": ColetorCariacica,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "immu_am": {
        "rotulo": "IMMU Manaus/AM - fiscalizacao eletronica",
        "conector": ColetorIMMUAM,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "agetran_ms": {
        "rotulo": "Agetran Campo Grande/MS - radares",
        "conector": ColetorAgetranMS,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "semob_pb": {
        "rotulo": "Semob Joao Pessoa/PB - medidores de velocidade",
        "conector": ColetorSemobPB,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "semtran_ro": {
        "rotulo": "SEMTRAN Porto Velho/RO - radares fixos",
        "conector": ColetorSEMTRANRO,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "detran_df": {
        "rotulo": "Detran-DF - medidores de velocidade",
        "conector": ColetorDetranDF,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "detran_ma": {
        "rotulo": "Detran-MA - fiscalizacao eletronica",
        "conector": ColetorDetranMA,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "der_se": {
        "rotulo": "DER-SE - radares e lombadas fixas",
        "conector": ColetorDERSE,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "araguaiana_to": {
        "rotulo": "ASTT Araguaina/TO - medidores de velocidade",
        "conector": ColetorASTTAraguaina,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    # -- 27 UFs: diagnosticados (sem cadastro -> so evidencia) ----------
    # Ativos de proposito: registram REGISTRO_FONTE e nao criam ponto.
    "joinville_sc": {
        "rotulo": "Joinville/SC - estudos tecnicos (sem cadastro)",
        "conector": ColetorJoinville,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "segbell_pa": {
        "rotulo": "SEGBEL Belem/PA - portarias (sem cadastro)",
        "conector": ColetorSEGBELPA,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "ctmac_ap": {
        "rotulo": "CTMac Macapa/AP - lista historica (sem cadastro)",
        "conector": ColetorCtmacAP,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "cuiaba_mt": {
        "rotulo": "Cuiaba/MT - noticia historica (sem cadastro)",
        "conector": ColetorCuiabaMT,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "boavista_rr": {
        "rotulo": "Boa Vista/RR - lista em imagem (sem cadastro)",
        "conector": ColetorBoaVistaRR,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "detran_ac": {
        "rotulo": "Detran-AC - sem publicacao (pendente LAI)",
        "conector": ColetorDetranAC,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "der_al": {
        "rotulo": "DER-AL - sem publicacao",
        "conector": ColetorDerAL,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "natal_rn": {
        "rotulo": "STTU Natal/RN - sem publicacao estadual",
        "conector": ColetorNatalRN,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    "teresina_pi": {
        "rotulo": "Teresina/PI - sem publicacao (pendente LAI)",
        "conector": ColetorTeresinaPI,
        "intervalo_s": SEMANA,
        "url_direta": None,
        "ativo": True,
    },
    # -- cadastro PROPRIO (alimentado pela API de escrita) -------------
    # Nao e publicacao de orgao: e a NOSSA base (Bundita de Urso). Entra pela
    # API (POST /api/v1/radares); nao ha coleta agendada (ativo False) e o
    # tick NAO a dispara. O conector existe para compartilhar normalizacao e
    # upsert com as demais fontes.
    "base_lwb": {
        "rotulo": "Bundita de Urso - A base do Bunda de urso",
        "conector": ColetorBaseLWB,
        "intervalo_s": None,
        "url_direta": None,
        "ativo": False,
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
