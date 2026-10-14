# -*- coding: utf-8 -*-
"""Modo console do Radar Brasil.

Ativado pelo `api.pse` quando ele percebe que NAO esta sob o nginx/fcgiwrap
(isto e, foi chamado na linha de comando do servidor). Assim o MESMO arquivo
serve a web (CGI) e o terminal:

    ./api.pse                    # menu interativo
    ./api.pse menu               # idem (forca o menu)
    ./api.pse pendentes          # cadastros nao verificados
    ./api.pse cadastro P-1130    # detalhes de um cadastro
    ./api.pse usuarios           # usuarios do painel
    ./api.pse senha admin        # define nova senha (pede e confirma)
    ./api.pse resetar-senha admin# gera temporaria (aparece 1x, troca obrigatoria)
    ./api.pse desativar-usuario <login>   # inativa (ativo=0)
    ./api.pse ativar-usuario <login>      # reativa (ativo=1)
    ./api.pse excluir-usuario <login>     # exclui em definitivo (pede confirmacao)
    ./api.pse tokens | bloqueios | historico P-1130
    ./api.pse ajuda

Usa a MESMA camada do app (core.governanca) — o console e o proprio app, nao
um caminho paralelo para o banco.
"""
import getpass
import json
import sys

from core import config
from core import db as dbmod
from core import governanca as gov

_RESUMO = "  %-10s %-3s %-24s %-26s %s"


def _conn():
    con = dbmod.connect(config.DB_PATH)
    gov.garantir_esquema(con)
    return con


def _p_id(texto):
    t = (texto or "").strip().upper()
    if t.startswith("P-"):
        t = t[2:]
    if not t.isdigit():
        raise ValueError("id deve ser P-<numero> (ex.: P-1130)")
    return int(t)


def _corta(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n - 1] + "~"


def _json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


# ------------------------------ comandos -----------------------------------

def pendentes(conn, argv):
    limite = 50
    if len(argv) >= 2 and argv[0] == "--limite":
        limite = int(argv[1])
    pontos, meta = gov.listar_pendentes(conn, limite=limite)
    if not pontos:
        print("Nenhum cadastro pendente (fila vazia).")
        return 0
    print(_RESUMO % ("id", "UF", "municipio", "via", "km"))
    for p in pontos:
        print(_RESUMO % (p.get("id"), _corta(p.get("uf"), 3),
                         _corta(p.get("municipio"), 24),
                         _corta(p.get("via"), 26), _corta(p.get("km"), 8)))
    print("total: %s" % meta.get("total"))
    return 0


def cadastro(conn, argv):
    if not argv:
        print("uso: cadastro P-<numero>")
        return 2
    pid = _p_id(argv[0])
    try:
        reg = gov.obter_radar(conn, pid)
    except gov.GovernancaError as e:
        print("erro: %s" % e.mensagem)
        return 1
    g = reg.get("governanca", {}) or {}
    print("Ponto:      %s" % ("P-%d" % pid))
    print("Procedencia:%s   Verificacao: %s" % (g.get("procedencia"),
                                                g.get("verificacao_status")))
    if g.get("removido_em"):
        print("REMOVIDO em %s  por %s  motivo: %s" % (
            g.get("removido_em"), g.get("removido_por"), g.get("motivo_remocao")))
    for chave in ("via", "municipio", "uf", "km", "latitude", "longitude",
                  "tipo_pista", "observacoes", "situacao_operacional", "sentido"):
        if reg.get(chave) not in (None, ""):
            print("  %-12s %s" % (chave + ":", reg.get(chave)))
    corr = reg.get("correspondencias") or []
    if corr:
        print("  correspondencias:")
        for c in corr:
            print("    #%s %s" % (c.get("id"), c.get("status")))
    print("  (detalhe completo em JSON: --json)")
    if "--json" in argv:
        _json(reg)
    return 0


def usuarios(conn, argv):
    us = gov.listar_usuarios(conn)
    if not us:
        print("Nenhum usuario.")
        return 0
    print("  %-4s %-16s %-11s %-6s %-8s %s" % (
        "id", "login", "papel", "ativo", "trocar", "ultimo_login"))
    for u in us:
        print("  %-4s %-16s %-11s %-6s %-8s %s" % (
            u.get("id"), _corta(u.get("login"), 16), u.get("papel"),
            u.get("ativo"), u.get("deve_trocar_senha"), u.get("ultimo_login") or "-"))
    return 0


def senha(conn, argv):
    if not argv:
        print("uso: senha <login>")
        return 2
    login = argv[0]
    if gov.obter_usuario_por_login(conn, login) is None:
        print("usuario %s nao encontrado" % login)
        return 1
    nova = getpass.getpass("Nova senha para %s (min. 8): " % login)
    if len(nova) < 8:
        print("erro: a senha deve ter ao menos 8 caracteres")
        return 2
    if nova != getpass.getpass("Repita a nova senha: "):
        print("erro: as senhas nao conferem")
        return 2
    gov.resetar_senha(conn, login, nova_senha=nova, deve_trocar=False)
    print("senha de %s alterada (nao exige troca no proximo login)." % login)
    return 0


