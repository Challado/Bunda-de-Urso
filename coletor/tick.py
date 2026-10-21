#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tick do coletor: uma passada curta, dispara SO as fontes vencidas.

Feito para o cron chamar a cada minuto:

    * * * * * /usr/bin/python3 /home/openclaw/bin/radar/tick.py

Cada fonte tem o seu intervalo (coletor/agenda.py); a passada decide o que
esta vencido e coleta apenas isso. Se nada venceu, sai sem fazer nada.
Lockfile: duas passadas nunca se sobrepoem.

Nada aqui roda em tempo de requisicao da API.
"""
import argparse
import datetime
import fcntl
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config                                   # noqa: E402
from core import db as dbmod                              # noqa: E402
from coletor import agenda as agenda_mod                  # noqa: E402


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_ts(ts):
    if not ts:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def historico(conn, recurso_id, n=10):
    """Ultimas tentativas daquele recurso, da mais recente para a mais antiga."""
    return dbmod.query_all(
        conn,
        "SELECT status, iniciada_em FROM EXECUCAO_COLETA "
        "WHERE recurso_id = ? ORDER BY id DESC LIMIT ?",
        (recurso_id, n))


def espera_s(intervalo_s, hist):
    """Segundos de espera desde a ultima tentativa (qualquer status).

    Sucesso -> intervalo da fonte. Erro -> backoff exponencial por erro
    consecutivo, com piso, para nao virar tempestade de retentativas.
    """
    if not hist:
        return 0
    ##-- BUNDITA DE URSO #{16} -- Coletas sem mudanca eram contadas como erros e acumulavam backoff. ##
    if hist[0]["status"] in ("ok", "sem_mudanca"):
        intervalo = intervalo_s if intervalo_s and intervalo_s > 0 else 0
        return intervalo
    erros = 0
    for h in hist:
        if h["status"] in ("ok", "sem_mudanca"):
            break
        erros += 1
    fator = min(2 ** max(erros - 1, 0), agenda_mod.BACKOFF_TETO)
    base = intervalo_s if intervalo_s and intervalo_s > 0 else 0
    return max(base * fator, agenda_mod.BACKOFF_MINIMO_S)


def situacao(conn, item, agora):
    """Decide se a fonte esta vencida. Retorna dict de decisao."""
    conector = item["conector"](conn=conn)
    _, recurso_id = conector.garantir_referencias()
    hist = historico(conn, recurso_id)
    if not hist:
        return {"vencida": True, "motivo": "nunca_coletada",
                "recurso_id": recurso_id, "ultima": None, "espera_s": 0}
    ultima = parse_ts(hist[0]["iniciada_em"])
    espera = espera_s(item.get("intervalo_s"), hist)
    if ultima is None:
        return {"vencida": True, "motivo": "ultima_ilegivel",
                "recurso_id": recurso_id, "ultima": hist[0]["iniciada_em"],
                "espera_s": espera}
    decorrido = (agora - ultima).total_seconds()
    if decorrido >= espera:
        return {"vencida": True, "motivo": "intervalo_vencido",
                "recurso_id": recurso_id, "ultima": hist[0]["iniciada_em"],
                "espera_s": espera, "decorrido_s": int(decorrido)}
    return {"vencida": False, "motivo": "dentro_do_intervalo",
            "recurso_id": recurso_id, "ultima": hist[0]["iniciada_em"],
            "espera_s": espera, "decorrido_s": int(decorrido),
            "faltam_s": int(espera - decorrido)}


def _resolver_pos_coleta(spec):
    """Aceita callable ou 'modulo:funcao' e devolve a funcao (import tardio).

    O import e tardio de proposito: a agenda nao precisa carregar o modulo de
    pos-coleta so para decidir o que esta vencido.
    """
    if callable(spec):
        return spec
    nome_mod, _, nome_fn = str(spec).partition(":")
    if not (nome_mod and nome_fn):
        raise ValueError("pos_coleta invalido: %r" % (spec,))
    return getattr(importlib.import_module(nome_mod), nome_fn)


def executar(db_path=None, agora=None, forcar=None, arquivos=None,
             dry_run=False, agenda=None):
    """Uma passada. Retorna a lista de decisoes (testavel sem rede)."""
    agora = agora or agora_utc()
    forcar = set(forcar or ())
    arquivos = dict(arquivos or {})
    agenda = agenda or agenda_mod.carregar_agenda()
    config.ensure_dirs()
    conn = dbmod.connect(db_path or config.DB_PATH)
    dbmod.init_db(conn)
    resultados = []
    try:
        for chave, item in sorted(agenda.items()):
            if not item.get("ativo", True) and chave not in forcar:
                resultados.append({"fonte": chave, "acao": "inativo"})
                continue
            diag = situacao(conn, item, agora)
            if not diag["vencida"] and chave not in forcar:
                resultados.append({
                    "fonte": chave, "acao": "nao_vencido",
                    "intervalo_s": item.get("intervalo_s"),
                    "faltam_s": diag.get("faltam_s")})
                continue
            origem = arquivos.get(chave) or item.get("url_direta")
            if origem is None:
                resolver = getattr(item["conector"], "resolver_url", None)
                if callable(resolver):
                    try:
                        origem = resolver()
                    except Exception as exc:            # noqa: BLE001
                        resultados.append({
                            "fonte": chave, "acao": "erro",
                            "tipo": type(exc).__name__,
                            "detalhe": "resolver_url: " + str(exc)[:160]})
                        continue
            if origem is None:
                resultados.append({
                    "fonte": chave, "acao": "pulado",
                    "motivo": "sem_origem"})
                continue
            if dry_run:
                resultados.append({
                    "fonte": chave, "acao": "executaria",
                    "motivo": diag["motivo"], "origem": origem})
                continue
            conector = item["conector"](conn=conn)
            try:
                resumo = conector.sincronizar(origem)
                resultado = {
                    "fonte": chave, "acao": "erro" if resumo.get("status") == "erro" else "executado",
                    "motivo": diag["motivo"], "criados": resumo["criados"],
                    "rejeitados": resumo["rejeitados"],
                    "recebidos": resumo["linhas_recebidas"]}
                # Gancho pos-coleta: so roda se a coleta deu certo. Erro no
                # gancho NAO derruba a coleta (fica registrado no resultado).
                spec = item.get("pos_coleta")
                ##-- BUNDITA DE URSO #{9} -- Nao executar pos-coleta sobre lote vazio ou rejeitado. ##
                if spec and resumo.get("status", "ok") in ("ok", "sem_mudanca"):
                    try:
                        resultado["pos_coleta"] = _resolver_pos_coleta(spec)(conn)
                    except Exception as exc:               # noqa: BLE001
                        resultado["pos_coleta_erro"] = {
                            "tipo": type(exc).__name__, "detalhe": str(exc)[:200]}
                resultados.append(resultado)
            except Exception as exc:                       # noqa: BLE001
                resultados.append({
                    "fonte": chave, "acao": "erro",
                    "tipo": type(exc).__name__, "detalhe": str(exc)[:200]})
    finally:
        conn.close()
    return resultados


def _travar(caminho):
    f = open(caminho, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f   # mantem o fd aberto enquanto o processo viver


from core.contexto_api import operacao_local


@operacao_local
def _main_servico(argv=None):
    p = argparse.ArgumentParser(description="Radar Brasil - tick do coletor")
    p.add_argument("--db", default=None)
    p.add_argument("--forcar", action="append", default=[],
                   help="fonte a executar ignorando a agenda (repetivel)")
    p.add_argument("--arquivo", action="append", default=[],
                   metavar="FONTE=PATH", help="ingere um arquivo local")
    p.add_argument("--dry-run", action="store_true",
                   help="mostra o que faria, sem coletar")
    p.add_argument("--ticks", type=int, default=0,
                   help="0=uma passada (cron); N>0=repete N vezes")
    p.add_argument("--intervalo-tick", type=int, default=60)
    args = p.parse_args(argv)

    arquivos = {}
    for par in args.arquivo:
        k, _, v = par.partition("=")
        if k and v:
            arquivos[k] = v

    config.ensure_dirs()
    trava = _travar(os.path.join(config.DATA_DIR, "tick.lock"))
    if trava is None:
        print(json.dumps({"acao": "pulado", "motivo": "ja_em_execucao"}))
        return 0

    passadas = max(args.ticks, 1)
    for i in range(passadas):
        if i:
            import time
            time.sleep(args.intervalo_tick)
        res = executar(db_path=args.db, forcar=args.forcar,
                       arquivos=arquivos, dry_run=args.dry_run)
        print(json.dumps({"quando": agora_utc().isoformat(),
                          "resultados": res}, ensure_ascii=False),
              flush=True)
    return 0


def main(argv=None):
    from core.cliente_api import executar
    return executar(["tick"], argv)


if __name__ == "__main__":
    raise SystemExit(main())
