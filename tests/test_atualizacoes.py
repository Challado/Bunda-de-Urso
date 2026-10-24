"""Relatorios reais pela API, preservacao, concorrencia e diagnostico de falhas."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import atualizacoes, caminhos
from core.instalacao import _executar

ROOT = Path(__file__).resolve().parents[1]


class RelatoriosTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="radar-diario-")
        self.addCleanup(temp.cleanup)
        self.pasta = Path(temp.name)
        self.home = self.pasta / "codigo"
        (self.home / "core").mkdir(parents=True)
        self.conf = self.pasta / "radar.conf"
        self.conf.write_text("[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[logs]\ndir = %s\n" % (
            self.home, self.pasta / "dados", self.pasta / "dados/radar.sqlite3", self.pasta / "dados/logs"))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("RADAR_") and k not in ("REQUEST_METHOD", "GATEWAY_INTERFACE")}
        self.env["RADAR_CONF"] = str(self.conf)
        ambiente = patch.dict(os.environ, self.env, clear=True)
        ambiente.start()
        caminhos.recarregar()
        self.addCleanup(caminhos.recarregar)
        self.addCleanup(ambiente.stop)

    def estado(self):
        return json.loads(Path(caminhos.status_atualizacoes()).read_text())

    def api(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "web/api.pse"), *args], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_erro_preserva_stdout_stderr_codigo_traceback_e_nao_vaza_credenciais(self):
        with self.assertRaises(subprocess.CalledProcessError):
            with atualizacoes.acompanhar("instalacao"):
                _executar([sys.executable, "-c", "import sys; print('saida completa'); sys.stderr.write('falha detalhada\\n'); sys.exit(7)"])
        instalacao = self.estado()["operacoes"]["instalacao"]
        self.assertEqual(instalacao["estado"], "erro")
        self.assertIn("CalledProcessError", instalacao["traceback"])
        falha = next(e for e in instalacao["erros"] if e.get("codigo_comando") == 7)
        self.assertEqual(falha["stdout"], "saida completa\n")
        self.assertEqual(falha["stderr"], "falha detalhada\n")
        self.assertTrue(Path(instalacao["arquivo_relatorio"]).is_file())
        atualizacoes.registrar("teste", {"token": "credencial-exemplo", "mensagem": "https://usuario:senha-exemplo@exemplo.org/?api_key=chave-exemplo"})
        for arquivo in (Path(caminhos.status_atualizacoes()), Path(caminhos.log_atualizacoes())):
            texto = arquivo.read_text()
            for segredo in ("credencial-exemplo", "senha-exemplo", "chave-exemplo"):
                self.assertNotIn(segredo, texto)

    def test_concorrencia_preserva_todas_as_fontes_e_diario_json_valido(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: atualizacoes.registrar("coleta", {"estado": "ok", "numero": i}, fonte=i), range(32)))
        self.assertEqual(len(self.estado()["fontes"]), 32)
        linhas = Path(caminhos.log_atualizacoes()).read_text().splitlines()
        self.assertEqual(len(linhas), 32)
        self.assertEqual({json.loads(l)["numero"] for l in linhas}, set(range(32)))

    def test_corrompido_e_preservado_e_recriado_com_observacao(self):
        atualizacoes.registrar("teste", {"estado": "ok"})
        Path(caminhos.status_atualizacoes()).write_text("{incompleto")
        atualizacoes.registrar("teste", {"estado": "ok"})
        antigo = Path(self.estado()["erro_status_anterior"]["arquivo_preservado"])
        self.assertEqual(antigo.read_text(), "{incompleto")

    def test_falha_no_diario_e_visivel_sem_mudar_resultado(self):
        with patch.object(atualizacoes, "_atomico", side_effect=PermissionError("sem permissao")), patch("sys.stderr") as erro:
            atualizacoes.registrar("teste", {"estado": "ok"})
        self.assertIn("sem permissao", "".join(c.args[0] for c in erro.write.call_args_list))

    def test_interrupcao_sem_conclusao_nao_e_anunciada_como_sucesso(self):
        atualizacoes.registrar("instalacao", {"estado": "em_andamento", "id": "antigo", "pid": 123456789})
        atualizacoes.registrar("tick", {"estado": "ok"})
        self.assertEqual(self.estado()["operacoes"]["instalacao"]["estado"], "interrompido")
        self.assertIn("instalacao", self.estado()["resumo"]["operacoes_com_erro"])

    def test_coleta_real_pela_api_registra_contadores_hash_e_erro_completo(self):
        r = self.api("ferramenta", "inicializar_banco")
        self.assertEqual(r.returncode, 0, r.stderr)
        arquivo = next((ROOT / "tests/fixtures").glob("antt*.json"))
        r = self.api("sync", "--fonte", "antt", "--arquivo", str(arquivo))
        self.assertEqual(r.returncode, 0, r.stderr)
        fonte = next(iter(self.estado()["fontes"].values()))
        self.assertEqual(fonte["estado"], "ok")
        self.assertEqual(fonte["contadores"]["linhas_recebidas"], 4)
        self.assertEqual(fonte["contadores"]["linhas_validas"], 3)
        self.assertTrue(fonte["erros_validacao"])
        self.assertEqual(len(fonte["hash_sha256"]), 64)
        primeiro = json.loads(Path(fonte["arquivo_relatorio"]).read_text())
        ruim = self.pasta / "invalido.json"
        ruim.write_text("{json invalido")
        r = self.api("sync", "--fonte", "antt", "--arquivo", str(ruim))
        self.assertNotEqual(r.returncode, 0)
        fonte = next(iter(self.estado()["fontes"].values()))
        self.assertEqual(fonte["estado"], "erro")
        self.assertIn("JSONDecodeError", fonte["contadores"]["traceback"])
        self.assertEqual(json.loads(Path(primeiro["arquivo_relatorio"]).read_text())["estado"], "ok")
        self.assertTrue(Path(fonte["arquivo_relatorio"]).is_file())

    def test_rejeicoes_tambem_tem_descricao_no_json(self):
        from coletor.base import ColetorBase
        coletor = ColetorBase()
        coletor._diario_coleta = {"erros_validacao": []}
        with patch.object(type(coletor), "conn", new_callable=unittest.mock.PropertyMock) as conn, patch("coletor.base.dbmod.insert"):
            conn.return_value = unittest.mock.Mock()
            coletor._rejeitar(12, 7, "coordenada_invalida", "descricao completa " * 80)
        self.assertGreater(len(coletor._diario_coleta["erros_validacao"][0]["descricao"]), 500)

    def test_link_continua_apontando_estado_apos_troca_do_codigo(self):
        atualizacoes.registrar("instalacao", {"estado": "ok"})
        atualizacoes.publicar_link()
        self.home.rename(self.pasta / "codigo-antigo")
        (self.home / "core").mkdir(parents=True)
        atualizacoes.publicar_link()
        self.assertEqual(json.loads(Path(caminhos.link_atualizacoes()).read_text())["operacoes"]["instalacao"]["estado"], "ok")
