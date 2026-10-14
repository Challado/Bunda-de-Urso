# -*- coding: utf-8 -*-
"""Infraestrutura comum aos conectores.

Implementa o fluxo da spec 7/13/17.5:
  descobrir fonte -> baixar/ler bruto -> validar hash -> persistir
  IMUTAVELMENTE (por sha256) -> staging -> deduplicar -> publicar snapshot.

Nada aqui executa em tempo de requisicao da API.
"""
import datetime
import hashlib
import json
import os
import shutil

from core import config
from core import db as dbmod


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def sha256_bytes(dados):
    return hashlib.sha256(dados).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


class CacheImutavel(object):
    """Cache de arquivos brutos por sha256 (uma copia por conteudo)."""

    def __init__(self, base_dir=None):
        self.base = base_dir or config.RAW_DIR
        os.makedirs(self.base, exist_ok=True)

    def guardar(self, conteudo, ext):
        h = sha256_bytes(conteudo if isinstance(conteudo, bytes)
                         else conteudo.encode("utf-8"))
        ext = ext if ext.startswith(".") else ("." + ext if ext else "")
        ns = os.path.join(self.base, h[:2])
        os.makedirs(ns, exist_ok=True)
        destino = os.path.join(ns, h + ext)
        if not os.path.exists(destino):
            tmp = destino + ".tmp"
            with open(tmp, "wb") as f:
                f.write(conteudo if isinstance(conteudo, bytes)
                        else conteudo.encode("utf-8"))
            os.replace(tmp, destino)   # publicacao atomica do arquivo
        return destino, h


def publicar_atomico(origem, destino):
    """Publica um arquivo por rename atomico (mesmo filesystem)."""
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    os.replace(origem, destino)


