# -*- coding: utf-8 -*-
"""Testes offline do conector Semob Joao Pessoa - PB (medidores de velocidade).

Nenhum teste acessa a rede: usam a fixture HTML local e substituem
``coletor.http.baixar``. A fonte publica ENDERECOS sem coordenada; NADA de GPS
inventado e cada local vira cadastro SEM POSICAO_GEOGRAFICA. O recurso e
PARCIAL: a relacao completa esta em PDF (ilegivel pela stdlib) no portal.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.semob_pb import ColetorSemobPB, _logradouro, _sentido
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, "semob_pb", nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestSemobPB(unittest.TestCase):

    def test_carregar_lista_de_locais(self):
        c = ColetorSemobPB()
        _, ext, mime, regs = c.carregar(fx("semob_jp_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 6)
        self.assertEqual(regs[0]["texto"][:5], "Rua B")
        self.assertIn("Epitacio Pessoa", regs[-1]["texto"])

    def test_normalizar_sem_gps(self):
        c = ColetorSemobPB()
        _, _, _, regs = c.carregar(fx("semob_jp_fixture.html"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["uf"], "PB")
        self.assertEqual(d["municipio_nome"], "Joao Pessoa")
        self.assertEqual(d["municipio_ibge"], "2507507")
        self.assertEqual(d["via_tipo"], "municipal")
        self.assertEqual(d["via_codigo"],
                         "Rua Bancario Waldemar de Mesquita Accioly")
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["tipo_radar"], "desconhecido")
        self.assertIn("PDF ilegivel", d["observacoes"])
        for i, r in enumerate(regs):
            dd = c.normalizar(i, r)
            self.assertIsNone(dd["latitude"])
            self.assertIsNone(dd["longitude"])

    def test_logradouro_e_sentido(self):
        self.assertEqual(
            _logradouro("Rua Bancario Waldemar de Mesquita Accioly (sentido Centro)"),
            "Rua Bancario Waldemar de Mesquita Accioly")
        self.assertEqual(
            _logradouro("Avenida Epitacio Pessoa x Rua Paulino Pinto (praia/Centro)"),
            "Avenida Epitacio Pessoa x Rua Paulino Pinto")
        self.assertIsNone(_logradouro("sem via na frente"))
        self.assertEqual(_sentido("(sentido Centro)")[1], "Centro")
        self.assertEqual(_sentido("sem indicacao"), (None, None))

    def test_status_parcial_e_portal(self):
        self.assertEqual(ColetorSemobPB.RECURSO["status_integracao"], "parcial")
        self.assertIn("portal.semobjp.pb.gov.br",
                      ColetorSemobPB.URL_RELACAO_OFICIAL)

    def test_resolver_url_pagina_oficial(self):
        url = ColetorSemobPB.resolver_url()
        self.assertEqual(url, ColetorSemobPB.PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("joaopessoa.pb.gov.br", url)

    def test_download_passa_por_http_baixar(self):
        with open(fx("semob_jp_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorSemobPB().carregar(ColetorSemobPB.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 6)

    def test_sincronizar_sem_ponto_geografico(self):
        common.ambiente_temporario()
        c = ColetorSemobPB(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("semob_jp_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 6)
            self.assertEqual(res["criados"], 6)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                6)
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"), 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
