"""Localiza cadastros oficiais pela quilometragem das malhas do DNIT e da IDE-Sisema."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import malhas_oficiais as malhas
from coletor.fontes.dermg import ColetorDERMG
from coletor.fontes.dnit import ColetorDNIT
from core import caminhos, db, geo_municipio
from core.contexto_api import operacao_local


class MalhaSNV(ColetorBase):
    FONTE = ColetorDNIT.FONTE
    RECURSO = {"nome": "SNV - Rotas com quilometragem", "url_recurso": malhas.DNIT_SNV,
               "formato_origem": "zip", "status_integracao": "ok"}


class MalhaMinas(ColetorBase):
    FONTE = {"nome": "IDE-Sisema - Malha rodoviaria de Minas Gerais",
             "organizacao": "Secretaria de Estado de Meio Ambiente de Minas Gerais",
             "natureza": "oficial", "esfera": "estadual", "url_institucional": malhas.IDE_MG}
    RECURSO = {"nome": "Rede rodoviaria oficial com quilometragem", "url_recurso": malhas.IDE_MG,
               "formato_origem": "geojson", "status_integracao": "ok"}


_PONTOS_MG = """
SELECT p.id, p.km, p.municipio_id, v.codigo AS via
FROM PONTO_FISCALIZACAO p
JOIN VIA v ON v.id=p.via_id
JOIN MUNICIPIO m ON m.codigo_ibge=p.municipio_id AND m.uf_sigla='MG'
WHERE p.posicao_id IS NULL AND p.km IS NOT NULL AND p.removido_em IS NULL
  AND EXISTS (
      SELECT 1 FROM VINCULO_REGISTRO_PONTO vp
      JOIN REGISTRO_FONTE r ON r.id=vp.registro_id
      JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
      JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
      JOIN FONTE f ON f.id=rf.fonte_id
      WHERE vp.ponto_id=p.id AND vp.decisao_id IS NULL AND f.nome=?)
ORDER BY p.id
"""

_TRECHOS_PRF = """
SELECT t.id, t.uf_sigla, t.km_inicio, t.km_fim, v.codigo AS via
FROM TRECHO_ELEGIVEL t
JOIN VIA v ON v.id=t.via_id
JOIN REGISTRO_FONTE r ON r.id=t.registro_fonte_id
JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
JOIN FONTE f ON f.id=rf.fonte_id
WHERE f.nome='PRF - Trechos criticos para radar portatil'
  AND t.uf_sigla IS NOT NULL AND t.km_inicio IS NOT NULL AND t.km_fim IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM TRECHO_VERTICE tv WHERE tv.trecho_id=t.id)
