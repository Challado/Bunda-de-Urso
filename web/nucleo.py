# -*- coding: utf-8 -*-
"""Nucleo CGI do Radar Brasil (Python puro, stdlib).

Le os.environ (REQUEST_METHOD, QUERY_STRING, CONTENT_LENGTH, PATH_INFO) e
stdin; emite headers + corpo. NENHUMA chamada a servico externo: consulta
somente o banco local ja validado (spec 13.1).
"""
import datetime
import hmac
import ipaddress
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config
from core import db as dbmod
from core import consultas
from core import painel_status
from core import geo
from core import governanca
from core.serializers import serialize, is_valido, FORMATOS
from core.serializers import campos, txt_ser, json_ser, xml_ser, edifact_ser, dif_ser

_cls_txt = txt_ser

STATUS_REASON = {
    200: "OK", 201: "Created", 202: "Accepted", 400: "Bad Request", 401: "Unauthorized",
    403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
    409: "Conflict", 413: "Payload Too Large", 422: "Unprocessable Entity",
    429: "Too Many Requests", 503: "Service Unavailable",
    500: "Internal Server Error",
}


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


# ---------------------------------------------------------------------------
# AJUDA (gerada da mesma definicao usada no codigo)
# ---------------------------------------------------------------------------
PARAMS = [
    ("lat", "decimal", True, "-90..90", "latitude WGS84 (graus)"),
    ("lon", "decimal", True, "-180..180", "longitude WGS84 (graus)"),
    ("raio", "inteiro", False, config.RAIO_FAIXA_TXT, "raio em metros (padrao 1000; cobre ate 1000 km)"),
    ("formato", "string", False, "|".join(FORMATOS), "json|ndjson|xml|txt|edi|edifact|dif"),
    ("delimitador", "string", False, "1 caractere", "apenas txt; padrao '|'; rejeita CR/LF/NUL/aspas"),
    ("detalhado", "boolean", False, "true|false", "todos os campos disponiveis (padrao true)"),
    ("incluir_inativos", "boolean", False, "true|false", "padrao false"),
    ("incluir_incertos", "boolean", False, "true|false", "padrao true, com indicador"),
    ("incluir_trechos", "boolean", False, "true|false", "colecao separada (padrao false)"),
    ("incluir_operacoes", "boolean", False, "true|false", "padrao true"),
    ("tipo_radar", "string", False, "codigo cadastrado", "fixo|portatil|movel|desconhecido"),
    ("modalidade", "string", False, "codigo cadastrado", "modalidade de fiscalizacao"),
    ("fiscalizacao_pontual", "boolean", False, "true|false", "desconhecido fica fora"),
    ("uf", "string", False, "sigla", "sigla de UF"),
    ("municipio_ibge", "string", False, "7 digitos", "codigo IBGE"),
    ("rodovia", "string", False, "codigo", "codigo de rodovia/via"),
    ("sentido", "string", False, "codigo cadastrado", "sentido"),
    ("em", "datetime", False, "ISO8601", "instante de referencia temporal"),
    ("ponto_id", "string", False, "P-<n>", "filtra /api/v1/trafego por ponto"),
    ("limite", "inteiro", False, "1..1000", "itens por pagina (padrao 100)"),
    ("cursor", "string", False, "opaco", "cursor estavel de paginacao"),
    ("depois", "inteiro", False, ">=0", "ultimo ID numerico exibido no status do estado"),
    ("versao_esquema", "string", False, "string", "versao de contrato"),
]

ENDPOINTS_AJUDA = {
    "/api/v1/status/estados": ["GET"],
    "/api/v1/status/estados/{uf}": ["GET"],
    "/api/v1/status/coletores": ["GET"],
    "/api/v1/radares": ["GET", "POST"],
    "/api/v1/radares/submeter": ["POST"],
    "/api/v1/radares/envios/{protocolo}": ["GET"],
    "/api/v1/radares/busca": ["GET", "POST"],
    "/api/v1/radares/{id}": ["GET"],
    "/api/v1/radares/{id}/historico": ["GET"],
    "/api/v1/trafego": ["GET", "POST"],
    "/api/v1/trechos": ["GET", "POST"],
    "/api/v1/operacoes": ["GET", "POST"],
    "/api/v1/equipamentos/{id}": ["GET"],
    "/api/v1/fontes": ["GET"],
    "/api/v1/fontes/{id}": ["GET"],
    "/api/v1/atualizacoes": ["GET"],
    "/api/v1/atualizacoes/status": ["GET"],
    "/api/v1/login": ["POST"],
    "/api/v1/logout": ["POST"],
    "/api/v1/minha-senha": ["POST"],
    "/api/v1/ajuda": ["GET", "POST"],
    "/api/v1/status": ["GET", "POST"],
    "/health/live": ["GET"],
    "/health/ready": ["GET"],
}

ENDPOINTS_ADMINISTRATIVOS = {
    "/api/v1/gestao/assistente": ["GET", "POST"],
    "/api/v1/gestao/assistente/chave": ["PUT", "DELETE"],
    "/api/v1/gestao/assistente/relatorios/{id}": ["GET"],
    "/api/v1/gestao/configuracao": ["GET", "PUT"],
    "/api/v1/admin/sincronizar": ["POST"],
    "/api/v1/admin/rollback": ["POST"],
    "/api/v1/gestao/pendentes": ["GET"],
    "/api/v1/gestao/radar/{id}": ["GET", "PATCH"],
    "/api/v1/gestao/radar/{id}/verificar": ["POST"],
    "/api/v1/gestao/radar/{id}/cruzar": ["POST"],
    "/api/v1/gestao/cruzamentos": ["POST"],
    "/api/v1/gestao/radar/{id}/desabilitar": ["POST"],
    "/api/v1/gestao/radar/{id}/remover": ["POST"],
    "/api/v1/gestao/radar/{id}/historico": ["GET"],
    "/api/v1/gestao/eu": ["GET"],
    "/api/v1/gestao/correspondencias/{id}": ["POST"],
    "/api/v1/gestao/bloqueios": ["GET", "POST"],
    "/api/v1/gestao/bloqueios/{id}": ["DELETE"],
    "/api/v1/gestao/tokens": ["GET", "POST"],
    "/api/v1/gestao/tokens/{id}/revogar": ["POST"],
    "/api/v1/gestao/usuarios": ["GET", "POST"],
    "/api/v1/gestao/usuarios/{id}": ["PATCH"],
    "/api/v1/gestao/usuarios/{id}/senha": ["POST"],
}

ENDPOINTS_DESC = {
    "/api/v1/atualizacoes/status": "Relatorio consolidado das atualizacoes, em JSON e sem acesso ao banco.",
    "/api/v1/status/estados": "Contagem de pontos unicos nas 27 UFs por esfera de fiscalizacao; inclui nao classificados.",
    "/api/v1/status/estados/{uf}": "Detalhes da cobertura por UF, municipios, orgaos, fontes e pontos paginados.",
    "/api/v1/status/coletores": "Todos os leitores, inclusive nunca executados; ultima tentativa, ultimo sucesso, erros e URLs configuradas.",
    "/api/v1/gestao/radar/{id}/cruzar": "Recruza contribuicao ativa, inclusive verificada, com fontes oficiais locais; gera sugestoes auditadas.",
    "/api/v1/gestao/cruzamentos": "Recruza contribuicoes ativas em lotes de ate 20, com cursor e teto por ID; exige moderador.",
    "/api/v1/radares": "Pontos de fiscalizacao (radar instalado) num raio.",
    "/api/v1/radares/submeter": ("Submissao PUBLICA de radar (sem token): "
                                  "entra como colaborativo/nao verificado e "
                                  "publica na hora; Prefer: respond-async recebe em fila duravel e retorna 202 com protocolo."),
    "/api/v1/radares/envios/{protocolo}": "Andamento do envio em fila; nao expoe payload, contato ou IP.",
    "/api/v1/radares/{id}/historico": ("Historico/auditoria PUBLICO de um "
                                        "ponto: quem, quando, tipo, motivo."),
    "/api/v1/login": "Login do painel -> sessao (cookie httpOnly).",
    "/api/v1/logout": "Encerra a sessao do painel.",
    "/api/v1/minha-senha": "Troca a propria senha (exige a senha atual).",
    "/api/v1/gestao/eu": ("Contexto da sessao/token atual (login, papel): "
                          "usado pelo painel para decidir o que exibir."),
    "/api/v1/gestao/correspondencias/{id}": ("Resolve o vinculo de "
                                             "correspondencia "
                                             "(oficial_vence|colaborativo_vence)."),
    "/api/v1/radares/busca": ("Busca cadastral por UF/rodovia/municipio, "
                              "sem coordenada; cobertura parcial."),
    "/api/v1/radares/{id}": "Um ponto de fiscalizacao por id (P-<n>).",
    "/api/v1/trafego": ("Observacoes agregadas de trafego: velocidade de "
                        "PASSAGEM, nunca limite regulamentado da via."),
    "/api/v1/trechos": ("TRECHO ELEGIVEL para radar portatil: NAO e radar "
                        "nem operacao; indica apenas que PODE haver "
                        "fiscalizacao (spec 11.5)."),
    "/api/v1/operacoes": ("Operacoes de fiscalizacao publicadas. Exige "
                          "data/hora OFICIAL: sem ela a operacao vem com "
                          "inicio_em NULL e evidencia descoberta."),
    "/api/v1/equipamentos/{id}": "Equipamento fisico por id (E-<n>) (spec 11.3).",
    "/api/v1/fontes": "Lista de fontes e seus recursos.",
    "/api/v1/fontes/{id}": "Uma fonte por id (S-<n>).",
    "/api/v1/atualizacoes": ("Historico de execucoes de coleta e snapshots "
                             "publicados por fonte."),
    "/api/v1/ajuda": "Esta ajuda, em todos os formatos.",
    "/api/v1/status": "Estado do snapshot local e cobertura.",
    "/health/live": "Sinal de vida do processo.",
    "/health/ready": "Prontidao (banco local utilizavel).",
}

