# -*- coding: utf-8 -*-
"""Testes do carregador da verificacao metrologica (PSIE/INMETRO).

Cobrem o mapeamento (resultado/tipo/datas), a leitura do ``Historico`` e do
registro vigente, a idempotencia e a recusa de data incoerente.
"""
import json
import unittest

from core import db as dbmod
from tests.common import banco_memoria
from tools import carregar_verificacao_metrologica as vm

PAYLOAD = {
    "SiglaUf": "AC", "Municipio": "RIO BRANCO",
    "DataUltimaVerificacao": "04/08/2026", "DataValidade": "03/08/2027",
    "UltimoResultado": "Aprovado", "NumeroSerie": "S1",
    "Historico": [
        {"NumeroCertificado": "15020223", "NumeroEnsaio": "1", "Ano": "2026",
         "DataLaudo": "04/08/2026", "DataValidade": "03/08/2027",
         "TipoServico": "Inicial", "Resultado": "Aprovado"},
        {"NumeroCertificado": "15020220", "NumeroEnsaio": "2", "Ano": "2024",
         "DataLaudo": "04/07/2024", "DataValidade": "03/07/2025",
         "TipoServico": "Periódica", "Resultado": "Reprovado"},
    ],
}


class TestMapeamento(unittest.TestCase):

    def test_data_iso_formatos(self):
        self.assertEqual(vm.data_iso("04/08/2026"), "2026-08-04")
        self.assertEqual(vm.data_iso("2026-08-04"), "2026-08-04")
        self.assertIsNone(vm.data_iso(""))
        self.assertIsNone(vm.data_iso("32/13/2026"))

    def test_resultado(self):
        self.assertEqual(vm.mapear_resultado("Aprovado"), "conforme")
        self.assertEqual(vm.mapear_resultado("REPROVADO"), "nao_conforme")
        self.assertEqual(vm.mapear_resultado("Sei la"), "outro")
        self.assertEqual(vm.mapear_resultado(None), "desconhecido")

    def test_tipo_servico(self):
        self.assertEqual(vm.mapear_tipo("Inicial"), "inicial")
        self.assertEqual(vm.mapear_tipo("Periódica"), "periodica")
        self.assertEqual(vm.mapear_tipo("Após reparo"), "apos_reparo")
        self.assertEqual(vm.mapear_tipo("Outro"), "outra")
        self.assertEqual(vm.mapear_tipo(None), "desconhecida")


class TestExtrair(unittest.TestCase):

    def test_le_historico_completo(self):
        linhas = vm.extrair_verificacoes(PAYLOAD, 7, 99)
        self.assertEqual(len(linhas), 2)
        a = linhas[0]
        self.assertEqual(a["equipamento_id"], 7)
        self.assertEqual(a["registro_fonte_id"], 99)
        self.assertEqual(a["numero_certificado"], "15020223")
        self.assertEqual(a["data_verificacao"], "2026-08-04")
        self.assertEqual(a["validade_ate"], "2027-08-03")
        self.assertEqual(a["resultado"], "conforme")
        self.assertEqual(a["tipo"], "inicial")
        self.assertEqual(linhas[1]["resultado"], "nao_conforme")

    def test_sem_historico_usa_registro_vigente(self):
        p = dict(PAYLOAD)
        p.pop("Historico")
        linhas = vm.extrair_verificacoes(p, 7, 99)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["resultado"], "conforme")
        self.assertIsNone(linhas[0]["numero_certificado"])

    def test_payload_invalido(self):
        self.assertEqual(vm.extrair_verificacoes("{nao json", 7, 99), [])

    def test_data_incoerente_zera_validade(self):
        p = {"Historico": [{"NumeroCertificado": "X",
                            "DataLaudo": "10/10/2026",
                            "DataValidade": "01/01/2020",
                            "Resultado": "Aprovado", "TipoServico": "Inicial"}]}
        linhas = vm.extrair_verificacoes(p, 1, 1)
        self.assertEqual(linhas[0]["data_verificacao"], "2026-10-10")
        self.assertIsNone(linhas[0]["validade_ate"])


