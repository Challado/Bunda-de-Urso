# -*- coding: utf-8 -*-
"""Caminhos: ambiente > /etc/radar-brasil/radar.conf > padrao do checkout.

O que se protege aqui: nenhum script inventa diretorio, a instalacao e
declarativa (um arquivo editavel) e o checkout continua rodando sozinho.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from core import caminhos

ROOT = Path(__file__).resolve().parents[1]
CHAVES = ("RADAR_CONF", "RADAR_BRASIL_HOME", "RADAR_DATA_DIR", "RADAR_DB",
          "RADAR_WEB_ROOT", "RADAR_WEB_URL", "RADAR_LOG_DIR",
          "RADAR_SYNC_CLONE", "RADAR_SYNC_REMOTO")


class BaseCaminhos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="radar-caminhos-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.conf = self.dir / "radar.conf"
        self._salvo = {k: os.environ.get(k) for k in CHAVES}
        for k in CHAVES:
            os.environ.pop(k, None)
        os.environ["RADAR_CONF"] = str(self.conf)
        caminhos.recarregar()
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        for k, v in self._salvo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        caminhos.recarregar()

    def escrever(self, texto):
        self.conf.write_text(textwrap.dedent(texto), encoding="utf-8")
        caminhos.recarregar()


class TestSemConfiguracao(BaseCaminhos):

    def test_checkout_e_o_padrao(self):
        self.assertFalse(caminhos.existe_conf())
        self.assertEqual(caminhos.home(), str(ROOT))
        self.assertEqual(caminhos.data_dir(), str(ROOT / "dados"))
        self.assertEqual(caminhos.banco(), str(ROOT / "dados" / "radar.sqlite3"))
        self.assertEqual(caminhos.bruto(), str(ROOT / "dados" / "raw"))

    def test_arquivo_ausente_nao_e_problema(self):
        self.assertEqual(caminhos.problemas(), [])

    def test_resumo_diz_que_veio_do_padrao(self):
        origens = {(i["secao"], i["chave"]): i["origem"] for i in caminhos.resumo()}
        self.assertEqual(origens[("dados", "banco")], "padrao")


class TestArquivo(BaseCaminhos):

    def test_le_caminhos_do_arquivo(self):
        self.escrever("""
            [instalacao]
            home = /opt/radar
            [dados]
            dir = /servico/dados
            [logs]
            dir = /servico/log
        """)
        self.assertEqual(caminhos.home(), "/opt/radar")
        self.assertEqual(caminhos.data_dir(), "/servico/dados")
        self.assertEqual(caminhos.banco(), "/servico/dados/radar.sqlite3")
        self.assertEqual(caminhos.log_dir(), "/servico/log")
        self.assertEqual(caminhos.problemas(), [])

    def test_banco_explicito_ganha_do_dir(self):
        self.escrever("""
            [dados]
            dir = /servico/dados
            banco = /outro/lugar/radar.sqlite3
        """)
        self.assertEqual(caminhos.banco(), "/outro/lugar/radar.sqlite3")

    def test_banco_vazio_cai_no_dir(self):
        self.escrever("""
            [dados]
            dir = /servico/dados
            banco =
        """)
        self.assertEqual(caminhos.banco(), "/servico/dados/radar.sqlite3")

    def test_caminho_relativo_resolve_contra_a_pasta_do_conf(self):
        self.escrever("""
            [dados]
            dir = dados
        """)
        self.assertEqual(caminhos.data_dir(), str(self.dir / "dados"))

    def test_ambiente_ganha_do_arquivo(self):
        self.escrever("""
            [dados]
            dir = /servico/dados
        """)
        os.environ["RADAR_DATA_DIR"] = "/tmp/outro"
        self.assertEqual(caminhos.data_dir(), "/tmp/outro")
        self.assertEqual(caminhos.banco(), "/tmp/outro/radar.sqlite3")

    def test_chave_desconhecida_vira_problema_sem_derrubar(self):
        self.escrever("""
            [dados]
            diretorio = /servico/dados
        """)
        self.assertEqual(caminhos.data_dir(), str(ROOT / "dados"))
        self.assertTrue(any("chave desconhecida" in p for p in caminhos.problemas()))

    def test_secao_desconhecida_vira_problema(self):
        self.escrever("""
            [inventada]
            home = /qualquer
        """)
        self.assertTrue(any("secao desconhecida" in p for p in caminhos.problemas()))

    def test_url_e_espelho(self):
        self.escrever("""
            [web]
            url = /radar/
            [sincronizacao]
            clone = /dados/clone
            remoto = https://exemplo/repo.git
        """)
        self.assertEqual(caminhos.web_url(), "/radar/")
        self.assertEqual(caminhos.sync_clone(), "/dados/clone")
        self.assertEqual(caminhos.sync_remoto(), "https://exemplo/repo.git")

    def test_espelho_nao_configurado_e_vazio(self):
        self.assertEqual(caminhos.sync_clone(), "")
        self.assertEqual(caminhos.sync_remoto(), "")

    def test_resumo_diz_que_veio_do_arquivo(self):
        self.escrever("""
            [dados]
            dir = /servico/dados
        """)
        origens = {(i["secao"], i["chave"]): i["origem"] for i in caminhos.resumo()}
        self.assertEqual(origens[("dados", "dir")], str(self.conf))


class TestRegraDoRepositorio(unittest.TestCase):

    def test_verificador_de_caminhos_passa(self):
        resultado = subprocess.run(
            [sys.executable, str(ROOT / ".github" / "scripts" / "verificar_caminhos.py")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

    def test_config_vem_da_porta(self):
        texto = (ROOT / "core" / "config.py").read_text(encoding="utf-8")
        self.assertIn("caminhos.data_dir()", texto)
        self.assertIn("caminhos.banco()", texto)
        self.assertIn("caminhos.bruto()", texto)

    def test_manutencao_nao_fixa_banco_de_producao(self):
        for arquivo in sorted((ROOT / "core" / "manutencao").glob("*.py")):
            texto = arquivo.read_text(encoding="utf-8")
            self.assertNotIn("/var/lib/radar", texto, arquivo.name)
            if "DB_PADRAO" in texto:
                self.assertIn("caminhos.banco()", texto, arquivo.name)


if __name__ == "__main__":
    unittest.main()
