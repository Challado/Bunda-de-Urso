# -*- coding: utf-8 -*-
"""Consultas read-only sobre o banco local (spec 9, 11, 14).

Duas fases: bounding box em SQL + Haversine na aplicacao (sem PostGIS).
LIMIT so depois do calculo de distancia (spec 9.4).
"""
import datetime
import json
import sqlite3

from . import db as dbmod
from . import geo
from . import georesolver
from .identidade import VisaoCanonica

_PONTO_SQL = """
SELECT p.id AS ponto_id, p.km AS km, p.tipo_pista AS tipo_pista,
       p.observacoes AS observacoes, p.inicio_operacao AS inicio_operacao,
       p.data_inativacao AS data_inativacao,
       pos.id AS posicao_id, pos.latitude AS latitude,
       pos.longitude AS longitude, pos.precisao_metros AS precisao_metros,
       pos.metodo_obtencao AS metodo_obtencao,
       qp.codigo AS qualidade,
       m.codigo_ibge AS codigo_ibge, m.nome AS municipio, u.sigla AS uf,
       v.codigo AS via_codigo, v.nome AS via_nome, tv.codigo AS via_tipo,
       so.codigo AS situacao_operacional
FROM PONTO_FISCALIZACAO p
LEFT JOIN POSICAO_GEOGRAFICA pos ON pos.id = p.posicao_id
LEFT JOIN QUALIDADE_POSICAO qp ON qp.id = pos.qualidade_posicao_id
LEFT JOIN MUNICIPIO m ON m.codigo_ibge = p.municipio_id
LEFT JOIN UF u ON u.sigla = m.uf_sigla
LEFT JOIN VIA v ON v.id = p.via_id
LEFT JOIN TIPO_VIA tv ON tv.id = v.tipo_via_id
LEFT JOIN SITUACAO_OPERACIONAL so ON so.id = p.situacao_operacional_id
"""


def _bbox_clause(lat_min, lat_max, lon_min, lon_max, cruza):
    if cruza:
        lon_min_n = geo.normaliza_longitude(lon_min)
        lon_max_n = geo.normaliza_longitude(lon_max)
        return ("pos.latitude BETWEEN ? AND ? AND "
                "(pos.longitude >= ? OR pos.longitude <= ?)",
                [lat_min, lat_max, lon_min_n, lon_max_n])
    return ("pos.latitude BETWEEN ? AND ? AND pos.longitude BETWEEN ? AND ?",
            [lat_min, lat_max, lon_min, lon_max])


