# -*- coding: utf-8 -*-
"""Testes offline do conector SEMTRAN Porto Velho (RO).

Nenhum teste acessa a rede: usam a fixture PDF local e, quando verificam a
camada HTTP, substituem ``coletor.http.baixar`` por um duble.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.semtran_ro import ColetorSEMTRANRO, extrair_texto_pdf
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RAIZ = os.path.join(FIXTURES, "semtran_ro")


def fx(nome):
    return os.path.join(RAIZ, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestSEMTRANRO(unittest.TestCase):

    def test_extrator_cmap_reconstroi_texto(self):
        with open(fx("radares_fixos_porto_velho_2026_1.pdf"), "rb") as f:
            celulas = extrair_texto_pdf(f.read())
        self.assertIn("NUMERO_SERIE", celulas)
        self.assertIn("FSC110", celulas)
        self.assertIn("Rua Raimundo Cantuária x Rua Buenos Aires", celulas)

    def test_carregar_pdf_fixture(self):
        c = ColetorSEMTRANRO()
        _, ext, mime, regs = c.carregar(
            fx("radares_fixos_porto_velho_2026_1.pdf"))
        self.assertEqual(ext, ".pdf")
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(len(regs), 85)
        r = regs[0]
        self.assertEqual(r["TIPO"], "FSC110")
        self.assertEqual(r["NUMERO_SERIE"], "448")
        self.assertEqual(r["NOME_PISTA"],
                         "Rua Raimundo Cantuária x Rua Buenos Aires")

    def test_ids_sequenciais(self):
        c = ColetorSEMTRANRO()
        _, _, _, regs = c.carregar(
            fx("radares_fixos_porto_velho_2026_1.pdf"))
        ids = [int(r["ID"]) for r in regs]
        self.assertEqual(ids, list(range(1, 86)))

    def test_coordenada_publicada_fora_de_faixa_vira_nulo(self):
        c = ColetorSEMTRANRO()
        _, _, _, regs = c.carregar(
            fx("radares_fixos_porto_velho_2026_1.pdf"))
        d = c.normalizar(0, regs[0])
        # a fonte publica POSICAO fora de faixa: NAO vira GPS
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertIn("-876.651.999.999.999.000", d["observacoes"])
        self.assertEqual(d["uf"], "RO")
        self.assertEqual(d["municipio_nome"], "Porto Velho")
        self.assertEqual(d["tipo_radar"], "fixo")
        self.assertEqual(d["numero_serie"], "448")

    def test_coordenada_valida_seria_aceita(self):
        c = ColetorSEMTRANRO()
        raw = {"POSICAO_LAT": "-8,7619", "POSICAO_LON": "-63,9039",
               "NUMERO_SERIE": "1"}
        d = c.normalizar(0, raw)
        self.assertAlmostEqual(d["latitude"], -8.7619)
        self.assertAlmostEqual(d["longitude"], -63.9039)

    def test_descobrir_url_arquivo_prefere_dados_atualizados(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        url = ColetorSEMTRANRO.descobrir_url_arquivo(html)
        self.assertIn("Dados", url)
        self.assertIn("atualizados", url)

    def test_descobrir_url_fallback_sem_pdf(self):
        url = ColetorSEMTRANRO.descobrir_url_arquivo("<html>nada</html>")
        self.assertEqual(url, ColetorSEMTRANRO.URL_FALLBACK)

    def test_resolver_url_usa_http_baixar(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            url = ColetorSEMTRANRO.resolver_url()
        self.assertTrue(m.called)
        self.assertIn("Dados", url)

    def test_carregar_remoto_descobre_e_baixa_pdf(self):
        with open(fx("pagina_fixture.html"), "rb") as f:
            html = f.read()
        with open(fx("radares_fixos_porto_velho_2026_1.pdf"), "rb") as f:
            pdf = f.read()

        chamadas = []

        def fake_baixar(url, *a, **k):
            chamadas.append(url)
            if url.endswith(".pdf"):
                return _resp(pdf, url)
            return _resp(html, url)

        with mock.patch.object(http, "baixar", side_effect=fake_baixar):
            _, _, _, regs = ColetorSEMTRANRO().carregar(
                ColetorSEMTRANRO.PAGINA)
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(len(regs), 85)

    def test_sincronizar_offline_grava_pontos_sem_posicao(self):
        common.ambiente_temporario()
        c = ColetorSEMTRANRO(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(
                fx("radares_fixos_porto_velho_2026_1.pdf"))
            self.assertEqual(res["linhas_recebidas"], 85)
            self.assertEqual(res["criados"], 85)
            self.assertEqual(res["rejeitados"], 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                85)
            # coordenada fora de faixa -> nenhuma POSICAO_GEOGRAFICA
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA"), 0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
