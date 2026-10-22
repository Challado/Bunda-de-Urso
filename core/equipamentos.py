"""Identidade fisica na escrita; fontes e instalacoes continuam independentes.

Serie isolada e proximidade nao sao chaves. Reuso automatico exige fontes
oficiais, tipo/serie exatos e fabricante conhecido ou local cadastral completo.
"""
import json
import math

from . import db
from .dedup import normalizar_serie, normalizar_texto, serie_generica


def serie_valida(valor):
    normalizada = normalizar_serie(valor)
    return (normalizada and not serie_generica(normalizada)
            and normalizada not in ('DESCONHECIDO', 'NAOINFORMADO')
            and len(normalizada) >= 5)


def _oficial(conn, fonte_id):
    return db.scalar(conn, "SELECT n.codigo FROM FONTE f JOIN NATUREZA_FONTE n "
                     "ON n.id=f.natureza_id WHERE f.id=?", (fonte_id,)) == 'oficial'


def _decidido(conn, eid, registro_id=None):
    # Mesmo decisoes revertidas conservam IDs historicos: nao mover suas FKs.
    return db.scalar(conn, "SELECT 1 FROM CANDIDATO_DUPLICIDADE c "
                     "JOIN DECISAO_DUPLICIDADE d ON d.candidato_id=c.id "
                     "WHERE c.registro_a_id IN (SELECT registro_id FROM VINCULO_REGISTRO_EQUIPAMENTO WHERE equipamento_id=?) "
                     "OR c.registro_b_id IN (SELECT registro_id FROM VINCULO_REGISTRO_EQUIPAMENTO WHERE equipamento_id=?) "
                     "OR c.registro_a_id=? OR c.registro_b_id=? LIMIT 1",
                     (eid, eid, registro_id, registro_id)) is not None


def _modelo(conn, mid):
    row = db.query_one(conn, "SELECT m.nome_modelo, o.nome FROM MODELO_EQUIPAMENTO m "
                       "LEFT JOIN ORGANIZACAO o ON o.id=m.fabricante_id WHERE m.id=?", (mid,))
    def conhecido(v):
        v = normalizar_texto(v)
        return v if v and v not in ('DESCONHECIDO', 'NAOINFORMADO') else None
    return (conhecido(row[0]), conhecido(row[1])) if row else (None, None)


def modelos_compativeis(conn, a, b):
    ma, mb = _modelo(conn, a), _modelo(conn, b)
    if any(x and y and x != y for x, y in zip(ma, mb)):
        return False
    ra = db.query_one(conn, 'SELECT * FROM MODELO_EQUIPAMENTO WHERE id=?', (a,))
    rb = db.query_one(conn, 'SELECT * FROM MODELO_EQUIPAMENTO WHERE id=?', (b,))
    if ra and rb:
        for campo in ('tecnologia_id', 'registro_aprovacao_inmetro', 'portaria_aprovacao_modelo'):
            if ra[campo] is not None and rb[campo] is not None and ra[campo] != rb[campo]:
                return False
    return True


def modelo_complementado(conn, atual, novo):
    if atual is None:
        return novo
    if novo is None or not modelos_compativeis(conn, atual, novo):
        return atual
    def completude(mid):
        row = db.query_one(conn, 'SELECT * FROM MODELO_EQUIPAMENTO WHERE id=?', (mid,))
        return sum(v is not None for v in _modelo(conn, mid)) + sum(
            row[c] is not None for c in ('tecnologia_id', 'registro_aprovacao_inmetro', 'portaria_aprovacao_modelo'))
    ra = db.query_one(conn, 'SELECT * FROM MODELO_EQUIPAMENTO WHERE id=?', (atual,))
    rb = db.query_one(conn, 'SELECT * FROM MODELO_EQUIPAMENTO WHERE id=?', (novo,))
    preserva = all(ra[c] is None or ra[c] == rb[c] for c in
                   ('tecnologia_id', 'registro_aprovacao_inmetro', 'portaria_aprovacao_modelo'))
    return novo if preserva and completude(novo) > completude(atual) else atual


