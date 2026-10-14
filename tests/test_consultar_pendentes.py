# -*- coding: utf-8 -*-
"""Testes da consulta de pendentes (tools/consultar_nomes_pendentes.py).

O ponto central: a sugestao do MODELO nunca vale por si; ela e conferida
contra o cadastro oficial do IBGE. Um palpite sem correspondencia oficial
cai em ``revisar_humano`` (nada inventado).
"""
import unittest
from unittest import mock

from core import db as dbmod
from tests.common import banco_memoria
from tools import consultar_nomes_pendentes as cp


def _mun(con, codigo, uf, nome):
    dbmod.insert(con, "MUNICIPIO", {"codigo_ibge": codigo, "uf_sigla": uf,
                                    "nome": nome})


class TestValidarSugestao(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()
        _mun(self.con, "5107008", "MT", "Poxoréu")
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_sugestao_exata_aceita(self):
        cod, uf, sc, mot = cp.validar_sugestao(
            self.con, {"municipio": "Poxoréu", "uf": "MT"})
        self.assertEqual(cod, "5107008")
        self.assertEqual(mot, "exato")

    def test_grafia_aproximada_do_modelo_e_validada(self):
        cod, uf, sc, mot = cp.validar_sugestao(
            self.con, {"municipio": "POXOREO", "uf": "MT"})
        self.assertEqual(cod, "5107008")

    def test_palpite_sem_correspondencia_vai_para_revisao(self):
        cod, uf, sc, mot = cp.validar_sugestao(
            self.con, {"municipio": "Cidade Fantasma", "uf": "MT"})
        self.assertIsNone(cod)

    def test_modelo_sem_resposta(self):
        cod, uf, sc, mot = cp.validar_sugestao(
            self.con, {"municipio": "", "uf": ""})
        self.assertIsNone(cod)
        self.assertEqual(mot, "modelo_sem_resposta")

    def test_sugestao_ausente(self):
        self.assertIsNone(cp.validar_sugestao(self.con, None)[0])


class TestAnalisar(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()
        _mun(self.con, "5107008", "MT", "Poxoréu")
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_aproximacao_resolve_sem_chamar_modelo(self):
        grupos = {("MT", "POXOREO"): {"pontos": [1, 2], "fonte": "X"}}
        with mock.patch.object(cp, "perguntar_modelo") as m:
            props = cp.analisar(self.con, grupos, "http://x", "m", 0)
        self.assertEqual(props[0]["origem"], "aproximacao")
        self.assertEqual(props[0]["codigo"], "5107008")
        m.assert_not_called()

    def test_modelo_confirma_quando_aproximacao_falha(self):
        grupos = {("MT", "CIDADE FANTASMA"): {"pontos": [9], "fonte": "X"}}
        with mock.patch.object(cp, "perguntar_modelo",
                               return_value={"municipio": "Poxoréu",
                                             "uf": "MT"}):
            props = cp.analisar(self.con, grupos, "http://x", "m", 0)
        self.assertEqual(props[0]["origem"], "modelo_validado")
        self.assertEqual(props[0]["codigo"], "5107008")

    def test_modelo_erra_e_vai_para_revisao(self):
        grupos = {("MT", "CIDADE FANTASMA"): {"pontos": [9], "fonte": "X"}}
        with mock.patch.object(cp, "perguntar_modelo",
                               return_value={"municipio": "Nova Cidade",
                                             "uf": "MT"}):
            props = cp.analisar(self.con, grupos, "http://x", "m", 0)
        self.assertEqual(props[0]["origem"], "revisar_humano")
        self.assertIsNone(props[0]["codigo"])

    def test_ollama_indisponivel_vai_para_revisao(self):
        grupos = {("MT", "CIDADE FANTASMA"): {"pontos": [9], "fonte": "X"}}
        with mock.patch.object(cp, "perguntar_modelo", return_value=None):
            props = cp.analisar(self.con, grupos, "http://x", "m", 0)
        self.assertEqual(props[0]["origem"], "revisar_humano")
        self.assertIn("ollama_off", props[0]["motivo"])


if __name__ == "__main__":
    unittest.main()
