# -*- coding: utf-8 -*-
"""Apoio comum aos testes: ambiente temporario, banco em memoria e fixtures."""
import os
import tempfile

from core import config
from core import db as dbmod
from coletor.fontes.antt import ColetorANTT
from coletor.fontes.recife import ColetorRecife

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ANTT_FIXTURE = os.path.join(FIXTURES, "antt_radares_fixture.json")
RECIFE_FIXTURE = os.path.join(FIXTURES, "recife_equipamentos.csv")


def ambiente_temporario():
    """Redireciona config para um diretorio temporario. Retorna o caminho."""
    tmp = tempfile.mkdtemp(prefix="radar-test-")
    config.DATA_DIR = tmp
    config.RAW_DIR = os.path.join(tmp, "raw")
    config.STAGING_DIR = os.path.join(tmp, "staging")
    config.DB_PATH = os.path.join(tmp, "radar.sqlite3")
    os.makedirs(config.RAW_DIR, exist_ok=True)
    return tmp


def banco_memoria():
    con = dbmod.connect(":memory:")
    dbmod.init_db(con)
    return con


def banco_com_antt():
    ambiente_temporario()
    coletor = ColetorANTT(db_path=config.DB_PATH)
    try:
        resumo = coletor.sincronizar(ANTT_FIXTURE)
    finally:
        coletor.conn.close()
    return config.DB_PATH, resumo


def banco_com_recife():
    ambiente_temporario()
    coletor = ColetorRecife(db_path=config.DB_PATH)
    try:
        resumo = coletor.sincronizar(RECIFE_FIXTURE)
    finally:
        coletor.conn.close()
    return config.DB_PATH, resumo


def exemplo_ponto():
    """Ponto canonico sintetico (spec 11.2) para testes de serializacao."""
    return {
        "id": "P-EXEMPLO-1",
        "tipo_registro": "ponto_fiscalizacao",
        "situacao_operacional": "ativo",
        "situacao_original": "Ativo",
        "localizacao": {
            "latitude": -24.9555,
            "longitude": -53.4552,
            "distancia_metros": 0.0,
            "precisao_metros": None,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao",
            "uf": "PR",
            "municipio": "Cascavel",
            "codigo_ibge": "4104808",
            "endereco": {},
            "via": {"codigo": "BR-277", "tipo": "federal", "nome": None},
            "km": 580.5,
            "tipo_pista": "Principal",
        },
        "data_inicio_operacao": None,
        "data_inativacao": None,
        "motivo_inativacao": None,
        "organizacoes": [],
        "faixas": [
            {"id": "F-1", "numero": None, "sentido": "crescente",
             "sentido_original": "Crescente"},
        ],
        "quantidade_faixas_declarada": None,
        "limites_velocidade": [
            {"faixa_id": "F-1", "categoria_veiculo": "leves",
             "velocidade_kmh": 110, "vigencia_inicio": None,
             "vigencia_fim": None, "fonte_registro_id": None},
        ],
        "regimes": [
            {"id": "R-1", "modalidade_fiscalizacao": "permanente",
             "tipo_medicao": "velocidade_instantanea",
             "situacao_operacional": "ativo", "inicio_em": None, "fim_em": None},
        ],
        "fiscalizacao_pontual": None,
        "tipos_radar_presentes": ["fixo"],
        "equipamentos": [
            {"id": "E-1", "tipo_radar": "fixo"},
        ],
        "operacoes": [],
        "documentos": [],
        "fontes": [],
        "conflitos": [],
        "primeira_observacao": None,
        "ultima_confirmacao": None,
        "ultima_coleta": None,
        "confianca": "nao_avaliada",
        "observacoes": "teste",
        "proveniencia_campos": {},
    }