def _locais(conn, eid):
    from .local_cadastral import extrair
    locais = {(r[0], r[1], r[2]) for r in conn.execute("""SELECT p.municipio_id, v.codigo, p.km
        FROM INSTALACAO i JOIN PONTO_FISCALIZACAO p ON p.id=i.ponto_id
        JOIN VIA v ON v.id=p.via_id
        WHERE i.equipamento_id=? AND p.municipio_id IS NOT NULL AND p.km IS NOT NULL""", (eid,))}
    # Bases anteriores mantinham esse marco somente no bruto do Inmetro.
    for row in conn.execute("""SELECT r.payload_original, p.municipio_id
        FROM VINCULO_REGISTRO_EQUIPAMENTO ve
        JOIN REGISTRO_FONTE r ON r.id=ve.registro_id
        JOIN VINCULO_REGISTRO_PONTO vp ON vp.registro_id=r.id
        JOIN PONTO_FISCALIZACAO p ON p.id=vp.ponto_id
        WHERE ve.equipamento_id=? AND ve.decisao_id IS NULL AND vp.decisao_id IS NULL
          AND p.municipio_id IS NOT NULL""", (eid,)):
        try:
            bruto = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if isinstance(bruto, dict):
            marco = extrair(bruto.get('LocalVerificacao'))
            if marco:
                locais.add((row[1], *marco))
    return locais


def compativeis(conn, a, b):
    _, fa = _modelo(conn, a['modelo_id'])
    _, fb = _modelo(conn, b['modelo_id'])
    if not modelos_compativeis(conn, a['modelo_id'], b['modelo_id']):
        return False
    for coluna in ('ano_fabricacao', 'observacoes'):
        if a[coluna] is not None and b[coluna] is not None and a[coluna] != b[coluna]:
            return False
    if fa and fb and fa == fb:
        return True
    # Municipio + via + quilometro exatos, sem inferir local por proximidade.
    return bool(_locais(conn, a['id']) & _locais(conn, b['id']))


def _oficial_exclusivo(conn, eid):
    naturezas = {r[0] for r in conn.execute("""SELECT n.codigo
        FROM VINCULO_REGISTRO_EQUIPAMENTO v
        LEFT JOIN REGISTRO_FONTE r ON r.id=v.registro_id
        LEFT JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        LEFT JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
        LEFT JOIN FONTE f ON f.id=rf.fonte_id
        LEFT JOIN NATUREZA_FONTE n ON n.id=f.natureza_id
        WHERE v.equipamento_id=? AND v.decisao_id IS NULL""", (eid,))}
    return naturezas == {'oficial'}


def resolver(conn, fonte_id, registro_id, ponto_id, dados):
    """Reaproveita apenas um candidato comprovado; ambiguos ficam separados."""
    if not _oficial(conn, fonte_id) or not serie_valida(dados['numero_serie']):
        return None
    tipo = db.scalar(conn, 'SELECT codigo FROM TIPO_RADAR WHERE id=?', (dados['tipo_radar_id'],))
    if tipo in (None, 'desconhecido'):
        return None
    candidatos = db.query_all(conn, "SELECT * FROM EQUIPAMENTO WHERE "
        "UPPER(TRIM(numero_serie))=UPPER(TRIM(?)) AND tipo_radar_id=? ORDER BY id",
        (dados['numero_serie'], dados['tipo_radar_id']))
    _, fabricante = _modelo(conn, dados['modelo_id'])
    ponto = db.query_one(conn, 'SELECT * FROM PONTO_FISCALIZACAO WHERE id=?', (ponto_id,))
    elegiveis = []
    for c in candidatos:
        if not _oficial_exclusivo(conn, c['id']) or _decidido(conn, c['id'], registro_id):
            continue
        _, outro_fabricante = _modelo(conn, c['modelo_id'])
        if (not modelos_compativeis(conn, dados['modelo_id'], c['modelo_id'])
                or (dados['ano_fabricacao'] is not None and c['ano_fabricacao'] is not None
                    and dados['ano_fabricacao'] != c['ano_fabricacao'])):
            # Colisao da serie: nao escolher arbitrariamente outro candidato.
            return None
        mesma_fabrica = fabricante and fabricante == outro_fabricante
        via = db.scalar(conn, 'SELECT codigo FROM VIA WHERE id=?', (ponto['via_id'],)) if ponto else None
        mesmo_local = (ponto and ponto['municipio_id'] is not None and via is not None
                       and ponto['km'] is not None
                       and (ponto['municipio_id'], via, ponto['km']) in _locais(conn, c['id']))
        if mesma_fabrica or mesmo_local:
            elegiveis.append(c['id'])
    return elegiveis[0] if len(elegiveis) == 1 else None


