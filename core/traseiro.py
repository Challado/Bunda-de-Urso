"""TRASEIRO DE URSO: diario imutavel, cadastro mesh e decisoes locais.

Somente a entrada API chama esta camada. Nenhuma requisicao HTTP recebida
inicia downloads. Documentos de rede sao evidencias; entidades e vinculos
vivem em tabelas normalizadas com chaves e restricoes.
"""
import datetime
import fcntl
from functools import wraps
import hashlib
import hmac
import json
import math
from pathlib import Path
import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl
from . import caminhos, governanca as gov, db as dbmod, intercambio

PROTOCOLO = intercambio.PROTOCOLO
TIPO_RADAR='radar.v1'
TIPO_FONTE='fonte-coleta.v1'
TIPOS=(TIPO_RADAR,TIPO_FONTE)
CAMPOS = frozenset(('latitude','longitude','uf','municipio','municipio_ibge','via','km',
 'tipo_pista','tipo_radar','sentido','velocidade_geral','velocidade_leves','velocidade_pesados',
 'numero_serie','fabricante','modelo','situacao','precisao_metros','observacoes'))

def gravacao(funcao):
    @wraps(funcao)
    def chamar(*args,**kwargs):
        pasta=Path(caminhos.dentro_dados('traseiro','traseiro')); pasta.mkdir(parents=True,exist_ok=True)
        with (pasta/'gravacao.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            return funcao(*args,**kwargs)
    return chamar

def erro(status, codigo, mensagem):
    raise gov.GovernancaError(status, 'traseiro_'+codigo, mensagem)

def agora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

def numero(chave):
    return caminhos.inteiro('traseiro', chave)

def habilitado():
    return numero('habilitado') == 1

def json_doc(doc):
    return json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def id_uuid(texto):
    try:
        return str(uuid.UUID(str(texto)))
    except (ValueError,TypeError,AttributeError):
        erro(422,'uuid_invalido','Identidade de instancia/evento deve ser UUID.')

def url_publica(texto, *, api=False):
    from coletor.http import url_checada, ErroFonte
    if not isinstance(texto,str) or len(texto)>2048 or any(ord(c)<=32 for c in texto):
        erro(422,'url_invalida','Informe URL HTTPS publica.')
    try:
        url_checada(texto)
        p=urlsplit(texto)
        if p.fragment:
            raise ValueError()
        if any(any(palavra in k.lower() for palavra in ('token','secret','password','senha','signature','api_key')) for k,v in parse_qsl(p.query)):
            raise ValueError()
        return urlunsplit(('https',p.netloc.lower(),p.path or '/',p.query,''))
    except (ErroFonte,ValueError):
        erro(422,'url_invalida','Use URL HTTPS publica sem credenciais ou parametros secretos.')

def api_local():
    explicita=caminhos.valor('traseiro','api_url')[0]
    if explicita:
        return url_publica(explicita,api=True)
    return url_publica(caminhos.valor('web','origem')[0].rstrip('/')+'/'+caminhos.web_url().strip('/')+'/api.pse?rota=%2Fapi%2Fv1%2Fintercambio%2Ftrocar',api=True)

def identidade(conn):
    gov.garantir_esquema(conn)
    row=conn.execute('SELECT uuid FROM TRASEIRO_LOCAL WHERE singleton=1').fetchone()
    if row is None:
        conn.execute('INSERT OR IGNORE INTO TRASEIRO_LOCAL(singleton,uuid,criado_em) VALUES(1,?,?)',(str(uuid.uuid4()),agora()))
        conn.execute('INSERT OR IGNORE INTO TRASEIRO_PONTO_PENDENTE(ponto_id) SELECT id FROM PONTO_FISCALIZACAO')
        conn.commit()
        row=conn.execute('SELECT uuid FROM TRASEIRO_LOCAL WHERE singleton=1').fetchone()
    return {'uuid':row['uuid'],'nome':caminhos.valor('traseiro','nome')[0],'api_url':api_local(),'protocolo':dict(PROTOCOLO),'aplicacao':'Radar Brasil / TRASEIRO DE URSO',
            'capacidades':{'tipos_evento':list(TIPOS)},'configuracao':informacoes(conn)}

def validar_informacoes(doc):
    try:
        return intercambio.validar_configuracao(doc)
    except intercambio.ErroIntercambio as exc:
        erro(422,'informacoes_invalidas',str(exc))

def informacoes(conn):
    cfg={k:numero(k) for k in ('intervalo_segundos','lote','max_bytes')}
    cfg['max_bytes']=min(cfg['max_bytes'],caminhos.inteiro('api','max_body'))
    parada={k:numero(k) for k in ('parada_programada','parar_em_segundos','retornar_em_segundos')}
    if parada['parada_programada'] not in (0,1) or min(parada['parar_em_segundos'],parada['retornar_em_segundos'])<0 or (not parada['parada_programada'] and (parada['parar_em_segundos'] or parada['retornar_em_segundos'])) or (parada['parada_programada'] and parada['retornar_em_segundos'] and parada['retornar_em_segundos']<=parada['parar_em_segundos']):
        erro(503,'configuracao_invalida','Programacao de parada invalida no radar.conf; ao cancelar, zere os prazos.')
    assinatura=hashlib.sha256(json_doc(parada).encode()).hexdigest()
    row=conn.execute('SELECT aviso_hash,aviso_em FROM TRASEIRO_LOCAL WHERE singleton=1').fetchone()
    if row['aviso_hash']!=assinatura:
        instante=datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute('UPDATE TRASEIRO_LOCAL SET aviso_hash=?,aviso_em=? WHERE singleton=1',(assinatura,instante)); conn.commit()
    else:
        instante=row['aviso_em']
    decorrido=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(instante)).total_seconds()
    ativa=parada['parada_programada']==1 and (not parada['retornar_em_segundos'] or decorrido<parada['retornar_em_segundos'])
    cfg.update(parada_programada=ativa,
        parar_em_segundos=max(0,math.ceil(parada['parar_em_segundos']-decorrido)) if ativa else 0,
        retornar_em_segundos=max(0,math.ceil(parada['retornar_em_segundos']-decorrido)) if ativa and parada['retornar_em_segundos'] else 0,
        anuncio_id=hashlib.sha256((assinatura+instante).encode()).hexdigest() if ativa else None)
    return validar_informacoes(cfg)

