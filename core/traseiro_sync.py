"""Troca mesh e leitores ensinados; executados apenas no cron/API local."""
import csv
import datetime
import fcntl
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import socket
import urllib.parse
import urllib.request
import urllib.error
from . import atualizacoes, caminhos, db as dbmod, traseiro as tr
from .contexto_api import operacao_local


def _publica_resolvida(url):
    partes=urllib.parse.urlsplit(url)
    tr.url_publica(urllib.parse.urlunsplit((partes.scheme,partes.netloc,partes.path,'','')), api=urlsplit_api(url))
    host=urllib.parse.urlsplit(url).hostname
    ips=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not ips or any(not ipaddress.ip_address(i[4][0]).is_global for i in ips):
        raise ValueError('Destino mesh deve resolver somente para enderecos publicos.')


def urlsplit_api(url):
    return urllib.parse.urlsplit(url).path.endswith('.pse')


def _bytes(url, *, dados=None, headers=None):
    # Sem redirects: credenciais nunca sao reenviadas a outro destino.
    from coletor import http
    _publica_resolvida(url)
    corpo=None if dados is None else tr.json_doc(dados).encode()
    if corpo is not None and len(corpo)>tr.numero('max_bytes'):
        raise ValueError('Lote mesh excedeu max_bytes.')
    req=urllib.request.Request(url,data=corpo,headers={
        'Accept':'application/json','Accept-Encoding':'identity','User-Agent':'Traseiro-de-Urso/1',
        **({'Content-Type':'application/json'} if corpo is not None else {}),**(headers or {})})
    try:
        r=http._abrir(req,tr.numero('timeout'),True)
    except urllib.error.HTTPError as exc:
        if not headers or 'X-Interchange-Info' not in headers:
            exc.close()
            raise
        r=exc  # Erros autenticados podem anunciar limites novos para renegociacao.
    with r:
        raw=r.read(tr.numero('max_bytes')+1)
    if len(raw)>tr.numero('max_bytes'):
        raise ValueError('Resposta mesh excedeu max_bytes.')
    if isinstance(r,urllib.error.HTTPError):
        try:
            tem_bloco=isinstance(json.loads(raw).get('rede'),dict)
        except (ValueError,TypeError,AttributeError):
            tem_bloco=False
        if not tem_bloco:
            raise r
    return raw


def requisitar(api,local,doc=None):
    api=tr.url_publica(api,api=True)
    arquivo=tr.arquivo_tokens()
    credenciais=tr.tokens() if arquivo.exists() else {'saida':{}}
    valor=credenciais.get('saida',{}).get(api) or credenciais.get('token_rede')
    headers={'X-Interchange-Info':tr.cabecalho(local)}
    if valor:
        headers['Authorization']='Bearer '+valor
    url=api
    raw=_bytes(url,dados=doc,headers=headers)
    try:
        resposta=json.loads(raw)
        if not isinstance(resposta,dict):
            raise ValueError()
        remoto=resposta['rede']['consultado']
        if resposta['rede']['consultante']['uuid']!=local['uuid']:
            raise ValueError()
        tr.validar_informacoes(remoto.get('configuracao'))
        if resposta.get('sucesso') is not True:
            return {'_erro':resposta.get('erro') or {},'_instancia':remoto}
        if not isinstance(resposta.get('resultado'),dict):
            raise ValueError()
        return dict(resposta['resultado'],_instancia=remoto)
    except (ValueError,TypeError,KeyError):
        raise ValueError('Resposta invalida do protocolo TRASEIRO DE URSO.') from None


def inativar_vencidas(conn,agora=None):
    agora=agora or datetime.datetime.now(datetime.timezone.utc)
    tipo=caminhos.valor('traseiro','inatividade_tipo')[0]
    n=tr.numero('inatividade_numero')
    if tipo not in ('dias','tentativas') or n<1:
        raise ValueError('Use inatividade_tipo=dias|tentativas e inatividade_numero positivo.')
    instante=agora.isoformat(timespec='seconds')
    conn.execute("UPDATE TRASEIRO_INSTANCIA SET estado='ativo',ultima_tentativa=NULL,falhas=0 WHERE estado='pausado' AND pausa_fim<=?",(instante,))
    conn.execute("UPDATE TRASEIRO_INSTANCIA SET estado='pausado',falhas=0 WHERE estado!='bloqueado' AND parada_anunciada=1 AND pausa_inicio<=? AND (pausa_fim IS NULL OR pausa_fim>?)",(instante,instante))
    if tipo=='dias':
        limite=(agora-datetime.timedelta(days=n)).isoformat(timespec='seconds')
        conn.execute("UPDATE TRASEIRO_INSTANCIA SET estado='inativo' WHERE estado='ativo' AND CASE WHEN pausa_fim>COALESCE(ultimo_contato,criado_em) THEN pausa_fim ELSE COALESCE(ultimo_contato,criado_em) END<=?",(limite,))
    else:
        conn.execute("UPDATE TRASEIRO_INSTANCIA SET estado='inativo' WHERE estado='ativo' AND falhas>=?",(n,))
    conn.commit()


