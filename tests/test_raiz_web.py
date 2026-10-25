"""Migracao real pela API, sem nginx/cron do sistema no laboratorio."""
from contextlib import closing
import getpass
import pwd
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import caminhos, db
from core.raiz_web import _cron, _bloqueios_http
from core.protecao_configuracao import proteger_texto

ROOT = Path(__file__).resolve().parents[1]


class TestRaizWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='radar-raiz-')
        self.addCleanup(self.tmp.cleanup)
        self.lab = Path(self.tmp.name)
        self.home = self.lab/'bin/radar'
        self.home.mkdir(parents=True)
        self.web = self.lab/'www/radar'
        self.web.mkdir(parents=True)
        (self.web/'api.pse').write_text('# anterior')
        self.conf = self.lab/'etc/radar.conf'
        self.conf.parent.mkdir()
        self.dados = self.lab/'dados'
        self.dados.mkdir()
        self.logs = self.lab/'logs'
        self.logs.mkdir()
        (self.logs/'tick.log').write_text('historico anterior\n')
        self.db = self.dados/'radar.sqlite3'
        with closing(db.connect(self.db)) as con:
            db.init_db(con)
            con.execute('CREATE TABLE SENTINELA (valor TEXT)')
            con.execute("INSERT INTO SENTINELA VALUES ('preservar')")
            con.execute("INSERT INTO ORGANIZACAO (nome,tipo_organizacao_id) VALUES ('Teste', (SELECT id FROM TIPO_ORGANIZACAO LIMIT 1))")
            con.execute("INSERT INTO FONTE (organizacao_id,natureza_id,nome,url_institucional,esfera,situacao) VALUES (1, (SELECT id FROM NATUREZA_FONTE WHERE codigo='oficial'),'Teste','https://teste.example','federal','ativa')")
            con.execute("INSERT INTO RECURSO_FONTE (fonte_id, nome, url_recurso, formato_origem, ativo, status_integracao) VALUES (1, 'Teste', 'https://teste.example/recurso', 'json', 1, 'ativo')")
            con.execute("INSERT INTO ARTEFATO_COLETA (recurso_id,hash_sha256,caminho_cache,bytes_arquivo,baixado_em,resultado_validacao) VALUES (1, ?, ?, 19, '2026-10-24', 'valido')", ('a'*64,str(self.dados/'raw/evidencia.txt')))
            con.commit()
        (self.dados/'raw').mkdir()
        (self.dados/'raw/evidencia.txt').write_text('publicacao original')
        (self.dados/'fila-cadastros/pendentes').mkdir(parents=True)
        (self.dados/'fila-cadastros/pendentes/pedido.json').write_text('{"id":"preservar"}')
        (self.conf.parent/'api_token').write_text('token-de-teste-nao-publicar')
        self.conf.write_text('# manter comentario\n[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[web]\nraiz = %s\nurl = /radar/\n[logs]\ndir = %s\n[cadastro]\nlote = 7\n' % (self.home,self.dados,self.db,self.web,self.logs))
        (self.web/'radar.conf').symlink_to(self.conf)
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('RADAR_') and k not in ('GATEWAY_INTERFACE','REQUEST_METHOD')}
        self.env['PYTHONDONTWRITEBYTECODE']='1'

    def rodar(self, *extras, conf=None):
        return subprocess.run([sys.executable,str(ROOT/'web/api.pse'),'instalacao','--conf',str(conf or self.conf),
                               '--laboratorio',str(self.lab),'--usuario-web',getpass.getuser(),*extras],
                              env=dict(self.env,RADAR_CONF=str(conf or self.conf)),capture_output=True,text=True,timeout=100,cwd='/tmp')

    def test_aplicacao_sem_laboratorio_so_verifica_nginx_e_recusa_http_exposto(self):
        from core.raiz_web import _aplicar
        from core.instalacao import _usar_conf
        nginx = self.lab / 'etc/nginx/default'
        nginx.parent.mkdir(parents=True)
        nginx.write_text('configuracao exclusiva do operador')
        with _usar_conf(self.conf), \
             patch('core.protecao_configuracao.planejar', side_effect=AssertionError('nao gerenciar nginx')) as planejar, \
             patch('core.raiz_web._executar', return_value='') as executar, \
             patch('core.raiz_web._bloqueios_http', side_effect=RuntimeError('HTTP privado exposto')):
            with self.assertRaisesRegex(RuntimeError, 'HTTP privado exposto'):
                _aplicar(SimpleNamespace(origem_http='https://teste.example'), ROOT, self.conf, self.web,
                         self.dados, self.db, self.logs, self.home, pwd.getpwuid(os.getuid()), None,
                         'teste', {}, [], self.web/'dados', self.web/'dados/radar.sqlite3', self.web/'dados/logs')
        planejar.assert_not_called()
        self.assertEqual([c.args[0] for c in executar.call_args_list], [['nginx', '-t']])
        self.assertEqual(nginx.read_text(), 'configuracao exclusiva do operador')

    def test_simular_nao_copia_dados_nem_troca_link(self):
        r=self.rodar('--migrar-raiz-web')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertTrue((self.web/'radar.conf').is_symlink())
        self.assertFalse((self.web/'dados').exists())
        self.assertFalse((self.dados/'backups').exists())

    def test_migra_preserva_e_reaplica_sem_apagar_dados(self):
        r=self.rodar('--migrar-raiz-web','--aplicar')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        novo=self.web/'radar.conf'
        self.assertFalse(novo.is_symlink())
        self.assertIn('home = '+str(self.web),novo.read_text())
        self.assertNotIn('usuario =',novo.read_text())
        self.assertNotIn('grupo =',novo.read_text())
        self.assertIn('banco = radar.sqlite3',novo.read_text())
        self.assertIn('lote = 7',novo.read_text())
        r_config=subprocess.run([sys.executable,str(self.web/'api.pse'),'configuracao','verificar-web'],env=self.env,cwd='/',capture_output=True,text=True,timeout=20)
        self.assertEqual(r_config.returncode,0,r_config.stdout+r_config.stderr)
        self.assertIn('# manter comentario',novo.read_text())
        with closing(db.connect_readonly(self.web/'dados/radar.sqlite3')) as con:
            self.assertEqual(con.execute('SELECT valor FROM SENTINELA').fetchone()[0],'preservar')
            self.assertEqual(con.execute('SELECT caminho_cache FROM ARTEFATO_COLETA').fetchone()[0],str(self.web/'dados/raw/evidencia.txt'))
        self.assertEqual((self.web/'dados/raw/evidencia.txt').read_text(),'publicacao original')
        self.assertTrue((self.web/'dados/fila-cadastros/pendentes/pedido.json').is_file())
        self.assertEqual((self.web/'dados/api_token').read_text(),'token-de-teste-nao-publicar')
        self.assertEqual(self.conf.read_text().splitlines()[0],'# manter comentario')
        r=self.rodar('--aplicar',conf=novo)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual((self.web/'dados/raw/evidencia.txt').read_text(),'publicacao original')
        r=self.rodar('--verificar',conf=novo)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        # O CGI descobre o arquivo junto a si, sem env e independente de cwd.
        env=dict(self.env,REQUEST_METHOD='GET',GATEWAY_INTERFACE='CGI/1.1',QUERY_STRING='rota=/health/ready')
        r=subprocess.run([sys.executable,str(self.web/'api.pse')],env=env,cwd='/',capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('"ready"',r.stdout)

    def test_reaplicacao_respeita_banco_e_logs_reconfigurados(self):
        r=self.rodar('--migrar-raiz-web','--aplicar')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        novo=self.web/'radar.conf'
        (self.web/'dados/radar.sqlite3').rename(self.web/'dados/producao.sqlite3')
        log=self.web/'dados/logs/tick.log'
        (self.web/'dados/logs/diario').mkdir()
        log.rename(self.web/'dados/logs/diario/tick.log')
        novo.write_text(novo.read_text().replace('banco = radar.sqlite3','banco = producao.sqlite3').replace('dir = logs','dir = logs/diario'))
        r=self.rodar('--aplicar',conf=novo)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('banco = producao.sqlite3',novo.read_text())
        self.assertIn('dir = logs/diario',novo.read_text())
        self.assertFalse((self.web/'dados/radar.sqlite3').exists())
        self.assertEqual((self.web/'dados/logs/diario/tick.log').read_text(),'historico anterior\n')

    def test_destino_com_outro_banco_nao_e_sobrescrito(self):
        (self.web/'dados').mkdir()
        sentinela=self.web/'dados/radar.sqlite3'
        sentinela.write_bytes(b'outro banco')
        r=self.rodar('--migrar-raiz-web','--aplicar')
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(sentinela.read_bytes(),b'outro banco')
        self.assertTrue((self.web/'radar.conf').is_symlink())

    def test_falha_recupera_api_e_link_sem_apagar_origem(self):
        # Uma chave diferente ja no cache impede substituicao; falha apos copia.
        (self.dados/'api_token').write_text('divergente')
        self.conf.write_text(self.conf.read_text()+'\n[api]\ntoken_arquivo = '+str(self.conf.parent/'api_token')+'\n')
        r=self.rodar('--migrar-raiz-web','--aplicar')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('Segredo divergente',r.stderr)
        self.assertEqual((self.web/'api.pse').read_text(),'# anterior')
        self.assertTrue((self.web/'radar.conf').is_symlink())
        self.assertFalse((self.web/'dados').exists())
        with closing(db.connect_readonly(self.db)) as con:
            self.assertEqual(con.execute('SELECT valor FROM SENTINELA').fetchone()[0],'preservar')
        self.assertTrue(list((self.dados/'backups/raiz-web').glob('*/checagem-final.json')))

    def test_cron_baixa_privilegios_e_preserva_rotinas_externas(self):
        antigo=self.home.parent
        externo='*/5 * * * * /opt/rotina-externa\n'
        texto=externo+'* * * * * '+str(antigo/'radar-tick.sh')+'\n'
        novo=_cron(texto,antigo,self.web,'www-data')
        self.assertIn(externo,novo)
        self.assertNotIn('runuser',novo)
        self.assertIn('env -u RADAR_BRASIL_HOME',novo)
        self.assertIn('RADAR_CONF='+str(self.web/'radar.conf'),novo)
        self.assertEqual(novo.count('# radar-raiz-web'),2)
        self.assertEqual(_cron(novo,self.web.parent,self.web,'www-data'),novo)

    def test_nginx_privado_idempotente_preserva_handler_cgi(self):
        fonte='server { root /srv/www; location ~ \\.pse$ { fastcgi_pass unix:/socket; } }'
        novo,n=proteger_texto(fonte,'/radar/','/srv/www/radar','',raiz_local=True)
        self.assertEqual(n,1)
        self.assertIn('fastcgi_pass unix:/socket;',novo)
        self.assertIn('location "/radar/" { return 404; }',novo)
        self.assertIn('location ^~ "/radar/resources/"',novo)
        self.assertNotIn('location = "/radar/api.pse"',novo)
        self.assertEqual(novo.count('fastcgi_pass'),1)
        self.assertEqual(proteger_texto(novo,'/radar/','/srv/www/radar','',raiz_local=True)[0],novo)

    def test_bloqueio_http_nao_aceita_arquivo_publico_com_200(self):
        class Resposta:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch('core.raiz_web.urllib.request.urlopen',return_value=Resposta()):
            with self.assertRaisesRegex(RuntimeError,'Protecao HTTP reprovada'):
                _bloqueios_http(self.web,'https://radar.test','/radar/')
        self.assertFalse(list(self.web.rglob('.sonda-*')))

    def test_bloqueio_http_aguarda_recarga_e_nao_reutiliza_cache(self):
        class Resposta:
            def __init__(self,status): self.status=status
            def __enter__(self):return self
            def __exit__(self,*args):pass
        pedidos=[]
        def abrir(pedido,**kw):
            pedidos.append(pedido)
            # O worker antigo ja protegia radar.conf, mas ainda serve o backup.
            return Resposta(200 if len(pedidos)==2 else 404)
        with patch('core.raiz_web.urllib.request.urlopen',side_effect=abrir), patch('core.raiz_web.time.sleep') as pausa:
            _bloqueios_http(self.web,'https://radar.test','/radar/',aguardar=2)
        self.assertGreaterEqual(pausa.call_count,2)
        self.assertTrue(all('radar_sonda=' in p.full_url for p in pedidos))
        self.assertTrue(all(p.get_header('Cache-control')=='no-cache, no-store' for p in pedidos))
        self.assertGreater(len(pedidos),3)
        self.assertFalse(list(self.web.rglob('.sonda-*')))

    def test_bloqueio_http_200_persistente_reprova_mesmo_com_espera(self):
        class Resposta:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
        relogio=[0]
        def pausa(segundos):relogio[0]+=segundos
        with patch('core.raiz_web.urllib.request.urlopen',return_value=Resposta()), \
             patch('core.raiz_web.time.monotonic',side_effect=lambda:relogio[0]), \
             patch('core.raiz_web.time.sleep',side_effect=pausa):
            with self.assertRaisesRegex(RuntimeError,'Protecao HTTP reprovada'):
                _bloqueios_http(self.web,'https://radar.test','/radar/',aguardar=.5)
        self.assertEqual(relogio[0],.5)
        self.assertFalse(list(self.web.rglob('.sonda-*')))

    def test_banco_ja_movido_e_secoes_repetidas_sao_preservados_e_normalizados(self):
        dados=self.web/'dados'
        self.dados.rename(dados)
        self.db=dados/'radar.sqlite3'
        self.dados=dados
        with closing(db.connect(self.db)) as con:
            con.execute('UPDATE ARTEFATO_COLETA SET caminho_cache=?',(str(dados/'raw/evidencia.txt'),))
            con.commit()
        novo=self.web/'radar.conf'
        novo.unlink()
        novo.write_text('[instalacao]\nhome = '+str(self.web)+'\nusuario = root\ngrupo = root\n[dados]\ndir = '+str(dados)+'\nbanco = radar.sqlite3\n[web]\nraiz = '+str(self.web)+'\nurl = /radar/\n[logs]\ndir = '+str(self.logs)+'\n[assistente]\nhabilitado = 0\nurl = http://127.0.0.1:11434\n[assistente]\nmodelo = preservar-modelo\n[web]\norigem =\n[api]\nmax_body = 16384\n[api]\ntoken_arquivo = api_token\n')
        (self.web/'api_token').write_text('credencial-original')
        inode=self.db.stat().st_ino
        r=self.rodar('--aplicar',conf=novo)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(self.db.stat().st_ino,inode)
        texto=novo.read_text()
        for secao in ('instalacao','dados','web','api','assistente'):
            self.assertEqual(texto.count('['+secao+']'),1)
        self.assertNotIn('usuario =',texto)
        self.assertNotIn('grupo =',texto)
        self.assertIn('modelo = preservar-modelo',texto)
        self.assertIn('banco = radar.sqlite3',texto)
        self.assertEqual((dados/'api_token').read_text(),'credencial-original')
        self.assertEqual((dados/'logs/tick.log').read_text(),'historico anterior\n')
        with closing(db.connect_readonly(self.db)) as con:
            self.assertEqual(con.execute('SELECT valor FROM SENTINELA').fetchone()[0],'preservar')

    def test_transferencia_crontab_www_data_preserva_outros_sistemas(self):
        from core.raiz_web import _transferir_crons
        root='* * * * * '+str(self.home.parent/'radar-tick.sh')+'\n0 2 * * * /opt/outro-sistema\n'
        estado={'root':root,'www-data':'15 * * * * /opt/tarefa-web\n'}
        def ler(usuario=None):return estado[usuario or 'root']
        def gravar(cmd,**kw):
            usuario=cmd[2] if cmd[1:2]==['-u'] else 'root'
            estado[usuario]=kw['input']
            return ''
        with patch('core.raiz_web.auditoria.ler_crontab',side_effect=ler), patch('core.raiz_web._executar',side_effect=gravar):
            _transferir_crons(self.lab,self.home.parent,self.web,'www-data')
            primeiro=dict(estado)
            _transferir_crons(self.lab,self.home.parent,self.web,'www-data')
        self.assertEqual(estado,primeiro)
        self.assertEqual(estado['root'],'0 2 * * * /opt/outro-sistema\n')
        self.assertIn('15 * * * * /opt/tarefa-web',estado['www-data'])
        self.assertEqual(estado['www-data'].count('# radar-raiz-web'),2)
        self.assertNotIn('runuser',estado['www-data'])

    def test_cron_do_servidor3_migra_ambos_e_preserva_sincronizadores(self):
        from core.raiz_web import _transferir_crons, _checagens_cron
        externo = '''# Backup remoto do host (infra antiga do root -- nao mexer).
06  01  *   *   *    /bin/bash /root/scripts/bkpremoto.sh
*/10 * * * * /usr/bin/python3 /openclaw/bin/hamqsl.py >> /var/log/openclaw/hamqsl/hamqsl.log 2>&1
*/5 * * * * /usr/bin/python3 /openclaw/bin/cepea_cache.py >> /var/log/openclaw/cepea/cepea.log 2>&1
*/10 * * * * /usr/bin/python3 /openclaw/bin/prop_dados.py >> /var/log/openclaw/prop/prop.log 2>&1
*/15 * * * * /usr/bin/python3 /openclaw/bin/hud_faxina.py >> /var/log/openclaw/hud/faxina.log 2>&1
*/10 * * * * /usr/bin/python3 /openclaw/bin/radar-dados-sync.py >> /var/log/openclaw/radar/dados-sync.log 2>&1
*/10 * * * * /usr/bin/python3 /openclaw/bin/radar-instaladores-sync.py >> /var/log/openclaw/radar/instaladores-sync.log 2>&1
'''
        root=externo+'* * * * * /openclaw/bin/radar-tick.sh\n* * * * * /openclaw/bin/radar-api.pse cron fila\n'
        for conf in (self.web/'radar.conf', self.conf):
            with self.subTest(conf=conf):
                estado={'root':root,'www-data':''}
                chamadas=[]
                def ler(usuario=None): return estado[usuario or 'root']
                def gravar(cmd,**kw):
                    self.assertEqual(cmd[:2],['crontab','-u'])
                    chamadas.append(cmd[2])
                    estado[cmd[2]]=kw['input']
                    return ''
                with patch('core.raiz_web.auditoria.ler_crontab',side_effect=ler), patch('core.raiz_web._executar',side_effect=gravar):
                    antes=_checagens_cron(self.home.parent,self.web,'www-data',conf)
                    self.assertEqual([c['estado'] for c in antes],['erro','erro'])
                    _transferir_crons(self.lab,self.home.parent,self.web,'www-data',conf)
                    self.assertEqual(chamadas[:2],['www-data','root'])
                    self.assertEqual(estado['root'],externo)
                    self.assertEqual((self.lab/'crontab-root-anterior.txt').read_text(),root)
                    self.assertIn('RADAR_CONF='+str(conf),estado['www-data'])
                    depois=_checagens_cron(self.home.parent,self.web,'www-data',conf)
                    self.assertEqual([c['estado'] for c in depois],['ok','ok'])
                    primeiro=dict(estado)
                    _transferir_crons(self.lab,self.home.parent,self.web,'www-data',conf)
                    self.assertEqual(estado,primeiro)
                    estado['www-data']+=estado['www-data'].splitlines()[0]+'\n'
                    self.assertEqual(_checagens_cron(self.home.parent,self.web,'www-data',conf)[1]['estado'],'erro')

    def test_transferencia_cron_recupera_ambos_se_limpeza_do_root_falhar(self):
        from core.raiz_web import _transferir_crons
        anteriores={'root':'* * * * * /openclaw/bin/radar-tick.sh\n','www-data':'15 * * * * /opt/outro\n'}
        estado=dict(anteriores)
        falhou=False
        def ler(usuario=None): return estado[usuario or 'root']
        def gravar(cmd,**kw):
            nonlocal falhou
            if cmd[2]=='root' and not falhou:
                falhou=True
                raise RuntimeError('crontab indisponivel')
            estado[cmd[2]]=kw['input']
            return ''
        with patch('core.raiz_web.auditoria.ler_crontab',side_effect=ler), patch('core.raiz_web._executar',side_effect=gravar):
            with self.assertRaisesRegex(RuntimeError,'crontab indisponivel'):
                _transferir_crons(self.lab,self.home.parent,self.web,'www-data')
        self.assertEqual(estado,anteriores)

    def test_auditoria_cron_nao_aceita_crontab_web_ilegivel(self):
        from core.raiz_web import _checagens_cron
        def ler(usuario):
            if usuario=='root': return ''
            raise RuntimeError('Nao foi possivel ler o crontab de www-data')
        with patch('core.raiz_web.auditoria.ler_crontab',side_effect=ler):
            estado=_checagens_cron(self.home.parent,self.web,'www-data')
        self.assertEqual([c['estado'] for c in estado],['ok','erro'])
        self.assertIn('www-data',estado[1]['detalhe'])

    def test_verificacao_final_reprova_root_ativo_e_web_sem_tarefas(self):
        import pwd
        from core.raiz_web import _verificar
        conta=pwd.getpwnam('www-data')
        def ler(usuario):
            return '* * * * * /openclaw/bin/radar-tick.sh\n' if usuario=='root' else ''
        with patch('core.raiz_web.auditoria.ler_crontab',side_effect=ler), \
             patch('core.raiz_web._cgi'), patch('core.raiz_web._comando'), \
             patch('core.raiz_web._bloqueios_http'), patch('core.raiz_web.auditoria.verificar_http'):
            checagens=_verificar(ROOT,self.web,self.conf,conta,None)
            sem_cron=_verificar(ROOT,self.web,self.conf,conta,None,cron=False)
        crons={c['checagem']:c['estado'] for c in checagens if c['checagem'].startswith('cron.')}
        self.assertEqual(crons,{'cron.root':'erro','cron.www-data':'erro'})
        self.assertFalse(any(c['checagem'].startswith('cron.') for c in sem_cron))

    def test_containers_de_backup_sao_preparados_para_o_usuario_web(self):
        import pwd
        from core.raiz_web import _preparar_backups
        conta=pwd.getpwnam('www-data')
        historico=self.dados/'backups/raiz-web/antigo.sqlite3'
        historico.parent.mkdir(parents=True)
        historico.write_text('preservar backup anterior')
        historico.chmod(0o600)
        with patch('core.raiz_web.os.geteuid',return_value=0), patch('core.raiz_web.os.chown') as chown:
            _preparar_backups(self.dados,conta)
        self.assertEqual(chown.call_count,2)
        for pasta in (self.dados/'backups',self.dados/'backups/identidade'):
            chown.assert_any_call(pasta,conta.pw_uid,conta.pw_gid)
            self.assertEqual(pasta.stat().st_mode & 0o7777,0o2770)
        self.assertEqual(historico.read_text(),'preservar backup anterior')
        self.assertEqual(historico.stat().st_mode & 0o777,0o600)
