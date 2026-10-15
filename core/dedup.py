# -*- coding: utf-8 -*-
"""Deduplicacao rastreavel (spec secao 8 e 17.4).

API pura sobre uma conexao SQLite ja inicializada (core.db). Nada aqui monta
SQL com valores do usuario sem parametrizacao, nada apaga dado de origem e o
modulo NAO faz ligacao no pipeline: quem chama decide quando rodar.

Modelo de rastreabilidade usado (tabelas ja existentes no schema):

  REGISTRO_FONTE (T59) -- artefato (T57) -- RECURSO_FONTE (T56) -- FONTE (T54)
  VALOR_OBSERVADO (T72) fornece os valores normalizados por campo/campo_id.

Conceitos centrais da spec:
  * CADEIA DE EVIDENCIA (17.4-3): dois registros com o MESMO artefato
    (mesmo hash de arquivo) ou o MESMO registro bruto (mesmo hash_registro)
    sao copias da MESMA origem -> contam como UMA prova, nunca duas.
    O "recurso primario" e o recurso de menor id que compartilha o hash.
  * MESMA COORDENADA entre fontes = CANDIDATO, nunca decisao automatica
    (17.4-4 / 8.4): `gerar_candidatos` sempre grava estado 'pendente'.
  * MESMA SERIE em varias faixas = UM equipamento + MULTIPLAS faixas
    (17.4-5): `aplicar` liga todos os registros ao mesmo equipamento
    canonico, sem apagar as faixas nem os equipamentos de origem.
  * DIVERGENCIA oficial/comunitaria NAO sobrescreve dado oficial
    (17.4-5/6): `aplicar` nunca faz UPDATE/DELETE em POSICAO_GEOGRAFICA,
    FONTE ou REGISTRO_FONTE; registra a divergencia na evidencia.
  * HISTORICO METROLOGICO nao duplica por faixa (17.4-9):
    `verificacoes_duplicadas` apenas REPORTA o que ja esta duplicado.

Reversao: as ligacoes criadas por `aplicar` carregam o `decisao_id` das
tabelas VINCULO_* (T63..T66). `reverter_decisao` marca `revertida_em` e apaga
SOMENTE essas ligacoes; a linha de DECISAO_DUPLICIDADE permanece (auditoria).
"""
import datetime
import json
import math
import re
import unicodedata

from . import db as dbmod
from . import geo
from . import identidade
from .domains import UFS

__all__ = [
    "normalizar_texto", "normalizar_serie", "normalizar_rodovia",
    "normalizar_km", "normalizar_sentido", "serie_generica",
    "cadeia_evidencia", "mesma_cadeia", "evidencias_independentes",
    "atributos_registro", "pontuar", "avaliar_escopos", "gerar_candidatos", "candidatos",
    "decidir", "decisao_ativa", "listar_decisoes", "aplicar",
    "reverter_decisao", "verificacoes_duplicadas", "classificacao_evidencia",
    "registrar_regra",
]

# --------------------------------------------------------------- constantes

##-- BUNDITA DE URSO #{4} -- Regras alteradas precisam de nova versao para nao reutilizar evidencias antigas. ##
##-- BUNDITA DE URSO #{26} -- A fila passa a avaliar separadamente a identidade do ponto e a do instrumento, sem reutilizar a regra antiga. ##
VERSAO_REGRA_PADRAO = "dedup-1.2"

# Pesos versionaveis (spec 8.5: definir e versionar apos inspecionar amostras).
PESOS_PADRAO = {
    "serie": 0.45,
    "proximidade": 0.30,
    "via_km": 0.15,
    "sentido": 0.05,
    "corroboracao_independente": 0.05,
}

LIMIAR_FORTE = 0.75
LIMIAR_MODERADO = 0.30
LIMIAR_MIN_CANDIDATO = 0.20

RAIO_CANDIDATO_M = 2000.0
# (limite em metros, fator de proximidade) - jamais "<=10 m => mesmo radar".
FAIXAS_PROXIMIDADE = ((50.0, 1.0), (200.0, 0.7), (1000.0, 0.35), (5000.0, 0.10))
TOLERANCIA_KM = 0.5       # km considerado "o mesmo"
CONFLITO_KM = 5.0         # acima disso, mesma via = contradicao
TOLERANCIA_POSICAO_M = 1.0
# Numero curto (< isto) nao tem contexto suficiente para identidade global.
SERIE_CURTA_MAX_DIGITOS = 4
DISTANCIA_REVISAO_PONTO_M = 200.0


def serie_generica(numero_serie, municipios=None):
    """True quando o valor nao sustenta identidade global sem contexto.

    Ausencia e numeros curtos nao pontuam como identidade. `municipios` e
    mantido por compatibilidade, mas mover um instrumento entre municipios
    nao invalida sua serie. Nenhum desses sinais comprova aparelho distinto.
    """
    if not numero_serie:
        return True
    s = str(numero_serie)
    if s.isdigit() and len(s) < SERIE_CURTA_MAX_DIGITOS:
        return True
    ##-- BUNDITA DE URSO #{5} -- Um aparelho pode mudar de municipio; repeticao nao invalida sua serie. ##
    return False

_ESTADO_POR_DECISAO = {
    "unificar": "decidido_unificar",
    "manter_separados": "decidido_manter_separados",
    "revisar": "revisar",
}

CAMPO_ALIASES = {
    "latitude": {"latitude", "lat"},
    "longitude": {"longitude", "lon", "lng", "long"},
    "numero_serie": {"numero_serie", "numeroserie", "serie", "serial", "numero_de_serie", "ns"},
    "uf": {"uf", "uf_sigla", "estado", "siglauf", "sigla_uf"},
    "fabricante": {"fabricante", "marca"},
    "modelo": {"modelo"},
    "rodovia": {"rodovia", "via"},
    "km": {"km", "quilometro", "quilometragem"},
    "sentido": {"sentido", "sentido_original"},
}

_SERIE_VAZIA = {"SN", "SNUMERO", "SEMNUMERO", "NAOAPLICAVEL", "NA", "NAN"}

_SENTIDOS = {
    "crescente": "crescente",
    "sentido crescente": "crescente",
    "decrescente": "decrescente",
    "sentido decrescente": "decrescente",
    "ambos": "ambos",
    "ambos os sentidos": "ambos",
    "bidirecional": "ambos",
    "duplo": "ambos",
    "both": "ambos",
}


# --------------------------------------------------------------- utilitarios

def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def _primeiro(*valores):
    for v in valores:
        if v is not None and v != "":
            return v
    return None


