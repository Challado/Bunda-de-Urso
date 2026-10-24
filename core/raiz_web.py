"""Migracao local pela API para codigo/configuracao/dados na raiz do site.

Nunca substitui a arvore inteira da instalacao. Nao oferece execucao por HTTP.
A preparacao do sistema operacional e exclusiva desta primeira etapa, como root.
"""
from contextlib import closing, ExitStack
import datetime
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import caminhos, db, atualizacoes, auditoria_instalacao as auditoria
from .configuracao import _editar
from .contexto_api import operacao_local
from .instalacao import CODIGO, ESTATICOS, _usar_conf, _executar, _cgi, _esperar_coletor, _diretorio

PASTAS_PRIVADAS = (*CODIGO, "dados", "logs")


def _json(arquivo, valor):
    arquivo.write_text(json.dumps(valor, ensure_ascii=False, indent=2) + "\n")
    arquivo.chmod(0o660)


def _sem_links(pasta):
    if pasta.is_symlink():
        raise RuntimeError("Destino privado nao pode ser link: " + str(pasta))
    if (pasta/'backups').is_symlink():
        raise RuntimeError('Container de backups nao pode ser link: '+str(pasta/'backups'))
    if pasta.exists():
        for base, dirs, arquivos in os.walk(pasta):
            if Path(base) == pasta:
                dirs[:] = [n for n in dirs if n != "backups"]
            for nome in (*dirs, *arquivos):
                item = Path(base) / nome
                if item.is_symlink():
                    raise RuntimeError("Link em dados/codigo exige revisao antes da migracao: " + str(item))


def _permissoes(pasta, conta):
    # Nao percorre o restante do site nem os antigos diretorios de instalacao.
    itens = [pasta]
    if pasta.is_dir():
        for base, dirs, arquivos in os.walk(pasta):
            if Path(base) == pasta:
                dirs[:] = [n for n in dirs if n != "backups"]
            itens.extend(Path(base) / n for n in (*dirs, *arquivos))
    for item in itens:
        if item.is_symlink():
            raise RuntimeError("Link inesperado ao ajustar permissoes: " + str(item))
        if os.geteuid() == 0:
            os.chown(item, conta.pw_uid, conta.pw_gid)
        item.chmod(0o2770 if item.is_dir() else 0o660)


def _preparar_backups(dados, conta):
    # Os arquivos historicos continuam intactos, mas o processo www-data
    # precisa atravessar/criar os containers usados pelas migracoes da base.
    for pasta in (dados/'backups', dados/'backups/identidade'):
        if pasta.is_symlink():
            raise RuntimeError('Container de backups nao pode ser link: '+str(pasta))
        pasta.mkdir(parents=True,exist_ok=True,mode=0o2770)
        if os.geteuid()==0:
            os.chown(pasta,conta.pw_uid,conta.pw_gid)
        pasta.chmod(0o2770)


def _copiar_dados(origem, destino, banco):
    """Preserva a fila e os brutos, sem copiar uma base WAL de forma inconsistente."""
    if origem == destino:
        return
    if destino.exists() and any(destino.iterdir()):
        raise RuntimeError("Existem dados em dois destinos diferentes; nada sera sobrescrito: " + str(destino))
    destino.mkdir(parents=True, exist_ok=True)
    for item in origem.iterdir():
        if item == banco or item.name in {banco.name + '-wal', banco.name + '-shm', banco.name + '-journal'}:
            continue
        # Backups anteriores permanecem intactos na origem; nao os duplica.
        if item.name == 'backups' or item.name.endswith('.lock'):
            continue
        alvo = destino / item.name
        if item.is_dir():
            shutil.copytree(item, alvo)
        else:
            shutil.copy2(item, alvo)


