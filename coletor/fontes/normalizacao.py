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

    Dois degraus: (1) casamento exato normalizado; (2) na falta dele,
    casamento APROXIMADO (fuzzy + fonetico) via ``core.casamento_municipio``,
    confiante so com ratio/margem. Nada e inventado: sem correspondencia
    oficial na lista, devolve None.
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
    # 2o degrau: nome grafado diferente do oficial (renome, abreviacao,
    # acento, erro de digitacao). Conservador: so preenche com confianca.
    from core import casamento_municipio as cm      # import tardio: sem ciclo
    d = cm.melhor_por_nome(conn, uf_sigla, municipio_nome)
    if d and d.get("codigo"):
        log.info("municipio casado por aproximacao: nome=%r uf=%r -> %s "
                 "(motivo=%s score=%.3f)", municipio_nome, uf_sigla,
                 d["codigo"], d["motivo"], d["score"])
        return d["codigo"]
    log.debug("municipio nao resolvido (uf=%r nome=%r): fica NULL",
              uf_sigla, municipio_nome)
    return None


def municipio_por_geografia(conn, latitude, longitude):
    """Resolve (codigo_ibge, uf_sigla) pela malha OFICIAL do IBGE, ou (None, None).

    Fallback para quando o nome nao casa contra MUNICIPIO: se o registro tem
    coordenada valida, o ponto-em-poligono sobre a malha municipal do IBGE
    decide o municipio. Nada e inventado: coordenada ausente/implausivel ou
    ponto fora de qualquer municipio (agua/limite) devolvem (None, None).
    """
    if latitude is None or longitude is None:
        return None, None
    try:
        from core import geo_municipio as geo
    except Exception:                                       # noqa: BLE001
        return None, None
    if not geo.coordenada_valida(latitude, longitude):
        return None, None
    codigo = geo.municipio_por_coordenada(latitude, longitude)
    if not codigo:
        return None, None
    row = dbmod.query_one(
        conn, "SELECT uf_sigla FROM MUNICIPIO WHERE codigo_ibge=?", (codigo,))
    if row is None:
        # Municipio da malha que nao esta no cadastro local: nao inventa
        # (evita FK orfa num banco sem a carga oficial do IBGE).
        log.debug("fallback geo achou %s, ausente em MUNICIPIO: fica NULL",
                  codigo)
        return None, None
    return codigo, row["uf_sigla"]