class ColetorBase(object):
    """Classe-base parametrizada por FONTE/RECURSO (dicts canonicos)."""

    FONTE = None      # dict com nome, url_institucional, esfera, natureza, organizacao, tipo_organizacao
    RECURSO = None    # dict com nome, url_recurso, formato_origem, dicionario_url, periodicidade_segundos

    def __init__(self, conn=None, db_path=None):
        self._conn = conn
        self._db_path = db_path
        self.cache = CacheImutavel()

    # -- conexao -----------------------------------------------------------
    @property
    def conn(self):
        if self._conn is None:
            self._conn = dbmod.connect(self._db_path or config.DB_PATH)
        return self._conn

    # -- referencias -------------------------------------------------------
    def garantir_referencias(self):
        conn = self.conn
        org_id = dbmod.upsert_lookup(
            conn, "ORGANIZACAO", ["nome"],
            [self.FONTE["organizacao"]],
            extra={"tipo_organizacao_id": dbmod.domain_id(
                conn, "TIPO_ORGANIZACAO",
                self.FONTE.get("tipo_organizacao", "orgao_publico"))})
        natureza_id = dbmod.domain_id(conn, "NATUREZA_FONTE",
                                      self.FONTE.get("natureza", "oficial"))
        fonte_id = dbmod.upsert_lookup(
            conn, "FONTE", ["nome"], [self.FONTE["nome"]],
            extra={
                "organizacao_id": org_id,
                "natureza_id": natureza_id,
                "url_institucional": self.FONTE.get("url_institucional", ""),
                "esfera": self.FONTE.get("esfera", "desconhecida"),
                "licenca": self.FONTE.get("licenca"),
                "documentacao_url": self.FONTE.get("documentacao_url"),
                "situacao": self.FONTE.get("situacao", "ativa"),
                "periodicidade_declarada": self.FONTE.get("periodicidade_declarada"),
            })
        recurso_id = dbmod.upsert_lookup(
            conn, "RECURSO_FONTE", ["fonte_id", "nome"],
            [fonte_id, self.RECURSO["nome"]],
            extra={
                "url_recurso": self.RECURSO.get("url_recurso", ""),
                "formato_origem": self.RECURSO.get("formato_origem", "json"),
                "dicionario_url": self.RECURSO.get("dicionario_url"),
                "periodicidade_segundos": self.RECURSO.get("periodicidade_segundos"),
                "ativo": 1,
                "status_integracao": self.RECURSO.get("status_integracao", "ok"),
            })
        conn.commit()
        return fonte_id, recurso_id

    # -- artefato / cache --------------------------------------------------
    def registrar_artefato(self, recurso_id, conteudo, ext, mime,
                           data_publicacao_origem=None):
        caminho, h = self.cache.guardar(conteudo, ext)
        row = dbmod.query_one(
            self.conn, "SELECT id FROM ARTEFATO_COLETA WHERE recurso_id=? AND hash_sha256=?",
            (recurso_id, h))
        if row is not None:
            return row["id"], h, caminho
        artefato_id = dbmod.insert(self.conn, "ARTEFATO_COLETA", {
            "recurso_id": recurso_id,
            "hash_sha256": h,
            "caminho_cache": caminho,
            "bytes_arquivo": os.path.getsize(caminho),
            "tipo_mime": mime,
            "data_publicacao_origem": data_publicacao_origem,
            "baixado_em": agora_utc(),
            "validado_em": agora_utc(),
            "resultado_validacao": "ok",
        })
        self.conn.commit()
        return artefato_id, h, caminho

    # -- execucao ----------------------------------------------------------
    def iniciar_execucao(self, recurso_id):
        exec_id = dbmod.insert(self.conn, "EXECUCAO_COLETA", {
            "recurso_id": recurso_id,
            "iniciada_em": agora_utc(),
            "status": "em_andamento",
            "tentativas": 1,
        })
        self.conn.commit()
        return exec_id

    def encerrar_execucao(self, exec_id, status, artefato_id=None,
                          **contadores):
        campos = {"terminada_em": agora_utc(), "status": status,
                  "artefato_id": artefato_id}
        for k in ("linhas_recebidas", "linhas_validas", "linhas_rejeitadas",
                  "registros_criados", "registros_alterados", "http_status",
                  "erro_codigo", "erro_detalhe"):
            if k in contadores:
                campos[k] = contadores[k]
        sets = ", ".join("%s=?" % k for k in campos)
        self.conn.execute("UPDATE EXECUCAO_COLETA SET %s WHERE id=?" % sets,
                          list(campos.values()) + [exec_id])
        self.conn.commit()

    # -- registro bruto ----------------------------------------------------
    def registrar_registro(self, artefato_id, ordem, identificador, payload):
        texto = payload if isinstance(payload, str) else json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"))
        h = sha256_bytes(texto.encode("utf-8"))
        row = dbmod.query_one(
            self.conn, "SELECT id FROM REGISTRO_FONTE WHERE artefato_id=? AND numero_ordem=?",
            (artefato_id, ordem))
        if row is not None:
            return row["id"]
        return dbmod.insert(self.conn, "REGISTRO_FONTE", {
            "artefato_id": artefato_id,
            "numero_ordem": ordem,
            "identificador_na_fonte": identificador,
            "payload_original": texto,
            "hash_registro": h,
            "status_validacao": "ok",
        })

    def _assinatura(self, registros):
        """Assinatura estavel do CONTEUDO dos registros.

        Independe do hash do arquivo bruto: paginas dinamicas (Joomla, etc.)
        mudam token/contador a cada coleta sem mudar um unico radar.
        """
        hs = []
        for raw in registros:
            texto = raw if isinstance(raw, str) else json.dumps(
                raw, ensure_ascii=False, separators=(",", ":"))
            hs.append(sha256_bytes(texto.encode("utf-8")))
        return sha256_bytes("".join(sorted(hs)).encode("utf-8"))

    def _snapshot_repetido(self, recurso_id, registros):
        """True se o conteudo bate com o do ULTIMO artefato COM registros.

        Evita reingerir a mesma tabela quando so mudou token/contador da
        pagina (o hash do arquivo muda e duplicaria todos os registros).
        """
        if not registros:
            return False
        row = dbmod.query_one(
            self.conn, "SELECT id FROM ARTEFATO_COLETA WHERE recurso_id = ? "
                       "ORDER BY id DESC LIMIT 1", (recurso_id,))
        if row is None:
            return False
        hs = [r[0] for r in dbmod.query_all(
            self.conn, "SELECT hash_registro FROM REGISTRO_FONTE "
                       "WHERE artefato_id = ? ORDER BY id", (row["id"],))]
        if not hs:
            return False
        return sha256_bytes("".join(sorted(hs)).encode("utf-8")) == \
            self._assinatura(registros)

    # -- snapshot ----------------------------------------------------------
    def publicar_snapshot(self, pares, resumo="ok", status="publicado"):
        """pares: lista de (recurso_id, artefato_id)."""
        versao = "rb-" + datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ")
        anterior = dbmod.scalar(
            self.conn,
            "SELECT id FROM SNAPSHOT_PUBLICADO WHERE status='publicado' "
            "ORDER BY publicado_em DESC LIMIT 1")
        snap_id = dbmod.insert(self.conn, "SNAPSHOT_PUBLICADO", {
            "anterior_id": anterior,
            "publicado_em": agora_utc(),
            "status": status,
            "resumo_validacao": resumo,
            "identificador_versao": versao,
        })
        for recurso_id, artefato_id in pares:
            self.conn.execute(
                "INSERT OR IGNORE INTO SNAPSHOT_RECURSO "
                "(snapshot_id, recurso_id, artefato_id) VALUES (?,?,?)",
                (snap_id, recurso_id, artefato_id))
        self.conn.commit()
        return snap_id, versao

    # -- a implementar por fonte ------------------------------------------
    def carregar(self, origem):
        raise NotImplementedError

    def normalizar(self, idx, raw):
        raise NotImplementedError

    def identificador(self, raw):
        return None

    # -- orquestracao ------------------------------------------------------
    def sincronizar(self, origem, publicar=True):
        """Executa o pipeline completo para uma origem (arquivo local ou URL).

        Fluxo atomico: tudo entra numa transacao; o snapshot so e publicado
        se nao houver erro. Retorna um resumo com contadores.
        """
        from coletor.fontes import normalizacao as nz  # noqa: F401
        config.ensure_dirs()
        dbmod.init_db(self.conn)
        fonte_id, recurso_id = self.garantir_referencias()
        exec_id = self.iniciar_execucao(recurso_id)
        criados = 0
        rejeitados = 0
        try:
            conteudo, ext, mime, registros = self.carregar(origem)
            # Snapshot repetido nao se reingere (spec 8.1-A / 17.4-3): a
            # pagina pode mudar so em token/contador, o que trocaria o hash
            # do artefato e duplicaria TODOS os registros (DER-MG 10/2026).
            if self._snapshot_repetido(recurso_id, registros):
                self.encerrar_execucao(
                    exec_id, "sem_mudanca", http_status=200,
                    linhas_recebidas=len(registros))
                return {
                    "fonte": self.FONTE["nome"], "recurso_id": recurso_id,
                    "execucao_id": exec_id, "sem_mudanca": True,
                    "linhas_recebidas": len(registros),
                    "criados": 0, "rejeitados": 0,
                }
            artefato_id, h, caminho = self.registrar_artefato(
                recurso_id, conteudo, ext, mime)
            for idx, raw in enumerate(registros):
                reg_id = self.registrar_registro(
                    artefato_id, idx, self.identificador(raw), raw)
                # idempotencia: mesmo artefato (hash) ja ligado a um ponto
                # significa que esta versao ja foi ingerida -> pular.
                if dbmod.query_one(
                        self.conn,
                        "SELECT 1 AS x FROM VINCULO_REGISTRO_PONTO "
                        "WHERE registro_id=? LIMIT 1", (reg_id,)) is not None:
                    continue
                if dbmod.query_one(
                        self.conn,
                        "SELECT 1 AS x FROM TRECHO_ELEGIVEL "
                        "WHERE registro_fonte_id=? LIMIT 1",
                        (reg_id,)) is not None:
                    continue
                d = self.normalizar(idx, raw)
                if d is None:
                    rejeitados += 1
                    continue
                # um registro ruim nao pode derrubar a fonte inteira:
                # cada registro entra num savepoint proprio.
                self.conn.execute("SAVEPOINT reg")
                try:
                    if d.get("tipo_registro") == "trecho_elegivel":
                        nz.inserir_trecho(self.conn, reg_id, d, fonte_id)
                    else:
                        nz.inserir_normalizado(self.conn, reg_id, d, fonte_id)
                except Exception:                       # noqa: BLE001
                    self.conn.execute("ROLLBACK TO reg")
                    self.conn.execute("RELEASE reg")
                    rejeitados += 1
                    continue
                self.conn.execute("RELEASE reg")
                criados += 1
            self.conn.commit()
            snap_id = None
            versao = None
            if publicar:
                snap_id, versao = self.publicar_snapshot(
                    [(recurso_id, artefato_id)],
                    resumo="%d pontos normalizados" % criados)
            self.encerrar_execucao(
                exec_id, "ok", artefato_id=artefato_id,
                linhas_recebidas=len(registros), linhas_validas=criados,
                linhas_rejeitadas=rejeitados, registros_criados=criados,
                http_status=200)
            return {
                "fonte": self.FONTE["nome"],
                "recurso_id": recurso_id, "artefato_id": artefato_id,
                "execucao_id": exec_id, "snapshot_id": snap_id,
                "versao": versao, "hash_sha256": h,
                "cache": caminho, "linhas_recebidas": len(registros),
                "criados": criados, "rejeitados": rejeitados,
            }
        except Exception as exc:   # noqa: BLE001
            self.conn.rollback()
            try:
                self.encerrar_execucao(
                    exec_id, "erro", erro_codigo=type(exc).__name__,
                    erro_detalhe=str(exc)[:500])
            except Exception:      # pragma: no cover
                pass
            raise
