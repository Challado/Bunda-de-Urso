# -*- coding: utf-8 -*-
"""TXT: 32 colunas, delimitador trocavel, NULL=\\N, JSON em celula, escape."""
import unittest

from core.serializers import campos, txt_ser
from tests.common import exemplo_ponto


def _unquote(celula):
    if len(celula) >= 2 and celula[0] == '"' and celula[-1] == '"':
        return celula[1:-1].replace('""', '"')
    return celula


def _parse_linha(linha, delim):
    """Split respeitando aspas duplas (CSV-like, 1 delimitador de 1 char)."""
    celulas = []
    atual = []
    em_aspas = False
    i = 0
    while i < len(linha):
        ch = linha[i]
        if em_aspas:
            if ch == '"':
                if i + 1 < len(linha) and linha[i + 1] == '"':
                    atual.append('"')
                    i += 2
                    continue
                em_aspas = False
            else:
                atual.append(ch)
        else:
            if ch == '"':
                em_aspas = True
            elif ch == delim:
                celulas.append("".join(atual))
                atual = []
            else:
                atual.append(ch)
        i += 1
    celulas.append("".join(atual))
    return celulas


class TestTxt(unittest.TestCase):

    def test_trinta_e_duas_colunas(self):
        self.assertEqual(len(campos.TXT_COLUMNS), 32)
        self.assertEqual(campos.TXT_COLUMNS[0], "id")
        self.assertEqual(campos.TXT_COLUMNS[31], "quantidade_faixas_declarada")

    def test_uma_linha_por_ponto_sem_cabecalho(self):
        corpo = txt_ser.dumps([exemplo_ponto(), exemplo_ponto()], {}, "|")
        linhas = [l for l in corpo.split("\n") if l != ""]
        self.assertEqual(len(linhas), 2)
        for ln in linhas:
            self.assertEqual(len(ln.split("|")), 32)

    def test_null_marcador(self):
        p = exemplo_ponto()
        corpo = txt_ser.dumps([p], {}, "|")
        celulas = corpo.rstrip("\n").split("|")
        # precisao_metros e None -> \N (coluna 7, indice 6)
        self.assertEqual(celulas[6], "\\N")
        # distancia_metros = 0.0 -> "0.0"
        self.assertEqual(celulas[5], "0.0")

    def test_literal_backslash_n_entre_aspas(self):
        p = exemplo_ponto()
        p["observacoes"] = "\\N"
        corpo = txt_ser.dumps([p], {}, "|")
        celulas = corpo.rstrip("\n").split("|")
        # coluna 29 (indice 28) - observacoes
        self.assertEqual(celulas[28], '"\\N"')

    def test_json_em_celula(self):
        p = exemplo_ponto()
        corpo = txt_ser.dumps([p], {}, "|")
        celulas = corpo.rstrip("\n").split("|")
        # tipos_radar_presentes_json (indice 13) deve ser JSON valido
        import json
        self.assertEqual(json.loads(_unquote(celulas[13])), ["fixo"])

    def test_delimitador_ponto_e_virgula(self):
        p = exemplo_ponto()
        corpo = txt_ser.dumps([p], {}, ";")
        celulas = corpo.rstrip("\n").split(";")
        self.assertEqual(len(celulas), 32)
        self.assertEqual(_unquote(celulas[0]), "P-EXEMPLO-1")

    def test_celula_com_delimitador_recebe_aspas(self):
        p = exemplo_ponto()
        p["observacoes"] = "a;b"
        corpo = txt_ser.dumps([p], {}, ";")
        celulas = _parse_linha(corpo.rstrip("\n"), ";")
        # a celula com ';' nao quebra a linha: continuam 32 colunas
        self.assertEqual(len(celulas), 32)
        self.assertEqual(celulas[28], "a;b")

    def test_delimitador_inseguro_rejeitado(self):
        for ruim in ("\n", "\r", '"', "\x00", "ab", ""):
            if ruim == "":
                continue
            with self.assertRaises(ValueError):
                txt_ser.validar_delimitador(ruim)

    def test_delimitador_padrao_barra(self):
        self.assertEqual(txt_ser.validar_delimitador(None), "|")

    def test_corpo_vazio_sem_pontos(self):
        self.assertEqual(txt_ser.dumps([], {}, "|"), "")


if __name__ == "__main__":
    unittest.main()
