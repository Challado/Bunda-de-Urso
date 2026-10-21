"""Prepara a base da aplicacao pela API local, preservando bases existentes."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import tempfile

from core import config, db, governanca
from core.contexto_api import operacao_local


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=config.DB_PATH)
    parser.add_argument("--origem", help="snapshot existente; copiado apenas se a base destino nao existir")
    args = parser.parse_args(argv)
    destino = Path(args.db).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    if args.origem and not destino.exists():
        origem = Path(args.origem).resolve(strict=True)
        with tempfile.NamedTemporaryFile(dir=destino.parent, suffix=".sqlite3", delete=False) as f:
            temporario = Path(f.name)
        try:
            with closing(db.connect_readonly(origem)) as fonte, closing(db.connect(temporario)) as copia:
                fonte.backup(copia)
                copia.execute("PRAGMA journal_mode=DELETE")
            # Nao sobrescreve base criada em paralelo.
            os.link(temporario, destino)
        finally:
            temporario.unlink(missing_ok=True)
    with closing(db.connect(destino)) as conn:
        governanca.garantir_esquema(conn)
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Falha na integridade da base")
        print("Base preparada: %s" % destino)
    return 0