# Parametros aplicaveis por endpoint (documentado na ajuda, gerado do codigo).
ENDPOINTS_PARAMS = {
    "/api/v1/atualizacoes/status": [],
    "/api/v1/status/estados": [],
    "/api/v1/status/estados/{uf}": ["limite", "depois"],
    "/api/v1/status/coletores": [],
    "/api/v1/radares": ["lat", "lon", "raio", "formato", "delimitador",
                        "detalhado", "incluir_inativos", "incluir_incertos",
                        "incluir_trechos", "incluir_operacoes", "tipo_radar",
                        "modalidade", "fiscalizacao_pontual", "uf",
                        "municipio_ibge", "rodovia", "sentido", "em",
                        "limite", "cursor", "versao_esquema"],
    "/api/v1/radares/busca": ["formato", "delimitador", "detalhado",
                              "incluir_inativos", "tipo_radar", "modalidade",
                              "uf", "municipio_ibge", "rodovia",
                              "limite", "cursor"],
    "/api/v1/radares/{id}": ["formato", "delimitador", "detalhado"],
    "/api/v1/trafego": ["formato", "delimitador", "ponto_id",
                        "limite", "cursor"],
    "/api/v1/trechos": ["lat", "lon", "raio", "formato", "delimitador",
                        "uf", "municipio_ibge", "rodovia", "sentido",
                        "limite", "cursor"],
    "/api/v1/operacoes": ["lat", "lon", "raio", "formato", "delimitador",
                          "uf", "municipio_ibge", "rodovia", "modalidade",
                          "em", "limite", "cursor"],
    "/api/v1/equipamentos/{id}": ["formato", "delimitador"],
    "/api/v1/fontes": ["formato"],
    "/api/v1/fontes/{id}": ["formato"],
    "/api/v1/atualizacoes": ["formato", "delimitador", "fonte", "fonte_id",
                             "recurso", "status", "limite", "cursor"],
    "/api/v1/ajuda": ["formato", "delimitador"],
    "/api/v1/status": ["formato", "delimitador"],
    "/health/live": [],
    "/health/ready": [],
}

# Colunas fixas (ordem canonica) dos endpoints nao-tabulares, usadas em
# TXT / DIF / EDIFACT. O endpoint /radares usa as 32 colunas de campos.TXT_COLUMNS.
COLS_TRECHOS = (
    "id", "tipo_registro", "via", "via_nome", "uf", "municipios_json",
    "km_inicio", "km_fim", "sentido", "situacao", "vertices_json",
    "geometria_confirmada", "criterio_inclusao", "vigencia_inicio",
    "vigencia_fim", "documento_url", "documentos_json", "fontes_json",
    "indicador", "radar_instalado_confirmado",
)
COLS_OPERACOES = (
    "id", "tipo_registro", "modalidade", "fiscalizacao_pontual",
    "situacao_operacao", "tipo_operacao_original", "inicio_em", "fim_em",
    "fuso_original", "publicado_em", "recorrencias_json", "ponto_id",
    "trecho_id", "latitude", "longitude", "via", "via_nome", "km",
    "municipio", "uf", "orgao_responsavel", "equipamentos_ids_json",
    "faixas_ids_json", "documento_url", "fontes_json", "evidencia_operacao",
)
COLS_EQUIPAMENTO = (
    "id", "tipo_registro", "tipo_radar", "tipo_radar_original",
    "funcao_equipamento", "sigla_equipamento_original", "fabricante",
    "modelo", "tecnologia_medicao", "numero_serie", "ano_fabricacao",
    "registro_aprovacao_modelo", "portaria_aprovacao_modelo",
    "identificadores_oficiais_json", "instalacoes_json",
    "verificacoes_metrologicas_json", "proprietario", "mantenedor",
    "ultima_manutencao", "observacoes",
)
COLS_ATUALIZACOES = (
    "id", "tipo_registro", "fonte", "fonte_id", "esfera", "recurso",
    "recurso_id", "recurso_url", "iniciada_em", "terminada_em", "status",
    "http_status", "tentativas", "linhas_recebidas", "linhas_validas",
    "linhas_rejeitadas", "registros_criados", "registros_alterados",
    "erro_codigo", "erro_detalhe", "artefato_id", "artefato_hash",
)
COLS_TRAFEGO = (
    "id", "tipo_registro", "ponto_id", "equipamento_id", "faixa_id",
    "categoria_veiculo", "sentido", "data_observacao",
    "instante_observacao", "velocidade_publicada",
    "velocidade_observada_kmh", "volume_total", "fonte_json",
)
COLS_POR_ENDPOINT = {
    "/api/v1/radares": list(campos.TXT_COLUMNS),
    "/api/v1/radares/busca": list(campos.TXT_COLUMNS),
    "/api/v1/trafego": list(COLS_TRAFEGO),
    "/api/v1/trechos": list(COLS_TRECHOS),
    "/api/v1/operacoes": list(COLS_OPERACOES),
    "/api/v1/equipamentos/{id}": list(COLS_EQUIPAMENTO),
    "/api/v1/atualizacoes": list(COLS_ATUALIZACOES),
}


# Explicacao do ".pse": o termo so faz sentido para quem conhece este servidor.
# Fica no proprio texto de ajuda para que quem abre a API entenda o que e.
COMO_FUNCIONA_PSE = [
    "O QUE E ESTE ENDERECO (o \".pse\"):",
    "  Nao e um servidor nem um framework. E um programa Python 3 (so a",
    "  biblioteca padrao) que o nginx executa SOB DEMANDA via fcgiwrap",
    "  (FastCGI -> CGI). A extensao \".pse\" e uma convencao historica deste",
    "  servidor para scripts executaveis do site (ex.: cnpj.pse, frase.pse);",
    "  equivale a um \".cgi\" com a extensao da casa. Cada requisicao sobe o",
    "  processo, responde (JSON/XML/TXT/NDJSON/EDIFACT/DIF) e termina: sem",
    "  daemon e sem porta propria.",
    "  O nginx/fcgiwrap nao define PATH_INFO, entao a rota vai no parametro 'rota':",
    "    api.pse?rota=/api/v1/radares&lat=-24.9555&lon=-53.4552&raio=5000&formato=json",
    "",
]
COMO_FUNCIONA_PSE_TEXTO = (
    "Este endereco \".pse\" e um programa Python 3 (so biblioteca padrao) "
    "executado sob demanda pelo nginx via fcgiwrap (FastCGI->CGI) -- nao ha "
    "servidor, daemon nem porta propria. A extensao .pse e a convencao "
    "historica deste servidor para scripts do site. Como o nginx/fcgiwrap nao "
    "define PATH_INFO, a rota vai no parametro 'rota' (ex.: "
    "api.pse?rota=/api/v1/radares&lat=..&lon=..&raio=..)."
)


def ajuda_estrutura():
    return {
        "versao_api": config.API_VERSION,
        "como_funciona": COMO_FUNCIONA_PSE_TEXTO,
        "extensao_pse": ("convencao do servidor: fcgiwrap + nginx executam "
                         "este .pse (programa Python 3 sob demanda)"),
        "versao_esquema": config.SCHEMA_VERSION,
        "endpoints": ENDPOINTS_AJUDA,
        "endpoints_descricao": ENDPOINTS_DESC,
        "endpoints_administrativos": ENDPOINTS_ADMINISTRATIVOS,
        "parametros_por_endpoint": ENDPOINTS_PARAMS,
        "parametros": [
            {"nome": n, "tipo": t, "obrigatorio": o, "aceitos": a,
             "descricao": d} for (n, t, o, a, d) in PARAMS],
        "formatos": list(FORMATOS),
        "formato_content_type": {
            "json": "application/json; charset=utf-8",
            "ndjson": "application/x-ndjson; charset=utf-8",
            "xml": "application/xml; charset=utf-8",
            "txt": "text/plain; charset=utf-8",
            "edi": "application/EDIFACT; charset=utf-8",
            "edifact": "application/EDIFACT; charset=utf-8",
            "dif": "text/plain; charset=utf-8",
        },
        "txt_colunas_ordem": list(campos.TXT_COLUMNS),
        "txt_colunas": [
            {"posicao": i + 1, "nome": c, "descricao":
             campos.TXT_COLUMNS_DESC.get(c, "")}
            for i, c in enumerate(campos.TXT_COLUMNS)],
        "txt_null": "\\N",
        "txt_delimitador_padrao": "|",
        "colunas_por_endpoint": {k: list(v)
                                 for k, v in COLS_POR_ENDPOINT.items()},
        "edifact": {
            "mensagem": "GENRAL:D:96A:UN",
            "separadores": {"segmento": "'", "elemento": "+",
                            "componente": ":", "liberacao": "?"},
            "segmento_dados": "RAD0 (segmento de projeto/bilateral; NAO e "
                               "segmento padronizado UN/EDIFACT)",
            "colunas": "mesma ordem canonica do TXT; 1 elemento por coluna",
            "null": "elemento vazio",
        },
        "dif": {
            "tabela": "RADAR_BRASIL",
            "secoes": ["TABLE", "VECTORS", "TUPLES", "DATA", "EOD"],
            "diretivas": ["BOT", "EOD"],
            "colunas": "mesma ordem canonica do TXT (VECTORS)",
            "null": "tipo 0 com keyword NA",
        },
        "http_status": {
            "200": "consulta executada (inclusive zero pontos com cobertura)",
            "400/422": "parametro ou formato invalido",
            "404": "id individual nao encontrado",
            "405": "metodo nao permitido para o endpoint",
            "503": "banco/snapshot nao utilizavel",
            "500": "erro interno (com correlation_id)",
        },
    }


