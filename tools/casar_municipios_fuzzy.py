#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Casamento aproximado (fuzzy + fonetico) dos municipios que ficaram NULL.

Sobraram em ``PONTO_FISCALIZACAO.municipio_id`` os pontos cujo nome de
municipio publicado pela fonte NAO bate exatamente com a lista oficial do
IBGE (ex.: ``POXOREO`` x *Poxoreu*, ``SAO LUIS DO PARAITINGA`` x *Sao Luiz do
Paraitinga*, ``CARIRI DE TOCANTINS`` x *Cariri do Tocantins*). Este utilitario
faz o casamento aproximado e PREENCHE apenas quando ha confianca.

Algoritmo
---------
1. Normaliza o nome: NFKD sem acento, maiusculas, espacos colapsados,
   pontuacao removida e conectivos (DE/DA/DO/DAS/DOS/E) descartados.
2. Compara contra ``MUNICIPIO`` com ``difflib.SequenceMatcher`` (ratio) e uma
   chave fonetica simples adaptada do portugues (colapsa equivalentes:
   S/Z/X, C/K/Q, G/J, V/F, H/W/Y mudos).
3. ESCOPO: primeiro dentro da UF do payload (ou, na falta dela, da UF tirada
   do nome da fonte); sem candidato confiavel na UF, tenta NACIONALMENTE
   apenas quando o nome for unico (sem empate, com margem). Excecao: se a
   propria UF tem o alvo acrescido de qualificador (``TUNAS`` -> *Tunas do
   Parana*), nao se cruza a UF (a fonte so omitiu o qualificador).
4. PREENCHE somente quando confiante: ``ratio >= 0.85`` E margem ``>= 0.05``
   sobre o segundo colocado (leitura conservadora: o item "ratio >= 0.90" da
   regra tambem exige que nao exista quasi-empate). Nada e inventado: sem
   confianca o campo permanece NULL.

Saida (para conferencia do Lucas):
  dados/calibracao/municipios_duvidosos.csv
      nome_fonte;uf_fonte;melhor_candidato;uf_candidato;score;motivo
      (traz os NAO casados e tambem os casados com UF divergente da fonte)

Uso:
  python3 tools/casar_municipios_fuzzy.py --dry-run     # so mede e reporta
  sudo python3 tools/casar_municipios_fuzzy.py          # aplica (backup antes)
