# -*- coding: utf-8 -*-
"""Ingestao pela API de escrita (POST /api/v1/radares) e upsert idempotente.

Cobre:
  - POST /radares continua sendo CONSULTA quando nao ha token (corpo lat/lon);
  - POST /radares vira ESCRITA autenticada com o cabecalho ``X-Api-Token``;
  - sem token configurado no servidor, a escrita FALHA SEGURA (401);
  - upsert da nossa base (Bundita de Urso): reingerir o mesmo payload nao
    cria ponto; campo alterado atualiza o MESMO ponto (mesmo id);
    identificador novo cria ponto novo; e fonte sem identificador segue
    criando um ponto por registro.

Nenhum teste acessa a rede nem o banco de producao: tudo roda em banco
temporario (``tests.common.ambiente_temporario``).
"""
import json
import os
import unittest
from unittest import mock

from core import config
from core import db as dbmod
from coletor.fontes.base_lwb import ColetorBaseLWB
from web import nucleo
import tests.common as common


def _radar(ident=None, **kw):
    """Radar de exemplo da nossa base (coordenada plausivel em SP)."""
    d = {"latitude": -23.55, "longitude": -46.63,
         "municipio": "Sao Paulo", "uf": "SP", "via": "BR-116"}
    if ident is not None:
        d["identificador"] = ident
    d.update(kw)
    return d


def _doc(resp):
    """Corpo do handle_request: dict (erro/ingestao) ou string JSON (consulta)."""
    return resp if isinstance(resp, dict) else json.loads(resp)


class BaseUpsert(unittest.TestCase):

    def setUp(self):
        common.ambiente_temporario()
        # a API so responde consulta com um banco existente.
        con = dbmod.connect(config.DB_PATH)
        try:
            dbmod.init_db(con)
        finally:
            con.close()

    def _conector(self):
        return ColetorBaseLWB(db_path=config.DB_PATH)

    @staticmethod
    def _pontos(conn):
        return dbmod.scalar(conn, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO")


class TestUpsertBaseLWB(BaseUpsert):

    def test_reingerir_mesmo_payload_nao_cria_ponto(self):
        c = self._conector()
        try:
            r1 = c.ingerir_registros([_radar("E-1", velocidade_geral=60)])
            self.assertEqual(r1["criados"], 1)
            self.assertEqual(self._pontos(c.conn), 1)
            # mesmo payload de novo: nada de ponto novo, nada a atualizar.
            r2 = c.ingerir_registros([_radar("E-1", velocidade_geral=60)])
            self.assertEqual(r2["criados"], 0)
            self.assertEqual(r2["atualizados"], 0)
            self.assertEqual(self._pontos(c.conn), 1)
        finally:
            c.conn.close()

    def test_campo_alterado_atualiza_o_mesmo_ponto(self):
        c = self._conector()
        try:
            c.ingerir_registros([_radar("E-1", velocidade_geral=60)])
            antes = dbmod.scalar(c.conn, "SELECT id FROM PONTO_FISCALIZACAO")
            r = c.ingerir_registros([_radar("E-1", velocidade_geral=80, km=10)])
            self.assertEqual(r["criados"], 0)
            self.assertEqual(r["atualizados"], 1)
            # nenhum ponto novo e o MESMO id foi atualizado.
            self.assertEqual(self._pontos(c.conn), 1)
            depois = dbmod.scalar(c.conn, "SELECT id FROM PONTO_FISCALIZACAO")
            self.assertEqual(antes, depois)
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT km FROM PONTO_FISCALIZACAO WHERE id=?" ,
                             (antes,)), 10)
        finally:
            c.conn.close()

    def test_identificador_novo_cria_ponto_novo(self):
        c = self._conector()
        try:
            c.ingerir_registros([_radar("E-1")])
            r = c.ingerir_registros([_radar("E-2")])
            self.assertEqual(r["criados"], 1)
            self.assertEqual(self._pontos(c.conn), 2)
        finally:
            c.conn.close()

    def test_sem_identificador_um_ponto_por_registro(self):
        c = self._conector()
        try:
            r = c.ingerir_registros([_radar(None, km=1),
                                     _radar(None, km=2)])
            self.assertEqual(r["criados"], 2)
            self.assertEqual(r["atualizados"], 0)
            self.assertEqual(self._pontos(c.conn), 2)
        finally:
            c.conn.close()


class TestPostRadares(BaseUpsert):
    """POST /api/v1/radares: consulta x escrita autenticada x 401."""

    def _req(self, corpo=b"", metodo="POST",
             ctype="application/json", token=None, latlon=False):
        env = {
            "REQUEST_METHOD": metodo,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(corpo)),
            "CONTENT_TYPE": ctype,
            "PATH_INFO": "/api/v1/radares",
            "REQUEST_URI": "/api/v1/radares",
            "SCRIPT_NAME": "",
        }
        if token is not None:
            env["HTTP_X_API_TOKEN"] = token
        return nucleo.handle_request(env, corpo)

    def test_post_latlon_sem_token_continua_consulta(self):
        # consulta antiga: corpo objeto com lat/lon, sem token -> resultado.
        corpo = json.dumps({"lat": -23.55, "lon": -46.63, "raio": 5000,
                            "formato": "json"}).encode("utf-8")
        status, _h, resp = self._req(corpo)
        self.assertEqual(status, 200)
        self.assertIn("resultado", _doc(resp))

    def test_escrita_sem_token_configurado_e_401(self):
        # sem RADAR_API_TOKEN no ambiente, a escrita fica desabilitada.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RADAR_API_TOKEN", None)
            corpo = json.dumps([_radar("E-1")]).encode("utf-8")
            status, _h, resp = self._req(corpo)
        self.assertEqual(status, 401)
        self.assertEqual(_doc(resp)["erro"]["codigo"],
                         "ingestao_desabilitada")

    def test_escrita_com_token_valido_grava(self):
        with mock.patch.object(config, "token_ingestao", return_value="segredo-teste"):
            corpo = json.dumps([_radar("E-1")]).encode("utf-8")
            status, _h, resp = self._req(corpo, token="segredo-teste")
        self.assertEqual(status, 200)
        doc = _doc(resp)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["criados"], 1)
        con = dbmod.connect(config.DB_PATH)
        try:
            self.assertEqual(
                dbmod.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                1)
        finally:
            con.close()

    def test_escrita_com_token_errado_e_401(self):
        with mock.patch.object(config, "token_ingestao", return_value="segredo-teste"):
            corpo = json.dumps([_radar("E-1")]).encode("utf-8")
            status, _h, resp = self._req(corpo, token="errado")
        self.assertEqual(status, 401)
        self.assertEqual(_doc(resp)["erro"]["codigo"], "nao_autorizado")

    def test_escrita_reusa_mesmo_ponto_via_api(self):
        with mock.patch.object(config, "token_ingestao", return_value="segredo-teste"):
            c1 = json.dumps([_radar("E-1", velocidade_geral=60)]).encode("utf-8")
            s1, _h, r1 = self._req(c1, token="segredo-teste")
            c2 = json.dumps([_radar("E-1", velocidade_geral=80)]).encode("utf-8")
            s2, _h, r2 = self._req(c2, token="segredo-teste")
        self.assertEqual(s1, 200)
        self.assertEqual(_doc(r1)["criados"], 1)
        self.assertEqual(s2, 200)
        doc2 = _doc(r2)
        self.assertEqual(doc2["criados"], 0)
        self.assertEqual(doc2["atualizados"], 1)
        con = dbmod.connect(config.DB_PATH)
        try:
            self.assertEqual(
                dbmod.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"),
                1)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
