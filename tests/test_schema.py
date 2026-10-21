# -*- coding: utf-8 -*-
"""O schema carrega no SQLite e faz valer FK/CHECK/UNIQUE/NOT NULL."""
import sqlite3
import unittest

from core import db as dbmod
from tests.common import banco_memoria


class TestSchema(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()

    def tearDown(self):
        self.con.close()

    def test_todas_as_tabelas_t01_t77(self):
        nomes = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")}
        for nome in ("UF", "MUNICIPIO", "PONTO_FISCALIZACAO",
                     "POSICAO_GEOGRAFICA", "EQUIPAMENTO", "FONTE",
                     "ARTEFATO_COLETA", "REGISTRO_FONTE", "NATUREZA_FONTE",
                     "RECURSO_LICENCA"):
            self.assertIn(nome, nomes)
        self.assertEqual(len(nomes), 78)

    def test_uf_check_sigla(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO UF (sigla, nome) VALUES ('XX', 'X')")

    def test_uf_unique_nome(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO UF (sigla, nome) VALUES ('ZZ', 'Acre')")

    def test_fk_com_prcatica(self):
        self.assertEqual(
            self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_fk_municipio_uf_inexistente(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO MUNICIPIO (codigo_ibge, uf_sigla, nome) "
                "VALUES ('9999999', 'QQ', 'Nenhum')")

    def test_fk_valida_ok(self):
        self.con.execute(
            "INSERT INTO MUNICIPIO (codigo_ibge, uf_sigla, nome) "
            "VALUES ('4104808', 'PR', 'Cascavel')")
        n = self.con.execute("SELECT count(*) FROM MUNICIPIO").fetchone()[0]
        self.assertEqual(n, 1)

    def test_check_latitude_fora(self):
        q = dbmod.domain_id(self.con, "QUALIDADE_POSICAO", "oficial")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO POSICAO_GEOGRAFICA (latitude, longitude, "
                "qualidade_posicao_id) VALUES (200, 0, ?)", (q,))

    def test_check_velocidade_limite(self):
        # exatamente um entre ponto_id/faixa_id + faixa de velocidade
        cat = dbmod.domain_id(self.con, "CATEGORIA_VEICULO", "leves")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO LIMITE_VELOCIDADE (ponto_id, faixa_id, "
                "categoria_veiculo_id, velocidade_kmh) VALUES (1, 1, ?, 100)",
                (cat,))

    def test_not_null_codigo_dominio(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO TIPO_RADAR (codigo, descricao) "
                             "VALUES (NULL, 'x')")

    def test_unique_codigo_dominio(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO TIPO_RADAR (codigo, descricao) "
                             "VALUES ('fixo', 'duplicado')")

    def test_delete_referenciado_restrito(self):
        q = dbmod.domain_id(self.con, "QUALIDADE_POSICAO", "oficial")
        pid = self.con.execute(
            "INSERT INTO POSICAO_GEOGRAFICA (latitude, longitude, "
            "qualidade_posicao_id) VALUES (-24.0, -53.0, ?)",
            (q,)).lastrowid
        self.con.execute(
            "INSERT INTO PONTO_FISCALIZACAO (posicao_id) VALUES (?)", (pid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM POSICAO_GEOGRAFICA WHERE id=?", (pid,))


if __name__ == "__main__":
    unittest.main()
