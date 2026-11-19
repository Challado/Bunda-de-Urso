# -*- coding: utf-8 -*-
"""Acesso ao banco configurado, inicializacao do esquema e
helpers de consulta parametrizada (spec 3.2, 15).

Nenhum SQL e montado por concatenacao de valores do usuario: sempre
parametrizado.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

from . import config, caminhos
from .contexto_api import _LOCAL
from . import domains as _domains


ErroIntegridade = sqlite3.IntegrityError


def postgres_ativo():
    return caminhos.motor_banco() == "postgres"


@contextmanager
def transacao(conn):
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def _servico_postgres(path, *, leitura=False):
    from .postgres_runtime import conectar

    if path is not None and os.fspath(path) not in (config.DB_PATH, caminhos.banco()):
        raise ValueError("Uma instalação PostgreSQL usa o banco de radar.conf, sem arquivo --db.")
    return conectar(connect_postgres, leitura=leitura)


def connect(path=None, *, uri=False):
    if postgres_ativo():
        return _servico_postgres(path)
    return connect_sqlite(path, uri=uri)


def connect_sqlite(path=None, *, uri=False):
    """Abre conexao SQLite com foreign_keys=ON e Row factory."""
    path = path or config.DB_PATH
    path = os.fspath(path)
    if _LOCAL.get() and not caminhos._LEGADO.get() and path != ":memory:":
        if uri:
            partes = urlsplit(path)
            if partes.scheme != "file" or partes.netloc not in ("", "localhost"):
                raise ValueError("O banco deve ser um arquivo local dentro de dados.dir.")
            destino = caminhos.dentro_dados(unquote(partes.path), "banco", base=config.DATA_DIR)
            path = Path(destino).as_uri() + ("?" + partes.query if partes.query else "")
        else:
            path = caminhos.dentro_dados(path, "banco", base=config.DATA_DIR)
    readonly = uri and parse_qs(urlsplit(path).query).get("mode") == ["ro"]
    if path != ":memory:" and not uri:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, uri=uri)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # Leitor (web) e escritor (coletor) ao mesmo tempo: WAL deixa a leitura
    # nao travar na escrita e o busy_timeout evita "database is locked".
    if not readonly:
        try:
            con.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:                              # pragma: no cover
            pass
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def connect_existing(path):
    """Escrita no banco existente; nunca cria uma base vazia por engano."""
    if postgres_ativo():
        return _servico_postgres(path)
    return connect_sqlite(Path(path).resolve(strict=True).as_uri() + "?mode=rw", uri=True)


def connect_readonly(path):
    """Leitura sem criar arquivos, alterar journal ou aceitar fallback de escrita."""
    if postgres_ativo():
        return _servico_postgres(path, leitura=True)
    return connect_sqlite_readonly(path)


def connect_sqlite_readonly(path):
    return connect_sqlite(Path(path).resolve(strict=True).as_uri() + "?mode=ro", uri=True)


def connect_postgres(conninfo="", *, autocommit=False, **parametros):
    """Abra PostgreSQL com o psycopg2 instalado."""
    import psycopg2
    from .postgres_runtime import Conexao

    if parametros.get("sslrootcert") == "system":
        parametros["sslrootcert"] = caminhos.certificado_postgres()
    conn = psycopg2.connect(dsn=conninfo, connection_factory=Conexao, **parametros)
    if autocommit:
        conn.autocommit = True
    return conn


def e_postgres(conn):
    return not isinstance(conn, sqlite3.Connection)


def tabela_existe(conn, tabela):
    if e_postgres(conn):
        return bool(scalar(conn, "SELECT to_regclass(?) IS NOT NULL", (tabela.lower(),)))
    return bool(scalar(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND upper(name)=?", (tabela.upper(),)))


def colunas(conn, tabela):
    if e_postgres(conn):
        return [r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position",
            (tabela.lower(),))]
    return [r[0] for r in conn.execute("SELECT name FROM pragma_table_info(?)", (tabela,))]


def esquema_carregado(conn):
    return all(tabela_existe(conn, t) for t in ("UF", "PONTO_FISCALIZACAO", "RECURSO_LICENCA"))


def init_db(conn, schema_path=None):
    """Cria o esquema canonico (se ainda nao existir) e carrega dominios.

    Idempotente: pode ser chamada a cada passada do coletor sem recriar nada.
    """
    if e_postgres(conn):
        if not esquema_carregado(conn):
            raise RuntimeError("Banco PostgreSQL ainda não preparado pelo migrador.")
        return
    schema_path = schema_path or config.SCHEMA_SQLITE
    if not esquema_carregado(conn):
        with open(schema_path, "r", encoding="utf-8") as f:
            script = f.read()
        # Uma transacao so: sem isso cada CREATE TABLE vira um COMMIT/fsync
        # proprio e a carga do esquema passa de ~9 s para ~0,1 s.
        conn.executescript("BEGIN;\n" + script + "\nCOMMIT;")
    seed_dominios(conn)
    conn.commit()


def seed_dominios(conn):
    """Carga idempotente dos catalogos e das UFs."""
    catalogos = [("UF", "sigla", "nome", _domains.UFS)]
    catalogos.extend((tabela, "codigo", COLUNA_TEXTO_DOMINIO.get(tabela, "descricao"), itens)
                    for tabela, itens in _domains.DOMINIOS.items())
    for tabela, chave, texto, itens in catalogos:
        existentes = {linha[0] for linha in conn.execute(f"SELECT {chave} FROM {tabela}")}
        for codigo, descricao in itens:
            if codigo not in existentes:
                conn.execute(f"INSERT OR IGNORE INTO {tabela} ({chave}, {texto}) VALUES (?, ?)",
                             (codigo, descricao))
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
    return insert(conn, tabela, {"codigo": codigo, col: codigo})


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
    valores = [dados[c] for c in cols]
    if not e_postgres(conn):
        return conn.execute(sql, valores).lastrowid
    chave = {"TRASEIRO_EVENTO": "seq", "MUNICIPIO": "codigo_ibge"}.get(tabela.upper(), "id")
    return inserir_id(conn, sql, valores, chave)


def inserir_id(conn, sql, params, chave="id"):
    row = conn.execute(sql + " RETURNING " + chave, params).fetchone()
    return row[0] if row is not None else None


def upsert_lookup(conn, tabela, chave_cols, chave_vals, extra=None):
    """Retorna PK existente ou insere (usado para entidades sem PK surrogate
    natural, ex.: VIA por (tipo_via_id, codigo))."""
    partes = [(f"{c} IS NULL" if v is None else f"{c} = ?") for c, v in zip(chave_cols, chave_vals)]
    where = " AND ".join(partes)
    row = conn.execute("SELECT id FROM %s WHERE %s" % (tabela, where),
                       [v for v in chave_vals if v is not None]).fetchone()
    if row is not None:
        return row[0]
    dados = dict(zip(chave_cols, chave_vals))
    if extra:
        dados.update(extra)
    return insert(conn, tabela, dados)


def verificar_integridade(conn):
    if e_postgres(conn):
        if not esquema_carregado(conn):
            raise RuntimeError("Esquema PostgreSQL ausente.")
        nao_validadas = scalar(conn, """
            SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
            WHERE t.relnamespace=current_schema()::regnamespace AND NOT c.convalidated
        """)
        if nao_validadas:
            raise RuntimeError("O banco tem restrições ainda não validadas.")
    elif scalar(conn, "PRAGMA integrity_check") != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone():
        raise RuntimeError("Banco SQLite com problemas de integridade.")


def backup_operacional(pasta, nome, origem=None):
    """Backup nativo do motor configurado com publicação atômica."""
    from contextlib import closing
    import subprocess
    from tempfile import NamedTemporaryFile

    pasta = Path(pasta)
    postgres = postgres_ativo()
    saida = pasta / (nome + (".pgdump" if postgres else ".sqlite3"))
    with NamedTemporaryFile(dir=pasta, delete=False) as arq:
        temporario = Path(arq.name)
    try:
        with closing(connect_readonly(origem or caminhos.banco())) as fonte:
            verificar_integridade(fonte)
            if postgres:
                opcoes = caminhos.postgres()
                ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
                variaveis = {
                    "host": "PGHOST", "port": "PGPORT", "dbname": "PGDATABASE", "user": "PGUSER",
                    "passfile": "PGPASSFILE", "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT",
                    "connect_timeout": "PGCONNECT_TIMEOUT",
                }
                ambiente.update({v: str(opcoes[k]) for k, v in variaveis.items()})
                try:
                    subprocess.run(["pg_dump", "-w", "-Fc", "--schema", opcoes["esquema"],
                                    "--file", str(temporario)], env=ambiente,
                                   capture_output=True, check=True, timeout=1800)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise RuntimeError("Falha no pg_dump. Confira a versão do cliente, TLS e acesso ao esquema.") from exc
            else:
                with closing(connect_sqlite(temporario)) as copia:
                    fonte.backup(copia)
                    copia.execute("PRAGMA journal_mode=DELETE")
        os.link(temporario, saida)
        return saida
    finally:
        temporario.unlink(missing_ok=True)


def backup_manutencao(origem, tarefa):
    from datetime import datetime, timezone

    pasta = Path(caminhos.dentro_dados("backups/manutencao", "backup de manutenção"))
    pasta.mkdir(parents=True, mode=0o700, exist_ok=True)
    agora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return backup_operacional(pasta, f"{tarefa}-{agora}", origem)


def inserir_registro_fonte(conn, dados):
    """Guarda o documento pelo hash e liga o registro ao documento original."""
    dados = dict(dados)
    texto = dados.pop("payload_original")
    hash_registro = dados["hash_registro"]
    gravado = scalar(conn, "INSERT INTO PAYLOAD_FONTE (hash_registro, payload_original) VALUES (?,?) "
                     "ON CONFLICT (hash_registro) DO NOTHING RETURNING hash_registro", (hash_registro, texto))
    if gravado is None and scalar(conn, "SELECT payload_original FROM PAYLOAD_FONTE WHERE hash_registro=?", (hash_registro,)) != texto:
        raise ErroIntegridade("Um hash de registro aponta para dois documentos diferentes.")
    return insert(conn, "REGISTRO_FONTE", dados)


def guardar_conteudo_artefato(conn, digest, tamanho):
    gravado = scalar(conn, "INSERT INTO CONTEUDO_ARTEFATO (hash_sha256,bytes_arquivo) VALUES (?,?) "
                     "ON CONFLICT (hash_sha256) DO NOTHING RETURNING bytes_arquivo", (digest, tamanho))
    if gravado is None and scalar(conn, "SELECT bytes_arquivo FROM CONTEUDO_ARTEFATO WHERE hash_sha256=?",
                                  (digest,)) != tamanho:
        raise ErroIntegridade("Um hash de artefato aponta para dois tamanhos diferentes.")


def inserir_artefato(conn, dados):
    dados = dict(dados)
    guardar_conteudo_artefato(conn, dados["hash_sha256"], dados.pop("bytes_arquivo"))
    return insert(conn, "ARTEFATO_COLETA", dados)
