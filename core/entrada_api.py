"""Entrada unica CGI e local. Operacoes locais nunca viram rotas HTTP."""
import importlib
import os
import sys

from .contexto_api import atendimento_local

FERRAMENTAS = frozenset((
    "aplicar_correcoes_municipio", "auditar_coleta", "auditar_deduplicacao",
    "auditar_fontes_estaduais", "auditar_geografia_municipios", "build_schema",
    "carregar_municipios_ibge", "carregar_verificacao_metrologica",
    "casar_municipios_fuzzy", "construir_cadastro_municipios", "construir_malha",
    "consultar_nomes_pendentes", "corrigir_coordenadas_brasil", "gerar_calibracao",
    "gerar_correcoes_municipio", "gerar_municipios_site", "limpar_calibracao",
    "listar_duplicidades", "preencher_municipio", "radar_admin", "inicializar_banco",
    "recuperar_posicoes_legadas", "validar_georesolver", "reconciliar_equipamentos",
))


def main(argv=None):
    if os.environ.get("GATEWAY_INTERFACE") or os.environ.get("REQUEST_METHOD"):
        from web.nucleo import main as cgi
        return cgi()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    with atendimento_local():
        if argumentos[:1] == ["fila"]:
            from .fila_cadastros import main as fila
            return fila(argumentos[1:])
        if argumentos[:1] == ["assistente"]:
            from .assistencia import main as assistir
            return assistir(argumentos[1:])
        if argumentos[:1] == ["instalacao"]:
            from .instalacao import main as instalar
            return instalar(argumentos[1:])
        if argumentos[:1] == ["configuracao"]:
            from .configuracao import main as configurar
            return configurar(argumentos[1:])
        if argumentos[:1] == ["cron"]:
            if argumentos[1:2] not in (["tick"], ["fila"]):
                print("Operacao de cron desconhecida.", file=sys.stderr)
                return 2
            from . import caminhos
            os.makedirs(caminhos.log_dir(), exist_ok=True)
            with open(os.path.join(caminhos.log_dir(), argumentos[1] + ".log"), "a") as log:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
                argumentos = (["fila", "processar"] if argumentos[1] == "fila" else argumentos[1:])
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
