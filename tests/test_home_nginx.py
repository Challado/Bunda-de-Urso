"""Home na raiz, assets em resources e CGI generico, com nginx temporario."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request


class TestHomeNginx(unittest.TestCase):
    def test_home_paginas_assets_e_cgi_sem_download_de_dados(self):
        binario = os.environ.get('RADAR_TEST_NGINX') or shutil.which('nginx')
        if not binario:
            self.skipTest('nginx ausente; instalado pelo CI')
        with tempfile.TemporaryDirectory(prefix='radar-home-nginx-') as pasta:
            base = Path(pasta)
            web = base / 'www/radar'
            (web/'resources').mkdir(parents=True)
            (web/'dados/fila-cadastros').mkdir(parents=True)
            for nome, texto in {'index.html':'HOME', 'cadastro.html':'CADASTRO',
                                'resources/logo.png':'LOGO', 'resources/teste.pse':'PRIVADO',
                                'resources/.env':'SEGREDO', 'radar.conf':'SEGREDO',
                                'dados/radar.sqlite3':'BANCO', 'dados/fila-cadastros/pedido.json':'PRIVADO'}.items():
                (web/nome).write_text(texto)
            with socket.socket() as s:
                s.bind(('127.0.0.1',0))
                porta = s.getsockname()[1]
            conf = base/'nginx.conf'
            temporarios = ' '.join('%s_temp_path "%s";' % (n,base/n) for n in ('client_body','proxy','fastcgi','uwsgi','scgi'))
            conf.write_text('pid "'+str(base/'nginx.pid')+'"; error_log stderr; events {} http { access_log off; '+temporarios+
                ' server { listen 127.0.0.1:'+str(porta)+'; root "'+str(base/'www')+'"; '+r'''
                location ~ \.pse$ { return 200 'CGI'; }
                location ^~ /radar/resources/ {
                    autoindex off;
                    disable_symlinks on;
                    if ($uri ~ "(?:^|/)\\.") { return 404; }
                    if ($uri !~* "\\.(?:css|js|json|png|ico|svg|jpg|jpeg|webp|woff|woff2)$") { return 404; }
                }
                location /radar/ {
                    index index.html;
                    autoindex off;
                    if ($uri !~ "^/radar/(?:[A-Za-z0-9_-]+\\.html)?$") { return 404; }
                    try_files $uri $uri/ =404;
                }
            }}''')
            cmd = [binario,'-p',str(base),'-c',str(conf),'-e','stderr']
            sintaxe = subprocess.run(cmd+['-t'],capture_output=True,text=True,timeout=10)
            self.assertEqual(sintaxe.returncode,0,sintaxe.stderr)
            with tempfile.TemporaryFile() as log:
                proc = subprocess.Popen(cmd+['-g','daemon off;'],stdout=log,stderr=log)
                try:
                    limite = time.monotonic()+5
                    while True:
                        try:
                            with urllib.request.urlopen('http://127.0.0.1:%s/radar/' % porta,timeout=1) as r:
                                self.assertEqual(r.status,200)
                                self.assertEqual(r.read(),b'HOME')
                            break
                        except urllib.error.URLError:
                            if time.monotonic()>limite:
                                log.seek(0)
                                self.fail(log.read().decode())
                            time.sleep(.05)
                    for caminho, corpo in [('index.html',b'HOME'),('cadastro.html',b'CADASTRO'),
                                           ('resources/logo.png',b'LOGO'),('api.pse',b'CGI'),('novo.pse',b'CGI')]:
                        with self.subTest(caminho=caminho):
                            with urllib.request.urlopen('http://127.0.0.1:%s/radar/%s' % (porta,caminho)) as r:
                                self.assertEqual(r.read(),corpo)
                    for caminho in ('radar.conf','dados/radar.sqlite3','dados/fila-cadastros/pedido.json',
                                    'dados/','resources/teste.pse','resources/.env','segredo.html.bak'):
                        with self.subTest(privado=caminho):
                            with self.assertRaises(urllib.error.HTTPError) as erro:
                                urllib.request.urlopen('http://127.0.0.1:%s/radar/%s' % (porta,caminho))
                            self.assertEqual(erro.exception.code,404)
                finally:
                    proc.terminate()
                    proc.wait(timeout=10)
