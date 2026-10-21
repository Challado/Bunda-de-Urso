"""Configuracao real em arquivo temporario: permissoes, conflitos e proxima CGI."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import caminhos, config, configuracao, db, governanca
from web import nucleo

ROOT = Path(__file__).resolve().parents[1]


class TestConfiguracaoAPI(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="radar-config-api-")
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.conf = self.raiz / "etc" / "radar.conf"
        self.conf.parent.mkdir()
        self.dados = self.raiz / "dados"
        self.dados.mkdir()
        self.banco = self.dados / "radar.sqlite3"
        self.web = self.raiz / "web"
        self.web.mkdir()
        self.conf.write_text("# comentario mantido\n[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[web]\nraiz = %s\n[governanca]\nsubmissao_limite = 20\n" %
                             (ROOT, self.dados, self.banco, self.web))
        self.conf.chmod(0o660)
        (self.web / "radar.conf").symlink_to(self.conf)
        ambiente = {k: v for k, v in os.environ.items() if not k.startswith(("RADAR_", "OLLAMA_"))}
        ambiente["RADAR_CONF"] = str(self.conf)
        self.env = ambiente
        self.patchenv = patch.dict(os.environ, ambiente, clear=True)
        self.patchenv.start()
        self.addCleanup(self.patchenv.stop)
        self.addCleanup(caminhos.recarregar)
        caminhos.recarregar()
        self.patchdb = patch.object(config, "DB_PATH", str(self.banco))
        self.patchdb.start()
        self.addCleanup(self.patchdb.stop)
        self.tokens = {}
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
            for escopo in ("contribuidor", "moderador", "admin"):
                self.tokens[escopo] = governanca.emitir_token(conn, "teste-" + escopo, escopo)[1]

    def requisicao(self, metodo="GET", corpo=None, papel="admin", headers=None):
        env = {"REQUEST_METHOD": metodo, "PATH_INFO": "/api/v1/gestao/configuracao",
               "CONTENT_TYPE": "application/json", "HTTP_X_RADAR_CONFIGURACAO": "1"}
        if papel:
            env["HTTP_X_API_TOKEN"] = self.tokens[papel]
        env.update(headers or {})
        return nucleo.handle_request(env, json.dumps(corpo).encode() if corpo is not None else b"")

    def alteracao(self, **valores):
        return {"revisao": configuracao.consultar()["revisao"], "alteracoes": valores}

    def test_leitura_exige_admin_e_nao_retorna_segredos(self):
        for papel, esperado in ((None, 401), ("contribuidor", 403), ("moderador", 403), ("admin", 200)):
            self.assertEqual(self.requisicao(papel=papel)[0], esperado)
        with patch.dict(os.environ, RADAR_API_TOKEN="valor-secreto-nao-retornar"):
            status, headers, corpo = self.requisicao()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("valor-secreto", json.dumps(corpo))
        self.assertFalse(next(i for i in corpo["itens"] if i["chave"] == "home")["editavel"])

    def test_link_grava_atomicamente_e_nova_cgi_le_arquivo(self):
        anterior = self.conf.read_bytes()
        payload = self.alteracao(**{"governanca.submissao_limite": "7", "api.max_body": "16384"})
        script = "import os,runpy,sys;os.umask(0o077);runpy.run_path(sys.argv.pop(1),run_name='__main__')"
        resultado = subprocess.run([sys.executable, "-c", script, str(ROOT / "web" / "api.pse"), "configuracao", "salvar-web", "--conf", str(self.conf)],
                                  env=self.env, input=json.dumps(payload), capture_output=True, text=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.conf.with_name("radar.conf.anterior").read_bytes(), anterior)
        self.assertIn("# comentario mantido", self.conf.read_text())
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o660)
        self.assertTrue((self.web / "radar.conf").is_symlink())
        self.assertEqual((self.web / "radar.conf").read_bytes(), self.conf.read_bytes())
        for sufixo in (".lock", ".anterior", ".auditoria.jsonl"):
            self.assertEqual(Path(str(self.conf) + sufixo).stat().st_mode & 0o777, 0o660)
        verificar = subprocess.run([sys.executable, "-c", "from core import config; print(config.SUBMISSAO_LIMITE, config.API_MAX_BODY)"],
                                  cwd=ROOT, env=self.env, text=True, capture_output=True, check=True)
        self.assertEqual(verificar.stdout.strip(), "7 16384")
        self.assertEqual(json.loads(Path(str(self.conf) + ".auditoria.jsonl").read_text())["chaves"],
                         ["api.max_body", "governanca.submissao_limite"])

    def test_revisao_antiga_nao_sobrescreve_outra_edicao(self):
        payload = self.alteracao(**{"governanca.submissao_limite": "9"})
        self.conf.write_text(self.conf.read_text() + "\n# editado no servidor\n")
        with self.assertRaises(governanca.GovernancaError) as erro:
            configuracao.salvar(payload)
        self.assertEqual(erro.exception.status, 409)
        self.assertIn("editado no servidor", self.conf.read_text())

    def test_web_recusa_caminhos_e_requisicao_externa_sem_alterar_arquivo(self):
        payload = self.alteracao(**{"instalacao.home": "/tmp/codigo-arbitrario"})
        antes = self.conf.read_bytes()
        self.assertEqual(self.requisicao("PUT", payload)[0], 403)
        self.assertEqual(self.requisicao("PUT", self.alteracao(), headers={"HTTP_X_RADAR_CONFIGURACAO": ""})[0], 403)
        self.assertEqual(self.requisicao("PUT", self.alteracao(), headers={"HTTP_SEC_FETCH_SITE": "cross-site"})[0], 403)
        self.assertEqual(self.conf.read_bytes(), antes)

    def test_validacao_recusa_injecao_numeros_e_campos_desconhecidos(self):
        for valores in ({"api.max_body": "-1"}, {"governanca.gov_iteracoes": "1"},
                        {"web.url": "/site/\n[dados]\nbanco=/tmp/outro"},
                        {"segredo.valor": "qualquer"}):
            with self.subTest(valores=valores):
                with self.assertRaises(governanca.GovernancaError):
                    configuracao.salvar(self.alteracao(**valores))
        self.assertFalse(self.conf.with_name("radar.conf.anterior").exists())

    def test_override_real_de_ambiente_e_explicito_e_bloqueia_gravacao_enganosa(self):
        with patch.dict(os.environ, RADAR_API_MAX_BODY="32768"):
            item = next(i for i in configuracao.consultar()["itens"] if i["chave"] == "max_body")
            self.assertEqual(item["efetivo"], "32768")
            with self.assertRaises(governanca.GovernancaError) as erro:
                configuracao.salvar(self.alteracao(**{"api.max_body": "65536"}))
        self.assertEqual(erro.exception.codigo, "configuracao_sobreposta")

    def test_api_put_salva_pelo_link_sem_processo_externo(self):
        payload = self.alteracao(**{"governanca.submissao_limite": "10"})
        with patch("subprocess.run", side_effect=AssertionError("Gravacao nao pode executar outro processo")):
            self.assertEqual(self.requisicao("PUT", payload)[0], 200)
        self.assertIn("submissao_limite = 10", self.conf.read_text())
        self.assertTrue((self.web / "radar.conf").is_symlink())

    def test_link_alterado_nao_grava_em_arquivo_arbitrario(self):
        link = self.web / "radar.conf"
        outro = self.raiz / "outro.conf"
        outro.write_text("nao alterar")
        link.unlink()
        link.symlink_to(outro)
        self.assertEqual(self.requisicao("PUT", self.alteracao(**{"coleta.timeout": "42"}))[0], 503)
        self.assertEqual(outro.read_text(), "nao alterar")
