# -*- coding: utf-8 -*-
"""Consultas read-only sobre o banco local (spec 9, 11, 14).

Duas fases: bounding box em SQL + Haversine na aplicacao (sem PostGIS).
LIMIT so depois do calculo de distancia (spec 9.4).
"""
import datetime
import json

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
            "WHERE vp.ponto_id=? ORDER BY r.id", (pid,)):
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


def _filtros_extra(filtros):
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

    uf_filtro = (filtros.get("uf") or "").upper() or None
    dentro = []
    for r in rows:
        if r["latitude"] is None or r["longitude"] is None:
            continue
        if uf_filtro and _uf_do_ponto(conn, r) != uf_filtro:
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

    incluir_operacoes = filtros.get("incluir_operacoes", True)
    pontual_filtro = filtros.get("fiscalizacao_pontual")
    records = []
    total_equip = 0
    for dist, r in recorte:
        registro = montar_registro(conn, r, distancia_metros=round(dist, 3),
                                   incluir_operacoes=incluir_operacoes)
        if pontual_filtro is not None:
            if registro.get("fiscalizacao_pontual") is None:
                continue                     # desconhecido fica fora
            if bool(registro["fiscalizacao_pontual"]) != bool(pontual_filtro):
                continue
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


def montar_registro(conn, r, distancia_metros=None, incluir_operacoes=True):
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


def operacoes_do_ponto(conn, pid):
    """Operacoes publicadas vinculadas a UM ponto (spec 11.4)."""
    out = []
    for r in dbmod.query_all(conn, _OPERACAO_SQL + " WHERE o.ponto_id = ? "
                             "ORDER BY o.id", (pid,)):
        out.append(montar_operacao(conn, r))
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


def montar_equipamento(conn, r):
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
            "v.norma_aplicada, v.observacoes, org.nome AS orgao "
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
            "fonte": None,
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


def buscar_equipamento_por_id(conn, ident):
    try:
        eid = int(str(ident).upper().replace("E-", ""))
    except (TypeError, ValueError):
        return None
    r = dbmod.query_one(conn, _EQUIP_SQL, (eid,))
    if r is None:
        return None
    return montar_equipamento(conn, r)


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
def buscar_cadastral(conn, filtros=None, limite=100, cursor=None):
    filtros = filtros or {}
    clauses, params = _filtros_extra(filtros)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = dbmod.query_all(conn, _PONTO_SQL + where + " ORDER BY p.id",
                           params)
    uf_filtro = (filtros.get("uf") or "").upper() or None
    if uf_filtro:
        rows = [r for r in rows if _uf_do_ponto(conn, r) == uf_filtro]
    total = len(rows)
    offset = _offset_cursor(cursor)
    recorte = rows[offset:offset + limite]
    proximo = None
    if offset + limite < total:
        proximo = str(offset + limite)
    recs = [montar_registro(
        conn, r,
        incluir_operacoes=filtros.get("incluir_operacoes", True))
        for r in recorte]
    return recs, {"total_pontos": total, "retornados": len(recs),
                  "proximo_cursor": proximo}
