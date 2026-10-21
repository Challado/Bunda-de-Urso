"""Contexto das operacoes locais iniciadas pelo ponto de entrada api.pse."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_LOCAL = ContextVar("operacao_local_api", default=False)


@contextmanager
def atendimento_local():
    token = _LOCAL.set(True)
    try:
        yield
    finally:
        _LOCAL.reset(token)


def operacao_local(funcao):
    @wraps(funcao)
    def executar(*args, **kwargs):
        if not _LOCAL.get():
            raise RuntimeError("Operacao local exige a entrada api.pse")
        return funcao(*args, **kwargs)
    return executar
