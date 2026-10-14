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
from core.serializers import campos, txt_ser, json_ser, xml_ser

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
    ("raio", "inteiro", False, "1..50000", "raio em metros (padrao 1000)"),
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
    ("limite", "inteiro", False, "1..1000", "itens por pagina (padrao 100)"),
    ("cursor", "string", False, "opaco", "cursor estavel de paginacao"),
    ("versao_esquema", "string", False, "string", "versao de contrato"),
]

ENDPOINTS_AJUDA = {
    "/api/v1/radares": ["GET", "POST"],
    "/api/v1/radares/{id}": ["GET"],
    "/api/v1/ajuda": ["GET", "POST"],
    "/api/v1/status": ["GET", "POST"],
    "/api/v1/fontes": ["GET"],
}


def ajuda_estrutura():
    return {
        "versao_api": config.API_VERSION,
        "versao_esquema": config.SCHEMA_VERSION,
        "endpoints": ENDPOINTS_AJUDA,
        "parametros": [
            {"nome": n, "tipo": t, "obrigatorio": o, "aceitos": a,
             "descricao": d} for (n, t, o, a, d) in PARAMS],
        "formatos": list(FORMATOS),
        "txt_colunas_ordem": list(campos.TXT_COLUMNS),
        "txt_colunas": [
            {"posicao": i + 1, "nome": c, "descricao":
             campos.TXT_COLUMNS_DESC.get(c, "")}
            for i, c in enumerate(campos.TXT_COLUMNS)],
        "txt_null": "\\N",
        "txt_delimitador_padrao": "|",
    }


def ajuda_texto():
    linhas = ["RADAR BRASIL - AJUDA v%s" % config.API_VERSION, ""]
    linhas.append("ENDPOINTS:")
    for ep, metodos in ENDPOINTS_AJUDA.items():
        linhas.append("  %-28s %s" % (ep, "/".join(metodos)))
    linhas.append("")
    linhas.append("PARAMETROS DE /api/v1/radares:")
    for (n, t, o, a, d) in PARAMS:
        linhas.append("  %-18s %-9s %-3s aceitos=%-22s %s" % (
            n, t, "sim" if o else "nao", a, d))
    linhas.append("")
    linhas.append("FORMATOS: %s" % ", ".join(FORMATOS))
    linhas.append("")
    linhas.append("ORDEM CANONICA TXT v1 (32 colunas, delimitador '%s', "
                  "NULL=\\N):" % "|")
    for i, c in enumerate(campos.TXT_COLUMNS):
        linhas.append("  %02d %-32s %s" % (
            i + 1, c, campos.TXT_COLUMNS_DESC.get(c, "")))
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Serializacao genérica para endpoints nao-tabulares (ajuda/status/fontes)
# ---------------------------------------------------------------------------
def _wrap_edifact(texto):
    from core.serializers import edifact_ser
    linhas = texto.rstrip("\n").split("\n")
    agora = datetime.datetime.utcnow().strftime("%y%m%d:%H%M")
    ref = datetime.datetime.utcnow().strftime("%y%m%d%H%M%S")
    segs = ["UNB+UNOC:3+RADARBRASIL:ZZ+RECEPTOR:ZZ+%s+%s" % (agora, ref),
            "UNH+%s+GENRAL:D:96A:UN" % ref]
    for ln in linhas:
        segs.append("FTX" + "+" + edifact_ser._esc(ln))
    segs.append("UNT+%d+%s" % (len(segs) + 1, ref))
    segs.append("UNZ+1+%s" % ref)
    return "'".join(segs) + "'\n"


def _wrap_dif(texto):
    from core.serializers import dif_ser
    linhas = texto.rstrip("\n").split("\n")
    out = ["TABLE", "0,1", '"AJUDA"', "VECTORS", "0,%d" % (len(linhas) + 1),
           '""', "TUPLES", "0,1", '""', "DATA", "0,0", '""']
    out.append('1,"linha"')
    for ln in linhas:
        out.append("-1,0")
        out.append('1,%s' % dif_ser._quote(ln))
    out.append("-1,0")
    out.append("EOD")
    return "\n".join(out) + "\n"


def serializa_objeto(formato, obj, texto=None, delimitador="|"):
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
        base = texto or json.dumps(obj, ensure_ascii=False, indent=2)
        return _wrap_edifact(base), "application/EDIFACT; charset=utf-8"
    if formato == "dif":
        base = texto or json.dumps(obj, ensure_ascii=False, indent=2)
        return _wrap_dif(base), "text/plain; charset=utf-8"
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
        return _erro(422, "raio_invalido", "raio inteiro 1..50000")
    if raio < config.MIN_RAIO or raio > config.MAX_RAIO:
        return _erro(422, "raio_invalido", "raio 1..50000")
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
    try:
        filtros["incluir_inativos"] = _bool_param(
            params.get("incluir_inativos"), False)
    except ValueError as exc:
        return _erro(422, "parametro_invalido", str(exc))

    records, res = consultas.buscar_pontos(
        conn, lat, lon, raio, filtros, limite, params.get("cursor"))
    st = consultas.status_base(conn)

    meta = _base_meta()
    meta["consultado_em"] = _agora()
    meta["consulta"] = {"lat": lat, "lon": lon, "raio_metros": raio,
                        "filtros": filtros}
    res["status"] = "completo" if res["total_pontos"] else "sem_cobertura"
    res.setdefault("total_operacoes", 0)
    res["operacoes"] = []
    meta["resultado"] = res
    meta["cobertura"]["fontes_ativas"] = [f["nome"] for f in st["fontes"]]
    meta["base"]["snapshot_id"] = st["snapshot_id"]
    meta["base"]["publicado_em"] = st["publicado_em"]
    meta["base"]["status_cache"] = "fresco" if st["snapshot_id"] else "sem_cache"

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
