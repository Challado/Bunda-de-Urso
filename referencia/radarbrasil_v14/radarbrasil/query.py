"""Consultas apenas no banco local, sem funções geográficas proprietárias."""
import base64,json,hashlib,math
from datetime import datetime,timezone
from sqlalchemy import select,and_,or_,func
from .schema import Session,TABLES as T
from .normalization import bbox,haversine,normalize_record
from . import settings

def iso(d):
    if d is None:return None
    if isinstance(d,datetime) and d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
    return d.isoformat()

def named(s,tab,id):
    if id is None:return None
    t=T[tab];r=s.execute(select(t.c.codigo).where(t.c.id==id)).scalar_one_or_none()
    return r

def raw_source(s,reg_id):
    if reg_id is None:return None
    rf=T['registro_fonte'];art=T['artefato_coleta'];res=T['recurso_fonte'];fon=T['fonte']
    x=s.execute(select(fon.c.nome,res.c.url_recurso,art.c.baixado_em,rf.c.identificador_na_fonte).select_from(rf.join(art,rf.c.artefato_id==art.c.id).join(res,art.c.recurso_id==res.c.id).join(fon,res.c.fonte_id==fon.c.id)).where(rf.c.id==reg_id)).first()
    return {'fonte':x[0],'url':x[1],'coletado_em':iso(x[2]),'identificador':x[3]} if x else None

def equipments_for(s,pid):
    ii=T['instalacao'];ee=T['equipamento']
    rows=s.execute(select(ii,ee).select_from(ii.join(ee,ii.c.equipamento_id==ee.c.id)).where(ii.c.ponto_id==pid)).mappings()
    result=[]
    for a in rows:
        eid=a['id_1'] if 'id_1' in a else a['equipamento_id']
        # mapeamento select(T1,T2) pode colidir em id. Usar lookup explícito.
        e=s.execute(select(ee).where(ee.c.id==a['equipamento_id'])).mappings().one()
        checks=[]
        for v in s.execute(select(T['verificacao_metrologica']).where(T['verificacao_metrologica'].c.equipamento_id==e['id']).order_by(T['verificacao_metrologica'].c.data_verificacao.desc())).mappings():
            checks.append({'id':v['id'],'tipo':named(s,'tipo_verificacao',v['tipo_verificacao_id']),'resultado':named(s,'resultado_verificacao',v['resultado_id']),
                'data':iso(v['data_verificacao']),'validade_ate':iso(v['validade_ate']),'numero_certificado':v['numero_certificado'],'norma':v['norma_aplicada'],
                'fonte':raw_source(s,v['registro_fonte_id'])})
        ids=T['identificador_equipamento'];ext=T['identificador_externo'];kind=T['tipo_identificador']
        names=s.execute(select(ext.c.valor,kind.c.codigo).select_from(ids.join(ext,ids.c.identificador_id==ext.c.id).join(kind,ext.c.tipo_identificador_id==kind.c.id)).where(ids.c.equipamento_id==e['id'])).all()
        nominal=[]
        seen_nominal=set()
        for m in s.execute(select(T['faixa_medicao_equipamento']).where(T['faixa_medicao_equipamento'].c.equipamento_id==e['id']).order_by(T['faixa_medicao_equipamento'].c.id.desc())).mappings():
            item=(m['numero_faixa'],m['sentido_id'],m['velocidade_nominal_kmh'])
            if item in seen_nominal:continue
            seen_nominal.add(item)
            nominal.append({'numero_faixa':m['numero_faixa'],'sentido':named(s,'sentido',m['sentido_id']),
                'velocidade_nominal_kmh':float(m['velocidade_nominal_kmh']) if m['velocidade_nominal_kmh'] is not None else None,
                'origem':raw_source(s,m['registro_fonte_id'])})
        result.append({'id':e['id'],'numero_serie':e['numero_serie'],'tipo_radar':named(s,'tipo_radar',e['tipo_radar_id']),
          'modelo_id':e['modelo_id'],'ano_fabricacao':e['ano_fabricacao'],'identificadores':[{'tipo':k,'valor':v} for v,k in names],
          'instalacao':{'id':a['id'],'inicio_em':iso(a['inicio_em']),'fim_em':iso(a['fim_em']),'inicio_autuacao':iso(a['data_inicio_autuacao']),'inicio_educativo':iso(a['data_inicio_educativo'])},
          'verificacoes_metrologicas':checks,'faixas_medicao_nominal':nominal,'funcao_equipamento':named(s,'funcao_equipamento',a['funcao_equipamento_id']), 'observacoes':e['observacoes']})
    return result

