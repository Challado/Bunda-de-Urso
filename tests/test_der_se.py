# -*- coding: utf-8 -*-
"""Testes offline do conector DER-SE (localizacao de radares e lombadas fixas).

Sem rede: usam a fixture CSV real (exportacao da planilha publicada na pagina) e
dubles para a descoberta dos iframes. Verificam a extracao da coordenada
embutida no link do Google Maps, o tratamento do municipio com codigo, a
normalizacao e a preservacao de linhas sem coordenada (sem GPS artificial).
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes import der_se
from coletor.fontes.der_se import ColetorDERSE
from core import config
from core import db as dbmod
import tests.common as common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "der_se")
CSV = os.path.join(FIX, "radares.csv")

# Fragmento real da pagina (iframes reais de 10/10/2026).
HTML_PAGINA = """<html><body>
<iframe title="radares" src="https://docs.google.com/spreadsheets/d/e/2PACX-1vTsjvD1KDfkk7ZInL2TE0d3zM9j_7MOS34BoeRgiV23xKbSLjFyO2n9KWnqRuv_mYUnSYpJsbsQYS1F/pubhtml?gid=1987757175&#038;single=true"></iframe>
<iframe title="cameras" src="https://docs.google.com/spreadsheets/d/e/2PACX-1vQK5_zDnYUr2-VHyHKxfdsbXppEb6yfed7yuh3bz24okL4JsJLC78DAoMXt-D6ltIWp6H7dhTjELT85/pubhtml?gid=1959991435&#038;single=true"></iframe>
</body></html>"""


def _resp(conteudo, url="https://x/"):
    dados = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    return (dados, {}, url)


class TestDERSeCarregar(unittest.TestCase):

    def test_carregar_csv(self):
        _, ext, mime, regs = ColetorDERSE().carregar(CSV)
        self.assertEqual(ext, ".csv")
        self.assertEqual(mime, "text/csv")
        self.assertEqual(len(regs), 129)
        self.assertEqual(regs[0]["CÓDIGO EQUIPAMENTO"], "SE001R")
        self.assertEqual(regs[0]["RODOVIA"], "SE-100")


class TestDERSeNormalizar(unittest.TestCase):

    def test_normalizar_com_coordenada(self):
        c = ColetorDERSE()
        _, _, _, regs = c.carregar(CSV)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "SE001R")
        self.assertEqual(d["uf"], "SE")
        self.assertEqual(d["municipio_nome"], "Aracaju")   # " (3105)" removido
        self.assertEqual(d["via_codigo"], "SE-100")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["velocidade_geral"], 50.0)
        self.assertAlmostEqual(d["latitude"], -11.062782, places=6)
        self.assertAlmostEqual(d["longitude"], -37.101103, places=6)

    def test_normalizar_sem_coordenada_preserva_sem_gps(self):
        c = ColetorDERSE()
        _, _, _, regs = c.carregar(CSV)
        d = c.normalizar(0, regs[-1])          # SE398R (link curto, sem query)
        self.assertEqual(d["identificador"], "SE398R")
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["municipio_nome"], "Simão Dias")


class TestDERSeDescobrir(unittest.TestCase):

    def test_csv_de_pubhtml(self):
        url = ColetorDERSE._csv_de_pubhtml(
            "https://docs.google.com/spreadsheets/d/e/ABC/pubhtml"
            "?gid=1987757175&single=true")
        self.assertTrue(url.startswith(
            "https://docs.google.com/spreadsheets/d/e/ABC/pub?"))
        self.assertIn("gid=1987757175", url)
        self.assertTrue(url.endswith("output=csv"))
        self.assertIsNone(ColetorDERSE._csv_de_pubhtml("https://x/y.csv"))

    def test_descobrir_recursos_offline(self):
        achados = ColetorDERSE.descobrir_recursos(HTML_PAGINA)
        self.assertIn("radares", achados)
        self.assertIn("cameras", achados)
        self.assertIn("gid=1987757175", achados["radares"])
        self.assertTrue(achados["radares"].endswith("output=csv"))
        self.assertIn("gid=1959991435", achados["cameras"])

    def test_resolver_url_usa_pagina_e_cai_no_fallback(self):
        with mock.patch.object(der_se.http, "baixar",
                               return_value=_resp(HTML_PAGINA)):
            url = ColetorDERSE.resolver_url()
        self.assertIn("gid=1987757175", url)
        self.assertIn("output=csv", url)
        with mock.patch.object(der_se.http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorDERSE.resolver_url()
        self.assertEqual(url, ColetorDERSE.URL_FALLBACK)

    def test_download_passa_por_http_baixar(self):
        with open(CSV, "rb") as f:
            conteudo = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(conteudo)) as m:
            _, _, _, regs = ColetorDERSE().carregar(
                ColetorDERSE.URL_FALLBACK)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 129)


class TestDERSeSync(unittest.TestCase):

    def test_sincronizar_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorDERSE(db_path=config.DB_PATH)
        try:
            resumo = c.sincronizar(CSV, publicar=False)
            self.assertEqual(resumo["linhas_recebidas"], 129)
            self.assertEqual(resumo["criados"], 129)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                129)
            # so as linhas com coordenada viram posicao
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"),
                85)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
