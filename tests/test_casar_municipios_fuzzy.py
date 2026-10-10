# -*- coding: utf-8 -*-
"""Casamento aproximado de municipio (fuzzy + fonetico).

Casos deterministicos, sobre um banco em memoria com uma lista MINIMA de
municipios: os casos reais que motivaram o utilitario (Poxoreu, Sao Luiz do
Paraitinga, Cariri do Tocantins) casam; nomes realmente diferentes NAO casam;
ambiguidade e qualificador-omitido ficam NULL (nada inventado).
"""
import os
import sqlite3
import tempfile
import unittest

from core import db as dbmod
from tests.common import banco_memoria
from tools import casar_municipios_fuzzy as fz


def _mun(con, codigo, uf, nome):
    dbmod.insert(con, "MUNICIPIO", {"codigo_ibge": codigo, "uf_sigla": uf,
                                    "nome": nome})


class TestNormalizacao(unittest.TestCase):

    def test_sem_acento_maiuscula_e_pontuacao(self):
        self.assertEqual(fz.normalizar("São Luiz do Paraitinga"),
                         "SAO LUIZ PARAITINGA")
        self.assertEqual(fz.normalizar("Mogi-Guaçu"), "MOGI GUACU")
        self.assertEqual(fz.normalizar("Olhos D'Água"), "OLHOS D AGUA")

    def test_conectivos_removidos(self):
        self.assertEqual(fz.normalizar("Cariri de Tocantins"),
                         "CARIRI TOCANTINS")
        self.assertEqual(fz.normalizar("Entre-Ijuís"), "ENTRE IJUIS")

    def test_chave_fonetica_colapsa_equivalentes(self):
        # Poxoreu/Poxoreo (X~S, vogais fora) caem na mesma chave.
        self.assertEqual(fz.chave_fonetica("Poxoréu"),
                         fz.chave_fonetica("POXOREO"))
        # S/Z equivalentes: Sao Luiz x Sao Luis.
        self.assertEqual(fz.chave_fonetica("São Luiz"),
                         fz.chave_fonetica("SAO LUIS"))

    def test_chave_fonetica_distingue_nomes_diferentes(self):
        self.assertNotEqual(fz.chave_fonetica("Poxoréu"),
                            fz.chave_fonetica("Cuiabá"))


class TestResolver(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()
        _mun(self.con, "5107008", "MT", "Poxoréu")
        _mun(self.con, "3550001", "SP", "São Luiz do Paraitinga")
        _mun(self.con, "1703867", "TO", "Cariri do Tocantins")
        _mun(self.con, "2804607", "SE", "Nossa Senhora das Dores")
        _mun(self.con, "1400100", "RR", "Boa Vista")
        _mun(self.con, "2502151", "PB", "Boa Vista")
        _mun(self.con, "1300680", "AM", "Boa Vista do Ramos")
        _mun(self.con, "5300108", "DF", "Brasília")
        _mun(self.con, "4115804", "PR", "Tunas do Paraná")
        self.con.commit()
        self.ind = fz.Indice.do_banco(self.con)

    def tearDown(self):
        self.con.close()

    def test_poxoreu_casa_na_uf(self):
        d = fz.resolver(self.ind, "POXOREO", "MT")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "5107008")
        self.assertEqual(d["escopo"], "uf")

    def test_sao_luiz_do_paraitinga_casa(self):
        d = fz.resolver(self.ind, "SAO LUIS DO PARAITINGA", "SP")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "3550001")

    def test_cariri_do_tocantins_casa(self):
        d = fz.resolver(self.ind, "CARIRI DE TOCANTINS", "TO")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "1703867")

    def test_nossa_sra_das_dores_abreviado_casa(self):
        d = fz.resolver(self.ind, "Nossa Sra. das Dores", "SE")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "2804607")

    def test_nome_realmente_diferente_nao_casa(self):
        d = fz.resolver(self.ind, "Cidade Fantasma", "SP")
        self.assertFalse(d["preenche"])
        self.assertIsNone(d["codigo"])

    def test_sem_nome_nao_casa(self):
        self.assertIsNone(fz.resolver(self.ind, "", "SP"))
        self.assertIsNone(fz.resolver(self.ind, None, "SP"))

    def test_uf_do_payload_prevalece_sobre_nacional(self):
        # 'Boa Vista' existe em RR e PB; com UF=RR, casa RR.
        d = fz.resolver(self.ind, "BOA VISTA", "RR")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "1400100")
        self.assertEqual(d["escopo"], "uf")

    def test_homonimo_sem_uf_fica_null(self):
        # fora de RR/PB/AM, 'Boa Vista' empata -> nao inventa
        d = fz.resolver(self.ind, "BOA VISTA", "GO")
        self.assertFalse(d["preenche"])
        self.assertEqual(d["motivo"], "ambiguo")

    def test_qualificador_omitido_na_uf_nao_cruza_uf(self):
        # 'TUNAS' so existe em PR como 'Tunas do Paraná' -> nao arrisca RS.
        d = fz.resolver(self.ind, "TUNAS", "PR")
        self.assertFalse(d["preenche"])
        self.assertEqual(d["motivo"], "qualificador_na_uf")
        self.assertEqual(d["cand_uf"], "PR")

    def test_uf_divergente_unico_preenche(self):
        # 'BRASILIA' nao existe em GO e e unica nacionalmente -> DF.
        d = fz.resolver(self.ind, "BRASILIA", "GO")
        self.assertTrue(d["preenche"])
        self.assertEqual(d["codigo"], "5300108")
        self.assertEqual(d["motivo"], "uf_divergente")


class TestEscrita(unittest.TestCase):

    def test_csv_dedup_e_cabecalho(self):
        tmp = tempfile.mkdtemp(prefix="radar-fz-")
        caminho = os.path.join(tmp, "duvidosos.csv")
        duvidosos = [("POXOREO", "MT", "Poxoréu", "MT", 0.9, "ambiguo"),
                     ("POXOREO", "MT", "Poxoréu", "MT", 0.9, "ambiguo"),
                     ("X", "SP", "Y", "SP", 0.8, "abaixo_do_limiar")]
        cam, n = fz.escrever_csv(caminho, duvidosos)
        self.assertEqual(n, 2)                       # dedup por decisao
        with open(cam, encoding="utf-8") as f:
            linhas = f.read().splitlines()
        self.assertEqual(linhas[0].split(";"),
                         ["nome_fonte", "uf_fonte", "melhor_candidato",
                          "uf_candidato", "score", "motivo"])
        self.assertEqual(len(linhas), 3)             # cabecalho + 2

    def test_processar_sem_pontos_nao_quebra(self):
        con = banco_memoria()
        try:
            _mun(con, "3550308", "SP", "São Paulo")
            res = fz.processar(con, aplicar=False)
            self.assertEqual(res["total"], 0)
            self.assertEqual(res["preenchidos"], 0)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
