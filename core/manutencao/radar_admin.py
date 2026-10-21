#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI de administracao do Radar Brasil (anti-lockout e provisionamento).

Roda NO HOST, fora do painel — se a unica senha admin se perder, o painel
nao resolve. Usa as MESMAS funcoes do app (core.governanca) e o MESMO banco
(env RADAR_DB / config.DB_PATH); nao duplica regra nem escreve por outro
caminho.

Subcomandos:
    criar-admin <login>   cria (ou reusa) um usuario admin com
                          deve_trocar_senha=1. A senha vem de --senha, da
                          variavel RADAR_ADMIN_SENHA ou do stdin (getpass).
                          NUNCA existe senha no codigo.
    reset-senha <login>   gera senha temporaria (deve_trocar_senha=1) e a
                          imprime UMA vez.
    listar-usuarios       lista usuarios (sem hashes).
    criar-token           emite um token de API; o valor aparece UMA vez.
    revogar-token <id>    marca revogado_em (sem apagar historico).

Exemplos:
    python3 tools/radar_admin.py criar-admin admin
    python3 tools/radar_admin.py reset-senha admin
    python3 tools/radar_admin.py criar-token --nome github:fulano --escopo moderador
    python3 tools/radar_admin.py revogar-token 3
"""
import argparse
import getpass
import os
import sys


from core import config          # noqa: E402
from core import db as dbmod     # noqa: E402
from core import governanca as gov  # noqa: E402
from core.contexto_api import operacao_local


def _conn():
    con = dbmod.connect(config.DB_PATH)
    gov.garantir_esquema(con)
    return con


def _ler_senha(args):
    if args.senha:
        return args.senha
    env = os.environ.get("RADAR_ADMIN_SENHA")
    if env:
        return env
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    s1 = getpass.getpass("senha: ")
    s2 = getpass.getpass("repita a senha: ")
    if s1 != s2:
        print("erro: as senhas nao coincidem", file=sys.stderr)
        raise SystemExit(2)
    return s1


def cmd_criar_admin(args):
    senha = _ler_senha(args)
    if not senha:
        print("erro: senha vazia", file=sys.stderr)
        return 2
    con = _conn()
    try:
        existente = gov.obter_usuario_por_login(con, args.login)
        if existente is not None:
            _row, senha = gov.resetar_senha(con, args.login, senha,
                                            deve_trocar=True)
            gov.definir_papel_ativo(con, existente["id"], papel="admin",
                                    ativo=True)
            print("usuario %s ja existia: senha redefinida "
                  "(deve_trocar_senha=1)" % args.login)
            return 0
        gov.criar_usuario(con, args.login, senha, nome=args.nome,
                          email=args.email, papel="admin",
                          deve_trocar_senha=True)
        print("admin %s criado (deve_trocar_senha=1). Troque no 1o login."
              % args.login)
        return 0
    except gov.GovernancaError as exc:
        print("erro: %s" % exc.mensagem, file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_reset_senha(args):
    con = _conn()
    try:
        _row, senha = gov.resetar_senha(con, args.login, deve_trocar=True)
        print("senha temporaria de %s (aparece uma unica vez):" % args.login)
        print(senha)
        print("O usuario deve troca-la no proximo login "
              "(deve_trocar_senha=1).")
        return 0
    except gov.GovernancaError as exc:
        print("erro: %s" % exc.mensagem, file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_listar_usuarios(_args):
    con = _conn()
    try:
        print("%-4s %-20s %-10s %-5s %-6s %s"
              % ("id", "login", "papel", "ativo", "troca", "criado_em"))
        for u in gov.listar_usuarios(con):
            print("%-4s %-20s %-10s %-5s %-6s %s"
                  % (u["id"], u["login"], u["papel"], u["ativo"],
                     u["deve_trocar_senha"], u["criado_em"]))
        return 0
    finally:
        con.close()


def cmd_criar_token(args):
    con = _conn()
    try:
        tid, valor = gov.emitir_token(
            con, args.nome, args.escopo, dono=args.dono,
            expira_em=args.expira_em, observacoes=args.observacoes,
            criado_por="cli")
        print("token #%d (escopo %s) — valor (aparece UMA vez):"
              % (tid, args.escopo))
        print(valor)
        print("prefixo: %s" % gov.prefixo_token(valor))
        return 0
    except gov.GovernancaError as exc:
        print("erro: %s" % exc.mensagem, file=sys.stderr)
        return 1
    finally:
        con.close()


def cmd_revogar_token(args):
    con = _conn()
    try:
        gov.revogar_token(con, args.id)
        print("token #%d revogado" % args.id)
        return 0
    except gov.GovernancaError as exc:
        print("erro: %s" % exc.mensagem, file=sys.stderr)
        return 1
    finally:
        con.close()


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="radar_admin",
        description="Administracao do Radar Brasil (usa core.governanca).")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("criar-admin", help="cria/usar admin com troca obrigatoria")
    p.add_argument("login")
    p.add_argument("--senha", help="senha (senao stdin/env RADAR_ADMIN_SENHA)")
    p.add_argument("--nome")
    p.add_argument("--email")
    p.set_defaults(func=cmd_criar_admin)

    p = sub.add_parser("reset-senha", help="gera senha temporaria")
    p.add_argument("login")
    p.set_defaults(func=cmd_reset_senha)

    p = sub.add_parser("listar-usuarios", help="lista usuarios")
    p.set_defaults(func=cmd_listar_usuarios)

    p = sub.add_parser("criar-token", help="emite token de API (valor 1 vez)")
    p.add_argument("--nome", required=True)
    p.add_argument("--escopo", default="contribuidor",
                   choices=list(gov.ESCOPOS))
    p.add_argument("--dono")
    p.add_argument("--expira-em", dest="expira_em")
    p.add_argument("--observacoes")
    p.set_defaults(func=cmd_criar_token)

    p = sub.add_parser("revogar-token", help="revoga um token")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_revogar_token)

    args = parser.parse_args(argv)
    return args.func(args)
