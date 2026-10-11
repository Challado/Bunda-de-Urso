# -*- coding: utf-8 -*-
"""Testes offline do conector ASTT Araguaina (medidores de velocidade).

Sem rede: usam a fixture PDF real (lista de enderecos) e dubles para a
descoberta de URL. Verificam o parse linha-a-linha (uma linha por faixa), o
agrupamento por equipamento (processo + serie), a interpretacao da
coordenada malformada pelo formato da fonte (sem GPS artificial) e a
normalizacao.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes import araguaiana_to
from coletor.fontes.araguaiana_to import ColetorASTTAraguaina, _coord
from core import config
from core import db as dbmod
import tests.common as common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "araguaiana_to")
PDF = os.path.join(FIX, "equipamentos_araguaina.pdf")

HTML_PAGINA = """<html><body>
<p>A ASTT disponibiliza a Lista de Enderecos dos Radares ... Acesse a lista
completa abaixo: <a href="https://www.araguaina.to.gov.br/documentos/equipamentos_araguaina.pdf">Baixar Lista de Endere&ccedil;os</a></p>
</body></html>"""


def _resp(conteudo, url="https://x/"):
    dados = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    return (dados, {}, url)


class TestASTTAraguainaCarregar(unittest.TestCase):

    def test_carregar_pdf_agrupa_por_equipamento(self):
        _, ext, mime, regs = ColetorASTTAraguaina().carregar(PDF)
        self.assertEqual(ext, ".pdf")
        self.assertEqual(mime, "application/pdf")
        # 92 faixas na fonte -> 53 equipamentos (processo + serie)
        self.assertEqual(len(regs), 53)
        r = regs[0]
        self.assertEqual(r["processo"], "ARAGU7542")
        self.assertEqual(r["serie"], "R10010")
        self.assertEqual(r["tipo"], "CEV")
        self.assertEqual(r["faixas"], ["1", "2"])
        self.assertEqual(r["regul"], "50")

    def test_seriais_reais_presentes(self):
        _, _, _, regs = ColetorASTTAraguaina().carregar(PDF)
        seriais = {r["serie"] for r in regs}
        self.assertIn("R10010", seriais)
        self.assertIn("R10340", seriais)      # so extraida pelo layout
        self.assertIn("R10342", seriais)


class TestASTTAraguainaNormalizar(unittest.TestCase):

    def test_normalizar_ponto_fixo(self):
        c = ColetorASTTAraguaina()
        _, _, _, regs = c.carregar(PDF)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "ARAGU7542")
        self.assertEqual(d["tipo_identificador"], "codigo_equipamento")
        self.assertEqual(d["uf"], "TO")
        self.assertEqual(d["municipio_nome"], "Araguaina")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "R10010")
        self.assertEqual(d["velocidade_geral"], 50.0)
        self.assertAlmostEqual(d["latitude"], -7.191751, places=6)
        self.assertAlmostEqual(d["longitude"], -48.229020, places=6)
        self.assertIn("Faixas: 1, 2", d["observacoes"])

    def test_coordenada_malformada_e_interpretada_pelo_formato_da_fonte(self):
        c = ColetorASTTAraguaina()
        _, _, _, regs = c.carregar(PDF)
        # R10341 publica "-7.158.138" / "-48.192.593": ponto de milhar no
        # lugar do decimal. E malformacao de FORMATO, nao GPS artificial --
        # a fonte usa 6 casas decimais e a coordenada e recuperada.
        alvo = [r for r in regs if r["serie"] == "R10341"]
        self.assertEqual(len(alvo), 1)
        d = c.normalizar(0, alvo[0])
        self.assertAlmostEqual(d["latitude"], -7.158138, places=6)
        self.assertAlmostEqual(d["longitude"], -48.192593, places=6)
        self.assertNotIn("Coordenada ilegivel", d["observacoes"])


class TestASTTAraguainaDescobrir(unittest.TestCase):

    def test_descobrir_recursos_offline(self):
        achados = ColetorASTTAraguaina.descobrir_recursos(HTML_PAGINA)
        self.assertTrue(achados["pdf"].endswith(
            "documentos/equipamentos_araguaina.pdf"))

    def test_resolver_url_usa_pagina_e_cai_no_fallback(self):
        with mock.patch.object(araguaiana_to.http, "baixar",
                               return_value=_resp(HTML_PAGINA)):
            url = ColetorASTTAraguaina.resolver_url()
        self.assertTrue(url.endswith("equipamentos_araguaina.pdf"))
        with mock.patch.object(araguaiana_to.http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorASTTAraguaina.resolver_url()
        self.assertEqual(url, ColetorASTTAraguaina.URL_FALLBACK)

    def test_download_passa_por_http_baixar(self):
        with open(PDF, "rb") as f:
            pdf = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(pdf)) as m:
            _, _, _, regs = ColetorASTTAraguaina().carregar(
                ColetorASTTAraguaina.URL_FALLBACK)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 53)


class TestASTTAraguainaUtil(unittest.TestCase):

    def test_coord(self):
        # decimal normal
        self.assertEqual(_coord("-7.191751"), -7.191751)
        # formas MALFORMADAS publicadas pela fonte (6 casas decimais):
        # ponto de milhar no lugar do decimal, e separador ausente
        self.assertEqual(_coord("-7.158.138"), -7.158138)
        self.assertEqual(_coord("-7158138"), -7.158138)
        self.assertEqual(_coord("-48.192.593"), -48.192593)
        self.assertEqual(_coord("-48192593"), -48.192593)
        # lixo / fora do formato publicado
        self.assertIsNone(_coord(""))
        self.assertIsNone(_coord(None))
        self.assertIsNone(_coord("abc"))
        self.assertIsNone(_coord("123456789012"))  # > 2 digitos inteiros


class TestASTTAraguainaSync(unittest.TestCase):

    def test_sincronizar_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorASTTAraguaina(db_path=config.DB_PATH)
        try:
            resumo = c.sincronizar(PDF, publicar=False)
            self.assertEqual(resumo["linhas_recebidas"], 53)
            self.assertEqual(resumo["criados"], 53)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                53)
            # todas as 53 com coordenada valida (o formato da fonte e
            # interpretado: ponto de milhar no lugar do decimal)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"),
                53)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
