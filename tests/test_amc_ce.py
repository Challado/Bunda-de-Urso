# -*- coding: utf-8 -*-
"""Testes offline do conector AMC Fortaleza (F-CE).

Sem rede: usam a fixture GeoJSON real do endpoint publico e dubles para a
descoberta de URL. Exercitam o parse GeoJSON (geometria MultiPoint em ordem
LONGITUDE,LATITUDE), o parse CSV alternativo e a normalizacao sem inventar
tipo de radar (a fonte so declara "finalidade").
"""
import os
import unittest
from unittest import mock

from core import db as dbmod
from coletor import http
from coletor.fontes import amc_ce
from coletor.fontes.amc_ce import ColetorAMCCE, _data_compacta
from tests import common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "amc_ce")
GEOJSON = os.path.join(FIX, "equipamentos_fiscalizacao_eletronica.geojson")

# Fragmento real da pagina (hrefs reais de 10/10/2026).
HTML_PAGINA = """<html><body>
<a href="https://mapas.fortaleza.ce.gov.br/api/download/geojson/538">GeoJSON</a>
<a href="https://mapas.fortaleza.ce.gov.br/api/download/csv/538">CSV</a>
<a href="https://mapas.fortaleza.ce.gov.br/api/download/kml/538">KML</a>
<a href="https://mapas.fortaleza.ce.gov.br/api/download/shape/538">Shape</a>
</body></html>"""

# Duas linhas reais da exportacao CSV do mesmo endpoint.
CSV = (
    'FID,id,sitio,status,finalidade,endereco,viasentido,bairro,regional,'
    'dataativacao,datadesativacao,faixas_via,faixas_fis,temcontagem,fonte,ano,'
    'src_codif,the_geom\n'
    'vw_fid--a,1,06702001,Ativo,Fiscalização,"Av. Bezerra de Menezes, 306 '
    '[L-O]",Av. Bezerra de Menezes [L-O],Farias Brito,SR 3,20221116,,4,4,S,'
    'Autarquia Municipal de Trânsito e Cidadania - AMC,2026,'
    '"SIRGAS 2000 - UTM Zone 24S (EPSG: 31984); Codificação: UTF-8",'
    'MULTIPOINT ((-38.547493 -3.732050000000006))\n'
    'vw_fid--b,2,06702002,Ativo,Fiscalização,"Av. Bezerra de Menezes, 310 '
    '[O-L]",Av. Bezerra de Menezes [O-L],Farias Brito,SR 3,20221116,,4,4,S,'
    'Autarquia Municipal de Trânsito e Cidadania - AMC,2026,'
    '"SIRGAS 2000 - UTM Zone 24S (EPSG: 31984); Codificação: UTF-8",'
    'MULTIPOINT ((-38.548100 -3.732200))\n'
)


class TestAmcCeGeoJSON(unittest.TestCase):

    def test_carregar_geojson_e_normalizar(self):
        c = ColetorAMCCE()
        _c, ext, mime, regs = c.carregar(GEOJSON)
        self.assertEqual(ext, ".geojson")
        self.assertEqual(mime, amc_ce.MIME_GEOJSON)
        self.assertEqual(len(regs), 3)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["uf"], "CE")
        self.assertEqual(d["municipio_nome"], "Fortaleza")
        self.assertEqual(d["municipio_ibge"], "2304400")
        self.assertEqual(d["identificador"], "06702001")
        self.assertEqual(d["tipo_identificador"], "cadastro_local")
        self.assertEqual(d["situacao"], "ativo")
        self.assertEqual(d["via_tipo"], "municipal")
        self.assertEqual(d["via_codigo"], "Av. Bezerra de Menezes [L-O]")
        # a fonte NAO declara fixo/portatil -> nada e inventado
        self.assertEqual(d["tipo_radar"], "desconhecido")
        self.assertIsNone(d.get("velocidade_geral"))
        self.assertAlmostEqual(d["latitude"], -3.73205, places=5)
        self.assertAlmostEqual(d["longitude"], -38.547493, places=5)
        self.assertIn("Finalidade: Fiscalização", d["observacoes"])
        self.assertIn("Bairro: Farias Brito", d["observacoes"])
        # data de ativacao formatada (YYYYMMDD -> ISO), sem inventar
        self.assertIn("Ativacao: 2022-11-16", d["observacoes"])

    def test_normalizar_sem_coordenada_retorna_none(self):
        c = ColetorAMCCE()
        self.assertIsNone(c.normalizar(0, {"sitio": "06702001",
                                           "status": "Ativo"}))


class TestAmcCeCSV(unittest.TestCase):

    def test_decodificar_csv_the_geom_multi_point(self):
        c = ColetorAMCCE()
        _c, ext, mime, regs = c._decodificar(CSV.encode("utf-8"), ".csv")
        self.assertEqual(ext, ".csv")
        self.assertEqual(mime, amc_ce.MIME_CSV)
        self.assertEqual(len(regs), 2)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "06702001")
        self.assertEqual(d["situacao"], "ativo")
        # the_geom "MULTIPOINT ((lon lat))" -> ordem LON,LAT
        self.assertAlmostEqual(d["longitude"], -38.547493, places=5)
        self.assertAlmostEqual(d["latitude"], -3.73205, places=5)


class TestAmcCeDescobrir(unittest.TestCase):

    def test_descobrir_recursos_offline(self):
        urls = ColetorAMCCE.descobrir_recursos(HTML_PAGINA)
        self.assertEqual(urls["geojson"],
                         "https://mapas.fortaleza.ce.gov.br/api/download/"
                         "geojson/538")
        self.assertEqual(urls["csv"].rsplit("/", 2)[1], "csv")

    def test_resolver_url_usa_geojson_e_cai_no_fallback(self):
        with mock.patch.object(amc_ce.http, "baixar",
                               return_value=(HTML_PAGINA.encode(), {},
                                             ColetorAMCCE.URL_PAGINA)):
            url = ColetorAMCCE.resolver_url()
        self.assertTrue(url.endswith("/api/download/geojson/538"))

        with mock.patch.object(amc_ce.http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorAMCCE.resolver_url()
        self.assertEqual(url, ColetorAMCCE.API_GEOJSON)


class TestAmcCeUtil(unittest.TestCase):

    def test_data_compacta(self):
        self.assertEqual(_data_compacta("20221116"), "2022-11-16")
        self.assertEqual(_data_compacta(20221116.0), "2022-11-16")
        self.assertIsNone(_data_compacta(""))
        self.assertIsNone(_data_compacta(None))
        self.assertIsNone(_data_compacta("2022-11-16"))   # nao inventa
        self.assertIsNone(_data_compacta("20221316"))     # mes invalido


class TestAmcCeSync(unittest.TestCase):

    def test_sincronizar_geojson_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorAMCCE(db_path=common.config.DB_PATH)
        try:
            resumo = c.sincronizar(GEOJSON)
            self.assertEqual(resumo["linhas_recebidas"], 3)
            self.assertEqual(resumo["criados"], 3)
            self.assertEqual(resumo["rejeitados"], 0)
            n = dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO")
            self.assertEqual(n, 3)
            row = dbmod.query_one(
                c.conn,
                "SELECT uf_sigla FROM MUNICIPIO WHERE codigo_ibge='2304400'")
            self.assertEqual(row["uf_sigla"], "CE")
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
