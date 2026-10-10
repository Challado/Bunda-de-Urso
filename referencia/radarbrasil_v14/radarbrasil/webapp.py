"""Gateway CGI compatível com fcgiwrap — não importa o módulo cgi.
Entradas por environ/STDIN e saída por stdout, execução em api.pse.
"""
import os,sys,json,logging,re,urllib.parse,traceback,subprocess
from datetime import datetime,timezone
from sqlalchemy import select,func
from . import settings
from .schema import init_db,Session,TABLES as T
from .normalization import decimal,road
from .query import query_points,get_point,get_equipment,list_ops,list_stretches,list_traffic,search_points,iso
from .collector import status as collector_status
from .formats import serialize,COLUMNS
from .logging_setup import setup
log=logging.getLogger('webapp')

PARAMS={
'lat':('decimal',True,'Latitude WGS84 graus decimais, -90..90',-24.9555),
'lon':('decimal',True,'Longitude WGS84 graus decimais, -180..180',-53.4552),
'raio':('integer',False,'Distância em metros, 1..50000 (configurável)',1000),
'formato':('string',False,'txt|json|ndjson|xml|edi|edifact|dif','json'),
'delimitador':('string',False,'Separador TXT, 1 caracter permitido, padrão |','|'),
'detalhado':('boolean',False,'Incluir objetos relacionais detalhados',True),
'incluir_inativos':('boolean',False,'Incluir situação operacional inativa',False),
'incluir_incertos':('boolean',False,'Incluir registros sem confirmação adicional',True),
'incluir_trechos':('boolean',False,'Adicionar trechos em coleção separada, sem inferir radar presente',False),
'incluir_operacoes':('boolean',False,'Adicionar operações relacionadas aos pontos retornados',False),
'uf':('string',False,'Sigla oficial da UF','PR'),
'municipio_ibge':('string',False,'Código IBGE de 7 dígitos','4104808'),
'rodovia':('string',False,'Código da rodovia','BR-277'),
'tipo_radar':('string',False,'Tipo de equipamento fixo|portatil|movel|desconhecido','fixo'),
'modalidade':('string',False,'permanente|pontual|itinerante|por_trecho|desconhecida','pontual'),
'sentido':('string',False,'crescente|decrescente|ambos|desconhecido','crescente'),
'fiscalizacao_pontual':('boolean',False,'true/false; desconhecido não coincide com ambos',True),
'em':('datetime',False,'Instante ISO 8601; restringe a operações com horário oficial comprovado','2026-10-10T12:00:00-03:00'),
'limite':('integer',False,'Resultados por página, 1..1000',100),
'offset':('integer',False,'Deslocamento da página de geolocalização, 0..10000000',0),
'ponto_id':('integer',False,'Filtra observações em /api/v1/trafego pelo ponto consolidado',1),
'equipamento_id':('integer',False,'Filtra /api/v1/geolocalizacoes por instrumento',1),
'somente_pendentes':('boolean',False,'Retorna apenas instrumentos sem coordenada cadastrada',True),
'cursor':('string',False,'Cursor da página anterior','...'),
'versao_esquema':('string',False,'Versão dos campos do contrato','1'),
}
ALLOWED_FORMATS={'txt','json','ndjson','xml','edi','edifact','dif'}
class APIError(Exception):
    def __init__(self,code,message,http=400):super().__init__(message);self.code=code;self.http=http

def parse_bool(value,name):
    v=str(value).lower()
    if v in ('true','1'):return True
    if v in ('false','0'):return False
    raise APIError('PARAM_INVALIDO',f'{name} requer true/false',422)