"""
import argparse
import csv
import difflib
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletor.fontes import normalizacao as nz                  # noqa: E402
from core.config import ROOT                                   # noqa: E402
from tools.preencher_municipio import (                         # noqa: E402
    extrair_municipio_uf, uf_da_fonte, SQL_PONTOS)

DB_PADRAO = os.environ.get("RADAR_DB", "/var/lib/radar-brasil/radar.sqlite3")
CSV_PADRAO = os.path.join(ROOT, "dados", "calibracao",
                          "municipios_duvidosos.csv")

# conectivos descartados na normalizacao
CONECTIVOS = frozenset(("DE", "DA", "DO", "DAS", "DOS", "E"))

LIMIAR = 0.85      # piso de ratio para preencher
MARGEM = 0.05      # vantagem minima sobre o segundo colocado


# ---------------------------------------------------------------------------
# Normalizacao e chave fonetica
# ---------------------------------------------------------------------------
def normalizar(valor):
    """Nome de municipio -> forma canonica para casamento.

    NFKD sem acento, maiusculas, pontuacao virando espaco, conectivos fora.
    Ex.: 'Sao Luiz do Paraitinga' -> 'SAO LUIZ PARAITINGA';
         "Olhos D'Agua" -> 'OLHOS AGUA'.
    """
    s = nz.normalizar_nome_texto(valor)          # NFKD, upper, espacos colapsados
    s = re.sub(r"[^A-Z0-9 ]", " ", s)            # pontuacao -> espaco
    return " ".join(t for t in s.split() if t and t not in CONECTIVOS)


_TROCAS = (("Z", "S"), ("X", "S"), ("Q", "K"), ("C", "K"), ("G", "J"),
           ("V", "F"), ("Y", "I"), ("W", "V"), ("H", ""))


def chave_fonetica(valor):
    """Chave fonetica simples (Soundex adaptado p/ portugues).

    Colapsa consoantes equivalentes e remove vogais (mantendo a inicial), de
    modo que *Poxoreu* e *Poxoreo* caiam na mesma chave (``PSR``). Serve para
    reforco do ratio e desempate; nao substitui o limiar numerico.
    """
    s = normalizar(valor).replace(" ", "")
    for a, b in _TROCAS:
        s = s.replace(a, b)
    if not s:
        return ""
    saida = s[0]
    for ch in s[1:]:
        if ch not in "AEIOU":
            saida += ch
    return saida


def score(a, b):
    """Score de similaridade 0..1 entre duas formas ja normalizadas."""
    if not a or not b:
        return 0.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    # chave fonetica igual so reforca quando o texto ja e proximo (evita que
    # um nome curto foneticamente parecido vire candidato artificial).
    if r >= 0.80 and chave_fonetica(a) == chave_fonetica(b):
        r = max(r, 0.90)
    return r


# ---------------------------------------------------------------------------
# Indice de municipios
# ---------------------------------------------------------------------------
class Indice(object):
    """Lista oficial MUNICIPIO indexada por UF e de forma nacional."""

    def __init__(self, linhas):
        self.por_uf = {}
        self.nacional = []
        for cod, uf, nome in linhas:
            norm = normalizar(nome)
            if not norm:
                continue
            item = (norm, cod, uf, nome)
            self.por_uf.setdefault(uf, []).append(item)
            self.nacional.append(item)

    @classmethod
    def do_banco(cls, conn):
        linhas = [(r["codigo_ibge"], r["uf_sigla"], r["nome"])
                  for r in conn.execute(
                      "SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO")]
        return cls(linhas)

    def _top(self, pool, alvo, k=3):
        ranque = sorted(((score(alvo, e[0]), e) for e in pool),
                        key=lambda x: (-x[0], x[1][1]))
        return ranque[:k]


def avaliar(top):
    """(best, second, confiavel, motivo) para o ranking de candidatos."""
    if not top:
        return 0.0, 0.0, False, "sem_candidato"
    best = top[0][0]
    second = top[1][0] if len(top) > 1 else 0.0
    if best < LIMIAR:
        return best, second, False, "abaixo_do_limiar"
    if (best - second) < MARGEM:
        return best, second, False, "ambiguo"
    return best, second, True, "ok"


def _qualificador_na_uf(pool, alvo):
    """Candidato da UF que e o alvo ACRESCENTADO de qualificador.

    Ex.: alvo ``TUNAS`` e candidato ``TUNAS DO PARANA`` na mesma UF. A fonte
    so omitiu o qualificador; nao se deve arriscar outro estado.
    """
    ta = set(alvo.split())
    if not ta:
        return None
    for e in pool:
        if ta < set(e[0].split()):        # subconjunto estrito
            return e
    return None


def resolver(indice, nome, uf):
    """Resolve um nome (com a UF do payload, se houver) contra MUNICIPIO.

    Devolve dict com o candidato, escopo, score, margem e se preenche.
    """
    alvo = normalizar(nome)
    if not alvo:
        return None
    pool_uf = indice.por_uf.get(uf, []) if uf else []
    top = indice._top(pool_uf, alvo) if pool_uf else []
    best, second, conf, motivo = avaliar(top)
    escopo = "uf"
    if not conf:
        # a mesma UF tem o alvo com qualificador? entao nao cruza UF.
        guarda = _qualificador_na_uf(pool_uf, alvo) if pool_uf else None
        if guarda is not None:
            return {"codigo": None, "cand_nome": guarda[3], "cand_uf": guarda[2],
                    "score": best, "margem": best - second, "escopo": "uf",
                    "preenche": False, "motivo": "qualificador_na_uf"}
        top_nac = indice._top(indice.nacional, alvo)
        b2, s2, conf2, motivo2 = avaliar(top_nac)
        if b2 >= best or not top:      # nacional e mais informativo
            top, best, second, conf, motivo = top_nac, b2, s2, conf2, motivo2
            escopo = "nacional"
    cand = top[0][1] if top else None      # (norm, cod, uf, nome)
    preenche = bool(conf and cand)
    if preenche:
        if escopo == "uf":
            motivo = "casado_na_uf"
        elif uf and cand[2] != uf:
            motivo = "uf_divergente"
        else:
            motivo = "casado_nacional"
    return {
        "codigo": cand[1] if (cand and conf) else None,
        "cand_nome": cand[3] if cand else None,
        "cand_uf": cand[2] if cand else None,
        "score": best,
        "margem": best - second,
        "escopo": escopo,
        "preenche": preenche,
        "motivo": motivo,
    }


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------
FAIXAS = ((0.98, 1.01, ">= 0.98"),
          (0.90, 0.98, "0.90 - 0.98"),
          (0.85, 0.90, "0.85 - 0.90"))


def _faixa(sc):
    for lo, hi, rot in FAIXAS:
        if lo <= sc < hi:
            return rot
    return "< 0.85"


def processar(conn, aplicar=True):
    indice = Indice.do_banco(conn)
    res = {
        "total": 0, "sem_nome": 0, "preenchidos": 0, "nao_preenchidos": 0,
        "por_faixa": {rot: 0 for _, _, rot in FAIXAS},
        "por_escopo": {"uf": 0, "nacional": 0},
        "uf_divergente": 0, "na_uf_divergente": 0,
        "duvidosos": [], "atualizacoes": [], "exemplos": {},
    }
    EXEMPLOS = {"POXOREO", "SAO LUIS PARAITINGA", "CARIRI TOCANTINS",
                "BRASILIA", "BOA VISTA"}
    for r in conn.execute(SQL_PONTOS):
        res["total"] += 1
        nome, uf = extrair_municipio_uf(r["payload"])
        if not nome:
            res["sem_nome"] += 1
            continue
        if not uf:
            uf = uf_da_fonte(r["fonte"])
        d = resolver(indice, nome, uf)
        if d is None:
            res["sem_nome"] += 1
            continue
        if normalizar(nome) in EXEMPLOS and normalizar(nome) not in res["exemplos"]:
            res["exemplos"][normalizar(nome)] = dict(d, nome_fonte=nome, uf_fonte=uf)
        if d["preenche"]:
            res["preenchidos"] += 1
            res["por_faixa"][_faixa(d["score"])] += 1
            res["por_escopo"][d["escopo"]] += 1
            res["atualizacoes"].append((d["codigo"], r["ponto_id"]))
            if d["motivo"] == "uf_divergente":
                res["uf_divergente"] += 1
                res["duvidosos"].append((nome, uf, d["cand_nome"], d["cand_uf"],
                                         d["score"], "uf_divergente"))
        else:
            res["nao_preenchidos"] += 1
            res["duvidosos"].append((nome, uf, d["cand_nome"], d["cand_uf"],
                                     d["score"], d["motivo"]))
    if aplicar and res["atualizacoes"]:
        conn.executemany(
            "UPDATE PONTO_FISCALIZACAO SET municipio_id=? WHERE id=?",
            res["atualizacoes"])
        conn.commit()
    return res


def escrever_csv(caminho, duvidosos):
    """CSV de conferencia: uma linha por decisao distinta (sem repetir pontos)."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    vistos = set()
    linhas = []
    for nome, uf, cand, cand_uf, sc, motivo in duvidosos:
        chave = (nome or "", uf or "", cand or "", cand_uf or "", motivo)
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append((motivo, nome or "", uf or "", cand or "", cand_uf or "",
                       "%.3f" % sc if sc else ""))
    linhas.sort()
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["nome_fonte", "uf_fonte", "melhor_candidato",
                    "uf_candidato", "score", "motivo"])
        for _m, nome, uf, cand, cand_uf, sc in linhas:
            w.writerow([nome, uf, cand, cand_uf, sc, _m])
    return caminho, len(linhas)


