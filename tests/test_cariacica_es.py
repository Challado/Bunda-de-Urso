# -*- coding: utf-8 -*-
"""Testes offline do conector Cariacica-ES (mapa de radares -> KML).

Nenhum teste acessa a rede: usam a fixture KML local e substituem
``coletor.http.baixar`` para verificar a descoberta do MID e o download.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.cariacica_es import ColetorCariacica
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


PAGINA_HTML = ('<a href="https://www.google.com/maps/d/u/0/embed'
               '?mid=1mhWiOBdxJtxmhcvUWExBEwiFSTBcU0A&amp;ehbc=2E312F'
               '&amp;noprof=1&amp;ll=-20.32,-40.37&amp;z=16">Consulte no mapa'
               '</a>'
               '<a href="/uploads/files/servicos/mapa-de-radares/'
               'faixas-monitoradas.pdf">Planilha - Faixas monitoradas'
               ' (PDF, 224 KB)</a>')


class TestCariacicaES(unittest.TestCase):

    def test_carregar_kml_fixture(self):
        c = ColetorCariacica()
        _, ext, mime, regs = c.carregar(fx("cariacica_radares_fixture.kml"))
        self.assertEqual(ext, ".kml")
        self.assertIn("kml", mime)
        self.assertEqual(len(regs), 13)
        r = regs[0]
        self.assertEqual(r["nome"], "Mário Gurgel")
        self.assertAlmostEqual(r["lat"], -20.3323, places=4)
        self.assertAlmostEqual(r["lon"], -40.367228, places=5)
        self.assertIn("Codigo", r["atributos"])
        self.assertEqual(r["atributos"]["Marca"], "1: Perkons")

    def test_descobrir_mid(self):
        self.assertEqual(ColetorCariacica.descobrir_mid(PAGINA_HTML),
                         "1mhWiOBdxJtxmhcvUWExBEwiFSTBcU0A")
        self.assertIsNone(ColetorCariacica.descobrir_mid("<p>sem mapa</p>"))

    def test_descobrir_documentos(self):
        docs = ColetorCariacica.descobrir_documentos(PAGINA_HTML)
        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0]["url"].endswith("faixas-monitoradas.pdf"))
        self.assertIn("Faixas monitoradas", docs[0]["titulo"])

    def test_normalizar_vira_ponto_fixo(self):
        c = ColetorCariacica()
        _, _, _, regs = c.carregar(fx("cariacica_radares_fixture.kml"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["tipo_registro"], "ponto_fiscalizacao")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["uf"], "ES")
        self.assertEqual(d["municipio_nome"], "Cariacica")
        self.assertEqual(d["via_codigo"], "Mário Gurgel")
        self.assertEqual(d["via_tipo"], "municipal")
        self.assertAlmostEqual(d["latitude"], -20.3323, places=4)
        self.assertAlmostEqual(d["longitude"], -40.367228, places=5)
        self.assertEqual(d["fabricante"], "Perkons")     # prefixo "1: " removido
        self.assertEqual(d["modelo"], "SMARTPK FROD")
        self.assertIsNone(d["numero_serie"])
        self.assertEqual(d["velocidade_geral"], 60.0)
        self.assertIn("Registro INMETRO", d["observacoes"])

    def test_normalizar_sem_coordenada_rejeita(self):
        c = ColetorCariacica()
        self.assertIsNone(c.normalizar(0, {"nome": "X", "lat": None,
                                           "lon": None, "atributos": {}}))

    def test_parse_kml_recusa_doctype(self):
        with self.assertRaises(http.ErroFonte):
            ColetorCariacica._parse_kml(
                b'<!DOCTYPE kml [<!ENTITY x "y">]><kml/>')

    def test_parse_kml_invalido(self):
        with self.assertRaises(http.ErroFonte):
            ColetorCariacica._parse_kml(b"isto nao e xml")

    def test_resolver_kml_descobre_mid_e_baixa(self):
        with mock.patch.object(http, "baixar",
                               return_value=_resp(PAGINA_HTML)) as m:
            url = ColetorCariacica.resolver_kml()
        self.assertTrue(m.called)
        self.assertIn("mid=1mhWiOBdxJtxmhcvUWExBEwiFSTBcU0A", url)
        self.assertIn("forcekml=1", url)
        self.assertTrue(url.startswith("https://www.google.com/maps/d/kml"))

    def test_carregar_url_usa_http_baixar_em_dois_saltos(self):
        with open(fx("cariacica_radares_fixture.kml"), "rb") as f:
            kml = f.read()
        with mock.patch.object(
                http, "baixar",
                side_effect=[_resp(PAGINA_HTML), _resp(kml)]) as m:
            _, ext, _, regs = ColetorCariacica().carregar(
                ColetorCariacica.PAGINA)
        self.assertEqual(m.call_count, 2)
        self.assertEqual(ext, ".kml")
        self.assertEqual(len(regs), 13)

    def test_sincronizar_offline_grava_pontos(self):
        common.ambiente_temporario()
        c = ColetorCariacica(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("cariacica_radares_fixture.kml"))
            self.assertEqual(res["linhas_recebidas"], 13)
            self.assertEqual(res["criados"], 13)
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 13)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM EQUIPAMENTO"), 13)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
