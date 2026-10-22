# -*- coding: utf-8 -*-
"""Valida o catalogo nacional das 27 UFs (coletor/catalogo_ufs.json).

Confere:
  - 27 UFs exatamente, no conjunto canonico esperado;
  - campos obrigatorios presentes em cada entrada;
  - cobertura_estadual_confirmada == false (nao prometer cobertura);
  - a lista de UFs do JSON bate com a do documento docs/COBERTURA_27_UFS.md.
"""
import json
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOGO = os.path.join(RAIZ, "coletor", "catalogo_ufs.json")
DOC = os.path.join(RAIZ, "docs", "COBERTURA_27_UFS.md")

UFS_CANONICAS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
]

CAMPOS_OBRIGATORIOS = [
    "uf", "nome_fonte", "orgao", "url_pagina", "classificacao_evidencia",
    "tipo_esperado", "estado_integracao", "nosso_modulo", "observacao",
    "cobertura_estadual_confirmada",
]

TIPOS_ESPERADOS = {
    "cadastro_equipamento", "operacao_real", "trecho_elegivel",
    "estudo_tecnico", "certificado_metrologico", "estatistica",
    "institucional_sem_lista",
}

ESTADOS_INTEGRACAO = {
    "implementado", "parcial", "pendente", "sem_publicacao", "pendente_lai",
}


def _carregar():
    with open(CATALOGO, "r", encoding="utf-8") as f:
        return json.load(f)


def _ufs_do_doc():
    """Extrai as siglas de UF da primeira coluna da tabela do doc de acompanhamento."""
    siglas = []
    with open(DOC, "r", encoding="utf-8") as f:
        for linha in f:
            m = re.match(r"^\|\s*([A-Z]{2})\s*\|", linha)
            if m and m.group(1) != "UF":   # ignora o cabecalho da tabela
                siglas.append(m.group(1))
    return siglas


