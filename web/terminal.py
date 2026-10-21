"""Cliente console: todas as operacoes passam por api.pse."""
from core.cliente_api import executar


def main(argv=None):
    return executar(["console"], argv)
