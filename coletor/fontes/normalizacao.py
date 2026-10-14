# -*- coding: utf-8 -*-
"""Normalizacao compartilhada: insere registros normalizados no modelo
canonico, preservando proveniencia (REGISTRO_FONTE + VINCULO_*).

Nada e inventado: campos ausentes viram NULL; o payload bruto permanece em
REGISTRO_FONTE.payload_original (spec 3.7, 11).
"""
import logging
import re
import unicodedata

from core import db as dbmod

log = logging.getLogger(__name__)


def _txt(v):
    return "" if v is None else str(v).strip().lower()


def normalizar_tipo_radar(v):
    t = _txt(v)
    if not t:
        return "desconhecido"
    if "fix" in t:
        return "fixo"
    if "port" in t:
        return "portatil"
    if "móv" in t or "mov" in t:
        return "movel"
    return "desconhecido"


def normalizar_situacao(v):
    t = _txt(v)
    if "manut" in t:
        return "manutencao"
    if "suspens" in t:
        return "suspenso"
    if "instala" in t:
        return "em_instalacao"
    if "ativ" in t:
        # 'inativo' contem 'ativ'; checar negacao primeiro
        return "inativo" if "inativ" in t or "desativ" in t else "ativo"
    if "inativ" in t or "desativ" in t:
        return "inativo"
    return "desconhecido"


def normalizar_sentido(v):
    t = _txt(v)
    if not t:
        return None
    # 'decrescente' CONTEM a substring 'cresc': testar a negacao primeiro.
    if "decresc" in t:
        return "decrescente"
    if "cresc" in t:
        return "crescente"
    if "ambos" in t or "duplo" in t or "bidir" in t:
        return "ambos"
    return "sentido_geografico"


def pick(d, *chaves):
    for k in chaves:
        if k in d and d[k] not in (None, ""):
            return d[k]
    # fallback case-insensitive
    baixo = {str(k).strip().lower(): v for k, v in d.items()}
    for k in chaves:
        v = baixo.get(str(k).strip().lower())
        if v not in (None, ""):
            return v
    return None


def to_float(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    # decimal brasileiro: 1.234,56 -> 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_velocidade(v):
    """Converte velocidade publicada em texto livre para float.

    Ex.: "40 Km/h" -> 40.0 ; "60" -> 60.0 ; "N/I" -> None.
    Nao arredonda nem inventa: extrai apenas o numero publicado.
    """
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:[.,]\d+)?", str(v))
    if not m:
        return None
    s = m.group(0)
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_int(v):
    f = to_float(v)
    return None if f is None else int(round(f))


def tipo_via_de_rodovia(codigo):
    if not codigo:
        return "desconhecida"
    c = str(codigo).strip().upper()
    if c.startswith("BR"):
        return "federal"
    if len(c) >= 2 and c[:2].isalpha():
        return "estadual"
    return "outra"


