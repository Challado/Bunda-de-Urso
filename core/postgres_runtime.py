"""Adaptação do contrato de acesso do Radar para PostgreSQL."""

from datetime import date, datetime, time
from decimal import Decimal
from functools import lru_cache
import re

from psycopg2 import IntegrityError, sql
from psycopg2.extensions import connection, cursor

from . import caminhos
from .db import ErroIntegridade


class Conexao(connection):
    def execute(self, query, params=None):
        cur = self.cursor()
        try:
            cur.execute(query, params)
        except BaseException:
            cur.close()
            raise
        return cur


class Linha(tuple):
    """Uma linha consultável por posição ou pelo nome da coluna."""

    def __new__(cls, valores, nomes):
        linha = super().__new__(cls, valores)
        linha._nomes = nomes
        return linha

    def keys(self):
        return self._nomes

    def __getitem__(self, item):
        if isinstance(item, str):
            try:
                item = self._nomes.index(item)
            except ValueError as exc:
                raise IndexError(item) from exc
        return super().__getitem__(item)


def _valor(valor):
    if isinstance(valor, (date, datetime, time)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


@lru_cache(maxsize=1024)
def _parametros(comando):
    texto = comando.replace("%", "%%")
    return re.sub(r"""'(?:''|[^'])*'|"(?:""|[^"])*"|\?""",
                  lambda m: "%s" if m[0] == "?" else m[0], texto)


class Cursor(cursor):
    def execute(self, query, params=None):
        if isinstance(query, str):
            if re.match(r"\s*INSERT OR IGNORE INTO\b", query, re.I):
                query = re.sub(r"\bINSERT OR IGNORE INTO\b", "INSERT INTO", query,
                               count=1, flags=re.I).rstrip().rstrip(";")
                partes = re.split(r"\s+RETURNING\s+", query, maxsplit=1, flags=re.I)
                query = partes[0] + " ON CONFLICT DO NOTHING"
                if len(partes) == 2:
                    query += " RETURNING " + partes[1]
            if params:
                query = _parametros(query)
        try:
            super().execute(query, params or None)
        except IntegrityError as exc:
            # Os chamadores desfazem a unidade de trabalho ou o savepoint.
            raise ErroIntegridade(f"Restrição PostgreSQL ({exc.pgcode}).") from None
        self._nomes = tuple(col.name for col in self.description or ())
        return self

    def fetchone(self):
        valores = super().fetchone()
        return None if valores is None else Linha(map(_valor, valores), self._nomes)

    def fetchall(self):
        return [Linha(map(_valor, valores), self._nomes) for valores in super().fetchall()]

    def fetchmany(self, size=None):
        linhas = super().fetchmany(self.arraysize if size is None else size)
        return [Linha(map(_valor, valores), self._nomes) for valores in linhas]

    def __iter__(self):
        return iter(self.fetchone, None)


def conectar(conector, leitura=False, opcoes=None):
    """Abra a base configurada. Falhas não selecionam outro banco."""
    parametros = dict(caminhos.postgres() if opcoes is None else opcoes)
    esquema = parametros.pop("esquema")
    conn = conector(**parametros, cursor_factory=Cursor, autocommit=True)
    try:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(esquema)))
        conn.execute("SET TimeZone TO 'UTC'")
        if leitura:
            conn.execute("SET default_transaction_read_only TO on")
        if conn.execute("SELECT current_schema()").fetchone()[0] != esquema:
            raise RuntimeError("Esquema PostgreSQL ausente ou inacessível. Execute o migrador primeiro.")
        conn.autocommit = False
        return conn
    except BaseException:
        conn.close()
        raise
