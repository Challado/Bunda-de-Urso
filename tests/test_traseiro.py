"""Federacao real entre tres bancos/API; somente transporte externo e simulado."""
import contextlib
import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.parse
import uuid
from unittest.mock import patch
from core import config, caminhos, db, governanca as gov, traseiro as tr, traseiro_sync as sync, intercambio
from core.contexto_api import atendimento_local
from web import nucleo
from coletor.fontes.base_lwb import ColetorBaseLWB

ROOT=Path(__file__).resolve().parents[1]
RADAR={'latitude':-24.9556,'longitude':-53.4552,'velocidade_geral':80,'uf':'PR','via':'BR-277','km':580.5}
ADMIN={'escopo':'admin','rotulo':'admin de teste'}

class No:
    def __init__(self,pasta,nome,**cfg):
        self.raiz=Path(pasta)/nome; self.raiz.mkdir(); self.dados=self.raiz/'dados'; self.dados.mkdir()
        self.banco=self.dados/'radar.sqlite3'; self.conf=self.raiz/'radar.conf'; self.nome=nome
        self.cfg={'habilitado':'1','acesso':'livre','intervalo_segundos':'1',**{k:str(v) for k,v in cfg.items()}}
        self.salvar()
        with self.ambiente():
            self.conn=db.connect(str(self.banco)); self.identidade=tr.identidade(self.conn)
    def salvar(self):
        self.conf.write_text('[instalacao]\nhome = '+str(ROOT)+'\n[dados]\ndir = '+str(self.dados)+'\nbanco = radar.sqlite3\n[logs]\ndir = logs\n[web]\norigem = https://'+self.nome+'.example.org\nurl = /openclaw/radar/\n[traseiro]\n'+'\n'.join(k+' = '+v for k,v in self.cfg.items())+'\n')
        caminhos.recarregar()
    @contextlib.contextmanager
    def ambiente(self):
        with patch.dict(os.environ,{'RADAR_CONF':str(self.conf)}),patch.multiple(config,DATA_DIR=str(self.dados),DB_PATH=str(self.banco),RAW_DIR=str(self.dados/'raw'),STAGING_DIR=str(self.dados/'staging')):
            caminhos.recarregar()
            yield self
    def info(self):
        with self.ambiente():return tr.identidade(self.conn)
    def publicar(self,doc=None,chave='radar-1',tipo='radar',acao='publicar'):
        with self.ambiente():return tr.publicar(self.conn,tipo,chave,RADAR if doc is None else doc,acao)
    def cadastro(self):
        with self.ambiente():return tr.listar(self.conn,'cadastros')[0]
    def req(self,rota,doc=None,info=None,headers=None,metodo=None):
        with self.ambiente():
            raw=json.dumps(doc).encode() if doc is not None else b''
            env={'PATH_INFO':rota,'REQUEST_METHOD':metodo or ('POST' if doc is not None else 'GET'),'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw))}
            if info:env['HTTP_X_INTERCHANGE_INFO']=tr.cabecalho(info)
            env.update(headers or {})
            return nucleo.handle_request(env,raw)
    def fechar(self):self.conn.close()

class TestTraseiro(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.a=No(self.tmp.name,'a'); self.b=No(self.tmp.name,'b'); self.c=No(self.tmp.name,'c')
        for n in (self.a,self.b,self.c):self.addCleanup(n.fechar)
        self.nos={n.nome+'.example.org':n for n in (self.a,self.b,self.c)}; self.chamadas=[]
        self.transporte=patch.object(sync,'_bytes',side_effect=self.rede); self.transporte.start(); self.addCleanup(self.transporte.stop)
    def rede(self,url,*,dados=None,headers=None):
        p=urllib.parse.urlsplit(url); self.chamadas.append((p.hostname,dados,headers))
        no=self.nos[p.hostname]; rota=urllib.parse.parse_qs(p.query)['rota'][0]
        env={'HTTP_'+k.upper().replace('-','_'):v for k,v in (headers or {}).items()}
        status,_,corpo=no.req(rota,dados,headers=env)
        if status!=200 and 'rede' not in corpo:raise ValueError('HTTP '+str(status)+': '+str(corpo))
        return json.dumps(corpo).encode()
    def par(self,a,b):
        with a.ambiente():return tr.registrar_instancia(a.conn,b.info())
    def trocar(self,a,b):
        with a.ambiente():
            par=a.conn.execute('SELECT * FROM TRASEIRO_INSTANCIA WHERE api_url=?',(b.info()['api_url'],)).fetchone()
            return sync.sincronizar_par(a.conn,dict(par) if par else None,a.info(),api=b.info()['api_url'])
    def liberar(self,a,b):
        velho=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=10)).isoformat()
        a.conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_tentativa=?,ultima_consulta_recebida=? WHERE uuid=?',(velho,velho,b.info()['uuid']));a.conn.commit()
        b.conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_consulta_recebida=? WHERE uuid=?',(velho,a.info()['uuid']));b.conn.commit()
    def test_identidade_persiste_e_bloco_tem_somente_limites_publicos(self):
        primeiro=self.a.info(); self.assertEqual(primeiro,self.a.info())
        self.assertNotEqual(primeiro['uuid'],self.b.info()['uuid'])
        self.assertEqual(set(primeiro['configuracao']),{'intervalo_segundos','lote','max_bytes','parada_programada','parar_em_segundos','retornar_em_segundos','anuncio_id'})
        self.assertNotIn('tokens',json.dumps(primeiro))

    def test_endpoint_publico_na_raiz_nao_cria_barra_dupla(self):
        self.a.conf.write_text(self.a.conf.read_text().replace('url = /openclaw/radar/','url = /'))
        self.assertEqual(self.a.info()['api_url'],'https://a.example.org/api.pse?rota=%2Fapi%2Fv1%2Fintercambio%2Ftrocar')
    def test_registro_automatico_e_blocos_nos_dois_sentidos(self):
        status,_,corpo=self.b.req('/api/v1/intercambio/trocar',{'eventos':[],'depois':0},info=self.a.info())
        self.assertEqual(status,200,corpo)
        self.assertEqual(corpo['rede']['consultado']['uuid'],self.b.info()['uuid'])
        self.assertEqual(corpo['rede']['consultante']['uuid'],self.a.info()['uuid'])
        self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_INSTANCIA'),1)
        self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),0)
    def test_tokens_de_rede_nao_sao_tokens_de_moderacao(self):
        self.b.cfg['acesso']='tokens';self.b.salvar()
        with self.b.ambiente():tr.arquivo_tokens().write_text(json.dumps({'entrada':['x'*32],'saida':{}}))
        for token,status in (('',401),('errado',401),('x'*32,200)):
            s,_,_=self.b.req('/api/v1/intercambio/identidade',info=self.a.info(),headers={'HTTP_AUTHORIZATION':'Bearer '+token})
            self.assertEqual(s,status)
        s,_,_=self.b.req('/api/v1/gestao/traseiro',headers={'HTTP_AUTHORIZATION':'Bearer '+'x'*32})
        self.assertEqual(s,401)
    def test_desativado_nao_aceita_pares_nem_faz_rede(self):
        self.a.cfg['habilitado']='0';self.a.salvar()
        self.assertEqual(self.a.req('/api/v1/intercambio/identidade',info=self.b.info())[0],503)
        with self.a.ambiente(),atendimento_local():self.assertEqual(sync.executar(self.a.conn)['estado'],'desativado')
        self.assertEqual(self.chamadas,[])
    def test_rede_a_b_c_preserva_origem_sem_eco_ou_publicacao_automatica(self):
        self.a.publicar();self.b.publicar(dict(RADAR,latitude=-24.96),chave='outro')
        self.trocar(self.a,self.b);self.liberar(self.a,self.b);self.trocar(self.a,self.b)
        self.trocar(self.c,self.b)
        self.assertEqual(db.scalar(self.c.conn,'SELECT COUNT(*) FROM TRASEIRO_CADASTRO'),2)
        self.assertEqual(db.scalar(self.c.conn,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),0)
        self.assertEqual(db.scalar(self.a.conn,'SELECT COUNT(*) FROM TRASEIRO_EVENTO'),2)
        self.assertEqual(len(self.chamadas),3)  # Uma consulta por rodada, nao uma por pagina/direcao.
        origem=self.c.conn.execute('SELECT origem FROM TRASEIRO_CADASTRO WHERE chave=?',('radar-1',)).fetchone()[0]
        self.assertEqual(origem,self.a.info()['uuid'])
    def test_reenvio_idempotente_e_lote_conflitante_e_atomico(self):
        self.a.publicar()
        with self.a.ambiente():eventos=tr.pagina(self.a.conn)['eventos']
        self.par(self.b,self.a)
        with self.b.ambiente():
            self.assertEqual(tr.receber(self.b.conn,eventos,self.a.info()['uuid'])['novos'],1)
            self.assertEqual(tr.receber(self.b.conn,eventos,self.a.info()['uuid'])['repetidos'],1)
            novo=dict(eventos[0],uuid=str(uuid.uuid4()),chave='novo'); ruim=dict(eventos[0],documento=dict(RADAR,velocidade_geral=40))
            with self.assertRaises(gov.GovernancaError):tr.receber(self.b.conn,[novo,ruim],self.a.info()['uuid'])
            self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_EVENTO'),1)
    def test_peer_nao_pode_criar_revisao_em_nome_do_receptor(self):
        self.par(self.b,self.a);self.a.publicar()
        with self.a.ambiente():e=tr.pagina(self.a.conn)['eventos'][0]
        with self.b.ambiente(),self.assertRaises(gov.GovernancaError):
            tr.receber(self.b.conn,[dict(e,origem=self.b.info()['uuid'])],self.a.info()['uuid'])
    def test_aprovacao_publica_em_fonte_separada_e_nova_revisao_fica_pendente(self):
        self.a.publicar();self.trocar(self.b,self.a);c=self.b.cadastro()
        with self.b.ambiente():
            out=tr.decidir(self.b.conn,c['id'],'aprovar',ADMIN,'Conferido no estudo tecnico publico',c['evento_id'])
            self.assertEqual(out['estado'],'aprovado')
            p=self.b.conn.execute('SELECT * FROM PONTO_FISCALIZACAO WHERE id=?',(out['ponto_id'],)).fetchone()
            self.assertEqual(p['procedencia'],'oficial');self.assertEqual(p['verificacao_status'],'verificado')
            self.assertEqual(self.b.conn.execute('SELECT nome FROM FONTE').fetchone()[0],'TRASEIRO DE URSO - posicoes validadas')
            tr.exportar_pontos(self.b.conn)
            self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_EVENTO WHERE origem=?',(self.b.info()['uuid'],)),0)
        self.a.publicar(dict(RADAR,velocidade_geral=60));self.liberar(self.b,self.a);self.trocar(self.b,self.a)
        self.assertEqual(self.b.cadastro()['estado'],'pendente')
        with self.b.ambiente(),self.assertRaises(gov.GovernancaError):tr.decidir(self.b.conn,c['id'],'aprovar',ADMIN,'Conferido novamente',c['evento_id'])
    def test_removido_local_nao_e_ressuscitado_pela_rede(self):
        self.a.publicar();self.trocar(self.b,self.a);c=self.b.cadastro()
        with self.b.ambiente():
            out=tr.decidir(self.b.conn,c['id'],'aprovar',ADMIN,'Posicao conferida',c['evento_id'])
            gov.remover_radar(self.b.conn,out['ponto_id'],ADMIN,'Equipamento removido')
        self.a.publicar(dict(RADAR,velocidade_geral=60));self.liberar(self.b,self.a);self.trocar(self.b,self.a);c=self.b.cadastro()
        with self.b.ambiente(),self.assertRaises(gov.GovernancaError):tr.decidir(self.b.conn,c['id'],'aprovar',ADMIN,'Posicao conferida',c['evento_id'])
    def test_receita_ensinada_fica_desativada_e_nao_recebe_codigo(self):
        receita={'nome':'Lista publica','url':'https://fonte.example.org/lista.csv','formato':'csv','campos':{'latitude':'lat','longitude':'lon','velocidade_geral':'vel'}}
        self.a.publicar(receita,'nova-fonte','fonte');self.trocar(self.b,self.a)
        self.assertEqual(db.scalar(self.b.conn,'SELECT ativo FROM TRASEIRO_FONTE'),0)
        with self.b.ambiente():
            for doc in (dict(receita,codigo='print(1)'),dict(receita,url='http://127.0.0.1/x'),dict(receita,formato='python')):
                with self.assertRaises(gov.GovernancaError):tr.validar_fonte(doc)
            f=tr.listar(self.b.conn,'fontes')[0]
            tr.ativar_fonte(self.b.conn,f['id'],True,ADMIN,f['evento_id'])
            with patch.object(sync,'_bytes',return_value=b'lat,lon,vel\n-24.9556,-53.4552,80\n'):
                self.assertEqual(sync.coletar_fonte(self.b.conn,f),1)
            self.assertEqual(self.b.cadastro()['estado'],'pendente')
            self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),0)
    def test_tipo_de_inatividade_seleciona_somente_um_criterio(self):
        self.par(self.a,self.b)
        velho=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat()
        self.a.conn.execute('UPDATE TRASEIRO_INSTANCIA SET criado_em=?',(velho,));self.a.conn.commit()
        self.a.cfg.update(inatividade_tipo='tentativas',inatividade_numero='2');self.a.salvar()
        with self.a.ambiente():
            sync.inativar_vencidas(self.a.conn);self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'ativo')
            sync.falha(self.a.conn,self.b.info()['uuid'],ValueError('indisponivel'))
            self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'ativo')
            sync.falha(self.a.conn,self.b.info()['uuid'],ValueError('indisponivel'))
            self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'inativo')
        self.a.cfg['inatividade_tipo']='dias';self.a.salvar()
        self.a.conn.execute("UPDATE TRASEIRO_INSTANCIA SET estado='ativo',falhas=0");self.a.conn.commit()
        with self.a.ambiente():sync.inativar_vencidas(self.a.conn)
        self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'inativo')
    def test_intervalos_sao_independentes_e_uma_rodada_e_uma_consulta(self):
        self.a.cfg['intervalo_segundos']='2';self.a.salvar();self.b.cfg['intervalo_segundos']='600';self.b.salvar()
        self.trocar(self.a,self.b)
        recente=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=3)).isoformat()
        self.a.conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_tentativa=?',(recente,));self.a.conn.commit()
        with self.a.ambiente(),atendimento_local():sync.executar(self.a.conn)
        self.assertEqual(len(self.chamadas),1) # A respeita B=600, apesar de A=2.
        self.b.conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_tentativa=?',(recente,));self.b.conn.commit()
        with self.b.ambiente(),atendimento_local():sync.executar(self.b.conn)
        self.assertEqual(len(self.chamadas),2) # B consulta A apos 2, sem esperar seus 600.
    def test_servidor_informa_adiamento_quando_consultado_antes_do_prazo(self):
        self.b.cfg['intervalo_segundos']='600';self.b.salvar()
        self.trocar(self.a,self.b)
        self.assertEqual(self.trocar(self.a,self.b)['estado'],'adiado')
        self.assertEqual(db.scalar(self.a.conn,'SELECT falhas FROM TRASEIRO_INSTANCIA'),0)
    def test_parado_permanente_nao_consulta_e_deve_zerar_aviso_para_voltar(self):
        self.par(self.b,self.a)
        self.a.cfg.update(parada_programada='1',parar_em_segundos='0',retornar_em_segundos='0');self.a.salvar()
        with self.a.ambiente(),atendimento_local():self.assertEqual(sync.executar(self.a.conn)['estado'],'pausado')
        self.assertEqual(self.chamadas,[])
        s,_,corpo=self.b.req('/api/v1/intercambio/trocar',{'eventos':[]},info=self.a.info())
        self.assertEqual(s,403,corpo)
        self.a.cfg.update(parada_programada='0',parar_em_segundos='0',retornar_em_segundos='0');self.a.salvar()
        self.assertFalse(self.a.info()['configuracao']['parada_programada'])
        self.assertEqual(self.trocar(self.a,self.b)['estado'],'ok')
    def test_pausa_temporaria_nao_acumula_falhas_e_retorna_automaticamente(self):
        self.b.cfg.update(parada_programada='1',parar_em_segundos='0',retornar_em_segundos='3600');self.b.salvar()
        self.trocar(self.a,self.b)
        self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'pausado')
        self.assertEqual(db.scalar(self.a.conn,'SELECT falhas FROM TRASEIRO_INSTANCIA'),0)
        futuro=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)
        with self.a.ambiente():sync.inativar_vencidas(self.a.conn,futuro)
        self.assertEqual(db.scalar(self.a.conn,'SELECT estado FROM TRASEIRO_INSTANCIA'),'ativo')
        anterior=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=2)).isoformat()
        self.b.conn.execute('UPDATE TRASEIRO_LOCAL SET aviso_em=?',(anterior,));self.b.conn.commit()
        self.assertFalse(self.b.info()['configuracao']['parada_programada'])
    def test_anuncio_de_parada_nao_reinicia_contagem_em_cada_consulta(self):
        self.a.cfg.update(parada_programada='1',parar_em_segundos='3600',retornar_em_segundos='0');self.a.salvar()
        antes=self.a.info();self.assertTrue(antes['configuracao']['parada_programada'])
        hora=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=100)).isoformat()
        self.a.conn.execute('UPDATE TRASEIRO_LOCAL SET aviso_em=?',(hora,));self.a.conn.commit()
        depois=self.a.info();self.assertLessEqual(depois['configuracao']['parar_em_segundos'],3500)
        self.assertEqual(self.a.info()['configuracao']['anuncio_id'],depois['configuracao']['anuncio_id'])
    def test_ack_perdido_nao_avanca_cursor_e_reenvio_nao_duplica(self):
        self.a.publicar();self.trocar(self.a,self.b);self.liberar(self.a,self.b)
        original=sync.requisitar
        def perder(*a,**kw):
            original(*a,**kw);raise TimeoutError('ACK perdido')
        with self.a.ambiente(),patch.object(sync,'requisitar',side_effect=perder),self.assertRaises(TimeoutError):
            par=dict(self.a.conn.execute('SELECT * FROM TRASEIRO_INSTANCIA').fetchone())
            sync.sincronizar_par(self.a.conn,par,self.a.info())
        self.assertEqual(db.scalar(self.a.conn,'SELECT cursor_saida FROM TRASEIRO_INSTANCIA'),0)
        self.liberar(self.a,self.b);self.trocar(self.a,self.b)
        self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_CADASTRO'),1)
    def test_outbox_captura_insercao_e_remocao_canonicas_sem_varrer_a_base(self):
        with self.a.ambiente():
            coletor=ColetorBaseLWB(conn=self.a.conn);coletor.ingerir_registros([dict(RADAR,identificador='meu')])
            self.assertGreater(db.scalar(self.a.conn,'SELECT COUNT(*) FROM TRASEIRO_PONTO_PENDENTE'),0)
            tr.exportar_pontos(self.a.conn);self.assertEqual(db.scalar(self.a.conn,'SELECT COUNT(*) FROM TRASEIRO_EVENTO'),1)
            pid=db.scalar(self.a.conn,'SELECT id FROM PONTO_FISCALIZACAO')
            gov.remover_radar(self.a.conn,pid,ADMIN,'Removido no local')
            tr.exportar_pontos(self.a.conn)
            self.assertEqual(self.a.conn.execute('SELECT acao FROM TRASEIRO_EVENTO ORDER BY seq DESC').fetchone()[0],'retirar')
    def test_gestao_exige_papel_e_nao_expoe_token(self):
        with self.a.ambiente():
            _,token=gov.emitir_token(self.a.conn,'teste','contribuidor')
        s,_,corpo=self.a.req('/api/v1/gestao/traseiro',headers={'HTTP_X_API_TOKEN':token})
        self.assertEqual(s,200,corpo);self.assertNotIn(token,json.dumps(corpo))
        s,_,_=self.a.req('/api/v1/gestao/traseiro/fontes',{'chave':'f','receita':{}},headers={'HTTP_X_API_TOKEN':token})
        self.assertEqual(s,403)

    def test_cliente_independente_de_outro_sistema_e_endpoint_sem_pse(self):
        # Carrega o arquivo isoladamente, sem importar nenhuma dependencia do Radar.
        import importlib.util
        spec=importlib.util.spec_from_file_location('cliente_generico',ROOT/'core/intercambio.py')
        cliente=importlib.util.module_from_spec(spec);spec.loader.exec_module(cliente)
        info=dict(self.a.info(),uuid=str(uuid.uuid4()),nome='Sistema de mobilidade externo',
                  aplicacao='Outro produto',api_url='https://externo.example.org/services/exchange',
                  capacidades={'tipos_evento':[]})
        self.b.publicar()
        def transporte(req,timeout):
            return self.rede(req.full_url,dados=json.loads(req.data),headers=dict(req.header_items()))
        doc=cliente.consultar(self.b.info()['api_url'],info,transporte=transporte)
        self.assertEqual(doc['rede']['consultante']['aplicacao'],'Outro produto')
        self.assertEqual(doc['resultado']['eventos'],[]) # Nao envia tipo que o sistema nao aceita.
        self.assertGreater(doc['resultado']['cursor'],0)
        self.assertEqual(db.scalar(self.b.conn,'SELECT api_url FROM TRASEIRO_INSTANCIA'),info['api_url'])

    def test_cliente_generico_importa_radares_ao_anunciar_o_adaptador(self):
        info=dict(self.a.info(),aplicacao='Inventario de outro fornecedor')
        evento={'uuid':str(uuid.uuid4()),'origem':info['uuid'],'tipo':'radar.v1','chave':'externo',
                'revisao':1,'acao':'publicar','documento':RADAR}
        def transporte(req,timeout):
            return self.rede(req.full_url,dados=json.loads(req.data),headers=dict(req.header_items()))
        doc=intercambio.consultar(self.b.info()['api_url'],info,eventos=[evento],transporte=transporte)
        self.assertEqual(doc['resultado']['recebidos'],1)
        self.assertEqual(self.b.cadastro()['estado'],'pendente')

    def test_reducao_de_capacidade_e_renegociada_sem_perder_lote(self):
        self.a.publicar();self.a.publicar(dict(RADAR,latitude=-24.96),chave='segundo')
        self.trocar(self.a,self.b)
        self.b.cfg['lote']='1';self.b.salvar();self.liberar(self.a,self.b)
        with self.assertRaises(ValueError):self.trocar(self.a,self.b)
        self.assertEqual(db.scalar(self.a.conn,'SELECT lote FROM TRASEIRO_INSTANCIA'),1)
        self.assertEqual(db.scalar(self.a.conn,'SELECT cursor_saida FROM TRASEIRO_INSTANCIA'),0)
        self.liberar(self.a,self.b);self.trocar(self.a,self.b)
        self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_CADASTRO'),1)
        self.liberar(self.a,self.b);self.trocar(self.a,self.b)
        self.assertEqual(db.scalar(self.b.conn,'SELECT COUNT(*) FROM TRASEIRO_CADASTRO'),2)

    def test_outbox_nao_perde_mudanca_concorrente_da_coleta(self):
        with self.a.ambiente():
            ColetorBaseLWB(conn=self.a.conn).ingerir_registros([dict(RADAR,identificador='concorrente')])
            original=tr.publicar
            def mudar_depois(*args,**kwargs):
                retorno=original(*args,**kwargs)
                self.a.conn.execute('UPDATE POSICAO_GEOGRAFICA SET latitude=-24.97')
                self.a.conn.commit()
                return retorno
            with patch.object(tr,'publicar',side_effect=mudar_depois):tr.exportar_pontos(self.a.conn)
            self.assertEqual(db.scalar(self.a.conn,'SELECT COUNT(*) FROM TRASEIRO_PONTO_PENDENTE'),1)
            tr.exportar_pontos(self.a.conn)
            self.assertEqual(db.scalar(self.a.conn,'SELECT COUNT(*) FROM TRASEIRO_PONTO_PENDENTE'),0)
            evento=self.a.conn.execute('SELECT documento FROM TRASEIRO_EVENTO ORDER BY seq DESC').fetchone()[0]
            self.assertEqual(json.loads(evento)['latitude'],-24.97)
