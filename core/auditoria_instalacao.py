"""Checagens locais do atualizador. Nao coleta fontes nem envia dados ao GitHub."""
import hashlib
import json
import os
import grp
import pwd
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import urllib.parse
import urllib.error
import urllib.request

from . import caminhos


def chaves_gravadas(texto):
    """Inclui chaves vazias: vazio e uma escolha explicita de usar o padrao."""
    secao, chaves = None, set()
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(("#", ";")):
            continue
        if linha.startswith("[") and linha.endswith("]"):
            secao = linha[1:-1].strip().lower()
        elif "=" in linha:
            chaves.add((secao, linha.split("=", 1)[0].strip().lower()))
    return chaves


def opcoes_faltantes(texto):
    gravadas = chaves_gravadas(texto)
    return {par: valor for par, valor in caminhos.PADROES.items() if par not in gravadas}


def comando_coletor(linha, wrapper):
    """Reconhece somente entradas do coletor; nunca os sincronizadores privados."""
    if not linha.strip() or linha.lstrip().startswith("#") or "=" in linha.split()[0]:
        return False
    try:
        partes = shlex.split(linha, comments=True)
    except ValueError:
        return False
    comando = partes[1:] if partes[0].startswith("@") else partes[5:]
    if comando[:1] == ["root"]:
        comando = comando[1:]
    if not comando:
        return False
    executavel = Path(comando[0]).name
    permitidos = {"radar-tick.sh", "radar-api.pse", "api.pse", "sh", "bash", "env",
                  "flock", "timeout", "nice", "cd"}
    if executavel not in permitidos and not executavel.startswith("python"):
        return False
    partes = comando
    if any(Path(p).name in ("radar-dados-sync.py", "radar-base-sync.py") for p in partes):
        return False
    for i, parte in enumerate(partes):
        if Path(parte).name == "radar-tick.sh":
            return True
        if parte == "coletor.tick" and i and partes[i - 1] == "-m":
            return True
        if parte.endswith("/coletor/tick.py") and (
                str(wrapper.parent) in parte or "/radar/" in parte):
            return True
        if Path(parte).name in ("api.pse", "radar-api.pse") and (
                partes[i + 1:i + 2] == ["tick"] or partes[i + 1:i + 3] == ["cron", "tick"]):
            return True
    return False


def ler_crontab():
    env = dict(os.environ, LC_ALL="C")
    res = subprocess.run(["crontab", "-l"], capture_output=True, text=True,
                         env=env, timeout=15)
    from . import atualizacoes
    # Cron pode conter comandos de outros projetos com credenciais. Seu texto
    # permanece no backup restrito; o diario registra somente o resultado.
    atualizacoes.evento("cron.ler", codigo_comando=res.returncode,
                       stderr=res.stderr, tem_crontab=res.returncode == 0)
    if res.returncode == 0:
        return res.stdout
    if res.returncode == 1 and "no crontab for" in res.stderr.lower():
        return ""
    raise RuntimeError("Nao foi possivel ler o crontab de root; nenhuma linha deve ser sobrescrita.")


def bootstrap(texto, conf):
    return texto.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1).replace(
        'CONF_PADRAO = "/etc/radar-brasil/radar.conf"', 'CONF_PADRAO = ' + repr(str(conf)), 1)


def render_logrotate(origem, logs):
    diretorio = str(logs).replace("\\", "\\\\").replace('"', '\\"')
    conta = pwd.getpwuid(os.geteuid())
    gid = Path(logs).stat().st_gid if Path(logs).exists() else conta.pw_gid
    usuario = caminhos.valor("instalacao", "usuario", conta.pw_name)[0]
    grupo = caminhos.valor("instalacao", "grupo", grp.getgrgid(gid).gr_name)[0]
    # Alem de conferir as contas, impede injetar diretivas no modelo.
    pwd.getpwnam(usuario)
    grp.getgrnam(grupo)
    return ((origem / "deploy" / "openclaw-radar.logrotate").read_text()
            .replace("@RADAR_LOG_DIR@", diretorio)
            .replace("@RADAR_LOG_USUARIO@", usuario)
            .replace("@RADAR_LOG_GRUPO@", grupo))


