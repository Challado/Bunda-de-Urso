# -*- coding: utf-8 -*-
"""CGI simulado: /ajuda e /radares via QUERY_STRING (spec 10, 14)."""
import json
import unittest

from core import config
from web import nucleo
from tests.common import banco_com_antt


class TestCgi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db, cls.resumo = banco_com_antt()

    def _req(self, caminho, query="", metodo="GET", corpo=b"", ctype=""):
        env = {
            "REQUEST_METHOD": metodo,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(corpo)),
            "CONTENT_TYPE": ctype,
            "PATH_INFO": caminho,
            "REQUEST_URI": caminho + (("?" + query) if query else ""),
            "SCRIPT_NAME": "",
        }
        return nucleo.handle_request(env, corpo)

    # -- /ajuda ------------------------------------------------------------
    def test_ajuda_json_lista_32_colunas(self):
        status, headers, corpo = self._req("/api/v1/ajuda", "formato=json")
        self.assertEqual(status, 200)
        doc = json.loads(corpo if isinstance(corpo, str) else corpo)
        self.assertEqual(len(doc["txt_colunas_ordem"]), 32)
        self.assertEqual(doc["txt_colunas_ordem"][0], "id")
        nomes = [p["nome"] for p in doc["parametros"]]
        for esperado in ("lat", "lon", "raio", "formato", "delimitador",
                         "limite", "uf"):
            self.assertIn(esperado, nomes)

    def test_ajuda_txt(self):
        status, headers, corpo = self._req("/api/v1/ajuda", "formato=txt")
        self.assertEqual(status, 200)
        self.assertIn("ORDEM CANONICA TXT", corpo)
        self.assertIn("01 id", corpo)

    # -- /radares ----------------------------------------------------------
    def test_radares_json(self):
        status, headers, corpo = self._req(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=json")
        self.assertEqual(status, 200)
        doc = json.loads(corpo)
        self.assertTrue(doc["sucesso"])
        self.assertGreaterEqual(doc["resultado"]["total_pontos"], 1)
        self.assertIn("X-Radar-Total-Points", headers)
        # municipio/UF resolvidos via FK (spec 3.6: UF vem do municipio)
        primeiro = doc["resultado"]["pontos"][0]
        self.assertEqual(primeiro["localizacao"]["uf"], "PR")
        self.assertEqual(primeiro["localizacao"]["municipio"], "Cascavel")

    def test_sentido_decrescente_nao_vira_crescente(self):
        _s, _h, corpo = self._req(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=json")
        pontos = json.loads(corpo)["resultado"]["pontos"]
        sentidos = {p["localizacao"]["via"]["codigo"]: None for p in pontos}
        todos = [f["sentido"] for p in pontos for f in p["faixas"]]
        self.assertIn("decrescente", todos)
        self.assertIn("crescente", todos)

    def test_radares_txt_valido(self):
        status, headers, corpo = self._req(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=txt&delimitador=%7C")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        linhas = [l for l in corpo.split("\n") if l]
        self.assertGreaterEqual(len(linhas), 1)
        for ln in linhas:
            self.assertEqual(len(ln.split("|")), 32)

    def test_radares_raio_pequeno_zero_pontos(self):
        status, _h, corpo = self._req(
            "/api/v1/radares",
            "lat=0&lon=0&raio=100&formato=json")
        self.assertEqual(status, 200)
        doc = json.loads(corpo)
        self.assertEqual(doc["resultado"]["total_pontos"], 0)

    def test_radares_sem_lat_erro(self):
        status, _h, _c = self._req("/api/v1/radares", "lon=-53&formato=json")
        self.assertEqual(status, 422)

    def test_radares_coordenada_invalida(self):
        status, _h, _c = self._req(
            "/api/v1/radares", "lat=200&lon=0&formato=json")
        self.assertEqual(status, 422)

    def test_radares_raio_fora_do_limite(self):
        status, _h, _c = self._req(
            "/api/v1/radares", "lat=-24.9&lon=-53.4&raio=99999")
        self.assertEqual(status, 422)

    def test_formato_invalido(self):
        status, _h, _c = self._req("/api/v1/radares", "lat=0&lon=0&formato=nope")
        self.assertEqual(status, 400)

    def test_post_json_equivale_a_get(self):
        corpo = json.dumps({"lat": -24.9555, "lon": -53.4552, "raio": 5000,
                            "formato": "json"}).encode("utf-8")
        status, _h, resp = self._req(
            "/api/v1/radares", "", metodo="POST", corpo=corpo,
            ctype="application/json")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(json.loads(resp)["resultado"]["total_pontos"], 1)

    def test_ponto_por_id(self):
        status, _h, corpo = self._req("/api/v1/radares/P-1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(corpo)["resultado"]["pontos"][0]["id"],
                         "P-1")

    def test_ponto_inexistente(self):
        status, _h, _c = self._req("/api/v1/radares/P-99999")
        self.assertEqual(status, 404)

    def test_status_e_fontes(self):
        s, _h, corpo = self._req("/api/v1/status", "formato=json")
        self.assertEqual(s, 200)
        self.assertIn("total_pontos", json.loads(corpo))
        s, _h, corpo = self._req("/api/v1/fontes", "formato=json")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(json.loads(corpo)["fontes"]), 1)


if __name__ == "__main__":
    unittest.main()