##-- BUNDITA DE URSO #{18} -- NaN e infinito vindos da fonte podiam quebrar a indexacao geografica. ##
def _num(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        numero = float(valor)
        return numero if math.isfinite(numero) else None
    try:
        numero = float(str(valor).strip().replace(",", "."))
        return numero if math.isfinite(numero) else None
    except (TypeError, ValueError):
        return None


def _load_json(texto):
    try:
        obj = json.loads(texto) if texto else {}
    except (TypeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _achatar(obj, prefixo=""):
    """Achata um JSON aninhado em {chave_normalizada: escalar}."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_achatar(v, k))
    elif isinstance(obj, list):
        for item in obj:
            out.update(_achatar(item, prefixo))
    else:
        if prefixo:
            out[_normaliza_chave(prefixo)] = obj
    return out


def _normaliza_chave(nome):
    nome = normalizar_texto(nome) or ""
    return re.sub(r"\s+", "_", nome.lower())


def _extrair(flat, alvo):
    for k, v in flat.items():
        if k in CAMPO_ALIASES[alvo] and v not in (None, ""):
            return v
    return None


# ------------------------------------------------------------- normalizacao

def normalizar_texto(valor):
    """Caixa alta, sem acentos, espacos colapsados (spec 8.2). None se vazio."""
    if valor is None:
        return None
    s = unicodedata.normalize("NFKD", str(valor))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s or None


##-- BUNDITA DE URSO #{24} -- ESTADO na PRF e situacao operacional; ATIVO nao pode substituir a UF publicada. ##
_UF_POR_NOME = {normalizar_texto(nome): sigla for sigla, nome in UFS}
_UF_SIGLAS = {sigla for sigla, _ in UFS}


def _uf_valida(valor):
    texto = normalizar_texto(valor)
    return texto if texto in _UF_SIGLAS else _UF_POR_NOME.get(texto)


def _uf_payload(payload):
    for chave in ("uf", "uf_sigla", "siglauf", "sigla_uf", "estado"):
        uf = _uf_valida(payload.get(chave))
        if uf:
            return uf
    return None


def normalizar_serie(valor):
    """Numero de serie: remove prefixos, separadores e zeros a esquerda.

    'S-N 1539' e 's1539' -> 'S1539'. 'S/N'/'sem numero' -> None.
    """
    if valor is None:
        return None
    s = normalizar_texto(valor)
    if not s:
        return None
    s = re.sub(r"[^A-Z0-9]", "", s)
    if not s or s in _SERIE_VAZIA:
        return None
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s or None


def normalizar_rodovia(valor):
    """'BR-277' / 'BR277' / 'br 277' -> 'BR-277'."""
    if valor is None:
        return None
    s = normalizar_texto(valor)
    if not s:
        return None
    m = re.match(r"^([A-Z]+)[\s\-]*0*(\d+)", s)
    if m:
        return "%s-%s" % (m.group(1), m.group(2))
    return re.sub(r"[^A-Z0-9]", "", s) or None


##-- BUNDITA DE URSO #{18} -- Quilometragem numerica nao finita tambem precisa ser descartada. ##
def normalizar_km(valor):
    """Aceita virgula decimal, ponto e sufixo 'km' (spec 8.2)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return _num(valor)
    s = str(valor).strip().lower().replace("km", "").replace("\u00a0", "")
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


##-- BUNDITA DE URSO #{7} -- Decrescente contem crescente; testar primeiro evitava inverter o sentido. ##
def normalizar_sentido(valor):
    """Sentido canonico: crescente|decrescente|ambos|desconhecido."""
    if valor is None:
        return None
    s = normalizar_texto(valor)
    if not s:
        return None
    chave = s.lower()
    if chave in _SENTIDOS:
        return _SENTIDOS[chave]
    if "decrescente" in chave:
        return "decrescente"
    if "crescente" in chave:
        return "crescente"
    if "ambos" in chave or "bidi" in chave:
        return "ambos"
    return "desconhecido"


# ---------------------------------------------------------------- linhagem

def _base_registro(conn, registro_id):
    return dbmod.query_one(conn, """
        SELECT r.id AS registro_id, r.artefato_id, r.identificador_na_fonte,
               r.hash_registro, r.payload_original,
               a.hash_sha256 AS artefato_hash, a.recurso_id,
               rf.fonte_id, rf.nome AS recurso_nome, rf.url_recurso,
               f.natureza_id, nf.codigo AS natureza
        FROM REGISTRO_FONTE r
        JOIN ARTEFATO_COLETA a ON a.id = r.artefato_id
        JOIN RECURSO_FONTE rf ON rf.id = a.recurso_id
        JOIN FONTE f ON f.id = rf.fonte_id
        JOIN NATUREZA_FONTE nf ON nf.id = f.natureza_id
        WHERE r.id = ?""", (registro_id,))


def cadeia_evidencia(conn, registro_id):
    """Cadeia de evidencia de um REGISTRO_FONTE (spec 17.4-3).

    A chave e o hash do artefato: dois recursos/mirrors que baixaram o MESMO
    arquivo formam UMA cadeia. `recurso_primario_id` e o recurso de menor id
    que compartilha o hash (origem presumida).
    """
    base = _base_registro(conn, registro_id)
    if base is None:
        raise ValueError("REGISTRO_FONTE %r inexistente" % (registro_id,))
    h = base["artefato_hash"]
    prim = dbmod.scalar(
        conn, "SELECT MIN(rf.id) FROM ARTEFATO_COLETA a "
              "JOIN RECURSO_FONTE rf ON rf.id = a.recurso_id "
              "WHERE a.hash_sha256 = ?", (h,))
    fontes = [r[0] for r in dbmod.query_all(
        conn, "SELECT DISTINCT rf.fonte_id FROM ARTEFATO_COLETA a "
              "JOIN RECURSO_FONTE rf ON rf.id = a.recurso_id "
              "WHERE a.hash_sha256 = ? ORDER BY rf.fonte_id", (h,))]
    return {
        "chave": "art:%s" % h,
        "registro_id": registro_id,
        "artefato_hash": h,
        "recurso_id": base["recurso_id"],
        "recurso_primario_id": prim,
        "fonte_ids": fontes,
        "natureza": base["natureza"],
        "hash_registro": base["hash_registro"],
        "identificador_na_fonte": base["identificador_na_fonte"],
    }


def mesma_cadeia(conn, registro_a, registro_b):
    """True se os dois registros vem da MESMA origem (cadeia de evidencia).

    Espelho: mesmo hash de artefato; copia: mesmo hash_registro; mesmo
    recurso: mesmo arquivo baixado.
    """
    ca = cadeia_evidencia(conn, registro_a)
    cb = cadeia_evidencia(conn, registro_b)
    if ca["chave"] == cb["chave"]:
        return True
    if ca["hash_registro"] and ca["hash_registro"] == cb["hash_registro"]:
        return True
    if ca["recurso_id"] == cb["recurso_id"]:
        return True
    return False


##-- BUNDITA DE URSO #{6} -- Contar apenas arquivos diferentes superestimava a independencia da evidencia. ##
def evidencias_independentes(conn, registro_ids):
    """Numero de cadeias de evidencia distintas entre os registros dados."""
    # Union-find por chaves evita comparar todos os registros entre si.
    parents, vistos = {}, {}

    def raiz(item):
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    for rid in dict.fromkeys(registro_ids):
        parents[rid] = rid
        cadeia = cadeia_evidencia(conn, rid)
        for nome in ("chave", "recurso_id", "hash_registro"):
            valor = cadeia[nome]
            if valor is None:
                continue
            chave = (nome, valor)
            if chave in vistos:
                parents[raiz(rid)] = raiz(vistos[chave])
            vistos[chave] = rid
    return len({raiz(rid) for rid in parents})



# ------------------------------------------------------------- atributos

##-- BUNDITA DE URSO #{17} -- Vinculos de decisoes anteriores nao podem servir de prova para a proxima decisao. ##
def atributos_registro(conn, registro_id):
    """Atributos normalizados de um registro (spec 8.2), sem alterar o dado.

    Valores observados e payload original precedem entidades mutaveis.
    Coordenadas normalizadas da propria observacao mantem precedencia.
    Vinculos derivados de outras decisoes nunca alimentam a comparacao.
    """
    base = _base_registro(conn, registro_id)
    if base is None:
        raise ValueError("REGISTRO_FONTE %r inexistente" % (registro_id,))

    at = {
        "registro_id": registro_id,
        "artefato_id": base["artefato_id"],
        "fonte_id": base["fonte_id"],
        "recurso_id": base["recurso_id"],
        "natureza": base["natureza"],
        "artefato_hash": base["artefato_hash"],
        "hash_registro": base["hash_registro"],
        "identificador_na_fonte": base["identificador_na_fonte"],
        "ponto_ids": identidade.originais(conn, "ponto", registro_id),
        "equipamento_ids": identidade.originais(conn, "equipamento", registro_id),
    }
    at["cadeia"] = cadeia_evidencia(conn, registro_id)["chave"]

    # 1) valores normalizados por campo (T72)
    valores = {}
    for row in dbmod.query_all(
            conn, "SELECT c.nome_campo AS campo, v.valor_normalizado AS vn, "
                  "v.valor_original AS vo FROM VALOR_OBSERVADO v "
                  "JOIN CATALOGO_CAMPO c ON c.id = v.campo_id "
                  "WHERE v.registro_id = ? ORDER BY v.id", (registro_id,)):
        nc = _normaliza_chave(row["campo"])
        for alvo, aliases in CAMPO_ALIASES.items():
            if nc in aliases and alvo not in valores:
                valor = row["vn"] if row["vn"] is not None else row["vo"]
                if valor not in (None, ""):
                    valores[alvo] = valor

    # 2) entidades ligadas
    lat = lon = precisao = qualidade = via = km = sentido = None
    pos = dbmod.query_one(conn, """
        SELECT p.latitude, p.longitude, p.precisao_metros, qp.codigo AS qualidade
        FROM POSICAO_GEOGRAFICA p
        JOIN QUALIDADE_POSICAO qp ON qp.id = p.qualidade_posicao_id
        WHERE p.registro_fonte_id = ?
        ORDER BY (qp.codigo = 'oficial') DESC, p.id LIMIT 1""", (registro_id,))
    if pos is not None:
        lat, lon = pos["latitude"], pos["longitude"]
        precisao, qualidade = pos["precisao_metros"], pos["qualidade"]
    posicao_observada = (lat, lon)

    for pid in at["ponto_ids"]:
        p = dbmod.query_one(conn, "SELECT * FROM PONTO_FISCALIZACAO WHERE id = ?",
                            (pid,))
        if p is None:
            continue
        if lat is None and p["posicao_id"] is not None:
            pp = dbmod.query_one(conn, """
                SELECT p.latitude, p.longitude, p.precisao_metros,
                       qp.codigo AS qualidade
                FROM POSICAO_GEOGRAFICA p
                JOIN QUALIDADE_POSICAO qp ON qp.id = p.qualidade_posicao_id
                WHERE p.id = ?""", (p["posicao_id"],))
            if pp is not None:
                lat, lon = pp["latitude"], pp["longitude"]
                precisao, qualidade = pp["precisao_metros"], pp["qualidade"]
        if via is None and p["via_id"] is not None:
            v = dbmod.query_one(conn, "SELECT codigo FROM VIA WHERE id = ?",
                                (p["via_id"],))
            if v is not None:
                via = v["codigo"]
        if km is None and p["km"] is not None:
            km = p["km"]
        if sentido is None:
            fx = dbmod.query_one(conn, """
                SELECT s.codigo AS codigo, f.sentido_original AS original
                FROM FAIXA_FISCALIZACAO f
                LEFT JOIN SENTIDO s ON s.id = f.sentido_id
                WHERE f.ponto_id = ? ORDER BY f.id LIMIT 1""", (pid,))
            if fx is not None:
                sentido = fx["codigo"] or fx["original"]

    serie = fabricante = modelo = None
    for eid in at["equipamento_ids"]:
        e = dbmod.query_one(conn, """
            SELECT e.numero_serie, m.nome_modelo, org.nome AS fabricante
            FROM EQUIPAMENTO e
            LEFT JOIN MODELO_EQUIPAMENTO m ON m.id = e.modelo_id
            LEFT JOIN ORGANIZACAO org ON org.id = m.fabricante_id
            WHERE e.id = ?""", (eid,))
        if e is None:
            continue
        if serie is None and e["numero_serie"]:
            serie = e["numero_serie"]
        if modelo is None and e["nome_modelo"]:
            modelo = e["nome_modelo"]
        if fabricante is None and e["fabricante"]:
            fabricante = e["fabricante"]

    # 3) payload original tem precedencia sobre entidades mutaveis por recoleta.
    payload = {}
    try:
        payload = _achatar(json.loads(base["payload_original"] or "{}"))
    except (TypeError, ValueError):
        payload = {}

    ##-- BUNDITA DE URSO #{24} -- GPS do ponto mutavel nao pode ocultar uma observacao original diferente e faze-la parecer historico equivalente. ##
    at["latitude"] = _num(_primeiro(valores.get("latitude"), posicao_observada[0],
                                    _extrair(payload, "latitude"), lat))
    at["longitude"] = _num(_primeiro(valores.get("longitude"), posicao_observada[1],
                                     _extrair(payload, "longitude"), lon))
    at["numero_serie"] = normalizar_serie(
        _primeiro(valores.get("numero_serie"), _extrair(payload, "numero_serie"), serie))
    at["fabricante"] = normalizar_texto(
        _primeiro(valores.get("fabricante"), _extrair(payload, "fabricante"), fabricante))
    at["modelo"] = normalizar_texto(
        _primeiro(valores.get("modelo"), _extrair(payload, "modelo"), modelo))
    at["rodovia"] = normalizar_rodovia(
        _primeiro(valores.get("rodovia"), _extrair(payload, "rodovia"), via))
    at["km"] = normalizar_km(
        _primeiro(valores.get("km"), _extrair(payload, "km"), km))
    at["sentido"] = normalizar_sentido(
        _primeiro(valores.get("sentido"), _extrair(payload, "sentido"), sentido))
    uf = None
    if at["ponto_ids"]:
        uf = dbmod.scalar(conn, "SELECT m.uf_sigla FROM PONTO_FISCALIZACAO p "
                          "JOIN MUNICIPIO m ON m.codigo_ibge=p.municipio_id WHERE p.id=?",
                          (at["ponto_ids"][0],))
    at["uf"] = (_uf_valida(valores.get("uf")) or _uf_payload(payload) or _uf_valida(uf))
    ##-- BUNDITA DE URSO #{24} -- Coordenadas fora da faixa nao servem como evidencia geografica, mesmo sendo numeros finitos. ##
    if (at["latitude"] is None or at["longitude"] is None
            or not -90 <= at["latitude"] <= 90 or not -180 <= at["longitude"] <= 180):
        at["latitude"] = at["longitude"] = None
    at["precisao_metros"] = precisao
    at["qualidade_posicao"] = qualidade
    at["serie_generica"] = serie_generica(at.get("numero_serie"))
    return at


# ------------------------------------------------------------- pontuacao

def _componente(nome, peso, fator, explicacao):
    return {"nome": nome, "peso": round(float(peso), 4),
            "fator": round(float(fator), 4),
            "contribuicao": round(float(peso) * float(fator), 4),
            "explicacao": explicacao}


##-- BUNDITA DE URSO #{4} -- Pesos invalidos ou incompletos nao podem produzir regra parcialmente registrada. ##
def _pesos_validos(pesos):
    valores = dict(PESOS_PADRAO)
    if pesos is not None:
        if set(pesos) - set(valores):
            raise ValueError("peso desconhecido na regra")
        valores.update(pesos)
    for nome, valor in valores.items():
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            raise ValueError("peso invalido: %s" % nome) from None
        if isinstance(valor, bool) or not math.isfinite(numero) or not 0 <= numero <= 1:
            raise ValueError("peso deve estar entre zero e um: %s" % nome)
        valores[nome] = numero
    return valores


##-- BUNDITA DE URSO #{5} -- Serie isolada e ausencia de contexto nao sustentam evidencia moderada. ##
def pontuar(a, b, pesos=None):
    """Escore explicavel entre dois conjuntos de atributos (spec 8.5).

    `a`/`b` sao dicts (tipicamente `atributos_registro`), ou aceitam o campo
    `cadeia`: se as cadeias coincidem, a origem e compartilhada e NAO conta
    como confirmacao independente (17.4-3).

    Retorna score 0..1, nivel (forte|moderado|fraco|contraditorio),
    componentes (por que casou), bloqueadores (por que NAO casaria) e a
    distancia em metros. Nunca consolida: apenas mede evidencia.
    """
    pesos = _pesos_validos(pesos)
    componentes = []
    bloqueadores = []

    sa, sb = a.get("numero_serie"), b.get("numero_serie")
    fa, fb = a.get("fabricante"), b.get("fabricante")
    ma, mb = a.get("modelo"), b.get("modelo")
    # serie "generica" (contador curto/codigo repetido) NAO identifica
    # instrumento: nem confirma nem bloqueia (spec 8.5).
    generica = bool(a.get("serie_generica") or b.get("serie_generica")
                    or serie_generica(sa) or serie_generica(sb))
    tem_serie = bool(sa and sb) and not generica

    if tem_serie:
        if sa == sb:
            componentes.append(_componente(
                "serie_igual", pesos["serie"], 1.0,
                "mesmo numero de serie normalizado (%s)" % sa))
        else:
            bloqueadores.append({
                "nome": "serie_conflitante",
                "detalhe": "series divergentes: %s vs %s" % (sa, sb)})
    elif sa and sb:
        componentes.append(_componente(
            "serie_generica", 0.0, 0.0,
            "serie %r nao identifica instrumento (codigo curto ou repetido "
            "entre municipios)" % sa))
    if ma and mb and ma != mb:
        bloqueadores.append({
            "nome": "modelo_conflitante",
            "detalhe": "modelos divergentes: %s vs %s" % (ma, mb)})
    if fa and fb and fa != fb:
        bloqueadores.append({
            "nome": "fabricante_conflitante",
            "detalhe": "fabricantes divergentes: %s vs %s" % (fa, fb)})

    dist = None
    ##-- BUNDITA DE URSO #{24} -- A API pura de pontuacao tambem deve recusar coordenadas invalidas antes do Haversine. ##
    coords = tuple(_num(at.get(k)) for at in (a, b) for k in ("latitude", "longitude"))
    if (None not in coords and -90 <= coords[0] <= 90 and -180 <= coords[1] <= 180
            and -90 <= coords[2] <= 90 and -180 <= coords[3] <= 180):
        dist = geo.haversine_m(*coords)
        fator = 0.0
        for limite, valor in FAIXAS_PROXIMIDADE:
            if dist <= limite:
                fator = valor
                break
        componentes.append(_componente(
            "proximidade", pesos.get("proximidade", 0.0), fator,
            "%.1f m entre as posicoes" % dist))

    va, vb = a.get("rodovia"), b.get("rodovia")
    ka, kb = a.get("km"), b.get("km")
    if va and vb and va == vb:
        if ka is not None and kb is not None:
            dkm = abs(ka - kb)
            if dkm <= TOLERANCIA_KM:
                componentes.append(_componente(
                    "via_km", pesos["via_km"], 1.0,
                    "mesma via %s, km %.3f/%.3f" % (va, ka, kb)))
            elif dkm <= CONFLITO_KM:
                componentes.append(_componente(
                    "via_km", pesos["via_km"], 0.5,
                    "mesma via %s, km vizinhos (dx=%.3f km)" % (va, dkm)))
            else:
                bloqueadores.append({
                    "nome": "km_incompativel",
                    "detalhe": "mesma via %s com km distantes (%.1f km)"
                               % (va, dkm)})
        else:
            componentes.append(_componente(
                "via_km", pesos["via_km"], 0.5,
                "mesma via %s sem km comparavel" % va))
    elif va and vb:
        componentes.append(_componente(
            "via_diferente", 0.0, 0.0, "vias diferentes: %s vs %s" % (va, vb)))

    sea, seb = a.get("sentido"), b.get("sentido")
    if sea and seb and "desconhecido" not in (sea, seb):
        if sea == seb:
            componentes.append(_componente(
                "sentido_igual", pesos["sentido"], 1.0, "sentido %s" % sea))
        elif {sea, seb} == {"crescente", "decrescente"}:
            bloqueadores.append({
                "nome": "sentido_oposto",
                "detalhe": "sentidos opostos (%s vs %s): nao colapsar por "
                           "proximidade" % (sea, seb)})

    mesma = any(a.get(chave) is not None and a.get(chave) == b.get(chave)
                for chave in ("cadeia", "recurso_id", "hash_registro"))
    n_indep = (1 if mesma else 2) if a.get("cadeia") and b.get("cadeia") else int(bool(a.get("cadeia") or b.get("cadeia")))
    if mesma:
        componentes.append({
            "nome": "origem_compartilhada", "peso": 0.0, "fator": 1.0,
            "contribuicao": 0.0,
            "explicacao": "mesma cadeia de evidencia (T59/T72): nao conta "
                          "como confirmacao independente"})
    elif a.get("cadeia") and b.get("cadeia"):
        componentes.append(_componente(
            "corroboracao_independente",
            pesos.get("corroboracao_independente", 0.0), 1.0,
            "fontes/cadeias independentes"))

    score = round(max(0.0, min(1.0, sum(c["contribuicao"]
                                        for c in componentes))), 4)

    if bloqueadores:
        nivel = "contraditorio"
    elif score >= LIMIAR_FORTE:
        nivel = "forte"
    elif score >= LIMIAR_MODERADO:
        nivel = "moderado"
    else:
        nivel = "fraco"
    # Travas da spec: 'forte' exige serie e cadeia independente; e mesma
    # coordenada sozinha NUNCA vira 'forte' (8.5 / 17.4-4).
    if nivel == "forte" and (not tem_serie or mesma):
        nivel = "moderado"
    # Serie isolada e apenas uma pista. Fabricante/modelo contextualizam a
    # identidade de instrumentos sem GPS (inclusive portateis).
    via_km_contextualizado = (va and va == vb and ka is not None and kb is not None
                              and abs(ka - kb) <= TOLERANCIA_KM
                              and _uf_valida(a.get("uf"))
                              and _uf_valida(a.get("uf")) == _uf_valida(b.get("uf")))
    corrobora = ((dist is not None and dist <= 200.0)
                or via_km_contextualizado
                or (fa and fa == fb and ma and ma == mb))
    if nivel in ("moderado", "forte") and tem_serie and sa == sb and not corrobora:
        nivel = "fraco"
        componentes.append(_componente(
            "serie_sem_corrob", 0.0, 0.0,
            "serie isolada: falta posicao proxima, via/km/UF ou fabricante/modelo"))

    return {
        "score": score,
        "nivel": nivel,
        "componentes": componentes,
        "bloqueadores": bloqueadores,
        "distancia_m": None if dist is None else round(dist, 3),
        "n_evidencias_independentes": n_indep,
        "mesma_origem": mesma,
    }


##-- BUNDITA DE URSO #{26} -- Serie divergente bloqueia instrumento, nao necessariamente local; sentido oposto nao invalida aparelho portatil. ##
def _mesma_entidade(a, b, tipo, visao=None):
    def ids(at):
        return {visao.canonico(tipo, i) if visao else i
                for i in at.get(tipo + "_ids", ())}
    aa, bb = ids(a), ids(b)
    return len(aa) == len(bb) == 1 and aa == bb


def avaliar_escopos(a, b, pontuacao=None, visao=None):
    """Separa sugestoes de ponto/instrumento; nunca decide nem altera dados."""
    res = dict(pontuacao if pontuacao is not None else pontuar(a, b))
    bloqueios = res["bloqueadores"]
    dist = res["distancia_m"]
    va, vb = a.get("rodovia"), b.get("rodovia")
    ua, ub = _uf_valida(a.get("uf")), _uf_valida(b.get("uf"))
    ka, kb = a.get("km"), b.get("km")
    via_km = bool(va and va == vb and ua and ua == ub
                  and ka is not None and kb is not None
                  and abs(ka - kb) <= TOLERANCIA_KM)
    proximo = dist is not None and dist <= DISTANCIA_REVISAO_PONTO_M
    bloqueios_ponto = [b for b in bloqueios if b["nome"] in ("sentido_oposto", "km_incompativel")]
    for condicao, nome, detalhe in (
            (va and vb and va != vb, "via_divergente", "vias publicadas diferentes: requer revisar local"),
            (ua and ub and ua != ub, "uf_divergente", "UFs publicadas diferentes: requer revisar local"),
            (dist is not None and not proximo, "posicao_distante", "posicoes acima da tolerancia de revisao do ponto")):
        if condicao:
            bloqueios_ponto.append({"nome": nome, "detalhe": detalhe})
    componentes_ponto = {"proximidade", "via_km", "sentido_igual", "corroboracao_independente"}
    score_ponto = round(sum(c["contribuicao"] for c in res["componentes"]
                            if c["nome"] in componentes_ponto), 4)
    ponto = {"score": score_ponto, "bloqueadores": bloqueios_ponto,
             "componentes": [c for c in res["componentes"] if c["nome"] in componentes_ponto]}
    if _mesma_entidade(a, b, "ponto", visao):
        ponto["nivel"] = "ja_associado"
    elif bloqueios_ponto:
        ponto["nivel"] = "contraditorio"
    elif (proximo or via_km) and score_ponto >= LIMIAR_MODERADO:
        # Mesmo local ainda exige revisao; coordenada isolada nao e prova forte.
        ponto["nivel"] = "moderado"
    else:
        ponto["nivel"] = "fraco"

    sa, sb = a.get("numero_serie"), b.get("numero_serie")
    serie = bool(sa and sa == sb and not (a.get("serie_generica") or b.get("serie_generica")
                                         or serie_generica(sa)))
    modelo = bool(a.get("fabricante") and a["fabricante"] == b.get("fabricante")
                  and a.get("modelo") and a["modelo"] == b.get("modelo"))
    bloqueios_equipamento = [b for b in bloqueios if b["nome"] in
                            ("serie_conflitante", "modelo_conflitante", "fabricante_conflitante")]
    equipamento = {"score": res["score"], "bloqueadores": bloqueios_equipamento,
                   "componentes": res["componentes"]}
    if _mesma_entidade(a, b, "equipamento", visao):
        equipamento["nivel"] = "ja_associado"
    elif bloqueios_equipamento:
        equipamento["nivel"] = "contraditorio"
    elif serie and (proximo or via_km or modelo) and res["score"] >= LIMIAR_MODERADO:
        equipamento["nivel"] = ("forte" if res["score"] >= LIMIAR_FORTE
                                 and res["n_evidencias_independentes"] >= 2 else "moderado")
    else:
        equipamento["nivel"] = "fraco"
    escopos = {"ponto": ponto, "equipamento": equipamento}
    sugeridos = [tipo for tipo, ev in escopos.items() if ev["nivel"] in ("moderado", "forte")]
    res["nivel_original"] = res["nivel"]
    res["score_original"] = res["score"]
    if sugeridos:
        melhor = max((escopos[t] for t in sugeridos),
                     key=lambda ev: (ev["nivel"] == "forte", ev["score"]))
        res.update(nivel=melhor["nivel"], score=melhor["score"], encaminhamento="revisao")
    elif all(ev["nivel"] == "ja_associado" for ev in escopos.values()):
        res.update(nivel="ja_associado", encaminhamento="ja_associado")
    else:
        res.update(nivel="contraditorio" if any(ev["nivel"] == "contraditorio" for ev in escopos.values()) else "fraco",
                   encaminhamento="diagnostico")
    res.update(avaliacao_escopos=escopos, escopos_sugeridos=sugeridos)
    return res


# --------------------------------------------------------- regra versionada

##-- BUNDITA DE URSO #{4} -- A mesma versao aceitava pesos novos sem atualizar sua configuracao persistida. ##
def registrar_regra(conn, versao=None, pesos=None, raio_m=None, descricao=None,
                    agora=None):
    """Insere (ou recupera) a REGRA_DEDUPLICACAO versionada. Retorna o id."""
    versao = versao or VERSAO_REGRA_PADRAO
    if versao in ("dedup-1.0", "dedup-1.1"):
        raise ValueError("versao antiga apenas para consulta; use a regra vigente ou uma nova versao")
    pesos = _pesos_validos(pesos)
    raio_m = RAIO_CANDIDATO_M if raio_m is None else float(raio_m)
    if not math.isfinite(raio_m) or raio_m <= 0:
        raise ValueError("raio_m deve ser finito e positivo")
    cfg = json.dumps({
        "pesos": pesos,
        "raio_m": RAIO_CANDIDATO_M if raio_m is None else float(raio_m),
        "limiar_forte": LIMIAR_FORTE,
        "limiar_moderado": LIMIAR_MODERADO,
        "limiar_min_candidato": LIMIAR_MIN_CANDIDATO,
        "tolerancia_km": TOLERANCIA_KM,
        "conflito_km": CONFLITO_KM,
        "faixas_proximidade": FAIXAS_PROXIMIDADE,
        "serie_curta_max_digitos": SERIE_CURTA_MAX_DIGITOS,
        "serie_isolada": "fraco",
        "corroboracao_posicao_max_m": 200.0,
        "via_km_exige_uf": True,
        "generica_por_municipio": False,
        "indice_espacial": "esfera_cartesiana",
        ##-- BUNDITA DE URSO #{26} -- Persistir os criterios de escopo impede chamar uma mudanca de politica de mesma regra. ##
        "avaliacao_por_escopo": True,
        "distancia_revisao_ponto_m": DISTANCIA_REVISAO_PONTO_M,
        "fila_padrao": "escopo_moderado_ou_forte",
        "uf_validada": True,
        "historico_equivalente": "mesma_origem_entidades_e_atributos",
    }, sort_keys=True, ensure_ascii=False)
    row = dbmod.query_one(
        conn, "SELECT id, configuracao_serializada FROM REGRA_DEDUPLICACAO "
              "WHERE versao = ?", (versao,))
    if row is not None:
        if _load_json(row["configuracao_serializada"]) != _load_json(cfg):
            raise ValueError("configuracao diferente: use uma nova versao da regra")
        return row["id"]
    return dbmod.insert(conn, "REGRA_DEDUPLICACAO", {
        "versao": versao,
        "descricao": descricao or "Deduplicacao rastreavel (spec 8/17.4)",
        "configuracao_serializada": cfg,
        "inicio_validade": agora or _agora(),
    })


# ------------------------------------------------------- gerar candidatos

def _ord(a, b):
    return (a, b) if a < b else (b, a)


##-- BUNDITA DE URSO #{25} -- Novas coletas do mesmo cadastro e com os mesmos atributos multiplicavam pares sem acrescentar evidencia de identidade. ##
def _representantes(attrs):
    grupos = {}
    campos = ("latitude", "longitude", "precisao_metros", "qualidade_posicao",
              "numero_serie", "serie_generica", "fabricante", "modelo", "rodovia", "km", "sentido", "uf")
    for rid in sorted(attrs):
        at = attrs[rid]
        entidades = (tuple(sorted(at.get("ponto_ids", ()))),
                     tuple(sorted(at.get("equipamento_ids", ()))))
        # Sem entidade original nao ha prova de que dois brutos sejam o mesmo cadastro.
        chave = ((at.get("fonte_id"), at.get("recurso_id"), entidades,
                  tuple(at.get(c) for c in campos)) if any(entidades) else ("registro", rid))
        grupos.setdefault(chave, []).append(rid)
    # O menor ID e estavel ao acrescentar uma nova observacao equivalente.
    return {membros[0]: membros for membros in grupos.values()}


##-- BUNDITA DE URSO #{14} -- A grade em graus perdia vizinhos e uma rodovia inteira gerava pares quadraticos. ##
def _pares_candidatos(ids, attrs, raio_m):
    """Indices por serie, UF/via/km e celulas 3D na esfera terrestre.

    A corda e menor que o arco: pontos dentro do raio geodesico estao na
    mesma celula cartesiana ou numa das 26 vizinhas, inclusive nos polos.
    """
    pares, por_serie, por_trecho = set(), {}, {}
    for rid in ids:
        at = attrs[rid]
        if at.get("numero_serie") and not at.get("serie_generica"):
            por_serie.setdefault(at["numero_serie"], []).append(rid)
        if at.get("rodovia") and at.get("km") is not None and at.get("uf"):
            faixa = int(math.floor(at["km"] / TOLERANCIA_KM))
            chave = (at["uf"], at["rodovia"], faixa)
            for vizinha in (faixa - 1, faixa, faixa + 1):
                for outro in por_trecho.get((at["uf"], at["rodovia"], vizinha), ()):
                    if abs(at["km"] - attrs[outro]["km"]) <= TOLERANCIA_KM:
                        pares.add(_ord(rid, outro))
            por_trecho.setdefault(chave, []).append(rid)
    for grupo in por_serie.values():
        for i, rid in enumerate(grupo):
            for outro in grupo[i + 1:]:
                pares.add(_ord(rid, outro))
    grade = {}
    for rid in ids:
        at = attrs[rid]
        lat, lon = at.get("latitude"), at.get("longitude")
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        phi, lamb = math.radians(lat), math.radians(lon)
        xyz = (geo.EARTH_RADIUS_M * math.cos(phi) * math.cos(lamb),
               geo.EARTH_RADIUS_M * math.cos(phi) * math.sin(lamb),
               geo.EARTH_RADIUS_M * math.sin(phi))
        cx, cy, cz = (math.floor(v / raio_m) for v in xyz)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for outro in grade.get((cx + dx, cy + dy, cz + dz), ()):
                        aj = attrs[outro]
                        if geo.haversine_m(lat, lon, aj["latitude"], aj["longitude"]) <= raio_m:
                            pares.add(_ord(rid, outro))
        grade.setdefault((cx, cy, cz), []).append(rid)
    return sorted(pares)


##-- BUNDITA DE URSO #{6} -- Registros diferentes no mesmo arquivo podem descrever faixas do mesmo instrumento. ##
def gerar_candidatos(conn, regra=None, pesos=None, raio_m=None, agora=None):
    """Gera CANDIDATO_DUPLICIDADE a partir dos REGISTRO_FONTE (spec 8.3).

    Nunca decide: todo candidato nasce com estado 'pendente'. Copias do mesmo
    bruto e arquivo sao ignoradas; observacoes equivalentes usam representante
    estavel, preservando seus registros na evidencia.
    Idempotente: UNIQUE(registro_a_id, registro_b_id, regra_id).
    """
    raio_m = RAIO_CANDIDATO_M if raio_m is None else float(raio_m)
    if not math.isfinite(raio_m) or raio_m <= 0:
        raise ValueError("raio_m deve ser finito e positivo")
    pesos = _pesos_validos(pesos)
    regra_id = registrar_regra(conn, versao=regra, pesos=pesos, raio_m=raio_m,
                               agora=agora)
    agora = agora or _agora()

    ids = [r[0] for r in dbmod.query_all(
        conn, "SELECT id FROM REGISTRO_FONTE ORDER BY id")]
    attrs = {rid: atributos_registro(conn, rid) for rid in ids}
    grupos = _representantes(attrs)
    visao = identidade.VisaoCanonica(conn)

    criados, existentes, ignorados, associados = [], [], 0, 0
    for a, b in _pares_candidatos(sorted(grupos), attrs, raio_m):
        if (attrs[a]["hash_registro"]
                and attrs[a]["hash_registro"] == attrs[b]["hash_registro"]
                and attrs[a]["artefato_hash"] == attrs[b]["artefato_hash"]):
            ignorados += 1                      # mesma origem: nao e duplicata
            continue
        res = pontuar(attrs[a], attrs[b], pesos)
        if not res["bloqueadores"] and res["score"] < LIMIAR_MIN_CANDIDATO:
            continue
        res = avaliar_escopos(attrs[a], attrs[b], res, visao)
        if res["encaminhamento"] == "ja_associado":
            associados += 1
            continue
        ev = {
            "score": res["score"],
            "nivel": res["nivel"],
            "componentes": res["componentes"],
            "bloqueadores": res["bloqueadores"],
            "distancia_m": res["distancia_m"],
            "n_evidencias_independentes": res["n_evidencias_independentes"],
            "cadeia_a": attrs[a]["cadeia"],
            "cadeia_b": attrs[b]["cadeia"],
            "nivel_original": res["nivel_original"],
            "score_original": res["score_original"],
            "avaliacao_escopos": res["avaliacao_escopos"],
            "escopos_sugeridos": res["escopos_sugeridos"],
            "encaminhamento": res["encaminhamento"],
            "observacoes_equivalentes": {"a": grupos[a], "b": grupos[b]},
        }
        cur = conn.execute(
            "INSERT OR IGNORE INTO CANDIDATO_DUPLICIDADE "
            "(registro_a_id, registro_b_id, regra_id, score, estado, "
            "evidencias_resumo, gerado_em) VALUES (?,?,?,?,?,?,?)",
            (a, b, regra_id, res["score"], "pendente",
             json.dumps(ev, sort_keys=True, ensure_ascii=False), agora))
        if cur.rowcount == 1:
            criados.append(cur.lastrowid)
        else:
            row = dbmod.query_one(
                conn, "SELECT id FROM CANDIDATO_DUPLICIDADE "
                      "WHERE registro_a_id=? AND registro_b_id=? AND regra_id=?",
                (a, b, regra_id))
            existentes.append(row["id"])
            # Atualizar apenas a lista de observacoes da pendencia ainda nunca decidida.
            conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET evidencias_resumo=? "
                         "WHERE id=? AND estado='pendente' AND NOT EXISTS "
                         "(SELECT 1 FROM DECISAO_DUPLICIDADE WHERE candidato_id=?)",
                         (json.dumps(ev, sort_keys=True, ensure_ascii=False), row["id"], row["id"]))
    conn.commit()
    return {
        "regra_id": regra_id,
        "total_registros": len(ids),
        "criados": criados,
        "existentes": existentes,
        "ignorados_mesma_origem": ignorados,
        "registros_representantes": len(grupos),
        "observacoes_equivalentes_agrupadas": len(ids) - len(grupos),
        "pares_ja_associados": associados,
    }


##-- BUNDITA DE URSO #{4} -- Misturar geracoes antigas com a regra vigente mantinha a fila obsoleta. ##
def candidatos(conn, ponto_id=None, estado=None, regra=VERSAO_REGRA_PADRAO,
               incluir_fracos=False, incluir_diagnosticos=False, escopo=None):
    """Fila de revisao vigente. Diagnostico completo: incluir_diagnosticos=True.

    `incluir_fracos` continua aceito como alias para diagnostico completo.
    `regra=None` permite consultar tambem as geracoes historicas.
    """
    if escopo is not None and escopo not in identidade.ESCOPOS:
        raise ValueError("escopo deve ser ponto, equipamento ou ambos")
    sql = ("SELECT cd.*, ra.identificador_na_fonte AS a_identificador, "
           "rb.identificador_na_fonte AS b_identificador "
           "FROM CANDIDATO_DUPLICIDADE cd "
           "JOIN REGISTRO_FONTE ra ON ra.id = cd.registro_a_id "
           "JOIN REGISTRO_FONTE rb ON rb.id = cd.registro_b_id ")
    cond, params = [], []
    if regra is not None:
        cond.append("cd.regra_id IN (SELECT id FROM REGRA_DEDUPLICACAO WHERE versao=?)")
        params.append(regra)
    if estado:
        cond.append("cd.estado = ?")
        params.append(estado)
    if ponto_id is not None:
        cond.append("(cd.registro_a_id IN (SELECT registro_id FROM "
                    "VINCULO_REGISTRO_PONTO WHERE ponto_id = ?) OR "
                    "cd.registro_b_id IN (SELECT registro_id FROM "
                    "VINCULO_REGISTRO_PONTO WHERE ponto_id = ?))")
        params.extend([ponto_id, ponto_id])
    if cond:
        sql += "WHERE " + " AND ".join(cond) + " "
    sql += "ORDER BY cd.id"
    rows = [dict(r) for r in dbmod.query_all(conn, sql, params)]
    ##-- BUNDITA DE URSO #{26} -- Contraditorios e pistas fracas nao podem parecer propostas prontas de unificacao. ##
    saida = []
    diagnostico = incluir_diagnosticos or incluir_fracos
    visao = None
    for row in rows:
        ev = _load_json(row["evidencias_resumo"])
        if row["estado"] == "pendente" and ev.get("escopos_sugeridos"):
            # Decisoes de outros pares podem ter associado estas entidades.
            # Isso retira trabalho ja feito; nao serve como evidencia nova.
            if visao is None:
                visao = identidade.VisaoCanonica(conn)
            aa, bb = ({tipo + "_ids": identidade.originais(conn, tipo, row[chave])
                       for tipo in identidade.TIPOS} for chave in ("registro_a_id", "registro_b_id"))
            ja = [tipo for tipo in ev["escopos_sugeridos"] if _mesma_entidade(aa, bb, tipo, visao)]
            if ja:
                ev["escopos_ja_associados"] = ja
                ev["escopos_sugeridos"] = [t for t in ev["escopos_sugeridos"] if t not in ja]
                if not ev["escopos_sugeridos"]:
                    ev["encaminhamento"] = "ja_associado"
                row["evidencias_resumo"] = json.dumps(ev, sort_keys=True, ensure_ascii=False)
        if not diagnostico and row["estado"] == "pendente":
            if ev.get("encaminhamento") not in (None, "revisao") or ev.get("nivel") not in ("moderado", "forte"):
                continue
        if escopo is not None and not diagnostico:
            if not set(identidade.ESCOPOS[escopo]) <= set(ev.get("escopos_sugeridos", ())):
                continue
        saida.append(row)
    return saida


# --------------------------------------------------------------- decisoes

##-- BUNDITA DE URSO #{2} -- A decisao precisa distinguir instrumento e ponto, com autor e escopo explicitos. ##
def decidir(conn, candidato_id, decisao, usuario, motivo, observacoes=None,
            forcar=False, agora=None, escopo=None):
    """Grava DECISAO_DUPLICIDADE (append-only) com a evidencia e o autor.

    `motivo` e a fundamentacao obrigatoria. Retorna o id da decisao. Nunca
    consolida nada: apenas registra a intencao humana.
    """
    if decisao not in _ESTADO_POR_DECISAO:
        raise ValueError("decisao invalida: %r" % (decisao,))
    if not motivo or not str(motivo).strip():
        raise ValueError("fundamentacao (motivo) obrigatoria")
    if not usuario or not str(usuario).strip():
        raise ValueError("autor (usuario) obrigatorio")
    if decisao in ("unificar", "manter_separados") and escopo not in identidade.ESCOPOS:
        raise ValueError("indique escopo: ponto, equipamento ou ambos")
    cand = dbmod.query_one(
        conn, "SELECT * FROM CANDIDATO_DUPLICIDADE WHERE id = ?", (candidato_id,))
    if cand is None:
        raise ValueError("CANDIDATO_DUPLICIDADE %r inexistente" % (candidato_id,))
    if decisao_ativa(conn, candidato_id) is not None:
        raise ValueError("reverta a decisao ativa antes de registrar outra")
    agora = agora or _agora()
    obs = {
        "evidencia": _load_json(cand["evidencias_resumo"]),
        "decisao": decisao,
        "forcar": bool(forcar),
        "escopo": escopo,
    }
    if decisao in ("unificar", "manter_separados"):
        obs["entidades"] = {
            tipo: {str(rid): identidade.originais(conn, tipo, rid)
                   for rid in (cand["registro_a_id"], cand["registro_b_id"])}
            for tipo in identidade.ESCOPOS[escopo]}
        if any(len(ids) != 1 for valores in obs["entidades"].values()
               for ids in valores.values()):
            raise ValueError("escopo requer uma entidade original inequivoca por registro")
    if observacoes:
        obs["observacoes"] = observacoes
    with conn:
        decisao_id = dbmod.insert(conn, "DECISAO_DUPLICIDADE", {
            "candidato_id": candidato_id,
            "decisao": decisao,
            "fundamentacao": str(motivo),
            "ator": usuario,
            "decidida_em": agora,
            "observacoes": json.dumps(obs, sort_keys=True, ensure_ascii=False),
        })
        conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET estado = ? WHERE id = ?",
                     (_ESTADO_POR_DECISAO[decisao], candidato_id))
        identidade.VisaoCanonica(conn)
    return decisao_id


