# -*- coding: utf-8 -*-
"""Testes offline dos conectores de fonte com arquivo legivel:
F04 DNIT, F08 DER-SP, F09 DER-PR, F10 DER-MG, F13 Belo Horizonte.

Nenhum teste acessa a rede: usam fixtures locais e, quando verificam a
resolucao de URL, substituem a funcao de rede por um duble.
"""
import os
import unittest
from unittest import mock

from coletor.fontes import ckan
from coletor.fontes import planilha as pl
from coletor.fontes.dnit import ColetorDNIT
from coletor.fontes.dersp import ColetorDERSP
from coletor.fontes.derpr import ColetorDERPR
from coletor.fontes.dermg import ColetorDERMG
from coletor.fontes.pbh import ColetorPBH

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, nome)


class _FakeResp(object):
    def __init__(self, dados):
        self._d = dados if isinstance(dados, bytes) else dados.encode("utf-8")

    def read(self, *a):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ==========================================================================
# F04 DNIT
# ==========================================================================
class TestDNIT(unittest.TestCase):

    def test_carregar_xlsx_e_normalizar(self):
        c = ColetorDNIT()
        conteudo, ext, mime, regs = c.carregar(fx("dnit_pncv_fixture.xlsx"))
        self.assertEqual(ext, ".xlsx")
        self.assertEqual(len(regs), 3)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["via_codigo"], "BR-364")
        self.assertEqual(d["via_tipo"], "federal")
        self.assertEqual(d["fabricante"], "Vizentec")
        self.assertEqual(d["modelo"], "DTV 102")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertAlmostEqual(d["latitude"], -10.011852, places=6)
        self.assertAlmostEqual(d["longitude"], -67.773819, places=6)
        self.assertIn("Tipo: REV", d["observacoes"])
        # linha sem coordenada -> None (preservado, nao posicionado)
        self.assertIsNone(c.normalizar(2, regs[2]))

    def test_carregar_csv(self):
        c = ColetorDNIT()
        _, ext, _, regs = c.carregar(fx("dnit_pncv_fixture.csv"))
        self.assertEqual(ext, ".csv")
        self.assertEqual(len(regs), 2)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["via_codigo"], "BR-364")

    def test_resolver_url_usa_mais_novo_e_cai_no_fallback(self):
        recursos = [
            {"format": "XLSX", "name": "Controle de Velocidade - Junho/2024",
             "url": "https://x/dataset/a/resource/b/download/pncv_dados_abertos_12_07_2024.xlsx"},
            {"format": "XLSX", "name": "Controle de Velocidade - Julho/2026",
             "url": "https://x/dataset/a/resource/c/download/cgpert___pncv___07_2026.xlsx"},
            {"format": "CSV", "name": "Controle de Velocidade - Dezembro/2023",
             "url": "https://x/download/pncv_dados_abertos_14_12_2023.csv"},
        ]
        with mock.patch.object(ckan, "package_show", return_value=recursos):
            url = ColetorDNIT.resolver_url()
        self.assertTrue(url.endswith("cgpert___pncv___07_2026.xlsx"))

        with mock.patch.object(ckan, "package_show",
                               side_effect=RuntimeError("portal fora")):
            url = ColetorDNIT.resolver_url()
        self.assertEqual(url, ColetorDNIT.URL_FALLBACK)
        self.assertTrue(url.endswith(".xlsx"))
        self.assertIn("cgpert___pncv", url)


# ==========================================================================
# F08 DER-SP
# ==========================================================================
class TestDERSP(unittest.TestCase):

    def test_carregar_xlsx_e_normalizar(self):
        c = ColetorDERSP()
        _, ext, _, regs = c.carregar(fx("dersp_radares_fixture.xlsx"))
        self.assertEqual(ext, ".xlsx")
        self.assertEqual(len(regs), 3)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["via_codigo"], "SP-008")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertEqual(d["uf"], "SP")
        self.assertEqual(d["fabricante"], "Splice")
        self.assertEqual(d["modelo"], "SPL-MFS1")
        self.assertAlmostEqual(d["latitude"], -22.910293, places=6)
        self.assertIn("Inicio Operacao: 2025-07-16", d["observacoes"])
        # linha sem coordenada -> None
        self.assertIsNone(c.normalizar(2, regs[2]))

    def test_resolver_url_xlsx_e_fallback(self):
        recursos = [
            {"format": "LINK", "name": "Pesquisa de Radares",
             "url": "https://dersp.der.sp.gov.br/WebSite/MalhaRodoviaria/PesquisaRadar.aspx"},
            {"format": "XLSX", "name": "Radar",
             "url": "https://dersp.der.sp.gov.br/WebSite/Arquivos/DadosAbertos/AtivosRodoviarios/Radar/radares.xlsx"},
        ]
        with mock.patch.object(ckan, "package_show", return_value=recursos):
            url = ColetorDERSP.resolver_url()
        self.assertTrue(url.endswith("radares.xlsx"))

        with mock.patch.object(ckan, "package_show",
                               side_effect=RuntimeError("fora")):
            url = ColetorDERSP.resolver_url()
        self.assertEqual(url, ColetorDERSP.URL_FALLBACK)


