"""Entrada real CGI/local, clientes legados e regressao dos atalhos ao banco."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import db
from core.manutencao import radar_admin
from coletor import sync, tick

ROOT = Path(__file__).resolve().parents[1]


class TestEntradaApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="radar-api-unica-")
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.banco = self.pasta / "radar.sqlite3"
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("GATEWAY_INTERFACE", "REQUEST_METHOD", "PATH_INFO", "QUERY_STRING")}
        self.env.update(RADAR_DB=str(self.banco), RADAR_DATA_DIR=str(self.pasta))

    def executar(self, *args, entrada="web/api.pse", env=None, stdin=None):
        return subprocess.run([sys.executable, str(ROOT / entrada), *args], cwd=ROOT,
                              env=env or self.env, input=stdin, capture_output=True,
                              text=True, timeout=20)

    def test_cliente_sync_passa_pela_api_e_cgi_consulta_o_resultado(self):
        result = self.executar("--fonte", "antt", "--arquivo", "tests/fixtures/antt_radares_fixture.json",
                               entrada="coletor/sync.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(json.loads(result.stdout)["criados"], 0)
        env = {**self.env, "RADAR_BRASIL_HOME": str(ROOT),
               "REQUEST_METHOD": "GET", "SCRIPT_NAME": "/api.pse",
               "QUERY_STRING": "rota=/api/v1/radares/P-1&formato=json"}
        for entrada in ("web/api.pse", "deploy/api.pse"):
            with self.subTest(entrada=entrada):
                response = self.executar(entrada=entrada, env=env)
                self.assertEqual(response.returncode, 0, response.stderr)
                headers, body = response.stdout.replace("\r\n", "\n").split("\n\n", 1)
                self.assertIn("200", headers)
                self.assertEqual(json.loads(body)["resultado"]["pontos"][0]["id"], "P-1")

    def test_admin_legado_e_console_usam_a_mesma_api(self):
        result = self.executar("criar-admin", "admin-teste", entrada="tools/radar_admin.py",
                               stdin="SenhaDeTesteTemporaria123\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        users = self.executar("usuarios")
        self.assertEqual(users.returncode, 0, users.stderr)
        self.assertIn("admin-teste", users.stdout)
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM USUARIO").fetchone()[0], 1)

    def test_http_nao_despacha_operacoes_locais_mesmo_com_argumentos_cli(self):
        initialized = self.executar("ferramenta", "inicializar_banco")
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        env = {**self.env, "REQUEST_METHOD": "GET", "SCRIPT_NAME": "/api.pse",
               "QUERY_STRING": "rota=/api/v1/ferramenta/radar_admin"}
        result = self.executar("ferramenta", "radar_admin", "criar-admin", "intruso",
                               env=env, stdin="SenhaDeTesteTemporaria123\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("404", result.stdout.split("\n\n", 1)[0])
        self.assertNotIn("admin intruso criado", result.stdout)
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM USUARIO").fetchone()[0], 0)

    def test_operacoes_locais_recusam_entrada_direta(self):
        for main in (radar_admin.main, sync._main_servico, tick._main_servico):
            with self.subTest(main=main):
                with self.assertRaisesRegex(RuntimeError, "api.pse"):
                    main(["--help"])

    def test_despachante_recusa_modulo_fora_da_lista(self):
        result = self.executar("ferramenta", "../../qualquer_modulo")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.banco.exists())

    def test_bootstrap_copia_snapshot_e_preserva_base_existente(self):
        source = self.pasta / "snapshot.sqlite3"
        with closing(db.connect(source)) as conn:
            db.init_db(conn)
            conn.execute("CREATE TABLE TESTE_PRESERVACAO (valor INTEGER)")
            conn.execute("INSERT INTO TESTE_PRESERVACAO VALUES (1)")
            conn.commit()
        args = ("ferramenta", "inicializar_banco", "--origem", str(source))
        result = self.executar(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(db.connect(self.banco)) as conn:
            conn.execute("INSERT INTO TESTE_PRESERVACAO VALUES (2)")
            conn.commit()
        result = self.executar(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM TESTE_PRESERVACAO").fetchone()[0], 2)
        with closing(db.connect_readonly(source)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM TESTE_PRESERVACAO").fetchone()[0], 1)

    def test_conexao_somente_leitura_nao_cria_banco_nem_permite_escrita(self):
        with self.assertRaises(FileNotFoundError):
            db.connect_readonly(self.banco)
        self.assertFalse(self.banco.exists())
        with closing(db.connect(self.banco)) as writer:
            writer.execute("CREATE TABLE TESTE (valor INTEGER)")
            writer.execute("INSERT INTO TESTE VALUES (1)")
            writer.commit()
            with closing(db.connect_readonly(self.banco)) as reader:
                self.assertEqual(reader.execute("SELECT valor FROM TESTE").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("INSERT INTO TESTE VALUES (2)")


class TestFiscalizacaoApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = ROOT / ".github/scripts"
        spec = importlib.util.spec_from_file_location("verificar_banco_test", scripts / "verificar_banco.py")
        cls.checker = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(scripts), *sys.path]):
            spec.loader.exec_module(cls.checker)

    def test_detecta_aliases_e_atalhos_em_ferramentas_e_console(self):
        for rel, codigo in [
            ("tools/atalho.py", "import sqlite3 as banco\nbanco.connect('radar.db')"),
            ("core/atalho.py", "from sqlite3 import connect as abrir\nabrir('radar.db')"),
            ("tools/atalho.py", "from core import db\ndb.connect()"),
            ("web/terminal.py", "from core import governanca\ngovernanca.criar_usuario(None)"),
            ("tools/atalho.py", "conn.execute('DELETE FROM USUARIO')"),
            ("deploy/cron.sh", "exec python3 coletor/tick.py"),
            ("core/manutencao/atalho.py", "def main(): pass"),
        ]:
            with self.subTest(rel=rel, codigo=codigo):
                self.assertTrue(self.checker.verificar_arquivo(rel, codigo))

    def test_checkout_inclui_arquivos_novos_sem_isencao_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp, "tools/nao_versionado.py")
            arquivo.parent.mkdir()
            arquivo.write_text("from sqlite3 import connect\nconnect('radar.db')")
            self.assertIn(arquivo, list(self.checker.arquivos(Path(tmp))))
        codigo = "from core.cliente_api import executar\ndef main(argv=None):\n    return executar(['ferramenta', 'radar_admin'], argv)"
        self.assertEqual(self.checker.verificar_arquivo("tools/radar_admin.py", codigo), [])