def get_point(s,pid,distance=None):
    pt=s.execute(select(T['ponto_fiscalizacao']).where(T['ponto_fiscalizacao'].c.id==pid)).mappings().first()
    if pt is None:return None
    pos=s.execute(select(T['posicao_geografica']).where(T['posicao_geografica'].c.id==pt['posicao_id'])).mappings().first() if pt['posicao_id'] else None
    via=s.execute(select(T['via']).where(T['via'].c.id==pt['via_id'])).mappings().first() if pt['via_id'] else None
    municipio=s.execute(select(T['municipio']).where(T['municipio'].c.codigo_ibge==pt['municipio_id'])).mappings().first() if pt['municipio_id'] else None
    addr=s.execute(select(T['endereco']).where(T['endereco'].c.id==pt['endereco_id'])).mappings().first() if pt['endereco_id'] else None
    equip=equipments_for(s,pid)
    lanes=[]
    for v in s.execute(select(T['faixa_fiscalizacao']).where(T['faixa_fiscalizacao'].c.ponto_id==pid)).mappings():
        lanes.append({'id':v['id'],'numero':v['numero_faixa'],'sentido':named(s,'sentido',v['sentido_id']), 'sentido_original':v['sentido_original']})
    speeds=[]
    for v in s.execute(select(T['limite_velocidade']).where(or_(T['limite_velocidade'].c.ponto_id==pid,T['limite_velocidade'].c.faixa_id.in_([x['id'] for x in lanes] or [-1])))).mappings():
        speeds.append({'categoria':named(s,'categoria_veiculo',v['categoria_veiculo_id']),'velocidade_kmh':float(v['velocidade_kmh']),'faixa_id':v['faixa_id'],'inicio':iso(v['vigencia_inicio']),'fim':iso(v['vigencia_fim']), 'fonte':raw_source(s,v['registro_fonte_id'])})
    # Resolver limites sem substituir valores divergentes por um palpite.
    # Chave = (categoria do veículo, faixa), o campo 'limites_velocidade' conserva
    # todas as evidências; a visão resolvida torna conflitos explícitos.
    by_scope={}
    for speed in speeds:
        scope=(speed['categoria'],speed['faixa_id'])
        by_scope.setdefault(scope,[]).append(speed)
    resolved=[];speed_conflicts=[]
    for (category,lane),observations in sorted(by_scope.items(), key=lambda kv:(kv[0][0] or '',kv[0][1] or -1)):
        unique=sorted({obs['velocidade_kmh'] for obs in observations})
        if len(unique)>1:
            speed_conflicts.append({'campo':'limite_velocidade','categoria':category,'faixa_id':lane,
                'valores_kmh':unique,'fontes':[x['fonte'] for x in observations]})
        resolved.append({'categoria':category,'faixa_id':lane,
            'velocidade_kmh':unique[0] if len(unique)==1 else None,
            'estado':'conflitante' if len(unique)>1 else 'sem_conflito',
            'valores_publicados_kmh':unique})
    top_speeds={f'velocidade_{kind}_kmh':next((v['velocidade_kmh'] for v in resolved if v['categoria']==kind and v['faixa_id'] is None),None) for kind in ('leves','pesados','geral')}
    regimes=[]
    for v in s.execute(select(T['regime_fiscalizacao']).where(T['regime_fiscalizacao'].c.ponto_id==pid)).mappings():
        regimes.append({'modalidade':named(s,'modalidade_fiscalizacao',v['modalidade_id']),'tipo_medicao':named(s,'tipo_medicao',v['tipo_medicao_id']),'inicio':iso(v['inicio_em']),'fim':iso(v['fim_em']),'fonte':raw_source(s,v['fonte_registro_id'])})
    operacoes=[]
    for v in s.execute(select(T['operacao_fiscalizacao']).where(T['operacao_fiscalizacao'].c.ponto_id==pid)).mappings():
        operacoes.append({'id':v['id'],'modalidade':named(s,'modalidade_fiscalizacao',v['modalidade_id']),'situacao':named(s,'situacao_operacao',v['situacao_operacao_id']),'inicio':iso(v['inicio_em']),'fim':iso(v['fim_em']),'fuso_original':v['fuso_original'],'descricao':v['descricao'],'fonte':raw_source(s,v['registro_fonte_id'])})
    docs=[]
    for d in s.execute(select(T['documento']).select_from(T['documento'].join(T['documento_ponto'],T['documento'].c.id==T['documento_ponto'].c.documento_id)).where(T['documento_ponto'].c.ponto_id==pid)).mappings():
        docs.append({'id':d['id'],'tipo':named(s,'tipo_documento',d['tipo_documento_id']),'url':d['url'],'codigo':d['codigo_documento'],'titulo':d['titulo']})
    orgs=[]
    po=T['ponto_organizacao'];orga=T['organizacao'];role=T['papel_organizacao']
    for o in s.execute(select(orga.c.id,orga.c.nome,role.c.codigo,po.c.inicio_em,po.c.fim_em).select_from(
        po.join(orga,po.c.organizacao_id==orga.c.id).join(role,po.c.papel_id==role.c.id)).where(po.c.ponto_id==pid)).all():
        orgs.append({'id':o[0],'nome':o[1],'papel':o[2],'inicio_em':iso(o[3]),'fim_em':iso(o[4])})
    records=T['vinculo_registro_ponto'];ref=T['registro_fonte'];sources=[];seen=set()
    for rec in s.execute(select(records.c.registro_id).where(records.c.ponto_id==pid)).scalars():
        f=raw_source(s,rec)
        if f and (f['fonte'],f['identificador']) not in seen:
            f['registro_origem_id']=rec;f['dados_originais']=json.loads(s.execute(select(ref.c.payload_original).where(ref.c.id==rec)).scalar_one());sources.append(f);seen.add((f['fonte'],f['identificador']))
    # Texto administrativo sem código IBGE permanece na fonte original, não inventar IBGE.
    original_locations=[]
    for reg_id in s.execute(select(records.c.registro_id).where(records.c.ponto_id==pid)).scalars():
        payload=s.execute(select(ref.c.payload_original).where(ref.c.id==reg_id)).scalar_one_or_none()
        if payload:
            try:normalized=normalize_record(json.loads(payload),'')
            except (ValueError,TypeError):continue
            original_locations.append(normalized)
    uf_original=next((x['uf'] for x in original_locations if x.get('uf')),None)
    municipio_original=next((x['municipio'] for x in original_locations if x.get('municipio')),None)
    kinds=sorted({e['tipo_radar'] for e in equip if e['tipo_radar']})
    modalities=[r['modalidade'] for r in regimes if r['modalidade']!='desconhecida']
    pontual=True if 'pontual' in modalities else False if modalities else None
    # Evidencias candidatas nunca substituem silenciosamente coordenadas oficiais.
    geo=T['geo_candidato'];gps=T['posicao_geografica'];geos=[]
    for g in s.execute(select(geo.c.id,geo.c.metodo,geo.c.status,geo.c.score,geo.c.evidencia,gps.c.latitude,gps.c.longitude)
        .select_from(geo.join(gps,geo.c.posicao_id==gps.c.id)).where(geo.c.ponto_id==pid)).all():
        geos.append({'id':g[0],'metodo':g[1],'status':g[2],'score':float(g[3]),'evidencia':g[4],
                     'latitude':float(g[5]),'longitude':float(g[6])})
    return {'id':pid,'tipo_registro':'ponto_fiscalizacao','situacao_operacional':named(s,'situacao_operacional',pt['situacao_operacional_id']) or 'desconhecido',
      'latitude':float(pos['latitude']) if pos else None,'longitude':float(pos['longitude']) if pos else None,'distancia_metros':round(distance,2) if distance is not None else None,
      'precisao_metros':float(pos['precisao_metros']) if pos and pos['precisao_metros'] is not None else None,'uf':municipio['uf_sigla'] if municipio else uf_original,
      'municipio':municipio['nome'] if municipio else municipio_original,'codigo_ibge':municipio['codigo_ibge'] if municipio else None,
      'via_codigo':via['codigo'] if via else None,'km':float(pt['km']) if pt['km'] is not None else None,'tipo_pista':pt['tipo_pista'],
      'tipos_radar_presentes':kinds,'fiscalizacao_pontual':pontual,'regimes':regimes,'faixas':lanes,
      **top_speeds,'velocidades_resolvidas':resolved,'limites_velocidade':speeds,'equipamentos':equip,'operacoes':operacoes,
      'documentos':docs,'fontes':sources,'conflitos':speed_conflicts,'confianca':'conflitante' if speed_conflicts else 'nao_aferida','atualizacao':{'ultima_confirmacao':max((x['coletado_em'] or '' for x in sources),default=None)},
      'endereco':dict(addr) if addr else None,'organizacoes':orgs,
      'localizacao_metadados':{'qualidade':named(s,'qualidade_posicao',pos['qualidade_posicao_id']) if pos else None,'metodo':pos['metodo_obtencao'] if pos else None,'fonte':raw_source(s,pos['registro_fonte_id']) if pos else None,'candidatos':geos,'coordinate_of_equipment_exact':False if pos and named(s,'qualidade_posicao',pos['qualidade_posicao_id']) in ('inferida','estimada','desconhecida') else None},
      'observacoes':pt['observacoes'],'proveniencia_campos':[],'estado_temporal':{},'quantidade_faixas_declarada':pt['quantidade_faixas_declarada']}

