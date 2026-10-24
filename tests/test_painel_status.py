"""Cobertura nacional, identidade, fiscalizacao e observabilidade dos leitores."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import db, dedup, governanca, painel_status as status
from coletor.fontes.antt import ColetorANTT
from coletor.fontes.inmetro import ColetorINMETRO
from tests.test_dedup import BaseDedup
from tests.common import banco_com_antt
from web import nucleo


class TestCoberturaStatus(BaseDedup):
    def cadastro(self, fonte, uf='GO', ponto=None, payload=None):
        rid = self.registro(self.artefato(self.recurso(fonte)), payload or {'UF': uf})
        pid = self.ponto() if ponto is None else ponto
        self.ligar_ponto(rid, pid)
        return pid, rid

    def estado(self, uf='GO', **kwargs):
        return status.cobertura(self.con, uf, **kwargs)

    def test_27_ufs_ordenadas_incluindo_zeros(self):
        d = status.cobertura(self.con)
        self.assertEqual([e['numero'] for e in d['estados']], list(range(1,28)))
        self.assertEqual([e['uf'] for e in d['estados']], ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO'])
        self.assertEqual(d['totais']['total'], 0)

    def test_inmetro_nao_transforma_radar_estadual_em_federal(self):
        pid,_ = self.cadastro(self.fonte('GOINFRA', esfera='estadual'))
        self.cadastro(self.fonte(ColetorINMETRO.FONTE['nome']), ponto=pid)
        self.faixa(pid,1); self.faixa(pid,2)
        self.assertEqual(self.estado()['estado']['estadual'], 1)
        self.assertEqual(self.estado()['estado']['federal'], 0)
        self.assertEqual(len(self.estado()['fontes']),2)

    def test_so_inmetro_sem_esfera_comprovada(self):
        self.cadastro(self.fonte('INMETRO / PSIE'))
        d = self.estado()
        self.assertEqual(d['estado']['nao_classificado'], 1)
        self.assertEqual(d['estado']['federal'], 0)

    def test_classifica_por_fonte_nao_pela_rodovia(self):
        pid,_=self.cadastro(self.fonte('Municipio', esfera='municipal'))
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET via_id=? WHERE id=?', (self.via('BR-153'),pid))
        self.assertEqual(self.estado()['estado']['municipal'],1)

    def test_fiscalizador_prevalece_sobre_publicador(self):
        pid,_=self.cadastro(self.fonte('Publicador federal'))
        fid=self.fonte('Fiscalizador municipal', esfera='municipal')
        oid=db.scalar(self.con, 'SELECT organizacao_id FROM FONTE WHERE id=?',(fid,))
        db.insert(self.con,'PONTO_ORGANIZACAO',dict(ponto_id=pid,organizacao_id=oid,papel_id=db.domain_id(self.con,'PAPEL_ORGANIZACAO','fiscalizador')))
        self.assertEqual(self.estado()['estado']['municipal'],1)

    def test_esferas_divergentes_nao_contam_em_duas_colunas(self):
        pid,_=self.cadastro(self.fonte('Estadual', esfera='estadual'))
        self.cadastro(self.fonte('Municipal', esfera='municipal'),ponto=pid)
        d=self.estado()
        self.assertEqual(d['estado']['total'],1)
        self.assertEqual(d['estado']['nao_classificado'],1)
        self.assertEqual(d['pontos'][0]['classificacao'],'conflitante')

    def test_distrital_conta_como_estadual_no_df(self):
        self.cadastro(self.fonte('DETRAN DF', esfera='distrital'),uf='DF')
        self.assertEqual(self.estado('DF')['estado']['estadual'],1)

    def test_sem_gps_municipio_ou_fonte_nao_desaparece(self):
        self.ponto()
        pid,_=self.cadastro(self.fonte('Estadual',esfera='estadual'))
        self.con.execute('UPDATE PONTO_FISCALIZACAO SET situacao_operacional_id=? WHERE id=?', (db.domain_id(self.con,'SITUACAO_OPERACIONAL','inativo'),pid))
        d=status.cobertura(self.con)
        self.assertEqual(d['totais']['total'],2)
        self.assertEqual(d['sem_uf']['total'],1)
        self.assertEqual(self.estado()['pontos'][0]['latitude'],None)

    def test_removidos_e_desabilitados_nao_reaparecem_na_contagem(self):
        governanca.garantir_esquema(self.con)
        f=self.fonte('Estado',esfera='estadual')
        for campo,valor in [('removido_em','2026-10-22'),('verificacao_status','desabilitado')]:
            pid,_=self.cadastro(f)
            self.con.execute('UPDATE PONTO_FISCALIZACAO SET '+campo+'=? WHERE id=?',(valor,pid))
        self.assertEqual(status.cobertura(self.con)['totais']['total'],0)

    def test_unificacao_e_reversao_contam_uma_vez_preservando_fontes(self):
        a,ra=self.cadastro(self.fonte('A',esfera='estadual'))
        b,rb=self.cadastro(self.fonte('B',esfera='estadual'))
        regra=db.insert(self.con,'REGRA_DEDUPLICACAO',dict(versao='teste-status',descricao='teste',configuracao_serializada='{}',inicio_validade='2026-10-22'))
        cand=db.insert(self.con,'CANDIDATO_DUPLICIDADE',dict(registro_a_id=ra,registro_b_id=rb,regra_id=regra,estado='pendente',gerado_em='2026-10-22'))
        decisao=dedup.decidir(self.con,cand,'unificar','revisor','Local confirmado',escopo='ponto')
        dedup.aplicar(self.con,cand,'revisor')
        d=self.estado()
        self.assertEqual(d['estado']['total'],1)
        self.assertEqual({f['nome'] for f in d['fontes']},{'A','B'})
        dedup.reverter_decisao(self.con,decisao,'revisor','Reavaliar')
        self.assertEqual(self.estado()['estado']['total'],2)

    def test_paginacao_sem_perder_ou_duplicar_pontos(self):
        f=self.fonte('Estado',esfera='estadual')
        ids=[self.cadastro(f)[0] for _ in range(5)]
        d=self.estado(limite=2)
        self.assertEqual(d['estado']['total'],5)
        vistos=[p['id'] for p in d['pontos']]
        while d['proximo_depois'] is not None:
            d=self.estado(limite=2,depois=d['proximo_depois'])
            vistos += [p['id'] for p in d['pontos']]
        self.assertEqual(vistos,['P-%s'%i for i in ids])

    def test_somente_leitura_sem_rede(self):
        self.cadastro(self.fonte('Estado',esfera='estadual'))
        self.con.commit();self.con.execute('PRAGMA query_only=ON')
        with patch('urllib.request.urlopen',side_effect=AssertionError('rede proibida')):
            status.cobertura(self.con)
            status.coletores(self.con)


class TestLeitoresStatus(BaseDedup):
    def execucao(self, recurso, estado, quando=None, **campos):
        return db.insert(self.con,'EXECUCAO_COLETA',dict(recurso_id=recurso,
            iniciada_em=quando or '2026-10-22T10:00:00+00:00',
            terminada_em=quando or '2026-10-22T10:00:00+00:00',status=estado,tentativas=1,**campos))

    def test_erro_posterior_nao_apaga_ultimo_sucesso(self):
        r=self.recurso(self.fonte('DNIT'))
        ok=self.execucao(r,'sem_mudanca')
        erro=self.execucao(r,'erro','2026-10-22T11:00:00+00:00',erro_codigo='http',erro_detalhe='Falha HTTP 503',http_status=503)
        db.insert(self.con,'ERRO_VALIDACAO',dict(execucao_id=erro,codigo_erro='download',descricao='Servidor indisponivel',severidade='erro',registrado_em='2026-10-22'))
        d=status.coletores(self.con,agenda={})['coletores'][0]
        self.assertEqual(d['estado'],'erro')
        self.assertEqual(d['ultimo_sucesso']['id'],ok)
        self.assertEqual(d['ultima_tentativa']['id'],erro)
        self.assertEqual(d['erros'][0]['codigo_erro'],'download')

    def test_inclui_leitores_da_agenda_ainda_nao_cadastrados(self):
        d=status.coletores(self.con,agenda={'antt':dict(conector=ColetorANTT,ativo=True,intervalo_s=3600)})
        self.assertEqual(d['total'],1)
        self.assertIsNone(d['coletores'][0]['id'])
        self.assertEqual(d['coletores'][0]['estado'],'nunca_coletado')
        self.assertTrue(d['coletores'][0]['agendado'])

    def test_sem_mudanca_e_ok_atrasado_separados_de_desativado(self):
        f=self.fonte('ANTT')
        a,b=self.recurso(f,'a'),self.recurso(f,'b')
        self.con.execute('UPDATE RECURSO_FONTE SET periodicidade_segundos=3600 WHERE id IN (?,?)',(a,b))
        self.con.execute('UPDATE RECURSO_FONTE SET ativo=0 WHERE id=?',(b,))
        self.execucao(a,'sem_mudanca','2020-01-01T00:00:00+00:00')
        self.execucao(b,'ok','2020-01-01T00:00:00+00:00')
        d=status.coletores(self.con,agenda={})['coletores']
        self.assertEqual(d[0]['estado'],'sem_mudanca')
        self.assertTrue(d[0]['leitura_atrasada'])
        self.assertFalse(d[1]['ativo'])
        self.assertIsNone(d[1]['leitura_atrasada'])

    def test_credenciais_ocultas_em_urls_e_erros(self):
        r=self.recurso(self.fonte('Fonte'))
        self.con.execute('UPDATE RECURSO_FONTE SET url_recurso=? WHERE id=?',('https://login:segredo@exemplo/dados?token=secreto',r))
        self.execucao(r,'erro',erro_detalhe='api_key=chavesecreta')
        texto=json.dumps(status.coletores(self.con,agenda={}))
        for segredo in ['segredo','secreto','chavesecreta']:
            self.assertNotIn(segredo,texto)
        self.assertIn('[oculto]',texto)

    def test_diario_complementa_somente_a_tentativa_correspondente(self):
        r=self.recurso(self.fonte('Fonte'))
        execucao=self.execucao(r,'em_andamento')
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'status.json'
            arquivo.write_text(json.dumps({'fontes':{str(r):dict(execucao_id=execucao,
                estado='interrompido',origem='https://exemplo/dados?token=secreto',erro='Processo terminou')}}))
            with patch('core.caminhos.status_atualizacoes',return_value=str(arquivo)):
                d=status.coletores(self.con,agenda={})['coletores'][0]
                self.assertEqual(d['estado'],'interrompido')
                self.assertNotIn('secreto',d['url_ultima_tentativa'])
                self.assertEqual(d['erro_relatorio_coleta'],'Processo terminou')
                self.execucao(r,'ok')
                d=status.coletores(self.con,agenda={})['coletores'][0]
                self.assertEqual(d['estado'],'ok')
                self.assertIsNone(d['url_ultima_tentativa'])

    def test_diario_invalido_nao_oculta_leitor(self):
        self.recurso(self.fonte('Fonte'))
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'status.json';arquivo.write_text('{invalido')
            with patch('core.caminhos.status_atualizacoes',return_value=str(arquivo)):
                d=status.coletores(self.con,agenda={})
            self.assertEqual(d['total'],1)
            self.assertTrue(d['erro_relatorio'])

    def test_agenda_invalida_ainda_mostra_historico(self):
        self.recurso(self.fonte('Fonte'))
        with patch('coletor.agenda.carregar_agenda',side_effect=ValueError('agenda invalida')):
            d=status.coletores(self.con)
        self.assertEqual(d['total'],1)
        self.assertIn('agenda invalida',d['erro_agenda'])


class TestApiStatus(unittest.TestCase):
    def setUp(self):
        self.path,_=banco_com_antt()

    def req(self,rota,query='',metodo='GET'):
        with patch('core.config.DB_PATH',self.path):
            code,headers,body=nucleo.handle_request(dict(REQUEST_METHOD=metodo,PATH_INFO=rota,QUERY_STRING=query))
        return code,headers,json.loads(body) if isinstance(body,str) else body

    def test_rotas_publicas_get_sem_cache(self):
        for rota in ['/api/v1/status/estados','/api/v1/status/estados/PR','/api/v1/status/coletores']:
            code,headers,d=self.req(rota)
            self.assertEqual(code,200)
            self.assertTrue(d['sucesso'])
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertEqual(self.req(rota,metodo='POST')[0],405)

    def test_uf_e_paginacao_invalidas(self):
        self.assertEqual(self.req('/api/v1/status/estados/XX')[0],422)
        for query in ['limite=0','limite=1001','depois=-1','depois=abc']:
            self.assertEqual(self.req('/api/v1/status/estados/PR',query)[0],422)
        self.assertEqual(self.req('/api/v1/status/estados/PR','formato=xml')[0],400)

    def test_estado_zerado_e_uf_em_minusculas(self):
        d=self.req('/api/v1/status/estados/ac')[2]['resultado']
        self.assertEqual(d['estado']['uf'],'AC')
        self.assertEqual(d['estado']['total'],0)
        self.assertEqual(d['pontos'],[])
