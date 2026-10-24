"""Chaves, dependencias, migracao e identidade na escrita (sem rede)."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from core import consultas, db, equipamentos, governanca
from core.contexto_api import atendimento_local
from core.local_cadastral import extrair
from core.manutencao import reconciliar_equipamentos
from coletor.fontes import normalizacao as nz
from coletor.fontes.inmetro import ColetorINMETRO
from tests import test_dedup as apoio


class TestNormalizacaoRelacional(apoio.BaseDedup):
    def setUp(self):
        super().setUp()
        governanca.garantir_esquema(self.con)
        db.insert(self.con, 'MUNICIPIO', {'codigo_ibge': '5210208', 'nome': 'Iporá', 'uf_sigla': 'GO'})
        self.a = self.fonte('GOINFRA')
        self.b = self.fonte('INMETRO / PSIE')

    def observar(self, fonte, **campos):
        d = dict(tipo_radar='fixo', numero_serie='118690160', uf='GO',
                 municipio_ibge='5210208', via_codigo='GO-060', km=249.1)
        d.update(campos)
        rid = self.registro(self.artefato(self.recurso(fonte)), d)
        return nz.inserir_normalizado(self.con, rid, d, fonte_id=fonte), rid

    def duplicar(self, **campos):
        x, rx = self.observar(self.a, **campos)
        # Simula a base anterior: insercao por ponto, sem resolver entre fontes.
        with patch('core.equipamentos.resolver', return_value=None):
            y, ry = self.observar(self.b, **campos)
        return x, rx, y, ry

    def test_reusa_equipamento_entre_fontes_sem_fundir_pontos(self):
        x, rx = self.observar(self.a)
        y, ry = self.observar(self.b)
        self.assertEqual(x['equipamento_id'], y['equipamento_id'])
        self.assertNotEqual(x['ponto_id'], y['ponto_id'])
        self.assertEqual(self.contar('EQUIPAMENTO'), 1)
        self.assertEqual(self.contar('INSTALACAO'), 2)
        p = consultas.buscar_ponto_por_id(self.con, x['ponto_id'])
        self.assertEqual({f['nome'] for f in p['dados_por_fonte']}, {'GOINFRA', 'INMETRO / PSIE'})
        self.assertEqual(self.contar('REGISTRO_FONTE'), 2)

    def test_nao_reusa_sem_local_completo_ou_com_outro_km(self):
        x, _ = self.observar(self.a)
        for campos in ({'km': None}, {'via_codigo': None}, {'km': 249.101}):
            y, _ = self.observar(self.b, **campos)
            self.assertNotEqual(x['equipamento_id'], y['equipamento_id'])

    def test_fabricante_conhecido_identifica_instrumento_movido(self):
        x, _ = self.observar(self.a, fabricante='Fabricante X', modelo='Modelo A')
        y, _ = self.observar(self.b, fabricante='Fabricante X', modelo='Modelo A', km=500)
        self.assertEqual(x['equipamento_id'], y['equipamento_id'])

    def test_modelos_ou_anos_conflitantes_nao_se_fundem(self):
        for coluna, a, b in (('modelo', 'A', 'B'), ('ano_fabricacao', 2025, 2026)):
            with self.subTest(coluna=coluna):
                self.con.execute('DELETE FROM VINCULO_REGISTRO_EQUIPAMENTO')
                self.con.execute('DELETE FROM INSTALACAO')
                self.con.execute('DELETE FROM EQUIPAMENTO')
                x, _ = self.observar(self.a, **{coluna: a})
                y, _ = self.observar(self.b, **{coluna: b})
                self.assertNotEqual(x['equipamento_id'], y['equipamento_id'])

    def test_serie_isolada_generica_e_comunitaria_nao_alteram_oficial(self):
        x, _ = self.observar(self.a)
        comunitaria = self.fonte('Envio publico', natureza='comunitaria')
        y, _ = self.observar(comunitaria)
        self.assertNotEqual(x['equipamento_id'], y['equipamento_id'])
        for serie in (None, 'S/N', '000000', '123', 'desconhecido'):
            x, _ = self.observar(self.a, numero_serie=serie)
            y, _ = self.observar(self.b, numero_serie=serie)
            self.assertNotEqual(x['equipamento_id'], y['equipamento_id'])

    def test_modelo_sem_fabricante_e_reutilizado_com_null(self):
        x, _ = self.observar(self.a, modelo='Modelo incompleto')
        y, _ = self.observar(self.b, modelo='Modelo incompleto')
        self.assertEqual(self.contar('MODELO_EQUIPAMENTO'), 1)
        self.assertEqual(x['equipamento_id'], y['equipamento_id'])

    def test_conflito_no_mesmo_ponto_nao_e_encoberto(self):
        x, _ = self.observar(self.a, identificador='LOCAL-X', modelo='Modelo A')
        y, _ = self.observar(self.a, identificador='LOCAL-X', modelo='Modelo B')
        self.assertEqual(x['ponto_id'], y['ponto_id'])
        self.assertNotEqual(x['equipamento_id'], y['equipamento_id'])

    def test_reconciliacao_move_fks_preserva_origem_alias_e_idempotencia(self):
        x, rx, y, ry = self.duplicar()
        eid, antigo = x['equipamento_id'], y['equipamento_id']
        vid = db.insert(self.con, 'VERIFICACAO_METROLOGICA', dict(equipamento_id=antigo,
            tipo_verificacao_id=db.domain_id(self.con, 'TIPO_VERIFICACAO', 'periodica'),
            resultado_id=db.domain_id(self.con, 'RESULTADO_VERIFICACAO', 'conforme'), registro_fonte_id=ry))
        doc = db.insert(self.con, 'DOCUMENTO', dict(tipo_documento_id=db.domain_id(self.con, 'TIPO_DOCUMENTO', 'outro'), titulo='Laudo'))
        db.insert(self.con, 'DOCUMENTO_EQUIPAMENTO', dict(documento_id=doc, equipamento_id=antigo))
        raw = [tuple(r) for r in self.con.execute('SELECT * FROM REGISTRO_FONTE')]
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 1)
        self.assertEqual(self.contar('EQUIPAMENTO'), 1)
        self.assertEqual(self.contar('INSTALACAO'), 2)
        self.assertEqual(db.scalar(self.con, 'SELECT equipamento_id FROM VERIFICACAO_METROLOGICA WHERE id=?', (vid,)), eid)
        self.assertEqual(db.scalar(self.con, 'SELECT equipamento_id FROM DOCUMENTO_EQUIPAMENTO'), eid)
        self.assertEqual(raw, [tuple(r) for r in self.con.execute('SELECT * FROM REGISTRO_FONTE')])
        self.assertEqual(consultas.buscar_equipamento_por_id(self.con, antigo)['id'], 'E-%s' % eid)
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 0)
        self.assertEqual(self.con.execute('PRAGMA foreign_key_check').fetchall(), [])
        novo = db.insert(self.con, 'EQUIPAMENTO', {'tipo_radar_id': db.domain_id(self.con, 'TIPO_RADAR', 'fixo')})
        self.assertGreater(novo, antigo)

    def test_reconciliacao_respeita_decisoes_humanas(self):
        x, rx, y, ry = self.duplicar()
        regra = db.insert(self.con, 'REGRA_DEDUPLICACAO', dict(versao='x', descricao='x', configuracao_serializada='{}', inicio_validade='2026-10-21'))
        cand = db.insert(self.con, 'CANDIDATO_DUPLICIDADE', dict(registro_a_id=min(rx,ry), registro_b_id=max(rx,ry), regra_id=regra, estado='revisar', gerado_em='2026-10-21'))
        db.insert(self.con, 'DECISAO_DUPLICIDADE', dict(candidato_id=cand, decisao='manter_separados', fundamentacao='Instrumentos distintos', ator='revisor', decidida_em='2026-10-21'))
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 0)
        self.assertEqual(self.contar('EQUIPAMENTO'), 2)

    def test_ambiguidade_entre_tres_modelos_nao_escolhe_um(self):
        self.duplicar(modelo=None)
        with patch('core.equipamentos.resolver', return_value=None):
            self.observar(self.b, modelo='Modelo A')
            self.observar(self.b, modelo='Modelo B')
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 0)

    def test_reconciliacao_aproveita_marco_explicito_no_bruto_antigo(self):
        x, rx, y, ry = self.duplicar()
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET via_id=NULL,km=NULL WHERE id=?', (y['ponto_id'],))
        self.con.execute('UPDATE REGISTRO_FONTE SET payload_original=? WHERE id=?', (json.dumps({'LocalVerificacao':'GO 060 KM249+100M'}),ry))
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 1)
        self.assertIsNone(db.scalar(self.con, 'SELECT km FROM PONTO_FISCALIZACAO WHERE id=?', (y['ponto_id'],)))

    def test_parser_nao_inventa_via_km_ou_gps(self):
        self.assertEqual(extrair('GO060 KM249+100M'), ('GO-060',249.1))
        self.assertEqual(extrair('BR 364 KM 123,830'), ('BR-364',123.83))
        for texto in ('Rua X, 249', 'GO060 km249', 'GO060 km249+100 ate 300', 'BR364 KM100+100 e KM200+200', 'GO060 / BR070 km249+100', 'GO060 km249+1000'):
            self.assertIsNone(extrair(texto), texto)
        with patch.object(ColetorINMETRO, '__init__', return_value=None):
            d = ColetorINMETRO().normalizar(0, {'NumeroSerie':'118690160','LocalVerificacao':'GO060 KM249+100M'})
        self.assertEqual((d['via_codigo'],d['km']), ('GO-060',249.1))
        self.assertIsNone(d['latitude'])
        self.assertIsNone(d['longitude'])

    def test_snapshot_deriva_recurso_e_impede_dois_artefatos_do_mesmo_recurso(self):
        recurso = self.recurso(self.a)
        a, b = self.artefato(recurso), self.artefato(recurso)
        snap = db.insert(self.con,'SNAPSHOT_PUBLICADO',dict(publicado_em='2026-10-21',status='publicado',identificador_versao='s1'))
        self.con.execute('INSERT INTO SNAPSHOT_RECURSO VALUES (?,?)',(snap,a))
        self.assertEqual(db.scalar(self.con,'SELECT recurso_id FROM SNAPSHOT_RECURSO_DETALHE'), recurso)
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('INSERT INTO SNAPSHOT_RECURSO VALUES (?,?)',(snap,b))
        self.assertNotIn('recurso_id', {r[1] for r in self.con.execute('PRAGMA table_info(SNAPSHOT_RECURSO)')})

    def test_execucao_sem_artefato_e_fk_de_sucesso_consistente(self):
        recurso = self.recurso(self.a)
        outro = self.recurso(self.b)
        a = self.artefato(recurso)
        e = db.insert(self.con, 'EXECUCAO_COLETA',dict(recurso_id=recurso,iniciada_em='2026-10-21',status='ok',tentativas=1))
        self.assertIsNone(db.scalar(self.con,'SELECT artefato_id FROM EXECUCAO_COLETA_DETALHE WHERE id=?',(e,)))
        self.con.execute('INSERT INTO EXECUCAO_ARTEFATO VALUES (?,?)',(e,a))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('UPDATE EXECUCAO_COLETA SET recurso_id=? WHERE id=?',(outro,e))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('UPDATE ARTEFATO_COLETA SET recurso_id=? WHERE id=?',(outro,a))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('UPDATE EXECUCAO_ARTEFATO SET artefato_id=? WHERE execucao_id=?',(self.artefato(outro),e))
        self.assertNotIn('artefato_id', {r[1] for r in self.con.execute('PRAGMA table_info(EXECUCAO_COLETA)')})

    def test_cobertura_municipal_deriva_uf(self):
        cid = db.insert(self.con,'COBERTURA_FONTE',dict(fonte_id=self.a,tipo_abrangencia='municipal',municipio_id='5210208',confirmada=1))
        self.assertEqual(db.scalar(self.con,'SELECT uf_sigla FROM COBERTURA_FONTE_DETALHE WHERE id=?',(cid,)),'GO')
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute('UPDATE COBERTURA_FONTE SET uf_sigla=\'GO\' WHERE id=?',(cid,))

    def test_comando_simula_sem_gravar_e_aplica_com_backup(self):
        self.duplicar()
        self.con.commit()
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta)/'base.sqlite3'
            with contextlib.closing(db.connect(alvo)) as copia:
                self.con.backup(copia)
            with atendimento_local(), patch('core.config.DATA_DIR',pasta), patch('core.caminhos.data_dir',return_value=pasta), contextlib.redirect_stdout(io.StringIO()) as saida:
                self.assertEqual(reconciliar_equipamentos.main(['--db',str(alvo)]),0)
                self.assertEqual(json.loads(saida.getvalue())['modo'],'simulacao')
            with contextlib.closing(db.connect_readonly(alvo)) as c:
                self.assertEqual(db.scalar(c,'SELECT COUNT(*) FROM EQUIPAMENTO'),2)
            with atendimento_local(), patch('core.config.DATA_DIR',pasta), patch('core.caminhos.data_dir',return_value=pasta), contextlib.redirect_stdout(io.StringIO()) as saida:
                self.assertEqual(reconciliar_equipamentos.main(['--db',str(alvo),'--aplicar']),0)
                backup = json.loads(saida.getvalue())['backup']
            with contextlib.closing(db.connect_readonly(backup)) as c:
                self.assertEqual(db.scalar(c,'SELECT COUNT(*) FROM EQUIPAMENTO'),2)
            with contextlib.closing(db.connect_readonly(alvo)) as c:
                self.assertEqual(db.scalar(c,'SELECT COUNT(*) FROM EQUIPAMENTO'),1)

    def legado(self, inconsistente=False):
        """Reconstroi as duas relacoes antigas com dados, mantendo FK ativas."""
        for row in self.con.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            self.con.execute('DROP TRIGGER ' + row[0])
        self.con.execute('DROP VIEW EXECUCAO_COLETA_DETALHE')
        self.con.execute('DROP VIEW SNAPSHOT_RECURSO_DETALHE')
        self.con.execute('DROP TABLE SNAPSHOT_RECURSO')
        self.con.execute('CREATE TABLE SNAPSHOT_RECURSO (snapshot_id INTEGER NOT NULL REFERENCES SNAPSHOT_PUBLICADO(id), recurso_id INTEGER NOT NULL REFERENCES RECURSO_FONTE(id), artefato_id INTEGER NOT NULL REFERENCES ARTEFATO_COLETA(id), PRIMARY KEY(snapshot_id,recurso_id))')
        self.con.execute('DROP TABLE EXECUCAO_ARTEFATO')
        self.con.execute('ALTER TABLE EXECUCAO_COLETA ADD COLUMN artefato_id INTEGER REFERENCES ARTEFATO_COLETA(id)')
        recurso, outro = self.recurso(self.a), self.recurso(self.b)
        art = self.artefato(recurso)
        eid = db.insert(self.con,'EXECUCAO_COLETA',dict(recurso_id=recurso,iniciada_em='2026-10-21',status='ok',tentativas=1,artefato_id=art))
        sid = db.insert(self.con,'SNAPSHOT_PUBLICADO',dict(publicado_em='2026-10-21',status='publicado',identificador_versao='legado'))
        self.con.execute('INSERT INTO SNAPSHOT_RECURSO VALUES (?,?,?)',(sid,outro if inconsistente else recurso,art))
        self.con.execute("DELETE FROM MIGRACAO_GOVERNANCA WHERE versao IN ('0004','0006')")
        self.con.commit()
        return recurso,art,eid,sid

    def test_migracao_populada_preserva_ids_vinculos_e_execucoes(self):
        recurso,art,eid,sid = self.legado()
        governanca.aplicar_migracoes(self.con)
        self.assertEqual(tuple(self.con.execute('SELECT snapshot_id,recurso_id,artefato_id FROM SNAPSHOT_RECURSO_DETALHE').fetchone()),(sid,recurso,art))
        self.assertEqual(db.scalar(self.con,'SELECT artefato_id FROM EXECUCAO_COLETA_DETALHE WHERE id=?',(eid,)),art)
        self.assertEqual(self.con.execute('PRAGMA foreign_key_check').fetchall(),[])
        governanca.aplicar_migracoes(self.con)
        self.assertEqual(self.contar('SNAPSHOT_RECURSO'),1)
        self.assertEqual(self.contar('EXECUCAO_ARTEFATO'),1)

    def test_migracao_recusa_contradicao_sem_escolher_um_valor(self):
        self.legado(inconsistente=True)
        with self.assertRaises(sqlite3.IntegrityError):
            governanca.aplicar_migracoes(self.con)
        self.con.rollback()
        self.assertIn('recurso_id',{r[1] for r in self.con.execute('PRAGMA table_info(SNAPSHOT_RECURSO)')})
        self.assertEqual(self.contar('SNAPSHOT_RECURSO'),1)
        self.assertEqual(db.scalar(self.con,"SELECT COUNT(*) FROM MIGRACAO_GOVERNANCA WHERE versao='0004'"),0)

    def test_migracao_da_cobertura_remove_apenas_uf_derivavel(self):
        self.legado()
        # Esta redundancia era permitida na DDL anterior; simula somente o legado.
        self.con.execute('PRAGMA ignore_check_constraints=ON')
        cid = db.insert(self.con,'COBERTURA_FONTE',dict(fonte_id=self.a,tipo_abrangencia='municipal',municipio_id='5210208',uf_sigla='GO',confirmada=1))
        self.con.execute('PRAGMA ignore_check_constraints=OFF')
        self.con.commit()
        governanca.aplicar_migracoes(self.con)
        self.assertIsNone(db.scalar(self.con,'SELECT uf_sigla FROM COBERTURA_FONTE WHERE id=?',(cid,)))
        self.assertEqual(db.scalar(self.con,'SELECT uf_sigla FROM COBERTURA_FONTE_DETALHE WHERE id=?',(cid,)),'GO')

    def test_verificacoes_compartilhadas_preservam_observacoes_divergentes(self):
        from core.manutencao.carregar_verificacao_metrologica import carregar
        x, rx = self.observar(self.a)
        y, ry = self.observar(self.b)
        a = dict(UltimoResultado='Aprovado',DataUltimaVerificacao='25/06/2026',DataValidade='24/06/2027')
        b = dict(a,DataValidade='25/06/2027')
        registros = [(rx,x['equipamento_id'],a),(ry,y['equipamento_id'],b)]
        self.assertEqual(carregar(self.con,registros)['inseridas'],2)
        self.assertEqual(carregar(self.con,registros)['inseridas'],0)
        self.assertEqual({r[0] for r in self.con.execute('SELECT validade_ate FROM VERIFICACAO_METROLOGICA')},{'2027-06-24','2027-06-25'})

    def test_releitura_idempotente_das_duas_fontes(self):
        for _ in range(3):
            a, _ = self.observar(self.a, identificador='LOCAL-123')
            b, _ = self.observar(self.b, identificador='INMETRO-456')
            self.assertEqual(a['equipamento_id'], b['equipamento_id'])
        self.assertEqual(self.contar('EQUIPAMENTO'), 1)
        self.assertEqual(self.contar('PONTO_FISCALIZACAO'), 2)
        self.assertEqual(self.contar('INSTALACAO'), 2)
        self.assertEqual(self.contar('REGISTRO_FONTE'), 6)

    def test_recuperacao_nao_reinstala_codigo_incompativel_com_schema_migrado(self):
        from core.instalacao import _esquema_compativel_com_backup
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            backup = pasta / 'backup'
            backup.mkdir()
            atual = pasta / 'atual.sqlite3'
            with contextlib.closing(db.connect(backup / 'radar.sqlite3')) as c:
                c.execute('CREATE TABLE EXECUCAO_COLETA (id INTEGER PRIMARY KEY, artefato_id INTEGER)')
            with contextlib.closing(db.connect(atual)) as c:
                c.execute('CREATE TABLE EXECUCAO_COLETA (id INTEGER PRIMARY KEY)')
            self.assertFalse(_esquema_compativel_com_backup(backup, atual))
            with contextlib.closing(db.connect(atual)) as c:
                c.execute('ALTER TABLE EXECUCAO_COLETA ADD COLUMN artefato_id INTEGER')
            self.assertTrue(_esquema_compativel_com_backup(backup, atual))

    def test_modelo_conhecido_complementa_desconhecido_sem_trocar_equipamento(self):
        x, _ = self.observar(self.a, fabricante='Fabricante X')
        y, _ = self.observar(self.b, fabricante='Fabricante X', modelo='Modelo A')
        self.assertEqual(x['equipamento_id'], y['equipamento_id'])
        self.assertEqual(consultas.buscar_equipamento_por_id(self.con, x['equipamento_id'])['modelo'], 'Modelo A')

    def test_conflito_tecnico_entre_modelos_incompletos_impede_reconciliacao(self):
        x, rx, y, ry = self.duplicar(modelo='Modelo A')
        mid = db.scalar(self.con, 'SELECT modelo_id FROM EQUIPAMENTO WHERE id=?', (x['equipamento_id'],))
        self.con.execute("UPDATE MODELO_EQUIPAMENTO SET registro_aprovacao_inmetro='A' WHERE id=?", (mid,))
        outro = db.insert(self.con, 'MODELO_EQUIPAMENTO', dict(nome_modelo='Modelo A', registro_aprovacao_inmetro='B'))
        self.con.execute('UPDATE EQUIPAMENTO SET modelo_id=? WHERE id=?', (outro, y['equipamento_id']))
        self.assertEqual(equipamentos.reconciliar(self.con)['equipamentos_reconciliados'], 0)
