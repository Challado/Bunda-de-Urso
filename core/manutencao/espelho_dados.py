"""Exporta os metadados e o backup do banco ativo para o sincronizador local."""
import argparse
from contextlib import closing
import json
from pathlib import Path

from core import caminhos, db
from core.contexto_api import operacao_local

CONTAGENS = (
    "PONTO_FISCALIZACAO", "REGISTRO_FONTE", "EQUIPAMENTO",
    "POSICAO_GEOGRAFICA", "CANDIDATO_DUPLICIDADE", "DECISAO_DUPLICIDADE",
    "RADAR_ALTERACAO", "SUBMISSAO_PUBLICA", "TRECHO_ELEGIVEL",
)


def retrato(conn):
    snapshot = db.query_one(conn, """
        SELECT id, identificador_versao FROM SNAPSHOT_PUBLICADO ORDER BY id DESC LIMIT 1
    """)
    artefatos = db.query_one(conn, """
        SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(SUM(bytes_arquivo),0) FROM ARTEFATO_COLETA_DETALHE
    """)
    return {
        "snapshot_id": snapshot[0] if snapshot else None,
        "snapshot_versao": snapshot[1] if snapshot else None,
        **{t: db.scalar(conn, "SELECT COUNT(*) FROM " + t) for t in CONTAGENS},
        "artefatos": artefatos[0], "artefato_max_id": artefatos[1], "artefato_bytes": int(artefatos[2]),
        "execucoes": db.scalar(conn, "SELECT COUNT(*) FROM EXECUCAO_COLETA"),
    }


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", help="nome de saída no diretório privado de backups")
    args = parser.parse_args(argv)
    with closing(db.connect_readonly(caminhos.banco())) as conn:
        resultado = {"motor": caminhos.motor_banco(), "retrato": retrato(conn),
                     "dados_dir": caminhos.data_dir(), "raw": caminhos.bruto(),
                     "clone": caminhos.sync_clone()}
        if not args.backup:
            resultado["brutos"] = [dict(r) for r in db.query_all(conn, """
                SELECT a.id,a.hash_sha256,a.caminho_cache,a.bytes_arquivo,a.baixado_em,
                       a.tipo_mime,a.recurso_id,r.nome AS recurso,f.nome AS fonte,
                       (SELECT MIN(e.execucao_id) FROM EXECUCAO_ARTEFATO e WHERE e.artefato_id=a.id) AS execucao
                FROM ARTEFATO_COLETA_DETALHE a JOIN RECURSO_FONTE r ON r.id=a.recurso_id
                JOIN FONTE f ON f.id=r.fonte_id ORDER BY a.id
            """)]
            resultado["execucoes"] = [dict(r) for r in db.query_all(conn, """
                SELECT e.id,f.nome AS fonte,e.recurso_id,e.iniciada_em,e.terminada_em,
                       e.status,e.http_status,e.tentativas,e.linhas_recebidas,
                       e.linhas_validas,e.linhas_rejeitadas,e.registros_criados,
                       e.registros_alterados,e.erro_codigo,e.erro_detalhe,e.artefato_id
                FROM EXECUCAO_COLETA_DETALHE e JOIN RECURSO_FONTE r ON r.id=e.recurso_id
                JOIN FONTE f ON f.id=r.fonte_id ORDER BY e.id
            """)]
    if args.backup:
        import re

        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", args.backup):
            parser.error("Informe um nome de arquivo válido, sem extensão.")
        pasta = Path(caminhos.dentro_dados("backups/espelho-dados", "backup do espelho"))
        pasta.mkdir(parents=True, mode=0o700, exist_ok=True)
        resultado["backup"] = str(db.backup_operacional(pasta, args.backup))
    print(json.dumps(resultado, ensure_ascii=False))
    return 0
