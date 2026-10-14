# -*- coding: utf-8 -*-
"""Casamento aproximado de nome de municipio (fuzzy + fonetico).

Modulo UNICO, compartilhado entre o CAMINHO DE ENTRADA
(``coletor/fontes/normalizacao.py``) e os utilitarios de limpeza
(``tools/casar_municipios_fuzzy.py``). Antes a mesma regua vivia em dois
lugares; aqui ela passa a ter uma fonte so.

Nada e inventado: quando a confianca nao atinge o limiar, o retorno e ``None``
e o campo permanece NULL.

Algoritmo
---------
1. Normaliza o nome: NFKD sem acento, maiusculo, espacos colapsados,
   pontuacao removida e conectivos (DE/DA/DO/DAS/DOS/E) descartados.
2. Compara contra ``MUNICIPIO`` com ``difflib.SequenceMatcher`` (ratio) e
   reforca com uma chave fonetica simples adaptada do portugues.
3. Preenche somente quando ``ratio >= LIMIAR`` E margem ``>= MARGEM`` sobre o
   segundo colocado (leitura conservadora: quasi-empate fica NULL).
"""
import difflib
import re
import unicodedata

CONECTIVOS = frozenset(("DE", "DA", "DO", "DAS", "DOS", "E"))

LIMIAR = 0.85      # piso de ratio para preencher
MARGEM = 0.05      # vantagem minima sobre o segundo colocado

FAIXAS = ((0.98, 1.01, ">= 0.98"),
          (0.90, 0.98, "0.90 - 0.98"),
          (0.85, 0.90, "0.85 - 0.90"))