def decisao_ativa(conn, candidato_id):
    """Ultima decisao nao revertida do candidato (ou None)."""
    row = dbmod.query_one(conn, """
        SELECT * FROM DECISAO_DUPLICIDADE
        WHERE candidato_id = ? AND revertida_em IS NULL
        ORDER BY id DESC LIMIT 1""", (candidato_id,))
    return None if row is None else dict(row)


def listar_decisoes(conn, candidato_id):
    """Todas as decisoes (inclusive revertidas) - auditoria completa."""
    return [dict(r) for r in dbmod.query_all(
        conn, "SELECT * FROM DECISAO_DUPLICIDADE WHERE candidato_id = ? "
              "ORDER BY id", (candidato_id,))]


# ---------------------------------------------------------------- aplicar

def _natureza(conn, registro_id):
    base = _base_registro(conn, registro_id)
    return None if base is None else base["natureza"]


def _divergencia(at_a, at_b, tolerancia=TOLERANCIA_POSICAO_M):
    if None in (at_a.get("latitude"), at_a.get("longitude"),
                at_b.get("latitude"), at_b.get("longitude")):
        return None
    d = geo.haversine_m(at_a["latitude"], at_a["longitude"],
                        at_b["latitude"], at_b["longitude"])
    if d <= tolerancia:
        return None
    return {
        "distancia_m": round(d, 3),
        "observacao": "divergencia geografica preservada; nenhum dado "
                      "oficial foi sobrescrito",
        "a": {"registro_id": at_a["registro_id"],
              "latitude": at_a["latitude"], "longitude": at_a["longitude"],
              "qualidade": at_a.get("qualidade_posicao"),
              "natureza": at_a.get("natureza")},
        "b": {"registro_id": at_b["registro_id"],
              "latitude": at_b["latitude"], "longitude": at_b["longitude"],
              "qualidade": at_b.get("qualidade_posicao"),
              "natureza": at_b.get("natureza")},
    }


