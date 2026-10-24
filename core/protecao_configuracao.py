"""Protege configuracao e pastas privadas, preservando os locais publicos do nginx."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import urllib.parse

TOKEN = re.compile(r'''\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{};]|(?:\\.|\$\{[^}]*\}|[^\s{};\#'"\\])+''')
PAGINAS = ('index.html', 'cadastro.html', 'detalhe.html', 'gestao.html',
           'usuarios.html', 'status.html', 'status-estado.html')
INICIO_PUBLICACAO = '# radar: inicio publicacao resources'
FIM_PUBLICACAO = '# radar: fim publicacao resources'
SNIPPET_RADAR = '/etc/nginx/snippets/radar-brasil.conf'


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
    if raiz_local:
        return _publicacao_texto(texto, prefixo, webroot, origem)
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
    return texto, encontrados


def _publicacao_texto(texto, prefixo, webroot, origem):
    """Duas areas publicas: API exata e arquivos estaticos em resources/."""
    original=texto
    base = prefixo.rstrip('/')
    api = base+'/api.pse'
    blocos, diretivas = _analisar(texto)
    handlers = {}
    def atende_api(bloco):
        palavras=bloco['palavras'][1:]
        if palavras[:1]==['=']:
            return palavras[1:]==[api]
        if palavras[:1] in (['~'],['~*']):
            try:return bool(re.search(palavras[1],api,re.I if palavras[0]=='~*' else 0))
            except re.error:return False
        if palavras[:1]==['^~']:
            return len(palavras)>1 and api.startswith(palavras[1])
        return bool(palavras and api.startswith(palavras[0]))
    for i, servidor in enumerate(b for b in blocos if b['palavras']==['server']):
        candidatos = [b for b in blocos if b['pai'] is servidor and b['palavras'][:1]==['location']
                      and atende_api(b)
                      and any(d['pai'] is b and d['palavras'][:1]==['fastcgi_pass'] for d in diretivas)]
        candidatos.sort(key=lambda b:b['palavras']!=['location','=',api])
        if candidatos:
            b=candidatos[0]
            handlers[i]=texto[b['abertura']:b['fim']-1].strip()
    # O template CGI e preservado antes de retirar a secao gerenciada anterior.
    texto=re.sub(re.escape(INICIO_PUBLICACAO)+r'.*?'+re.escape(FIM_PUBLICACAO),'',texto,flags=re.S)
    texto,encontrados=proteger_texto(texto,prefixo,webroot,origem,raiz_local=False)
    blocos,diretivas=_analisar(texto)
    servidores=[b for b in blocos if b['palavras']==['server'] and any(
        l['pai'] is b and l['palavras']==['location','=',base+'/radar.conf'] for l in blocos)]
    externos=[b for b in servidores if any(d['pai'] is b and d['palavras']==['include',SNIPPET_RADAR] for d in diretivas)]
    if externos:
        if len(externos)!=len(servidores):
            raise RuntimeError('Use o include do snippet do Radar em todos os servers que publicam este prefixo; nenhum arquivo foi alterado.')
        # Configuracao fornecida pelo operador: preserva o vhost literalmente.
        # nginx -T ja validou o include; as sondas reais validam seus bloqueios.
        return original,encontrados
    alteracoes=[]
    for i, servidor in enumerate(b for b in blocos if b['palavras']==['server']):
        locais=[b for b in blocos if b['pai'] is servidor and b['palavras'][:1]==['location']]
        if not any(b['palavras']==['location','=',base+'/radar.conf'] for b in locais):
            continue
        if i not in handlers:
            raise RuntimeError('Nao foi encontrado o handler FastCGI .pse do radar; nenhuma regra sera aplicada.')
        # Assume a publicacao deste prefixo; mantem os outros projetos do server.
        for local in locais:
            palavras=local['palavras'][1:]
            caminho=palavras[1] if palavras[:1] in (['='],['^~'],['~'],['~*']) and len(palavras)>1 else palavras[0]
            if caminho==base or caminho.startswith(base+'/'):
                alteracoes.append((local['inicio'],local['fim'],''))
        regras=[INICIO_PUBLICACAO,
                'location = '+json.dumps(api)+' {\n'+handlers[i]+'\n}']
        if base:
            regras.append('location = '+json.dumps(base)+' { return 302 '+json.dumps(base+'/$is_args$args')+'; }')
        regras.append('location = '+json.dumps(base+'/')+' { return 302 '+json.dumps(base+'/resources/index.html$is_args$args')+'; }')
        for pagina in (*PAGINAS,'projeto.json'):
            regras.append('location = '+json.dumps(base+'/'+pagina)+' { return 302 '+json.dumps(base+'/resources/'+pagina+'$is_args$args')+'; }')
        regras.append('location = '+json.dumps(base+'/status-atualizacoes.json')+' { return 302 '+json.dumps(api+'?rota=/api/v1/atualizacoes/status')+'; }')
        regras.append('location ^~ '+json.dumps(base+'/resources/')+' {\n'
                      '    alias '+json.dumps(str(Path(webroot).resolve()/'resources')+'/')+';\n'
                      '    autoindex off;\n    disable_symlinks on;\n'
                      '    if ($uri ~ "(?:^|/)\\\\.") { return 404; }\n'
                      '    if ($uri !~* "\\\\.(?:html|css|js|json|png|ico|svg|jpg|jpeg|webp|woff|woff2)$") { return 404; }\n'
                      '}')
        regras.extend(['location ^~ '+json.dumps(base+'/')+' { return 404; }',FIM_PUBLICACAO])
        alteracoes.append((servidor['abertura'],servidor['abertura'],'\n    '+'\n    '.join(regras)+'\n'))
    for inicio,fim,valor in sorted(alteracoes,reverse=True):
        texto=texto[:inicio]+valor+texto[fim:]
    def tokens(s):return [m.group() for m in TOKEN.finditer(s) if not m.group().startswith('#')]
    if tokens(texto)==tokens(original):
        return original,encontrados
    return texto,encontrados


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
