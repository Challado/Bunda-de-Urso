# -*- coding: utf-8 -*-
"""O detalhe atribui publicacoes a suas fontes sem expor contato privado."""
from core import consultas
from tests.test_dedup import BaseDedup


class TestDetalheFontes(BaseDedup):

    def publicar(self, ponto, fonte, dados):
        registro = self.registro(self.artefato(self.recurso(fonte)), dados)
        self.ligar_ponto(registro, ponto)
        self.con.commit()
        return registro

    def test_fontes_mantem_seus_dados_e_valores_divergentes(self):
        ponto = self.ponto(self.posicao(-25, -54))
        inmetro = self.fonte("INMETRO / PSIE")
        der = self.fonte("DER")
        primeiro = self.publicar(ponto, inmetro, {
            "NumeroSerie": "ABC123", "VelocidadeNominal": 50,
            "Historico": [{"NumeroCertificado": "CERT-1"}],
        })
        self.publicar(ponto, der, {"velocidade": 60, "rodovia": "BR-277"})
        self.publicar(ponto, der, {"velocidade": 80, "rodovia": "BR-277"})
        detalhe = consultas.buscar_ponto_por_id(self.con, "P-%d" % ponto)
        fontes = {fonte["nome"]: fonte for fonte in detalhe["dados_por_fonte"]}
        self.assertEqual(set(fontes), {"INMETRO / PSIE", "DER"})
        registros = fontes["INMETRO / PSIE"]["registros"]
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["registro_id"], primeiro)
        self.assertEqual(registros[0]["dados_publicados"]["VelocidadeNominal"], 50)
        self.assertEqual(registros[0]["dados_publicados"]["Historico"],
                         [{"NumeroCertificado": "CERT-1"}])
        self.assertEqual({r["dados_publicados"]["velocidade"]
                          for r in fontes["DER"]["registros"]}, {60, 80})
        self.assertNotIn("VelocidadeNominal", fontes["DER"]["registros"][0]["dados_publicados"])

    def test_cadastro_proprio_e_publico_nao_expoem_contato_ou_metadados(self):
        for natureza in ("outra", "comunitaria"):
            with self.subTest(natureza=natureza):
                ponto = self.ponto()
                fonte = self.fonte(natureza, natureza=natureza)
                self.publicar(ponto, fonte, {
                    "latitude": -25, "longitude": -54, "velocidade": 60,
                    "contato": "privado@example.invalid", "token": "privado",
                    "metadados": {"ip": "192.0.2.1"},
                    "via": {"contato": "privado"},
                })
                grupos = consultas.buscar_ponto_por_id(self.con, ponto)["dados_por_fonte"]
                self.assertEqual(grupos[0]["natureza"], natureza)
                self.assertEqual(grupos[0]["registros"][0]["dados_publicados"],
                                 {"latitude": -25, "longitude": -54, "velocidade": 60})

    def test_busca_do_mapa_nao_carrega_publicacoes_e_detalhe_sem_fonte_e_explicito(self):
        ponto = self.ponto(self.posicao(-25, -54))
        self.con.commit()
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertNotIn("dados_por_fonte", pontos[0])
        self.assertEqual(consultas.buscar_ponto_por_id(self.con, ponto)["dados_por_fonte"], [])
