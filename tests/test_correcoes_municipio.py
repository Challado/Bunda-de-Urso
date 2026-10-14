# -*- coding: utf-8 -*-
"""Testes das correcoes de municipio (carregamento e reaplicacao idempotente)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config                          # noqa: E402
from core import correcoes_municipio as corr      # noqa: E402
from core import db as dbmod                      # noqa: E402
from tests.common import banco_memoria            # noqa: E402

CSV_VERSIONADO = os.path.join(config.ROOT, "config", "correcoes_municipio.csv")


class TestCarregarCorrecoes(unittest.TestCase):
    def test_le_csv_com_comentario_e_branco(self):
        conteudo = (
            "# comentario\n"
            "ponto_id;codigo_ibge;motivo\n"
            "\n"
            "10;3550308;malha_ibge\n"
            "# outro comentario\n"
            "11;3304557;uf_divergente_confirmada\n")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "c.csv")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)
            c = corr.carregar_correcoes(caminho)
        self.assertEqual(len(c), 2)
        self.assertEqual(c[0], {"ponto_id": "10", "codigo_ibge": "3550308",
                                "motivo": "malha_ibge"})

    def test_ignora_linhas_sem_ponto_ou_codigo(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "c.csv")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write("ponto_id;codigo_ibge;motivo\n;3550308;x\n7;;y\n")
            self.assertEqual(corr.carregar_correcoes(caminho), [])

    def test_csv_versionado_existe_e_carrega(self):
        self.assertTrue(os.path.exists(CSV_VERSIONADO),
                        "config/correcoes_municipio.csv ausente")
        c = corr.carregar_correcoes(CSV_VERSIONADO)
        self.assertGreater(len(c), 0)
        for row in c:
            self.assertTrue(row["ponto_id"].isdigit())
            self.assertTrue(row["codigo_ibge"].isdigit()
                            and len(row["codigo_ibge"]) == 7)
            self.assertIn(row["motivo"], ("malha_ibge",
                                          "uf_divergente_confirmada"))


class TestAplicarIdempotente(unittest.TestCase):
    def setUp(self):
        self.con = banco_memoria()
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3550308",
                                             "uf_sigla": "SP",
                                             "nome": "São Paulo"})
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3304557",
                                             "uf_sigla": "RJ",
                                             "nome": "Rio de Janeiro"})
        self.p1 = dbmod.insert(self.con, "PONTO_FISCALIZACAO",
                               {"municipio_id": None})
        self.p2 = dbmod.insert(self.con, "PONTO_FISCALIZACAO",
                               {"municipio_id": "3550308"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_aplica_e_reaplica_sem_mudar(self):
        correcoes = [
            {"ponto_id": str(self.p1), "codigo_ibge": "3550308",
             "motivo": "malha_ibge"},
            {"ponto_id": str(self.p2), "codigo_ibge": "3550308",
             "motivo": "uf_divergente_confirmada"},
        ]
        est1 = corr.aplicar_correcoes(self.con, correcoes)
        self.assertEqual(est1["alterados"], 1)      # só o p1 mudou
        self.assertEqual(est1["ja_corretos"], 1)    # p2 já estava certo
        mun = dbmod.scalar(self.con, "SELECT municipio_id FROM "
                           "PONTO_FISCALIZACAO WHERE id=?", (self.p1,))
        self.assertEqual(mun, "3550308")
        # reaplicar: idempotente
        est2 = corr.aplicar_correcoes(self.con, correcoes)
        self.assertEqual(est2["alterados"], 0)
        self.assertEqual(est2["ja_corretos"], 2)

    def test_dry_run_nao_grava(self):
        est = corr.aplicar_correcoes(
            self.con, [{"ponto_id": str(self.p1), "codigo_ibge": "3550308",
                        "motivo": "malha_ibge"}], dry_run=True)
        self.assertEqual(est["alterados"], 1)
        mun = dbmod.scalar(self.con, "SELECT municipio_id FROM "
                           "PONTO_FISCALIZACAO WHERE id=?", (self.p1,))
        self.assertIsNone(mun)

    def test_ponto_e_codigo_inexistentes_sao_ignorados(self):
        est = corr.aplicar_correcoes(self.con, [
            {"ponto_id": "99999", "codigo_ibge": "3550308", "motivo": "x"},
            {"ponto_id": str(self.p1), "codigo_ibge": "9999999",
             "motivo": "x"},
        ])
        self.assertEqual(est["ponto_inexistente"], 1)
        self.assertEqual(est["codigo_desconhecido"], 1)
        self.assertEqual(est["alterados"], 0)

    def test_reaplicar_atalho(self):
        caminho = os.path.join(config.ROOT, "config",
                               "correcoes_municipio.csv")
        correcoes, est = corr.reaplicar(self.con, caminho)
        self.assertEqual(len(correcoes), est["total"])


if __name__ == "__main__":
    unittest.main()
