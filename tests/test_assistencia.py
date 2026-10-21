"""Assistencia com evidencias reais de fixtures e preservacao dos dados de origem."""
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from core import assistencia, assistente_ia as ia, caminhos
from core.governanca import GovernancaError
from tests.test_assistente_ia import AmbienteIA
from tests.test_dedup import BaseDedup


class TestAssistencia(BaseDedup, AmbienteIA):
    def setUp(self):
        BaseDedup.setUp(self)
        AmbienteIA.setUp(self)

    def publicar(self, nome="Fonte oficial", lat=-25.123, lon=-54.321, serie="ABC123"):
        fonte = self.fonte(nome)
        recurso = self.recurso(fonte)
        artefato = self.artefato(recurso)
        registro = self.registro(artefato, {"latitude": lat, "longitude": lon, "serie": serie, "velocidade": 60})
        ponto = self.ponto(self.posicao(lat, lon, registro_id=registro))
        self.ligar_ponto(registro, ponto)
        self.con.commit()
        return ponto, artefato, recurso

    def documento(self, conteudo, nome="Fonte oficial"):
        _, artefato, _ = self.publicar(nome)
        arquivo = Path(caminhos.bruto()) / (str(artefato) + ".pdf")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)
        self.con.execute("UPDATE ARTEFATO_COLETA SET caminho_cache=?, hash_sha256=?, bytes_arquivo=? WHERE id=?",
                         (str(arquivo), hashlib.sha256(conteudo).hexdigest(), len(conteudo), artefato))
        self.con.commit()
        return artefato

    def test_tarefas_sem_ia_preservam_banco_e_registram_relatorio(self):
        ponto, _, recurso = self.publicar()
        self.publicar("Outra fonte", -25.12301, -54.32101)
        self.con.execute("INSERT INTO EXECUCAO_COLETA(recurso_id,iniciada_em,status,tentativas,http_status,erro_detalhe) VALUES (?, '2026-10-21', 'erro', 1, 429, 'mensagem interna privada')", (recurso,))
        execucao = self.con.execute("SELECT max(id) FROM EXECUCAO_COLETA").fetchone()[0]
        self.con.commit()
        antes = tuple(self.con.iterdump())
        with patch.object(ia.urllib.request, "build_opener", side_effect=AssertionError("nao chamar IA")):
            for tarefa in ("explicacao", "auditoria", "correspondencias", "diagnostico"):
                r = assistencia.analisar(self.con, {"tarefa": tarefa, "ponto_id": ponto, "execucao_id": execucao})
                self.assertFalse(r["ia"]["usou_ia"])
                self.assertFalse(r["dados_oficiais_alterados"])
                self.assertEqual(assistencia.obter(r["id"]), r)
                self.assertNotIn("mensagem interna privada", json.dumps(r))
        self.assertEqual(tuple(self.con.iterdump()), antes)
        self.assertEqual(len(assistencia.listar()), 4)

    def test_extracao_local_guarda_pagina_trecho_hash_e_nao_inventa_campos(self):
        texto = "Latitude: -25.123 Longitude: -54.321 Velocidade: 60 km/h\fLatitude: -26.123 Longitude: -53.321"
        artefato = self.documento(texto.encode())
        r = assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        registros = r["alternativa_local"]["registros"]
        self.assertEqual([i["pagina"] for i in registros], [1, 2])
        self.assertEqual(registros[0]["velocidade"], 60)
        self.assertIsNone(registros[1]["velocidade"])
        self.assertEqual(r["alternativa_local"]["hash_sha256"], hashlib.sha256(texto.encode()).hexdigest())
        self.assertTrue(all(i["revisao_necessaria"] for i in registros))

    def test_hash_divergente_e_caminho_fora_do_cache_sao_recusados(self):
        artefato = self.documento(b"texto")
        self.con.execute("UPDATE ARTEFATO_COLETA SET hash_sha256=? WHERE id=?", ("0" * 64, artefato))
        with self.assertRaisesRegex(GovernancaError, "Hash"):
            assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        self.con.execute("UPDATE ARTEFATO_COLETA SET caminho_cache=? WHERE id=?", (str(self.conf), artefato))
        with self.assertRaisesRegex(GovernancaError, "cache"):
            assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})

    def test_documento_comunitario_bruto_permanece_local(self):
        artefato = self.documento(b"Latitude: -25.123 Longitude: -54.321")
        self.con.execute("UPDATE FONTE SET natureza_id=(SELECT id FROM NATUREZA_FONTE WHERE codigo='comunitaria')")
        self.con.commit()
        self.escrever(1, provedor="openai_compativel", url="https://api.exemplo.invalid/v1")
        with patch.object(ia.urllib.request, "build_opener", side_effect=AssertionError("nao enviar arquivo comunitario")):
            r = assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        self.assertEqual(r["ia"]["motivo"], "documento_nao_oficial_local")
        self.assertEqual(len(r["alternativa_local"]["registros"]), 1)

    def test_ia_nao_inventa_evidencia_e_fallback_local_continua(self):
        artefato = self.documento(b"Latitude: -25.123 Longitude: -54.321 Velocidade: 60 km/h")
        resposta = {"usou_ia": True, "motivo": "ok", "provedor": "teste", "modelo": "modelo",
                    "resposta": {"registros": [{"pagina": 1, "trecho": "trecho inventado", "latitude": -25.123, "longitude": -54.321}]}}
        with patch.object(ia, "consultar_json", return_value=resposta):
            r = assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        self.assertEqual(r["ia"]["motivo"], "sugestao_nao_validada")
        self.assertIsNone(r["sugestao_ia"])
        self.assertEqual(len(r["alternativa_local"]["registros"]), 1)

    def test_extracao_ia_confere_numeros_pagina_e_citacao(self):
        texto = "Latitude: -25.123 Longitude: -54.321 Velocidade: 60 km/h"
        artefato = self.documento(texto.encode())
        registro = {"pagina": 1, "trecho": texto, "latitude": -25.123, "longitude": -54.321, "velocidade": 60}
        resposta = {"usou_ia": True, "motivo": "ok", "provedor": "teste", "modelo": "modelo", "resposta": {"registros": [registro]}}
        with patch.object(ia, "consultar_json", return_value=resposta):
            r = assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        self.assertEqual(r["sugestao_ia"]["registros"][0]["velocidade"], 60)
        for troca in ({"pagina": 2}, {"velocidade": 80}, {"latitude": -12}, {"longitude": float("nan")}):
            self.assertIsNone(assistencia._validar_registro({**registro, **troca}, texto))

    def test_correspondencia_contraditoria_nao_pode_ser_promovida_pela_ia(self):
        ponto, _, _ = self.publicar()
        outro, _, _ = self.publicar("Outra fonte", -25.12301, -54.32101, "XYZ987")
        resposta = {"usou_ia": True, "motivo": "ok", "provedor": "teste", "modelo": "modelo", "resposta": {"ordem": ["P-%d" % outro]}}
        with patch.object(ia, "consultar_json", return_value=resposta):
            r = assistencia.analisar(self.con, {"tarefa": "correspondencias", "ponto_id": ponto})
        self.assertEqual(r["alternativa_local"]["candidatos"][0]["encaminhamento"], "inconclusivo_ou_contraditorio")
        self.assertFalse(r["ia"]["usou_ia"])
        self.assertEqual(self.con.execute("SELECT count(*) FROM DECISAO_DUPLICIDADE").fetchone()[0], 0)

    def test_resumo_publico_atribui_valores_e_nunca_chama_ia(self):
        ponto, _, _ = self.publicar()
        p = assistencia._ponto(self.con, ponto)
        with patch.object(ia, "consultar_json", side_effect=AssertionError("publico nao chama IA")):
            r = assistencia.resumo_local(p)
        self.assertIn("Fonte oficial publicou velocidade = 60", r["texto"])
        self.assertTrue(any(f.get("hash_artefato") for f in r["fatos"]))

    def test_pdf_sem_texto_sem_ia_nao_executa_ocr_e_pede_revisao(self):
        artefato = self.documento(b"%PDF-1.4\nstream\nsem texto\nendstream")
        with patch.object(assistencia, "_ocr_local", side_effect=AssertionError("IA desligada")):
            r = assistencia.analisar(self.con, {"tarefa": "documento", "artefato_id": artefato})
        self.assertEqual(r["alternativa_local"]["estado"], "revisar_documento")
        self.assertEqual(r["alternativa_local"]["registros"], [])

    def test_ocr_opcional_respeita_ativacao_e_forcar_sem_ia(self):
        artefato = self.documento(b"%PDF-1.4\nsem camada de texto")
        self.escrever(1)
        with patch.object(assistencia.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=b"")), \
                patch.object(assistencia, "_ocr_local", return_value="Latitude: -25.123 Longitude: -54.321") as ocr:
            local = assistencia._documento(self.con, artefato)
            self.assertEqual(local["metodo_leitura"], "ocr_local_3_paginas")
            self.assertEqual(local["registros"][0]["pagina"], 1)
            self.assertEqual(local["limite_paginas_pdf"], 3)
            ocr.assert_called_once()
            ocr.reset_mock()
            sem_ia = assistencia._documento(self.con, artefato, sem_ia=True)
            ocr.assert_not_called()
            self.assertEqual(sem_ia["estado"], "revisar_documento")

    def test_tarefa_e_relatorio_nao_aceitam_injecao_de_caminhos(self):
        for valor in ("../../radar.conf", "1;DROP TABLE FONTE"):
            with self.assertRaises(GovernancaError):
                assistencia.obter(valor)
            with self.assertRaises(GovernancaError):
                assistencia.analisar(self.con, {"tarefa": "explicacao", "ponto_id": valor})
