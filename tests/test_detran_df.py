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
import json
import subprocess
import unittest
from unittest import mock

from coletor import http, politica_http
from coletor.fontes import detran_df
from coletor.fontes.detran_df import ColetorDetranDF
from core import caminhos, config
from core import db as dbmod
import tests.common as common

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "detran_df")
JS = os.path.join(FIX, "equipamentos.js")

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

    def test_origem_padrao_e_pagina_direta(self):
        with mock.patch.object(detran_df.http, "baixar") as baixar:
            url = ColetorDetranDF.resolver_url()
        self.assertEqual(url, ColetorDetranDF.RECURSO["url_recurso"])
        self.assertTrue(url.endswith("/lista_equipto/index.html"))
        baixar.assert_not_called()

    def test_pagina_oficial_descobre_o_arquivo_de_dados(self):
        lista = ColetorDetranDF.resolver_url()
        dados = lista.replace("index.html", "equipamentos-atual.json")
        html = ('<script src="https://terceiro.example/equipamentos.js"></script>'
                '<script src="./equipamentos-atual.json"></script>')
        arquivo = '[{"identificacao":"A007","tipo":"DETRAN - RADAR"}]'
        with mock.patch.object(detran_df.http, "baixar",
                               side_effect=[_resp(html, lista), _resp(arquivo, dados)]) as baixar:
            _, ext, mime, regs = ColetorDetranDF().carregar(lista)
        self.assertEqual([c.args[0] for c in baixar.call_args_list], [lista, dados])
        self.assertEqual((ext, mime, regs[0]["identificacao"]), (".json", "application/json", "A007"))

    def test_pagina_com_cadastro_embutido_e_lida_sem_buscar_js(self):
        lista = ColetorDetranDF.resolver_url()
        pagina = ('<html><script>const idiomas = ["pt-BR"];'
                  'const equipamentos = [{"identificacao":"A007","tipo":"DETRAN - RADAR"}];'
                  '</script></html>')
        with mock.patch.object(detran_df.http, "baixar", return_value=_resp(pagina, lista)) as baixar:
            _, ext, mime, regs = ColetorDetranDF().carregar(None)
        baixar.assert_called_once_with(lista)
        self.assertEqual((ext, mime, regs[0]["identificacao"]), (".html", "text/html", "A007"))

    def test_bloqueio_com_200_nao_publica_lista_falsa(self):
        lista = ColetorDetranDF.resolver_url()
        negado = '<html><title>Request Rejected</title><script>var erros = [{"erro":1}]</script></html>'
        with mock.patch.object(detran_df.http, "baixar", return_value=_resp(negado, lista)), \
                mock.patch.object(detran_df, "_achar_navegador", return_value=None):
            with self.assertRaisesRegex(http.ErroFonte, "Request Rejected"):
                ColetorDetranDF().carregar(lista)


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

    def test_regra_da_url_configura_timeout_e_user_agent_no_chromium(self):
        url = ColetorDetranDF.URL_DADOS_FALLBACK
        regras = json.dumps([{"fonte": "detran_df", "url": url, "timeout": 150, "user_agent": "RadarLab/2.0"}])
        resultado = subprocess.CompletedProcess([], 0, b"<html></html>", b"")
        with (mock.patch.object(caminhos, "valor", return_value=(regras, "teste")),
              mock.patch.object(detran_df.subprocess, "run", return_value=resultado) as rodar,
              politica_http.fonte("detran_df")):
            self.assertEqual(detran_df._dump_dom("chromium", url, "/perfil"), "<html></html>")
        self.assertEqual(rodar.call_args.kwargs["timeout"], 150)
        self.assertIn("--user-agent=RadarLab/2.0", rodar.call_args.args[0])


class TestDetranDFSync(unittest.TestCase):

    def test_atualiza_url_antiga_no_mesmo_recurso(self):
        common.ambiente_temporario()
        c = ColetorDetranDF(db_path=config.DB_PATH)
        try:
            dbmod.init_db(c.conn)
            chave = c.garantir_referencias()
            c.conn.execute("UPDATE RECURSO_FONTE SET url_recurso=? WHERE id=?", (c.URL_PAGINA, chave[1]))
            c.conn.commit()
            self.assertEqual(c.garantir_referencias(), chave)
            self.assertEqual(dbmod.scalar(c.conn,
                "SELECT url_recurso FROM RECURSO_FONTE WHERE id=?", (chave[1],)), c.resolver_url())
        finally:
            c.conn.close()

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
