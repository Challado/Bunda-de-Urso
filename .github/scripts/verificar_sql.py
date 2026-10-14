#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paridade dos esquemas (SQLite x PostgreSQL) e aplicabilidade da DDL.

Por que existe: o projeto mantem dois DDLs do MESMO modelo relacional
(`sql/schema.sqlite.sql` e `sql/schema.postgres.sql`) mais as migracoes de
governanca por dialeto. Nada garante que eles nao divirjam -- e uma coluna que
existe so num dialeto e uma cagada silenciosa.

O que confere:
  1. as tabelas dos dois dialetos sao as MESMAS;
  2. cada tabela tem as MESMAS colunas nos dois dialetos (CREATE TABLE + ALTER
     TABLE ADD COLUMN das migracoes);
  3. o DDL do SQLite (base + migracoes) EXECUTA num banco em memoria.

Sai com 1 se houver divergencia ou erro de execucao. Uso:
    python3 .github/scripts/verificar_sql.py
"""
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SQL = RAIZ / "sql"

RESTRICOES = ("constraint", "primary", "unique", "foreign", "check", "exclude")


def tira_comentarios(texto):
    """Remove comentarios de linha (`-- ...`) sem tocar no que esta entre aspas.

    Sem isso um `;` dentro de um comentario fatiava o comando e o `CREATE TABLE`
    seguinte deixava de ser reconhecido.
    """
    saida, aspas, i = [], None, 0
    while i < len(texto):
        ch = texto[i]
        if aspas:
            saida.append(ch)
            if ch == aspas:
                aspas = None
            i += 1
            continue
        if ch in "'\"":
            aspas = ch
            saida.append(ch)
            i += 1
            continue
        if ch == "-" and texto[i:i + 2] == "--":
            while i < len(texto) and texto[i] != "\n":
                i += 1
            continue
        saida.append(ch)
        i += 1
    return "".join(saida)


def blocos(texto):
    """Divide o script em comandos, separando por ';' fora de parenteses/aspas."""
    comandos, atual, prof, aspas = [], [], 0, None
    for ch in tira_comentarios(texto):
        if aspas:
            atual.append(ch)
            if ch == aspas:
                aspas = None
            continue
        if ch in "'\"":
            aspas = ch
            atual.append(ch)
            continue
        if ch == "(":
            prof += 1
        elif ch == ")":
            prof = max(0, prof - 1)
        if ch == ";" and prof == 0:
            comandos.append("".join(atual).strip())
            atual = []
        else:
            atual.append(ch)
    if "".join(atual).strip():
        comandos.append("".join(atual).strip())
    return [limpar(c) for c in comandos if limpar(c)]


def limpar(comando):
    """Tira as linhas de comentario (`--`) para o comando poder ser reconhecido."""
    linhas = [l for l in comando.splitlines() if not l.strip().startswith("--")]
    return "\n".join(linhas).strip()


def divide_topo(corpo):
    """Separa por virgula no nivel de parenteses 0."""
    partes, atual, prof, aspas = [], [], 0, None
    for ch in corpo:
        if aspas:
            atual.append(ch)
            if ch == aspas:
                aspas = None
            continue
        if ch in "'\"":
            aspas = ch
            atual.append(ch)
            continue
        if ch == "(":
            prof += 1
        elif ch == ")":
            prof -= 1
        if ch == "," and prof == 0:
            partes.append("".join(atual).strip())
            atual = []
        else:
            atual.append(ch)
    if "".join(atual).strip():
        partes.append("".join(atual).strip())
    return partes


def coluna_de(parte):
    nome = re.match(r'^["`\[]?([A-Za-z0-9_]+)["`\]]?', parte.strip())
    return nome.group(1).lower() if nome else None


DIRETIVA = re.compile(
    r'^\s*--\s*\+COLUNA\s+["`\[]?([A-Za-z0-9_]+)["`\]]?\s+["`\[]?([A-Za-z0-9_]+)', re.I)


def ler_dialeto(sufixo):
    """tabela -> {colunas} a partir do schema base + migracoes do dialeto.

    O SQLite nao tem ADD COLUMN IF NOT EXISTS, entao a migracao declara as
    colunas novas com a diretiva `-- +COLUNA <tabela> <coluna> ...` (o runner
    em core/governanca.py traduz para ALTER TABLE so quando falta). Ler a
    diretiva e o que mantem a paridade comparavel entre os dialetos.
    """
    arquivos = sorted(SQL.glob("schema.%s.sql" % sufixo))
    arquivos += sorted((SQL / "migracoes").glob("*%s.sql" % sufixo))
    tabelas = {}
    for caminho in arquivos:
        texto = caminho.read_text(encoding="utf-8")
        for linha in texto.splitlines():
            m = DIRETIVA.match(linha)
            if m:
                tabela, col = m.group(1).lower(), m.group(2).lower()
                tabelas.setdefault(tabela, [])
                if col not in tabelas[tabela]:
                    tabelas[tabela].append(col)
        for comando in blocos(texto):
            m = re.match(
                r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z0-9_.]+)["`\]]?\s*\(',
                comando, re.I | re.S)
            if m:
                nome = m.group(1).lower()
                corpo = comando[comando.index("(") + 1:]
                corpo = corpo[:corpo.rindex(")")] if ")" in corpo else corpo
                cols = []
                for parte in divide_topo(corpo):
                    if parte.lower().startswith(RESTRICOES):
                        continue
                    col = coluna_de(parte)
                    if col:
                        cols.append(col)
                tabelas.setdefault(nome, [])
                for c in cols:
                    if c not in tabelas[nome]:
                        tabelas[nome].append(c)
                continue
            m = re.match(
                r'ALTER\s+TABLE\s+["`\[]?([A-Za-z0-9_.]+)["`\]]?\s+ADD\s+(?:COLUMN\s+)'
                r'(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z0-9_]+)',
                comando, re.I | re.S)
            if m:
                tabela, col = m.group(1).lower(), m.group(2).lower()
                tabelas.setdefault(tabela, [])
                if col not in tabelas[tabela]:
                    tabelas[tabela].append(col)
    return tabelas


def main():
    problemas = []
    if not (SQL / "schema.sqlite.sql").is_file():
        print("::error::nao encontrei sql/schema.sqlite.sql")
        return 1

    sq = ler_dialeto("sqlite")
    pg = ler_dialeto("postgres")

    print("Tabelas: SQLite=%d  PostgreSQL=%d" % (len(sq), len(pg)))
    so_sq = sorted(set(sq) - set(pg))
    so_pg = sorted(set(pg) - set(sq))
    if so_sq:
        problemas.append("tabelas so no SQLite: %s" % ", ".join(so_sq))
    if so_pg:
        problemas.append("tabelas so no PostgreSQL: %s" % ", ".join(so_pg))

    for tabela in sorted(set(sq) & set(pg)):
        cs, cp = set(sq[tabela]), set(pg[tabela])
        faltam_pg = sorted(cs - cp)
        faltam_sq = sorted(cp - cs)
        if faltam_pg:
            problemas.append("%s: colunas sem par no PostgreSQL: %s" % (tabela, ", ".join(faltam_pg)))
        if faltam_sq:
            problemas.append("%s: colunas sem par no SQLite: %s" % (tabela, ", ".join(faltam_sq)))

    # o DDL do SQLite tem de executar de verdade
    con = sqlite3.connect(":memory:")
    try:
        for caminho in [SQL / "schema.sqlite.sql"] + sorted((SQL / "migracoes").glob("*.sqlite.sql")):
            con.executescript(caminho.read_text(encoding="utf-8"))
        con.commit()
        live = {r[0].lower() for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        print("DDL do SQLite executou: %d tabelas no banco" % len(live))
        fora = sorted(set(sq) - live)
        if fora:
            problemas.append("tabelas declaradas mas ausentes apos executar: %s" % ", ".join(fora))
    except sqlite3.Error as erro:
        problemas.append("DDL do SQLite nao executa: %s" % erro)
    finally:
        con.close()

    if problemas:
        print("\nDIVERGENCIAS (%d):" % len(problemas))
        for p in problemas:
            print("  - %s" % p)
            print("::error::%s" % p)
        return 1

    print("Paridade OK: mesmos nomes de tabela e de coluna nos dois dialetos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
