"""Protege o link no nginx real, preservando as demais paginas e servidores."""
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
from unittest.mock import patch

from core.protecao_configuracao import planejar, proteger_texto


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

    def test_identifica_raiz_com_link_intermediario_sem_server_name(self):
        with tempfile.TemporaryDirectory(prefix='radar-raiz-link-') as pasta:
            base=Path(pasta)
            real=base/'openclaw/html/radar'
            real.mkdir(parents=True)
            www=base/'www'
            www.mkdir()
            (www/'openclaw').symlink_to(real.parent,target_is_directory=True)
            fonte='server { server_name _; root "'+str(www)+'"; }'
            novo,n=proteger_texto(fonte,'/openclaw/radar/',real,'https://servidor3.test',raiz_local=True)
            self.assertEqual(n,1)
            self.assertIn('location = "/openclaw/radar/radar.conf.anterior" { return 404; }',novo)
            self.assertIn('location ^~ "/openclaw/radar/dados/" { return 404; }',novo)
            self.assertEqual(proteger_texto(novo,'/openclaw/radar/',real,'https://servidor3.test',raiz_local=True)[0],novo)

    def _nginx_real(self, raiz_local=False, recarregar=False):
        binario = os.environ.get("RADAR_TEST_NGINX") or shutil.which("nginx")
        if not binario:
            self.skipTest("nginx nao instalado (o CI instala o pacote)")
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
                        "logs/tick.log", "core/entrada_api.py", "web/api.pse", "deploy/api.pse",
                        "radar.conf.anterior", "radar.conf.lock", "sql/schema.sqlite.sql", ".radar-temporario-privado"]
            if raiz_local:
                for rel in privados:
                    arquivo = web / rel
                    arquivo.parent.mkdir(parents=True, exist_ok=True)
                    arquivo.write_text("conteudo privado nao deve sair por HTTP")
            (web / "index.html").write_text("pagina publica de teste")
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                porta = s.getsockname()[1]
            fonte = 'pid "%s"; error_log stderr; events {} http { access_log off; server { listen 127.0.0.1:%d; root "%s"; } }' % (base / "nginx.pid", porta, base / "www")
            temporarios = " ".join('%s_temp_path "%s";' % (nome, base / nome)
                                   for nome in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
            fonte = fonte.replace("http {", "http { " + temporarios)
            protegido, encontrados = proteger_texto(fonte, "/radar/", web, "", raiz_local=raiz_local)
            self.assertEqual(encontrados, 1)
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
                            with urllib.request.urlopen("http://127.0.0.1:%d/radar/" % porta, timeout=1) as r:
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
                    for uri in uris:
                        with self.assertRaises(urllib.error.HTTPError) as erro:
                            urllib.request.urlopen("http://127.0.0.1:%d%s" % (porta, uri), timeout=2)
                        self.assertEqual(erro.exception.code, 404)
                    self.assertEqual(conf.read_text(), "configuracao privada de teste")
                finally:
                    processo.terminate()
                    processo.wait(timeout=10)