# ==========================================================================
# F09 DER-PR
# ==========================================================================
class TestDERPR(unittest.TestCase):

    def test_carregar_txt_e_extrair_registros(self):
        c = ColetorDERPR()
        _, ext, _, regs = c.carregar(fx("derpr_medidores_fixture.txt"))
        self.assertEqual(len(regs), 3)
        r = regs[0]
        self.assertEqual(r["serie"], "FSC110-0572")
        self.assertEqual(r["identificacao"], "012.407.001.02")
        self.assertEqual(r["municipio"], "Paranaguá")
        self.assertEqual(r["rodovia"], "PR-407")
        self.assertEqual(r["km_completo"], "000+000")
        self.assertEqual(regs[1]["rodovia"], "PR-151")   # "PR- 151" normalizado
        self.assertEqual(regs[1]["municipio"], "Carambeí")

    def test_normalizar_sem_coordenada_guarda_sem_posicao(self):
        c = ColetorDERPR()
        # o relatorio NAO traz coordenada -> registro preservado SEM posicao
        s = c.normalizar(0, {"serie": "FSC110-0572"})
        self.assertIsNotNone(s)
        self.assertIsNone(s["latitude"])
        self.assertIsNone(s["longitude"])
        self.assertEqual(s["numero_serie"], "FSC110-0572")
        # com coordenada (sintetica) monta o dict canonico
        d = c.normalizar(0, {"serie": "FSC110-0572", "identificacao": "012.407.001.02",
                             "municipio": "Paranaguá", "rodovia": "PR-407",
                             "km": "000", "metros": "000", "tipo": "Controlador",
                             "coordenadas": "-25.5, -48.5"})
        self.assertEqual(d["via_codigo"], "PR-407")
        self.assertEqual(d["numero_serie"], "FSC110-0572")
        self.assertEqual(d["tipo_radar"], "fixo")

    def test_resolver_url_descobre_pdf_e_fallback(self):
        html = ('<html><body><p><a href="/x/fixos_240326.pdf">'
                'Rela&ccedil;&atilde;o de Radares</a></p></body></html>')
        with mock.patch("urllib.request.urlopen",
                        return_value=_FakeResp(html)):
            url = ColetorDERPR.resolver_url()
        self.assertTrue(url.endswith("fixos_240326.pdf"))
        self.assertTrue(url.endswith(".pdf"))

        with mock.patch("urllib.request.urlopen",
                        side_effect=RuntimeError("fora")):
            url = ColetorDERPR.resolver_url()
        self.assertEqual(url, ColetorDERPR.URL_FALLBACK)
        self.assertTrue(url.endswith(".pdf"))


