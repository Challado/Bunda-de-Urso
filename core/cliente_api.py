"""Cliente local: preserva stdin, stdout, stderr e status de api.pse."""
from pathlib import Path
import subprocess
import sys


def executar(comando, argv=None):
    argumentos = list(sys.argv[1:] if argv is None else argv)
    entrada = Path(__file__).resolve().parents[1] / "web" / "api.pse"
    return subprocess.call([sys.executable, str(entrada), *comando, *argumentos])