def query_points(lat,lon,radius,filters,limit=100,cursor=None):
    with Session() as s:
        total_all=s.execute(select(func.count()).select_from(T['ponto_fiscalizacao'])).scalar_one()
        if total_all==0:raise RuntimeError('BASE_INDISPONIVEL: nenhum ponto fiscalizado foi importado/validado')
        pos=T['posicao_geografica'];pt=T['ponto_fiscalizacao'];q=select(pt.c.id,pos.c.latitude,pos.c.longitude).select_from(pt.join(pos,pt.c.posicao_id==pos.c.id))
        a,b,c,d,wrap=bbox(lat,lon,radius)
        q=q.where(pos.c.latitude.between(a,b))
        q=q.where(or_(pos.c.longitude>=c,pos.c.longitude<=d) if wrap else pos.c.longitude.between(c,d))
        if not filters.get('incluir_inativos',False):
            st=T['situacao_operacional'];q=q.outerjoin(st,pt.c.situacao_operacional_id==st.c.id).where(or_(st.c.codigo.is_(None),st.c.codigo!='inativo'))
        if filters.get('tipo_radar'):
            e=T['equipamento'];it=T['instalacao'];rad=T['tipo_radar']
            q=q.where(pt.c.id.in_(select(it.c.ponto_id).select_from(it.join(e,it.c.equipamento_id==e.c.id).join(rad,e.c.tipo_radar_id==rad.c.id)).where(rad.c.codigo==filters['tipo_radar'])))
        if filters.get('municipio_ibge'):q=q.where(pt.c.municipio_id==filters['municipio_ibge'])
        if filters.get('rodovia'):q=q.where(pt.c.via_id.in_(select(T['via'].c.id).where(T['via'].c.codigo==filters['rodovia'])))
        coords=s.execute(q).all()
        # Comparar raio em distância NÃO arredondada; ordenar pelo mesmo valor
        # arredondado que será retornado/codificado no cursor para evitar saltos.
        exact=[(haversine(lat,lon,x[1],x[2]),x[0]) for x in coords]
        nearby=sorted(((round(dist,2),pid) for dist,pid in exact if dist<=radius+1e-7),
                      key=lambda x:(x[0],x[1]))
        # Filtro avançado necessita analisar a entidade; nunca limitar antes da aplicação.
        details=[]
        for dist,id in nearby:
            obj=get_point(s,id,dist)
            if filters.get('em'):
                at=filters['em']
                valid=False
                for op in obj['operacoes']:
                    if op['situacao'] in ('cancelada','desconhecida'):continue
                    if not op['inicio'] or not op['fim']:continue
                    from datetime import datetime,timezone
                    lo=datetime.fromisoformat(op['inicio']).replace(tzinfo=timezone.utc) if not datetime.fromisoformat(op['inicio']).tzinfo else datetime.fromisoformat(op['inicio'])
                    hi=datetime.fromisoformat(op['fim']).replace(tzinfo=timezone.utc) if not datetime.fromisoformat(op['fim']).tzinfo else datetime.fromisoformat(op['fim'])
                    if lo<=at<=hi:valid=True;break
                if not valid:continue
            if filters.get('uf') and obj['uf']!=filters['uf']:continue
            if filters.get('sentido') and filters['sentido'] not in [x['sentido'] for x in obj['faixas']]:continue
            if filters.get('modalidade') and filters['modalidade'] not in [x['modalidade'] for x in obj['regimes']]:continue
            if filters.get('fiscalizacao_pontual') is not None and obj['fiscalizacao_pontual'] is not filters['fiscalizacao_pontual']:continue
            if not filters.get('incluir_incertos',True) and not obj['fontes']:continue
            details.append(obj)
        qhash=hashlib.sha256(json.dumps([lat,lon,radius,filters],sort_keys=True,default=str).encode()).hexdigest()[:16]
        if cursor:
            try:
                parsed=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if parsed['h']!=qhash:raise ValueError('cursor de consulta diferente')
                details=[v for v in details if (v['distancia_metros'],v['id'])>(parsed['distance'],parsed['id'])]
            except Exception as e:raise ValueError('cursor inválido ou incompatível') from e
        total=len(details)
        selected=details[:limit]
        next_cursor=None
        if len(details)>limit:
            last=selected[-1];next_cursor=base64.urlsafe_b64encode(json.dumps({'h':qhash,'distance':last['distancia_metros'],'id':last['id']}).encode()).decode().rstrip('=')
        return {'itens':selected,'total':total,'retornados':len(selected),'proximo_cursor':next_cursor,'base_pontos':total_all}

