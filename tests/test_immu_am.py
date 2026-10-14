# -*- coding: utf-8 -*-
"""Testes offline do conector IMMU Manaus - AM (fiscalizacao eletronica).

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble. O ponto central:
a fonte publica ENDERECOS sem coordenada; NADA de GPS inventado e cada local
vira cadastro SEM POSICAO_GEOGRAFICA.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.immu_am import ColetorIMMUAM, _logradouro, _sentido
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, "immu_am", nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestIMMUAM(unittest.TestCase):

    def test_carregar_lista_de_locais(self):
        c = ColetorIMMUAM()
        _, ext, mime, regs = c.carregar(fx("immu_manaus_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 34)
        self.assertEqual(regs[0]["ordem"], 1)
        self.assertEqual(regs[0]["categoria"], "Detector de Eixo")
        self.assertTrue(regs[0]["texto"].startswith("Avenida General"))
        self.assertEqual(regs[-1]["ordem"], 34)

    def test_categorias_declaradas_preservadas(self):
        with open(fx("immu_manaus_fixture.html"), "r", encoding="utf-8") as f:
            regs = ColetorIMMUAM.extrair_pontos(f.read())
        cats = {}
        for r in regs:
            cats.setdefault(r["categoria"], 0)
            cats[r["categoria"]] += 1
        self.assertEqual(cats["Detector de Eixo"], 10)
        self.assertEqual(cats["Controle de velocidade (60 quilometros)"], 7)
        self.assertEqual(cats["Lombada Eletronica (40 quilometros)"], 2)
        self.assertEqual(cats["Avanco de sinal de vermelho"], 15)

    def test_normalizar_sem_gps(self):
        c = ColetorIMMUAM()
        _, _, _, regs = c.carregar(fx("immu_manaus_fixture.html"))
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["uf"], "AM")
        self.assertEqual(d["municipio_nome"], "Manaus")
        self.assertEqual(d["municipio_ibge"], "1302603")
        self.assertEqual(d["via_tipo"], "municipal")
        self.assertEqual(d["via_codigo"], "Avenida General Rodrigo Otavio Jordao Ramos")
        # ENDERECO nunca vira GPS
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        # fonte nao declara fixo/portatil/movel
        self.assertEqual(d["tipo_radar"], "desconhecido")
        self.assertEqual(d["sentido"], "sentido_geografico")
        self.assertIn("Detector de Eixo", d["observacoes"])
        # nenhum registro da lista ganha coordenada
        for i, r in enumerate(regs):
            dd = c.normalizar(i, r)
            self.assertIsNone(dd["latitude"])
            self.assertIsNone(dd["longitude"])

    def test_logradouro_e_sentido(self):
        self.assertEqual(
            _logradouro("Avenida Pedro Teixeira , 725, nas proximidades"),
            "Avenida Pedro Teixeira")
        self.assertEqual(
            _logradouro("Avenida Brasil com avenida Compensa, Compensa"),
            "Avenida Brasil com avenida Compensa")
        self.assertIsNone(_logradouro("trecho qualquer sem via"))
        self.assertEqual(_sentido("trecho, Coroado, sentido Norte")[0],
                         "sentido_geografico")
        self.assertEqual(_sentido("sem indicacao"), (None, None))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorIMMUAM.resolver_url()
        self.assertEqual(url, ColetorIMMUAM.PAGINA)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("manaus.am.gov.br", url)

    def test_download_passa_por_http_baixar(self):
        with open(fx("immu_manaus_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorIMMUAM().carregar(ColetorIMMUAM.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 34)

    def test_sincronizar_sem_ponto_geografico(self):
        common.ambiente_temporario()
        c = ColetorIMMUAM(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("immu_manaus_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 34)
            self.assertEqual(res["criados"], 34)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                34)
            # nenhuma coordenada inventada
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"), 0)
            # nada virou trecho elegivel
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