class CatalogoUFsTest(unittest.TestCase):

    def setUp(self):
        self.doc = _carregar()
        self.ufs = self.doc["ufs"]

    def test_vinte_e_sete_ufs(self):
        self.assertEqual(len(self.ufs), 27)
        obtidas = sorted(e["uf"] for e in self.ufs)
        self.assertEqual(obtidas, sorted(UFS_CANONICAS))

    def test_sem_uf_duplicada(self):
        siglas = [e["uf"] for e in self.ufs]
        self.assertEqual(len(siglas), len(set(siglas)))

    def test_campos_obrigatorios(self):
        for e in self.ufs:
            for campo in CAMPOS_OBRIGATORIOS:
                self.assertIn(campo, e, "UF %s sem campo %s" % (e.get("uf"), campo))

    def test_tipo_e_estado_validos(self):
        for e in self.ufs:
            self.assertIn(e["tipo_esperado"], TIPOS_ESPERADOS,
                          "tipo_esperado invalido em %s" % e["uf"])
            self.assertIn(e["estado_integracao"], ESTADOS_INTEGRACAO,
                          "estado_integracao invalido em %s" % e["uf"])

    def test_cobertura_nao_confirmada(self):
        for e in self.ufs:
            self.assertIs(e["cobertura_estadual_confirmada"], False,
                          "UF %s promete cobertura" % e["uf"])

    def test_nosso_modulo_coerente_com_estado(self):
        # UF com conector nosso (implementado OU parcial) aponta o modulo; as
        # demais (pendente/sem_publicacao/pendente_lai) ficam null.
        for e in self.ufs:
            if e["estado_integracao"] in ("implementado", "parcial"):
                self.assertTrue(e["nosso_modulo"],
                                "UF %s com conector sem modulo" % e["uf"])
            else:
                self.assertIsNone(e["nosso_modulo"],
                                  "UF %s sem conector com modulo" % e["uf"])

    def test_ufs_batem_com_o_doc(self):
        self.assertEqual(sorted(UFS_CANONICAS), sorted(_ufs_do_doc()))
        self.assertEqual(sorted(e["uf"] for e in self.ufs), sorted(_ufs_do_doc()))

    def test_ufs_sem_publicacao_marcadas(self):
        por_uf = {e["uf"]: e for e in self.ufs}
        for uf in ("AL", "RN"):
            self.assertEqual(por_uf[uf]["classificacao_evidencia"],
                             "institucional_sem_lista")
            self.assertEqual(por_uf[uf]["estado_integracao"], "sem_publicacao")

    def test_ufs_historicas_nao_implementadas(self):
        por_uf = {e["uf"]: e for e in self.ufs}
        for uf in ("AC", "PI", "MT", "RR"):
            self.assertIsNone(por_uf[uf]["nosso_modulo"])
            self.assertIn(por_uf[uf]["estado_integracao"],
                          ("pendente", "pendente_lai"))

    def test_modulos_existentes_mapeados(self):
        por_uf = {e["uf"]: e for e in self.ufs}
        self.assertEqual(por_uf["SP"]["nosso_modulo"], "dersp")
        self.assertEqual(por_uf["PR"]["nosso_modulo"], "derpr")
        self.assertEqual(por_uf["MG"]["nosso_modulo"], "dermg")
        self.assertEqual(por_uf["PE"]["nosso_modulo"], "der_pe_lombadas")
        # complemento municipal de MG
        municipais = por_uf["MG"].get("modulos_municipais", [])
        self.assertIn("pbh", [m.get("modulo") for m in municipais])

    def test_modulos_ondas_1_2_mapeados(self):
        # estado REAL pos-ondas 1/2: o modulo do conector por UF.
        por_uf = {e["uf"]: e for e in self.ufs}
        esperado = {
            "GO": "goinfra", "BA": "seinfra_ba", "CE": "amc_ce",
            "RJ": "der_rj", "RS": "daer_rs", "ES": "der_es",
            "SC": "sie_sc_portateis", "AM": "immu_am", "MS": "agetran_ms",
            "PB": "semob_pb", "RO": "semtran_ro",
            "DF": "detran_df", "MA": "detran_ma",
            "SE": "der_se", "TO": "ageto_to",
        }
        for uf, modulo in esperado.items():
            self.assertEqual(por_uf[uf]["nosso_modulo"], modulo,
                             "UF %s com modulo inesperado" % uf)

    def test_catalogo_separa_esfera_e_nao_conta_diagnostico_como_pontos(self):
        from coletor.agenda import AGENDA_PADRAO
        por_uf = {e["uf"]: e for e in self.ufs}
        for uf in ("AP", "PA"):
            self.assertIsNone(por_uf[uf]["nosso_modulo"])
            self.assertTrue(por_uf[uf]["modulo_diagnostico"])
        for e in self.ufs:
            self.assertIs(e["cobertura_municipal_confirmada"], False)
            for lista, esferas in (("fontes_estaduais", ("estadual", "distrital")),
                                    ("modulos_municipais", ("municipal",))):
                for fonte in e[lista]:
                    cls = AGENDA_PADRAO[fonte["modulo"]]["conector"]
                    self.assertIn(cls.FONTE["esfera"], esferas)

    def test_diagnosticos_4_ufs_finais(self):
        # AC/AL/RN/PI: conector diagnostico que DOCUMENTA a ausencia de
        # cadastro (nao ha conector consumivel -> nosso_modulo null).
        por_uf = {e["uf"]: e for e in self.ufs}
        esperado = {
            "AC": ("detran_ac", "pendente_lai"),
            "PI": ("teresina_pi", "pendente_lai"),
            "AL": ("der_al", "sem_publicacao"),
            "RN": ("natal_rn", "sem_publicacao"),
        }
        for uf, (modulo, estado) in esperado.items():
            self.assertEqual(por_uf[uf]["modulo_diagnostico"], modulo)
            self.assertEqual(por_uf[uf]["estado_integracao"], estado)
            self.assertIsNone(por_uf[uf]["nosso_modulo"])


if __name__ == "__main__":
    unittest.main()
