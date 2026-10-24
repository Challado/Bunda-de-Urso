"""Protege configuracao e pastas privadas, preservando os locais publicos do nginx."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import urllib.parse

TOKEN = re.compile(r'''\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{};]|(?:\\.|\$\{[^}]*\}|[^\s{};\#'"\\])+''')


def _analisar(texto):
    blocos, diretivas, pilha, palavras = [], [], [], []
    inicio = 0
    for m in TOKEN.finditer(texto):
        token = m.group()
        if token.startswith("#"):
            continue
        if token == "{":
            bloco = {"palavras": palavras, "inicio": inicio, "abertura": m.end(),
                     "pai": pilha[-1] if pilha else None}
            blocos.append(bloco)
            pilha.append(bloco)
            palavras = []
        elif token == "}":
            if not pilha:
                raise RuntimeError("Chaves inesperadas na configuracao do nginx.")
            pilha.pop()["fim"] = m.end()
            palavras = []
        elif token == ";":
            diretivas.append({"palavras": palavras, "pai": pilha[-1] if pilha else None})
            palavras = []
        else:
            if not palavras:
                inicio = m.start()
            palavras.append(shlex.split(token)[0])
    if pilha:
        raise RuntimeError("Bloco incompleto na configuracao do nginx.")
    return blocos, diretivas


def proteger_texto(texto, prefixo, webroot, origem, raiz_local=False):
    """Retorna texto e numero de servers do radar identificados neste arquivo."""
    uri = prefixo.rstrip("/") + "/radar.conf"
    if not uri.startswith("/") or any(ord(c) < 32 for c in uri):
        raise RuntimeError("Prefixo web invalido para proteger radar.conf.")
    host = urllib.parse.urlsplit(origem).hostname
    blocos, diretivas = _analisar(texto)
    alteracoes, encontrados = [], 0
    regra = 'location = ' + json.dumps(uri, ensure_ascii=False) + ' {\n        # radar: configuracao acessivel somente pela API administrativa\n        return 404;\n    }'
    for servidor in (b for b in blocos if b["palavras"] == ["server"]):
        corresponde = False
        for d in diretivas:
            if not d["palavras"]:
                continue
            if host and d["pai"] is servidor and d["palavras"][0] == "server_name" and host in [p.lower() for p in d["palavras"][1:]]:
                corresponde = True
            pai = d["pai"]
            while pai is not None and pai is not servidor:
                pai = pai["pai"]
            if pai is servidor and d["palavras"][0] in ("root", "alias") and len(d["palavras"]) == 2:
                raiz = d["palavras"][1]
                if raiz.startswith("/") and "$" not in raiz:
                    destino = Path(webroot).resolve()
                    # Um link intermediario pode levar para fora da raiz
                    # canonica, mas a URI continua servindo o mesmo destino.
                    servido = (Path(raiz) / prefixo.lstrip('/')).resolve()
                    if destino.is_relative_to(Path(raiz).resolve()) or (d['palavras'][0] == 'root' and servido == destino):
                        corresponde = True
        if not corresponde:
            continue
        encontrados += 1
        locais = [b for b in blocos if b["pai"] is servidor and b["palavras"] == ["location", "=", uri]]
        if locais:
            for local in locais:
                if texto[local["inicio"]:local["fim"]] != regra:
                    alteracoes.append((local["inicio"], local["fim"], regra))
        else:
            alteracoes.append((servidor["abertura"], servidor["abertura"], "\n    " + regra + "\n"))
    for inicio, fim, valor in sorted(alteracoes, reverse=True):
        texto = texto[:inicio] + valor + texto[fim:]
    if raiz_local:
        # Blocos exatos/de prefixo ganham de handlers genericos (.pse, estaticos).
        # O instalador testa os bloqueios por HTTP antes de copiar dados privados.
        regras = [("^~", prefixo.rstrip("/") + "/" + nome + "/")
                  for nome in ("dados", "logs", "core", "coletor", "config", "sql",
                               "web", "deploy", "tools", ".git", ".github", ".updater")]
        regras.append(("^~", prefixo.rstrip("/") + "/.radar-"))
        regras += [("=", prefixo.rstrip("/") + "/" + nome)
                   for nome in ("radar.conf.lock", "radar.conf.anterior", "radar.conf.auditoria.jsonl", "api_token", "assistente_chave",
                                "VERSAO", "README.md", "LICENSE", "arquivos-instalados.json")]
        # Reanalisa depois da insercao do bloqueio radar.conf.
        blocos, _ = _analisar(texto)
        alteracoes = []
        for servidor in (b for b in blocos if b["palavras"] == ["server"]):
            if not any(b["pai"] is servidor and b["palavras"] == ["location", "=", uri] for b in blocos):
                continue
            for modificador, caminho in regras:
                palavras = ["location", modificador, caminho]
                regra_privada = "location " + modificador + " " + json.dumps(caminho) + " { return 404; }"
                locais = [b for b in blocos if b["pai"] is servidor and b["palavras"] == palavras]
                if locais:
                    for local in locais:
                        if texto[local["inicio"]:local["fim"]] != regra_privada:
                            alteracoes.append((local["inicio"], local["fim"], regra_privada))
                else:
                    alteracoes.append((servidor["abertura"], servidor["abertura"], "\n    " + regra_privada + "\n"))
        for inicio, fim, valor in sorted(alteracoes, reverse=True):
            texto = texto[:inicio] + valor + texto[fim:]
    return texto, encontrados


def planejar(prefixo, webroot, origem, raiz_local=False):
    r = subprocess.run(["nginx", "-T"], check=True, capture_output=True, text=True, timeout=30)
    arquivos = dict.fromkeys(re.findall(r"^# configuration file (.+):$", r.stdout, re.M))
    plano, encontrados, vistos = [], 0, set()
    for nome in arquivos:
        arquivo = Path(nome).resolve(strict=True)
        if arquivo in vistos:
            continue
        vistos.add(arquivo)
        anterior = arquivo.read_text()
        novo, servidores = proteger_texto(anterior, prefixo, webroot, origem, raiz_local=raiz_local)
        encontrados += servidores
        if novo != anterior:
            if not arquivo.is_relative_to(Path("/etc/nginx")):
                raise RuntimeError("A protecao automatica exige configuracoes do nginx dentro de /etc/nginx.")
            plano.append((arquivo, anterior, novo))
    if not encontrados:
        raise RuntimeError("Nao foi identificado o server do radar no nginx por web.origem ou web.raiz.")
    return plano