def pausada(info,instante=None):
    if 'parada_programada' in info:
        return bool(info['parada_programada'] and info['parar_em_segundos']==0)
    instante=instante or agora()
    return bool(info.get('pausa_inicio') and info['pausa_inicio']<=instante and (not info.get('pausa_fim') or instante<info['pausa_fim']))

def cabecalho(local):
    return intercambio.codificar_info(local)

def ler_cabecalho(environ):
    try:
        return intercambio.decodificar_info(environ.get('HTTP_X_INTERCHANGE_INFO',''))
    except intercambio.ErroIntercambio as exc:
        erro(422,'informacoes_invalidas',str(exc))

def arquivo_tokens():
    return Path(caminhos.caminho('traseiro','tokens_arquivo'))

def tokens():
    try:
        arq=arquivo_tokens()
        if arq.stat().st_size>65536:
            raise ValueError()
        doc=json.loads(arq.read_text(encoding='utf-8'))
        if not isinstance(doc,dict) or not isinstance(doc.get('entrada',[]),list) or not isinstance(doc.get('saida',{}),dict):
            raise ValueError()
        if any(not isinstance(v,str) or len(v)<24 for v in doc.get('entrada',[])):
            raise ValueError()
        if any(not isinstance(v,str) or len(v)<24 for v in doc.get('saida',{}).values()):
            raise ValueError()
        if doc.get('token_rede') is not None and (not isinstance(doc['token_rede'],str) or len(doc['token_rede'])<24):
            raise ValueError()
        return doc
    except (OSError,ValueError,TypeError):
        erro(503,'tokens_indisponiveis','Prepare o arquivo JSON de tokens da rede dentro de dados.dir.')

def autenticar(environ):
    if not habilitado():
        erro(503,'desativado','TRASEIRO DE URSO desativado nesta instancia.')
    modo=caminhos.valor('traseiro','acesso')[0]
    if modo=='livre':
        return
    if modo!='tokens':
        erro(503,'configuracao_invalida','traseiro.acesso deve ser livre ou tokens.')
    valor=''
    auth=environ.get('HTTP_AUTHORIZATION','')
    valor=valor or (auth[7:] if auth.startswith('Bearer ') else '')
    arquivo=tokens()
    aceitos=arquivo.get('entrada',[])+([arquivo['token_rede']] if arquivo.get('token_rede') else [])
    if not valor or not any(hmac.compare_digest(valor.encode(),t.encode()) for t in aceitos):
        erro(401,'token_invalido','Token da rede ausente ou invalido.')

