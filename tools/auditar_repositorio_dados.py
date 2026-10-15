#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Confere o espelho de dados, seus brutos e o SQLite sem alterar a origem."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import dedup
from tools.auditar_deduplicacao import _conservacao_consulta


##-- BUNDITA DE URSO #{27} -- Conferir apenas o SQLite nao prova que o espelho bruto possa restaurar os mesmos registros. ##
def _csv(caminho, obrigatorias):
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        campos = leitor.fieldnames or []
        if len(campos) != len(set(campos)) or not set(obrigatorias) <= set(campos):
            raise ValueError("cabecalho invalido: " + caminho.name)
        return list(leitor)


def _arquivo_interno(raiz, relativo):
    caminho = (raiz / relativo).resolve(strict=True)
    if not caminho.is_relative_to(raiz):
        raise ValueError("arquivo fora do repositorio: " + relativo)
    return caminho


def _reler(classe, arquivo):
    from coletor.fontes.base_lwb import ColetorBaseLWB
    coletor = classe()
    # A releitura de um espelho precisa funcionar inteiramente offline.
    with patch("coletor.http.baixar", side_effect=AssertionError("rede durante releitura")), \
            patch("urllib.request.urlopen", side_effect=AssertionError("rede durante releitura")), \
            patch("socket.socket.connect", side_effect=AssertionError("rede durante releitura")):
        if classe is ColetorBaseLWB:
            registros = json.loads(arquivo.read_bytes())
            registros = registros if isinstance(registros, list) else [registros]
        else:
            registros = coletor.carregar(str(arquivo))[3]
        normalizados, rejeitados = 0, 0
        hashes = hashlib.sha256()
        for i, raw in enumerate(registros):
            texto = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            hashes.update(hashlib.sha256(texto.encode()).digest())
            try:
                dado = coletor.normalizar(i, raw)
            except ValueError:
                dado = None
            if dado is None:
                rejeitados += 1
            else:
                normalizados += 1
        return {"recebidos": len(registros), "normalizados": normalizados,
                "rejeitados": rejeitados, "sha256_registros_relidos": hashes.hexdigest()}


