# -*- coding: utf-8 -*-
"""DIF FUNCIONAL (Data Interchange Format, .dif) para o Radar Brasil
(spec 12.6).

------------------------------------------------------------------------------
LAYOUT (baseado na especificacao DIF 1981 / Software Arts; ver tambem a
descricao publica em https://en.wikipedia.org/wiki/Data_Interchange_Format)
------------------------------------------------------------------------------
Todo o arquivo e ASCII/UTF-8, em blocos de 2 ou 3 linhas.

Cabecalho (blocos de 3 linhas: identificador + par numerico + string):

    TABLE
    0,1
    "RADAR_BRASIL"

    VECTORS
    0,<n_colunas>
    "id","tipo_registro",...,"quantidade_faixas_declarada"

    TUPLES
    0,<n_linhas>
    ""

    DATA
    0,0
    ""

  * VECTORS = numero de COLUNAS; a 3a linha nomeia os vetores (colunas),
    separados por virgula e cada um entre aspas duplas (convencao de fato;
    a especificacao original admitia uma unica string de comentario).
  * TUPLES = numero de LINHAS de dados.
  * DATA: apos o valor "dummy" 0,0, seguem os dados.

Dados: cada celula ocupa DUAS linhas: um par "tipo,valor" e a linha seguinte
com o conteudo. Tipos usados:
    1,0        -> string; a linha seguinte e a string entre aspas duplas.
                  Aspas internas sao dobradas (" -> ""). CR/LF internos sao
                  representados como as sequencias literais \\r e \\n (uma
                  unica linha), a MESMA convencao do TXT (spec 12.4), para
                  que DIF e TXT tenham paridade celula a celula.
    0,0 + NA   -> valor AUSENTE/NULL (keyword NA, conforme a especificacao).

Cada LINHA de dados e precedida por um bloco de diretiva:
    -1,0
    BOT
e a tabela inteira e terminada por:
    -1,0
    EOD

Ou seja, DIF = uma linha por ponto, MESMA ordem imutavel das 32 colunas do
TXT; arrays/objetos em celula string JSON compacto; NULL preservado por NA.

Recuperacao: `loads(texto)` devolve (nomes_das_colunas, linhas) onde cada
celula e a string original ou None. Ha teste de ida-e-volta em
tests/test_edifact_dif.py.
"""

from . import campos

NULL_KEYWORD = "NA"


def _escape_str(s):
    """Escapa uma string para celula DIF de uma unica linha."""
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    return s.replace('"', '""')


def _unescape_str(s):
    """Desfaz o escape DIF (aspas dobradas). Nao reverte \\r/\\n (paridade TXT)."""
    return s.replace('""', '"')


def _quote(s):
    return '"' + _escape_str(s) + '"'


def _string_cell(s):
    return ["1,0", _quote(s)]


def celula(v):
    """Valor canonico -> lista de DUAS linhas DIF (par de tipo + conteudo)."""
    if v is None:
        return ["0,0", NULL_KEYWORD]
    if isinstance(v, bool):
        return _string_cell("true" if v else "false")
    if isinstance(v, (list, dict)):
        return _string_cell(campos.json_cell(v))
    return _string_cell(str(v))


def dumps_celulas(rows, colunas, meta=None):
    """Serializa uma matriz de celulas em DIF.

    `colunas` = nomes das colunas (vetores); `rows` = lista de linhas.
    """
    linhas = []
    linhas.extend(["TABLE", "0,1", '"RADAR_BRASIL"'])
    nomes = list(colunas)
    linhas.extend(["VECTORS", "0,%d" % len(nomes),
                   ",".join('"%s"' % _escape_str(c) for c in nomes)])
    linhas.extend(["TUPLES", "0,%d" % len(rows), '""'])
    linhas.extend(["DATA", "0,0", '""'])
    for row in rows:
        linhas.extend(["-1,0", "BOT"])
        for v in row:
            linhas.extend(celula(v))
    linhas.extend(["-1,0", "EOD"])
    return "\n".join(linhas) + "\n"


def dumps(records, meta):
    """Serializa pontos canonicos: 32 colunas do TXT, uma linha por ponto."""
    rows = [campos.build_cells(p) for p in records]
    return dumps_celulas(rows, campos.TXT_COLUMNS, meta)


def envolver_texto(texto, meta=None):
    """Envelopa texto livre (ex.: /ajuda) como DIF de uma coluna ("linha")."""
    linhas = texto.rstrip("\n").split("\n") if texto else [""]
    return dumps_celulas([[ln] for ln in linhas], ["linha"], meta)


# ---------------------------------------------------------------------------
# Leitor DIF (prova de recuperacao dos valores originais)
# ---------------------------------------------------------------------------
def _parse_pair(linha):
    a, _, b = linha.partition(",")
    return a.strip(), b.strip()


def _parse_names(linha):
    """Le a 3a linha de VECTORS: nomes entre aspas, separados por virgula."""
    nomes = []
    i = 0
    n = len(linha)
    while i < n:
        ch = linha[i]
        if ch == '"':
            i += 1
            buf = []
            while i < n:
                if linha[i] == '"':
                    if i + 1 < n and linha[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(linha[i])
                i += 1
            nomes.append("".join(buf))
        else:
            i += 1
    return nomes


def _unquote(linha):
    s = linha.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return _unescape_str(s)


def loads(texto):
    """Le um arquivo DIF. Retorna (colunas, linhas).

    `colunas` = lista de nomes; `linhas` = lista de listas de celulas, onde
    cada celula e str (tipo 1), numero (tipo 0 + V) ou None (tipo 0 + NA).
    """
    linhas = texto.split("\n")
    i = 0
    n = len(linhas)
    colunas = []
    # -- cabecalho ---------------------------------------------------------
    while i < n:
        ident = linhas[i].strip()
        if ident in ("TABLE", "VECTORS", "TUPLES", "DATA"):
            ter = linhas[i + 2] if i + 2 < n else ""
            i += 3
            if ident == "VECTORS":
                colunas = _parse_names(ter)
            elif ident == "DATA":
                break
        else:
            i += 1
    # -- dados -------------------------------------------------------------
    dados = []
    atual = None
    texto_livre = []
    while i < n:
        linha = linhas[i].rstrip("\r")
        if linha.strip() == "":
            i += 1
            continue
        if linha.strip().startswith("-1,"):
            kw = linhas[i + 1].strip() if i + 1 < n else ""
            i += 2
            if kw == "BOT":
                if atual is not None:
                    dados.append(atual)
                atual = []
            elif kw == "EOD":
                break
            continue
        tipo, valor = _parse_pair(linha)
        conteudo = linhas[i + 1].rstrip("\r") if i + 1 < n else ""
        i += 2
        if atual is None:
            atual = []
        if tipo == "1":
            atual.append(_unquote(conteudo))
        elif tipo == "0":
            kw = conteudo.strip()
            if kw == NULL_KEYWORD:
                atual.append(None)
            elif kw == "V":
                atual.append(_to_number(valor))
            elif kw == "TRUE":
                atual.append(True)
            elif kw == "FALSE":
                atual.append(False)
            else:
                atual.append(kw)
        # tipo -1 inesperado no meio de dados: ignora
    if atual is not None:
        dados.append(atual)
    loads.texto_livre = texto_livre
    return colunas, dados


def _to_number(s):
    try:
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


loads.texto_livre = []