def _capacidades(conn,ident,doc):
    novos=set(doc['capacidades']['tipos_evento'])
    antigos={r[0] for r in conn.execute('SELECT tipo FROM INTERCAMBIO_TIPO_INSTANCIA WHERE instancia_uuid=?',(ident,))}
    if novos!=antigos:
        conn.execute('DELETE FROM INTERCAMBIO_TIPO_INSTANCIA WHERE instancia_uuid=?',(ident,))
        conn.executemany('INSERT INTO INTERCAMBIO_TIPO_INSTANCIA(instancia_uuid,tipo) VALUES(?,?)',[(ident,t) for t in sorted(novos)])
        if novos-antigos:
            conn.execute('UPDATE TRASEIRO_INSTANCIA SET cursor_saida=0 WHERE uuid=?',(ident,))
    conn.execute('UPDATE TRASEIRO_INSTANCIA SET aplicacao=? WHERE uuid=?',(doc['aplicacao'],ident))

def tipos_par(conn,ident):
    return {r[0] for r in conn.execute('SELECT tipo FROM INTERCAMBIO_TIPO_INSTANCIA WHERE instancia_uuid=?',(ident,))}

def registrar_instancia(conn,doc):
    try:
        intercambio.validar_identidade(doc)
    except intercambio.ErroIntercambio as exc:
        erro(422,'protocolo_invalido',str(exc))
    info=validar_informacoes(doc.get('configuracao'))
    instante=datetime.datetime.now(datetime.timezone.utc)
    inicio=(instante+datetime.timedelta(seconds=info['parar_em_segundos'])).isoformat(timespec='seconds') if info['parada_programada'] else None
    fim=(instante+datetime.timedelta(seconds=info['retornar_em_segundos'])).isoformat(timespec='seconds') if info['parada_programada'] and info['retornar_em_segundos'] else None
    ident=id_uuid(doc.get('uuid')); local=identidade(conn)
    endereco=url_publica(doc.get('api_url'),api=True); nome=doc.get('nome')
    if not isinstance(nome,str) or not 1<=len(nome.strip())<=120:
        erro(422,'nome_invalido','Nome da instancia deve ter 1 a 120 caracteres.')
    if ident==local['uuid'] or endereco==local['api_url']:
        erro(409,'instancia_local','Nao cadastre a propria instancia como par.')
    row=conn.execute('SELECT * FROM TRASEIRO_INSTANCIA WHERE uuid=? OR api_url=?',(ident,endereco)).fetchone()
    if row is not None:
        if row['uuid']!=ident or row['api_url']!=endereco:
            erro(409,'identidade_conflitante','URL e UUID pertencem a outra identidade; revise o cadastro local.')
        if row['estado']=='bloqueado':
            erro(403,'instancia_bloqueada','Instancia bloqueada pelo administrador local.')
        conn.execute("UPDATE TRASEIRO_INSTANCIA SET nome=?,intervalo_segundos=?,lote=?,max_bytes=?,parada_anunciada=?,anuncio_id=?,pausa_inicio=?,pausa_fim=?,estado=CASE WHEN estado='pausado' AND ?=0 THEN 'ativo' ELSE estado END WHERE uuid=?",
            (nome.strip(),info['intervalo_segundos'],info['lote'],info['max_bytes'],int(info['parada_programada']),info['anuncio_id'],inicio,fim,int(info['parada_programada']),ident))
        _capacidades(conn,ident,doc)
        conn.commit()
        return dict(conn.execute('SELECT * FROM TRASEIRO_INSTANCIA WHERE uuid=?',(ident,)).fetchone())
    if dbmod.scalar(conn,'SELECT COUNT(*) FROM TRASEIRO_INSTANCIA')>=numero('max_instancias'):
        erro(429,'limite_instancias','Limite de instancias da rede atingido.')
    conn.execute('INSERT INTO TRASEIRO_INSTANCIA(uuid,api_url,nome,criado_em) VALUES(?,?,?,?)',(ident,endereco,nome.strip(),agora()))
    conn.execute('UPDATE TRASEIRO_INSTANCIA SET intervalo_segundos=?,lote=?,max_bytes=?,parada_anunciada=?,anuncio_id=?,pausa_inicio=?,pausa_fim=? WHERE uuid=?',
        (info['intervalo_segundos'],info['lote'],info['max_bytes'],int(info['parada_programada']),info['anuncio_id'],inicio,fim,ident))
    _capacidades(conn,ident,doc)
    conn.commit()
    return dict(conn.execute('SELECT * FROM TRASEIRO_INSTANCIA WHERE uuid=?',(ident,)).fetchone())

