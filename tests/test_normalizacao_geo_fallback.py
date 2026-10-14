# -*- coding: utf-8 -*-
"""Testes do FALLBACK GEOGRAFICO em normalizacao.resolver_uf_municipio.

O importador resolve municipio por nome; quando o nome nao casa e o registro
tem coordenada, cai na malha oficial do IBGE (core.geo_municipio).
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.geo_municipio as geo                 # noqa: E402
from coletor.fontes import normalizacao as nz    # noqa: E402
from core import db as dbmod                     # noqa: E402
from tests.common import banco_memoria           # noqa: E402


class TestFallbackGeografico(unittest.TestCase):
    def setUp(self):
        self.con = banco_memoria()
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3550308",
                                             "uf_sigla": "SP",
                                             "nome": "São Paulo"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_nome_nao_resolve_mas_coordenada_resolve(self):
        with mock.patch.object(geo, "municipio_por_coordenada",
                               return_value="3550308") as m:
            uf, mun = nz.resolver_uf_municipio(
                self.con, "SP", "Cidade Fantasma", None,
                latitude=-23.55, longitude=-46.63)
        self.assertEqual(mun, "3550308")
        self.assertEqual(uf, "SP")            # UF vem do municipio resolvido
        m.assert_called_once()

    def test_sem_coordenada_continua_null(self):
        with mock.patch.object(geo, "municipio_por_coordenada") as m:
            uf, mun = nz.resolver_uf_municipio(self.con, "SP",
                                               "Cidade Fantasma", None)
        self.assertIsNone(mun)
        m.assert_not_called()

    def test_nome_resolvido_nao_usa_fallback(self):
        with mock.patch.object(geo, "municipio_por_coordenada") as m:
            uf, mun = nz.resolver_uf_municipio(
                self.con, "SP", "sao paulo", None,
                latitude=-23.55, longitude=-46.63)
        self.assertEqual(mun, "3550308")
        m.assert_not_called()                 # o nome ja resolveu

    def test_coordenada_fora_de_faixa_nao_inventa(self):
        uf, mun = nz.resolver_uf_municipio(
            self.con, "SP", "Cidade Fantasma", None,
            latitude=-200.0, longitude=-46.63)
        self.assertIsNone(mun)
        self.assertEqual(uf, "SP")

    def test_geo_sem_resultado_fica_null(self):
        with mock.patch.object(geo, "municipio_por_coordenada",
                               return_value=None):
            uf, mun = nz.resolver_uf_municipio(
                self.con, "SP", "Cidade Fantasma", None,
                latitude=-23.0, longitude=-46.0)
        self.assertIsNone(mun)

    def test_codigo_ibge_ainda_tem_prioridade(self):
        with mock.patch.object(geo, "municipio_por_coordenada") as m:
            uf, mun = nz.resolver_uf_municipio(
                self.con, None, None, "3550308",
                latitude=-23.55, longitude=-46.63)
        self.assertEqual(mun, "3550308")
        m.assert_not_called()


class TestMunicipioPorGeografia(unittest.TestCase):
    def setUp(self):
        self.con = banco_memoria()
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3304557",
                                             "uf_sigla": "RJ",
                                             "nome": "Rio de Janeiro"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_resolve_uf_do_municipio(self):
        with mock.patch.object(geo, "municipio_por_coordenada",
                               return_value="3304557"):
            cod, uf = nz.municipio_por_geografia(self.con, -22.9, -43.2)
        self.assertEqual((cod, uf), ("3304557", "RJ"))

    def test_sem_coordenada(self):
        self.assertEqual(nz.municipio_por_geografia(self.con, None, None),
                         (None, None))

    def test_coordenada_implausivel(self):
        self.assertEqual(
            nz.municipio_por_geografia(self.con, -20.9, 48.4), (None, None))


if __name__ == "__main__":
    unittest.main()
