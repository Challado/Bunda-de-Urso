"""Recebimento duravel em JSON e processamento local pela entrada api.pse."""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import sys
import time
import uuid

from . import caminhos, config, db, governanca
from .contexto_api import operacao_local

ESTADOS = ('pendentes', 'processando', 'concluidos', 'rejeitados')
PASTAS = ESTADOS + ('indices', 'limites', 'quarentena')
TERMINAIS = ('processado', 'rejeitado', 'falhou')


def pasta():
    return Path(caminhos.fila_cadastros(config.DATA_DIR))


def _erro(status, codigo, mensagem):
    raise governanca.GovernancaError(status, codigo, mensagem)


def _fsync_dir(diretorio):
    fd = os.open(diretorio, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _preparar():
    raiz = pasta()
    if raiz.resolve().is_relative_to(Path(caminhos.web_raiz()).resolve()):
        _erro(503, 'fila_insegura', 'A fila deve ficar fora da pasta web.')
    for d in (raiz, *(raiz / nome for nome in PASTAS)):
        if d.is_symlink():
            _erro(503, 'fila_insegura', 'A fila exige diretorios regulares.')
        novo = not d.exists()
        d.mkdir(parents=True, exist_ok=True)
        if d.stat().st_mode & 0o7777 != 0o2770:
            d.chmod(0o2770)
        if novo:
            _fsync_dir(d.parent)


def _gravar(arquivo, dados):
    texto = json.dumps(dados, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    fd, tmp = tempfile.mkstemp(prefix='.gravando-', dir=arquivo.parent)
    try:
        with os.fdopen(fd, 'wb') as saida:
            os.fchmod(saida.fileno(), 0o660)
            saida.write(texto)
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(tmp, arquivo)
        _fsync_dir(arquivo.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _ler(arquivo):
    if arquivo.is_symlink() or arquivo.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('arquivo de fila invalido')
    return json.loads(arquivo.read_text())


def _mover(origem, destino):
    os.replace(origem, destino)
    _fsync_dir(destino.parent)
    if origem.parent != destino.parent:
        _fsync_dir(origem.parent)


@contextmanager
def _trava(nome):
    fd = os.open(pasta() / nome, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    try:
        if os.fstat(fd).st_mode & 0o777 != 0o660:
            os.fchmod(fd, 0o660)
        prazo = time.monotonic() + (0.15 if nome == 'entrada.lock' else 0)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= prazo:
                    _erro(503, 'fila_ocupada', 'Fila ocupada por outra operacao; tente novamente em instantes.')
                time.sleep(0.002)
        yield
    finally:
        os.close(fd)


def _localizar(protocolo):
    if not isinstance(protocolo, str) or not re.fullmatch(r'[a-f0-9]{32}', protocolo):
        _erro(404, 'envio_nao_encontrado', 'Protocolo de envio nao encontrado.')
    # Uma segunda passagem cobre a recuperacao processando -> pendente.
    for _ in range(2):
        for estado in ESTADOS:
            arquivo = pasta() / estado / (protocolo + '.json')
            try:
                doc = _ler(arquivo)
            except FileNotFoundError:
                continue
            if not isinstance(doc, dict) or doc.get('protocolo') != protocolo:
                raise ValueError('protocolo divergente')
            return arquivo, doc
    _erro(404, 'envio_nao_encontrado', 'Protocolo de envio nao encontrado.')


def _publico(doc):
    out = {k: doc[k] for k in ('protocolo', 'estado', 'recebido_em', 'tentativas')}
    out['consulta_url'] = '?rota=/api/v1/radares/envios/' + doc['protocolo']
    for k in ('resultado', 'erro', 'finalizado_em'):
        if k in doc:
            out[k] = doc[k]
    return out


def consultar(protocolo):
    try:
        return _publico(_localizar(protocolo)[1])
    except (OSError, ValueError, KeyError, TypeError):
        _erro(503, 'fila_indisponivel', 'Nao foi possivel consultar este envio; tente novamente.')


def _limite_ip(ip):
    if not ip or config.SUBMISSAO_LIMITE <= 0:
        return
    arquivo = pasta() / 'limites' / (hashlib.sha256(ip.encode()).hexdigest() + '.json')
    agora = time.time()
    try:
        anteriores = _ler(arquivo)
    except FileNotFoundError:
        anteriores = []
    if not isinstance(anteriores, list):
        raise ValueError('contador invalido')
    tempos = [t for t in anteriores if isinstance(t, (int, float)) and agora - t < config.SUBMISSAO_JANELA_SEGUNDOS]
    if len(tempos) >= config.SUBMISSAO_LIMITE:
        _erro(429, 'limite_submissao', 'Limite de envios atingido; tente mais tarde.')
    _gravar(arquivo, tempos + [agora])


def receber(dados, procedencia=None):
    """ACK somente apos fsync do JSON e seu indice. Nao abre SQLite."""
    procedencia = dict(procedencia or {})
    if isinstance(dados, dict):
        procedencia['contato'] = dados.get('contato')
    elif isinstance(dados, list) and dados and isinstance(dados[0], dict):
        procedencia['contato'] = dados[0].get('contato')
    itens = [dados] if isinstance(dados, dict) else dados
    if not isinstance(itens, list) or not itens or len(itens) > caminhos.inteiro('cadastro', 'max_itens'):
        _erro(422, 'payload_invalido', 'Envie um radar ou um lote dentro do limite configurado.')
    erros = [dict(indice=i, campo=e[0], mensagem=e[1]) for i, item in enumerate(itens)
             if (e := governanca.validar_minimo(item)) is not None]
    if len(erros) == len(itens):
        raise governanca.GovernancaError(422, 'payload_invalido', 'Nenhum radar valido no envio.', detalhes=erros)
    try:
        bruto = json.dumps(dados, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError):
        _erro(422, 'payload_invalido', 'Envie dados JSON validos.')
    if len(bruto) > caminhos.inteiro('cadastro', 'max_bytes'):
        _erro(413, 'envio_grande', 'Envio excede o tamanho configurado para a fila.')
    digest = hashlib.sha256(bruto).hexdigest()
    try:
        _preparar()
        with _trava('entrada.lock'):
            indice = pasta() / 'indices' / (digest + '.json')
            if indice.is_file():
                try:
                    anterior, registro = _localizar(_ler(indice)['protocolo'])
                    expirado = (registro['estado'] in ('processado','rejeitado') and
                                anterior.stat().st_mtime < time.time()-caminhos.inteiro('cadastro','retencao_dias')*86400)
                    if not expirado:
                        repetido = _publico(registro)
                        repetido['reenvio'] = True
                        return repetido
                except governanca.GovernancaError as exc:
                    if exc.status != 404:
                        raise
            quantidade = sum(1 for nome in ('pendentes', 'processando') for _ in (pasta() / nome).glob('*.json'))
            if quantidade >= caminhos.inteiro('cadastro', 'max_pendentes'):
                _erro(503, 'fila_cheia', 'Fila temporariamente cheia; envio nao confirmado. Tente mais tarde.')
            _limite_ip(procedencia.get('ip'))
            protocolo = uuid.uuid4().hex
            doc = {'versao': 1, 'protocolo': protocolo, 'digest': digest, 'estado': 'recebido',
                   'recebido_em': governanca._agora(), 'tentativas': 0, 'proxima_tentativa': 0,
                   'dados': dados, 'procedencia': procedencia}
            _gravar(pasta() / 'pendentes' / (protocolo + '.json'), doc)
            _gravar(indice, {'protocolo': protocolo})
            return _publico(doc)
    except (OSError, ValueError, KeyError, TypeError):
        _erro(503, 'fila_indisponivel', 'Nao foi possivel confirmar a gravacao do envio; tente novamente.')


def _finalizar(arquivo, doc, estado):
    doc['estado'] = estado
    doc['finalizado_em'] = governanca._agora()
    destino = pasta() / ('concluidos' if estado == 'processado' else 'rejeitados') / arquivo.name
    _gravar(arquivo, doc)
    _mover(arquivo, destino)


def _recuperar():
    # O lock exclusivo garante que nenhum processo vivo esta usando esses itens.
    for arquivo in (pasta() / 'processando').glob('*.json'):
        _mover(arquivo, pasta() / 'pendentes' / arquivo.name)


def _limpar():
    antes = time.time() - caminhos.inteiro('cadastro', 'retencao_dias') * 86400
    for nome in ('concluidos', 'rejeitados'):
        for arquivo in (pasta() / nome).glob('*.json'):
            if arquivo.stat().st_mtime >= antes:
                continue
            doc = _ler(arquivo)
            if doc.get('estado') == 'falhou':
                continue  # falha ainda nao resolvida fica para revisao
            indice = pasta() / 'indices' / (str(doc.get('digest')) + '.json')
            if doc.get('digest') and indice.is_file() and _ler(indice).get('protocolo') == doc['protocolo']:
                indice.unlink()
            arquivo.unlink()
    for arquivo in (pasta() / 'limites').glob('*.json'):
        if arquivo.stat().st_mtime < antes:
            arquivo.unlink()


def processar(limite=None, db_path=None):
    _preparar()
    limite = limite if limite is not None else caminhos.inteiro('cadastro', 'lote')
    if not isinstance(limite, int) or not 1 <= limite <= 1000:
        _erro(422, 'limite_invalido', 'Use um lote de 1..1000 envios.')
    resumo = {'processados': 0, 'rejeitados': 0, 'adiados': 0, 'falharam': 0, 'recuperados': 0}
    try:
        with _trava('processador.lock'):
            with _trava("entrada.lock"):
                _recuperar()
            arquivos = sorted((pasta() / 'pendentes').glob('*.json'), key=lambda p:p.stat().st_mtime)
            atendidos = 0
            for origem in arquivos:
                if atendidos >= limite:
                    break
                try:
                    doc = _ler(origem)
                    if (not isinstance(doc, dict) or doc.get('versao') != 1 or doc.get('protocolo') != origem.stem or
                            not isinstance(doc.get('tentativas'), int) or doc['tentativas'] < 0 or
                            ('dados' not in doc and doc.get('estado') not in TERMINAIS)):
                        raise ValueError('origem incompleta')
                    if doc.get('estado') not in TERMINAIS and hashlib.sha256(json.dumps(doc['dados'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest() != doc.get('digest'):
                        raise ValueError('conteudo divergente')
                except (ValueError, KeyError, TypeError):
                    _mover(origem, pasta() / 'quarentena' / origem.name)
                    doc = {'versao':1, 'protocolo':origem.stem, 'digest':None,
                           'recebido_em':governanca._agora(), 'tentativas':0,
                           'erro':{'codigo':'origem_invalida', 'mensagem':'Origem preservada para revisao administrativa.'}}
                    _gravar(origem, doc)
                    _finalizar(origem, doc, 'falhou')
                    resumo['falharam'] += 1
                    atendidos += 1
                    continue
                if doc.get('estado') in TERMINAIS:
                    _finalizar(origem, doc, doc['estado'])
                    resumo['recuperados'] += 1
                    atendidos += 1
                    continue
                if doc['tentativas'] >= caminhos.inteiro('cadastro', 'tentativas'):
                    doc['erro'] = {'codigo':'tentativas_esgotadas', 'mensagem':'Nao foi possivel confirmar o processamento; origem preservada para revisao.'}
                    _finalizar(origem, doc, 'falhou')
                    resumo['falharam'] += 1
                    atendidos += 1
                    continue
                if doc.get('proxima_tentativa', 0) > time.time():
                    continue
                atendidos += 1
                arquivo = pasta() / 'processando' / origem.name
                with _trava('entrada.lock'):
                    _mover(origem, arquivo)
                doc['estado'] = 'processando'
                doc['tentativas'] += 1
                _gravar(arquivo, doc)
                try:
                    with closing(db.connect_existing(db_path or config.DB_PATH)) as conn:
                        if not db.esquema_carregado(conn):
                            raise OSError('banco nao inicializado')
                        resultado = governanca.submeter(conn, doc['dados'], doc['procedencia'], checar_limite=False)
                    doc['resultado'] = resultado
                    doc.pop('erro', None)
                    _finalizar(arquivo, doc, 'processado')
                    resumo['processados'] += 1
                except Exception as exc:
                    if isinstance(exc, governanca.GovernancaError) and exc.status < 500:
                        doc['erro'] = {'codigo': exc.codigo, 'mensagem': exc.mensagem, 'detalhes': exc.detalhes}
                        _finalizar(arquivo, doc, 'rejeitado')
                        resumo['rejeitados'] += 1
                        continue
                    # A origem fica preservada; nao publica excecoes/credenciais.
                    doc['erro'] = {'codigo': 'processamento_temporario', 'mensagem': 'Falha no processamento; a origem foi preservada.'}
                    if doc['tentativas'] >= caminhos.inteiro('cadastro', 'tentativas'):
                        _finalizar(arquivo, doc, 'falhou')
                        resumo['falharam'] += 1
                    else:
                        doc['estado'] = 'aguardando_nova_tentativa'
                        doc['proxima_tentativa'] = time.time() + min(3600, 60 * 2 ** (doc['tentativas'] - 1))
                        _gravar(arquivo, doc)
                        _mover(arquivo, pasta() / 'pendentes' / arquivo.name)
                        resumo['adiados'] += 1
            with _trava("entrada.lock"):
                _limpar()
    except governanca.GovernancaError as exc:
        if exc.codigo != 'fila_ocupada':
            raise
        resumo['ocupado'] = True
    return resumo


def reprocessar(protocolo):
    _preparar()
    with _trava('processador.lock'):
        arquivo, doc = _localizar(protocolo)
        if 'dados' not in doc:
            _erro(422, 'origem_invalida', 'Confira a origem preservada antes de reprocessar.')
        if doc['estado'] == 'processado':
            _erro(409, 'envio_concluido', 'Envio ja processado; consulte o radar informado no protocolo.')
        doc.update(estado='recebido', tentativas=0, proxima_tentativa=0)
        doc.pop('erro', None)
        doc.pop('finalizado_em', None)
        _gravar(arquivo, doc)
        if arquivo.parent.name != 'pendentes':
            _mover(arquivo, pasta() / 'pendentes' / arquivo.name)
        return _publico(doc)


def verificar():
    """Prova gravacao com o usuario real, sem criar pedido nem reparar diretorios."""
    for nome in PASTAS:
        d = pasta() / nome
        if not d.is_dir() or d.is_symlink():
            _erro(503, 'fila_indisponivel', 'Execute o instalador para preparar a fila.')
    fd, tmp = tempfile.mkstemp(prefix='.verificacao-', dir=pasta() / 'pendentes')
    try:
        os.write(fd, b'verificacao de gravacao')
        os.fsync(fd)
    finally:
        os.close(fd)
        Path(tmp).unlink(missing_ok=True)
    _fsync_dir(pasta() / 'pendentes')
    lock = pasta() / 'entrada.lock'
    if lock.exists():
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        os.close(fd)
    return {'sucesso': True, 'gravacao_duravel': True}


@operacao_local
def main(argv=None):
    p = argparse.ArgumentParser(description='Fila duravel de cadastros; recebimento sem SQLite.')
    p.add_argument('acao', choices=('processar', 'consultar', 'reprocessar', 'verificar'))
    p.add_argument('--protocolo')
    p.add_argument('--limite', type=int)
    p.add_argument('--db')
    args = p.parse_args(argv)
    try:
        resultado = (verificar() if args.acao == 'verificar' else
                     processar(args.limite, args.db) if args.acao == 'processar' else
                     reprocessar(args.protocolo) if args.acao == 'reprocessar' else consultar(args.protocolo))
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0 if not resultado.get('falharam') else 1
    except (OSError, ValueError, KeyError, governanca.GovernancaError):
        print('Nao foi possivel concluir a operacao da fila; os envios permanecem preservados.', file=sys.stderr)
        return 1
