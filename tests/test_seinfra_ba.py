# -*- coding: utf-8 -*-
"""Testes offline do conector SEINFRA-BA (F-BA).

Sem rede: usam fixtures locais capturadas da fonte real (KML dos radares
estaticos, GeoJSON dos fixos, texto extraido do PDF "Lista-Radar") e dubles
para a descoberta de URL. Exercitam KML (xml.etree), GeoJSON (json), ZIP
(zipfile), PDF-texto, a recusa de RAR e a ordem LONGITUDE,LATITUDE.
"""
import io
import os
import unittest
import zipfile
from unittest import mock

from core import db as dbmod
from coletor import http
from coletor.fontes import seinfra_ba
from coletor.fontes.seinfra_ba import (ColetorSEINFRABA, _coordenadas_kml,
                                       _km_ba, _via_ba)
from tests import common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "seinfra_ba")
KML = os.path.join(FIX, "radar_estatico_4cia.kml")
GEOJSON = os.path.join(FIX, "mapa_radar_15092026.geojson")
TXT = os.path.join(FIX, "lista_radar_15-09-2026.txt")

# Fragmento real da pagina oficial (hrefs reais de 10/10/2026).
HTML_PAGINA = """<html><body>
<p>Localizacao dos Radares Fixos de Controle de Velocidade de
Responsabilidade da SEINFRA<br>
Formato: <a href="http://sit.infraestrutura.ba.gov.br/maparadar/"
target="_blank">Pagina WEB</a><br>
Formato: <a href="/infraestrutura/sites/site-seinfra/files/2026-09/Mapa-Radar_15-09-2026.rar"
target="_blank">Arquivo KML</a><br>
Tabela: <a href="/infraestrutura/sites/site-seinfra/files/2026-09/Lista-Radar_15-09-2026.pdf"
target="_blank">Arquivo PDF</a></p>
<p>Localizacao dos Radares Estaticos de Responsabilidade da SEINFRA</p>
<p>Formato: <a href="http://sit.infraestrutura.ba.gov.br/docs/download/mapas/radar-estatico-4CIA.zip"
target="_blank">Arquivo KML</a></p>
</body></html>"""


def _zip_de(fonte, nome="radar-estatico-2024.kml"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        with open(fonte, "rb") as f:
            z.writestr(nome, f.read())
    return buf.getvalue()


# ==========================================================================
# KML (radares estaticos)
# ==========================================================================
class TestSeinfraBaKML(unittest.TestCase):

    def test_carregar_kml_e_normalizar(self):
        c = ColetorSEINFRABA()
        _c, ext, mime, regs = c.carregar(KML)
        self.assertEqual(ext, ".kml")
        self.assertEqual(mime, seinfra_ba.MIME_KML)
        self.assertEqual(len(regs), 104)          # 104 Placemarks reais
        r0 = regs[0]
        self.assertEqual(r0["UOE"], "4ªCIA")
        self.assertEqual(r0["Radar"], "TC010657")
        self.assertEqual(r0["Rodovia"], "BA210")
        d = c.normalizar(0, r0)
        self.assertEqual(d["uf"], "BA")
        self.assertEqual(d["identificador"], "TC010657")
        self.assertEqual(d["via_codigo"], "BA-210")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["km"], 381.0)
        self.assertEqual(d["tipo_radar"], "fixo")     # estatico -> fixo (dominio)
        self.assertIsNone(d["municipio_nome"])        # KML nao traz municipio
        self.assertAlmostEqual(d["latitude"], -9.403211, places=6)
        self.assertAlmostEqual(d["longitude"], -40.356365, places=6)
        self.assertIn("Radares Estaticos", d["observacoes"])

    def test_normalizar_sem_coordenada_retorna_none(self):
        c = ColetorSEINFRABA()
        self.assertIsNone(c.normalizar(0, {"Radar": "TC1", "Rodovia": "BA210"}))


# ==========================================================================
# GeoJSON (radares fixos)
# ==========================================================================
class TestSeinfraBaGeoJSON(unittest.TestCase):

    def test_carregar_geojson_e_normalizar(self):
        c = ColetorSEINFRABA()
        _c, ext, mime, regs = c.carregar(GEOJSON)
        self.assertEqual(ext, ".geojson")
        self.assertEqual(mime, seinfra_ba.MIME_GEOJSON)
        self.assertEqual(len(regs), 3)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "FIGCT0005 / FIGCT0006")
        self.assertEqual(d["numero_serie"], "2100006")
        self.assertEqual(d["uf"], "BA")
        self.assertEqual(d["municipio_nome"], "SENHOR DO BONFIM")
        self.assertEqual(d["via_codigo"], "BA-131")
        self.assertEqual(d["km"], 9.5)
        self.assertEqual(d["velocidade_geral"], 50.0)
        self.assertEqual(d["fabricante"], "CONSILUX")
        self.assertEqual(d["modelo"], "CSC-II")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertAlmostEqual(d["latitude"], -10.5177, places=4)
        self.assertAlmostEqual(d["longitude"], -40.2295, places=4)


