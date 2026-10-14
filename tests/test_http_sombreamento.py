# -*- coding: utf-8 -*-
"""Regressao: coletor/http.py NAO pode sombrear a stdlib `http`.

O cron roda ``python3 coletor/tick.py`` (por caminho), o que coloca
``coletor/`` no ``sys.path[0]``. Sem protecao, o modulo local ``coletor/http.py``
passa a sombrear a stdlib ``http`` e ``urllib.request`` (que faz
``import http.client``) quebra com import circular.

Este teste reproduz exatamente esse ``sys.path`` (coletor/ na frente) e
verifica que tanto ``coletor.agenda`` (que importa todos os conectores, logo
``coletor.http``) quanto a stdlib ``http.client`` importam sem erro.
"""
import os
import subprocess
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLETOR = os.path.join(RAIZ, "coletor")

CODIGO = (
    "import sys\n"
    "sys.path.insert(0, {coletor!r})   # simula `python3 coletor/tick.py`\n"
    "import coletor.agenda             # carrega coletor.http e todos os conectores\n"
    "import http.client                # a stdlib precisa estar intacta\n"
    "print('OK', http.client.__name__)\n"
)


class TestSemSombreamentoStdlib(unittest.TestCase):

    def test_import_por_caminho_nao_quebra_urllib(self):
        codigo = CODIGO.format(coletor=COLETOR)
        r = subprocess.run([sys.executable, "-c", codigo],
                           capture_output=True, text=True, cwd=RAIZ)
        self.assertEqual(r.returncode, 0,
                         "import por caminho quebrou:\n" + r.stderr)
        self.assertNotIn("circular import", r.stderr)
        self.assertIn("OK http.client", r.stdout)


if __name__ == "__main__":
    unittest.main()
