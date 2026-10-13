#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""radar-api — cliente de console (Linux) para a API do Radar Brasil.

Fala com a API publica do site (api.pse) por HTTPS e guarda a sessao num
cookie jar local. NAO acessa o banco: tudo passa pela API, como manda a regra
dura do projeto.

Uso rapido:
    radar-api login admin            # pede a senha (nao aparece na tela)
    radar-api pendentes              # fila de cadastros nao verificados
    radar-api senha                  # troca a propria senha (pede atual/nova)
    radar-api radar P-1130
    radar-api radares --lat -23.55 --lon -46.63 --raio 1000
    radar-api ajuda

Sessao:   ~/.config/radar-api/cookies.txt   (modo 600)
Token:    ~/.config/radar-api/token.txt     (usar-token / limpar-token)
Base:     variavel RADAR_API_URL (default: producao)
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get(
    "RADAR_API_URL",
    "https://servidor3.lucas.inf.br/openclaw/radar/api.pse")
CONF_DIR = os.path.expanduser(os.environ.get("RADAR_API_CONF", "~/.config/radar-api"))
COOKIE = os.path.join(CONF_DIR, "cookies.txt")
TOKENF = os.path.join(CONF_DIR, "token.txt")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE          # cert autoassinado da casa


def _jar():
    os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
    jar = http.cookiejar.MozillaCookieJar(COOKIE)
    if os.path.exists(COOKIE):
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    return jar


def _token():
    try:
        with open(TOKENF, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _mostrar(status, texto):
    try:
        dados = json.loads(texto)
        print(json.dumps(dados, ensure_ascii=False, indent=2))
    except ValueError:
        print(texto)
    if status >= 400:
        print("(HTTP %d)" % status, file=sys.stderr)


def chamar(rota, metodo="GET", params=None, corpo=None):
    url = BASE + "?rota=" + urllib.parse.quote(rota, safe="/")
    if params:
        url += "&" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None})
    data = None
    headers = {"Accept": "application/json"}
    if corpo is not None:
        data = json.dumps(corpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    tok = _token()
    if tok:
        headers["X-Api-Token"] = tok
    req = urllib.request.Request(url, data=data, headers=headers, method=metodo)
    jar = _jar()
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=_CTX))
    try:
        r = op.open(req, timeout=30)
        texto, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        texto, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:                      # rede/DNS/TLS
        print("erro de rede:", e, file=sys.stderr)
        return 1
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    _mostrar(status, texto)
    return 0 if status < 400 else 1


def _senha(flag, prompt="Senha: "):
    return flag if flag else getpass.getpass(prompt)


def _limpo(*pares):
    """dict sem os valores None (monta corpo de POST/PATCH)."""
    return {k: v for k, v in zip(pares[0::2], pares[1::2]) if v is not None}


# ------------------------------- comandos ---------------------------------

def c_login(a):
    return chamar("/api/v1/login", "POST",
                  corpo={"login": a.login, "senha": _senha(a.senha)})


def c_logout(a):
    return chamar("/api/v1/logout", "POST", corpo={})


def c_eu(a):
    return chamar("/api/v1/gestao/eu")


def c_senha(a):
    atual = _senha(a.atual, "Senha atual: ")
    nova = a.nova
    if not nova:
        nova = getpass.getpass("Nova senha (min. 8): ")
        if nova != getpass.getpass("Repita a nova senha: "):
            print("as senhas nao conferem", file=sys.stderr)
            return 2
    return chamar("/api/v1/minha-senha", "POST",
                  corpo={"senha_atual": atual, "senha_nova": nova})


def c_pendentes(a):
    return chamar("/api/v1/gestao/pendentes")


def c_radar(a):
    return chamar("/api/v1/radares/" + a.id, params={"formato": "json"})


def c_radares(a):
    return chamar("/api/v1/radares", params=_limpo(
        "lat", a.lat, "lon", a.lon, "raio", a.raio, "limite", a.limite,
        "uf", a.uf, "rodovia", a.rodovia, "formato", "json"))


def c_historico(a):
    return chamar("/api/v1/radares/%s/historico" % a.id)


def c_verificar(a):
    return chamar("/api/v1/gestao/radar/%s/verificar" % a.id, "POST",
                  corpo={"motivo": a.motivo})


def c_editar(a):
    return chamar("/api/v1/gestao/radar/" + a.id, "PATCH", corpo=_limpo(
        "km", a.km, "observacoes", a.observacoes, "velocidade_geral", a.velocidade,
        "tipo_pista", a.tipo_pista, "via", a.via, "municipio", a.municipio, "uf", a.uf))


def c_desabilitar(a):
    return chamar("/api/v1/gestao/radar/%s/desabilitar" % a.id, "POST",
                  corpo={"motivo": a.motivo})


def c_remover(a):
    return chamar("/api/v1/gestao/radar/%s/remover" % a.id, "POST",
                  corpo={"motivo": a.motivo})


def c_vinculo(a):
    return chamar("/api/v1/gestao/correspondencias/" + a.id, "POST",
                  corpo=_limpo("status", a.status, "motivo", a.motivo))


def c_usuarios(a):
    return chamar("/api/v1/gestao/usuarios")


def c_criar_usuario(a):
    return chamar("/api/v1/gestao/usuarios", "POST", corpo=_limpo(
        "login", a.login, "papel", a.papel, "senha", a.senha,
        "nome", a.nome, "email", a.email))


