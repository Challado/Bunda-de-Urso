# -*- coding: utf-8 -*-
"""Cadastro simples/expert, persistencia e complemento sem alterar o oficial."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from core import config, consultas, db, governanca
from coletor.fontes.antt import ColetorANTT
from tests.test_governanca import BaseGov
from web import nucleo


class TestCadastro(BaseGov):
    dados = {"latitude": -24.9555, "longitude": -53.4552, "velocidade_geral": 60}

    def enviar(self, dados=None):
        resposta = self._req("POST", "/api/v1/radares/submeter",
                             self.dados if dados is None else dados)
        self.assertEqual(resposta[0], 201, resposta[2])
        return self._doc(resposta)["resultado"]

    def oficial(self, codigo="OFICIAL-1", latitude=-24.9556):
        with db.connect(config.DB_PATH) as con:
            resumo = ColetorANTT(conn=con).ingerir_registros([{
                "Codigo": codigo, "Latitude": latitude, "Longitude": -53.4552,
                "Rodovia": "BR-277", "Km": 580.5, "Pista": "Principal",
                "VelocidadeLeves": 80,
            }], publicar=False)
            return resumo["detalhes"][0]["ponto_id"]

    def test_tres_campos_persistem_e_aparecem_na_consulta(self):
        res = self.enviar()
        self.assertEqual(res["aceitos"], 1)
        cadastro = res["cadastros"][0]
        self.assertEqual(cadastro["proximidade"]["status"], "sem_candidatos")
        with db.connect(config.DB_PATH) as con:
            ponto = consultas.buscar_ponto_por_id(con, cadastro["id"])
            self.assertEqual(ponto["velocidade_geral_kmh"], 60)
            self.assertAlmostEqual(ponto["localizacao"]["latitude"], self.dados["latitude"])
            self.assertAlmostEqual(ponto["localizacao"]["longitude"], self.dados["longitude"])
            self.assertEqual(ponto["procedencia"], "colaborativo")
            self.assertEqual(ponto["verificacao_status"], "nao_verificado")
            self.assertEqual(ponto["dados_por_fonte"][0]["registros"][0]["dados_publicados"], self.dados)
            pontos, _ = consultas.buscar_pontos(con, self.dados["latitude"], self.dados["longitude"], 100)
            self.assertIn(cadastro["id"], [p["id"] for p in pontos])

    def test_cgi_sem_path_info_aceita_a_rota_da_pagina(self):
        body = json.dumps(self.dados).encode()
        resposta = nucleo.handle_request({
            "REQUEST_METHOD": "POST", "SCRIPT_NAME": "/api.pse",
            "QUERY_STRING": "rota=/api/v1/radares/submeter&formato=json",
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(body)),
        }, body)
        self.assertEqual(resposta[0], 201, resposta[2])
        self.assertEqual(self._doc(resposta)["resultado"]["aceitos"], 1)

    def test_complementa_lacunas_preserva_velocidade_coordenada_e_oficial(self):
        oficial = self.oficial()
        with db.connect(config.DB_PATH) as con:
            antes = consultas.buscar_ponto_por_id(con, oficial)
        res = self.enviar()
        cadastro = res["cadastros"][0]
        proximo = cadastro["proximidade"]
        self.assertEqual(proximo["campos_complementados"]["via"], "BR-277")
        self.assertEqual(proximo["campos_complementados"]["km"], 580.5)
        self.assertEqual(proximo["candidatos"][0]["id"], "P-%d" % oficial)
        self.assertEqual(res["correspondencias_sugeridas"], 1)
        with db.connect(config.DB_PATH) as con:
            self.assertEqual(consultas.buscar_ponto_por_id(con, oficial), antes)
            ponto = consultas.buscar_ponto_por_id(con, cadastro["id"])
            self.assertEqual(ponto["velocidade_geral_kmh"], 60)
            self.assertEqual(ponto["localizacao"]["via"]["codigo"], "BR-277")
            self.assertEqual(ponto["localizacao"]["latitude"], self.dados["latitude"])
            self.assertEqual(ponto["verificacao_status"], "nao_verificado")
            self.assertEqual(ponto["proveniencia_campos"]["complemento_proximidade"]["ponto_origem_id"], "P-%d" % oficial)
            # A publicacao do usuario continua contendo apenas o que ele enviou.
            self.assertEqual(ponto["dados_por_fonte"][0]["registros"][0]["dados_publicados"], self.dados)

    def test_varios_candidatos_nao_copiam_campos_automaticamente(self):
        self.oficial()
        self.oficial("OFICIAL-2", -24.9557)
        cadastro = self.enviar()["cadastros"][0]
        self.assertEqual(cadastro["proximidade"]["status"], "ambiguo")
        self.assertEqual(len(cadastro["proximidade"]["candidatos"]), 2)
        self.assertEqual(cadastro["proximidade"]["campos_complementados"], {})
        with db.connect(config.DB_PATH) as con:
            self.assertIsNone(consultas.buscar_ponto_por_id(con, cadastro["id"])["localizacao"]["via"]["codigo"])

    def test_busca_de_proximidade_nao_revarre_toda_a_origem_para_cada_ponto(self):
        oficial = self.oficial()
        with db.connect(config.DB_PATH) as con:
            registro = db.scalar(con, "SELECT registro_id FROM VINCULO_REGISTRO_PONTO WHERE ponto_id=?", (oficial,))
            artefato = db.scalar(con, "SELECT artefato_id FROM REGISTRO_FONTE WHERE id=?", (registro,))
            qualidade = db.domain_id(con, "QUALIDADE_POSICAO", "oficial")
            # Muitos pontos oficiais fora do raio. A busca deve percorrer a
            # origem em lote, sem trabalho quadratico conforme a base cresce.
            for i in range(3000):
                origem = db.insert(con, "REGISTRO_FONTE", {
                    "artefato_id": artefato, "numero_ordem": i + 100,
                    "payload_original": json.dumps({"Codigo": "CARGA-%d" % i}),
                    "hash_registro": "%064x" % i, "status_validacao": "ok"})
                pos = db.insert(con, "POSICAO_GEOGRAFICA", {
                    "latitude": -23, "longitude": -46 - i / 100000,
                    "qualidade_posicao_id": qualidade})
                ponto = db.insert(con, "PONTO_FISCALIZACAO", {"posicao_id": pos})
                con.execute("INSERT INTO VINCULO_REGISTRO_PONTO(registro_id,ponto_id) VALUES (?,?)", (origem, ponto))
            con.commit()
            passos = 0
            def limite_operacoes():
                nonlocal passos
                passos += 1
                return passos > 2000
            # Orcamento de instrucoes SQLite, independente da velocidade da CI.
            con.set_progress_handler(limite_operacoes, 1000)
            try:
                candidatos = governanca._oficiais_proximos(con, -24.9555, -53.4552, 150)
            finally:
                con.set_progress_handler(None, 0)
            self.assertEqual([c["ponto_id"] for c in candidatos], [oficial])

    def test_expert_nao_sobrescreve_via_informada(self):
        self.oficial()
        cadastro = self.enviar({**self.dados, "via": "BR-999", "km": 12})["cadastros"][0]
        self.assertEqual(cadastro["proximidade"]["campos_complementados"], {})
        with db.connect(config.DB_PATH) as con:
            ponto = consultas.buscar_ponto_por_id(con, cadastro["id"])
            self.assertEqual(ponto["localizacao"]["via"]["codigo"], "BR-999")
            self.assertEqual(ponto["localizacao"]["km"], 12)

    def test_reenvio_confirma_id_sem_duplicar_ou_desfazer_moderacao(self):
        primeiro = self.enviar()["cadastros"][0]["id"]
        with db.connect(config.DB_PATH) as con:
            con.execute("UPDATE PONTO_FISCALIZACAO SET verificacao_status='verificado'")
        res = self.enviar()
        self.assertEqual(res["aceitos"], 1)
        self.assertEqual(res["criados"], 0)
        self.assertEqual(res["ja_cadastrados"], 1)
        self.assertEqual(res["cadastros"][0]["id"], primeiro)
        with db.connect(config.DB_PATH) as con:
            self.assertEqual(db.scalar(con, "SELECT count(*) FROM PONTO_FISCALIZACAO"), 1)
            self.assertEqual(db.scalar(con, "SELECT verificacao_status FROM PONTO_FISCALIZACAO"), "verificado")
            self.assertEqual(db.scalar(con, "SELECT count(*) FROM RADAR_ALTERACAO WHERE tipo='criado'"), 1)

    def test_velocidades_e_coordenadas_invalidas_sao_rejeitadas_sem_gravar(self):
        casos = [{**self.dados, "velocidade_geral": v} for v in (0, -60, 351, "NaN", "abc", True)]
        casos += [{**self.dados, "latitude": "abc", "municipio": "Cascavel", "via": "BR-277"},
                  {**self.dados, "latitude": 0, "longitude": 0},
                  {**self.dados, "longitude": float("inf")}]
        for dados in casos:
            with self.subTest(dados=dados):
                resposta = self._req("POST", "/api/v1/radares/submeter", dados)
                self.assertEqual(resposta[0], 422)
                self.assertTrue(self._doc(resposta)["erro"]["detalhes"])
        with db.connect(config.DB_PATH) as con:
            self.assertEqual(db.scalar(con, "SELECT count(*) FROM PONTO_FISCALIZACAO"), 0)

    def test_expert_aceita_municipio_via_e_decimais_com_virgula(self):
        cadastro = self.enviar({"municipio": "Cascavel", "uf": "PR", "via": "BR-277"})["cadastros"][0]
        self.assertEqual(cadastro["proximidade"]["status"], "sem_coordenadas")
        cadastro = self.enviar({"latitude": "-24,9555", "longitude": "-53,4552", "velocidade_geral": "60"})["cadastros"][0]
        with db.connect(config.DB_PATH) as con:
            self.assertEqual(consultas.buscar_ponto_por_id(con, cadastro["id"])["velocidade_geral_kmh"], 60)

    def test_lote_parcial_mantem_indices_originais(self):
        res = self.enviar([{"latitude": 999, "longitude": 0}, self.dados])
        self.assertEqual(res["aceitos"], 1)
        self.assertEqual(res["rejeitados"], 1)
        self.assertEqual(res["erros"][0]["indice"], 0)
        self.assertEqual(res["cadastros"][0]["indice"], 1)


class TestCadastroPagina(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node necessario para testar o formulario")
    def test_formulario_contrato_respostas_e_validacao(self):
        resultado = subprocess.run([shutil.which("node"), str(Path(__file__).with_suffix(".js"))],
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
