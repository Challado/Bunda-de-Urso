"""Importação transacional contra um servidor PostgreSQL real de testes."""

from contextlib import closing
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
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

    def test_recria_destino_e_recupera_o_esquema_anterior_se_copy_falhar(self):
        with closing(db.connect(self.copia)) as origem:
            importar(origem, self.pg, self.esquema)
            pontos = self.tabela("ponto_fiscalizacao")
            self.pg.execute(self.sql.SQL("INSERT INTO {} DEFAULT VALUES").format(pontos))
            origem.execute("UPDATE snapshot_publicado SET publicado_em='data inválida'")
            origem.commit()
            with self.assertRaisesRegex(ErroMigracao, "22007"):
                importar(origem, self.pg, self.esquema, recriar=True)
            self.assertEqual(self.pg.execute(self.sql.SQL("SELECT count(*) FROM {}").format(pontos)).fetchone(), (2,))
        with closing(db.connect_readonly(self.origem)) as origem:
            importar(origem, self.pg, self.esquema, recriar=True)
        self.assertEqual(self.pg.execute(self.sql.SQL("SELECT count(*) FROM {}").format(pontos)).fetchone(), (1,))

    def test_recriacao_recusa_dependencias_externas(self):
        with closing(db.connect_readonly(self.copia)) as origem:
            importar(origem, self.pg, self.esquema)
            fora = self.esquema + "_outro"
            self.pg.execute(self.sql.SQL("CREATE SCHEMA {}").format(self.sql.Identifier(fora)))
            self.addCleanup(self.pg.execute, self.sql.SQL("DROP SCHEMA {} CASCADE").format(self.sql.Identifier(fora)))
            consulta = self.sql.Identifier(fora, "consulta")
            self.pg.execute(self.sql.SQL("CREATE VIEW {} AS SELECT id FROM {}").format(
                consulta, self.tabela("ponto_fiscalizacao")))
            with self.assertRaisesRegex(ErroMigracao, "dependências externas"):
                importar(origem, self.pg, self.esquema, recriar=True)
            self.assertEqual(self.pg.execute(self.sql.SQL("SELECT id FROM {}").format(consulta)).fetchall(), [(3000000000,)])

    def test_copy_preserva_texto_maior_que_um_bloco(self):
        texto = ("Radar ç 🐻 \\N\tlinha\r\n" * 2000) + "fim"
        with closing(db.connect(self.copia)) as origem:
            origem.execute("UPDATE ponto_fiscalizacao SET observacoes=?", (texto,))
            origem.commit()
            importar(origem, self.pg, self.esquema)
        self.assertEqual(self.pg.execute(self.sql.SQL("SELECT observacoes FROM {}").format(
            self.tabela("ponto_fiscalizacao"))).fetchone(), (texto,))

    def test_backup_sql_recria_esquema_completo_e_preserva_dados_e_sequencias(self):
        from psycopg import errors
        from psycopg.conninfo import conninfo_to_dict
        from core import caminhos

        with closing(db.connect_readonly(self.copia)) as origem:
            totais = importar(origem, self.pg, self.esquema)
        sql = self.sql
        pontos = self.tabela("ponto_fiscalizacao")
        extra = self.tabela("nova_tabela")
        vista = self.tabela("nova_vista")
        self.pg.execute(sql.SQL("""
            CREATE TABLE {} (
                id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 30 INCREMENT BY 2),
                id_ponto BIGINT UNIQUE REFERENCES {}(id),
                exato NUMERIC(29, 13), texto TEXT, binario BYTEA, itens TEXT[],
                dobro BIGINT GENERATED ALWAYS AS (id * 2) STORED
            )
        """).format(extra, pontos))
        self.pg.execute(sql.SQL("CREATE VIEW {} AS SELECT * FROM {}").format(vista, extra))
        exato = Decimal("6543210987654321.0123456789123")
        texto = "ação ' ☃\\N\r\n\\q\n"
        self.pg.execute(sql.SQL("""
            INSERT INTO {}(id_ponto, exato, texto, binario, itens) VALUES (%s, %s, %s, %s, %s)
        """).format(extra), (3000000000, exato, texto, bytes(range(256)), ["a,b", None, ""]))
        self.pg.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES").format(extra))
        self.pg.execute(sql.SQL("DELETE FROM {} WHERE id = 32").format(extra))
        opcoes = conninfo_to_dict(os.environ["RADAR_TESTE_POSTGRES"])
        opcoes["esquema"] = self.esquema
        with (patch.object(caminhos, "motor_banco", return_value="postgres"),
              patch.object(caminhos, "postgres", return_value=opcoes),
              patch.object(caminhos, "banco", return_value=str(self.origem)),
              patch("subprocess.run", side_effect=AssertionError("Backup invocou um cliente externo"))):
            backup = db.backup_operacional(self.origem.parent, "completo", self.origem)
        self.assertEqual(backup.name, "completo.sql.gz")
        with gzip.open(backup, "rt", encoding="utf-8") as arquivo:
            comandos = arquivo.read()

        self.pg.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES").format(extra))
        with self.assertRaises(errors.DivisionByZero):
            try:
                self.pg.execute(comandos.replace("\nCOMMIT;\n", "\nSELECT 1/0;\nCOMMIT;\n"))
            finally:
                self.pg.execute("ROLLBACK")
        self.assertEqual(self.pg.execute(sql.SQL("SELECT count(*) FROM {}").format(extra)).fetchone(), (2,))

        self.pg.execute(comandos)
        for tabela, esperado in totais.items():
            self.assertEqual(self.pg.execute(sql.SQL("SELECT count(*) FROM {}")
                             .format(self.tabela(tabela))).fetchone(), (esperado,), tabela)
        self.assertEqual(self.pg.execute(sql.SQL("SELECT * FROM {}").format(vista)).fetchall(),
                         [(30, 3000000000, exato, texto, bytes(range(256)), ["a,b", None, ""], 60)])
        self.assertEqual(self.pg.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES RETURNING id")
                         .format(extra)).fetchone(), (34,))
        self.pg.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.esquema)))
        self.assertEqual(self.pg.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES RETURNING id")
                         .format(pontos)).fetchone(), (3000000011,))
        self.assertTrue(self.pg.execute("SELECT 1 FROM traseiro_ponto_pendente WHERE ponto_id=3000000011").fetchone())
        self.pg.execute("RESET search_path")

    def test_api_coletor_e_fila_usam_postgres_sem_sqlite(self):
        from psycopg.conninfo import conninfo_to_dict
        from coletor.fontes.dnit import ColetorDNITEquipamentos
        from core import caminhos, config, fila_cadastros
        from tests.test_dnit_http import API
        from web import nucleo

        with closing(db.connect_sqlite_readonly(self.copia)) as origem:
            importar(origem, self.pg, self.esquema)
        pasta = self.origem.parent / "operacional"
        pasta.mkdir()
        inexistente = str(pasta / "radar.sqlite3")
        opcoes = conninfo_to_dict(os.environ["RADAR_TESTE_POSTGRES"])
        opcoes["esquema"] = self.esquema
        with (patch.object(caminhos, "motor_banco", return_value="postgres"),
              patch.object(caminhos, "postgres", return_value=opcoes),
              patch.object(caminhos, "data_dir", return_value=str(pasta)),
              patch.object(caminhos, "banco", return_value=inexistente),
              patch.multiple(config, DATA_DIR=str(pasta), RAW_DIR=str(pasta),
                             STAGING_DIR=str(pasta), DB_PATH=inexistente),
              patch.object(db, "connect_sqlite", side_effect=AssertionError("SQLite operacional")),
              patch.object(db, "connect_sqlite_readonly", side_effect=AssertionError("SQLite operacional"))):
            self.assertEqual(nucleo.handle_request({"PATH_INFO": "/health/ready"})[0], 200)
            with closing(db.connect_existing(inexistente)) as conn:
                item = json.loads(API.read_bytes())["features"][0]
                coletor = ColetorDNITEquipamentos(conn=conn)
                self.assertEqual(coletor.ingerir_registros([item])["status"], "ok")
                self.assertEqual(coletor.ingerir_registros([item])["status"], "sem_mudanca")
                governanca.criar_usuario(conn, "operador", "uma-senha-local-de-teste", "admin")
            envio = fila_cadastros.receber({"latitude": -24.9555, "longitude": -53.4552,
                                            "velocidade_geral": 60})
            self.assertEqual(fila_cadastros.processar()["processados"], 1)
            self.assertEqual(fila_cadastros.consultar(envio["protocolo"])["estado"], "processado")
            self.assertFalse(Path(inexistente).exists())
