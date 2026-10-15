# -*- coding: utf-8 -*-
"""Conservacao de localizacoes: uma decisao de identidade nao apaga GPS publicado."""
import json
import random
import unittest
from unittest.mock import patch

from core import consultas, db, dedup, governanca
from tests import test_reconciliacao as cenarios


class TestConservacaoMarcacoes(unittest.TestCase):
    def setUp(self):
        self.cenario = cenarios.TestReconciliacao()
        self.cenario.setUp()
        self.addCleanup(self.cenario.tearDown)
        self.cenario.preparar()
        self.con = self.cenario.con

    def marcacoes(self, lat=-25, lon=-54, raio=100):
        pontos, _ = consultas.buscar_pontos(self.con, lat, lon, raio)
        return {(p["localizacao"]["latitude"], p["localizacao"]["longitude"])
                for p in pontos}

    ##-- BUNDITA DE URSO #{20} -- Um canonico sem GPS nao pode ocultar a coordenada valida de outra fonte. ##
    def test_canonico_sem_gps_preserva_marcacao_do_alias(self):
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=NULL WHERE id=1")
        antes = self.marcacoes()
        self.cenario.unificar()
        self.assertEqual(self.marcacoes(), antes)
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertFalse(any(c["campo"] == "localizacao" for c in pontos[0]["conflitos"]))

    def test_posicao_divergente_continua_consultavel_no_proprio_raio(self):
        self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=-25.01 WHERE id=2")
        antes = self.marcacoes(lat=-25.01)
        self.cenario.unificar()
        self.assertEqual(self.marcacoes(lat=-25.01), antes)

    def test_consulta_ampla_preserva_as_duas_posicoes_publicadas(self):
        self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=-25.01 WHERE id=2")
        antes = self.marcacoes(raio=2000)
        self.cenario.unificar()
        self.assertEqual(self.marcacoes(raio=2000), antes)

    def test_detalhe_preserva_coordenada_mostrada_no_mapa(self):
        self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=-25.01 WHERE id=2")
        self.cenario.unificar()
        ponto = consultas.buscar_ponto_por_id(self.con, "P-2")
        self.assertEqual(ponto["localizacao"]["latitude"], -25.01)
        self.assertEqual(ponto["id"], "P-2")
        self.assertEqual(ponto["ponto_canonico_id"], "P-1")

    def test_canonico_inativo_nao_esconde_publicacao_ativa(self):
        inativo = db.domain_id(self.con, "SITUACAO_OPERACIONAL", "inativo")
        ativo = db.domain_id(self.con, "SITUACAO_OPERACIONAL", "ativo")
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET situacao_operacional_id=? WHERE id=1", (inativo,))
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET situacao_operacional_id=? WHERE id=2", (ativo,))
        antes = self.marcacoes()
        self.cenario.unificar()
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertEqual(self.marcacoes(), antes)
        self.assertEqual(pontos[0]["situacao_operacional"], "ativo")

    def test_filtro_de_uf_preserva_observacao_que_satisfez_o_filtro(self):
        for registro, uf in ((1, "SC"), (2, "PR")):
            payload = json.loads(db.scalar(self.con, "SELECT payload_original FROM REGISTRO_FONTE WHERE id=?", (registro,)))
            payload["uf"] = uf
            self.con.execute("UPDATE REGISTRO_FONTE SET payload_original=? WHERE id=?", (json.dumps(payload), registro))
        self.cenario.unificar()
        for uf in ("PR", "SC"):
            pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100, {"uf": uf})
            self.assertEqual(len(pontos), 1)
            self.assertEqual(pontos[0]["localizacao"]["uf"], uf)

    def test_filtro_de_rodovia_nao_some_apos_resolver_o_alias(self):
        via = self.cenario.via("BR-101")
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET via_id=? WHERE id=2", (via,))
        self.cenario.unificar()
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100, {"rodovia": "BR-101"})
        self.assertEqual(len(pontos), 1)
        self.assertEqual(pontos[0]["localizacao"]["via"]["codigo"], "BR-101")

    def test_remocao_do_canonico_nao_apaga_posicao_divergente_ativa(self):
        governanca.garantir_esquema(self.con)
        self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=-25.01 WHERE id=2")
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-15' WHERE id=1")
        antes = self.marcacoes(lat=-25.01)
        self.cenario.unificar()
        self.assertEqual(self.marcacoes(lat=-25.01), antes)

    def test_duplicata_identica_removida_nao_ressuscita(self):
        governanca.garantir_esquema(self.con)
        self.cenario.unificar()
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-15' WHERE id=1")
        self.assertEqual(self.marcacoes(), set())

    def test_coordenada_inferida_valida_tambem_e_preservada(self):
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=NULL WHERE id=2")
        resolucao = {"status": "ok", "lat": -25.01, "lon": -54}
        with patch("core.georesolver.calibracao", return_value={}), \
                patch("core.georesolver.resolver", return_value=resolucao):
            antes = self.marcacoes(lat=-25.01)
            self.cenario.unificar()
            self.assertEqual(self.marcacoes(lat=-25.01), antes)

    def test_fila_fraca_ou_serie_generica_nao_remove_marcacoes(self):
        antes = self.marcacoes()
        self.con.execute("UPDATE EQUIPAMENTO SET numero_serie='14'")
        evid = json.loads(db.scalar(self.con, "SELECT evidencias_resumo FROM CANDIDATO_DUPLICIDADE"))
        evid["nivel"] = "fraco"
        self.con.execute("UPDATE CANDIDATO_DUPLICIDADE SET score=0.2, evidencias_resumo=?", (json.dumps(evid),))
        self.assertEqual(dedup.candidatos(self.con), [])
        self.assertEqual(self.marcacoes(), antes)

    def test_paginacao_cobre_todas_as_posicoes_divergentes(self):
        self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=-25.01 WHERE id=2")
        antes = self.marcacoes(raio=2000)
        self.cenario.unificar()
        observadas, cursor = set(), None
        for _ in range(4):
            pontos, meta = consultas.buscar_pontos(self.con, -25, -54, 2000, limite=1, cursor=cursor)
            observadas.update((p["localizacao"]["latitude"], p["localizacao"]["longitude"]) for p in pontos)
            cursor = meta["proximo_cursor"]
            if cursor is None:
                break
        self.assertIsNone(cursor)
        self.assertEqual(observadas, antes)

    def test_varredura_aleatoria_de_raios_nao_perde_posicoes(self):
        rng = random.Random(2001)
        for _ in range(40):
            lat = -25 + rng.uniform(-0.03, 0.03)
            lon = -54 + rng.uniform(-0.03, 0.03)
            self.con.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=?, longitude=? WHERE id=2", (lat, lon))
            consultas_teste = [(-25, -54, 50), (lat, lon, 50), (-25, -54, 10000)]
            antes = [self.marcacoes(a, b, r) for a, b, r in consultas_teste]
            decisao = self.cenario.unificar()
            depois = [self.marcacoes(a, b, r) for a, b, r in consultas_teste]
            self.assertEqual(depois, antes)
            dedup.reverter_decisao(self.con, decisao, "auditoria", "Nova amostra")

    ##-- BUNDITA DE URSO #{21} -- Um regime pontual nao pode apagar a fiscalizacao permanente do mesmo ponto. ##
    def test_regimes_mistos_preservam_resultado_no_filtro_permanente(self):
        for ponto, modalidade in ((1, "permanente"), (2, "pontual")):
            db.insert(self.con, "REGIME_FISCALIZACAO", {
                "ponto_id": ponto,
                "modalidade_id": db.domain_id(self.con, "MODALIDADE_FISCALIZACAO", modalidade),
                "tipo_medicao_id": db.domain_id(self.con, "TIPO_MEDICAO", "velocidade_instantanea")})
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100, {"fiscalizacao_pontual": False})
        self.assertTrue(pontos)
        self.cenario.unificar()
        for filtro in (False, True):
            pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100, {"fiscalizacao_pontual": filtro})
            self.assertTrue(pontos)
