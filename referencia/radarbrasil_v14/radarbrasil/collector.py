"""CLI do coletor, independiente de CGI/web. Uso: python -m radarbrasil.collector --help"""
import argparse, os, json, sys, time, hashlib, logging, pathlib, fcntl, random
from datetime import timedelta
from sqlalchemy import select,func
from . import settings
from .schema import init_db,Session,seed_domains,TABLES as T
from .logging_setup import setup
from .sources import Downloader, SourceError, NotModified, ckan_discover, prf_fixed_discover,parse_table,osm_parse,OVERPASS_QUERY
from .ingest import register_resource,ingest_rows,new,row1,utcnow,asjson
log=logging.getLogger('collector')


def published_timestamp(value):
    """Data declarada pelo servidor ou catálogo; não confundir com baixado_em."""
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except (ValueError,TypeError):
        try:
            d=parsedate_to_datetime(str(value))
            if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except (ValueError,TypeError):return None

def sources():
    data=json.loads(settings.CONFIG_FILE.read_text('utf-8'))
    if not isinstance(data.get('sources'),list):raise ValueError('sources.json requer array sources')
    proibidas=[s.get('code','?') for s in data['sources'] if s.get('esfera')=='outra' or s.get('format')=='osm_overpass']
    if proibidas:raise ValueError('Fontes não oficiais proibidas: '+','.join(proibidas))
    return data['sources']

def alert(session,resource,execution,key,message,level='warning',resolve=False):
    now=utcnow();a=session.execute(select(T['alerta_operacional']).where(T['alerta_operacional'].c.chave_incidente==key,T['alerta_operacional'].c.status=='aberto').order_by(T['alerta_operacional'].c.id.desc()).limit(1)).mappings().first()
    if a:
        session.execute(T['alerta_operacional'].update().where(T['alerta_operacional'].c.id==a['id']).values(ultima_ocorrencia=now,ocorrencias=a['ocorrencias']+1,status='resolvido' if resolve else 'aberto',resolvido_em=now if resolve else None))
    elif not resolve:
        new(session,'alerta_operacional',recurso_id=resource,execucao_id=execution,chave_incidente=key,nivel=level,status='aberto',mensagem=message,primeira_ocorrencia=now,ultima_ocorrencia=now,ocorrencias=1)

def recent_artifact(s,rid):
    return s.execute(select(T['artefato_coleta']).where(T['artefato_coleta'].c.recurso_id==rid,T['artefato_coleta'].c.resultado_validacao=='valido').order_by(T['artefato_coleta'].c.id.desc()).limit(1)).mappings().first()