def auditar(repositorio, testar_coletores=False):
    raiz = Path(repositorio).resolve(strict=True)
    indice = _csv(raiz / "INDICE.csv", ("arquivo", "fonte", "recurso_id", "execucao_id",
                                          "artefato_id", "bytes", "sha256"))
    execucoes = _csv(raiz / "execucoes.csv", ("id", "recurso_id", "status", "artefato_id"))
    problemas = []
    avisos = []
    arquivos, artefatos = set(), set()
    for linha in indice:
        rel = linha["arquivo"]
        aid = int(linha["artefato_id"])
        if rel in arquivos or aid in artefatos:
            problemas.append({"codigo": "entrada_duplicada", "arquivo": rel})
        arquivos.add(rel)
        artefatos.add(aid)
        arquivo = _arquivo_interno(raiz, rel)
        with arquivo.open("rb") as f:
            assinatura = hashlib.file_digest(f, "sha256").hexdigest()
        if assinatura != linha["sha256"] or arquivo.stat().st_size != int(linha["bytes"]):
            problemas.append({"codigo": "hash_ou_bytes_divergentes", "arquivo": rel})
    extras = {str(p.relative_to(raiz)) for p in (raiz / "bruto").rglob("*") if p.is_file()} - arquivos
    for rel in sorted(extras):
        problemas.append({"codigo": "bruto_sem_indice", "arquivo": rel})
    backups = sorted((raiz / "base de dados").glob("radar-*.sqlite3.gz"))
    if not backups:
        raise ValueError("nenhum backup SQLite encontrado")
    backup = _arquivo_interno(raiz, str(backups[-1].relative_to(raiz)))
    with tempfile.TemporaryDirectory(prefix="radar-espelho-") as pasta:
        banco = Path(pasta, "radar.sqlite3")
        with gzip.open(backup, "rb") as fonte, banco.open("wb") as destino:
            shutil.copyfileobj(fonte, destino)
        conn = sqlite3.connect(banco.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            integridade = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integridade != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                problemas.append({"codigo": "integridade_sqlite"})
            mapa = {r["id"]: r for r in conn.execute("""
                SELECT a.*, f.nome fonte FROM ARTEFATO_COLETA a
                JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
                JOIN FONTE f ON f.id=rf.fonte_id""")}
            diario = {str(r["id"]): dict(r) for r in conn.execute("SELECT * FROM EXECUCAO_COLETA")}
            for linha in indice:
                art = mapa.get(int(linha["artefato_id"]))
                if (art is None or art["hash_sha256"] != linha["sha256"]
                        or art["recurso_id"] != int(linha["recurso_id"])
                        or art["fonte"] != linha["fonte"]):
                    problemas.append({"codigo": "linhagem_divergente", "arquivo": linha["arquivo"]})
                execucao = diario.get(linha["execucao_id"])
                if (execucao is None or execucao["recurso_id"] != int(linha["recurso_id"])
                        or execucao["artefato_id"] != int(linha["artefato_id"])):
                    problemas.append({"codigo": "execucao_do_artefato_divergente", "arquivo": linha["arquivo"]})
            if set(mapa) != artefatos:
                problemas.append({"codigo": "artefatos_sqlite_sem_indice"})
            ids = [r["id"] for r in execucoes]
            if len(set(ids)) != len(ids) or set(ids) != set(diario):
                problemas.append({"codigo": "ids_execucoes_divergentes"})
            for linha in execucoes:
                row = diario.get(linha["id"], {})
                if not row or any(("" if row[k] is None else str(row[k])) != valor
                                  for k, valor in linha.items() if k in row):
                    problemas.append({"codigo": "execucao_csv_divergente", "id": linha["id"]})
            conservacao = _conservacao_consulta(conn)
            if conservacao["marcacoes_nao_representadas"]:
                problemas.append({"codigo": "marcacoes_nao_representadas"})
            regras = [r[0] for r in conn.execute("SELECT versao FROM REGRA_DEDUPLICACAO ORDER BY id")]
            hashes_registros, contagens = {}, collections.Counter()
            if testar_coletores:
                for aid, assinatura in conn.execute(
                        "SELECT artefato_id,hash_registro FROM REGISTRO_FONTE "
                        "ORDER BY artefato_id,numero_ordem,id"):
                    hashes_registros.setdefault(aid, hashlib.sha256()).update(bytes.fromhex(assinatura))
                    contagens[aid] += 1
            if dedup.VERSAO_REGRA_PADRAO not in regras:
                avisos.append({"codigo": "regra_vigente_ausente_na_base",
                               "regra": dedup.VERSAO_REGRA_PADRAO})
            base = {"arquivo": backup.name, "integridade": integridade,
                    "pontos": conn.execute("SELECT COUNT(*) FROM PONTO_FISCALIZACAO").fetchone()[0],
                    "registros": conn.execute("SELECT COUNT(*) FROM REGISTRO_FONTE").fetchone()[0],
                    "regras_na_base": regras, "regra_vigente_do_codigo": dedup.VERSAO_REGRA_PADRAO,
                    **conservacao}
        finally:
            conn.close()
    releituras = []
    if testar_coletores and not problemas:
        from coletor.agenda import AGENDA_PADRAO
        classes = {v["conector"].FONTE["nome"]: v["conector"] for v in AGENDA_PADRAO.values()}
        for linha in indice:
            try:
                resultado = _reler(classes[linha["fonte"]], _arquivo_interno(raiz, linha["arquivo"]))
                aid = int(linha["artefato_id"])
                esperado = hashes_registros.get(aid, hashlib.sha256()).hexdigest()
                resultado["registros_no_snapshot"] = contagens[aid]
                resultado["registros_iguais_ao_snapshot"] = esperado == resultado["sha256_registros_relidos"]
                if contagens[aid] and not resultado["registros_iguais_ao_snapshot"]:
                    problemas.append({"codigo": "registros_relidos_divergentes", "arquivo": linha["arquivo"]})
                elif not contagens[aid] and resultado["recebidos"]:
                    avisos.append({"codigo": "bruto_sem_registros_no_snapshot", "arquivo": linha["arquivo"]})
                releituras.append({"arquivo": linha["arquivo"], **resultado})
            except Exception as exc:
                problemas.append({"codigo": "releitura_falhou", "arquivo": linha["arquivo"],
                                  "erro": type(exc).__name__, "mensagem": str(exc)})
    return {"arquivos": len(indice), "fontes": len({r["fonte"] for r in indice}),
            "bytes_brutos": sum(int(r["bytes"]) for r in indice), "execucoes": len(execucoes),
            "status_execucoes": dict(collections.Counter(r["status"] for r in execucoes)),
            "base": base, "releituras": releituras, "avisos": avisos, "problemas": problemas}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositorio", required=True, help="checkout local do repositorio de dados")
    parser.add_argument("--testar-coletores", action="store_true", help="releitura e normalizacao offline dos brutos")
    args = parser.parse_args(argv)
    resultado = auditar(args.repositorio, args.testar_coletores)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return int(bool(resultado["problemas"]))


if __name__ == "__main__":
    raise SystemExit(main())
