#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carrega a VERIFICACAO METROLOGICA do PSIE/INMETRO (tabela hoje vazia).

O PSIE publica, por instrumento verificado, o resultado e a validade da
verificacao, alem de um ``Historico`` de certificados. A camada de
normalizacao generica nao persiste isso como entidade; o dado fica integral
no payload bruto (``REGISTRO_FONTE.payload_original``). Este carregador le
esse payload JA COLETADO (sem rebaixar nada) e grava:

  VERIFICACAO_METROLOGICA (equipamento, tipo, resultado, data, validade,
  certificado, registro_origem) + VINCULO_REGISTRO_VERIFICACAO.

Regras (nada e inventado)
-------------------------
- resultado: ``Aprovado`` -> conforme; ``Reprovado`` -> nao_conforme;
  qualquer outro -> outro.  Ausente -> desconhecido.
- tipo de servico: ``Inicial`` -> inicial; ``Periodica`` -> periodica;
  ``Apos reparo``/``Reparo`` -> apos_reparo; qualquer outro -> outra.
- orgao executor: NAO publicado por registro -> fica NULL.
- datas convertidas para ISO (a fonte usa dd/mm/yyyy); se vierem
  incoerentes (validade < laudo) a validade vira NULL, para nao violar o
  CHECK sem inventar.
- IDEMPOTENTE: chave (equipamento, certificado, data) — reaplicar nao duplica.

Uso:
  python3 tools/carregar_verificacao_metrologica.py --dry-run
  sudo python3 tools/carregar_verificacao_metrologica.py --backup
"""
import argparse
import datetime
import json
import os
import shutil
import sqlite3
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import db as dbmod                          # noqa: E402

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")

SQL_INMETRO = """
SELECT r.id            AS registro_id,
       r.payload_original AS payload,
       ve.equipamento_id  AS equipamento_id
