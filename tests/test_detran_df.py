# -*- coding: utf-8 -*-
"""Testes offline do conector Detran-DF (equipamentos eletronicos).

Sem rede: usam a fixture real de ``equipamentos.js`` (lista completa de
10/10/2026, 407 registros) e dubles para a descoberta de URL / download.

O arquivo de dados real e servido a navegadores; um WAF F5/BigIP reseta a
conexao de clientes nao-navegador.  Por isso o modulo TENTA primeiro
``coletor.http.baixar`` e, se o WAF resetar, cai no CONTORNO de navegador
(Chromium headless em 2 passos).  Estes testes cobrem os dois caminhos com
dubles (sem subir navegador).
"""
import os
import subprocess
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


def _pre(texto):
    return "<html><body><pre style=\"white-space: pre-wrap;\">%s</pre></body></html>" % texto


class TestDetranDFCarregar(unittest.TestCase):

    def test_carregar_fixture(self):
        _, ext, mime, regs = ColetorDetranDF().carregar(JS)
        self.assertEqual(ext, ".js")
        self.assertEqual(mime, "application/javascript")
        self.assertEqual(len(regs), 407)              # lista completa real
        por_id = {r["identificacao"]: r for r in regs}
        self.assertEqual(por_id["FIS001"]["tipo"], "AVANÇO DE SINAL VERMELHO")
        self.assertEqual(por_id["KR007"]["numero_serie"], "516301114, 516301204")
        self.assertEqual(por_id["RE001"]["numero_serie"], "R13195/R13188")

    def test_tipos_presentes(self):
        _, _, _, regs = ColetorDetranDF().carregar(JS)
        tipos = {r["tipo"] for r in regs}
        self.assertEqual(tipos, {"AVANÇO DE SINAL VERMELHO", "DETRAN - RADAR",
                                 "DETRAN - LOMBADA ELETRÔNICA"})


class TestDetranDFNormalizar(unittest.TestCase):

    def _por_id(self):
        regs = ColetorDetranDF().carregar(JS)[3]
        return {r["identificacao"]: r for r in regs}

    def test_radar_vira_fixo_sem_coordenada(self):
        c = ColetorDetranDF()
        d = c.normalizar(0, self._por_id()["KR007"])
        self.assertEqual(d["identificador"], "KR007")
        self.assertEqual(d["uf"], "DF")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "516301114, 516301204")
        self.assertIsNone(d["latitude"])       # a lista nao traz coordenadas
        self.assertIsNone(d["longitude"])
        self.assertIn("Local:", d["observacoes"])

    def test_lombada_vira_fixo(self):
        c = ColetorDetranDF()
        d = c.normalizar(0, self._por_id()["RE001"])
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "R13195/R13188")

    def test_avanco_de_sinal_nao_e_radar(self):
        c = ColetorDetranDF()
        d = c.normalizar(0, self._por_id()["FIS001"])
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


class TestDetranDFContornoWaf(unittest.TestCase):
    """Contorno do WAF F5: 2 passos (index.html -> equipamentos.js)."""

    def test_waf_resetado_cai_no_navegador(self):
        with open(JS, encoding="utf-8") as fh:
            texto_js = fh.read()
        chamadas = []

        def _fake_dump(navegador, url, perfil, timeout=90):
            chamadas.append(url)
            return _pre(texto_js) if url.endswith(".js") else _pre("<html></html>")

        with mock.patch.object(detran_df.http, "baixar",
                               side_effect=http.ErroFonte("reset pelo WAF")), \
                mock.patch.object(detran_df, "_achar_navegador",
                                  return_value="/usr/bin/chromium"), \
                mock.patch.object(detran_df, "_dump_dom", side_effect=_fake_dump):
            _, _, _, regs = ColetorDetranDF().carregar(
                ColetorDetranDF.URL_DADOS_FALLBACK)
        self.assertEqual(len(regs), 407)
        # passo 1 no index.html, passo 2 no equipamentos.js, mesmo perfil
        self.assertEqual(len(chamadas), 2)
        self.assertTrue(chamadas[0].endswith("lista_equipto/index.html"))
        self.assertTrue(chamadas[1].endswith("lista_equipto/equipamentos.js"))

    def test_sem_navegador_o_erro_sobe(self):
        with mock.patch.object(detran_df.http, "baixar",
                               side_effect=http.ErroFonte("reset pelo WAF")), \
                mock.patch.object(detran_df, "_achar_navegador",
                                  return_value=None):
            with self.assertRaises(http.ErroFonte):
                ColetorDetranDF().carregar(ColetorDetranDF.URL_DADOS_FALLBACK)

    def test_http_200_com_html_em_vez_da_lista_tenta_navegador(self):
        with open(JS, encoding='utf-8') as arquivo:
            texto = arquivo.read()
        with mock.patch.object(http, 'baixar', return_value=_resp('<html>Erro</html>')), \
             mock.patch.object(ColetorDetranDF, '_texto_via_navegador', return_value=texto) as navegador:
            self.assertEqual(len(ColetorDetranDF().carregar(ColetorDetranDF.URL_DADOS_FALLBACK)[3]), 407)
        navegador.assert_called_once()

    def test_bloqueio_do_navegador_com_nome_do_arquivo_nao_passa_por_lista(self):
        bloqueio = '<html><title>Request Rejected</title><body>equipamentos.js</body></html>'
        with mock.patch.object(detran_df, '_achar_navegador', return_value='/usr/bin/chromium'), \
             mock.patch.object(detran_df, '_dump_dom', return_value=bloqueio):
            with self.assertRaisesRegex(http.ErroFonte, 'Request Rejected'):
                ColetorDetranDF._texto_via_navegador(ColetorDetranDF.URL_DADOS_FALLBACK)

    def test_erro_do_navegador_preserva_as_duas_causas(self):
        with mock.patch.object(http, 'baixar', side_effect=http.ErroFonte('HTTP 503')), \
             mock.patch.object(ColetorDetranDF, '_texto_via_navegador', side_effect=http.ErroFonte('codigo 1: sem permissao')):
            with self.assertRaisesRegex(http.ErroFonte, 'HTTP 503.*codigo 1: sem permissao'):
                ColetorDetranDF().carregar(ColetorDetranDF.URL_DADOS_FALLBACK)

    def test_falha_do_processo_chromium_informa_codigo_e_stderr(self):
        resultado = subprocess.CompletedProcess([], 1, b'', b'Permission denied')
        with mock.patch.object(detran_df.subprocess, 'run', return_value=resultado):
            with self.assertRaisesRegex(http.ErroFonte, 'codigo 1.*Permission denied'):
                detran_df._dump_dom('chromium', ColetorDetranDF.URL_DADOS_FALLBACK, '/perfil')

    def test_timeout_do_chromium_e_registrado_com_a_url(self):
        with mock.patch.object(detran_df.subprocess, 'run', side_effect=subprocess.TimeoutExpired('chromium', 90)):
            with self.assertRaisesRegex(http.ErroFonte, 'excedeu 90 segundos.*equipamentos.js'):
                detran_df._dump_dom('chromium', ColetorDetranDF.URL_DADOS_FALLBACK, '/perfil')


class TestDetranDFSync(unittest.TestCase):

    def test_sincronizar_fixture_em_banco_temporario(self):
        common.ambiente_temporario()
        c = ColetorDetranDF(db_path=config.DB_PATH)
        try:
            resumo = c.sincronizar(JS, publicar=False)
            self.assertEqual(resumo["linhas_recebidas"], 407)
            self.assertEqual(resumo["criados"], 407)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                407)
            # sem coordenadas -> nenhuma posicao geografica
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"),
                0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
