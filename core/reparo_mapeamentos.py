"""Completa campos perdidos na importacao, sem reinserir pontos nem reescrever bruto."""
import json
from collections import defaultdict

from . import db


def reparar(conn):
    from coletor.fontes.antt import ColetorANTT
    from coletor.fontes.inmetro import ColetorINMETRO
    from coletor.fontes.prf import ColetorPRFFixos
    from coletor.fontes import normalizacao as nz
    adaptadores = [('ANTT - ', object.__new__(ColetorANTT)),
                   ('INMETRO / ', object.__new__(ColetorINMETRO)),
                   ('PRF - Radares fixos', object.__new__(ColetorPRFFixos))]
    propostas = defaultdict(set)
    revisados = {r[0] for r in conn.execute("SELECT DISTINCT ponto_id FROM RADAR_ALTERACAO WHERE ponto_id IS NOT NULL")}
    res = {'registros_lidos': 0, 'campos_completados': 0, 'campos_divergentes_preservados': 0}
    rows = conn.execute("""SELECT r.id, r.payload_original, f.nome
        FROM REGISTRO_FONTE r JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id JOIN FONTE f ON f.id=rf.fonte_id
        JOIN NATUREZA_FONTE n ON n.id=f.natureza_id AND n.codigo='oficial'
        WHERE f.nome LIKE 'ANTT - %' OR f.nome LIKE 'INMETRO / %' OR f.nome='PRF - Radares fixos'
        ORDER BY r.id""").fetchall()
    for row in rows:
        adaptador = next((a for prefixo,a in adaptadores if row['nome'].startswith(prefixo)), None)
        if adaptador is None:
            continue
        try:
            raw = json.loads(row['payload_original'])
            d = adaptador.normalizar(0, raw) if isinstance(raw, dict) else None
        except (ValueError, TypeError, AttributeError):
            continue
        if not d:
            continue
        res['registros_lidos'] += 1
        for ponto in conn.execute('SELECT ponto_id FROM VINCULO_REGISTRO_PONTO WHERE registro_id=? AND decisao_id IS NULL', (row['id'],)):
            pid = ponto[0]
            if pid in revisados:
                continue
            for coluna in ('km', 'tipo_pista'):
                if d.get(coluna) is not None:
                    propostas['PONTO_FISCALIZACAO', pid, coluna].add(d[coluna])
            if d.get('via_codigo'):
                via = nz.obter_via(conn, d['via_codigo'], d.get('via_tipo'))
                propostas['PONTO_FISCALIZACAO', pid, 'via_id'].add(via)
            if d.get('situacao') not in (None, 'desconhecido'):
                sid = db.domain_id(conn, 'SITUACAO_OPERACIONAL', d['situacao'])
                propostas['PONTO_FISCALIZACAO', pid, 'situacao_operacional_id'].add(sid)
            for equip in conn.execute('SELECT equipamento_id FROM VINCULO_REGISTRO_EQUIPAMENTO WHERE registro_id=? AND decisao_id IS NULL', (row['id'],)):
                if d.get('tipo_radar') not in (None, 'desconhecido'):
                    tid = db.domain_id(conn, 'TIPO_RADAR', d['tipo_radar'])
                    propostas['EQUIPAMENTO', equip[0], 'tipo_radar_id'].add(tid)
    desconhecidos = {
        'situacao_operacional_id': db.domain_id(conn, 'SITUACAO_OPERACIONAL', 'desconhecido'),
        'tipo_radar_id': db.domain_id(conn, 'TIPO_RADAR', 'desconhecido'),
    }
    for (tabela, eid, coluna), valores in propostas.items():
        if len(valores) != 1:
            res['campos_divergentes_preservados'] += 1
            continue
        valor = next(iter(valores))
        atual = db.scalar(conn, 'SELECT %s FROM %s WHERE id=?' % (coluna, tabela), (eid,))
        if atual is None or atual == desconhecidos.get(coluna, object()):
            conn.execute('UPDATE %s SET %s=? WHERE id=?' % (tabela,coluna), (valor,eid))
            res['campos_completados'] += 1
    return res
