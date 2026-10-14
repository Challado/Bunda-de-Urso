# -*- coding: utf-8 -*-
"""Testes deterministicos do resolvedor km->coordenada (ancoras sinteticas)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import georesolver  # noqa: E402
from tools import limpar_calibracao as limpar  # noqa: E402


def anc(km, lat, lon, pid=None, segmento=None):
    d = {"km": km, "lat": lat, "lon": lon, "ponto_id": pid,
         "uf": None, "fonte": None}
    if segmento is not None:
        d["segmento"] = segmento
    return d


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


class TestCaixaBrasil(unittest.TestCase):
    """Filtro de caixa do Brasil (captura o sinal/ordem da longitude)."""

    def _reg(self, lat, lon, via="A", km=0.0):
        return {"via": via, "km": km, "lat": lat, "lon": lon,
                "ponto_id": 1, "fonte": None}

    def test_dentro_da_caixa_true(self):
        self.assertTrue(limpar.dentro_da_caixa(-24.95, -53.45))
        self.assertTrue(limpar.dentro_da_caixa(-34.0, -74.0))   # limite
        self.assertTrue(limpar.dentro_da_caixa(5.5, -28.0))    # limite

    def test_fora_da_caixa_lon_positiva(self):
        # Ex.: GO-070 com lon=+49,465963 (sinal trocado).
        self.assertFalse(limpar.dentro_da_caixa(-16.425392, 49.465963))
        # Ex.: BA-099 com lon=+38.04553.
        self.assertFalse(limpar.dentro_da_caixa(-12.6002, 38.04553))

    def test_filtro_descarta_lon_positiva_e_conta_motivo(self):
        regs = [
            self._reg(-16.425392, 49.465963),   # descartada (lon +)
            self._reg(-24.95, -53.45),          # mantida
            self._reg(5.6, -50.0),              # descartada (lat > 5.5)
        ]
        mantidas, desc = limpar.aplicar_filtro(regs)
        self.assertEqual(len(mantidas), 1)
        self.assertEqual(desc["fora_lon"], 1)
        self.assertEqual(desc["fora_lat"], 1)
        self.assertEqual(desc["campo_ausente"], 0)

    def test_filtro_campo_ausente(self):
        regs = [self._reg(None, -53.0)]
        mantidas, desc = limpar.aplicar_filtro(regs)
        self.assertEqual(mantidas, [])
        self.assertEqual(desc["campo_ausente"], 1)


class TestSegmentacao(unittest.TestCase):
    """Dois trechos no mesmo via (km inconsistente) nao se misturam."""

    def test_segmentar_abre_novo_segmento(self):
        # Segmento 1: km 0..10 perto de (0,0). Segmento 2: km 1000..1010 em
        # (20,20), muito longe para 1 km de via.
        ancoras = [
            anc(0.0, 0.0, 0.0),
            anc(10.0, 0.0, 0.1),
            anc(1000.0, 20.0, 20.0),
            anc(1010.0, 20.0, 20.1),
        ]
        segs = limpar.segmentar(ancoras)
        self.assertEqual(len(segs), 2)
        self.assertEqual([len(s) for s in segs], [2, 2])
        self.assertEqual(segs[0][0]["km"], 0.0)
        self.assertEqual(segs[1][0]["km"], 1000.0)

    def test_segmentar_trecho_continuo_fica_um(self):
        # ~1 km de km para ~0.009 deg (~1 km): coerente -> 1 segmento.
        ancoras = [anc(0.0, 0.0, 0.0), anc(1.0, 0.0, 0.009),
                   anc(2.0, 0.0, 0.018)]
        self.assertEqual(len(limpar.segmentar(ancoras)), 1)

    def test_resolver_nao_mistura_segmentos(self):
        cal = {"X": [anc(0.0, 0.0, 0.0, segmento=1),
                      anc(10.0, 0.0, 0.1, segmento=1),
                      anc(1000.0, 20.0, 20.0, segmento=2),
                      anc(1010.0, 20.0, 20.1, segmento=2)]}
        r1 = georesolver.resolver("X", 5.0, cal)     # so o segmento 1 cobre
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r1["segmento"], 1)
        self.assertAlmostEqual(r1["lat"], 0.0, places=9)

        r2 = georesolver.resolver("X", 1005.0, cal)  # so o segmento 2 cobre
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["segmento"], 2)
        self.assertAlmostEqual(r2["lat"], 20.0, places=9)

        r3 = georesolver.resolver("X", 500.0, cal)   # entre os dois -> fora
        self.assertEqual(r3["status"], "fora_de_faixa")


class TestAmbiguo(unittest.TestCase):
    """Mais de um segmento cobrindo o km => nao escolhe, nao extrapola."""

    def test_dois_segmentos_cobrem(self):
        cal = {"X": [anc(0.0, 0.0, 0.0, segmento=1),
                      anc(100.0, 0.0, 1.0, segmento=1),
                      anc(0.0, 10.0, 10.0, segmento=2),
                      anc(100.0, 10.0, 11.0, segmento=2)]}
        r = georesolver.resolver("X", 50.0, cal)
        self.assertEqual(r["status"], "ambiguo")
        self.assertIsNone(r["lat"])
        self.assertIsNone(r["lon"])
        self.assertEqual(sorted(r["segmentos"]), [1, 2])

    def test_um_segmento_nao_e_ambiguo(self):
        cal = {"X": [anc(0.0, 0.0, 0.0, segmento=3),
                      anc(100.0, 0.0, 1.0, segmento=3)]}
        r = georesolver.resolver("X", 50.0, cal)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["segmento"], 3)


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
