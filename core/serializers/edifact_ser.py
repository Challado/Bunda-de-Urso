# -*- coding: utf-8 -*-
"""UN/EDIFACT FUNCIONAL para o Radar Brasil (spec 12.5).

------------------------------------------------------------------------------
GUIA DE IMPLEMENTACAO (bilateral Radar Brasil -> consumidor)
------------------------------------------------------------------------------
Mensagem: GENRAL:D:96A:UN (General purpose message, diretorio D, versao 96A,
UN = UN/EDIFACT). GENRAL e um tipo de mensagem real do diretorio UN/EDIFACT,
adequado a intercambio de proposito geral e texto livre.

Envelope UN/EDIFACT:
    UNB+UNOC:3+RADARBRASIL:ZZ+RECEPTOR:ZZ+<AAMMDD:HHMM>+<ref>'   (intercambio)
    UNH+<ref>+GENRAL:D:96A:UN'                                    (mensagem)
    ...
    UNT+<n_segmentos_da_mensagem>+<ref>'
    UNZ+1+<ref>'
Separadores: elemento '+', componente ':', terminador de segmento "'",
caractere de liberacao '?' (release). Qualquer um desses quatro caracteres
que apareca DENTRO de um valor e escapado com '?' (ex.: '+' -> '?+',
"'" -> "?'", ':' -> '?:', '?' -> '??'). O leitor (`loads`) desfaz o escape.

Service String Advice: NAO emitimos UNA. Os separadores default acima sao
os mesmos de UNOC (ISO-8859-1); por isso UNB usa "UNOC:3" (sintaxe nivel 3).

Segmentos de cabecalho da mensagem:
    BGM+RADAR_BRASIL+<ref>'                    nome/numero do documento
    DTM+137+<consultado_em>'                   data/hora do documento
    FTX+AAI+1+<nota de layout>'                informacao geral (opcional)

Dados (um segmento por ponto/registro):
    RAD0+<col1>+<col2>+...+<col32>'
    * "RAD0" e um SEGMENTO DE PROJETO (guia bilateral). NAO e um segmento
      padronizado do diretorio UN/EDIFACT e NUNCA e apresentado como tal.
      Ele carrega exatamente as 32 COLUNAS CANONICAS do TXT v1 (spec 12.4),
      na MESMA ordem imutavel publicada em /api/v1/ajuda, uma coluna por
      elemento, posicao 1..32. Arrays/objetos vao em JSON compacto UTF-8.
    * Elemento vazio (nada entre dois separadores) = valor AUSENTE/NULL.
      Um valor string vazio produziria o mesmo elemento vazio; isso e
      documentado e nao ocorre com as colunas canonicas (JSON compacto e
      sempre nao-vazio quando o valor existe).
    * Contagens UNT/UNZ sao calculadas de fato (nao ha numero fixo).

Recuperacao: `loads(texto)` devolve, para cada segmento RAD0, a lista de
elementos ja dessescapados (string) ou None para elemento vazio. Ha teste de
ida-e-volta em tests/test_edifact_dif.py.
"""

import datetime

from . import campos

# Separadores UN/EDIFACT (default UNOC / ISO 8859-1).
SEG = "'"        # terminador de segmento
ELEM = "+"       # separador de elemento
COMP = ":"       # separador de componente
RELEASE = "?"    # caractere de liberacao (escape)

_RESERVADOS = frozenset((RELEASE, SEG, ELEM, COMP))


def esc(s):
    """Escapa separadores reservados e o proprio '?' do EDIFACT."""
    if s is None:
        return ""
    out = []
    for ch in str(s):
        if ch in _RESERVADOS:
            out.append(RELEASE)
        out.append(ch)
    return "".join(out)


def unesc(s):
    """Desfaz o escape EDIFACT."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == RELEASE and i + 1 < n:
            out.append(s[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def celula(v):
    """Valor canonico -> texto de UM elemento EDIFACT (NULL = vazio)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return esc(campos.json_cell(v))
    return esc(v)


def _split_segmentos(texto):
    """Divide em segmentos respeitando o escape '?'."""
    segs = []
    atual = []
    i = 0
    n = len(texto)
    while i < n:
        ch = texto[i]
        if ch == RELEASE and i + 1 < n:
            atual.append(ch)
            atual.append(texto[i + 1])
            i += 2
            continue
        if ch == SEG:
            segs.append("".join(atual))
            atual = []
            i += 1
            continue
        atual.append(ch)
        i += 1
    resto = "".join(atual)
    if resto.strip():
        segs.append(resto)
    return [s for s in segs if s.strip()]


