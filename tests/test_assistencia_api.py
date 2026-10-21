"""Contrato web: admin/CSRF, chave nunca retornada e analise sem IA funcional."""
from contextlib import closing
import json
import unittest
from unittest.mock import patch

from core import assistente_ia as ia, db
from tests import test_configuracao_api as config_fixture
from tests.test_dedup import BaseDedup
from web import nucleo


class TestAssistenciaAPI(unittest.TestCase):
    def setUp(self):
        config_fixture.TestConfiguracaoAPI.setUp(self)
        with closing(db.connect(self.banco)) as conn:
            self.con = conn
            db.init_db(conn)
            pos = BaseDedup.posicao(self, -25.123, -54.321)
            self.ponto = BaseDedup.ponto(self, pos)
            conn.commit()

    def pedir(self, rota="/api/v1/gestao/assistente", metodo="GET", dados=None, papel="admin", extra=None):
        env = {"REQUEST_METHOD": metodo, "PATH_INFO": rota, "CONTENT_TYPE": "application/json", "HTTP_X_RADAR_CONFIGURACAO": "1"}
        if papel:
            env["HTTP_X_API_TOKEN"] = self.tokens[papel]
        env.update(extra or {})
        return nucleo.handle_request(env, json.dumps(dados).encode() if dados is not None else b"")

    def test_admin_obrigatorio_e_ia_desligada_por_padrao(self):
        for papel, esperado in ((None, 401), ("contribuidor", 403), ("moderador", 403), ("admin", 200)):
            self.assertEqual(self.pedir(papel=papel)[0], esperado)
        status, headers, corpo = self.pedir()
        self.assertFalse(corpo["assistente"]["habilitado"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_chave_separada_sem_echo_na_configuracao_status_ou_historico(self):
        segredo = "apenas_uma_chave_de_teste_12345"
        rota = "/api/v1/gestao/assistente/chave"
        status, headers, corpo = self.pedir(rota, "PUT", {"chave": segredo})
        self.assertEqual(status, 200)
        self.assertTrue(corpo["assistente"]["chave_configurada"])
        for r in (corpo, self.pedir()[2], self.pedir("/api/v1/gestao/configuracao")[2]):
            self.assertNotIn(segredo, json.dumps(r))
        self.assertNotIn(segredo, self.conf.read_text())
        self.assertEqual(ia.arquivo_chave().read_text(), segredo)
        self.assertEqual(self.pedir(rota, "DELETE", {})[0], 200)
        self.assertFalse(ia.arquivo_chave().exists())

    def test_csrf_e_escopo_bloqueiam_gravacao_de_chave_e_analise(self):
        for rota, dados in (("/api/v1/gestao/assistente/chave", {"chave": "uma_chave_de_teste"}),
                            ("/api/v1/gestao/assistente", {"tarefa": "explicacao", "ponto_id": self.ponto})):
            metodo = "PUT" if rota.endswith("chave") else "POST"
            self.assertEqual(self.pedir(rota, metodo, dados, papel="moderador")[0], 403)
            self.assertEqual(self.pedir(rota, metodo, dados, extra={"HTTP_SEC_FETCH_SITE": "cross-site"})[0], 403)
            self.assertEqual(self.pedir(rota, metodo, dados, extra={"HTTP_X_RADAR_CONFIGURACAO": ""})[0], 403)

    def test_analise_web_local_funciona_sem_chave_sem_rede_e_persiste_proposta(self):
        with patch.object(ia.urllib.request, "build_opener", side_effect=AssertionError("IA desligada")):
            status, _, r = self.pedir(metodo="POST", dados={"tarefa": "explicacao", "ponto_id": self.ponto})
        self.assertEqual(status, 200)
        self.assertEqual(r["ia"]["motivo"], "desativada")
        self.assertFalse(r["dados_oficiais_alterados"])
        self.assertEqual(self.pedir("/api/v1/gestao/assistente/relatorios/" + r["id"])[2], r)

    def test_painel_pode_configurar_provedor_modelo_e_interruptor_sem_chave(self):
        from core import configuracao
        payload = {"revisao": configuracao.consultar()["revisao"], "alteracoes": {
            "assistente.habilitado": "1", "assistente.provedor": "openai_compativel",
            "assistente.url": "https://api.exemplo.invalid/v1", "assistente.modelo": "modelo-escolhido"}}
        self.assertEqual(self.pedir("/api/v1/gestao/configuracao", "PUT", payload)[0], 200)
        self.assertEqual(ia.status()["modelo"], "modelo-escolhido")
        self.assertTrue(ia.status()["habilitado"])
        self.assertFalse(ia.status()["chave_configurada"])
        desativar = {"revisao": configuracao.consultar()["revisao"],
                     "alteracoes": {"assistente.habilitado": "0"}}
        self.assertEqual(self.pedir("/api/v1/gestao/configuracao", "PUT", desativar)[0], 200)
        self.assertFalse(ia.status()["habilitado"])
