# -*- coding: utf-8 -*-
"""Visibilidade do vao cadastro IBGE x malha municipal.

Boa Esperanca do Norte/MT (5101837) e um municipio novo: existe no cadastro
(localidades do IBGE) mas o IBGE ainda NAO publicou o poligono na API de
malhas. O construtor da malha deve TORNAR ISSO VISIVEL, sem inventar
geometria.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import construir_malha as cm               # noqa: E402


class TestMunicipiosAusentes(unittest.TestCase):
    def _cadastro(self, municipios):
        fd, caminho = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"municipios": municipios}, f)
        self.addCleanup(os.remove, caminho)
        return caminho

    def test_detecta_ausente_sem_inventar(self):
        caminho = self._cadastro([
            {"codigo_ibge": "5101837", "nome": "Boa Esperança do Norte",
             "uf_sigla": "MT"},
            {"codigo_ibge": "5107925", "nome": "Sorriso", "uf_sigla": "MT"},
        ])
        fora = cm.municipios_ausentes({"5107925"}, cadastro=caminho)
        self.assertEqual([a["codigo_ibge"] for a in fora], ["5101837"])
        self.assertEqual(fora[0]["uf_sigla"], "MT")

    def test_sem_vao_devolve_vazio(self):
        caminho = self._cadastro([
            {"codigo_ibge": "5107925", "nome": "Sorriso", "uf_sigla": "MT"}])
        self.assertEqual(cm.municipios_ausentes({"5107925"}, cadastro=caminho),
                         [])

    def test_ausente_quando_cadastro_inexistente(self):
        self.assertEqual(cm.municipios_ausentes(set(),
                                                cadastro="/nao/existe.json"),
                         [])

    def test_vao_real_do_repositorio_inclui_5101837(self):
        # A malha versionada do repositorio tem 5570; o cadastro tem 5571.
        import gzip
        with gzip.open(cm.DESTINO_PADRAO, "rb") as gz:
            fc = json.loads(gz.read().decode("utf-8"))
        codigos = {str((f.get("properties") or {}).get("codarea"))
                   for f in fc["features"]}
        fora = {a["codigo_ibge"] for a in cm.municipios_ausentes(codigos)}
        self.assertIn("5101837", fora)


if __name__ == "__main__":
    unittest.main()
