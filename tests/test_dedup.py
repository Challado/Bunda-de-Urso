# -*- coding: utf-8 -*-
"""Deduplicacao rastreavel (spec secao 8 e 17.4).

Cobre: par duplicado obvio (serie + proximidade) vira candidato com escore;
origem compartilhada (copia do mesmo OSM) nao conta como prova dupla; decisao
+ reversao preservam auditoria; mesma coordenada sozinha NAO consolida;
divergencia oficial/comunitaria nao sobrescreve o dado oficial; mesma serie
em varias faixas = um equipamento + multiplas faixas.
"""
import hashlib
import json
import unittest

from core import db as dbmod
from core import dedup
from tests.common import banco_memoria


def _hash(*partes):
    return hashlib.sha256("|".join(str(p) for p in partes).encode()).hexdigest()


class BaseDedup(unittest.TestCase):

    def setUp(self):
        self.con = banco_memoria()
        self._seq = 0

    def tearDown(self):
        self.con.close()

    # -- construtores ----------------------------------------------------
    def fonte(self, nome, natureza="oficial", esfera="federal"):
        org = dbmod.insert(self.con, "ORGANIZACAO", {
            "nome": "Org " + nome,
            "tipo_organizacao_id": dbmod.domain_id(
                self.con, "TIPO_ORGANIZACAO", "orgao_publico")})
        return dbmod.insert(self.con, "FONTE", {
            "organizacao_id": org,
            "natureza_id": dbmod.domain_id(self.con, "NATUREZA_FONTE", natureza),
            "nome": nome, "url_institucional": "https://exemplo/" + nome,
            "esfera": esfera, "situacao": "ativa"})

    def recurso(self, fonte_id, nome="rec"):
        return dbmod.insert(self.con, "RECURSO_FONTE", {
            "fonte_id": fonte_id, "nome": nome,
            "url_recurso": "https://exemplo/%s/%s" % (fonte_id, nome),
            "formato_origem": "json", "ativo": 1, "status_integracao": "ok"})

    def artefato(self, recurso_id, hash64=None):
        self._seq += 1
        return dbmod.insert(self.con, "ARTEFATO_COLETA", {
            "recurso_id": recurso_id,
            "hash_sha256": hash64 or _hash("artefato", recurso_id, self._seq),
            "caminho_cache": "/tmp/raw/%d" % self._seq, "bytes_arquivo": 10,
            "baixado_em": "2026-10-10T00:00:00+00:00",
            "resultado_validacao": "ok"})

    def registro(self, artefato_id, payload, ident=None, hash_registro=None):
        self._seq += 1
        return dbmod.insert(self.con, "REGISTRO_FONTE", {
            "artefato_id": artefato_id, "numero_ordem": self._seq,
            "identificador_na_fonte": ident,
            "payload_original": json.dumps(payload, sort_keys=True),
            "hash_registro": hash_registro or _hash("registro", payload),
            "status_validacao": "ok"})

    def posicao(self, lat, lon, qualidade="oficial", registro_id=None):
        return dbmod.insert(self.con, "POSICAO_GEOGRAFICA", {
            "latitude": lat, "longitude": lon,
            "qualidade_posicao_id": dbmod.domain_id(
                self.con, "QUALIDADE_POSICAO", qualidade),
            "registro_fonte_id": registro_id})

    def via(self, codigo, tipo="federal"):
        return dbmod.insert(self.con, "VIA", {
            "tipo_via_id": dbmod.domain_id(self.con, "TIPO_VIA", tipo),
            "codigo": codigo})

    def ponto(self, posicao_id=None, via_id=None, km=None):
        return dbmod.insert(self.con, "PONTO_FISCALIZACAO", {
            "posicao_id": posicao_id, "via_id": via_id, "km": km})

    def faixa(self, ponto_id, numero=1, sentido="crescente"):
        return dbmod.insert(self.con, "FAIXA_FISCALIZACAO", {
            "ponto_id": ponto_id, "numero_faixa": numero,
            "sentido_id": dbmod.domain_id(self.con, "SENTIDO", sentido)})

    def equipamento(self, serie, tipo="fixo"):
        return dbmod.insert(self.con, "EQUIPAMENTO", {
            "tipo_radar_id": dbmod.domain_id(self.con, "TIPO_RADAR", tipo),
            "numero_serie": serie})

    def ligar_ponto(self, registro_id, ponto_id):
        self.con.execute(
            "INSERT OR IGNORE INTO VINCULO_REGISTRO_PONTO "
            "(registro_id, ponto_id) VALUES (?,?)", (registro_id, ponto_id))

    def ligar_equip(self, registro_id, equip_id):
        self.con.execute(
            "INSERT OR IGNORE INTO VINCULO_REGISTRO_EQUIPAMENTO "
            "(registro_id, equipamento_id) VALUES (?,?)",
            (registro_id, equip_id))

    # -- consultas de apoio ---------------------------------------------
    def contar(self, tabela):
        return self.con.execute(
            "SELECT COUNT(*) FROM %s" % tabela).fetchone()[0]

    def vinculos_com_decisao(self, decisao_id):
        total = 0
        for t in ("VINCULO_REGISTRO_PONTO", "VINCULO_REGISTRO_EQUIPAMENTO",
                  "VINCULO_REGISTRO_OPERACAO", "VINCULO_REGISTRO_TRECHO"):
            total += self.con.execute(
                "SELECT COUNT(*) FROM %s WHERE decisao_id = ?"
                % t, (decisao_id,)).fetchone()[0]
        return total

    def candidato_unico(self):
        cands = dedup.candidatos(self.con)
        self.assertEqual(len(cands), 1, "esperava exatamente 1 candidato")
        return cands[0]