def get_equipment(eid):
    with Session() as s:
        r=s.execute(select(T['equipamento']).where(T['equipamento'].c.id==eid)).mappings().first()
        if not r:return None
        nominal=[]
        for m in s.execute(select(T['faixa_medicao_equipamento']).where(T['faixa_medicao_equipamento'].c.equipamento_id==eid)).mappings():
            nominal.append({'numero_faixa':m['numero_faixa'],'sentido':named(s,'sentido',m['sentido_id']),
                'velocidade_nominal_kmh':float(m['velocidade_nominal_kmh']) if m['velocidade_nominal_kmh'] is not None else None,
                'origem':raw_source(s,m['registro_fonte_id'])})
        v=T['vinculo_registro_equipamento'];rf=T['registro_fonte']
        evidencias=[]
        for rid in s.execute(select(v.c.registro_id).where(v.c.equipamento_id==eid)).scalars():
            original=s.execute(select(rf.c.payload_original).where(rf.c.id==rid)).scalar_one_or_none()
            evidencias.append({'fonte':raw_source(s,rid),'dados_originais':json.loads(original) if original else None})
        checks=[]
        for m in s.execute(select(T['verificacao_metrologica']).where(T['verificacao_metrologica'].c.equipamento_id==eid)
                .order_by(T['verificacao_metrologica'].c.data_verificacao.desc())).mappings():
            checks.append({'numero_certificado':m['numero_certificado'],'data_verificacao':iso(m['data_verificacao']),
                'validade_ate':iso(m['validade_ate']),'tipo':named(s,'tipo_verificacao',m['tipo_verificacao_id']),
                'resultado':named(s,'resultado_verificacao',m['resultado_id']),'fonte':raw_source(s,m['registro_fonte_id'])})
        return {'id':r['id'],'tipo_radar':named(s,'tipo_radar',r['tipo_radar_id']),'numero_serie':r['numero_serie'],
                'modelo_id':r['modelo_id'],'ano_fabricacao':r['ano_fabricacao'],'faixas_medicao_nominal':nominal,
                'verificacoes_metrologicas':checks,'evidencias':evidencias,'observacoes':r['observacoes']}

