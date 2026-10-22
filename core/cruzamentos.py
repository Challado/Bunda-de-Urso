"""Reconsulta fontes oficiais locais sem mudar a origem da contribuicao.

Chamado pela API, em unidades pequenas. Sugestoes usam a mesma tabela de
correspondencias do cadastro; decisoes anteriores nunca sao reabertas.
"""
from . import config, db, geo, governanca as gov


def _velocidades(conn, pid):
    return {r["codigo"]: r["velocidade_kmh"] for r in conn.execute(
        "SELECT c.codigo, l.velocidade_kmh FROM LIMITE_VELOCIDADE l "
        "LEFT JOIN CATEGORIA_VEICULO c ON c.id=l.categoria_veiculo_id "
        "WHERE l.ponto_id=?", (pid,))}


def evidencia(conn, colaborativo_id, oficial_id):
    """Comparacao legivel; dados ausentes nao se tornam igualdade."""
    atual = gov._resumo_ponto(conn, colaborativo_id)
    oficial = gov._resumo_ponto(conn, oficial_id)
    if atual is None or oficial is None:
        return None
    coordenadas = (atual["latitude"], atual["longitude"], oficial["latitude"], oficial["longitude"])
    distancia = (round(geo.haversine_m(*coordenadas), 3)
                 if all(v is not None for v in coordenadas) else None)
    dentro_raio = distancia is not None and distancia <= config.RAIO_CORRESPONDENCIA_M
    divergencias = []
    for campo, rotulo in (("municipio", "Município"), ("uf", "UF"),
                          ("via", "Rodovia"), ("km", "Quilômetro")):
        a, b = atual[campo], oficial[campo]
        if a is not None and b is not None and a != b:
            divergencias.append("%s: contribuição %s; fonte oficial %s" % (rotulo, a, b))
    va, vb = _velocidades(conn, colaborativo_id), _velocidades(conn, oficial_id)
    for categoria in va.keys() & vb.keys():
        if va[categoria] != vb[categoria]:
            divergencias.append("Velocidade (%s): contribuição %s; fonte oficial %s km/h" %
                                (categoria, va[categoria], vb[categoria]))
    fontes = [dict(r) for r in conn.execute(
        "SELECT DISTINCT f.nome, rf.url_recurso AS url FROM VINCULO_REGISTRO_PONTO vp "
        "JOIN REGISTRO_FONTE r ON r.id=vp.registro_id "
        "JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id "
        "JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id "
        "JOIN FONTE f ON f.id=rf.fonte_id "
        "JOIN NATUREZA_FONTE n ON n.id=f.natureza_id "
        "WHERE vp.ponto_id=? AND vp.decisao_id IS NULL AND n.codigo='oficial' "
        "ORDER BY f.nome", (oficial_id,))]
    return {"id": oficial["id"], "distancia_metros": distancia,
            "municipio": oficial["municipio"], "uf": oficial["uf"],
            "via": oficial["via"], "km": oficial["km"],
            "velocidades": vb, "fontes": fontes, "divergencias": divergencias,
            "dentro_raio": dentro_raio,
            "disponivel": dentro_raio and bool(fontes) and oficial["removido_em"] is None
            and oficial["verificacao_status"] != "desabilitado"}


def cruzar(conn, ponto_id, ctx, ip=None):
    gov.garantir_esquema(conn)
    ponto = gov._resumo_ponto(conn, ponto_id)
    if ponto is None:
        raise gov.GovernancaError(404, "ponto_nao_encontrado", "Radar não encontrado.")
    if (ponto["removido_em"] or ponto["verificacao_status"] == "desabilitado"
            or ponto["procedencia"] != "colaborativo"):
        raise gov.GovernancaError(409, "radar_nao_elegivel",
                                 "Escolha uma contribuição ativa, verificada ou não.")
    raio = config.RAIO_CORRESPONDENCIA_M
    lat, lon = ponto["latitude"], ponto["longitude"]
    candidatos = [] if lat is None or lon is None else gov._oficiais_proximos(conn, lat, lon, raio)
    resultado = {"id": ponto["id"], "raio_metros": raio, "novas_correspondencias": 0,
                 "status": "sem_coordenadas" if lat is None or lon is None else "sem_correspondencias",
                 "candidatos": []}
    for candidato in candidatos:
        oid = candidato["ponto_id"]
        if oid == ponto_id:
            continue
        # O esquema legado chama a sugestao pendente de "corroborado";
        # isso nao verifica o cadastro nem confirma a identidade do aparelho.
        nova = gov._inserir_correspondencia(conn, ponto_id, oid,
                                            candidato["distancia_metros"], "corroborado")
        resultado["novas_correspondencias"] += int(nova is not None)
        vinculo = conn.execute(
            "SELECT id, status, resolvido_em FROM CORRESPONDENCIA_PONTO "
            "WHERE ponto_colaborativo_id=? AND ponto_oficial_id=?", (ponto_id, oid)).fetchone()
        # A distancia publicada no painel deve refletir as coordenadas atuais.
        if not vinculo["resolvido_em"]:
            conn.execute("UPDATE CORRESPONDENCIA_PONTO SET distancia_metros=? WHERE id=?",
                         (candidato["distancia_metros"], vinculo["id"]))
        item = evidencia(conn, ponto_id, oid)
        item.update(correspondencia_id=vinculo["id"], status=vinculo["status"],
                    resolvido_em=vinculo["resolvido_em"])
        resultado["candidatos"].append(item)
    if resultado["candidatos"]:
        resultado["status"] = "revisar"
    gov.registrar_alteracao(conn, ponto_id, ctx, "editado",
                           motivo="Cruzamento com fontes oficiais; cadastro e verificação preservados",
                           campos={"cruzamento_oficial": resultado}, ip=ip)
    return resultado


def cruzar_lote(conn, dados, ctx, ip=None):
    """Paginacao por ID com teto fixo: nao perde registros se a fila mudar."""
    gov.garantir_esquema(conn)
    if not isinstance(dados, dict) or set(dados) - {"cursor", "ate_id", "limite"}:
        raise gov.GovernancaError(422, "parametro_invalido", "Envie cursor, ate_id e limite, se necessários.")
    for chave in ("cursor", "ate_id", "limite"):
        if chave in dados and (type(dados[chave]) is not int or not 0 <= dados[chave] <= 2**63 - 1):
            raise gov.GovernancaError(422, "parametro_invalido", "%s deve ser inteiro não negativo." % chave)
    limite = dados.get("limite", 20)
    if not 1 <= limite <= 20:
        raise gov.GovernancaError(422, "limite_invalido", "O limite deve ser de 1 a 20.")
    cursor = dados.get("cursor", 0)
    teto = dados.get("ate_id")
    if teto is None:
        teto = db.scalar(conn, "SELECT COALESCE(MAX(id),0) FROM PONTO_FISCALIZACAO")
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM PONTO_FISCALIZACAO WHERE id>? AND id<=? "
        "AND procedencia='colaborativo' AND removido_em IS NULL "
        "AND (verificacao_status IS NULL OR verificacao_status<>'desabilitado') "
        "ORDER BY id LIMIT ?", (cursor, teto, limite + 1))]
    resultados = [cruzar(conn, pid, ctx, ip) for pid in ids[:limite]]
    return {"resultados": resultados, "processados": len(resultados), "ate_id": teto,
            "proximo_cursor": ids[limite - 1] if len(ids) > limite else None}
