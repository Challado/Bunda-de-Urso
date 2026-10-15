# -*- coding: utf-8 -*-
"""Regressoes de coleta, governanca e prontidao em banco temporario."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coletor.fontes.antt import ColetorANTT
from coletor.fontes.base_lwb import ColetorBaseLWB
from coletor import tick
from core import config, consultas, db, governanca
from tests.common import ANTT_FIXTURE
from web import nucleo
from tools.auditar_deduplicacao import auditar


class TestOperacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bundita-regressao-")
        self.addCleanup(self.tmp.cleanup)
        self.config = patch.multiple(config, DATA_DIR=self.tmp.name,
                                     RAW_DIR=self.tmp.name + "/raw",
                                     STAGING_DIR=self.tmp.name + "/staging",
                                     DB_PATH=self.tmp.name + "/radar.sqlite3")
        self.config.start()
        self.addCleanup(self.config.stop)
        self.con = db.connect()
        self.addCleanup(self.con.close)
        governanca.garantir_esquema(self.con)

    def coletar(self, arquivo=ANTT_FIXTURE):
        return ColetorANTT(conn=self.con).sincronizar(arquivo)

    def request(self, caminho, dados=None, query="", xff="198.51.100.1"):
        corpo = json.dumps(dados).encode() if dados is not None else b""
        return nucleo.handle_request({
            "REQUEST_METHOD": "POST" if dados is not None else "GET",
            "PATH_INFO": caminho, "QUERY_STRING": query,
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(corpo)),
            "REMOTE_ADDR": "203.0.113.9", "HTTP_X_FORWARDED_FOR": xff}, corpo)

    ##-- BUNDITA DE URSO #{9} -- Falha inesperada precisa abortar e permitir nova tentativa do mesmo arquivo. ##
    def test_erro_do_programa_nao_e_rejeicao_silenciosa(self):
        with patch("coletor.fontes.normalizacao.inserir_normalizado", side_effect=RuntimeError("falha controlada")):
            with self.assertRaises(RuntimeError):
                self.coletar()
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM SNAPSHOT_PUBLICADO"), 0)
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 0)
        self.assertEqual(db.scalar(self.con, "SELECT status FROM EXECUCAO_COLETA"), "erro")
        self.assertEqual(self.coletar()["criados"], 3)

    def test_lote_rejeitado_tem_causas_e_nao_publica(self):
        with patch("coletor.fontes.normalizacao.inserir_normalizado", side_effect=ValueError("dado invalido")):
            resumo = self.coletar()
        self.assertEqual(resumo["status"], "erro")
        self.assertIsNone(resumo["snapshot_id"])
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM ERRO_VALIDACAO"), 4)
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM REGISTRO_FONTE WHERE status_validacao='rejeitado'"), 4)
        self.assertEqual(db.scalar(self.con, "SELECT erro_codigo FROM EXECUCAO_COLETA"), "lote_sem_registros_validos")
        self.assertEqual(self.coletar()["criados"], 3)

    def test_falha_ao_publicar_desfaz_normalizacao(self):
        coletor = ColetorANTT(conn=self.con)
        with patch.object(coletor, "publicar_snapshot", side_effect=RuntimeError("publicacao falhou")):
            with self.assertRaises(RuntimeError):
                coletor.sincronizar(ANTT_FIXTURE)
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 0)
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM SNAPSHOT_PUBLICADO"), 0)

    def test_lote_vazio_preserva_snapshot_anterior(self):
        primeiro = self.coletar()
        vazio = Path(self.tmp.name, "vazio.json")
        vazio.write_text("[]")
        resumo = self.coletar(str(vazio))
        self.assertEqual(resumo["status"], "sem_dados")
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM SNAPSHOT_PUBLICADO"), 1)
        self.assertEqual(consultas.status_base(self.con)["snapshot_id"], primeiro["versao"])

    ##-- BUNDITA DE URSO #{13} -- O sync sem arquivo deve resolver o recurso de dados, nao baixar HTML do catalogo. ##
    def test_antt_resolve_url_no_caminho_do_cli(self):
        coletor = ColetorANTT(conn=self.con)
        with patch.object(coletor, "resolver_url", return_value="https://dados.antt.gov.br/radares.json"), \
                patch.object(coletor, "_baixar", return_value=Path(ANTT_FIXTURE).read_bytes()) as baixar:
            _, _, _, registros = coletor.carregar(None)
        baixar.assert_called_once_with("https://dados.antt.gov.br/radares.json")
        self.assertEqual(len(registros), 4)

    ##-- BUNDITA DE URSO #{11} -- Arquivo vazio ou corrompido nao pode responder ready. ##
    def test_health_ready_verifica_schema_e_leitura(self):
        for conteudo in (b"", b"isto nao e um banco"):
            outro = Path(self.tmp.name, "outro.sqlite3")
            outro.write_bytes(conteudo)
            with patch.object(config, "DB_PATH", str(outro)):
                self.assertEqual(self.request("/health/ready")[0], 503)
        self.assertEqual(self.request("/health/ready")[0], 200)

    ##-- BUNDITA DE URSO #{10} -- Resultado presente nao significa cobertura completa nem cache comprovadamente fresco. ##
    def test_api_nao_promete_completude_ou_atualidade(self):
        self.coletar()
        status, _, corpo = self.request("/api/v1/radares", query="lat=-24.9555&lon=-53.4552&raio=5000")
        self.assertEqual(status, 200)
        doc = json.loads(corpo)
        self.assertEqual(doc["resultado"]["status"], "parcial")
        self.assertEqual(doc["base"]["status_cache"], "desconhecido")

    ##-- BUNDITA DE URSO #{12} -- IP fornecido pelo cliente nao pode alterar sua quota sem proxy confiavel. ##
    def test_xff_nao_contorna_rate_limit(self):
        with patch.object(config, "TRUSTED_PROXIES", ()), patch.object(config, "SUBMISSAO_LIMITE", 2):
            for i in range(2):
                status, _, _ = self.request("/api/v1/radares/submeter", {
                    "latitude": -23.55, "longitude": -46.63}, xff="198.51.100.%d" % i)
                self.assertEqual(status, 201)
            self.assertEqual(self.request("/api/v1/radares/submeter", {
                "latitude": -23.55, "longitude": -46.63}, xff="198.51.100.99")[0], 429)

    def test_proxy_confiavel_le_o_primeiro_salto_nao_confiavel(self):
        with patch.object(config, "TRUSTED_PROXIES", ("10.0.0.0/8",)):
            ip = nucleo._ip_requisicao({"REMOTE_ADDR": "10.0.0.1",
                                       "HTTP_X_FORWARDED_FOR": "192.0.2.99, 203.0.113.7, 10.0.0.2"})
        self.assertEqual(ip, "203.0.113.7")

    ##-- BUNDITA DE URSO #{8} -- Outra rodovia e velocidade publicas nao podem substituir o oficial por proximidade. ##
    def test_contribuicao_perto_do_oficial_nao_e_verificada(self):
        self.coletar()
        resultado = governanca.submeter(self.con, {"latitude": -24.9555,
            "longitude": -53.4552, "via": "BR-999", "velocidade_leves": 10})
        self.assertEqual(resultado["corroborados"], 0)
        pid = db.scalar(self.con, "SELECT MAX(id) FROM PONTO_FISCALIZACAO")
        self.assertEqual(db.scalar(self.con, "SELECT verificacao_status FROM PONTO_FISCALIZACAO WHERE id=?", (pid,)), "nao_verificado")
        pontos, _ = consultas.buscar_pontos(self.con, -24.9555, -53.4552, 100)
        self.assertIn("P-1", [p["id"] for p in pontos])
        self.assertIn("P-%d" % pid, [p["id"] for p in pontos])
        cid = db.scalar(self.con, "SELECT id FROM CORRESPONDENCIA_PONTO")
        ctx = {"rotulo": "moderador", "escopo": "moderador"}
        with self.assertRaises(governanca.GovernancaError):
            governanca.resolver_correspondencia(self.con, cid, "colaborativo_vence", ctx)
        governanca.resolver_correspondencia(self.con, cid, "colaborativo_vence", ctx, "Documento confirma correcao")
        pontos, _ = consultas.buscar_pontos(self.con, -24.9555, -53.4552, 100)
        self.assertNotIn("P-1", [p["id"] for p in pontos])

    def test_cadastro_proprio_nao_e_prova_de_fonte_oficial(self):
        ColetorBaseLWB(conn=self.con).ingerir_registros([{
            "latitude": -23.55, "longitude": -46.63}], publicar=False)
        governanca.submeter(self.con, {"latitude": -23.55, "longitude": -46.63})
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM CORRESPONDENCIA_PONTO"), 0)

    ##-- BUNDITA DE URSO #{19} -- IDs de anonimos nao podem atualizar pontos da ingestao autenticada ou de outro envio. ##
    def test_identificador_publico_nao_sobrescreve_base_autenticada(self):
        ColetorBaseLWB(conn=self.con).ingerir_registros([{
            "latitude": -23.55, "longitude": -46.63, "identificador": "INTERNO-1"}], publicar=False)
        original = self.con.execute("SELECT p.id, p.procedencia, pos.latitude FROM PONTO_FISCALIZACAO p "
                                    "JOIN POSICAO_GEOGRAFICA pos ON pos.id=p.posicao_id").fetchone()
        self.assertEqual(original["procedencia"], "cadastro_proprio")
        for lat in (-23.56, -23.57):
            governanca.submeter(self.con, {"latitude": lat, "longitude": -46.63,
                                          "identificador": "INTERNO-1"})
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 3)
        latitude = db.scalar(self.con, "SELECT pos.latitude FROM PONTO_FISCALIZACAO p "
                             "JOIN POSICAO_GEOGRAFICA pos ON pos.id=p.posicao_id WHERE p.id=?", (original["id"],))
        self.assertEqual(latitude, original["latitude"])

    ##-- BUNDITA DE URSO #{8} -- Falha no filtro de governanca precisa interromper a consulta, nao expor registros ocultos. ##
    def test_filtro_de_governanca_nao_falha_aberto(self):
        self.coletar()
        with patch("core.governanca.clausulas_consulta", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                consultas.buscar_pontos(self.con, -24.9555, -53.4552, 100)

    ##-- BUNDITA DE URSO #{15} -- Paginacao precisa considerar o filtro temporal antes de calcular totais. ##
    def test_filtro_pontual_e_aplicado_antes_da_paginacao(self):
        self.coletar()
        permanente = db.domain_id(self.con, "MODALIDADE_FISCALIZACAO", "permanente")
        pontual = db.domain_id(self.con, "MODALIDADE_FISCALIZACAO", "pontual")
        self.con.execute("UPDATE REGIME_FISCALIZACAO SET modalidade_id=? WHERE ponto_id=1", (permanente,))
        self.con.execute("UPDATE REGIME_FISCALIZACAO SET modalidade_id=? WHERE ponto_id=2", (pontual,))
        pontos, meta = consultas.buscar_pontos(self.con, -24.9555, -53.4552, 5000,
                                               {"fiscalizacao_pontual": True}, limite=1)
        self.assertEqual([p["id"] for p in pontos], ["P-2"])
        self.assertEqual(meta["total_pontos"], 1)
        self.assertIsNone(meta["proximo_cursor"])

    def test_total_de_instrumentos_nao_e_so_da_pagina(self):
        self.coletar()
        pontos, meta = consultas.buscar_pontos(self.con, -24.9555, -53.4552, 5000, limite=1)
        self.assertEqual(len(pontos), 1)
        self.assertEqual(meta["total_equipamentos"], 2)

    ##-- BUNDITA DE URSO #{16} -- Sucesso sem mudanca nao deve acumular backoff de falha. ##
    def test_sem_mudanca_respeita_intervalo_normal(self):
        self.assertEqual(tick.espera_s(60, [{"status": "sem_mudanca"}] * 4), 60)

    ##-- BUNDITA DE URSO #{4} -- A auditoria precisa provar que gera candidatos apenas na copia. ##
    def test_auditoria_de_regra_nao_muda_banco_original(self):
        self.coletar()
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        caminho = Path(config.DB_PATH)
        antes = hashlib.sha256(caminho.read_bytes()).digest()
        resultado = auditar(caminho)
        self.assertEqual(resultado["registros"], 4)
        self.assertEqual(resultado["decisoes_aplicadas_nesta_auditoria"], 0)
        self.assertGreater(resultado["candidatos_criados"], 0)
        self.assertTrue(resultado["conservacao"]["inventario_original_inalterado"])
        self.assertEqual(resultado["conservacao"]["marcacoes_com_gps_examinadas"], 3)
        self.assertEqual(resultado["conservacao"]["marcacoes_nao_representadas"], [])
        self.assertEqual(db.scalar(self.con, "SELECT COUNT(*) FROM CANDIDATO_DUPLICIDADE"), 0)
        self.assertEqual(hashlib.sha256(caminho.read_bytes()).digest(), antes)

    ##-- BUNDITA DE URSO #{20} -- Auditoria precisa acusar GPS oculto, em vez de aprovar apenas contagens de candidatos. ##
    def test_auditoria_acusa_perda_de_marcacao_na_projecao(self):
        self.coletar()
        with patch("core.consultas._linha_canonica", return_value=None):
            resultado = auditar(config.DB_PATH)
        self.assertEqual(len(resultado["conservacao"]["marcacoes_nao_representadas"]), 3)
