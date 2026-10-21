#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cliente de compatibilidade; a operacao e executada por api.pse."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cliente_api import executar


def main(argv=None):
    return executar(["ferramenta", "validar_georesolver"], argv)


if __name__ == "__main__":
    raise SystemExit(main())
