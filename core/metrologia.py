"""Juncao cadastral de verificacoes oficiais entre observacoes do instrumento.

Nao funde pontos nem reescreve instalacoes: a serie publicada, o municipio e
o tipo delimitam a juncao. Fabricante/modelo conhecidos e decisoes explicitas
de separacao continuam prevalecendo sobre coincidencias de serie.
"""
import re

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


def numeros_inmetro(conn, eid):
    """Numero publicado: tolera apenas pontos e zeros de formatacao.

    A leitura do identificador do ponto conserva compatibilidade com cargas
    anteriores que ainda nao ligavam IDENTIFICADOR_EQUIPAMENTO.
    """
    rows = db.query_all(conn, """SELECT ie.valor FROM IDENTIFICADOR_EXTERNO ie
        JOIN TIPO_IDENTIFICADOR ti ON ti.id=ie.tipo_identificador_id AND ti.codigo='numero_inmetro'
        JOIN FONTE f ON f.id=ie.fonte_id
        JOIN NATUREZA_FONTE n ON n.id=f.natureza_id AND n.codigo='oficial'
        WHERE ie.id IN (
            SELECT identificador_id FROM IDENTIFICADOR_EQUIPAMENTO WHERE equipamento_id=?
            UNION SELECT ip.identificador_id FROM IDENTIFICADOR_PONTO ip
            JOIN INSTALACAO i ON i.ponto_id=ip.ponto_id WHERE i.equipamento_id=?)""", (eid, eid))
    numeros = set()
    for row in rows:
        texto = str(row[0] or '').strip()
        if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', texto):
            numero = texto.replace('.', '').lstrip('0')
            if numero:
                numeros.add(numero)
    return numeros


def equipamentos_relacionados(conn, eid, visao):
    """Equipamento -> registros de verificacao oficiais compativeis."""
    serie = db.scalar(conn, "SELECT numero_serie FROM EQUIPAMENTO WHERE id=?", (eid,))
    normalizada = normalizar_serie(serie)
    if not normalizada or normalizada in ("0", "DESCONHECIDO", "NAOINFORMADO"):
        return {}
    origem_inmetro = numeros_inmetro(conn, eid)
    if serie_generica(normalizada) and not (
            normalizada.isdigit() and len(origem_inmetro) == 1):
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
        destino_inmetro = numeros_inmetro(conn, outro)
        # Serie curta so sustenta a juncao com corroboracao do numero oficial.
        # Numeros oficiais divergentes ou ambiguos nunca sao ignorados.
        if (len(origem_inmetro) > 1 or len(destino_inmetro) > 1
                or (origem_inmetro and destino_inmetro and origem_inmetro != destino_inmetro)
                or (normalizada.isdigit() and len(normalizada) <= 4 and
                    (len(origem_inmetro) != 1 or origem_inmetro != destino_inmetro))):
            continue
        if outro not in membros and not visao.separados("equipamento", eid, outro):
            relacionados.setdefault(outro, set()).add(row["registro_fonte_id"])
    return relacionados


def _sentidos(conn, pid):
    return {r[0] for r in conn.execute("SELECT s.codigo FROM FAIXA_FISCALIZACAO f "
        "LEFT JOIN SENTIDO s ON s.id=f.sentido_id WHERE f.ponto_id=?", (pid,))
        if r[0] in ('crescente','decrescente')}


def _velocidades(conn, pid):
    return {r[0] for r in conn.execute("SELECT l.velocidade_kmh FROM LIMITE_VELOCIDADE l "
        "LEFT JOIN FAIXA_FISCALIZACAO f ON f.id=l.faixa_id WHERE l.ponto_id=? OR f.ponto_id=?", (pid,pid))}


