# -*- coding: utf-8 -*-
"""Fonte F01 - INMETRO/PSIE: agrupamento por instrumento, campos canonicos.

Testes OFFLINE (fixture local, sem rede), conforme spec 15 e 17.1/[G01].
"""
import os
import unittest

from core import config
from core import db as dbmod
from coletor.fontes import inmetro
from coletor.fontes.inmetro import ColetorINMETRO
from tests.common import ambiente_temporario

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "novos", "inmetro_medidores_fixture.json")


class TestInmetroReconhecimento(unittest.TestCase):
    """Contrato de URL descoberto no reconhecimento (endpoint estatico)."""

    def test_resolver_url_por_uf(self):
        url = ColetorINMETRO.resolver_url("ac")
        self.assertEqual(
            url, "https://servicos.rbmlq.gov.br/dados-abertos/AC/medidores.json")

    def test_resolver_url_sem_uf_devolve_template(self):
        self.assertEqual(ColetorINMETRO.resolver_url(), inmetro.URL_TEMPLATE)
        self.assertIn("{uf}", ColetorINMETRO.resolver_url())

    def test_resolver_url_uf_invalida(self):
        with self.assertRaises(ValueError):
            ColetorINMETRO.resolver_url("XX")

    def test_todas_as_ufs_do_template(self):
        for uf in inmetro.UFS_BR:
            self.assertIn("/%s/medidores.json" % uf,
                          ColetorINMETRO.resolver_url(uf))
        self.assertNotIn("DF", [])  # DF ausente na fonte, nao inventado


class TestCarregamentoAgrupamento(unittest.TestCase):

    def setUp(self):
        self.coletor = ColetorINMETRO()
        self.conteudo, self.ext, self.mime, self.registros = \
            self.coletor.carregar(FIXTURE)

    def test_carrega_fixture_local(self):
        self.assertEqual(self.ext, ".json")
        self.assertEqual(self.mime, "application/json")
        self.assertTrue(self.conteudo.startswith(b"["))

    def test_serial_repetido_em_varias_faixas_e_um_instrumento(self):
        """[G01]/17.4.5: mesmo NumeroSerie em N faixas = 1 instrumento."""
        iguais = [r for r in self.registros
                  if r["NumeroSerie"] == "FLICD0426A01117"]
        self.assertEqual(len(iguais), 1)
        inst = iguais[0]
        self.assertEqual(len(inst["Faixas"]), 4)
        # historico das duas aparicoes foi unido e deduplicado
        self.assertEqual(len(inst["Historico"]), 2)
        # local mais recente prevalece; ambos ficam registrados
        self.assertEqual(len(inst["LocaisVerificacao"]), 2)

    def test_dois_seriais_no_mesmo_registro_viram_dois_instrumentos(self):
        sera = [r for r in self.registros if r["NumeroSerie"] == "SER-A"]
        serb = [r for r in self.registros if r["NumeroSerie"] == "SER-B"]
        self.assertEqual(len(sera), 1)
        self.assertEqual(len(serb), 1)
        self.assertEqual(len(sera[0]["Faixas"]), 2)
        self.assertEqual(len(serb[0]["Faixas"]), 1)
        self.assertEqual(sera[0]["NumeroInmetro"], "111")
        self.assertEqual(serb[0]["NumeroInmetro"], "222")

    def test_registro_vazio_separa_instrumento_sem_serial(self):
        vazios = [r for r in self.registros if not r["NumeroSerie"]]
        self.assertEqual(len(vazios), 1)
        self.assertIsNone(self.coletor.normalizar(5, vazios[0]))


