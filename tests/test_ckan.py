# -*- coding: utf-8 -*-
"""Escolha de recurso CKAN: pega a edicao mais nova e cai no fallback."""
import unittest

from coletor.fontes import ckan
from coletor.fontes.antt import ColetorANTT
from coletor.fontes.recife import ColetorRecife

BASE = "https://exemplo/dataset/x/resource/y/download/"

RESOURCES = [
    {"format": "JSON", "name": "Dados dos Radares", "url": BASE + "dados-dos-radares4_2026.json"},
    {"format": "JSON", "name": "Dados dos Radares", "url": BASE + "dados-dos-radares5_2026.json"},
    {"format": "JSON", "name": "Dados dos Radares", "url": BASE + "dados-dos-radares6_2026.json"},
    {"format": "CSV", "name": "Dados dos Radares", "url": BASE + "dados-dos-radares6_2026.csv"},
    {"format": "KMZ", "name": "Dados dos Radares", "url": BASE + "radar.kmz"},
    {"format": "PDF", "name": "Dicionario", "url": BASE + "radar_dicionario_dados.pdf"},
]

PADRAO_ANTT = r"dados-dos-radares(\d+)_(\d{4})"


class TestCkan(unittest.TestCase):

    def test_pega_edicao_mais_nova(self):
        achados = ckan.escolher_recursos(RESOURCES, "JSON", PADRAO_ANTT,
                                         ckan.versao_numerica())
        self.assertEqual(len(achados), 3)
        self.assertTrue(achados[0]["url"].endswith("radares6_2026.json"))

    def test_formato_filtra(self):
        achados = ckan.escolher_recursos(RESOURCES, "KMZ", None, None)
        self.assertEqual(len(achados), 1)
        self.assertTrue(achados[0]["url"].endswith("radar.kmz"))

    def test_padrao_sem_casamento_ignora(self):
        achados = ckan.escolher_recursos(RESOURCES, "JSON", r"nao-existe",
                                         ckan.versao_numerica())
        self.assertEqual(achados, [])

    def test_versao_numerica_desempata_ano(self):
        chave = ckan.versao_numerica()
        self.assertGreater(chave(type("M", (), {"groups": lambda self: ("2", "2027")})()),
                           chave(type("M", (), {"groups": lambda self: ("9", "2026")})()))

    def test_fallback_antt_com_api_fora(self):
        def explode(*a, **k):
            raise RuntimeError("portal fora do ar")
        orig = ckan.package_show
        ckan.package_show = explode
        try:
            url = ColetorANTT.resolver_url()
        finally:
            ckan.package_show = orig
        self.assertTrue(url.endswith(".json"))
        self.assertIn("dados-dos-radares", url)

    def test_fallback_recife_com_api_fora(self):
        def explode(*a, **k):
            raise RuntimeError("portal fora do ar")
        orig = ckan.package_show
        ckan.package_show = explode
        try:
            url = ColetorRecife.resolver_url()
        finally:
            ckan.package_show = orig
        self.assertTrue(url.endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