##-- BUNDITA DE URSO #{3} -- Decisoes encadeadas precisam atualizar o canonico quando uma aresta e revertida. ##
def _atualizar_canonicos(conn, visao):
    for decisao in visao.decisoes:
        row = dbmod.query_one(conn, "SELECT evidencias_resumo FROM "
                             "CANDIDATO_DUPLICIDADE WHERE id=?",
                             (decisao["candidato_id"],))
        evid = _load_json(row[0])
        for tipo in identidade.TIPOS:
            ids = [i for valores in decisao["entidades"].get(tipo, {}).values()
                   for i in valores]
            evid[tipo + "_canonico"] = (visao.canonico(tipo, ids[0])
                                        if ids else None)
        conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET estado='consolidado', "
                     "evidencias_resumo=? WHERE id=?",
                     (json.dumps(evid, sort_keys=True, ensure_ascii=False),
                      decisao["candidato_id"]))


##-- BUNDITA DE URSO #{3} -- Recalcular todos os vinculos ativos evita dependencia da ordem e permite rollback atomico. ##
def aplicar(conn, candidato_id=None, usuario=None, agora=None):
    """Aplica decisoes explicitas e reconstroi os vinculos ativos atomicamente.

    Nenhuma entidade de origem e alterada. O escopo da decisao separa ponto
    e equipamento; a API resolve aliases pela mesma visao canonica.
    """
    agora = agora or _agora()
    if candidato_id is None:
        alvos = [r[0] for r in conn.execute(
            "SELECT id FROM CANDIDATO_DUPLICIDADE "
            "WHERE estado='decidido_unificar' ORDER BY id")]
    else:
        alvos = [candidato_id]
    resultados = []
    with conn:
        antes = {(tipo, r[0], r[1])
                 for tipo, (tabela, coluna) in identidade.TIPOS.items()
                 for r in conn.execute("SELECT registro_id, %s FROM %s"
                                       % (coluna, tabela))}
        for cid in alvos:
            cand = dbmod.query_one(conn, "SELECT * FROM CANDIDATO_DUPLICIDADE "
                                  "WHERE id=?", (cid,))
            dec = decisao_ativa(conn, cid)
            if cand is None or dec is None or dec["decisao"] != "unificar":
                resultados.append({"candidato_id": cid, "aplicado": False,
                                   "motivo": "sem decisao ativa de unificar"})
                continue
            evid = _load_json(cand["evidencias_resumo"])
            obs = _load_json(dec["observacoes"])
            bloqueadores = evid.get("bloqueadores", [])
            tipos = identidade.ESCOPOS.get(obs.get("escopo") or "ambos", ())
            ##-- BUNDITA DE URSO #{26} -- Aplicar deve respeitar o conflito do escopo escolhido, inclusive via/UF/posicao divergentes. ##
            if evid.get("avaliacao_escopos"):
                bloqueadores = [b for tipo in tipos for b in
                                evid["avaliacao_escopos"][tipo]["bloqueadores"]]
            elif tipos == ("ponto",):
                bloqueadores = [b for b in bloqueadores if b["nome"] not in
                                ("serie_conflitante", "modelo_conflitante", "fabricante_conflitante")]
            elif tipos == ("equipamento",):
                bloqueadores = [b for b in bloqueadores if b["nome"] not in
                                ("sentido_oposto", "km_incompativel")]
            if bloqueadores and not obs.get("forcar"):
                resultados.append({"candidato_id": cid, "aplicado": False,
                                   "motivo": "evidencia contraditoria: requer forcar=True"})
                continue
            a, b = cand["registro_a_id"], cand["registro_b_id"]
            # Medir antes dos vinculos derivados: a decisao nao e sua propria prova.
            div = _divergencia(atributos_registro(conn, a), atributos_registro(conn, b))
            if div:
                evid["divergencia_posicao"] = div
            obs.setdefault("aplicada_em", agora)
            obs.setdefault("aplicada_por", usuario)
            evid.setdefault("aplicado_em", agora)
            evid.setdefault("aplicado_por", usuario)
            conn.execute("UPDATE DECISAO_DUPLICIDADE SET observacoes=? WHERE id=?",
                         (json.dumps(obs, sort_keys=True, ensure_ascii=False), dec["id"]))
            conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET evidencias_resumo=? WHERE id=?",
                         (json.dumps(evid, sort_keys=True, ensure_ascii=False), cid))
            resultados.append({"candidato_id": cid, "aplicado": True,
                               "decisao_id": dec["id"], "divergencia": div})
        visao = identidade.reconstruir_vinculos(conn)
        _atualizar_canonicos(conn, visao)
        for res in resultados:
            if not res["aplicado"]:
                continue
            evid = _load_json(dbmod.scalar(
                conn, "SELECT evidencias_resumo FROM CANDIDATO_DUPLICIDADE WHERE id=?",
                (res["candidato_id"],)))
            for tipo in identidade.TIPOS:
                res[tipo + "_canonico"] = evid.get(tipo + "_canonico")
            res["vinculos_criados"] = sum(
                (tipo, r[0], r[1]) not in antes
                for tipo, (tabela, coluna) in identidade.TIPOS.items()
                for r in conn.execute("SELECT registro_id, %s FROM %s WHERE decisao_id=?"
                                      % (coluna, tabela), (res["decisao_id"],)))
    return resultados


