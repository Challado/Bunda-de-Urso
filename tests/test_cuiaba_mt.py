# -*- coding: utf-8 -*-
"""Testes offline do conector Cuiaba MT (noticia historica).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.cuiaba_mt import ColetorCuiabaMT
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "cuiaba_mt")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestCuiabaMT(unittest.TestCase):

    def test_evidencia_declara_data_e_contagens(self):
        c = ColetorCuiabaMT()
        _, ext, mime, regs = c.carregar(fx("noticia_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["data_publicacao"], "2015-11-23")
        self.assertFalse(r["tem_dataset_estruturado"])
        cont = r["contagens_declaradas"]
        self.assertEqual(cont["radar_fixo"], 14)
        self.assertEqual(cont["lombada_eletronica"], 3)
        self.assertEqual(cont["avanco_semaforico"], 13)
        self.assertIn("transparencia", r["url_dados_abertos"])

    def test_descobre_documentos_sem_relacao_com_radar(self):
        c = ColetorCuiabaMT()
        _, _, _, regs = c.carregar(fx("noticia_fixture.html"))
        docs = regs[0]["documentos"]
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["tipo"], "documento")
        self.assertTrue(docs[0]["url"].endswith(".pdf"))

    def test_noticia_historica_nao_vira_radar(self):
        c = ColetorCuiabaMT()
        _, _, _, regs = c.carregar(fx("noticia_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorCuiabaMT.resolver_url()
        self.assertEqual(url, ColetorCuiabaMT.PAGINA)
        self.assertIn("cuiaba.mt.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("noticia_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorCuiabaMT().carregar(
                ColetorCuiabaMT.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorCuiabaMT(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("noticia_fixture.html"))
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
