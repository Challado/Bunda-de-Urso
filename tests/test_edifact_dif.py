# -*- coding: utf-8 -*-
"""EDIFACT e DIF FUNCIONAIS (spec 12.5/12.6, 17.5).

Verifica: envelope UNB/UNZ + UNH/UNT com contagens reais, as MESMAS 32
colunas canonicas do TXT, escape correto dos separadores e ida-e-volta
(recuperacao dos valores originais).
"""
import unittest

from core.serializers import campos, edifact_ser, dif_ser
from tests.common import exemplo_ponto


def _meta():
    return {"sucesso": True, "versao_api": "1.0", "versao_esquema": "1.0",
            "consultado_em": "2026-10-10T12:00:00+00:00",
            "resultado": {"total_pontos": 1, "total_equipamentos": 1}}


def _celula_texto(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return campos.json_cell(v)
    return str(v)


class TestEdifact(unittest.TestCase):

    def setUp(self):
        self.ponto = exemplo_ponto()
        self.meta = _meta()
        self.texto = edifact_ser.dumps([self.ponto], self.meta)
        self.segs = edifact_ser._split_segmentos(self.texto)

    def _por_tag(self, tag):
        return [s for s in self.segs
                if s.split("+", 1)[0].split(":", 1)[0] == tag]

    def test_envelope_unb_unz(self):
        self.assertTrue(self.segs[0].startswith("UNB+UNOC:3+"))
        self.assertTrue(self.segs[-1].startswith("UNZ+1+"))
        ref = self.segs[0].split("+")[-1]
        self.assertTrue(self.segs[-1].endswith(ref))
        # terminador de segmento
        self.assertTrue(self.texto.endswith("'\n"))

    def test_cabecalho_genral(self):
        unh = self._por_tag("UNH")
        self.assertEqual(len(unh), 1)
        self.assertIn("GENRAL:D:96A:UN", unh[0])
        self.assertTrue(self._por_tag("BGM"))
        self.assertTrue(self._por_tag("DTM"))
        self.assertTrue(self._por_tag("FTX"))

    def test_unt_conta_segmentos_de_verdade(self):
        unh_i = next(i for i, s in enumerate(self.segs)
                     if s.startswith("UNH+"))
        unt_i = next(i for i, s in enumerate(self.segs)
                     if s.startswith("UNT+"))
        declarado = int(self.segs[unt_i].split("+")[1])
        self.assertEqual(declarado, unt_i - unh_i + 1)

    def test_unt_conta_com_dois_pontos(self):
        texto = edifact_ser.dumps([exemplo_ponto(), exemplo_ponto()], self.meta)
        segs = edifact_ser._split_segmentos(texto)
        unh_i = next(i for i, s in enumerate(segs) if s.startswith("UNH+"))
        unt_i = next(i for i, s in enumerate(segs) if s.startswith("UNT+"))
        self.assertEqual(int(segs[unt_i].split("+")[1]), unt_i - unh_i + 1)

    def test_32_elementos_por_rad0(self):
        rad = self._por_tag("RAD0")
        self.assertEqual(len(rad), 1)
        elems = edifact_ser._split_elementos(rad[0][len("RAD0"):])[1:]
        self.assertEqual(len(elems), 32)
        self.assertEqual(len(campos.TXT_COLUMNS), 32)

    def test_ordem_das_colunas_igual_ao_txt(self):
        rad = self._por_tag("RAD0")[0]
        elems = edifact_ser._split_elementos(rad[len("RAD0"):])[1:]
        celulas = campos.build_cells(self.ponto)
        for i, celula in enumerate(celulas):
            esperado = _celula_texto(celula)
            if esperado is None:
                self.assertEqual(elems[i], "")
            else:
                self.assertEqual(edifact_ser.unesc(elems[i]), esperado)

    def test_ida_e_volta_recupera_valores(self):
        rows = edifact_ser.loads(self.texto)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 32)
        for i, celula in enumerate(campos.build_cells(self.ponto)):
            self.assertEqual(rows[0][i], _celula_texto(celula),
                             "coluna %02d" % (i + 1))

    def test_escape_de_separadores(self):
        p = exemplo_ponto()
        p["observacoes"] = "a+b'c?d:e"
        texto = edifact_ser.dumps([p], self.meta)
        rad = [s for s in edifact_ser._split_segmentos(texto)
               if s.startswith("RAD0")][0]
        elems = edifact_ser._split_elementos(rad[len("RAD0"):])[1:]
        # separadores escapados NAO criam elementos: continuam 32
        self.assertEqual(len(elems), 32)
        self.assertEqual(edifact_ser.unesc(elems[28]), "a+b'c?d:e")
        rows = edifact_ser.loads(texto)
        self.assertEqual(rows[0][28], "a+b'c?d:e")

    def test_escape_do_proprio_release(self):
        p = exemplo_ponto()
        p["observacoes"] = "??"
        rows = edifact_ser.loads(edifact_ser.dumps([p], self.meta))
        self.assertEqual(rows[0][28], "??")

    def test_null_vira_elemento_vazio(self):
        rows = edifact_ser.loads(self.texto)
        self.assertIsNone(rows[0][6])       # precisao_metros

    def test_uma_linha_por_ponto(self):
        texto = edifact_ser.dumps([exemplo_ponto(), exemplo_ponto()], self.meta)
        self.assertEqual(len(edifact_ser.loads(texto)), 2)

    def test_envolver_texto(self):
        t = edifact_ser.envolver_texto("linha A\nlinha B", self.meta)
        segs = edifact_ser._split_segmentos(t)
        self.assertTrue(segs[0].startswith("UNB+"))
        self.assertTrue(any(s.startswith("FTX+") for s in segs))
        self.assertEqual(edifact_ser.loads(t), [])
        self.assertEqual(edifact_ser.loads.texto_livre, ["linha A", "linha B"])


