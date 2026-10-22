"""Diario operacional local, sem consultar banco e sem alterar resultados.

O JSON consolida o ultimo estado de cada operacao/recurso. O JSONL rotacionado
guarda os eventos, saidas de comandos e erros completos. Instalacoes tambem
ganham um relatorio individual fora da arvore substituida do aplicativo.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import datetime
import fcntl
import grp
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import traceback
import uuid

from . import caminhos

_ATIVO = ContextVar("registro_atualizacao", default=None)


def agora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def limpar(valor):
    """Nao persistir credenciais em mensagens, URLs ou estruturas retornadas."""
    if isinstance(valor, bytes):
        return limpar(valor.decode("utf-8", errors="replace"))
    if isinstance(valor, dict):
        return {str(k): "[oculto]" if re.search(
            r"(?i)(senha|password|secret|token|authorization|api[_-]?key|user_content_key|signature|chave)", str(k))
                else limpar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [limpar(v) for v in valor]
    if isinstance(valor, str):
        valor = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[oculto]@", valor)
        valor = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\r\n]+", r"\1[oculto]", valor)
        return re.sub(r"(?i)((?:password|senha|secret|token|api[_-]?key|user_content_key|signature|chave)\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}\r\n]+",
                      r"\1[oculto]", valor)
    return valor if valor is None or isinstance(valor, (int, float, bool)) else str(valor)


def _atomico(arquivo, dados):
    fd, tmp = tempfile.mkstemp(prefix=".status-", dir=arquivo.parent)
    try:
        with os.fdopen(fd, "w") as saida:
            os.fchmod(saida.fileno(), 0o660)
            json.dump(dados, saida, ensure_ascii=False, indent=2)
            saida.write("\n")
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(tmp, arquivo)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _marcar_interrompidos(estado, pasta):
    for grupo in ("operacoes", "fontes"):
        for anterior in estado.get(grupo, {}).values():
            if anterior.get("estado") != "em_andamento" or not isinstance(anterior.get("pid"), int) or anterior["pid"] <= 0:
                continue
            try:
                os.kill(anterior["pid"], 0)
            except ProcessLookupError:
                anterior.update(estado="interrompido", detectado_em=agora(),
                                erro="Processo terminou sem registrar a conclusao; verificar log e backup antes de reaplicar.")
                nome = ("coleta-" + str(anterior["execucao_id"])) if grupo == "fontes" and "execucao_id" in anterior else (
                    anterior.get("operacao", "operacao") + "-" + str(anterior.get("id", "desconhecido")))
                _atomico(pasta / (re.sub(r"[^A-Za-z0-9_-]", "_", nome) + ".json"), anterior)
            except PermissionError:
                pass


def registrar(operacao, dados, *, fonte=None, historico=None, recursos=None):
    """Lock+rename impedem perder outras fontes ou publicar JSON pela metade.

    Sem radar.conf, desenvolvimento/testes continuam sem arquivos operacionais.
    Falha no diario e visivel no stderr; nunca desfaz uma coleta confirmada.
    """
    if not Path(caminhos.conf_path()).is_file():
        return
    try:
        arquivo = Path(caminhos.status_atualizacoes())
        if not arquivo.parent.exists():
            arquivo.parent.mkdir(parents=True, exist_ok=True, mode=0o2770)
            arquivo.parent.chmod(0o2770)
            if os.geteuid() == 0:
                os.chown(arquivo.parent, -1, grp.getgrnam(caminhos.valor("instalacao", "grupo", "www-data")[0]).gr_gid)
        log = Path(caminhos.log_atualizacoes())
        log.parent.mkdir(parents=True, exist_ok=True)
        evento = limpar({"quando": agora(), "operacao": operacao, **dados})
        with open(arquivo.parent / "status.lock", "a") as trava:
            if os.fstat(trava.fileno()).st_uid == os.geteuid():
                os.fchmod(trava.fileno(), 0o660)
            fcntl.flock(trava, fcntl.LOCK_EX)
            try:
                estado = json.loads(arquivo.read_text()) if arquivo.exists() else {
                    "versao_esquema": 1, "operacoes": {}, "fontes": {}}
                if not isinstance(estado, dict) or any(
                        not isinstance(estado.get(k, {}), dict) or any(not isinstance(v, dict) for v in estado.get(k, {}).values())
                        for k in ("operacoes", "fontes")):
                    raise ValueError("Estrutura invalida do status")
            except (ValueError, UnicodeError) as exc:
                preservado = arquivo.with_name("status-corrompido-" + uuid.uuid4().hex + ".json")
                arquivo.rename(preservado)
                estado = {"versao_esquema": 1, "operacoes": {}, "fontes": {},
                          "erro_status_anterior": {"erro": str(exc), "arquivo_preservado": str(preservado)}}
            estado["atualizado_em"] = evento["quando"]
            _marcar_interrompidos(estado, arquivo.parent)
            estado["log"] = str(log)
            if fonte is not None:
                estado.setdefault("fontes", {})[str(fonte)] = evento
            else:
                estado.setdefault("operacoes", {})[operacao] = evento
            for recurso in recursos or ():
                novo = limpar(recurso)
                chave = str(novo["recurso_id"])
                anterior = estado.setdefault("fontes", {}).get(chave, {})
                # O banco completa o historico anterior a este diario. Nao
                # substitui traceback/bytes/origem de uma execucao ja detalhada.
                if anterior.get("execucao_id") == novo.get("execucao_id") and anterior:
                    novo = {**novo, **anterior, "agenda": novo.get("agenda", {})}
                estado["fontes"][chave] = novo
            estado["resumo"] = {
                "operacoes_com_erro": [k for k, v in estado.get("operacoes", {}).items() if v.get("estado") in ("erro", "interrompido")],
                "fontes_com_erro": [k for k, v in estado.get("fontes", {}).items() if v.get("estado") in ("erro", "interrompido")],
                "fontes_em_andamento": [k for k, v in estado.get("fontes", {}).items() if v.get("estado") == "em_andamento"],
                "total_recursos_acompanhados": len(estado.get("fontes", {})),
                "recursos_nunca_coletados": [k for k, v in estado.get("fontes", {}).items() if v.get("estado") == "nunca_coletado"],
                "falhas_atuais": [{"recurso_id": k, "fonte": v.get("fonte"), "recurso": v.get("recurso"),
                                   "estado": v.get("estado"),
                                   "erro_codigo": v.get("contadores", {}).get("erro_codigo"),
                                   "causa": v.get("contadores", {}).get("erro_detalhe") or v.get("erro")}
                                  for k, v in estado.get("fontes", {}).items() if v.get("estado") in ("erro", "interrompido")],
            }
            # O append fica dentro do mesmo lock que protege o resumo.
            with log.open("a") as saida:
                if os.fstat(saida.fileno()).st_uid == os.geteuid():
                    os.fchmod(saida.fileno(), 0o660)
                saida.write(json.dumps(evento, ensure_ascii=False) + "\n")
                saida.flush()
            _atomico(arquivo, estado)
            if historico:
                _atomico(arquivo.parent / (historico + ".json"), evento)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("Observacao: nao foi possivel gravar o diario de atualizacoes: " + str(exc), file=sys.stderr)


def publicar_link():
    """O destino persiste mesmo quando codigo/web sao trocados ou restaurados."""
    link = Path(caminhos.link_atualizacoes())
    if link.parent.is_dir():
        if link.is_symlink() and link.resolve() == Path(caminhos.status_atualizacoes()).resolve():
            return
        if link.exists() or link.is_symlink():
            raise RuntimeError("Arquivo de status ocupado: " + str(link))
        link.symlink_to(caminhos.status_atualizacoes())


class Registro:
    def __init__(self, operacao, **dados):
        self.operacao = operacao
        self.inicio = time.monotonic()
        self.dados = {"id": uuid.uuid4().hex, "pid": os.getpid(),
                      "iniciado_em": agora(), "estado": "em_andamento", "erros": [], **dados}
        self.historico = ("instalacao-" + self.dados["id"]) if operacao == "instalacao" else None
        if self.historico:
            self.dados["etapas"] = []
        self.evento("inicio")

    def evento(self, etapa, **dados):
        item = limpar({"etapa": etapa, "quando": agora(), **dados})
        if dados.get("erro") or (dados.get("codigo_comando", 0) and not dados.get("codigo_esperado", False)):
            self.dados["erros"].append(item)
        for checagem in dados.get("relatorio", {}).get("checagens", []):
            if checagem.get("estado") == "erro":
                self.dados["erros"].append(limpar({"etapa": etapa, "quando": agora(), **checagem}))
        self.dados.update(etapa=etapa, **limpar(dados))
        if self.historico:
            self.dados.setdefault("etapas", []).append(item)
        registrar(self.operacao, self.dados, historico=self.historico)

    def terminar(self, codigo=0, **dados):
        if not self.historico and (self.operacao == "sync" or codigo or self.dados["erros"] or any(
                r.get("acao") in ("executado", "erro") for r in dados.get("resultados", []))):
            self.historico = self.operacao + "-" + self.dados["id"]
        if self.historico:
            self.dados["arquivo_relatorio"] = str(Path(caminhos.status_atualizacoes()).parent / (self.historico + ".json"))
        self.evento("fim", estado="ok" if codigo == 0 else "erro", codigo_saida=codigo,
                    terminado_em=agora(), duracao_s=round(time.monotonic() - self.inicio, 3), **dados)


def evento(etapa, **dados):
    registro = _ATIVO.get()
    if registro:
        registro.evento(etapa, **dados)


@contextmanager
def acompanhar(operacao, **dados):
    registro = Registro(operacao, **dados)
    token = _ATIVO.set(registro)
    try:
        yield registro
    except BaseException as exc:
        codigo = exc.code if isinstance(exc, SystemExit) and isinstance(exc.code, int) else 1
        registro.terminar(codigo, erro=type(exc).__name__ + ": " + str(exc), traceback=traceback.format_exc())
        raise
    finally:
        _ATIVO.reset(token)
