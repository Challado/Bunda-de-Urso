# -*- coding: utf-8 -*-
"""Comparacao independente com a coleta do commit anterior as correcoes."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import config, consultas, db


##-- BUNDITA DE URSO #{20} -- Contar testes aprovados nao prova que as coordenadas coletadas continuam no banco e no mapa. ##
class TestConservacaoFontes(unittest.TestCase):
    def test_coletas_preservam_inventario_e_marcacoes_da_versao_original(self):
        fixtures = Path(__file__).parent / "fixtures"
        referencia = json.loads((fixtures / "conservacao_fontes.json").read_text())
        for caso in referencia["casos"]:
            with self.subTest(fonte=caso["modulo"], arquivo=caso["arquivo"]):
                with tempfile.TemporaryDirectory(prefix="radar-conservacao-") as pasta, \
                        patch.multiple(config, DATA_DIR=pasta, RAW_DIR=pasta + "/raw",
                                       STAGING_DIR=pasta + "/staging", DB_PATH=pasta + "/radar.sqlite3"):
                    con = db.connect()
                    try:
                        classe = getattr(importlib.import_module("coletor.fontes." + caso["modulo"]), caso["classe"])
                        coletor = classe(conn=con)
                        with patch("coletor.http.baixar", side_effect=AssertionError("rede inesperada no teste offline")), \
                                patch("urllib.request.urlopen", side_effect=AssertionError("rede inesperada no teste offline")):
                            resumo = coletor.sincronizar(str(fixtures / caso["arquivo"]))
                        for tabela, campo in (("REGISTRO_FONTE", "registros"),
                                               ("PONTO_FISCALIZACAO", "pontos"),
                                               ("TRECHO_ELEGIVEL", "trechos")):
                            self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM " + tabela), caso[campo])
                        self.assertEqual(resumo["linhas_recebidas"], caso["recebidos"])
                        if coletor.MODO_COLETA == "documental":
                            self.assertEqual(resumo["evidencias_documentais"], caso["rejeitados"])
                            self.assertEqual(resumo["rejeitados"], 0)
                        else:
                            self.assertEqual(resumo["rejeitados"], caso["rejeitados"])
                        gps = sorted([list(r) for r in con.execute(
                            "SELECT pos.latitude, pos.longitude FROM PONTO_FISCALIZACAO p "
                            "JOIN POSICAO_GEOGRAFICA pos ON pos.id=p.posicao_id")])
                        self.assertEqual(gps, caso["gps"])
                        # Cada localizacao da referencia deve ser encontrada no seu proprio raio.
                        for lat, lon in set(map(tuple, caso["gps"])):
                            pontos, _ = consultas.buscar_pontos(con, lat, lon, 1,
                                                                {"incluir_inativos": True}, limite=1000)
                            encontrados = {(p["localizacao"]["latitude"], p["localizacao"]["longitude"])
                                           for p in pontos}
                            self.assertIn((lat, lon), encontrados)
                    finally:
                        con.close()