FROM REGISTRO_FONTE r
JOIN ARTEFATO_COLETA a ON a.id = r.artefato_id
JOIN RECURSO_FONTE rc ON rc.id = a.recurso_id
JOIN FONTE f ON f.id = rc.fonte_id
LEFT JOIN VINCULO_REGISTRO_EQUIPAMENTO ve ON ve.registro_id = r.id
WHERE f.nome LIKE 'INMETRO%'
"""


def _norm(v):
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v).strip())
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def data_iso(valor):
    """'04/08/2026' ou '2026-08-04' -> '2026-08-04'. Invalido -> None."""
    if not valor:
        return None
    s = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


_RESULTADO = {"aprovado": "conforme", "reprovado": "nao_conforme",
              "conforme": "conforme", "nao conforme": "nao_conforme"}


def mapear_resultado(txt):
    if not txt:
        return "desconhecido"
    return _RESULTADO.get(_norm(txt), "outro")


_TIPO = {"inicial": "inicial", "periodica": "periodica",
         "periodico": "periodica", "apos reparo": "apos_reparo",
         "reparo": "apos_reparo", "apos conserto": "apos_reparo"}


def mapear_tipo(txt):
    if not txt:
        return "desconhecida"
    return _TIPO.get(_norm(txt), "outra")


def extrair_verificacoes(payload, equipamento_id, registro_id):
    """-> lista de linhas de VERIFICACAO_METROLOGICA (dicts) do payload.

    Le o ``Historico``; quando ele nao existe, usa a verificacao vigente do
    proprio registro (UltimoResultado/DataUltimaVerificacao/DataValidade).
    """
    try:
        d = json.loads(payload) if isinstance(payload, str) else payload
    except (ValueError, TypeError):
        return []
    if not isinstance(d, dict):
        return []
    itens = [h for h in (d.get("Historico") or []) if isinstance(h, dict)]
    if not itens:
        itens = [{
            "NumeroCertificado": None,
            "DataLaudo": d.get("DataUltimaVerificacao"),
            "DataValidade": d.get("DataValidade"),
            "Resultado": d.get("UltimoResultado"),
            "TipoServico": None,
            "NumeroEnsaio": None,
            "Ano": None,
        }]
    vistos, linhas = set(), []
    for h in itens:
        data = data_iso(h.get("DataLaudo") or h.get("DataVerificacao"))
        val = data_iso(h.get("DataValidade"))
        if data and val and val < data:
            val = None                      # incoerente: nao inventa, nao viola CHECK
        cert = (h.get("NumeroCertificado") or "").strip() or None
        chave = (cert, data)
        if chave in vistos:
            continue
        vistos.add(chave)
        obs = "; ".join(t for t in (
            "Ensaio %s" % h.get("NumeroEnsaio") if h.get("NumeroEnsaio") else "",
            "Ano %s" % h.get("Ano") if h.get("Ano") else "",
            "Tipo na fonte: %s" % h.get("TipoServico") if h.get("TipoServico") else "",
        ) if t) or None
        linhas.append({
            "equipamento_id": equipamento_id,
            "resultado": mapear_resultado(h.get("Resultado")),
            "tipo": mapear_tipo(h.get("TipoServico")),
            "data_verificacao": data,
            "validade_ate": val,
            "numero_certificado": cert,
            "observacoes": obs,
            "registro_fonte_id": registro_id,
        })
    return linhas


def carregar(conn, registros, aplicar=True):
    """Insere as verificacoes (idempotente). ``registros`` = (registro_id,
    equipamento_id, payload). -> resumo."""
    existentes = set()
    for r in conn.execute("SELECT equipamento_id, numero_certificado, "
                          "data_verificacao FROM VERIFICACAO_METROLOGICA"):
        existentes.add((r[0], (r[1] or ""), (r[2] or "")))
    res = {"registros": 0, "sem_equipamento": 0, "linhas": 0, "inseridas": 0,
           "duplicadas": 0, "por_resultado": {}}
    for registro_id, equipamento_id, payload in registros:
        res["registros"] += 1
        if not equipamento_id:
            res["sem_equipamento"] += 1
            continue
        for linha in extrair_verificacoes(payload, equipamento_id, registro_id):
            res["linhas"] += 1
            chave = (equipamento_id, linha["numero_certificado"] or "",
                     linha["data_verificacao"] or "")
            if chave in existentes:
                res["duplicadas"] += 1
                continue
            res["por_resultado"][linha["resultado"]] = \
                res["por_resultado"].get(linha["resultado"], 0) + 1
            if aplicar:
                tid = dbmod.domain_id(conn, "TIPO_VERIFICACAO", linha["tipo"])
                rid = dbmod.domain_id(conn, "RESULTADO_VERIFICACAO",
                                      linha["resultado"])
                vid = dbmod.insert(conn, "VERIFICACAO_METROLOGICA", {
                    "equipamento_id": equipamento_id,
                    "tipo_verificacao_id": tid,
                    "resultado_id": rid,
                    "data_verificacao": linha["data_verificacao"],
                    "validade_ate": linha["validade_ate"],
                    "numero_certificado": linha["numero_certificado"],
                    "observacoes": linha["observacoes"],
                    "registro_fonte_id": registro_id,
                })
                conn.execute("INSERT OR IGNORE INTO VINCULO_REGISTRO_VERIFICACAO"
                             " (registro_id, verificacao_id) VALUES (?, ?)",
                             (registro_id, vid))
            existentes.add(chave)
            res["inseridas"] += 1
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Carrega a verificacao metrologica do PSIE/INMETRO.")
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--dry-run", action="store_true", help="nao grava")
    ap.add_argument("--backup", action="store_true",
                    help="copia o banco antes de gravar")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    if args.backup and not args.dry_run:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = "%s.bak.%s" % (args.db, ts)
        shutil.copy2(args.db, destino)
        print("backup: %s" % destino)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        registros = [(r["registro_id"], r["equipamento_id"], r["payload"])
                     for r in conn.execute(SQL_INMETRO)]
        antes = conn.execute(
            "SELECT COUNT(*) FROM VERIFICACAO_METROLOGICA").fetchone()[0]
        res = carregar(conn, registros, aplicar=not args.dry_run)
        if not args.dry_run:
            conn.commit()
        depois = conn.execute(
            "SELECT COUNT(*) FROM VERIFICACAO_METROLOGICA").fetchone()[0]
    finally:
        conn.close()

    print("modo: %s" % ("dry-run (nada gravado)" if args.dry_run
                        else "aplicado"))
    print("registros INMETRO lidos:   %d" % res["registros"])
    print("  sem equipamento ligado:  %d" % res["sem_equipamento"])
    print("linhas de verificacao:     %d" % res["linhas"])
    print("  inseridas agora:         %d" % res["inseridas"])
    print("  ja existentes (idemp.):  %d" % res["duplicadas"])
    print("por resultado:             %s" % res["por_resultado"])
    print("VERIFICACAO_METROLOGICA:   %d -> %d" % (antes, depois))
    return 0


if __name__ == "__main__":
    sys.exit(main())