class TestNormalizacao(BaseDedup):

    def test_serie(self):
        self.assertEqual(dedup.normalizar_serie(" S-1539 "), "S1539")
        self.assertEqual(dedup.normalizar_serie("s1539"), "S1539")
        self.assertIsNone(dedup.normalizar_serie("S/N"))
        self.assertEqual(dedup.normalizar_serie("005867"), "5867")

    def test_rodovia_e_km(self):
        for v in ("BR-277", "BR277", "br 277"):
            self.assertEqual(dedup.normalizar_rodovia(v), "BR-277")
        self.assertEqual(dedup.normalizar_km("580,5 km"), 580.5)
        self.assertEqual(dedup.normalizar_km("580.5"), 580.5)

    def test_sentido(self):
        self.assertEqual(dedup.normalizar_sentido("Crescente"), "crescente")
        self.assertEqual(dedup.normalizar_sentido("Decrescente"),
                         "decrescente")
        self.assertEqual(dedup.normalizar_sentido("bidirecional"), "ambos")


class TestGerarCandidatos(BaseDedup):

    def test_par_duplicado_obvio_vira_candidato_com_escore(self):
        f1 = self.fonte("PRF", "oficial")
        a1 = self.artefato(self.recurso(f1, "prf"))
        via = self.via("BR-277")
        r1 = self.registro(a1, {"numero_serie": "TC-005867", "rodovia": "BR-277",
                                "km": "580,5", "sentido": "crescente"},
                          ident="REF181")
        self.ligar_ponto(r1, self.ponto(self.posicao(-24.9555, -53.4552,
                                                      registro_id=r1), via, 580.5))
        self.ligar_equip(r1, self.equipamento("TC-005867"))

        f2 = self.fonte("OSM", "comunitaria")
        a2 = self.artefato(self.recurso(f2, "osm"))
        r2 = self.registro(a2, {"numero_serie": "TC005867", "rodovia": "BR277",
                                "km": 580.5, "sentido": "crescente"},
                           ident="node/123")
        self.ligar_ponto(r2, self.ponto(self.posicao(-24.9556, -53.4552,
                                                      registro_id=r2), via, 580.5))
        self.ligar_equip(r2, self.equipamento("TC005867"))

        res = dedup.gerar_candidatos(self.con)
        self.assertEqual(len(res["criados"]), 1)

        c = self.candidato_unico()
        self.assertEqual(c["estado"], "pendente")     # nunca automatico
        self.assertGreaterEqual(c["score"], 0.9)
        ev = json.loads(c["evidencias_resumo"])
        self.assertEqual(ev["nivel"], "forte")
        nomes = {x["nome"] for x in ev["componentes"]}
        self.assertIn("serie_igual", nomes)
        self.assertIn("proximidade", nomes)
        self.assertEqual(ev["n_evidencias_independentes"], 2)

    def test_origem_compartilhada_nao_conta_como_prova_dupla(self):
        # duas copias do MESMO arquivo OSM (mirror) + uma fonte oficial
        h = _hash("mesmo arquivo osm")
        f_osm = self.fonte("OSM", "comunitaria")
        art = self.artefato(self.recurso(f_osm, "osm_extract"), hash64=h)
        m1 = self.registro(art, {"numero_serie": "X1", "latitude": -24.0,
                                 "longitude": -53.0})
        r_mir = self.recurso(self.fonte("Mirror", "comunitaria"),
                             "mirror_copy")
        art2 = self.artefato(r_mir, hash64=h)         # mesmo hash -> mesmo dado
        m2 = self.registro(art2, {"numero_serie": "X1", "latitude": -24.0,
                                  "longitude": -53.0})

        f_of = self.fonte("PRF", "oficial")
        a3 = self.artefato(self.recurso(f_of, "prf"))
        o1 = self.registro(a3, {"numero_serie": "X1", "latitude": -24.00001,
                                "longitude": -53.0})

        self.assertTrue(dedup.mesma_cadeia(self.con, m1, m2))
        self.assertFalse(dedup.mesma_cadeia(self.con, m1, o1))
        self.assertEqual(dedup.evidencias_independentes(self.con, [m1, m2]), 1)
        self.assertEqual(dedup.evidencias_independentes(self.con, [m1, o1]), 2)

        at1 = dedup.atributos_registro(self.con, m1)
        at2 = dedup.atributos_registro(self.con, m2)
        sc = dedup.pontuar(at1, at2)
        self.assertTrue(sc["mesma_origem"])
        self.assertEqual(sc["n_evidencias_independentes"], 1)
        self.assertNotEqual(sc["nivel"], "forte")     # nao se confirma sozinha
        self.assertIn("origem_compartilhada",
                      {x["nome"] for x in sc["componentes"]})

        res = dedup.gerar_candidatos(self.con)
        self.assertGreaterEqual(res["ignorados_mesma_origem"], 1)
        pares = {(c["registro_a_id"], c["registro_b_id"])
                 for c in dedup.candidatos(self.con)}
        self.assertNotIn((m1, m2), pares)             # copia nao vira duplicata
        self.assertIn((min(m1, o1), max(m1, o1)), pares)

        cls = dedup.classificacao_evidencia(self.con, [m1, m2, o1])
        self.assertEqual(cls["n_evidencias_independentes"], 2)
        self.assertTrue(cls["confirmado_oficial"])

    def test_par_contraditorio_por_serie(self):
        f = self.fonte("PRF", "oficial")
        a1 = self.artefato(self.recurso(f, "r1"))
        r1 = self.registro(a1, {"numero_serie": "AAA1", "latitude": -25.0,
                                "longitude": -54.0})
        a2 = self.artefato(self.recurso(f, "r2"))
        r2 = self.registro(a2, {"numero_serie": "BBB2", "latitude": -25.0,
                                "longitude": -54.0})
        # mesma coordenada, series diferentes: cand. mas contraditorio
        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)
        ev = json.loads(self.candidato_unico()["evidencias_resumo"])
        self.assertEqual(ev["nivel"], "contraditorio")
        self.assertTrue(any(b["nome"] == "serie_conflitante"
                            for b in ev["bloqueadores"]))