##-- BUNDITA DE URSO #{3} -- Apagar apenas os vinculos da decisao deixava as demais unificacoes inconsistentes. ##
def reverter_decisao(conn, decisao_id, usuario, motivo=None, agora=None):
    """Retira uma decisao e recalcula a visao das restantes, com auditoria."""
    dec = dbmod.query_one(conn, "SELECT * FROM DECISAO_DUPLICIDADE WHERE id=?",
                         (decisao_id,))
    if dec is None:
        raise ValueError("DECISAO_DUPLICIDADE %r inexistente" % (decisao_id,))
    if dec["revertida_em"]:
        return {"decisao_id": decisao_id, "revertida": False,
                "motivo": "decisao ja revertida"}
    agora = agora or _agora()
    with conn:
        removidos = sum(dbmod.scalar(conn, "SELECT COUNT(*) FROM %s WHERE decisao_id=?"
                                     % tabela, (decisao_id,))
                        for tabela, _ in identidade.TIPOS.values())
        obs = _load_json(dec["observacoes"])
        obs["reversao"] = {"por": usuario, "em": agora, "motivo": motivo}
        conn.execute("UPDATE DECISAO_DUPLICIDADE SET revertida_em=?, observacoes=? WHERE id=?",
                     (agora, json.dumps(obs, sort_keys=True, ensure_ascii=False), decisao_id))
        anterior = decisao_ativa(conn, dec["candidato_id"])
        estado = (_ESTADO_POR_DECISAO[anterior["decisao"]] if anterior else "pendente")
        row = dbmod.scalar(conn, "SELECT evidencias_resumo FROM CANDIDATO_DUPLICIDADE WHERE id=?",
                           (dec["candidato_id"],))
        evid = _load_json(row)
        for chave in ("aplicado_em", "aplicado_por", "ponto_canonico",
                      "equipamento_canonico", "vinculos_criados", "divergencia_posicao"):
            evid.pop(chave, None)
        conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET estado=?, evidencias_resumo=? WHERE id=?",
                     (estado, json.dumps(evid, sort_keys=True, ensure_ascii=False), dec["candidato_id"]))
        visao = identidade.reconstruir_vinculos(conn)
        _atualizar_canonicos(conn, visao)
        # Compatibilidade com eventuais vinculos legados de operacoes/trechos.
        for tabela in ("VINCULO_REGISTRO_OPERACAO", "VINCULO_REGISTRO_TRECHO"):
            cur = conn.execute("DELETE FROM %s WHERE decisao_id=?" % tabela, (decisao_id,))
            removidos += cur.rowcount
        estado = dbmod.scalar(conn, "SELECT estado FROM CANDIDATO_DUPLICIDADE WHERE id=?",
                              (dec["candidato_id"],))
    return {"decisao_id": decisao_id, "revertida": True,
            "vinculos_removidos": removidos, "estado": estado}


