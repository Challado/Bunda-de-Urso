#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI de sincronizacao.

Uso:
    python3 -m coletor.sync --fonte antt --arquivo fixture.json
    python3 -m coletor.sync --fonte recife --arquivo equipamentos.csv
    python3 -m coletor.sync --fonte antt --db /caminho/radar.sqlite3
    python3 -m coletor.sync --fonte antt            # origem = URL publicada

Sempre le primeiro o arquivo bruto, persiste imutavelmente por sha256,
normaliza em transacao e publica um snapshot atomico.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config                                   # noqa: E402
from coletor.fontes.antt import ColetorANTT               # noqa: E402
from coletor.fontes.recife import ColetorRecife           # noqa: E402

FONTES = {
    "antt": ColetorANTT,
    "recife": ColetorRecife,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Radar Brasil - sincronizador")
    parser.add_argument("--fonte", required=True, choices=sorted(FONTES),
                        help="conector a executar")
    parser.add_argument("--arquivo", default=None,
                        help="arquivo local (fixture). Se ausente, baixa da URL.")
    parser.add_argument("--db", default=None, help="caminho do SQLite alvo")
    parser.add_argument("--sem-publicar", action="store_true",
                        help="nao publica snapshot (so staging)")
    args = parser.parse_args(argv)

    classe = FONTES[args.fonte]
    coletor = classe(db_path=args.db or config.DB_PATH)
    resumo = coletor.sincronizar(args.arquivo, publicar=not args.sem_publicar)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    ##-- BUNDITA DE URSO #{9} -- Lote inteiramente rejeitado nao pode devolver sucesso ao shell. ##
    return 1 if resumo.get("status") == "erro" else 0


if __name__ == "__main__":
    raise SystemExit(main())