def resetar_senha(conn, argv):
    if not argv:
        print("uso: resetar-senha <login>")
        return 2
    login = argv[0]
    try:
        _row, temp = gov.resetar_senha(conn, login)
    except gov.GovernancaError as e:
        print("erro: %s" % e.mensagem)
        return 1
    print("senha temporaria de %s: %s" % (login, temp))
    print("(aparece UMA vez; o login exigira a troca)")
    return 0


def desativar_usuario(conn, argv):
    if not argv:
        print("uso: desativar-usuario <login>")
        return 2
    row = gov.desativar_usuario(conn, argv[0])
    print("usuario %s desativado (ativo=0)." % row["login"])
    return 0


def ativar_usuario(conn, argv):
    if not argv:
        print("uso: ativar-usuario <login>")
        return 2
    row = gov.reativar_usuario(conn, argv[0])
    print("usuario %s reativado (ativo=1)." % row["login"])
    return 0


def excluir_usuario(conn, argv):
    if not argv:
        print("uso: excluir-usuario <login>")
        return 2
    login = argv[0]
    try:
        resp = input("Excluir %s DEFINITIVAMENTE? (digite o login para confirmar): " % login)
    except EOFError:
        print("cancelado (sem confirmacao).")
        return 1
    if resp.strip() != login:
        print("cancelado.")
        return 1
    row = gov.excluir_usuario(conn, login)
    print("usuario %s excluido." % row["login"])
    return 0


def tokens(conn, argv):
    _json(gov.listar_tokens(conn))
    return 0


def bloqueios(conn, argv):
    _json(gov.listar_bloqueios(conn, incluir_inativos="--todos" in argv))
    return 0


def historico(conn, argv):
    if not argv:
        print("uso: historico P-<numero>")
        return 2
    _json(gov.historico(conn, _p_id(argv[0]), publico="--publico" in argv))
    return 0


def ajuda(conn=None, argv=None):
    print(__doc__.strip())
    return 0


COMANDOS = {
    "pendentes": pendentes,
    "cadastro": cadastro,
    "radar": cadastro,
    "usuarios": usuarios,
    "senha": senha,
    "resetar-senha": resetar_senha,
    "desativar-usuario": desativar_usuario,
    "ativar-usuario": ativar_usuario,
    "excluir-usuario": excluir_usuario,
    "tokens": tokens,
    "bloqueios": bloqueios,
    "historico": historico,
    "ajuda": ajuda,
    "-h": ajuda,
    "--help": ajuda,
}


def _menu():
    conn = _conn()
    while True:
        print("""
Radar Brasil — modo console (servidor)
  1) Cadastros pendentes (nao verificados)
  2) Detalhes de um cadastro
  3) Trocar senha de um usuario
  4) Resetar senha (gera temporaria)
  5) Listar usuarios
  6) Tokens de API
  7) Bloqueios geograficos
  8) Historico de um ponto
  9) Desativar usuario
 10) Reativar usuario
 11) Excluir usuario
  0) Sair""")
        try:
            op = input("Opcao: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if op == "1":
                pendentes(conn, [])
            elif op == "2":
                cadastro(conn, [input("id (ex.: P-1130): ").strip()])
            elif op == "3":
                senha(conn, [input("login: ").strip()])
            elif op == "4":
                resetar_senha(conn, [input("login: ").strip()])
            elif op == "5":
                usuarios(conn, [])
            elif op == "6":
                tokens(conn, [])
            elif op == "7":
                bloqueios(conn, [])
            elif op == "8":
                historico(conn, [input("id (ex.: P-1130): ").strip()])
            elif op == "9":
                desativar_usuario(conn, [input("login: ").strip()])
            elif op == "10":
                ativar_usuario(conn, [input("login: ").strip()])
            elif op == "11":
                excluir_usuario(conn, [input("login: ").strip()])
            elif op in ("0", "sair", "q"):
                return 0
            elif op == "":
                pass
            else:
                print("opcao invalida")
        except (ValueError, gov.GovernancaError) as e:
            print("erro: %s" % getattr(e, "mensagem", e))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        if sys.stdin.isatty():
            return _menu()
        return ajuda()
    if argv[0].lower() in ("menu", "console"):
        return _menu()
    fn = COMANDOS.get(argv[0].lower())
    if fn is None:
        print("comando desconhecido: %s\n" % argv[0])
        return ajuda()
    if fn is ajuda:
        return ajuda()
    conn = _conn()
    try:
        return fn(conn, argv[1:])
    except (ValueError, gov.GovernancaError) as e:
        print("erro: %s" % getattr(e, "mensagem", e))
        return 1
    except KeyboardInterrupt:
        print()
        return 130
    finally:
        try:
            conn.close()
        except Exception:
            pass