# ------------------------------------------------------- consultas auxiliares

def verificacoes_duplicadas(conn, equipamento_ids):
    """Historico metrologico repetido por faixa (spec 17.4-9) - so relatorio.

    Agrupa por (certificado, data, tipo) e devolve os grupos com mais de uma
    VERIFICACAO_METROLOGICA. Nao altera nada.
    """
    if not equipamento_ids:
        return []
    qs = ",".join("?" for _ in equipamento_ids)
    rows = dbmod.query_all(conn, """
        SELECT numero_certificado, data_verificacao, tipo_verificacao_id,
               COUNT(*) AS n, GROUP_CONCAT(id) AS verificacao_ids
        FROM VERIFICACAO_METROLOGICA
        WHERE equipamento_id IN (%s) AND numero_certificado IS NOT NULL
        GROUP BY numero_certificado, data_verificacao, tipo_verificacao_id
        HAVING COUNT(*) > 1""" % qs, list(equipamento_ids))
    return [dict(r) for r in rows]


def classificacao_evidencia(conn, registro_ids):
    """Resume a evidencia de um conjunto: independentes e natureza (17.4-1/2).

    `confirmado_oficial` so e True se uma das cadeias independentes for de
    fonte oficial - radar comunitario nunca aparece como confirmado.
    """
    naturezas = set()
    for rid in registro_ids:
        nat = _natureza(conn, rid)
        if nat:
            naturezas.add(nat)
    return {
        "n_evidencias_independentes": evidencias_independentes(conn, registro_ids),
        "naturezas": sorted(naturezas),
        "confirmado_oficial": "oficial" in naturezas,
    }