def contar(conn, cond=""):
    return conn.execute(
        "SELECT COUNT(*) FROM PONTO_FISCALIZACAO %s" % cond).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Casamento aproximado (fuzzy/fonetico) de municipio.")
    ap.add_argument("--db", default=DB_PADRAO, help="banco SQLite")
    ap.add_argument("--saida", default=CSV_PADRAO,
                    help="CSV de municipios duvidosos")
    ap.add_argument("--dry-run", action="store_true",
                    help="mede e reporta sem gravar no banco")
    ap.add_argument("--sem-backup", action="store_true",
                    help="nao faz backup antes de gravar (nao recomendado)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("ERRO: banco nao encontrado: %s" % args.db, file=sys.stderr)
        return 2

    aplicar = not args.dry_run
    if aplicar and not args.sem_backup:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = "%s.bak.%s" % (args.db, ts)
        shutil.copy2(args.db, destino)
        print("backup: %s" % destino)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        antes = contar(conn, "WHERE municipio_id IS NOT NULL")
        res = processar(conn, aplicar=aplicar)
        depois = contar(conn, "WHERE municipio_id IS NOT NULL")
    finally:
        conn.close()

    csv_path, n_duv = escrever_csv(args.saida, res["duvidosos"])
    total_pontos = antes + res["total"]

    print("modo: %s" % ("dry-run (nada gravado)" if args.dry_run
                        else "aplicado"))
    print("pontos com municipio NULL analisados: %d" % res["total"])
    print("  sem nome de municipio no payload: %d" % res["sem_nome"])
    print("  preenchidos agora: %d" % res["preenchidos"])
    for _, _, rot in FAIXAS:
        print("      score %-10s %5d" % (rot, res["por_faixa"][rot]))
    print("      escopo: na UF=%d, nacional=%d (uf_divergente=%d)"
          % (res["por_escopo"]["uf"], res["por_escopo"]["nacional"],
             res["uf_divergente"]))
    print("  permanecem NULL (nao confiavel): %d" % res["nao_preenchidos"])
    print("PONTO_FISCALIZACAO com municipio: %d -> %d (de %d; %d ainda NULL)"
          % (antes, depois, total_pontos, total_pontos - depois))
    print("CSV duvidosos: %s (%d decisoes distintas)" % (csv_path, n_duv))
    print("--- exemplos ---")
    for chave in ("POXOREO", "SAO LUIS PARAITINGA", "CARIRI TOCANTINS",
                  "BRASILIA", "BOA VISTA"):
        e = res["exemplos"].get(chave)
        if not e:
            continue
        print("  %-22s uf_fonte=%-4s -> %s/%s score=%.3f margem=%.3f "
              "escopo=%s %s"
              % (chave, e["uf_fonte"] or "-", e["cand_nome"] or "-",
                 e["cand_uf"] or "-", e["score"], e["margem"], e["escopo"],
                 "PREENCHE" if e["preenche"] else "NULL (%s)" % e["motivo"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
