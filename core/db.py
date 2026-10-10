# -*- coding: utf-8 -*-
"""Acesso ao SQLite: conexao com FK ligadas, inicializacao do esquema e
helpers de consulta parametrizada (spec 3.2, 15).

Nenhum SQL e montado por concatenacao de valores do usuario: sempre
parametrizado.
"""
import os
import sqlite3

from . import config
from . import domains as _domains


def connect(path=None):
    """Abre conexao SQLite com foreign_keys=ON e Row factory."""
    path = path or config.DB_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(conn, schema_path=None):
    """Cria o esquema canonico (se ainda nao existir) e carrega dominios."""
    schema_path = schema_path or config.SCHEMA_SQLITE
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    seed_dominios(conn)
    conn.commit()


def seed_dominios(conn):
    """Carga idempotente dos catalogos e das UFs."""
    cur = conn.cursor()
    for sigla, nome in _domains.UFS:
        cur.execute("INSERT OR IGNORE INTO UF (sigla, nome) VALUES (?, ?)",
                    (sigla, nome))
    for tabela, itens in _domains.DOMINIOS.items():
        col = COLUNA_TEXTO_DOMINIO.get(tabela, "descricao")
        for codigo, descricao in itens:
            cur.execute(
                "INSERT OR IGNORE INTO %s (codigo, %s) VALUES (?, ?)"
                % (tabela, col), (codigo, descricao))
    conn.commit()


# Catalogos cujo texto descritivo mora em `nome` (nao em `descricao`).
COLUNA_TEXTO_DOMINIO = {
    "LICENCA_DADOS": "nome",
    "NATUREZA_FONTE": "nome",
}


def domain_id(conn, tabela, codigo, criar=True):
    """Resolve PK de um dominio por codigo (opcionalmente cria)."""
    cur = conn.execute("SELECT id FROM %s WHERE codigo = ?" % tabela, (codigo,))
    row = cur.fetchone()
    if row is not None:
        return row[0]
    if not criar:
        return None
    col = COLUNA_TEXTO_DOMINIO.get(tabela, "descricao")
    cur = conn.execute(
        "INSERT INTO %s (codigo, %s) VALUES (?, ?)" % (tabela, col),
        (codigo, codigo))
    return cur.lastrowid


# --- helpers de consulta -------------------------------------------------

def query_all(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def query_one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def scalar(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def insert(conn, tabela, dados):
    """INSERT parametrizado a partir de dict coluna->valor. Retorna PK."""
    cols = list(dados.keys())
    placeholders = ", ".join("?" for _ in cols)
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (tabela, ", ".join(cols),
                                               placeholders)
    cur = conn.execute(sql, [dados[c] for c in cols])
    return cur.lastrowid


def upsert_lookup(conn, tabela, chave_cols, chave_vals, extra=None):
    """Retorna PK existente ou insere (usado para entidades sem PK surrogate
    natural, ex.: VIA por (tipo_via_id, codigo))."""
    where = " AND ".join("%s = ?" % c for c in chave_cols)
    row = conn.execute("SELECT id FROM %s WHERE %s" % (tabela, where),
                       list(chave_vals)).fetchone()
    if row is not None:
        return row[0]
    dados = dict(zip(chave_cols, chave_vals))
    if extra:
        dados.update(extra)
    return insert(conn, tabela, dados)
