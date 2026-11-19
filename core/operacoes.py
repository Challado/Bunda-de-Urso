"""Coordena as operações da API com a pausa para troca do banco ativo."""

from contextlib import ExitStack, contextmanager
import fcntl
import os
from pathlib import Path
import signal
import sys
import time

from . import caminhos


class OperacoesPausadas(RuntimeError):
    """Uma operação de manutenção impediu o acesso no momento."""


@contextmanager
def _travar(fd, modo, espera=0):
    try:
        limite = time.monotonic() + espera
        while True:
            try:
                fcntl.flock(fd, modo | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= limite:
                    raise OperacoesPausadas("Operações do Radar temporariamente indisponíveis.") from exc
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)


def _diretorio(pasta):
    return os.open(pasta, os.O_RDONLY | os.O_DIRECTORY)


def _pastas():
    return Path(caminhos.conf_path()).resolve().parent, Path(caminhos.data_dir())


@contextmanager
def acompanhar():
    entrada, dados = _pastas()
    if not dados.is_dir():
        yield
        return
    # A admissão segura a entrada só até registrar a operação em andamento.
    with ExitStack() as operacao:
        with _travar(_diretorio(entrada), fcntl.LOCK_SH):
            operacao.enter_context(_travar(_diretorio(dados), fcntl.LOCK_SH))
        yield


@contextmanager
def pausar():
    entrada, dados = _pastas()
    # A instalação também usa este lock para publicar a API e o radar.conf.
    instalacao = os.open(dados / "instalacao.lock", os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW, 0o660)
    with ExitStack() as pausa:
        pausa.enter_context(_travar(instalacao, fcntl.LOCK_EX))
        pausa.enter_context(_travar(_diretorio(entrada), fcntl.LOCK_EX, espera=300))
        if not dados.samefile(entrada):
            pausa.enter_context(_travar(_diretorio(dados), fcntl.LOCK_EX, espera=300))
        yield


def encerrar_reconciliacao_abandonada(origem):
    """Encerra só o subprocesso órfão da instalação que ainda abriu este SQLite."""
    api = Path(caminhos.web_raiz(), 'web/api.pse').resolve()
    origem = Path(origem).resolve()
    for processo in Path('/proc').iterdir():
        if not processo.name.isdecimal():
            continue
        try:
            with os.fdopen(os.pidfd_open(int(processo.name)), 'rb') as pid:
                status = dict(linha.split(':', 1) for linha in (processo / 'status').read_text().splitlines())
                if status['PPid'].strip() != '1' or int(status['Uid'].split()[1]) != os.geteuid():
                    continue
                args = (processo / 'cmdline').read_bytes().split(b'\0')[:-1]
                if (len(args) != 5 or args[2:] != [b'ferramenta', b'reconciliar_equipamentos', b'--aplicar']
                        or Path(os.fsdecode(args[0])).resolve() != Path(sys.executable).resolve()
                        or Path(os.fsdecode(args[1])).resolve() != api):
                    continue
                if any(os.readlink(fd) == str(origem) for fd in (processo / 'fd').iterdir()):
                    signal.pidfd_send_signal(pid.fileno(), signal.SIGTERM)
        except OSError:
            continue