def ajuda_texto():
    linhas = ["RADAR BRASIL - AJUDA v%s" % config.API_VERSION, ""]
    linhas.extend(COMO_FUNCIONA_PSE)
    linhas.append("ENDPOINTS:")
    for ep, metodos in ENDPOINTS_AJUDA.items():
        linhas.append("  %-28s %-10s %s" % (
            ep, "/".join(metodos), ENDPOINTS_DESC.get(ep, "")))
    linhas.append("")
    linhas.append("ENDPOINTS ADMINISTRATIVOS (autenticados):")
    for ep, metodos in ENDPOINTS_ADMINISTRATIVOS.items():
        linhas.append("  %-28s %s" % (ep, "/".join(metodos)))
    linhas.append("")
    linhas.append("GOVERNANCA DA INGESTAO (colaborativo x oficial):")
    linhas.extend([
        "  - Leitura aberta; criacao aberta por POST /api/v1/radares/submeter",
        "    (sem token): entra como colaborativo NAO verificado e publica na",
        "    hora, com rate limit por IP e procedencia (IP/user-agent/quando).",
        "  - Se houver ponto OFICIAL no raio de correspondencia (config",
        ##-- BUNDITA DE URSO #{8} -- A ajuda precisa distinguir proximidade de verificacao por moderador. ##
        "    RAIO_CORRESPONDENCIA_M), cria-se uma sugestao de correspondencia;",
        "    o colaborativo continua NAO verificado ate revisao.",
        "  - Geofencing: coordenada dentro de BLOQUEIO_GEOGRAFICO ativo",
        "    (marcacao_falsa / zona_sombra) e recusada com 409 e motivo.",
        "  - Gestao exige sessao (login) ou cabecalho X-Api-Token; escopos:",
        "    contribuidor (le) < moderador (verifica/edita/remove) < admin",
        "    (usuarios, tokens, bloqueios). Remocao e TOMBSTONE: nada e apagado.",
        "  - Consulta publica preserva o oficial ate decisao de moderacao e esconde removidos e",
        "    desabilitados; GET /api/v1/radares/{id}/historico e publico.",
    ])
    linhas.append("")
    linhas.append("PARAMETROS (nome tipo obrig aceitos descricao):")
    for (n, t, o, a, d) in PARAMS:
        linhas.append("  %-18s %-9s %-3s aceitos=%-22s %s" % (
            n, t, "sim" if o else "nao", a, d))
    linhas.append("")
    linhas.append("PARAMETROS POR ENDPOINT:")
    for ep, nomes in ENDPOINTS_PARAMS.items():
        linhas.append("  %-28s %s" % (ep, ", ".join(nomes) or "(nenhum)"))
    linhas.append("")
    linhas.append("FORMATOS: %s" % ", ".join(FORMATOS))
    linhas.append("")
    linhas.append("ORDEM CANONICA TXT v1 (32 colunas, delimitador '%s', "
                  "NULL=\\N):" % "|")
    for i, c in enumerate(campos.TXT_COLUMNS):
        linhas.append("  %02d %-32s %s" % (
            i + 1, c, campos.TXT_COLUMNS_DESC.get(c, "")))
    linhas.append("")
    linhas.append("COLUNAS DOS DEMAIS ENDPOINTS (mesma ordem no TXT/DIF/EDIFACT):")
    for ep, cols in COLS_POR_ENDPOINT.items():
        if ep == "/api/v1/radares":
            continue
        linhas.append("  %s: %s" % (ep, ", ".join(cols)))
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Serializacao genérica para endpoints nao-tabulares (ajuda/status/fontes)
# ---------------------------------------------------------------------------
def serializa_objeto(formato, obj, texto=None, delimitador="|"):
    """Serializa um objeto/envelope nao-tabular (ajuda/status/fontes/etc.).

    json/ndjson/xml refletem o objeto; txt recebe `texto` (ou JSON indentado);
    edifact/dif envelopam `texto` (ou o JSON) com envelope valido e
    documentado (uma linha -> um segmento FTX / uma linha da tabela).
    """
    if formato == "json":
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                          default=str), "application/json; charset=utf-8"
    if formato == "ndjson":
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                          default=str) + "\n", "application/x-ndjson; charset=utf-8"
    if formato == "xml":
        import xml.etree.ElementTree as ET
        root = ET.Element("radar_brasil")
        xml_ser._fill(root, obj)
        return (ET.tostring(root, encoding="utf-8",
                            xml_declaration=True).decode("utf-8"),
                "application/xml; charset=utf-8")
    if formato == "txt":
        if texto is None:
            texto = json.dumps(obj, ensure_ascii=False, indent=2)
        return texto, "text/plain; charset=utf-8"
    if formato in ("edi", "edifact"):
        base = texto if texto is not None else json.dumps(
            obj, ensure_ascii=False, indent=2)
        return (edifact_ser.envolver_texto(base, obj),
                "application/EDIFACT; charset=utf-8")
    if formato == "dif":
        base = texto if texto is not None else json.dumps(
            obj, ensure_ascii=False, indent=2)
        return dif_ser.envolver_texto(base, obj), "text/plain; charset=utf-8"
    raise ValueError("formato invalido")


# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------
def _parse_params(environ, stdin_bytes):
    params = dict(urllib.parse.parse_qsl(
        environ.get("QUERY_STRING", ""), keep_blank_values=True))
    metodo = environ.get("REQUEST_METHOD", "GET").upper()
    if metodo == "POST" and stdin_bytes:
        ctype = environ.get("CONTENT_TYPE", "")
        texto = stdin_bytes.decode("utf-8", "replace")
        if "application/json" in ctype:
            try:
                dados = json.loads(texto)
                if isinstance(dados, dict):
                    for k, v in dados.items():
                        params[k] = v
            except ValueError:
                params["__json_invalido__"] = "1"
        else:
            for k, v in urllib.parse.parse_qsl(texto, keep_blank_values=True):
                params[k] = v
    return params


def _bool_param(v, default):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "sim", "yes", "y"):
        return True
    if s in ("0", "false", "nao", "no", "n"):
        return False
    raise ValueError("valor booleano invalido: %r" % v)


def _erro(status, codigo, mensagem, campo=None):
    body = {
        "sucesso": False,
        "versao_api": config.API_VERSION,
        "versao_esquema": config.SCHEMA_VERSION,
        "erro": {
            "codigo": codigo,
            "mensagem": mensagem,
            "detalhes": [],
            "campo": campo,
            "correlation_id": _agora(),
            "timestamp": _agora(),
        },
    }
    return status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control":"no-store"}, body


##-- BUNDITA DE URSO #{10} -- Sem medicao de idade nao existe evidencia para afirmar cache fresco. ##
def _base_meta():
    return {
        "versao_api": config.API_VERSION,
        "versao_esquema": config.SCHEMA_VERSION,
        "cobertura": {
            "fontes_ativas": [], "fontes_indisponiveis": [],
            "territorios_verificados": [], "limitacoes": [],
            "completude_confirmada": False,
        },
        "base": {
            "snapshot_id": None, "publicado_em": None,
            "idade_snapshot_segundos": None,
            "ultima_sincronizacao_valida": None,
            "idade_publicacao_origem_segundos": None,
            "status_cache": "desconhecido", "alertas": [],
        },
    }


def _conn():
    path = config.DB_PATH
    if not os.path.exists(path):
        return None
    return dbmod.connect(path)


def _headers_radar(meta, status_code):
    base = meta.get("base", {})
    resultado = meta.get("resultado", {})
    return {
        "Cache-Control": "no-store",
        "X-Radar-Snapshot-ID": str(base.get("snapshot_id") or ""),
        "X-Radar-Base-Updated-At": str(base.get("publicado_em") or ""),
        "X-Radar-Cache-Age-Seconds": str(base.get("idade_snapshot_segundos") or ""),
        "X-Radar-Coverage-Status": str(resultado.get("status") or ""),
        "X-Radar-Total-Points": str(resultado.get("total_pontos") or 0),
        "X-Radar-Total-Equipment": str(resultado.get("total_equipamentos") or 0),
        "X-Radar-Response-Schema-Version": config.SCHEMA_VERSION,
    }


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------
def _rota(environ):
    """Deriva o caminho do endpoint tolerando variacoes de CGI/fcgiwrap."""
    caminho = environ.get("PATH_INFO") or ""
    if not caminho:
        query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
        caminho = (query.get("rota") or query.get("path") or [""])[0]
    if not caminho:
        uri = environ.get("REQUEST_URI", "").split("?", 1)[0]
        script = environ.get("SCRIPT_NAME", "")
        if uri.startswith(script):
            caminho = uri[len(script):]
        else:
            caminho = uri
    if not caminho:
        caminho = "/"
    return caminho


def _token_escrita(environ):
    """Valida o token de escrita (cabecalho X-Api-Token).

    O token vem somente de api.token_arquivo no radar.conf, dentro de dados.dir.
    Sem token configurado a escrita fica DESABILITADA e a resposta e 401
    (falha segura). A comparacao e em tempo constante (hmac.compare_digest).

    Devolve ``(ok, codigo)``.
    """
    configurado = config.token_ingestao()
    if not configurado:
        return False, "ingestao_desabilitada"
    enviado = environ.get("HTTP_X_API_TOKEN") or ""
    if not enviado or not hmac.compare_digest(str(enviado), configurado):
        return False, "nao_autorizado"
    return True, None


def _validar_item_radar(item):
    """Valida o minimo de cada radar enviado. Devolve (campo, msg) ou None.

    Delega para ``core.governanca.validar_minimo`` para que a ingestao
    autenticada e a submissao publica usem EXATAMENTE a mesma regra.
    """
    return governanca.validar_minimo(item)