def run_source(config,downloader,force=False,file=None,file_fmt=None):
    name=config['code'];start=utcnow()
    if file:
        chosen={'url':config['url'] if config.get('url') else 'https://local.example/', 'format':file_fmt or pathlib.Path(file).suffix.lstrip('.'), 'name':name}
    elif config['format']=='ckan':chosen=ckan_discover(config,downloader)
    elif config['format']=='prf_fixos':chosen=prf_fixed_discover(config,downloader)
    else:chosen={'url':config['url'],'format':config['format'],'name':name}
    url=chosen['url'];fmt=chosen['format'].lower()
    with Session.begin() as s:
        sourceid,resourceid=register_resource(s,config,url,fmt)
        prev=recent_artifact(s,resourceid)
        past=s.execute(select(T['execucao_coleta'].c.iniciada_em).where(T['execucao_coleta'].c.recurso_id==resourceid,T['execucao_coleta'].c.status.in_(['ok','inalterado'])).order_by(T['execucao_coleta'].c.id.desc()).limit(1)).scalar_one_or_none()
    if not force and past and (start.replace(tzinfo=None)-past.replace(tzinfo=None)).total_seconds()<config.get('interval_seconds',3600):
        log.info('SKIP %s, intervalo ainda não vencido',name);return {'source':name,'status':'aguardando_intervalo'}
    status=200;headers={};raw=None
    try:
        if file:
            raw=pathlib.Path(file).read_bytes()
            if len(raw)>settings.MAX_BYTES:raise SourceError('Arquivo excede limite')
        elif fmt=='manual_json':raise SourceError('Fonte manual sem arquivo --file')
        elif fmt=='osm_overpass':
            raw,headers,_=downloader.fetch(url,method='POST',data={'data':OVERPASS_QUERY})
        else:
            raw,headers,_=downloader.fetch(url,etag=None if force or not prev else prev['etag'],last_modified=None if force or not prev else prev['last_modified_http'])
        if fmt=='osm_overpass':rows=osm_parse(raw)
        elif fmt=='prf_portateis':rows=parse_table(raw,'prf_portateis')
        elif fmt=='prf_fixos':rows=parse_table(raw,'html')
        else:rows=parse_table(raw,fmt)
        if not rows:raise SourceError('Fonte retornou zero registros')
        digest=hashlib.sha256(raw).hexdigest();folder=settings.CACHE_DIR/name
        folder.mkdir(parents=True,exist_ok=True)
        filepath=folder/(digest+'.'+('html' if fmt in ('prf_fixos','prf_portateis') else fmt))
        if not filepath.exists():
            temp=filepath.with_suffix(filepath.suffix+'.tmp')
            temp.write_bytes(raw);os.replace(temp,filepath)
        with Session.begin() as s:
            old=s.execute(select(T['artefato_coleta'].c.id).where(T['artefato_coleta'].c.recurso_id==resourceid,T['artefato_coleta'].c.hash_sha256==digest)).scalar_one_or_none()
            if old:
                art_id=old;counts={'received':len(rows),'accepted':len(rows),'rejected':0,'created':0};state='inalterado'
            else:
                art_id=new(s,'artefato_coleta',recurso_id=resourceid,hash_sha256=digest,caminho_cache=str(filepath),bytes_arquivo=len(raw),tipo_mime=headers.get('Content-Type'),data_publicacao_origem=published_timestamp(chosen.get('updated') or headers.get('Last-Modified')),etag=headers.get('ETag'),last_modified_http=headers.get('Last-Modified'),baixado_em=utcnow(),validado_em=utcnow(),resultado_validacao='valido')
                run_id=new(s,'execucao_coleta',recurso_id=resourceid,artefato_id=art_id,iniciada_em=start,status='executando',tentativas=1)
                counts=ingest_rows(s,resourceid,art_id,name,sourceid,rows,run_id)
                s.execute(T['execucao_coleta'].update().where(T['execucao_coleta'].c.id==run_id).values(terminada_em=utcnow(),status='ok',http_status=200,linhas_recebidas=counts['received'],linhas_validas=counts['accepted'],linhas_rejeitadas=counts['rejected'],registros_criados=counts['created']))
                state='ok'
            if old:
                run_id=new(s,'execucao_coleta',recurso_id=resourceid,artefato_id=art_id,iniciada_em=start,terminada_em=utcnow(),status=state,http_status=200,tentativas=1,linhas_recebidas=counts['received'],linhas_validas=counts['accepted'],linhas_rejeitadas=0,registros_criados=0)
            if state=='ok':
                last=s.execute(select(T['snapshot_publicado'].c.id).order_by(T['snapshot_publicado'].c.id.desc()).limit(1)).scalar_one_or_none()
                snapshot=new(s,'snapshot_publicado',anterior_id=last,publicado_em=utcnow(),status='parcial',identificador_versao=f'{name}:{digest[:20]}:{int(time.time())}',resumo_validacao=asjson(counts))
                new(s,'snapshot_recurso',snapshot_id=snapshot,recurso_id=resourceid,artefato_id=art_id)
            alert(s,resourceid,run_id,f'COLETA:{name}','restabelecida',resolve=True)
            s.execute(T['recurso_fonte'].update().where(T['recurso_fonte'].c.id==resourceid).values(status_integracao='implementado_nao_validado' if file else 'conectado'))
        log.info('IMPORT %s %s %s',name,state,counts)
        return {'source':name,'status':state,**counts}
    except NotModified:
        if not prev:
            raise SourceError('HTTP 304 sem cache válido anterior; revisar servidor externo')
        with Session.begin() as s:
            run_id=new(s,'execucao_coleta',recurso_id=resourceid,artefato_id=prev['id'] if prev else None,iniciada_em=start,terminada_em=utcnow(),status='inalterado',http_status=304,tentativas=1)
            alert(s,resourceid,run_id,f'COLETA:{name}','304',resolve=True)
        return {'source':name,'status':'inalterado_http_304'}
    except Exception as e:
        msg=str(e)[:1500]
        with Session.begin() as s:
            run_id=new(s,'execucao_coleta',recurso_id=resourceid,iniciada_em=start,terminada_em=utcnow(),status='falha',tentativas=1,erro_codigo=type(e).__name__,erro_detalhe=msg)
            alert(s,resourceid,run_id,f'COLETA:{name}',msg)
        log.exception('Falha na fonte %s, snapshot anterior preservado',name)
        return {'source':name,'status':'falha','erro':msg}

