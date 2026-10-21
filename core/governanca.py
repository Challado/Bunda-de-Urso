# -*- coding: utf-8 -*-
"""Governanca da ingestao do Radar Brasil (camada colaborativa).

Regra dura do dono: NADA escreve direto no banco por fora do app — toda
escrita passa pela API. Este modulo e o unico lugar que grava as tabelas de
governanca (USUARIO, API_TOKEN, SESSAO, RADAR_ALTERACAO, BLOQUEIO_GEOGRAFICO,
CORRESPONDENCIA_PONTO, SUBMISSAO_PUBLICA) e marca o estado do radar
(procedencia / verificacao_status / tombstone) em PONTO_FISCALIZACAO.

Camadas de confianca (especificacao aprovada 13/10/2026):
  - leitura aberta;
  - submissao publica entra como ``colaborativo`` NAO verificado e publica na
    hora; proximidade de ponto OFICIAL apenas sugere correspondencia para
    revisao; verificacao e substituicao exigem moderacao;
  - verificacao / edicao / remocao exigem sessao ou X-Api-Token de gestao;
  - remocao e TOMBSTONE (soft delete): a linha nunca e apagada.

O esquema desta camada vive em sql/migracoes/0001_governanca.*.sql e e
aplicado por ``aplicar_migracoes`` (aditivo e idempotente). Nao altera o
esquema canonico T01..T77 nem o init_db do projeto.
"""
import datetime
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import urllib.parse

from . import config
from . import db as dbmod
from . import geo

# Nivel de privilegio por escopo/papel. contribuidor le a gestao mas nao
# altera; moderador verifica/edita/remove; admin gerencia usuarios, tokens e
# bloqueios.
NIVEL = {"contribuidor": 1, "moderador": 2, "admin": 3}
PAPEIS = ("admin", "moderador")
ESCOPOS = ("contribuidor", "moderador", "admin")
GOVERNANCA_VERSION = "0001"

COOKIE_SESSAO = "radar_sessao"

_TIPOS_ALTERACAO = ("criado", "editado", "verificado", "desabilitado",
                    "removido", "bloqueio_criado", "bloqueio_removido")


class GovernancaError(Exception):
    """Erro de dominio com codigo HTTP/codigo de erro para a API."""

    def __init__(self, status, codigo, mensagem, campo=None, detalhes=None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.campo = campo
        self.detalhes = detalhes or []


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def _agora_mais(segundos):
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=int(segundos))).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def _agora_menos(segundos):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=int(segundos))).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"),
                      default=str)


# ---------------------------------------------------------------------------
# Esquema / migracoes versionadas
# ---------------------------------------------------------------------------
def _dir_migracoes():
    return os.path.join(config.SQL_DIR, "migracoes")


def migracoes_disponiveis():
    """Lista (versao, caminho) das migracoes SQLite, em ordem."""
    d = _dir_migracoes()
    if not os.path.isdir(d):
        return []
    saida = []
    for nome in sorted(os.listdir(d)):
        if not nome.endswith(".sqlite.sql"):
            continue
        versao = nome.split("_", 1)[0]
        saida.append((versao, os.path.join(d, nome)))
    return saida


def _colunas(conn, tabela):
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(%s)" % tabela)}
    except sqlite3.Error:
        return set()


def _aplicar_diretiva_coluna(conn, linha):
    """Aplica ``-- +COLUNA tabela coluna definicao`` (ALTER se faltar)."""
    partes = linha[len("-- +COLUNA"):].strip().split(None, 2)
    if len(partes) < 3:
        return
    tabela, coluna, definicao = partes
    if not tabela.isidentifier() or not coluna.isidentifier():
        return
    if coluna in _colunas(conn, tabela):
        return
    conn.execute("ALTER TABLE %s ADD COLUMN %s %s"
                 % (tabela, coluna, definicao))