class TestCarregar(unittest.TestCase):
    def setUp(self):
        self.con = banco_memoria()
        # a FK de registro e exercitada na producao; aqui o alvo e a idempotencia
        self.con.execute("PRAGMA foreign_keys = OFF")
        self.con.execute("INSERT INTO EQUIPAMENTO (id, tipo_radar_id) "
                         "VALUES (7, 4)")
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_insere_e_e_idempotente(self):
        regs = [(99, 7, json.dumps(PAYLOAD))]
        r1 = vm.carregar(self.con, regs, aplicar=True)
        self.con.commit()
        self.assertEqual(r1["inseridas"], 2)
        n = self.con.execute(
            "SELECT COUNT(*) FROM VERIFICACAO_METROLOGICA").fetchone()[0]
        self.assertEqual(n, 2)
        r2 = vm.carregar(self.con, regs, aplicar=True)
        self.assertEqual(r2["inseridas"], 0)
        self.assertEqual(r2["duplicadas"], 2)

    def test_sem_equipamento_ignora(self):
        r = vm.carregar(self.con, [(99, None, json.dumps(PAYLOAD))],
                        aplicar=True)
        self.assertEqual(r["sem_equipamento"], 1)
        self.assertEqual(r["inseridas"], 0)


class TestCarregarDoBanco(unittest.TestCase):
    """O gancho pos-coleta le os payloads INMETRO ja gravados no banco."""

    def setUp(self):
        self.con = banco_memoria()
        org = dbmod.insert(self.con, "ORGANIZACAO", {
            "nome": "Inmetro", "tipo_organizacao_id": dbmod.domain_id(
                self.con, "TIPO_ORGANIZACAO", "orgao_publico")})
        fonte = dbmod.insert(self.con, "FONTE", {
            "organizacao_id": org,
            "natureza_id": dbmod.domain_id(self.con, "NATUREZA_FONTE",
                                           "oficial"),
            "nome": "INMETRO / PSIE - instrumentos",
            "url_institucional": "https://exemplo/inmetro",
            "esfera": "federal", "situacao": "ativa"})
        rec = dbmod.insert(self.con, "RECURSO_FONTE", {
            "fonte_id": fonte, "nome": "medidores",
            "url_recurso": "https://exemplo/medidores.json",
            "formato_origem": "json", "ativo": 1,
            "status_integracao": "ok"})
        art = dbmod.insert(self.con, "ARTEFATO_COLETA", {
            "recurso_id": rec, "hash_sha256": "h1",
            "caminho_cache": "/tmp/medidores.json", "bytes_arquivo": 10,
            "baixado_em": "2026-10-10T00:00:00+00:00",
            "resultado_validacao": "ok"})
        self.reg = dbmod.insert(self.con, "REGISTRO_FONTE", {
            "artefato_id": art, "numero_ordem": 1,
            "payload_original": json.dumps(PAYLOAD), "hash_registro": "r1",
            "status_validacao": "ok"})
        equip = dbmod.insert(self.con, "EQUIPAMENTO", {
            "tipo_radar_id": dbmod.domain_id(self.con, "TIPO_RADAR", "fixo")})
        self.con.execute("INSERT INTO VINCULO_REGISTRO_EQUIPAMENTO "
                         "(registro_id, equipamento_id) VALUES (?,?)",
                         (self.reg, equip))
        self.con.commit()

    def tearDown(self):
        self.con.close()

    def test_le_do_banco_e_e_idempotente(self):
        r1 = vm.carregar_do_banco(self.con)
        self.assertEqual(r1["registros"], 1)
        self.assertEqual(r1["inseridas"], 2)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM VERIFICACAO_METROLOGICA").fetchone()[0], 2)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM VINCULO_REGISTRO_VERIFICACAO"
        ).fetchone()[0], 2)
        r2 = vm.carregar_do_banco(self.con)     # reaplicar nao duplica
        self.assertEqual(r2["inseridas"], 0)
        self.assertEqual(r2["duplicadas"], 2)

    def test_dry_run_nao_grava(self):
        r = vm.carregar_do_banco(self.con, aplicar=False)
        self.assertEqual(r["inseridas"], 2)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM VERIFICACAO_METROLOGICA").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