ORDER BY t.id
"""


def _ler_snv(origem):
    if origem.startswith("https://"):
        if urlsplit(origem).hostname != "servicos.dnit.gov.br":
            raise ValueError("Use uma URL HTTPS do DNIT para a malha SNV")
        dado, _, destino = http.baixar(origem)
        if urlsplit(destino).hostname != "servicos.dnit.gov.br":
            raise ValueError("O recurso da malha SNV saiu do domínio oficial do DNIT")
        return dado
    return Path(caminhos.dentro_dados(origem, "arquivo SNV")).read_bytes()


def _posicao(conn, ponto, qualidade, registro, metodo):
    return db.insert(conn, "POSICAO_GEOGRAFICA", {
        "latitude": ponto[0], "longitude": ponto[1], "qualidade_posicao_id": qualidade,
        "registro_fonte_id": registro, "metodo_obtencao": metodo,
    })


def _referencia(conn, classe, corpo, formato, mime):
    coletor = classe(conn=conn)
    _, recurso = coletor.garantir_referencias()
    artefato, _, _ = coletor.registrar_artefato(recurso, corpo, formato, mime)
    return coletor.registrar_registro(artefato, 0, classe.RECURSO["nome"],
                                      {"url": classe.RECURSO["url_recurso"]})


def _aplicar_pontos(conn, planos, qualidade, registro, metodo):
    for alvo, coordenada in planos:
        posicao = _posicao(conn, coordenada, qualidade, registro, metodo)
        resultado = conn.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=? "
                                 "WHERE id=? AND posicao_id IS NULL AND removido_em IS NULL",
                                 (posicao, alvo))
        if resultado.rowcount == 0:
            conn.execute("DELETE FROM POSICAO_GEOGRAFICA WHERE id=?", (posicao,))
            continue
        db.insert(conn, "VINCULO_REGISTRO_PONTO", {"registro_id": registro, "ponto_id": alvo})


def _aplicar_trechos(conn, planos, qualidade, registro, metodo):
    for alvo, vertices in planos:
        if db.e_postgres(conn):
            conn.execute("SELECT id FROM TRECHO_ELEGIVEL WHERE id=? FOR UPDATE", (alvo,))
        if db.scalar(conn, "SELECT 1 FROM TRECHO_VERTICE WHERE trecho_id=? LIMIT 1", (alvo,)):
            continue
        for ordem, vertice in enumerate(vertices):
            posicao = _posicao(conn, vertice, qualidade, registro, metodo)
            conn.execute("INSERT INTO TRECHO_VERTICE(trecho_id,ordem,posicao_id) VALUES (?,?,?)",
                         (alvo, ordem, posicao))


def executar(conn, *, mg=False, snv=None, aplicar=False):
    resultado = {}
    trabalhos = []
    pontos_mg = db.query_all(conn, _PONTOS_MG, (ColetorDERMG.FONTE["nome"],)) if mg or snv else []
    if mg:
        pontos = [p for p in pontos_mg if re.fullmatch(r"MG\d{1,3}", malhas.rodovia(p["via"]))]
        corpo = malhas.baixar_mg([p["via"] for p in pontos]) if pontos else None
        if corpo:
            trabalhos.append((MalhaMinas, corpo, ".geojson", "application/geo+json",
                              malhas.malha_mg(json.loads(corpo)), pontos, []))
        else:
            resultado[MalhaMinas.RECURSO["nome"]] = {"pontos": 0, "trechos": 0}
    if snv:
        corpo = _ler_snv(snv)
        pontos = [p for p in pontos_mg if re.fullmatch(r"BR\d{1,3}", malhas.rodovia(p["via"]))]
        trabalhos.append((MalhaSNV, corpo, ".zip", "application/zip",
                          malhas.malha_snv(corpo), pontos, db.query_all(conn, _TRECHOS_PRF)))
    conn.rollback()  # libera o snapshot de leitura antes de abrir a transação de escrita

    for classe, corpo, ext, mime, malha, pontos, trechos in trabalhos:
        realizados_pontos, realizados_trechos = [], []
        for p in pontos:
            via = malhas.rodovia(p["via"])
            via = via[:2] + via[2:].zfill(3)
            lugar = malhas.geometria(malha.get(("MG", via), ()), p["km"], p["km"])
            if lugar and geo_municipio.municipio_por_coordenada(*lugar[0]) == p["municipio_id"]:
                realizados_pontos.append((p["id"], lugar[0]))
        for t in trechos:
            via = malhas.rodovia(t["via"])
            if not re.fullmatch(r"BR\d{1,3}", via):
                continue
            vertices = malhas.geometria(malha.get((t["uf_sigla"], "BR" + via[2:].zfill(3)), ()),
                                         t["km_inicio"], t["km_fim"])
            if vertices:
                realizados_trechos.append((t["id"], vertices))
        nome = classe.RECURSO["nome"]
        resultado[nome] = {"pontos": len(realizados_pontos), "trechos": len(realizados_trechos),
                           "pontos_sem_correspondencia": len(pontos) - len(realizados_pontos),
                           "trechos_sem_correspondencia": len(trechos) - len(realizados_trechos)}
        if aplicar and (realizados_pontos or realizados_trechos):
            registro = _referencia(conn, classe, corpo, ext, mime)
            with db.transacao(conn):
                qualidade = db.domain_id(conn, "QUALIDADE_POSICAO", "inferida")
                metodo = "Localização por quilometragem em malha oficial: " + nome
                _aplicar_pontos(conn, realizados_pontos, qualidade, registro, metodo)
                _aplicar_trechos(conn, realizados_trechos, qualidade, registro, metodo)
    return resultado


def depois_der_mg(conn):
    return executar(conn, mg=True, aplicar=True)


def depois_prf(conn):
    origem = caminhos.valor("geografia", "snv_rotas")[0]
    return executar(conn, snv=origem, aplicar=True) if origem else {}


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mg", action="store_true", help="Buscar a malha do DER-MG na IDE-Sisema")
    parser.add_argument("--snv", help="ZIP de rotas oficial do DNIT, por URL direta ou arquivo em dados.dir")
    parser.add_argument("--aplicar", action="store_true", help="Gravar as correspondências obtidas")
    args = parser.parse_args(argv)
    with closing(db.connect_existing()) as conn:
        resultado = executar(conn, mg=args.mg or not args.snv, snv=args.snv, aplicar=args.aplicar)
    print(json.dumps({"aplicado": args.aplicar, "malhas": resultado}, ensure_ascii=False, indent=2))
    return 0