def complementar_cadastro(conn, fonte_id, registro_id, ponto_id, identificador_id,
                          dados, anterior, local):
    """Refina um unico equipamento do mesmo codigo oficial e mesmo local.

    Opt-in do conector DNIT. Um cadastro sem serie nao e prova de um segundo
    instrumento. Nao altera serie conhecida, decisoes, certificados, outros
    locais ou publicacoes de outro codigo/orgao. Series divergentes continuam
    sendo equipamentos distintos (possivel substituicao).
    """
    if not anterior or identificador_id is None or not _oficial(conn, fonte_id):
        return None
    if any(anterior[k] is None or local[k] is None for k in ("municipio_id", "via_id", "km")):
        return None
    if (anterior["municipio_id"] != local["municipio_id"] or anterior["via_id"] != local["via_id"]
            or not math.isclose(anterior["km"], local["km"], abs_tol=0.000001, rel_tol=0)):
        return None
    codigo = db.scalar(conn, "SELECT valor_normalizado FROM IDENTIFICADOR_EXTERNO WHERE id=?", (identificador_id,))
    rows = db.query_all(conn, "SELECT e.* FROM EQUIPAMENTO e JOIN INSTALACAO i ON i.equipamento_id=e.id "
                       "WHERE i.ponto_id=?", (ponto_id,))
    if len(rows) != 1:
        return None
    row = rows[0]
    a, b = str(row["numero_serie"] or "").strip().upper(), str(dados["numero_serie"] or "").strip().upper()
    if (a and b and a != b) or row["tipo_radar_id"] != dados["tipo_radar_id"]:
        return None
    if not modelos_compativeis(conn, row["modelo_id"], dados["modelo_id"]) or _decidido(conn, row["id"], registro_id):
        return None
    origens = db.query_all(conn, "SELECT r.identificador_na_fonte, rf.fonte_id, v.decisao_id "
        "FROM VINCULO_REGISTRO_EQUIPAMENTO v JOIN REGISTRO_FONTE r ON r.id=v.registro_id "
        "JOIN ARTEFATO_COLETA ar ON ar.id=r.artefato_id JOIN RECURSO_FONTE rf ON rf.id=ar.recurso_id "
        "WHERE v.equipamento_id=?", (row["id"],))
    do_orgao = [o for o in origens if o["fonte_id"] == fonte_id]
    if not do_orgao or any(o["decisao_id"] is not None
                         or str(o["identificador_na_fonte"] or "").strip().upper() != codigo for o in do_orgao):
        return None
    # Republicacao mais pobre preserva a relacao instalada conhecida, inclusive
    # quando o Inmetro ja corroborou o instrumento em seu proprio ponto.
    if a and not b:
        return row["id"] if _oficial_exclusivo(conn, row["id"]) else None
    if any(o["fonte_id"] != fonte_id or o["decisao_id"] is not None for o in origens):
        return None
    if db.scalar(conn, "SELECT 1 FROM INSTALACAO WHERE equipamento_id=? AND ponto_id<>? LIMIT 1", (row["id"], ponto_id)):
        return None
    if not a and db.scalar(conn, "SELECT 1 FROM VERIFICACAO_METROLOGICA WHERE equipamento_id=? LIMIT 1", (row["id"],)):
        return None
    return row["id"]