def parse_params(values,endpoint):
    unknown=set(values)-set(PARAMS)
    if unknown:raise APIError('PARAM_DESCONHECIDO','Parâmetros desconhecidos: '+', '.join(sorted(unknown)),422)
    fmt=values.get('formato','json').lower()
    if fmt not in ALLOWED_FORMATS:raise APIError('FORMATO_INVALIDO','formatos aceitos: '+','.join(sorted(ALLOWED_FORMATS)),400)
    result={'formato':fmt}
    dl=values.get('delimitador','|')
    if dl.lower()=='tab' or dl=='\\t':dl='\t'
    if len(dl)!=1 or dl in '\r\n\x00"\\':raise APIError('DELIMITADOR_INVALIDO','Delimitador deve ser um caractere seguro (ex.: | ; , # tab)',422)
    if 'delimitador' in values and fmt!='txt':raise APIError('DELIMITADOR_APENAS_TXT','delimitador só é aceito em formato=txt',422)
    result['delimitador']=dl
    if endpoint=='radares':
        if 'ponto_id' in values:raise APIError('PARAM_INVALIDO','ponto_id vale apenas em /api/v1/trafego',422)
        for name,lo,hi in [('lat',-90,90),('lon',-180,180)]:
            if name not in values:raise APIError('PARAM_OBRIGATORIO',f'{name} é obrigatório',422)
            try:parsed=float(values[name])
            except (ValueError,TypeError):raise APIError('PARAM_INVALIDO',f'{name} não é decimal',422)
            import math
            if not math.isfinite(parsed) or not lo<=parsed<=hi:raise APIError('PARAM_INVALIDO',f'{name} fora do intervalo {lo}..{hi}',422)
            result[name]=parsed
        try:radius=int(values.get('raio','1000'))
        except (ValueError,TypeError):raise APIError('PARAM_INVALIDO','raio deve ser inteiro',422)
        if not 1<=radius<=settings.MAX_RADIUS:raise APIError('PARAM_INVALIDO',f'raio deve ser 1..{settings.MAX_RADIUS}',422)
        result['raio']=radius
    try:limite=int(values.get('limite',100))
    except (ValueError,TypeError):raise APIError('PARAM_INVALIDO','limite deve ser inteiro',422)
    if not 1<=limite<=settings.MAX_RESULTS:raise APIError('PARAM_INVALIDO',f'limite deve ser 1..{settings.MAX_RESULTS}',422)
    result['limite']=limite
    if 'offset' in values:
        try:offset=int(values['offset'])
        except (ValueError,TypeError):raise APIError('PARAM_INVALIDO','offset requer inteiro',422)
        if offset<0 or offset>10000000:raise APIError('PARAM_INVALIDO','offset fora do intervalo',422)
        result['offset']=offset
    if 'ponto_id' in values:
        try:point_id=int(values['ponto_id'])
        except (ValueError,TypeError):raise APIError('PARAM_INVALIDO','ponto_id deve ser inteiro positivo',422)
        if point_id<1:raise APIError('PARAM_INVALIDO','ponto_id deve ser positivo',422)
        result['ponto_id']=point_id
    if 'equipamento_id' in values:
        try: eid=int(values['equipamento_id'])
        except (ValueError,TypeError):raise APIError('PARAM_INVALIDO','equipamento_id deve ser inteiro',422)
        if eid<1:raise APIError('PARAM_INVALIDO','equipamento_id deve ser positivo',422)
        result['equipamento_id']=eid
    for name in ('detalhado','incluir_inativos','incluir_incertos','incluir_operacoes','incluir_trechos','fiscalizacao_pontual','somente_pendentes'):
        if name in values:result[name]=parse_bool(values[name],name)
    for name in ('uf','municipio_ibge','rodovia','tipo_radar','modalidade','sentido','cursor','versao_esquema'):
        if name in values:
            v=str(values[name]).strip()
            if not v or len(v)>256:raise APIError('PARAM_INVALIDO',f'{name} vazio ou excessivamente longo',422)
            result[name]=v
    if 'uf' in result:
        result['uf']=result['uf'].upper()
        if not re.fullmatch('[A-Z]{2}',result['uf']):raise APIError('PARAM_INVALIDO','uf requer duas letras',422)
    if 'municipio_ibge' in result and not re.fullmatch(r'\d{7}',result['municipio_ibge']):raise APIError('PARAM_INVALIDO','municipio_ibge requer sete dígitos',422)
    if 'rodovia' in result:result['rodovia']=road(result['rodovia'])
    if 'em' in values:
        try:
            dt=datetime.fromisoformat(values['em'].replace('Z','+00:00'))
            if dt.tzinfo is None:raise ValueError('sem timezone')
            result['em']=dt.astimezone(timezone.utc)
        except ValueError:raise APIError('PARAM_INVALIDO','em requer ISO 8601 com fuso horário',422)
    if result.get('versao_esquema','1')!='1':raise APIError('VERSAO_INVALIDA','versao_esquema suportada: 1',422)
    return result

