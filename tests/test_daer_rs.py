# -*- coding: utf-8 -*-
"""Testes offline do conector DAER-RS (radar portatil -> TRECHO_ELEGIVEL).

Nenhum teste acessa a rede: usam a fixture CSV local e substituem
``coletor.http.baixar`` por um duble na verificacao da descoberta.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.daer_rs import ColetorDAERRS
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestDAERRS(unittest.TestCase):

    def test_carregar_csv_fixture(self):
        c = ColetorDAERRS()
        _, ext, mime, regs = c.carregar(fx("daer_rs_trechos_fixture.csv"))
        self.assertEqual(ext, ".csv")
        self.assertIn("csv", mime)
        self.assertEqual(len(regs), 74)
        r = regs[0]
        self.assertEqual(r["rodovia"], "RSC 153")
        self.assertEqual(r["km_inicial"], "138")
        self.assertEqual(r["km_final"], "148")
        self.assertEqual(r["unidade"], "CRBM - 1º BRBM")
        self.assertIn("outubro de 2026", r["periodo"])
        # periodos/unidades propagados para todos os registros do bloco
        self.assertTrue(all(x.get("unidade") for x in regs))
        self.assertTrue(all(x.get("periodo") for x in regs))

    def test_normalizar_vira_trecho_elegivel(self):
        c = ColetorDAERRS()
        _, _, _, regs = c.carregar(fx("daer_rs_trechos_fixture.csv"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["tipo_registro"], "trecho_elegivel")
        self.assertEqual(d["indicador"], "pode_haver_fiscalizacao")
        self.assertIsNone(d["radar_instalado_confirmado"])
        self.assertNotIn("tipo_radar", d)
        self.assertEqual(d["via_codigo"], "RSC-153")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["uf"], "RS")
        self.assertAlmostEqual(d["km_inicio"], 138.0)
        self.assertAlmostEqual(d["km_fim"], 148.0)
        self.assertEqual(d["sentido"], "crescente")
        self.assertIn("CRBM/CPRv", d["criterio_inclusao"])

    def test_normalizar_reverso_ordena_km_e_marca_sentido(self):
        c = ColetorDAERRS()
        rev = {"rodovia": "ERS 324", "km_inicial": "268", "km_final": "218"}
        d = c.normalizar(0, rev)
        self.assertEqual(d["km_inicio"], 218.0)
        self.assertEqual(d["km_fim"], 268.0)
        self.assertEqual(d["sentido"], "decrescente")
        # segmento degenerado (mesmo km) fica "ambos"
        d2 = c.normalizar(0, {"rodovia": "ERS 135", "km_inicial": "10",
                              "km_final": "10"})
        self.assertEqual(d2["sentido"], "ambos")

    def test_normalizar_sem_rodovia_rejeita(self):
        c = ColetorDAERRS()
        self.assertIsNone(c.normalizar(0, {"rodovia": "", "km_inicial": "1"}))

    def test_descobrir_pagina_cprv(self):
        html = ('<p><a href="https://crbm.bm.rs.gov.br/radar-movel">Confira a '
                'localizacao</a></p>')
        self.assertEqual(ColetorDAERRS.descobrir_pagina_cprv(html),
                         "https://crbm.bm.rs.gov.br/radar-movel")
        self.assertIsNone(ColetorDAERRS.descobrir_pagina_cprv("<p>nada</p>"))

    def test_descobrir_planilhas_vira_csv(self):
        html = ('<a href="https://docs.google.com/spreadsheets/d/'
                '12-i1iBbrJ71W0_4-twbZWr-p00zZH5WvKy-Kt6GGi0k/export'
                '?format=pdf&size=A4">1o</a>'
                '<a href="https://docs.google.com/spreadsheets/d/'
                '12-i1iBbrJ71W0_4-twbZWr-p00zZH5WvKy-Kt6GGi0k/export'
                '?format=pdf">1o dup</a>')
        urls = ColetorDAERRS.descobrir_planilhas(html)
        self.assertEqual(len(urls), 1)                 # dedup por ID
        self.assertTrue(urls[0].endswith("/export?format=csv"))
        self.assertIn("12-i1iBbrJ71W0", urls[0])

    def test_resolver_planilhas_segue_pagina_e_cprv(self):
        pagina = '<a href="https://crbm.bm.rs.gov.br/radar-movel">x</a>'
        cprv = ('<a href="https://docs.google.com/spreadsheets/d/'
                'AAAAAAAAAAAAAAAAAAAAAAAA/export?format=pdf">1</a>')
        with mock.patch.object(
                http, "baixar",
                side_effect=[_resp(pagina), _resp(cprv)]) as m:
            urls = ColetorDAERRS.resolver_planilhas()
        self.assertEqual(m.call_count, 2)
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("export?format=csv"))

    def test_resolver_planilhas_tolerante_a_falha(self):
        with mock.patch.object(http, "baixar",
                               side_effect=RuntimeError("portal fora")):
            self.assertEqual(ColetorDAERRS.resolver_planilhas(), [])

    def test_resolver_url_devolve_as_planilhas(self):
        """O tick entrega resolver_url() direto ao carregar(); tem de ser a
        LISTA de CSVs (nao a pagina HTML, que daria 0 linhas)."""
        pagina = '<a href="https://crbm.bm.rs.gov.br/radar-movel">x</a>'
        cprv = ('<a href="https://docs.google.com/spreadsheets/d/'
                'AAAAAAAAAAAAAAAAAAAAAAAA/export?format=pdf">1</a>')
        with mock.patch.object(http, "baixar",
                               side_effect=[_resp(pagina), _resp(cprv)]):
            urls = ColetorDAERRS.resolver_url()
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("export?format=csv"))

    def test_resolver_url_erro_quando_sem_planilha(self):
        with mock.patch.object(http, "baixar",
                               side_effect=RuntimeError("portal fora")):
            with self.assertRaises(http.ErroFonte):
                ColetorDAERRS.resolver_url()

    def test_carregar_lista_de_urls_usa_http_baixar(self):
        with open(fx("daer_rs_trechos_fixture.csv"), "rb") as f:
            csv_bytes = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(csv_bytes)) as m:
            _, ext, _, regs = ColetorDAERRS().carregar(
                ["https://docs.google.com/spreadsheets/d/X/export?format=csv"])
        self.assertEqual(m.call_count, 1)
        self.assertEqual(ext, ".csv")
        self.assertEqual(len(regs), 74)

    def test_sincronizar_offline_grava_todos_os_trechos(self):
        common.ambiente_temporario()
        c = ColetorDAERRS(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("daer_rs_trechos_fixture.csv"))
            self.assertEqual(res["linhas_recebidas"], 74)
            self.assertEqual(res["criados"], 74)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                74)
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
