"""Juncao cadastral de verificacoes oficiais entre observacoes do instrumento.

Nao funde pontos nem reescreve instalacoes: a serie publicada, o municipio e
o tipo delimitam a juncao. Fabricante/modelo conhecidos e decisoes explicitas
de separacao continuam prevalecendo sobre coincidencias de serie.
"""
from . import db
from .dedup import normalizar_serie, normalizar_texto, serie_generica


_RELACIONADOS_SQL = """
SELECT DISTINCT e.id, p.id AS ponto_id, e.modelo_id, vm.registro_fonte_id,
       mo.nome_modelo AS modelo_origem, fo.nome AS fabricante_origem,
       me.nome_modelo AS modelo, fe.nome AS fabricante
FROM EQUIPAMENTO origem
JOIN EQUIPAMENTO e ON UPPER(TRIM(e.numero_serie)) = UPPER(TRIM(origem.numero_serie))
                  AND e.tipo_radar_id = origem.tipo_radar_id AND e.id <> origem.id
JOIN INSTALACAO io ON io.equipamento_id = origem.id
JOIN PONTO_FISCALIZACAO po ON po.id = io.ponto_id
JOIN INSTALACAO i ON i.equipamento_id = e.id
JOIN PONTO_FISCALIZACAO p ON p.id = i.ponto_id AND p.municipio_id = po.municipio_id
JOIN VINCULO_REGISTRO_EQUIPAMENTO vo ON vo.equipamento_id = origem.id AND vo.decisao_id IS NULL
JOIN REGISTRO_FONTE ro ON ro.id = vo.registro_id
JOIN ARTEFATO_COLETA ao ON ao.id = ro.artefato_id
JOIN RECURSO_FONTE rfo ON rfo.id = ao.recurso_id
JOIN FONTE f_o ON f_o.id = rfo.fonte_id
JOIN NATUREZA_FONTE no ON no.id = f_o.natureza_id AND no.codigo = 'oficial'
JOIN VERIFICACAO_METROLOGICA vm ON vm.equipamento_id = e.id
JOIN REGISTRO_FONTE r ON r.id = vm.registro_fonte_id
JOIN ARTEFATO_COLETA a ON a.id = r.artefato_id
JOIN RECURSO_FONTE rf ON rf.id = a.recurso_id
JOIN FONTE f ON f.id = rf.fonte_id AND f.id <> f_o.id
JOIN NATUREZA_FONTE n ON n.id = f.natureza_id AND n.codigo = 'oficial'
LEFT JOIN MODELO_EQUIPAMENTO mo ON mo.id = origem.modelo_id
LEFT JOIN ORGANIZACAO fo ON fo.id = mo.fabricante_id
LEFT JOIN MODELO_EQUIPAMENTO me ON me.id = e.modelo_id
LEFT JOIN ORGANIZACAO fe ON fe.id = me.fabricante_id
WHERE origem.id = ?
"""


def equipamentos_relacionados(conn, eid, visao):
    """Equipamento -> registros de verificacao oficiais compativeis."""
    serie = db.scalar(conn, "SELECT numero_serie FROM EQUIPAMENTO WHERE id=?", (eid,))
    normalizada = normalizar_serie(serie)
    if serie_generica(normalizada) or normalizada in ("DESCONHECIDO", "NAOINFORMADO"):
        return {}
    from . import governanca
    clausulas, params = governanca.clausulas_consulta(conn)
    sql = _RELACIONADOS_SQL + (" AND " + " AND ".join(clausulas) if clausulas else "")
    candidatos = db.query_all(conn, sql + " ORDER BY e.id, p.id", [eid] + params)
    if not candidatos:
        return {}
    # Uma colisao de fabricante/modelo torna a serie ambigua neste contexto.
    modelos, fabricantes = set(), set()
    for row in candidatos:
        for chave, conjunto in (("modelo", modelos), ("modelo_origem", modelos),
                                ("fabricante", fabricantes), ("fabricante_origem", fabricantes)):
            valor = normalizar_texto(row[chave])
            if valor and valor != "DESCONHECIDO":
                conjunto.add(valor)
    if len(modelos) > 1 or len(fabricantes) > 1:
        return {}
    membros = set(visao.membros("equipamento", eid))
    relacionados = {}
    for row in candidatos:
        outro = row["id"]
        if outro not in membros and not visao.separados("equipamento", eid, outro):
            relacionados.setdefault(outro, set()).add(row["registro_fonte_id"])
    return relacionados
