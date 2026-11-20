"""Entrada unica CGI e local. Operacoes locais nunca viram rotas HTTP."""
import importlib
import os
import sys

from .contexto_api import atendimento_local

FERRAMENTAS = frozenset((
    "aplicar_correcoes_municipio", "auditar_coleta", "auditar_deduplicacao",
    "auditar_fontes_estaduais", "auditar_geografia_municipios", "build_schema",
    "espelho_dados", "carregar_municipios_ibge", "carregar_verificacao_metrologica",
    "casar_municipios_fuzzy", "construir_cadastro_municipios", "construir_malha",
    "consultar_nomes_pendentes", "corrigir_coordenadas_brasil", "gerar_calibracao",
    "gerar_correcoes_municipio", "gerar_municipios_site", "limpar_calibracao",
    "listar_duplicidades", "preencher_municipio", "radar_admin", "inicializar_banco", "migrar_postgres",
    "reprocessar_fontes_corrigidas", "recuperar_posicoes_legadas", "validar_georesolver", "reconciliar_equipamentos",
))


def main(argv=None):
    argumentos = list(sys.argv[1:] if argv is None else argv)
    cgi = bool(os.environ.get("GATEWAY_INTERFACE") or os.environ.get("REQUEST_METHOD"))
    # O instalador coordena a publicação com instalacao.lock. A ferramenta de
    # migração pausa a API depois de confirmar as credenciais do destino.
    if not cgi and (argumentos[:1] == ["instalacao"] or
                    argumentos[:2] == ["ferramenta", "migrar_postgres"]):
        return _local(argumentos)

    from . import operacoes

    try:
        with operacoes.acompanhar():
            if cgi:
                from web.nucleo import main as atender
                return atender()
            return _local(argumentos)
    except operacoes.OperacoesPausadas as exc:
        if cgi:
            from web.nucleo import _emitir, _erro
            status, headers, corpo = _erro(503, "manutencao", str(exc))
            _emitir(status, {**headers, "Retry-After": "30", "Cache-Control": "no-store"}, corpo)
            return 0
        if argumentos[:1] == ["cron"]:
            return 0
        print(str(exc), file=sys.stderr)
        return 75


def _local(argumentos):
    with atendimento_local():
        if argumentos[:1] == ["fila"]:
            from .fila_cadastros import main as fila
            return fila(argumentos[1:])
        if argumentos[:1] == ["assistente"]:
            from .assistencia import main as assistir
            return assistir(argumentos[1:])
        if argumentos[:1] == ["instalacao"]:
            from . import caminhos
            with caminhos.migracao_local():
                from .instalacao import main as instalar
                return instalar(argumentos[1:])
        if argumentos[:1] == ["configuracao"]:
            from .configuracao import main as configurar
            return configurar(argumentos[1:])
        if argumentos[:1] == ["cron"]:
            if argumentos[1:2] not in (["tick"], ["fila"], ["traseiro"], ["dump"]):
                print("Operacao de cron desconhecida.", file=sys.stderr)
                return 2
            from . import caminhos
            os.makedirs(caminhos.log_dir(), exist_ok=True)
            with open(os.path.join(caminhos.log_dir(), argumentos[1] + ".log"), "a") as log:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
                argumentos = (["fila", "processar"] if argumentos[1] == "fila" else
                              ["traseiro", "sincronizar"] if argumentos[1] == "traseiro" else argumentos[1:])
        if argumentos == ["dump"]:
            from .dump_radares import main as gerar_dump
            return gerar_dump()
        if argumentos[:1] == ["traseiro"]:
            from .traseiro_console import main as traseiro
            return traseiro(argumentos[1:])
        if argumentos[:1] == ["fila"]:
            from .fila_cadastros import main as fila
            return fila(argumentos[1:])
        if argumentos and argumentos[0] in ("sync", "tick"):
            modulo = importlib.import_module("coletor." + argumentos[0])
            return modulo._main_servico(argumentos[1:])
        if argumentos and argumentos[0] == "ferramenta":
            if len(argumentos) < 2 or argumentos[1] not in FERRAMENTAS:
                print("Ferramenta desconhecida. Use uma das operacoes registradas.", file=sys.stderr)
                return 2
            modulo = importlib.import_module("core.manutencao." + argumentos[1])
            return modulo.main(argumentos[2:])
        if argumentos and argumentos[0] == "console":
            argumentos = argumentos[1:]
        from .console_api import main as console
        return console(argumentos)