def locked_update(which=None,force=False,file=None,file_fmt=None):
    settings.CACHE_DIR.mkdir(parents=True,exist_ok=True)
    lock_file=settings.CACHE_DIR/'.collector.lock'
    with lock_file.open('w') as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Coletor já em execução')
        init_db()
        with Session.begin() as s:seed_domains(s)
        configs=sources()
        if which:configs=[v for v in configs if v['code'].upper()==which.upper()]
        else:configs=[v for v in configs if v.get('enabled')]
        if not configs:raise RuntimeError('Nenhuma fonte correspondente/habilitada')
        downloader=Downloader();results=[]
        for cfg in configs:
            try:results.append(run_source(cfg,downloader,force=force,file=file,file_fmt=file_fmt))
            except Exception as e:
                log.exception('Erro de descoberta na fonte %s',cfg['code'])
                # Erro antes de escolher recurso; registrar no cadastro da fonte como erro de descoberta
                with Session.begin() as s:
                    sid,rid=register_resource(s,cfg,cfg['url'],cfg['format'])
                    ridexec=new(s,'execucao_coleta',recurso_id=rid,iniciada_em=utcnow(),terminada_em=utcnow(),status='falha',tentativas=1,erro_codigo=type(e).__name__,erro_detalhe=str(e)[:1000])
                    alert(s,rid,ridexec,f'DESCOBERTA:{cfg["code"]}',str(e)[:1000])
                results.append({'source':cfg['code'],'status':'falha','erro':str(e)[:600]})
        return results

def status():
    init_db()
    with Session() as s:
        counts={name:s.execute(select(func.count()).select_from(T[name])).scalar_one() for name in ('ponto_fiscalizacao','equipamento','instalacao','fonte','registro_fonte','snapshot_publicado','alerta_operacional')}
        ins=T['instalacao'];point=T['ponto_fiscalizacao'];equip=T['equipamento']
        geo_count=s.execute(select(func.count(func.distinct(ins.c.equipamento_id)))
           .select_from(ins.join(point,ins.c.ponto_id==point.c.id))
           .where(point.c.posicao_id.is_not(None))).scalar_one()
        geo_summary={'total_equipamentos':counts['equipamento'],
            'equipamentos_com_coordenada':geo_count,
            'equipamentos_sem_coordenada':counts['equipamento']-geo_count,
            'aviso':'coordenada atribuida nao significa GPS de alta precisao; conferir qualidade e evidencia por equipamento'}
        src=[]
        for row in s.execute(select(T['recurso_fonte'])).mappings():
            last=s.execute(select(T['execucao_coleta']).where(T['execucao_coleta'].c.recurso_id==row['id']).order_by(T['execucao_coleta'].c.id.desc()).limit(1)).mappings().first()
            good=s.execute(select(T['execucao_coleta'].c.terminada_em).where(T['execucao_coleta'].c.recurso_id==row['id'],T['execucao_coleta'].c.status.in_(['ok','inalterado'])).order_by(T['execucao_coleta'].c.id.desc()).limit(1)).scalar_one_or_none()
            hours=(utcnow().replace(tzinfo=None)-good.replace(tzinfo=None)).total_seconds()/3600 if good else None
            health='indisponivel' if hours is None else 'critico' if hours>settings.CRITICAL_HOURS else 'atrasado' if hours>settings.WARNING_HOURS else 'recente'
            artifact=recent_artifact(s,row['id'])
            pub=artifact['data_publicacao_origem'] if artifact else None
            pubhours=(utcnow().replace(tzinfo=None)-pub.replace(tzinfo=None)).total_seconds()/3600 if pub else None
            src.append({'id':row['id'],'url':row['url_recurso'],'status':last['status'] if last else 'nunca_executado',
                'ultima_tentativa':str(last['iniciada_em']) if last else None,
                'ultima_sincronizacao':str(good) if good else None,
                'idade_horas':round(hours,2) if hours is not None else None,
                'publicado_na_origem_em':str(pub) if pub else None,
                'idade_publicacao_horas':round(pubhours,2) if pubhours is not None else None,
                'saude':health,'erro':last['erro_detalhe'] if last else None})
    return {'contadores':counts,'geolocalizacao':geo_summary,'recursos':src}