def validar_logrotate(arquivo):
    comando = ["logrotate", "--debug", str(arquivo)]
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=30)
        from . import atualizacoes
        atualizacoes.evento("logrotate.validar", comando=comando, codigo_comando=r.returncode,
                           stdout=r.stdout, stderr=r.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"checagem": "logrotate.sintaxe", "estado": "erro", "comando": comando,
                "detalhe": "Nao foi possivel concluir a verificacao do logrotate: " + str(exc)}
    resultado = {"checagem": "logrotate.sintaxe", "estado": "ok" if r.returncode == 0 else "erro",
                 "codigo_saida": r.returncode,
                 "detalhe": "configuracao e permissoes aceitas, sem executar rotacao"}
    if r.returncode:
        linhas = (r.stderr + "\n" + r.stdout).splitlines()
        erros = [linha for linha in linhas if linha.strip().lower().startswith("error:")]
        resultado.update(comando=comando, stdout=r.stdout[:16384], stderr=r.stderr[:16384],
                         saida_truncada=len(r.stdout) > 16384 or len(r.stderr) > 16384,
                         detalhe="Logrotate reprovou: " + "\n".join(erros or linhas[-20:])[:4096])
    return resultado


def artefatos(origem, dirs, codigo, estaticos):
    """Bytes esperados, inclusive arquivos gerados a partir da configuracao."""
    for pasta in codigo:
        for arquivo in sorted((origem / pasta).rglob("*")):
            if not arquivo.is_file() or "__pycache__" in arquivo.parts or arquivo.suffix == ".pyc":
                continue
            rel = arquivo.relative_to(origem)
            conteudo = arquivo.read_bytes()
            if str(rel) == "web/api.pse":
                # O bootstrap interno conserva seu shebang original.
                conteudo = conteudo.decode().replace(
                    'CONF_PADRAO = "/etc/radar-brasil/radar.conf"',
                    'CONF_PADRAO = ' + repr(str(dirs["conf"])), 1).encode()
            yield dirs["codigo"] / rel, conteudo
    for nome in ("README.md", "LICENSE"):
        yield dirs["codigo"] / nome, (origem / nome).read_bytes()
    for arquivo in sorted((origem / "web").iterdir()):
        if not arquivo.is_file() or arquivo.suffix not in estaticos:
            continue
        conteudo = arquivo.read_bytes()
        if arquivo.name == "projeto.json":
            descritor = json.loads(conteudo)
            descritor["url"] = caminhos.web_url()
            conteudo = (json.dumps(descritor, ensure_ascii=False, indent=2) + "\n").encode()
        yield dirs["web"] / arquivo.name, conteudo
    api = bootstrap((origem / "deploy" / "api.pse").read_text(), dirs["conf"]).encode()
    yield dirs["web"] / "api.pse", api
    yield dirs["codigo"].parent / "radar-api.pse", api
    wrapper = (origem / "deploy" / "radar-tick.sh").read_text().replace(
        '${RADAR_PYTHON:-/usr/bin/python3}', '${RADAR_PYTHON:-' + sys.executable + '}')
    yield dirs["codigo"].parent / "radar-tick.sh", wrapper.encode()


def arquivos_divergentes(origem, dirs, codigo, estaticos):
    divergencias = []
    for alvo, esperado in artefatos(origem, dirs, codigo, estaticos):
        estado = "ausente" if not alvo.is_file() else "diferente"
        if not alvo.is_file() or hashlib.sha256(alvo.read_bytes()).digest() != hashlib.sha256(esperado).digest():
            divergencias.append({"arquivo": str(alvo), "estado": estado})
    return divergencias


