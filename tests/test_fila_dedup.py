# -*- coding: utf-8 -*-
"""Fila por entidade/escopo: historico nao multiplica propostas nem vira prova."""
import json
from pathlib import Path
import sqlite3
import tempfile

from core import consultas, db, dedup
from tests.test_dedup import BaseDedup
from core.manutencao.auditar_deduplicacao import _inventario
from core.manutencao.auditar_deduplicacao import auditar
from core.manutencao.listar_duplicidades import listar


class TestFilaDedup(BaseDedup):
    def lado(self, nome, payload, recurso=None, ponto=None, equipamento=None):
        recurso = recurso or self.recurso(self.fonte(nome))
        rid = self.registro(self.artefato(recurso), payload)
        if ponto is None:
            ponto = self.ponto()
        if equipamento is None:
            equipamento = self.equipamento(payload.get("numero_serie"))
        self.ligar_ponto(rid, ponto)
        self.ligar_equip(rid, equipamento)
        return rid, ponto, equipamento, recurso

    def evidencia(self, diagnostico=False):
        rows = dedup.candidatos(self.con, incluir_diagnosticos=diagnostico)
        self.assertEqual(len(rows), 1)
        return rows[0], json.loads(rows[0]["evidencias_resumo"])

    ##-- BUNDITA DE URSO #{24} -- Campo ESTADO de situacao nao pode encobrir a UF real, independentemente da ordem do JSON. ##
    def test_prf_estado_operacional_nao_e_uf(self):
        for valor in ("ATIVO", "INOPERANTE", "E/L OU CERTIFICADO VENCIDOS"):
            rid, _, _, _ = self.lado("PRF-" + valor, {"ESTADO": valor, "UF": "sc"})
            self.assertEqual(dedup.atributos_registro(self.con, rid)["uf"], "SC")

    def test_uf_valida_nome_completo_sem_aceitar_situacao(self):
        self.assertEqual(dedup._uf_payload({"estado": "Santa Catarina"}), "SC")
        self.assertIsNone(dedup._uf_payload({"estado": "ATIVO", "uf": "XX"}))
        rid, _, _, _ = self.lado("sem UF", {"ESTADO": "INOPERANTE"})
        self.assertIsNone(dedup.atributos_registro(self.con, rid)["uf"])

    def test_coordenada_invalida_nao_corroborra_serie(self):
        for nome in ("A", "B"):
            rid, _, _, _ = self.lado(nome, {"latitude": -27.651668, "longitude": -48676127,
                                           "numero_serie": "R14119"})
            attrs = dedup.atributos_registro(self.con, rid)
            self.assertIsNone(attrs["latitude"])
            self.assertIsNone(attrs["longitude"])
        dedup.gerar_candidatos(self.con)
        self.assertEqual(dedup.candidatos(self.con), [])
        _, ev = self.evidencia(True)
        self.assertIsNone(ev["distancia_m"])

    def test_pontuacao_direta_recusa_geografia_invalida(self):
        a = {"numero_serie": "R14119", "rodovia": "BR-101", "km": 100, "uf": "ATIVO"}
        for lat, lon in ((-27, -48676127), (float("nan"), -48), (91, -48)):
            a.update(latitude=lat, longitude=lon)
            ev = dedup.avaliar_escopos(a, dict(a))
            self.assertIsNone(ev["distancia_m"])
            self.assertEqual(ev["escopos_sugeridos"], [])

    ##-- BUNDITA DE URSO #{25} -- Historico equivalente usa um representante estavel e mantem todos os registros na evidencia. ##
    def test_historico_equivalente_nao_multiplica_pares(self):
        raw = {"numero_serie": "R14119", "latitude": -25, "longitude": -54}
        r1, ponto, equipamento, recurso = self.lado("PRF", raw)
        r2, _, _, _ = self.lado("PRF", dict(raw, dias_sem_imagens=12), recurso, ponto, equipamento)
        outro, _, _, _ = self.lado("ANTT", raw)
        antes = _inventario(self.con)
        resultado = dedup.gerar_candidatos(self.con)
        row, ev = self.evidencia()
        self.assertEqual(resultado["observacoes_equivalentes_agrupadas"], 1)
        self.assertEqual(len(resultado["criados"]), 1)
        self.assertEqual(ev["observacoes_equivalentes"], {"a": [r1, r2], "b": [outro]})
        self.assertEqual(_inventario(self.con), antes)
        r3, _, _, _ = self.lado("PRF", dict(raw, dias_sem_imagens=13), recurso, ponto, equipamento)
        novamente = dedup.gerar_candidatos(self.con)
        self.assertEqual(novamente["criados"], [])
        self.assertEqual(novamente["existentes"], [row["id"]])
        row2, ev2 = self.evidencia()
        self.assertEqual(row2["id"], row["id"])
        self.assertEqual(ev2["observacoes_equivalentes"]["a"], [r1, r2, r3])

    def test_gps_original_diferente_nao_e_agrupado_por_ponto_mutavel(self):
        pos = self.posicao(-25, -54)
        ponto = self.ponto(pos)
        r1, _, equipamento, recurso = self.lado("PRF", {"latitude": -25, "longitude": -54}, ponto=ponto)
        r2, _, _, _ = self.lado("PRF", {"latitude": -26, "longitude": -54}, recurso, ponto, equipamento)
        attrs = {r: dedup.atributos_registro(self.con, r) for r in (r1, r2)}
        self.assertEqual(attrs[r2]["latitude"], -26)
        self.assertEqual(len(dedup._representantes(attrs)), 2)

    def test_mesmo_cadastro_sem_entidade_nao_e_agrupado_por_suposto_id(self):
        art = self.artefato(self.recurso(self.fonte("PRF")))
        ids = [self.registro(art, {"numero_serie": "TC005867", "faixa": n,
                                   "latitude": -25, "longitude": -54}, ident="MESMO") for n in (1, 2)]
        attrs = {r: dedup.atributos_registro(self.con, r) for r in ids}
        self.assertEqual(len(dedup._representantes(attrs)), 2)
        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)

    def test_observacoes_do_mesmo_ponto_e_equipamento_nao_propoem_duplicidade(self):
        r1, ponto, equipamento, recurso = self.lado("PRF", {"latitude": -25, "longitude": -54})
        self.lado("PRF", {"latitude": -25.00001, "longitude": -54}, recurso, ponto, equipamento)
        resultado = dedup.gerar_candidatos(self.con)
        self.assertEqual(resultado["criados"], [])
        self.assertEqual(resultado["pares_ja_associados"], 1)
        self.assertEqual(self.contar("REGISTRO_FONTE"), 2)

    ##-- BUNDITA DE URSO #{26} -- A fila encaminha somente o escopo sustentado pela evidencia e preserva os demais conflitos. ##
    def test_serie_diferente_permite_rever_ponto_sem_unir_aparelhos(self):
        for nome, serie in (("PRF", "R12345"), ("ANTT", "R54321")):
            self.lado(nome, {"numero_serie": serie, "latitude": -25, "longitude": -54})
        dedup.gerar_candidatos(self.con)
        row, ev = self.evidencia()
        self.assertEqual(ev["escopos_sugeridos"], ["ponto"])
        self.assertAlmostEqual(ev["score"], sum(c["contribuicao"] for c in
                                               ev["avaliacao_escopos"]["ponto"]["componentes"]))
        self.assertEqual(len(dedup.candidatos(self.con, escopo="ponto")), 1)
        self.assertEqual(dedup.candidatos(self.con, escopo="equipamento"), [])
        self.assertEqual(dedup.candidatos(self.con, escopo="ambos"), [])
        did = dedup.decidir(self.con, row["id"], "unificar", "teste", "Revisao documental de instrumento", escopo="equipamento")
        self.assertFalse(dedup.aplicar(self.con, row["id"])[0]["aplicado"])
        dedup.reverter_decisao(self.con, did, "teste")
        dedup.decidir(self.con, row["id"], "unificar", "teste", "Documento comprova mesmo local", escopo="ponto")
        self.assertTrue(dedup.aplicar(self.con, row["id"])[0]["aplicado"])
        self.assertEqual(self.contar("EQUIPAMENTO"), 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM VINCULO_REGISTRO_EQUIPAMENTO WHERE decisao_id IS NOT NULL").fetchone()[0], 0)

    def test_instrumento_movel_nao_exige_unificar_pontos_distantes(self):
        for nome, lat in (("A", -25), ("B", -26)):
            self.lado(nome, {"numero_serie": "TC005867", "fabricante": "FAB", "modelo": "MOD",
                             "latitude": lat, "longitude": -54})
        dedup.gerar_candidatos(self.con)
        row, ev = self.evidencia()
        self.assertEqual(ev["escopos_sugeridos"], ["equipamento"])
        self.assertEqual(ev["avaliacao_escopos"]["ponto"]["nivel"], "contraditorio")
        dedup.decidir(self.con, row["id"], "unificar", "teste", "Historico comprova mesmo instrumento", escopo="equipamento")
        self.assertTrue(dedup.aplicar(self.con, row["id"])[0]["aplicado"])
        self.assertEqual(self.contar("PONTO_FISCALIZACAO"), 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM VINCULO_REGISTRO_PONTO WHERE decisao_id IS NOT NULL").fetchone()[0], 0)

    def test_mesma_coordenada_vias_distintas_vai_para_diagnostico(self):
        for nome, via in (("A", "BR-101"), ("B", "BR-376")):
            self.lado(nome, {"latitude": -25, "longitude": -54, "rodovia": via, "uf": "PR"})
        dedup.gerar_candidatos(self.con)
        self.assertEqual(dedup.candidatos(self.con), [])
        row, ev = self.evidencia(True)
        self.assertEqual(ev["encaminhamento"], "diagnostico")
        self.assertEqual(ev["escopos_sugeridos"], [])
        dedup.decidir(self.con, row["id"], "unificar", "teste", "Proposta sem resolver conflito", escopo="ponto")
        self.assertFalse(dedup.aplicar(self.con, row["id"])[0]["aplicado"])

    def test_uf_divergente_bloqueia_somente_local(self):
        a = {"latitude": -25, "longitude": -54, "uf": "PR", "numero_serie": "TC005867"}
        b = dict(a, uf="SC")
        ev = dedup.avaliar_escopos(a, b)
        self.assertEqual(ev["escopos_sugeridos"], ["equipamento"])
        self.assertIn("uf_divergente", {x["nome"] for x in ev["avaliacao_escopos"]["ponto"]["bloqueadores"]})

    def test_serie_generica_sozinha_nao_identifica_instrumento(self):
        a = {"latitude": -25, "longitude": -54, "numero_serie": "14", "cadeia": "a"}
        b = dict(a, cadeia="b")
        ev = dedup.avaliar_escopos(a, b)
        self.assertEqual(ev["escopos_sugeridos"], ["ponto"])
        self.assertNotEqual(ev["nivel"], "forte")

    def test_contraditorio_e_fraco_continuam_consultaveis_sem_decisao(self):
        for nome, sentido in (("A", "crescente"), ("B", "decrescente")):
            self.lado(nome, {"latitude": -25, "longitude": -54, "sentido": sentido})
        antes = _inventario(self.con)
        dedup.gerar_candidatos(self.con)
        self.assertEqual(dedup.candidatos(self.con), [])
        self.assertEqual(len(dedup.candidatos(self.con, incluir_diagnosticos=True)), 1)
        self.assertEqual(len(dedup.candidatos(self.con, incluir_fracos=True)), 1)
        self.assertEqual(self.contar("DECISAO_DUPLICIDADE"), 0)
        self.assertEqual(_inventario(self.con), antes)

    def test_contexto_de_modelo_nao_cria_identidade_sem_serie(self):
        ev = dedup.avaliar_escopos({"fabricante": "FAB", "modelo": "MOD"},
                                  {"fabricante": "FAB", "modelo": "MOD"})
        self.assertEqual(ev["escopos_sugeridos"], [])

    def test_nova_regra_nao_reutiliza_versao_antiga(self):
        for antiga in ("dedup-1.0", "dedup-1.1"):
            with self.assertRaisesRegex(ValueError, "versao antiga"):
                dedup.gerar_candidatos(self.con, regra=antiga)
        self.assertEqual(self.contar("REGRA_DEDUPLICACAO"), 0)

    def test_escopo_de_consulta_invalido_falha_explicitamente(self):
        with self.assertRaisesRegex(ValueError, "escopo"):
            dedup.candidatos(self.con, escopo="instalacao")

    def test_serie_sem_gps_com_modelo_preserva_pista_de_instrumento(self):
        for nome in ("PRF", "INMETRO"):
            self.lado(nome, {"numero_serie": "TC005867", "fabricante": "FAB", "modelo": "MOD"})
        dedup.gerar_candidatos(self.con)
        _, ev = self.evidencia()
        self.assertEqual(ev["escopos_sugeridos"], ["equipamento"])
        self.assertIsNone(ev["distancia_m"])

    def test_fila_omite_proposta_ja_resolvida_por_decisoes_transitivas(self):
        for nome in ("A", "B", "C"):
            self.lado(nome, {"numero_serie": "TC005867", "latitude": -25, "longitude": -54})
        dedup.gerar_candidatos(self.con)
        for a, b in ((1, 2), (2, 3)):
            cid = db.scalar(self.con, "SELECT id FROM CANDIDATO_DUPLICIDADE "
                            "WHERE registro_a_id=? AND registro_b_id=?", (a, b))
            dedup.decidir(self.con, cid, "unificar", "teste", "Documento confirma as duas identidades", escopo="ambos")
            dedup.aplicar(self.con, cid)
        self.assertEqual(dedup.candidatos(self.con, estado="pendente"), [])
        pendentes = dedup.candidatos(self.con, estado="pendente", incluir_diagnosticos=True)
        self.assertEqual(len(pendentes), 1)
        ev = json.loads(pendentes[0]["evidencias_resumo"])
        self.assertEqual(ev["encaminhamento"], "ja_associado")
        self.assertEqual(ev["escopos_sugeridos"], [])

    def test_fila_salva_em_copia_pode_ser_revisada_por_escopo_e_paginada(self):
        for i in range(3):
            self.lado("F%d" % i, {"numero_serie": "R100%d" % i, "latitude": -25, "longitude": -54})
        self.con.commit()
        with tempfile.TemporaryDirectory() as pasta:
            origem, destino = Path(pasta, "original.sqlite3"), Path(pasta, "fila.sqlite3")
            c = sqlite3.connect(origem)
            self.con.backup(c)
            c.close()
            antes = origem.read_bytes()
            relatorio = auditar(origem, destino)
            self.assertEqual(relatorio["propostas_por_escopo"], {"ponto": 3})
            self.assertEqual(relatorio["fila_vigente_pendente"], 3)
            primeira = listar(destino, "ponto", limite=2)
            segunda = listar(destino, "ponto", limite=2, cursor=primeira["proximo_cursor"])
            self.assertEqual(primeira["total"], 3)
            self.assertEqual(segunda["retornados"], 1)
            ids = [r["id"] for pagina in (primeira, segunda) for r in pagina["candidatos"]]
            self.assertEqual(len(set(ids)), 3)
            self.assertEqual(listar(destino, "equipamento")["total"], 0)
            self.assertEqual(origem.read_bytes(), antes)
            with self.assertRaises(ValueError):
                auditar(origem, destino)
            with self.assertRaises(ValueError):
                auditar(origem, origem)