def _eh_ingestao(caminho, metodo, environ, stdin_bytes):
    """Decide se POST /api/v1/radares e ESCRITA (ingestao) ou consulta.

    E escrita quando: (a) vem o cabecalho X-Api-Token; ou (b) o corpo e um
    array JSON (uma consulta nunca usa array). Sem isso, mantem o contrato
    antigo (POST com lat/lon = consulta). A submissao PUBLICA (sem token) usa
    a rota propria /api/v1/radares/submeter.
    """
    if metodo != "POST":
        return False
    if caminho.rstrip("/") != "/api/v1/radares":
        return False
    if (environ.get("HTTP_X_API_TOKEN") or "").strip():
        return True
    if "application/json" in (environ.get("CONTENT_TYPE") or ""):
        try:
            dados = json.loads(stdin_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        if isinstance(dados, list):
            return True
    return False


def _ingestao_radares(environ, stdin_bytes):
    """POST /api/v1/radares — escrita autenticada (a base NOSSA).

    Aceita um objeto JSON ou um array. Reutiliza a MESMA normalizacao + upsert
    do coletor (ColetorBaseLWB.ingerir_registros) para que o radar ingerido
    pela API se comporte igual ao coletado. Resposta:
    ``{ok, criados, atualizados, rejeitados, erros:[{indice,campo,mensagem}]}``.
    """
    if len(stdin_bytes) > config.API_MAX_BODY:
        return _erro(413, "corpo_muito_grande",
                     "corpo excede %d bytes" % config.API_MAX_BODY)
    ok, codigo = _token_escrita(environ)
    if not ok:
        msg = ("token de escrita nao configurado no servidor "
               "(api.token_arquivo no radar.conf)"
               if codigo == "ingestao_desabilitada" else
               "token ausente ou invalido no cabecalho X-Api-Token")
        return _erro(401, codigo, msg, campo="X-Api-Token")
    try:
        dados = json.loads(stdin_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return _erro(400, "json_invalido",
                     "corpo JSON invalido: %s" % str(exc)[:200])
    if isinstance(dados, dict):
        itens = [dados]
    elif isinstance(dados, list):
        itens = dados
    else:
        return _erro(422, "payload_invalido",
                     "envie um objeto JSON ou um array de objetos")
    if not itens:
        return _erro(422, "payload_vazio", "nenhum radar enviado")

    validos = []
    erros = []
    for i, item in enumerate(itens):
        erro = _validar_item_radar(item)
        if erro is None:
            validos.append(item)
        else:
            campo, mensagem = erro
            erros.append({"indice": i, "campo": campo,
                          "mensagem": mensagem})

    criados = atualizados = 0
    rejeitados = len(erros)
    if validos:
        from coletor.fontes.base_lwb import ColetorBaseLWB
        conector = ColetorBaseLWB(db_path=config.DB_PATH)
        try:
            resumo = conector.ingerir_registros(validos)
            criados = resumo["criados"]
            atualizados = resumo["atualizados"]
            rejeitados += resumo["rejeitados"]
        except Exception as exc:                       # noqa: BLE001
            return _erro(500, "falha_ingestao", str(exc)[:300])
        finally:
            conector.conn.close()

    aceitos = criados + atualizados
    if aceitos == 0 and not erros:
        erros.append({"indice": None, "campo": None,
                      "mensagem": "nenhum registro aceito"})
        rejeitados = len(itens)
    corpo = {
        "ok": rejeitados == 0 and aceitos > 0,
        "criados": criados,
        "atualizados": atualizados,
        "rejeitados": rejeitados,
        "erros": erros,
    }
    status = 200 if aceitos > 0 else 422
    return status, {"Content-Type": "application/json; charset=utf-8"}, corpo


# ---------------------------------------------------------------------------
# GOVERNANCA (rotas novas): submissao publica, login/sessao e gestao.
# Toda escrita passa por core.governanca (a API e o unico caminho de escrita).
# ---------------------------------------------------------------------------
def _resp(obj, status=200, extra_headers=None):
    headers = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    if extra_headers:
        headers.update(extra_headers)
    return status, headers, obj


def _gov_erro(exc):
    status, headers, body = _erro(exc.status, exc.codigo, exc.mensagem,
                                  campo=exc.campo)
    if exc.detalhes:
        body["erro"]["detalhes"] = exc.detalhes
    return status, headers, body


def _corpo_json(stdin_bytes):
    if not stdin_bytes:
        return {}
    if len(stdin_bytes) > config.API_MAX_BODY:
        raise governanca.GovernancaError(
            413, "corpo_muito_grande",
            "corpo excede %d bytes" % config.API_MAX_BODY)
    try:
        return json.loads(stdin_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise governanca.GovernancaError(
            400, "json_invalido", "corpo JSON invalido: %s" % str(exc)[:200])


def _pid(parte):
    try:
        return int(str(parte).upper().replace("P-", ""))
    except (TypeError, ValueError):
        raise governanca.GovernancaError(404, "ponto_nao_encontrado",
                                         "id de ponto invalido: %s" % parte)


def _ip_requisicao(environ):
    ##-- BUNDITA DE URSO #{12} -- X-Forwarded-For arbitrario permitia trocar IP e contornar o rate limit. ##
    remoto = environ.get("REMOTE_ADDR") or "desconhecido"
    redes = []
    for especificacao in config.TRUSTED_PROXIES:
        try:
            redes.append(ipaddress.ip_network(especificacao, strict=False))
        except ValueError:
            continue  # Configuracao invalida nunca amplia a confianca.
    try:
        ip = ipaddress.ip_address(remoto)
        if not any(ip in rede for rede in redes):
            return remoto
        for parte in reversed(environ.get("HTTP_X_FORWARDED_FOR", "").split(",")):
            ip = ipaddress.ip_address(parte.strip())
            if not any(ip in rede for rede in redes):
                return str(ip)
    except ValueError:
        pass
    return remoto


def _consulta_params(environ):
    return dict(urllib.parse.parse_qsl(environ.get("QUERY_STRING", ""),
                                       keep_blank_values=True))


def _dispatch_governanca(conn, caminho, metodo, environ, stdin_bytes):
    """Trata as rotas de governanca; devolve resposta ou None (nao e nossa)."""
    p = caminho.rstrip("/") or "/"
    if p == "/api/v1/radares/submeter":
        if metodo != "POST":
            return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
        return _submeter(conn, environ, stdin_bytes)
    if p == "/api/v1/login":
        if metodo != "POST":
            return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
        return _login(conn, environ, stdin_bytes)
    if p == "/api/v1/logout":
        if metodo != "POST":
            return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
        return _logout(conn, environ)
    if p == "/api/v1/minha-senha":
        if metodo != "POST":
            return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
        return _minha_senha(conn, environ, stdin_bytes)
    if p == "/api/v1/gestao" or p.startswith("/api/v1/gestao/"):
        return _gestao(conn, p, metodo, environ, stdin_bytes)
    m = re.match(r"^/api/v1/radares/([^/]+)/historico$", p)
    if m:
        if metodo != "GET":
            return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
        return _historico_publico(conn, m.group(1))
    return None


def _submeter(conn, environ, stdin_bytes):
    try:
        dados = _corpo_json(stdin_bytes)
        contato = None
        if isinstance(dados, dict):
            contato = dados.get("contato")
        elif isinstance(dados, list) and dados and isinstance(dados[0], dict):
            contato = dados[0].get("contato")
        procedencia = {"ip": _ip_requisicao(environ),
                       "user_agent": environ.get("HTTP_USER_AGENT"),
                       "quando": _agora(), "contato": contato}
        res = governanca.submeter(conn, dados, procedencia)
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    return _resp({"sucesso": True, "versao_api": config.API_VERSION,
                  "versao_esquema": config.SCHEMA_VERSION,
                  "resultado": res}, 201)


def _login(conn, environ, stdin_bytes):
    try:
        dados = _corpo_json(stdin_bytes) or {}
        usuario = governanca.autenticar_senha(conn, dados.get("login"),
                                              dados.get("senha"))
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    if usuario is None:
        return _erro(401, "credenciais_invalidas",
                     "login ou senha invalidos")
    valor, ttl = governanca.criar_sessao(
        conn, usuario["id"], ip=_ip_requisicao(environ),
        user_agent=environ.get("HTTP_USER_AGENT"))
    conn.execute("UPDATE USUARIO SET ultimo_login=? WHERE id=?",
                 (_agora(), usuario["id"]))
    conn.commit()
    cookie = ("%s=%s; HttpOnly; Path=/; SameSite=Lax; Max-Age=%d"
              % (governanca.COOKIE_SESSAO, valor, ttl))
    corpo = {"sucesso": True, "token": valor, "expira_em_segundos": ttl,
             "usuario": {"id": usuario["id"], "login": usuario["login"],
                         "papel": usuario["papel"],
                         "deve_trocar_senha": bool(
                             usuario["deve_trocar_senha"])}}
    return _resp(corpo, 200, {"Set-Cookie": cookie})


def _logout(conn, environ):
    valor = (governanca._cookie(environ, governanca.COOKIE_SESSAO)
             or environ.get("HTTP_X_SESSAO"))
    governanca.encerrar_sessao(conn, valor)
    cookie = "%s=; HttpOnly; Path=/; Max-Age=0" % governanca.COOKIE_SESSAO
    return _resp({"sucesso": True}, 200, {"Set-Cookie": cookie})


def _minha_senha(conn, environ, stdin_bytes):
    try:
        ctx = governanca.contexto_autenticacao(conn, environ)
        governanca.exigir(ctx, "contribuidor")
        if ctx.get("tipo") != "usuario":
            raise governanca.GovernancaError(
                403, "permissao_negada",
                "troca de senha exige sessao do painel (nao token de API)")
        dados = _corpo_json(stdin_bytes) or {}
        governanca.trocar_propria_senha(conn, ctx["usuario_id"],
                                        dados.get("senha_atual"),
                                        dados.get("senha_nova"))
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    return _resp({"sucesso": True})


def _historico_publico(conn, parte):
    try:
        pid = _pid(parte)
        governanca.garantir_esquema(conn)
        hist = governanca.historico(conn, pid, publico=True)
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    return _resp({"sucesso": True, "ponto_id": "P-%d" % pid,
                  "historico": hist})


def _gestao(conn, p, metodo, environ, stdin_bytes):
    try:
        ctx = governanca.contexto_autenticacao(conn, environ)
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    resto = p[len("/api/v1/gestao"):].strip("/")
    partes = resto.split("/") if resto else []
    try:
        if partes[:1] == ["assistente"]:
            governanca.exigir(ctx, "admin")
            from core import assistencia, assistente_ia
            if metodo in ("POST", "PUT", "DELETE") and (
                    environ.get("HTTP_X_RADAR_CONFIGURACAO") != "1" or
                    environ.get("HTTP_SEC_FETCH_SITE") == "cross-site" or
                    environ.get("CONTENT_TYPE", "").split(";")[0] != "application/json"):
                return _erro(403, "origem_invalida", "Use o painel administrativo.")
            if partes == ["assistente"] and metodo == "GET":
                return _resp({"sucesso": True, "assistente": assistente_ia.status(), "relatorios": assistencia.listar()}, extra_headers={"Cache-Control": "no-store"})
            if partes == ["assistente"] and metodo == "POST":
                return _resp(assistencia.analisar(conn, _corpo_json(stdin_bytes), autor=ctx.get("rotulo")), extra_headers={"Cache-Control": "no-store"})
            if partes == ["assistente", "chave"] and metodo in ("PUT", "DELETE"):
                dados = {"remover": True} if metodo == "DELETE" else _corpo_json(stdin_bytes)
                return _resp(assistente_ia.salvar_chave(dados), extra_headers={"Cache-Control": "no-store"})
            if len(partes) == 3 and partes[:2] == ["assistente", "relatorios"] and metodo == "GET":
                return _resp(assistencia.obter(partes[2]), extra_headers={"Cache-Control": "no-store"})
            return _erro(405, "metodo_nao_permitido", "Operacao do assistente nao permitida.")
        if partes == ["configuracao"]:
            governanca.exigir(ctx, "admin")
            from core import configuracao
            if metodo == "GET":
                return _resp(configuracao.consultar(web=True), extra_headers={"Cache-Control": "no-store"})
            if metodo == "PUT":
                # Cabecalho nao simples impede envio por formulario/site externo.
                if (environ.get("HTTP_X_RADAR_CONFIGURACAO") != "1" or
                        environ.get("HTTP_SEC_FETCH_SITE") == "cross-site" or
                        environ.get("CONTENT_TYPE", "").split(";")[0] != "application/json"):
                    return _erro(403, "origem_invalida", "Salve a configuracao pelo painel administrativo.")
                resultado = configuracao.salvar(_corpo_json(stdin_bytes), autor=ctx.get("rotulo"), web=True)
                return _resp(resultado, extra_headers={"Cache-Control": "no-store"})
            return _erro(405, "metodo_nao_permitido", "Use GET ou PUT.")
        # -- quem sou eu (contexto da sessao/token) -----------------------
        if partes[:1] == ["eu"]:
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            governanca.exigir(ctx, "contribuidor")
            return _resp({"sucesso": True, "autenticado": True,
                          "tipo": ctx.get("tipo"),
                          "escopo": ctx.get("escopo"),
                          "rotulo": ctx.get("rotulo"),
                          "usuario_id": ctx.get("usuario_id"),
                          "token_id": ctx.get("token_id")})

        # -- resolucao de vinculo de correspondencia ----------------------
        if partes[:1] == ["correspondencias"] and len(partes) == 2:
            if metodo != "POST":
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            governanca.exigir(ctx, "moderador")
            try:
                cid = int(partes[1])
            except (TypeError, ValueError):
                return _erro(422, "parametro_invalido",
                             "id de correspondencia invalido")
            dados = _corpo_json(stdin_bytes) or {}
            governanca.resolver_correspondencia(
                conn, cid, dados.get("status"), ctx,
                motivo=dados.get("motivo"))
            return _resp({"sucesso": True})

        if partes == ["cruzamentos"]:
            if metodo != "POST":
                return _erro(405, "metodo_nao_permitido", "Use POST.")
            governanca.exigir(ctx, "moderador")
            from core import cruzamentos
            dados = _corpo_json(stdin_bytes)
            return _resp({"sucesso": True, "resultado": cruzamentos.cruzar_lote(
                conn, dados, ctx, _ip_requisicao(environ))})

        # -- fila de pendentes --------------------------------------------
        if partes[:1] == ["pendentes"]:
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            governanca.exigir(ctx, "contribuidor")
            params = _consulta_params(environ)
            try:
                limite = int(params.get("limite", config.DEFAULT_LIMITE))
            except (TypeError, ValueError):
                return _erro(422, "limite_invalido", "limite inteiro 1..1000")
            pontos, meta = governanca.listar_pendentes(
                conn, limite, params.get("cursor"), params.get("status"))
            return _resp({"sucesso": True, "pendentes": pontos,
                          "resultado": meta})

        # -- radar/{id} e acoes -------------------------------------------
        if partes[:1] == ["radar"] and len(partes) >= 2:
            pid = _pid(partes[1])
            acao = partes[2] if len(partes) > 2 else None
            if acao is None:
                if metodo == "GET":
                    governanca.exigir(ctx, "contribuidor")
                    return _resp({"sucesso": True,
                                  "radar": governanca.obter_radar(conn, pid)})
                if metodo == "PATCH":
                    governanca.exigir(ctx, "moderador")
                    dados = _corpo_json(stdin_bytes) or {}
                    depois = governanca.editar_radar(
                        conn, pid, dados, ctx, ip=_ip_requisicao(environ))
                    return _resp({"sucesso": True, "editado": depois})
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            if acao == "historico" and metodo == "GET":
                governanca.exigir(ctx, "contribuidor")
                hist = governanca.historico(conn, pid, publico=False)
                return _resp({"sucesso": True, "ponto_id": "P-%d" % pid,
                              "historico": hist})
            if metodo != "POST":
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            governanca.exigir(ctx, "moderador")
            dados = _corpo_json(stdin_bytes) or {}
            ip = _ip_requisicao(environ)
            if acao == "cruzar":
                from core import cruzamentos
                resultado = cruzamentos.cruzar(conn, pid, ctx, ip)
                return _resp({"sucesso": True, "resultado": resultado,
                              "radar": governanca.obter_radar(conn, pid)})
            if acao == "verificar":
                governanca.verificar_radar(conn, pid, ctx,
                                           motivo=dados.get("motivo"), ip=ip)
                return _resp({"sucesso": True})
            if acao == "desabilitar":
                governanca.desabilitar_radar(conn, pid, ctx,
                                             dados.get("motivo"), ip=ip)
                return _resp({"sucesso": True})
            if acao == "remover":
                governanca.remover_radar(conn, pid, ctx, dados.get("motivo"),
                                         ip=ip)
                return _resp({"sucesso": True, "removido": "P-%d" % pid})
            return _erro(404, "rota_desconhecida",
                         "acao desconhecida: %s" % acao)

        # -- bloqueios geograficos ---------------------------------------
        if partes[:1] == ["bloqueios"]:
            if len(partes) == 1:
                if metodo == "GET":
                    governanca.exigir(ctx, "moderador")
                    params = _consulta_params(environ)
                    incluir = str(params.get("incluir_inativos", "")).lower() in ("1", "true", "sim")
                    return _resp({"sucesso": True,
                                  "bloqueios": governanca.listar_bloqueios(conn, incluir)})
                if metodo == "POST":
                    governanca.exigir(ctx, "admin")
                    dados = _corpo_json(stdin_bytes) or {}
                    raio = dados.get("raio_metros")
                    if not raio and dados.get("tipo") == "zona_sombra":
                        raio = config.RAIO_ZONA_SOMBRA_M
                    bid = governanca.criar_bloqueio(
                        conn, dados.get("tipo"), dados.get("latitude"),
                        dados.get("longitude"), raio, dados.get("motivo"),
                        ctx, origem_ponto_id=dados.get("origem_ponto_id"))
                    return _resp({"sucesso": True, "bloqueio_id": bid}, 201)
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            if len(partes) == 2:
                governanca.exigir(ctx, "admin")
                if metodo != "DELETE":
                    return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
                try:
                    bid = int(partes[1])
                except (TypeError, ValueError):
                    return _erro(422, "parametro_invalido", "id de bloqueio invalido")
                governanca.desativar_bloqueio(conn, bid, ctx)
                return _resp({"sucesso": True})
            return _erro(404, "rota_desconhecida", "rota de bloqueio desconhecida")

        # -- tokens -------------------------------------------------------
        if partes[:1] == ["tokens"]:
            governanca.exigir(ctx, "admin")
            if len(partes) == 1:
                if metodo == "GET":
                    return _resp({"sucesso": True,
                                  "tokens": governanca.listar_tokens(conn)})
                if metodo == "POST":
                    dados = _corpo_json(stdin_bytes) or {}
                    tid, valor = governanca.emitir_token(
                        conn, dados.get("nome"),
                        dados.get("escopo") or "contribuidor",
                        dono=dados.get("dono"),
                        expira_em=dados.get("expira_em"),
                        observacoes=dados.get("observacoes"),
                        criado_por=(ctx or {}).get("rotulo"))
                    return _resp({"sucesso": True, "token_id": tid,
                                  "token": valor,
                                  "prefixo": governanca.prefixo_token(valor),
                                  "aviso": "guarde o valor agora: ele NAO "
                                            "sera exibido de novo"}, 201)
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            if len(partes) == 3 and partes[2] == "revogar" and metodo == "POST":
                try:
                    tid = int(partes[1])
                except (TypeError, ValueError):
                    return _erro(422, "parametro_invalido", "id de token invalido")
                governanca.revogar_token(conn, tid)
                return _resp({"sucesso": True})
            return _erro(404, "rota_desconhecida", "rota de token desconhecida")

        # -- usuarios -----------------------------------------------------
        if partes[:1] == ["usuarios"]:
            governanca.exigir(ctx, "admin")
            if len(partes) == 1:
                if metodo == "GET":
                    return _resp({"sucesso": True,
                                  "usuarios": governanca.listar_usuarios(conn)})
                if metodo == "POST":
                    dados = _corpo_json(stdin_bytes) or {}
                    res = governanca.criar_usuario_api(conn, dados, ctx)
                    return _resp({"sucesso": True, "usuario": res}, 201)
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            if len(partes) == 2:
                try:
                    uid = int(partes[1])
                except (TypeError, ValueError):
                    return _erro(422, "parametro_invalido", "id de usuario invalido")
                if metodo == "PATCH":
                    dados = _corpo_json(stdin_bytes) or {}
                    governanca.definir_papel_ativo(
                        conn, uid, papel=dados.get("papel"),
                        ativo=(None if "ativo" not in dados
                               else bool(dados.get("ativo"))))
                    return _resp({"sucesso": True})
                return _erro(405, "metodo_nao_permitido", "metodo %s nao permitido" % metodo)
            if len(partes) == 3 and partes[2] == "senha" and metodo == "POST":
                try:
                    uid = int(partes[1])
                except (TypeError, ValueError):
                    return _erro(422, "parametro_invalido", "id de usuario invalido")
                usuario = governanca.obter_usuario(conn, uid)
                if usuario is None:
                    return _erro(404, "usuario_nao_encontrado",
                                 "usuario %s nao encontrado" % uid)
                _row, senha = governanca.resetar_senha(conn, usuario["login"])
                return _resp({"sucesso": True, "login": usuario["login"],
                              "senha_temporaria": senha,
                              "deve_trocar_senha": True})
            return _erro(404, "rota_desconhecida", "rota de usuario desconhecida")
    except governanca.GovernancaError as exc:
        return _gov_erro(exc)
    return _erro(404, "rota_desconhecida", "rota de gestao nao encontrada")


def handle_request(environ, stdin_bytes=b""):
    metodo = environ.get("REQUEST_METHOD", "GET").upper()
    caminho = _rota(environ)
    # Recebimento rapido e andamento nao dependem de SQLite, nem quando ha lock.
    envio = re.fullmatch(r"/api/v1/radares/envios/(.*)", caminho)
    assincrono = caminho == "/api/v1/radares/submeter" and "respond-async" in environ.get("HTTP_PREFER", "").lower()
    if envio or assincrono:
        from core import fila_cadastros
        if metodo != ("GET" if envio else "POST"):
            return _erro(405, "metodo_nao_permitido", "Metodo nao permitido para este envio.")
        try:
            if envio:
                resultado = fila_cadastros.consultar(envio.group(1))
                return _resp({"sucesso": True, "resultado": resultado}, extra_headers={"Cache-Control":"no-store"})
            if (environ.get("CONTENT_TYPE", "").split(";")[0].strip() != "application/json" or
                    environ.get("HTTP_SEC_FETCH_SITE") == "cross-site"):
                return _erro(403, "origem_invalida", "Envie JSON pelo formulario de cadastro.")
            resultado = fila_cadastros.receber(_corpo_json(stdin_bytes), {
                "ip": _ip_requisicao(environ), "user_agent": environ.get("HTTP_USER_AGENT"), "quando": _agora()})
            return _resp({"sucesso": True, "resultado": resultado}, 202, {
                "Cache-Control":"no-store", "Preference-Applied":"respond-async", "Location":resultado["consulta_url"]})
        except governanca.GovernancaError as exc:
            return _gov_erro(exc)
    # escrita autenticada ANTES do parsing de consulta (corpo pode ser array)
    if _eh_ingestao(caminho, metodo, environ, stdin_bytes):
        return _ingestao_radares(environ, stdin_bytes)
    params = _parse_params(environ, stdin_bytes)

    if caminho in ("/health/live", "/api/v1/health/live"):
        return 200, {"Content-Type": "application/json; charset=utf-8"}, {"status": "live"}

    # formato / delimitador
    formato = str(params.get("formato") or "json").lower()
    if formato == "edi":
        formato = "edifact"
    if not is_valido(formato):
        return _erro(400, "formato_invalido",
                     "formato nao suportado: %s" % params.get("formato"))
    delimitador = params.get("delimitador") or "|"
    try:
        delimitador = _cls_txt.validar_delimitador(delimitador)
    except ValueError as exc:
        return _erro(400, "delimitador_invalido", str(exc), campo="delimitador")

    # --- endpoints sem banco -------------------------------------------------
    if caminho.rstrip('/') == '/api/v1/atualizacoes/status':
        if metodo != 'GET':
            return _erro(405, 'metodo_nao_permitido', 'Use GET para consultar o relatorio.')
        if formato != 'json':
            return _erro(400,'formato_invalido','O relatorio de atualizacoes usa JSON.')
        from core import atualizacoes, caminhos
        from pathlib import Path
        try:
            estado=json.loads(Path(caminhos.status_atualizacoes()).read_text())
        except FileNotFoundError:
            estado={'versao_esquema':1,'operacoes':{},'fontes':{}}
        except (OSError, ValueError):
            return _erro(503,'relatorio_indisponivel','O relatorio de atualizacoes esta indisponivel.')
        return _resp(atualizacoes.limpar(estado))
    if caminho in ("/api/v1/ajuda", "/api/v1/ajuda/"):
        estrutura = ajuda_estrutura()
        try:
            corpo, ctype = serializa_objeto(formato, estrutura,
                                            texto=ajuda_texto())
        except ValueError as exc:
            return _erro(400, "formato_invalido", str(exc))
        return 200, {"Content-Type": ctype}, corpo

    # --- endpoints com banco -------------------------------------------------
    if caminho in ("/health/ready", "/api/v1/health/ready"):
        ##-- BUNDITA DE URSO #{11} -- Arquivo existente nao comprova banco legivel nem schema inicializado. ##
        conn = None
        try:
            conn = _conn()
            pronto = conn is not None and dbmod.esquema_carregado(conn)
        except Exception:
            pronto = False
        finally:
            if conn is not None:
                conn.close()
        if not pronto:
            return 503, {"Content-Type": "application/json; charset=utf-8"}, \
                {"status": "not-ready", "motivo": "banco ausente, ilegivel ou nao inicializado"}
        return 200, {"Content-Type": "application/json; charset=utf-8"}, {"status": "ready"}

    conn = _conn()

    if conn is None:
        return _erro(503, "snapshot_indisponivel",
                     "banco local ausente ou nao inicializado")

    try:
        gov = _dispatch_governanca(conn, caminho, metodo, environ, stdin_bytes)
        if gov is not None:
            return gov

        if caminho.rstrip("/") in ("/api/v1/status/estados", "/api/v1/status/coletores") or caminho.startswith("/api/v1/status/estados/"):
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido", "Use GET para consultar o status.")
            if formato != "json":
                return _erro(400, "formato_invalido", "O painel de status usa JSON.")
            if caminho.rstrip("/") == "/api/v1/status/coletores":
                resultado = painel_status.coletores(conn)
            else:
                uf = caminho[len("/api/v1/status/estados"):].strip("/").upper() or None
                limite = _param_limite(params)
                try:
                    depois = int(params.get("depois", 0))
                    if depois < 0 or limite is None:
                        raise ValueError()
                except (TypeError, ValueError):
                    return _erro(422, "paginacao_invalida", "limite 1..1000 e depois inteiro nao negativo.")
                if uf is not None and uf not in painel_status.NOMES:
                    return _erro(422, "uf_invalida", "Informe uma das 27 siglas de UF.")
                resultado = painel_status.cobertura(conn, uf, limite, depois)
            return _resp({"sucesso": True, "resultado": resultado}, extra_headers={"Cache-Control": "no-store"})

        if caminho in ("/api/v1/status", "/api/v1/status/"):
            st = consultas.status_base(conn)
            try:
                corpo, ctype = serializa_objeto(formato, st)
            except ValueError as exc:
                return _erro(400, "formato_invalido", str(exc))
            return 200, {"Content-Type": ctype}, corpo

        if caminho in ("/api/v1/fontes", "/api/v1/fontes/"):
            fontes = consultas.listar_fontes(conn)
            obj = {"sucesso": True, "versao_api": config.API_VERSION,
                   "fontes": fontes}
            corpo, ctype = serializa_objeto(formato, obj)
            return 200, {"Content-Type": ctype}, corpo

        if caminho.startswith("/api/v1/fontes/"):
            resto = caminho[len("/api/v1/fontes/"):].strip("/")
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _fonte_id(conn, resto, formato, delimitador)

        if caminho in ("/api/v1/trechos", "/api/v1/trechos/"):
            if metodo not in ("GET", "POST"):
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _trechos(conn, params, formato, delimitador)

        if caminho in ("/api/v1/operacoes", "/api/v1/operacoes/"):
            if metodo not in ("GET", "POST"):
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _operacoes(conn, params, formato, delimitador)

        if caminho in ("/api/v1/atualizacoes", "/api/v1/atualizacoes/"):
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _atualizacoes(conn, params, formato, delimitador)

        if caminho.startswith("/api/v1/equipamentos"):
            if metodo != "GET":
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            resto = caminho[len("/api/v1/equipamentos"):].strip("/")
            if not resto:
                return _erro(404, "equipamento_nao_encontrado",
                             "informe o id do equipamento (E-<n>)")
            return _equipamento(conn, resto, formato, delimitador)

        if caminho in ("/api/v1/trafego", "/api/v1/trafego/"):
            if metodo not in ("GET", "POST"):
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _trafego(conn, params, formato, delimitador)

        if caminho in ("/api/v1/radares/busca", "/api/v1/radares/busca/"):
            if metodo not in ("GET", "POST"):
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _busca(conn, params, formato, delimitador)

        if caminho.startswith("/api/v1/radares"):
            resto = caminho[len("/api/v1/radares"):].strip("/")
            if resto:
                return _ponto(conn, resto, formato, delimitador)
            if metodo not in ("GET", "POST"):
                return _erro(405, "metodo_nao_permitido",
                             "metodo %s nao permitido" % metodo)
            return _radares(conn, params, formato, delimitador)

        return _erro(404, "rota_desconhecida", "rota nao encontrada: %s" % caminho)
    finally:
        conn.close()


def _radares(conn, params, formato, delimitador):
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
    except (KeyError, TypeError, ValueError):
        return _erro(422, "parametro_obrigatorio",
                     "lat e lon sao obrigatorios", campo="lat")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return _erro(422, "coordenada_invalida",
                     "lat -90..90 e lon -180..180")
    try:
        raio = int(params.get("raio", config.DEFAULT_RAIO))
    except (TypeError, ValueError):
        return _erro(422, "raio_invalido",
                     "raio inteiro " + config.RAIO_FAIXA_TXT)
    if raio < config.MIN_RAIO or raio > config.MAX_RAIO:
        return _erro(422, "raio_invalido", "raio " + config.RAIO_FAIXA_TXT)
    try:
        limite = int(params.get("limite", config.DEFAULT_LIMITE))
    except (TypeError, ValueError):
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    if limite < config.MIN_LIMITE or limite > config.MAX_LIMITE:
        return _erro(422, "limite_invalido", "limite 1..1000")

    filtros = {}
    if params.get("uf"):
        filtros["uf"] = str(params["uf"])
    if params.get("municipio_ibge"):
        filtros["municipio_ibge"] = str(params["municipio_ibge"])
    if params.get("rodovia"):
        filtros["rodovia"] = str(params["rodovia"])
    for nome in ("tipo_radar", "sentido", "modalidade"):
        if params.get(nome):
            filtros[nome] = str(params[nome])
    try:
        filtros["incluir_inativos"] = _bool_param(
            params.get("incluir_inativos"), False)
        filtros["incluir_operacoes"] = _bool_param(
            params.get("incluir_operacoes"), True)
        incluir_trechos = _bool_param(params.get("incluir_trechos"), False)
    except ValueError as exc:
        return _erro(422, "parametro_invalido", str(exc))
    fp = params.get("fiscalizacao_pontual")
    if fp not in (None, ""):
        try:
            filtros["fiscalizacao_pontual"] = _bool_param(fp, None)
        except ValueError as exc:
            return _erro(422, "parametro_invalido", str(exc), campo="fiscalizacao_pontual")

    records, res = consultas.buscar_pontos(
        conn, lat, lon, raio, filtros, limite, params.get("cursor"))
    st = consultas.status_base(conn)

    operacoes = []
    for registro in records:
        operacoes.extend(registro.get("operacoes") or [])
    res["operacoes"] = operacoes
    res["total_operacoes"] = len(operacoes)
    ##-- BUNDITA DE URSO #{10} -- Encontrar um ponto nao comprova cobertura completa do territorio. ##
    res["status"] = "parcial" if res["total_pontos"] else "sem_cobertura"
    res["encontrado"] = bool(res["total_pontos"])

    if incluir_trechos:
        trechos, tres = consultas.buscar_trechos(
            conn, lat, lon, raio, filtros, limite, None)
        res["trechos"] = trechos
        res["total_trechos"] = tres["total_trechos"]

    meta = _envelope(st, {"lat": lat, "lon": lon, "raio_metros": raio,
                          "filtros": filtros}, res)
    ctype, corpo = serialize(formato, records, meta, delimitador=delimitador)
    headers = {"Content-Type": ctype}
    headers.update(_headers_radar(meta, 200))
    return 200, headers, corpo


def _ponto(conn, ident, formato, delimitador):
    registro = consultas.buscar_ponto_por_id(conn, ident)
    if registro is None:
        return _erro(404, "ponto_nao_encontrado",
                     "ponto %s nao encontrado" % ident)
    from core.assistencia import resumo_local
    registro["explicacao"] = resumo_local(registro)
    st = consultas.status_base(conn)
    meta = _base_meta()
    meta["consultado_em"] = _agora()
    meta["consulta"] = {"id": ident}
    meta["resultado"] = {"total_pontos": 1, "total_equipamentos":
                         len(registro.get("equipamentos") or []),
                         "retornados": 1, "proximo_cursor": None,
                         "status": "completo", "total_operacoes": 0,
                         "operacoes": []}
    meta["base"]["snapshot_id"] = st["snapshot_id"]
    meta["base"]["publicado_em"] = st["publicado_em"]
    ctype, corpo = serialize(formato, [registro], meta, delimitador=delimitador)
    headers = {"Content-Type": ctype}
    headers.update(_headers_radar(meta, 200))
    return 200, headers, corpo


# ---------------------------------------------------------------------------
# Envelope e serializacao tabular dos endpoints nao-tabulares
# ---------------------------------------------------------------------------
def _envelope(st, consulta, resultado):
    meta = _base_meta()
    meta["consultado_em"] = _agora()
    meta["consulta"] = consulta
    meta["resultado"] = resultado
    meta["cobertura"]["fontes_ativas"] = [f["nome"] for f in st["fontes"]]
    meta["base"]["snapshot_id"] = st["snapshot_id"]
    meta["base"]["publicado_em"] = st["publicado_em"]
    ##-- BUNDITA DE URSO #{10} -- Ter snapshot nao demonstra atualidade das publicacoes de origem. ##
    meta["base"]["status_cache"] = "desconhecido" if st["snapshot_id"] else "sem_cache"
    return meta


def _envelope_dict(meta):
    """Mesma forma do envelope JSON dos endpoints existentes (sem injetar
    'pontos': a colecao e propria de cada endpoint)."""
    env = {
        "sucesso": meta.get("sucesso", True),
        "versao_api": meta.get("versao_api"),
        "versao_esquema": meta.get("versao_esquema"),
        "consultado_em": meta.get("consultado_em"),
        "consulta": meta.get("consulta", {}),
        "resultado": meta.get("resultado", {}),
        "cobertura": meta.get("cobertura", {}),
        "base": meta.get("base", {}),
    }
    return env


def _linha_por_colunas(reg, colunas):
    """Projeta um registro nas colunas fixas do endpoint. Colunas '*_json'
    apontam para o campo aninhado correspondente (arrays/objetos -> JSON)."""
    linha = []
    for c in colunas:
        if c.endswith("_json"):
            linha.append(reg.get(c[:-5]))
        else:
            linha.append(reg.get(c))
    return linha


def _texto_tabela(rows, delim):
    linhas = [delim.join(txt_ser.formatar_celula(c, delim) for c in row)
              for row in rows]
    return ("\n".join(linhas) + "\n") if linhas else ""


def _resposta_tabela(formato, envelope, rows, colunas, delimitador, meta):
    if formato in ("json", "ndjson", "xml"):
        corpo, ctype = serializa_objeto(formato, envelope)
    elif formato == "txt":
        corpo = _texto_tabela(rows, delimitador)
        ctype = "text/plain; charset=utf-8"
    elif formato in ("edi", "edifact"):
        corpo = edifact_ser.dumps_celulas(rows, meta)
        ctype = "application/EDIFACT; charset=utf-8"
    else:  # dif
        corpo = dif_ser.dumps_celulas(rows, colunas, meta)
        ctype = "text/plain; charset=utf-8"
    headers = {"Content-Type": ctype}
    headers.update(_headers_radar(meta, 200))
    return 200, headers, corpo


def _param_raio(params):
    try:
        raio = int(params.get("raio", config.DEFAULT_RAIO))
    except (TypeError, ValueError):
        return None
    if raio < config.MIN_RAIO or raio > config.MAX_RAIO:
        return None
    return raio


def _param_limite(params):
    try:
        limite = int(params.get("limite", config.DEFAULT_LIMITE))
    except (TypeError, ValueError):
        return None
    if limite < config.MIN_LIMITE or limite > config.MAX_LIMITE:
        return None
    return limite


def _coord(params):
    """Le lat/lon/raio opcionais. Retorna (lat, lon, raio, erro)."""
    if not (params.get("lat") or params.get("lon")):
        return None, None, None, None
    try:
        lat = float(params["lat"])
        lon = float(params["lon"])
    except (KeyError, TypeError, ValueError):
        return None, None, None, _erro(
            422, "parametro_obrigatorio", "lat e lon sao obrigatorios juntos",
            campo="lat")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, None, _erro(
            422, "coordenada_invalida", "lat -90..90 e lon -180..180")
    raio = _param_raio(params)
    if raio is None:
        return None, None, None, _erro(
            422, "raio_invalido", "raio inteiro " + config.RAIO_FAIXA_TXT)
    return lat, lon, raio, None


# ---------------------------------------------------------------------------
# /api/v1/radares/busca — BUSCA CADASTRAL (sem coordenada)
# ---------------------------------------------------------------------------
def _busca(conn, params, formato, delimitador):
    filtros = {}
    for nome in ("uf", "municipio_ibge", "rodovia", "tipo_radar",
                 "modalidade"):
        if params.get(nome):
            filtros[nome] = str(params[nome])
    try:
        filtros["incluir_inativos"] = _bool_param(
            params.get("incluir_inativos"), False)
    except ValueError as exc:
        return _erro(422, "parametro_invalido", str(exc))
    limite = _param_limite(params)
    if limite is None:
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    records, res = consultas.buscar_cadastral(
        conn, filtros, limite, params.get("cursor"))
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": bool(res["total_pontos"]),
        "total_pontos": res["total_pontos"],
        "total_equipamentos": sum(len(r.get("equipamentos") or [])
                                  for r in records),
        "retornados": res["retornados"],
        "proximo_cursor": res["proximo_cursor"],
        "total_operacoes": 0, "operacoes": [], "trechos": [],
        "pontos": records,
        "status": "parcial",
    }
    meta = _envelope(st, {"filtros": filtros, "busca": "cadastral"},
                     resultado)
    rows = [_linha_por_colunas(r, campos.TXT_COLUMNS) for r in records]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(campos.TXT_COLUMNS), delimitador, meta)


# ---------------------------------------------------------------------------
# /api/v1/trafego — OBSERVACAO AGREGADA (nao e limite legal)
# ---------------------------------------------------------------------------
def _trafego(conn, params, formato, delimitador):
    limite = _param_limite(params)
    if limite is None:
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    ponto_id = None
    if params.get("ponto_id"):
        try:
            ponto_id = int(str(params["ponto_id"]).upper().replace("P-", ""))
        except (TypeError, ValueError):
            return _erro(422, "parametro_invalido", "ponto_id invalido",
                         campo="ponto_id")
    records, res = consultas.buscar_trafego(
        conn, limite, ponto_id, params.get("cursor"))
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": bool(res["total_observacoes"]),
        "total_observacoes": res["total_observacoes"],
        "retornados": res["retornados"],
        "proximo_cursor": res["proximo_cursor"],
        "total_pontos": 0, "total_equipamentos": 0, "total_operacoes": 0,
        "pontos": [], "operacoes": [], "trechos": [],
        "observacoes_trafego": records,
        "status": "parcial",
        "aviso": ("velocidade_observada_kmh e velocidade de PASSAGEM, "
                  "nunca limite regulamentado da via"),
    }
    meta = _envelope(st, {"ponto_id": ponto_id}, resultado)
    rows = [_linha_por_colunas(o, COLS_TRAFEGO) for o in records]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(COLS_TRAFEGO), delimitador, meta)


