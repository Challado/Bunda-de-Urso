# -*- coding: utf-8 -*-
"""Consultas read-only sobre o banco local (spec 9, 11, 14).

Duas fases: bounding box em SQL + Haversine na aplicacao (sem PostGIS).
LIMIT so depois do calculo de distancia (spec 9.4).
"""
from . import db as dbmod
from . import geo

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


def _filtros_extra(filtros):
    clauses = []
    params = []
    if filtros.get("uf"):
        clauses.append("u.sigla = ?")
        params.append(filtros["uf"].upper())
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
    return clauses, params


def buscar_pontos(conn, lat, lon, raio, filtros=None, limite=100, cursor=None):
    """Retorna (records, meta) com pontos dentro do raio, ordenados por
    distancia. `meta` traz total_pontos/total_equipamentos/proximo_cursor."""
    filtros = filtros or {}
    bb = geo.bounding_box(lat, lon, raio)
    bbox_sql, bbox_params = _bbox_clause(
        bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"],
        bb["cruza_antimeridiano"])
    extra, extra_params = _filtros_extra(filtros)
    where = bbox_sql if not extra else bbox_sql + " AND " + " AND ".join(extra)
    sql = _PONTO_SQL + " WHERE " + where
    rows = dbmod.query_all(conn, sql, bbox_params + extra_params)

    dentro = []
    for r in rows:
        if r["latitude"] is None or r["longitude"] is None:
            continue
        dist = geo.haversine_m(lat, lon, r["latitude"], r["longitude"])
        if dist <= raio:
            dentro.append((dist, r))
    dentro.sort(key=lambda t: (t[0], t[1]["ponto_id"]))

    total = len(dentro)
    offset = 0
    if cursor:
        try:
            offset = int(cursor)
        except (TypeError, ValueError):
            offset = 0
    recorte = dentro[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)

    records = []
    total_equip = 0
    for dist, r in recorte:
        registro = montar_registro(conn, r, distancia_metros=round(dist, 3))
        records.append(registro)
        total_equip += len(registro.get("equipamentos") or [])
    return records, {
        "total_pontos": total,
        "total_equipamentos": total_equip,
        "retornados": len(records),
        "proximo_cursor": proximo,
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


def montar_registro(conn, r, distancia_metros=None):
    pid = r["ponto_id"]
    reg = _row_to_base(r, distancia_metros)

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
    reg["operacoes"] = []
    reg["conflitos"] = []
    reg["primeira_observacao"] = None
    reg["ultima_confirmacao"] = None
    reg["ultima_coleta"] = reg["fontes"][0]["coletado_em"] if reg["fontes"] else None
    reg["confianca"] = "nao_avaliada"
    reg["observacoes"] = r["observacoes"]
    reg["proveniencia_campos"] = {}
    return reg


def _derivar_pontual(regimes):
    if not regimes:
        return None
    modalidades = [rg.get("modalidade_fiscalizacao") for rg in regimes]
    if any(m == "pontual" for m in modalidades):
        return True
    if all(m and m != "desconhecida" for m in modalidades):
        return False
    return None


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
        out.append({
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
        })
    return out


def buscar_ponto_por_id(conn, pid_str):
    try:
        pid = int(str(pid_str).upper().replace("P-", ""))
    except (TypeError, ValueError):
        return None
    r = dbmod.query_one(conn, _PONTO_SQL + " WHERE p.id = ?", (pid,))
    if r is None:
        return None
    return montar_registro(conn, r)


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


def status_base(conn):
    snap = dbmod.query_one(
        conn, "SELECT id, identificador_versao, publicado_em, status "
        "FROM SNAPSHOT_PUBLICADO ORDER BY publicado_em DESC LIMIT 1")
    total_pontos = dbmod.scalar(conn, "SELECT count(*) FROM PONTO_FISCALIZACAO")
    total_equip = dbmod.scalar(conn, "SELECT count(*) FROM EQUIPAMENTO")
    total_fontes = dbmod.scalar(conn, "SELECT count(*) FROM FONTE")
    return {
        "snapshot_id": (snap["identificador_versao"] if snap else None),
        "publicado_em": (snap["publicado_em"] if snap else None),
        "total_pontos": total_pontos,
        "total_equipamentos": total_equip,
        "total_fontes": total_fontes,
        "fontes": listar_fontes(conn),
    }
