"""RadarBrasil: coordenadas auditáveis sem PostGIS.

Nunca transforma endereço aproximado, marco quilométrico, ou POI OSM na posição
EXATA de um equipamento. O OSM é usado SOMENTE como candidato independente.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,logging,math,os,pathlib,re,sys,unicodedata,zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, and_, or_, func
from .schema import TABLES as T, Session, init_db, seed_domains,get_code
from .normalization import decimal as dnum,road as road_normalize, haversine,key

LOG=logging.getLogger('radarbrasil.georesolver')
UF_IBGE={'12':'AC','27':'AL','16':'AP','13':'AM','29':'BA','23':'CE','53':'DF','32':'ES','52':'GO','21':'MA','51':'MT','50':'MS','31':'MG','15':'PA','25':'PB','41':'PR','26':'PE','22':'PI','33':'RJ','24':'RN','43':'RS','11':'RO','14':'RR','42':'SC','35':'SP','28':'SE','17':'TO'}

def now():return datetime.now(timezone.utc)
def norm(x):return key(x)
def number(x,lat=True):
    value=dnum(x,-90 if lat else -180,90 if lat else 180)
    if value is None or (lat and abs(value)>34) or (not lat and not -75<=value<=-32):
        return None
    return float(value)

def row_id(s,tablename,**fields):
    return s.execute(T[tablename].insert().values(**fields)).inserted_primary_key[0]

def get_source(s,name,kind='oficial',url=''):
    t=T['geo_fonte'];old=s.execute(select(t.c.id).where(t.c.nome==name)).scalar_one_or_none()
    if old is not None:return old
    return row_id(s,'geo_fonte',nome=name,tipo=kind,url=url or None,registrado_em=now())

def _sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()

def candidates(s,point_id=None,equip_id=None,status=None):
    t=T['geo_candidato'];q=select(t)
    if point_id is not None:q=q.where(t.c.ponto_id==point_id)
    if equip_id is not None:q=q.where(t.c.equipamento_id==equip_id)
    if status:q=q.where(t.c.status==status)
    return [dict(r) for r in s.execute(q.order_by(t.c.id)).mappings()]

def add_candidate(s,*,point_id=None,equip_id=None,lat,lon,method,source_id,proof,score,precision=None,external_id=None,detail=None):
    if (point_id is None)==(equip_id is None):raise ValueError('Fornecer exatamente um alvo: ponto_id ou equipamento_id')
    lat=number(lat);lon=number(lon,False)
    if lat is None or lon is None:raise ValueError('Coordenada invalida ou fora do Brasil')
    if not 0<=score<=1:raise ValueError('score deve estar entre 0 e 1')
    if precision is not None and (precision<0 or not math.isfinite(precision)):raise ValueError('precisao invalida')
    stable=json.dumps([point_id,equip_id,round(lat,7),round(lon,7),method,source_id,external_id],ensure_ascii=False)
    digest=_sha(stable)
    t=T['geo_candidato'];old=s.execute(select(t.c.id).where(t.c.hash_identidade==digest)).scalar_one_or_none()
    if old is not None:return old,False
    pos_id=row_id(s,'posicao_geografica',latitude=lat,longitude=lon,precisao_metros=precision,
       qualidade_posicao_id=get_code(s,'qualidade_posicao','estimada' if method in ('km_calibrado','cnefe_endereco') else 'desconhecida'),metodo_obtencao=method)
    cid=row_id(s,'geo_candidato',ponto_id=point_id,equipamento_id=equip_id,posicao_id=pos_id,fonte_geo_id=source_id,
       metodo=method,status='revisar',score=score,evidencia=proof[:2000],referencia_externa=(external_id or '')[:255] or None,
       detalhe_json=json.dumps(detail or {},ensure_ascii=False,default=str),hash_identidade=digest,criado_em=now())
    return cid,True

def _quality(candidate):
    # Posição OSM / CNEFE nunca é tratada como medida direta do equipamento.
    return 'inferida' if candidate['metodo'] in ('km_calibrado','cnefe_endereco') else 'desconhecida'

def promote_candidate(s,cid,actor,reason):
    """Confirma associação manual. Nunca sobrescreve GPS oficial preexistente."""
    if not actor or not reason or len(reason.strip())<15:raise ValueError('Ator e justificativa com pelo menos 15 caracteres obrigatorios')
    c=s.execute(select(T['geo_candidato']).where(T['geo_candidato'].c.id==cid)).mappings().first()
    if c is None:raise ValueError('candidato inexistente')
    if c['status']=='aprovado':return {'id':cid,'status':'aprovado','idempotente':True}
    if c['status']=='rejeitado':raise ValueError('candidato rejeitado: requer nova avaliação')
    pid=c['ponto_id']
    if pid is None:
        # Só criar ponto para equipamento ainda sem instalação. Não inferir associação
        # temporal de radar portátil que pode trocar de local.
        eq=s.execute(select(T['equipamento']).where(T['equipamento'].c.id==c['equipamento_id'])).mappings().first()
        if eq is None:raise ValueError('equipamento inexistente')
        if s.execute(select(T['instalacao'].c.id).where(T['instalacao'].c.equipamento_id==eq['id']).limit(1)).first():
            raise ValueError('equipamento ja instalado em outro ponto: associacao de sitio exige revisao explicita')
        if get_code(s,'tipo_radar','portatil')==eq['tipo_radar_id'] or get_code(s,'tipo_radar','movel')==eq['tipo_radar_id']:
            raise ValueError('radar portatil/movel nao deve receber posicao fixa por candidato')
        pid=row_id(s,'ponto_fiscalizacao',posicao_id=c['posicao_id'],situacao_operacional_id=get_code(s,'situacao_operacional','desconhecido'))
        row_id(s,'instalacao',ponto_id=pid,equipamento_id=eq['id'])
        s.execute(T['geo_candidato'].update().where(T['geo_candidato'].c.id==cid).values(ponto_id=pid,equipamento_id=None))
    else:
        p=s.execute(select(T['ponto_fiscalizacao']).where(T['ponto_fiscalizacao'].c.id==pid)).mappings().one()
        if p['posicao_id'] is not None:raise ValueError('ponto ja tem coordenada: nao sobrescrever')
        s.execute(T['ponto_fiscalizacao'].update().where(T['ponto_fiscalizacao'].c.id==pid).values(posicao_id=c['posicao_id']))
    s.execute(T['posicao_geografica'].update().where(T['posicao_geografica'].c.id==c['posicao_id']).values(
        qualidade_posicao_id=get_code(s,'qualidade_posicao',_quality(c))))
    s.execute(T['geo_candidato'].update().where(T['geo_candidato'].c.id==cid).values(status='aprovado'))
    row_id(s,'geo_decisao',candidato_id=cid,decisao='aprovado',ator=actor,justificativa=reason,decidida_em=now())
    return {'id':cid,'ponto_id':pid,'status':'aprovado'}

def reject_candidate(s,cid,actor,reason):
    if not actor or len(reason.strip())<10:raise ValueError('Ator e justificativa obrigatorios')
    c=s.execute(select(T['geo_candidato']).where(T['geo_candidato'].c.id==cid)).mappings().first()
    if not c or c['status']!='revisar':raise ValueError('candidato ausente ou ja decidido')
    s.execute(T['geo_candidato'].update().where(T['geo_candidato'].c.id==cid).values(status='rejeitado'))
    row_id(s,'geo_decisao',candidato_id=cid,decisao='rejeitado',ator=actor,justificativa=reason,decidida_em=now())

def _open_csv_rows(filename):
    """CSV plano ou ZIP com CSV: leitura em streaming, separador autodetectado."""
    f=pathlib.Path(filename)
    if f.stat().st_size>2_500_000_000:raise ValueError('arquivo excede limite de 2,5 GB')
    if f.suffix.lower()=='.zip':
        with zipfile.ZipFile(f) as z:
            candidates=[x for x in z.infolist() if x.filename.lower().endswith('.csv') and not x.is_dir()]
            if len(candidates)!=1:raise ValueError('ZIP deve conter exatamente um CSV; use arquivo municipal por vez')
            info=candidates[0]
            if info.file_size>3_000_000_000 or info.file_size/max(info.compress_size,1)>500:
                raise ValueError('possivel ZIP bomb')
            with z.open(info) as b,io.TextIOWrapper(b,encoding='utf-8-sig',errors='replace',newline='') as stream:
                yield from _read_stream(stream)
    else:
        with f.open(encoding='utf-8-sig',errors='replace',newline='') as stream:
            yield from _read_stream(stream)

def _read_stream(stream):
    head=stream.readline();
    if not head:return
    delim=';' if head.count(';')>head.count(',') else ','
    stream=iter([head]+list(stream)) if False else _rechain(head,stream)
    reader=csv.DictReader(stream,delimiter=delim)
    for row in reader:yield row

def _rechain(head, stream):
    yield head
    yield from stream

def getv(row,*aliases):
    indexed={key(k):v for k,v in row.items() if k is not None}
    for k in aliases:
        x=indexed.get(key(k))
        if x is not None and str(x).strip():return str(x).strip()
    return None

def _via_id(s,name):
    label=road_normalize(name)
    if not label or not re.fullmatch(r'[A-Z]{2}-\d{2,4}',label):return None
    old=s.execute(select(T['via'].c.id).where(T['via'].c.codigo==label)).scalar_one_or_none()
    if old is not None:return old
    kind='federal' if label.startswith('BR-') else 'estadual'
    return row_id(s,'via',codigo=label,tipo_via_id=get_code(s,'tipo_via',kind))

def import_road_segments(path,source_name,source_url):
    """Importa trechos oficiais CALIBRADOS por km_inicio/km_fim com polilinha WGS84.
    CSV: via,km_inicio,km_fim,geometria_json (GeoJSON LineString coordinates lon,lat),uf.
    Segmentos sem km calibrado são rejeitados; evitar interpolar quilômetros ao longo
    de linha sem referência de marcos e sem saber se usa mesmo SNV/SRE.
    """
    result={'linhas':0,'criadas':0,'rejeitadas':0,'erros':[]}
    with Session.begin() as s:
        sourceid=get_source(s,source_name,'oficial',source_url)
        for line,row in enumerate(_open_csv_rows(path),2):
            result['linhas']+=1
            try:
                km0=dnum(getv(row,'km_inicio','km_inicial'),0,100000)
                km1=dnum(getv(row,'km_fim','km_final'),0,100000)
                if km0 is None or km1 is None or km1<=km0:raise ValueError('marcos quilometricos nao calibrados')
                via=_via_id(s,getv(row,'via','rodovia'))
                if via is None:raise ValueError('rodovia ainda nao cadastrada na base')
                poly=json.loads(getv(row,'geometria_json','geometry','linestring') or 'null')
                if isinstance(poly,dict):poly=poly.get('coordinates') if poly.get('type')=='LineString' else None
                if not isinstance(poly,list) or len(poly)<2 or len(poly)>100000:raise ValueError('LineString nao presente ou invalida')
                points=[]
                for coord in poly:
                    if not isinstance(coord,(list,tuple)) or len(coord)<2:raise ValueError('vertice invalido')
                    lon=number(coord[0],False);lat=number(coord[1]);
                    if lat is None or lon is None:raise ValueError('vertice fora do Brasil')
                    points.append((lat,lon))
                if max(haversine(*points[i],*points[i+1]) for i in range(len(points)-1))>30000:
                    raise ValueError('vertices separados por mais de 30km: geometria insuficiente')
                identity=_sha(json.dumps([sourceid,via,str(km0),str(km1),points]))
                tab=T['geo_trecho_calibrado'];old=s.execute(select(tab.c.id).where(tab.c.hash_origem==identity)).scalar_one_or_none()
                if old:continue
                tid=row_id(s,'geo_trecho_calibrado',via_id=via,fonte_geo_id=sourceid,km_inicio=km0,km_fim=km1,
                    hash_origem=identity,referencia=getv(row,'identificador','referencia','id') or source_url,
                    uf=getv(row,'uf'),importado_em=now())
                for order,(lat,lon) in enumerate(points):row_id(s,'geo_trecho_vertice',trecho_id=tid,ordem=order,latitude=lat,longitude=lon)
                result['criadas']+=1
            except (ValueError,TypeError,json.JSONDecodeError) as e:
                result['rejeitadas']+=1
                if len(result['erros'])<50:result['erros'].append({'linha':line,'erro':str(e)})
    return result

def import_road_geojson(path,source_name,source_url):
    """Importa camada rodoviaria GeoJSON oficial com geometria LineString e
    marcos kilometrico INICIAL e FINAL presentes no mesmo feature. Sem ambos,
    recusa o registro; não inventa marco pela extensão da linha.
    """
    f=pathlib.Path(path)
    if f.stat().st_size>300_000_000:raise ValueError('GeoJSON oficial excede limite de 300MB; dividir por estado/rodovia')
    data=json.loads(f.read_text(encoding='utf-8'))
    if data.get('type')!='FeatureCollection':raise ValueError('GeoJSON FeatureCollection exigido')
    crs=data.get('crs')
    if crs and '4326' not in json.dumps(crs) and 'CRS84' not in json.dumps(crs).upper():
        raise ValueError('CRS diferente de WGS84/EPSG:4326; transformar usando dados oficiais antes de importar')
    counts={'features':len(data.get('features',[])),'criados':0,'rejeitados':0,'erros':[]}
    # Mesmo validador do importador CSV; não duplica regras de negocio.
    lines=[]
    for idx,feature in enumerate(data.get('features',[])):
        geom=feature.get('geometry') or {};pr=feature.get('properties') or {}
        if geom.get('type')!='LineString':
            counts['rejeitados']+=1;continue
        name=getv(pr,'rodovia','via','rodovia_snv','sigla_rodovia','codigo_rodovia','br')
        start=getv(pr,'km_inicio','km_inicial','km_ini','kmi','inicio_km')
        end=getv(pr,'km_fim','km_final','km_fin','kmf','fim_km')
        if not name or not start or not end:
            counts['rejeitados']+=1;continue
        lines.append({'via':name,'km_inicio':start,'km_fim':end,'geometria_json':json.dumps(geom),
            'uf':getv(pr,'uf'),'referencia':getv(pr,'id','codigo','trecho') or f'{f.name}:feature:{idx}'})
    import tempfile
    with tempfile.TemporaryDirectory(prefix='radar_geo_') as temp:
        csv_file=pathlib.Path(temp)/'segmentos.csv'
        with csv_file.open('w',newline='',encoding='utf-8') as b:
            writer=csv.DictWriter(b,fieldnames=['via','km_inicio','km_fim','geometria_json','uf','referencia'],delimiter=';')
            writer.writeheader();writer.writerows(lines)
        result=import_road_segments(csv_file,source_name,source_url)
    counts['criados']=result['criadas']
    counts['rejeitados']+=result['rejeitadas']
    counts['erros']=result['erros']
    return counts

def importar_municipios_api_ibge(cache_file=None,request_func=None):
    """Consulta EXCLUSIVAMENTE a API oficial de localidades do IBGE e preserva
    JSON para auditoria. Falhas de rede não mudam o cadastro prévio.
    """
    import urllib.request
    url='https://servicodados.ibge.gov.br/api/v1/localidades/municipios'
    if request_func is None:
        req=urllib.request.Request(url,headers={'User-Agent':'RadarBrasil/1.4 - auditoria de coordenadas'})
        with urllib.request.urlopen(req,timeout=60) as resp:
            if resp.status!=200:raise ValueError('IBGE resposta HTTP invalida')
            raw=resp.read(10_000_001)
            if len(raw)>10_000_000:raise ValueError('Resposta IBGE excede 10 MB')
    else:raw=request_func(url)
    data=json.loads(raw)
    if not isinstance(data,list) or len(data)<5000:
        raise ValueError('Resposta IBGE incompleta - nao alterar municipios')
    rows=[]
    for mun in data:
        id=str(mun.get('id',''));name=mun.get('nome')
        im=mun.get('microrregiao') or {};meso=im.get('mesorregiao') or {};uf=(meso.get('UF') or {}).get('sigla')
        if not uf:
            imediato=mun.get('regiao-imediata') or {};inter=imediato.get('regiao-intermediaria') or {}
            uf=(inter.get('UF') or {}).get('sigla')
        rows.append({'codigo_ibge':id,'uf':uf or '', 'nome':name or ''})
    import tempfile
    with tempfile.TemporaryDirectory(prefix='radar_ibge_') as tmp:
        path=pathlib.Path(tmp)/'municipios.csv'
        with path.open('w',newline='',encoding='utf-8') as out:
            writer=csv.DictWriter(out,fieldnames=['codigo_ibge','uf','nome']);writer.writeheader();writer.writerows(rows)
        result=import_ibge_municipios(path)
    if cache_file:
        dest=pathlib.Path(cache_file);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
    return result

def _interpolate(points, fraction):
    lengths=[haversine(*a,*b) for a,b in zip(points,points[1:])]
    total=sum(lengths)
    if total<=0:raise ValueError('polilinha degenerada')
    target=total*fraction
    for i,d in enumerate(lengths):
        if target<=d or i==len(lengths)-1:
            t=0 if d==0 else min(1,max(0,target/d))
            return (points[i][0]+t*(points[i+1][0]-points[i][0]),points[i][1]+t*(points[i+1][1]-points[i][1]))
        target-=d
    raise AssertionError('interpolacao fora do dominio')

def resolve_road_km(max_items=10000):
    result={'avaliados':0,'candidatos':0,'ambiguos':0,'sem_referencia':0}
    with Session.begin() as s:
        p=T['ponto_fiscalizacao'];segments=T['geo_trecho_calibrado'];
        points=s.execute(select(p).where(p.c.posicao_id.is_(None),p.c.via_id.is_not(None),p.c.km.is_not(None)).limit(max_items)).mappings().all()
        for point in points:
            result['avaliados']+=1
            sections=s.execute(select(segments).where(segments.c.via_id==point['via_id'],segments.c.km_inicio<=point['km'],segments.c.km_fim>=point['km'])).mappings().all()
            if len(sections)!=1:
                result['ambiguos' if sections else 'sem_referencia']+=1
                continue
            r=sections[0];v=T['geo_trecho_vertice']
            shape=[(float(x['latitude']),float(x['longitude'])) for x in s.execute(select(v).where(v.c.trecho_id==r['id']).order_by(v.c.ordem)).mappings()]
            f=float((point['km']-r['km_inicio'])/(r['km_fim']-r['km_inicio']))
            if not 0<=f<=1:continue
            lat,lon=_interpolate(shape,f)
            _,created=add_candidate(s,point_id=point['id'],lat=lat,lon=lon,method='km_calibrado',source_id=r['fonte_geo_id'],
                proof=f"Referência KM oficial {r['referencia']}; via_id={r['via_id']}; km={point['km']}; KM ajustado por geometria, não coordenada instrumental",
                score=0.75,precision=None,external_id=f"trecho-{r['id']}",detail={'km':float(point['km']),'segmento_id':r['id']})
            result['candidatos']+=int(created)
    return result

def import_cnefe(path,municipality_id=None,max_rows=5000000):
    """Lê CSV oficial CNEFE e SALVA SOMENTE ENDEREÇOS que casem exatamente com
    endereços cadastrados dos pontos, sem carregar milhões de domicílios no DB.
    Não inventar coordenada de radar em esquina/sem numero.
    """
    result={'linhas':0,'conferidos':0,'candidatos':0,'ambiguos':0,'erros':0}
    with Session.begin() as s:
        p=T['ponto_fiscalizacao'];a=T['endereco'];mun=T['municipio']
        targets=s.execute(select(p.c.id,a.c.logradouro,a.c.numero,p.c.municipio_id,mun.c.uf_sigla)
           .select_from(p.join(a,p.c.endereco_id==a.c.id).outerjoin(mun,p.c.municipio_id==mun.c.codigo_ibge))
           .where(p.c.posicao_id.is_(None),a.c.logradouro.is_not(None),a.c.numero.is_not(None))).all()
        targets_map=defaultdict(list)
        for pid,logradouro,num,m_id,uf in targets:
            if m_id and num and logradouro:targets_map[(m_id,norm(logradouro),norm(num))].append(pid)
        if not targets_map:return result
        sid=get_source(s,'IBGE_CNEFE_2022','oficial','https://www.ibge.gov.br/estatisticas/sociais/populacao/38734-cadastro-nacional-de-enderecos-para-finsestatisticos.html')
        matched=defaultdict(list)
        for row in _open_csv_rows(path):
            result['linhas']+=1
            if result['linhas']>max_rows:raise ValueError('limite de registros CNEFE excedido; execute arquivos municipais menores')
            city=getv(row,'COD_MUNICIPIO','COD_MUN')
            if municipality_id and city!=municipality_id:continue
            street=getv(row,'NOM_SEGLOGR','NOM_LOGRADOURO','logradouro')
            prefix=' '.join(filter(None,[getv(row,'NOM_TIPO_SEGLOGR'),getv(row,'NOM_TITULO_SEGLOGR')]))
            num=getv(row,'NUM_ENDERECO','numero')
            aliases=[norm(street),norm(f'{prefix} {street}')]
            ids=set()
            for akey in aliases:ids.update(targets_map.get((city,akey,norm(num)),[]))
            if not ids:continue
            lat=number(getv(row,'LATITUDE'));lon=number(getv(row,'LONGITUDE'),False)
            if lat is None or lon is None:result['erros']+=1;continue
            geonivel=getv(row,'NV_GEO_COORD')
            result['conferidos']+=1
            for pid in ids:matched[pid].append((lat,lon,geonivel,getv(row,'COD_UNICO_ENDERECO')))
        for pid,found in matched.items():
            # Multiendereços ou proximidade de número igual em bairro distinto? Não promover.
            unique={ (round(lat,6),round(lon,6)) for lat,lon,_,_ in found}
            if len(unique)!=1:result['ambiguos']+=1;continue
            lat,lon,level,external=found[0]
            _,added=add_candidate(s,point_id=pid,lat=lat,lon=lon,method='cnefe_endereco',source_id=sid,
               proof=f'IBGE CNEFE endereco coincidente por COD_MUNICIPIO, logradouro e numero; nivel_geo={level}. A posicao E DO ENDERECO, nao do instrumento.',
               score=.65,precision=None,external_id=external,
               detail={'nivel_geocodificacao':level,'endereco_ibge':external,'coincidencias':len(found)})
            result['candidatos']+=int(added)
    return result

def _iter_osm_geojson(path):
    # Apenas extrato filtrado de radares, não o PBF nacional inteiro.
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if data.get('type')!='FeatureCollection':raise ValueError('Esperado GeoJSON FeatureCollection')
    for feature in data.get('features',[]):
        if feature.get('geometry',{}).get('type')!='Point':continue
        properties=feature.get('properties') or {}
        tags=properties.get('tags') if isinstance(properties.get('tags'),dict) else properties
        if tags.get('highway')!='speed_camera' and not (tags.get('type')=='enforcement' and tags.get('enforcement') in ('maxspeed','average_speed')):
            continue
        coords=feature['geometry'].get('coordinates',[])
        if len(coords)<2:continue
        lon=number(coords[0],False);lat=number(coords[1])
        if lat is None or lon is None:continue
        osm_id=str(feature.get('id') or tags.get('osm_id') or '')
        yield osm_id,lat,lon,tags

def import_osm_geojson(path,radius_m=1000,max_items=500000):
    """Cria CANDIDATOS OSM SOMENTE para pontos já aproximados por fonte oficial.
    Não cria radares novos nem chama OSM de fonte oficial.
    """
    if not 10<=radius_m<=5000:raise ValueError('raio permitido 10..5000 m')
    data=list(_iter_osm_geojson(path))
    if len(data)>max_items:raise ValueError('GeoJSON ultrapassa limite')
    result={'pontos_osm':len(data),'alvos_com_ancora':0,'candidatos':0,'rejeitados_distancia':0}
    # Grade para não comparar cada POI do país com todos os pontos existentes.
    cell=.02
    grid=defaultdict(list)
    for entry in data:grid[(math.floor(entry[1]/cell),math.floor(entry[2]/cell))].append(entry)
    with Session.begin() as s:
        sid=get_source(s,'OPENSTREETMAP_CANDIDATO','comunitaria','https://www.openstreetmap.org/')
        c=T['geo_candidato'];pos=T['posicao_geografica'];p=T['ponto_fiscalizacao']
        anchors=s.execute(select(c.c.ponto_id,pos.c.latitude,pos.c.longitude)
            .select_from(c.join(pos,c.c.posicao_id==pos.c.id))
            .where(c.c.status=='revisar',c.c.ponto_id.is_not(None),c.c.metodo.in_(['km_calibrado','cnefe_endereco']))).all()
        for pid,plat,plon in anchors:
            result['alvos_com_ancora']+=1
            lat=float(plat);lon=float(plon)
            y=math.floor(lat/cell);x=math.floor(lon/cell)
            # 5000m correspondem a ~3 células na latitude brasileira.
            count=math.ceil(radius_m/1800)+1
            for iy in range(y-count,y+count+1):
                for ix in range(x-count,x+count+1):
                    for oid,olat,olon,tags in grid.get((iy,ix),[]):
                        dist=haversine(lat,lon,olat,olon)
                        if dist>radius_m:
                            result['rejeitados_distancia']+=1;continue
                        _,created=add_candidate(s,point_id=pid,lat=olat,lon=olon,method='osm_comunitario',source_id=sid,
                            proof=f'OSM {oid} a {dist:.0f}m de coordenada inferida oficial. SEM identificacao fisica comprovada',
                            score=max(.15,.4*(1-dist/radius_m)),precision=None,external_id=oid,
                            detail={'distancia_ancora_m':round(dist,2),'tags':tags})
                        result['candidatos']+=int(created)
    return result

def consult_osm_online(point_id,radius_m=700,cache_dir=None,request_func=None):
    """Busca no Overpass APENAS apos obter ancora oficial aproximada.

    Respeita cache em disco 24h; nunca altera GPS cadastrado diretamente.
    Função request_func existe para teste offline determinístico.
    """
    import time, urllib.request
    if not 50<=radius_m<=2000:raise ValueError('raio OSM permitido entre 50 e 2000 metros')
    with Session() as s:
        p=s.execute(select(T['ponto_fiscalizacao']).where(T['ponto_fiscalizacao'].c.id==point_id)).mappings().first()
        if p is None:raise ValueError('ponto inexistente')
        if p['posicao_id'] is not None:raise ValueError('ponto ja tem localizacao; consulta OSM desnecessaria')
        c=T['geo_candidato'];pos=T['posicao_geografica']
        bases=s.execute(select(c.c.id,pos.c.latitude,pos.c.longitude).select_from(c.join(pos,c.c.posicao_id==pos.c.id))
            .where(c.c.ponto_id==point_id,c.c.metodo.in_(['km_calibrado','cnefe_endereco']),c.c.status=='revisar')).all()
        if len(bases)!=1:raise ValueError('necessaria exatamente uma ancora derivada oficial para consultar OSM')
        lat=float(bases[0][1]);lon=float(bases[0][2])
    cache=pathlib.Path(cache_dir or './cache/overpass');cache.mkdir(parents=True,exist_ok=True)
    cachefile=cache/f'{point_id}_{radius_m}_{round(lat,5)}_{round(lon,5)}.json'
    if cachefile.exists() and time.time()-cachefile.stat().st_mtime<86400:
        raw=cachefile.read_bytes();from_cache=True
    else:
        ql=f'[out:json][timeout:45];node["highway"="speed_camera"](around:{radius_m},{lat:.7f},{lon:.7f});out body;'
        if request_func is None:
            req=urllib.request.Request('https://overpass-api.de/api/interpreter',data=ql.encode('utf-8'),
                headers={'Content-Type':'application/x-www-form-urlencoded; charset=utf-8','User-Agent':'RadarBrasil-georesolver/1.4 (+https://www.openstreetmap.org/copyright)'},method='POST')
            with urllib.request.urlopen(req,timeout=60) as resp:
                if resp.status!=200:raise ValueError(f'Overpass HTTP {resp.status}')
                raw=resp.read(5_000_001)
                if len(raw)>5_000_000:raise ValueError('resposta OSM muito grande')
        else:raw=request_func(ql)
        # Não armazenar payload de erro/HTML como se fosse snapshot Overpass válido.
        parsed=json.loads(raw)
        if not isinstance(parsed.get('elements'),list):raise ValueError('resposta OSM invalida')
        temp=cachefile.with_suffix('.tmp');temp.write_bytes(raw);os.replace(temp,cachefile)
        from_cache=False
    elements=json.loads(raw).get('elements')
    if not isinstance(elements,list):raise ValueError('resposta OSM invalida')
    created=0
    with Session.begin() as s:
        sid=get_source(s,'OPENSTREETMAP_CANDIDATO','comunitaria','https://www.openstreetmap.org/')
        for el in elements:
            if el.get('type')!='node' or (el.get('tags') or {}).get('highway')!='speed_camera':continue
            alat=number(el.get('lat'));alon=number(el.get('lon'),False)
            if alat is None or alon is None or haversine(lat,lon,alat,alon)>radius_m:continue
            distance=haversine(lat,lon,alat,alon)
            _,fresh=add_candidate(s,point_id=point_id,lat=alat,lon=alon,method='osm_comunitario',source_id=sid,
                proof=f'Overpass OSM node {el.get("id")} a {distance:.1f}m de ancora oficial inferida; NAO e prova de identidade do equipamento',
                score=max(.15,.4*(1-distance/radius_m)),external_id=f'node/{el.get("id")}',
                detail={'tags':el.get('tags',{}),'distancia_ancora_m':round(distance,1)})
            created+=int(fresh)
    return {'ponto_id':point_id,'candidatos_novos':created,'consultados':len(elements),'cache':from_cache}

def import_ibge_municipios(path):
    """Importa a tabela pública oficial de códigos municipais IBGE (CSV local).
    Campos: codigo_ibge,uf,nome; permite casar endereço do CNEFE com registros.
    """
    result={'lidas':0,'criadas':0,'atualizadas':0,'ignoradas':0}
    with Session.begin() as s:
        for r in _open_csv_rows(path):
            result['lidas']+=1
            ibge=getv(r,'codigo_ibge','codigo_municipio','cod_municipio','id')
            name=getv(r,'nome','municipio','nome_municipio')
            uf=getv(r,'uf','sigla_uf','estado')
            if not ibge or not re.fullmatch(r'\d{7}',ibge) or not name or not uf or len(uf)!=2:
                result['ignoradas']+=1;continue
            uf=uf.upper()
            if ibge[:2] not in UF_IBGE or UF_IBGE[ibge[:2]]!=uf:
                result['ignoradas']+=1;continue
            t=T['municipio'];old=s.execute(select(t).where(t.c.codigo_ibge==ibge)).mappings().first()
            if old:
                if norm(old['nome'])!=norm(name) or old['uf_sigla']!=uf:
                    s.execute(t.update().where(t.c.codigo_ibge==ibge).values(nome=name,uf_sigla=uf))
                    result['atualizadas']+=1
            else:
                row_id(s,'municipio',codigo_ibge=ibge,uf_sigla=uf,nome=name)
                result['criadas']+=1
    return result

def preparar_pontos_antigos(max_items=10000):
    """Migração não destrutiva: recupera LOCALVERIFICACAO em registros já importados,
    mesmo que o importador antigo não tivesse criado ponto para o instrumento.
    """
    from .ingest import find_road
    from .normalization import normalize_record
    result={'equipamentos_conferidos':0,'pontos_preparados':0,'sem_referencia':0,'moveis_pulados':0}
    with Session.begin() as s:
        v=T['vinculo_registro_equipamento'];rf=T['registro_fonte'];eq=T['equipamento'];inst=T['instalacao']
        rows=s.execute(select(eq.c.id,eq.c.tipo_radar_id).where(~select(inst.c.id).where(inst.c.equipamento_id==eq.c.id).exists()).limit(max_items)).all()
        for eqid,radar_type in rows:
            result['equipamentos_conferidos']+=1
            if radar_type in (get_code(s,'tipo_radar','movel'),get_code(s,'tipo_radar','portatil')):
                result['moveis_pulados']+=1;continue
            evid=s.execute(select(rf.c.id,rf.c.payload_original).select_from(v.join(rf,rf.c.id==v.c.registro_id)).where(v.c.equipamento_id==eqid)).all()
            unique=set();matches=[]
            for rid,payload in evid:
                try:record=json.loads(payload)
                except (TypeError,ValueError):continue
                n=normalize_record(record,'INMETRO_IMPORT')
                via=n.get('road');km=n.get('km')
                if via and km is not None:
                    identity=(via,str(km))
                    if identity not in unique:
                        unique.add(identity);matches.append((rid,via,km))
            if len(matches)!=1:
                result['sem_referencia']+=1;continue
            rid,via,km=matches[0]
            viaid=find_road(s,via)
            if viaid is None:continue
            pid=row_id(s,'ponto_fiscalizacao',via_id=viaid,km=km,
                situacao_operacional_id=get_code(s,'situacao_operacional','desconhecido'))
            row_id(s,'instalacao',ponto_id=pid,equipamento_id=eqid)
            if not s.execute(select(T['vinculo_registro_ponto'].c.registro_id).where(T['vinculo_registro_ponto'].c.registro_id==rid,T['vinculo_registro_ponto'].c.ponto_id==pid)).first():
                row_id(s,'vinculo_registro_ponto',registro_id=rid,ponto_id=pid,confianca=Decimal('.75'))
            result['pontos_preparados']+=1
    return result

def resolver_por_serie(max_items=10000):
    """Usa serie idêntica em órgãos oficiais como CANDIDATO, NÃO publicação.
    Requer coincidência de contexto rodoviário ou município e rejeita origens OSM.
    """
    result={'avaliados':0,'candidatos':0,'ambiguos':0,'sem_correspondencia':0}
    with Session.begin() as s:
        eq=T['equipamento'];inst=T['instalacao'];p=T['ponto_fiscalizacao'];pos=T['posicao_geografica']
        unlocated=s.execute(select(eq.c.id,eq.c.numero_serie).where(eq.c.numero_serie.is_not(None)).limit(max_items)).all()
        sid=get_source(s,'CRUZAMENTO_SERIE_CADASTROS_OFICIAIS','oficial','')
        all_equips=s.execute(select(eq.c.id,eq.c.numero_serie)).all()
        by_serial=defaultdict(list)
        for eid,series in all_equips:
            if series:by_serial[norm(series)].append(eid)
        for eid,series in unlocated:
            result['avaliados']+=1
            visits=s.execute(select(p.c.id,p.c.via_id,p.c.km,p.c.municipio_id,p.c.posicao_id)
                .select_from(inst.join(p,inst.c.ponto_id==p.c.id)).where(inst.c.equipamento_id==eid)).all()
            if visits and all(x[4] is not None for x in visits):continue
            alternatives=[other for other in by_serial[norm(series)] if other!=eid]
            if not alternatives:result['sem_correspondencia']+=1;continue
            positions=[]
            for other in alternatives:
                hits=s.execute(select(p.c.id,p.c.via_id,p.c.km,p.c.municipio_id,pos.c.latitude,pos.c.longitude,pos.c.qualidade_posicao_id)
                    .select_from(inst.join(p,inst.c.ponto_id==p.c.id).join(pos,p.c.posicao_id==pos.c.id)).where(inst.c.equipamento_id==other)).all()
                for hit in hits:
                    if hit[-1] not in (get_code(s,'qualidade_posicao','oficial'),get_code(s,'qualidade_posicao','oficial_imprecisa')):continue
                    if visits and not any((loc[1] is not None and loc[1]==hit[1] and loc[2] is not None and hit[2] is not None and abs(float(loc[2]-hit[2]))<=.1)
                        or (loc[3] is not None and loc[3]==hit[3]) for loc in visits):continue
                    positions.append((hit,other))
            xy={(round(float(h[4]),5),round(float(h[5]),5)) for h,_ in positions}
            if len(xy)!=1:
                result['ambiguos' if positions else 'sem_correspondencia']+=1;continue
            h,other=positions[0]
            targets=[x[0] for x in visits if x[4] is None]
            if not targets:targets=[None]
            for pid in targets:
                _,new=add_candidate(s,point_id=pid,equip_id=eid if pid is None else None,lat=h[4],lon=h[5],
                    method='serie_cruzada',source_id=sid,
                    proof=f'Serie {series} corresponde ao equipamento {other} com ponto oficial {h[0]}; verificar modelo e historico de troca de equipamento',
                    score=.86,precision=None,external_id=f'{eid}_{other}_{h[0]}')
                result['candidatos']+=int(new)
    return result

def _record_unlocated(s,eqid):
    eq=s.execute(select(T['equipamento']).where(T['equipamento'].c.id==eqid)).mappings().first()
    if not eq:return None
    ins=T['instalacao'];p=T['ponto_fiscalizacao'];pos=T['posicao_geografica']
    locations=s.execute(select(ins.c.ponto_id,pos.c.latitude,pos.c.longitude,pos.c.qualidade_posicao_id,pos.c.metodo_obtencao)
        .select_from(ins.join(p,ins.c.ponto_id==p.c.id).outerjoin(pos,p.c.posicao_id==pos.c.id)).where(ins.c.equipamento_id==eqid)).all()
    quality=T['qualidade_posicao'];quality_map={r[0]:r[1] for r in s.execute(select(quality.c.id,quality.c.codigo)).all()}
    official_coords=[{'ponto_id':pid,'latitude':float(lat),'longitude':float(lon),
        'qualidade':quality_map.get(qid),'metodo':method} for pid,lat,lon,qid,method in locations if lat is not None]
    c=T['geo_candidato'];pv=T['posicao_geografica'];gs=T['geo_fonte']
    ca=s.execute(select(c.c.id,c.c.metodo,c.c.status,c.c.score,c.c.evidencia,pv.c.latitude,pv.c.longitude,gs.c.nome,gs.c.tipo,gs.c.url)
        .select_from(c.join(pv,c.c.posicao_id==pv.c.id).join(gs,c.c.fonte_geo_id==gs.c.id))
        .where(or_(c.c.equipamento_id==eqid,c.c.ponto_id.in_([r[0] for r in locations] or [-1])))).all()
    possible=[{'id':r[0],'metodo':r[1],'status':r[2],'score':float(r[3]),'evidencia':r[4],
        'latitude':float(r[5]),'longitude':float(r[6]),'fonte':r[7],'natureza_fonte':r[8],'url_fonte':r[9]} for r in ca]
    return {'equipamento_id':eqid,'numero_serie':eq['numero_serie'],'status':'localizado' if official_coords else 'pendente' if possible else 'sem_coordenada',
        'locais':official_coords,'candidatos':possible,'aviso':'localizado significa coordenada cadastrada (pode ser inferida), nao GPS com exatidao de 10 metros'}

def locations_report(limit=100000,offset=0):
    with Session() as s:
        ids=s.execute(select(T['equipamento'].c.id).order_by(T['equipamento'].c.id).limit(limit).offset(offset)).scalars().all()
        rows=[_record_unlocated(s,eid) for eid in ids]
        statuses={x:sum(row['status']==x for row in rows) for x in ('localizado','pendente','sem_coordenada')}
        return {'total_no_lote':len(rows),'offset':offset,'sumario':statuses,'equipamentos':rows}

def main(argv=None):
    p=argparse.ArgumentParser(description='Resolvedor geografico RadarBrasil; sem PostGIS')
    sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('importar-trechos');a.add_argument('--arquivo',required=True);a.add_argument('--fonte',required=True);a.add_argument('--url',required=True)
    a=sub.add_parser('resolver-km');a.add_argument('--limite',type=int,default=10000)
    a=sub.add_parser('resolver-tudo');a.add_argument('--limite',type=int,default=10000);a.add_argument('--cnefe');a.add_argument('--osm');a.add_argument('--raio-osm',type=int,default=1000)
    a=sub.add_parser('importar-municipios');a.add_argument('--arquivo',required=True)
    a=sub.add_parser('baixar-municipios-ibge');a.add_argument('--cache')
    a=sub.add_parser('importar-geojson-oficial');a.add_argument('--arquivo',required=True);a.add_argument('--fonte',required=True);a.add_argument('--url',required=True)
    a=sub.add_parser('preparar-antigos');a.add_argument('--limite',type=int,default=10000)
    a=sub.add_parser('resolver-series');a.add_argument('--limite',type=int,default=10000)
    a=sub.add_parser('importar-cnefe');a.add_argument('--arquivo',required=True);a.add_argument('--municipio-ibge')
    a=sub.add_parser('importar-osm');a.add_argument('--arquivo',required=True);a.add_argument('--raio',type=int,default=1000)
    a=sub.add_parser('consultar-osm');a.add_argument('--ponto-id',type=int,required=True);a.add_argument('--raio',type=int,default=700);a.add_argument('--cache')
    a=sub.add_parser('aprovar');a.add_argument('--candidato',type=int,required=True);a.add_argument('--autor',required=True);a.add_argument('--justificativa',required=True)
    a=sub.add_parser('rejeitar');a.add_argument('--candidato',type=int,required=True);a.add_argument('--autor',required=True);a.add_argument('--justificativa',required=True)
    a=sub.add_parser('relatorio');a.add_argument('--arquivo');a.add_argument('--formato',choices=['json','csv'],default='json');a.add_argument('--limite',type=int,default=100000);a.add_argument('--offset',type=int,default=0)
    a=p.parse_args(argv)
    try:
        init_db()
        with Session.begin() as s:seed_domains(s)
        if a.cmd=='importar-trechos':out=import_road_segments(a.arquivo,a.fonte,a.url)
        elif a.cmd=='resolver-km':out=resolve_road_km(a.limite)
        elif a.cmd=='resolver-tudo':
            out={'preparacao':preparar_pontos_antigos(a.limite),'series':resolver_por_serie(a.limite),'quilometragem':resolve_road_km(a.limite)}
            if a.cnefe:out['enderecos']=import_cnefe(a.cnefe)
            if a.osm:out['osm_candidatos']=import_osm_geojson(a.osm,a.raio_osm)
            out['pendencias']=locations_report(a.limite)['sumario']
        elif a.cmd=='importar-municipios':out=import_ibge_municipios(a.arquivo)
        elif a.cmd=='baixar-municipios-ibge':out=importar_municipios_api_ibge(a.cache)
        elif a.cmd=='importar-geojson-oficial':out=import_road_geojson(a.arquivo,a.fonte,a.url)
        elif a.cmd=='preparar-antigos':out=preparar_pontos_antigos(a.limite)
        elif a.cmd=='resolver-series':out=resolver_por_serie(a.limite)
        elif a.cmd=='importar-cnefe':out=import_cnefe(a.arquivo,a.municipio_ibge)
        elif a.cmd=='importar-osm':out=import_osm_geojson(a.arquivo,a.raio)
        elif a.cmd=='consultar-osm':out=consult_osm_online(a.ponto_id,a.raio,a.cache)
        elif a.cmd in ('aprovar','rejeitar'):
            with Session.begin() as s:
                out=promote_candidate(s,a.candidato,a.autor,a.justificativa) if a.cmd=='aprovar' else (reject_candidate(s,a.candidato,a.autor,a.justificativa) or {'status':'rejeitado'})
        else:
            out=locations_report(a.limite,a.offset)
            if a.arquivo:
                path=pathlib.Path(a.arquivo)
                if a.formato=='json':path.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
                else:
                    with path.open('w',newline='',encoding='utf-8') as f:
                        writer=csv.writer(f,delimiter=';');writer.writerow(['equipamento_id','numero_serie','status','latitude','longitude','quantidade_candidatos'])
                        for r in out['equipamentos']:
                            for loc in (r['locais'] or [None]):
                                writer.writerow([r['equipamento_id'],r['numero_serie'],r['status'],loc['latitude'] if loc else '',loc['longitude'] if loc else '',len(r['candidatos'])])
        print(json.dumps(out if a.cmd!='relatorio' else {'total_no_lote':out['total_no_lote'],'sumario':out['sumario'],'arquivo':a.arquivo},ensure_ascii=False,indent=2,default=str))
        return 0
    except Exception as exc:
        LOG.exception('geolocalizacao falhou')
        print(json.dumps({'sucesso':False,'erro':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
if __name__=='__main__':sys.exit(main())
