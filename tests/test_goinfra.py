# -*- coding: utf-8 -*-
"""Testes offline do conector GOINFRA (GO).

Nenhum teste acessa a rede: usam a amostra recortada extraida do PDF oficial
com ``pdftotext -layout`` (tests/fixtures/goinfra/, ver PROVENANCIA.txt) e,
quando verificam a descoberta de URL, substituem ``coletor.http.baixar`` por
um duble.

Cobre: parsing das 20 linhas da amostra, conversao de km, coordenadas em
micrograus, identidades distintas (codigo != serie != faixa), conflito do
codigo 174L5R129 (GO-050 x GO-174), quarentena de coordenada (fora da UF,
lat==lon, divergencia no mesmo trecho), normalizacao canonica e o teste de
aceitacao dos 5 POIs do Waze por distancia haversine.
"""
import math
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes import goinfra
from coletor.fontes.goinfra import (ColetorGOINFRA, analisar,
                                    descobrir_url_recurso, extrair_registros,
                                    ler_pdf_texto_layout)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "goinfra")
FIX_TXT = os.path.join(FIXTURES, "goinfra_equipamentos_fixture.txt")
FIX_HTML = os.path.join(FIXTURES, "goinfra_pagina_fixture.html")


def ler(path):
    with open(path, "rb") as f:
        return f.read()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p = math.radians
    dphi = p(lat2 - lat1)
    dl = p(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def registros_fixture():
    return extrair_registros(ler(FIX_TXT).decode("utf-8"))


def buscar(regs, cod):
    return [r for r in regs if r["cod"] == cod]


class TestExtracao(unittest.TestCase):

    def test_conta_registros_da_amostra(self):
        regs = registros_fixture()
        self.assertEqual(len(regs), 20)
        tipos = [r["tipo"] for r in regs]
        self.assertIn("RADAR FIXO", tipos)
        self.assertIn("LOMBADA ELET", tipos)

    def test_km_mais_metros_preserva_original(self):
        regs = registros_fixture()
        r = buscar(regs, "060L5R001")[0]
        self.assertEqual(r["km"], "225")
        self.assertEqual(r["metros"], "332")
        self.assertAlmostEqual(goinfra._km_decimal(r), 225.332, places=6)
        self.assertEqual(goinfra._km_original(r), "225+332")

    def test_km_com_virgula_decimal(self):
        regs = registros_fixture()
        r = buscar(regs, "174L5R131")[0]
        self.assertIsNone(r["km"])
        self.assertEqual(r["km_decimal"], "255,530")
        self.assertAlmostEqual(goinfra._km_decimal(r), 255.530, places=6)
        self.assertEqual(goinfra._km_original(r), "255,530")

    def test_complemento_ausente_nao_quebra(self):
        regs = registros_fixture()
        r = buscar(regs, "060L4B083")[0]
        self.assertIsNone(r["km"])
        self.assertIsNone(r["km_decimal"])
        self.assertIsNone(goinfra._km_decimal(r))

    def test_campos_da_linha(self):
        regs = registros_fixture()
        r = buscar(regs, "060L5R001")[0]
        self.assertEqual(r["faixa"], "1C")
        self.assertEqual(r["sentido_cd"], "Crescente")
        self.assertEqual(r["serie"], "118690177")
        self.assertEqual(r["local"], "GO-060")
        self.assertEqual(r["municipio"], "IPORA")
        self.assertEqual(r["sre"], "060EGO0230")
        self.assertEqual(r["velocidade"], "60")
        self.assertEqual(r["data_autorizacao"], "09/04/2026")
        self.assertEqual(r["afericao_valida_ate"], "28/02/2027")
        self.assertEqual(r["lote"], "Lote 05 - 2025005")
        self.assertEqual(r["estudo_tecnico"], "ET060L5001")

    def test_identidades_distintas(self):
        # codigo de equipamento != numero de serie != faixa (contrato)
        regs = registros_fixture()
        r = buscar(regs, "060L5R001")[0]
        self.assertNotEqual(r["cod"], r["serie"])
        self.assertEqual(r["cod"], "060L5R001")
        self.assertEqual(r["serie"], "118690177")
        self.assertEqual(r["faixa"], "1C")

    def test_codigo_sre_sem_letra(self):
        # alguns SRE vem sem a letra entre o numero e GO (ex.: 156GO0140)
        testo = (" RADAR FIXO       156L4R114        1D     Decrescente      "
                 "FSC110-0874     GO-156    km 090+380           "
                 "NAZARIO/AMERICANO DO BRASIL                                "
                 "ANICUNS          156GO0140    -16374468   -49964847       80"
                 "          03/08/2026      03/08/2026     16/07/2027      "
                 "Lote 04 - 2025004       4            85889637           "
                 "ET156L40115")
        regs = extrair_registros(testo)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["sre"], "156GO0140")


