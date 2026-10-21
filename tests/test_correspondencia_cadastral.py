"""Regressao E-604: reparo do bruto, sugestao Inmetro e divergencia PRF."""
import copy
import json
from pathlib import Path
from core import consultas, db, governanca
from core.reparo_mapeamentos import reparar
from core.manutencao.carregar_verificacao_metrologica import carregar
from coletor.fontes.antt import ColetorANTT
from coletor.fontes.inmetro import ColetorINMETRO
from coletor.fontes.prf import ColetorPRFFixos
from coletor.fontes.normalizacao import inserir_normalizado
from tests import test_dedup as apoio

FIXTURE = Path(__file__).parent/'fixtures'/'novos'/'correspondencia_e604.json'


class TestCorrespondenciaCadastral(apoio.BaseDedup):
    def setUp(self):
        super().setUp()
        governanca.garantir_esquema(self.con)
        db.insert(self.con,'MUNICIPIO',dict(codigo_ibge='4104808',uf_sigla='PR',nome='Cascavel'))
        self.raw = json.loads(FIXTURE.read_text())
        self.fontes = {chave:self.fonte(nome) for chave,nome in
            (('antt','ANTT - Dados dos radares em rodovias concedidas'),('inmetro','INMETRO / PSIE'),('prf','PRF - Radares fixos'))}
        self.adaptadores = {'antt':object.__new__(ColetorANTT),'inmetro':object.__new__(ColetorINMETRO),'prf':object.__new__(ColetorPRFFixos)}

    def observar(self,chave,raw=None,legado=False):
        raw=copy.deepcopy(self.raw[chave] if raw is None else raw)
        rid=self.registro(self.artefato(self.recurso(self.fontes[chave])),raw)
        d=self.adaptadores[chave].normalizar(0,raw)
        if legado:
            if chave in ('antt','inmetro'):d.update(km=None,via_codigo=None if chave=='inmetro' else d['via_codigo'])
            if chave=='antt':d.update(tipo_pista=None,tipo_radar='desconhecido')
            if chave=='prf':d['situacao']='desconhecido'
        ids=inserir_normalizado(self.con,rid,d,fonte_id=self.fontes[chave])
        if chave=='inmetro':carregar(self.con,[(rid,ids['equipamento_id'],raw)])
        return ids,rid

    def par(self,legado=False):
        self.a,self.ra=self.observar('antt',legado=legado)
        self.b,self.rb=self.observar('inmetro',legado=legado)

    def detalhe(self):
        return consultas.buscar_ponto_por_id(self.con,self.a['ponto_id'])

    def test_campos_reais_antt_sao_mapeados(self):
        d=self.adaptadores['antt'].normalizar(0,self.raw['antt'])
        self.assertEqual(d['km'],597.42)
        self.assertEqual(d['tipo_pista'],'Principal')
        self.assertEqual(d['tipo_radar'],'fixo')
        self.assertEqual(d['velocidade_leves'],60)
        self.assertEqual(d['velocidade_pesados'],60)

    def test_correspondencia_por_marco_nao_inventa_serie_nem_funde(self):
        self.par()
        antes=self.con.total_changes
        p=self.detalhe();c=p['correspondencia_metrologica']
        self.assertEqual(self.con.total_changes,antes)
        self.assertEqual(c['estado'],'compativel')
        e=c['candidatos'][0]
        self.assertEqual(e['numero_serie'],'FSC110-0811')
        self.assertFalse(e['identidade_fisica_confirmada'])
        self.assertEqual(e['verificacoes_metrologicas'][0]['numero_certificado'],'16415173')
        self.assertEqual(e['verificacoes_metrologicas'][0]['validade_ate'],'2027-05-03')
        self.assertIsNone(p['equipamentos'][0]['numero_serie'])
        self.assertEqual(p['equipamentos'][0]['verificacoes_metrologicas'],[])
        self.assertEqual(self.contar('EQUIPAMENTO'),2)
        self.assertEqual(self.contar('PONTO_FISCALIZACAO'),2)
        fonte=next(f for f in p['dados_por_fonte'] if f['nome']=='INMETRO / PSIE')
        self.assertEqual(fonte['registros'][0]['escopo_vinculo'],'correspondencia_cadastral')
        self.assertEqual(p['localizacao']['latitude'],-24.982289)
        self.assertIsNone(db.scalar(self.con,'SELECT posicao_id FROM PONTO_FISCALIZACAO WHERE id=?',(self.b['ponto_id'],)))

    def test_reparo_completa_base_existente_preservando_ids_e_bruto(self):
        self.par(legado=True)
        prf,rprf=self.observar('prf',legado=True)
        bruto=[tuple(r) for r in self.con.execute('SELECT * FROM REGISTRO_FONTE')]
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['estado'],'dados_insuficientes')
        self.assertGreater(reparar(self.con)['campos_completados'],0)
        p=self.detalhe()
        self.assertEqual(p['correspondencia_metrologica']['estado'],'compativel')
        self.assertEqual(p['localizacao']['km'],597.42)
        self.assertEqual(p['localizacao']['tipo_pista'],'Principal')
        self.assertEqual(p['equipamentos'][0]['id'],'E-%s'%self.a['equipamento_id'])
        self.assertEqual(bruto,[tuple(r) for r in self.con.execute('SELECT * FROM REGISTRO_FONTE')])
        self.assertEqual(reparar(self.con)['campos_completados'],0)
        self.assertEqual(self.contar('PONTO_FISCALIZACAO'),3)
        self.assertEqual(self.contar('EQUIPAMENTO'),3)
        self.assertEqual(self.con.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_divergencia_prf_fica_visivel_sem_sobrescrever_antt(self):
        self.par()
        self.observar('prf')
        p=self.detalhe()
        self.assertEqual(p['situacao_operacional'],'ativo')
        self.assertEqual(p['confianca'],'conflitante')
        self.assertEqual(p['correspondencia_metrologica']['divergencias'][0]['valor_correspondente'],'inativo')
        self.assertEqual(p['correspondencia_metrologica']['divergencias'][0]['valor_publicado'],'INOPERANTE')
        self.assertEqual(len(p['dados_por_fonte']),3)

    def test_nao_relaciona_sentido_ou_velocidade_diferentes(self):
        for chave,valor in (('Sentido','CRESCENTE'),('VelocidadeNominal','80')):
            with self.subTest(chave=chave):
                self.par()
                if chave=='Sentido':
                    self.con.execute("UPDATE FAIXA_FISCALIZACAO SET sentido_id=? WHERE ponto_id=?",(db.domain_id(self.con,'SENTIDO','crescente'),self.b['ponto_id']))
                else:
                    self.con.execute('UPDATE LIMITE_VELOCIDADE SET velocidade_kmh=80 WHERE ponto_id=? OR faixa_id IN (SELECT id FROM FAIXA_FISCALIZACAO WHERE ponto_id=?)',(self.b['ponto_id'],self.b['ponto_id']))
                self.assertEqual(self.detalhe()['correspondencia_metrologica']['candidatos'],[])

    def test_nao_relaciona_marco_diferente_ou_sem_sentido(self):
        self.par()
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET km=597.421 WHERE id=?',(self.b['ponto_id'],))
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['candidatos'],[])
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET km=597.42 WHERE id=?',(self.b['ponto_id'],))
        self.con.execute('UPDATE FAIXA_FISCALIZACAO SET sentido_id=NULL WHERE ponto_id=?',(self.a['ponto_id'],))
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['estado'],'dados_insuficientes')

    def test_dois_instrumentos_compativeis_ficam_ambiguos(self):
        self.par()
        outro=copy.deepcopy(self.raw['inmetro']);outro['NumeroSerie']='FSC110-OUTRO';outro['NumeroInmetro']='16176986'
        for faixa in outro['Faixas']:faixa.update(NumeroSerie='FSC110-OUTRO',NumeroInmetro='16176986')
        self.observar('inmetro',outro)
        c=self.detalhe()['correspondencia_metrologica']
        self.assertEqual(c['estado'],'ambigua')
        self.assertEqual(len(c['candidatos']),2)

    def test_fonte_comunitaria_nao_vira_correspondencia_oficial(self):
        self.par()
        self.con.execute('UPDATE FONTE SET natureza_id=? WHERE id=?',(db.domain_id(self.con,'NATUREZA_FONTE','comunitaria'),self.fontes['inmetro']))
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['candidatos'],[])

    def test_remocao_desabilitacao_e_decisao_de_separacao_prevalecem(self):
        self.par()
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-21' WHERE id=?",(self.b['ponto_id'],))
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['candidatos'],[])
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET removido_em=NULL WHERE id=?',(self.b['ponto_id'],))
        regra=db.insert(self.con,'REGRA_DEDUPLICACAO',dict(versao='regra',descricao='regra',configuracao_serializada='{}',inicio_validade='2026-10-21'))
        c=db.insert(self.con,'CANDIDATO_DUPLICIDADE',dict(registro_a_id=self.ra,registro_b_id=self.rb,regra_id=regra,estado='revisar',gerado_em='2026-10-21'))
        db.insert(self.con,'DECISAO_DUPLICIDADE',dict(candidato_id=c,decisao='manter_separados',fundamentacao='distintos',ator='revisor',decidida_em='2026-10-21'))
        self.assertEqual(self.detalhe()['correspondencia_metrologica']['candidatos'],[])

    def test_reparo_nao_sobrescreve_edicao_humana(self):
        self.par(legado=True)
        db.insert(self.con,'RADAR_ALTERACAO',dict(ponto_id=self.a['ponto_id'],quem_rotulo='revisor',quando='2026-10-21',tipo='editado',campos_json='{}'))
        reparar(self.con)
        self.assertIsNone(self.detalhe()['localizacao']['km'])