# ---------------------------------------------------------------------------
# /api/v1/trechos — TRECHO ELEGIVEL (nao e radar nem operacao confirmada)
# ---------------------------------------------------------------------------
def _trechos(conn, params, formato, delimitador):
    filtros = {}
    for nome in ("uf", "municipio_ibge", "rodovia", "sentido"):
        if params.get(nome):
            filtros[nome] = str(params[nome])
    limite = _param_limite(params)
    if limite is None:
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    lat, lon, raio, erro = _coord(params)
    if erro is not None:
        return erro
    records, res = consultas.buscar_trechos(
        conn, lat, lon, raio, filtros, limite, params.get("cursor"))
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": bool(res["total_trechos"]),
        "total_trechos": res["total_trechos"],
        "retornados": res["retornados"],
        "proximo_cursor": res["proximo_cursor"],
        "total_pontos": 0, "total_equipamentos": 0, "total_operacoes": 0,
        "pontos": [], "operacoes": [], "trechos": records,
        "status": "completo" if res["total_trechos"] else "sem_cobertura",
    }
    meta = _envelope(st, {"lat": lat, "lon": lon, "raio_metros": raio,
                          "filtros": filtros}, resultado)
    rows = [_linha_por_colunas(t, COLS_TRECHOS) for t in records]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(COLS_TRECHOS), delimitador, meta)


