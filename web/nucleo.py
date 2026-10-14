# -*- coding: utf-8 -*-
"""Nucleo CGI do Radar Brasil (Python puro, stdlib).

Le os.environ (REQUEST_METHOD, QUERY_STRING, CONTENT_LENGTH, PATH_INFO) e
stdin; emite headers + corpo. NENHUMA chamada a servico externo: consulta
somente o banco local ja validado (spec 13.1).
"""
import datetime
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config
from core import db as dbmod
from core import consultas
from core import geo
from core.serializers import serialize, is_valido, FORMATOS
from core.serializers import campos, txt_ser, json_ser, xml_ser, edifact_ser, dif_ser

_cls_txt = txt_ser

STATUS_REASON = {
    200: "OK", 400: "Bad Request", 404: "Not Found",
    405: "Method Not Allowed", 422: "Unprocessable Entity",
    503: "Service Unavailable", 500: "Internal Server Error",
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
    ("versao_esquema", "string", False, "string", "versao de contrato"),
]

ENDPOINTS_AJUDA = {
    "/api/v1/radares": ["GET", "POST"],
    "/api/v1/radares/busca": ["GET", "POST"],
    "/api/v1/radares/{id}": ["GET"],
    "/api/v1/trafego": ["GET", "POST"],
    "/api/v1/trechos": ["GET", "POST"],
    "/api/v1/operacoes": ["GET", "POST"],
    "/api/v1/equipamentos/{id}": ["GET"],
    "/api/v1/fontes": ["GET"],
    "/api/v1/fontes/{id}": ["GET"],
    "/api/v1/atualizacoes": ["GET"],
    "/api/v1/ajuda": ["GET", "POST"],
    "/api/v1/status": ["GET", "POST"],
    "/health/live": ["GET"],
    "/health/ready": ["GET"],
}

ENDPOINTS_ADMINISTRATIVOS = {
    "/api/v1/admin/sincronizar": ["POST"],
    "/api/v1/admin/rollback": ["POST"],
}

ENDPOINTS_DESC = {
    "/api/v1/radares": "Pontos de fiscalizacao (radar instalado) num raio.",
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
    return status, {"Content-Type": "application/json; charset=utf-8"}, body


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
            "status_cache": "fresco", "alertas": [],
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
        uri = environ.get("REQUEST_URI", "").split("?", 1)[0]
        script = environ.get("SCRIPT_NAME", "")
        if uri.startswith(script):
            caminho = uri[len(script):]
        else:
            caminho = uri
    if not caminho:
        caminho = "/"
    return caminho


def handle_request(environ, stdin_bytes=b""):
    metodo = environ.get("REQUEST_METHOD", "GET").upper()
    caminho = _rota(environ)
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
    if caminho in ("/api/v1/ajuda", "/api/v1/ajuda/"):
        estrutura = ajuda_estrutura()
        try:
            corpo, ctype = serializa_objeto(formato, estrutura,
                                            texto=ajuda_texto())
        except ValueError as exc:
            return _erro(400, "formato_invalido", str(exc))
        return 200, {"Content-Type": ctype}, corpo

    # --- endpoints com banco -------------------------------------------------
    conn = _conn()
    if caminho in ("/health/ready", "/api/v1/health/ready"):
        if conn is None:
            return 503, {"Content-Type": "application/json; charset=utf-8"}, \
                {"status": "not-ready", "motivo": "banco ausente"}
        conn.close()
        return 200, {"Content-Type": "application/json; charset=utf-8"}, {"status": "ready"}

    if conn is None:
        return _erro(503, "snapshot_indisponivel",
                     "banco local ausente ou nao inicializado")

    try:
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
    res["status"] = "completo" if res["total_pontos"] else "sem_cobertura"
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
    meta["base"]["status_cache"] = "fresco" if st["snapshot_id"] else "sem_cache"
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
    main()