class TestNormalizacao(unittest.TestCase):

    def setUp(self):
        self.coletor = ColetorINMETRO()
        _, _, _, self.registros = self.coletor.carregar(FIXTURE)
        self.por_serial = {r["NumeroSerie"]: r for r in self.registros}

    def test_campos_canonicos(self):
        d = self.coletor.normalizar(0, self.por_serial["FLICD0426A01117"])
        self.assertEqual(d["identificador"], "15030378")
        self.assertEqual(d["tipo_identificador"], "numero_inmetro")
        self.assertEqual(d["numero_serie"], "FLICD0426A01117")
        self.assertEqual(d["uf"], "AC")
        self.assertEqual(d["municipio_nome"], "RIO BRANCO")
        self.assertEqual(d["velocidade_leves"], 40.0)
        self.assertEqual(d["tipo_radar"], "fixo")

    def test_sem_posicao_oficial_nao_confirmada(self):
        d = self.coletor.normalizar(0, self.por_serial["FLICD0426A01117"])
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["qualidade"], "nao_confirmada")
        self.assertIsNone(d["situacao"])   # nao deduzir de certificado

    def test_sentido_ambos_quando_faixas_divergem(self):
        d = self.coletor.normalizar(0, self.por_serial["FLICD0426A01117"])
        self.assertEqual(d["sentido"], "ambos")

    def test_velocidade_divergente_nao_e_inventada(self):
        d = self.coletor.normalizar(0, self.por_serial["SER-C"])
        self.assertIsNone(d["velocidade_leves"])
        self.assertIn("40", d["observacoes"])
        self.assertIn("80", d["observacoes"])

    def test_tipo_medidor_mapeado(self):
        c = self.coletor
        self.assertEqual(c.normalizar(0, {"NumeroSerie": "x",
                                          "TipoMedidor": "Fixo"})["tipo_radar"],
                         "fixo")
        self.assertEqual(c.normalizar(0, {"NumeroSerie": "x",
                                          "TipoMedidor": "Móvel"})["tipo_radar"],
                         "movel")
        self.assertEqual(c.normalizar(0, {"NumeroSerie": "x",
                                          "TipoMedidor": "Estático ou Portátil"}
                                      )["tipo_radar"], "portatil")
        # 'Estático' isolado NAO e afirmado como fixo nem portatil
        self.assertEqual(c.normalizar(0, {"NumeroSerie": "x",
                                          "TipoMedidor": "Estático"}
                                      )["tipo_radar"], "desconhecido")

    def test_observacoes_preservam_local_e_certificado(self):
        d = self.coletor.normalizar(0, self.por_serial["FLICD0426A01117"])
        self.assertIn("BR 364 KM 123,830", d["observacoes"])
        self.assertIn("Certificado", d["observacoes"])
        self.assertIn("Faixas: 4", d["observacoes"])


class TestSincronizacaoOffline(unittest.TestCase):

    def test_sincroniza_sem_rede(self):
        ambiente_temporario()
        coletor = ColetorINMETRO(db_path=config.DB_PATH)
        try:
            resumo = coletor.sincronizar(FIXTURE)
            con = coletor.conn
            self.assertEqual(resumo["criados"], 5)
            self.assertEqual(resumo["rejeitados"], 1)
            pontos = dbmod.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO")
            self.assertEqual(pontos, 5)
            # nenhuma posicao: a fonte nao publica coordenadas
            posicoes = dbmod.scalar(con, "SELECT COUNT(*) FROM POSICAO_GEOGRAFICA")
            self.assertEqual(posicoes, 0)
            equip = dbmod.scalar(con, "SELECT COUNT(*) FROM EQUIPAMENTO")
            self.assertEqual(equip, 5)   # 1 por instrumento, nao por faixa
            # numero INMETRO persistido como identificador externo
            ident = dbmod.query_one(
                con, "SELECT valor FROM IDENTIFICADOR_EXTERNO WHERE valor=?",
                ("15030378",))
            self.assertIsNotNone(ident)
        finally:
            coletor.conn.close()


class TestDatasAuxiliares(unittest.TestCase):

    def test_data_br(self):
        import datetime
        self.assertEqual(inmetro._data_br("04/08/2026"),
                         datetime.date(2026, 8, 4))
        self.assertIsNone(inmetro._data_br("2026-08-04"))
        self.assertIsNone(inmetro._data_br("31/02/2026"))
        self.assertIsNone(inmetro._data_br(None))


if __name__ == "__main__":
    unittest.main()