class TestDif(unittest.TestCase):

    def setUp(self):
        self.ponto = exemplo_ponto()
        self.meta = _meta()
        self.texto = dif_ser.dumps([self.ponto], self.meta)
        self.linhas = self.texto.split("\n")

    def test_secoes_presentes(self):
        for secao in ("TABLE", "VECTORS", "TUPLES", "DATA", "EOD"):
            self.assertIn(secao, self.linhas)

    def test_diretivas_bot_e_eod(self):
        self.assertIn("BOT", self.linhas)
        self.assertEqual(self.linhas[-3], "-1,0")
        self.assertEqual(self.linhas[-2], "EOD")

    def test_colunas_32_na_ordem(self):
        cols, rows = dif_ser.loads(self.texto)
        self.assertEqual(cols, list(campos.TXT_COLUMNS))
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 32)

    def test_ida_e_volta_recupera_valores(self):
        _cols, rows = dif_ser.loads(self.texto)
        for i, celula in enumerate(campos.build_cells(self.ponto)):
            self.assertEqual(rows[0][i], _celula_texto(celula),
                             "coluna %02d" % (i + 1))

    def test_tipo_string_e_aspas_dobradas(self):
        p = exemplo_ponto()
        p["observacoes"] = 'aspas "internas"'
        texto = dif_ser.dumps([p], self.meta)
        self.assertIn('aspas ""internas""', texto)
        _cols, rows = dif_ser.loads(texto)
        self.assertEqual(rows[0][28], 'aspas "internas"')

    def test_null_usa_keyword_na(self):
        _cols, rows = dif_ser.loads(self.texto)
        self.assertIsNone(rows[0][6])
        self.assertIn("NA", self.linhas)

    def test_null_distinto_de_string_vazia(self):
        p = exemplo_ponto()
        p["observacoes"] = ""
        _cols, rows = dif_ser.loads(dif_ser.dumps([p], self.meta))
        self.assertEqual(rows[0][28], "")
        p["observacoes"] = None
        _cols, rows = dif_ser.loads(dif_ser.dumps([p], self.meta))
        self.assertIsNone(rows[0][28])

    def test_duas_linhas_uma_por_ponto(self):
        texto = dif_ser.dumps([exemplo_ponto(), exemplo_ponto()], self.meta)
        _cols, rows = dif_ser.loads(texto)
        self.assertEqual(len(rows), 2)

    def test_envolver_texto(self):
        t = dif_ser.envolver_texto("l1\nl2", self.meta)
        cols, rows = dif_ser.loads(t)
        self.assertEqual(cols, ["linha"])
        self.assertEqual([r[0] for r in rows], ["l1", "l2"])

    def test_dif_de_zero_pontos(self):
        texto = dif_ser.dumps([], self.meta)
        cols, rows = dif_ser.loads(texto)
        self.assertEqual(cols, list(campos.TXT_COLUMNS))
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
