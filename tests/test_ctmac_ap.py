# -*- coding: utf-8 -*-
"""Testes offline do conector CTMac Macapa - AP (lista de locais HISTORICA).

Nenhum teste acessa a rede: usam a fixture HTML local e substituem
``coletor.http.baixar``. O ponto central: a publicacao e de 2022 (historica),
sem coordenada e sem dataset atual; a lista e PRESERVADA como evidencia bruta,
mas NUNCA vira ponto/radar "atual" (nada inventado).
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.ctmac_ap import ColetorCtmacAP
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, "ctmac_ap", nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestCtmacAP(unittest.TestCase):

    def test_carregar_lista_historica(self):
        c = ColetorCtmacAP()
        _, ext, mime, regs = c.carregar(fx("ctmac_macapa_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 17)
        self.assertEqual(regs[0]["texto"], "Av. Padre Julio (em frente ao Exercito)")
        self.assertEqual(regs[-1]["texto"],
                         "Av. Henrique Galicio com a Rua Sao Jose")
        # o rotulo "Localizacao dos radares" nao vira item
        self.assertTrue(all("Localiza" not in r["texto"] for r in regs))
        # o mapa embutido (sede da Prefeitura) nao vira item
        self.assertTrue(all("Prefeitura" not in r["texto"] for r in regs))

    def test_normalizar_nunca_fabrica_radar_atual(self):
        c = ColetorCtmacAP()
        _, _, _, regs = c.carregar(fx("ctmac_macapa_fixture.html"))
        for i, r in enumerate(regs):
            self.assertIsNone(c.normalizar(i, r))
        # nem mesmo com um texto de radar vira ponto
        self.assertIsNone(c.normalizar(0, {"ordem": 1, "texto": "Av. X, radar 60 km/h"}))

    def test_status_pendente_historico(self):
        self.assertEqual(ColetorCtmacAP.RECURSO["status_integracao"], "pendente")
        self.assertIn("historico", ColetorCtmacAP.FONTE["periodicidade_declarada"])

    def test_resolver_url_pagina_oficial(self):
        url = ColetorCtmacAP.resolver_url()
        self.assertEqual(url, ColetorCtmacAP.PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("macapa.ap.gov.br", url)

    def test_download_passa_por_http_baixar(self):
        with open(fx("ctmac_macapa_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorCtmacAP().carregar(ColetorCtmacAP.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 17)

    def test_sincronizar_preserva_evidencia_sem_pontos(self):
        common.ambiente_temporario()
        c = ColetorCtmacAP(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("ctmac_macapa_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 17)
            self.assertEqual(res["criados"], 0)      # nada normalizado
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(res["status"], "documentado")
            self.assertEqual(res["evidencias_documentais"], res["linhas_recebidas"])
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 17)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"), 0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