def audit_database():
    """Auditoria local: PK/FK/duplicidade/validade do cache, sem contato externo."""
    init_db()
    out={'tabelas':len(T),'contagem':{},'duplicidades':[],'integridade':{},'alertas':[]}
    for tab in ('ponto_fiscalizacao','equipamento','verificacao_metrologica','registro_fonte','candidato_duplicidade','limite_velocidade','execucao_coleta','erro_validacao','snapshot_publicado'):
        with Session() as s:out['contagem'][tab]=s.execute(select(func.count()).select_from(T[tab])).scalar_one()
    with Session() as s:
        for r in s.execute(select(T['candidato_duplicidade']).order_by(T['candidato_duplicidade'].c.id.desc()).limit(100)).mappings():
            out['duplicidades'].append({'id':r['id'],'registro_a':r['registro_a_id'],'registro_b':r['registro_b_id'],
                'score':float(r['score']) if r['score'] is not None else None,'estado':r['estado'],'evidencias':r['evidencias_resumo']})
        a=s.execute(select(T['alerta_operacional']).where(T['alerta_operacional'].c.status=='aberto').limit(100)).mappings().all()
        out['alertas']=[{'id':r['id'],'mensagem':r['mensagem'],'nivel':r['nivel']} for r in a]
        # FK cross-db executado pelo banco; SQLite verifica todas as relações.
        if s.bind.dialect.name=='sqlite':
            from sqlalchemy import text as sql_text
            out['integridade']['foreign_key_check']=[list(r) for r in s.execute(sql_text('PRAGMA foreign_key_check'))]
            out['integridade']['integrity_check']=[r[0] for r in s.execute(sql_text('PRAGMA integrity_check'))]
        else:
            out['integridade']['verificacao']='validar com ferramentas nativas do SGBD; constraints habilitadas no DDL'
    out['ok']=not out['integridade'].get('foreign_key_check') and out['integridade'].get('integrity_check',['ok'])==['ok']
    return out

def main(argv=None):
    p=argparse.ArgumentParser(description='RadarBrasil - coletor/sincronizador')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init');sub.add_parser('status');sub.add_parser('sources');sub.add_parser('validate-cache');sub.add_parser('audit')
    inventory=sub.add_parser('catalogo-nacional',help='Inventário de fontes por UF; não demonstra cobertura implantada')
    inventory.add_argument('--uf',help='Filtrar estado, exemplo: GO')
    up=sub.add_parser('update');up.add_argument('--source');up.add_argument('--force',action='store_true')
    imp=sub.add_parser('import-file');imp.add_argument('--source',required=True);imp.add_argument('--file',required=True);imp.add_argument('--format',required=True,choices=['csv','json','xlsx','xml','geojson','kml','prf_portateis'])
    args=p.parse_args(argv);setup(os.environ.get('RADAR_LOG_LEVEL','INFO'))
    try:
        if args.command=='init':
            n=init_db()
            with Session.begin() as s:seed_domains(s)
            result={'ok':True,'tabelas':n}
        elif args.command=='status':result=status()
        elif args.command=='audit':result=audit_database()
        elif args.command=='sources':result={'sources':sources()}
        elif args.command=='catalogo-nacional':
            catalog_path=pathlib.Path(__file__).resolve().parents[1]/'config'/'fontes_nacionais_27ufs.json'
            inventory=json.loads(catalog_path.read_text(encoding='utf-8'))
            uf=(args.uf or '').strip().upper()
            if uf and uf not in [row['uf'] for row in inventory['estados']]:
                raise ValueError('UF inválida: '+uf)
            states=[item for item in inventory['estados'] if not uf or item['uf']==uf]
            extra=[item for item in inventory['fontes_adicionais'] if not uf or item['uf']==uf]
            result={'data_catalogo':inventory['versao'],'total_ufs':len(states), 'total_fontes':len(states)+len(extra),'estados':states,'fontes_adicionais':extra,'aviso':'Fonte encontrada não significa coletor funcional, radar ativo ou cobertura estadual completa.'}
        elif args.command=='validate-cache':
            result={'files':0,'corrupt':[]}
            init_db()
            with Session() as s:
                for a in s.execute(select(T['artefato_coleta'])).mappings():
                    result['files']+=1
                    try:correct=hashlib.sha256(pathlib.Path(a['caminho_cache']).read_bytes()).hexdigest()==a['hash_sha256']
                    except OSError:correct=False
                    if not correct:result['corrupt'].append(a['id'])
            result['ok']=not result['corrupt']
        elif args.command=='update':result={'executions':locked_update(args.source,args.force)}
        else:result={'executions':locked_update(args.source,True,args.file,args.format)}
        print(json.dumps(result,ensure_ascii=False,default=str,indent=2))
        if args.command in ('update','import-file') and any(r['status']=='falha' for r in result['executions']):return 2
        if args.command in ('validate-cache','audit') and not result['ok']:return 2
        return 0
    except Exception as e:
        log.exception('Execução falhou');print(json.dumps({'success':False,'error':str(e)}),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
