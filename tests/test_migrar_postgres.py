"""Importação transacional contra um servidor PostgreSQL real de testes."""

from contextlib import closing
from decimal import Decimal
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from core import db, governanca
from core.manutencao.migrar_postgres import ErroMigracao, importar, preparar_origem


@unittest.skipUnless(os.environ.get("RADAR_TESTE_POSTGRES"), "Requer PostgreSQL de testes.")
class MigrarPostgresTest(unittest.TestCase):
    def setUp(self):
        from psycopg import sql

        self.sql = sql
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.origem = Path(temp.name) / "origem.sqlite3"
        self.copia = Path(temp.name) / "copia.sqlite3"
        self.esquema = "radar_teste_" + uuid4().hex
        self.pg = db.connect_postgres(conninfo=os.environ["RADAR_TESTE_POSTGRES"], autocommit=True)
        self.addCleanup(self.pg.close)
        self.addCleanup(self.pg.execute, sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE")
                        .format(sql.Identifier(self.esquema)))

        with closing(db.connect(self.origem)) as c:
            governanca.garantir_esquema(c)
            c.execute("INSERT INTO traseiro_local(singleton, uuid, criado_em) VALUES (1, 'local', '2026-11-19')")
            c.execute("INSERT INTO ponto_fiscalizacao(id, km, observacoes) VALUES (?, ?, ?)",
                      (3000000000, 1.23456789, "Radar ç\nsegunda linha \t \\N"))
            c.execute("INSERT INTO ponto_fiscalizacao(id) VALUES (3000000010)")
            c.execute("DELETE FROM ponto_fiscalizacao WHERE id=3000000010")
            c.execute("UPDATE traseiro_ponto_pendente SET revisao=17 WHERE ponto_id=3000000000")
            c.execute("""
                INSERT INTO snapshot_publicado(id, publicado_em, status, identificador_versao)
                VALUES (2, '2026-11-19T12:00:00-03:00', 'publicado', 'pai')
            """)
            c.execute("""
                INSERT INTO snapshot_publicado(id, anterior_id, publicado_em, status, identificador_versao)
                VALUES (1, 2, '2026-11-19T16:00:00Z', 'publicado', 'filho')
            """)
            c.commit()
        preparar_origem(self.origem, self.copia)

    def tabela(self, nome):
        return self.sql.Identifier(self.esquema, nome)

    def esquema_existe(self):
        return self.pg.execute("SELECT to_regnamespace(%s) IS NOT NULL", (self.esquema,)).fetchone()[0]

    def test_copia_simula_publica_preserva_e_recusa_repeticao(self):
        with closing(db.connect_readonly(self.copia)) as c:
            totais = importar(c, self.pg, self.esquema, simular=True)
            self.assertGreater(len(totais), 90)
            self.assertEqual(totais["ponto_fiscalizacao"], 1)
            self.assertFalse(self.esquema_existe())
            self.assertEqual(importar(c, self.pg, self.esquema), totais)
            with self.assertRaisesRegex(ErroMigracao, "já existe"):
                importar(c, self.pg, self.esquema)
        sql = self.sql
        self.assertEqual(self.pg.execute(sql.SQL("SELECT id, km, observacoes FROM {}")
                         .format(self.tabela("ponto_fiscalizacao"))).fetchall(),
                         [(3000000000, Decimal("1.23456789"), "Radar ç\nsegunda linha \t \\N")])
        self.assertEqual(self.pg.execute(sql.SQL("SELECT ponto_id, revisao FROM {}")
                         .format(self.tabela("traseiro_ponto_pendente"))).fetchall(),
                         [(3000000000, 17)])
        self.assertEqual(self.pg.execute(sql.SQL("SELECT anterior_id FROM {} WHERE id=1")
                         .format(self.tabela("snapshot_publicado"))).fetchone(), (2,))
        novo = self.pg.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES RETURNING id")
                               .format(self.tabela("ponto_fiscalizacao"))).fetchone()
        self.assertEqual(novo, (3000000011,))
        self.assertTrue(self.pg.execute(sql.SQL("SELECT 1 FROM {} WHERE ponto_id=%s")
                                        .format(self.tabela("traseiro_ponto_pendente")), novo).fetchone())

    def test_falha_de_dados_desfaz_esquema_inteiro_sem_expor_valor(self):
        with closing(db.connect(self.copia)) as c:
            c.execute("UPDATE snapshot_publicado SET publicado_em='valor que não é uma data'")
            c.commit()
            with self.assertRaisesRegex(ErroMigracao, r"snapshot_publicado.*publicado_em.*22007") as erro:
                importar(c, self.pg, self.esquema)
            self.assertNotIn("valor que não é uma data", str(erro.exception))
        self.assertFalse(self.esquema_existe())
