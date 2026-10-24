"""Reprocessa o cache das correcoes documentais/PRF sem rede ou recriar a base."""
import argparse
import hashlib
import json
from pathlib import Path

from coletor.agenda import AGENDA_PADRAO
from core import atualizacoes, config, db, caminhos
from core.contexto_api import operacao_local


def reprocessar(conn):
    resultados = []
    for chave, cfg in AGENDA_PADRAO.items():
        classe = cfg['conector']
        documental = classe.MODO_COLETA == 'documental'
        if not documental and chave != 'prf_fixos':
            continue
        recurso = db.query_one(conn, """
            SELECT r.id FROM RECURSO_FONTE r
            LEFT JOIN FONTE f ON f.id=r.fonte_id WHERE f.nome=? AND r.nome=?
        """, (classe.FONTE['nome'], classe.RECURSO['nome']))
        if recurso is None:
            continue
        artefato = db.query_one(conn, 'SELECT * FROM ARTEFATO_COLETA WHERE recurso_id=? ORDER BY id DESC LIMIT 1', (recurso['id'],))
        if artefato is None:
            continue
        rows = db.query_all(conn, """
            SELECT r.*, v.ponto_id FROM REGISTRO_FONTE r
            LEFT JOIN VINCULO_REGISTRO_PONTO v ON v.registro_id=r.id
            WHERE r.artefato_id=?
        """, (artefato['id'],))
        coletor = classe(conn=conn)
        if documental:
            pendente = bool(rows) and any(r['status_validacao'] != 'documental' for r in rows)
        else:
            pendente = any(r['ponto_id'] is None and coletor.normalizar(0, json.loads(r['payload_original'])) is not None for r in rows)
        if not pendente:
            resultados.append(dict(fonte=chave, estado='ja_corrigido'))
            continue
        try:
            arquivo = Path(caminhos.dentro_dados(artefato['caminho_cache'], 'artefato.caminho_cache'))
            if not arquivo.is_file():
                resultados.append(dict(fonte=chave, estado='pendente', motivo='Cache ausente; aguarda a proxima coleta da origem.'))
                continue
            if hashlib.sha256(arquivo.read_bytes()).hexdigest() != artefato['hash_sha256']:
                raise ValueError('Hash do cache diverge do artefato original; arquivo nao reprocessado.')
            resumo = coletor.sincronizar(str(arquivo), publicar=not documental)
            resultados.append(dict(fonte=chave, estado=resumo.get('status', 'sem_mudanca'),
                                   origem='cache_local', resumo={k:v for k,v in resumo.items() if k not in ('detalhes','cache')}))
        except Exception as exc:
            resultados.append(dict(fonte=chave, estado='erro', motivo=str(exc)))
    return resultados


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    with atualizacoes.acompanhar('reprocessar_fontes_corrigidas') as diario:
        if not Path(config.DB_PATH).is_file():
            raise FileNotFoundError('Banco existente nao encontrado; reprocessamento recusado sem criar uma base vazia.')
        conn = db.connect(config.DB_PATH)
        try:
            fontes = reprocessar(conn)
        finally:
            conn.close()
        falhou = any(r['estado'] == 'erro' for r in fontes)
        diario.terminar(1 if falhou else 0, fontes=fontes)
    print(json.dumps(atualizacoes.limpar(dict(sucesso=not falhou, fontes=fontes)),ensure_ascii=False,indent=2))
    return 1 if falhou else 0