def aplicar_migracoes(conn):
    """Aplica as migracoes de governanca ainda nao executadas. Idempotente."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS MIGRACAO_GOVERNANCA ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "versao TEXT NOT NULL UNIQUE, aplicada_em TEXT NOT NULL)")
    aplicadas = {r[0] for r in conn.execute(
        "SELECT versao FROM MIGRACAO_GOVERNANCA")}
    for versao, caminho in migracoes_disponiveis():
        if versao in aplicadas:
            continue
        with open(caminho, "r", encoding="utf-8") as f:
            texto = f.read()
        linhas_sql = []
        for linha in texto.splitlines():
            if linha.strip().startswith("-- +COLUNA"):
                _aplicar_diretiva_coluna(conn, linha.strip())
            else:
                linhas_sql.append(linha)
        conn.executescript("BEGIN;\n" + "\n".join(linhas_sql) + "\nCOMMIT;")
        conn.execute(
            "INSERT INTO MIGRACAO_GOVERNANCA (versao, aplicada_em) "
            "VALUES (?, ?)", (versao, _agora()))
        conn.commit()
    return conn


def garantir_esquema(conn):
    """Garante o esquema canonico (T01..T77) + a camada de governanca."""
    dbmod.init_db(conn)
    aplicar_migracoes(conn)
    return conn


def tem_governanca(conn):
    for t in ("USUARIO", "API_TOKEN", "RADAR_ALTERACAO", "BLOQUEIO_GEOGRAFICO"):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name=?", (t,)).fetchone() is None:
            return False
    return True


def colunas_ponto_governanca(conn):
    return _colunas(conn, "PONTO_FISCALIZACAO")


# ---------------------------------------------------------------------------
# Senha — PBKDF2-HMAC-SHA256 (stdlib), salt por usuario, comparacao constante
# ---------------------------------------------------------------------------
def hash_senha(senha, salt=None, iteracoes=None):
    """Devolve (hash_hex, salt_hex, iteracoes). NUNCA guarda a senha."""
    salt = salt or secrets.token_hex(16)
    n = int(iteracoes or config.GOV_ITERACOES)
    if n < 200000:
        n = 200000
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                            bytes.fromhex(salt), n).hex()
    return h, salt, n


def verificar_senha(senha, senha_hash, salt, iteracoes):
    calc = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                               bytes.fromhex(salt), int(iteracoes)).hex()
    return hmac.compare_digest(calc, senha_hash or "")


_SALT_DUMMY = "00" * 16


def _hash_dummy(senha):
    """Hash descartavel para gastar o mesmo tempo quando o usuario nao existe."""
    hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                        bytes.fromhex(_SALT_DUMMY), config.GOV_ITERACOES)


# ---------------------------------------------------------------------------
# Tokens de API — guarda o HASH; o valor aparece UMA vez na emissao
# ---------------------------------------------------------------------------
def gerar_token_valor():
    return "rb_" + secrets.token_urlsafe(32)


def hash_token(valor):
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def prefixo_token(valor):
    return valor[:10]


def emitir_token(conn, nome, escopo, dono=None, expira_em=None,
                 observacoes=None, criado_por=None):
    garantir_esquema(conn)
    if escopo not in ESCOPOS:
        raise GovernancaError(422, "escopo_invalido",
                              "escopo deve ser um de: %s" % ", ".join(ESCOPOS),
                              campo="escopo")
    if not (nome or "").strip():
        raise GovernancaError(422, "nome_obrigatorio", "informe o nome do token",
                              campo="nome")
    valor = gerar_token_valor()
    tid = dbmod.insert(conn, "API_TOKEN", {
        "nome": nome.strip(), "dono": dono, "escopo": escopo,
        "valor_hash": hash_token(valor), "prefixo": prefixo_token(valor),
        "criado_em": _agora(), "expira_em": expira_em, "observacoes":
        observacoes})
    conn.commit()
    return tid, valor


def _token_por_valor(conn, valor):
    if not valor:
        return None
    row = conn.execute("SELECT * FROM API_TOKEN WHERE valor_hash = ?",
                       (hash_token(valor),)).fetchone()
    if row is None or row["revogado_em"]:
        return None
    if row["expira_em"] and row["expira_em"] <= _agora():
        return None
    return row


def listar_tokens(conn):
    garantir_esquema(conn)
    out = []
    for r in conn.execute(
            "SELECT id, nome, dono, escopo, prefixo, criado_em, expira_em, "
            "revogado_em, ultimo_uso, observacoes FROM API_TOKEN ORDER BY id"):
        out.append(dict(r))
    return out


def revogar_token(conn, token_id):
    garantir_esquema(conn)
    row = conn.execute("SELECT id FROM API_TOKEN WHERE id=?",
                       (token_id,)).fetchone()
    if row is None:
        raise GovernancaError(404, "token_nao_encontrado",
                              "token %s nao encontrado" % token_id)
    conn.execute("UPDATE API_TOKEN SET revogado_em=? WHERE id=? AND "
                 "revogado_em IS NULL", (_agora(), token_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def criar_usuario(conn, login, senha, nome=None, email=None, papel="admin",
                  deve_trocar_senha=True, ativo=True, iteracoes=None):
    garantir_esquema(conn)
    login = (login or "").strip()
    if not login:
        raise GovernancaError(422, "login_obrigatorio", "informe o login",
                              campo="login")
    if not senha:
        raise GovernancaError(422, "senha_obrigatoria", "informe a senha",
                              campo="senha")
    if papel not in PAPEIS:
        raise GovernancaError(422, "papel_invalido",
                              "papel deve ser admin ou moderador",
                              campo="papel")
    if conn.execute("SELECT 1 FROM USUARIO WHERE login=?", (login,)).fetchone():
        raise GovernancaError(409, "login_existente",
                              "ja existe usuario com esse login",
                              campo="login")
    h, salt, n = hash_senha(senha, iteracoes=iteracoes)
    uid = dbmod.insert(conn, "USUARIO", {
        "login": login, "nome": nome, "email": email, "senha_hash": h,
        "senha_salt": salt, "iteracoes": n, "papel": papel,
        "ativo": 1 if ativo else 0, "criado_em": _agora(),
        "deve_trocar_senha": 1 if deve_trocar_senha else 0})
    conn.commit()
    return uid


def obter_usuario_por_login(conn, login):
    garantir_esquema(conn)
    return conn.execute("SELECT * FROM USUARIO WHERE login=?",
                        ((login or "").strip(),)).fetchone()


def obter_usuario(conn, usuario_id):
    return conn.execute("SELECT * FROM USUARIO WHERE id=?",
                        (usuario_id,)).fetchone()


def listar_usuarios(conn):
    garantir_esquema(conn)
    out = []
    for r in conn.execute(
            "SELECT id, login, nome, email, papel, ativo, criado_em, "
            "ultimo_login, deve_trocar_senha FROM USUARIO ORDER BY id"):
        out.append(dict(r))
    return out


def autenticar_senha(conn, login, senha):
    """Devolve a linha do usuario autenticado, ou None (falha generica)."""
    garantir_esquema(conn)
    row = obter_usuario_por_login(conn, login)
    if row is None or not row["ativo"]:
        _hash_dummy(senha or "")           # tempo constante (anti-enumeracao)
        return None
    if not verificar_senha(senha or "", row["senha_hash"], row["senha_salt"],
                           row["iteracoes"]):
        return None
    return row


def gerar_senha_temporaria():
    return secrets.token_urlsafe(9)


def definir_papel_ativo(conn, usuario_id, papel=None, ativo=None):
    row = obter_usuario(conn, usuario_id)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado",
                              "usuario %s nao encontrado" % usuario_id)
    if papel is not None:
        if papel not in PAPEIS:
            raise GovernancaError(422, "papel_invalido",
                                  "papel deve ser admin ou moderador",
                                  campo="papel")
        conn.execute("UPDATE USUARIO SET papel=? WHERE id=?",
                     (papel, usuario_id))
    if ativo is not None:
        conn.execute("UPDATE USUARIO SET ativo=? WHERE id=?",
                     (1 if ativo else 0, usuario_id))
    conn.commit()


def resetar_senha(conn, login, nova_senha=None, deve_trocar=True):
    """Define nova senha (temporaria por padrao). Devolve (usuario, senha)."""
    garantir_esquema(conn)
    row = obter_usuario_por_login(conn, login)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado",
                              "usuario %s nao encontrado" % login)
    senha = nova_senha or gerar_senha_temporaria()
    h, salt, n = hash_senha(senha)
    conn.execute("UPDATE USUARIO SET senha_hash=?, senha_salt=?, iteracoes=?, "
                 "deve_trocar_senha=? WHERE id=?",
                 (h, salt, n, 1 if deve_trocar else 0, row["id"]))
    # derruba sessoes antigas do usuario
    conn.execute("DELETE FROM SESSAO WHERE usuario_id=?", (row["id"],))
    conn.commit()
    return row, senha


def trocar_propria_senha(conn, usuario_id, senha_atual, senha_nova):
    row = obter_usuario(conn, usuario_id)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado", "usuario invalido")
    if not senha_atual or not verificar_senha(senha_atual, row["senha_hash"],
                                              row["senha_salt"],
                                              row["iteracoes"]):
        raise GovernancaError(401, "senha_atual_invalida",
                              "senha atual invalida", campo="senha_atual")
    if not senha_nova or len(senha_nova) < 8:
        raise GovernancaError(422, "senha_fraca",
                              "a nova senha deve ter ao menos 8 caracteres",
                              campo="senha_nova")
    h, salt, n = hash_senha(senha_nova)
    conn.execute("UPDATE USUARIO SET senha_hash=?, senha_salt=?, iteracoes=?, "
                 "deve_trocar_senha=0 WHERE id=?", (h, salt, n, usuario_id))
    conn.commit()


def _ultimo_admin(conn, usuario_id):
    """True se o usuario for o ultimo admin ATIVO (nao pode ser tirado)."""
    row = obter_usuario(conn, usuario_id)
    if row is None or row["papel"] != "admin" or not row["ativo"]:
        return False
    restantes = conn.execute(
        "SELECT COUNT(*) FROM USUARIO WHERE papel='admin' AND ativo=1 "
        "AND id<>?", (usuario_id,)).fetchone()[0]
    return restantes == 0


def desativar_usuario(conn, login):
    """Desativa (ativo=0) um usuario. Recusa desativar o ultimo admin ativo."""
    garantir_esquema(conn)
    row = obter_usuario_por_login(conn, login)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado",
                              "usuario %s nao encontrado" % login)
    if _ultimo_admin(conn, row["id"]):
        raise GovernancaError(409, "ultimo_admin",
                              "nao posso desativar o ultimo admin ativo")
    definir_papel_ativo(conn, row["id"], ativo=0)
    return row


def reativar_usuario(conn, login):
    """Reativa (ativo=1) um usuario."""
    garantir_esquema(conn)
    row = obter_usuario_por_login(conn, login)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado",
                              "usuario %s nao encontrado" % login)
    definir_papel_ativo(conn, row["id"], ativo=1)
    return row


def excluir_usuario(conn, login):
    """Exclui um usuario em definitivo.

    Preserva a AUDITORIA: as referencias em RADAR_ALTERACAO e
    BLOQUEIO_GEOGRAFICO viram NULL (resta o rotulo textual); as sessoes sao
    apagadas. Guarda anti-lockout: recusa excluir o ultimo admin ativo.
    """
    garantir_esquema(conn)
    row = obter_usuario_por_login(conn, login)
    if row is None:
        raise GovernancaError(404, "usuario_nao_encontrado",
                              "usuario %s nao encontrado" % login)
    if _ultimo_admin(conn, row["id"]):
        raise GovernancaError(409, "ultimo_admin",
                              "nao posso excluir o ultimo admin ativo")
    uid = row["id"]
    conn.execute("DELETE FROM SESSAO WHERE usuario_id=?", (uid,))
    conn.execute("UPDATE RADAR_ALTERACAO SET quem_usuario_id=NULL "
                 "WHERE quem_usuario_id=?", (uid,))
    conn.execute("UPDATE BLOQUEIO_GEOGRAFICO SET criado_por_usuario_id=NULL "
                 "WHERE criado_por_usuario_id=?", (uid,))
    conn.execute("DELETE FROM USUARIO WHERE id=?", (uid,))
    conn.commit()
    return row


# ---------------------------------------------------------------------------
# Sessao do painel
# ---------------------------------------------------------------------------
def criar_sessao(conn, usuario_id, ip=None, user_agent=None, ttl=None):
    garantir_esquema(conn)
    ttl = int(ttl or config.SESSAO_TTL_SEGUNDOS)
    valor = "s_" + secrets.token_urlsafe(32)
    dbmod.insert(conn, "SESSAO", {
        "token_hash": hash_token(valor), "usuario_id": usuario_id,
        "criado_em": _agora(), "expira_em": _agora_mais(ttl),
        "ultimo_uso": _agora(), "ip": ip, "user_agent": user_agent})
    conn.commit()
    return valor, ttl


def validar_sessao(conn, valor):
    if not valor:
        return None
    row = conn.execute(
        "SELECT s.id AS sessao_id, s.usuario_id, s.expira_em, u.login, "
        "u.papel, u.ativo, u.deve_trocar_senha FROM SESSAO s "
        "JOIN USUARIO u ON u.id=s.usuario_id WHERE s.token_hash=?",
        (hash_token(valor),)).fetchone()
    if row is None:
        return None
    if row["expira_em"] <= _agora():
        conn.execute("DELETE FROM SESSAO WHERE id=?", (row["sessao_id"],))
        conn.commit()
        return None
    if not row["ativo"]:
        return None
    conn.execute("UPDATE SESSAO SET ultimo_uso=? WHERE id=?",
                 (_agora(), row["sessao_id"]))
    conn.commit()
    return dict(row)


def encerrar_sessao(conn, valor):
    if not valor:
        return
    conn.execute("DELETE FROM SESSAO WHERE token_hash=?",
                 (hash_token(valor),))
    conn.commit()


def _cookie(environ, nome):
    raw = environ.get("HTTP_COOKIE") or ""
    for parte in raw.split(";"):
        parte = parte.strip()
        if "=" in parte:
            k, v = parte.split("=", 1)
            if k == nome:
                return urllib.parse.unquote(v)
    return None


def contexto_autenticacao(conn, environ):
    """Resolve o contexto de gestao a partir do pedido, ou None.

    Aceita ``X-Api-Token`` (escopo do token) OU a sessao do painel (cookie
    ``radar_sessao`` ou cabecalho ``X-Sessao``). Token invalido/revogado e
    sessao expirada levantam 401 (falha generica).
    """
    valor = (environ.get("HTTP_X_API_TOKEN") or "").strip()
    if valor:
        row = _token_por_valor(conn, valor)
        if row is None:
            raise GovernancaError(401, "token_invalido",
                                  "token ausente, invalido, expirado ou "
                                  "revogado")
        conn.execute("UPDATE API_TOKEN SET ultimo_uso=? WHERE id=?",
                     (_agora(), row["id"]))
        conn.commit()
        return {"tipo": "token", "token_id": row["id"],
                "usuario_id": None, "escopo": row["escopo"],
                "rotulo": row["nome"]}
    sess = _cookie(environ, COOKIE_SESSAO) or environ.get("HTTP_X_SESSAO")
    if sess:
        d = validar_sessao(conn, sess)
        if d is None:
            raise GovernancaError(401, "sessao_invalida",
                                  "sessao ausente ou expirada")
        return {"tipo": "usuario", "usuario_id": d["usuario_id"],
                "token_id": None, "escopo": d["papel"],
                "rotulo": d["login"]}
    return None


def nivel(ctx):
    if ctx is None:
        return 0
    return NIVEL.get(ctx.get("escopo"), 0)


def exigir(ctx, minimo):
    if ctx is None:
        raise GovernancaError(401, "autenticacao_obrigatoria",
                              "informe a sessao do painel ou o cabecalho "
                              "X-Api-Token")
    if nivel(ctx) < NIVEL[minimo]:
        raise GovernancaError(403, "permissao_negada",
                              "escopo insuficiente (exige %s)" % minimo)


# ---------------------------------------------------------------------------
# Auditoria (RADAR_ALTERACAO) — imutavel
# ---------------------------------------------------------------------------
def registrar_alteracao(conn, ponto_id, ctx, tipo, motivo=None, campos=None,
                        ip=None):
    if tipo not in _TIPOS_ALTERACAO:
        raise ValueError("tipo de alteracao invalido: %s" % tipo)
    ctx = ctx or {}
    dbmod.insert(conn, "RADAR_ALTERACAO", {
        "ponto_id": ponto_id,
        "quem_usuario_id": ctx.get("usuario_id"),
        "quem_token_id": ctx.get("token_id"),
        "quem_rotulo": ctx.get("rotulo"),
        "quando": _agora(),
        "tipo": tipo,
        "motivo": motivo,
        "campos_json": _json(campos) if campos is not None else None,
        "ip": ip})
    conn.commit()


def historico(conn, ponto_id, publico=False):
    garantir_esquema(conn)
    out = []
    for r in conn.execute(
            "SELECT id, ponto_id, quem_usuario_id, quem_token_id, quem_rotulo, "
            "quando, tipo, motivo, campos_json, ip FROM RADAR_ALTERACAO "
            "WHERE ponto_id=? ORDER BY id", (ponto_id,)):
        item = {"id": r["id"], "quando": r["quando"], "tipo": r["tipo"],
                "quem": r["quem_rotulo"] or "(sistema)", "motivo": r["motivo"]}
        try:
            item["campos"] = json.loads(r["campos_json"]) if r["campos_json"] else None
        except (ValueError, TypeError):
            item["campos"] = None
        if not publico:
            item["quem_usuario_id"] = r["quem_usuario_id"]
            item["quem_token_id"] = r["quem_token_id"]
            item["ip"] = r["ip"]
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Bloqueios geograficos (anti-sabotagem)
# ---------------------------------------------------------------------------
def bloqueios_ativos(conn):
    garantir_esquema(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM BLOQUEIO_GEOGRAFICO WHERE ativo=1 ORDER BY id")]


def listar_bloqueios(conn, incluir_inativos=False):
    garantir_esquema(conn)
    sql = ("SELECT * FROM BLOQUEIO_GEOGRAFICO"
           if incluir_inativos else
           "SELECT * FROM BLOQUEIO_GEOGRAFICO WHERE ativo=1")
    return [dict(r) for r in conn.execute(sql + " ORDER BY id")]


def bloqueio_que_contem(conn, lat, lon):
    for b in bloqueios_ativos(conn):
        raio = b["raio_metros"]
        if b["tipo"] == "zona_sombra" and not raio:
            raio = config.RAIO_ZONA_SOMBRA_M
        if geo.haversine_m(lat, lon, b["latitude"], b["longitude"]) <= raio:
            return b
    return None


def criar_bloqueio(conn, tipo, latitude, longitude, raio_metros, motivo,
                   ctx, origem_ponto_id=None):
    garantir_esquema(conn)
    if tipo not in ("marcacao_falsa", "zona_sombra"):
        raise GovernancaError(422, "tipo_invalido",
                              "tipo deve ser marcacao_falsa ou zona_sombra",
                              campo="tipo")
    try:
        lat = float(latitude)
        lon = float(longitude)
        raio = int(raio_metros)
    except (TypeError, ValueError):
        raise GovernancaError(422, "parametro_invalido",
                              "latitude, longitude e raio_metros sao "
                              "obrigatorios e numericos")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise GovernancaError(422, "coordenada_invalida",
                              "lat -90..90 e lon -180..180")
    if raio <= 0:
        raise GovernancaError(422, "raio_invalido",
                              "raio_metros deve ser positivo",
                              campo="raio_metros")
    bid = dbmod.insert(conn, "BLOQUEIO_GEOGRAFICO", {
        "tipo": tipo, "latitude": lat, "longitude": lon, "raio_metros": raio,
        "motivo": motivo, "criado_por_usuario_id": (ctx or {}).get("usuario_id"),
        "criado_em": _agora(), "ativo": 1, "origem_ponto_id": origem_ponto_id})
    registrar_alteracao(conn, origem_ponto_id, ctx, "bloqueio_criado",
                        motivo=motivo, campos={"bloqueio_id": bid, "tipo": tipo,
                                               "raio_metros": raio})
    return bid


def desativar_bloqueio(conn, bloqueio_id, ctx, motivo=None):
    garantir_esquema(conn)
    row = conn.execute("SELECT * FROM BLOQUEIO_GEOGRAFICO WHERE id=?",
                       (bloqueio_id,)).fetchone()
    if row is None:
        raise GovernancaError(404, "bloqueio_nao_encontrado",
                              "bloqueio %s nao encontrado" % bloqueio_id)
    conn.execute("UPDATE BLOQUEIO_GEOGRAFICO SET ativo=0 WHERE id=?",
                 (bloqueio_id,))
    conn.commit()
    registrar_alteracao(conn, row["origem_ponto_id"], ctx,
                        "bloqueio_removido", motivo=motivo,
                        campos={"bloqueio_id": bloqueio_id})


# ---------------------------------------------------------------------------
# Correspondencia colaborativo <-> oficial
# ---------------------------------------------------------------------------
def _coordenada_ponto(conn, ponto_id):
    row = conn.execute(
        "SELECT pos.latitude AS latitude, pos.longitude AS longitude "
        "FROM PONTO_FISCALIZACAO p LEFT JOIN POSICAO_GEOGRAFICA pos "
        "ON pos.id=p.posicao_id WHERE p.id=?", (ponto_id,)).fetchone()
    if row is None or row["latitude"] is None:
        return None, None
    return row["latitude"], row["longitude"]


##-- BUNDITA DE URSO #{8} -- Rotulo padrao de procedencia nao comprova origem oficial; verificar a cadeia documental. ##
def _oficiais_proximos(conn, lat, lon, raio):
    """Candidatos oficiais, ordenados por distancia; proximidade nao e identidade."""
    bb = geo.bounding_box(lat, lon, raio)
    longitude = ("(pos.longitude >= ? OR pos.longitude <= ?)"
                 if bb["cruza_antimeridiano"] else "pos.longitude BETWEEN ? AND ?")
    rows = conn.execute(
        "SELECT p.id AS ponto_id, pos.latitude AS latitude, "
        "pos.longitude AS longitude, p.municipio_id, p.via_id, p.km, p.tipo_pista, "
        "m.nome AS municipio, m.uf_sigla AS uf, v.codigo AS via "
        "FROM PONTO_FISCALIZACAO p "
        "JOIN POSICAO_GEOGRAFICA pos ON pos.id=p.posicao_id "
        "LEFT JOIN MUNICIPIO m ON m.codigo_ibge=p.municipio_id "
        "LEFT JOIN VIA v ON v.id=p.via_id "
        "WHERE pos.latitude BETWEEN ? AND ? AND " + longitude + " "
        "AND (p.procedencia IS NULL OR p.procedencia <> 'colaborativo') "
        "AND p.removido_em IS NULL "
        "AND (p.verificacao_status IS NULL OR p.verificacao_status <> 'desabilitado') "
        # Calcula a origem oficial uma vez. EXISTS correlacionado sem indice
        # por ponto varria os vinculos para cada ponto, travando bases grandes.
        "AND p.id IN (SELECT vp.ponto_id FROM VINCULO_REGISTRO_PONTO vp "
        "JOIN REGISTRO_FONTE r ON r.id=vp.registro_id "
        "JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id "
        "JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id "
        "JOIN FONTE f ON f.id=rf.fonte_id "
        "JOIN NATUREZA_FONTE nf ON nf.id=f.natureza_id "
        "WHERE vp.decisao_id IS NULL AND nf.codigo='oficial')",
        (bb["lat_min"], bb["lat_max"], bb["lon_min"], bb["lon_max"])).fetchall()
    candidatos = []
    for r in rows:
        d = geo.haversine_m(lat, lon, r["latitude"], r["longitude"])
        if d <= raio:
            candidatos.append({**dict(r), "distancia_metros": round(d, 3)})
    return sorted(candidatos, key=lambda r: (r["distancia_metros"], r["ponto_id"]))


def _oficial_perto(conn, lat, lon, raio):
    candidatos = _oficiais_proximos(conn, lat, lon, raio)
    return ((candidatos[0]["ponto_id"], candidatos[0]["distancia_metros"])
            if candidatos else (None, None))


def _complementar_por_proximidade(conn, ponto_id, candidatos):
    """Preenche somente lacunas do NOVO colaborativo com origem auditavel.

    Nao copia coordenada, velocidade, identidade, situacao ou verificacao.
    Mais de um candidato ou divergencia de municipio/via exige revisao.
    """
    if len(candidatos) != 1:
        return {}
    origem = candidatos[0]
    atual = conn.execute("SELECT municipio_id, via_id, km, tipo_pista FROM "
                         "PONTO_FISCALIZACAO WHERE id=?", (ponto_id,)).fetchone()
    if any(atual[campo] is not None and origem[campo] is not None
           and atual[campo] != origem[campo] for campo in ("municipio_id", "via_id")):
        return {}
    campos = {campo: origem[campo] for campo in ("municipio_id", "via_id", "tipo_pista")
              if atual[campo] is None and origem[campo] is not None}
    if atual["km"] is None and origem["via_id"] is not None and origem["km"] is not None:
        campos["km"] = origem["km"]
    if not campos:
        return {}
    conn.execute("UPDATE PONTO_FISCALIZACAO SET " +
                 ", ".join(campo + "=?" for campo in campos) + " WHERE id=?",
                 [*campos.values(), ponto_id])
    publicos = {"municipio": origem["municipio"], "via": origem["via"],
                "km": origem["km"], "tipo_pista": origem["tipo_pista"]}
    preenchidos = {campo.removesuffix("_id"): publicos[campo.removesuffix("_id")]
                   for campo in campos}
    registrar_alteracao(conn, ponto_id, None, "editado",
                        motivo="Complemento sugerido por proximidade; identidade nao verificada",
                        campos={"complemento_proximidade": {
                            "ponto_origem_id": "P-%d" % origem["ponto_id"],
                            "distancia_metros": origem["distancia_metros"],
                            "campos": preenchidos}})
    return preenchidos


def _inserir_correspondencia(conn, colaborativo_id, oficial_id, distancia,
                            status):
    if conn.execute("SELECT 1 FROM CORRESPONDENCIA_PONTO WHERE "
                    "ponto_colaborativo_id=? AND ponto_oficial_id=?",
                    (colaborativo_id, oficial_id)).fetchone():
        return None
    return dbmod.insert(conn, "CORRESPONDENCIA_PONTO", {
        "ponto_colaborativo_id": colaborativo_id,
        "ponto_oficial_id": oficial_id,
        "distancia_metros": round(distancia, 3),
        "status": status, "criado_em": _agora()})


def correspondencias_do_ponto(conn, ponto_id):
    garantir_esquema(conn)
    out = []
    for r in conn.execute(
            "SELECT * FROM CORRESPONDENCIA_PONTO WHERE ponto_colaborativo_id=? "
            "OR ponto_oficial_id=? ORDER BY id", (ponto_id, ponto_id)):
        out.append(dict(r))
    return out


# ---------------------------------------------------------------------------
# Validacao minima da submissao (mesma regra da ingestao autenticada)
# ---------------------------------------------------------------------------
def validar_minimo(item):
    """Exige coordenada plausivel OU municipio+via. Devolve (campo, msg) ou None."""
    if not isinstance(item, dict):
        return None, "cada item deve ser um objeto JSON"
    from coletor.fontes import normalizacao as nz
    for campo, aliases in (("velocidade_geral", ("velocidade_geral", "velocidade")),
                           ("velocidade_leves", ("velocidade_leves",)),
                           ("velocidade_pesados", ("velocidade_pesados",)),
                           ("km", ("km", "quilometro"))):
        valor = nz.pick(item, *aliases)
        if valor is not None:
            numero = nz.to_float(valor)
            valido = (numero is not None and math.isfinite(numero)
                      and (numero >= 0 if campo == "km" else 0 < numero <= 350))
            if isinstance(valor, bool) or not valido:
                return campo, ("informe um quilometro valido, maior ou igual a zero"
                               if campo == "km" else "informe uma velocidade maior que zero e ate 350 km/h")
    lat_raw = nz.pick(item, "latitude", "lat")
    lon_raw = nz.pick(item, "longitude", "lon", "lng")
    lat, lon = nz.to_float(lat_raw), nz.to_float(lon_raw)
    if lat_raw is not None or lon_raw is not None:
        if lat is None or lon is None or isinstance(lat_raw, bool) or isinstance(lon_raw, bool):
            return "latitude", "informe latitude E longitude juntas"
        if not (-90 <= lat <= 90):
            return "latitude", "latitude fora de -90..90"
        if not (-180 <= lon <= 180):
            return "longitude", "longitude fora de -180..180"
        if lat == 0 and lon == 0:
            return "latitude", "a coordenada 0,0 nao identifica um radar"
        return None
    municipio = nz.pick(item, "municipio", "municipio_nome", "cidade",
                        "municipio_ibge", "codigo_ibge", "ibge")
    via = nz.pick(item, "via", "via_codigo", "rodovia", "br")
    if not municipio:
        return "municipio", "informe latitude/longitude ou municipio+via"
    if not via:
        return "via", "informe latitude/longitude ou municipio+via"
    return None


def _coord_item(item):
    from coletor.fontes import normalizacao as nz
    return (nz.to_float(nz.pick(item, "latitude", "lat")),
            nz.to_float(nz.pick(item, "longitude", "lon", "lng")))


# ---------------------------------------------------------------------------
# Rate limit da submissao publica (por IP, por janela)
# ---------------------------------------------------------------------------
def _registrar_submissao(conn, procedencia, total, aceitos, rejeitados):
    procedencia = procedencia or {}
    dbmod.insert(conn, "SUBMISSAO_PUBLICA", {
        "ip": procedencia.get("ip"), "user_agent": procedencia.get("user_agent"),
        "quando": procedencia.get("quando") or _agora(),
        "contato": procedencia.get("contato"), "total": total,
        "aceitos": aceitos, "rejeitados": rejeitados})
    conn.commit()


def _checar_rate_limit(conn, ip):
    limite = int(config.SUBMISSAO_LIMITE)
    janela = int(config.SUBMISSAO_JANELA_SEGUNDOS)
    if not ip or limite <= 0:
        return
    n = dbmod.scalar(
        conn, "SELECT COUNT(*) FROM SUBMISSAO_PUBLICA WHERE ip=? AND quando>=?",
        (ip, _agora_menos(janela)))
    if n >= limite:
        raise GovernancaError(
            429, "limite_submissao",
            "limite de %d submissoes por IP a cada %d s atingido; tente mais "
            "tarde" % (limite, janela))


# ---------------------------------------------------------------------------
# Submissao PUBLICA
# ---------------------------------------------------------------------------
##-- BUNDITA DE URSO #{8} -- Proximidade de contribuicao publica nao comprova identidade nem verifica seus campos. ##
def submeter(conn, dados, procedencia=None, *, checar_limite=True):
    """POST /api/v1/radares/submeter — criacao aberta (sem token).

    Publica NA HORA como ``colaborativo``/``nao_verificado``; se houver ponto
    OFICIAL no raio de correspondencia, sugere revisao e, com candidato unico
    sem divergencia de municipio/via, complementa lacunas com auditoria. Reusa a
    MESMA normalizacao/upsert do coletor (ColetorBaseLWB sobre a mesma
    conexao). Recusa (409) o lote inteiro se alguma coordenada cair em
    BLOQUEIO_GEOGRAFICO ativo.
    """
    garantir_esquema(conn)
    procedencia = procedencia or {}
    ip = procedencia.get("ip")
    if checar_limite:
        _checar_rate_limit(conn, ip)

    if isinstance(dados, dict):
        itens = [dados]
    elif isinstance(dados, list):
        itens = dados
    else:
        raise GovernancaError(422, "payload_invalido",
                              "envie um objeto JSON ou um array de objetos")
    if not itens:
        raise GovernancaError(422, "payload_vazio", "nenhum radar enviado")

    validos, erros = [], []
    for i, item in enumerate(itens):
        erro = validar_minimo(item)
        if erro is None:
            validos.append((i, item))
        else:
            campo, msg = erro
            erros.append({"indice": i, "campo": campo, "mensagem": msg})

    # BLOQUEIO_GEOGRAFICO ativo: recusa o lote inteiro, com motivo.
    bloqueados = []
    for i, item in validos:
        lat, lon = _coord_item(item)
        if lat is None or lon is None:
            continue
        b = bloqueio_que_contem(conn, lat, lon)
        if b is not None:
            bloqueados.append({
                "indice": i, "campo": "coordenada",
                "mensagem": "submissao recusada: area bloqueada (%s)"
                            % b["tipo"],
                "bloqueio_id": b["id"], "tipo": b["tipo"],
                "motivo": b["motivo"]})
    if bloqueados:
        _registrar_submissao(conn, procedencia, len(itens), 0,
                             len(bloqueados) + len(erros))
        raise GovernancaError(
            409, "area_bloqueada",
            "submissao recusada: uma ou mais coordenadas caem em area "
            "bloqueada", detalhes=bloqueados)

    if not validos:
        _registrar_submissao(conn, procedencia, len(itens), 0, len(erros))
        raise GovernancaError(422, "payload_invalido",
                              "nenhum registro valido no envio",
                              detalhes=erros)

    # Mesma normalizacao/upsert do coletor, na MESMA conexao.
    ##-- BUNDITA DE URSO #{19} -- Escrita publica nao pode compartilhar a identidade da base autenticada. ##
    from coletor.fontes.submissao_publica import ColetorSubmissaoPublica
    conector = ColetorSubmissaoPublica(conn=conn)
    resumo = conector.ingerir_registros([it for _, it in validos],
                                        publicar=False)
    detalhes = resumo.get("detalhes") or []

    # O pipeline ignora corretamente um artefato ja ingerido. Reconstroi os
    # IDs para confirmar o reenvio sem apresentar erro ou criar duplicatas.
    detalhes_por_indice = {det["indice"]: det for det in detalhes}
    for det in conn.execute(
            "SELECT r.numero_ordem AS indice, r.id AS registro_id, vp.ponto_id "
            "FROM REGISTRO_FONTE r JOIN VINCULO_REGISTRO_PONTO vp "
            "ON vp.registro_id=r.id AND vp.decisao_id IS NULL "
            "WHERE r.artefato_id=?", (resumo["artefato_id"],)):
        detalhes_por_indice.setdefault(det["indice"], dict(det))
    sugeridos_ids, cadastros = [], []
    for erro in conn.execute(
            "SELECT r.numero_ordem AS indice, e.descricao FROM ERRO_VALIDACAO e "
            "JOIN REGISTRO_FONTE r ON r.id=e.registro_id WHERE e.execucao_id=?",
            (resumo["execucao_id"],)):
        erros.append({"indice": validos[erro["indice"]][0],
                      "mensagem": erro["descricao"]})
    for indice, det in sorted(detalhes_por_indice.items()):
        pid = det.get("ponto_id")
        if pid is None:
            continue
        novo = det.get("ponto_criado", False)
        if novo:
            conn.execute(
                "UPDATE PONTO_FISCALIZACAO SET procedencia='colaborativo', "
                "verificacao_status='nao_verificado' WHERE id=?", (pid,))
            registrar_alteracao(conn, pid, None, "criado",
                                campos={"origem": "submissao_publica",
                                        "procedencia": {
                                            "ip": ip,
                                            "user_agent": procedencia.get("user_agent"),
                                            "quando": procedencia.get("quando"),
                                            "contato": procedencia.get("contato")}},
                                ip=ip)
        proximidade = {"raio_metros": config.RAIO_CORRESPONDENCIA_M,
                       "candidatos": [], "campos_complementados": {},
                       "status": "sem_coordenadas"}
        cadastros.append({"indice": validos[indice][0], "id": "P-%d" % pid,
                          "proximidade": proximidade})
        lat, lon = _coordenada_ponto(conn, pid)
        if lat is None:
            continue
        candidatos = _oficiais_proximos(conn, lat, lon, config.RAIO_CORRESPONDENCIA_M)
        proximidade["status"] = ("sem_candidatos" if not candidatos else
                                  "candidato" if len(candidatos) == 1 else "ambiguo")
        proximidade["candidatos"] = [{"id": "P-%d" % p["ponto_id"],
                                      "distancia_metros": p["distancia_metros"],
                                      "via": p["via"], "municipio": p["municipio"],
                                      "uf": p["uf"]} for p in candidatos]
        if novo:
            proximidade["campos_complementados"] = _complementar_por_proximidade(conn, pid, candidatos)
        if candidatos:
            for candidato in candidatos:
                _inserir_correspondencia(conn, pid, candidato["ponto_id"],
                                        candidato["distancia_metros"], "corroborado")
            # Proximidade sugere revisao; nao verifica identidade ou campos.
            sugeridos_ids.append(pid)
    conn.commit()

    ignorados = resumo.get("ignorados", 0)
    aceitos = resumo.get("criados", 0) + resumo.get("atualizados", 0) + ignorados
    rejeitados = len(itens) - aceitos
    _registrar_submissao(conn, procedencia, len(itens), aceitos, rejeitados)
    if not aceitos:
        raise GovernancaError(422, "payload_invalido", "nenhum registro valido no envio",
                              detalhes=erros)
    return {
        "ok": aceitos > 0,
        "aceitos": aceitos,
        "criados": resumo.get("criados", 0),
        "atualizados": resumo.get("atualizados", 0),
        "ja_cadastrados": ignorados,
        "cadastros": cadastros,
        "corroborados": 0,
        "corroborados_ids": [],
        "correspondencias_sugeridas": len(sugeridos_ids),
        "correspondencias_sugeridas_ids": sugeridos_ids,
        "rejeitados": rejeitados,
        "erros": erros,
    }


# ---------------------------------------------------------------------------
# Gestao — leitura
# ---------------------------------------------------------------------------
def _resumo_ponto(conn, ponto_id):
    row = conn.execute(
        "SELECT p.id, p.procedencia, p.verificacao_status, p.removido_em, "
        "p.motivo_remocao, p.km, p.tipo_pista, p.observacoes, pos.latitude, "
        "pos.longitude, m.nome AS municipio, u.sigla AS uf, v.codigo AS via "
        "FROM PONTO_FISCALIZACAO p "
        "LEFT JOIN POSICAO_GEOGRAFICA pos ON pos.id=p.posicao_id "
        "LEFT JOIN MUNICIPIO m ON m.codigo_ibge=p.municipio_id "
        "LEFT JOIN UF u ON u.sigla=m.uf_sigla "
        "LEFT JOIN VIA v ON v.id=p.via_id WHERE p.id=?", (ponto_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["id"] = "P-%d" % d["id"]
    return d


def listar_pendentes(conn, limite=100, cursor=None, status=None):
    """Fila de colaborativos (nao removidos). status filtra verificacao."""
    garantir_esquema(conn)
    where = ["procedencia='colaborativo'", "removido_em IS NULL"]
    params = []
    if status:
        where.append("verificacao_status=?")
        params.append(status)
    sql = ("SELECT p.id FROM PONTO_FISCALIZACAO p WHERE " + " AND ".join(where)
           + " ORDER BY p.id")
    ids = [r[0] for r in conn.execute(sql, params)]
    total = len(ids)
    try:
        offset = int(cursor) if cursor else 0
    except (TypeError, ValueError):
        offset = 0
    recorte = ids[offset:offset + limite]
    pontos = [_resumo_ponto(conn, pid) for pid in recorte]
    proximo = str(offset + limite) if offset + limite < total else None
    return pontos, {"total": total, "retornados": len(pontos),
                    "proximo_cursor": proximo}


def obter_radar(conn, ponto_id):
    from . import consultas
    reg = consultas.buscar_ponto_por_id(conn, "P-%d" % ponto_id)
    if reg is None:
        raise GovernancaError(404, "ponto_nao_encontrado",
                              "ponto P-%d nao encontrado" % ponto_id)
    reg["governanca"] = {
        "procedencia": _scalar_ponto(conn, ponto_id, "procedencia"),
        "verificacao_status": _scalar_ponto(conn, ponto_id,
                                            "verificacao_status"),
        "removido_em": _scalar_ponto(conn, ponto_id, "removido_em"),
        "removido_por": _scalar_ponto(conn, ponto_id, "removido_por"),
        "motivo_remocao": _scalar_ponto(conn, ponto_id, "motivo_remocao"),
    }
    reg["correspondencias"] = correspondencias_do_ponto(conn, ponto_id)
    return reg


def _scalar_ponto(conn, ponto_id, coluna):
    try:
        return dbmod.scalar(conn, "SELECT %s FROM PONTO_FISCALIZACAO WHERE id=?"
                           % coluna, (ponto_id,))
    except sqlite3.OperationalError:
        return None


# ---------------------------------------------------------------------------
# Gestao — escrita
# ---------------------------------------------------------------------------
def _existe_ponto(conn, ponto_id):
    return conn.execute("SELECT 1 FROM PONTO_FISCALIZACAO WHERE id=?",
                        (ponto_id,)).fetchone() is not None


def editar_radar(conn, ponto_id, campos, ctx, ip=None):
    """Edita campos permitidos do ponto; registra diff em RADAR_ALTERACAO."""
    garantir_esquema(conn)
    if not _existe_ponto(conn, ponto_id):
        raise GovernancaError(404, "ponto_nao_encontrado",
                              "ponto P-%d nao encontrado" % ponto_id)
    from coletor.fontes import normalizacao as nz
    campos = campos or {}
    antes, depois = {}, {}

    sets_ponto = {}
    if "observacoes" in campos:
        sets_ponto["observacoes"] = campos["observacoes"]
    if "km" in campos:
        sets_ponto["km"] = nz.to_float(campos["km"])
    if "tipo_pista" in campos:
        sets_ponto["tipo_pista"] = campos["tipo_pista"]
    if any(k in campos for k in ("uf", "municipio", "municipio_nome",
                                 "municipio_ibge", "codigo_ibge")):
        lat = nz.to_float(campos.get("latitude"))
        lon = nz.to_float(campos.get("longitude"))
        uf, mun = nz.resolver_uf_municipio(
            conn, campos.get("uf"), campos.get("municipio")
            or campos.get("municipio_nome"),
            campos.get("municipio_ibge") or campos.get("codigo_ibge"),
            latitude=lat, longitude=lon)
        sets_ponto["municipio_id"] = mun
    if any(k in campos for k in ("via", "via_codigo", "rodovia")):
        vid = nz.obter_via(conn, campos.get("via") or campos.get("via_codigo")
                           or campos.get("rodovia"), campos.get("via_tipo"))
        sets_ponto["via_id"] = vid
    if "situacao" in campos and campos["situacao"]:
        sets_ponto["situacao_operacional_id"] = dbmod.domain_id(
            conn, "SITUACAO_OPERACIONAL", campos["situacao"])

    if sets_ponto:
        _snapshot(conn, ponto_id, antes)
        sets = ", ".join("%s=?" % k for k in sets_ponto)
        conn.execute("UPDATE PONTO_FISCALIZACAO SET %s WHERE id=?" % sets,
                     list(sets_ponto.values()) + [ponto_id])
        depois.update(sets_ponto)

    # coordenada -> POSICAO_GEOGRAFICA (cria se faltar)
    if "latitude" in campos or "longitude" in campos:
        lat = nz.to_float(campos.get("latitude"))
        lon = nz.to_float(campos.get("longitude"))
        if lat is None or lon is None:
            raise GovernancaError(422, "coordenada_invalida",
                                  "informe latitude E longitude juntas")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise GovernancaError(422, "coordenada_invalida",
                                  "lat -90..90 e lon -180..180")
        pid_pos = dbmod.scalar(conn,
                               "SELECT posicao_id FROM PONTO_FISCALIZACAO "
                               "WHERE id=?", (ponto_id,))
        if pid_pos is None:
            pos_id = dbmod.insert(conn, "POSICAO_GEOGRAFICA", {
                "latitude": lat, "longitude": lon,
                "qualidade_posicao_id": dbmod.domain_id(
                    conn, "QUALIDADE_POSICAO", "colaborativa"),
                "precisao_metros": nz.to_float(
                    campos.get("precisao_metros"))})
            conn.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=? "
                         "WHERE id=?", (pos_id, ponto_id))
        else:
            conn.execute("UPDATE POSICAO_GEOGRAFICA SET latitude=?, "
                         "longitude=? WHERE id=?", (lat, lon, pid_pos))
        depois["latitude"], depois["longitude"] = lat, lon

    # velocidades -> LIMITE_VELOCIDADE (escopo geral, no proprio ponto)
    for chave, categoria in (("velocidade_geral", "geral"),
                             ("velocidade_leves", "leves"),
                             ("velocidade_pesados", "pesados")):
        if chave not in campos:
            continue
        val = nz.to_velocidade(campos[chave])
        if val is not None and not (0 < val <= 350):
            raise GovernancaError(422, "velocidade_invalida",
                                  "%s fora de 0..350" % chave, campo=chave)
        cat_id = dbmod.domain_id(conn, "CATEGORIA_VEICULO", categoria)
        row = conn.execute(
            "SELECT id FROM LIMITE_VELOCIDADE WHERE ponto_id=? AND "
            "categoria_veiculo_id=?", (ponto_id, cat_id)).fetchone()
        if row is not None:
            conn.execute("UPDATE LIMITE_VELOCIDADE SET velocidade_kmh=? "
                         "WHERE id=?", (val, row["id"]))
        elif val is not None:
            dbmod.insert(conn, "LIMITE_VELOCIDADE", {
                "ponto_id": ponto_id, "categoria_veiculo_id": cat_id,
                "velocidade_kmh": val})
        depois[chave] = val

    if not depois:
        raise GovernancaError(422, "nada_a_editar",
                              "nenhum campo reconhecido para editar")
    conn.commit()
    registrar_alteracao(conn, ponto_id, ctx, "editado", motivo=None,
                        campos={"antes": antes, "depois": depois}, ip=ip)
    return depois


def _snapshot(conn, ponto_id, destino):
    row = conn.execute(
        "SELECT km, tipo_pista, observacoes, municipio_id, via_id, "
        "situacao_operacional_id FROM PONTO_FISCALIZACAO WHERE id=?",
        (ponto_id,)).fetchone()
    if row is not None:
        destino.update(dict(row))


def verificar_radar(conn, ponto_id, ctx, motivo=None, ip=None):
    garantir_esquema(conn)
    if not _existe_ponto(conn, ponto_id):
        raise GovernancaError(404, "ponto_nao_encontrado",
                              "ponto P-%d nao encontrado" % ponto_id)
    conn.execute("UPDATE PONTO_FISCALIZACAO SET verificacao_status='verificado' "
                 "WHERE id=?", (ponto_id,))
    conn.commit()
    registrar_alteracao(conn, ponto_id, ctx, "verificado", motivo=motivo,
                        ip=ip)


def desabilitar_radar(conn, ponto_id, ctx, motivo, ip=None):
    garantir_esquema(conn)
    if not (motivo or "").strip():
        raise GovernancaError(422, "motivo_obrigatorio",
                              "informe o motivo", campo="motivo")
    if not _existe_ponto(conn, ponto_id):
        raise GovernancaError(404, "ponto_nao_encontrado",
                              "ponto P-%d nao encontrado" % ponto_id)
    conn.execute(
        "UPDATE PONTO_FISCALIZACAO SET verificacao_status='desabilitado' "
        "WHERE id=?", (ponto_id,))
    conn.commit()
    registrar_alteracao(conn, ponto_id, ctx, "desabilitado", motivo=motivo,
                        ip=ip)


def remover_radar(conn, ponto_id, ctx, motivo, ip=None):
    """Tombstone: marca removido_em/motivo; NUNCA apaga a linha."""
    garantir_esquema(conn)
    if not (motivo or "").strip():
        raise GovernancaError(422, "motivo_obrigatorio",
                              "informe o motivo da remocao", campo="motivo")
    if not _existe_ponto(conn, ponto_id):
        raise GovernancaError(404, "ponto_nao_encontrado",
                              "ponto P-%d nao encontrado" % ponto_id)
    rotulo = (ctx or {}).get("rotulo") or "sistema"
    conn.execute(
        "UPDATE PONTO_FISCALIZACAO SET removido_em=?, removido_por=?, "
        "motivo_remocao=? WHERE id=?", (_agora(), rotulo, motivo, ponto_id))
    conn.commit()
    registrar_alteracao(conn, ponto_id, ctx, "removido", motivo=motivo,
                        ip=ip)


##-- BUNDITA DE URSO #{8} -- Substituir o oficial exige decisao de moderacao fundamentada. ##
def resolver_correspondencia(conn, correspondencia_id, status, ctx, motivo=None):
    """Resolve o vinculo (oficial_vence|colaborativo_vence)."""
    if status not in ("oficial_vence", "colaborativo_vence"):
        raise GovernancaError(422, "status_invalido",
                              "status deve ser oficial_vence ou "
                              "colaborativo_vence")
    row = conn.execute("SELECT * FROM CORRESPONDENCIA_PONTO WHERE id=?",
                       (correspondencia_id,)).fetchone()
    if row is None:
        raise GovernancaError(404, "correspondencia_nao_encontrada",
                              "correspondencia %s nao encontrada"
                              % correspondencia_id)
    if status == "colaborativo_vence" and not (motivo or "").strip():
        raise GovernancaError(422, "motivo_obrigatorio",
                              "fundamente a substituicao do ponto oficial", campo="motivo")
    conn.execute("UPDATE CORRESPONDENCIA_PONTO SET status=?, resolvido_por=?, "
                 "resolvido_em=?, motivo=? WHERE id=?",
                 (status, (ctx or {}).get("rotulo"), _agora(), motivo,
                  correspondencia_id))
    conn.commit()
    if status == "colaborativo_vence":
        verificar_radar(conn, row["ponto_colaborativo_id"], ctx, motivo=motivo)
    if status == "oficial_vence":
        remover_radar(conn, row["ponto_colaborativo_id"], ctx,
                      motivo=motivo or "oficial vence a correspondencia")


# ---------------------------------------------------------------------------
# Usuarios/tokens via API de gestao
# ---------------------------------------------------------------------------
def criar_usuario_api(conn, dados, ctx):
    senha = dados.get("senha")
    temporaria = False
    if not senha:
        senha = gerar_senha_temporaria()
        temporaria = True
    uid = criar_usuario(
        conn, dados.get("login"), senha, nome=dados.get("nome"),
        email=dados.get("email"), papel=dados.get("papel") or "moderador",
        deve_trocar_senha=True if (temporaria or dados.get(
            "deve_trocar_senha")) else False)
    resposta = {"id": uid, "login": dados.get("login")}
    if temporaria:
        resposta["senha_temporaria"] = senha
    return resposta


# ---------------------------------------------------------------------------
# Estado do radar na CONSULTA publica (preferir colaborativo; esconder
# removidos/desabilitados). Usado por core.consultas.
# ---------------------------------------------------------------------------
##-- BUNDITA DE URSO #{8} -- Correspondencia automatica estava ocultando o ponto oficial sem revisao. ##
def clausulas_consulta(conn):
    """Clausulas SQL que escondem removidos/desabilitados e o oficial
    'perdedor' quando ha um colaborativo ativo correspondente.

    Devolve (clausulas, params) seguros: se a camada de governanca ainda nao
    existe na base (esquema antigo), devolve ([], []).
    """
    cols = colunas_ponto_governanca(conn)
    if not {"procedencia", "verificacao_status", "removido_em"} <= cols:
        return [], []
    clausulas = ["(p.removido_em IS NULL)",
                 "(p.verificacao_status IS NULL OR "
                 "p.verificacao_status <> 'desabilitado')"]
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='CORRESPONDENCIA_PONTO'").fetchone() is not None:
        clausulas.append(
            "p.id NOT IN (SELECT cp.ponto_oficial_id FROM "
            "CORRESPONDENCIA_PONTO cp JOIN PONTO_FISCALIZACAO c ON "
            "c.id=cp.ponto_colaborativo_id WHERE "
            "cp.status='colaborativo_vence' AND cp.resolvido_em IS NOT NULL AND "
            "c.verificacao_status='verificado' AND "
            "c.removido_em IS NULL AND "
            "(c.verificacao_status IS NULL OR "
            "c.verificacao_status <> 'desabilitado'))")
    return clausulas, []