# ---------------------------------------------------------------------------
# /api/v1/operacoes — OPERACAO DE FISCALIZACAO (so o que a fonte publica)
# ---------------------------------------------------------------------------
def _operacoes(conn, params, formato, delimitador):
    filtros = {}
    for nome in ("uf", "municipio_ibge", "rodovia", "modalidade"):
        if params.get(nome):
            filtros[nome] = str(params[nome])
    if params.get("em"):
        filtros["em"] = str(params["em"])
    limite = _param_limite(params)
    if limite is None:
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    lat, lon, raio, erro = _coord(params)
    if erro is not None:
        return erro
    records, res = consultas.buscar_operacoes(
        conn, lat, lon, raio, filtros, limite, params.get("cursor"))
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": bool(res["total_operacoes"]),
        "total_operacoes": res["total_operacoes"],
        "retornados": res["retornados"],
        "proximo_cursor": res["proximo_cursor"],
        "total_pontos": 0, "total_equipamentos": 0,
        "pontos": [], "trechos": [], "operacoes": records,
        "status": "completo" if res["total_operacoes"] else "sem_cobertura",
    }
    meta = _envelope(st, {"lat": lat, "lon": lon, "raio_metros": raio,
                          "filtros": filtros}, resultado)
    rows = [_linha_por_colunas(o, COLS_OPERACOES) for o in records]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(COLS_OPERACOES), delimitador, meta)


