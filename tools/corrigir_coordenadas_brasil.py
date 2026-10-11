#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corrige/marca POSICAO_GEOGRAFICA com coordenada impossivel para o Brasil.

Tarefa: 10 posicoes publicadas por fontes estaduais (DER-SP, GOINFRA,
SEINFRA-BA) com longitude POSITIVA (impossivel no Brasil: o pais esta a
oeste de Greenwich) ou latitude == longitude (dado degenerado na fonte).

Regra (nada e inventado):
  - longitude positiva VALIDADA pela malha municipal oficial do IBGE + UF
    declarada -> o sinal oeste foi perdido na fonte; corrige para -abs(lon);
  - longitude positiva NAO consertavel, ou latitude == longitude -> preserva
    o bruto e marca a posicao como qualidade "conflitante" (quarentena).

O dado original permanece intacto em REGISTRO_FONTE.payload_original.

Uso:
  python3 tools/corrigir_coordenadas_brasil.py [--db CAMINHO] [--aplicar]

Sem --aplicar e dry-run (mostra antes/depois sem escrever). Com --aplicar,
faz backup CONSISTENTE (sqlite3.Connection.backup, o banco esta em WAL)
antes de escrever, e valida foreign_key_check + integrity_check depois.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor.fontes import normalizacao as nz    # noqa: E402

DB_PADRAO = "/var/lib/radar-brasil/radar.sqlite3"


def _iso_agora():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _uf_do_ponto(cur, posicao_id):
    """UF da malha do municipio ligado ao ponto da POSICAO (ou None)."""
    cur.execute(
        "SELECT m.uf_sigla FROM POSICAO_GEOGRAFICA p "
        "JOIN VINCULO_REGISTRO_PONTO v ON v.registro_id=p.registro_fonte_id "
        "JOIN PONTO_FISCALIZACAO pf ON pf.id=v.ponto_id "
        "LEFT JOIN MUNICIPIO m ON m.codigo_ibge=pf.municipio_id "
        "WHERE p.id=?", (posicao_id,))
    linhas = [r[0] for r in cur.fetchall() if r[0]]
    return linhas[0] if linhas else None


def _pontos_da_posicao(cur, posicao_id):
    cur.execute(
        "SELECT pf.id, pf.observacoes FROM POSICAO_GEOGRAFICA p "
        "JOIN VINCULO_REGISTRO_PONTO v ON v.registro_id=p.registro_fonte_id "
        "JOIN PONTO_FISCALIZACAO pf ON pf.id=v.ponto_id "
        "WHERE p.id=?", (posicao_id,))
    return cur.fetchall()


def _anotar_obs(cur, ponto_id, obs_atual, texto, substituir_prefixo=None):
    obs = obs_atual or ""
    if substituir_prefixo and obs.startswith(substituir_prefixo):
        obs = texto + obs[len(substituir_prefixo):]
    elif texto not in obs:
        obs = (obs + "; " + texto) if obs.strip() else texto
    cur.execute("UPDATE PONTO_FISCALIZACAO SET observacoes=? WHERE id=?",
                (obs, ponto_id))


def coletar(cur, localizar=None):
    """Lista (posicao_id, lat, lon, qualidade, plano) das linhas afetadas."""
    cur.execute(
        "SELECT p.id, p.latitude, p.longitude, q.codigo "
        "FROM POSICAO_GEOGRAFICA p "
        "JOIN QUALIDADE_POSICAO q ON q.id=p.qualidade_posicao_id "
        "WHERE p.longitude > 0 OR (p.latitude = p.longitude "
        "AND p.latitude <> 0)")
    plano = []
    for pid, lat, lon, qual in cur.fetchall():
        uf = _uf_do_ponto(cur, pid)
        if abs(lat - lon) < 1e-9:
            plano.append((pid, lat, lon, qual, {
                "acao": "quarentena",
                "motivo": "latitude igual a longitude (%.6f): coordenada "
                          "degenerada na fonte" % lat}))
            continue
        nova, corrigido, motivo = nz.normalizar_sinal_longitude(
            lat, lon, uf, localizar=localizar)
        if corrigido:
            plano.append((pid, lat, lon, qual, {
                "acao": "corrigir", "nova": nova,
                "nota": "longitude normalizada para o hemisferio oeste "
                        "(sinal oeste perdido na fonte): %.6f -> %.6f"
                        % (lon, nova)}))
        else:
            plano.append((pid, lat, lon, qual, {
                "acao": "quarentena", "motivo": motivo}))
    return plano


def aplicar(con, plano):
    cur = con.cursor()
    mudancas = 0
    for pid, lat, lon, qual, plan in plano:
        pontos = _pontos_da_posicao(cur, pid)
        if plan["acao"] == "corrigir":
            cur.execute("UPDATE POSICAO_GEOGRAFICA SET longitude=?, "
                        "qualidade_posicao_id=(SELECT id FROM "
                        "QUALIDADE_POSICAO WHERE codigo='oficial') WHERE id=?",
                        (plan["nova"], pid))
            prefixo = "QUARENTENA: coordenada fora da UF GO: %s,%s" % (lat, lon)
            for ponto_id, obs in pontos:
                _anotar_obs(cur, ponto_id, obs, plan["nota"],
                            substituir_prefixo=prefixo)
            mudancas += 1
        else:
            cur.execute("UPDATE POSICAO_GEOGRAFICA SET qualidade_posicao_id="
                        "(SELECT id FROM QUALIDADE_POSICAO WHERE "
                        "codigo='conflitante') WHERE id=?", (pid,))
            for ponto_id, obs in pontos:
                texto = "QUARENTENA: %s" % plan["motivo"]
                _anotar_obs(cur, ponto_id, obs, texto)
            mudancas += 1
    con.commit()
    return mudancas


def _backup_consistente(db, destino):
    origem = sqlite3.connect(db)
    try:
        alvo = sqlite3.connect(destino)
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
    finally:
        origem.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_PADRAO)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args(argv)

    con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    plano = coletar(con.cursor())
    con.close()

    print("Linhas afetadas: %d" % len(plano))
    for pid, lat, lon, qual, plan in plano:
        if plan["acao"] == "corrigir":
            print("  pos %s [%s]: lon %s -> %s" % (pid, qual, lon, plan["nova"]))
        else:
            print("  pos %s [%s]: MANTEM (%s) -> quarentena"
                  % (pid, qual, plan["motivo"]))

    if not args.aplicar:
        print("DRY-RUN: nada foi escrito (use --aplicar para gravar).")
        return 0

    destino = "%s.bak.%s" % (args.db, _iso_agora())
    _backup_consistente(args.db, destino)
    print("backup consistente: %s" % destino)

    con = sqlite3.connect(args.db)
    try:
        n = aplicar(con, plano)
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    print("linhas atualizadas: %d" % n)
    print("foreign_key_check: %s" % ("vazio OK" if not fk else fk))
    print("integrity_check: %s" % integridade)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
