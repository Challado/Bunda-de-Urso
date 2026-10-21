"""Juncoes entre o cadastro localizado e a metrologia oficial do instrumento."""
import json

from core import consultas, db, dedup, governanca, metrologia
from core.identidade import VisaoCanonica
from tests import test_dedup as apoio


class TestJuncaoMetrologica(apoio.BaseDedup):
    def setUp(self):
        super().setUp()
        governanca.garantir_esquema(self.con)
        for codigo, nome, uf in (("5210208", "Iporá", "GO"), ("5208707", "Goiânia", "GO")):
            db.insert(self.con, "MUNICIPIO", {"codigo_ibge": codigo, "nome": nome, "uf_sigla": uf})
        self.goinfra = self.fonte("GOINFRA")
        self.inmetro = self.fonte("INMETRO / PSIE")

    def observar(self, fonte, serie="118690160", municipio="5210208", verificar=False,
                 modelo=None, coordenada=None, tipo="fixo"):
        payload = ({"NumeroSerie": serie, "DataValidade": "24/06/2027",
                    "UltimoResultado": "Aprovado", "LocalVerificacao": "GO-060 KM 249+100M"}
                   if verificar else {"serie": serie, "afericao_valida_ate": "25/06/2027"})
        rid = self.registro(self.artefato(self.recurso(fonte)), payload)
        ponto = self.ponto(self.posicao(*coordenada) if coordenada else None)
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?", (municipio, ponto))
        equipamento = self.equipamento(serie, tipo)
        if modelo:
            fabricante = db.upsert_lookup(self.con, "ORGANIZACAO", ["nome"], [modelo[0]],
                extra={"tipo_organizacao_id": db.domain_id(self.con, "TIPO_ORGANIZACAO", "fabricante")})
            mid = db.upsert_lookup(self.con, "MODELO_EQUIPAMENTO", ["fabricante_id", "nome_modelo"],
                                  [fabricante, modelo[1]])
            self.con.execute("UPDATE EQUIPAMENTO SET modelo_id=? WHERE id=?", (mid, equipamento))
        db.insert(self.con, "INSTALACAO", {"ponto_id": ponto, "equipamento_id": equipamento})
        self.ligar_ponto(rid, ponto)
        self.ligar_equip(rid, equipamento)
        if verificar:
            db.insert(self.con, "VERIFICACAO_METROLOGICA", {
                "equipamento_id": equipamento, "registro_fonte_id": rid,
                "tipo_verificacao_id": db.domain_id(self.con, "TIPO_VERIFICACAO", "periodica"),
                "resultado_id": db.domain_id(self.con, "RESULTADO_VERIFICACAO", "conforme"),
                "data_verificacao": "2026-06-25", "validade_ate": "2027-06-24"})
        self.con.commit()
        return ponto, equipamento, rid

    def par(self, **kwargs):
        self.a = self.observar(self.goinfra, coordenada=(-16.327755, -51.356763))
        self.b = self.observar(self.inmetro, verificar=True, **kwargs)

    def detalhe(self):
        return consultas.buscar_ponto_por_id(self.con, self.a[0])

    def test_join_reune_fontes_e_verificacao_sem_mudar_ponto_ou_origem(self):
        self.par()
        antes = self.con.total_changes
        p = self.detalhe()
        self.assertEqual(self.con.total_changes, antes)
        self.assertEqual(p["id"], "P-%s" % self.a[0])
        self.assertEqual(p["localizacao"]["latitude"], -16.327755)
        e = p["equipamentos"][0]
        self.assertEqual(e["id"], "E-%s" % self.a[1])
        self.assertEqual(len(e["instalacoes"]), 1)
        self.assertEqual(len(e["verificacoes_metrologicas"]), 1)
        self.assertEqual(e["verificacoes_metrologicas"][0]["validade_ate"], "2027-06-24")
        self.assertEqual(e["verificacoes_metrologicas"][0]["equipamento_origem_id"], "E-%s" % self.b[1])
        fontes = {f["nome"]: f for f in p["dados_por_fonte"]}
        self.assertEqual(set(fontes), {"GOINFRA", "INMETRO / PSIE"})
        r = fontes["INMETRO / PSIE"]["registros"][0]
        self.assertEqual(r["registro_id"], self.b[2])
        self.assertEqual(r["escopo_vinculo"], "equipamento")
        self.assertEqual(r["dados_publicados"]["DataValidade"], "24/06/2027")
        self.assertEqual(fontes["GOINFRA"]["registros"][0]["dados_publicados"]["afericao_valida_ate"], "25/06/2027")
        self.assertEqual({f["nome"] for f in p["fontes"]}, set(fontes))
        self.assertEqual(self.contar("PONTO_FISCALIZACAO"), 2)
        self.assertEqual(self.contar("EQUIPAMENTO"), 2)
        direto = consultas.buscar_equipamento_por_id(self.con, self.a[1])
        self.assertEqual(direto, e)
        self.assertNotIn("juncao_metrologica", consultas.buscar_equipamento_por_id(self.con, self.b[1]))

    def test_sem_correspondencia_preserva_radar_e_nao_exige_inmetro(self):
        self.a = self.observar(self.goinfra)
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_coordenada_proxima_nao_liga_serie_diferente(self):
        self.par(serie="118690346", coordenada=(-16.327755, -51.356763))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_nao_liga_municipio_diferente_ou_ausente(self):
        self.par(municipio="5208707")
        for municipio in ("5208707", None):
            self.con.execute("UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?", (municipio, self.b[0]))
            self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_nao_liga_tipo_diferente(self):
        self.par(tipo="portatil")
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_nao_liga_serie_vazia_ou_generica(self):
        self.par()
        for serie in (None, "", "S/N", "000000", "123", "desconhecido"):
            with self.subTest(serie=serie):
                self.con.execute("UPDATE EQUIPAMENTO SET numero_serie=?", (serie,))
                self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_aceita_caixa_e_espacos_mas_nao_faz_fuzzy_na_serie(self):
        self.par(serie=" abC12345 ")
        self.con.execute("UPDATE EQUIPAMENTO SET numero_serie='ABC12345' WHERE id=?", (self.a[1],))
        self.assertEqual(len(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"]), 1)
        self.con.execute("UPDATE EQUIPAMENTO SET numero_serie='ABC12346' WHERE id=?", (self.a[1],))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_somente_fontes_oficiais_nos_dois_lados(self):
        self.par()
        comunitaria = db.domain_id(self.con, "NATUREZA_FONTE", "comunitaria")
        oficial = db.domain_id(self.con, "NATUREZA_FONTE", "oficial")
        for fid in (self.goinfra, self.inmetro):
            self.con.execute("UPDATE FONTE SET natureza_id=? WHERE id=?", (comunitaria, fid))
            self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])
            self.con.execute("UPDATE FONTE SET natureza_id=? WHERE id=?", (oficial, fid))

    def test_modelo_ou_fabricante_conflitante_recusa_juncao(self):
        self.a = self.observar(self.goinfra, modelo=("Fabricante A", "Modelo A"))
        self.b = self.observar(self.inmetro, verificar=True, modelo=("Fabricante B", "Modelo A"))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])
        self.con.execute("UPDATE MODELO_EQUIPAMENTO SET fabricante_id=(SELECT fabricante_id FROM MODELO_EQUIPAMENTO WHERE id=(SELECT modelo_id FROM EQUIPAMENTO WHERE id=?)), nome_modelo='Modelo B' WHERE id=(SELECT modelo_id FROM EQUIPAMENTO WHERE id=?)", (self.a[1], self.b[1]))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_serie_ambigua_com_modelos_diferentes_nao_escolhe_um(self):
        self.par()
        self.con.execute("UPDATE EQUIPAMENTO SET modelo_id=NULL")
        self.observar(self.inmetro, verificar=True, modelo=("Fabricante A", "Modelo A"))
        self.observar(self.inmetro, verificar=True, modelo=("Fabricante B", "Modelo B"))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_decisao_de_separacao_prevalece_e_reversao_reabilita_join(self):
        self.par()
        dedup.gerar_candidatos(self.con)
        cid = db.scalar(self.con, "SELECT id FROM CANDIDATO_DUPLICIDADE")
        decisao = dedup.decidir(self.con, cid, "manter_separados", "revisor", "Instrumentos distintos", escopo="equipamento")
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])
        dedup.reverter_decisao(self.con, decisao, "revisor", "Documento corrigido")
        self.assertEqual(len(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"]), 1)

    def test_instrumento_removido_nao_reaparece_por_join(self):
        self.par()
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-21' WHERE id=?", (self.b[0],))
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"], [])

    def test_historico_oficial_nao_importa_verificacao_de_outra_natureza(self):
        self.par()
        fonte = self.fonte("Origem não oficial", natureza="comunitaria")
        rid = self.registro(self.artefato(self.recurso(fonte)), {"segredo": "nao publicar"})
        self.con.execute("INSERT INTO VERIFICACAO_METROLOGICA (equipamento_id, tipo_verificacao_id, resultado_id, registro_fonte_id) SELECT equipamento_id,tipo_verificacao_id,resultado_id,? FROM VERIFICACAO_METROLOGICA", (rid,))
        e = self.detalhe()["equipamentos"][0]
        self.assertEqual(len(e["verificacoes_metrologicas"]), 1)
        self.assertNotIn("nao publicar", json.dumps(self.detalhe()))

    def test_join_usa_indice_de_serie(self):
        self.par()
        plano = " ".join(str(tuple(r)) for r in self.con.execute(
            "EXPLAIN QUERY PLAN " + metrologia._RELACIONADOS_SQL, (self.a[1],)))
        self.assertIn("IX_EQUIPAMENTO_SERIE_TIPO", plano)
        self.assertEqual(len(metrologia.equipamentos_relacionados(self.con, self.a[1], VisaoCanonica(self.con))), 1)
