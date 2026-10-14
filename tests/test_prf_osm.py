# -*- coding: utf-8 -*-
"""Testes OFFLINE das fontes F05/F06/F07 (PRF) e F15 (OSM/Overpass).

Nenhum teste acessa a rede: as fixtures ficam em tests/fixtures/novos/ e os
coletores sao exercitados por arquivo local.  Rode somente este arquivo:

    python3 -m unittest tests.test_prf_osm -v
"""
import os
import tempfile
import unittest

from core import config
from coletor.base import ColetorBase
from coletor.fontes.prf import (ColetorPRFFixos, ColetorPRFPortateis,
                                ColetorPRFTrechos, _parse_csv_trechos)
from coletor.fontes.osm import (ColetorOSM, _espera_backoff, ATRIBUICAO,
                                LICENCA)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "novos")
F_PORTATEIS = os.path.join(FIX, "prf_portateis.html")
F_FIXOS_JSON = os.path.join(FIX, "prf_fixos.json")
F_FIXOS_TABELA = os.path.join(FIX, "prf_fixos_tabela.html")
F_TRECHOS_CSV = os.path.join(FIX, "prf_trechos_lista.csv")
F_TRECHOS_PAGINA = os.path.join(FIX, "prf_trechos_pagina.html")
F_OSM = os.path.join(FIX, "osm_overpass.json")


class BaseOffline(unittest.TestCase):
    """Isola o cache de arquivos num diretorio temporario (sem tocar o repo)."""

    def setUp(self):
        self._data = config.DATA_DIR
        self._raw = config.RAW_DIR
        tmp = tempfile.mkdtemp(prefix="radar-prf-osm-")
        config.DATA_DIR = tmp
        config.RAW_DIR = os.path.join(tmp, "raw")
        os.makedirs(config.RAW_DIR, exist_ok=True)

    def tearDown(self):
        config.DATA_DIR = self._data
        config.RAW_DIR = self._raw


# --------------------------------------------------------------------------
# F05 - PRF radares fixos
# --------------------------------------------------------------------------

class TestPRFFixos(BaseOffline):

    def test_herda_coletor_base(self):
        self.assertTrue(issubclass(ColetorPRFFixos, ColetorBase))
        self.assertTrue(ColetorPRFFixos.resolver_url().startswith(
            "https://www.gov.br/prf/"))

    def test_carregar_json_records(self):
        _, ext, mime, regs = ColetorPRFFixos().carregar(F_FIXOS_JSON)
        self.assertEqual(ext, ".json")
        self.assertEqual(mime, "application/json")
        self.assertEqual(len(regs), 2)

    def test_normalizar_json_tem_posicao_oficial(self):
        c = ColetorPRFFixos()
        _, _, _, regs = c.carregar(F_FIXOS_JSON)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "AFD060")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["qualidade"], "oficial")
        self.assertAlmostEqual(d["latitude"], -23.288997, places=6)
        self.assertEqual(d["via_codigo"], "BR-381")
        self.assertAlmostEqual(d["km"], 59.795, places=3)
        self.assertEqual(d["funcao_equipamento"], "controlador")
        self.assertEqual(d["velocidade_leves"], 80.0)
        self.assertEqual(d["situacao"], "ativo")
        self.assertEqual(d["procedencia"], "oficial")
        self.assertEqual(d["confiabilidade"], "oficial")
        self.assertIn("ARTERIS", d["observacoes"])

    def test_carregar_tabela_html_estatica(self):
        # caminho da tabela HTML: parse com html.parser (sem coordenadas)
        c = ColetorPRFFixos()
        _, ext, mime, regs = c.carregar(F_FIXOS_TABELA)
        self.assertEqual(ext, ".html")
        self.assertTrue(mime.startswith("text/html"))
        self.assertEqual(len(regs), 2)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "AFD060")
        self.assertEqual(d["via_codigo"], "BR-381")   # "BR 381" -> 381
        self.assertAlmostEqual(d["km"], 59.795, places=3)  # "59,795"
        self.assertIsNone(d["latitude"])
        self.assertEqual(d["qualidade"], "desconhecida")
        self.assertEqual(d["tipo_radar"], "fixo")


# --------------------------------------------------------------------------
# F06 - PRF lista de radares portateis
# --------------------------------------------------------------------------

