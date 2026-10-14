# -*- coding: utf-8 -*-
"""Resolucao de URLs de arquivo em portais CKAN (dados.gov.br, ANTT, Recife).

Os portais publicam uma PAGINA de dataset; o arquivo real e um recurso
interno cuja URL muda a cada edicao. Em vez de fixar a URL de um arquivo
mensal, o coletor pergunta a API `package_show` e escolhe o recurso mais
recente pelo padrao do nome.

Isto roda SO no coletor (nunca em tempo de requisicao da API).
"""
import json
import re
import ssl
import urllib.request

from core import config

# Portais do governo usam certificados validos; mantemos a verificacao, mas
# deixamos um caminho tolerante para portais com cadeia incompleta.
_CTX_TOLERANTE = ssl.create_default_context()
_CTX_TOLERANTE.check_hostname = False
_CTX_TOLERANTE.verify_mode = ssl.CERT_NONE


def package_show(base_url, dataset_id, timeout=None, tolerante=False):
    """Retorna a lista de recursos (dicts) do dataset."""
    url = "%s/api/3/action/package_show?id=%s" % (base_url.rstrip("/"), dataset_id)
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    ctx = _CTX_TOLERANTE if tolerante else None
    with urllib.request.urlopen(req, timeout=timeout or config.DEFAULT_TIMEOUT,
                               context=ctx) as resp:
        dados = json.loads(resp.read().decode("utf-8", "replace"))
    if not dados.get("success"):
        raise RuntimeError("package_show falhou para %s" % dataset_id)
    return dados["result"].get("resources", [])


def escolher_recursos(resources, formato=None, padrao=None, chave_versao=None):
    r"""Filtra e ordena recursos por formato/nome.

    formato: sigla desejada (ex.: 'JSON', 'CSV'), case-insensitive.
    padrao:  regex aplicada ao nome OU a URL do recurso.
    chave_versao: funcao que extrai a versao do casamento da regex; o maior
                  valor vence (para pegar a edicao mais nova).
    """
    rx = re.compile(padrao) if padrao else None
    achados = []
    for r in resources:
        if formato and (r.get("format") or "").upper() != formato.upper():
            continue
        alvo = "%s %s" % (r.get("name") or "", r.get("url") or "")
        m = rx.search(alvo) if rx else None
        if rx and not m:
            continue
        versao = chave_versao(m) if (chave_versao and m) else 0
        achados.append((versao, r))
    achados.sort(key=lambda par: par[0], reverse=True)
    return [r for _, r in achados]


def url_do_mais_novo(base_url, dataset_id, formato, padrao,
                     chave_versao=None, tolerante=False):
    """URL direta do recurso mais novo que casa com formato/padrao."""
    resources = package_show(base_url, dataset_id, tolerante=tolerante)
    achados = escolher_recursos(resources, formato, padrao, chave_versao)
    if not achados:
        return None
    return achados[0].get("url")


def versao_numerica(ano_maior=True):
    r"""chave_versao: usa (ano, numero) do padrao 'algo(\d+)_(\d{4})'."""
    def _chave(m):
        if not m:
            return (0, 0)
        grupos = m.groups()
        numero = int(grupos[0]) if grupos[0] and grupos[0].isdigit() else 0
        ano = int(grupos[1]) if len(grupos) > 1 and grupos[1] and grupos[1].isdigit() else 0
        return (ano, numero) if ano_maior else (numero, ano)
    return _chave