class TestConflitoEQuarentena(unittest.TestCase):

    def test_conflito_codigo_em_duas_vias(self):
        regs = registros_fixture()
        regs, conflitos, _quar = analisar(regs)
        self.assertIn("174L5R129", conflitos)
        marcados = buscar(regs, "174L5R129")
        self.assertEqual(len(marcados), 2)   # as DUAS linhas, nao escolhe
        for r in marcados:
            self.assertIsNotNone(r["_conflito"])
        vias = sorted(r["local"] for r in marcados)
        self.assertEqual(vias, ["GO-050", "GO-174"])
        # o conflito e registrado; nenhuma das linhas e descartada
        self.assertIn("GO-050", conflitos["174L5R129"])
        self.assertIn("GO-174", conflitos["174L5R129"])

    def test_quarentena_coordenada_fora_da_uf(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        # 070L4B031/041 tem longitude POSITIVA (+49.46 / +49.60) -> impossivel
        for cod in ("070L4B031", "070L4B041"):
            for r in buscar(regs, cod):
                self.assertIsNotNone(r["_quarentena"])
                self.assertIn("fora da UF", r["_quarentena"])

    def test_quarentena_latitude_igual_longitude(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        for r in buscar(regs, "010L3B185"):
            self.assertIsNotNone(r["_quarentena"])
            self.assertIn("igual a longitude", r["_quarentena"])

    def test_quarentena_divergencia_no_mesmo_trecho(self):
        # GO-174 km 254+524: 174L5R021 (lon ~ -50.03) x 174L5R022/023 (-51.03)
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        for cod in ("174L5R021", "174L5R022", "174L5R023"):
            r = buscar(regs, cod)[0]
            self.assertIsNotNone(r["_quarentena"])
            self.assertIn("divergentes", r["_quarentena"])
        # a divergencia real e ~1 grau (nao confundir com ruido de metros)
        r21 = buscar(regs, "174L5R021")[0]
        r22 = buscar(regs, "174L5R022")[0]
        self.assertAlmostEqual(int(r21["lon"]) / 1e6, -50.034189, places=6)
        self.assertAlmostEqual(int(r22["lon"]) / 1e6, -51.034260, places=6)


class TestNormalizacao(unittest.TestCase):

    def test_normaliza_coordenada_micrograus(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        c = ColetorGOINFRA()
        r = buscar(regs, "174L5R125")[0]
        d = c.normalizar(0, r)
        self.assertEqual(d["uf"], "GO")
        self.assertEqual(d["via_codigo"], "GO-174")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["identificador"], "174L5R125")
        self.assertEqual(d["tipo_identificador"], "codigo_equipamento")
        self.assertEqual(d["numero_serie"], "118690606")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["velocidade_geral"], 80.0)
        self.assertEqual(d["sentido"], "crescente")
        self.assertEqual(d["qualidade"], "oficial")
        self.assertAlmostEqual(d["latitude"], -17.528653, places=6)
        self.assertAlmostEqual(d["longitude"], -51.111486, places=6)
        # km 274+050 -> 274.050 preservando original
        self.assertAlmostEqual(d["km"], 274.050, places=6)
        self.assertIn("KM original: 274+050", d["observacoes"])

    def test_afericao_nao_vira_situacao(self):
        # validade metrologica NAO prova operacao: situacao fica None
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        c = ColetorGOINFRA()
        d = c.normalizar(0, buscar(regs, "060L5R001")[0])
        self.assertIsNone(d["situacao"])
        self.assertIn("Afericao valida ate: 28/02/2027", d["observacoes"])

    def test_quarentena_marca_qualidade(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        c = ColetorGOINFRA()
        d = c.normalizar(0, buscar(regs, "070L4B031")[0])
        self.assertEqual(d["qualidade"], "conflitante")
        self.assertIn("QUARENTENA", d["observacoes"])

    def test_conflito_marca_observacao(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        c = ColetorGOINFRA()
        d = c.normalizar(0, buscar(regs, "174L5R129")[0])
        self.assertEqual(d["qualidade"], "conflitante")
        self.assertIn("CONFLITO", d["observacoes"])

    def test_linha_vazia_nao_vira_registro(self):
        c = ColetorGOINFRA()
        self.assertEqual(extrair_registros(""), [])
        self.assertIsNone(c.normalizar(0, {"cod": None, "lat": None,
                                           "lon": None}))


class TestAceitacaoPOIs(unittest.TestCase):
    """Os 5 POIs do Waze devem casar com o equipamento oficial (haversine)."""

    POIS = [
        ("174L5R129", -17.625377, -51.060863, 88.9),
        ("174L5R127", -17.584521, -51.089497, 87.3),
        ("174L5R125", -17.529214, -51.111256, 67.0),
        ("060L5R091", -16.459361, -51.671518, 83.2),
        ("060L5B058", -16.385100, -51.564215, 43.0),
    ]

    def test_pareamento_por_haversine(self):
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        for cod, plat, plon, esperado in self.POIS:
            cands = buscar(regs, cod)
            self.assertTrue(cands, "equipamento %s ausente na amostra" % cod)
            melhor = min(
                cands,
                key=lambda r: haversine(plat, plon, int(r["lat"]) / 1e6,
                                        int(r["lon"]) / 1e6))
            d = haversine(plat, plon, int(melhor["lat"]) / 1e6,
                          int(melhor["lon"]) / 1e6)
            self.assertAlmostEqual(
                d, esperado, delta=0.5,
                msg="POI %s: %.1f m (esperado ~%.1f)" % (cod, d, esperado))

    def test_conflito_174L5R129_usa_a_linha_GO_174(self):
        # as duas linhas de 174L5R129: so a de GO-174 fica perto do POI;
        # a de GO-050 esta a dezenas de km (nao escolher cegamente).
        regs = registros_fixture()
        regs, _c, _q = analisar(regs)
        cands = buscar(regs, "174L5R129")
        dists = {r["local"]: haversine(-17.625377, -51.060863,
                                       int(r["lat"]) / 1e6,
                                       int(r["lon"]) / 1e6)
                 for r in cands}
        self.assertLess(dists["GO-174"], 100.0)
        self.assertGreater(dists["GO-050"], 1000.0)


class TestResolucaoDeUrl(unittest.TestCase):

    def test_descobre_o_relatorio_mais_recente(self):
        html = ler(FIX_HTML)
        url, todas = descobrir_url_recurso(html.decode("utf-8"))
        self.assertTrue(url.endswith("Lista_de_Equipamento_02_10_2026.xlsx-"
                                     "Equipamentos-Ativos.pdf"))
        self.assertIn("Equipamentos_Fiscalizacao_Ativos_11_2025", " ".join(todas))

    def test_resolver_url_usa_a_pagina(self):
        html = ler(FIX_HTML)
        with mock.patch.object(http, "baixar", return_value=(html, {}, "u")):
            url = ColetorGOINFRA.resolver_url()
        self.assertIn("Lista_de_Equipamento_02_10_2026", url)

    def test_resolver_url_cai_no_fallback(self):
        with mock.patch.object(http, "baixar",
                               side_effect=RuntimeError("pagina fora")):
            url = ColetorGOINFRA.resolver_url()
        self.assertEqual(url, ColetorGOINFRA.URL_FALLBACK)
        self.assertTrue(url.endswith(".pdf"))

    def test_descobrir_url_sem_arquivos(self):
        url, todas = descobrir_url_recurso("<html><body>sem arquivos</body></html>")
        self.assertIsNone(url)
        self.assertEqual(todas, [])


class TestDependenciaPoppler(unittest.TestCase):

    def test_ler_pdf_texto_layout_sem_pdftotext(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(http.ErroFonte) as ctx:
                ler_pdf_texto_layout(b"%PDF-1.4 ...")
        self.assertIn("poppler-utils", str(ctx.exception))

    def test_ler_pdf_texto_layout_pdf_invalido(self):
        if not goinfra.pdftotext_disponivel():
            self.skipTest("pdftotext ausente")
        with self.assertRaises(http.ErroFonte):
            ler_pdf_texto_layout(b"isto nao e um pdf")


class TestSincronizacao(unittest.TestCase):

    def test_pipeline_grava_pontos_em_banco_temporario(self):
        from core import config
        from tests.common import ambiente_temporario
        ambiente_temporario()          # nunca toca o DB de producao
        coletor = ColetorGOINFRA(db_path=config.DB_PATH)
        try:
            resumo = coletor.sincronizar(FIX_TXT)
            self.assertEqual(resumo["linhas_recebidas"], 20)
            self.assertEqual(resumo["criados"], 20)
            self.assertTrue(resumo["hash_sha256"])
            # ha pontos no banco e o valor publicado foi preservado
            cur = coletor.conn.execute(
                "SELECT COUNT(*) FROM PONTO_FISCALIZACAO")
            self.assertEqual(cur.fetchone()[0], 20)
            # nenhuma velocidade fora de faixa plausivel foi gravada
            cur = coletor.conn.execute(
                "SELECT COUNT(*) FROM LIMITE_VELOCIDADE WHERE "
                "velocidade_kmh <= 0 OR velocidade_kmh > 350")
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            coletor.conn.close()


if __name__ == "__main__":
    unittest.main()
