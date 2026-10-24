# -*- coding: utf-8 -*-
"""Executa a logica JavaScript real do mapa quando Node esta disponivel."""
from pathlib import Path
import shutil
import subprocess
import unittest


##-- BUNDITA DE URSO #{23} -- A conservacao no backend nao garante que o mapa percorra todas as paginas. ##
class TestPaginacaoMapa(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node necessario para executar JavaScript do mapa")
    def test_paginas_cancelamento_erros_e_avisos_por_transicao_do_raio(self):
        resultado = subprocess.run(
            [shutil.which("node"), str(Path(__file__).with_suffix(".js"))],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)


if __name__ == "__main__":
    unittest.main()