def contato(conn,ident):
    conn.execute("UPDATE TRASEIRO_INSTANCIA SET ultimo_contato=?,falhas=0,estado='ativo',ultimo_erro=NULL WHERE uuid=? AND estado!='bloqueado'",(tr.agora(),ident))
    conn.commit()


def falha(conn,ident,exc):
    conn.execute('UPDATE TRASEIRO_INSTANCIA SET falhas=falhas+1,ultimo_erro=? WHERE uuid=?',(str(atualizacoes.limpar(str(exc)))[:2000],ident))
    conn.commit()
    inativar_vencidas(conn)


def sincronizar_par(conn,par,local,api=None):
    """Uma unica consulta por rodada: envia e recebe um lote em cada direcao."""
    api=api or par['api_url']
    conhecido=par is not None
    if conhecido:
        conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_tentativa=? WHERE uuid=?',(tr.agora(),par['uuid'])); conn.commit()
        lote=tr.pagina(conn,par['cursor_saida'],min(tr.numero('lote'),par['lote']),max_bytes=par['max_bytes'],tipos=tr.tipos_par(conn,par['uuid']))
    else:
        lote={'eventos':[],'cursor':0}
    resposta=requisitar(api,local,{'eventos':lote['eventos'],'depois':par['cursor_entrada'] if conhecido else 0,'limite':tr.numero('lote')})
    remoto=resposta.pop('_instancia')
    if remoto.get('api_url')!=api or (conhecido and remoto.get('uuid')!=par['uuid']):
        raise ValueError('Identidade remota mudou; nao avanca cursores.')
    atual=tr.registrar_instancia(conn,remoto)
    ident=atual['uuid']
    if '_erro' in resposta:
        codigo=resposta['_erro'].get('codigo','erro_remoto')
        raise ValueError('Consulta recusada pelo destino: '+str(atualizacoes.limpar(codigo))[:120])
    if resposta.get('pausado') or resposta.get('adiado'):
        contato(conn,ident)
        inativar_vencidas(conn)
        return {'instancia':ident,'estado':'pausado' if resposta.get('pausado') else 'adiado'}
    if resposta.get('recebidos')!=len(lote['eventos']):
        raise ValueError('ACK remoto nao confirma o lote inteiro; sera reenviado.')
    cursor=resposta.get('cursor'); anterior=par['cursor_entrada'] if conhecido else 0
    if type(cursor) is not int or not anterior<=cursor<2**63 or (resposta.get('eventos') and cursor<=anterior):
        raise ValueError('Cursor remoto invalido.')
    recebidos=tr.receber(conn,resposta.get('eventos'),ident)
    # Persistencia vem antes do cursor: perda do ACK apenas repete o lote.
    conn.execute('UPDATE TRASEIRO_INSTANCIA SET cursor_entrada=?,cursor_saida=?,ultima_tentativa=? WHERE uuid=?',(cursor,lote['cursor'],tr.agora(),ident)); conn.commit()
    pares=resposta.get('instancias',[])
    if not isinstance(pares,list) or len(pares)>tr.numero('max_instancias'):
        raise ValueError('Catalogo remoto invalido.')
    for novo in pares:
        if isinstance(novo,dict) and novo.get('uuid')!=local['uuid']:
            try:
                if dbmod.scalar(conn,'SELECT 1 FROM TRASEIRO_INSTANCIA WHERE uuid=? OR api_url=?',(novo.get('uuid'),novo.get('api_url'))):
                    continue  # Limites/pausas de par conhecido so mudam em contato direto.
                tr.registrar_instancia(conn,novo)
            except tr.gov.GovernancaError as exc:
                atualizacoes.evento('traseiro.descoberta_recusada',codigo=exc.codigo)
    contato(conn,ident)
    return {'instancia':ident,'recebidos':recebidos['novos'],'enviados':len(lote['eventos']),'estado':'ok'}


def coletar_fonte(conn,row):
    receita=row['documento'] if isinstance(row['documento'],dict) else json.loads(row['documento']); tr.validar_fonte(receita)
    conn.execute('UPDATE TRASEIRO_FONTE SET ultima_tentativa=? WHERE id=?',(tr.agora(),row['id'])); conn.commit()
    raw=_bytes(receita['url'])
    if receita['formato']=='json':
        linhas=json.loads(raw)
        for chave in receita.get('caminho_itens','').split('.'):
            if chave:
                linhas=linhas[chave]
        if not isinstance(linhas,list):
            raise ValueError('Receita JSON nao aponta para uma lista.')
    else:
        linhas=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=receita.get('delimitador',',')))
    if len(linhas)>tr.numero('max_pendentes'):
        raise ValueError('Fonte excede limite de registros por documento.')
    recebidos=0
    for linha in linhas:
        if not isinstance(linha,dict):
            raise ValueError('Linha de fonte deve ser um objeto.')
        doc={k:linha.get(coluna) for k,coluna in receita['campos'].items() if k!='identificador' and linha.get(coluna) not in ('',None)}
        tr.validar_radar(doc)
        chave=linha.get(receita['campos'].get('identificador',''))
        if chave is None:
            chave=hashlib.sha256(tr.json_doc({k:doc.get(k) for k in ('latitude','longitude','via','km','sentido')}).encode()).hexdigest()
        chave='fonte:'+str(row['id'])+':'+str(chave)
        if len(chave)>160:
            chave='fonte:'+str(row['id'])+':'+hashlib.sha256(chave.encode()).hexdigest()
        tr.publicar(conn,'radar',chave,doc)
        recebidos+=1
    conn.execute('UPDATE TRASEIRO_FONTE SET ultimo_sucesso=?,ultimo_erro=NULL WHERE id=?',(tr.agora(),row['id'])); conn.commit()
    return recebidos