class TestDecisaoReversao(BaseDedup):

    def _par_serie_e_local(self):
        f1 = self.fonte("PRF", "oficial")
        via = self.via("BR-277")
        r1 = self.registro(self.artefato(self.recurso(f1, "prf")),
                           {"numero_serie": "S1539", "rodovia": "BR-277",
                            "km": 100.0, "sentido": "crescente"})
        self.ligar_ponto(r1, self.ponto(self.posicao(-25.0, -54.0,
                                                      registro_id=r1), via, 100.0))
        e1 = self.equipamento("S1539")
        self.ligar_equip(r1, e1)

        f2 = self.fonte("Comunidade", "comunitaria")
        r2 = self.registro(self.artefato(self.recurso(f2, "osm")),
                           {"numero_serie": "S1539", "rodovia": "BR-277",
                            "km": 100.0, "sentido": "crescente"})
        self.ligar_ponto(r2, self.ponto(self.posicao(-25.00005, -54.0,
                                                      registro_id=r2), via, 100.0))
        e2 = self.equipamento("S1539")
        self.ligar_equip(r2, e2)
        return r1, r2, e1, e2

    def test_decisao_aplicacao_e_reversao_preservam_auditoria(self):
        r1, r2, e1, e2 = self._par_serie_e_local()
        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)
        cid = self.candidato_unico()["id"]

        decisao_id = dedup.decidir(self.con, cid, "unificar", "revisor",
                                   "mesma serie e mesmo km", escopo="ambos")
        self.assertEqual(self.candidato_unico()["estado"], "decidido_unificar")
        self.assertEqual(self.contar("DECISAO_DUPLICIDADE"), 1)

        res = dedup.aplicar(self.con, cid, usuario="revisor")
        self.assertTrue(res[0]["aplicado"])
        self.assertEqual(self.candidato_unico()["estado"], "consolidado")
        n_antes = self.vinculos_com_decisao(decisao_id)
        self.assertGreaterEqual(n_antes, 1)

        rev = dedup.reverter_decisao(self.con, decisao_id, "revisor", "engano")
        self.assertTrue(rev["revertida"])
        self.assertEqual(self.vinculos_com_decisao(decisao_id), 0)
        # auditoria intacta: a decisao continua, com revertida_em marcado
        self.assertEqual(self.contar("DECISAO_DUPLICIDADE"), 1)
        linha = self.con.execute(
            "SELECT decisao, revertida_em FROM DECISAO_DUPLICIDADE "
            "WHERE id = ?", (decisao_id,)).fetchone()
        self.assertEqual(linha["decisao"], "unificar")
        self.assertIsNotNone(linha["revertida_em"])
        self.assertEqual(self.candidato_unico()["estado"], "pendente")
        # origens preservadas
        self.assertEqual(self.contar("REGISTRO_FONTE"), 2)
        self.assertEqual(self.contar("EQUIPAMENTO"), 2)

    def test_aplicar_sem_decisao_nao_consolida(self):
        self._par_serie_e_local()
        dedup.gerar_candidatos(self.con)
        base = self.vinculos_com_decisao(0)
        self.assertEqual(dedup.aplicar(self.con), [])
        self.assertEqual(self.candidato_unico()["estado"], "pendente")
        self.assertEqual(self.vinculos_com_decisao(0), base)


