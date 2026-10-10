# -*- coding: utf-8 -*-
"""Testes deterministicos do resolvedor km->coordenada (ancoras sinteticas)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import georesolver  # noqa: E402


def anc(km, lat, lon, pid=None):
    return {"km": km, "lat": lat, "lon": lon, "ponto_id": pid,
            "uf": None, "fonte": None}


class TestInterpolacao(unittest.TestCase):

    def setUp(self):
        # Via A: reta ao longo da longitude no equador (km = graus).
        self.cal = {
            "A": [anc(0.0, 0.0, 0.0, 1), anc(100.0, 0.0, 1.0, 2)],
        }

    def test_meio(self):
        r = georesolver.resolver("A", 50.0, self.cal)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["metodo"], "linear_km")
        self.assertEqual(r["qualidade"], "inferida")
        self.assertAlmostEqual(r["lat"], 0.0, places=9)
        self.assertAlmostEqual(r["lon"], 0.5, places=9)
        self.assertEqual(r["n_ancoras_via"], 2)
        self.assertEqual(r["ancora_antes"]["ponto_id"], 1)
        self.assertEqual(r["ancora_depois"]["ponto_id"], 2)

    def test_quarto(self):
        r = georesolver.resolver("A", 25.0, self.cal)
        self.assertAlmostEqual(r["lon"], 0.25, places=9)

    def test_nas_ancoras(self):
        r0 = georesolver.resolver("A", 0.0, self.cal)
        self.assertAlmostEqual(r0["lat"], 0.0, places=9)
        self.assertAlmostEqual(r0["lon"], 0.0, places=9)
        r1 = georesolver.resolver("A", 100.0, self.cal)
        self.assertAlmostEqual(r1["lon"], 1.0, places=9)

    def test_tres_ancoras_escolhe_par_certo(self):
        cal = {"B": [anc(0.0, 0.0, 0.0), anc(10.0, 0.0, 1.0), anc(20.0, 0.0, 3.0)]}
        r = georesolver.resolver("B", 15.0, cal)   # entre a 2a e a 3a
        self.assertAlmostEqual(r["lon"], 2.0, places=9)
        self.assertEqual(r["ancora_antes"]["km"], 10.0)
        self.assertEqual(r["ancora_depois"]["km"], 20.0)


class TestNaoMisturaVias(unittest.TestCase):

    def setUp(self):
        self.cal = {
            "A": [anc(0.0, 0.0, 0.0), anc(10.0, 0.0, 0.1)],
            "B": [anc(0.0, 10.0, 10.0), anc(10.0, 10.0, 10.1)],
        }

    def test_via_certa(self):
        ra = georesolver.resolver("A", 5.0, self.cal)
        self.assertAlmostEqual(ra["lat"], 0.0, places=9)
        self.assertAlmostEqual(ra["lon"], 0.05, places=9)
        self.assertEqual(ra["n_ancoras_via"], 2)

        rb = georesolver.resolver("B", 5.0, self.cal)
        self.assertAlmostEqual(rb["lat"], 10.0, places=9)
        self.assertAlmostEqual(rb["lon"], 10.05, places=9)

    def test_via_ausente_nao_usa_outra(self):
        r = georesolver.resolver("C", 5.0, self.cal)
        self.assertEqual(r["status"], "sem_calibracao")
        self.assertIsNone(r["lat"])


class TestForaDeFaixa(unittest.TestCase):

    def setUp(self):
        self.cal = {"A": [anc(10.0, -1.0, -50.0), anc(20.0, -1.1, -50.1)]}

    def test_abaixo(self):
        r = georesolver.resolver("A", 5.0, self.cal)
        self.assertEqual(r["status"], "fora_de_faixa")
        self.assertIsNone(r["lat"])
        self.assertIsNone(r["lon"])
        self.assertIsNone(r["ancora_antes"])
        self.assertEqual(r["ancora_depois"]["km"], 10.0)

    def test_acima(self):
        r = georesolver.resolver("A", 25.0, self.cal)
        self.assertEqual(r["status"], "fora_de_faixa")
        self.assertEqual(r["ancora_antes"]["km"], 20.0)
        self.assertIsNone(r["ancora_depois"])

    def test_limite_incluso(self):
        r = georesolver.resolver("A", 10.0, self.cal)
        self.assertEqual(r["status"], "ok")


class TestSemCalibracao(unittest.TestCase):

    def test_via_desconhecida(self):
        r = georesolver.resolver("ZZZ", 1.0, {})
        self.assertEqual(r["status"], "sem_calibracao")
        self.assertEqual(r["n_ancoras_via"], 0)

    def test_uma_ancora(self):
        cal = {"A": [anc(0.0, 0.0, 0.0)]}
        r = georesolver.resolver("A", 0.0, cal)
        self.assertEqual(r["status"], "sem_calibracao")
        self.assertEqual(r["n_ancoras_via"], 1)

    def test_via_none(self):
        r = georesolver.resolver(None, 1.0, {"A": [anc(0, 0, 0), anc(1, 0, 1)]})
        self.assertEqual(r["status"], "sem_calibracao")


class TestErroHaversine(unittest.TestCase):

    def test_erro_zero_no_alvo(self):
        cal = {"A": [anc(0.0, -24.95, -53.45), anc(50.0, -24.50, -53.00)]}
        r = georesolver.resolver("A", 0.0, cal)
        e = georesolver.erro_m(r, -24.95, -53.45)
        self.assertLess(e, 1.0)

    def test_erro_positivo_meio(self):
        # km 25 no meio de uma reta: o erro contra a ancora real e > 0.
        cal = {"A": [anc(0.0, -24.95, -53.45), anc(50.0, -24.50, -53.00)]}
        r = georesolver.resolver("A", 25.0, cal)
        self.assertIsNotNone(r["lat"])
        e = georesolver.erro_m(r, -24.95, -53.45)
        self.assertGreater(e, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