# ---------------------------------------------------------------------------
# /api/v1/equipamentos/{id} — EQUIPAMENTO FISICO
# ---------------------------------------------------------------------------
def _equipamento(conn, ident, formato, delimitador):
    reg = consultas.buscar_equipamento_por_id(conn, ident)
    if reg is None:
        return _erro(404, "equipamento_nao_encontrado",
                     "equipamento %s nao encontrado" % ident)
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": True, "total_equipamentos": 1, "retornados": 1,
        "proximo_cursor": None, "total_pontos": 0, "total_operacoes": 0,
        "pontos": [], "operacoes": [], "equipamento": reg,
        "status": "completo",
    }
    meta = _envelope(st, {"id": reg["id"]}, resultado)
    rows = [_linha_por_colunas(reg, COLS_EQUIPAMENTO)]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(COLS_EQUIPAMENTO), delimitador, meta)


# ---------------------------------------------------------------------------
# /api/v1/atualizacoes — historico de execucoes e snapshots por fonte
# ---------------------------------------------------------------------------
def _atualizacoes(conn, params, formato, delimitador):
    filtros = {}
    for nome in ("fonte", "recurso", "status"):
        if params.get(nome):
            filtros[nome] = str(params[nome])
    if params.get("fonte_id"):
        try:
            filtros["fonte_id"] = int(
                str(params["fonte_id"]).upper().replace("S-", ""))
        except (TypeError, ValueError):
            return _erro(422, "parametro_invalido", "fonte_id invalido",
                         campo="fonte_id")
    limite = _param_limite(params)
    if limite is None:
        return _erro(422, "limite_invalido", "limite inteiro 1..1000")
    records, res = consultas.listar_atualizacoes(
        conn, filtros, limite, params.get("cursor"))
    snaps = consultas.listar_snapshots(conn)
    st = consultas.status_base(conn)
    resultado = {
        "encontrado": bool(res["total_atualizacoes"]),
        "total_atualizacoes": res["total_atualizacoes"],
        "retornados": res["retornados"],
        "proximo_cursor": res["proximo_cursor"],
        "total_pontos": 0, "total_equipamentos": 0, "total_operacoes": 0,
        "pontos": [], "operacoes": [], "atualizacoes": records,
        "snapshots": snaps,
        "status": "completo" if res["total_atualizacoes"] else "sem_cobertura",
    }
    meta = _envelope(st, {"filtros": filtros}, resultado)
    rows = [_linha_por_colunas(r, COLS_ATUALIZACOES) for r in records]
    return _resposta_tabela(formato, _envelope_dict(meta), rows,
                            list(COLS_ATUALIZACOES), delimitador, meta)