class TestSemOrdemAutomatica(BaseDedup):

    def test_mesma_coordenada_sozinha_nao_consolida(self):
        f1 = self.fonte("OSM", "comunitaria")
        r1 = self.registro(self.artefato(self.recurso(f1, "a")),
                           {"latitude": -25.0, "longitude": -54.0})
        f2 = self.fonte("Waze", "comunitaria")
        r2 = self.registro(self.artefato(self.recurso(f2, "b")),
                           {"latitude": -25.0, "longitude": -54.0})

        # mesma coordenada entre fontes = CANDIDATO (17.4-4)
        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)
        c = self.candidato_unico()
        ev = json.loads(c["evidencias_resumo"])
        self.assertNotEqual(ev["nivel"], "forte")   # 10 m/0 m nao e prova
        self.assertEqual(self.contar("VINCULO_REGISTRO_PONTO"), 0)
        # nada consolida sem decisao humana explicita
        self.assertEqual(dedup.candidatos(self.con, estado="consolidado"), [])
        self.assertEqual(c["estado"], "pendente")


class TestRegras17p4(BaseDedup):

    def test_divergencia_oficial_nao_sobrescreve_latitude_oficial(self):
        f_of = self.fonte("PRF", "oficial")
        r_of = self.registro(self.artefato(self.recurso(f_of, "prf")),
                             {"numero_serie": "S1", "latitude": -25.0,
                              "longitude": -54.0})
        self.ligar_ponto(r_of, self.ponto(self.posicao(-25.0, -54.0,
                                                        registro_id=r_of)))
        self.ligar_equip(r_of, self.equipamento("S1"))

        f_com = self.fonte("OSM", "comunitaria")
        r_com = self.registro(self.artefato(self.recurso(f_com, "osm")),
                              {"numero_serie": "S1", "latitude": -25.000045,
                               "longitude": -54.0})
        self.ligar_ponto(r_com, self.ponto(self.posicao(-25.000045, -54.0,
                                                         registro_id=r_com)))
        self.ligar_equip(r_com, self.equipamento("S1"))

        dedup.gerar_candidatos(self.con)
        cid = self.candidato_unico()["id"]
        dedup.decidir(self.con, cid, "unificar", "revisor", "mesmo instrumento",
                     escopo="equipamento")
        res = dedup.aplicar(self.con, cid, usuario="revisor")
        self.assertTrue(res[0]["aplicado"])

        # a posicao OFICIAL segue intacta (nada de sobrescrever divergencia)
        lat = self.con.execute(
            "SELECT latitude FROM POSICAO_GEOGRAFICA WHERE registro_fonte_id = ?",
            (r_of,)).fetchone()[0]
        self.assertEqual(lat, -25.0)
        self.assertEqual(self.contar("POSICAO_GEOGRAFICA"), 2)

        ev = json.loads(self.candidato_unico()["evidencias_resumo"])
        self.assertIn("divergencia_posicao", ev)
        self.assertGreater(ev["divergencia_posicao"]["distancia_m"], 1.0)
        naturezas = {ev["divergencia_posicao"]["a"]["natureza"],
                     ev["divergencia_posicao"]["b"]["natureza"]}
        self.assertEqual(naturezas, {"oficial", "comunitaria"})

    def test_mesma_serie_varias_faixas_um_equipamento(self):
        via = self.via("BR-277")
        f = self.fonte("DER", "oficial")
        rec = self.recurso(f, "der")

        p1 = self.ponto(self.posicao(-20.0, -44.0), via, 100.0)
        self.faixa(p1, 1)
        p2 = self.ponto(self.posicao(-20.001, -44.0), via, 101.0)
        self.faixa(p2, 2)

        r1 = self.registro(self.artefato(rec), {"numero_serie": "S1539"})
        self.ligar_ponto(r1, p1)
        e1 = self.equipamento("S1539")
        self.ligar_equip(r1, e1)

        r2 = self.registro(self.artefato(rec), {"numero_serie": "S1539"})
        self.ligar_ponto(r2, p2)
        e2 = self.equipamento("S1539")
        self.ligar_equip(r2, e2)

        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)
        cid = self.candidato_unico()["id"]
        dedup.decidir(self.con, cid, "unificar", "revisor", "mesma serie",
                     escopo="equipamento")
        res = dedup.aplicar(self.con, cid, usuario="revisor")
        canonico = res[0]["equipamento_canonico"]
        self.assertIsNotNone(canonico)

        for r in (r1, r2):                       # ambos -> UM equipamento
            alvos = {row[0] for row in self.con.execute(
                "SELECT equipamento_id FROM VINCULO_REGISTRO_EQUIPAMENTO "
                "WHERE registro_id = ?", (r,))}
            self.assertIn(canonico, alvos)
        # multiplas faixas preservadas e nada apagado
        self.assertEqual(self.contar("FAIXA_FISCALIZACAO"), 2)
        self.assertEqual(self.contar("EQUIPAMENTO"), 2)
        self.assertEqual(self.contar("PONTO_FISCALIZACAO"), 2)

    def test_historico_metrologico_nao_duplica_por_faixa(self):
        e1 = self.equipamento("S1539")
        e2 = self.equipamento("S1539")
        tipo = dbmod.domain_id(self.con, "TIPO_VERIFICACAO", "periodica")
        res = dbmod.domain_id(self.con, "RESULTADO_VERIFICACAO", "conforme")
        for equip in (e1, e2):
            dbmod.insert(self.con, "VERIFICACAO_METROLOGICA", {
                "equipamento_id": equip, "tipo_verificacao_id": tipo,
                "resultado_id": res, "numero_certificado": "CERT-123",
                "data_verificacao": "2026-01-10"})
        dup = dedup.verificacoes_duplicadas(self.con, [e1, e2])
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0]["n"], 2)


