# -*- coding: utf-8 -*-
"""Haversine e bounding box contra distancias conhecidas."""
import math
import unittest

from core import geo
from core.config import EARTH_RADIUS_M


class TestGeo(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(geo.haversine_m(-24.9555, -53.4552,
                                         -24.9555, -53.4552), 0.0)

    def test_um_grau_de_latitude(self):
        esperado = EARTH_RADIUS_M * math.pi / 180.0   # ~111194.93 m
        self.assertAlmostEqual(
            geo.haversine_m(0.0, 0.0, 1.0, 0.0), esperado, places=3)

    def test_um_grau_de_longitude_no_equador(self):
        esperado = EARTH_RADIUS_M * math.pi / 180.0
        self.assertAlmostEqual(
            geo.haversine_m(0.0, 0.0, 0.0, 1.0), esperado, places=3)

    def test_distancia_conhecida_paris_londres(self):
        # ~343 km; tolerancia ampla por ser esfera media
        d = geo.haversine_m(48.8566, 2.3522, 51.5074, -0.1278)
        self.assertTrue(330000 < d < 360000, d)

    def test_bounding_box_contem_ponto_no_limite(self):
        bb = geo.bounding_box(-24.9555, -53.4552, 1000)
        self.assertLessEqual(bb["lat_min"], -24.9555)
        self.assertGreaterEqual(bb["lat_max"], -24.9555)
        # ponto a ~500 m deve cair dentro da caixa
        lat2 = -24.9555 + 500.0 / 111320.0
        self.assertTrue(bb["lat_min"] <= lat2 <= bb["lat_max"])

    def test_bounding_box_polos_aceita_toda_longitude(self):
        bb = geo.bounding_box(89.9999, 10.0, 5000)
        self.assertTrue(bb["inclui_polos"])
        self.assertEqual((bb["lon_min"], bb["lon_max"]), (-180.0, 180.0))

    def test_antimeridiano(self):
        bb = geo.bounding_box(0.0, 179.9999, 5000)
        self.assertTrue(bb["cruza_antimeridiano"])

    def test_coordenada_invalida(self):
        with self.assertRaises(ValueError):
            geo.bounding_box(100.0, 0.0, 1000)


if __name__ == "__main__":
    unittest.main()
