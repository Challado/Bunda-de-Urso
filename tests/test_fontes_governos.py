"""Regressões de cobertura por UF e da localização por malha oficial."""
import io
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZipFile

from coletor.fontes import malhas_oficiais as malhas
from coletor.fontes.fiscalizacao_municipal import ColetorCETRio, ColetorMogiSP
from coletor.fontes.normalizacao import inserir_trecho
from coletor.fontes.prf import ColetorPRFTrechos
from core import consultas, db, governanca
from core.manutencao.georreferenciar_oficiais import _aplicar_trechos
from tests.test_dedup import BaseDedup


class TrechosPorUFTest(BaseDedup):
    def test_uf_da_coleta_e_recuperacao_da_prf_sem_municipio(self):
        governanca.garantir_esquema(self.con)
        fonte = self.fonte(ColetorPRFTrechos.FONTE["nome"])
        artefato = self.artefato(self.recurso(fonte))
        for uf in ("SC", "PR"):
            recurso = self.registro(artefato, {"ESTADO (UF)": uf}, ident=f"{uf} BR-101 0-10")
            inserir_trecho(self.con, recurso, {"via_codigo": "BR-101", "uf": uf, "km_inicio": 0, "km_fim": 10})
        self.con.execute("UPDATE TRECHO_ELEGIVEL SET uf_sigla=NULL WHERE uf_sigla='SC'")
        self.con.execute("DELETE FROM MIGRACAO_GOVERNANCA WHERE versao='0015'")
        self.con.commit()
        governanca.garantir_esquema(self.con)
        [trecho], meta = consultas.buscar_trechos(self.con, filtros={"uf": "SC"})
        self.assertEqual((trecho["uf"], trecho["municipios"], meta["total_trechos"]), ("SC", [], 1))
        self.assertEqual(consultas.buscar_trechos(self.con, limite=1)[1]["proximo_cursor"], "1")

    def test_tracado_inferido_preserva_prova_da_malha_e_nao_confirma_radar(self):
        governanca.garantir_esquema(self.con)
        fonte = self.fonte("DNIT - malha")
        registro = self.registro(self.artefato(self.recurso(fonte)), {"malha": "SNV"})
        tid = inserir_trecho(self.con, None, {"via_codigo": "BR-101", "uf": "SC"})["trecho_id"]
        qualidade = db.domain_id(self.con, "QUALIDADE_POSICAO", "inferida")
        planos = [(tid, [(-27.1, -48.8), (-27.2, -48.9)])]
        _aplicar_trechos(self.con, planos, qualidade, registro, "DNIT SNV")
        _aplicar_trechos(self.con, planos, qualidade, registro, "DNIT SNV")
        [trecho], _ = consultas.buscar_trechos(self.con)
        self.assertEqual(len(trecho["vertices"]), 2)
        self.assertFalse(trecho["geometria_confirmada"])
        self.assertTrue(trecho["geometria_inferida"])
        self.assertIsNone(trecho["radar_instalado_confirmado"])
        self.assertEqual(trecho["fontes_geometria"][0]["nome"], "DNIT - malha")


class LeitoresOficiaisTest(TestCase):
    def test_mogi_separa_avanco_de_sinal_de_medicao_de_velocidade(self):
        conteudo = ("id_radar;Logradouro;subtipo;latitude;longitude;Sentido;Velocidade;Status\n"
                    "10;Rua Um;REDUTOR DE VELOCIDADE;-23.5;-46.2;Centro-Bairro;40;Em operação\n"
                    "11;Rua Dois;AVANÇO DE SINAL;-23.6;-46.2;Bairro-Centro;0;Inativo\n")
        coletor = object.__new__(ColetorMogiSP)
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "mogi.csv"
            caminho.write_bytes(conteudo.encode("cp1252"))
            registros = coletor.carregar(str(caminho))[3]
        medidor, semaforo = [coletor.normalizar(i, r) for i, r in enumerate(registros)]
        self.assertEqual((medidor["situacao"], medidor["velocidade_geral"]), ("ativo", 40))
        self.assertEqual((semaforo["situacao"], semaforo["tipo_medicao"]), ("inativo", "outra"))
        self.assertIsNone(semaforo["velocidade_geral"])

    def test_rio_preserva_codigo_e_tipos_da_listagem(self):
        registros = ColetorCETRio.extrair_registros(
            "Lombada eletrônica\nRUA A, PRÓXIMO AO Nº 19 (123456) 40\n"
            "Avanço de sinal\nRUA B, PRÓXIMO AO Nº 58 (456789)\n")
        self.assertEqual([r["identificador"] for r in registros], ["123456", "456789"])
        self.assertEqual([r["velocidade_geral"] for r in registros], [40, None])

    def test_snv_usa_o_km_do_vertex_e_a_uf_da_rota(self):
        cabecalho_shp = struct.pack(">i", 9994) + bytes(96)
        registro = (struct.pack("<i4d3i", 23, -49, -28, -48, -27, 1, 3, 0)
                    + struct.pack("<6d", -49, -28, -48.6, -27.75, -48, -27)
                    + struct.pack("<5d", 0, 10, 0, 2, 10))
        shp = cabecalho_shp + struct.pack(">ii", 1, len(registro) // 2) + registro
        dbf = bytearray(65)
        struct.pack_into("<IHH", dbf, 4, 1, 65, 13)
        dbf[32:41], dbf[48], dbf[64] = b"vl_codigo", 12, 13
        arquivo = io.BytesIO()
        with ZipFile(arquivo, "w") as z:
            z.writestr("rotas.shp", shp)
            z.writestr("rotas.dbf", dbf + b" 101BSC2026A" + b" ")
        linhas = malhas.malha_snv(arquivo.getvalue())
        self.assertEqual(sorted(linhas), [("SC", "BR101")])
        self.assertEqual(malhas.geometria(linhas[("SC", "BR101")], 2.0, 2.0), ((-27.75, -48.6),))
        self.assertIsNone(malhas.geometria(linhas[("SC", "BR101")], 2, 11))
        self.assertIsNone(malhas.geometria(linhas[("SC", "BR101")] + [[(0, (-27, -48)), (10, (-28, -49))]], 2, 2))