class TestSerieGenerica(BaseDedup):
    """Codigo curto/repetido nao e identidade de instrumento (spec 8.5)."""

    def test_regra_por_valor(self):
        self.assertTrue(dedup.serie_generica(None))
        self.assertTrue(dedup.serie_generica("9"))
        self.assertTrue(dedup.serie_generica("224"))
        self.assertFalse(dedup.serie_generica("2244"))     # 4 digitos: ok
        self.assertFalse(dedup.serie_generica("TC005867"))
        ##-- BUNDITA DE URSO #{5} -- Mudanca de municipio nao prova reutilizacao de codigo. ##
        self.assertFalse(dedup.serie_generica("1591", municipios=[1, 2]))
        self.assertFalse(dedup.serie_generica("1591", municipios=[1, 1]))

    def test_nao_confirma_nem_bloqueia(self):
        a = {"numero_serie": "9", "serie_generica": True}
        b = {"numero_serie": "9", "serie_generica": True}
        res = dedup.pontuar(a, b)
        nomes = {c["nome"] for c in res["componentes"]}
        self.assertIn("serie_generica", nomes)
        self.assertNotIn("serie_igual", nomes)
        self.assertEqual(res["bloqueadores"], [])

    def test_curta_nao_gera_bloqueio_por_serie(self):
        f1 = self.fonte("PRF", "oficial")
        self.registro(self.artefato(self.recurso(f1, "a")),
                      {"numero_serie": "9", "latitude": -25.0,
                       "longitude": -54.0})
        f2 = self.fonte("OSM", "comunitaria")
        self.registro(self.artefato(self.recurso(f2, "b")),
                      {"numero_serie": "9", "latitude": -20.0,
                       "longitude": -44.0})
        # series iguais mas genericas: nao viram bloqueio -> nenhum par
        self.assertEqual(dedup.gerar_candidatos(self.con)["criados"], [])

    def test_serie_real_ainda_vira_candidato(self):
        # Contraponto: serie de verdade (>=4 digitos, so um municipio) segue
        # contando como identidade forte, como manda a spec 8.3.
        f1 = self.fonte("ANTT", "oficial")
        self.registro(self.artefato(self.recurso(f1, "a")),
                      {"numero_serie": "TC005867", "latitude": -25.0,
                       "longitude": -54.0})
        f2 = self.fonte("PRF", "oficial")
        self.registro(self.artefato(self.recurso(f2, "b")),
                      {"numero_serie": "TC005867", "latitude": -25.0,
                       "longitude": -54.0})
        res = dedup.gerar_candidatos(self.con)
        self.assertEqual(len(res["criados"]), 1)


if __name__ == "__main__":
    unittest.main()