def instancias_publicas(conn,max_bytes=None):
    saida=[]; tamanho=0
    rows=conn.execute("SELECT * FROM TRASEIRO_INSTANCIA WHERE estado IN ('ativo','pausado') ORDER BY uuid LIMIT ?",(numero('max_instancias'),)).fetchall()
    if rows:
        offset=int(datetime.datetime.now(datetime.timezone.utc).timestamp())//max(1,numero('intervalo_segundos'))%len(rows)
        rows=rows[offset:]+rows[:offset]
    for row in rows:
        saida.append({k:row[k] for k in ('uuid','nome','api_url','aplicacao')})
        agora_=datetime.datetime.now(datetime.timezone.utc)
        segundos=lambda t:max(0,math.ceil((datetime.datetime.fromisoformat(t)-agora_).total_seconds())) if t else 0
        fim=segundos(row['pausa_fim'])
        ativa=bool(row['parada_anunciada'] and (not row['pausa_fim'] or fim>0))
        saida[-1].update(protocolo=PROTOCOLO,capacidades={'tipos_evento':sorted(tipos_par(conn,row['uuid']))},configuracao={
            **{k:row[k] for k in ('intervalo_segundos','lote','max_bytes')},
            'parada_programada':ativa,'parar_em_segundos':segundos(row['pausa_inicio']) if ativa else 0,
            'retornar_em_segundos':fim if ativa else 0,'anuncio_id':row['anuncio_id'] if ativa else None})
        n=len(json_doc(saida[-1]).encode())+1
        if max_bytes and tamanho+n>max_bytes:
            saida.pop();break
        tamanho+=n
    return saida

def validar_radar(doc):
    if not isinstance(doc,dict) or set(doc)-CAMPOS:
        erro(422,'radar_invalido','Radar deve conter somente campos publicos do protocolo.')
    for v in doc.values():
        if isinstance(v,(dict,list,bool)) or (isinstance(v,str) and len(v)>2000):
            erro(422,'radar_invalido','Campos devem ser escalares de ate 2000 caracteres.')
    try:
        json_doc(doc); falha=gov.validar_minimo(doc)
    except (ValueError,TypeError,OverflowError):
        falha=('radar','Campos numericos invalidos.')
    if falha:
        erro(422,'radar_invalido',str(falha[1]))
    return doc

def validar_fonte(doc):
    permitidas={'nome','url','formato','campos','caminho_itens','delimitador','intervalo_segundos'}
    if not isinstance(doc,dict) or set(doc)-permitidas:
        erro(422,'fonte_invalida','Receita invalida: nao recebe codigo, comandos nem credenciais.')
    if not isinstance(doc.get('nome'),str) or not 1<=len(doc['nome'])<=160:
        erro(422,'fonte_invalida','Informe o nome da fonte (ate 160 caracteres).')
    url_publica(doc.get('url'))
    if doc.get('formato') not in ('json','csv'):
        erro(422,'fonte_invalida','Receitas ensinadas aceitam JSON ou CSV.')
    campos=doc.get('campos')
    if not isinstance(campos,dict) or not campos or set(campos)-(CAMPOS|{'identificador'}):
        erro(422,'fonte_invalida','Mapeamento de colunas invalido.')
    if any(not isinstance(v,str) or not 1<=len(v)<=100 for v in campos.values()):
        erro(422,'fonte_invalida','Use nomes de colunas, sem expressoes executaveis.')
    if not isinstance(doc.get('caminho_itens',''),str) or len(doc.get('caminho_itens',''))>200:
        erro(422,'fonte_invalida','caminho_itens deve conter chaves separadas por ponto.')
    if doc.get('delimitador',',') not in (',',';','\t','|'):
        erro(422,'fonte_invalida','Delimitador CSV invalido.')
    n=doc.get('intervalo_segundos',86400)
    if type(n) is not int or not 300<=n<=31536000:
        erro(422,'fonte_invalida','Intervalo da fonte: 300 a 31536000 segundos.')
    return doc

