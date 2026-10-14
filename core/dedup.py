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

__all__ = [
    "normalizar_texto", "normalizar_serie", "normalizar_rodovia",
    "normalizar_km", "normalizar_sentido",
    "cadeia_evidencia", "mesma_cadeia", "evidencias_independentes",
    "atributos_registro", "pontuar", "gerar_candidatos", "candidatos",
    "decidir", "decisao_ativa", "listar_decisoes", "aplicar",
    "reverter_decisao", "verificacoes_duplicadas", "classificacao_evidencia",
    "registrar_regra",
]

# --------------------------------------------------------------- constantes

VERSAO_REGRA_PADRAO = "dedup-1.0"

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

_ESTADO_POR_DECISAO = {
    "unificar": "decidido_unificar",
    "manter_separados": "decidido_manter_separados",
    "revisar": "revisar",
}

CAMPO_ALIASES = {
    "latitude": {"latitude", "lat"},
    "longitude": {"longitude", "lon", "lng", "long"},
    "numero_serie": {"numero_serie", "serie", "serial", "numero_de_serie", "ns"},
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


def _num(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
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


def normalizar_km(valor):
    """Aceita virgula decimal, ponto e sufixo 'km' (spec 8.2)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
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
    if "crescente" in chave:
        return "crescente"
    if "decrescente" in chave:
        return "decrescente"
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


def evidencias_independentes(conn, registro_ids):
    """Numero de cadeias de evidencia distintas entre os registros dados."""
    chaves = set()
    for rid in registro_ids:
        chaves.add(cadeia_evidencia(conn, rid)["chave"])
    return len(chaves)


# ------------------------------------------------------------- atributos

def _pontos(conn, registro_id):
    return [r[0] for r in dbmod.query_all(
        conn, "SELECT ponto_id FROM VINCULO_REGISTRO_PONTO "
              "WHERE registro_id = ? ORDER BY ponto_id", (registro_id,))]


def _equipamentos(conn, registro_id):
    return [r[0] for r in dbmod.query_all(
        conn, "SELECT equipamento_id FROM VINCULO_REGISTRO_EQUIPAMENTO "
              "WHERE registro_id = ? ORDER BY equipamento_id", (registro_id,))]


def atributos_registro(conn, registro_id):
    """Atributos normalizados de um registro (spec 8.2), sem alterar o dado.

    Ordem de precedencia do valor: VALOR_OBSERVADO (T72, ja normalizado) >
    entidades ligadas (PONTO/EQUIPAMENTO/POSICAO) > JSON de payload_original.
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
        "ponto_ids": _pontos(conn, registro_id),
        "equipamento_ids": _equipamentos(conn, registro_id),
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

    # 3) payload JSON (menor prioridade)
    payload = {}
    try:
        payload = _achatar(json.loads(base["payload_original"] or "{}"))
    except (TypeError, ValueError):
        payload = {}

    at["latitude"] = _num(_primeiro(valores.get("latitude"), lat,
                                    _extrair(payload, "latitude")))
    at["longitude"] = _num(_primeiro(valores.get("longitude"), lon,
                                     _extrair(payload, "longitude")))
    at["numero_serie"] = normalizar_serie(
        _primeiro(valores.get("numero_serie"), serie,
                  _extrair(payload, "numero_serie")))
    at["fabricante"] = normalizar_texto(
        _primeiro(valores.get("fabricante"), fabricante,
                  _extrair(payload, "fabricante")))
    at["modelo"] = normalizar_texto(
        _primeiro(valores.get("modelo"), modelo, _extrair(payload, "modelo")))
    at["rodovia"] = normalizar_rodovia(
        _primeiro(valores.get("rodovia"), via, _extrair(payload, "rodovia")))
    at["km"] = normalizar_km(
        _primeiro(valores.get("km"), km, _extrair(payload, "km")))
    at["sentido"] = normalizar_sentido(
        _primeiro(valores.get("sentido"), sentido,
                  _extrair(payload, "sentido")))
    at["precisao_metros"] = precisao
    at["qualidade_posicao"] = qualidade
    return at


# ------------------------------------------------------------- pontuacao

def _componente(nome, peso, fator, explicacao):
    return {"nome": nome, "peso": round(float(peso), 4),
            "fator": round(float(fator), 4),
            "contribuicao": round(float(peso) * float(fator), 4),
            "explicacao": explicacao}


def pontuar(a, b, pesos=None):
    """Escore explicavel entre dois conjuntos de atributos (spec 8.5).

    `a`/`b` sao dicts (tipicamente `atributos_registro`), ou aceitam o campo
    `cadeia`: se as cadeias coincidem, a origem e compartilhada e NAO conta
    como confirmacao independente (17.4-3).

    Retorna score 0..1, nivel (forte|moderado|fraco|contraditorio),
    componentes (por que casou), bloqueadores (por que NAO casaria) e a
    distancia em metros. Nunca consolida: apenas mede evidencia.
    """
    pesos = dict(PESOS_PADRAO if pesos is None else pesos)
    componentes = []
    bloqueadores = []

    sa, sb = a.get("numero_serie"), b.get("numero_serie")
    fa, fb = a.get("fabricante"), b.get("fabricante")
    ma, mb = a.get("modelo"), b.get("modelo")
    tem_serie = bool(sa and sb)

    if tem_serie:
        if sa == sb:
            componentes.append(_componente(
                "serie_igual", pesos["serie"], 1.0,
                "mesmo numero de serie normalizado (%s)" % sa))
        else:
            bloqueadores.append({
                "nome": "serie_conflitante",
                "detalhe": "series divergentes: %s vs %s" % (sa, sb)})
    if ma and mb and ma != mb:
        bloqueadores.append({
            "nome": "modelo_conflitante",
            "detalhe": "modelos divergentes: %s vs %s" % (ma, mb)})
    if fa and fb and fa != fb:
        bloqueadores.append({
            "nome": "fabricante_conflitante",
            "detalhe": "fabricantes divergentes: %s vs %s" % (fa, fb)})

    dist = None
    if None not in (a.get("latitude"), a.get("longitude"),
                    b.get("latitude"), b.get("longitude")):
        dist = geo.haversine_m(a["latitude"], a["longitude"],
                               b["latitude"], b["longitude"])
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

    mesma = bool(a.get("cadeia") and a.get("cadeia") == b.get("cadeia"))
    n_indep = 1 if mesma else 2
    if mesma:
        componentes.append({
            "nome": "origem_compartilhada", "peso": 0.0, "fator": 1.0,
            "contribuicao": 0.0,
            "explicacao": "mesma cadeia de evidencia (T59/T72): nao conta "
                          "como confirmacao independente"})
    elif a.get("cadeia") or b.get("cadeia"):
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

    return {
        "score": score,
        "nivel": nivel,
        "componentes": componentes,
        "bloqueadores": bloqueadores,
        "distancia_m": None if dist is None else round(dist, 3),
        "n_evidencias_independentes": n_indep,
        "mesma_origem": mesma,
    }


# --------------------------------------------------------- regra versionada

def registrar_regra(conn, versao=None, pesos=None, raio_m=None, descricao=None,
                    agora=None):
    """Insere (ou recupera) a REGRA_DEDUPLICACAO versionada. Retorna o id."""
    versao = versao or VERSAO_REGRA_PADRAO
    row = dbmod.query_one(
        conn, "SELECT id FROM REGRA_DEDUPLICACAO WHERE versao = ?", (versao,))
    if row is not None:
        return row["id"]
    cfg = json.dumps({
        "pesos": pesos or PESOS_PADRAO,
        "raio_m": RAIO_CANDIDATO_M if raio_m is None else float(raio_m),
        "limiar_forte": LIMIAR_FORTE,
        "limiar_moderado": LIMIAR_MODERADO,
        "limiar_min_candidato": LIMIAR_MIN_CANDIDATO,
        "tolerancia_km": TOLERANCIA_KM,
        "conflito_km": CONFLITO_KM,
        "faixas_proximidade": FAIXAS_PROXIMIDADE,
    }, sort_keys=True, ensure_ascii=False)
    return dbmod.insert(conn, "REGRA_DEDUPLICACAO", {
        "versao": versao,
        "descricao": descricao or "Deduplicacao rastreavel (spec 8/17.4)",
        "configuracao_serializada": cfg,
        "inicio_validade": agora or _agora(),
    })


# ------------------------------------------------------- gerar candidatos

def _ord(a, b):
    return (a, b) if a < b else (b, a)


def _pares_candidatos(ids, attrs, raio_m):
    """Blocking por chaves (serie, via) + grade geografica (spec 8.3)."""
    pares = set()
    por_serie = {}
    por_via = {}
    for rid in ids:
        at = attrs[rid]
        if at.get("numero_serie"):
            por_serie.setdefault(at["numero_serie"], []).append(rid)
        if at.get("rodovia"):
            por_via.setdefault(at["rodovia"], []).append(rid)
    for grupo in list(por_serie.values()) + list(por_via.values()):
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                pares.add(_ord(grupo[i], grupo[j]))

    celula = max(float(raio_m), 1.0) / 111320.0
    grade = {}
    for rid in ids:
        at = attrs[rid]
        if at.get("latitude") is None or at.get("longitude") is None:
            continue
        cx = int(math.floor(at["latitude"] / celula))
        cy = int(math.floor(at["longitude"] / celula))
        grade.setdefault((cx, cy), []).append(rid)
    for (cx, cy), grupo in grade.items():
        vizinhos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vizinhos.extend(grade.get((cx + dx, cy + dy), []))
        for i in grupo:
            for j in vizinhos:
                if i == j:
                    continue
                ai, aj = attrs[i], attrs[j]
                if None in (ai.get("latitude"), ai.get("longitude"),
                            aj.get("latitude"), aj.get("longitude")):
                    continue
                if geo.haversine_m(ai["latitude"], ai["longitude"],
                                   aj["latitude"], aj["longitude"]) <= raio_m:
                    pares.add(_ord(i, j))
    return sorted(pares)


def gerar_candidatos(conn, regra=None, pesos=None, raio_m=None, agora=None):
    """Gera CANDIDATO_DUPLICIDADE a partir dos REGISTRO_FONTE (spec 8.3).

    Nunca decide: todo candidato nasce com estado 'pendente'. Pares na MESMA
    cadeia de evidencia sao ignorados (copia do mesmo registro bruto, 8.1-A).
    Idempotente: UNIQUE(registro_a_id, registro_b_id, regra_id).
    """
    raio_m = RAIO_CANDIDATO_M if raio_m is None else float(raio_m)
    pesos = PESOS_PADRAO if pesos is None else pesos
    regra_id = registrar_regra(conn, versao=regra, pesos=pesos, raio_m=raio_m,
                               agora=agora)
    agora = agora or _agora()

    ids = [r[0] for r in dbmod.query_all(
        conn, "SELECT id FROM REGISTRO_FONTE ORDER BY id")]
    attrs = {rid: atributos_registro(conn, rid) for rid in ids}

    criados, existentes, ignorados = [], [], 0
    for a, b in _pares_candidatos(ids, attrs, raio_m):
        if attrs[a]["cadeia"] == attrs[b]["cadeia"]:
            ignorados += 1                      # mesma origem: nao e duplicata
            continue
        res = pontuar(attrs[a], attrs[b], pesos)
        if not res["bloqueadores"] and res["score"] < LIMIAR_MIN_CANDIDATO:
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
    conn.commit()
    return {
        "regra_id": regra_id,
        "total_registros": len(ids),
        "criados": criados,
        "existentes": existentes,
        "ignorados_mesma_origem": ignorados,
    }


def candidatos(conn, ponto_id=None, estado=None):
    """Lista candidatos (opcionalmente por ponto ou estado)."""
    sql = ("SELECT cd.*, ra.identificador_na_fonte AS a_identificador, "
           "rb.identificador_na_fonte AS b_identificador "
           "FROM CANDIDATO_DUPLICIDADE cd "
           "JOIN REGISTRO_FONTE ra ON ra.id = cd.registro_a_id "
           "JOIN REGISTRO_FONTE rb ON rb.id = cd.registro_b_id ")
    cond, params = [], []
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
    return [dict(r) for r in dbmod.query_all(conn, sql, params)]


# --------------------------------------------------------------- decisoes

def decidir(conn, candidato_id, decisao, usuario, motivo, observacoes=None,
            forcar=False, agora=None):
    """Grava DECISAO_DUPLICIDADE (append-only) com a evidencia e o autor.

    `motivo` e a fundamentacao obrigatoria. Retorna o id da decisao. Nunca
    consolida nada: apenas registra a intencao humana.
    """
    if decisao not in _ESTADO_POR_DECISAO:
        raise ValueError("decisao invalida: %r" % (decisao,))
    if not motivo or not str(motivo).strip():
        raise ValueError("fundamentacao (motivo) obrigatoria")
    cand = dbmod.query_one(
        conn, "SELECT * FROM CANDIDATO_DUPLICIDADE WHERE id = ?", (candidato_id,))
    if cand is None:
        raise ValueError("CANDIDATO_DUPLICIDADE %r inexistente" % (candidato_id,))
    agora = agora or _agora()
    obs = {
        "evidencia": _load_json(cand["evidencias_resumo"]),
        "decisao": decisao,
        "forcar": bool(forcar),
    }
    if observacoes:
        obs["observacoes"] = observacoes
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
    conn.commit()
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


def _escolher_canonico(conn, lista_a, lista_b, nat_a, nat_b):
    if not lista_a and not lista_b:
        return None
    if lista_a and not lista_b:
        return min(lista_a)
    if lista_b and not lista_a:
        return min(lista_b)
    if nat_a == "oficial" and nat_b != "oficial":
        return min(lista_a)
    if nat_b == "oficial" and nat_a != "oficial":
        return min(lista_b)
    return min(min(lista_a), min(lista_b))


def _vincular(conn, tabela, coluna, registro_id, entidade_id, decisao_id):
    existe = conn.execute(
        "SELECT 1 FROM %s WHERE registro_id = ? AND %s = ?" % (tabela, coluna),
        (registro_id, entidade_id)).fetchone()
    if existe is not None:
        return 0                    # preserva vinculo preexistente do pipeline
    conn.execute(
        "INSERT INTO %s (registro_id, %s, decisao_id) VALUES (?,?,?)"
        % (tabela, coluna), (registro_id, entidade_id, decisao_id))
    return 1


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


def _aplicar_um(conn, candidato_id, usuario, agora):
    cand = dbmod.query_one(
        conn, "SELECT * FROM CANDIDATO_DUPLICIDADE WHERE id = ?", (candidato_id,))
    if cand is None:
        return {"candidato_id": candidato_id, "aplicado": False,
                "motivo": "candidato inexistente"}
    dec = decisao_ativa(conn, candidato_id)
    if dec is None or dec["decisao"] != "unificar":
        return {"candidato_id": candidato_id, "aplicado": False,
                "motivo": "sem decisao ativa de unificar"}

    evid = _load_json(cand["evidencias_resumo"])
    obs_dec = _load_json(dec["observacoes"])
    if evid.get("nivel") == "contraditorio" and not obs_dec.get("forcar"):
        return {"candidato_id": candidato_id, "aplicado": False,
                "motivo": "evidencia contraditoria: requer decisao explicita "
                          "com forcar=True"}

    a, b = cand["registro_a_id"], cand["registro_b_id"]
    nat_a, nat_b = _natureza(conn, a), _natureza(conn, b)
    ponto_canonico = _escolher_canonico(
        conn, _pontos(conn, a), _pontos(conn, b), nat_a, nat_b)
    equip_canonico = _escolher_canonico(
        conn, _equipamentos(conn, a), _equipamentos(conn, b), nat_a, nat_b)

    vinculos = 0
    if ponto_canonico is not None:
        for rid in (a, b):
            vinculos += _vincular(conn, "VINCULO_REGISTRO_PONTO", "ponto_id",
                                  rid, ponto_canonico, dec["id"])
    if equip_canonico is not None:
        for rid in (a, b):
            vinculos += _vincular(conn, "VINCULO_REGISTRO_EQUIPAMENTO",
                                  "equipamento_id", rid, equip_canonico,
                                  dec["id"])

    div = _divergencia(atributos_registro(conn, a), atributos_registro(conn, b))
    if div is not None:
        evid["divergencia_posicao"] = div
    evid["aplicado_em"] = agora
    evid["aplicado_por"] = usuario
    evid["ponto_canonico"] = ponto_canonico
    evid["equipamento_canonico"] = equip_canonico
    evid["vinculos_criados"] = vinculos
    conn.execute(
        "UPDATE CANDIDATO_DUPLICIDADE SET estado = 'consolidado', "
        "evidencias_resumo = ? WHERE id = ?",
        (json.dumps(evid, sort_keys=True, ensure_ascii=False), candidato_id))
    return {"candidato_id": candidato_id, "aplicado": True,
            "ponto_canonico": ponto_canonico,
            "equipamento_canonico": equip_canonico,
            "vinculos_criados": vinculos, "divergencia": div}


def aplicar(conn, candidato_id=None, usuario=None, agora=None):
    """Consolida apenas quando ha decisao ativa 'unificar' (spec 8.4/8.7).

    Cria/garante ligacoes VINCULO_* (T63/T64) marcadas com o `decisao_id`,
    escolhendo a entidade canonica (dado oficial tem precedencia). NAO apaga
    nem altera POSICAO_GEOGRAFICA, FONTE ou REGISTRO_FONTE. Idempotente.
    Retorna a lista de resultados (um por candidato tratado).
    """
    agora = agora or _agora()
    if candidato_id is None:
        alvos = [r["id"] for r in dbmod.query_all(
            conn, "SELECT id FROM CANDIDATO_DUPLICIDADE "
                  "WHERE estado = 'decidido_unificar' ORDER BY id")]
    else:
        alvos = [candidato_id]
    resultados = [_aplicar_um(conn, cid, usuario, agora) for cid in alvos]
    conn.commit()
    return resultados


# --------------------------------------------------------------- reversao

def _remover_vinculos(conn, decisao_id):
    total = 0
    for tabela in ("VINCULO_REGISTRO_PONTO", "VINCULO_REGISTRO_EQUIPAMENTO",
                   "VINCULO_REGISTRO_OPERACAO", "VINCULO_REGISTRO_TRECHO"):
        cur = conn.execute(
            "DELETE FROM %s WHERE decisao_id = ?" % tabela, (decisao_id,))
        total += cur.rowcount
    return total


def reverter_decisao(conn, decisao_id, usuario, motivo=None, agora=None):
    """Desfaz uma decisao SEM apagar auditoria (spec 8.7).

    Marca `revertida_em`, remove as ligacoes criadas por `aplicar` (aquelas
    com o `decisao_id`) e restaura o estado anterior do candidato. A linha de
    DECISAO permanece, com o registro da reversao.
    """
    dec = dbmod.query_one(
        conn, "SELECT * FROM DECISAO_DUPLICIDADE WHERE id = ?", (decisao_id,))
    if dec is None:
        raise ValueError("DECISAO_DUPLICIDADE %r inexistente" % (decisao_id,))
    if dec["revertida_em"]:
        return {"decisao_id": decisao_id, "revertida": False,
                "motivo": "decisao ja revertida"}
    agora = agora or _agora()
    obs = _load_json(dec["observacoes"])
    obs["reversao"] = {"por": usuario, "em": agora, "motivo": motivo}
    conn.execute(
        "UPDATE DECISAO_DUPLICIDADE SET revertida_em = ?, observacoes = ? "
        "WHERE id = ?",
        (agora, json.dumps(obs, sort_keys=True, ensure_ascii=False), decisao_id))
    removidos = _remover_vinculos(conn, decisao_id)

    anterior = dbmod.query_one(conn, """
        SELECT decisao FROM DECISAO_DUPLICIDADE
        WHERE candidato_id = ? AND revertida_em IS NULL
        ORDER BY id DESC LIMIT 1""", (dec["candidato_id"],))
    novo_estado = (_ESTADO_POR_DECISAO[anterior["decisao"]]
                   if anterior is not None else "pendente")
    conn.execute("UPDATE CANDIDATO_DUPLICIDADE SET estado = ? WHERE id = ?",
                 (novo_estado, dec["candidato_id"]))
    conn.commit()
    return {"decisao_id": decisao_id, "revertida": True,
            "vinculos_removidos": removidos, "estado": novo_estado}


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