def c_editar_usuario(a):
    corpo = _limpo("papel", a.papel)
    if a.ativo is not None:
        corpo["ativo"] = bool(a.ativo)
    return chamar("/api/v1/gestao/usuarios/" + a.id, "PATCH", corpo=corpo)


def c_resetar_senha(a):
    return chamar("/api/v1/gestao/usuarios/%s/senha" % a.id, "POST", corpo={})


def c_tokens(a):
    return chamar("/api/v1/gestao/tokens")


def c_criar_token(a):
    return chamar("/api/v1/gestao/tokens", "POST",
                  corpo={"nome": a.nome, "escopo": a.escopo})


def c_revogar_token(a):
    return chamar("/api/v1/gestao/tokens/%s/revogar" % a.id, "POST", corpo={})


def c_bloqueios(a):
    return chamar("/api/v1/gestao/bloqueios")


def c_bloquear(a):
    return chamar("/api/v1/gestao/bloqueios", "POST", corpo={
        "tipo": a.tipo, "latitude": a.lat, "longitude": a.lon,
        "raio_metros": a.raio, "motivo": a.motivo})


def c_desbloquear(a):
    return chamar("/api/v1/gestao/bloqueios/" + a.id, "DELETE")


def c_usar_token(a):
    os.makedirs(CONF_DIR, mode=0o700, exist_ok=True)
    with open(TOKENF, "w", encoding="utf-8") as f:
        f.write(a.valor.strip() + "\n")
    os.chmod(TOKENF, 0o600)
    print("token de API salvo em %s" % TOKENF)
    return 0


def c_limpar_token(a):
    try:
        os.remove(TOKENF)
    except OSError:
        pass
    print("token de API removido")
    return 0


def c_ajuda(a):
    print(__doc__)
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="radar-api", description="Cliente de console (Linux) da API do Radar Brasil.")
    sub = p.add_subparsers(dest="cmd")

    def add(nome, fn, help_):
        s = sub.add_parser(nome, help=help_)
        s.set_defaults(fn=fn)
        return s

    s = add("login", c_login, "entra e guarda a sessao (cookie)")
    s.add_argument("login")
    s.add_argument("--senha", help="senha (senao pede no prompt)")

    add("logout", c_logout, "encerra a sessao")
    add("eu", c_eu, "quem sou eu (login/papel)")

    s = add("senha", c_senha, "troca a propria senha")
    s.add_argument("--atual"); s.add_argument("--nova")

    add("pendentes", c_pendentes, "cadastros nao verificados")
    s = add("radar", c_radar, "um radar por id"); s.add_argument("id")
    s = add("radares", c_radares, "consulta por raio/filtros")
    s.add_argument("--lat"); s.add_argument("--lon"); s.add_argument("--raio")
    s.add_argument("--limite"); s.add_argument("--uf"); s.add_argument("--rodovia")
    s = add("historico", c_historico, "historico publico de um ponto"); s.add_argument("id")

    s = add("verificar", c_verificar, "marca um radar como verificado")
    s.add_argument("id"); s.add_argument("--motivo", default="vistoria")
    s = add("editar", c_editar, "edita campos de um radar")
    s.add_argument("id")
    for opt in ("km", "observacoes", "velocidade", "tipo-pista", "via", "municipio", "uf"):
        s.add_argument("--" + opt)
    s = add("desabilitar", c_desabilitar, "desabilita (motivo obrigatorio)")
    s.add_argument("id"); s.add_argument("--motivo", required=True)
    s = add("remover", c_remover, "remove = tombstone (motivo obrigatorio)")
    s.add_argument("id"); s.add_argument("--motivo", required=True)
    s = add("vinculo", c_vinculo, "resolve vinculo de correspondencia")
    s.add_argument("id"); s.add_argument("--status", required=True,
                                         choices=["oficial_vence", "colaborativo_vence"])
    s.add_argument("--motivo")

    add("usuarios", c_usuarios, "lista usuarios")
    s = add("criar-usuario", c_criar_usuario, "cria usuario")
    s.add_argument("login"); s.add_argument("--papel", default="moderador")
    s.add_argument("--senha"); s.add_argument("--nome"); s.add_argument("--email")
    s = add("editar-usuario", c_editar_usuario, "papel/ativo de um usuario")
    s.add_argument("id"); s.add_argument("--papel"); s.add_argument("--ativo", type=int, choices=[0, 1])
    s = add("resetar-senha", c_resetar_senha, "gera senha temporaria"); s.add_argument("id")

    add("tokens", c_tokens, "lista tokens (so prefixo)")
    s = add("criar-token", c_criar_token, "emite token (valor aparece 1x)")
    s.add_argument("nome"); s.add_argument("--escopo", default="moderador")
    s = add("revogar-token", c_revogar_token, "revoga um token"); s.add_argument("id")

    add("bloqueios", c_bloqueios, "lista bloqueios geograficos")
    s = add("bloquear", c_bloquear, "cria bloqueio (marcacao_falsa|zona_sombra)")
    s.add_argument("--tipo", required=True, choices=["marcacao_falsa", "zona_sombra"])
    s.add_argument("--lat", required=True); s.add_argument("--lon", required=True)
    s.add_argument("--raio", required=True); s.add_argument("--motivo", required=True)
    s = add("desbloquear", c_desbloquear, "desativa um bloqueio"); s.add_argument("id")

    s = add("usar-token", c_usar_token, "usa um token de API (X-Api-Token)")
    s.add_argument("valor")
    add("limpar-token", c_limpar_token, "volta a usar so a sessao")
    add("ajuda", c_ajuda, "mostra a ajuda")
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        p.print_help()
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