# ==========================================================================
# PDF-texto (Lista-Radar, fixos)
# ==========================================================================
class TestSeinfraBaPDF(unittest.TestCase):

    def test_parse_texto_completo(self):
        c = ColetorSEINFRABA()
        _c, ext, mime, regs = c.carregar(TXT)
        self.assertEqual(ext, ".txt")
        self.assertEqual(mime, seinfra_ba.MIME_TXT)
        self.assertEqual(len(regs), 79)           # 79 radares fixos reais
        ids = [r["ID"] for r in regs]
        self.assertEqual(ids[0], "1")
        self.assertEqual(ids[-1], "79")
        # linha com serie alfanumerica atipica (CSX2100017) preservada
        d9 = c.normalizar(8, regs[8])
        self.assertEqual(d9["numero_serie"], "CSX2100017")
        self.assertEqual(d9["municipio_nome"], "LUÍS EDUARDO MAGALHÃES")
        # linha com espaco dentro da serie ("FSCII 7363") nao desloca registros
        d = c.normalizar(65, regs[65])
        self.assertEqual(regs[65]["ID"], "66")
        self.assertEqual(d["numero_serie"], "FSCII 7363")
        self.assertEqual(d["velocidade_geral"], 60.0)
        self.assertEqual(d["via_codigo"], "BA-526")

    def test_km_e_via_normalizacao(self):
        c = ColetorSEINFRABA()
        _c, _e, _m, regs = c.carregar(TXT)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["uf"], "BA")
        self.assertEqual(d["km"], 9.5)
        self.assertAlmostEqual(d["latitude"], -10.5177, places=4)
        self.assertAlmostEqual(d["longitude"], -40.2295, places=4)
        self.assertIn("INMETRO: 13854596", d["observacoes"])


# ==========================================================================
# ZIP e RAR
# ==========================================================================
class TestSeinfraBaEmpacotado(unittest.TestCase):

    def test_zip_extrai_kml(self):
        c = ColetorSEINFRABA()
        dados = _zip_de(KML)
        conteudo, ext, mime, regs = c._decodificar(dados, ".zip")
        self.assertEqual(ext, ".zip")
        self.assertEqual(mime, seinfra_ba.MIME_ZIP)
        self.assertEqual(conteudo, dados)          # preserva o ZIP original
        self.assertEqual(len(regs), 104)

    def test_rar_e_recusado_com_erro_claro(self):
        c = ColetorSEINFRABA()
        with self.assertRaises(http.ErroFonte) as ctx:
            c._decodificar(b"Rar!\x1a\x07\x01\x00conteudo", ".rar")
        self.assertIn("RAR", str(ctx.exception))


# ==========================================================================
# descoberta de URL
# ==========================================================================
class TestSeinfraBaDescobrir(unittest.TestCase):

    def test_descobrir_recursos_offline(self):
        urls = ColetorSEINFRABA.descobrir_recursos(HTML_PAGINA)
        self.assertTrue(urls["fixos_kml"].endswith("Mapa-Radar_15-09-2026.rar"))
        self.assertTrue(urls["fixos_kml"].startswith("https://www.ba.gov.br/"))
        self.assertTrue(urls["fixos_pdf"].endswith("Lista-Radar_15-09-2026.pdf"))
        self.assertTrue(urls["estaticos_kml"].endswith("radar-estatico-4CIA.zip"))
        self.assertTrue(urls["estaticos_kml"].startswith("http://"))

    def test_resolver_url_prefere_pdf_e_cai_no_fallback(self):
        with mock.patch.object(seinfra_ba.http, "baixar",
                               return_value=(HTML_PAGINA.encode(), {},
                                             ColetorSEINFRABA.URL_PAGINA)):
            url = ColetorSEINFRABA.resolver_url()
        self.assertTrue(url.endswith("Lista-Radar_15-09-2026.pdf"))

        with mock.patch.object(seinfra_ba.http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorSEINFRABA.resolver_url()
        self.assertEqual(url, ColetorSEINFRABA.URL_FALLBACK)


# ==========================================================================
# utilidades (ordem LON,LAT etc.)
# ==========================================================================
class TestSeinfraBaUtil(unittest.TestCase):

    def test_coordenadas_kml_lon_lat(self):
        # KML: "lon,lat" -> devolve (lon, lat)
        self.assertEqual(_coordenadas_kml("-40.356365,-9.403211"),
                         (-40.356365, -9.403211))
        self.assertEqual(_coordenadas_kml(""), (None, None))

    def test_via_e_km(self):
        self.assertEqual(_via_ba("BA131"), "BA-131")
        self.assertEqual(_via_ba("ba 210"), "BA-210")
        self.assertIsNone(_via_ba(""))
        self.assertEqual(_km_ba("9+500m"), 9.5)
        self.assertEqual(_km_ba("381.000000"), 381.0)
        self.assertIsNone(_km_ba(None))


# ==========================================================================
# integracao (banco temporario)
# ==========================================================================
class TestSeinfraBaSync(unittest.TestCase):

    def test_sincronizar_kml_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorSEINFRABA(db_path=common.config.DB_PATH)
        try:
            resumo = c.sincronizar(KML)
            self.assertEqual(resumo["linhas_recebidas"], 104)
            self.assertEqual(resumo["criados"], 104)
            self.assertEqual(resumo["rejeitados"], 0)
            n = dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO")
            self.assertEqual(n, 104)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
