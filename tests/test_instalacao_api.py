"""Instalacao em laboratorio: preservacao, repeticao, falha e cron alheio."""
from contextlib import closing
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from core import db
from core.instalacao import _cron_tick

ROOT = Path(__file__).resolve().parents[1]


class TestInstalacaoAPI(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="radar-instalar-teste-")
        self.addCleanup(tmp.cleanup)
        self.lab = Path(tmp.name)
        self.home = self.lab / "bin" / "radar"
        self.home.mkdir(parents=True)
        (self.home / "core").mkdir()
        (self.home / "ANTERIOR").write_text("versao antiga")
        (self.home / "config").mkdir()
        (self.home / "config" / "governanca.json").write_text('{"SUBMISSAO_LIMITE":7}')
        self.web = self.lab / "www" / "radar"
        self.web.mkdir(parents=True)
        (self.web / "api.pse").write_text("# entrada antiga")
        self.dados = self.lab / "dados"
        self.dados.mkdir()
        self.banco = self.dados / "radar.sqlite3"
        with closing(db.connect(self.banco)) as conn:
            db.init_db(conn)
            conn.execute("CREATE TABLE SENTINELA (valor TEXT)")
            conn.execute("INSERT INTO SENTINELA VALUES ('nao perder')")
            conn.commit()
        self.conf = self.lab / "etc" / "radar" / "radar.conf"
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text("# configuracao do servidor\n[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[web]\nraiz = %s\nurl = /teste/\n[logs]\ndir = %s\n" %
                             (self.home, self.dados, self.banco, self.web, self.lab / "logs"))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("RADAR_") and k not in ("REQUEST_METHOD", "GATEWAY_INTERFACE")}
        self.env["RADAR_CONF"] = str(self.conf)
        self.externo = self.home.parent / "radar-dados-sync.py"
        self.externo.write_text("# ESPECIFICO DO SERVIDOR, NAO ALTERAR")

    def instalar(self, aplicar=False):
        return subprocess.run([sys.executable, str(ROOT / "web" / "api.pse"), "instalacao", "--conf", str(self.conf),
                               "--laboratorio", str(self.lab), "--usuario-web", getpass.getuser(),
                               *(["--aplicar"] if aplicar else [])], env=self.env,
                              capture_output=True, text=True, timeout=120)

    def test_simulacao_nao_modifica_instalacao(self):
        antes = {str(p.relative_to(self.lab)): p.read_bytes() for p in self.lab.rglob("*") if p.is_file()}
        resultado = self.instalar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        depois = {str(p.relative_to(self.lab)): p.read_bytes() for p in self.lab.rglob("*") if p.is_file()}
        self.assertEqual(antes, depois)

    def test_aplicar_repetir_preserva_config_banco_e_rotina_externa(self):
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn("submissao_limite = 7", self.conf.read_text())
        self.conf.write_text(self.conf.read_text().replace("submissao_limite = 7", "submissao_limite = 11"))
        conf_antes = self.conf.read_bytes()
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.conf.read_bytes(), conf_antes)
        self.assertIn("NAO ALTERAR", self.externo.read_text())
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")
        self.assertTrue((self.home / "core" / "entrada_api.py").is_file())
        ambiente_cgi = {k: v for k, v in self.env.items() if k != "RADAR_CONF"}
        ambiente_cgi.update(REQUEST_METHOD="GET", QUERY_STRING="rota=/health/ready", SCRIPT_NAME="/api.pse")
        cgi = subprocess.run([sys.executable, str(self.web / "api.pse")], env=ambiente_cgi,
                             capture_output=True, text=True, timeout=15)
        self.assertIn("Status: 200 OK", cgi.stdout)
        self.assertFalse((self.web / "nucleo.py").exists())
        self.assertFalse(any(p.is_symlink() for p in self.web.rglob("*")))
        self.assertEqual(len(list((self.dados / "backups" / "instalacao").glob("*/CONCLUIDO"))), 2)
        wrapper = self.home.parent / "radar-tick.sh"
        ensaio = subprocess.run(["sh", str(wrapper), "--help"], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(ensaio.returncode, 0, ensaio.stderr)
        self.assertTrue((self.lab / "logs" / "tick.log").is_file())

    def test_recuperacao_explicita_preserva_banco(self):
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        backup = next((self.dados / "backups" / "instalacao").iterdir())
        resultado = subprocess.run([sys.executable, str(ROOT / "web" / "api.pse"), "instalacao", "--conf", str(self.conf),
                                   "--laboratorio", str(self.lab), "--restaurar", str(backup)],
                                  env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual((self.home / "ANTERIOR").read_text(), "versao antiga")
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")

    def test_falha_restaura_codigo_web_e_config_sem_apagar_banco(self):
        (self.web / "nucleo.py").write_text("# fonte antigo indevido no webroot")
        antes_conf = self.conf.read_bytes()
        resultado = self.instalar(True)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("restaurados", resultado.stderr)
        self.assertEqual((self.home / "ANTERIOR").read_text(), "versao antiga")
        self.assertEqual((self.web / "api.pse").read_text(), "# entrada antiga")
        self.assertEqual(self.conf.read_bytes(), antes_conf)
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")

    def test_cron_preserva_envio_privado_e_outros_projetos(self):
        wrapper = self.home.parent / "radar-tick.sh"
        externo = "*/10 * * * * python3 %s >> /logs/dados-sync.log 2>&1" % self.externo
        outro = "6 1 * * * /outro/projeto/bkpremoto.sh"
        texto = externo + "\n" + outro + "\n* * * * * " + str(wrapper) + " >> /logs/antigo.log 2>&1\n"
        novo = _cron_tick(texto, wrapper)
        self.assertIn(externo + "\n", novo)
        self.assertIn(outro + "\n", novo)
        self.assertEqual(novo, _cron_tick(novo, wrapper))