def _split_elementos(corpo):
    """Divide o corpo de um segmento em elementos, respeitando o escape."""
    partes = []
    atual = []
    i = 0
    n = len(corpo)
    while i < n:
        ch = corpo[i]
        if ch == RELEASE and i + 1 < n:
            atual.append(ch)
            atual.append(corpo[i + 1])
            i += 2
            continue
        if ch == ELEM:
            partes.append("".join(atual))
            atual = []
            i += 1
            continue
        atual.append(ch)
        i += 1
    partes.append("".join(atual))
    return partes


def _cabecalho(segs, ref, meta, nota_layout=True):
    """Acrescenta UNH/BGM/DTM(/FTX de layout) ao inicio da mensagem."""
    segs.append("UNH" + ELEM + ref + ELEM + "GENRAL" + COMP + "D" + COMP +
                "96A" + COMP + "UN")
    segs.append("BGM" + ELEM + "RADAR_BRASIL" + ELEM + ref)
    segs.append("DTM" + ELEM + "137" + COMP +
                esc(str(meta.get("consultado_em") or "")))
    if nota_layout:
        segs.append("FTX" + ELEM + "AAI" + ELEM + "1" + ELEM +
                    esc("RAD0: 32 colunas TXT v1 na ordem canonica; "
                        "ver /api/v1/ajuda; elemento vazio = NULL"))


def _fechar(segs, ref):
    """Fecha a mensagem (UNT com a contagem real) e o intercambio (UNZ)."""
    segs.append("UNT" + ELEM + str(len(segs)) + ELEM + ref)
    segs.append("UNZ" + ELEM + "1" + ELEM + ref)
    return SEG.join(segs) + SEG + "\n"


def _novo_intercambio():
    agora = datetime.datetime.now(datetime.timezone.utc)
    dt = agora.strftime("%y%m%d:%H%M")
    ref = agora.strftime("%y%m%d%H%M%S")
    unb = "UNB" + ELEM + ELEM.join([
        "UNOC" + COMP + "3",
        "RADARBRASIL" + COMP + "ZZ",
        "RECEPTOR" + COMP + "ZZ",
        dt, ref])
    return [unb], ref


def dumps_celulas(rows, meta=None):
    """Serializa uma matriz de celulas (linha = lista de valores canonicos).

    Cada linha vira um segmento RAD0 com um elemento por coluna.
    """
    meta = meta or {}
    segs, ref = _novo_intercambio()
    _cabecalho(segs, ref, meta)
    for linha in rows:
        segs.append("RAD0" + ELEM + ELEM.join(celula(c) for c in linha))
    return _fechar(segs, ref)


def dumps(records, meta):
    """Serializa pontos canonicos: RAD0 com as 32 colunas canonicas do TXT."""
    rows = [campos.build_cells(p) for p in records]
    return dumps_celulas(rows, meta)


def envolver_texto(texto, meta=None):
    """Envelopa um texto livre (ex.: /ajuda) como mensagem EDIFACT valida:
    cada linha do texto vira um segmento FTX (texto livre, codigo AAI)."""
    meta = meta or {}
    linhas = texto.rstrip("\n").split("\n") if texto else [""]
    segs, ref = _novo_intercambio()
    _cabecalho(segs, ref, meta, nota_layout=False)
    for ln in linhas:
        segs.append("FTX" + ELEM + "AAI" + ELEM + "1" + ELEM + esc(ln))
    return _fechar(segs, ref)


def loads(texto):
    """Le um texto EDIFACT e devolve as linhas de dados (segmentos RAD0).

    Retorna lista de listas; cada elemento e a string dessescapada ou None
    quando o elemento estava vazio (NULL). Tambem devolve as linhas FTX de
    texto livre em `loads.texto_livre` (atributo da funcao, util na ajuda).
    """
    linhas = []
    texto_livre = []
    for seg in _split_segmentos(texto):
        tag = seg.split(ELEM, 1)[0].split(COMP, 1)[0]
        if tag == "RAD0":
            corpo = seg[len("RAD0"):]
            elems = _split_elementos(corpo)
            # o primeiro elemento e o vazio antes do primeiro '+'
            vals = elems[1:]
            linhas.append([None if e == "" else unesc(e) for e in vals])
        elif tag == "FTX":
            elems = _split_elementos(seg[len("FTX"):])
            # FTX+4451+4453+4440 -> texto em elems[3]
            if len(elems) > 3:
                texto_livre.append(unesc(elems[3]))
    loads.texto_livre = texto_livre
    return linhas


loads.texto_livre = []
