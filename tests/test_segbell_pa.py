# -*- coding: utf-8 -*-
"""Testes offline do conector SEGBEL Belem (PA) - portarias.

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.segbell_pa import ColetorSEGBELPA
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "segbell_pa")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestSEGBELPA(unittest.TestCase):

    def test_descobre_documentos(self):
        c = ColetorSEGBELPA()
        _, ext, mime, regs = c.carregar(fx("portarias_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 10)
        tipos = [r["tipo"] for r in regs]
        self.assertEqual(tipos.count("portaria"), 8)
        self.assertEqual(tipos.count("mapa_radares"), 1)
        self.assertEqual(tipos.count("certificado_afericao"), 1)

    def test_classifica_ativacao_desativacao(self):
        c = ColetorSEGBELPA()
        _, _, _, regs = c.carregar(fx("portarias_fixture.html"))
        por_numero = {r["numero"]: r for r in regs if r["tipo"] == "portaria"}
        self.assertEqual(por_numero["0677"]["acao"], "ativacao")
        self.assertEqual(por_numero["0677"]["operadora"], "Perkons")
        self.assertEqual(por_numero["0677"]["lote"], "4o")
        self.assertEqual(por_numero["0677"]["data_publicacao"], "2022-09-01")
        self.assertEqual(por_numero["0666"]["acao"], "desativacao")
        self.assertEqual(por_numero["0510"]["acao"], "desativacao")
        self.assertEqual(por_numero["0473"]["acao"], "ativacao")
        self.assertEqual(por_numero["0473"]["lote"], "1o")
        self.assertEqual(por_numero["0677"]["ano"], "2022")

    def test_identificador_da_portaria(self):
        c = ColetorSEGBELPA()
        _, _, _, regs = c.carregar(fx("portarias_fixture.html"))
        por_numero = {r["numero"]: r for r in regs if r["tipo"] == "portaria"}
        self.assertEqual(c.identificador(por_numero["0677"]),
                         "Portaria 0677/2022")

    def test_portaria_nao_vira_cadastro_inventado(self):
        c = ColetorSEGBELPA()
        _, _, _, regs = c.carregar(fx("portarias_fixture.html"))
        for r in regs:
            # ato administrativo nao vira ponto/trecho/radar
            self.assertIsNone(c.normalizar(0, r))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorSEGBELPA.resolver_url()
        self.assertEqual(url, ColetorSEGBELPA.PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("seguranca.belem.pa.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("portarias_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorSEGBELPA().carregar(
                ColetorSEGBELPA.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 10)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorSEGBELPA(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("portarias_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 10)
            self.assertEqual(res["criados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                0)
            # a evidencia bruta permanece registrada
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 10)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