##-- BUNDITA DE URSO #{17} -- A UF de um alias nao pode alterar a localizacao original escolhida para o canonico. ##
def _uf_original(conn, pid):
    """UF derivada do payload original quando NAO ha municipio cadastrado.

    Nao inventa nada: le o campo 'uf'/sigla ja publicado pela propria fonte
    (spec: texto administrativo sem IBGE nao vira codigo, mas a sigla de UF
    publicada e um dado real da origem).
    """
    for r in dbmod.query_all(
            conn, "SELECT r.payload_original AS p "
            "FROM VINCULO_REGISTRO_PONTO vp "
            "JOIN REGISTRO_FONTE r ON r.id=vp.registro_id "
            "WHERE vp.ponto_id=? AND vp.decisao_id IS NULL ORDER BY r.id", (pid,)):
        try:
            d = json.loads(r["p"])
        except (ValueError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        baixo = {str(k).strip().lower(): v for k, v in d.items()}
        for chave in ("uf", "sigla uf", "siglauf", "estado uf", "uf_sigla"):
            v = baixo.get(chave)
            if not v:
                continue
            s = str(v).strip().upper()
            if len(s) == 2 and s.isalpha():
                return s
    return None


def _uf_do_ponto(conn, row):
    """UF do ponto: municipio cadastrado; senao a UF publicada na origem."""
    uf = row["uf"] if "uf" in row.keys() else None
    return (uf or _uf_original(conn, row["ponto_id"]) or "").upper() or None


def _governanca_do_ponto(conn, pid):
    """Campos de governanca do ponto (ou {} se a base ainda nao os tem)."""
    try:
        row = dbmod.query_one(
            conn, "SELECT procedencia, verificacao_status, removido_em, "
            "motivo_remocao FROM PONTO_FISCALIZACAO WHERE id=?", (pid,))
    except sqlite3.OperationalError:
        return {}
    return dict(row) if row is not None else {}


def _filtros_extra(filtros, conn=None):
    clauses = []
    params = []
    # O filtro de UF NAO entra em SQL: a UF pode vir do municipio OU do
    # payload original (ponto sem municipio cadastrado). Filtra-se em
    # Python com _uf_do_ponto (spec: nao inventar IBGE, mas nao descartar
    # a UF real publicada pela fonte).
    if filtros.get("municipio_ibge"):
        clauses.append("m.codigo_ibge = ?")
        params.append(filtros["municipio_ibge"])
    if filtros.get("rodovia"):
        clauses.append("v.codigo = ?")
        params.append(filtros["rodovia"])
    if not filtros.get("incluir_inativos", False):
        clauses.append("(so.codigo IS NULL OR so.codigo <> 'inativo')")
    if filtros.get("registro_id"):
        clauses.append(
            "p.id IN (SELECT ponto_id FROM VINCULO_REGISTRO_PONTO WHERE registro_id = ?)")
        params.append(filtros["registro_id"])
    if filtros.get("tipo_radar"):
        clauses.append(
            "p.id IN (SELECT i.ponto_id FROM INSTALACAO i "
            "JOIN EQUIPAMENTO e ON e.id=i.equipamento_id "
            "JOIN TIPO_RADAR tr ON tr.id=e.tipo_radar_id WHERE tr.codigo = ?)")
        params.append(filtros["tipo_radar"])
    if filtros.get("sentido"):
        clauses.append(
            "p.id IN (SELECT f.ponto_id FROM FAIXA_FISCALIZACAO f "
            "JOIN SENTIDO s ON s.id=f.sentido_id WHERE s.codigo = ?)")
        params.append(filtros["sentido"])
    if filtros.get("modalidade"):
        clauses.append(
            "p.id IN (SELECT r.ponto_id FROM REGIME_FISCALIZACAO r "
            "JOIN MODALIDADE_FISCALIZACAO mf ON mf.id=r.modalidade_id "
            "WHERE mf.codigo = ?)")
        params.append(filtros["modalidade"])
    # GOVERNANCA: esconde removidos (tombstone) e desabilitados e, quando ha
    # uma decisao explicita de moderacao, pode preferir o colaborativo.
    # Proximidade sozinha nunca oculta o oficial. Bases antigas sao suportadas.
    if conn is not None:
        ##-- BUNDITA DE URSO #{8} -- Erro de governanca nao pode desativar silenciosamente os filtros de remocao. ##
        from . import governanca as _gov
        gclauses, gparams = _gov.clausulas_consulta(conn)
        clauses.extend(gclauses)
        params.extend(gparams)
    return clauses, params


def _pontos_inferidos_dentro(conn, lat, lon, raio, filtros):
    """Pontos SEM posicao que ganham coordenada INFERIDA via (via, km).

    Le os pontos sem POSICAO_GEOGRAFICA mas com via + km, resolve o km pelo
    referenciamento linear (``core.georesolver``) e filtra por Haversine. So
    entram os que resolvem de forma inequivoca (``status == 'ok'``);
    ``ambiguo``/``fora_de_faixa``/``sem_calibracao`` NAO entram (nada e
    inventado). A coordenada sai marcada ``qualidade='inferida'`` /
    ``metodo_obtencao='linear_km'``.

    Devolve lista de ``(distancia_m, row)`` no mesmo formato de ``_PONTO_SQL``.
    """
    candidatos = dbmod.query_all(
        conn,
        "SELECT p.id AS ponto_id, v.codigo AS via_codigo, p.km AS km "
        "FROM PONTO_FISCALIZACAO p JOIN VIA v ON v.id = p.via_id "
        "WHERE p.posicao_id IS NULL AND p.via_id IS NOT NULL "
        "AND p.km IS NOT NULL", ())
    if not candidatos:
        return []
    calibracao = georesolver.calibracao()
    dentro = {}
    for c in candidatos:
        try:
            res = georesolver.resolver(c["via_codigo"], c["km"],
                                       calibracao=calibracao)
        except (ValueError, TypeError):
            continue
        if res.get("status") != georesolver.STATUS_OK:
            continue                      # nao resolvido: nao entra
        rlat, rlon = res.get("lat"), res.get("lon")
        if rlat is None or rlon is None:
            continue
        dist = geo.haversine_m(lat, lon, rlat, rlon)
        if dist <= raio:
            dentro[c["ponto_id"]] = (dist, rlat, rlon)
    if not dentro:
        return []
    ids = sorted(dentro)
    placeholders = ",".join("?" * len(ids))
    extra, extra_params = _filtros_extra(filtros, conn)
    sql = _PONTO_SQL + " WHERE p.id IN (%s)" % placeholders
    if extra:
        sql += " AND " + " AND ".join(extra)
    saida = []
    for row in dbmod.query_all(conn, sql, ids + extra_params):
        dist, rlat, rlon = dentro[row["ponto_id"]]
        d = dict(row)
        d["latitude"] = rlat
        d["longitude"] = rlon
        d["precisao_metros"] = None
        d["qualidade"] = georesolver.QUALIDADE_INFERIDA
        d["metodo_obtencao"] = georesolver.METODO
        d["posicao_id"] = None
        saida.append((dist, d))
    return saida


##-- BUNDITA DE URSO #{1} -- Consultas ignoravam a unificacao e contavam entidades duplicadas. ##
def buscar_pontos(conn, lat, lon, raio, filtros=None, limite=100, cursor=None):
    """Retorna (records, meta) com pontos dentro do raio, ordenados por
    distancia. `meta` traz total_pontos/total_equipamentos/proximo_cursor."""
    filtros = filtros or {}
    bb = geo.bounding_box(lat, lon, raio)
    bbox_sql, bbox_params = _bbox_clause(
        bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"],
        bb["cruza_antimeridiano"])
    extra, extra_params = _filtros_extra(filtros, conn)
    where = bbox_sql if not extra else bbox_sql + " AND " + " AND ".join(extra)
    sql = _PONTO_SQL + " WHERE " + where
    rows = dbmod.query_all(conn, sql, bbox_params + extra_params)

    visao = VisaoCanonica(conn)
    uf_filtro = (filtros.get("uf") or "").upper() or None
    dentro = []
    encontrados = set()
    for r in rows:
        r = _linha_canonica(conn, r, visao)
        if r is None or r["ponto_id"] in encontrados:
            continue
        if r["latitude"] is None or r["longitude"] is None:
            continue
        if uf_filtro and _uf_do_ponto(conn, r) != uf_filtro:
            continue
        dist = geo.haversine_m(lat, lon, r["latitude"], r["longitude"])
        if dist <= raio:
            dentro.append((dist, r))
            encontrados.add(r["ponto_id"])
    dentro.sort(key=lambda t: (t[0], t[1]["ponto_id"]))

    inferidos = _pontos_inferidos_dentro(conn, lat, lon, raio, filtros)
    uf_inf = (filtros.get("uf") or "").upper() or None
    for dist, r in inferidos:
        r = _linha_canonica(conn, r, visao)
        if r is None or r["ponto_id"] in encontrados:
            continue
        if r["latitude"] is None or r["longitude"] is None:
            continue
        dist = geo.haversine_m(lat, lon, r["latitude"], r["longitude"])
        if dist > raio:
            continue
        if uf_inf and _uf_do_ponto(conn, r) != uf_inf:
            continue
        dentro.append((dist, r))
        encontrados.add(r["ponto_id"])
    dentro.sort(key=lambda t: (t[0], t[1]["ponto_id"]))

    incluir_operacoes = filtros.get("incluir_operacoes", True)
    pontual = filtros.get("fiscalizacao_pontual")
    pre_montados = {}
    ##-- BUNDITA DE URSO #{15} -- Filtrar depois de paginar produzia totais e paginas incorretos. ##
    if pontual is not None:
        filtrados = []
        for dist, row in dentro:
            registro = montar_registro(conn, row, round(dist, 3), incluir_operacoes, visao)
            ##-- BUNDITA DE URSO #{21} -- Regimes mistos satisfazem ambos os filtros; um regime nao pode apagar o outro. ##
            modalidades = {rg["modalidade_fiscalizacao"] == "pontual"
                           for rg in registro["regimes"]
                           if rg.get("modalidade_fiscalizacao") not in (None, "", "desconhecida")}
            if bool(pontual) in modalidades:
                filtrados.append((dist, row))
                pre_montados[row["ponto_id"]] = registro
        dentro = filtrados
    total = len(dentro)
    offset = max(0, _offset_cursor(cursor))
    recorte = dentro[offset:offset + limite]
    records = [pre_montados.get(r["ponto_id"]) or montar_registro(
        conn, r, round(dist, 3), incluir_operacoes, visao) for dist, r in recorte]
    # Contagem de instrumentos de todo o resultado, nao so da pagina.
    pontos = {m for _, r in dentro for m in visao.membros("ponto", r["ponto_id"])}
    equipamentos = set()
    if pontos:
        # Consultas por ponto evitam exceder o limite de parametros SQLite.
        for pid in pontos:
            equipamentos.update(visao.canonico("equipamento", row[0]) for row in conn.execute(
                "SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?", (pid,)))
    return records, {
        "total_pontos": total,
        "total_equipamentos": len(equipamentos),
        "retornados": len(records),
        "proximo_cursor": str(offset + limite) if offset + limite < total else None,
        "total_inferidos": sum(r["qualidade"] == georesolver.QUALIDADE_INFERIDA for _, r in dentro),
    }


def _row_to_base(r, distancia_metros=None):
    return {
        "id": "P-%d" % r["ponto_id"],
        "tipo_registro": "ponto_fiscalizacao",
        "situacao_operacional": r["situacao_operacional"],
        "situacao_original": None,
        "localizacao": {
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "distancia_metros": distancia_metros,
            "precisao_metros": r["precisao_metros"],
            "qualidade": r["qualidade"],
            "metodo_obtencao": r["metodo_obtencao"],
            "uf": r["uf"],
            "municipio": r["municipio"],
            "codigo_ibge": r["codigo_ibge"],
            "endereco": {},
            "via": {"codigo": r["via_codigo"], "tipo": r["via_tipo"],
                    "nome": r["via_nome"]},
            "km": r["km"],
            "tipo_pista": r["tipo_pista"],
        },
        "data_inicio_operacao": r["inicio_operacao"],
        "data_inativacao": r["data_inativacao"],
        "motivo_inativacao": None,
    }


def _resolver_velocidades(limites):
    """Agrupa limites por (categoria, faixa) e NUNCA arbitra conflito.

    Quando a mesma categoria/faixa traz mais de um valor publicado, a
    velocidade resolvida fica None e todos os valores ficam expostos em
    `valores_publicados_kmh` (spec 8/17.4: nao fabricar valor consolidado).
    Retorna (resolvidos, conflitos).
    """
    por_escopo = {}
    for lim in limites:
        escopo = (lim["categoria_veiculo"], lim["faixa_id"])
        por_escopo.setdefault(escopo, []).append(lim)
    resolvidos, conflitos = [], []
    for (categoria, faixa), obs in sorted(
            por_escopo.items(), key=lambda kv: (kv[0][0] or "",
                                                kv[0][1] or "")):
        valores = sorted({o["velocidade_kmh"] for o in obs
                          if o["velocidade_kmh"] is not None})
        if len(valores) > 1:
            conflitos.append({
                "campo": "limite_velocidade", "categoria": categoria,
                "faixa_id": faixa, "valores_kmh": valores})
        resolvidos.append({
            "categoria": categoria, "faixa_id": faixa,
            "velocidade_kmh": valores[0] if len(valores) == 1 else None,
            "estado": "conflitante" if len(valores) > 1 else "sem_conflito",
            "valores_publicados_kmh": valores,
        })
    return resolvidos, conflitos


def _top_velocidade(resolvidos, categoria):
    """Limite de escopo geral (sem faixa) para a categoria, se nao conflitar."""
    for r in resolvidos:
        if r["categoria"] == categoria and r["faixa_id"] is None:
            return r["velocidade_kmh"]
    return None


def _montar_registro_original(conn, r, distancia_metros=None, incluir_operacoes=True):
    pid = r["ponto_id"]
    reg = _row_to_base(r, distancia_metros)
    if reg["localizacao"].get("uf") is None:
        reg["localizacao"]["uf"] = _uf_original(conn, pid)

    faixas = []
    for f in dbmod.query_all(
            conn, "SELECT f.id, f.numero_faixa, f.sentido_original, "
            "s.codigo AS sentido FROM FAIXA_FISCALIZACAO f "
            "LEFT JOIN SENTIDO s ON s.id=f.sentido_id WHERE f.ponto_id=?",
            (pid,)):
        faixas.append({"id": "F-%d" % f["id"], "numero": f["numero_faixa"],
                       "sentido": f["sentido"],
                       "sentido_original": f["sentido_original"]})
    reg["faixas"] = faixas

    limites = []
    for lim in dbmod.query_all(
            conn, "SELECT l.id, l.faixa_id, l.velocidade_kmh, l.vigencia_inicio, "
            "l.vigencia_fim, l.registro_fonte_id, c.codigo AS categoria "
            "FROM LIMITE_VELOCIDADE l "
            "LEFT JOIN CATEGORIA_VEICULO c ON c.id=l.categoria_veiculo_id "
            "WHERE l.ponto_id=? OR l.faixa_id IN "
            "(SELECT id FROM FAIXA_FISCALIZACAO WHERE ponto_id=?)",
            (pid, pid)):
        limites.append({
            "faixa_id": ("F-%d" % lim["faixa_id"]) if lim["faixa_id"] else None,
            "categoria_veiculo": lim["categoria"],
            "velocidade_kmh": lim["velocidade_kmh"],
            "vigencia_inicio": lim["vigencia_inicio"],
            "vigencia_fim": lim["vigencia_fim"],
            "fonte_registro_id": lim["registro_fonte_id"],
        })
    reg["limites_velocidade"] = limites
    resolvidos, conflitos_velocidade = _resolver_velocidades(limites)
    reg["velocidades_resolvidas"] = resolvidos
    reg["velocidade_leves_kmh"] = _top_velocidade(resolvidos, "leves")
    reg["velocidade_pesados_kmh"] = _top_velocidade(resolvidos, "pesados")
    reg["velocidade_geral_kmh"] = _top_velocidade(resolvidos, "geral")
    reg["conflitos"] = conflitos_velocidade
    reg["quantidade_faixas_declarada"] = None

    regimes = []
    for rg in dbmod.query_all(
            conn, "SELECT r.id, r.inicio_em, r.fim_em, "
            "mf.codigo AS modalidade, tm.codigo AS tipo_medicao, "
            "so.codigo AS situacao FROM REGIME_FISCALIZACAO r "
            "LEFT JOIN MODALIDADE_FISCALIZACAO mf ON mf.id=r.modalidade_id "
            "LEFT JOIN TIPO_MEDICAO tm ON tm.id=r.tipo_medicao_id "
            "LEFT JOIN SITUACAO_OPERACIONAL so ON so.id=r.situacao_operacional_id "
            "WHERE r.ponto_id=?", (pid,)):
        regimes.append({
            "id": "R-%d" % rg["id"],
            "modalidade_fiscalizacao": rg["modalidade"],
            "tipo_medicao": rg["tipo_medicao"],
            "situacao_operacional": rg["situacao"],
            "inicio_em": rg["inicio_em"], "fim_em": rg["fim_em"],
        })
    reg["regimes"] = regimes
    reg["fiscalizacao_pontual"] = _derivar_pontual(regimes)

    equipamentos = []
    tipos = []
    for eq in dbmod.query_all(
            conn, "SELECT e.id, e.numero_serie, e.ano_fabricacao, "
            "tr.codigo AS tipo_radar, mo.nome_modelo, fa.nome AS fabricante, "
            "i.id AS instalacao_id, i.inicio_em, i.fim_em "
            "FROM INSTALACAO i "
            "JOIN EQUIPAMENTO e ON e.id=i.equipamento_id "
            "JOIN TIPO_RADAR tr ON tr.id=e.tipo_radar_id "
            "LEFT JOIN MODELO_EQUIPAMENTO mo ON mo.id=e.modelo_id "
            "LEFT JOIN ORGANIZACAO fa ON fa.id=mo.fabricante_id "
            "WHERE i.ponto_id=?", (pid,)):
        equipamentos.append({
            "id": "E-%d" % eq["id"],
            "tipo_radar": eq["tipo_radar"],
            "tipo_radar_original": None,
            "funcao_equipamento": None,
            "sigla_equipamento_original": None,
            "fabricante": eq["fabricante"],
            "modelo": eq["nome_modelo"],
            "tecnologia_medicao": None,
            "numero_serie": eq["numero_serie"],
            "ano_fabricacao": eq["ano_fabricacao"],
            "registro_aprovacao_modelo": None,
            "portaria_aprovacao_modelo": None,
            "identificadores_oficiais": [],
            "instalacoes": [{"id": "I-%d" % eq["instalacao_id"],
                             "ponto_id": reg["id"],
                             "inicio_em": eq["inicio_em"],
                             "fim_em": eq["fim_em"],
                             "situacao": r["situacao_operacional"],
                             "faixas_ids": [],
                             "data_inicio_educativo": None,
                             "data_inicio_autuacao": None}],
            "verificacoes_metrologicas": [],
            "proprietario": None, "mantenedor": None,
            "ultima_manutencao": None, "observacoes": None,
        })
        if eq["tipo_radar"] and eq["tipo_radar"] not in tipos:
            tipos.append(eq["tipo_radar"])
    reg["equipamentos"] = equipamentos
    reg["tipos_radar_presentes"] = tipos

    organizacoes = []
    for org in dbmod.query_all(
            conn, "SELECT o.id, o.nome, p.codigo AS papel, po.inicio_em, po.fim_em "
            "FROM PONTO_ORGANIZACAO po JOIN ORGANIZACAO o ON o.id=po.organizacao_id "
            "LEFT JOIN PAPEL_ORGANIZACAO p ON p.id=po.papel_id "
            "WHERE po.ponto_id=?", (pid,)):
        organizacoes.append({"id": "O-%d" % org["id"], "nome": org["nome"],
                             "papel": org["papel"],
                             "inicio_em": org["inicio_em"],
                             "fim_em": org["fim_em"]})
    reg["organizacoes"] = organizacoes

    documentos = []
    for doc in dbmod.query_all(
            conn, "SELECT d.id, td.codigo AS tipo, d.codigo_documento, "
            "d.titulo, d.url, d.data_emissao, d.validade_ate, d.descricao "
            "FROM DOCUMENTO_PONTO dp JOIN DOCUMENTO d ON d.id=dp.documento_id "
            "LEFT JOIN TIPO_DOCUMENTO td ON td.id=d.tipo_documento_id "
            "WHERE dp.ponto_id=?", (pid,)):
        documentos.append({
            "id": "D-%d" % doc["id"], "tipo_documento": doc["tipo"],
            "codigo_documento": doc["codigo_documento"], "titulo": doc["titulo"],
            "url": doc["url"], "data_emissao": doc["data_emissao"],
            "validade_ate": doc["validade_ate"], "orgao_emissor": None,
            "hash_conteudo": None, "descricao": doc["descricao"]})
    reg["documentos"] = documentos

    reg["fontes"] = _fontes_do_ponto(conn, pid)
    reg["operacoes"] = (operacoes_do_ponto(conn, pid)
                        if incluir_operacoes else [])
    reg["primeira_observacao"] = None
    reg["ultima_confirmacao"] = None
    reg["ultima_coleta"] = reg["fontes"][0]["coletado_em"] if reg["fontes"] else None
    reg["confianca"] = ("conflitante" if conflitos_velocidade
                        else "nao_avaliada")
    reg["observacoes"] = r["observacoes"]
    reg["proveniencia_campos"] = {}
    gov = _governanca_do_ponto(conn, pid)
    if gov:
        reg["procedencia"] = gov.get("procedencia")
        reg["verificacao_status"] = gov.get("verificacao_status")
        reg["removido_em"] = gov.get("removido_em")
        reg["motivo_remocao"] = gov.get("motivo_remocao")
    return reg


def _unicos(itens):
    vistos, saida = set(), []
    for item in itens:
        chave = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if chave not in vistos:
            vistos.add(chave)
            saida.append(item)
    return saida


##-- BUNDITA DE URSO #{1} -- Aliases precisam resolver o ponto vencedor sem ressuscitar entidades removidas. ##
def _linha_canonica(conn, row, visao):
    pid = visao.canonico("ponto", row["ponto_id"])
    if pid == row["ponto_id"]:
        return row
    # Uma entidade removida/desabilitada nao pode reaparecer por um alias.
    from . import governanca
    clausulas, params = governanca.clausulas_consulta(conn)
    sql = _PONTO_SQL + " WHERE p.id=?"
    canonico = dbmod.query_one(conn, sql, (pid,))
    if canonico is None:
        return row
    ##-- BUNDITA DE URSO #{20} -- Escolher o ID canonico nao pode apagar GPS divergente, valido ou inferido de outra fonte. ##
    localizado = row["latitude"] is not None and row["longitude"] is not None
    if localizado and any(row[k] != canonico[k] for k in ("latitude", "longitude")):
        return row
    # Filtros foram satisfeitos pela observacao original. Nao trocar seus
    # atributos por uma versao inativa ou de outra UF/via depois do filtro.
    if any(row[k] != canonico[k] for k in
           ("codigo_ibge", "via_codigo", "km", "situacao_operacional")):
        return row
    if _uf_do_ponto(conn, row) != _uf_do_ponto(conn, canonico):
        return row
    if clausulas:
        # Uma remocao do canonico so oculta aliases equivalentes. Outra
        # posicao publicada e uma divergencia preservada, nao uma exclusao.
        return dbmod.query_one(conn, sql + " AND " + " AND ".join(clausulas), [pid] + params)
    return canonico


##-- BUNDITA DE URSO #{1} -- Consolidar requer preservar faixas, fontes e divergencias dos pontos originais. ##
def montar_registro(conn, r, distancia_metros=None, incluir_operacoes=True, visao=None):
    visao = visao or VisaoCanonica(conn)
    r = _linha_canonica(conn, r, visao)
    if r is None:
        return None
    pid = r["ponto_id"]
    reg = _montar_registro_original(conn, r, distancia_metros, incluir_operacoes)
    membros = visao.membros("ponto", pid)
    campos_lista = ("faixas", "limites_velocidade", "regimes", "equipamentos",
                    "organizacoes", "documentos", "fontes", "operacoes")
    for outro in membros:
        if outro == pid:
            continue
        row = dbmod.query_one(conn, _PONTO_SQL + " WHERE p.id=?", (outro,))
        if row is None:
            continue
        original = _montar_registro_original(conn, row, incluir_operacoes=incluir_operacoes)
        for campo in campos_lista:
            reg[campo].extend(original[campo])
        ##-- BUNDITA DE URSO #{20} -- Ausencia de GPS nao e uma coordenada contraditoria; preservar e comparar apenas valores publicados. ##
        comparaveis = [(original["localizacao"].get(k), reg["localizacao"].get(k))
                      for k in ("latitude", "longitude", "km", "uf", "codigo_ibge")]
        comparaveis.append((original["localizacao"]["via"].get("codigo"),
                            reg["localizacao"]["via"].get("codigo")))
        if any(a is not None and b is not None and a != b for a, b in comparaveis):
            reg["conflitos"].append({"campo": "localizacao", "ponto_original_id": original["id"],
                                     "valor_original": original["localizacao"]})
    for campo in campos_lista:
        reg[campo] = _unicos(reg[campo])
    # Mesmo instrumento em duas instalacoes e uma entidade, com ambos os historicos.
    equipamentos, vistos = [], set()
    for equip in reg["equipamentos"]:
        eid = visao.canonico("equipamento", int(equip["id"][2:]))
        if eid in vistos:
            continue
        vistos.add(eid)
        if len(visao.membros("equipamento", eid)) > 1:
            equip = buscar_equipamento_por_id(conn, eid, visao=visao)
        equipamentos.append(equip)
    reg["equipamentos"] = equipamentos
    reg["tipos_radar_presentes"] = sorted({e["tipo_radar"] for e in equipamentos if e["tipo_radar"]})
    resolvidos, conflitos = _resolver_velocidades(reg["limites_velocidade"])
    reg["velocidades_resolvidas"] = resolvidos
    for categoria in ("leves", "pesados", "geral"):
        reg["velocidade_" + categoria + "_kmh"] = _top_velocidade(resolvidos, categoria)
    reg["conflitos"] = _unicos(reg["conflitos"] + conflitos)
    reg["fiscalizacao_pontual"] = _derivar_pontual(reg["regimes"])
    if reg["conflitos"]:
        reg["confianca"] = "conflitante"
    if len(membros) > 1:
        reg["aliases"] = ["P-%d" % i for i in membros if i != pid]
        ##-- BUNDITA DE URSO #{20} -- Uma marcacao preservada precisa informar sua identidade comum sem perder a coordenada original. ##
        reg["ponto_canonico_id"] = "P-%d" % visao.canonico("ponto", pid)
        reg["proveniencia_campos"]["reconciliacao"] = {
            "ponto_canonico_id": reg["ponto_canonico_id"],
            "marcacao_original_id": reg["id"],
            "pontos_originais": ["P-%d" % i for i in membros],
        }
    return reg


def _derivar_pontual(regimes):
    if not regimes:
        return None
    modalidades = [rg.get("modalidade_fiscalizacao") for rg in regimes]
    if any(m == "pontual" for m in modalidades):
        ##-- BUNDITA DE URSO #{21} -- Modalidades permanente e pontual coexistentes nao cabem num unico booleano. ##
        if any(m not in (None, "", "pontual", "desconhecida") for m in modalidades):
            return None
        return True
    if all(m and m != "desconhecida" for m in modalidades):
        return False
    return None


def _fmt_fonte(f):
    return {
        "id": "S-%d" % f["id"], "nome": f["nome"], "esfera": f["esfera"],
        "organizacao": f["organizacao"], "url": f["url_institucional"],
        "recurso_url": f["url_recurso"],
        "id_registro_original": None,
        "publicado_em": None, "coletado_em": f["iniciada_em"],
        "validado_em": f["baixado_em"],
        "ultima_verificacao_acesso": f["baixado_em"],
        "hash_artefato": f["hash_sha256"],
        "status_integracao": f["status_integracao"],
        "idade_dados_segundos": None,
    }


def _fontes_do_ponto(conn, pid):
    out = []
    for f in dbmod.query_all(
            conn, "SELECT DISTINCT fo.id, fo.nome, fo.esfera, org.nome AS organizacao, "
            "fo.url_institucional, rf.url_recurso, rf.status_integracao, "
            "a.hash_sha256, a.baixado_em, ac.iniciada_em "
            "FROM VINCULO_REGISTRO_PONTO vp "
            "JOIN REGISTRO_FONTE r ON r.id=vp.registro_id "
            "JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id "
            "JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id "
            "JOIN FONTE fo ON fo.id=rf.fonte_id "
            "JOIN ORGANIZACAO org ON org.id=fo.organizacao_id "
            "LEFT JOIN EXECUCAO_COLETA ac ON ac.artefato_id=a.id "
            "WHERE vp.ponto_id=?", (pid,)):
        out.append(_fmt_fonte(f))
    return out


def _fontes_por_registro(conn, registro_id):
    """Fontes de proveniencia de UM REGISTRO_FONTE (usado por trechos/operacoes)."""
    if registro_id is None:
        return []
    out = []
    for f in dbmod.query_all(
            conn, "SELECT fo.id, fo.nome, fo.esfera, org.nome AS organizacao, "
            "fo.url_institucional, rf.url_recurso, rf.status_integracao, "
            "a.hash_sha256, a.baixado_em, ac.iniciada_em "
            "FROM REGISTRO_FONTE r "
            "JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id "
            "JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id "
            "JOIN FONTE fo ON fo.id=rf.fonte_id "
            "JOIN ORGANIZACAO org ON org.id=fo.organizacao_id "
            "LEFT JOIN EXECUCAO_COLETA ac ON ac.artefato_id=a.id "
            "WHERE r.id=?", (registro_id,)):
        out.append(_fmt_fonte(f))
    return out


# O cadastro proprio pode guardar contato e metadados privados no bruto.
# Apenas campos de radar ja aceitos pelo normalizador entram no detalhe publico.
_CAMPOS_PUBLICOS_CADASTRO = frozenset((
    "identificador", "id_orgao", "codigo", "id", "ID", "tipo_identificador",
    "latitude", "lat", "longitude", "lon", "lng", "precisao_metros", "precisao",
    "qualidade", "qualidade_posicao", "metodo_obtencao", "municipio",
    "municipio_nome", "cidade", "municipio_ibge", "codigo_ibge", "ibge",
    "uf", "UF", "estado", "via", "via_codigo", "rodovia", "br", "km",
    "quilometro", "tipo_pista", "pista", "faixa", "situacao", "status",
    "tipo_radar", "tipo", "modalidade", "numero_serie", "serie", "fabricante",
    "marca", "modelo", "ano_fabricacao", "velocidade_leves", "velocidade_pesados",
    "velocidade_geral", "velocidade", "sentido", "observacoes",
))


def _dados_por_fonte(conn, pid, visao, registros_metrologicos=()):
    """Publicacoes originais por fonte, somente no detalhe do ponto.

    Nao atribui campos consolidados a todas as fontes nem reinterpreta o bruto
    com o normalizador atual. Preserva valores divergentes e coletas historicas.
    """
    grupos, registros = {}, {}
    membros = visao.membros("ponto", pid)
    selecionados = {r[0] for membro in membros for r in conn.execute(
        "SELECT registro_id FROM VINCULO_REGISTRO_PONTO WHERE ponto_id=?", (membro,))}
    registros_do_ponto = set(selecionados)
    selecionados.update(rid for rid in registros_metrologicos if rid is not None)
    # Consultas por PK evitam produto cartesiano entre faixas, verificacoes e fontes.
    for rid in sorted(selecionados):
        for row in dbmod.query_all(conn, """
                SELECT r.id AS registro_id, r.identificador_na_fonte,
                       r.payload_original, a.hash_sha256, a.baixado_em,
                       rf.nome AS recurso, rf.url_recurso,
                       fo.id AS fonte_id, fo.nome, fo.url_institucional,
                       n.codigo AS natureza, org.nome AS organizacao
                FROM REGISTRO_FONTE r
                JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
                JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
                JOIN FONTE fo ON fo.id=rf.fonte_id
                JOIN NATUREZA_FONTE n ON n.id=fo.natureza_id
                JOIN ORGANIZACAO org ON org.id=fo.organizacao_id
                WHERE r.id=?
                """, (rid,)):
            registros[row["registro_id"]] = row
    for row in sorted(registros.values(),
                      key=lambda r: (r["baixado_em"], r["registro_id"]), reverse=True):
        fid = row["fonte_id"]
        grupo = grupos.setdefault(fid, {
            "id": "S-%d" % fid, "nome": row["nome"],
            "organizacao": row["organizacao"], "natureza": row["natureza"],
            "url": row["url_institucional"], "registros": [],
        })
        try:
            dados = json.loads(row["payload_original"])
        except (ValueError, TypeError):
            dados = None
        if row["natureza"] != "oficial":
            dados = {k: v for k, v in dados.items()
                     if k in _CAMPOS_PUBLICOS_CADASTRO
                     and not isinstance(v, (dict, list))} if isinstance(dados, dict) else {}
        grupo["registros"].append({
            "registro_id": row["registro_id"],
            "id_registro_original": row["identificador_na_fonte"],
            "recurso": row["recurso"], "recurso_url": row["url_recurso"],
            "coletado_em": row["baixado_em"],
            "hash_artefato": row["hash_sha256"], "dados_publicados": dados,
            "escopo_vinculo": "ponto" if row["registro_id"] in registros_do_ponto else "equipamento",
        })
    return sorted(grupos.values(), key=lambda grupo: (grupo["nome"].casefold(), grupo["id"]))


def operacoes_do_ponto(conn, pid):
    """Operacoes publicadas vinculadas a UM ponto (spec 11.4)."""
    out = []
    for r in dbmod.query_all(conn, _OPERACAO_SQL + " WHERE o.ponto_id = ? "
                             "ORDER BY o.id", (pid,)):
        out.append(montar_operacao(conn, r))
    return out


##-- BUNDITA DE URSO #{1} -- O detalhe de um alias deve retornar a mesma entidade canonica da busca. ##
def buscar_ponto_por_id(conn, pid_str):
    try:
        pid = int(str(pid_str).upper().replace("P-", ""))
    except (TypeError, ValueError):
        return None
    visao = VisaoCanonica(conn)
    ##-- BUNDITA DE URSO #{20} -- O detalhe do alias tambem precisa preservar a posicao que aparece no mapa. ##
    r = dbmod.query_one(conn, _PONTO_SQL + " WHERE p.id = ?", (pid,))
    if r is None:
        return None
    registro = montar_registro(conn, r, visao=visao)
    if registro is not None:
        # A lista do mapa usa um resumo. O detalhe precisa do mesmo historico
        # metrologico e identificacao devolvidos no endpoint do instrumento.
        registro["equipamentos"] = [buscar_equipamento_por_id(conn, e["id"], visao=visao) or e
                                    for e in registro["equipamentos"]]
        verificacoes = [v for e in registro["equipamentos"] for v in e["verificacoes_metrologicas"]]
        registro["dados_por_fonte"] = _dados_por_fonte(
            conn, pid, visao, [v["fonte_registro_id"] for v in verificacoes])
        registro["fontes"] = _unicos(registro["fontes"] + [v["fonte"] for v in verificacoes if v["fonte"]])
        # Complementos sao inferencias da base, nao publicacoes da fonte do envio.
        # O detalhe expoe a origem separadamente, sem reescrever o bruto.
        try:
            alteracoes = dbmod.query_all(
                conn, "SELECT campos_json FROM RADAR_ALTERACAO WHERE ponto_id=? "
                "AND tipo='editado' ORDER BY id DESC", (int(registro["id"][2:]),))
        except sqlite3.OperationalError:
            alteracoes = []
        for alteracao in alteracoes:
            try:
                complemento = json.loads(alteracao["campos_json"] or "{}").get("complemento_proximidade")
            except (ValueError, TypeError, AttributeError):
                continue
            if complemento:
                registro["proveniencia_campos"]["complemento_proximidade"] = complemento
                break
    return registro


def listar_fontes(conn):
    out = []
    for f in dbmod.query_all(
            conn, "SELECT f.id, f.nome, f.esfera, f.situacao, "
            "f.url_institucional, f.periodicidade_declarada, "
            "o.nome AS organizacao, n.codigo AS natureza "
            "FROM FONTE f JOIN ORGANIZACAO o ON o.id=f.organizacao_id "
            "LEFT JOIN NATUREZA_FONTE n ON n.id=f.natureza_id "
            "ORDER BY f.nome"):
        recursos = []
        for rq in dbmod.query_all(
                conn, "SELECT id, nome, url_recurso, formato_origem, "
                "status_integracao FROM RECURSO_FONTE WHERE fonte_id=?",
                (f["id"],)):
            recursos.append({"id": "RF-%d" % rq["id"], "nome": rq["nome"],
                             "url_recurso": rq["url_recurso"],
                             "formato_origem": rq["formato_origem"],
                             "status_integracao": rq["status_integracao"]})
        out.append({
            "id": "S-%d" % f["id"], "nome": f["nome"], "esfera": f["esfera"],
            "natureza": f["natureza"], "organizacao": f["organizacao"],
            "url_institucional": f["url_institucional"],
            "situacao": f["situacao"],
            "periodicidade_declarada": f["periodicidade_declarada"],
            "recursos": recursos,
        })
    return out


##-- BUNDITA DE URSO #{1} -- As contagens publicas ainda somavam aliases como entidades distintas. ##
def status_base(conn):
    snap = dbmod.query_one(
        conn, "SELECT id, identificador_versao, publicado_em, status "
        "FROM SNAPSHOT_PUBLICADO ORDER BY publicado_em DESC LIMIT 1")
    total_pontos = dbmod.scalar(conn, "SELECT count(*) FROM PONTO_FISCALIZACAO")
    total_equip = dbmod.scalar(conn, "SELECT count(*) FROM EQUIPAMENTO")
    visao = VisaoCanonica(conn)
    total_pontos -= len(visao.aliases("ponto"))
    total_equip -= len(visao.aliases("equipamento"))
    total_fontes = dbmod.scalar(conn, "SELECT count(*) FROM FONTE")
    return {
        "snapshot_id": (snap["identificador_versao"] if snap else None),
        "publicado_em": (snap["publicado_em"] if snap else None),
        "total_pontos": total_pontos,
        "total_equipamentos": total_equip,
        "total_fontes": total_fontes,
        "fontes": listar_fontes(conn),
    }


# =========================================================================
# /api/v1/trechos — TRECHO ELEGIVEL PARA RADAR PORTATIL (spec 11.5)
# =========================================================================
# NAO e radar nem operacao confirmada: indica apenas que PODE haver
# fiscalizacao. `radar_instalado_confirmado` NUNCA e inferido como True.
_TRECHO_SQL = """
SELECT t.id AS trecho_id, t.km_inicio AS km_inicio, t.km_fim AS km_fim,
       t.criterio_inclusao AS criterio_inclusao,
       t.vigencia_inicio AS vigencia_inicio, t.vigencia_fim AS vigencia_fim,
       t.situacao AS situacao, t.registro_fonte_id AS registro_fonte_id,
       v.codigo AS via_codigo, v.nome AS via_nome,
       s.codigo AS sentido
FROM TRECHO_ELEGIVEL t
LEFT JOIN VIA v ON v.id = t.via_id
LEFT JOIN SENTIDO s ON s.id = t.sentido_id
"""


def _filtros_trecho(filtros):
    clauses, params = [], []
    if filtros.get("uf"):
        clauses.append(
            "t.id IN (SELECT tm.trecho_id FROM TRECHO_MUNICIPIO tm "
            "JOIN MUNICIPIO m ON m.codigo_ibge=tm.municipio_id "
            "WHERE m.uf_sigla = ?)")
        params.append(filtros["uf"].upper())
    if filtros.get("municipio_ibge"):
        clauses.append(
            "t.id IN (SELECT trecho_id FROM TRECHO_MUNICIPIO "
            "WHERE municipio_id = ?)")
        params.append(filtros["municipio_ibge"])
    if filtros.get("rodovia"):
        clauses.append("v.codigo = ?")
        params.append(filtros["rodovia"])
    if filtros.get("sentido"):
        clauses.append("s.codigo = ?")
        params.append(filtros["sentido"])
    return clauses, params


def _clausula_bbox_vertices(bb):
    """Clausula de bounding box sobre TRECHO_VERTICE (spec 9.1)."""
    if bb.get("cruza_antimeridiano"):
        cond = ("vp.latitude BETWEEN ? AND ? AND "
                "(vp.longitude >= ? OR vp.longitude <= ?)")
        params = [bb["lat_min"], bb["lat_max"],
                  geo.normaliza_longitude(bb["lon_min"]),
                  geo.normaliza_longitude(bb["lon_max"])]
    elif bb.get("inclui_polos"):
        cond = "vp.latitude BETWEEN ? AND ?"
        params = [bb["lat_min"], bb["lat_max"]]
    else:
        cond = ("vp.latitude BETWEEN ? AND ? AND vp.longitude BETWEEN ? AND ?")
        params = [bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"]]
    return ("t.id IN (SELECT tv.trecho_id FROM TRECHO_VERTICE tv "
            "JOIN POSICAO_GEOGRAFICA vp ON vp.id=tv.posicao_id WHERE %s)" % cond,
            params)


def _dist_trecho(lat, lon, vertices):
    """Menor distancia Haversine aos vertices; None se nao houver geometria.

    Spec 9.6: so mede distancia a segmento quando existe tracado confiavel;
    nao estima distancia ao longo da rodovia a partir dos kms.
    """
    if not vertices:
        return None
    return min(geo.haversine_m(lat, lon, v["latitude"], v["longitude"])
               for v in vertices)


def _offset_cursor(cursor):
    try:
        return max(0, int(cursor))
    except (TypeError, ValueError):
        return 0


def montar_trecho(conn, r):
    tid = r["trecho_id"]
    municipios = []
    uf = None
    for m in dbmod.query_all(
            conn, "SELECT m.codigo_ibge, m.nome, m.uf_sigla "
            "FROM TRECHO_MUNICIPIO tm JOIN MUNICIPIO m "
            "ON m.codigo_ibge=tm.municipio_id WHERE tm.trecho_id=? "
            "ORDER BY m.nome", (tid,)):
        municipios.append({"codigo_ibge": m["codigo_ibge"], "nome": m["nome"],
                           "uf": m["uf_sigla"]})
        uf = uf or m["uf_sigla"]
    vertices = []
    for v in dbmod.query_all(
            conn, "SELECT p.latitude, p.longitude FROM TRECHO_VERTICE tv "
            "JOIN POSICAO_GEOGRAFICA p ON p.id=tv.posicao_id "
            "WHERE tv.trecho_id=? ORDER BY tv.ordem", (tid,)):
        vertices.append({"latitude": v["latitude"],
                         "longitude": v["longitude"]})
    documentos = []
    for d in dbmod.query_all(
            conn, "SELECT d.id, d.url FROM DOCUMENTO_TRECHO dt "
            "JOIN DOCUMENTO d ON d.id=dt.documento_id WHERE dt.trecho_id=?",
            (tid,)):
        documentos.append({"id": "D-%d" % d["id"], "url": d["url"]})
    return {
        "id": "T-%d" % tid,
        "tipo_registro": "trecho_elegivel",
        "via": r["via_codigo"],
        "via_nome": r["via_nome"],
        "uf": uf,
        "municipios": municipios,
        "km_inicio": r["km_inicio"],
        "km_fim": r["km_fim"],
        "sentido": r["sentido"],
        "situacao": r["situacao"],
        "vertices": vertices,
        "geometria_confirmada": bool(vertices),
        "criterio_inclusao": r["criterio_inclusao"],
        "vigencia_inicio": r["vigencia_inicio"],
        "vigencia_fim": r["vigencia_fim"],
        "documento_url": (documentos[0]["url"] if documentos else None),
        "documentos": documentos,
        "fontes": _fontes_por_registro(conn, r["registro_fonte_id"]),
        "indicador": "pode_haver_fiscalizacao",
        "radar_instalado_confirmado": None,
    }


def buscar_trechos(conn, lat=None, lon=None, raio=None, filtros=None,
                   limite=100, cursor=None):
    """Trechos elegiveis. Localizacao (lat/lon/raio) e opcional; quando
    informada, considera apenas trechos com vertice dentro do raio (sem
    inventar geometria: trecho sem vertices nunca e posicionado)."""
    filtros = filtros or {}
    clauses, params = _filtros_trecho(filtros)
    usar_loc = lat is not None and lon is not None and raio is not None
    bbox_params = []
    if usar_loc:
        bb = geo.bounding_box(lat, lon, raio)
        cond, bbox_params = _clausula_bbox_vertices(bb)
        clauses.append(cond)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(conn, _TRECHO_SQL + where, params + bbox_params)

    recs = []
    for r in rows:
        trecho = montar_trecho(conn, r)
        if usar_loc:
            dist = _dist_trecho(lat, lon, trecho["vertices"])
            if dist is None or dist > raio:
                continue
        recs.append(trecho)
    recs.sort(key=lambda t: t["id"])

    total = len(recs)
    offset = _offset_cursor(cursor)
    recorte = recs[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)
    return recorte, {"total_trechos": total, "retornados": len(recorte),
                     "proximo_cursor": proximo}


# =========================================================================
# /api/v1/operacoes — OPERACAO DE FISCALIZACAO (spec 11.4)
# =========================================================================
# Somente operacoes reais publicadas por fonte. TRECHO ELEGIVEL nunca vira
# operacao ficticia. Sem data/hora oficial a operacao vem com inicio_em NULL
# e evidencia_operacao='desconhecida' (nao se inventa horario).
_OPERACAO_SQL = """
SELECT o.id AS operacao_id, o.km AS km, o.descricao AS descricao,
       o.inicio_em AS inicio_em, o.fim_em AS fim_em,
       o.fuso_original AS fuso_original, o.publicado_em AS publicado_em,
       o.ponto_id AS ponto_id, o.trecho_id AS trecho_id,
       o.registro_fonte_id AS registro_fonte_id,
       pos.latitude AS latitude, pos.longitude AS longitude,
       v.codigo AS via_codigo, v.nome AS via_nome,
       m.nome AS municipio, m.uf_sigla AS uf,
       mf.codigo AS modalidade, so.codigo AS situacao_operacao,
       org.nome AS orgao_responsavel
FROM OPERACAO_FISCALIZACAO o
LEFT JOIN POSICAO_GEOGRAFICA pos ON pos.id = o.posicao_id
LEFT JOIN VIA v ON v.id = o.via_id
LEFT JOIN MUNICIPIO m ON m.codigo_ibge = o.municipio_id
LEFT JOIN MODALIDADE_FISCALIZACAO mf ON mf.id = o.modalidade_id
LEFT JOIN SITUACAO_OPERACAO so ON so.id = o.situacao_operacao_id
LEFT JOIN ORGANIZACAO org ON org.id = o.organizacao_id
"""


def _fiscalizacao_pontual(modalidade):
    if modalidade is None:
        return None
    if modalidade == "pontual":
        return True
    if modalidade == "desconhecida":
        return None
    return False


def montar_operacao(conn, r):
    oid = r["operacao_id"]
    equipamentos_ids = [
        "E-%d" % e["equipamento_id"] for e in dbmod.query_all(
            conn, "SELECT equipamento_id FROM OPERACAO_EQUIPAMENTO "
            "WHERE operacao_id=? ORDER BY equipamento_id", (oid,))]
    faixas_ids = [
        "F-%d" % f["faixa_id"] for f in dbmod.query_all(
            conn, "SELECT faixa_id FROM OPERACAO_FAIXA WHERE operacao_id=? "
            "ORDER BY faixa_id", (oid,))]
    recorrencias = []
    for rc in dbmod.query_all(
            conn, "SELECT id, regra_repeticao, fuso_horario, data_inicio, "
            "data_fim FROM OPERACAO_RECORRENCIA WHERE operacao_id=? "
            "ORDER BY id", (oid,)):
        dias = []
        for d in dbmod.query_all(
                conn, "SELECT dia_semana, hora_inicio, hora_fim "
                "FROM RECORRENCIA_DIA WHERE recorrencia_id=? "
                "ORDER BY dia_semana, hora_inicio", (rc["id"],)):
            dias.append({"dia_semana": d["dia_semana"],
                         "hora_inicio": d["hora_inicio"],
                         "hora_fim": d["hora_fim"]})
        recorrencias.append({"regra": rc["regra_repeticao"],
                             "fuso": rc["fuso_horario"],
                             "inicio": rc["data_inicio"],
                             "fim": rc["data_fim"], "dias": dias})
    docs = dbmod.query_all(
        conn, "SELECT d.url FROM DOCUMENTO_OPERACAO do "
        "JOIN DOCUMENTO d ON d.id=do.documento_id WHERE do.operacao_id=? "
        "ORDER BY d.id", (oid,))
    if r["inicio_em"]:
        evidencia = "confirmada"
    elif r["publicado_em"]:
        evidencia = "planejada"
    else:
        evidencia = "desconhecida"
    return {
        "id": "O-%d" % oid,
        "tipo_registro": "operacao_fiscalizacao",
        "modalidade": r["modalidade"],
        "fiscalizacao_pontual": _fiscalizacao_pontual(r["modalidade"]),
        "situacao_operacao": r["situacao_operacao"],
        "tipo_operacao_original": r["descricao"],
        "inicio_em": r["inicio_em"],
        "fim_em": r["fim_em"],
        "fuso_original": r["fuso_original"],
        "publicado_em": r["publicado_em"],
        "recorrencias": recorrencias,
        "ponto_id": ("P-%d" % r["ponto_id"]) if r["ponto_id"] else None,
        "trecho_id": ("T-%d" % r["trecho_id"]) if r["trecho_id"] else None,
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "via": r["via_codigo"],
        "via_nome": r["via_nome"],
        "km": r["km"],
        "municipio": r["municipio"],
        "uf": r["uf"],
        "orgao_responsavel": r["orgao_responsavel"],
        "equipamentos_ids": equipamentos_ids,
        "faixas_ids": faixas_ids,
        "documento_url": (docs[0]["url"] if docs else None),
        "fontes": _fontes_por_registro(conn, r["registro_fonte_id"]),
        "evidencia_operacao": evidencia,
    }


def _filtros_operacao(filtros):
    clauses, params = [], []
    if filtros.get("uf"):
        clauses.append("m.uf_sigla = ?")
        params.append(filtros["uf"].upper())
    if filtros.get("municipio_ibge"):
        clauses.append("m.codigo_ibge = ?")
        params.append(filtros["municipio_ibge"])
    if filtros.get("rodovia"):
        clauses.append("v.codigo = ?")
        params.append(filtros["rodovia"])
    if filtros.get("modalidade"):
        clauses.append("mf.codigo = ?")
        params.append(filtros["modalidade"])
    if filtros.get("em"):
        clauses.append("o.inicio_em IS NOT NULL AND o.inicio_em <= ? AND "
                       "(o.fim_em IS NULL OR o.fim_em >= ?)")
        params.append(filtros["em"])
        params.append(filtros["em"])
    return clauses, params


def _clausula_bbox_posicao(bb):
    """Clausula de bounding box sobre POSICAO_GEOGRAFICA (operacoes)."""
    if bb.get("cruza_antimeridiano"):
        cond = ("pos.latitude BETWEEN ? AND ? AND "
                "(pos.longitude >= ? OR pos.longitude <= ?)")
        params = [bb["lat_min"], bb["lat_max"],
                  geo.normaliza_longitude(bb["lon_min"]),
                  geo.normaliza_longitude(bb["lon_max"])]
    elif bb.get("inclui_polos"):
        cond = "pos.latitude BETWEEN ? AND ?"
        params = [bb["lat_min"], bb["lat_max"]]
    else:
        cond = ("pos.latitude BETWEEN ? AND ? AND pos.longitude BETWEEN ? AND ?")
        params = [bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"]]
    return cond, params


def buscar_operacoes(conn, lat=None, lon=None, raio=None, filtros=None,
                     limite=100, cursor=None):
    """Operacoes de fiscalizacao publicadas. Com lat/lon/raio, considera
    apenas operacoes com posicao valida dentro do raio (Haversine)."""
    filtros = filtros or {}
    clauses, params = _filtros_operacao(filtros)
    usar_loc = lat is not None and lon is not None and raio is not None
    bbox_params = []
    if usar_loc:
        bb = geo.bounding_box(lat, lon, raio)
        cond, bbox_params = _clausula_bbox_posicao(bb)
        clauses.append("pos.id IS NOT NULL")
        clauses.append(cond)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(conn, _OPERACAO_SQL + where, params + bbox_params)

    recs = []
    for r in rows:
        if usar_loc:
            if r["latitude"] is None or r["longitude"] is None:
                continue
            if geo.haversine_m(lat, lon, r["latitude"], r["longitude"]) > raio:
                continue
        recs.append(montar_operacao(conn, r))
    recs.sort(key=lambda o: o["id"])

    total = len(recs)
    offset = _offset_cursor(cursor)
    recorte = recs[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)
    return recorte, {"total_operacoes": total, "retornados": len(recorte),
                     "proximo_cursor": proximo}


# =========================================================================
# /api/v1/equipamentos/{id} — EQUIPAMENTO FISICO (spec 11.3)
# =========================================================================
_EQUIP_SQL = """
SELECT e.id AS equipamento_id, e.numero_serie AS numero_serie,
       e.ano_fabricacao AS ano_fabricacao, e.observacoes AS observacoes,
       tr.codigo AS tipo_radar,
       mo.nome_modelo AS nome_modelo,
       mo.registro_aprovacao_inmetro AS registro_aprovacao,
       mo.portaria_aprovacao_modelo AS portaria_aprovacao,
       tm.codigo AS tecnologia_medicao,
       fa.nome AS fabricante
FROM EQUIPAMENTO e
JOIN TIPO_RADAR tr ON tr.id = e.tipo_radar_id
LEFT JOIN MODELO_EQUIPAMENTO mo ON mo.id = e.modelo_id
LEFT JOIN TECNOLOGIA_MEDICAO tm ON tm.id = mo.tecnologia_id
LEFT JOIN ORGANIZACAO fa ON fa.id = mo.fabricante_id
WHERE e.id = ?
"""


def _situacao_metrologica(validade_ate):
    if not validade_ate:
        return "desconhecida"
    hoje = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        vencida = str(validade_ate)[:10] < hoje
    except (TypeError, ValueError):
        return "desconhecida"
    return "vencida" if vencida else "valida"


def _montar_equipamento_original(conn, r):
    eid = r["equipamento_id"]
    instalacoes = []
    funcao = None
    for i in dbmod.query_all(
            conn, "SELECT i.id, i.ponto_id, i.inicio_em, i.fim_em, "
            "i.data_inicio_autuacao, i.data_inicio_educativo, "
            "so.codigo AS situacao, fe.descricao AS funcao "
            "FROM INSTALACAO i "
            "LEFT JOIN SITUACAO_OPERACIONAL so "
            "ON so.id=i.situacao_operacional_id "
            "LEFT JOIN FUNCAO_EQUIPAMENTO fe ON fe.id=i.funcao_equipamento_id "
            "WHERE i.equipamento_id=? ORDER BY i.id", (eid,)):
        faixas_ids = [
            "F-%d" % f["faixa_id"] for f in dbmod.query_all(
                conn, "SELECT faixa_id FROM INSTALACAO_FAIXA "
                "WHERE instalacao_id=? ORDER BY faixa_id", (i["id"],))]
        instalacoes.append({
            "id": "I-%d" % i["id"],
            "ponto_id": ("P-%d" % i["ponto_id"]) if i["ponto_id"] else None,
            "inicio_em": i["inicio_em"], "fim_em": i["fim_em"],
            "situacao": i["situacao"], "faixas_ids": faixas_ids,
            "data_inicio_educativo": i["data_inicio_educativo"],
            "data_inicio_autuacao": i["data_inicio_autuacao"],
        })
        funcao = funcao or i["funcao"]

    verificacoes = []
    for v in dbmod.query_all(
            conn, "SELECT v.id, tv.codigo AS tipo, v.data_verificacao, "
            "v.validade_ate, rv.codigo AS resultado, v.numero_certificado, "
            "v.norma_aplicada, v.observacoes, v.registro_fonte_id, org.nome AS orgao "
            "FROM VERIFICACAO_METROLOGICA v "
            "LEFT JOIN TIPO_VERIFICACAO tv ON tv.id=v.tipo_verificacao_id "
            "LEFT JOIN RESULTADO_VERIFICACAO rv ON rv.id=v.resultado_id "
            "LEFT JOIN ORGANIZACAO org ON org.id=v.orgao_executor_id "
            "WHERE v.equipamento_id=? ORDER BY v.id", (eid,)):
        verificacoes.append({
            "id": "V-%d" % v["id"],
            "tipo_verificacao": v["tipo"],
            "data_verificacao": v["data_verificacao"],
            "validade_ate": v["validade_ate"],
            "resultado": v["resultado"],
            "numero_certificado": v["numero_certificado"],
            "certificado_url": None,
            "orgao_executor": v["orgao"],
            "norma_aplicada": v["norma_aplicada"],
            "situacao_metrologica_derivada": _situacao_metrologica(
                v["validade_ate"]),
            "documentos": [],
            "fonte_registro_id": v["registro_fonte_id"],
            "fonte": (_fontes_por_registro(conn, v["registro_fonte_id"]) or [None])[0],
            "observacoes": v["observacoes"],
        })

    identificadores = []
    for ident in dbmod.query_all(
            conn, "SELECT ex.valor, ti.codigo AS tipo, f.nome AS fonte, "
            "ie.vigencia_inicio, ie.vigencia_fim "
            "FROM IDENTIFICADOR_EQUIPAMENTO ie "
            "JOIN IDENTIFICADOR_EXTERNO ex ON ex.id=ie.identificador_id "
            "JOIN TIPO_IDENTIFICADOR ti ON ti.id=ex.tipo_identificador_id "
            "JOIN FONTE f ON f.id=ex.fonte_id "
            "WHERE ie.equipamento_id=? ORDER BY ex.id", (eid,)):
        identificadores.append({
            "fonte": ident["fonte"], "tipo": ident["tipo"],
            "valor": ident["valor"],
            "vigencia": {"inicio": ident["vigencia_inicio"],
                         "fim": ident["vigencia_fim"]},
        })

    observacoes = r["observacoes"] if "observacoes" in r.keys() else None
    return {
        "id": "E-%d" % eid,
        "tipo_registro": "equipamento",
        "tipo_radar": r["tipo_radar"],
        "tipo_radar_original": None,
        "funcao_equipamento": funcao,
        "sigla_equipamento_original": None,
        "fabricante": r["fabricante"],
        "modelo": r["nome_modelo"],
        "tecnologia_medicao": r["tecnologia_medicao"],
        "numero_serie": r["numero_serie"],
        "ano_fabricacao": r["ano_fabricacao"],
        "registro_aprovacao_modelo": r["registro_aprovacao"],
        "portaria_aprovacao_modelo": r["portaria_aprovacao"],
        "identificadores_oficiais": identificadores,
        "instalacoes": instalacoes,
        "verificacoes_metrologicas": verificacoes,
        "proprietario": None,
        "mantenedor": None,
        "ultima_manutencao": None,
        "observacoes": observacoes,
    }


##-- BUNDITA DE URSO #{1} -- Um instrumento consolidado precisa manter todas as instalacoes e verificacoes. ##
def montar_equipamento(conn, r, visao=None):
    visao = visao or VisaoCanonica(conn)
    eid = visao.canonico("equipamento", r["equipamento_id"])
    if eid != r["equipamento_id"]:
        r = dbmod.query_one(conn, _EQUIP_SQL, (eid,))
    reg = _montar_equipamento_original(conn, r)
    membros = visao.membros("equipamento", eid)
    for outro in membros:
        if outro == eid:
            continue
        row = dbmod.query_one(conn, _EQUIP_SQL, (outro,))
        original = _montar_equipamento_original(conn, row)
        for campo in ("instalacoes", "verificacoes_metrologicas", "identificadores_oficiais"):
            reg[campo].extend(original[campo])
    from .metrologia import equipamentos_relacionados
    relacionados = {}
    for membro in membros:
        for outro, registros in equipamentos_relacionados(conn, membro, visao).items():
            if outro not in membros:
                relacionados.setdefault(outro, set()).update(registros)
    for outro in sorted(relacionados):
        row = dbmod.query_one(conn, _EQUIP_SQL, (outro,))
        original = _montar_equipamento_original(conn, row)
        # A juncao e do instrumento: nao copia GPS, limite da via ou instalacoes.
        for v in original["verificacoes_metrologicas"]:
            if v["fonte_registro_id"] in relacionados[outro]:
                v["equipamento_origem_id"] = original["id"]
                reg["verificacoes_metrologicas"].append(v)
    if relacionados:
        reg["juncao_metrologica"] = {
            "criterio": "serie_exata_tipo_e_municipio",
            "equipamentos_origem": ["E-%d" % i for i in sorted(relacionados)],
        }
    for campo in ("instalacoes", "identificadores_oficiais"):
        reg[campo] = _unicos(reg[campo])
    for instalacao in reg["instalacoes"]:
        if instalacao["ponto_id"]:
            instalacao["ponto_id"] = "P-%d" % visao.canonico("ponto", int(instalacao["ponto_id"][2:]))
    ##-- BUNDITA DE URSO #{1} -- Certificado sem data ou executor nao basta para eliminar uma verificacao do historico. ##
    vistos, verificacoes = {}, []
    for verificacao in reg["verificacoes_metrologicas"]:
        certificado = (verificacao["numero_certificado"] and verificacao["data_verificacao"]
                       and verificacao["orgao_executor"])
        chave = tuple(verificacao.get(k) for k in
                      ("numero_certificado", "data_verificacao", "tipo_verificacao", "orgao_executor",
                       "resultado", "validade_ate", "norma_aplicada")) if certificado else verificacao["id"]
        if chave in vistos:
            vistos[chave].setdefault("aliases", []).append(verificacao["id"])
        else:
            vistos[chave] = verificacao
            verificacoes.append(verificacao)
    reg["verificacoes_metrologicas"] = verificacoes
    if len(membros) > 1:
        reg["aliases"] = ["E-%d" % i for i in membros if i != eid]
    return reg


##-- BUNDITA DE URSO #{1} -- IDs de equipamento reconciliados nao eram resolvidos nas consultas. ##
def buscar_equipamento_por_id(conn, ident, visao=None):
    try:
        eid = int(str(ident).upper().replace("E-", ""))
    except (TypeError, ValueError):
        return None
    visao = visao or VisaoCanonica(conn)
    eid = visao.canonico("equipamento", eid)
    r = dbmod.query_one(conn, _EQUIP_SQL, (eid,))
    if r is None:
        return None
    return montar_equipamento(conn, r, visao=visao)


# =========================================================================
# /api/v1/fontes/{id} — detalhe de UMA fonte
# =========================================================================
def buscar_fonte_por_id(conn, ident):
    try:
        fid = int(str(ident).upper().replace("S-", ""))
    except (TypeError, ValueError):
        return None
    for f in listar_fontes(conn):
        if f["id"] == "S-%d" % fid:
            return f
    return None


# =========================================================================
# /api/v1/atualizacoes — historico de execucoes/snapshots por fonte
# =========================================================================
_EXEC_SQL = """
SELECT ac.id AS execucao_id, ac.iniciada_em, ac.terminada_em, ac.status,
       ac.http_status, ac.tentativas, ac.linhas_recebidas, ac.linhas_validas,
       ac.linhas_rejeitadas, ac.registros_criados, ac.registros_alterados,
       ac.erro_codigo, ac.erro_detalhe, ac.artefato_id,
       rf.id AS recurso_id, rf.nome AS recurso_nome, rf.url_recurso,
       f.id AS fonte_id, f.nome AS fonte_nome, f.esfera AS fonte_esfera,
       a.hash_sha256 AS artefato_hash
FROM EXECUCAO_COLETA ac
JOIN RECURSO_FONTE rf ON rf.id = ac.recurso_id
JOIN FONTE f ON f.id = rf.fonte_id
LEFT JOIN ARTEFATO_COLETA a ON a.id = ac.artefato_id
"""


def montar_execucao(conn, r):
    return {
        "id": "X-%d" % r["execucao_id"],
        "tipo_registro": "execucao_coleta",
        "fonte": r["fonte_nome"],
        "fonte_id": "S-%d" % r["fonte_id"],
        "esfera": r["fonte_esfera"],
        "recurso": r["recurso_nome"],
        "recurso_id": "RF-%d" % r["recurso_id"],
        "recurso_url": r["url_recurso"],
        "iniciada_em": r["iniciada_em"],
        "terminada_em": r["terminada_em"],
        "status": r["status"],
        "http_status": r["http_status"],
        "tentativas": r["tentativas"],
        "linhas_recebidas": r["linhas_recebidas"],
        "linhas_validas": r["linhas_validas"],
        "linhas_rejeitadas": r["linhas_rejeitadas"],
        "registros_criados": r["registros_criados"],
        "registros_alterados": r["registros_alterados"],
        "erro_codigo": r["erro_codigo"],
        "erro_detalhe": r["erro_detalhe"],
        "artefato_id": (("A-%d" % r["artefato_id"])
                        if r["artefato_id"] else None),
        "artefato_hash": r["artefato_hash"],
    }


def listar_atualizacoes(conn, filtros=None, limite=100, cursor=None):
    """Historico de execucoes de coleta (mais recentes primeiro)."""
    filtros = filtros or {}
    clauses, params = [], []
    if filtros.get("fonte"):
        clauses.append("f.nome = ?")
        params.append(filtros["fonte"])
    if filtros.get("fonte_id"):
        clauses.append("f.id = ?")
        params.append(filtros["fonte_id"])
    if filtros.get("recurso"):
        clauses.append("rf.nome = ?")
        params.append(filtros["recurso"])
    if filtros.get("status"):
        clauses.append("ac.status = ?")
        params.append(filtros["status"])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(
        conn, _EXEC_SQL + where +
        " ORDER BY ac.iniciada_em DESC, ac.id DESC", params)
    total = len(rows)
    offset = _offset_cursor(cursor)
    recorte = rows[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)
    records = [montar_execucao(conn, r) for r in recorte]
    return records, {"total_atualizacoes": total, "retornados": len(records),
                     "proximo_cursor": proximo}


def listar_snapshots(conn, limite=50):
    out = []
    for s in dbmod.query_all(
            conn, "SELECT id, identificador_versao, publicado_em, status, "
            "resumo_validacao, anterior_id FROM SNAPSHOT_PUBLICADO "
            "ORDER BY publicado_em DESC, id DESC LIMIT ?", (limite,)):
        out.append({
            "id": "SN-%d" % s["id"],
            "identificador_versao": s["identificador_versao"],
            "publicado_em": s["publicado_em"],
            "status": s["status"],
            "resumo_validacao": s["resumo_validacao"],
            "anterior_id": (("SN-%d" % s["anterior_id"])
                            if s["anterior_id"] else None),
        })
    return out


# =========================================================================
# /api/v1/trafego — OBSERVACAO AGREGADA DE TRAFEGO
# =========================================================================
# Velocidade de PASSAGEM observada, JAMAIS limite regulamentado da via.
_TRAFEGO_SQL = """
SELECT o.id AS observacao_id, o.ponto_id AS ponto_id,
       o.equipamento_id AS equipamento_id, o.faixa_id AS faixa_id,
       o.instante_observacao AS instante_observacao,
       o.data_observacao AS data_observacao,
       o.velocidade_publicada AS velocidade_publicada,
       o.velocidade_kmh AS velocidade_kmh, o.volume_total AS volume_total,
       o.registro_fonte_id AS registro_fonte_id,
       c.codigo AS categoria, s.codigo AS sentido
FROM OBSERVACAO_TRAFEGO o
LEFT JOIN CATEGORIA_VEICULO c ON c.id = o.categoria_veiculo_id
LEFT JOIN SENTIDO s ON s.id = o.sentido_id
"""


def montar_observacao_trafego(conn, r):
    fontes = _fontes_por_registro(conn, r["registro_fonte_id"])
    return {
        "id": "OT-%d" % r["observacao_id"],
        "tipo_registro": "observacao_trafego",
        "ponto_id": ("P-%d" % r["ponto_id"]) if r["ponto_id"] else None,
        "equipamento_id": (("E-%d" % r["equipamento_id"])
                           if r["equipamento_id"] else None),
        "faixa_id": ("F-%d" % r["faixa_id"]) if r["faixa_id"] else None,
        "categoria_veiculo": r["categoria"],
        "sentido": r["sentido"],
        "data_observacao": r["data_observacao"],
        "instante_observacao": r["instante_observacao"],
        "velocidade_publicada": r["velocidade_publicada"],
        "velocidade_observada_kmh": r["velocidade_kmh"],
        "volume_total": r["volume_total"],
        "fonte": (fontes[0] if fontes else None),
    }


def buscar_trafego(conn, limite=100, ponto_id=None, cursor=None):
    """Observacoes agregadas de trafego (mais recentes primeiro)."""
    clauses, params = [], []
    if ponto_id is not None:
        clauses.append("o.ponto_id = ?")
        params.append(int(ponto_id))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(
        conn, _TRAFEGO_SQL + where + " ORDER BY o.id DESC", params)
    total = len(rows)
    offset = _offset_cursor(cursor)
    recorte = rows[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)
    recs = [montar_observacao_trafego(conn, r) for r in recorte]
    return recs, {"total_observacoes": total, "retornados": len(recs),
                  "proximo_cursor": proximo}


# =========================================================================
# /api/v1/radares/busca — BUSCA CADASTRAL (sem coordenada/raio)
# =========================================================================
# Mesma projecao de /radares. Cobertura parcial: ausencia de resultado NAO
# prova ausencia de fiscalizacao.
##-- BUNDITA DE URSO #{1} -- Busca cadastral tambem precisa consolidar antes de paginar. ##
def buscar_cadastral(conn, filtros=None, limite=100, cursor=None):
    filtros = filtros or {}
    clauses, params = _filtros_extra(filtros, conn)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(conn, _PONTO_SQL + where + " ORDER BY p.id",
                           params)
    visao = VisaoCanonica(conn)
    canonicos = {}
    for row in rows:
        row = _linha_canonica(conn, row, visao)
        if row is not None:
            canonicos[row["ponto_id"]] = row
    rows = [canonicos[pid] for pid in sorted(canonicos)]
    uf_filtro = (filtros.get("uf") or "").upper() or None
    if uf_filtro:
        rows = [r for r in rows if _uf_do_ponto(conn, r) == uf_filtro]
    total = len(rows)
    offset = max(0, _offset_cursor(cursor))
    recorte = rows[offset:offset + limite]
    recs = [montar_registro(conn, r,
             incluir_operacoes=filtros.get("incluir_operacoes", True), visao=visao)
            for r in recorte]
    return recs, {"total_pontos": total, "retornados": len(recs),
                  "proximo_cursor": str(offset + limite) if offset + limite < total else None}