def validar_evento(doc):
    if not isinstance(doc,dict) or set(doc)!={'uuid','origem','tipo','chave','revisao','acao','documento'}:
        erro(422,'evento_invalido','Envelope de evento invalido.')
    doc=dict(doc); doc['uuid']=id_uuid(doc['uuid']); doc['origem']=id_uuid(doc['origem'])
    if doc['tipo'] not in TIPOS or doc['acao'] not in ('publicar','retirar'):
        erro(422,'evento_invalido','Tipo ou acao invalido.')
    if not isinstance(doc['chave'],str) or not 1<=len(doc['chave'])<=160 or any(ord(c)<32 for c in doc['chave']):
        erro(422,'evento_invalido','Chave invalida.')
    if type(doc['revisao']) is not int or not 1<=doc['revisao']<=2147483647:
        erro(422,'evento_invalido','Revisao deve ser inteiro positivo.')
    if doc['acao']=='retirar':
        if doc['documento']!={}:
            erro(422,'evento_invalido','Retirada nao recebe dados.')
    else:
        (validar_radar if doc['tipo']==TIPO_RADAR else validar_fonte)(doc['documento'])
    if len(json_doc(doc).encode())>32768:
        erro(413,'evento_grande','Evento excede 32 KiB.')
    return doc

def _envelope(row):
    return {k:json.loads(row[k]) if k=='documento' else row[k] for k in ('uuid','origem','tipo','chave','revisao','acao','documento')}

def _catalogar(conn,seq,doc):
    tabela='TRASEIRO_CADASTRO' if doc['tipo']==TIPO_RADAR else 'TRASEIRO_FONTE'
    antigo=conn.execute('SELECT c.*,e.revisao FROM '+tabela+' c LEFT JOIN TRASEIRO_EVENTO e ON e.seq=c.evento_id WHERE c.origem=? AND c.chave=?',(doc['origem'],doc['chave'])).fetchone()
    if antigo is not None and antigo['revisao']>=doc['revisao']:
        return
    if antigo is None:
        conn.execute('INSERT INTO '+tabela+'(origem,chave,evento_id) VALUES(?,?,?)',(doc['origem'],doc['chave'],seq))
    else:
        campo="estado='pendente'" if doc['tipo']==TIPO_RADAR else 'ativo=0'
        conn.execute('UPDATE '+tabela+' SET evento_id=?, '+campo+' WHERE id=?',(seq,antigo['id']))

@gravacao
def receber(conn,eventos,via):
    if not isinstance(eventos,list) or len(eventos)>numero('lote'):
        erro(422,'lote_invalido','Envie uma lista com ate traseiro.lote eventos.')
    docs=[validar_evento(e) for e in eventos]; local=identidade(conn)['uuid']; novos=0
    conn.execute('SAVEPOINT traseiro_receber')
    try:
        for doc in docs:
            existente=conn.execute('SELECT * FROM TRASEIRO_EVENTO WHERE uuid=? OR (origem=? AND tipo=? AND chave=? AND revisao=?)',(doc['uuid'],doc['origem'],doc['tipo'],doc['chave'],doc['revisao'])).fetchone()
            if existente is not None:
                if _envelope(existente)!=doc:
                    erro(409,'evento_conflitante','Evento/revisao imutavel com conteudo divergente.')
                continue
            if doc['origem']==local:
                erro(409,'origem_local','Um par nao cria revisoes em nome desta instancia.')
            if doc['tipo']==TIPO_RADAR and dbmod.scalar(conn,"SELECT COUNT(*) FROM TRASEIRO_CADASTRO WHERE estado='pendente'")>=numero('max_pendentes'):
                erro(429,'fila_cheia','Fila mesh cheia; o remetente deve tentar depois.')
            texto=json_doc(doc['documento'])
            seq=dbmod.insert(conn,'TRASEIRO_EVENTO',{**{k:doc[k] for k in ('uuid','origem','tipo','chave','revisao','acao')},'documento':texto,'hash_documento':hashlib.sha256(texto.encode()).hexdigest(),'recebido_via':via,'recebido_em':agora()})
            _catalogar(conn,seq,doc); novos+=1
        conn.execute('RELEASE traseiro_receber'); conn.commit()
    except Exception:
        conn.execute('ROLLBACK TO traseiro_receber'); conn.execute('RELEASE traseiro_receber')
        raise
    return {'recebidos':len(docs),'novos':novos,'repetidos':len(docs)-novos}

