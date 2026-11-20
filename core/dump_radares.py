"""Geração diária e entrega do arquivo público já comprimido."""
from contextlib import closing
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
import fcntl
import gzip
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import caminhos, config, consultas, db

NOME = "radares.json.gz"
ATRIBUICAO = {
    "projeto": "Bunda de Urso — cadastro nacional de radares",
    "repositorio": "https://github.com/Challado/Bunda-de-Urso",
    "licenca": "https://creativecommons.org/licenses/by/4.0/",
    "fontes": "Respeite as condições de cada fonte original.",
}


def arquivo():
    return Path(caminhos.dentro_dados("exportacao/" + NOME, "dump público"))


def disponivel():
    return arquivo().is_file()


def _gravar(saida, conn, agora):
    meta = consultas.metadados_base(conn)
    inicio = {
        "versao_api": config.API_VERSION,
        "versao_esquema": config.SCHEMA_VERSION,
        "gerado_em": agora.isoformat(),
        "snapshot_id": meta["snapshot_id"], "publicado_em": meta["publicado_em"],
        "atribuicao": ATRIBUICAO,
        "fontes": consultas.listar_fontes(conn),
    }
    saida.write(json.dumps(inicio, ensure_ascii=False, separators=(",", ":"))[:-1])
    saida.write(',"pontos":[')
    total = 0
    for ponto in consultas.exportar_cadastral(conn):
        if total:
            saida.write(",")
        saida.write(json.dumps(ponto, ensure_ascii=False, separators=(",", ":"), default=str))
        total += 1
    saida.write('],"total_pontos":' + str(total) + "}")
    return total


def gerar(agora=None):
    agora = agora or datetime.now(timezone.utc)
    destino = arquivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destino.parent / "dump.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    with os.fdopen(fd) as trava:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"estado": "em_andamento"}
        try:
            gerado = datetime.fromtimestamp(destino.stat().st_mtime, timezone.utc)
        except FileNotFoundError:
            gerado = None
        if gerado is not None and gerado.date() >= agora.date():
            return {"estado": "atual", "arquivo": destino.name}
        with NamedTemporaryFile(prefix=".radares-", dir=destino.parent, delete=False) as tmp:
            parcial = Path(tmp.name)
        try:
            with closing(db.connect_readonly()) as conn:
                if db.e_postgres(conn):
                    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                else:
                    conn.execute("BEGIN")
                with gzip.open(parcial, "wt", encoding="utf-8", compresslevel=5) as saida:
                    total = _gravar(saida, conn, agora)
            os.utime(parcial, (agora.timestamp(), agora.timestamp()))
            with parcial.open("rb") as conteudo:
                os.fsync(conteudo.fileno())
            os.replace(parcial, destino)
            return {"estado": "publicado", "arquivo": destino.name, "total_pontos": total}
        finally:
            parcial.unlink(missing_ok=True)


def main():
    print(json.dumps(gerar(), ensure_ascii=False))
    return 0


class Conteudo:
    """Arquivo aberto antes dos validadores HTTP, mesmo durante publicação."""

    def __init__(self, entrada):
        self.entrada = entrada

    def copiar(self, saida):
        with self.entrada:
            while bloco := self.entrada.read(128 * 1024):
                saida.write(bloco)


def download(environ, metodo):
    entrada = arquivo().open("rb")
    st = os.fstat(entrada.fileno())
    etag = f'"{st.st_ino:x}-{st.st_mtime_ns:x}-{st.st_size:x}"'
    headers = {"Content-Type": "application/gzip",
               "Content-Disposition": f'attachment; filename="{NOME}"',
               "Cache-Control": "private, max-age=0, must-revalidate",
               "ETag": etag, "Last-Modified": formatdate(st.st_mtime, usegmt=True)}
    tags = environ.get("HTTP_IF_NONE_MATCH")
    if tags is not None:
        atual = any(tag.strip().removeprefix("W/") in ("*", etag) for tag in tags.split(","))
    else:
        atual = False
        try:
            data = parsedate_to_datetime(environ.get("HTTP_IF_MODIFIED_SINCE", ""))
            atual = data.tzinfo is not None and int(st.st_mtime) <= data.timestamp()
        except (ValueError, TypeError, OverflowError):
            pass
    if atual:
        entrada.close()
        return 304, headers, b""
    headers["Content-Length"] = str(st.st_size)
    if metodo == "HEAD":
        entrada.close()
        return 200, headers, b""
    return 200, headers, Conteudo(entrada)