def normalizar_nome_texto(valor):
    """Normaliza um nome para casamento: sem acento, maiusculo, espacos
    colapsados (ex.: 'Água Branca ' -> 'AGUA BRANCA').

    Usado para casar o nome de municipio publicado pela fonte com o nome
    oficial em MUNICIPIO; nao altera o valor gravado.
    """
    if valor is None:
        return ""
    s = unicodedata.normalize("NFKD", str(valor).strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def buscar_municipio_por_nome(conn, uf_sigla, municipio_nome):
    """Casa (uf_sigla, nome) contra MUNICIPIO com normalizacao de
    maiusculas/acentos/espacos. Devolve o codigo_ibge ou None.

    Nada e inventado: sem correspondencia na lista oficial, devolve None.
    """
    if not uf_sigla or not municipio_nome:
        return None
    alvo = normalizar_nome_texto(municipio_nome)
    if not alvo:
        return None
    for row in dbmod.query_all(
            conn, "SELECT codigo_ibge, nome FROM MUNICIPIO WHERE uf_sigla=?",
            (uf_sigla,)):
        if normalizar_nome_texto(row["nome"]) == alvo:
            return row["codigo_ibge"]
    return None


def resolver_uf_municipio(conn, uf_sigla, municipio_nome, municipio_ibge):
    """Resolve/cria municipio e retorna (uf_sigla, municipio_id).

    Ordem de resolucao:
      1. codigo IBGE publicado pela fonte (com cria se ainda nao existir);
      2. (uf_sigla, nome) normalizado contra MUNICIPIO (carga oficial IBGE).

    Fontes mandam quase sempre o *nome* e raramente o codigo; por isso o
    passo 2 e o que evita perder o municipio. Nunca insere municipio com
    codigo_ibge NULL: sem correspondencia oficial fica NULL (e fica no log).
    """
    uf_sigla = (uf_sigla or "").strip().upper() or None
    if uf_sigla:
        row = dbmod.query_one(conn, "SELECT sigla FROM UF WHERE sigla=?",
                              (uf_sigla,))
        if row is None:
            uf_sigla = None
    municipio_id = None
    if municipio_ibge:
        municipio_ibge = str(municipio_ibge).strip()
        row = dbmod.query_one(
            conn, "SELECT codigo_ibge, uf_sigla FROM MUNICIPIO WHERE codigo_ibge=?",
            (municipio_ibge,))
        if row is not None:
            municipio_id = row["codigo_ibge"]
            uf_sigla = uf_sigla or row["uf_sigla"]
        elif uf_sigla and municipio_nome:
            dbmod.insert(conn, "MUNICIPIO", {
                "codigo_ibge": municipio_ibge,
                "uf_sigla": uf_sigla,
                "nome": municipio_nome,
            })
            municipio_id = municipio_ibge
    # sem codigo IBGE (ou codigo desconhecido): casar pelo nome oficial
    if municipio_id is None and municipio_nome:
        municipio_id = buscar_municipio_por_nome(conn, uf_sigla,
                                                 municipio_nome)
        if municipio_id is None:
            log.debug("municipio nao resolvido (uf=%r nome=%r): fica NULL",
                      uf_sigla, municipio_nome)
    return uf_sigla, municipio_id


def obter_via(conn, codigo, tipo_codigo=None):
    if not codigo:
        return None
    codigo = str(codigo).strip()
    tipo_codigo = tipo_codigo or tipo_via_de_rodovia(codigo)
    tipo_id = dbmod.domain_id(conn, "TIPO_VIA", tipo_codigo)
    return dbmod.upsert_lookup(conn, "VIA", ["tipo_via_id", "codigo"],
                               [tipo_id, codigo])


def inserir_normalizado(conn, registro_id, d, fonte_id=None):
    """Insere um ponto normalizado (dict `d`) com equipamento, faixa,
    limites e vinculo. Retorna dict com ids criados."""
    uf_sigla, municipio_id = resolver_uf_municipio(
        conn, d.get("uf"), d.get("municipio_nome"), d.get("municipio_ibge"))
    via_id = obter_via(conn, d.get("via_codigo"), d.get("via_tipo"))

    qualidade_id = dbmod.domain_id(conn, "QUALIDADE_POSICAO",
                                   d.get("qualidade") or "desconhecida")
    posicao_id = None
    lat, lon = d.get("latitude"), d.get("longitude")
    # coordenada fora de faixa (ou 0,0) nao vira POSICAO: o registro e
    # preservado sem posicao em vez de estourar o CHECK / apontar pro mar.
    if (lat is not None and lon is not None
            and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0
            and not (lat == 0.0 and lon == 0.0)):
        posicao_id = dbmod.insert(conn, "POSICAO_GEOGRAFICA", {
            "latitude": lat,
            "longitude": lon,
            "precisao_metros": d.get("precisao_metros"),
            "qualidade_posicao_id": qualidade_id,
            "metodo_obtencao": d.get("metodo_obtencao"),
            "registro_fonte_id": registro_id,
        })

    situacao_id = None
    if d.get("situacao"):
        situacao_id = dbmod.domain_id(conn, "SITUACAO_OPERACIONAL",
                                      d["situacao"])
    ponto_id = dbmod.insert(conn, "PONTO_FISCALIZACAO", {
        "posicao_id": posicao_id,
        "municipio_id": municipio_id,
        "via_id": via_id,
        "km": d.get("km"),
        "tipo_pista": d.get("tipo_pista"),
        "situacao_operacional_id": situacao_id,
        "observacoes": d.get("observacoes"),
    })

    # faixa (sentido) — so quando a fonte informa sentido/pista
    faixa_id = None
    if d.get("sentido") or d.get("sentido_original") or d.get("tipo_pista"):
        sentido_id = None
        if d.get("sentido"):
            sentido_id = dbmod.domain_id(conn, "SENTIDO", d["sentido"])
        faixa_id = dbmod.insert(conn, "FAIXA_FISCALIZACAO", {
            "ponto_id": ponto_id,
            "sentido_id": sentido_id,
            "sentido_original": d.get("sentido_original"),
            "descricao": d.get("tipo_pista"),
        })

    # limites de velocidade por categoria (sem inventar velocidade geral)
    limites = []
    for categoria, chave in (("leves", "velocidade_leves"),
                             ("pesados", "velocidade_pesados"),
                             ("geral", "velocidade_geral")):
        val = d.get(chave)
        # velocidade publicada fora da faixa plausivel (0..350) fica so no
        # payload bruto, nunca num LIMITE_VELOCIDADE invalido.
        if val is not None and 0 < val <= 350:
            cat_id = dbmod.domain_id(conn, "CATEGORIA_VEICULO", categoria)
            limite = {
                "categoria_veiculo_id": cat_id,
                "velocidade_kmh": val,
                "registro_fonte_id": registro_id,
            }
            # exatamente um entre ponto_id/faixa_id (CHECK T28)
            if faixa_id is not None:
                limite["faixa_id"] = faixa_id
            else:
                limite["ponto_id"] = ponto_id
            lid = dbmod.insert(conn, "LIMITE_VELOCIDADE", limite)
            limites.append(lid)

    # regime de fiscalizacao
    modalidade = d.get("modalidade")
    if modalidade is None:
        modalidade = ("permanente" if d.get("tipo_radar") == "fixo"
                      else "desconhecida")
    modalidade_id = dbmod.domain_id(conn, "MODALIDADE_FISCALIZACAO",
                                    modalidade)
    regime_id = dbmod.insert(conn, "REGIME_FISCALIZACAO", {
        "ponto_id": ponto_id,
        "modalidade_id": modalidade_id,
        "situacao_operacional_id": situacao_id,
        "fonte_registro_id": registro_id,
    })

    # equipamento + modelo + instalacao
    tipo_radar = d.get("tipo_radar") or "desconhecido"
    tipo_radar_id = dbmod.domain_id(conn, "TIPO_RADAR", tipo_radar)
    modelo_id = None
    if d.get("modelo") or d.get("fabricante"):
        fabricante_id = None
        if d.get("fabricante"):
            fabricante_id = dbmod.upsert_lookup(
                conn, "ORGANIZACAO", ["nome"], [d["fabricante"]],
                extra={"tipo_organizacao_id": dbmod.domain_id(
                    conn, "TIPO_ORGANIZACAO", "fabricante")})
        modelo_id = dbmod.upsert_lookup(
            conn, "MODELO_EQUIPAMENTO", ["fabricante_id", "nome_modelo"],
            [fabricante_id, d.get("modelo") or "desconhecido"])
    equipamento_id = dbmod.insert(conn, "EQUIPAMENTO", {
        "modelo_id": modelo_id,
        "tipo_radar_id": tipo_radar_id,
        "numero_serie": d.get("numero_serie"),
        "ano_fabricacao": d.get("ano_fabricacao"),
    })
    instalacao_id = dbmod.insert(conn, "INSTALACAO", {
        "ponto_id": ponto_id,
        "equipamento_id": equipamento_id,
        "situacao_operacional_id": situacao_id,
    })

    # identificador externo (administrativo) — nao e numero de serie
    identificador_id = None
    if fonte_id is not None and d.get("identificador"):
        tipo_ident_id = dbmod.domain_id(conn, "TIPO_IDENTIFICADOR",
                                        d.get("tipo_identificador", "id_orgao"))
        valor_norm = str(d["identificador"]).strip().upper()
        row = dbmod.query_one(
            conn, "SELECT id FROM IDENTIFICADOR_EXTERNO WHERE fonte_id=? AND "
            "tipo_identificador_id=? AND valor_normalizado=?",
            (fonte_id, tipo_ident_id, valor_norm))
        if row is not None:
            identificador_id = row["id"]
        else:
            identificador_id = dbmod.insert(conn, "IDENTIFICADOR_EXTERNO", {
                "fonte_id": fonte_id,
                "tipo_identificador_id": tipo_ident_id,
                "valor": d["identificador"],
                "valor_normalizado": valor_norm,
            })
        dbmod.insert(conn, "IDENTIFICADOR_PONTO", {
            "identificador_id": identificador_id,
            "ponto_id": ponto_id,
        })

    # vinculo de proveniencia
    conn.execute(
        "INSERT OR IGNORE INTO VINCULO_REGISTRO_PONTO (registro_id, ponto_id) "
        "VALUES (?,?)", (registro_id, ponto_id))
    if registro_id is not None:
        conn.execute(
            "INSERT OR IGNORE INTO VINCULO_REGISTRO_EQUIPAMENTO "
            "(registro_id, equipamento_id) VALUES (?,?)",
            (registro_id, equipamento_id))
    return {"ponto_id": ponto_id, "equipamento_id": equipamento_id,
            "faixa_id": faixa_id, "regime_id": regime_id,
            "instalacao_id": instalacao_id, "limites": limites,
            "posicao_id": posicao_id, "via_id": via_id,
            "municipio_id": municipio_id}


def inserir_trecho(conn, registro_id, d, fonte_id=None):
    """Insere um TRECHO_ELEGIVEL (spec F07 / 11.5).

    Trecho elegivel NAO e ponto, NAO e equipamento e NAO e operacao
    confirmada: por isso grava direto em TRECHO_ELEGIVEL, sem criar
    PONTO_FISCALIZACAO. Sem via, nao ha trecho (payload fica no bruto).
    """
    via_id = obter_via(conn, d.get("via_codigo"), d.get("via_tipo"))
    if via_id is None:
        return None
    sentido_id = None
    if d.get("sentido"):
        sentido_id = dbmod.domain_id(conn, "SENTIDO", d["sentido"])
    trecho_id = dbmod.insert(conn, "TRECHO_ELEGIVEL", {
        "via_id": via_id,
        "km_inicio": d.get("km_inicio"),
        "km_fim": d.get("km_fim"),
        "sentido_id": sentido_id,
        "criterio_inclusao": d.get("criterio_inclusao"),
        "vigencia_inicio": d.get("vigencia_inicio"),
        "vigencia_fim": d.get("vigencia_fim"),
        "situacao": d.get("situacao"),
        "registro_fonte_id": registro_id,
    })
    return {"trecho_id": trecho_id,
            "indicador": d.get("indicador"),
            "radar_instalado_confirmado": d.get("radar_instalado_confirmado")}