@gravacao
def publicar(conn,tipo,chave,documento,acao='publicar',catalogar=True):
    tipo={'radar':TIPO_RADAR,'fonte':TIPO_FONTE}.get(tipo,tipo)
    local=identidade(conn)['uuid']
    anterior=conn.execute('SELECT * FROM TRASEIRO_EVENTO WHERE origem=? AND tipo=? AND chave=? ORDER BY revisao DESC LIMIT 1',(local,tipo,chave)).fetchone()
    if anterior and anterior['acao']==acao and json.loads(anterior['documento'])==documento:
        return anterior['seq']
    if catalogar and tipo==TIPO_RADAR and not dbmod.scalar(conn,'SELECT 1 FROM TRASEIRO_CADASTRO WHERE origem=? AND chave=?',(local,chave)) and dbmod.scalar(conn,"SELECT COUNT(*) FROM TRASEIRO_CADASTRO WHERE estado='pendente'")>=numero('max_pendentes'):
        erro(429,'fila_cheia','Fila mesh cheia; coleta ensinada sera retomada depois.')
    doc=validar_evento({'uuid':str(uuid.uuid4()),'origem':local,'tipo':tipo,'chave':chave,'revisao':anterior['revisao']+1 if anterior else 1,'acao':acao,'documento':documento})
    texto=json_doc(documento)
    seq=dbmod.insert(conn,'TRASEIRO_EVENTO',{**{k:doc[k] for k in ('uuid','origem','tipo','chave','revisao','acao')},'documento':texto,'hash_documento':hashlib.sha256(texto.encode()).hexdigest(),'recebido_em':agora()})
    if catalogar:
        _catalogar(conn,seq,doc)
    conn.commit()
    return seq

def pagina(conn,depois=0,limite=None,max_bytes=None,tipos=None):
    limite=min(numero('lote'),limite or numero('lote'))
    if type(depois) is not int or depois<0 or limite<1:
        erro(422,'cursor_invalido','Cursor inteiro nao negativo e limite positivo.')
    candidatos=conn.execute('SELECT * FROM TRASEIRO_EVENTO WHERE seq>? ORDER BY seq LIMIT ?',(depois,limite)).fetchall()
    rows=[]; tamanho=0
    for row in candidatos:
        n=len(json_doc(_envelope(row)).encode())+1
        if tamanho+n>min(max_bytes or numero('max_bytes'),numero('max_bytes'))-8192:
            if not rows:
                erro(413,'limite_remoto_pequeno','Um evento nao cabe no limite de bytes negociado.')
            break
        rows.append(row); tamanho+=n
    return {'eventos':[_envelope(r) for r in rows if tipos is None or r['tipo'] in tipos],'cursor':rows[-1]['seq'] if rows else depois,'mais':bool(rows and dbmod.scalar(conn,'SELECT 1 FROM TRASEIRO_EVENTO WHERE seq>? LIMIT 1',(rows[-1]['seq'],)))}

