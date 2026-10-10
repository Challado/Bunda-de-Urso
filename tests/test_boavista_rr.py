# -*- coding: utf-8 -*-
"""Testes offline do conector Boa Vista RR (noticia historica, imagem).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.boavista_rr import ColetorBoaVistaRR
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "boavista_rr")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestBoaVistaRR(unittest.TestCase):

    def test_evidencia_declara_contagens(self):
        c = ColetorBoaVistaRR()
        _, ext, mime, regs = c.carregar(fx("noticia_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["total_radares_declarado"], 18)
        self.assertEqual(r["novos_equipamentos_declarado"], 8)
        self.assertFalse(r["tem_dataset_estruturado"])

    def test_lista_em_imagem_detectada(self):
        c = ColetorBoaVistaRR()
        _, _, _, regs = c.carregar(fx("noticia_fixture.html"))
        r = regs[0]
        self.assertTrue(r["lista_em_imagem"])
        urls = [x["url"] for x in r["recursos"]]
        self.assertTrue(any(u.endswith("radar.png") for u in urls))
        radar = [x for x in r["recursos"] if x["url"].endswith("radar.png")][0]
        self.assertEqual(radar["tipo"], "imagem_localizacao")
        self.assertFalse(radar["legivel_por_stdlib"])

    def test_noticia_historica_nao_vira_radar(self):
        c = ColetorBoaVistaRR()
        _, _, _, regs = c.carregar(fx("noticia_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorBoaVistaRR.resolver_url()
        self.assertEqual(url, ColetorBoaVistaRR.PAGINA)
        self.assertIn("boavista.rr.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("noticia_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorBoaVistaRR().carregar(
                ColetorBoaVistaRR.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorBoaVistaRR(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("noticia_fixture.html"))
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
