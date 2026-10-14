# -*- coding: utf-8 -*-
"""Testes offline do conector DER-AL (canal institucional, sem lista).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.der_al import ColetorDerAL
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "der_al")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestDerAL(unittest.TestCase):

    def test_evidencia_canal_institucional_sem_lista(self):
        c = ColetorDerAL()
        _, ext, mime, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertTrue(r["orgao_identificado"])
        self.assertTrue(r["fiscaliza_rodovias_estaduais"])
        self.assertFalse(r["publica_lista_equipamentos"])
        self.assertFalse(r["tem_dataset_estruturado"])
        self.assertEqual(r["motivo"], "sem_publicacao")

    def test_canal_institucional_nao_vira_radar(self):
        c = ColetorDerAL()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_canal_oficial(self):
        url = ColetorDerAL.resolver_url()
        self.assertEqual(url, ColetorDerAL.PAGINA)
        self.assertIn("alagoasdigital.al.gov.br", url)

    def test_referencia_municipal_maceio(self):
        c = ColetorDerAL()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIn("maceio.al.gov.br", regs[0]["fonte_municipal_maceio"])

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorDerAL().carregar(ColetorDerAL.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorDerAL(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("pagina_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 1)
            self.assertEqual(res["criados"], 0)
            self.assertEqual(res["rejeitados"], 1)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 1)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