# ---------------------------------------------------------------------------
# Normalizacao e chave fonetica
# ---------------------------------------------------------------------------
def texto_base(valor):
    """NFKD sem acento, maiusculo, espacos colapsados (base da normalizacao).

    'Água Branca ' -> 'AGUA BRANCA'. Mesma regra de
    ``coletor.fontes.normalizacao.normalizar_nome_texto``.
    """
    if valor is None:
        return ""
    s = unicodedata.normalize("NFKD", str(valor).strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def normalizar(valor):
    """Nome de municipio -> forma canonica para casamento.

    Ex.: 'Sao Luiz do Paraitinga' -> 'SAO LUIZ PARAITINGA';
         "Olhos D'Agua" -> 'OLHOS D AGUA'.
    """
    s = texto_base(valor)                        # NFKD, upper, espacos
    s = re.sub(r"[^A-Z0-9 ]", " ", s)            # pontuacao -> espaco
    return " ".join(t for t in s.split() if t and t not in CONECTIVOS)


_TROCAS = (("Z", "S"), ("X", "S"), ("Q", "K"), ("C", "K"), ("G", "J"),
           ("V", "F"), ("Y", "I"), ("W", "V"), ("H", ""))


def chave_fonetica(valor):
    """Chave fonetica simples (Soundex adaptado p/ portugues).

    Colapsa consoantes equivalentes e remove vogais (mantendo a inicial), de
    modo que *Poxoreu* e *Poxoreo* caiam na mesma chave (``PSR``). Serve para
    reforco do ratio e desempate; nao substitui o limiar numerico.
    """
    s = normalizar(valor).replace(" ", "")
    for a, b in _TROCAS:
        s = s.replace(a, b)
    if not s:
        return ""
    saida = s[0]
    for ch in s[1:]:
        if ch not in "AEIOU":
            saida += ch
    return saida


def score(a, b):
    """Score de similaridade 0..1 entre duas formas ja normalizadas."""
    if not a or not b:
        return 0.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    # chave fonetica igual so reforca quando o texto ja e proximo (evita que
    # um nome curto foneticamente parecido vire candidato artificial).
    if r >= 0.80 and chave_fonetica(a) == chave_fonetica(b):
        r = max(r, 0.90)
    return r


def _faixa(sc):
    for lo, hi, rot in FAIXAS:
        if lo <= sc < hi:
            return rot
    return "< 0.85"


# ---------------------------------------------------------------------------
# Indice de municipios
# ---------------------------------------------------------------------------
class Indice(object):
    """Lista oficial MUNICIPIO indexada por UF e de forma nacional."""

    def __init__(self, linhas):
        self.por_uf = {}
        self.nacional = []
        for cod, uf, nome in linhas:
            norm = normalizar(nome)
            if not norm:
                continue
            item = (norm, cod, uf, nome)
            self.por_uf.setdefault(uf, []).append(item)
            self.nacional.append(item)

    @classmethod
    def do_banco(cls, conn):
        linhas = [(r["codigo_ibge"], r["uf_sigla"], r["nome"])
                  for r in conn.execute(
                      "SELECT codigo_ibge, uf_sigla, nome FROM MUNICIPIO")]
        return cls(linhas)

    def _top(self, pool, alvo, k=3):
        ranque = sorted(((score(alvo, e[0]), e) for e in pool),
                        key=lambda x: (-x[0], x[1][1]))
        return ranque[:k]


def avaliar(top):
    """(best, second, confiavel, motivo) para o ranking de candidatos."""
    if not top:
        return 0.0, 0.0, False, "sem_candidato"
    best = top[0][0]
    second = top[1][0] if len(top) > 1 else 0.0
    if best < LIMIAR:
        return best, second, False, "abaixo_do_limiar"
    if (best - second) < MARGEM:
        return best, second, False, "ambiguo"
    return best, second, True, "ok"


def _qualificador_na_uf(pool, alvo):
    """Candidato da UF que e o alvo ACRESCENTADO de qualificador.

    Ex.: alvo ``TUNAS`` e candidato ``TUNAS DO PARANA`` na mesma UF. A fonte
    so omitiu o qualificador; nao se deve arriscar outro estado.
    """
    ta = set(alvo.split())
    if not ta:
        return None
    for e in pool:
        if ta < set(e[0].split()):        # subconjunto estrito
            return e
    return None


def resolver(indice, nome, uf):
    """Resolve um nome (com a UF do payload, se houver) contra MUNICIPIO.

    Devolve dict com candidato, escopo, score, margem e se preenche.
    """
    alvo = normalizar(nome)
    if not alvo:
        return None
    pool_uf = indice.por_uf.get(uf, []) if uf else []
    top = indice._top(pool_uf, alvo) if pool_uf else []
    best, second, conf, motivo = avaliar(top)
    escopo = "uf"
    if not conf:
        # a mesma UF tem o alvo com qualificador? entao nao cruza UF.
        guarda = _qualificador_na_uf(pool_uf, alvo) if pool_uf else None
        if guarda is not None:
            return {"codigo": None, "cand_nome": guarda[3], "cand_uf": guarda[2],
                    "score": best, "margem": best - second, "escopo": "uf",
                    "preenche": False, "motivo": "qualificador_na_uf"}
        top_nac = indice._top(indice.nacional, alvo)
        b2, s2, conf2, motivo2 = avaliar(top_nac)
        if b2 >= best or not top:      # nacional e mais informativo
            top, best, second, conf, motivo = top_nac, b2, s2, conf2, motivo2
            escopo = "nacional"
    cand = top[0][1] if top else None      # (norm, cod, uf, nome)
    preenche = bool(conf and cand)
    if preenche:
        if escopo == "uf":
            motivo = "casado_na_uf"
        elif uf and cand[2] != uf:
            motivo = "uf_divergente"
        else:
            motivo = "casado_nacional"
    return {
        "codigo": cand[1] if (cand and conf) else None,
        "cand_nome": cand[3] if cand else None,
        "cand_uf": cand[2] if cand else None,
        "score": best,
        "margem": best - second,
        "escopo": escopo,
        "preenche": preenche,
        "motivo": motivo,
    }


def melhor_por_nome(conn, uf, nome):
    """Atalho para o CAMINHO DE ENTRADA: (uf, nome) -> dict confiavel ou None.

    Exige UF (sem UF nao se arrisca homonimo, preservando a regra do
    resolvedor: 'sem UF nao casa'). Escopo: a UF primeiro e, sem candidato
    confiavel nela, o pais inteiro apenas quando o nome for unico com margem.
    """
    if not uf or not nome:
        return None
    indice = Indice.do_banco(conn)
    d = resolver(indice, nome, uf)
    if d and d.get("preenche") and d.get("codigo"):
        return d
    return None
