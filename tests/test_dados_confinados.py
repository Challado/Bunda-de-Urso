"""Contrato: uma configuracao, uma raiz de dados, sem escapes por ambiente/links."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from core import caminhos, configuracao, config


class DadosConfinados(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='radar-confinado-')
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.dados=self.base/'dados'
        self.dados.mkdir()
        self.conf=self.base/'radar.conf'
        self.conf.write_text('[dados]\ndir = '+str(self.dados)+'\nbanco = radar.sqlite3\n')
        self.env=patch.dict(os.environ,RADAR_CONF=str(self.conf))
        self.env.start();self.addCleanup(self.env.stop);self.addCleanup(caminhos.recarregar)
        caminhos.recarregar()

    def test_banco_nome_e_arquivos_operacionais_resolvem_dentro_dados(self):
        self.assertEqual(caminhos.banco(),str(self.dados/'radar.sqlite3'))
        self.assertEqual(caminhos.token_arquivo(),str(self.dados/'api_token'))
        self.assertEqual(caminhos.log_dir(),str(self.dados/'logs'))
        for secao,chave in [('logs','dir'),('api','token_arquivo'),('assistente','chave_arquivo'),('geografia','malha'),('sincronizacao','clone')]:
            with self.subTest(secao=secao):
                self.conf.write_text('[dados]\ndir = '+str(self.dados)+'\n['+secao+']\n'+chave+' = sub/item\n')
                caminhos.recarregar()
                self.assertEqual(caminhos.caminho(secao,chave),str(self.dados/'sub/item'))

    def test_configuracao_e_ambiente_nao_podem_escapar_da_raiz(self):
        with patch.dict(os.environ,RADAR_DB='/tmp/outro.sqlite3',RADAR_DATA_DIR='/tmp/outro',RADAR_LOG_DIR='/tmp/log',RADAR_API_TOKEN_FILE='/tmp/token',OLLAMA_URL='http://errado.example',RADAR_IA_HABILITADA='1'):
            self.assertEqual(caminhos.data_dir(),str(self.dados))
            self.assertEqual(caminhos.banco(),str(self.dados/'radar.sqlite3'))
            self.assertEqual(caminhos.valor('assistente','url')[0],'http://127.0.0.1:11434')
            self.assertEqual(caminhos.inteiro('assistente','habilitado'),0)
        for secao,chave in [('dados','banco'),('logs','dir'),('api','token_arquivo'),('assistente','chave_arquivo'),('geografia','malha'),('sincronizacao','clone')]:
            for valor in ('../fora','/tmp/fora'):
                with self.subTest(secao=secao,valor=valor):
                    texto='[dados]\ndir = '+str(self.dados)+'\n'
                    texto += ('' if secao=='dados' else '['+secao+']\n')+chave+' = '+valor+'\n'
                    self.conf.write_text(texto);caminhos.recarregar()
                    with self.assertRaises(ValueError):
                        caminhos.banco() if secao=='dados' else caminhos.caminho(secao,chave)

    def test_symlinks_nao_podem_apontar_para_fora(self):
        (self.base/'fora').mkdir()
        (self.dados/'sub').symlink_to(self.base/'fora',target_is_directory=True)
        with self.assertRaises(ValueError):caminhos.dentro_dados('sub/token')
        (self.dados/'radar.sqlite3').symlink_to(self.base/'outro.sqlite3')
        with self.assertRaises(ValueError):caminhos.banco()

    def test_credencial_apenas_do_arquivo_e_nao_do_ambiente(self):
        with patch.dict(os.environ,RADAR_API_TOKEN='ignorar-ambiente'):
            self.assertEqual(config.token_ingestao(),'')
            (self.dados/'api_token').write_text('credencial-do-arquivo')
            self.assertEqual(config.token_ingestao(),'credencial-do-arquivo')

    def test_editor_consolida_secoes_sem_perder_valores_e_sem_campos_de_identidade(self):
        texto='[instalacao]\nusuario = alguem\ngrupo = outro\nhome = .\n[assistente]\nurl = http://127.0.0.1:11434\n[api]\nmax_body = 16384\n[assistente]\nmodelo = preservar\nhabilitado = 0\n[api]\ntoken_arquivo = api_token\n'
        novo=configuracao._editar(texto,{('assistente','timeout'):'25'})
        self.assertEqual(novo.count('[assistente]'),1)
        self.assertEqual(novo.count('[api]'),1)
        self.assertIn('modelo = preservar',novo)
        self.assertIn('timeout = 25',novo)
        self.assertNotIn('usuario =',novo)
        self.assertNotIn('grupo =',novo)
        self.assertEqual(configuracao._editar(novo,{}),novo)

    def test_api_local_nao_pode_abrir_banco_fora_de_dados_nem_por_uri(self):
        from core import db
        from core.contexto_api import atendimento_local
        fora=self.base/'fora.sqlite3'
        with atendimento_local(), patch.object(config,'DATA_DIR',str(self.dados)):
            with self.assertRaises(ValueError):db.connect(fora)
            with self.assertRaises(ValueError):db.connect(fora.as_uri()+'?mode=rwc',uri=True)
        self.assertFalse(fora.exists())

    def test_importacao_local_pela_api_recusa_arquivo_fora_de_dados(self):
        import subprocess,sys
        root=Path(__file__).resolve().parents[1]
        r=subprocess.run([sys.executable,str(root/'web/api.pse'),'sync','--fonte','antt','--arquivo',str(root/'tests/fixtures/antt_radares_fixture.json')],env=dict(os.environ,RADAR_CONF=str(self.conf)),capture_output=True,text=True,timeout=20)
        self.assertNotEqual(r.returncode,0)
        self.assertIn('dentro de [dados] dir',r.stderr+r.stdout)
