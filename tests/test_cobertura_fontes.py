# -*- coding: utf-8 -*-
"""Guarda por FONTE: a cobertura de municipio/posicao nao pode CAIR.

Le os pisos versionados (``config/cobertura_minima.json``) e, quando o banco de
producao esta presente, mede a cobertura real e falha se qualquer fonte cair
abaixo do piso (tolerancia 1 p.p.) ou se aparecer uma FONTE NOVA (que precisa
ser reconhecida explicitamente com ``auditar_coleta.py --atualizar-minimos``).

Em ambientes sem o banco de producao os testes de medicao sao PULADOS; a
validade do proprio arquivo de pisos e sempre verificada.
"""
import json
import os
import unittest

from core.config import ROOT
from tools import auditar_coleta as ac

DB = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
MINIMOS = os.path.join(ROOT, "config", "cobertura_minima.json")
BASELINE = os.path.join(ROOT, "config", "cobertura_fontes.json")
TOLERANCIA = 1.0


class TestPisos(unittest.TestCase):

    def test_arquivo_existe_e_e_valido(self):
        self.assertTrue(os.path.exists(MINIMOS),
                        "config/cobertura_minima.json ausente")
        with open(MINIMOS, encoding="utf-8") as f:
            dados = json.load(f)
        self.assertIsInstance(dados, dict)
        self.assertGreater(len(dados), 0)
        for fonte, d in dados.items():
            for campo in ("pct_municipio", "pct_posicao"):
                self.assertIsInstance(d.get(campo), (int, float),
                                      "%s.%s ausente" % (fonte, campo))
                self.assertGreaterEqual(d[campo], 0.0)
                self.assertLessEqual(d[campo], 100.0)

    def test_toda_fonte_do_baseline_tem_piso(self):
        if not os.path.exists(BASELINE):
            self.skipTest("baseline de cobertura ausente")
        with open(BASELINE, encoding="utf-8") as f:
            base = json.load(f)
        with open(MINIMOS, encoding="utf-8") as f:
            pisos = json.load(f)
        faltando = sorted(set(base) - set(pisos))
        self.assertEqual(faltando, [],
                         "fontes sem piso de cobertura: %s" % faltando)


@unittest.skipUnless(os.path.exists(DB), "banco de producao ausente")
class TestCoberturaReal(unittest.TestCase):

    def test_cobertura_nao_caiu(self):
        import sqlite3
        with open(MINIMOS, encoding="utf-8") as f:
            pisos = json.load(f)
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
        con.row_factory = sqlite3.Row
        try:
            atual = ac.medir(con)
        finally:
            con.close()
        self.assertNotEqual(atual, {}, "nenhum ponto medido no banco")
        alertas = ac.comparar(atual, pisos, TOLERANCIA)
        self.assertEqual(alertas, [],
                         "cobertura regrediu:\n  " + "\n  ".join(alertas))


if __name__ == "__main__":
    unittest.main()