def help_document():
    return {'tipo_resposta':'ajuda','api':'RadarBrasil','versao':'1','endpoints':{
      '/api/v1/radares':'GET/POST; coordenadas e raio; saída consolidada',
      '/api/v1/radares/{id}':'GET; detalhe por ID',
      '/api/v1/radares/busca':'GET/POST; busca cadastral por UF, rodovia e filtros sem latitude/longitude',
      '/api/v1/equipamentos/{id}':'GET; instrumento cadastrado',
      '/api/v1/geolocalizacoes':'GET/POST; estados de GPS por instrumento, pendencias e candidatos geograficos',
      '/api/v1/operacoes':'GET/POST; operações conhecidas, sem presumir horário',
      '/api/v1/trechos':'GET/POST; trechos elegíveis, sem presumir operação',
      '/api/v1/fontes':'GET; status e cobertura de recursos',
      '/api/v1/fontes/{id}':'GET; dados de fonte',
      '/api/v1/atualizacoes':'GET; últimas execuções',
      '/api/v1/trafego':'GET/POST; observações agregadas, não limite regulamentado',
      '/api/v1/status':'GET/POST; situação da base e cache',
      '/api/v1/ajuda':'GET/POST; documentação do contrato',
      '/health/live':'GET; processo responde','/health/ready':'GET; base disponível',
      '/api/v1/admin/atualizar':'POST; requer token RADAR_ADMIN_TOKEN; dispara atualização',
    },'parametros':[{'nome':k,'tipo':v[0],'obrigatorio_em_radares':v[1],'descricao':v[2],'exemplo':v[3]} for k,v in PARAMS.items()],
      'colunas_txt_dif':[{'posicao':i,'nome':name,'tipo':'JSON em célula' if name.endswith('_json') else 'scalar','nullable':True} for i,name in enumerate(COLUMNS,1)],
      'velocidade':{'velocidade_leves_kmh':'limite regulamentado para leves; null se conflitante, não publicado ou incerto',
       'velocidade_pesados_kmh':'limite regulamentado para pesados, km/h',
       'velocidade_geral_kmh':'limite geral, km/h, não inferido de limites de categoria',
       'velocidades_resolvidas':'valores por categoria/faixa; quando conflito, velocidade_kmh=null e valores_publicados_kmh contém todas as versões',
       'limites_velocidade':'evidências de velocidade regulamentada com origem e histórico',
       'equipamentos[].faixas_medicao_nominal':'velocidade nominal do medidor no Inmetro, NÃO necessariamente limite legal da via',
       'trafego.velocidade_kmh':'velocidade observada de passagem, distinta do limite legal; não importada como limite'},
      'formatos':sorted(ALLOWED_FORMATS),'exemplos':{'GET':'/api/v1/radares?lat=-24.9555&lon=-53.4552&raio=100&formato=txt&delimitador=%7C','POST':{'url':'/api/v1/radares','body':{'lat':-24.9555,'lon':-53.4552,'raio':1000,'formato':'json'}}},
      'txt':{'linhas':f'uma por ponto; sem cabeçalho; {len(COLUMNS)} campos em ordem fixa','null':'\\N','literal_null':'\\\\N','escape':'CSV quoting com aspas duplas; barra invertida duplicada'},
      'edifact':{'mensagem':'GENRAL D96A','perfil':'RadarBrasil GENRAL/FTX AA I: JSON UTF-8 codificado em Base64; ver docs/EDIFACT_PERFIL.md'},
      'dif':{'formato':'Data Interchange Format tabular','nulidade':'\\N'},
      'codigos_http':{'200':'ok','400':'formato/endpoint inválido','422':'parâmetro inválido','404':'registro não encontrado','503':'base sem dados válidos'}}

