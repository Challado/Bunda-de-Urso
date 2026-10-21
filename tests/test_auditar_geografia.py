# -*- coding: utf-8 -*-
"""Testes deterministicos do ponto-em-poligono e da auditoria geografica.

Nao tocam rede nem banco: exercitam apenas a geometria (stdlib) e o
carregamento de GeoJSON sintetico.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manutencao import auditar_geografia_municipios as ag   # noqa: E402


QUADRADO = [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]


def _fc(*municipios):
    """FeatureCollection sintetica: (codarea, anel_exterior, [buracos...])."""
    features = []
    for item in municipios:
        cod = item[0]
        aneis = [item[1]] + list(item[2:])
        features.append({
            "type": "Feature",
            "properties": {"codarea": cod},
            "geometry": {"type": "Polygon",
                         "coordinates": [list(a) for a in aneis]},
        })
    return {"type": "FeatureCollection", "features": features}


class TestPontoEmAnel(unittest.TestCase):
    def test_dentro(self):
        self.assertTrue(ag.ponto_em_anel(QUADRADO[0], 5.0, 5.0))

    def test_fora_direita(self):
        self.assertFalse(ag.ponto_em_anel(QUADRADO[0], 15.0, 5.0))

    def test_fora_esquerda(self):
        self.assertFalse(ag.ponto_em_anel(QUADRADO[0], -1.0, 5.0))

    def test_fora_acima_abaixo(self):
        self.assertFalse(ag.ponto_em_anel(QUADRADO[0], 5.0, 11.0))
        self.assertFalse(ag.ponto_em_anel(QUADRADO[0], 5.0, -1.0))


class TestBorda(unittest.TestCase):
    def test_aresta_inferior(self):
        self.assertTrue(ag.ponto_na_borda(QUADRADO[0], 5.0, 0.0))

    def test_aresta_lateral(self):
        self.assertTrue(ag.ponto_na_borda(QUADRADO[0], 0.0, 5.0))
        self.assertTrue(ag.ponto_na_borda(QUADRADO[0], 10.0, 5.0))

    def test_vertice(self):
        self.assertTrue(ag.ponto_na_borda(QUADRADO[0], 0.0, 0.0))
        self.assertTrue(ag.ponto_na_borda(QUADRADO[0], 10.0, 10.0))

    def test_interior_nao_e_borda(self):
        self.assertFalse(ag.ponto_na_borda(QUADRADO[0], 5.0, 5.0))

    def test_borda_conta_como_dentro(self):
        self.assertTrue(ag.ponto_em_poligono([QUADRADO], 5.0, 0.0))
        self.assertTrue(ag.ponto_em_poligono([QUADRADO], 0.0, 0.0))


class TestBuraco(unittest.TestCase):
    def _com_buraco(self):
        buraco = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0)]
        return [QUADRADO[0], buraco]

    def test_dentro_do_buraco(self):
        self.assertFalse(ag.ponto_em_poligono([self._com_buraco()], 5.0, 5.0))

    def test_anel_macico(self):
        self.assertTrue(ag.ponto_em_poligono([self._com_buraco()], 2.0, 2.0))

    def test_borda_do_buraco_conta_dentro(self):
        # borda do buraco -> considerada DENTRO do municipio (regra acordada)
        self.assertTrue(
            ag.ponto_em_poligono([self._com_buraco()], 4.0, 5.0))

    def test_parte_sem_buraco_continua(self):
        partes = self._com_buraco()
        self.assertTrue(ag.ponto_em_poligono([partes], 9.0, 9.0))


class TestMultiPoligono(unittest.TestCase):
    def test_parte_distante(self):
        a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
        b = [(100.0, 100.0), (101.0, 100.0), (101.0, 101.0),
             (100.0, 101.0), (100.0, 100.0)]
        partes = [[a], [b]]
        self.assertTrue(ag.ponto_em_poligono(partes, 0.5, 0.5))
        self.assertTrue(ag.ponto_em_poligono(partes, 100.5, 100.5))
        self.assertFalse(ag.ponto_em_poligono(partes, 50.0, 50.0))


class TestCarregamento(unittest.TestCase):
    def test_extrair_partes_poligono(self):
        partes = ag.extrair_partes(
            {"type": "Polygon", "coordinates": [QUADRADO[0]]})
        self.assertEqual(len(partes), 1)
        self.assertEqual(len(partes[0]), 1)

    def test_extrair_partes_vertices_insuficientes(self):
        partes = ag.extrair_partes(
            {"type": "Polygon",
             "coordinates": [[(0.0, 0.0), (1.0, 1.0)]]})
        self.assertEqual(partes, [])

    def test_extrair_multipoligono(self):
        geom = {"type": "MultiPolygon", "coordinates": [[QUADRADO[0]],
                                                        [QUADRADO[0]]]}
        self.assertEqual(len(ag.extrair_partes(geom)), 2)

    def test_malha_localiza(self):
        malha = ag.Malha()
        self.assertEqual(malha.adicionar_featurecollection(
            _fc(("1111111", QUADRADO[0]))), 1)
        self.assertEqual(malha.localizar(5.0, 5.0), "1111111")
        self.assertIsNone(malha.localizar(500.0, 5.0))

    def test_malha_dois_municipios(self):
        direita = [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0),
                   (10.0, 0.0)]
        malha = ag.Malha()
        malha.adicionar_featurecollection(
            _fc(("1111111", QUADRADO[0]), ("2222222", direita)))
        self.assertEqual(malha.localizar(5.0, 5.0), "1111111")
        self.assertEqual(malha.localizar(15.0, 5.0), "2222222")

    def test_codarea_ausente_e_ignorada(self):
        malha = ag.Malha()
        fc = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [QUADRADO[0]]}}]}
        self.assertEqual(malha.adicionar_featurecollection(fc), 0)


class TestCorpoTexto(unittest.TestCase):
    def test_gzip(self):
        import gzip
        self.assertEqual(
            ag._corpo_texto(gzip.compress(b'{"a": 1}')), '{"a": 1}')

    def test_simples(self):
        self.assertEqual(ag._corpo_texto(b"plain"), "plain")


if __name__ == "__main__":
    unittest.main()
