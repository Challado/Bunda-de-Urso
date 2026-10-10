# -*- coding: utf-8 -*-
"""Testes offline do conector Detran-DF (equipamentos eletronicos).

Sem rede: usam a fixture real de ``equipamentos.js`` (subconjunto real de
10/10/2026) e dubles para a descoberta de URL / download.

ATENCAO: o modulo e PARCIAL.  O arquivo de dados real e servido a navegadores,
mas um WAF F5/BigIP reseta a conexao de clientes nao-navegador (ver o
docstring do modulo).  Por isso o teste de download confirma que o erro de rede
e PROPAGADO (sem fallback silencioso), alem de validar descobrimento/parse.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes import detran_df
from coletor.fontes.detran_df import ColetorDetranDF
from core import config
from core import db as dbmod
import tests.common as common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "detran_df")
JS = os.path.join(FIX, "equipamentos.js")

# Fragmento real da pagina institucional (href real de 10/10/2026).
HTML_PAGINA = """<html><body>
<p>O link abaixo atende o art. 6o, par. 3o, inciso I, da Resolucao CONTRAN
n. 798/2020. Relacao de todos os medidores de velocidade existentes
DETRAN-DF: <a href="https://geoservicos.detran.df.gov.br/geoserver/styles/lista_equipto/index.html" target="_blank">https://geoservicos.detran.df.gov.br</a></p>
</body></html>"""


def _resp(conteudo, url="https://x/"):
    dados = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    return (dados, {}, url)


class TestDetranDFCarregar(unittest.TestCase):

    def test_carregar_fixture(self):
        _, ext, mime, regs = ColetorDetranDF().carregar(JS)
        self.assertEqual(ext, ".js")
        self.assertEqual(mime, "application/javascript")
        self.assertEqual(len(regs), 10)
        self.assertEqual(regs[0]["identificacao"], "FIS001")
        self.assertEqual(regs[3]["identificacao"], "KR007")
        self.assertEqual(regs[6]["identificacao"], "RE001")

    def test_tipos_presentes(self):
        _, _, _, regs = ColetorDetranDF().carregar(JS)
        tipos = {r["tipo"] for r in regs}
        self.assertEqual(tipos, {"AVANÇO DE SINAL VERMELHO", "DETRAN - RADAR",
                                 "DETRAN - LOMBADA ELETRÔNICA"})


class TestDetranDFNormalizar(unittest.TestCase):

    def _regs(self):
        return ColetorDetranDF().carregar(JS)[3]

    def test_radar_vira_fixo_sem_coordenada(self):
        c = ColetorDetranDF()
        regs = self._regs()
        radar = [r for r in regs if r["identificacao"] == "KR007"][0]
        d = c.normalizar(0, radar)
        self.assertEqual(d["identificador"], "KR007")
        self.assertEqual(d["uf"], "DF")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "516301114, 516301204")
        self.assertIsNone(d["latitude"])       # a lista nao traz coordenadas
        self.assertIsNone(d["longitude"])
        self.assertIn("Local:", d["observacoes"])

    def test_lombada_vira_fixo(self):
        c = ColetorDetranDF()
        regs = self._regs()
        lomb = [r for r in regs if r["identificacao"] == "RE001"][0]
        d = c.normalizar(0, lomb)
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "R13195/R13188")

    def test_avanco_de_sinal_nao_e_radar(self):
        c = ColetorDetranDF()
        d = c.normalizar(0, self._regs()[0])   # FIS001
        self.assertIsNone(d["tipo_radar"])
        self.assertIn("Nao e medidor de velocidade", d["observacoes"])


class TestDetranDFDescobrir(unittest.TestCase):

    def test_descobrir_recursos_offline(self):
        achados = ColetorDetranDF.descobrir_recursos(HTML_PAGINA)
        self.assertIn("lista", achados)
        self.assertTrue(achados["lista"].endswith("lista_equipto/index.html"))

    def test_url_dados(self):
        url = ColetorDetranDF._url_dados(
            "https://geoservicos.detran.df.gov.br/geoserver/styles/"
            "lista_equipto/index.html")
        self.assertTrue(url.endswith("lista_equipto/equipamentos.js"))

    def test_resolver_url_usa_pagina_e_cai_no_fallback(self):
        with mock.patch.object(detran_df.http, "baixar",
                               return_value=_resp(HTML_PAGINA)):
            url = ColetorDetranDF.resolver_url()
        self.assertTrue(url.endswith("lista_equipto/equipamentos.js"))
        with mock.patch.object(detran_df.http, "baixar",
                               side_effect=http.ErroFonte("fora")):
            url = ColetorDetranDF.resolver_url()
        self.assertEqual(url, ColetorDetranDF.URL_DADOS_FALLBACK)

    def test_erro_de_waf_e_propagado(self):
        # cliente nao-navegador: o WAF reseta a conexao -> erro sobe
        with mock.patch.object(http, "baixar",
                               side_effect=http.ErroFonte("reset")):
            with self.assertRaises(http.ErroFonte):
                ColetorDetranDF().carregar(ColetorDetranDF.URL_DADOS_FALLBACK)


class TestDetranDFSync(unittest.TestCase):

    def test_sincronizar_fixture_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorDetranDF(db_path=config.DB_PATH)
        try:
            resumo = c.sincronizar(JS, publicar=False)
            self.assertEqual(resumo["linhas_recebidas"], 10)
            self.assertEqual(resumo["criados"], 10)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                10)
            # sem coordenadas -> nenhuma posicao geografica
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"),
                0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