def read_request(env,instream):
    method=env.get('REQUEST_METHOD','GET').upper()
    if method not in ('GET','POST'):raise APIError('METODO_INVALIDO','Use GET ou POST',405)
    p=urllib.parse.parse_qs(env.get('QUERY_STRING',''),keep_blank_values=True,strict_parsing=False)
    if any(len(v)!=1 for v in p.values()):raise APIError('PARAM_DUPLICADO','Não repetir nome de parâmetro',422)
    args={k:v[0] for k,v in p.items()}
    if method=='POST':
        try:size=int(env.get('CONTENT_LENGTH','0'))
        except ValueError:raise APIError('BODY_INVALIDO','CONTENT_LENGTH inválido',400)
        if size<0 or size>settings.MAX_POST_BODY:raise APIError('BODY_MUITO_GRANDE','Corpo da requisição muito grande',413)
        body=instream.read(size)
        content_type=env.get('CONTENT_TYPE','').split(';')[0].strip().lower()
        if content_type=='application/json':
            try:v=json.loads(body)
            except Exception:raise APIError('JSON_INVALIDO','Corpo JSON inválido',400)
            if not isinstance(v,dict):raise APIError('JSON_INVALIDO','Corpo JSON deve ser objeto',400)
            if any(isinstance(x,(list,dict)) for x in v.values()):raise APIError('JSON_INVALIDO','Parâmetros devem ser escalares',422)
            b={k:str(x).lower() if isinstance(x,bool) else str(x) for k,x in v.items()}
        elif content_type=='application/x-www-form-urlencoded':
            val=urllib.parse.parse_qs(body.decode('utf-8'),keep_blank_values=True)
            if any(len(x)!=1 for x in val.values()):raise APIError('PARAM_DUPLICADO','POST com parâmetro duplicado',422)
            b={k:v[0] for k,v in val.items()}
        else:raise APIError('CONTENT_TYPE_INVALIDO','Use application/json ou application/x-www-form-urlencoded',415)
        conflict=set(args)&set(b)
        if conflict:raise APIError('PARAM_DUPLICADO','Parâmetro simultâneo em query e corpo: '+','.join(conflict),422)
        args.update(b)
    path=env.get('PATH_INFO') or urllib.parse.urlsplit(env.get('REQUEST_URI','/')).path
    # SCRIPT_NAME = /api.pse quando o servidor chama CGI direto
    if path.endswith('/api.pse') or path=='/api.pse':path='/api/v1/radares'
    return method,path,args