class TestPRFPortateis(BaseOffline):

    def test_herda_e_resolve(self):
        self.assertTrue(issubclass(ColetorPRFPortateis, ColetorBase))
        self.assertIn("lista-de-radares", ColetorPRFPortateis.resolver_url())

    def test_carregar_tabela(self):
        _, ext, mime, regs = ColetorPRFPortateis().carregar(F_PORTATEIS)
        self.assertEqual(mime, "text/html; charset=utf-8")
        self.assertEqual(len(regs), 7)
        self.assertIn("IDENTIFICADOR DO EQUIPAMENTO", regs[0])
        self.assertIn("Nº DE SÉRIE", regs[0])

    def test_normalizar_sem_posicao(self):
        c = ColetorPRFPortateis()
        _, _, _, regs = c.carregar(F_PORTATEIS)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "REF181")
        self.assertEqual(d["numero_serie"], "TC005867")
        self.assertEqual(d["tipo_radar"], "portatil")
        # identificador administrativo + serie; SEM posicao oficial
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["qualidade"], "desconhecida")
        self.assertFalse(d["posicao_confirmada"])
        self.assertEqual(d["procedencia"], "oficial")

    def test_pares_de_serie_repetida_preservados(self):
        # spec 8.6: REF181/REF184 -> TC005867; RRJ004/RRJ005 -> S1539.
        c = ColetorPRFPortateis()
        _, _, _, regs = c.carregar(F_PORTATEIS)
        norm = [c.normalizar(i, r) for i, r in enumerate(regs)]
        pares = {}
        for d in norm:
            pares.setdefault(d["numero_serie"], []).append(d["identificador"])
        self.assertEqual(sorted(pares["TC005867"]), ["REF181", "REF184"])
        self.assertEqual(sorted(pares["S1539"]), ["RRJ004", "RRJ005"])
        # todos os IDs continuam presentes (nada consolidado automaticamente)
        self.assertEqual(len({d["identificador"] for d in norm}), 7)


# --------------------------------------------------------------------------
# F07 - PRF trechos criticos
# --------------------------------------------------------------------------

class TestPRFTrechos(BaseOffline):

    def test_herda_e_resolve(self):
        self.assertTrue(issubclass(ColetorPRFTrechos, ColetorBase))
        # resolver_url() descobre ao vivo; aqui so checamos a pagina institucional
        self.assertIn("trechos-criticos", ColetorPRFTrechos.URL_PAGINA)

    def test_descobrir_lista_mais_recente(self):
        with open(F_TRECHOS_PAGINA, encoding="utf-8") as f:
            html = f.read()
        url = ColetorPRFTrechos.descobrir_lista_url(html)
        self.assertIn("/d/e/ULT/", url)
        self.assertNotIn("&amp;", url)

    def test_resolver_url_offline_via_monkeypatch(self):
        import coletor.fontes.prf as prf
        orig = prf._baixar
        prf._baixar = lambda url: open(F_TRECHOS_PAGINA, "rb").read()
        try:
            url = ColetorPRFTrechos.resolver_url()
        finally:
            prf._baixar = orig
        self.assertIn("/d/e/ULT/", url)

    def test_carregar_csv(self):
        _, ext, mime, regs = ColetorPRFTrechos().carregar(F_TRECHOS_CSV)
        self.assertEqual(ext, ".csv")
        self.assertEqual(mime, "text/csv; charset=utf-8")
        self.assertEqual(len(regs), 4)
        self.assertEqual(regs[0]["ESTADO (UF)"], "AC")

    def test_normalizar_trecho_elegivel(self):
        c = ColetorPRFTrechos()
        _, _, _, regs = c.carregar(F_TRECHOS_CSV)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["tipo_registro"], "trecho_elegivel")
        self.assertEqual(d["uf"], "AC")
        self.assertEqual(d["via_codigo"], "BR-317")
        self.assertAlmostEqual(d["km_inicio"], 90.0, places=3)
        self.assertAlmostEqual(d["km_fim"], 95.0, places=3)
        self.assertIsNone(d["sentido"])
        self.assertEqual(d["indicador"], "pode_haver_fiscalizacao")
        # trecho elegivel NUNCA vira radar instalado/operacao confirmada
        self.assertIsNone(d["radar_instalado_confirmado"])
        self.assertIsNone(d.get("modalidade"))
        self.assertIn("CONTRAN", d["criterio_inclusao"])
        self.assertIn("nao e operacao confirmada", d["observacoes"])

    def test_carregar_pagina_sem_rede_nao_inventa(self):
        # passando a propria pagina local: nao baixa a planilha e devolve vazio
        _, _, _, regs = ColetorPRFTrechos().carregar(F_TRECHOS_PAGINA)
        self.assertEqual(regs, [])

    def test_parse_csv_helper_titulo(self):
        with open(F_TRECHOS_CSV, "rb") as f:
            dados = f.read()
        regs = _parse_csv_trechos(dados)
        self.assertEqual(len(regs), 4)
        self.assertIn("798/20", regs[0]["TITULO"])


# --------------------------------------------------------------------------
# F15 - OpenStreetMap / Overpass (complementar, nao oficial)
# --------------------------------------------------------------------------

