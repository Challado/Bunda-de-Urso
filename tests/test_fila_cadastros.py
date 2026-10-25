"""Fila real em disco: ACK sem SQLite, retomada, concorrencia e privacidade."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from core import config, db, fila_cadastros as fila, governanca
from tests import test_governanca as suporte
from web import nucleo


class TestFilaCadastros(suporte.BaseGov):
    dados = {'latitude':-24.9555, 'longitude':-53.4552, 'velocidade_geral':60}

    def pedir(self, dados=None, protocolo=None):
        env = {'REQUEST_METHOD':'GET' if protocolo else 'POST',
               'PATH_INFO':'/api/v1/radares/envios/'+protocolo if protocolo else '/api/v1/radares/submeter',
               'CONTENT_TYPE':'application/json', 'HTTP_PREFER':'respond-async',
               'REMOTE_ADDR':'192.0.2.21', 'HTTP_USER_AGENT':'Agente privado de teste'}
        return nucleo.handle_request(env, b'' if protocolo else json.dumps(self.dados if dados is None else dados).encode())

    def receber(self, dados=None):
        status, headers, corpo = self.pedir(dados)
        self.assertEqual(status,202,corpo)
        self.assertEqual(headers['Preference-Applied'],'respond-async')
        return corpo['resultado']

    def test_ack_duravel_sem_banco_e_consulta_nao_expoe_dados_privados(self):
        with patch.object(nucleo,'_conn',side_effect=AssertionError('nao abrir SQLite')):
            r = self.receber({**self.dados,'contato':'contato-privado@example.invalid'})
            status, headers, corpo = self.pedir(protocolo=r['protocolo'])
        self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(corpo['resultado']['estado'],'recebido')
        texto=json.dumps(corpo)
        for segredo in ('contato-privado','192.0.2.21','Agente privado','procedencia','dados'):
            self.assertNotIn(segredo,texto)
        arquivo=fila.pasta()/'pendentes'/(r['protocolo']+'.json')
        self.assertEqual(json.loads(arquivo.read_text())['dados']['contato'],'contato-privado@example.invalid')
        self.assertEqual(arquivo.stat().st_mode & 0o777,0o660)
        self.assertEqual(arquivo.parent.stat().st_mode & 0o7777,0o2770)
        with closing(db.connect_readonly(config.DB_PATH)) as conn:
            self.assertEqual(db.scalar(conn,'SELECT count(*) FROM PONTO_FISCALIZACAO'),0)

    def test_cadastro_e_worker_com_dados_dentro_da_raiz_web(self):
        web = Path(config.DATA_DIR) / 'site'
        dados = web / 'dados'
        dados.mkdir(parents=True)
        banco = dados / 'radar.sqlite3'
        shutil.copyfile(config.DB_PATH, banco)
        conf = web / 'radar.conf'
        conf.write_text('[dados]\ndir = dados\nbanco = radar.sqlite3\n[web]\nraiz = .\n')
        with patch.object(config, 'DATA_DIR', str(dados)), patch.object(config, 'DB_PATH', str(banco)), \
             patch.object(fila.caminhos, 'web_raiz', return_value=str(web)):
            with patch.object(nucleo, '_conn', side_effect=AssertionError('ACK sem SQLite')):
                r = self.receber()
            arquivo = dados / 'fila-cadastros/pendentes' / (r['protocolo'] + '.json')
            self.assertTrue(arquivo.is_file())
            self.assertEqual(arquivo.stat().st_mode & 0o777, 0o660)
            env = {k:v for k,v in os.environ.items() if k not in ('REQUEST_METHOD', 'GATEWAY_INTERFACE')}
            env['RADAR_CONF'] = str(conf)
            processo = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / 'web/api.pse'), 'cron', 'fila'],
                env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(processo.returncode, 0, processo.stdout + processo.stderr)
            self.assertEqual(fila.consultar(r['protocolo'])['estado'], 'processado')
            with closing(db.connect_readonly(banco)) as conn:
                self.assertEqual(db.scalar(conn, 'SELECT count(*) FROM PONTO_FISCALIZACAO'), 1)

    def test_fila_nao_escapa_de_dados_por_link_simbolico(self):
        externo = Path(config.DATA_DIR).parent / (Path(config.DATA_DIR).name + '-externo')
        externo.mkdir()
        self.addCleanup(externo.rmdir)
        (Path(config.DATA_DIR) / 'fila-cadastros').symlink_to(externo, target_is_directory=True)
        status, _, corpo = self.pedir()
        self.assertEqual(status, 503)
        self.assertFalse(corpo['sucesso'])
        self.assertEqual(list(externo.iterdir()), [])

    def test_reenvio_usa_o_mesmo_protocolo_antes_e_depois_do_processamento(self):
        r=self.receber()
        self.assertEqual(self.receber()['protocolo'],r['protocolo'])
        self.assertTrue(self.receber()['reenvio'])
        self.assertEqual(len(list((fila.pasta()/'pendentes').glob('*.json'))),1)
        self.assertEqual(fila.processar()['processados'],1)
        final=fila.consultar(r['protocolo'])
        self.assertEqual(final['estado'],'processado')
        ponto=final['resultado']['cadastros'][0]['id']
        self.assertEqual(self.receber()['resultado']['cadastros'][0]['id'],ponto)
        self.assertEqual(fila.processar()['processados'],0)
        with closing(db.connect_readonly(config.DB_PATH)) as conn:
            self.assertEqual(db.scalar(conn,'SELECT count(*) FROM PONTO_FISCALIZACAO'),1)

    def test_reinicio_apos_commit_antes_de_finalizar_nao_duplica_radar(self):
        r=self.receber()
        with patch.object(fila,'_finalizar',side_effect=KeyboardInterrupt('processo encerrado')):
            with self.assertRaises(KeyboardInterrupt):
                fila.processar()
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'processando')
        self.assertEqual(fila.processar()['processados'],1)
        final=fila.consultar(r['protocolo'])
        self.assertEqual(final['resultado']['ja_cadastrados'],1)
        with closing(db.connect_readonly(config.DB_PATH)) as conn:
            self.assertEqual(db.scalar(conn,'SELECT count(*) FROM PONTO_FISCALIZACAO'),1)

    def test_falha_de_disco_nunca_devolve_202(self):
        fila._preparar()
        with patch.object(fila.os,'fsync',side_effect=OSError('disco cheio')):
            status,_,corpo=self.pedir()
        self.assertEqual(status,503)
        self.assertFalse(corpo['sucesso'])
        self.assertEqual(list((fila.pasta()/'pendentes').glob('*.json')),[])

    def test_limite_por_ip_e_capacidade_sem_cobrar_reenvio(self):
        with patch.object(config,'SUBMISSAO_LIMITE',1):
            self.receber()
            self.receber()
            self.assertEqual(self.pedir({**self.dados,'velocidade_geral':61})[0],429)
        original=fila.caminhos.inteiro
        with patch.object(fila.caminhos,'inteiro',side_effect=lambda s,k:1 if (s,k)==('cadastro','max_pendentes') else original(s,k)):
            self.assertEqual(self.pedir({**self.dados,'velocidade_geral':62})[0],503)

    def test_processador_exclusivo_e_pedido_continua_salvo(self):
        r=self.receber()
        with fila._trava('processador.lock'):
            self.assertTrue(fila.processar()['ocupado'])
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'recebido')

    def test_rejeicao_geografica_e_feita_depois_do_ack(self):
        with closing(db.connect(config.DB_PATH)) as conn:
            governanca.criar_bloqueio(conn,'zona_sombra',-24.9555,-53.4552,200,'Area de teste',None)
        r=self.receber()
        self.assertEqual(r['estado'],'recebido')
        self.assertEqual(fila.processar()['rejeitados'],1)
        final=fila.consultar(r['protocolo'])
        self.assertEqual(final['estado'],'rejeitado')
        self.assertEqual(final['erro']['codigo'],'area_bloqueada')

    def test_falha_temporaria_preserva_origem_e_admite_reprocessamento(self):
        r=self.receber()
        with patch.object(governanca,'submeter',side_effect=OSError('segredo-interno-nao-publicar')):
            self.assertEqual(fila.processar()['adiados'],1)
        arquivo,doc=fila._localizar(r['protocolo'])
        self.assertEqual(doc['estado'],'aguardando_nova_tentativa')
        self.assertEqual(doc['dados'],self.dados)
        self.assertNotIn('segredo-interno',json.dumps(fila.consultar(r['protocolo'])))
        doc['proxima_tentativa']=0;doc['tentativas']=100;fila._gravar(arquivo,doc)
        with patch.object(governanca,'submeter',side_effect=OSError()):
            self.assertEqual(fila.processar()['falharam'],1)
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'falhou')
        fila.reprocessar(r['protocolo'])
        self.assertEqual(fila.processar()['processados'],1)

    def test_origem_corrompida_e_preservada_e_protocolo_informa_falha(self):
        r=self.receber()
        arquivo,_=fila._localizar(r['protocolo'])
        arquivo.write_text('JSON corrompido')
        self.assertEqual(fila.processar()['falharam'],1)
        self.assertEqual((fila.pasta()/'quarentena'/arquivo.name).read_text(),'JSON corrompido')
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'falhou')

    def test_hash_divergente_nao_e_processado_e_origem_fica_preservada(self):
        r=self.receber()
        arquivo,doc=fila._localizar(r['protocolo'])
        doc['dados']['velocidade_geral']=90
        fila._gravar(arquivo,doc)
        self.assertEqual(fila.processar()['falharam'],1)
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'falhou')
        with closing(db.connect_readonly(config.DB_PATH)) as conn:
            self.assertEqual(db.scalar(conn,'SELECT count(*) FROM PONTO_FISCALIZACAO'),0)

    def test_lock_de_entrada_impede_worker_de_consumir_envio_ainda_nao_confirmado(self):
        r=self.receber()
        with fila._trava('entrada.lock'):
            self.assertTrue(fila.processar()['ocupado'])
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'recebido')
        self.assertEqual(fila.processar()['processados'],1)

    def test_banco_ausente_nao_cria_base_vazia_e_mantem_envio_para_repetir(self):
        r=self.receber()
        Path(config.DB_PATH).unlink()
        self.assertEqual(fila.processar()['adiados'],1)
        self.assertFalse(Path(config.DB_PATH).exists())
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'aguardando_nova_tentativa')

    def test_retencao_nao_apaga_pendente_nem_falha_nao_resolvida(self):
        r=self.receber()
        pendente,_=fila._localizar(r['protocolo'])
        os.utime(pendente,(0,0))
        outro=self.receber({**self.dados,'velocidade_geral':61})
        arquivo,doc=fila._localizar(outro['protocolo'])
        doc['erro']={'codigo':'teste','mensagem':'Revisar'}
        fila._finalizar(arquivo,doc,'falhou')
        falhou,_=fila._localizar(outro['protocolo'])
        os.utime(falhou,(0,0))
        fila._limpar()
        self.assertTrue(pendente.is_file())
        self.assertTrue(falhou.is_file())

    def test_api_local_em_outro_processo_consome_o_json(self):
        r=self.receber()
        conf=Path(config.DATA_DIR)/'radar.conf'
        conf.write_text('[dados]\ndir = '+config.DATA_DIR+'\nbanco = '+Path(config.DB_PATH).name+'\n')
        env={**os.environ,'RADAR_CONF':str(conf)}
        for k in ('REQUEST_METHOD','GATEWAY_INTERFACE'):
            env.pop(k,None)
        p=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'web'/'api.pse'),'fila','processar'],
                         env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(fila.consultar(r['protocolo'])['estado'],'processado')

    def test_protocolo_invalido_e_payload_invalido_nao_abrem_banco(self):
        with patch.object(nucleo,'_conn',side_effect=AssertionError('sem SQLite')):
            self.assertEqual(self.pedir(protocolo='../../radar.conf')[0],404)
            self.assertEqual(self.pedir(protocolo='f'*32)[0],404)
            self.assertEqual(self.pedir({'latitude':999,'longitude':0})[0],422)
