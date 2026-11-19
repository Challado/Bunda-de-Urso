"""Exportação lógica do esquema operacional do Radar, pelo próprio PostgreSQL."""

import gzip
from collections import defaultdict
from graphlib import TopologicalSorter

from psycopg import sql

SUFIXO = ".sql.gz"

# Usados dos dois lados para a conversão de dados entre texto e seu tipo original.
FORMATOS = (
    "DateStyle TO 'ISO, YMD'",
    "IntervalStyle TO 'postgres'",
    "TimeZone TO 'UTC'",
    "standard_conforming_strings TO on",
    "extra_float_digits TO 3",
    "bytea_output TO 'hex'",
)


def _catalogo(conn, esquema):
    tabelas, vistas = {}, {}
    for oid, nome, tipo, persistencia, restrita in conn.execute("""
        SELECT oid, relname, relkind, relpersistence,
               relrowsecurity OR relispartition
        FROM pg_class WHERE relnamespace = ?::regnamespace
          AND relkind NOT IN ('i', 'I', 'S', 't')
        ORDER BY relname
    """, (esquema,)):
        if restrita or tipo not in ("r", "v"):
            raise RuntimeError(f"Relação PostgreSQL não suportada no backup: {nome}.")
        qualificado = sql.Identifier(esquema, nome)
        if tipo == "r":
            tabelas[oid] = (qualificado, persistencia)
        else:
            vistas[oid] = qualificado
    fora = conn.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_inherits
            WHERE inhrelid = ANY(?) OR inhparent = ANY(?)
        ) OR EXISTS (
            SELECT 1 FROM pg_rewrite
            WHERE ev_class = ANY(?) AND rulename <> '_RETURN'
        ) OR EXISTS (
            SELECT 1 FROM pg_type
            WHERE typnamespace = ?::regnamespace AND typrelid = 0
              AND NOT EXISTS (SELECT 1 FROM pg_type t WHERE t.typarray = pg_type.oid)
        )
    """, (list(tabelas), list(tabelas), list(tabelas) + list(vistas), esquema)).fetchone()[0]
    if fora:
        raise RuntimeError("O esquema PostgreSQL tem tipos próprios, herança ou regras fora do formato de backup do Radar.")
    if not tabelas:
        raise RuntimeError("O esquema PostgreSQL do Radar está sem tabelas.")
    return tabelas, vistas


def _sequencias(conn, esquema):
    return conn.execute("""
        SELECT c.relname, format_type(s.seqtypid, NULL), s.seqstart, s.seqincrement,
               s.seqmin, s.seqmax, s.seqcache, s.seqcycle,
               d.deptype, d.refobjid, d.refobjsubid
        FROM pg_class c JOIN pg_sequence s ON s.seqrelid = c.oid
        LEFT JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = c.oid
            AND d.refclassid = 'pg_class'::regclass AND d.refobjsubid > 0
            AND d.deptype IN ('a', 'i')
        WHERE c.relnamespace = ?::regnamespace
        ORDER BY c.relname
    """, (esquema,)).fetchall()


def _opcoes_seq(dados):
    return ("START WITH %s INCREMENT BY %s MINVALUE %s MAXVALUE %s CACHE %s %s"
            % (*dados[2:7], "CYCLE" if dados[7] else "NO CYCLE"))


def _colunas(conn, tabelas):
    colunas = defaultdict(list)
    for oid, numero, nome, tipo, nao_nulo, identidade, gerada, padrao, collation in conn.execute("""
        SELECT a.attrelid, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, a.attidentity, a.attgenerated, pg_get_expr(d.adbin, d.adrelid),
               CASE WHEN a.attcollation <> t.typcollation THEN a.attcollation::regcollation::text END
        FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE a.attrelid = ANY(?) AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attrelid, a.attnum
    """, (list(tabelas),)):
        colunas[oid].append((numero, sql.Identifier(nome), tipo, nao_nulo, identidade,
                             gerada, padrao, collation))
    return colunas


def _definicao_coluna(coluna, identidades):
    _, nome, tipo, nao_nulo, identidade, gerada, padrao, collation = coluna
    definicao = f"{nome.as_string()} {tipo}"
    if collation:
        definicao += " COLLATE " + collation
    if identidade:
        sequencia, opcoes = identidades[coluna[0]]
        modo = "ALWAYS" if identidade == "a" else "BY DEFAULT"
        definicao += f" GENERATED {modo} AS IDENTITY (SEQUENCE NAME {sequencia} {opcoes})"
    elif gerada:
        modo = "STORED" if gerada == "s" else "VIRTUAL"
        definicao += f" GENERATED ALWAYS AS ({padrao}) {modo}"
    elif padrao is not None:
        definicao += " DEFAULT " + padrao
    if nao_nulo:
        definicao += " NOT NULL"
    return definicao


def _dados(conn, arquivo, tabela, colunas):
    nomes = [c[1] for c in colunas if not c[5]]
    if not nomes:
        # PostgreSQL permite tabelas sem colunas e tabelas só com colunas geradas.
        total = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(tabela)).fetchone()[0]
        for _ in range(total):
            arquivo.write(f"INSERT INTO {tabela.as_string()} DEFAULT VALUES;\n")
        return
    # O servidor converte cada valor sem passar pelas coerções de tipos da API.
    literal = sql.SQL("""
        CASE WHEN {coluna} IS NULL THEN 'NULL'
        ELSE 'E' || chr(39) || replace(replace(replace(replace({coluna}::text,
            chr(92), chr(92) || chr(92)), chr(39), chr(39) || chr(39)),
            chr(13), chr(92) || 'r'), chr(10), chr(92) || 'n') || chr(39)
        END
    """)
    campos = sql.SQL(", ").join(literal.format(coluna=nome) for nome in nomes)
    consulta = sql.SQL("SELECT concat_ws(', ', {}) FROM {}").format(campos, tabela)
    colunas_sql = sql.SQL(", ").join(nomes).as_string()
    sobrescrever = " OVERRIDING SYSTEM VALUE" if any(c[4] for c in colunas) else ""
    prefixo = f"INSERT INTO {tabela.as_string()} ({colunas_sql}){sobrescrever} VALUES\n"
    with conn.cursor(name="radar_backup_dados") as cur:
        cur.execute(consulta)
        while linhas := cur.fetchmany(256):
            arquivo.write(prefixo + ",\n".join(f"({linha[0]})" for linha in linhas) + ";\n")


def _vistas(conn, vistas):
    dependencias = defaultdict(set)
    for vista, depende in conn.execute("""
        SELECT r.ev_class, d.refobjid FROM pg_rewrite r JOIN pg_depend d
            ON d.classid = 'pg_rewrite'::regclass AND d.objid = r.oid
            AND d.refclassid = 'pg_class'::regclass
        WHERE r.ev_class = ANY(?) AND d.refobjid = ANY(?) AND d.refobjid <> r.ev_class
        ORDER BY r.ev_class, d.refobjid
    """, (list(vistas), list(vistas))):
        dependencias[vista].add(depende)
    for oid in TopologicalSorter({oid: sorted(dependencias[oid]) for oid in vistas}).static_order():
        definicao, opcoes = conn.execute("""
            SELECT pg_get_viewdef(oid), reloptions FROM pg_class WHERE oid = ?
        """, (oid,)).fetchone()
        parametros = " WITH (" + ", ".join(opcoes) + ")" if opcoes else ""
        yield f"CREATE VIEW {vistas[oid].as_string()}{parametros} AS\n{definicao}"


def _restricoes_e_indices(conn, escrever, tabelas):
    ids = list(tabelas)
    for tabela, nome, definicao in conn.execute("""
        SELECT conrelid, conname, pg_get_constraintdef(oid)
        FROM pg_constraint WHERE conrelid = ANY(?) AND contype NOT IN ('f', 'n')
        ORDER BY conrelid, conname
    """, (ids,)):
        escrever(f"ALTER TABLE {tabelas[tabela][0].as_string()} "
                 f"ADD CONSTRAINT {sql.Identifier(nome).as_string()} {definicao}")
    for (definicao,) in conn.execute("""
        SELECT pg_get_indexdef(i.indexrelid)
        FROM pg_index i WHERE i.indrelid = ANY(?) AND i.indisvalid
          AND NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            WHERE c.conindid = i.indexrelid AND c.contype IN ('p', 'u', 'x')
          )
        ORDER BY i.indexrelid
    """, (ids,)):
        escrever(definicao)
    for tabela, nome, definicao in conn.execute("""
        SELECT conrelid, conname, pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid = ANY(?) AND contype = 'f' ORDER BY conrelid, conname
    """, (ids,)):
        escrever(f"ALTER TABLE {tabelas[tabela][0].as_string()} "
                 f"ADD CONSTRAINT {sql.Identifier(nome).as_string()} {definicao}")


def exportar(conn, esquema, temporario):
    """Escreve o arquivo a partir da transação de leitura aberta pelo chamador."""
    conn.execute("SET LOCAL search_path TO pg_catalog")
    conn.execute("SET LOCAL row_security TO off")
    for formato in FORMATOS:
        conn.execute("SET LOCAL " + formato)

    tabelas, vistas = _catalogo(conn, esquema)
    nomes_tabelas = sql.SQL(", ").join(t[0] for t in tabelas.values())
    conn.execute(sql.SQL("LOCK TABLE {} IN ACCESS SHARE MODE").format(nomes_tabelas))
    colunas = _colunas(conn, tabelas)
    sequencias = _sequencias(conn, esquema)
    rotinas = conn.execute("""
        SELECT oid, prokind FROM pg_proc WHERE pronamespace = ?::regnamespace ORDER BY oid
    """, (esquema,)).fetchall()
    if any(tipo == "a" for _, tipo in rotinas):
        raise RuntimeError("O esquema PostgreSQL tem agregações próprias fora do formato de backup do Radar.")

    with gzip.open(temporario, "wt", encoding="utf-8", newline="\n") as arquivo:
        def escrever(comando):
            arquivo.write(comando.rstrip().rstrip(";") + ";\n")

        arquivo.write("-- Radar Brasil: backup lógico PostgreSQL, esquema e dados.\n")
        escrever("BEGIN")
        escrever("SET LOCAL client_encoding TO 'UTF8'")
        escrever("SET LOCAL client_min_messages TO warning")
        for formato in FORMATOS:
            escrever("SET LOCAL " + formato)
        escrever("SET LOCAL search_path TO pg_catalog")
        escrever("SET LOCAL check_function_bodies TO off")
        escrever(f"CREATE SCHEMA IF NOT EXISTS {sql.Identifier(esquema).as_string()}")
        if vistas:
            escrever("DROP VIEW IF EXISTS " + sql.SQL(", ").join(vistas.values()).as_string() + " RESTRICT")
        escrever("DROP TABLE IF EXISTS " + nomes_tabelas.as_string() + " RESTRICT")

        identidades = defaultdict(dict)
        for seq in sequencias:
            nome = sql.Identifier(esquema, seq[0]).as_string()
            opcoes = _opcoes_seq(seq)
            if seq[8] == "i":
                identidades[seq[9]][seq[10]] = (nome, opcoes)
            else:
                escrever(f"DROP SEQUENCE IF EXISTS {nome}")
                escrever(f"CREATE SEQUENCE {nome} AS {seq[1]} {opcoes}")
        for oid, _ in rotinas:
            escrever(conn.execute("SELECT pg_get_functiondef(?)", (oid,)).fetchone()[0])
        for oid, (tabela, persistencia) in tabelas.items():
            definicoes = ",\n  ".join(_definicao_coluna(c, identidades[oid]) for c in colunas[oid])
            modo = "UNLOGGED " if persistencia == "u" else ""
            escrever(f"CREATE {modo}TABLE {tabela.as_string()} (\n  {definicoes}\n)")
        for seq in sequencias:
            if seq[8] == "a":
                tabela = tabelas[seq[9]][0].as_string()
                coluna = next(c[1].as_string() for c in colunas[seq[9]] if c[0] == seq[10])
                nome = sql.Identifier(esquema, seq[0]).as_string()
                escrever(f"ALTER SEQUENCE {nome} OWNED BY {tabela}.{coluna}")

        for oid, (tabela, _) in tabelas.items():
            _dados(conn, arquivo, tabela, colunas[oid])
        _restricoes_e_indices(conn, escrever, tabelas)
        for definicao in _vistas(conn, vistas):
            escrever(definicao)
        relacoes = {oid: tabela for oid, (tabela, _) in tabelas.items()} | vistas
        modos = {"D": "DISABLE", "A": "ENABLE ALWAYS", "R": "ENABLE REPLICA"}
        for oid, nome, modo, definicao in conn.execute("""
            SELECT tgrelid, tgname, tgenabled, pg_get_triggerdef(oid)
            FROM pg_trigger WHERE tgrelid = ANY(?) AND NOT tgisinternal
            ORDER BY tgrelid, tgname
        """, (list(relacoes),)):
            escrever(definicao)
            if modo in modos:
                escrever(f"ALTER TABLE {relacoes[oid].as_string()} {modos[modo]} TRIGGER "
                         + sql.Identifier(nome).as_string())
        for seq in sequencias:
            nome = sql.Identifier(esquema, seq[0])
            valor, chamado = conn.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(nome)).fetchone()
            referencia = sql.Literal(nome.as_string()).as_string()
            escrever(f"SELECT setval({referencia}::regclass, {valor}, {'true' if chamado else 'false'})")
        escrever("COMMIT")