def exportar_pontos(conn):
    from . import consultas
    identidade(conn)
    ids=[tuple(r) for r in conn.execute('SELECT ponto_id,revisao FROM TRASEIRO_PONTO_PENDENTE ORDER BY ponto_id LIMIT ?',(numero('lote'),))]
    enviados=0
    for pid,revisao in ids:
        if not dbmod.scalar(conn,'SELECT 1 FROM TRASEIRO_CADASTRO WHERE ponto_id=?',(pid,)):
            row=conn.execute('SELECT removido_em,verificacao_status FROM PONTO_FISCALIZACAO WHERE id=?',(pid,)).fetchone()
            if row is not None:
                if row['removido_em'] or row['verificacao_status']=='desabilitado':
                    publicar(conn,'radar','P-'+str(pid),{},'retirar',catalogar=False)
                else:
                    p=consultas.buscar_ponto_por_id(conn,pid)
                    if p:
                        loc=p.get('localizacao') or {}
                        doc={k:loc[k] for k in ('latitude','longitude','uf','municipio','km','tipo_pista') if loc.get(k) is not None}
                        doc['municipio_ibge']=loc.get('codigo_ibge'); doc['via']=(loc.get('via') or {}).get('codigo')
                        if p.get('faixas'):
                            doc['sentido']=p['faixas'][0].get('sentido')
                        for k in ('leves','pesados'):
                            doc['velocidade_'+k]=p.get('velocidade_'+k+'_kmh')
                        for l in p.get('limites_velocidade') or []:
                            if l.get('categoria_veiculo')=='geral':
                                doc['velocidade_geral']=l.get('velocidade_kmh')
                        doc={k:v for k,v in doc.items() if v is not None}
                        if gov.validar_minimo(doc) is None:
                            publicar(conn,'radar','P-'+str(pid),doc,catalogar=False); enviados+=1
        # Coleta e rede rodam separadas: uma mudanca durante o envio fica na fila.
        conn.execute('DELETE FROM TRASEIRO_PONTO_PENDENTE WHERE ponto_id=? AND revisao=?',(pid,revisao))
    conn.commit()
    return enviados

def listar(conn,tipo,depois=0,limite=100):
    tabela='TRASEIRO_CADASTRO' if tipo=='cadastros' else 'TRASEIRO_FONTE'
    rows=conn.execute('SELECT c.*,e.documento,e.acao,e.revisao,e.recebido_em,i.nome AS instancia_nome,i.api_url AS instancia_url FROM '+tabela+' c LEFT JOIN TRASEIRO_EVENTO e ON e.seq=c.evento_id LEFT JOIN TRASEIRO_INSTANCIA i ON i.uuid=c.origem WHERE c.id>? ORDER BY c.id LIMIT ?',(depois,min(200,max(1,limite)))).fetchall()
    return [{**dict(r),'documento':json.loads(r['documento'])} for r in rows]

@gravacao
def decidir(conn,cadastro_id,acao,ctx,motivo,evento_id):
    gov.exigir(ctx,'moderador')
    if acao not in ('aprovar','rejeitar') or not isinstance(motivo,str) or not 5<=len(motivo.strip())<=2000:
        erro(422,'decisao_invalida','Aprove/rejeite informando como conferiu a posicao (motivo com 5 a 2000 caracteres).')
    row=conn.execute('SELECT c.*,e.documento,e.acao FROM TRASEIRO_CADASTRO c LEFT JOIN TRASEIRO_EVENTO e ON e.seq=c.evento_id WHERE c.id=?',(cadastro_id,)).fetchone()
    if row is None:
        erro(404,'cadastro_ausente','Cadastro mesh nao encontrado.')
    if evento_id!=row['evento_id']:
        erro(409,'revisao_alterada','Chegou outra revisao; recarregue antes de validar.')
    if row['estado']!='pendente':
        erro(409,'ja_decidido','Esta revisao ja recebeu uma decisao local.')
    pid=row['ponto_id']
    if acao=='aprovar':
        if row['acao']=='retirar':
            if pid:
                gov.remover_radar(conn,pid,ctx,motivo)
            estado='retirado'
        else:
            doc=json.loads(row['documento']); validar_radar(doc)
            lat,lon=gov._coord_item(doc)
            if lat is None or lon is None:
                erro(422,'posicao_ausente','Para aprovar a posicao, a revisao deve informar latitude e longitude.')
            if lat is not None and gov.bloqueio_que_contem(conn,lat,lon):
                erro(409,'area_bloqueada','Posicao bloqueada pela moderacao local.')
            if pid:
                p=conn.execute('SELECT removido_em,verificacao_status FROM PONTO_FISCALIZACAO WHERE id=?',(pid,)).fetchone()
                if p['removido_em'] or p['verificacao_status']=='desabilitado':
                    erro(409,'ponto_removido','A rede nao reativa radar removido ou desabilitado localmente.')
            from coletor.fontes.traseiro import ColetorTraseiro
            coletor=ColetorTraseiro(conn=conn)
            resumo=coletor.ingerir_registros([dict(doc,identificador=row['origem']+':'+row['chave'])],publicar=False)
            detalhe=next(iter(resumo.get('detalhes') or []),None)
            if detalhe is None:
                detalhe=conn.execute('SELECT vp.ponto_id FROM VINCULO_REGISTRO_PONTO vp LEFT JOIN REGISTRO_FONTE r ON r.id=vp.registro_id WHERE r.artefato_id=? AND vp.decisao_id IS NULL LIMIT 1',(resumo['artefato_id'],)).fetchone()
            if detalhe is None or detalhe['ponto_id'] is None:
                erro(422,'normalizacao_falhou','Normalizador nao aceitou a posicao; nenhuma aprovacao registrada.')
            pid=detalhe['ponto_id']
            conn.execute("UPDATE PONTO_FISCALIZACAO SET procedencia='oficial',verificacao_status='verificado' WHERE id=?",(pid,))
            gov.registrar_alteracao(conn,pid,ctx,'verificado',motivo='TRASEIRO DE URSO: '+motivo,campos={'origem_mesh':row['origem'],'evento_id':evento_id})
            coletor.publicar_snapshot([(resumo['recurso_id'],resumo['artefato_id'])],resumo='Validacao local TRASEIRO DE URSO')
            estado='aprovado'
    else:
        estado='rejeitado'
    conn.execute("UPDATE TRASEIRO_CADASTRO SET estado=?,ponto_id=?,validado_evento_id=CASE WHEN ?='aprovar' THEN evento_id ELSE validado_evento_id END WHERE id=?",(estado,pid,acao,cadastro_id))
    conn.execute('INSERT INTO TRASEIRO_DECISAO(evento_id,acao,quem,motivo,quando) VALUES(?,?,?,?,?)',(evento_id,acao,ctx.get('rotulo') or ctx.get('escopo') or 'operador',motivo.strip(),agora()))
    conn.commit()
    return {'id':cadastro_id,'estado':estado,'ponto_id':pid}

