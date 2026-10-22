"""Regressoes observadas no relatorio real do servidor3 em 22/10/2026."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from core import atualizacoes, auditoria_instalacao
from coletor.fontes.recife import ColetorRecife
from tests import test_atualizacoes as base_testes
from tests.test_http import _Resp
from coletor import http
import unittest


class RevisaoRelatoriosTest(unittest.TestCase):
    setUp = base_testes.RelatoriosTest.setUp
    estado = base_testes.RelatoriosTest.estado
    api = base_testes.RelatoriosTest.api

    def _servicos(self, cron_ativo=True):
        def executar(cmd, **kw):
            codigo = 0
            if cmd[1] == "is-active":
                codigo = 4 if cmd[2] == "crond.service" else 0
                if cmd[2] == "cron.service" and not cron_ativo:
                    codigo = 3
            return subprocess.CompletedProcess(cmd, codigo, "active" if codigo == 0 else "unknown", "")
        with atualizacoes.acompanhar("instalacao") as registro:
            with patch("core.auditoria_instalacao.shutil.which", return_value="/bin/comando"), patch(
                    "core.auditoria_instalacao.subprocess.run", side_effect=executar):
                checagens = auditoria_instalacao.ambiente_servidor()
            registro.terminar(0 if cron_ativo else 1)
        return checagens, self.estado()["operacoes"]["instalacao"]

    def test_crond_ausente_nao_e_erro_com_cron_ativo(self):
        checagens, registro = self._servicos()
        self.assertEqual(next(c["estado"] for c in checagens if c["checagem"] == "servico.cron"), "ok")
        self.assertEqual(registro["erros"], [])
        sondagem = next(e for e in registro["etapas"] if e.get("unidade") == "crond.service")
        self.assertEqual(sondagem["codigo_comando"], 4)
        self.assertTrue(sondagem["codigo_esperado"])

    def test_nenhum_cron_ativo_continua_sendo_erro_real(self):
        checagens, registro = self._servicos(False)
        self.assertEqual(next(c["estado"] for c in checagens if c["checagem"] == "servico.cron"), "erro")
        self.assertTrue(any("Nenhuma unidade ativa" in e.get("erro", "") for e in registro["erros"]))

    def test_retorno_nao_zero_de_comando_comum_nao_e_escondido(self):
        with atualizacoes.acompanhar("instalacao") as registro:
            registro.evento("comando", codigo_comando=4, stderr="Falha real")
            registro.terminar(1)
        self.assertEqual(len(self.estado()["operacoes"]["instalacao"]["erros"]), 1)

    def test_tick_importa_erro_anterior_ao_diario_e_preserva_detalhamento_novo(self):
        self.assertEqual(self.api("ferramenta", "inicializar_banco").returncode, 0)
        ruim = self.pasta / "invalido.json"
        ruim.write_text("{nao e json")
        self.assertNotEqual(self.api("sync", "--fonte", "antt", "--arquivo", str(ruim)).returncode, 0)
        from core import caminhos
        Path(caminhos.status_atualizacoes()).unlink()  # simula banco anterior ao diario
        r = self.api("tick", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        fonte = next(v for v in self.estado()["fontes"].values() if v["fonte"].startswith("ANTT"))
        self.assertEqual(fonte["estado"], "erro")
        self.assertEqual(fonte["agenda"]["conector"], "antt")
        self.assertIn("JSONDecodeError", fonte["contadores"]["erro_codigo"])
        self.assertIn(str(fonte["recurso_id"]), self.estado()["resumo"]["fontes_com_erro"])
        self.assertTrue(any(v["fonte"].startswith("ANTT") for v in self.estado()["resumo"]["falhas_atuais"]))
        self.assertGreaterEqual(self.estado()["resumo"]["total_recursos_acompanhados"], 48)
        self.assertTrue(any(v["estado"] == "nunca_coletado" for v in self.estado()["fontes"].values()))
        self.assertNotEqual(self.api("sync", "--fonte", "antt", "--arquivo", str(ruim)).returncode, 0)
        self.assertEqual(self.api("tick", "--dry-run").returncode, 0)
        fonte = next(v for v in self.estado()["fontes"].values() if v["fonte"].startswith("ANTT"))
        self.assertIn("JSONDecodeError", fonte["contadores"]["traceback"])

    def test_recife_manual_resolve_csv_em_vez_de_baixar_pagina_dataset(self):
        corpo = b"id;latitude;longitude\nR1;-8.05;-34.9\n"
        url = "https://dados.recife.pe.gov.br/download/edicao-atual.csv"
        with patch.object(ColetorRecife, "resolver_url", return_value=url), patch(
                "coletor.fontes.recife.http.baixar", return_value=(corpo, {}, url)) as baixar:
            self.assertEqual(ColetorRecife().carregar(None)[3][0]["id"], "R1")
        baixar.assert_called_once_with(url)

    def test_http_200_com_bloqueio_nao_e_tratado_como_planilha_ou_json(self):
        resposta = _Resp(200, b"<html><title>Request Rejected</title>The requested URL was rejected</html>")
        with patch.object(http, "_abrir", return_value=resposta) as abrir:
            with self.assertRaisesRegex(http.ErroFonte, "pagina de bloqueio"):
                http.baixar("https://dados.antt.gov.br/recurso.json")
        self.assertEqual(abrir.call_count, 1)

    def test_url_temporaria_de_publicacao_nao_expoe_chave_no_diario(self):
        valor = atualizacoes.limpar('https://script.googleusercontent.com/macros/echo?user_content_key=segredo-de-teste&lib=publicacao')
        self.assertNotIn('segredo-de-teste', valor)
        self.assertIn('lib=publicacao', valor)

    def test_navegador_encerra_filhos_mesmo_apos_saida_do_launcher(self):
        from coletor.exportacao_publica import _encerrar_navegador
        marca = self.pasta / "filho_sobreviveu"
        filho = "import time,pathlib; time.sleep(.3); pathlib.Path(" + repr(str(marca)) + ").write_text('vivo'); time.sleep(5)"
        pai = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(filho) + "])"
        processo = subprocess.Popen([sys.executable, '-c', pai], start_new_session=True)
        processo.wait(timeout=5)
        _encerrar_navegador(processo, None)
        time.sleep(.4)
        self.assertFalse(marca.exists())
