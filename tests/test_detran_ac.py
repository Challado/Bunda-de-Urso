# -*- coding: utf-8 -*-
"""Testes offline do conector Detran-AC (portal institucional, sem cadastro).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.detran_ac import ColetorDetranAC
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "detran_ac")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestDetranAC(unittest.TestCase):

    def test_evidencia_publica_servicos_sem_cadastro(self):
        c = ColetorDetranAC()
        _, ext, mime, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertTrue(r["publica_consulta_de_autos_radar"])
        self.assertTrue(r["publica_convenios_fiscalizacao"])
        self.assertFalse(r["tem_cadastro_equipamentos"])
        self.assertFalse(r["tem_dataset_estruturado"])
        self.assertEqual(r["motivo"], "pendente_lai")

    def test_aponta_referencia_historica(self):
        c = ColetorDetranAC()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIn("agencia.ac.gov.br", regs[0]["referencia_historica"])

    def test_portal_nao_vira_radar(self):
        c = ColetorDetranAC()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorDetranAC.resolver_url()
        self.assertEqual(url, ColetorDetranAC.PAGINA)
        self.assertIn("detran.ac.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorDetranAC().carregar(
                ColetorDetranAC.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorDetranAC(db_path=config.DB_PATH)
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