def resolver_uf_municipio(conn, uf_sigla, municipio_nome, municipio_ibge,
                          latitude=None, longitude=None):
    """Resolve/cria municipio e retorna (uf_sigla, municipio_id).

    Ordem de resolucao:
      1. codigo IBGE publicado pela fonte (com cria se ainda nao existir);
      2. (uf_sigla, nome) normalizado contra MUNICIPIO (carga oficial IBGE);
      3. FALLBACK GEOGRAFICO: se 1 e 2 falharam E o registro tem coordenada,
         resolve por ponto-em-poligono sobre a malha oficial do IBGE
         (``core.geo_municipio``) — registrado no log.

    Fontes mandam quase sempre o *nome* e raramente o codigo; por isso o
    passo 2 e o que evita perder o municipio. Nunca insere municipio com
    codigo_ibge NULL: sem correspondencia oficial e sem coordenada fica NULL.
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
    # FALLBACK GEOGRAFICO (malha oficial do IBGE) — so quando o nome falhou
    if municipio_id is None:
        codigo, uf_geo = municipio_por_geografia(conn, latitude, longitude)
        if codigo:
            municipio_id = codigo
            uf_sigla = uf_geo or uf_sigla
            log.info("municipio resolvido por coordenada (fallback geo): "
                     "nome=%r uf=%r -> %s/%s", municipio_nome, uf_geo,
                     uf_geo, codigo)
    return uf_sigla, municipio_id


def obter_via(conn, codigo, tipo_codigo=None):
    if not codigo:
        return None
    codigo = str(codigo).strip()
    tipo_codigo = tipo_codigo or tipo_via_de_rodovia(codigo)
    tipo_id = dbmod.domain_id(conn, "TIPO_VIA", tipo_codigo)
    return dbmod.upsert_lookup(conn, "VIA", ["tipo_via_id", "codigo"],
                               [tipo_id, codigo])


# Faixa geografica do Brasil. Nenhuma longitude valida no pais e positiva
# (o territorio esta a oeste de Greenwich): -74 a -32 graus. Usada para
# detectar e consertar sinal oeste perdido na fonte.
BRASIL_LAT_MIN, BRASIL_LAT_MAX = -34.0, 6.0
BRASIL_LON_MIN, BRASIL_LON_MAX = -74.0, -32.0


def _localizar_uf_brasil(lat, lon):
    """(codigo_ibge, uf) do municipio da malha oficial que contem o ponto."""
    try:
        from core import geo_municipio as geo
        return geo.municipio_uf_por_coordenada(lat, lon)
    except Exception:                                    # noqa: BLE001
        return None, None


def normalizar_sinal_longitude(lat, lon, uf_esperada=None, localizar=None):
    """Conserta longitude positiva (sinal oeste perdido) de ponto no Brasil.

    Nenhuma longitude valida no Brasil e positiva. Quando a fonte publica o
    valor sem o sinal (ex.: ``48.459841`` em vez de ``-48.459841``), a
    leitura correta e ``-abs(lon)``. A troca nao e chute: so e aceita quando
    o ponto corrigido cai na malha municipal oficial do IBGE e a UF
    (quando conhecida) confere com a declarada; fora disso devolve o valor
    original e o motivo, para quarentena.

    Devolve ``(longitude_final, corrigido, motivo)``:
      - ``corrigido=True`` com ``longitude_final == -abs(lon)`` validado;
      - ``corrigido=False`` com a longitude original e ``motivo`` textual
        quando o valor e implausivel e nao pode ser consertado (ou ``None``
        quando nao ha o que corrigir).
    """
    if lat is None or lon is None:
        return lon, False, None
    if lon <= 0.0:
        return lon, False, None
    if not (BRASIL_LAT_MIN <= lat <= BRASIL_LAT_MAX):
        return lon, False, ("longitude positiva (%.6f) em latitude fora do "
                            "Brasil" % lon)
    candidata = -lon
    if not (BRASIL_LON_MIN <= candidata <= BRASIL_LON_MAX):
        return lon, False, ("longitude positiva (%.6f) fora da faixa "
                            "longitudinal do Brasil" % lon)
    localizar = localizar or _localizar_uf_brasil
    codigo, uf_geo = (localizar(lat, candidata) or (None, None))
    if not codigo:
        return lon, False, ("longitude positiva (%.6f): ponto corrigido "
                            "fora da malha municipal do IBGE" % lon)
    if uf_esperada and uf_geo and str(uf_geo).upper() != str(uf_esperada).upper():
        return lon, False, ("longitude positiva (%.6f): ponto corrigido em "
                            "%s, nao em %s" % (lon, uf_geo, uf_esperada))
    return candidata, True, None


def _anotar_observacao(d, texto):
    atual = (d.get("observacoes") or "").strip()
    d["observacoes"] = (atual + "; " + texto) if atual else texto


def ajustar_coordenada_brasil(d):
    """Conserta/marca, no dict normalizado ``d``, coordenada implausivel.

    - longitude positiva (sinal oeste perdido) VALIDADA pela malha: troca o
      sinal e anota o valor original nas observacoes;
    - longitude positiva nao consertavel, ou ``latitude == longitude``
      (dado degenerado): preserva o bruto e marca qualidade "conflitante"
      (quarentena), sem inventar posicao.
    """
    lat, lon = d.get("latitude"), d.get("longitude")
    if lat is None or lon is None:
        return
    if lat == 0.0 and lon == 0.0:
        return
    if abs(lat - lon) < 1e-9:
        d["qualidade"] = "conflitante"
        _anotar_observacao(
            d, "QUARENTENA: latitude igual a longitude (%.6f): coordenada "
               "degenerada na fonte" % lat)
        return
    if lon <= 0.0:
        return
    nova, corrigido, motivo = normalizar_sinal_longitude(lat, lon, d.get("uf"))
    if corrigido:
        d["longitude"] = nova
        _anotar_observacao(
            d, "longitude normalizada para o hemisferio oeste (sinal oeste "
               "perdido na fonte): %.6f -> %.6f" % (lon, nova))
        return
    if motivo:
        d["qualidade"] = "conflitante"
        _anotar_observacao(d, "QUARENTENA: %s" % motivo)


def _buscar_por(conn, tabela, campos):
    """Primeiro id de `tabela` que casa com `campos` (None = IS NULL).

    Usado para reaproveitar linhas derivadas no upsert sem estourar UNIQUE.
    """
    clausulas, params = [], []
    for col, val in campos.items():
        if val is None:
            clausulas.append("%s IS NULL" % col)
        else:
            clausulas.append("%s = ?" % col)
            params.append(val)
    sql = "SELECT id FROM %s WHERE %s LIMIT 1" % (tabela,
                                                   " AND ".join(clausulas))
    row = dbmod.query_one(conn, sql, params)
    return row["id"] if row is not None else None


def _obter_ou_inserir(conn, tabela, campos, dados):
    """Reusa a linha que casa com `campos` ou insere `dados`: (id, criado)."""
    existente = _buscar_por(conn, tabela, campos)
    if existente is not None:
        return existente, False
    return dbmod.insert(conn, tabela, dados), True


def _resolver_ponto_identificado(conn, fonte_id, d):
    """Resolve a identidade externa (fonte_id, tipo, valor) -> ponto.

    Devolve ``(ponto_id, identificador_id)``. ``identificador_id`` e a linha
    de IDENTIFICADOR_EXTERNO (criada sob demanda); ``ponto_id`` e None quando
    a identidade NAO designa UM ponto unico.

    Guarda de correcao (colapso de pontos distintos): so reaproveita o ponto
    quando a identidade esta ligada a EXATAMENTE UM ponto canonico. Se o mesmo
    (fonte, tipo, valor) ja aponta para varios pontos (identificador ambiguo —
    endereco generico, codigo de rota, etc.), nao se funde nada: e registrado
    como identidade ambigua e o registro ganha ponto proprio, como uma fonte
    sem identificador confiavel.
    """
    if fonte_id is None or d.get("identificador") in (None, ""):
        return None, None
    tipo_id = dbmod.domain_id(conn, "TIPO_IDENTIFICADOR",
                              d.get("tipo_identificador", "id_orgao"))
    valor_norm = str(d["identificador"]).strip().upper()
    identificador_id = _buscar_por(conn, "IDENTIFICADOR_EXTERNO", {
        "fonte_id": fonte_id, "tipo_identificador_id": tipo_id,
        "valor_normalizado": valor_norm})
    if identificador_id is None:
        identificador_id = dbmod.insert(conn, "IDENTIFICADOR_EXTERNO", {
            "fonte_id": fonte_id,
            "tipo_identificador_id": tipo_id,
            "valor": d["identificador"],
            "valor_normalizado": valor_norm,
        })
        return None, identificador_id
    pontos = dbmod.query_all(
        conn, "SELECT DISTINCT ponto_id FROM IDENTIFICADOR_PONTO "
              "WHERE identificador_id=?", (identificador_id,))
    if len(pontos) != 1:
        # 0 pontos (nunca ligado) ou >1 pontos (identificador ambiguo)
        return None, identificador_id
    return pontos[0]["ponto_id"], identificador_id


def _identificador_externo_id(conn, fonte_id, d):
    """Linha de IDENTIFICADOR_EXTERNO do registro (criada sob demanda).

    Usada quando NAO se reutiliza a identidade (identificador ambiguo): o
    vinculo e gravado como EVIDENCIA, sem servir de chave de fusao.
    """
    if fonte_id is None or d.get("identificador") in (None, ""):
        return None
    tipo_id = dbmod.domain_id(conn, "TIPO_IDENTIFICADOR",
                              d.get("tipo_identificador", "id_orgao"))
    valor_norm = str(d["identificador"]).strip().upper()
    identificador_id = _buscar_por(conn, "IDENTIFICADOR_EXTERNO", {
        "fonte_id": fonte_id, "tipo_identificador_id": tipo_id,
        "valor_normalizado": valor_norm})
    if identificador_id is None:
        identificador_id = dbmod.insert(conn, "IDENTIFICADOR_EXTERNO", {
            "fonte_id": fonte_id,
            "tipo_identificador_id": tipo_id,
            "valor": d["identificador"],
            "valor_normalizado": valor_norm,
        })
    return identificador_id


def _equipamento_do_ponto(conn, ponto_id, tipo_radar_id, numero_serie):
    """Equipamento ja instalado NESTE ponto com o mesmo tipo/serie (ou None).

    Reaproveitar evita que o reingesto idempotente do MESMO ponto crie um
    equipamento novo a cada coleta (upsert). Compara serie com IS NULL.
    """
    for row in dbmod.query_all(
            conn,
            "SELECT e.id AS id, e.numero_serie AS numero_serie "
            "FROM EQUIPAMENTO e JOIN INSTALACAO i "
            "ON i.equipamento_id = e.id "
            "WHERE i.ponto_id=? AND e.tipo_radar_id=?",
            (ponto_id, tipo_radar_id)):
        if (row["numero_serie"] or None) == (numero_serie or None):
            return row["id"]
    return None


def inserir_normalizado(conn, registro_id, d, fonte_id=None,
                        reutilizar_identidade=True):
    """Insere OU atualiza o ponto normalizado (dict `d`), preservando evidencia.

    Identidade externa (spec 8.2): quando o registro traz `identificador` e uma
    `fonte_id`, o par (fonte_id, tipo_identificador, valor_normalizado) resolve
    UM ponto canonico via IDENTIFICADOR_EXTERNO + IDENTIFICADOR_PONTO. Se o
    ponto ja existe E a identidade designa UM unico ponto, ele e ATUALIZADO
    (municipio/via/km/pista/situacao/observacoes, por COALESCE — dado novo nao
    nulo sobrescreve, NULL preserva o que ja havia) e as linhas derivadas sao
    reaproveitadas; NAO se cria ponto duplicado. Cada registro adiciona o SEU
    proprio vinculo de evidencia (VINCULO_REGISTRO_PONTO + POSICAO_GEOGRAFICA
    por registro).

    ``reutilizar_identidade=False`` (identificador ambiguo DENTRO do mesmo
    artefato: o mesmo valor aparece em >1 registro que sao pontos diferentes)
    forca o comportamento de fonte sem identificador confiavel: cada registro
    cria o seu ponto. O identificador continua sendo gravado como evidencia.

    Devolve dict com ids e ``ponto_criado``/``atualizado``.
    """
    ajustar_coordenada_brasil(d)
    uf_sigla, municipio_id = resolver_uf_municipio(
        conn, d.get("uf"), d.get("municipio_nome"), d.get("municipio_ibge"),
        latitude=d.get("latitude"), longitude=d.get("longitude"))
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

    # --- identidade externa: ponto existente OU novo ---------------------
    if reutilizar_identidade:
        ponto_existente_id, identificador_id = _resolver_ponto_identificado(
            conn, fonte_id, d)
    else:
        ponto_existente_id = None
        identificador_id = _identificador_externo_id(conn, fonte_id, d)
    campos_ponto = {
        "posicao_id": posicao_id,
        "municipio_id": municipio_id,
        "via_id": via_id,
        "km": d.get("km"),
        "tipo_pista": d.get("tipo_pista"),
        "situacao_operacional_id": situacao_id,
        "observacoes": d.get("observacoes"),
    }
    ##-- BUNDITA DE URSO #{8} -- O DEFAULT oficial da migracao rotulava cadastros proprios como prova governamental. ##
    colunas = {r[1] for r in conn.execute("PRAGMA table_info(PONTO_FISCALIZACAO)")}
    if {"procedencia", "verificacao_status"} <= colunas:
        natureza = dbmod.scalar(conn, "SELECT n.codigo FROM FONTE f "
                                "JOIN NATUREZA_FONTE n ON n.id=f.natureza_id WHERE f.id=?",
                                (fonte_id,))
        campos_ponto["procedencia"] = ("oficial" if natureza == "oficial"
                                       else d.get("procedencia") or "cadastro_proprio")
        # Nao sobrescrever revisao/moderacao numa atualizacao do mesmo ponto.
        if ponto_existente_id is None:
            campos_ponto["verificacao_status"] = ("verificado" if natureza == "oficial"
                                                  else "nao_verificado")
    if ponto_existente_id is None:
        ponto_id = dbmod.insert(conn, "PONTO_FISCALIZACAO", campos_ponto)
        ponto_criado = True
    else:
        ponto_id = ponto_existente_id
        ponto_criado = False
        # COALESCE: valor novo nao nulo atualiza; NULL preserva o existente
        # (uma coleta mais pobre nao apaga o que ja se sabia do ponto).
        sets = ", ".join("%s=COALESCE(?, %s)" % (k, k)
                         for k in campos_ponto)
        conn.execute("UPDATE PONTO_FISCALIZACAO SET %s WHERE id=?" % sets,
                     list(campos_ponto.values()) + [ponto_id])

    # identidade externa -> ponto canonico (varios registros -> 1 ponto)
    if identificador_id is not None:
        if _buscar_por(conn, "IDENTIFICADOR_PONTO", {
                "identificador_id": identificador_id,
                "ponto_id": ponto_id}) is None:
            dbmod.insert(conn, "IDENTIFICADOR_PONTO", {
                "identificador_id": identificador_id, "ponto_id": ponto_id})

    # faixa (sentido) — so quando a fonte informa sentido/pista
    faixa_id = None
    if d.get("sentido") or d.get("sentido_original") or d.get("tipo_pista"):
        sentido_id = None
        if d.get("sentido"):
            sentido_id = dbmod.domain_id(conn, "SENTIDO", d["sentido"])
        campos = {"ponto_id": ponto_id, "sentido_id": sentido_id,
                  "sentido_original": d.get("sentido_original"),
                  "descricao": d.get("tipo_pista")}
        faixa_id, _ = _obter_ou_inserir(conn, "FAIXA_FISCALIZACAO", campos,
                                        campos)

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
                campos = {"faixa_id": faixa_id,
                          "categoria_veiculo_id": cat_id,
                          "velocidade_kmh": val}
            else:
                limite["ponto_id"] = ponto_id
                campos = {"ponto_id": ponto_id,
                          "categoria_veiculo_id": cat_id,
                          "velocidade_kmh": val}
            lid, _ = _obter_ou_inserir(conn, "LIMITE_VELOCIDADE", campos,
                                       limite)
            limites.append(lid)

    # regime de fiscalizacao
    modalidade = d.get("modalidade")
    if modalidade is None:
        modalidade = ("permanente" if d.get("tipo_radar") == "fixo"
                      else "desconhecida")
    modalidade_id = dbmod.domain_id(conn, "MODALIDADE_FISCALIZACAO",
                                    modalidade)
    campos = {"ponto_id": ponto_id, "modalidade_id": modalidade_id,
              "situacao_operacional_id": situacao_id}
    regime_id, _ = _obter_ou_inserir(conn, "REGIME_FISCALIZACAO", campos, {
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
    # upsert: reaproveita o equipamento ja instalado NESTE ponto (mesmo
    # tipo/serie) em vez de criar um novo a cada reingestao do MESMO ponto.
    equipamento_id = None
    if not ponto_criado:
        equipamento_id = _equipamento_do_ponto(
            conn, ponto_id, tipo_radar_id, d.get("numero_serie"))
    if equipamento_id is None:
        equipamento_id = dbmod.insert(conn, "EQUIPAMENTO", {
            "modelo_id": modelo_id,
            "tipo_radar_id": tipo_radar_id,
            "numero_serie": d.get("numero_serie"),
            "ano_fabricacao": d.get("ano_fabricacao"),
        })
    instalacao_id = _buscar_por(conn, "INSTALACAO", {
        "ponto_id": ponto_id, "equipamento_id": equipamento_id})
    if instalacao_id is None:
        instalacao_id = dbmod.insert(conn, "INSTALACAO", {
            "ponto_id": ponto_id,
            "equipamento_id": equipamento_id,
            "situacao_operacional_id": situacao_id,
        })

    # vinculo de proveniencia (cada registro -> o ponto canonico)
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
            "municipio_id": municipio_id,
            "ponto_criado": ponto_criado, "atualizado": not ponto_criado}


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