def _fonte_id(conn, ident, formato, delimitador):
    fonte = consultas.buscar_fonte_por_id(conn, ident)
    if fonte is None:
        return _erro(404, "fonte_nao_encontrada",
                     "fonte %s nao encontrada" % ident)
    st = consultas.status_base(conn)
    meta = _envelope(st, {"id": fonte["id"]}, {"encontrado": True,
                                                 "fonte": fonte})
    try:
        corpo, ctype = serializa_objeto(formato, _envelope_dict(meta))
    except ValueError as exc:
        return _erro(400, "formato_invalido", str(exc))
    return 200, {"Content-Type": ctype}, corpo


# ---------------------------------------------------------------------------
# Entry point CGI
# ---------------------------------------------------------------------------
def _emitir(status, headers, corpo):
    if isinstance(corpo, (dict, list)):
        corpo = json.dumps(corpo, ensure_ascii=False, separators=(",", ":"),
                           default=str)
    if isinstance(corpo, str):
        corpo_b = corpo.encode("utf-8")
    else:
        corpo_b = corpo
    reason = STATUS_REASON.get(status, "OK")
    out = sys.stdout.buffer
    out.write(("Status: %d %s\r\n" % (status, reason)).encode("ascii"))
    for k, v in headers.items():
        out.write(("%s: %s\r\n" % (k, v)).encode("utf-8"))
    out.write(("Content-Length: %d\r\n" % len(corpo_b)).encode("ascii"))
    out.write(b"\r\n")
    out.write(corpo_b)
    out.flush()


def main(environ=None):
    environ = environ if environ is not None else os.environ
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        n = 0
    stdin_bytes = sys.stdin.buffer.read(n) if n > 0 else b""
    try:
        status, headers, corpo = handle_request(environ, stdin_bytes)
    except Exception as exc:                       # noqa: BLE001
        status, headers, corpo = _erro(500, "erro_interno", str(exc))
    _emitir(status, headers, corpo)


if __name__ == "__main__":
    from core.cliente_api import executar
    raise SystemExit(executar([], sys.argv[1:]))
