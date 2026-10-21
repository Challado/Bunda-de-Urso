# -*- coding: utf-8 -*-
"""Endpoints da API de consulta (spec 10, 11, 12, 14).

Cobre /trechos (TRECHO ELEGIVEL), /operacoes, /equipamentos/{id},
/atualizacoes e /fontes/{id}, o envelope/erros comuns e os seis formatos.
CGI simulado, sem rede (spec 13.1).
"""
import json
import unittest

from core import config
from core import db as dbmod
from core.serializers import campos, edifact_ser, dif_ser
from web import nucleo
from tests.common import banco_com_antt


def _popular(dbpath):
    """Insere trecho elegivel, operacoes e uma verificacao metrologica."""
    conn = dbmod.connect(dbpath)
    try:
        via_id = dbmod.query_one(
            conn, "SELECT id FROM VIA WHERE codigo='BR-277'")["id"]
        reg_id = dbmod.query_one(
            conn, "SELECT id FROM REGISTRO_FONTE ORDER BY id LIMIT 1")["id"]
        q_oficial = dbmod.domain_id(conn, "QUALIDADE_POSICAO", "oficial")
        sent = dbmod.domain_id(conn, "SENTIDO", "crescente")

        trecho_id = dbmod.insert(conn, "TRECHO_ELEGIVEL", {
            "via_id": via_id, "km_inicio": 100.0, "km_fim": 120.0,
            "sentido_id": sent, "criterio_inclusao": "rodovia com historico",
            "vigencia_inicio": "2026-01-01", "vigencia_fim": "2026-12-31",
            "situacao": "vigente", "registro_fonte_id": reg_id})
        conn.execute("INSERT INTO TRECHO_MUNICIPIO (trecho_id, municipio_id) "
                     "VALUES (?,?)", (trecho_id, "4104808"))
        pos = dbmod.insert(conn, "POSICAO_GEOGRAFICA", {
            "latitude": -24.9500, "longitude": -53.4500,
            "qualidade_posicao_id": q_oficial, "registro_fonte_id": reg_id})
        conn.execute("INSERT INTO TRECHO_VERTICE (trecho_id, ordem, posicao_id) "
                     "VALUES (?,?,?)", (trecho_id, 0, pos))

        mf_pontual = dbmod.domain_id(conn, "MODALIDADE_FISCALIZACAO", "pontual")
        so_conf = dbmod.domain_id(conn, "SITUACAO_OPERACAO", "confirmada")
        op_pos = dbmod.insert(conn, "POSICAO_GEOGRAFICA", {
            "latitude": -24.9555, "longitude": -53.4552,
            "qualidade_posicao_id": q_oficial, "registro_fonte_id": reg_id})
        ponto_id = dbmod.query_one(
            conn, "SELECT id FROM PONTO_FISCALIZACAO ORDER BY id LIMIT 1")["id"]
        op_id = dbmod.insert(conn, "OPERACAO_FISCALIZACAO", {
            "modalidade_id": mf_pontual, "situacao_operacao_id": so_conf,
            "posicao_id": op_pos, "via_id": via_id, "municipio_id": "4104808",
            "ponto_id": ponto_id,
            "km": 580.5, "descricao": "operacao pontual",
            "inicio_em": "2026-10-01T08:00:00+00:00",
            "fim_em": "2026-10-01T12:00:00+00:00",
            "publicado_em": "2026-09-25T10:00:00+00:00",
            "registro_fonte_id": reg_id})
        eq_id = dbmod.query_one(
            conn, "SELECT id FROM EQUIPAMENTO ORDER BY id LIMIT 1")["id"]
        conn.execute("INSERT INTO OPERACAO_EQUIPAMENTO (operacao_id, "
                     "equipamento_id) VALUES (?,?)", (op_id, eq_id))

        # operacao SEM data/hora oficial: nao pode ser apresentada como
        # confirmada nem ganhar horario inventado.
        dbmod.insert(conn, "OPERACAO_FISCALIZACAO", {
            "modalidade_id": dbmod.domain_id(
                conn, "MODALIDADE_FISCALIZACAO", "itinerante"),
            "situacao_operacao_id": dbmod.domain_id(
                conn, "SITUACAO_OPERACAO", "planejada"),
            "registro_fonte_id": reg_id})

        dbmod.insert(conn, "VERIFICACAO_METROLOGICA", {
            "equipamento_id": eq_id,
            "tipo_verificacao_id": dbmod.domain_id(
                conn, "TIPO_VERIFICACAO", "periodica"),
            "resultado_id": dbmod.domain_id(
                conn, "RESULTADO_VERIFICACAO", "conforme"),
            "data_verificacao": "2025-01-01", "validade_ate": "2026-01-01",
            "numero_certificado": "CERT-1", "registro_fonte_id": reg_id})
        conn.commit()
    finally:
        conn.close()


class TestEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db, cls.resumo = banco_com_antt()
        _popular(cls.db)

    def _req(self, caminho, query="", metodo="GET", corpo=b"", ctype=""):
        env = {
            "REQUEST_METHOD": metodo,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(corpo)),
            "CONTENT_TYPE": ctype,
            "PATH_INFO": caminho,
            "REQUEST_URI": caminho + (("?" + query) if query else ""),
            "SCRIPT_NAME": "",
        }
        return nucleo.handle_request(env, corpo)

    def _json(self, caminho, query=""):
        status, headers, corpo = self._req(caminho, query)
        self.assertEqual(status, 200, corpo if isinstance(corpo, str) else corpo)
        return json.loads(corpo), headers

    # -- /trechos ----------------------------------------------------------
    def test_trechos_json(self):
        doc, _h = self._json("/api/v1/trechos", "formato=json")
        self.assertTrue(doc["sucesso"])
        trechos = doc["resultado"]["trechos"]
        self.assertGreaterEqual(len(trechos), 1)
        t = trechos[0]
        self.assertEqual(t["id"], "T-1")
        self.assertEqual(t["indicador"], "pode_haver_fiscalizacao")
        self.assertIsNone(t["radar_instalado_confirmado"])   # nunca inferir true
        self.assertTrue(t["geometria_confirmada"])
        self.assertEqual(t["uf"], "PR")
        self.assertEqual(t["via"], "BR-277")
        self.assertEqual(doc["resultado"]["total_trechos"], len(trechos))

    def test_trechos_filtro_rodovia(self):
        doc, _h = self._json("/api/v1/trechos", "rodovia=BR-277&formato=json")
        self.assertEqual(doc["resultado"]["total_trechos"], 1)
        doc, _h = self._json("/api/v1/trechos", "rodovia=BR-000&formato=json")
        self.assertEqual(doc["resultado"]["total_trechos"], 0)

    def test_trechos_por_raio(self):
        doc, _h = self._json(
            "/api/v1/trechos",
            "lat=-24.95&lon=-53.45&raio=5000&formato=json")
        self.assertGreaterEqual(doc["resultado"]["total_trechos"], 1)
        doc, _h = self._json(
            "/api/v1/trechos",
            "lat=0&lon=0&raio=100&formato=json")
        self.assertEqual(doc["resultado"]["total_trechos"], 0)

    def test_trechos_txt(self):
        status, headers, corpo = self._req(
            "/api/v1/trechos", "formato=txt&delimitador=%7C")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        linhas = [l for l in corpo.split("\n") if l]
        self.assertGreaterEqual(len(linhas), 1)
        for ln in linhas:
            self.assertEqual(len(ln.split("|")), len(nucleo.COLS_TRECHOS))

    def test_trechos_edifact_e_dif(self):
        status, headers, corpo = self._req("/api/v1/trechos", "formato=edifact")
        self.assertEqual(status, 200)
        self.assertIn("EDIFACT", headers["Content-Type"])
        rows = edifact_ser.loads(corpo)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), len(nucleo.COLS_TRECHOS))
        status, headers, corpo = self._req("/api/v1/trechos", "formato=dif")
        self.assertEqual(status, 200)
        cols, rows = dif_ser.loads(corpo)
        self.assertEqual(cols, list(nucleo.COLS_TRECHOS))
        self.assertGreaterEqual(len(rows), 1)

    def test_trechos_metodo_nao_permitido(self):
        status, _h, _c = self._req("/api/v1/trechos", "", metodo="DELETE")
        self.assertEqual(status, 405)

    def test_trechos_post_equivale_a_get(self):
        corpo = json.dumps({"rodovia": "BR-277", "formato": "json"}).encode()
        status, _h, resp = self._req(
            "/api/v1/trechos", "", metodo="POST", corpo=corpo,
            ctype="application/json")
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(resp)["resultado"]["total_trechos"], 1)

    # -- /operacoes --------------------------------------------------------
    def test_operacoes_json(self):
        doc, _h = self._json("/api/v1/operacoes", "formato=json")
        ops = doc["resultado"]["operacoes"]
        self.assertGreaterEqual(len(ops), 2)
        por_id = {o["id"]: o for o in ops}
        self.assertIn("O-1", por_id)
        confirmada = por_id["O-1"]
        self.assertEqual(confirmada["evidencia_operacao"], "confirmada")
        self.assertEqual(confirmada["inicio_em"], "2026-10-01T08:00:00+00:00")
        self.assertEqual(confirmada["modalidade"], "pontual")
        self.assertTrue(confirmada["fiscalizacao_pontual"])
        self.assertEqual(confirmada["equipamentos_ids"], ["E-1"])
        # operacao sem data/hora oficial: nao inventa horario
        sem_data = [o for o in ops if o["inicio_em"] is None]
        self.assertGreaterEqual(len(sem_data), 1)
        self.assertEqual(sem_data[0]["evidencia_operacao"], "desconhecida")

    def test_operacoes_nao_inventa_de_trecho(self):
        # /trechos NAO cria operacao ficticia (colecao vazia, nao inventada)
        doc, _h = self._json("/api/v1/trechos", "formato=json")
        self.assertEqual(doc["resultado"]["operacoes"], [])
        self.assertEqual(doc["resultado"]["total_operacoes"], 0)
        # /operacoes so devolve o que existe no banco
        conn = dbmod.connect(self.db)
        try:
            n = dbmod.scalar(conn, "SELECT count(*) FROM OPERACAO_FISCALIZACAO")
        finally:
            conn.close()
        doc, _h = self._json("/api/v1/operacoes", "formato=json")
        self.assertEqual(doc["resultado"]["total_operacoes"], n)

    def test_operacoes_filtro_temporal_em(self):
        doc, _h = self._json(
            "/api/v1/operacoes", "em=2026-10-01T10:00:00&formato=json")
        ids = [o["id"] for o in doc["resultado"]["operacoes"]]
        self.assertIn("O-1", ids)

    def test_operacoes_por_raio(self):
        doc, _h = self._json(
            "/api/v1/operacoes",
            "lat=-24.9555&lon=-53.4552&raio=1000&formato=json")
        self.assertGreaterEqual(doc["resultado"]["total_operacoes"], 1)

    def test_operacoes_txt(self):
        status, headers, corpo = self._req(
            "/api/v1/operacoes", "formato=txt&delimitador=%7C")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        for ln in [l for l in corpo.split("\n") if l]:
            self.assertEqual(len(ln.split("|")), len(nucleo.COLS_OPERACOES))

    # -- /equipamentos/{id} ------------------------------------------------
    def test_equipamento_json(self):
        doc, _h = self._json("/api/v1/equipamentos/E-1")
        eq = doc["resultado"]["equipamento"]
        self.assertEqual(eq["id"], "E-1")
        self.assertIn(eq["tipo_radar"], ("fixo", "portatil", "movel",
                                         "desconhecido"))
        self.assertEqual(len(eq["instalacoes"]), 1)
        self.assertEqual(eq["instalacoes"][0]["ponto_id"], "P-1")
        # verificacao metrologica vencida (validade 2026-01-01)
        ver = eq["verificacoes_metrologicas"]
        self.assertEqual(len(ver), 1)
        self.assertEqual(ver[0]["situacao_metrologica_derivada"], "vencida")

    def test_equipamento_nao_encontrado(self):
        status, _h, _c = self._req("/api/v1/equipamentos/E-99999")
        self.assertEqual(status, 404)

    def test_detalhe_radar_preserva_metrologia_do_endpoint_do_instrumento(self):
        equipamento, _ = self._json("/api/v1/equipamentos/E-1")
        ponto, _ = self._json("/api/v1/radares/P-1")
        eq = equipamento["resultado"]["equipamento"]
        self.assertEqual(ponto["resultado"]["pontos"][0]["equipamentos"][0], eq)
        ver = eq["verificacoes_metrologicas"][0]
        self.assertEqual(ver["numero_certificado"], "CERT-1")
        self.assertTrue(ver["fonte_registro_id"])
        self.assertIn("ANTT", ver["fonte"]["nome"])
        # Uma verificacao atribuida a outra fonte nao e inventada como Inmetro.
        self.assertNotIn("INMETRO", ver["fonte"]["nome"])

    def test_equipamento_metodo_nao_permitido(self):
        status, _h, _c = self._req("/api/v1/equipamentos/E-1", "",
                                   metodo="POST")
        self.assertEqual(status, 405)

    def test_equipamento_txt(self):
        status, headers, corpo = self._req(
            "/api/v1/equipamentos/E-1", "formato=txt")
        self.assertEqual(status, 200)
        linhas = [l for l in corpo.split("\n") if l]
        self.assertEqual(len(linhas), 1)
        self.assertEqual(len(linhas[0].split("|")), len(nucleo.COLS_EQUIPAMENTO))

    # -- /atualizacoes -----------------------------------------------------
    def test_atualizacoes_json(self):
        doc, _h = self._json("/api/v1/atualizacoes", "formato=json")
        ats = doc["resultado"]["atualizacoes"]
        self.assertGreaterEqual(len(ats), 1)
        self.assertIsNotNone(doc["resultado"]["total_atualizacoes"])
        self.assertGreaterEqual(len(doc["resultado"]["snapshots"]), 1)
        a = ats[0]
        self.assertIn("iniciada_em", a)
        self.assertIn("status", a)
        self.assertIn("fonte", a)

    def test_atualizacoes_metodo_nao_permitido(self):
        status, _h, _c = self._req("/api/v1/atualizacoes", "", metodo="POST")
        self.assertEqual(status, 405)

    def test_atualizacoes_txt(self):
        status, headers, corpo = self._req(
            "/api/v1/atualizacoes", "formato=txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        for ln in [l for l in corpo.split("\n") if l]:
            self.assertEqual(len(ln.split("|")), len(nucleo.COLS_ATUALIZACOES))

    # -- /fontes/{id} ------------------------------------------------------
    def test_fonte_por_id(self):
        doc, _h = self._json("/api/v1/fontes/S-1")
        self.assertTrue(doc["sucesso"])
        self.assertEqual(doc["resultado"]["fonte"]["id"], "S-1")

    def test_fonte_inexistente(self):
        status, _h, _c = self._req("/api/v1/fontes/S-99999")
        self.assertEqual(status, 404)

    # -- /radares com operacoes e trechos ----------------------------------
    def test_radares_inclui_operacoes_publicadas(self):
        doc, _h = self._json(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=json")
        self.assertGreaterEqual(doc["resultado"]["total_operacoes"], 1)
        self.assertTrue(doc["resultado"]["operacoes"])

    def test_radares_edifact_valido(self):
        status, headers, corpo = self._req(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=edifact")
        self.assertEqual(status, 200)
        self.assertIn("EDIFACT", headers["Content-Type"])
        self.assertTrue(corpo.startswith("UNB+"))
        segs = edifact_ser._split_segmentos(corpo)
        unh_i = next(i for i, s in enumerate(segs) if s.startswith("UNH+"))
        unt_i = next(i for i, s in enumerate(segs) if s.startswith("UNT+"))
        self.assertEqual(int(segs[unt_i].split("+")[1]), unt_i - unh_i + 1)
        rows = edifact_ser.loads(corpo)
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(len(r), 32)

    def test_radares_dif_valido(self):
        status, headers, corpo = self._req(
            "/api/v1/radares",
            "lat=-24.9555&lon=-53.4552&raio=5000&formato=dif")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        cols, rows = dif_ser.loads(corpo)
        self.assertEqual(cols, list(campos.TXT_COLUMNS))
        self.assertGreaterEqual(len(rows), 1)
        for r in rows:
            self.assertEqual(len(r), 32)

    # -- /ajuda ------------------------------------------------------------
    def test_ajuda_lista_todos_endpoints(self):
        doc, _h = self._json("/api/v1/ajuda", "formato=json")
        for ep in ("/api/v1/radares", "/api/v1/trechos", "/api/v1/operacoes",
                   "/api/v1/equipamentos/{id}", "/api/v1/fontes",
                   "/api/v1/fontes/{id}", "/api/v1/atualizacoes",
                   "/api/v1/ajuda", "/api/v1/status", "/health/live",
                   "/health/ready"):
            self.assertIn(ep, doc["endpoints"])
        self.assertEqual(len(doc["txt_colunas_ordem"]), 32)
        self.assertEqual(doc["txt_colunas_ordem"][0], "id")
        self.assertEqual(doc["txt_colunas_ordem"][31],
                         "quantidade_faixas_declarada")
        self.assertIn("/api/v1/trechos", doc["colunas_por_endpoint"])

    def test_ajuda_texto_lista_endpoints(self):
        status, _h, corpo = self._req("/api/v1/ajuda", "formato=txt")
        self.assertEqual(status, 200)
        self.assertIn("ORDEM CANONICA TXT", corpo)
        for ep in ("/api/v1/trechos", "/api/v1/operacoes",
                   "/api/v1/equipamentos/{id}", "/api/v1/atualizacoes"):
            self.assertIn(ep, corpo)

    def test_ajuda_seis_formatos(self):
        esperado = {
            "json": "application/json", "ndjson": "application/x-ndjson",
            "xml": "application/xml", "txt": "text/plain",
            "edifact": "application/EDIFACT", "dif": "text/plain",
        }
        for fmt, ctype in esperado.items():
            status, headers, corpo = self._req(
                "/api/v1/ajuda", "formato=" + fmt)
            self.assertEqual(status, 200, fmt)
            self.assertIn(ctype, headers["Content-Type"], fmt)
            self.assertTrue(corpo, fmt)
        # edi e alias de edifact
        status, headers, _c = self._req("/api/v1/ajuda", "formato=edi")
        self.assertEqual(status, 200)
        self.assertIn("EDIFACT", headers["Content-Type"])

    def test_formato_invalido_novo_endpoint(self):
        status, _h, _c = self._req("/api/v1/trechos", "formato=nope")
        self.assertEqual(status, 400)

    def test_rota_desconhecida(self):
        status, _h, _c = self._req("/api/v1/inexistente", "formato=json")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
