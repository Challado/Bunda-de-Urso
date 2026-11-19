"""Reconciliacao de equipamentos por api.pse, com simulacao e backup consistente."""
import argparse
from contextlib import closing
import datetime
import json
from pathlib import Path

from core import caminhos, db, governanca
from core.contexto_api import operacao_local
from core.equipamentos import reconciliar


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=caminhos.banco())
    parser.add_argument('--aplicar', action='store_true', help='grava apos backup; padrao simula')
    args = parser.parse_args(argv)
    with closing(db.connect_existing(args.db)) as conn:
        db.verificar_integridade(conn)
        backup = None
        if args.aplicar:
            pasta = Path(caminhos.data_dir()) / 'backups' / 'identidade'
            pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
            ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = db.backup_operacional(pasta, ts, args.db)
        # O preparador e chamado pelo instalador. Simulacao nunca migra esquema.
        if not db.tabela_existe(conn, "EQUIPAMENTO_ALIAS"):
            if not args.aplicar:
                raise RuntimeError('Prepare o esquema pela API antes de simular a reconciliacao.')
            governanca.garantir_esquema(conn)
        if db.e_postgres(conn):
            conn.execute("SELECT pg_advisory_xact_lock(792078961)")
        else:
            conn.execute('BEGIN IMMEDIATE')
        try:
            from core.reparo_mapeamentos import reparar
            mapeamentos = reparar(conn)
            resumo = reconciliar(conn)
            resumo["mapeamentos"] = mapeamentos
            db.verificar_integridade(conn)
            if args.aplicar:
                conn.commit()
            else:
                conn.rollback()
        except BaseException:
            conn.rollback()
            raise
    print(json.dumps(dict(resumo, modo='aplicado' if args.aplicar else 'simulacao',
                          backup=str(backup) if backup else None), ensure_ascii=False))
    return 0
