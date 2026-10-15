# -*- coding: utf-8 -*-
"""Espelho de dados sintetico; nenhum arquivo privado entra nos testes."""
import csv
import gzip
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from coletor.fontes.antt import ColetorANTT
from core import config
from tools.auditar_repositorio_dados import auditar


##-- BUNDITA DE URSO #{27} -- Um espelho so e restauravel se arquivos, indice, execucoes e registros relidos corresponderem. ##
class TestRepositorioDados(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        self.raiz = self.pasta / "espelho"
        (self.raiz / "bruto").mkdir(parents=True)
        (self.raiz / "base de dados").mkdir()
        ambiente = patch.multiple(config, DATA_DIR=str(self.pasta / "work"),
                                 RAW_DIR=str(self.pasta / "raw"), STAGING_DIR=str(self.pasta / "staging"))
        ambiente.start()
        self.addCleanup(ambiente.stop)
        fixture = Path(__file__).parent / "fixtures" / "antt_radares_fixture.json"
        self.banco = self.pasta / "radar.sqlite3"
        coletor = ColetorANTT(db_path=str(self.banco))
        resumo = coletor.sincronizar(str(fixture), publicar=False)
        art = dict(coletor.conn.execute("SELECT * FROM ARTEFATO_COLETA").fetchone())
        execucao = dict(coletor.conn.execute("SELECT * FROM EXECUCAO_COLETA").fetchone())
        coletor.conn.close()
        self.bruto = self.raiz / "bruto" / "antt.json"
        self.bruto.write_bytes(fixture.read_bytes())
        self.indice = {"arquivo": "bruto/antt.json", "fonte": ColetorANTT.FONTE["nome"],
                       "recurso_id": resumo["recurso_id"], "execucao_id": resumo["execucao_id"],
                       "artefato_id": art["id"], "bytes": art["bytes_arquivo"], "sha256": art["hash_sha256"]}
        self.gravar_csv("INDICE.csv", [self.indice])
        self.gravar_csv("execucoes.csv", [execucao])
        self.backup = self.raiz / "base de dados" / "radar-2026-01-01_000000.sqlite3.gz"
        self.compactar()

    def gravar_csv(self, nome, linhas):
        with (self.raiz / nome).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(linhas[0]))
            writer.writeheader()
            writer.writerows(linhas)

    def compactar(self):
        with gzip.open(self.backup, "wb") as f:
            f.write(self.banco.read_bytes())

    def test_auditoria_completa_nao_altera_origem(self):
        antes = {str(p.relative_to(self.raiz)): p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()}
        relatorio = auditar(self.raiz, testar_coletores=True)
        self.assertEqual(relatorio["problemas"], [])
        self.assertEqual(relatorio["arquivos"], 1)
        self.assertEqual(relatorio["releituras"][0]["recebidos"], 4)
        self.assertEqual(relatorio["releituras"][0]["normalizados"], 3)
        self.assertTrue(relatorio["releituras"][0]["registros_iguais_ao_snapshot"])
        depois = {str(p.relative_to(self.raiz)): p.read_bytes() for p in self.raiz.rglob("*") if p.is_file()}
        self.assertEqual(antes, depois)

    def test_conteudo_alterado_e_detectado(self):
        self.bruto.write_bytes(self.bruto.read_bytes() + b" ")
        self.assertIn("hash_ou_bytes_divergentes", {r["codigo"] for r in auditar(self.raiz)["problemas"]})

    def test_linhagem_sqlite_divergente_e_detectada(self):
        with sqlite3.connect(self.banco) as c:
            c.execute("UPDATE ARTEFATO_COLETA SET hash_sha256=?", ("0" * 64,))
        c.close()
        self.compactar()
        self.assertIn("linhagem_divergente", {r["codigo"] for r in auditar(self.raiz)["problemas"]})

    def test_execucao_csv_divergente_e_detectada(self):
        with (self.raiz / "execucoes.csv").open() as f:
            linhas = list(csv.DictReader(f))
        linhas[0]["status"] = "erro"
        self.gravar_csv("execucoes.csv", linhas)
        self.assertIn("execucao_csv_divergente", {r["codigo"] for r in auditar(self.raiz)["problemas"]})

    def test_bruto_fora_do_indice_e_detectado(self):
        (self.raiz / "bruto" / "extra.txt").write_text("extra")
        self.assertIn("bruto_sem_indice", {r["codigo"] for r in auditar(self.raiz)["problemas"]})

    def test_indice_nao_pode_ler_arquivo_externo(self):
        (self.pasta / "externo.json").write_text("[]")
        self.indice["arquivo"] = "../externo.json"
        self.gravar_csv("INDICE.csv", [self.indice])
        with self.assertRaisesRegex(ValueError, "fora do repositorio"):
            auditar(self.raiz)
