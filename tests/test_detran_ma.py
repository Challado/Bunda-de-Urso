# -*- coding: utf-8 -*-
"""Testes offline do conector Detran-MA (fiscalizacao eletronica).

Sem rede: usam a fixture PDF real (lista de radares instalados) e dubles para
a descoberta de URL. Verificam o parse, a dedup de repeticoes exatas, a
normalizacao (tipo declarado pela fonte, coordenada, via/km) e a separacao em
relacao a tabela de Estudos Tecnicos (que nao vira ponto).
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.detran_ma import ColetorDetranMA
from core import config
from core import db as dbmod
import tests.common as common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "detran_ma")
LISTA_PDF = os.path.join(FIX, "fiscalizacao_eletronica.pdf")
ESTUDO_PDF = os.path.join(FIX, "estudo_tecnico_exemplo.pdf")

# Fragmento real da pagina (hrefs reais de 10/10/2026).
HTML_PAGINA = """<html><body>
<div>Para consultar a lista completa dos medidores de velocidade instalados e
em opera&ccedil;&atilde;o nas rodovias maranhenses, clique no link abaixo.</div>
<div><a href="https://sgp5.detran.ma.gov.br/uploads/midias/uf4n8qryt82xiqdp8nu5mv5i1ocvry.pdf" target="_blank">Fiscaliza&ccedil;&atilde;o Eletr&ocirc;nica</a></div>
<table align="center" border="1">
  <thead><tr><th colspan="2">Estudos T&eacute;cnicos</th></tr></thead>
  <tbody>
    <tr><td>MA 203 - KM 012 + 400 - S&Atilde;O JOS&Eacute; DE RIBAMAR - MA</td>
        <td><a href="https://uploads.detran.ma.gov.br/midias/e4rdko5vmxfkqfdh661bhky0rnvsit.pdf" target="_blank">Baixar Arquivo</a></td></tr>
    <tr><td>MA 106 - KM 116 + 158 - PINHEIRO - MA</td>
        <td><a href="https://uploads.detran.ma.gov.br/midias/5c2kawrh39m9k6pty0mh6o80ctuat9.pdf" target="_blank">Baixar Arquivo</a></td></tr>
  </tbody>
</table>
</body></html>"""


def _resp(conteudo, url="https://x/"):
    dados = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    return (dados, {}, url)


class TestDetranMACarregar(unittest.TestCase):

    def test_carregar_lista_e_dedup(self):
        _, ext, mime, regs = ColetorDetranMA().carregar(LISTA_PDF)
        self.assertEqual(ext, ".pdf")
        self.assertEqual(mime, "application/pdf")
        # o PDF repete linhas 2-3x; a dedup por conteudo deixa 54 equipamentos
        self.assertEqual(len(regs), 54)
        r = regs[0]
        self.assertEqual(r["codigo"], "MA301R")
        self.assertEqual(r["serie"], "L0533")
        self.assertEqual(r["tipo"], "FIXO")
        self.assertEqual(r["municipio"], "S. J. DE RIBAMAR")
        self.assertEqual(r["endereco"], "MA 203 - KM 012 + 400 - SÃO JOSÉ DE RIBAMAR - MA")

    def test_estudo_tecnico_nao_vira_lista(self):
        # o Levantamento Tecnico por local NAO e a lista de radares
        _, _, _, regs = ColetorDetranMA().carregar(ESTUDO_PDF)
        self.assertEqual(regs, [])


class TestDetranMANormalizar(unittest.TestCase):

    def test_normalizar_ponto_fixo(self):
        c = ColetorDetranMA()
        _, _, _, regs = c.carregar(LISTA_PDF)
        d = c.normalizar(0, regs[0])
        self.assertEqual(d["identificador"], "MA301R")
        self.assertEqual(d["tipo_identificador"], "codigo_equipamento")
        self.assertEqual(d["uf"], "MA")
        self.assertEqual(d["municipio_nome"], "S. J. DE RIBAMAR")
        self.assertEqual(d["via_codigo"], "MA-203")
        self.assertEqual(d["via_tipo"], "estadual")
        self.assertAlmostEqual(d["km"], 12.4)
        self.assertEqual(d["tipo_radar"], "fixo")     # TIPO=FIXO declarado
        self.assertEqual(d["numero_serie"], "L0533")
        self.assertEqual(d["fabricante"], "FOCALLE")
        self.assertEqual(d["modelo"], "F-LIN")
        self.assertEqual(d["velocidade_geral"], 60.0)
        self.assertAlmostEqual(d["latitude"], -2.478711, places=6)
        self.assertAlmostEqual(d["longitude"], -44.211409, places=6)
        self.assertIn("INMETRO: 00.001.002", d["observacoes"])

    def test_tipo_declarado_preserva_portatil(self):
        c = ColetorDetranMA()
        d = c.normalizar(0, {
            "codigo": "MA999R", "serie": "X1", "fabricante": "F", "modelo": "M",
            "endereco": "MA 010 - KM 001 + 000 - CIDADE - MA",
            "sentido": "NORTE/SUL", "municipio": "CIDADE", "tipo": "PORTATIL",
            "velocidade": "40", "inmetro": "1", "latitude": "-2.5",
            "longitude": "-44.3"})
        self.assertEqual(d["tipo_radar"], "portatil")

    def test_coordenada_invalida_nao_vira_gps(self):
        c = ColetorDetranMA()
        d = c.normalizar(0, {
            "codigo": "MA998R", "serie": "X", "fabricante": "F", "modelo": "M",
            "endereco": "MA 020 - KM 002 + 000 - CIDADE - MA",
            "sentido": "LESTE/OESTE", "municipio": "CIDADE", "tipo": "FIXO",
            "velocidade": "60", "inmetro": "1", "latitude": "999",
            "longitude": "-44.3"})
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])


class TestDetranMADescobrir(unittest.TestCase):

    def test_descobrir_recursos_offline(self):
        achados = ColetorDetranMA.descobrir_recursos(HTML_PAGINA)
        self.assertTrue(achados["fiscalizacao_pdf"].endswith(
            "uf4n8qryt82xiqdp8nu5mv5i1ocvry.pdf"))
        self.assertEqual(len(achados["estudos"]), 2)
        self.assertEqual(achados["estudos"][0]["local"],
                         "MA 203 - KM 012 + 400 - SÃO JOSÉ DE RIBAMAR - MA")
        self.assertTrue(achados["estudos"][0]["url"].endswith(".pdf"))

    def test_resolver_url_usa_pagina_e_cai_no_fallback(self):
        with mock.patch.object(http, "baixar",
                               return_value=_resp(HTML_PAGINA)):
            url = ColetorDetranMA.resolver_url()
        self.assertTrue(url.endswith("uf4n8qryt82xiqdp8nu5mv5i1ocvry.pdf"))
        with mock.patch.object(http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorDetranMA.resolver_url()
        self.assertEqual(url, ColetorDetranMA.URL_FALLBACK)

    def test_download_passa_por_http_baixar(self):
        with open(LISTA_PDF, "rb") as f:
            pdf = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(pdf)) as m:
            _, _, _, regs = ColetorDetranMA().carregar(
                ColetorDetranMA.URL_FALLBACK)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 54)


class TestDetranMASync(unittest.TestCase):

    def test_sincronizar_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorDetranMA(db_path=config.DB_PATH)
        try:
            resumo = c.sincronizar(LISTA_PDF, publicar=False)
            self.assertEqual(resumo["linhas_recebidas"], 54)
            self.assertEqual(resumo["criados"], 54)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                54)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"),
                54)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
