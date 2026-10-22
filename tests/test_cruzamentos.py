"""Revisao apos chegada de fonte nova, pela API real e banco temporario."""
from concurrent.futures import ThreadPoolExecutor
import shutil
import unittest
from core import config, db, governanca as gov
from coletor.fontes.base_lwb import ColetorBaseLWB
from tests.test_governanca import BaseGov


class TestCruzamentos(BaseGov):
    def setUp(self):
        super().setUp()
        self.token = self._token_cookie("moderador")
        self.headers = {"HTTP_X_API_TOKEN": self.token}

    def colab(self, lat=-23.55, lon=-46.63, verificar=False):
        status, _, corpo = self._req("POST", "/api/v1/radares/submeter",
                                     {"latitude": lat, "longitude": lon, "velocidade_geral": 40})
        self.assertEqual(status, 201, corpo)
        pid = int(corpo["resultado"]["cadastros"][0]["id"].split("-")[1])
        if verificar:
            self.assertEqual(self._req("POST", "/api/v1/gestao/radar/P-%d/verificar" % pid,
                                       {}, headers=self.headers)[0], 200)
        return pid

    def cruzar(self, pid):
        resposta = self._req("POST", "/api/v1/gestao/radar/P-%d/cruzar" % pid,
                             {}, headers=self.headers)
        self.assertEqual(resposta[0], 200, resposta[2])
        return resposta[2]

    def lote(self, dados=None):
        resposta = self._req("POST", "/api/v1/gestao/cruzamentos", dados or {}, headers=self.headers)
        self.assertEqual(resposta[0], 200, resposta[2])
        return resposta[2]["resultado"]

    def test_fonte_nova_recruza_verificado_sem_reenvio_e_preserva_origens(self):
        pid = self.colab(verificar=True)
        self.assertEqual(self.cruzar(pid)["resultado"]["status"], "sem_correspondencias")
        self._oficial(-23.5501, -46.6301, "OFICIAL-NOVO")
        oficial = self._novo_id()
        primeiro = self.cruzar(pid)
        r = primeiro["resultado"]
        self.assertEqual(r["novas_correspondencias"], 1)
        self.assertEqual(r["candidatos"][0]["id"], "P-%d" % oficial)
        self.assertIn("ANTT", r["candidatos"][0]["fontes"][0]["nome"])
        self.assertEqual(primeiro["radar"]["governanca"]["verificacao_status"], "verificado")
        self.assertEqual(primeiro["radar"]["governanca"]["procedencia"], "colaborativo")
        segundo = self.cruzar(pid)["resultado"]
        self.assertEqual(segundo["novas_correspondencias"], 0)
        con = db.connect(config.DB_PATH)
        try:
            self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM CORRESPONDENCIA_PONTO"), 1)
            self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 2)
            self.assertEqual(db.scalar(con, "SELECT latitude FROM POSICAO_GEOGRAFICA pos "
                                      "JOIN PONTO_FISCALIZACAO p ON p.posicao_id=pos.id WHERE p.id=?", (pid,)), -23.55)
            hist = gov.historico(con, pid)
            self.assertEqual(hist[-1]["campos"]["cruzamento_oficial"]["novas_correspondencias"], 0)
            self.assertEqual(hist[-1]["quem"], "t")
        finally:
            con.close()

    def test_ambiguidades_e_divergencias_ficam_para_revisao(self):
        pid = self.colab()
        self._oficial(-23.5501, -46.6301, "OF-1")
        self._oficial(-23.5502, -46.6302, "OF-2")
        con = db.connect(config.DB_PATH)
        try:
            gov.editar_radar(con, self._novo_id(), {"velocidade_geral": 80}, {})
        finally:
            con.close()
        r = self.cruzar(pid)["resultado"]
        self.assertEqual(len(r["candidatos"]), 2)
        self.assertTrue(any("Velocidade" in d for c in r["candidatos"] for d in c["divergencias"]))
        self.assertTrue(all(c["status"] == "corroborado" and c["resolvido_em"] is None
                            for c in r["candidatos"]))
        for ponto in [pid, self._novo_id()]:
            self.assertEqual(self._req("GET", "/api/v1/radares/P-%d" % ponto)[0], 200)

    def test_chamadas_simultaneas_nao_duplicam_sugestao_nem_falham(self):
        pid = self.colab(verificar=True)
        self._oficial(-23.5501, -46.6301, "OFICIAL-NOVO")
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: self.cruzar(pid), range(2)))
        self.assertEqual(sum(r["resultado"]["novas_correspondencias"] for r in resultados), 1)
        self.assertTrue(all(len(r["radar"]["correspondencias"]) == 1 for r in resultados))

    @unittest.skipUnless(shutil.which("pdftotext"), "poppler-utils necessario")
    def test_caseara_verificado_antes_da_importacao_do_pdf_real_ageto(self):
        from coletor.fontes.ageto_to import ColetorAGETOTO
        from tests.test_ageto_to import PDF, municipios_to
        pid = self.colab(-9.265218, -49.956872, verificar=True)
        con = db.connect(config.DB_PATH)
        try:
            municipios_to(con)
            ColetorAGETOTO(conn=con).sincronizar(str(PDF))
        finally:
            con.close()
        doc = self.cruzar(pid)
        self.assertEqual(len(doc["resultado"]["candidatos"]), 1)
        candidato = doc["resultado"]["candidatos"][0]
        self.assertEqual((candidato["via"], candidato["km"]), ("TO-080", 251))
        self.assertAlmostEqual(candidato["distancia_metros"], 61.351, places=2)
        self.assertIn("AGETO", candidato["fontes"][0]["nome"])
        self.assertEqual(doc["radar"]["governanca"]["verificacao_status"], "verificado")
        self.assertEqual(doc["radar"]["localizacao"]["latitude"], -9.265218)

    def test_base_propria_sem_cadeia_oficial_nao_e_fonte_oficial(self):
        pid = self.colab()
        con = db.connect(config.DB_PATH)
        try:
            ColetorBaseLWB(conn=con).ingerir_registros([
                {"identificador": "PROPRIO", "latitude": -23.5501, "longitude": -46.6301}], publicar=False)
        finally:
            con.close()
        self.assertEqual(self.cruzar(pid)["resultado"]["candidatos"], [])

    def test_sem_gps_e_exclusao_de_removidos_desabilitados_no_lote(self):
        sem_gps, removido, desabilitado = [self.colab(-23.55-i/10) for i in range(3)]
        con = db.connect(config.DB_PATH)
        try:
            con.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=NULL WHERE id=?", (sem_gps,))
            gov.remover_radar(con, removido, {}, "excluido")
            gov.desabilitar_radar(con, desabilitado, {}, "fora de uso")
        finally:
            con.close()
        r = self.lote()
        self.assertEqual(r["processados"], 1)
        self.assertEqual(r["resultados"][0]["status"], "sem_coordenadas")
        for pid in (removido, desabilitado):
            self.assertEqual(self._req("POST", "/api/v1/gestao/radar/P-%d/cruzar" % pid,
                                       {}, headers=self.headers)[0], 409)

    def test_lote_pagina_verificados_e_nao_verificados_sem_incluir_cadastros_posteriores(self):
        ids = [self.colab(-23.55-i/10, verificar=(i == 1)) for i in range(3)]
        r = self.lote({"limite": 1})
        recebidos = [r["resultados"][0]["id"]]
        self.colab(-24.1)
        while r["proximo_cursor"] is not None:
            r = self.lote({"limite": 1, "cursor": r["proximo_cursor"], "ate_id": r["ate_id"]})
            recebidos.extend(x["id"] for x in r["resultados"])
        self.assertEqual(recebidos, ["P-%d" % pid for pid in ids])

    def test_decisao_humana_preservada_ao_recruzar(self):
        pid = self.colab(verificar=True)
        self._oficial(-23.5501, -46.6301, "OFICIAL")
        r = self.cruzar(pid)["resultado"]
        cid = r["candidatos"][0]["correspondencia_id"]
        rota = "/api/v1/gestao/correspondencias/%d" % cid
        self.assertEqual(self._req("POST", rota,
            {"status": "colaborativo_vence", "motivo": "posição conferida em campo"}, headers=self.headers)[0], 200)
        depois = self.cruzar(pid)["resultado"]
        self.assertEqual(depois["novas_correspondencias"], 0)
        self.assertEqual(depois["candidatos"][0]["status"], "colaborativo_vence")
        self.assertIsNotNone(depois["candidatos"][0]["resolvido_em"])
        self.assertEqual(self._req("POST", rota, {"status": "oficial_vence"}, headers=self.headers)[0], 409)

    def test_confirmar_oficial_preserva_historico_e_documentos_sem_duplicar(self):
        pid = self.colab(verificar=True)
        self._oficial(-23.5501, -46.6301, "OFICIAL")
        oficial = self._novo_id()
        cid = self.cruzar(pid)["resultado"]["candidatos"][0]["correspondencia_id"]
        rota = "/api/v1/gestao/correspondencias/%d" % cid
        for _ in range(2):
            self.assertEqual(self._req("POST", rota, {"status": "oficial_vence"}, headers=self.headers)[0], 200)
        self.assertEqual(self._req("GET", "/api/v1/radares/P-%d" % oficial)[0], 200)
        self.assertEqual(self._req("GET", "/api/v1/radares/P-%d" % pid)[0], 404)
        con = db.connect(config.DB_PATH)
        try:
            self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 2)
            self.assertTrue(gov.historico(con, pid))
            self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM REGISTRO_FONTE"), 2)
        finally:
            con.close()

    def test_oficial_removido_nao_pode_ser_confirmado_nem_sugerido(self):
        pid = self.colab()
        self._oficial(-23.5501, -46.6301, "OFICIAL")
        oficial = self._novo_id()
        cid = self.cruzar(pid)["resultado"]["candidatos"][0]["correspondencia_id"]
        self._req("POST", "/api/v1/gestao/radar/P-%d/remover" % oficial,
                  {"motivo": "registro retirado"}, headers=self.headers)
        self.assertEqual(self._req("POST", "/api/v1/gestao/correspondencias/%d" % cid,
                                   {"status": "oficial_vence"}, headers=self.headers)[0], 409)
        self.assertEqual(self.cruzar(pid)["resultado"]["candidatos"], [])

    def test_coordenadas_alteradas_invalidam_sugestao_antiga_sem_apagar_historico(self):
        pid = self.colab(verificar=True)
        self._oficial(-23.5501, -46.6301, "OFICIAL")
        oficial = self._novo_id()
        cid = self.cruzar(pid)["resultado"]["candidatos"][0]["correspondencia_id"]
        status, _, corpo = self._req("PATCH", "/api/v1/gestao/radar/P-%d" % oficial,
                                    {"latitude": -24.5, "longitude": -47.5}, headers=self.headers)
        self.assertEqual(status, 200, corpo)
        doc = self.cruzar(pid)
        self.assertEqual(doc["resultado"]["candidatos"], [])
        vinculo = doc["radar"]["correspondencias"][0]
        self.assertEqual(vinculo["id"], cid)
        self.assertFalse(vinculo["oficial"]["disponivel"])
        self.assertGreater(vinculo["oficial"]["distancia_metros"], 100000)
        self.assertEqual(self._req("POST", "/api/v1/gestao/correspondencias/%d" % cid,
                                   {"status": "oficial_vence"}, headers=self.headers)[0], 409)

    def test_autorizacao_metodo_e_parametros_do_lote(self):
        pid = self.colab()
        for rota in ("/api/v1/gestao/cruzamentos", "/api/v1/gestao/radar/P-%d/cruzar" % pid):
            self.assertEqual(self._req("POST", rota, {})[0], 401)
            token = self._token_cookie("contribuidor")
            self.assertEqual(self._req("POST", rota, {}, headers={"HTTP_X_API_TOKEN": token})[0], 403)
            self.assertEqual(self._req("GET", rota, headers=self.headers)[0], 405)
        for dados in ({"limite": 0}, {"limite": 21}, {"cursor": -1}, {"cursor": True},
                      {"ate_id": "3"}, {"cursor": 2**64}, {"sql": "qualquer"}, []):
            self.assertEqual(self._req("POST", "/api/v1/gestao/cruzamentos", dados, headers=self.headers)[0], 422)