class TestOSM(BaseOffline):

    def test_herda_e_resolve(self):
        self.assertTrue(issubclass(ColetorOSM, ColetorBase))
        self.assertEqual(ColetorOSM.resolver_url(),
                         "https://overpass-api.de/api/interpreter")

    def test_nao_e_fonte_oficial(self):
        self.assertEqual(ColetorOSM.FONTE["natureza"], "comunitaria")
        self.assertEqual(ColetorOSM.FONTE["licenca"], LICENCA)
        self.assertEqual(ColetorOSM.FONTE["licenca_codigo"], "odbl")

    def test_montar_query(self):
        q = ColetorOSM().montar_query()
        self.assertIn('["highway"="speed_camera"]', q)
        self.assertIn('["type"="enforcement"]', q)
        self.assertIn("out meta center", q)
        # bbox limitada (nao global)
        self.assertIn("-23.70,-46.80,-23.45,-46.45", q)

    def test_carregar_fixture(self):
        _, ext, mime, els = ColetorOSM().carregar(F_OSM)
        self.assertEqual(ext, ".json")
        self.assertEqual(len(els), 7)

    def test_node_speed_camera_aceito(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        node = next(e for e in els if e["type"] == "node" and e["id"] == 577242)
        d = c.normalizar(0, node)
        self.assertEqual(d["identificador"], "osm:node/577242")
        self.assertEqual(d["osm_tipo_elemento"], "node")
        self.assertEqual(d["osm_id"], 577242)
        self.assertEqual(d["osm_versao"], 7)
        self.assertEqual(d["osm_timestamp"], "2018-05-04T20:11:36Z")
        self.assertEqual(d["osm_tipo"], "speed_camera")
        self.assertEqual(d["procedencia"], "comunitaria")
        self.assertEqual(d["confiabilidade"], "nao_confirmada")
        self.assertEqual(d["atribuicao"], ATRIBUICAO)
        self.assertEqual(d["licenca"], LICENCA)
        self.assertEqual(d["tipo_radar"], "desconhecido")
        self.assertIsNone(d["situacao"])

    def test_semaforo_luz_vermelha_descartado(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        n123 = next(e for e in els if e["type"] == "node" and e["id"] == 123)
        self.assertIsNone(c.normalizar(0, n123))       # red_light_camera

    def test_traffic_signals_descartado(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        n999 = next(e for e in els if e["type"] == "node" and e["id"] == 999)
        self.assertIsNone(c.normalizar(0, n999))
        rel = next(e for e in els if e["type"] == "relation"
                   and e["id"] == 4586165)
        self.assertIsNone(c.normalizar(0, rel))

    def test_alpr_descartado(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        n1000 = next(e for e in els if e["type"] == "node" and e["id"] == 1000)
        self.assertIsNone(c.normalizar(0, n1000))

    def test_way_speed_camera_aceito_com_center(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        way = next(e for e in els if e["type"] == "way" and e["id"] == 123)
        d = c.normalizar(0, way)
        self.assertEqual(d["identificador"], "osm:way/123")
        self.assertEqual(d["qualidade"], "inferida")   # centro do way
        self.assertAlmostEqual(d["latitude"], -23.51, places=6)

    def test_enforcement_maxspeed_aceito(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        rel = next(e for e in els if e["type"] == "relation"
                   and e["id"] == 2165372)
        d = c.normalizar(0, rel)
        self.assertEqual(d["identificador"], "osm:relation/2165372")
        self.assertTrue(d["osm_tipo"].startswith("enforcement"))
        self.assertAlmostEqual(d["latitude"], -23.6454225, places=6)

    def test_ids_de_tipos_diferentes_nao_colidem(self):
        c = ColetorOSM()
        _, _, _, els = c.carregar(F_OSM)
        node = next(e for e in els if e["type"] == "node" and e["id"] == 123)
        way = next(e for e in els if e["type"] == "way" and e["id"] == 123)
        d_node = c.normalizar(0, node)
        d_way = c.normalizar(0, way)
        # node/123 e red_light -> descartado; way/123 aceito. Chaves diferentes.
        self.assertIsNone(d_node)
        self.assertEqual(d_way["identificador"], "osm:way/123")
        # e um node de velocidade com o mesmo id nao colidiria com o way:
        self.assertNotEqual(c._chave({"type": "node", "id": 123}),
                            c._chave({"type": "way", "id": 123}))

    def test_backoff_respeita_retry_after(self):
        self.assertEqual(_espera_backoff(1, "2.5"), 2.5)
        self.assertEqual(_espera_backoff(1), 1.0)
        self.assertEqual(_espera_backoff(2), 2.0)
        self.assertLessEqual(_espera_backoff(99), 60.0)


if __name__ == "__main__":
    unittest.main()
