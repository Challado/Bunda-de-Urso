# -*- coding: utf-8 -*-
"""Testes do resolvedor geografico (core.geo_municipio) e do cadastro IBGE.

Nao tocam rede: usam malha sintetica e o arquivo versionado do repositorio.
"""
import gzip
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config                          # noqa: E402
from core import geo_municipio as geo             # noqa: E402


QUADRADO = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]
DIREITA = [[(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0),
            (10.0, 0.0)]]


def _malha(*municipios):
    """Malha sintetica: (codarea, [aneis...])."""
    m = geo.Malha()
    for cod, aneis in municipios:
        features = [{"type": "Feature", "properties": {"codarea": cod},
                     "geometry": {"type": "Polygon",
                                  "coordinates": [list(a) for a in aneis]}}]
        m.adicionar_featurecollection(
            {"type": "FeatureCollection", "features": features})
    return m


class TestGeometria(unittest.TestCase):
    def test_ponto_em_anel(self):
        self.assertTrue(geo.ponto_em_anel(QUADRADO[0], 5.0, 5.0))
        self.assertFalse(geo.ponto_em_anel(QUADRADO[0], 15.0, 5.0))

    def test_borda_conta_como_dentro(self):
        self.assertTrue(geo.ponto_na_borda(QUADRADO[0], 5.0, 0.0))
        self.assertTrue(geo.ponto_em_poligono([QUADRADO], 0.0, 0.0))

    def test_buraco(self):
        buraco = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]
        self.assertFalse(geo.ponto_em_poligono([[QUADRADO[0], buraco]], 5, 5))
        self.assertTrue(geo.ponto_em_poligono([[QUADRADO[0], buraco]], 2, 2))


class TestCoordenadaValida(unittest.TestCase):
    def test_validas(self):
        self.assertTrue(geo.coordenada_valida(-23.5, -46.6))
        self.assertTrue(geo.coordenada_valida(-15.79, -47.88))

    def test_invalidas(self):
        self.assertFalse(geo.coordenada_valida(None, -46.6))
        self.assertFalse(geo.coordenada_valida(0.0, 0.0))
        self.assertFalse(geo.coordenada_valida(-100.0, -46.0))
        self.assertFalse(geo.coordenada_valida(-23.0, 200.0))
        self.assertFalse(geo.coordenada_valida("x", -46.0))


class TestMunicipioPorCoordenada(unittest.TestCase):
    def setUp(self):
        self.malha = _malha(("1111111", QUADRADO), ("2222222", DIREITA))

    def test_dentro(self):
        self.assertEqual(
            geo.municipio_por_coordenada(5.0, 5.0, malha=self.malha), "1111111")
        self.assertEqual(
            geo.municipio_por_coordenada(5.0, 15.0, malha=self.malha), "2222222")

    def test_fora_de_tudo(self):
        self.assertIsNone(
            geo.municipio_por_coordenada(50.0, 50.0, malha=self.malha))

    def test_legenda_lat_lon(self):
        # (lat, lon) -> x=lon, y=lat: nao confundir os eixos
        self.assertEqual(
            geo.municipio_por_coordenada(5.0, 15.0, malha=self.malha), "2222222")

    def test_invalida_nunca_consulta(self):
        self.assertIsNone(geo.municipio_por_coordenada(0.0, 0.0, malha=self.malha))
        self.assertIsNone(geo.municipio_por_coordenada(-200.0, 5.0,
                                                       malha=self.malha))

    def test_coordenada_implausivel_brasil(self):
        # longitude positiva (leste de Greenwich) nao existe no Brasil
        self.assertIsNone(
            geo.municipio_por_coordenada(-20.91, 48.46, malha=self.malha))


class TestMalhaArquivo(unittest.TestCase):
    def test_geojson_gz_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "malha.geojson.gz")
            fc = {"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {"codarea": "1111111"},
                "geometry": {"type": "Polygon", "coordinates": QUADRADO}}]}
            with gzip.open(caminho, "wb") as f:
                f.write(json.dumps(fc).encode("utf-8"))
            m = geo.carregar_malha_geo(caminho)
            self.assertEqual(len(m), 1)
            self.assertEqual(m.localizar(5.0, 5.0), "1111111")

    def test_malha_versionada_existe(self):
        self.assertTrue(os.path.exists(geo.MALHA_VERSIONADA),
                        "malha simplificada versionada ausente")
        m = geo.carregar_malha()
        self.assertGreaterEqual(len(m), 5570)

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "m.geojson")
            fc = {"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {"codarea": "1111111"},
                "geometry": {"type": "Polygon", "coordinates": QUADRADO}}]}
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(fc, f)
            antigo = os.environ.get("RADAR_MALHA")
            os.environ["RADAR_MALHA"] = caminho
            try:
                m = geo.carregar_malha()
                self.assertEqual(len(m), 1)
            finally:
                if antigo is None:
                    os.environ.pop("RADAR_MALHA", None)
                else:
                    os.environ["RADAR_MALHA"] = antigo


class TestCadastroMunicipios(unittest.TestCase):
    CAMINHO = os.path.join(config.ROOT, "config", "municipios_ibge.json")

    def setUp(self):
        if not os.path.exists(self.CAMINHO):
            self.skipTest("config/municipios_ibge.json ainda nao gerado")
        with open(self.CAMINHO, "r", encoding="utf-8") as f:
            self.doc = json.load(f)

    def test_estrutura(self):
        self.assertIn("municipios", self.doc)
        self.assertGreaterEqual(self.doc["total"], 5570)
        self.assertEqual(self.doc["total"], len(self.doc["municipios"]))

    def test_registros_validos(self):
        ufs = set(geo.UFS)
        vistos = set()
        for m in self.doc["municipios"]:
            cod = m["codigo_ibge"]
            self.assertTrue(cod.isdigit() and len(cod) == 7, cod)
            self.assertNotIn(cod, vistos)
            vistos.add(cod)
            self.assertIn(m["uf_sigla"], ufs)
            self.assertTrue(m["nome"].strip())

    def test_centroides_no_brasil(self):
        # Limites generosos: inclui Fernando de Noronha (lon ~ -32,4).
        for m in self.doc["municipios"]:
            if "centroide_lat" not in m:
                continue
            self.assertTrue(-34.0 <= m["centroide_lat"] <= 6.0, m)
            self.assertTrue(-74.0 <= m["centroide_lon"] <= -32.0, m)


if __name__ == "__main__":
    unittest.main()
