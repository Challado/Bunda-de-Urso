# -*- coding: utf-8 -*-
"""Testes do monitor pos-coleta (tools/auditar_coleta.py).

Cobrem a logica de alerta (fonte nova / queda de cobertura) sem banco e um
smoke test de ``medir`` num banco vazio.
"""
import unittest

from tests.common import banco_memoria
from core.manutencao import auditar_coleta as ac


class TestComparar(unittest.TestCase):

    def test_sem_baseline_nao_alerta(self):
        atual = {"A": {"pontos": 3, "pct_municipio": 10.0, "pct_posicao": 5.0}}
        self.assertEqual(ac.comparar(atual, None, 1.0), [])

    def test_fonte_nova_alerta(self):
        base = {"ANTIGA": {"pct_municipio": 90.0, "pct_posicao": 90.0}}
        atual = {"ANTIGA": {"pontos": 4, "pct_municipio": 90.0,
                           "pct_posicao": 90.0},
                 "NOVA": {"pontos": 5, "pct_municipio": 80.0,
                          "pct_posicao": 100.0}}
        alertas = ac.comparar(atual, base, 1.0)
        self.assertTrue(any("FONTE NOVA" in a for a in alertas))

    def test_baseline_vazio_nao_alerta(self):
        # primeira execucao (sem baseline): informativo, sem alerta
        atual = {"NOVA": {"pontos": 5, "pct_municipio": 80.0,
                          "pct_posicao": 100.0}}
        self.assertEqual(ac.comparar(atual, {}, 1.0), [])

    def test_queda_de_cobertura_alerta(self):
        base = {"A": {"pct_municipio": 90.0, "pct_posicao": 90.0}}
        atual = {"A": {"pontos": 10, "pct_municipio": 70.0,
                       "pct_posicao": 90.0}}
        alertas = ac.comparar(atual, base, 1.0)
        self.assertTrue(any("municipio" in a for a in alertas))

    def test_queda_dentro_da_tolerancia_nao_alerta(self):
        base = {"A": {"pct_municipio": 90.0, "pct_posicao": 90.0}}
        atual = {"A": {"pontos": 10, "pct_municipio": 89.5,
                       "pct_posicao": 90.0}}
        self.assertEqual(ac.comparar(atual, base, 1.0), [])

    def test_estavel_nao_alerta(self):
        base = {"A": {"pct_municipio": 90.0, "pct_posicao": 90.0}}
        atual = {"A": {"pontos": 10, "pct_municipio": 90.0,
                       "pct_posicao": 90.0}}
        self.assertEqual(ac.comparar(atual, base, 1.0), [])


class TestMedir(unittest.TestCase):

    def test_banco_vazio(self):
        con = banco_memoria()
        try:
            self.assertEqual(ac.medir(con), {})
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