def _vencida(texto,intervalo):
    if not texto:
        return True
    return (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(texto)).total_seconds()>=intervalo


@operacao_local
def executar(conn):
    if not tr.habilitado():
        return {'estado':'desativado'}
    pasta=Path(caminhos.dentro_dados('traseiro','traseiro')); pasta.mkdir(parents=True,exist_ok=True)
    with (pasta/'sync.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {'estado':'em_execucao'}
        try:
            local=tr.identidade(conn)
            if caminhos.valor('traseiro','acesso')[0]=='tokens':
                tr.tokens()
        except Exception:
            with atualizacoes.acompanhar('traseiro'):
                raise
        if tr.pausada(local['configuracao']):
            return {'estado':'pausado','retornar_em_segundos':local['configuracao']['retornar_em_segundos']}
        with atualizacoes.acompanhar('traseiro') as registro:
            relatorio={'estado':'ok','exportados':tr.exportar_pontos(conn),'instancias':[],'fontes':[],'erros':[]}
            inativar_vencidas(conn)
            feitos=0
            for api in filter(None,(s.strip() for s in caminhos.valor('traseiro','pares')[0].split(','))):
                if feitos>=tr.numero('pares_por_tick'):
                    break
                try:
                    api=tr.url_publica(api,api=True)
                    if api==local['api_url'] or dbmod.scalar(conn,'SELECT 1 FROM TRASEIRO_INSTANCIA WHERE api_url=?',(api,)):
                        continue
                    feitos+=1
                    local=tr.identidade(conn)
                    if tr.pausada(local['configuracao']):
                        break
                    relatorio['instancias'].append(sincronizar_par(conn,None,local,api=api))
                except Exception as exc:
                    relatorio['erros'].append({'etapa':'descoberta','url':api,'erro':str(exc)})
            inativar_vencidas(conn)
            rows=conn.execute("SELECT * FROM TRASEIRO_INSTANCIA WHERE estado IN ('ativo','inativo') ORDER BY COALESCE(ultima_tentativa,''),uuid").fetchall()
            for r in rows:
                if feitos>=tr.numero('pares_por_tick'):
                    break
                intervalo=max(r['intervalo_segundos'],tr.numero('sondagem_segundos')) if r['estado']=='inativo' else r['intervalo_segundos']
                # Mesmo --forcar respeita o intervalo anunciado pelo servidor.
                if not _vencida(r['ultima_tentativa'],intervalo):
                    continue
                feitos+=1
                try:
                    local=tr.identidade(conn)
                    if tr.pausada(local['configuracao']):
                        break
                    relatorio['instancias'].append(sincronizar_par(conn,dict(r),local))
                except Exception as exc:
                    falha(conn,r['uuid'],exc)
                    relatorio['erros'].append({'etapa':'sincronizacao','instancia':r['uuid'],'erro':str(exc)})
            fontes_feitas=0
            for registro_fonte in conn.execute("SELECT f.*,e.documento FROM TRASEIRO_FONTE f LEFT JOIN TRASEIRO_EVENTO e ON e.seq=f.evento_id WHERE ativo=1 ORDER BY COALESCE(ultima_tentativa,''),f.id"):
                if fontes_feitas>=tr.numero('fontes_por_tick') or tr.pausada(tr.identidade(conn)['configuracao']):
                    break
                row=dict(registro_fonte); row['documento']=json.loads(row['documento'])
                if not _vencida(row['ultima_tentativa'],row['documento'].get('intervalo_segundos',86400)):
                    continue
                fontes_feitas+=1
                try:
                    relatorio['fontes'].append({'id':row['id'],'recebidos':coletar_fonte(conn,row)})
                except Exception as exc:
                    conn.execute('UPDATE TRASEIRO_FONTE SET ultimo_erro=? WHERE id=?',(str(atualizacoes.limpar(str(exc)))[:2000],row['id'])); conn.commit()
                    relatorio['erros'].append({'etapa':'fonte','id':row['id'],'erro':str(exc)})
            if relatorio['erros']:
                relatorio['estado']='erro'
            registro.terminar(1 if relatorio['erros'] else 0,resultado=atualizacoes.limpar(relatorio))
        return atualizacoes.limpar(relatorio)