def _rebase_cache(banco, anterior, novo):
    """Recupera referencias inclusive quando o operador ja moveu apenas o banco."""
    alterados = 0
    with closing(db.connect(banco)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='ARTEFATO_COLETA'").fetchone():
            return 0
        for linha in conn.execute('SELECT id, caminho_cache, hash_sha256 FROM ARTEFATO_COLETA').fetchall():
            arq = Path(linha['caminho_cache'])
            if arq.is_absolute() and arq.is_relative_to(novo):
                continue
            if arq.is_absolute() and arq.is_relative_to(anterior):
                destino = novo / arq.relative_to(anterior)
            else:
                digest = linha['hash_sha256']
                if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                    raise RuntimeError('Artefato com hash invalido; cache nao foi realocado.')
                sufixo = arq.name[len(digest):] if arq.name.startswith(digest) else arq.suffix or '.bin'
                destino = novo / 'raw' / digest[:2] / (digest + sufixo)
                # Apenas a migracao local le caches antigos, e somente arquivos
                # imutaveis identificados pelo hash. O runtime jamais usa a origem.
                if arq.name.startswith(digest) and arq.is_file() and not arq.is_symlink():
                    h = hashlib.sha256()
                    with arq.open('rb') as entrada:
                        for bloco in iter(lambda: entrada.read(1024*1024), b''):
                            h.update(bloco)
                    if h.hexdigest() != digest:
                        raise RuntimeError('Hash do cache antigo diverge; arquivo nao copiado.')
                    destino.parent.mkdir(parents=True,exist_ok=True)
                    if not destino.exists():
                        shutil.copy2(arq,destino)
            conn.execute('UPDATE ARTEFATO_COLETA SET caminho_cache=? WHERE id=?', (str(destino), linha['id']))
            alterados += 1
        conn.commit()
    return alterados


def _remover_cron(texto, antigo):
    linhas = [l for l in texto.splitlines()
              if not auditoria.comando_coletor(l, antigo / 'radar-tick.sh') and not auditoria.comando_fila(l) and '# radar-raiz-web ' not in l]
    return '\n'.join(linhas) + ('\n' if linhas else '')


def _cron(texto, antigo, raiz, usuario):
    linhas = _remover_cron(texto, antigo).splitlines()
    # A identidade vem do dono do crontab; o aplicativo nao seleciona UID/GID.
    comando = ' '.join(shlex.quote(s) for s in (
        'env',
        '-u','RADAR_BRASIL_HOME','-u','RADAR_DATA_DIR','-u','RADAR_DB','-u','RADAR_WEB_ROOT','-u','RADAR_LOG_DIR',
        'RADAR_CONF='+str(raiz/'radar.conf'), sys.executable, str(raiz / 'api.pse')))
    linhas.extend('* * * * * ' + comando + ' cron ' + tarefa + ' # radar-raiz-web ' + tarefa for tarefa in ('tick', 'fila'))
    return '\n'.join(linhas) + '\n'


def _transferir_crons(backup, antigo, raiz, usuario):
    root = auditoria.ler_crontab()
    web = auditoria.ler_crontab(usuario)
    anteriores = {'root': root, usuario: web}
    for nome, conteudo in anteriores.items():
        (backup / ('crontab-' + nome + '-anterior.txt')).write_text(conteudo)
    esperado = _cron(web, antigo, raiz, usuario)
    try:
        _executar(['crontab', '-u', usuario, '-'], input=esperado)
        if auditoria.ler_crontab(usuario) != esperado:
            raise RuntimeError('Crontab do usuario web diverge do esperado')
        limpo = _remover_cron(root, antigo)
        _executar(['crontab', '-'], input=limpo)
        if auditoria.ler_crontab() != limpo:
            raise RuntimeError('Cron do Radar ainda permanece no root')
    except BaseException:
        for nome, conteudo in anteriores.items():
            _executar(['crontab', '-u', nome, '-'], input=conteudo)
        raise
    return anteriores


def _bloqueios_http(raiz, origem, prefixo):
    if not origem:
        raise RuntimeError('Configure web.origem para testar a protecao HTTP antes de migrar dados.')
    from .configuracao import _validar
    _validar({('web', 'origem'): origem, ('web', 'url'): prefixo})
    # Sondas reais: uma resposta 404 generica num arquivo ausente nao prova protecao.
    nome = '.sonda-' + uuid.uuid4().hex + '.txt'
    criados, pastas = [], []
    try:
        for pasta in PASTAS_PRIVADAS:
            diretorio = raiz / pasta
            if not diretorio.exists():
                diretorio.mkdir(parents=True)
                diretorio.chmod(0o755)
                pastas.append(diretorio)
            arquivo = diretorio / nome
            arquivo.write_text('sonda privada de instalacao')
            arquivo.chmod(0o644)
            criados.append(arquivo)
        aux = raiz / 'radar.conf.anterior'
        if not aux.exists():
            aux.write_text('sonda privada de instalacao')
            aux.chmod(0o644)
            criados.append(aux)
        temporario=raiz/('.radar-'+uuid.uuid4().hex)
        temporario.write_text('sonda privada de configuracao')
        temporario.chmod(0o644)
        criados.append(temporario)
        for rel in ['radar.conf', 'radar.conf.anterior', temporario.name, *(p + '/' + nome for p in PASTAS_PRIVADAS)]:
            url = origem.rstrip('/') + prefixo.rstrip('/') + '/' + urllib.parse.quote(rel)
            try:
                with urllib.request.urlopen(url, timeout=20) as resposta:
                    codigo = resposta.status
            except urllib.error.HTTPError as exc:
                codigo = exc.code
                exc.close()
            if codigo not in (403, 404):
                raise RuntimeError('Protecao HTTP reprovada (%s): %s' % (codigo, rel))
    finally:
        for arquivo in criados:
            arquivo.unlink(missing_ok=True)
        for pasta in reversed(pastas):
            if pasta.exists() and not any(pasta.iterdir()):
                pasta.rmdir()


def _arquivos(origem):
    for nome in CODIGO:
        yield nome, origem / nome
    for arquivo in (origem / 'web').iterdir():
        if arquivo.is_file() and arquivo.suffix in ESTATICOS:
            yield arquivo.name, arquivo
    yield 'api.pse', origem / 'deploy' / 'api.pse'
    for nome in ('README.md', 'LICENSE'):
        yield nome, origem / nome


def _conf_nova(texto, conta, origem_http, raiz, novo_dados, novo_banco, novos_logs, malha=False):
    alteracoes = {('instalacao','home'): str(raiz), ('web','raiz'): str(raiz),
                  ('dados','dir'): str(novo_dados), ('dados','banco'): novo_banco.name,
                  ('logs','dir'): novos_logs.relative_to(novo_dados).as_posix(),
                  ('api','token_arquivo'): 'api_token', ('assistente','chave_arquivo'): 'assistente_chave'}
    if malha:
        alteracoes['geografia','malha'] = 'geografia/malha.json'
    if caminhos.sync_clone():
        alteracoes['sincronizacao','clone'] = 'repo-dados'
    if origem_http and not caminhos.valor('web','origem')[0]:
        alteracoes['web','origem'] = origem_http
    texto = _editar(texto, auditoria.opcoes_faltantes(texto))
    return _editar(texto, alteracoes)


@operacao_local
def executar(args, observacoes):
    origem = Path(caminhos.ROOT).resolve()
    conf = args.conf.absolute()
    if not conf.is_file() or conf.is_symlink():
        raise RuntimeError('A primeira migracao exige o radar.conf regular existente; nao cria banco vazio.')
    if caminhos.problemas():
        raise RuntimeError('; '.join(caminhos.problemas()))
    raiz = Path(caminhos.web_raiz()).resolve()
    dados = Path(caminhos.data_dir()).resolve()
    banco = Path(caminhos.banco()).resolve()
    logs = Path(caminhos.log_dir()).resolve()
    home = Path(caminhos.home()).resolve()
    novo_conf = raiz / 'radar.conf'
    local = conf == novo_conf and home == raiz
    novo_dados = dados if local else raiz/'dados'
    novo_banco = novo_dados / banco.name
    novos_logs = logs if logs.is_relative_to(novo_dados) else novo_dados/'logs'
    if local and not (dados.is_relative_to(raiz/'dados') and banco.is_relative_to(raiz/'dados') and novos_logs.is_relative_to(novo_dados)):
        raise RuntimeError('No layout web, os dados devem ficar na pasta privada dados/; logs tambem ficam dentro de dados.dir.')
    conta = pwd.getpwnam(args.usuario_web)
    if not args.laboratorio and conta.pw_uid == 0:
        raise RuntimeError('O usuario da aplicacao deve ser sem privilegios, como www-data.')
    lab = args.laboratorio.resolve() if args.laboratorio else None
    if args.restaurar:
        raise RuntimeError('Backups do layout antigo nao podem substituir a raiz com dados. Use o relatorio da migracao para recuperacao.')
    if sys.version_info < (3,13) or not banco.is_file():
        raise RuntimeError('Necessario Python >= 3.13 e banco existente no radar.conf.')
    for destino in (raiz, dados, banco, logs, home, conf):
        if destino == Path('/') or (lab and not destino.is_relative_to(lab)):
            raise RuntimeError('Destino invalido ou fora do laboratorio: ' + str(destino))
    if raiz == origem or origem.is_relative_to(raiz) or raiz.is_relative_to(origem):
        raise RuntimeError('Execute com checkout separado do destino, como faz o instalador .sh.')
    if dados == raiz or logs == raiz or raiz.is_relative_to(dados):
        raise RuntimeError('Dados/logs de origem precisam estar em pastas separadas, sem conter a raiz do site.')
    if novo_conf.exists() and not novo_conf.is_symlink() and conf != novo_conf:
        raise RuntimeError('Ja existe radar.conf na raiz; selecione-o com --conf para evitar duas configuracoes.')
    if dados != novo_dados and novo_dados.exists() and any(novo_dados.iterdir()):
        raise RuntimeError('Dados nos dois destinos: recusa sobrescrever uma base existente.')
    for pasta in (dados, logs, *(raiz / p for p in PASTAS_PRIVADAS)):
        _sem_links(pasta)
    if banco.is_relative_to(raiz) and banco != novo_banco and not banco.is_relative_to(novo_dados):
        raise RuntimeError('Banco em local publico inesperado: ajuste dados.banco antes de migrar.')
    # Nenhum dado ou codigo e criado durante a simulacao/verificacao.
    versao = _executar(['git','-C',str(origem),'rev-parse','HEAD']).strip()
    plano = dict(sucesso=True, modo='verificacao' if args.verificar else 'simulacao',
                 layout='raiz_web', configuracao=str(novo_conf), raiz=str(raiz),
                 dados_origem=str(dados), banco_origem=str(banco), dados_destino=str(novo_dados),
                 logs_destino=str(novos_logs), usuario=conta.pw_name, versao_disponivel=versao,
                 observacoes=observacoes)
    if args.verificar:
        with _usar_conf(novo_conf):
            plano['checagens'] = _verificar(origem, raiz, novo_conf, conta, lab)
        plano['sucesso'] = all(c['estado']=='ok' for c in plano['checagens'])
    elif args.aplicar:
        if os.geteuid() != 0 and not lab:
            raise RuntimeError('A primeira etapa prepara nginx/cron/permissoes; execute este .sh como root, sem sudo.')
        if not lab:
            from .instalacao import _preparar_servicos
            _preparar_servicos(observacoes)
        plano = _aplicar(args, origem, conf, raiz, dados, banco, logs, home, conta, lab, versao, plano, observacoes, novo_dados, novo_banco, novos_logs)
    print(json.dumps(plano, ensure_ascii=False, indent=2))
    if args.relatorio:
        args.relatorio.parent.mkdir(parents=True, exist_ok=True)
        _json(args.relatorio, plano)
    return 0 if plano['sucesso'] else 1


def _verificar(origem, raiz, conf, conta, lab):
    checagens = []
    def checar(nome, acao):
        try:
            acao()
            checagens.append(dict(checagem=nome, estado='ok'))
        except Exception as exc:
            checagens.append(dict(checagem=nome, estado='erro', detalhe=str(exc)))
    def integridade():
        with closing(db.connect_readonly(caminhos.banco())) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Integridade/referencias reprovadas')
    def permissoes():
        for arq in (raiz/'api.pse', raiz/'radar.conf', Path(caminhos.data_dir()), Path(caminhos.log_dir()), *(raiz/n for n in CODIGO)):
            nome = str(arq.relative_to(raiz))
            if not arq.exists() or arq.is_symlink():
                raise RuntimeError('Ausente ou link inesperado: ' + nome)
            if arq.stat().st_uid != conta.pw_uid or not arq.stat().st_mode & 0o200:
                raise RuntimeError('Dono/permissao incorretos: ' + nome)
    def arquivos():
        esperado = _manifesto(origem)
        if esperado != json.loads((raiz/'arquivos-instalados.json').read_text()):
            raise RuntimeError('Manifesto diverge da revisao selecionada')
        for nome, digest in esperado.items():
            arq = raiz / nome
            if not arq.is_file() or hashlib.sha256(arq.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Fonte divergente: ' + nome)
    checar('banco.integridade', integridade)
    checar('arquivos', arquivos)
    checar('permissoes', permissoes)
    usuario = None if lab else conta.pw_name
    checar('api.prontidao', lambda: _cgi(raiz/'api.pse', conf, '/health/ready', usuario))
    checar('configuracao.gravacao', lambda: _comando(raiz, conf, conta, lab, 'configuracao','verificar-web'))
    if not lab:
        checar('nginx.privado', lambda: _bloqueios_http(raiz,caminhos.valor('web','origem')[0],caminhos.web_url()))
        checar('http.publico', lambda: auditoria.verificar_http(caminhos.valor('web','origem')[0], caminhos.web_url(), raiz/'gestao.html', configuracao_privada=True))
        def rotacao():
            arquivo = Path('/etc/logrotate.d/openclaw-radar')
            if arquivo.read_text() != auditoria.render_logrotate(origem,Path(caminhos.log_dir())):
                raise RuntimeError('Regra de rotacao divergente')
            resultado = auditoria.validar_logrotate(arquivo)
            if resultado['estado'] != 'ok':
                raise RuntimeError(str(resultado))
        checar('logrotate', rotacao)
    return checagens


def _comando(raiz, conf, conta, lab, *argumentos):
    from .instalacao import _ambiente
    cmd = [] if lab else ['runuser','-u',conta.pw_name,'--']
    return _executar(cmd+[sys.executable,str(raiz/'web/api.pse'),*argumentos], env=_ambiente(conf))


def _conteudo(nome, arq):
    conteudo = arq.read_bytes()
    if nome in ('api.pse', 'web/api.pse', 'deploy/api.pse'):
        conteudo = conteudo.replace(b'#!/usr/bin/env python3', ('#!'+sys.executable).encode(), 1)
    return conteudo


def _manifesto(origem):
    manifesto = {}
    for nome, arq in _arquivos(origem):
        if arq.is_dir():
            for f in arq.rglob('*'):
                if f.is_file() and '__pycache__' not in f.parts and f.suffix != '.pyc':
                    rel = nome + '/' + f.relative_to(arq).as_posix()
                    manifesto[rel] = hashlib.sha256(_conteudo(rel,f)).hexdigest()
        elif nome != 'projeto.json':
            manifesto[nome] = hashlib.sha256(_conteudo(nome,arq)).hexdigest()
    return manifesto


def _aplicar(args, origem, conf, raiz, dados, banco, logs, home, conta, lab, versao, plano, observacoes, novo_dados, novo_banco, novos_logs):
    from .protecao_configuracao import planejar
    agora = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    # Backups continuam privados; a origem e mantida, jamais apagada.
    backup = dados/'backups/raiz-web'/agora
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    indice = []
    def posse(fonte, destino):
        if os.geteuid() == 0:
            itens = [fonte, *fonte.rglob('*')] if fonte.is_dir() else [fonte]
            for f in itens:
                d = destino if f == fonte else destino / f.relative_to(fonte)
                st = f.lstat()
                os.chown(d, st.st_uid, st.st_gid, follow_symlinks=False)
    def guardar(alvo):
        if any(i['alvo']==str(alvo) for i in indice):
            return
        copia = backup/('item-%03d'%len(indice))
        tipo = 'link' if alvo.is_symlink() else 'dir' if alvo.is_dir() else 'file' if alvo.exists() else 'ausente'
        if tipo=='link':
            copia.write_text(os.readlink(alvo))
        elif tipo=='dir':
            shutil.copytree(alvo,copia,symlinks=True)
        elif tipo=='file':
            shutil.copy2(alvo,copia)
        if tipo in ('dir','file'):
            posse(alvo,copia)
        indice.append(dict(alvo=str(alvo),copia=str(copia),tipo=tipo))
        _json(backup/'restauracao.json',indice)
    def remover(alvo):
        if alvo.is_dir() and not alvo.is_symlink():
            shutil.rmtree(alvo)
        else:
            alvo.unlink(missing_ok=True)
    def restaurar():
        for item in reversed(indice):
            alvo,copia=Path(item['alvo']),Path(item['copia'])
            remover(alvo)
            if item['tipo']=='link':
                alvo.symlink_to(copia.read_text())
            elif item['tipo']=='dir':
                shutil.copytree(copia,alvo,symlinks=True)
            elif item['tipo']=='file':
                shutil.copy2(copia,alvo)
            if item['tipo'] in ('dir','file'):
                posse(copia,alvo)
    alterou_nginx=False
    cron_anterior=None
    transferidos=False
    copiou_logs=False
    publicado=False
    try:
        _diretorio(raiz, observacoes)
        origem_http=caminhos.valor('web','origem')[0] or args.origem_http or ''
        if not lab:
            for arquivo,anterior,novo in planejar(caminhos.web_url(),raiz,origem_http,raiz_local=True):
                if arquivo.read_text()!=anterior:
                    raise RuntimeError('Nginx alterado durante o planejamento')
                guardar(arquivo)
                arquivo.write_text(novo)
                alterou_nginx=True
            _executar(['nginx','-t'])
            _executar(['systemctl','reload','nginx'])
            _bloqueios_http(raiz,origem_http,caminhos.web_url())
        with ExitStack() as locks:
            trava=locks.enter_context(open(dados/'instalacao.lock','a'))
            fcntl.flock(trava,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for alvo in (raiz/'api.pse', home.parent/'radar-tick.sh', home.parent/'radar-api.pse'):
                # Compatibilidade antiga so e criada quando o codigo ainda esta fora do site.
                if alvo.parent==home.parent and home==raiz:
                    continue
                guardar(alvo)
                _diretorio(alvo.parent, observacoes)
                if alvo.name=='api.pse':
                    alvo.write_text('#!'+sys.executable+"\nprint('Status: 503 Service Unavailable\\r\\nRetry-After: 30\\r\\nContent-Type: text/plain\\r\\n\\r\\nAtualizacao em andamento.')\n")
                else:
                    alvo.write_text('#!/bin/sh\nexit 0\n')
                alvo.chmod(0o755)
            fila=dados/'fila-cadastros'
            fila.mkdir(exist_ok=True)
            for arq in (dados/'tick.lock',fila/'processador.lock',fila/'entrada.lock'):
                lock=locks.enter_context(open(arq,'a'))
                _esperar_coletor(lock)
            with closing(db.connect_readonly(banco)) as conn, closing(db.connect(backup/'radar.sqlite3')) as copia:
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
                    raise RuntimeError('Banco de origem com problemas de integridade')
                conn.backup(copia)
                copia.execute('PRAGMA journal_mode=DELETE')
            # Nunca substitui o diretorio raiz: banco, fila e segredos nao sao fontes.
            transferidos = dados != novo_dados
            _copiar_dados(dados,novo_dados,banco)
            if novo_banco!=banco:
                if novo_banco.exists():
                    raise RuntimeError('Banco destino existente: recusa sobrescrever')
                shutil.copy2(backup/'radar.sqlite3',novo_banco)
            if logs!=novos_logs:
                copiou_logs=True
                if logs.exists():
                    novos_logs.mkdir(parents=True,exist_ok=True)
                    for arquivo in logs.rglob('*'):
                        alvo = novos_logs / arquivo.relative_to(logs)
                        if arquivo.is_dir():
                            alvo.mkdir(parents=True,exist_ok=True)
                        else:
                            if alvo.exists():
                                alvo = alvo.with_name(alvo.name + '.anterior-' + agora)
                            shutil.copy2(arquivo,alvo)
                else:
                    (novos_logs).mkdir(exist_ok=True)
                    observacoes.append('Diretorio de logs ausente; criado com valor relativo logs.')
            segredos=novo_dados
            segredos.mkdir(parents=True,exist_ok=True)
            from .assistente_ia import arquivo_chave
            token_original, chave_original = Path(caminhos.token_arquivo()), arquivo_chave()
            secretos=((token_original,novo_dados/'api_token'), (chave_original,novo_dados/'assistente_chave'))
            for antigo,novo in secretos:
                if antigo.exists() and antigo.resolve()!=novo.resolve():
                    if novo.exists() and antigo.read_bytes()!=novo.read_bytes():
                        raise RuntimeError('Segredo divergente no destino: '+novo.name)
                    shutil.copy2(antigo,novo)
            malha=caminhos.caminho('geografia','malha')
            if malha and Path(malha).is_file():
                destino=novo_dados/'geografia/malha.json'
                destino.parent.mkdir(exist_ok=True)
                if Path(malha).resolve()!=destino:
                    shutil.copy2(malha,destino)
            clone = caminhos.sync_clone()
            if clone and Path(clone).is_dir() and Path(clone).resolve() != novo_dados/'repo-dados':
                if (novo_dados/'repo-dados').exists():
                    raise RuntimeError('Clone privado ja existe em outro destino; nenhuma versao sera sobrescrita.')
                shutil.copytree(clone, novo_dados/'repo-dados', symlinks=True)
                observacoes.append('Clone local preservado dentro de dados.dir; sincronizacao nao foi ativada.')
            for nome,arq in _arquivos(origem):
                if nome == 'api.pse':
                    continue  # CGI continua respondendo 503 ate terminar a preparacao.
                alvo=raiz/nome
                guardar(alvo)
                remover(alvo)
                if arq.is_dir():
                    shutil.copytree(arq,alvo,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                else:
                    alvo.write_bytes(_conteudo(nome,arq))
            for nome in ('web/api.pse','deploy/api.pse'):
                (raiz/nome).write_bytes(_conteudo(nome,origem/nome))
            for nome in ('VERSAO','arquivos-instalados.json', 'radar.conf', 'status-atualizacoes.json'):
                guardar(raiz/nome)
            observacoes.extend('Opcao ausente acrescentada com padrao: %s.%s = %s' % (*par, valor or '(vazio)')
                               for par, valor in sorted(auditoria.opcoes_faltantes(conf.read_text()).items()))
            texto=_conf_nova(conf.read_text(),conta,args.origem_http,raiz,novo_dados,novo_banco,novos_logs,bool(malha and Path(malha).is_file()))
            (raiz/'radar.conf').unlink(missing_ok=True) # remove o antigo link ao /etc
            (raiz/'radar.conf').write_text(texto)
            (raiz/'VERSAO').write_text(versao+'\n')
            _json(raiz/'arquivos-instalados.json',_manifesto(origem))
            referencias=_rebase_cache(novo_banco,dados,novo_dados)
            novo_conf=raiz/'radar.conf'
            with _usar_conf(novo_conf):
                projeto=raiz/'projeto.json'
                descritor=json.loads(projeto.read_text())
                descritor['url']=caminhos.web_url()
                _json(projeto,descritor)
                for pasta in (novo_dados,novos_logs,*(raiz/p for p in CODIGO)):
                    _permissoes(pasta,conta)
                for arq in raiz.iterdir():
                    if arq.is_file() and not arq.is_symlink():
                        _permissoes(arq,conta)
                if os.geteuid()==0:
                    os.chown(raiz,conta.pw_uid,conta.pw_gid)
                raiz.chmod(0o2770)
                (raiz/'api.pse').chmod(0o770)
                # Entradas copiadas para dentro de pastas privadas nao sao CGI publicas.
                _preparar_backups(novo_dados,conta)
                _comando(raiz,novo_conf,conta,lab,'ferramenta','inicializar_banco')
                _comando(raiz,novo_conf,conta,lab,'ferramenta','reconciliar_equipamentos','--aplicar')
                print('RADAR_CONF_DESTINO: '+str(novo_conf),flush=True)
                publicado=True
                (raiz/'api.pse').write_bytes(_conteudo('api.pse',origem/'deploy/api.pse'))
                _permissoes(raiz/'api.pse',conta)
                (raiz/'api.pse').chmod(0o770)
                link=raiz/'status-atualizacoes.json'
                link.unlink(missing_ok=True)
                link.symlink_to(os.path.relpath(caminhos.status_atualizacoes(),raiz))
                if home!=raiz:
                    for nome,tarefa in (('radar-tick.sh','cron tick'),('radar-api.pse','')):
                        alvo=home.parent/nome
                        comando=' '.join(shlex.quote(s) for s in (shutil.which('runuser') or 'runuser','-u',conta.pw_name,'--',sys.executable,str(raiz/'api.pse')))
                        alvo.write_text('#!/bin/sh\nunset RADAR_BRASIL_HOME RADAR_DB RADAR_DATA_DIR RADAR_WEB_ROOT RADAR_LOG_DIR\nexport RADAR_CONF='+shlex.quote(str(novo_conf))+'\nexec '+comando+(' '+tarefa if tarefa else ' "$@"')+'\n')
                        alvo.chmod(0o755)
                etc=lab/'etc' if lab else Path('/etc')
                rotacao=etc/'logrotate.d/openclaw-radar'
                rotacao.parent.mkdir(parents=True,exist_ok=True)
                guardar(rotacao)
                rotacao.write_text(auditoria.render_logrotate(origem,novos_logs))
                rotacao.chmod(0o644)
                if not lab and not args.sem_cron:
                    cron_anterior=_transferir_crons(backup, home.parent, raiz, conta.pw_name)
                    observacoes.append('Agendamentos do Radar transferidos do root para '+conta.pw_name+'.')
                plano.update(modo='aplicacao',backup=str(backup),referencias_cache_atualizadas=referencias,
                             checagens=_verificar(origem,raiz,novo_conf,conta,lab))
                plano['sucesso']=all(c['estado']=='ok' for c in plano['checagens'])
                if not plano['sucesso']:
                    raise RuntimeError('Checagem final reprovada: '+json.dumps(plano['checagens'],ensure_ascii=False))
                with atualizacoes.acompanhar('instalacao',layout='raiz_web',backup=str(backup)) as registro:
                    registro.terminar(0,relatorio=plano)
                # Subprocessos podem criar arquivos; garante a posse ao CGI ao terminar.
                _permissoes(novo_dados,conta)
                _permissoes(novos_logs,conta)
            observacoes.append('Codigo, banco, fila, cache e segredos preparados para '+conta.pw_name+'.')
            observacoes.append('Origens antigas preservadas; novos caminhos relativos ao radar.conf da raiz.')
            observacoes.append('Backups anteriores permanecem em '+str(dados/'backups')+'.')
            _json(backup/'checagem-final.json',plano)
            (backup/'CONCLUIDO').write_text(agora+'\n')
            return plano
    except BaseException as exc:
        plano.update(sucesso=False,erro=str(exc),backup=str(backup),recuperacao_automatica=False)
        # Para migracao entre bancos, o original nunca foi alterado: pode recuperar
        # arquivos e descartar somente a copia nova. No layout existente preserva
        # o codigo novo se houve migracao do esquema, como o instalador legado.
        from .instalacao import _esquema_compativel_com_backup
        if not publicado and (not (backup/'radar.sqlite3').exists() or transferidos or _esquema_compativel_com_backup(backup,banco)):
            # Remove copias privadas ANTES de desfazer as protecoes do nginx.
            if transferidos and (novo_dados).exists():
                shutil.rmtree(novo_dados)
            restaurar()
            if cron_anterior is not None:
                for usuario, conteudo in cron_anterior.items():
                    _executar(['crontab','-u',usuario,'-'],input=conteudo)
            if alterou_nginx:
                _executar(['nginx','-t'])
                _executar(['systemctl','reload','nginx'])
            plano['recuperacao_automatica']=True
        if publicado:
            plano['observacao']='Instalacao nova preservada para nao perder gravacoes recebidas. Reaplique o script com --conf apontando ao radar.conf da raiz.'
        _json(backup/'checagem-final.json',plano)
        raise
