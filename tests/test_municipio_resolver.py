# -*- coding: utf-8 -*-
"""Resolucao de municipio por (uf, nome) quando a fonte nao manda o codigo IBGE.

Regressao do defeito medido: os importadores mandam ``municipio_nome`` e
raramente ``municipio_ibge``; sem o passo por nome o municipio era perdido.
"""
import unittest

from coletor.fontes import normalizacao as nz
from core import db as dbmod
from tests.common import banco_memoria


class TestResolverMunicipio(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3550308",
                                             "uf_sigla": "SP",
                                             "nome": "São Paulo"})
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3304557",
                                             "uf_sigla": "RJ",
                                             "nome": "Rio de Janeiro"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_resolve_por_nome_com_acento_e_caixa(self):
        uf, mun = nz.resolver_uf_municipio(self.con, "SP", "sao paulo", None)
        self.assertEqual(uf, "SP")
        self.assertEqual(mun, "3550308")

    def test_resolve_com_espacos_sobrando(self):
        uf, mun = nz.resolver_uf_municipio(self.con, "rj", "  RIO DE JANEIRO ",
                                           None)
        self.assertEqual(mun, "3304557")

    def test_resolve_por_codigo_ibge(self):
        uf, mun = nz.resolver_uf_municipio(self.con, None, "São Paulo",
                                           "3550308")
        self.assertEqual(mun, "3550308")
        self.assertEqual(uf, "SP")

    def test_nome_inexistente_fica_null_sem_inventar(self):
        antes = dbmod.scalar(self.con, "SELECT COUNT(*) FROM MUNICIPIO")
        uf, mun = nz.resolver_uf_municipio(self.con, "SP", "Cidade Fantasma",
                                           None)
        self.assertIsNone(mun)
        depois = dbmod.scalar(self.con, "SELECT COUNT(*) FROM MUNICIPIO")
        self.assertEqual(antes, depois)   # nada inventado
        nulos = dbmod.scalar(
            self.con, "SELECT COUNT(*) FROM MUNICIPIO WHERE codigo_ibge IS NULL")
        self.assertEqual(nulos, 0)

    def test_sem_uf_nao_casa_homonimo(self):
        uf, mun = nz.resolver_uf_municipio(self.con, None, "São Paulo", None)
        self.assertIsNone(mun)


class TestResolucaoAproximada(unittest.TestCase):
    """Nome grafado diferente do oficial resolvido no CAMINHO DE ENTRADA
    pelo casamento aproximado (fuzzy/fonetico) — 2o degrau do resolvedor."""

    def setUp(self):
        self.con = banco_memoria()
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "5107008",
                                             "uf_sigla": "MT",
                                             "nome": "Poxoréu"})
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3550001",
                                             "uf_sigla": "SP",
                                             "nome": "São Luiz do Paraitinga"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_grafia_diferente_resolve_na_entrada(self):
        uf, mun = nz.resolver_uf_municipio(self.con, "MT", "POXOREO", None)
        self.assertEqual(mun, "5107008")
        self.assertEqual(uf, "MT")

    def test_conectivo_trocado_resolve(self):
        uf, mun = nz.resolver_uf_municipio(self.con, "SP",
                                           "Sao Luis do Paraitinga", None)
        self.assertEqual(mun, "3550001")

    def test_nome_realmente_diferente_continua_null(self):
        uf, mun = nz.resolver_uf_municipio(self.con, "MT", "Cidade Fantasma",
                                           None)
        self.assertIsNone(mun)

    def test_sem_uf_aproximacao_nao_arrisca(self):
        # preserva a regra do resolvedor: sem UF nao se casa por nome
        uf, mun = nz.resolver_uf_municipio(self.con, None, "POXOREO", None)
        self.assertIsNone(mun)


if __name__ == "__main__":
    unittest.main()
