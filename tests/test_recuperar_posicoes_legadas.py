# -*- coding: utf-8 -*-
"""Recuperacao explicita de GPS legado, sem escrever no arquivo de origem."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from coletor.fontes.araguaiana_to import ColetorASTTAraguaina
from core import config, consultas, governanca
from core.manutencao import recuperar_posicoes_legadas as recuperacao


##-- BUNDITA DE URSO #{22} -- A recuperacao de legados deve conservar a origem, respeitar conflitos e nunca substituir GPS existente. ##
class TestRecuperarPosicoesLegadas(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        self.origem = self.pasta / "original.sqlite3"
        for nome, valor in {"DATA_DIR": str(self.pasta), "RAW_DIR": str(self.pasta / "raw"),
                            "STAGING_DIR": str(self.pasta / "staging")}.items():
            p = patch.object(config, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        self.coletor = ColetorASTTAraguaina(db_path=str(self.origem))
        self.addCleanup(self.coletor.conn.close)
        raws = []
        for i, (lat, lon) in enumerate([
                ("-7.158.138", "-48.192.593"), ("-7199534", "-48218441"),
                ("-7.191751", "-48.229020"), ("ilegivel", "ilegivel")]):
            raws.append({"processo": "TESTE%d" % i, "serie": "R100%d" % i,
                         "latitude": lat, "longitude": lon, "local": "Local %d" % i,
                         "faixas": ["1"], "sentidos": []})
        self.coletor.ingerir_registros(raws)
        self.conn = self.coletor.conn
        self.conn.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=NULL WHERE id IN (1,2)")
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def assinatura(self):
        with self.origem.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()

    def test_simulacao_recupera_formato_da_fonte_sem_escrever(self):
        antes = self.assinatura()
        plano = recuperacao.recuperar(self.origem)
        self.assertEqual(plano["modo"], "simulacao")
        self.assertEqual([(p["latitude"], p["longitude"]) for p in plano["recuperaveis"]],
                         [(-7.158138, -48.192593), (-7.199534, -48.218441)])
        self.assertEqual(self.assinatura(), antes)

    def test_copia_aparece_no_mapa_preserva_bruto_e_e_idempotente(self):
        antes = self.assinatura()
        bruto = self.conn.execute("SELECT id,payload_original,hash_registro FROM REGISTRO_FONTE").fetchall()
        pos_existente = self.conn.execute("SELECT posicao_id FROM PONTO_FISCALIZACAO WHERE id=3").fetchone()[0]
        destino = self.pasta / "recuperado.sqlite3"
        resultado = recuperacao.recuperar(self.origem, destino)
        self.assertEqual(len(resultado["recuperadas"]), 2)
        self.assertEqual(self.assinatura(), antes)
        with recuperacao.abrir_leitura(destino) as c:
            self.assertEqual(c.execute("SELECT id,payload_original,hash_registro FROM REGISTRO_FONTE").fetchall(), bruto)
            self.assertEqual(c.execute("SELECT posicao_id FROM PONTO_FISCALIZACAO WHERE id=3").fetchone()[0], pos_existente)
            for plano in resultado["recuperadas"]:
                recs, _ = consultas.buscar_pontos(c, plano["latitude"], plano["longitude"], 1)
                self.assertIn("P-%d" % plano["ponto_id"], {r["id"] for r in recs})
            self.assertEqual(c.execute("SELECT posicao_id FROM PONTO_FISCALIZACAO WHERE id=4").fetchone()[0], None)
        self.assertEqual(recuperacao.recuperar(destino)["recuperaveis"], [])

    def test_nao_sobrescreve_origem_nem_arquivo_existente(self):
        with self.assertRaises(ValueError):
            recuperacao.recuperar(self.origem, self.origem)
        destino = self.pasta / "existente.sqlite3"
        destino.write_bytes(b"preservar")
        with self.assertRaises(ValueError):
            recuperacao.recuperar(self.origem, destino)
        self.assertEqual(destino.read_bytes(), b"preservar")

    def test_ponto_removido_nao_e_recuperado(self):
        governanca.garantir_esquema(self.conn)
        self.conn.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-15' WHERE id=1")
        self.conn.commit()
        self.assertEqual([p["ponto_id"] for p in recuperacao.planejar(self.conn)], [2])

    def test_observacoes_discordantes_nao_escolhem_coordenada(self):
        registro = self.conn.execute("SELECT * FROM REGISTRO_FONTE WHERE id=1").fetchone()
        raw = json.loads(registro["payload_original"])
        raw["latitude"] = "-7.191751"
        rid = self.coletor.registrar_registro(registro["artefato_id"], 99, "OUTRO", raw)
        self.conn.execute("INSERT INTO VINCULO_REGISTRO_PONTO (registro_id,ponto_id) VALUES (?,1)", (rid,))
        self.conn.commit()
        self.assertEqual([p["ponto_id"] for p in recuperacao.planejar(self.conn)], [2])


if __name__ == "__main__":
    unittest.main()