def api_response(method,path,values,env):
    start=datetime.now(timezone.utc)
    suffix=path.rstrip('/').split('/')
    endpoint=suffix[2] if len(suffix)>=4 and suffix[1]=='api' and suffix[2]=='v1' else None
    # /api/v1/radares => ['', 'api','v1','radares']
    endpoint=suffix[3] if len(suffix)>=4 and suffix[1:3]==['api','v1'] else None
    if path in ('/health/live','/health/ready'):
        if path.endswith('ready'):
            try:
                with Session() as s:s.execute(select(func.count()).select_from(T['fonte'])).scalar_one()
            except Exception:raise APIError('BANCO_INDISPONIVEL','Banco não acessível',503)
        return 200,{'sucesso':True,'timestamp':start.isoformat()},'json',None
    if endpoint is None:raise APIError('ENDPOINT_INVALIDO','Endpoint desconhecido',404)
    if endpoint=='admin':
        if method!='POST' or suffix[-1]!='atualizar':raise APIError('METODO_INVALIDO','Somente POST /api/v1/admin/atualizar',405)
        if not settings.ADMIN_TOKEN:raise APIError('ADMIN_DESABILITADO','Token administrativo não configurado',403)
        import hmac
        token=env.get('HTTP_X_API_KEY','')
        if not hmac.compare_digest(token,settings.ADMIN_TOKEN):raise APIError('SEM_AUTORIZACAO','Token incorreto',403)
        # Coletor executa fora do processo CGI. Logs stdout/stderr no journald ou arquivo configurado.
        settings.CACHE_DIR.mkdir(parents=True,exist_ok=True)
        with (settings.CACHE_DIR/'admin-update.log').open('ab') as logfd:
            child=subprocess.Popen([sys.executable,'-m','radarbrasil.collector','update'],stdin=subprocess.DEVNULL,stdout=logfd,stderr=logfd,start_new_session=True,close_fds=True)
        return 202,{'sucesso':True,'pid':child.pid,'mensagem':'Atualização solicitada; acompanhe /api/v1/atualizacoes'},'json',None
    par=parse_params(values,'radar_detalhe' if endpoint=='radares' and len(suffix)==5 else endpoint)
    fmt=par['formato'];delimiter=par['delimitador']
    if endpoint=='ajuda':doc=help_document()
    elif endpoint=='status':doc={'sucesso':True,'versao_api':'1','consultado_em':start.isoformat(),**collector_status()}
    elif endpoint=='radares' and len(suffix)==4:
        lat,lon,raio=par['lat'],par['lon'],par['raio']
        filters={k:v for k,v in par.items() if k not in ('lat','lon','raio','formato','delimitador','limite','cursor','detalhado')}
        try:found=query_points(lat,lon,raio,filters,par['limite'],par.get('cursor'))
        except ValueError as e:raise APIError('CURSOR_INVALIDO',str(e),422)
        except RuntimeError as e:raise APIError('BASE_INDISPONIVEL',str(e),503)
        summary=collector_status()
        online=[v for v in summary['recursos'] if v['saude']=='recente']
        unavailable=[v for v in summary['recursos'] if v['saude'] in ('critico','indisponivel')]
        # Sem catálogo oficial de cobertura completa, não é possível afirmar inexistência.
        completo=False
        doc={'sucesso':True,'versao_api':'1','consultado_em':start.isoformat(),
             'consulta':{'latitude':lat,'longitude':lon,'raio_metros':raio,'filtros':filters},
             'resultado':{'encontrado':True if found['total'] else None,'total':found['total'],'retornados':found['retornados'],'total_equipamentos':sum(len(x['equipamentos']) for x in found['itens']),'proximo_cursor':found['proximo_cursor'],'status':'parcial' if not completo else 'completo','radares':found['itens']},
             'base_dados':{'status':'parcial','cobertura_completa':False,
               'fontes_com_sincronizacao_recente':len(online),'fontes_indisponiveis':len(unavailable),
               'recursos':summary['recursos'],
               'aviso_cache':'Datas de sincronização e publicação na origem são distintas; veja idade_horas e idade_publicacao_horas por recurso',
               'avisos':['Cobertura nacional não é comprovadamente completa; resultado vazio não significa ausência de fiscalização']}}
        if par.get('incluir_trechos'):
            # Não projetar todos os trechos nacionais como se coincidissem com o ponto consultado.
            doc['resultado']['trechos']=[]
            doc['base_dados']['avisos'].append('Consulta espacial de trechos sem geometria não implementada; consulte /api/v1/trechos separadamente')
        if par.get('incluir_operacoes',False):
            doc['resultado']['operacoes']=[op for item in found['itens'] for op in item['operacoes']]
    elif endpoint=='radares' and len(suffix)==5 and suffix[4]=='busca':
        fs={k:v for k,v in par.items() if k in ('uf','rodovia','municipio_ibge','tipo_radar','modalidade','incluir_inativos')}
        rows=search_points(fs,par['limite'])
        doc={'sucesso':True,'versao_api':'1','resultado':{'radares':rows,'total_retornado':len(rows),
            'status':'parcial','encontrado':True if rows else None},
            'aviso':'Busca cadastral sem cobertura integral garantida. Sem resultado não confirma ausência de radar'}
    elif endpoint=='radares' and len(suffix)==5:
        try:pid=int(suffix[4])
        except ValueError:raise APIError('ID_INVALIDO','ID não numérico',422)
        with Session() as s:obj=get_point(s,pid)
        if not obj:raise APIError('NAO_ENCONTRADO','Ponto não cadastrado',404)
        doc={'sucesso':True,'resultado':{'radares':[obj],'total':1}}
    elif endpoint=='equipamentos' and len(suffix)==5:
        try:eid=int(suffix[4])
        except ValueError:raise APIError('ID_INVALIDO','ID não numérico',422)
        obj=get_equipment(eid)
        if not obj:raise APIError('NAO_ENCONTRADO','Equipamento não cadastrado',404)
        doc={'sucesso':True,'resultado':{'itens':[obj],'total':1}}
    elif endpoint=='fontes':
        stat=collector_status()
        if len(suffix)==5:
            try:resourceid=int(suffix[-1])
            except ValueError:raise APIError('ID_INVALIDO','ID inválido',422)
            items=[x for x in stat['recursos'] if x['id']==resourceid]
            if not items:raise APIError('NAO_ENCONTRADO','Fonte/recurso não encontrado',404)
        else:items=stat['recursos']
        doc={'sucesso':True,'resultado':{'itens':items,'total':len(items)}}
    elif endpoint=='atualizacoes':
        with Session() as s:
            rows=s.execute(select(T['execucao_coleta']).order_by(T['execucao_coleta'].c.id.desc()).limit(par['limite'])).mappings().all()
            items=[{k:iso(v) if isinstance(v,datetime) else v for k,v in row.items()} for row in rows]
        doc={'sucesso':True,'resultado':{'itens':items,'total':len(items)}}
    elif endpoint=='geolocalizacoes':
        from .georesolver import locations_report
        eid=par.get('equipamento_id')
        # API paginada com teto: nao expor milhões de equipamentos em uma chamada.
        if eid:
            from .georesolver import _record_unlocated
            with Session() as s:r=_record_unlocated(s,eid)
            rows=[r] if r else []
        else:
            batch=locations_report(par['limite'],par.get('offset',0))
            rows=batch['equipamentos']
        if par.get('somente_pendentes'):
            rows=[x for x in rows if x['status']!='localizado']
        doc={'sucesso':True,'versao_api':'1','resultado':{'itens':rows,'total_retornado':len(rows),'proximo_offset':None if eid or len(rows)<par['limite'] else par.get('offset',0)+par['limite']},
             'aviso':'Um radar sem coordenada publicada nao pode ter posicao fisica exata garantida; candidatos podem ser coordenadas de endereco/rodovia ou OSM e exigem revisao'}
    elif endpoint=='trafego':
        rows=list_traffic(par['limite'],par.get('ponto_id'))
        doc={'sucesso':True,'resultado':{'itens':rows,'total_retornado':len(rows)},'aviso':'velocidade_observada_kmh não é limite regulamentado da via'}
    elif endpoint in ('trechos','operacoes'):
        items=list_stretches() if endpoint=='trechos' else list_ops()
        doc={'sucesso':True,'resultado':{endpoint:items,'total':len(items)},'aviso':'Registros sem coordenadas não comprovam fiscalização ativa'}
    else:raise APIError('ENDPOINT_INVALIDO','Endpoint não suportado',404)
    return 200,doc,fmt,delimiter