@gravacao
def ativar_fonte(conn,fonte_id,ativo,ctx,evento_id):
    gov.exigir(ctx,'admin')
    row=conn.execute('SELECT f.*,e.documento,e.acao FROM TRASEIRO_FONTE f LEFT JOIN TRASEIRO_EVENTO e ON e.seq=f.evento_id WHERE f.id=?',(fonte_id,)).fetchone()
    if row is None:
        erro(404,'fonte_ausente','Fonte ensinada nao encontrada.')
    if type(ativo) is not bool or row['evento_id']!=evento_id:
        erro(409,'revisao_alterada','Recarregue a receita antes de ativar/desativar.')
    if ativo:
        if row['acao']!='publicar':
            erro(409,'fonte_retirada','Receita retirada da rede.')
        validar_fonte(json.loads(row['documento']))
    conn.execute('UPDATE TRASEIRO_FONTE SET ativo=? WHERE id=?',(int(ativo),fonte_id))
    conn.execute('INSERT INTO TRASEIRO_DECISAO(evento_id,acao,quem,motivo,quando) VALUES(?,?,?,?,?)',(evento_id,'ativar_fonte' if ativo else 'desativar_fonte',ctx.get('rotulo') or 'admin','Decisao local; nao propagada.',agora()))
    conn.commit()

def status(conn):
    local=identidade(conn)
    return {'identidade':local,'habilitado':habilitado(),'acesso':caminhos.valor('traseiro','acesso')[0],
        'inatividade_tipo':caminhos.valor('traseiro','inatividade_tipo')[0],
        'inatividade_numero':numero('inatividade_numero'),
        'instancias':[dict(r) for r in conn.execute('SELECT * FROM TRASEIRO_INSTANCIA ORDER BY nome')],
        'pendentes':dbmod.scalar(conn,"SELECT COUNT(*) FROM TRASEIRO_CADASTRO WHERE estado='pendente'"),
        'eventos':dbmod.scalar(conn,'SELECT COUNT(*) FROM TRASEIRO_EVENTO'),
        'fontes':dbmod.scalar(conn,'SELECT COUNT(*) FROM TRASEIRO_FONTE'),
        'outbox':dbmod.scalar(conn,'SELECT COUNT(*) FROM TRASEIRO_PONTO_PENDENTE')}
