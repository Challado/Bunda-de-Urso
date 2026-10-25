"""Protocolo Intercambio de Instancias v1, independente do Radar Brasil.

Somente biblioteca padrao. Pode ser copiado/importado por outro sistema.
Nao conhece radar.conf, SQLite, coletores ou os tipos de dados da aplicacao.
"""
import base64
import datetime
import json
import uuid
import urllib.request
import urllib.parse

PROTOCOLO={'nome':'intercambio-instancias','versao':1}
CABECALHO='X-Interchange-Info'

class ErroIntercambio(ValueError):
    pass


def json_canonico(valor):
    return json.dumps(valor,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def validar_configuracao(doc):
    if not isinstance(doc,dict):
        raise ErroIntercambio('Informe o bloco publico de configuracao.')
    saida={}
    for k,minimo,maximo in (('intervalo_segundos',1,2592000),('lote',1,1000),('max_bytes',65536,8388608)):
        n=doc.get(k)
        if type(n) is not int or not minimo<=n<=maximo:
            raise ErroIntercambio('Limite publico invalido: '+k)
        saida[k]=n
    if type(doc.get('parada_programada')) is not bool:
        raise ErroIntercambio('parada_programada deve ser booleano.')
    saida['parada_programada']=doc['parada_programada']
    for k in ('parar_em_segundos','retornar_em_segundos'):
        if type(doc.get(k)) is not int or not 0<=doc[k]<=315360000:
            raise ErroIntercambio('Prazos devem ser segundos inteiros nao negativos.')
        saida[k]=doc[k]
    if saida['parada_programada']:
        if saida['retornar_em_segundos'] and saida['retornar_em_segundos']<=saida['parar_em_segundos']:
            raise ErroIntercambio('Retorno deve ser posterior a parada; zero significa sem retorno.')
        if not isinstance(doc.get('anuncio_id'),str) or not 1<=len(doc['anuncio_id'])<=64:
            raise ErroIntercambio('Parada exige identificador estavel do anuncio.')
    elif saida['parar_em_segundos'] or saida['retornar_em_segundos']:
        raise ErroIntercambio('Ao cancelar a parada, zere os dois prazos.')
    saida['anuncio_id']=doc.get('anuncio_id') if saida['parada_programada'] else None
    return saida


def validar_identidade(doc):
    if not isinstance(doc,dict) or doc.get('protocolo')!=PROTOCOLO or type(doc['protocolo'].get('versao')) is not int:
        raise ErroIntercambio('Protocolo nao suportado.')
    try:
        if str(uuid.UUID(str(doc.get('uuid'))))!=doc['uuid']:
            raise ValueError()
    except (ValueError,TypeError,KeyError):
        raise ErroIntercambio('UUID de instancia invalido.') from None
    for k in ('nome','aplicacao'):
        if not isinstance(doc.get(k),str) or not 1<=len(doc[k])<=120:
            raise ErroIntercambio('Informe '+k+' com 1 a 120 caracteres.')
    p=urllib.parse.urlsplit(doc.get('api_url',''))
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:
        raise ErroIntercambio('api_url deve ser URL HTTPS publica da operacao de troca.')
    capacidades=doc.get('capacidades')
    tipos=capacidades.get('tipos_evento') if isinstance(capacidades,dict) else None
    if not isinstance(tipos,list) or len(tipos)>32:
        raise ErroIntercambio('Declare tipos_evento como lista de nomes unicos.')
    if any(not isinstance(t,str) or not 1<=len(t)<=120 or any(ord(c)<33 for c in t) for t in tipos):
        raise ErroIntercambio('Tipo de evento invalido.')
    if len(set(tipos))!=len(tipos):
        raise ErroIntercambio('Tipos de evento devem ser unicos.')
    validar_configuracao(doc.get('configuracao'))
    return doc


def codificar_info(doc):
    validar_identidade(doc)
    valor=base64.urlsafe_b64encode(json_canonico(doc).encode()).decode()
    if len(valor)>8192:
        raise ErroIntercambio('Identidade excede limite do cabecalho.')
    return valor


def decodificar_info(texto):
    if not isinstance(texto,str) or not texto or len(texto)>8192:
        raise ErroIntercambio('Informe X-Interchange-Info com identidade e limites publicos.')
    try:
        valor=json.loads(base64.b64decode(texto,altchars=b'-_',validate=True))
    except (ValueError,TypeError):
        raise ErroIntercambio('X-Interchange-Info invalido.') from None
    return validar_identidade(valor)


def parado(info):
    cfg=info['configuracao']
    return cfg['parada_programada'] and cfg['parar_em_segundos']==0


def proxima_consulta(consultado,ultima_tentativa):
    """O prazo e exclusivamente do consultado; o consulente tem seu proprio."""
    validar_identidade(consultado)
    return ultima_tentativa+datetime.timedelta(seconds=consultado['configuracao']['intervalo_segundos'])


def validar_pedido(pedido,consultado):
    """Parte reutilizavel do receptor; documentos sao validados pelo adaptador."""
    validar_identidade(consultado)
    if not isinstance(pedido,dict) or set(pedido)-{'eventos','depois','limite'}:
        raise ErroIntercambio('Pedido de intercambio invalido.')
    eventos=pedido.get('eventos')
    if not isinstance(eventos,list) or len(eventos)>consultado['configuracao']['lote']:
        raise ErroIntercambio('Lote excede limite do consultado.')
    if type(pedido.get('depois',0)) is not int or not 0<=pedido.get('depois',0)<2**63:
        raise ErroIntercambio('Cursor invalido.')
    if type(pedido.get('limite',1)) is not int or not 1<=pedido.get('limite',1)<=1000:
        raise ErroIntercambio('Limite de pagina invalido.')
    for evento in eventos:
        if not isinstance(evento,dict) or evento.get('tipo') not in consultado['capacidades']['tipos_evento']:
            raise ErroIntercambio('Tipo de documento nao anunciado pelo consultado.')
    return pedido


def responder(consultado,consultante,resultado):
    """Envelope comum de servidor. Autorizacao e persistencia sao do hospedeiro."""
    validar_identidade(consultado);validar_identidade(consultante)
    if not isinstance(resultado,dict):
        raise ErroIntercambio('Resultado deve ser objeto JSON.')
    return {'sucesso':True,'rede':{'consultado':consultado,'consultante':consultante},'resultado':resultado}


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def consultar(url,identidade,*,eventos=(),depois=0,token=None,timeout=15,transporte=None):
    """Uma troca generica. O chamador persiste cursor/ACK e agenda nova consulta.

    transporte opcional recebe Request e timeout, devolve bytes (testes/SDKs).
    Nao envia eventos de tipos que o destino ainda nao anunciou: o primeiro
    contato deve usar eventos vazios para conhecer capacidades e limites.
    """
    validar_identidade(identidade)
    if parado(identidade):
        raise ErroIntercambio('Instancia declarada parada nao pode consultar pares.')
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:
        raise ErroIntercambio('Destino deve ser HTTPS sem credenciais embutidas.')
    headers={CABECALHO:codificar_info(identidade),'Content-Type':'application/json','Accept':'application/json'}
    if token:
        headers['Authorization']='Bearer '+token
    corpo=json_canonico({'eventos':list(eventos),'depois':depois,'limite':identidade['configuracao']['lote']}).encode()
    req=urllib.request.Request(url,data=corpo,headers=headers)
    if transporte:
        raw=transporte(req,timeout)
    else:
        with urllib.request.build_opener(_SemRedirecionar()).open(req,timeout=timeout) as resposta:
            raw=resposta.read(identidade['configuracao']['max_bytes']+1)
    if len(raw)>identidade['configuracao']['max_bytes']:
        raise ErroIntercambio('Resposta excede limite de bytes.')
    doc=json.loads(raw)
    if not isinstance(doc,dict) or doc.get('sucesso') is not True:
        raise ErroIntercambio('Operacao de intercambio recusada.')
    validar_identidade(doc['rede']['consultado'])
    if doc['rede']['consultante']['uuid']!=identidade['uuid']:
        raise ErroIntercambio('Resposta destinada a outra instancia.')
    return doc