def list_ops():
    with Session() as s:
        return [{**dict(x),'modalidade':named(s,'modalidade_fiscalizacao',x['modalidade_id'])} for x in s.execute(select(T['operacao_fiscalizacao']).limit(1000)).mappings()]

def list_stretches():
    with Session() as s:
        return [{**dict(x)} for x in s.execute(select(T['trecho_elegivel']).limit(1000)).mappings()]

def list_traffic(limit=100,point_id=None):
    """Observações de tráfego agregadas, jamais limites legais."""
    with Session() as sess:
        t=T['observacao_trafego']
        q=select(t).order_by(t.c.id.desc()).limit(limit)
        if point_id is not None:q=q.where(t.c.ponto_id==point_id)
        records=[]
        for r in sess.execute(q).mappings():
            records.append({'id':r['id'],'ponto_id':r['ponto_id'],'equipamento_id':r['equipamento_id'],
              'faixa_id':r['faixa_id'],'categoria':named(sess,'categoria_veiculo',r['categoria_veiculo_id']),
              'sentido':named(sess,'sentido',r['sentido_id']),'data':iso(r['data_observacao']),
              'instante':iso(r['instante_observacao']),
              'velocidade_observada_kmh':float(r['velocidade_kmh']) if r['velocidade_kmh'] is not None else None,
              'velocidade_original':r['velocidade_publicada'],'volume_total':r['volume_total'],
              'fonte':raw_source(sess,r['registro_fonte_id'])})
        return records

def search_points(filters,limit=100):
    """Busca cadastral por UF, rodovia, município IBGE ou tipo; sem raio."""
    with Session() as sess:
        pt=T['ponto_fiscalizacao']
        q=select(pt.c.id).order_by(pt.c.id).limit(limit*20)
        if filters.get('rodovia'):
            q=q.where(pt.c.via_id.in_(select(T['via'].c.id).where(T['via'].c.codigo==filters['rodovia'])))
        if filters.get('municipio_ibge'):
            q=q.where(pt.c.municipio_id==filters['municipio_ibge'])
        result=[]
        for pid in sess.execute(q).scalars():
            obj=get_point(sess,pid)
            if filters.get('uf') and obj['uf']!=filters['uf']:continue
            if filters.get('tipo_radar') and filters['tipo_radar'] not in obj['tipos_radar_presentes']:continue
            if filters.get('modalidade') and filters['modalidade'] not in [r['modalidade'] for r in obj['regimes']]:continue
            if not filters.get('incluir_inativos') and obj['situacao_operacional']=='inativo':continue
            result.append(obj)
            if len(result)>=limit:break
        return result