def reconciliar(conn):
    """Migra duplicatas comprovadas na transacao do chamador, mantendo aliases.

    Nao apaga publicacoes, pontos, instalacoes, documentos ou verificacoes.
    Decisoes humanas e grupos ambiguos ficam pendentes para revisao.
    """
    grupos = db.query_all(conn, """SELECT UPPER(TRIM(numero_serie)) AS serie, tipo_radar_id
        FROM EQUIPAMENTO GROUP BY UPPER(TRIM(numero_serie)), tipo_radar_id HAVING COUNT(*)>1""")
    res = {'grupos': len(grupos), 'equipamentos_reconciliados': 0, 'grupos_pendentes': 0}
    for g in grupos:
        rows = db.query_all(conn, "SELECT * FROM EQUIPAMENTO WHERE UPPER(TRIM(numero_serie))=? "
                            "AND tipo_radar_id=? ORDER BY id", (g['serie'], g['tipo_radar_id']))
        if (not serie_valida(g['serie'])
                or db.scalar(conn, 'SELECT codigo FROM TIPO_RADAR WHERE id=?', (g['tipo_radar_id'],)) == 'desconhecido'
                or any(not _oficial_exclusivo(conn, r['id']) or _decidido(conn, r['id']) for r in rows)
                or any(not compativeis(conn, a, b) for i, a in enumerate(rows) for b in rows[i+1:])):
            res['grupos_pendentes'] += 1
            continue
        registros = [r[0] for row in rows for r in conn.execute(
            'SELECT registro_id FROM VINCULO_REGISTRO_EQUIPAMENTO WHERE equipamento_id=?', (row['id'],))]
        if len(registros) != len(set(registros)):
            res['grupos_pendentes'] += 1
            continue
        canonico = rows[0]['id']
        for r in rows[1:]:
            antigo = r['id']
            for tabela in ('INSTALACAO', 'IDENTIFICADOR_EQUIPAMENTO', 'VERIFICACAO_METROLOGICA',
                           'OBSERVACAO_TRAFEGO', 'DECISAO_VALOR_CANONICO'):
                conn.execute('UPDATE %s SET equipamento_id=? WHERE equipamento_id=?' % tabela, (canonico, antigo))
            for tabela in ('DOCUMENTO_EQUIPAMENTO', 'OPERACAO_EQUIPAMENTO', 'VINCULO_REGISTRO_EQUIPAMENTO'):
                colunas = [x[1] for x in conn.execute('PRAGMA table_info(%s)' % tabela)]
                for vinculo in db.query_all(conn, 'SELECT * FROM %s WHERE equipamento_id=?' % tabela, (antigo,)):
                    dados = dict(vinculo)
                    dados['equipamento_id'] = canonico
                    cols = ','.join(colunas)
                    conn.execute('INSERT OR IGNORE INTO %s (%s) VALUES (%s)' % (tabela, cols, ','.join('?' for _ in colunas)),
                                 [dados[c] for c in colunas])
                conn.execute('DELETE FROM %s WHERE equipamento_id=?' % tabela, (antigo,))
            modelo = modelo_complementado(conn, db.scalar(conn, 'SELECT modelo_id FROM EQUIPAMENTO WHERE id=?', (canonico,)), r['modelo_id'])
            conn.execute('UPDATE EQUIPAMENTO SET modelo_id=?, '
                         'ano_fabricacao=COALESCE(ano_fabricacao,?), observacoes=COALESCE(observacoes,?) WHERE id=?',
                         (modelo, r['ano_fabricacao'], r['observacoes'], canonico))
            conn.execute("UPDATE EQUIPAMENTO_ALIAS SET equipamento_id=? WHERE equipamento_id=?", (canonico, antigo))
            conn.execute("INSERT INTO EQUIPAMENTO_ALIAS (alias_id, equipamento_id, criterio) VALUES (?,?,?)",
                         (antigo, canonico, 'serie_tipo_fabricante_ou_local_cadastral'))
            conn.execute('DELETE FROM EQUIPAMENTO WHERE id=?', (antigo,))
            res['equipamentos_reconciliados'] += 1
    return res
