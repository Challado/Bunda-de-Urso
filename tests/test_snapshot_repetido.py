# -*- coding: utf-8 -*-
"""Recoleta identica nao reingere: freio de snapshot repetido no coletor.

Motivo real (2026-10-10): a pagina do DER-MG muda apenas token/contador a
cada coleta; o hash do arquivo bruto muda, mas os radares sao os mesmos. Sem
o freio, todos os registros seriam duplicados (710 em 710).
"""
import unittest

from coletor.fontes.antt import ColetorANTT
from tests import common


class TestSnapshotRepetido(unittest.TestCase):

    def setUp(self):
        common.ambiente_temporario()

    def test_recoleta_identica_nao_duplica_registros(self):
        c1 = ColetorANTT()
        try:
            r1 = c1.sincronizar(common.ANTT_FIXTURE)
        finally:
            c1.conn.close()
        self.assertFalse(r1.get("sem_mudanca"))

        c2 = ColetorANTT()
        try:
            r2 = c2.sincronizar(common.ANTT_FIXTURE)
            n = c2.conn.execute(
                "SELECT COUNT(*) FROM REGISTRO_FONTE").fetchone()[0]
        finally:
            c2.conn.close()
        self.assertTrue(r2.get("sem_mudanca"))
        self.assertEqual(r2["criados"], 0)
        self.assertEqual(n, r1["linhas_recebidas"])   # nada duplicado

    def test_arreio_de_assinatura_ignora_ordem(self):
        c = ColetorANTT.__new__(ColetorANTT)          # so a assinatura
        a = c._assinatura([{"x": 1}, {"y": 2}])
        b = c._assinatura([{"y": 2}, {"x": 1}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c._assinatura([{"x": 1}]))


if __name__ == "__main__":
    unittest.main()