def ambiente_servidor(laboratorio=False):
    """Nao anuncia servicos como saudaveis quando nao foi possivel verifica-los."""
    if laboratorio:
        return [{"checagem": "servicos_do_servidor", "estado": "nao_aplicavel",
                 "detalhe": "Laboratorio: nenhum servico ou cron do sistema e alterado."}]
    resultados = []
    for comando in ("git", "sh", "crontab", "runuser", "pdftotext", "nginx", "logrotate", "systemctl"):
        resultados.append({"checagem": "comando." + comando,
                           "estado": "ok" if shutil.which(comando) else "erro",
                           "detalhe": "disponivel" if shutil.which(comando) else "comando ausente; instale antes de aplicar"})
    if shutil.which("systemctl"):
        for alternativas in (("cron.service", "crond.service"), ("nginx.service",),
                              ("fcgiwrap.socket", "fcgiwrap.service")):
            ativos = []
            for unidade in alternativas:
                r = subprocess.run(["systemctl", "is-active", unidade], capture_output=True,
                                   text=True, timeout=15)
                from . import atualizacoes
                atualizacoes.evento("auditoria.servico", unidade=unidade, codigo_comando=r.returncode,
                                   stdout=r.stdout, stderr=r.stderr)
                if r.returncode == 0:
                    ativos.append(unidade)
            resultados.append({"checagem": "servico." + alternativas[0].split(".")[0],
                               "estado": "ok" if ativos else "erro",
                               "detalhe": ", ".join(ativos) if ativos else "servico inativo ou indisponivel; confira antes de aplicar"})
    if shutil.which("nginx"):
        r = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=30)
        from . import atualizacoes
        atualizacoes.evento("auditoria.nginx", codigo_comando=r.returncode, stdout=r.stdout, stderr=r.stderr)
        resultados.append({"checagem": "nginx.configuracao", "estado": "ok" if r.returncode == 0 else "erro",
                           "detalhe": "sintaxe aceita" if r.returncode == 0 else "nginx -t reprovou; confira a configuracao do servidor"})
    return resultados


def verificar_http(origem, prefixo, pagina, configuracao_privada=False):
    url = urllib.parse.urlsplit(origem)
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise RuntimeError("web.origem invalida: use somente http(s)://host[:porta].")
    if not prefixo.startswith("/") or prefixo.startswith("//"):
        raise RuntimeError("web.url deve ser um prefixo local iniciado por uma barra.")
    base = origem.rstrip("/") + "/" + prefixo.strip("/")
    base = base.rstrip("/")
    def baixar(caminho):
        req = urllib.request.Request(base + caminho, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=15) as resposta:
            if resposta.status != 200:
                raise RuntimeError("HTTP nao retornou 200.")
            return resposta.read(2 * 1024 * 1024)
    saude = json.loads(baixar("/api.pse?rota=/health/ready"))
    if saude.get("status") != "ready":
        raise RuntimeError("A URL publica nao retornou a prontidao da API.")
    if baixar("/gestao.html") != pagina.read_bytes():
        raise RuntimeError("O nginx nao esta servindo a pagina atualizada neste endereco.")
    if configuracao_privada:
        try:
            with urllib.request.urlopen(base + "/radar.conf", timeout=15):
                raise RuntimeError("O nginx permitiu baixar a configuracao diretamente; reaplique a protecao do link.")
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 404):
                raise RuntimeError("Nao foi confirmado o bloqueio HTTP de radar.conf.") from exc


def comando_fila(linha):
    """Somente cron fila da API; nao reconhece echo nem sincronizadores externos."""
    if not linha.strip() or linha.lstrip().startswith('#'):
        return False
    try:
        partes = shlex.split(linha, comments=True)
    except ValueError:
        return False
    comando = partes[1:] if partes[0].startswith('@') else partes[5:]
    if comando[:1] == ['root']:
        comando = comando[1:]
    if not comando:
        return False
    nome = Path(comando[0]).name
    if nome not in ('api.pse', 'radar-api.pse', 'env', 'flock', 'timeout', 'nice') and not nome.startswith('python'):
        return False
    if any(Path(p).name in ('radar-dados-sync.py','radar-base-sync.py') for p in comando):
        return False
    return any(Path(p).name in ('api.pse','radar-api.pse') and comando[i+1:i+3] == ['cron','fila']
               for i,p in enumerate(comando))