def correspondencias_por_local(conn, pid, visao):
    """Sugestao cadastral explicita; nao afirma identidade fisica nem move FKs.

    Exige fonte oficial, marco exato, sentido e velocidade coincidentes.
    Mais de um instrumento compativel permanece ambiguo; nenhuma serie e copiada.
    """
    from . import governanca
    from .equipamentos import modelos_compativeis, serie_valida
    from .identidade import objeto
    res = {'estado':'dados_insuficientes', 'criterio':'municipio_rodovia_km_sentido_velocidade',
           'candidatos':[], 'registros_relacionados':[], 'divergencias':[]}
    origem = db.query_one(conn, 'SELECT * FROM PONTO_FISCALIZACAO WHERE id=?', (pid,))
    if origem is None or any(origem[c] is None for c in ('municipio_id','via_id','km')):
        return res
    oficial = db.scalar(conn, """SELECT 1 FROM VINCULO_REGISTRO_PONTO vp
        JOIN REGISTRO_FONTE r ON r.id=vp.registro_id JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id JOIN FONTE f ON f.id=rf.fonte_id
        JOIN NATUREZA_FONTE n ON n.id=f.natureza_id AND n.codigo='oficial'
        WHERE vp.ponto_id=? AND vp.decisao_id IS NULL LIMIT 1""", (pid,))
    if not oficial:
        return res
    originais = db.query_all(conn, 'SELECT DISTINCT e.* FROM EQUIPAMENTO e JOIN INSTALACAO i ON i.equipamento_id=e.id WHERE i.ponto_id=?', (pid,))
    if not originais or any(serie_valida(e['numero_serie']) for e in originais):
        res['estado'] = 'identificacao_disponivel'
        return res
    sentidos, velocidades = _sentidos(conn,pid), _velocidades(conn,pid)
    if len(sentidos)!=1 or len(velocidades)!=1:
        return res
    clausulas, params = governanca.clausulas_consulta(conn)
    sql = """SELECT DISTINCT p.id AS ponto_id,e.id AS equipamento_id,e.numero_serie,e.modelo_id,e.tipo_radar_id,r.id AS registro_id
        FROM PONTO_FISCALIZACAO p JOIN INSTALACAO i ON i.ponto_id=p.id
        JOIN EQUIPAMENTO e ON e.id=i.equipamento_id
        JOIN VINCULO_REGISTRO_EQUIPAMENTO ve ON ve.equipamento_id=e.id AND ve.decisao_id IS NULL
        JOIN REGISTRO_FONTE r ON r.id=ve.registro_id JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id JOIN FONTE f ON f.id=rf.fonte_id
        JOIN NATUREZA_FONTE n ON n.id=f.natureza_id AND n.codigo='oficial'
        WHERE p.municipio_id=? AND p.via_id=? AND p.km=? AND p.id<>? AND f.nome LIKE 'INMETRO%'
        """ + (' AND '+' AND '.join(clausulas) if clausulas else '')
    rows = db.query_all(conn,sql,[origem['municipio_id'],origem['via_id'],origem['km'],pid]+params)
    candidatos = {}
    desconhecido = db.domain_id(conn,'TIPO_RADAR','desconhecido',criar=False)
    for row in rows:
        eid, outro = visao.canonico('equipamento',row['equipamento_id']),row['ponto_id']
        if (not serie_valida(row['numero_serie']) or _sentidos(conn,outro)!=sentidos
                or _velocidades(conn,outro)!=velocidades or visao.separados('ponto',pid,outro)
                or any(visao.separados('equipamento',e['id'],eid)
                       or (e['tipo_radar_id']!=desconhecido and e['tipo_radar_id']!=row['tipo_radar_id'])
                       or not modelos_compativeis(conn,e['modelo_id'],row['modelo_id']) for e in originais)):
            continue
        c = candidatos.setdefault(eid, {'equipamento_id':'E-%d'%eid,'ponto_id':'P-%d'%outro,
                    'numero_serie':row['numero_serie'],'registros_origem':[],'identidade_fisica_confirmada':False})
        if row['registro_id'] not in c['registros_origem']:
            c['registros_origem'].append(row['registro_id'])
    res['candidatos'] = list(candidatos.values())
    res['estado'] = 'compativel' if len(candidatos)==1 else 'ambigua' if candidatos else 'nao_relacionado'
    res['registros_relacionados'] = sorted({r for c in candidatos.values() for r in c['registros_origem']})
    if len(candidatos)!=1:
        return res
    # Outra publicacao oficial com a mesma serie declarada no mesmo marco pode
    # contradizer o estado operacional; nao substituir a fonte do ponto.
    c = next(iter(candidatos.values()))
    estado = db.scalar(conn,'SELECT codigo FROM SITUACAO_OPERACIONAL WHERE id=?',(origem['situacao_operacional_id'],))
    sql = """SELECT DISTINCT p.id AS ponto_id,p.situacao_operacional_id,r.id,r.payload_original,f.nome
        FROM PONTO_FISCALIZACAO p JOIN VINCULO_REGISTRO_PONTO vp ON vp.ponto_id=p.id AND vp.decisao_id IS NULL
        JOIN REGISTRO_FONTE r ON r.id=vp.registro_id JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id JOIN FONTE f ON f.id=rf.fonte_id
        JOIN NATUREZA_FONTE n ON n.id=f.natureza_id AND n.codigo='oficial'
        WHERE p.municipio_id=? AND p.via_id=? AND p.km=? AND p.id<>?
        """ + (' AND '+' AND '.join(clausulas) if clausulas else '')
    for row in db.query_all(conn,sql,[origem['municipio_id'],origem['via_id'],origem['km'],pid]+params):
        bruto = objeto(row['payload_original'])
        serie = bruto.get('NumeroSerie') or bruto.get('EQUIPAMENTO')
        if str(serie or '').strip().upper()!=c['numero_serie'].strip().upper() or _sentidos(conn,row['ponto_id'])!=sentidos:
            continue
        res['registros_relacionados'].append(row['id'])
        outro_estado = db.scalar(conn,'SELECT codigo FROM SITUACAO_OPERACIONAL WHERE id=?',(row['situacao_operacional_id'],))
        if estado not in (None,'desconhecido') and outro_estado not in (None,'desconhecido',estado):
            res['divergencias'].append({'campo':'situacao_operacional','valor_principal':estado,
                'valor_correspondente':outro_estado,'valor_publicado':bruto.get('ESTADO') or bruto.get('situacao'),
                'ponto_origem_id':'P-%d'%row['ponto_id'],'registro_id':row['id'],'fonte':row['nome']})
    res['registros_relacionados'] = sorted(set(res['registros_relacionados']))
    return res
