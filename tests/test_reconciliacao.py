# -*- coding: utf-8 -*-
"""Identidade canonica, consultas e reversoes com mais de um candidato."""
import json
import random
from unittest.mock import patch

from core import consultas, db, dedup, geo
from core.identidade import VisaoCanonica
from tests.test_dedup import BaseDedup


class TestReconciliacao(BaseDedup):
    def preparar(self, total=2):
        self.registros, self.pontos, self.equipamentos = [], [], []
        via = self.via("BR-277")
        for i in range(total):
            fonte = self.fonte("fonte-%d" % i)
            registro = self.registro(self.artefato(self.recurso(fonte)), {
                "numero_serie": "TC005867", "latitude": -25.0,
                "longitude": -54.0, "rodovia": "BR-277", "km": 100,
                "sentido": "crescente", "contexto": i})
            ponto = self.ponto(self.posicao(-25.0, -54.0, registro_id=registro), via, 100)
            equipamento = self.equipamento("TC005867")
            self.ligar_ponto(registro, ponto)
            self.ligar_equip(registro, equipamento)
            db.insert(self.con, "INSTALACAO", {"ponto_id": ponto,
                                              "equipamento_id": equipamento})
            self.registros.append(registro)
            self.pontos.append(ponto)
            self.equipamentos.append(equipamento)
        self.con.commit()
        dedup.gerar_candidatos(self.con)

    def candidato(self, a=0, b=1):
        return db.scalar(self.con, "SELECT id FROM CANDIDATO_DUPLICIDADE "
                         "WHERE registro_a_id=? AND registro_b_id=?",
                         (self.registros[a], self.registros[b]))

    def unificar(self, a=0, b=1, escopo="ambos"):
        cid = self.candidato(a, b)
        decisao = dedup.decidir(self.con, cid, "unificar", "revisor",
                               "Identidade verificada em documento", escopo=escopo)
        dedup.aplicar(self.con, cid, "revisor")
        return decisao

    def test_api_consolida_e_reverte_sem_apagar_entidades(self):
        self.preparar()
        self.faixa(self.pontos[0], 1)
        self.faixa(self.pontos[1], 2)
        decisao = self.unificar()
        pontos, meta = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertEqual(meta["total_pontos"], 1)
        self.assertEqual(meta["total_equipamentos"], 1)
        self.assertEqual(len(pontos[0]["faixas"]), 2)
        self.assertEqual(len(pontos[0]["fontes"]), 2)
        self.assertEqual(len(pontos[0]["equipamentos"][0]["instalacoes"]), 2)
        self.assertEqual(consultas.buscar_ponto_por_id(self.con, "P-2")["id"], "P-1")
        self.assertEqual(consultas.buscar_equipamento_por_id(self.con, "E-2")["id"], "E-1")
        self.assertEqual(consultas.buscar_cadastral(self.con)[1]["total_pontos"], 1)
        self.assertEqual(consultas.status_base(self.con)["total_equipamentos"], 1)
        dedup.reverter_decisao(self.con, decisao, "revisor", "Reabrir revisao")
        self.assertEqual(consultas.buscar_pontos(self.con, -25, -54, 100)[1]["total_pontos"], 2)
        self.assertEqual(self.contar("PONTO_FISCALIZACAO"), 2)
        self.assertEqual(self.contar("EQUIPAMENTO"), 2)
        self.assertEqual(self.contar("DECISAO_DUPLICIDADE"), 1)

    def test_identidade_fisica_nao_funde_pontos(self):
        self.preparar()
        self.unificar(escopo="equipamento")
        pontos, meta = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertEqual(meta["total_pontos"], 2)
        self.assertEqual(meta["total_equipamentos"], 1)
        self.assertEqual([p["equipamentos"][0]["id"] for p in pontos], ["E-1", "E-1"])

    def test_identidade_de_ponto_nao_funde_equipamentos(self):
        self.preparar()
        self.unificar(escopo="ponto")
        pontos, meta = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertEqual(meta["total_pontos"], 1)
        self.assertEqual(meta["total_equipamentos"], 2)
        self.assertEqual(len(pontos[0]["equipamentos"]), 2)

    def test_reversao_encadeada_reconstroi_decisao_restante(self):
        self.preparar(3)
        ab = self.unificar(0, 1)
        self.unificar(1, 2)
        dedup.reverter_decisao(self.con, ab, "revisor")
        visao = VisaoCanonica(self.con)
        self.assertEqual(visao.canonico("ponto", 2), visao.canonico("ponto", 3))
        self.assertNotEqual(visao.canonico("ponto", 1), visao.canonico("ponto", 2))
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM VINCULO_REGISTRO_PONTO "
                                             "WHERE registro_id=3 AND ponto_id=2").fetchone())
        evid = json.loads(db.scalar(self.con, "SELECT evidencias_resumo FROM "
                                    "CANDIDATO_DUPLICIDADE WHERE id=?", (self.candidato(1, 2),)))
        self.assertEqual(evid["ponto_canonico"], 2)

    def test_ordem_de_aplicacao_nao_muda_canonico(self):
        self.preparar(3)
        self.unificar(1, 2)
        self.unificar(0, 1)
        visao = VisaoCanonica(self.con)
        self.assertEqual([visao.canonico("ponto", i) for i in self.pontos], [1, 1, 1])
        self.assertEqual(consultas.buscar_pontos(self.con, -25, -54, 100)[1]["total_pontos"], 1)

    def test_escopo_e_autor_sao_obrigatorios(self):
        self.preparar()
        with self.assertRaisesRegex(ValueError, "escopo"):
            dedup.decidir(self.con, self.candidato(), "unificar", "revisor", "Prova")
        with self.assertRaisesRegex(ValueError, "autor"):
            dedup.decidir(self.con, self.candidato(), "unificar", "", "Prova", escopo="ponto")

    def test_nova_decisao_exige_reversao_da_anterior(self):
        self.preparar()
        self.unificar()
        with self.assertRaisesRegex(ValueError, "reverta"):
            dedup.decidir(self.con, self.candidato(), "revisar", "revisor", "Outra avaliacao")

    def test_aplicacao_e_idempotente(self):
        self.preparar()
        self.unificar()
        antes = list(self.con.execute("SELECT * FROM VINCULO_REGISTRO_PONTO"))
        resultado = dedup.aplicar(self.con, self.candidato(), "revisor")
        self.assertEqual(resultado[0]["vinculos_criados"], 0)
        self.assertEqual(antes, list(self.con.execute("SELECT * FROM VINCULO_REGISTRO_PONTO")))

    def test_erro_de_reconstrucao_desfaz_aplicacao_inteira(self):
        self.preparar()
        dedup.decidir(self.con, self.candidato(), "unificar", "revisor", "Prova", escopo="ambos")
        with patch("core.identidade.reconstruir_vinculos", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                dedup.aplicar(self.con, self.candidato(), "revisor")
        self.assertEqual(self.contar("VINCULO_REGISTRO_PONTO"), 2)
        self.assertEqual(VisaoCanonica(self.con).aliases("ponto"), [])
        self.assertEqual(dedup.candidatos(self.con)[0]["estado"], "decidido_unificar")

    def test_configuracao_da_regra_e_imutavel(self):
        self.preparar()
        pesos = dict(dedup.PESOS_PADRAO, serie=0.1)
        with self.assertRaisesRegex(ValueError, "nova versao"):
            dedup.gerar_candidatos(self.con, pesos=pesos)
        dedup.gerar_candidatos(self.con, regra="dedup-experimento", pesos=pesos)
        self.assertEqual(len(dedup.candidatos(self.con)), 1)
        self.assertEqual(len(dedup.candidatos(self.con, regra=None)), 2)

    def test_serie_isolada_nao_e_moderada(self):
        resultado = dedup.pontuar({"numero_serie": "TC005867", "cadeia": "a"},
                                  {"numero_serie": "TC005867", "cadeia": "b"})
        self.assertEqual(resultado["nivel"], "fraco")
        self.assertIsNone(resultado["distancia_m"])

    def test_decrescente_com_texto_complementar(self):
        self.assertEqual(dedup.normalizar_sentido("Decrescente (Norte/Sul)"), "decrescente")

    def test_mesmo_arquivo_pode_conter_duas_faixas_do_mesmo_aparelho(self):
        artefato = self.artefato(self.recurso(self.fonte("DER")))
        for faixa in (1, 2):
            self.registro(artefato, {"numero_serie": "TC005867", "faixa": faixa,
                                     "latitude": -25, "longitude": -54})
        self.assertEqual(len(dedup.gerar_candidatos(self.con)["criados"]), 1)
        evid = json.loads(dedup.candidatos(self.con)[0]["evidencias_resumo"])
        self.assertEqual(evid["n_evidencias_independentes"], 1)
        self.assertNotEqual(evid["nivel"], "forte")

    ##-- BUNDITA DE URSO #{3} -- Uma cadeia de unificacoes nao pode passar por cima de separacao fundamentada. ##
    def test_unificacao_transitiva_respeita_manter_separados(self):
        self.preparar(3)
        dedup.decidir(self.con, self.candidato(0, 2), "manter_separados", "revisor",
                     "Documentos comprovam instrumentos distintos", escopo="ambos")
        self.unificar(0, 1)
        cid = self.candidato(1, 2)
        dedup.decidir(self.con, cid, "unificar", "revisor", "Proposta conflitante", escopo="ambos")
        with self.assertRaisesRegex(ValueError, "manter separados"):
            dedup.aplicar(self.con, cid, "revisor")
        visao = VisaoCanonica(self.con)
        self.assertNotEqual(visao.canonico("ponto", 1), visao.canonico("ponto", 3))
        self.assertEqual(db.scalar(self.con, "SELECT estado FROM CANDIDATO_DUPLICIDADE WHERE id=?", (cid,)), "decidido_unificar")

    def test_reversao_falha_atomicamente(self):
        self.preparar()
        decisao = self.unificar()
        with patch("core.identidade.reconstruir_vinculos", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                dedup.reverter_decisao(self.con, decisao, "revisor")
        self.assertIsNone(db.scalar(self.con, "SELECT revertida_em FROM DECISAO_DUPLICIDADE WHERE id=?", (decisao,)))
        self.assertEqual(VisaoCanonica(self.con).canonico("ponto", 2), 1)

    ##-- BUNDITA DE URSO #{1} -- Preferencia oficial depende da evidencia, nao da ordem de insercao. ##
    def test_entidade_oficial_prevalece_sobre_id_menor(self):
        self.preparar()
        comunitaria = db.domain_id(self.con, "NATUREZA_FONTE", "comunitaria")
        self.con.execute("UPDATE FONTE SET natureza_id=? WHERE id=1", (comunitaria,))
        self.unificar()
        pontos, _ = consultas.buscar_pontos(self.con, -25, -54, 100)
        self.assertEqual(pontos[0]["id"], "P-2")
        self.assertEqual(pontos[0]["equipamentos"][0]["id"], "E-2")

    ##-- BUNDITA DE URSO #{17} -- Atributos para nova comparacao precisam apontar so para entidades originais. ##
    def test_vinculos_derivados_nao_entram_nos_atributos(self):
        self.preparar()
        self.unificar()
        atributos = dedup.atributos_registro(self.con, self.registros[1])
        self.assertEqual(atributos["ponto_ids"], [2])
        self.assertEqual(atributos["equipamento_ids"], [2])

    ##-- BUNDITA DE URSO #{5} -- Falta de GPS nao impede corroboração documental; mesma via/km exige escopo geográfico. ##
    def test_serie_sem_gps_exige_contexto(self):
        a = {"numero_serie": "TC005867", "cadeia": "a", "rodovia": "BR-101", "km": 100, "uf": "SC"}
        b = dict(a, cadeia="b")
        self.assertEqual(dedup.pontuar(a, b)["nivel"], "moderado")
        b["uf"] = "PR"
        self.assertEqual(dedup.pontuar(a, b)["nivel"], "fraco")
        a.update(fabricante="FAB", modelo="MODELO")
        b.update(fabricante="FAB", modelo="MODELO")
        self.assertEqual(dedup.pontuar(a, b)["nivel"], "moderado")

    def test_fracos_ficam_no_diagnostico_fora_da_fila_padrao(self):
        for nome in ("PRF", "INMETRO"):
            self.registro(self.artefato(self.recurso(self.fonte(nome))),
                          {"numero_serie": "TC005867", "contexto": nome})
        dedup.gerar_candidatos(self.con)
        self.assertEqual(dedup.candidatos(self.con), [])
        self.assertEqual(len(dedup.candidatos(self.con, incluir_fracos=True)), 1)

    ##-- BUNDITA DE URSO #{14} -- Comparar a grade com busca exaustiva protege polos, antimeridiano e limites de celulas. ##
    def test_indice_espacial_nao_perde_pares_dentro_do_raio(self):
        rng = random.Random(1304)
        coordenadas = []
        for lat, lon in ((-30, -54), (0, 0), (85, 40), (0, 179.999), (-89.9, -90)):
            coordenadas.append((lat, lon))
            coordenadas.extend((lat + rng.uniform(-0.008, 0.008),
                                ((lon + rng.uniform(-0.02, 0.02) + 180) % 360) - 180)
                               for _ in range(8))
        attrs = {i: {"latitude": lat, "longitude": lon} for i, (lat, lon) in enumerate(coordenadas)}
        esperado = {(i, j) for i in attrs for j in attrs if i < j
                    and geo.haversine_m(*coordenadas[i], *coordenadas[j]) <= 2000}
        self.assertEqual(set(dedup._pares_candidatos(list(attrs), attrs, 2000)), esperado)

    def test_mesma_br_com_km_distante_nao_compara_todos_contra_todos(self):
        attrs = {i: {"rodovia": "BR-101", "km": i * 10, "uf": "SC"} for i in range(100)}
        self.assertEqual(dedup._pares_candidatos(list(attrs), attrs, 2000), [])

    ##-- BUNDITA DE URSO #{18} -- Numeros nao finitos nao sao coordenadas ou quilometros validos. ##
    def test_numero_nao_finito_e_descartado(self):
        for numero in (float("nan"), float("inf"), float("-inf")):
            self.assertIsNone(dedup._num(numero))
            self.assertIsNone(dedup.normalizar_km(numero))
            with self.assertRaises(ValueError):
                dedup.gerar_candidatos(self.con, raio_m=numero)

    ##-- BUNDITA DE URSO #{4} -- Configuracoes invalidas devem falhar antes de persistir uma regra. ##
    def test_peso_invalido_nao_registra_regra(self):
        for pesos in ({"serie": float("nan")}, {"serie": -1}, {"serrie": 0.5}):
            with self.assertRaises(ValueError):
                dedup.gerar_candidatos(self.con, pesos=pesos)
        self.assertEqual(self.contar("REGRA_DEDUPLICACAO"), 0)

    ##-- BUNDITA DE URSO #{1} -- Consolidar instrumentos preserva historico e nao elimina verificacao sem identidade suficiente. ##
    def test_verificacoes_consolidadas_preservam_identidade_e_auditoria(self):
        self.preparar()
        tipo = db.domain_id(self.con, "TIPO_VERIFICACAO", "periodica")
        resultado = db.domain_id(self.con, "RESULTADO_VERIFICACAO", "conforme")
        for equipamento in self.equipamentos:
            for orgao in (1, None):
                db.insert(self.con, "VERIFICACAO_METROLOGICA", {
                    "equipamento_id": equipamento, "tipo_verificacao_id": tipo,
                    "resultado_id": resultado, "orgao_executor_id": orgao,
                    "data_verificacao": "2026-10-01", "numero_certificado": "CERT-1"})
        self.unificar(escopo="equipamento")
        verificacoes = consultas.buscar_equipamento_por_id(self.con, "E-2")["verificacoes_metrologicas"]
        # Uma verificacao documentada comum, duas sem executor conhecido.
        self.assertEqual(len(verificacoes), 3)
        self.assertEqual(len([v for v in verificacoes if v.get("aliases")]), 1)
        self.assertEqual(self.contar("VERIFICACAO_METROLOGICA"), 4)
