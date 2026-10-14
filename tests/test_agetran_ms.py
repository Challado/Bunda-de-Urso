# -*- coding: utf-8 -*-
"""Testes offline do conector Agetran Campo Grande - MS (radares).

Nenhum teste acessa a rede: usam a fixture HTML local e substituem
``coletor.http.baixar``. A fonte publica ENDERECOS sem coordenada; NADA de GPS
inventado e cada local vira cadastro SEM POSICAO_GEOGRAFICA.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.agetran_ms import ColetorAgetranMS, _logradouro, _sentido
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, "agetran_ms", nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestAgetranMS(unittest.TestCase):

    def test_carregar_lista_de_enderecos(self):
        c = ColetorAgetranMS()
        _, ext, mime, regs = c.carregar(fx("agetran_cg_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 8)
        self.assertEqual(regs[0]["texto"][:28],
                         "Avenida Ministro Joao Arinos")
        self.assertEqual(regs[1]["texto"][:13], "Rua Brilhante")
        # a lista para no <ul> dos enderecos (nao pega "related posts")
        self.assertNotIn("interdicoes", " ".join(r["texto"] for r in regs))

    def test_normalizar_sem_gps(self):
        c = ColetorAgetranMS()
        _, _, _, regs = c.carregar(fx("agetran_cg_fixture.html"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["uf"], "MS")
        self.assertEqual(d["municipio_nome"], "Campo Grande")
        self.assertEqual(d["municipio_ibge"], "5002704")
        self.assertEqual(d["via_tipo"], "municipal")
        self.assertEqual(d["via_codigo"], "Avenida Ministro Joao Arinos")
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["tipo_radar"], "desconhecido")
        # "(em ambos os sentidos da via)"
        self.assertEqual(d["sentido"], "ambos")
        self.assertIn("15/07/2026", d["observacoes"])
        for i, r in enumerate(regs):
            dd = c.normalizar(i, r)
            self.assertIsNone(dd["latitude"])
            self.assertIsNone(dd["longitude"])

    def test_logradouro_e_sentido(self):
        self.assertEqual(_logradouro("Rua Ceara: no cruzamento com a Rua Amazonas"),
                         "Rua Ceara")
        self.assertEqual(_logradouro("Avenida Bandeirantes: proximo ao cruzamento"),
                         "Avenida Bandeirantes")
        self.assertIsNone(_logradouro("proximo ao n. 4136"))
        self.assertEqual(_sentido("(em ambos os sentidos da via)")[0], "ambos")
        self.assertEqual(_sentido("sem indicacao"), (None, None))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorAgetranMS.resolver_url()
        self.assertEqual(url, ColetorAgetranMS.PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("campogrande.ms.gov.br", url)

    def test_download_passa_por_http_baixar(self):
        with open(fx("agetran_cg_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorAgetranMS().carregar(ColetorAgetranMS.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 8)

    def test_sincronizar_sem_ponto_geografico(self):
        common.ambiente_temporario()
        c = ColetorAgetranMS(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("agetran_cg_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 8)
            self.assertEqual(res["criados"], 8)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                8)
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
