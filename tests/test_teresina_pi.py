# -*- coding: utf-8 -*-
"""Testes offline do mapa da STRANS e da publicação histórica de 2019.

Nenhum teste acessa a rede: usam a fixture HTML local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.teresina_pi import ColetorTeresinaHistorico, ColetorTeresinaPI
from core import config
from core import db as dbmod
from core import governanca
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "teresina_pi")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestTeresinaHistorico(unittest.TestCase):

    def test_evidencia_declara_data_e_tipos(self):
        c = ColetorTeresinaHistorico()
        _, ext, mime, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["data_publicacao"], "2019-04-10")
        self.assertEqual(r["tipos_radares_citados"], ["estatico", "fixo"])
        self.assertTrue(r["anuncia_divulgacao_mensal"])
        self.assertTrue(r["aponta_aba_localizacao_radares"])
        self.assertFalse(r["publica_lista_na_pagina"])
        self.assertFalse(r["tem_dataset_estruturado"])
        self.assertEqual(r["motivo"], "pendente_lai")

    def test_noticia_historica_nao_vira_radar(self):
        c = ColetorTeresinaHistorico()
        _, _, _, regs = c.carregar(fx("pagina_fixture.html"))
        self.assertIsNone(c.normalizar(0, regs[0]))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorTeresinaHistorico.resolver_url()
        self.assertEqual(url, ColetorTeresinaHistorico.PAGINA)
        self.assertIn("pmt.pi.gov.br", url)

    def test_carregar_remoto_passa_por_http_baixar(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorTeresinaHistorico().carregar(
                ColetorTeresinaHistorico.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 1)

    def test_sincronizar_offline_nao_cria_pontos(self):
        common.ambiente_temporario()
        c = ColetorTeresinaHistorico(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("pagina_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 1)
            self.assertEqual(res["criados"], 0)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(res["status"], "documentado")
            self.assertEqual(res["evidencias_documentais"], res["linhas_recebidas"])
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 1)
        finally:
            c.conn.close()


class TestTeresinaPI(unittest.TestCase):
    def test_descobre_mapa_na_publicacao_municipal(self):
        c = ColetorTeresinaPI()
        pagina = '<iframe src="https://www.google.com/maps/d/embed?mid=Teste-STRANS-2026&amp;ehbc=2E312F"></iframe>'
        url = "https://www.google.com/maps/d/kml?mid=Teste-STRANS-2026&forcekml=1"
        with open(fx("mapa_fixture.kml"), "rb") as arquivo:
            conteudo = arquivo.read()
        with mock.patch.object(http, "baixar", side_effect=[
                _resp(pagina, c.PAGINA), _resp(conteudo, url)]) as baixar:
            _, ext, mime, registros = c.carregar(None)
        self.assertEqual(baixar.call_args_list, [mock.call(c.PAGINA), mock.call(url)])
        self.assertEqual(ext, ".kml")
        self.assertIn("kml", mime)
        self.assertEqual(len(registros), 3)
        t1001, furtado, ocr = [c.normalizar(i, r) for i, r in enumerate(registros)]
        self.assertEqual((t1001["latitude"], t1001["longitude"]), (-5.093872, -42.765953))
        self.assertEqual(t1001["municipio_ibge"], "2211001")
        self.assertIn("OESTE - LESTE", t1001["sentido_original"])
        self.assertEqual(furtado["situacao"], "inativo")
        self.assertIn("EQUIPAMENTO FURTADO", furtado["observacoes"])
        self.assertIsNone(t1001.get("velocidade_geral"))
        self.assertIsNone(ocr.get("tipo_medicao"))

    def test_recusa_mapa_de_outro_dominio_e_kml_sem_marcacoes(self):
        with self.assertRaisesRegex(http.ErroFonte, "não publicou o mapa"):
            ColetorTeresinaPI._url_kml(
                b'<iframe src="https://example.org/maps/d/embed?mid=Teste-STRANS-2026"></iframe>')
        with self.assertRaisesRegex(http.ErroFonte, "não trouxe marcações"):
            ColetorTeresinaPI._registros(
                b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>STRANS</name></Document></kml>')

    def test_migra_leitor_sem_perder_historico_e_publica_mapa(self):
        common.ambiente_temporario()
        antigo = ColetorTeresinaHistorico(db_path=config.DB_PATH)
        conn = antigo.conn
        try:
            historico = antigo.sincronizar(fx("pagina_fixture.html"))
            governanca.garantir_esquema(conn)
            novo = ColetorTeresinaPI(conn=conn)
            resultado = novo.sincronizar(fx("mapa_fixture.kml"))
            self.assertEqual(resultado["recurso_id"], historico["recurso_id"])
            self.assertEqual(resultado["status"], "ok")
            self.assertEqual((resultado["criados"], resultado["rejeitados"]), (3, 0))
            self.assertEqual(dbmod.scalar(conn, "SELECT COUNT(*) FROM FONTE"), 1)
            self.assertEqual(dbmod.scalar(conn, "SELECT COUNT(*) FROM EXECUCAO_COLETA"), 2)
            self.assertTrue(novo.sincronizar(fx("mapa_fixture.kml"))["sem_mudanca"])
            self.assertEqual(dbmod.scalar(conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 3)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
