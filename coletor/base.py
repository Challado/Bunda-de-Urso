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
import sqlite3
import time
import traceback

from core import config
from core import db as dbmod
from core import atualizacoes


def agora_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def _chave_identidade(d):
    """Chave de identidade externa de um dict normalizado, ou None.

    (tipo_identificador, valor_normalizado) — a MESMA chave que o upsert usa
    para resolver o ponto (fonte_id entra em separado). Registro sem
    identificador devolve None (nao ha identidade a comparar).
    """
    ident = d.get("identificador")
    if ident in (None, ""):
        return None
    return (str(d.get("tipo_identificador") or "id_orgao"),
            str(ident).strip().upper())


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
        self._diario_coleta = {"execucao_id": exec_id, "recurso_id": recurso_id,
                              "pid": os.getpid(),
                              "fonte": self.FONTE["nome"], "recurso": self.RECURSO["nome"],
                              "iniciado_em": agora_utc(), "estado": "em_andamento", "erros_validacao": []}
        self._diario_coleta["arquivo_relatorio"] = str(os.path.join(
            config.caminhos.data_dir(), "atualizacoes", "coleta-" + str(exec_id) + ".json"))
        self._inicio_coleta = time.monotonic()
        atualizacoes.registrar("coleta", self._diario_coleta, fonte=recurso_id, historico="coleta-" + str(exec_id))
        return exec_id

    def encerrar_execucao(self, exec_id, status, artefato_id=None,
                          **contadores):
        campos = {"terminada_em": agora_utc(), "status": status}
        for k in ("linhas_recebidas", "linhas_validas", "linhas_rejeitadas",
                  "registros_criados", "registros_alterados", "http_status",
                  "erro_codigo", "erro_detalhe"):
            if k in contadores:
                campos[k] = contadores[k]
        sets = ", ".join("%s=?" % k for k in campos)
        if artefato_id is not None:
            recurso = dbmod.scalar(self.conn, "SELECT recurso_id FROM EXECUCAO_COLETA WHERE id=?", (exec_id,))
            if recurso != dbmod.scalar(self.conn, "SELECT recurso_id FROM ARTEFATO_COLETA WHERE id=?", (artefato_id,)):
                raise ValueError("artefato pertence a outro recurso")
            self.conn.execute("INSERT INTO EXECUCAO_ARTEFATO (execucao_id, artefato_id) VALUES (?,?) "
                              "ON CONFLICT(execucao_id) DO UPDATE SET artefato_id=excluded.artefato_id",
                              (exec_id, artefato_id))
        self.conn.execute("UPDATE EXECUCAO_COLETA SET %s WHERE id=?" % sets,
                          list(campos.values()) + [exec_id])
        self.conn.commit()
        diario = getattr(self, "_diario_coleta", {})
        atualizacoes.registrar("coleta", {
            **diario, "execucao_id": exec_id, "estado": status,
            "terminado_em": agora_utc(), "artefato_id": artefato_id,
            "duracao_s": round(time.monotonic() - getattr(self, "_inicio_coleta", time.monotonic()), 3),
            "contadores": contadores,
        }, fonte=diario.get("recurso_id", self.RECURSO["nome"]), historico="coleta-" + str(exec_id))

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
        ##-- BUNDITA DE URSO #{9} -- Conteudo de uma tentativa rejeitada precisa poder ser reprocessado. ##
        if not dbmod.scalar(self.conn, "SELECT 1 FROM EXECUCAO_COLETA_DETALHE "
                            "WHERE artefato_id=? AND status='ok' LIMIT 1", (row["id"],)):
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
            if recurso_id != dbmod.scalar(self.conn, "SELECT recurso_id FROM ARTEFATO_COLETA WHERE id=?", (artefato_id,)):
                raise ValueError("artefato pertence a outro recurso")
            self.conn.execute(
                "INSERT OR IGNORE INTO SNAPSHOT_RECURSO "
                "(snapshot_id, artefato_id) VALUES (?,?)", (snap_id, artefato_id))
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
    ##-- BUNDITA DE URSO #{9} -- Rejeicoes perdiam a causa e falhas do programa eram publicadas como sucesso. ##
    def _rejeitar(self, registro_id, exec_id, codigo, descricao):
        if hasattr(self, "_diario_coleta"):
            self._diario_coleta["erros_validacao"].append({
                "registro_id": registro_id, "execucao_id": exec_id, "codigo": codigo, "descricao": descricao})
        self.conn.execute("UPDATE REGISTRO_FONTE SET status_validacao='rejeitado' WHERE id=?",
                          (registro_id,))
        dbmod.insert(self.conn, "ERRO_VALIDACAO", {
            "registro_id": registro_id, "execucao_id": exec_id,
            "codigo_erro": codigo, "descricao": descricao[:500],
            "severidade": "erro", "registrado_em": agora_utc()})

    def _ingerir_registros(self, conteudo, ext, mime, registros, exec_id,
                           recurso_id, publicar=True, fonte_id=None):
        """Ingere uma lista de registros ja parseados (nucleo reutilizavel).

        E o MESMO caminho usado pela coleta e pela API de escrita: artefato
        imutavel -> REGISTRO_FONTE -> normalizar -> upsert (inserir_normalizado).
        Retorna o resumo com contadores ``criados``/``atualizados``/``rejeitados``.
        """
        ##-- BUNDITA DE URSO #{9} -- Registrar rejeicoes de dados e deixar falhas inesperadas abortarem a transacao. ##
        from coletor.fontes import normalizacao as nz  # noqa: F401
        artefato_id, h, caminho = self.registrar_artefato(
            recurso_id, conteudo, ext, mime)
        criados = 0
        atualizados = 0
        rejeitados = 0
        ignorados = 0
        detalhes = []       # por registro aceito: indice/registro/ponto
        pendentes = []      # (idx, reg_id, d) normalizados, ainda nao inseridos
        for idx, raw in enumerate(registros):
            reg_id = self.registrar_registro(
                artefato_id, idx, self.identificador(raw), raw)
            # idempotencia: mesmo artefato (hash) ja ligado a um ponto
            # significa que esta versao ja foi ingerida -> pular.
            if dbmod.query_one(
                    self.conn,
                    "SELECT 1 AS x FROM VINCULO_REGISTRO_PONTO "
                    "WHERE registro_id=? LIMIT 1", (reg_id,)) is not None:
                ignorados += 1
                continue
            if dbmod.query_one(
                    self.conn,
                    "SELECT 1 AS x FROM TRECHO_ELEGIVEL "
                    "WHERE registro_fonte_id=? LIMIT 1",
                    (reg_id,)) is not None:
                ignorados += 1
                continue
            try:
                d = self.normalizar(idx, raw)
            except ValueError as exc:
                self._rejeitar(reg_id, exec_id, type(exc).__name__, str(exc))
                rejeitados += 1
                continue
            if d is None:
                self._rejeitar(reg_id, exec_id, "registro_nao_normalizavel",
                               "O conector nao reconheceu um registro valido nesta entrada")
                rejeitados += 1
                continue
            pendentes.append((idx, reg_id, d))
        # Identificador que se REPETE no mesmo artefato designa pontos
        # DIFERENTES (endereco generico, codigo de rota): nao e identidade de
        # UM ponto. Nesses casos o registro ganha ponto proprio (comportamento
        # de fonte sem identificador confiavel) e o valor fica so como
        # evidencia — assim como nos casos em que o (fonte, tipo, valor) ja
        # aponta para mais de um ponto de coletas anteriores.
        ambiguos = self._identidades_ambiguas(pendentes)
        for idx, reg_id, d in pendentes:
            # um registro ruim nao pode derrubar a fonte inteira:
            # cada registro entra num savepoint proprio.
            self.conn.execute("SAVEPOINT reg")
            try:
                if d.get("tipo_registro") == "trecho_elegivel":
                    nz.inserir_trecho(self.conn, reg_id, d, fonte_id)
                    criados += 1
                    detalhes.append({"indice": idx, "registro_id": reg_id,
                                     "ponto_id": None,
                                     "ponto_criado": False,
                                     "trecho": True})
                else:
                    chave = _chave_identidade(d)
                    res = nz.inserir_normalizado(
                        self.conn, reg_id, d, fonte_id,
                        reutilizar_identidade=(chave is None
                                               or chave not in ambiguos))
                    if res.get("ponto_criado"):
                        criados += 1
                    else:
                        atualizados += 1
                    detalhes.append({"indice": idx, "registro_id": reg_id,
                                     "ponto_id": res.get("ponto_id"),
                                     "ponto_criado": bool(
                                         res.get("ponto_criado"))})
            except (ValueError, sqlite3.IntegrityError) as exc:
                self.conn.execute("ROLLBACK TO reg")
                self.conn.execute("RELEASE reg")
                self._rejeitar(reg_id, exec_id, type(exc).__name__, str(exc))
                rejeitados += 1
                continue
            self.conn.execute("RELEASE reg")
            self.conn.execute("UPDATE REGISTRO_FONTE SET status_validacao='ok' WHERE id=?", (reg_id,))
        snap_id = None
        versao = None
        status = ("erro" if registros and rejeitados == len(registros)
                  else "sem_mudanca" if ignorados == len(registros) and registros
                  else "sem_dados" if not registros else "ok")
        # Publicacao e dados normalizados compartilham a mesma transacao.
        # Um lote vazio/rejeitado nao atesta atualidade nem substitui o snapshot bom.
        if publicar and status == "ok":
            snap_id, versao = self.publicar_snapshot(
                [(recurso_id, artefato_id)],
                resumo="%d criados, %d atualizados" % (criados, atualizados))
        else:
            self.conn.commit()
        return {
            "status": status,
            "fonte": self.FONTE["nome"],
            "recurso_id": recurso_id, "artefato_id": artefato_id,
            "execucao_id": exec_id, "snapshot_id": snap_id,
            "versao": versao, "hash_sha256": h, "cache": caminho,
            "linhas_recebidas": len(registros),
            "criados": criados, "atualizados": atualizados,
            "rejeitados": rejeitados,
            "ignorados": ignorados,
            "detalhes": detalhes,
        }

    @staticmethod
    def _identidades_ambiguas(pendentes):
        """Chaves (tipo, valor) que aparecem em >1 registro do MESMO artefato.

        Sao identidades AMBIGUAS: o mesmo valor descreve pontos diferentes.
        """
        from collections import Counter
        contagem = Counter(_chave_identidade(d) for _, _, d in pendentes)
        return {k for k, n in contagem.items() if k is not None and n > 1}

    def sincronizar(self, origem, publicar=True):
        """Executa o pipeline completo para uma origem (arquivo local ou URL).

        Fluxo atomico: tudo entra numa transacao; o snapshot so e publicado
        se nao houver erro. Retorna um resumo com contadores.
        """
        config.ensure_dirs()
        dbmod.init_db(self.conn)
        fonte_id, recurso_id = self.garantir_referencias()
        exec_id = self.iniciar_execucao(recurso_id)
        try:
            self._diario_coleta.update(etapa="download_e_leitura", origem=origem)
            atualizacoes.registrar("coleta", self._diario_coleta, fonte=recurso_id)
            conteudo, ext, mime, registros = self.carregar(origem)
            self._diario_coleta.update(etapa="normalizacao", recebidos=len(registros), bytes=len(conteudo),
                                      hash_sha256=sha256_bytes(conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo))
            atualizacoes.registrar("coleta", self._diario_coleta, fonte=recurso_id)
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
                    "criados": 0, "atualizados": 0, "rejeitados": 0,
                }
            resumo = self._ingerir_registros(
                conteudo, ext, mime, registros, exec_id, recurso_id,
                publicar=publicar, fonte_id=fonte_id)
            ##-- BUNDITA DE URSO #{9} -- Persistir o resultado real do lote, em vez de declarar sucesso incondicional. ##
            self.encerrar_execucao(
                exec_id, resumo["status"], artefato_id=resumo["artefato_id"],
                erro_codigo="lote_sem_registros_validos" if resumo["status"] == "erro" else None,
                linhas_recebidas=resumo["linhas_recebidas"],
                linhas_validas=resumo["criados"] + resumo["atualizados"],
                linhas_rejeitadas=resumo["rejeitados"],
                registros_criados=resumo["criados"],
                registros_alterados=resumo["atualizados"],
                http_status=200)
            return resumo
        except Exception as exc:   # noqa: BLE001
            self.conn.rollback()
            try:
                self.encerrar_execucao(
                    exec_id, "erro", erro_codigo=type(exc).__name__,
                    erro_detalhe=str(exc)[:500], erro_completo=str(exc), traceback=traceback.format_exc())
            except Exception:      # pragma: no cover
                pass
            raise

    def ingerir_registros(self, registros, conteudo=None, ext=".json",
                          mime="application/json", publicar=False):
        """Ingere registros JA normalizaveis (usado pela API de escrita).

        Abre uma EXECUCAO_COLETA para o recurso da fonte, roda o MESMO
        pipeline do coletor (upsert idempotente) e encerra com os contadores.
        """
        import json as _json
        config.ensure_dirs()
        dbmod.init_db(self.conn)
        fonte_id, recurso_id = self.garantir_referencias()
        exec_id = self.iniciar_execucao(recurso_id)
        if conteudo is None:
            conteudo = _json.dumps(registros, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8")
        try:
            resumo = self._ingerir_registros(
                conteudo, ext, mime, registros, exec_id, recurso_id,
                publicar=publicar, fonte_id=fonte_id)
            ##-- BUNDITA DE URSO #{9} -- Persistir o resultado real do lote, em vez de declarar sucesso incondicional. ##
            self.encerrar_execucao(
                exec_id, resumo["status"], artefato_id=resumo["artefato_id"],
                erro_codigo="lote_sem_registros_validos" if resumo["status"] == "erro" else None,
                linhas_recebidas=resumo["linhas_recebidas"],
                linhas_validas=resumo["criados"] + resumo["atualizados"],
                linhas_rejeitadas=resumo["rejeitados"],
                registros_criados=resumo["criados"],
                registros_alterados=resumo["atualizados"],
                http_status=200)
            return resumo
        except Exception as exc:   # noqa: BLE001
            self.conn.rollback()
            try:
                self.encerrar_execucao(
                    exec_id, "erro", erro_codigo=type(exc).__name__,
                    erro_detalhe=str(exc)[:500], erro_completo=str(exc), traceback=traceback.format_exc())
            except Exception:      # pragma: no cover
                pass
            raise