def respond(environ=None,stdin=None,stdout=None):
    environ=environ or os.environ;stdin=stdin or sys.stdin.buffer;stdout=stdout or sys.stdout.buffer
    setup()
    fmt='json';dl='|'
    try:
        method,path,values=read_request(environ,stdin)
        fmt=values.get('formato','json');dl=values.get('delimitador','|')
        code,doc,fmt,dl=api_response(method,path,values,environ)
        body,ctype=serialize(doc,fmt,dl or '|')
        # Sem radares dentro do raio: TXT vazio e HTTP 200; NÃO afirmar ausência oficial.
        if fmt=='txt' and doc.get('resultado',{}).get('radares')==[]:
            body=b''
    except APIError as e:
        code=e.http;message={'sucesso':False,'erro':{'codigo':e.code,'mensagem':str(e)},'consultado_em':datetime.now(timezone.utc).isoformat()}
        if fmt=='txt':body=f'ERRO|{e.code}|{str(e).replace(chr(10)," ")}\n'.encode('utf-8');ctype='text/plain; charset=utf-8'
        else:body,ctype=serialize(message,fmt if fmt in ('json','xml','ndjson','dif','edifact','edi') else 'json')
    except Exception:
        log.exception('Falha inesperada na API')
        code=503;body,ctype=serialize({'sucesso':False,'erro':{'codigo':'SERVICO_INDISPONIVEL','mensagem':'Falha de serviço; verificar logs'}} ,'json')
    status={200:'OK',202:'Accepted',400:'Bad Request',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',415:'Unsupported Media Type',422:'Unprocessable Entity',501:'Not Implemented',503:'Service Unavailable'}.get(code,'Error')
    extra=''
    if code==200 and isinstance(locals().get('doc'),dict):
        result=doc.get('resultado')
        if isinstance(result,dict) and 'radares' in result:
            extra=(f'X-RadarBrasil-Total: {result.get("total",0)}\r\n'
                   f'X-RadarBrasil-Cobertura: parcial\r\n'
                   f'X-RadarBrasil-Encontrado: {"sim" if result.get("total") else "desconhecido"}\r\n')
    out=(f'Status: {code} {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n{extra}\r\n').encode('ascii')
    stdout.write(out);stdout.write(body);stdout.flush()
    return code

if __name__=='__main__':respond()