# ==========================================================================
# F10 DER-MG
# ==========================================================================
class TestDERMG(unittest.TestCase):

    def test_carregar_html_e_extrair_tabela(self):
        c = ColetorDERMG()
        _, ext, _, regs = c.carregar(fx("dermg_radares_fixture.html"))
        self.assertEqual(ext, ".html")
        # 3 linhas de dados; a linha de observacao e ignorada
        self.assertEqual(len(regs), 3)
        self.assertEqual(regs[0]["rodovia"], "AMG0150")
        self.assertEqual(regs[0]["km"], "3,10")
        self.assertEqual(regs[0]["equipamento"], "45424543")
        self.assertEqual(regs[0]["serie"], "R12687")
        self.assertIn("km/h", regs[0]["velocidade"])

    def test_normalizar_sem_coordenada_e_com_varios_equipamentos(self):
        c = ColetorDERMG()
        # a tabela nao traz coordenada -> registro preservado SEM posicao
        s = c.normalizar(0, {"rodovia": "AMG0150", "km": "3,10"})
        self.assertIsNotNone(s)
        self.assertIsNone(s["latitude"])
        self.assertIsNone(s["longitude"])
        self.assertEqual(s["via_codigo"], "AMG0150")
        # com coordenada sintetica: multiplos numeros de serie NAO viram 1:1
        d = c.normalizar(0, {"rodovia": "LMG800", "km": "2,6", "municipio": "Lagoa Santa",
                             "velocidade": "110 km/h 80 km/h",
                             "equipamento": "1934  1935  2292  2293",
                             "serie": "R09802 R13744",
                             "coordenadas": "-19.6, -43.9"})
        self.assertIsNone(d["numero_serie"])          # ambiguidade preservada
        self.assertEqual(d["velocidade_leves"], 110.0)
        self.assertEqual(d["velocidade_pesados"], 80.0)
        self.assertIn("Serie(s): R09802 R13744", d["observacoes"])

    def test_resolver_url_pagina_e_arquivo(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=RuntimeError("fora")):
            self.assertEqual(ColetorDERMG.resolver_url(), ColetorDERMG.PAGINA)
        html = '<a href="/arq/radares_2026.pdf">baixar</a>'
        with mock.patch("urllib.request.urlopen",
                        return_value=_FakeResp(html)):
            url = ColetorDERMG.resolver_url()
        self.assertTrue(url.endswith("radares_2026.pdf"))


# ==========================================================================
# F13 Belo Horizonte
# ==========================================================================
class TestPBH(unittest.TestCase):

    def test_carregar_csv_e_normalizar(self):
        c = ColetorPBH()
        _, ext, _, regs = c.carregar(fx("pbh_fiscalizacao_fixture.csv"))
        self.assertEqual(ext, ".csv")
        self.assertEqual(len(regs), 3)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "1461")
        self.assertEqual(d["uf"], "MG")
        self.assertEqual(d["municipio_nome"], "Belo Horizonte")
        self.assertEqual(d["numero_serie"], "1061")
        self.assertEqual(d["velocidade_leves"], 60.0)
        # GEOMETRIA projetada (EPSG:31983) convertida para graus, dentro de BH
        self.assertAlmostEqual(d["latitude"], -19.9213, places=3)
        self.assertAlmostEqual(d["longitude"], -43.9240, places=3)
        self.assertIn("31983", d["metodo_obtencao"])
        # registro sem geometria -> None
        self.assertIsNone(c.normalizar(2, regs[2]))

    def test_resolver_url_mais_recente_e_fallback(self):
        recursos = [
            {"name": "20220601_fiscalizacao_eletronica",
             "url": "https://x/download/20220601_fiscalizacao_eletronica.csv"},
            {"name": "20260901_fiscalizacao_eletronica",
             "url": "https://x/download/20260901_fiscalizacao_eletronica.csv"},
            {"name": "20260701_fiscalizacao_eletronica",
             "url": "https://x/download/20260701_fiscalizacao_eletronica.csv"},
            {"name": "fiscalizacao_eletronica", "url": "https://x/a.pdf"},
        ]
        with mock.patch.object(ckan, "package_show", return_value=recursos):
            url = ColetorPBH.resolver_url()
        self.assertTrue(url.endswith("20260901_fiscalizacao_eletronica.csv"))

        with mock.patch.object(ckan, "package_show",
                               side_effect=RuntimeError("fora")):
            url = ColetorPBH.resolver_url()
        self.assertEqual(url, ColetorPBH.URL_FALLBACK)


# ==========================================================================
# Utilitarios de leitura/coordenada
# ==========================================================================
class TestPlanilha(unittest.TestCase):

    def test_parse_coordenadas_formatos(self):
        self.assertEqual(pl.parse_coordenadas("-10,011852 / -67,773819"),
                         (-10.011852, -67.773819))
        self.assertEqual(pl.parse_coordenadas("-22.910293, -46.546438"),
                         (-22.910293, -46.546438))
        self.assertEqual(pl.parse_coordenadas(""), (None, None))
        self.assertEqual(pl.parse_coordenadas(None), (None, None))

    def test_utm_para_geografico(self):
        lat, lon = pl.utm_para_geografico(612616.59, 7796867.80, 23, True)
        self.assertAlmostEqual(lat, -19.9213, places=3)
        self.assertAlmostEqual(lon, -43.9240, places=3)


if __name__ == "__main__":
    unittest.main()
