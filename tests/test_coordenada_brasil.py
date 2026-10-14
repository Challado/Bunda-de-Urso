# -*- coding: utf-8 -*-
"""Coordenada implausivel para o Brasil: sinal oeste perdido / degenerada.

Nenhuma longitude valida no Brasil e positiva. Quando a fonte publica o
valor sem o sinal oeste (ex.: 48.459841 em vez de -48.459841), a leitura
correta e -abs(lon) -- mas so e aceita quando o ponto corrigido cai na
malha municipal oficial do IBGE e a UF confere. Dado degenerado
(latitude == longitude) ou nao consertavel e preservado e marcado.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor.fontes import normalizacao as nz    # noqa: E402
from core import db as dbmod                     # noqa: E402
from tests.common import banco_memoria           # noqa: E402


class TestSinalLongitude(unittest.TestCase):
    def test_longitude_negativa_nao_mexe(self):
        lon, corrig, motivo = nz.normalizar_sinal_longitude(-23.5, -46.6)
        self.assertEqual(lon, -46.6)
        self.assertFalse(corrig)
        self.assertIsNone(motivo)

    def test_sinal_perdido_corrige_quando_malha_e_uf_confirmam(self):
        # Bebedouro/SP: 48.459841 -> -48.459841 cai em Bebedouro (3506102).
        localizar = lambda lat, lon: ("3506102", "SP")       # noqa: E731
        lon, corrig, motivo = nz.normalizar_sinal_longitude(
            -20.910116, 48.459841, "SP", localizar=localizar)
        self.assertTrue(corrig)
        self.assertAlmostEqual(lon, -48.459841)
        self.assertIsNone(motivo)

    def test_uf_divergente_nao_corrige(self):
        # Monte Alto/SP com 43.549075: -43.549075 cai em MG -> nao e o SP
        # declarado; nao inventa, devolve o original + motivo.
        localizar = lambda lat, lon: ("3157302", "MG")       # noqa: E731
        lon, corrig, motivo = nz.normalizar_sinal_longitude(
            -21.250479, 43.549075, "SP", localizar=localizar)
        self.assertFalse(corrig)
        self.assertEqual(lon, 43.549075)
        self.assertIn("nao em SP", motivo)

    def test_ponto_corrigido_fora_da_malha_nao_corrige(self):
        localizar = lambda lat, lon: (None, None)            # noqa: E731
        lon, corrig, motivo = nz.normalizar_sinal_longitude(
            -16.425392, 49.465963, "GO", localizar=localizar)
        self.assertFalse(corrig)
        self.assertEqual(lon, 49.465963)
        self.assertIn("fora da malha", motivo)

    def test_longitude_positiva_fora_da_faixa_do_brasil(self):
        lon, corrig, motivo = nz.normalizar_sinal_longitude(-23.5, 180.0)
        self.assertFalse(corrig)
        self.assertEqual(lon, 180.0)
        self.assertIn("faixa longitudinal", motivo)

    def test_latitude_fora_do_brasil(self):
        lon, corrig, motivo = nz.normalizar_sinal_longitude(45.0, 8.0)
        self.assertFalse(corrig)
        self.assertEqual(lon, 8.0)
        self.assertIn("latitude fora do Brasil", motivo)


class TestAjustarCoordenada(unittest.TestCase):
    def test_corrige_e_anota_original(self):
        d = {"latitude": -20.910116, "longitude": 48.459841, "uf": "SP",
             "observacoes": None}
        with mock.patch.object(nz, "_localizar_uf_brasil",
                               return_value=("3506102", "SP")):
            nz.ajustar_coordenada_brasil(d)
        self.assertAlmostEqual(d["longitude"], -48.459841)
        self.assertIn("hemisferio oeste", d["observacoes"])
        # nao mexeu na qualidade de um ponto consertado
        self.assertNotIn("qualidade", d)

    def test_latitude_igual_longitude_marca_sem_corrigir(self):
        d = {"latitude": -16.615076, "longitude": -16.615076,
             "uf": "GO", "observacoes": "KM original: 050+674"}
        nz.ajustar_coordenada_brasil(d)
        self.assertEqual(d["longitude"], -16.615076)
        self.assertEqual(d["qualidade"], "conflitante")
        self.assertIn("QUARENTENA", d["observacoes"])
        self.assertIn("KM original", d["observacoes"])

    def test_nao_consertavel_marca_quarentena(self):
        d = {"latitude": -21.250479, "longitude": 43.549075, "uf": "SP",
             "observacoes": None}
        with mock.patch.object(nz, "_localizar_uf_brasil",
                               return_value=("3157302", "MG")):
            nz.ajustar_coordenada_brasil(d)
        self.assertEqual(d["longitude"], 43.549075)
        self.assertEqual(d["qualidade"], "conflitante")
        self.assertIn("QUARENTENA", d["observacoes"])


class TestInsercaoCoordenadaBrasil(unittest.TestCase):
    """Integracao: inserir_normalizado conserta/marca a POSICAO_GEOGRAFICA."""

    def setUp(self):
        self.con = banco_memoria()
        org_id = dbmod.insert(self.con, "ORGANIZACAO", {
            "nome": "DER-SP",
            "tipo_organizacao_id": dbmod.domain_id(
                self.con, "TIPO_ORGANIZACAO", "orgao_publico")})
        self.fonte_id = dbmod.insert(self.con, "FONTE", {
            "nome": "DER-SP - Radares estaduais",
            "organizacao_id": org_id,
            "natureza_id": dbmod.domain_id(self.con, "NATUREZA_FONTE",
                                           "oficial"),
            "url_institucional": "https://exemplo/", "esfera": "estadual",
            "situacao": "ativa"})
        self.recurso_id = dbmod.insert(self.con, "RECURSO_FONTE", {
            "fonte_id": self.fonte_id, "nome": "rec",
            "url_recurso": "https://exemplo/rec.xlsx",
            "formato_origem": "xlsx", "ativo": 1, "status_integracao": "ok"})
        self.artefato_id = dbmod.insert(self.con, "ARTEFATO_COLETA", {
            "recurso_id": self.recurso_id,
            "hash_sha256": "a" * 64, "caminho_cache": "/tmp/raw/x",
            "bytes_arquivo": 10, "baixado_em": "2026-10-10T00:00:00+00:00",
            "resultado_validacao": "ok"})
        dbmod.insert(self.con, "MUNICIPIO", {"codigo_ibge": "3506102",
                                             "uf_sigla": "SP",
                                             "nome": "Bebedouro"})
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def _registro(self):
        return dbmod.insert(self.con, "REGISTRO_FONTE", {
            "artefato_id": self.artefato_id, "numero_ordem": 1,
            "identificador_na_fonte": "00017098",
            "payload_original": "{}", "hash_registro": "b" * 64,
            "status_validacao": "ok"})

    def _d(self, lat, lon):
        return {
            "identificador": "00017098", "latitude": lat, "longitude": lon,
            "qualidade": "oficial", "metodo_obtencao": "publicacao DER-SP",
            "uf": "SP", "municipio_nome": "Bebedouro", "via_codigo": "SP-326",
            "via_tipo": "estadual", "km": 381.853, "tipo_radar": "fixo",
        }

    def test_posicao_corrigida_persiste_negativa(self):
        reg = self._registro()
        d = self._d(-20.910116, 48.459841)
        with mock.patch.object(nz, "_localizar_uf_brasil",
                               return_value=("3506102", "SP")):
            res = nz.inserir_normalizado(self.con, reg, d, self.fonte_id)
        pos = dbmod.query_one(
            self.con, "SELECT latitude, longitude FROM POSICAO_GEOGRAFICA "
                      "WHERE id=?", (res["posicao_id"],))
        self.assertAlmostEqual(pos["longitude"], -48.459841)
        self.assertAlmostEqual(pos["latitude"], -20.910116)

    def test_dado_degenerado_preserva_e_marca_conflitante(self):
        reg = self._registro()
        d = self._d(-16.615076, -16.615076)
        res = nz.inserir_normalizado(self.con, reg, d, self.fonte_id)
        pos = dbmod.query_one(
            self.con, "SELECT p.longitude, q.codigo AS qualidade "
                      "FROM POSICAO_GEOGRAFICA p JOIN QUALIDADE_POSICAO q "
                      "ON q.id=p.qualidade_posicao_id WHERE p.id=?",
            (res["posicao_id"],))
        self.assertEqual(pos["longitude"], -16.615076)   # bruto preservado
        self.assertEqual(pos["qualidade"], "conflitante")


if __name__ == "__main__":
    unittest.main()
