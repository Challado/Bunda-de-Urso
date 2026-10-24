# -*- coding: utf-8 -*-
"""Testes offline do conector STRANS Teresina PI (noticia historica 2019).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.teresina_pi import ColetorTeresinaPI
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "teresina_pi")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestTeresinaPI(unittest.TestCase):

    def test_evidencia_declara_data_e_tipos(self):
        c = ColetorTeresinaPI()
        _, ext, mime, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["data_publicacao"], "2019-04-10")
        self.assertEqual(r["tipos_radares_citados"], ["estatico", "fixo"])
        self.assertTrue(r["anuncia_divulgacao_mensal"])
        self.assertTrue(r["aponta_aba_localizacao_radares"])
        self.assertFalse(r["publica_lista_na_pagina"])
        self.assertFalse(r["tem_dataset_estruturado"])
        self.assertEqual(r["motivo"], "pendente_lai")

    def test_noticia_historica_nao_vira_radar(self):
        c = ColetorTeresinaPI()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorTeresinaPI.resolver_url()
        self.assertEqual(url, ColetorTeresinaPI.PAGINA)
        self.assertIn("pmt.pi.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorTeresinaPI().carregar(
                ColetorTeresinaPI.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorTeresinaPI(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("pagina_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 1)
            self.assertEqual(res["criados"], 0)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(res["status"], "documentado")
            self.assertEqual(res["evidencias_documentais"], res["linhas_recebidas"])
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 1)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
