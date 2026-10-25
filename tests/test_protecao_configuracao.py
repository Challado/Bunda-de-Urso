"""Protege o link no nginx real, preservando as demais paginas e servidores."""
import os
from pathlib import Path
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import time
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from core.protecao_configuracao import planejar, proteger_texto


class FastCGITeste(socketserver.BaseRequestHandler):
    def handle(self):
        def ler(n):
            dados=b''
            while len(dados)<n:
                parte=self.request.recv(n-len(dados))
                if not parte:raise EOFError()
                dados+=parte
            return dados
        parametros,corpo=bytearray(),bytearray()
        while True:
            _,tipo,identificador,tamanho,padding,_=struct.unpack('!BBHHBB',ler(8))
            dados=ler(tamanho+padding)[:tamanho]
            if tipo==4:parametros.extend(dados)
            if tipo==5:
                corpo.extend(dados)
                if not tamanho:break
        self.server.requisicoes.append((bytes(parametros),bytes(corpo)))
        for tipo,dados in ((6,b'Content-Type: application/json\r\n\r\n{"status":"ready"}'),(6,b''),(3,bytes(8))):
            self.request.sendall(struct.pack('!BBHHBB',1,tipo,identificador,len(dados),0,0)+dados)


class TestProtecaoConfiguracao(unittest.TestCase):
    def test_idempotente_preserva_outros_locais_e_servidores(self):
        outro = 'server { listen 81; server_name outro; root /outra/aplicacao; }'
        fonte = 'http { server { server_name radar.test; root /srv/www; location /api { return 200; } }\n' + outro + ' }'
        novo, encontrados = proteger_texto(fonte, "/radar/", "/srv/www/radar", "https://radar.test")
        self.assertEqual(encontrados, 1)
        self.assertIn(outro, novo)
        self.assertIn("location /api { return 200; }", novo)
        self.assertEqual(proteger_texto(novo, "/radar/", "/srv/www/radar", "https://radar.test")[0], novo)

    def test_corrige_local_exato_existente_sem_criar_duplicata(self):
        fonte = 'server { root /srv/www; location = /radar/radar.conf { return 200; } }'
        novo, encontrados = proteger_texto(fonte, "/radar/", "/srv/www/radar", "")
        self.assertEqual(encontrados, 1)
        self.assertEqual(novo.count("location ="), 1)
        self.assertIn("return 404;", novo)

    def test_identifica_alias_em_local_com_nome_generico_do_servidor(self):
        fonte = 'server { server_name _; location /radar/ { alias /srv/radar-web/; } }'
        novo, encontrados = proteger_texto(fonte, "/radar/", "/srv/radar-web", "https://publico.test")
        self.assertEqual(encontrados, 1)
        self.assertIn("return 404;", novo)
        self.assertIn("alias /srv/radar-web/;", novo)

    def test_nginx_real_bloqueia_download_e_mantem_pagina_acessivel(self):
        self._nginx_real()

    def test_nginx_real_layout_local_bloqueia_banco_codigo_logs_e_segredos(self):
        self._nginx_real(raiz_local=True)

    def test_nginx_real_recarga_legado_e_confirma_todas_as_sondas(self):
        self._nginx_real(raiz_local=True, recarregar=True)

    def test_handler_generico_e_preservado_sem_criar_excecao_para_api(self):
        fonte='server { root /srv/www; location = /outro/api.pse { fastcgi_pass unix:/outro; } location ~ \\.pse$ { fastcgi_pass unix:/radar; } }'
        novo,_=proteger_texto(fonte,'/radar/','/srv/www/radar','',raiz_local=True)
        self.assertNotIn('location = "/radar/api.pse"',novo)
        self.assertEqual(novo.count('fastcgi_pass unix:/radar;'),1)
        self.assertIn('location "/radar/" { return 404; }',novo)
        self.assertIn('location = /outro/api.pse { fastcgi_pass unix:/outro; }',novo)

    def test_exige_handler_generico_em_vez_de_copiar_excecao_antiga(self):
        fonte='server { root /srv/www; location = /radar/api.pse { fastcgi_pass unix:/radar; } }'
        with self.assertRaisesRegex(RuntimeError,'generico .pse'):
            proteger_texto(fonte,'/radar/','/srv/www/radar','',raiz_local=True)

    def test_publicacao_tambem_funciona_na_raiz_do_host(self):
        fonte='server { root /srv/www; location ~ \\.pse$ { fastcgi_pass unix:/radar; } }'
        novo,_=proteger_texto(fonte,'/','/srv/www','',raiz_local=True)
        self.assertNotIn('location = ""',novo)
        self.assertNotIn('location = "/api.pse"',novo)
        self.assertIn('location "/" { return 404; }',novo)
        self.assertIn('location ^~ "/resources/"',novo)

    def test_include_do_operador_preserva_o_bloco_original_inteiro(self):
        fonte='server { root /srv/www; include /etc/nginx/snippets/radar-brasil.conf; location /proxy/yahoo/ { proxy_pass https://exemplo.invalid/; } location ~ \\.pse$ { fastcgi_pass unix:/socket; } }'
        novo,n=proteger_texto(fonte,'/radar/','/srv/www/radar','',raiz_local=True)
        self.assertEqual(n,1)
        self.assertEqual(novo,fonte)

    def test_nginx_real_com_snippet_preserva_vhost_e_handler_generico(self):
        self._nginx_real(raiz_local=True, usar_snippet=True)

    def test_identifica_raiz_com_link_intermediario_sem_server_name(self):
        with tempfile.TemporaryDirectory(prefix='radar-raiz-link-') as pasta:
            base=Path(pasta)
            real=base/'openclaw/html/radar'
            real.mkdir(parents=True)
            www=base/'www'
            www.mkdir()
            (www/'openclaw').symlink_to(real.parent,target_is_directory=True)
            fonte='server { server_name _; root "'+str(www)+'"; location ~ \\.pse$ { fastcgi_pass unix:/socket; } }'
            novo,n=proteger_texto(fonte,'/openclaw/radar/',real,'https://servidor3.test',raiz_local=True)
            self.assertEqual(n,1)
            self.assertIn('location "/openclaw/radar/" { return 404; }',novo)
            self.assertIn('location ^~ "/openclaw/radar/resources/"',novo)
            self.assertEqual(proteger_texto(novo,'/openclaw/radar/',real,'https://servidor3.test',raiz_local=True)[0],novo)

    def _nginx_real(self, raiz_local=False, recarregar=False, usar_snippet=False):
        binario = os.environ.get("RADAR_TEST_NGINX") or shutil.which("nginx")
        if not binario:
            self.skipTest("nginx nao instalado (o CI instala o pacote)")
        backend=socketserver.ThreadingTCPServer(('127.0.0.1',0),FastCGITeste)
        backend.daemon_threads=True
        backend.requisicoes=[]
        self.addCleanup(backend.server_close)
        self.addCleanup(backend.shutdown)
        threading.Thread(target=backend.serve_forever,daemon=True).start()
        with tempfile.TemporaryDirectory(prefix="radar-nginx-") as pasta:
            base = Path(pasta)
            web = base / "www" / "radar"
            web.mkdir(parents=True)
            conf = base / "radar.conf"
            conf.write_text("configuracao privada de teste")
            if raiz_local:
                (web / "radar.conf").write_text("configuracao privada de teste")
            else:
                (web / "radar.conf").symlink_to(conf)
            privados = ["dados/radar.sqlite3", "dados/raw/original.json", "dados/segredos/api_token",
                        "logs/tick.log", "core/entrada_api.py",
                        "radar.conf.anterior", "radar.conf.lock", "sql/schema.sqlite.sql", ".radar-temporario-privado"]
            if raiz_local:
                for rel in privados:
                    arquivo = web / rel
                    arquivo.parent.mkdir(parents=True, exist_ok=True)
                    arquivo.write_text("conteudo privado nao deve sair por HTTP")
            (web / "index.html").write_text("pagina publica de teste")
            if raiz_local:
                recursos=web/'resources'
                recursos.mkdir()
                for nome in ('index.html','detalhe.html','cadastro.html','gestao.html','usuarios.html','status.html','status-estado.html','status.css','status.js','municipios.json','projeto.json'):
                    (recursos/nome).write_text('pagina publica de teste')
                (recursos/'segredo.json').symlink_to(conf)
                for nome in ('executar.pse','.oculto.json','config.conf'):
                    (recursos/nome).write_text('privado')
                for nome in ('arquivo-novo.json','copia-config.txt'):
                    (web/nome).write_text('privado')
                privados += ['arquivo-novo.json','copia-config.txt','resources/executar.pse','resources/.oculto.json','resources/config.conf']
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                porta = s.getsockname()[1]
            fonte = 'pid "%s"; error_log stderr; events {} http { access_log off; server { listen 127.0.0.1:%d; root "%s"; } }' % (base / "nginx.pid", porta, base / "www")
            temporarios = " ".join('%s_temp_path "%s";' % (nome, base / nome)
                                   for nome in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
            fonte = fonte.replace("http {", "http { " + temporarios)
            handler=('location ~ \\.pse$ { fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; '
                     'fastcgi_param QUERY_STRING $query_string; fastcgi_param REQUEST_METHOD $request_method; '
                     'fastcgi_param CONTENT_LENGTH $content_length; fastcgi_pass 127.0.0.1:%d; }'%backend.server_address[1])
            fonte=fonte.replace('root "%s";'% (base/'www'),'root "%s"; '%(base/'www')+handler)
            protegido, encontrados = proteger_texto(fonte, "/radar/", web, "", raiz_local=raiz_local)
            self.assertEqual(encontrados, 1)
            if usar_snippet:
                inicio=protegido.index('# radar: inicio publicacao resources')
                fim=protegido.index('# radar: fim publicacao resources')+len('# radar: fim publicacao resources')
                snippet=base/'radar-brasil.conf'
                snippet.write_text(protegido[inicio:fim].replace('# radar: inicio publicacao resources','').replace('# radar: fim publicacao resources',''))
                protegido=protegido[:inicio]+'include "'+str(snippet)+'";'+protegido[fim:]
                substituir=patch('core.protecao_configuracao.SNIPPET_RADAR',str(snippet))
                substituir.start()
                self.addCleanup(substituir.stop)
            nginx_conf = base / "nginx.conf"
            nginx_conf.write_text(protegido)
            comando = [binario, "-p", str(base), "-c", str(nginx_conf), "-e", "stderr"]
            teste = subprocess.run(comando + ["-t"], capture_output=True, text=True, timeout=15)
            self.assertEqual(teste.returncode, 0, teste.stderr)
            executar_real = subprocess.run
            with patch("core.protecao_configuracao.subprocess.run", side_effect=lambda cmd, **kw: executar_real(comando + ["-T"], **kw)):
                self.assertEqual(planejar("/radar/", web, "", raiz_local=raiz_local), [])
            with tempfile.TemporaryFile() as saida:
                if recarregar:
                    legado,_=proteger_texto(fonte,'/radar/',web,'',raiz_local=False)
                    nginx_conf.write_text(legado)
                processo = subprocess.Popen(comando + ["-g", "daemon off;"], stdout=saida, stderr=saida)
                try:
                    limite = time.monotonic() + 5
                    while True:
                        try:
                            entrada='/radar/resources/index.html' if raiz_local else '/radar/'
                            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (porta,entrada), timeout=1) as r:
                                self.assertEqual(r.read(), b"pagina publica de teste")
                            break
                        except urllib.error.URLError:
                            if time.monotonic() >= limite or processo.poll() is not None:
                                saida.seek(0)
                                self.fail(saida.read().decode())
                            time.sleep(0.05)
                    if recarregar:
                        with urllib.request.urlopen('http://127.0.0.1:%d/radar/radar.conf.anterior'%porta,timeout=2) as r:
                            self.assertEqual(r.status,200)
                        nginx_conf.write_text(protegido)
                        recarga=subprocess.run(comando+['-s','reload'],capture_output=True,text=True,timeout=10)
                        self.assertEqual(recarga.returncode,0,recarga.stderr)
                        from core.raiz_web import _bloqueios_http
                        _bloqueios_http(web,'http://127.0.0.1:%d'%porta,'/radar/',aguardar=5)
                    uris = ["/radar/radar.conf", "/radar/%72adar.conf?download=1"]
                    if raiz_local:
                        uris += ["/radar/" + rel for rel in privados]
                        uris += ["/radar/dados/%72adar.sqlite3?download=1"]
                        for nome in ('index.html','status.css','status.js','municipios.json'):
                            with urllib.request.urlopen('http://127.0.0.1:%d/radar/resources/%s'%(porta,nome),timeout=2) as r:
                                self.assertEqual(r.status,200)
                        uris += ['/radar/'+p for p in ('index.html','detalhe.html?id=P-42','cadastro.html','gestao.html','usuarios.html','status.html','status-estado.html','projeto.json','status-atualizacoes.json')]
                        uris += ['/radar','/radar/']
                        with self.assertRaises(urllib.error.HTTPError) as erro:
                            urllib.request.urlopen('http://127.0.0.1:%d/radar/resources/segredo.json'%porta,timeout=2)
                        self.assertIn(erro.exception.code,(403,404))
                    class SemRedirecionar(urllib.request.HTTPRedirectHandler):
                        def redirect_request(self,*args,**kwargs):return None
                    cliente=urllib.request.build_opener(SemRedirecionar())
                    for uri in uris:
                        with self.subTest(uri=uri):
                            with self.assertRaises(urllib.error.HTTPError) as erro:
                                cliente.open("http://127.0.0.1:%d%s" % (porta, uri), timeout=2)
                            self.assertEqual(erro.exception.code, 404)
                    self.assertEqual(conf.read_text(), "configuracao privada de teste")
                    if raiz_local:
                        antes=len(backend.requisicoes)
                        with urllib.request.urlopen('http://127.0.0.1:%d/radar/api.pse?rota=/health/ready'%porta,timeout=2) as r:
                            self.assertEqual(r.status,200)
                        self.assertIn(b'rota=/health/ready',backend.requisicoes[antes][0])
                        self.assertIn(str(web/'api.pse').encode(),backend.requisicoes[antes][0])
                        pedido=urllib.request.Request('http://127.0.0.1:%d/radar/api.pse'%porta,data=b'{"teste":true}',headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(pedido,timeout=2) as r:self.assertEqual(r.status,200)
                        self.assertEqual(backend.requisicoes[antes+1][1],b'{"teste":true}')
                        # Um script novo usa o mesmo handler, sem alterar a configuracao.
                        (web/'outro.pse').write_text('script adicionado depois da partida do nginx')
                        with urllib.request.urlopen('http://127.0.0.1:%d/radar/outro.pse?novo=1'%porta,timeout=2) as r:
                            self.assertEqual(r.status,200)
                            self.assertEqual(r.read(),b'{"status":"ready"}')
                        self.assertIn(str(web/'outro.pse').encode(),backend.requisicoes[antes+2][0])
                        self.assertIn(b'novo=1',backend.requisicoes[antes+2][0])
                        self.assertEqual(len(backend.requisicoes),antes+3)
                finally:
                    processo.terminate()
                    processo.wait(timeout=10)
