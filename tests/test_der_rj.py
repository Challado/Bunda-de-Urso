# -*- coding: utf-8 -*-
"""Testes offline do conector DER-RJ (radares portateis -> TRECHO_ELEGIVEL).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.der_rj import ColetorDERRJ
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestDERRJ(unittest.TestCase):

    def test_carregar_tabela_de_locais(self):
        c = ColetorDERRJ()
        _, ext, mime, regs = c.carregar(fx("der_rj_portateis_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 41)
        r = regs[0]
        self.assertEqual(r["RODOVIA"], "RJ-099")
        self.assertEqual(r["KM"], "5,5")
        self.assertEqual(r["MUNICIPIO"], "Seropedica")

    def test_equipamentos_sao_tabela_separada(self):
        with open(fx("der_rj_portateis_fixture.html"), "rb") as f:
            conteudo = f.read()
        eq = ColetorDERRJ.extrair_equipamentos(conteudo)
        self.assertGreaterEqual(len(eq), 30)
        self.assertIn("NÚMERO DE SÉRIE", eq[0])
        self.assertEqual(eq[0]["NÚMERO DE SÉRIE"], "TC008606")

    def test_normalizar_vira_trecho_elegivel_nunca_radar_fixo(self):
        c = ColetorDERRJ()
        _, _, _, regs = c.carregar(fx("der_rj_portateis_fixture.html"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["tipo_registro"], "trecho_elegivel")
        self.assertEqual(d["indicador"], "pode_haver_fiscalizacao")
        # radar PORTATIL nunca vira radar instalado confirmado
        self.assertIsNone(d["radar_instalado_confirmado"])
        self.assertNotIn("tipo_radar", d)
        self.assertEqual(d["via_codigo"], "RJ-099")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["uf"], "RJ")
        self.assertAlmostEqual(d["km_inicio"], 5.5)
        self.assertAlmostEqual(d["km_fim"], 5.5)
        self.assertIn("radar PORTATIL", d["observacoes"])

    def test_normalizar_sem_rodovia_rejeita(self):
        c = ColetorDERRJ()
        self.assertIsNone(c.normalizar(0, {"RODOVIA": "-", "KM": "1,0"}))
        self.assertIsNone(c.normalizar(0, {"RODOVIA": "", "KM": ""}))

    def test_rodovia_normalizacao(self):
        self.assertEqual(ColetorDERRJ._rodovia("rj 099"), "RJ-099")
        self.assertEqual(ColetorDERRJ._rodovia("RJ-104"), "RJ-104")
        self.assertIsNone(ColetorDERRJ._rodovia("-"))
        self.assertIsNone(ColetorDERRJ._rodovia(None))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorDERRJ.resolver_url()
        self.assertEqual(url, ColetorDERRJ.URL_PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("sgitp.der.rj.gov.br", url)

    def test_download_passa_por_http_baixar(self):
        with open(fx("der_rj_portateis_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorDERRJ().carregar(ColetorDERRJ.URL_PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 41)

    def test_sincronizar_offline_grava_trechos_sem_ponto(self):
        common.ambiente_temporario()
        c = ColetorDERRJ(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("der_rj_portateis_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 41)
            self.assertEqual(res["criados"], 41)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                41)
            # trecho elegivel NAO cria ponto de fiscalizacao
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
