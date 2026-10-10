# -*- coding: utf-8 -*-
"""Projecao canonica do ponto e as 32 colunas TXT v1 (spec 12.4).

A mesma projecao alimenta json/ndjson/xml/txt; a paridade e testada.
"""
import json

# Ordem canonica IMUTAVEL das 32 colunas TXT v1 (spec 12.4).
TXT_COLUMNS = (
    "id",
    "tipo_registro",
    "situacao_operacional",
    "latitude",
    "longitude",
    "distancia_metros",
    "precisao_metros",
    "uf",
    "municipio",
    "codigo_ibge",
    "via_codigo",
    "km",
    "tipo_pista",
    "tipos_radar_presentes_json",
    "fiscalizacao_pontual",
    "regimes_json",
    "faixas_json",
    "limites_velocidade_json",
    "equipamentos_json",
    "operacoes_json",
    "documentos_json",
    "fontes_json",
    "conflitos_json",
    "confianca",
    "atualizacao_json",
    "endereco_json",
    "organizacoes_json",
    "localizacao_metadados_json",
    "observacoes",
    "proveniencia_campos_json",
    "estado_temporal_json",
    "quantidade_faixas_declarada",
)

# Descricao por coluna (usada em /ajuda; nada de ajuda divergente do codigo).
TXT_COLUMNS_DESC = {
    "id": "Identificador canonico do ponto (PK da API).",
    "tipo_registro": "Sempre 'ponto_fiscalizacao'.",
    "situacao_operacional": "Estado operacional (nao e validade metrologica).",
    "latitude": "Latitude WGS84 (graus).",
    "longitude": "Longitude WGS84 (graus).",
    "distancia_metros": "Distancia calculada ao ponto consultado (Haversine).",
    "precisao_metros": "Precisao declarada da posicao, em metros.",
    "uf": "Sigla da UF.",
    "municipio": "Nome do municipio.",
    "codigo_ibge": "Codigo IBGE (7 digitos) do municipio.",
    "via_codigo": "Codigo da via/rodovia.",
    "km": "Marcador quilometrico da via.",
    "tipo_pista": "Tipo de pista conforme a fonte.",
    "tipos_radar_presentes_json": "JSON: tipos de radar presentes no ponto.",
    "fiscalizacao_pontual": "Triestado derivado: true/false/null.",
    "regimes_json": "JSON: regimes de fiscalizacao.",
    "faixas_json": "JSON: faixas de fiscalizacao.",
    "limites_velocidade_json": "JSON: limites de velocidade.",
    "equipamentos_json": "JSON: equipamentos instalados.",
    "operacoes_json": "JSON: operacoes publicadas.",
    "documentos_json": "JSON: documentos oficiais.",
    "fontes_json": "JSON: proveniencia/publicacao.",
    "conflitos_json": "JSON: conflitos entre fontes.",
    "confianca": "alta|media|baixa|conflitante|nao_avaliada.",
    "atualizacao_json": "JSON: marcos temporais de atualizacao.",
    "endereco_json": "JSON: endereco estruturado.",
    "organizacoes_json": "JSON: organizacoes e papeis.",
    "localizacao_metadados_json": "JSON: qualidade/metodo da posicao.",
    "observacoes": "Observacoes textuais.",
    "proveniencia_campos_json": "JSON: proveniencia por campo.",
    "estado_temporal_json": "JSON: inicio/inativacao/motivo/situacao original.",
    "quantidade_faixas_declarada": "Contagem agregada publicada (sem inventar faixas).",
}


def json_cell(obj):
    """JSON compacto UTF-8 para uma celula TXT."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _json_or_empty(obj):
    if obj is None:
        return None
    return obj


def build_cells(p):
    """Projeta um ponto canonico (spec 11.2) nas 32 celulas TXT."""
    loc = p.get("localizacao") or {}
    via = loc.get("via") or {}
    endereco = loc.get("endereco") or {}
    return [
        p.get("id"),
        p.get("tipo_registro", "ponto_fiscalizacao"),
        p.get("situacao_operacional"),
        loc.get("latitude"),
        loc.get("longitude"),
        loc.get("distancia_metros"),
        loc.get("precisao_metros"),
        loc.get("uf"),
        loc.get("municipio"),
        loc.get("codigo_ibge"),
        via.get("codigo"),
        loc.get("km"),
        loc.get("tipo_pista"),
        _json_or_empty(p.get("tipos_radar_presentes") or []),
        p.get("fiscalizacao_pontual"),
        _json_or_empty(p.get("regimes") or []),
        _json_or_empty(p.get("faixas") or []),
        _json_or_empty(p.get("limites_velocidade") or []),
        _json_or_empty(p.get("equipamentos") or []),
        _json_or_empty(p.get("operacoes") or []),
        _json_or_empty(p.get("documentos") or []),
        _json_or_empty(p.get("fontes") or []),
        _json_or_empty(p.get("conflitos") or []),
        p.get("confianca"),
        _json_or_empty({
            "primeira_observacao": p.get("primeira_observacao"),
            "ultima_confirmacao": p.get("ultima_confirmacao"),
            "ultima_coleta": p.get("ultima_coleta"),
        }),
        _json_or_empty(endereco),
        _json_or_empty(p.get("organizacoes") or []),
        _json_or_empty({
            "qualidade": loc.get("qualidade"),
            "metodo_obtencao": loc.get("metodo_obtencao"),
        }),
        p.get("observacoes"),
        _json_or_empty(p.get("proveniencia_campos") or {}),
        _json_or_empty({
            "data_inicio_operacao": p.get("data_inicio_operacao"),
            "data_inativacao": p.get("data_inativacao"),
            "motivo_inativacao": p.get("motivo_inativacao"),
            "situacao_original": p.get("situacao_original"),
        }),
        p.get("quantidade_faixas_declarada"),
    ]


def row_dict(p):
    """dict coluna->valor (32 chaves) — usado na checagem de paridade."""
    return dict(zip(TXT_COLUMNS, build_cells(p)))
