"""ETL transacional, conservação de evidências e deduplicação conservadora."""
import json, hashlib, logging
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, and_, or_
from .schema import TABLES as T,get_code
from .normalization import normalize_record,haversine,key,classify_mode,official_datetime
log=logging.getLogger(__name__)

def utcnow():return datetime.now(timezone.utc)
def asjson(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':'))
def sha(obj):return hashlib.sha256(asjson(obj).encode()).hexdigest()
def row1(s,t,**kwargs):return s.execute(select(T[t]).filter_by(**kwargs)).mappings().first()
def new(s,t,**kwargs):return s.execute(T[t].insert().values(**kwargs)).inserted_primary_key[0]

def get_org(s,name,kind='orgao_publico'):
    old=row1(s,'organizacao',nome=name)
    return old['id'] if old else new(s,'organizacao',nome=name,tipo_organizacao_id=get_code(s,'tipo_organizacao',kind))

def register_resource(s,config,url,fmt):
    org=get_org(s,config.get('organization',config['code']))
    source=row1(s,'fonte',nome=config['code'])
    if source:sourceid=source['id']
    else:
        natureza='comunitaria' if config['code'].startswith('OSM') else 'oficial'
        natureid=row1(s,'natureza_fonte',codigo=natureza)['id']
        sourceid=new(s,'fonte',organizacao_id=org,natureza_id=natureid,nome=config['code'],url_institucional=config['url'],esfera=config.get('esfera','desconhecida'),situacao='habilitada' if config.get('enabled') else 'desabilitada',observacoes=config.get('reason'))
    resource=row1(s,'recurso_fonte',fonte_id=sourceid,url_recurso=url)
    if resource:return sourceid,resource['id']
    return sourceid,new(s,'recurso_fonte',fonte_id=sourceid,nome=config.get('name',config['code']),url_recurso=url,formato_origem=fmt.upper(),periodicidade_segundos=config.get('interval_seconds',3600),ativo=True,status_integracao='nao_validado')

def find_identified(s,source_id,value,entity='equipamento'):
    if not value:return None
    t=T['identificador_externo'];rel=T['identificador_'+entity]
    q=(select(rel.c[f'{entity}_id']).select_from(rel.join(t,rel.c.identificador_id==t.c.id))
       .where(t.c.fonte_id==source_id,t.c.valor_normalizado==key(value)))
    return s.execute(q).scalar_one_or_none()

def link_ident(s,sourceid,value,entity,canonical,kind='id_orgao'):
    if not value:return
    typ=get_code(s,'tipo_identificador',kind);n=key(value)
    if not n:return
    t=T['identificador_externo'];ex=s.execute(select(t.c.id).where(t.c.fonte_id==sourceid,t.c.tipo_identificador_id==typ,t.c.valor_normalizado==n)).scalar_one_or_none()
    if ex is None:ex=new(s,'identificador_externo',fonte_id=sourceid,tipo_identificador_id=typ,valor=str(value),valor_normalizado=n)
    tname='identificador_'+entity; col=entity+'_id'
    if not row1(s,tname,identificador_id=ex,**{col:canonical}):new(s,tname,identificador_id=ex,**{col:canonical})

def find_equipment(s,source_id,r):
    # por ID de fonte existente antes de heurísticas
    equip=find_identified(s,source_id,r['identifier'],'equipamento')
    if equip:return equip
    ser=r['serial']
    if not ser:return None
    candidates=s.execute(select(T['equipamento'].c.id,T['equipamento'].c.numero_serie).where(T['equipamento'].c.numero_serie.is_not(None))).all()
    found=[id for id,val in candidates if key(val)==key(ser)]
    # Inmetro/PRF sem modelo: mesmo número de série pode se repetir entre fabricantes.
    # Só unificar automaticamente se mesma origem ou já há evidência do vínculo com esta fonte.
    safe=[]
    for eid in found:
        t=T['identificador_equipamento'];ex=T['identificador_externo']
        n=s.execute(select(t.c.equipamento_id).select_from(t.join(ex,t.c.identificador_id==ex.c.id)).where(t.c.equipamento_id==eid,ex.c.fonte_id==source_id).limit(1)).first()
        if n:safe.append(eid)
    return safe[0] if len(safe)==1 else None

def find_road(s,roadcode):
    if not roadcode:return None
    kind='federal' if roadcode.startswith('BR-') else 'estadual' if '-' in roadcode else 'desconhecida'
    tid=get_code(s,'tipo_via',kind);existing=row1(s,'via',tipo_via_id=tid,codigo=roadcode)
    return existing['id'] if existing else new(s,'via',tipo_via_id=tid,codigo=roadcode)

def find_point(s,sourceid,r,roadid):
    old=find_identified(s,sourceid,r['identifier'],'ponto')
    if old:return old
    if r['latitude'] is None:return None
    # A proximidade sozinha NUNCA funde: exige mesmíssima rodovia + km semelhante
    if roadid is None or r['km'] is None:return None
    lat=float(r['latitude']);lon=float(r['longitude'])
    pos=T['posicao_geografica'];pt=T['ponto_fiscalizacao']
    q=(select(pt.c.id,pos.c.latitude,pos.c.longitude,pt.c.km).select_from(pt.join(pos,pt.c.posicao_id==pos.c.id))
       .where(pt.c.via_id==roadid,pt.c.km.between(r['km']-Decimal('.020'),r['km']+Decimal('.020')),
             pos.c.latitude.between(lat-.001,lat+.001),pos.c.longitude.between(lon-.001,lon+.001)))
    hits=[x[0] for x in s.execute(q) if haversine(lat,lon,x[1],x[2])<=25]
    return hits[0] if len(hits)==1 else None

def attach_evidence(s,art_id,row,index,sourcecode,sourceid):
    h=sha(row)
    old=row1(s,'registro_fonte',artefato_id=art_id,numero_ordem=index)
    if old:return old['id'],None,False
    rid=new(s,'registro_fonte',artefato_id=art_id,numero_ordem=index,identificador_na_fonte=str(row.get('identificador') or row.get('Identificador') or '') or None,payload_original=asjson(row),hash_registro=h,status_validacao='pendente')
    r=normalize_record(row,sourcecode)
    for invalid in r.get('invalid_speeds',[]):
        new(s,'erro_validacao',registro_id=rid,campo_origem=invalid['campo'],
            codigo_erro='VELOCIDADE_INVALIDA',descricao=f"{invalid['motivo']}: {invalid['valor']}",
            severidade='warning',registrado_em=utcnow())
    if sourcecode=='OSM_COMPLEMENTAR':r['status']='desconhecido'
    if not r['identifier'] and not r['serial'] and r['latitude'] is None and not (r['road'] and r['km'] is not None):
        s.execute(T['registro_fonte'].update().where(T['registro_fonte'].c.id==rid).values(status_validacao='sem_identidade'))
        return rid,None,False
    equip=find_equipment(s,sourceid,r)
    if equip is None and (r['identifier'] or r['serial']):
        equip=new(s,'equipamento',tipo_radar_id=get_code(s,'tipo_radar',r['radar_type']),numero_serie=r['serial'],observacoes=None)
    # Mesmo número de série em fontes ou equipamentos diferentes é CANDIDATO,
    # não autorização para fundir automaticamente sem fabricante/modelo.
    if equip and r['serial']:
        matches=s.execute(select(T['equipamento'].c.id,T['equipamento'].c.numero_serie).where(T['equipamento'].c.numero_serie.is_not(None))).all()
        for other_id,other_serial in matches:
            if other_id==equip or key(other_serial)!=key(r['serial']):continue
            other_records=s.execute(select(T['vinculo_registro_equipamento'].c.registro_id).where(T['vinculo_registro_equipamento'].c.equipamento_id==other_id)).scalars().all()
            rule=s.execute(select(T['regra_deduplicacao'].c.id).order_by(T['regra_deduplicacao'].c.id.desc()).limit(1)).scalar_one_or_none()
            for oid in other_records[:20]:
                a,b=sorted((oid,rid))
                if rule is not None and not row1(s,'candidato_duplicidade',registro_a_id=a,registro_b_id=b,regra_id=rule):
                    new(s,'candidato_duplicidade',registro_a_id=a,registro_b_id=b,regra_id=rule,
                        score=Decimal('.8500'),estado='revisar',evidencias_resumo='Número de série normalizado coincidente; conferir fabricante/modelo e histórico',gerado_em=utcnow())
    if equip:
        link_ident(s,sourceid,r['identifier'],'equipamento',equip)
        if r['serial']:link_ident(s,sourceid,r['serial'],'equipamento',equip,'serie')
        if not row1(s,'vinculo_registro_equipamento',registro_id=rid,equipamento_id=equip):
            new(s,'vinculo_registro_equipamento',registro_id=rid,equipamento_id=equip,confianca=Decimal('0.9000'))
    roadid=find_road(s,r['road'])
    point=find_point(s,sourceid,r,roadid)
    if point is None and (r['latitude'] is not None or (roadid is not None and r['km'] is not None)):
        loc=None
        if r['latitude'] is not None:
            loc=new(s,'posicao_geografica',latitude=r['latitude'],longitude=r['longitude'],qualidade_posicao_id=get_code(s,'qualidade_posicao','oficial' if sourcecode!='OSM_COMPLEMENTAR' else 'desconhecida'),metodo_obtencao='dado_publicado',registro_fonte_id=rid)
        point=new(s,'ponto_fiscalizacao',posicao_id=loc,via_id=roadid,km=r['km'],tipo_pista=r['type_pista'],
                  situacao_operacional_id=get_code(s,'situacao_operacional',r['status']),quantidade_faixas_declarada=r['lane_count'])
    elif point is not None and r['latitude'] is not None:
        ex=row1(s,'ponto_fiscalizacao',id=point)
        if ex['posicao_id'] is None:
            loc=new(s,'posicao_geografica',latitude=r['latitude'],longitude=r['longitude'],qualidade_posicao_id=get_code(s,'qualidade_posicao','oficial'),registro_fonte_id=rid)
            s.execute(T['ponto_fiscalizacao'].update().where(T['ponto_fiscalizacao'].c.id==point).values(posicao_id=loc))
    if point:
        # Concessionária é uma entidade própria, não texto duplicado em pontos.
        if r.get('operator'):
            orgid=get_org(s,r['operator'],'concessionaria')
            roleid=get_code(s,'papel_organizacao','concessionaria')
            if not row1(s,'ponto_organizacao',ponto_id=point,organizacao_id=orgid,papel_id=roleid):
                new(s,'ponto_organizacao',ponto_id=point,organizacao_id=orgid,papel_id=roleid)
        # Documento técnico cadastrado em entidade e relação N:N.
        if r.get('tech_study') or r.get('tech_study_url'):
            docid=None
            if r.get('tech_study_url'):
                docid=s.execute(select(T['documento'].c.id).where(T['documento'].c.url==r['tech_study_url'])).scalar_one_or_none()
            if docid is None and r.get('tech_study'):
                docid=s.execute(select(T['documento'].c.id).where(T['documento'].c.codigo_documento==r['tech_study'])).scalar_one_or_none()
            if docid is None:
                docid=new(s,'documento',tipo_documento_id=get_code(s,'tipo_documento','estudo_tecnico'),
                    codigo_documento=r.get('tech_study'),url=r.get('tech_study_url'))
            if not row1(s,'documento_ponto',documento_id=docid,ponto_id=point):
                new(s,'documento_ponto',documento_id=docid,ponto_id=point)
        link_ident(s,sourceid,r['identifier'],'ponto',point)
        if not row1(s,'vinculo_registro_ponto',registro_id=rid,ponto_id=point):new(s,'vinculo_registro_ponto',registro_id=rid,ponto_id=point,confianca=Decimal('0.8000'))
        if equip and not row1(s,'instalacao',ponto_id=point,equipamento_id=equip):
            new(s,'instalacao',ponto_id=point,equipamento_id=equip,funcao_equipamento_id=get_code(s,'funcao_equipamento',r['function']))
        lane_id=None
        if r['direction'] or r['lane_number'] is not None:
            direction=get_code(s,'sentido',r['direction']) if r['direction'] else None
            num=int(r['lane_number']) if r['lane_number'] is not None else None
            oldlane=row1(s,'faixa_fiscalizacao',ponto_id=point,sentido_id=direction,numero_faixa=num)
            lane_id=oldlane['id'] if oldlane else new(s,'faixa_fiscalizacao',ponto_id=point,sentido_id=direction,numero_faixa=num,sentido_original=r['direction_original'])
        for categoria,field in [('leves','speed_light'),('pesados','speed_heavy'),('geral','speed_general')]:
            speed=r[field]
            if speed is None:continue
            cat=get_code(s,'categoria_veiculo',categoria)
            # Limite específico por faixa só é atribuído se a fonte declarar o NÚMERO da faixa.
            # Com sentido apenas, o limite continua sendo geral para o ponto.
            speed_lane=lane_id if r['lane_number'] is not None else None
            conditions=[T['limite_velocidade'].c.categoria_veiculo_id==cat,T['limite_velocidade'].c.velocidade_kmh==speed]
            conditions += [T['limite_velocidade'].c.faixa_id==speed_lane] if speed_lane else [T['limite_velocidade'].c.ponto_id==point]
            exists=s.execute(select(T['limite_velocidade'].c.id).where(*conditions).limit(1)).first()
            if not exists:new(s,'limite_velocidade',**({'faixa_id':speed_lane} if speed_lane else {'ponto_id':point}),categoria_veiculo_id=cat,velocidade_kmh=speed,registro_fonte_id=rid)
        mode=classify_mode(r.get('modalidade_original'))
        existing_reg=s.execute(select(T['regime_fiscalizacao'].c.id).where(
            T['regime_fiscalizacao'].c.ponto_id==point,
            T['regime_fiscalizacao'].c.modalidade_id==get_code(s,'modalidade_fiscalizacao',mode))).scalar_one_or_none()
        if existing_reg is None:
            new(s,'regime_fiscalizacao',ponto_id=point,modalidade_id=get_code(s,'modalidade_fiscalizacao',mode),fonte_registro_id=rid)
        begin=official_datetime(r.get('inicio_pontual'))
        end=official_datetime(r.get('fim_pontual'))
        if begin and end and end>=begin and mode in ('pontual','itinerante'):
            # Apenas criar OPERAÇÃO datada quando a fonte de origem fornece fuso e intervalo.
            exists=s.execute(select(T['operacao_fiscalizacao'].c.id).where(
                T['operacao_fiscalizacao'].c.registro_fonte_id==rid,
                T['operacao_fiscalizacao'].c.inicio_em==begin,
                T['operacao_fiscalizacao'].c.fim_em==end)).scalar_one_or_none()
            if exists is None:
                op=new(s,'operacao_fiscalizacao',modalidade_id=get_code(s,'modalidade_fiscalizacao',mode),
                    situacao_operacao_id=get_code(s,'situacao_operacao','confirmada'),
                    ponto_id=point,inicio_em=begin,fim_em=end,fuso_original=str(r.get('inicio_pontual'))[-6:],registro_fonte_id=rid)
                if equip:new(s,'operacao_equipamento',operacao_id=op,equipamento_id=equip)
        elif r.get('inicio_pontual') or r.get('fim_pontual'):
            new(s,'erro_validacao',registro_id=rid,campo_origem='periodo_fiscalizacao',codigo_erro='PERIODO_NAO_CONFIRMADO',
                descricao='Operacao sem dois instantes ISO8601 com timezone, datas invertidas ou modalidade não pontual/itinerante',
                severidade='warning',registrado_em=utcnow())
    # Configuração nominal de faixa do INMETRO: nunca a usar como limite da via.
    if equip and sourcecode=='INMETRO_IMPORT' and isinstance(row.get('_inmetro'),dict):
        lane=int(r['lane_number']) if r['lane_number'] is not None else None
        dirid=get_code(s,'sentido',r['direction']) if r['direction'] else None
        new(s,'faixa_medicao_equipamento',equipamento_id=equip,registro_fonte_id=rid,
            numero_faixa=lane,sentido_id=dirid,velocidade_nominal_kmh=r['speed_nominal'])
    # Histórico oficial do Inmetro: uma verificação por instrumento e certificado/data,
    # nunca criar uma verificação diferente por cada faixa do mesmo instrumento.
    if equip and isinstance(row.get('_inmetro'),dict):
        from datetime import datetime as _dt
        grp=row['_inmetro']['grupo']
        for h in grp.get('Historico',[]):
            number=h.get('NumeroCertificado')
            try:date=_dt.strptime(h.get('DataLaudo',''),'%d/%m/%Y').date()
            except ValueError:date=None
            try:expiry=_dt.strptime(h.get('DataValidade',''),'%d/%m/%Y').date()
            except ValueError:expiry=None
            if not (number or date):continue
            t=T['verificacao_metrologica']
            old=s.execute(select(t.c.id).where(t.c.equipamento_id==equip,t.c.numero_certificado==number,t.c.data_verificacao==date).limit(1)).first()
            if not old:
                typ='periodica' if 'period' in key(h.get('TipoServico','')) else 'outra'
                result='conforme' if key(h.get('Resultado')) in ('aprovado','conforme') else 'nao_conforme' if key(h.get('Resultado')) in ('reprovado','naoconforme') else 'desconhecido'
                new(s,'verificacao_metrologica',equipamento_id=equip,tipo_verificacao_id=get_code(s,'tipo_verificacao',typ),resultado_id=get_code(s,'resultado_verificacao',result),data_verificacao=date,validade_ate=expiry,numero_certificado=number,registro_fonte_id=rid)
    s.execute(T['registro_fonte'].update().where(T['registro_fonte'].c.id==rid).values(status_validacao='valido'))
    return rid,(point,equip),True

def attach_traffic(s,artifact_id,row,index,sourcecode,sourceid):
    """Observação agregada de tráfego ANTT: JAMAIS cadastra limite legal de velocidade.
    Só liga ao ponto quando o mesmo local (via/km/coord) está previamente cadastrado.
    """
    from .normalization import get,decimal,coord,speed_kmh,official_datetime,class_direction
    from datetime import date
    if row1(s,'registro_fonte',artefato_id=artifact_id,numero_ordem=index):
        return None,None,False
    rid=new(s,'registro_fonte',artefato_id=artifact_id,numero_ordem=index,
        identificador_na_fonte=str(get(row,'identificador') or '') or None,
        payload_original=asjson(row),hash_registro=sha(row),status_validacao='pendente')
    vol=decimal(get(row,'volume_total','volume total','volume'),0,10**12)
    speedoriginal=get(row,'velocidade','velocidade da passagem')
    speed=speed_kmh(speedoriginal)
    when=get(row,'data_da_passagem','data passagem','data_de_passagem')
    when_datetime=official_datetime(when)
    when_date=when_datetime.date() if when_datetime else None
    if when_date is None and when:
        try:when_date=date.fromisoformat(str(when).strip()[:10])
        except ValueError:
            try:when_date=datetime.strptime(str(when).strip()[:10],'%d/%m/%Y').date()
            except ValueError:pass
    if vol is None and speedoriginal is None:
        s.execute(T['registro_fonte'].update().where(T['registro_fonte'].c.id==rid).values(status_validacao='sem_observacao'))
        return rid,None,False
    if vol is not None and vol!=int(vol):
        new(s,'erro_validacao',registro_id=rid,campo_origem='volume_total',codigo_erro='VOLUME_FRACIONARIO',
            descricao='Volume de veículos precisa ser inteiro',severidade='warning',registrado_em=utcnow())
        s.execute(T['registro_fonte'].update().where(T['registro_fonte'].c.id==rid).values(status_validacao='invalido'))
        return rid,None,False
    r=normalize_record(row,sourcecode)
    # Ausência de localização não exclui observação agregada; permanece sem ponto associado.
    point=None;road_id=None;faixa=None
    if r['road'] and r['km'] is not None and r['latitude'] is not None:
        via=row1(s,'via',codigo=r['road']);road_id=via['id'] if via else None
        if road_id:point=find_point(s,sourceid,r,road_id)
    if point:
        lane_num=decimal(get(row,'faixa_da_passagem','faixa da passagem'),1,99)
        if lane_num is not None:
            f=T['faixa_fiscalizacao']
            faixa=s.execute(select(f.c.id).where(f.c.ponto_id==point,f.c.numero_faixa==int(lane_num))).scalar_one_or_none()
    typ=key(get(row,'tipo_de_veiculo','tipo do veículo','tipo veiculo'))
    category='leves' if typ in ('leve','leves') else 'pesados' if typ in ('pesado','pesados') else 'categoria_original'
    dirid=get_code(s,'sentido',r['direction']) if r['direction'] else None
    observation_id=new(s,'observacao_trafego',registro_fonte_id=rid,ponto_id=point,faixa_id=faixa,
        categoria_veiculo_id=get_code(s,'categoria_veiculo',category),sentido_id=dirid,
        data_observacao=when_date,instante_observacao=when_datetime,
        velocidade_publicada=str(speedoriginal) if speedoriginal is not None else None,
        velocidade_kmh=speed,volume_total=int(vol) if vol is not None else None)
    s.execute(T['registro_fonte'].update().where(T['registro_fonte'].c.id==rid).values(status_validacao='valido'))
    return rid,{'observacao_trafego_id':observation_id},True

def ingest_rows(s,resource_id,artifact_id,sourcecode,sourceid,rows,run_id):
    if sourcecode=='INMETRO_IMPORT':
        flattened=[]
        for group in rows:
            faixas=group.get('Faixas') or group.get('faixas') or []
            if not faixas:
                # Metrologia sem faixas publicadas também deve preservar o grupo e histórico.
                single=dict(group)
                single['_inmetro']={'grupo':group,'faixa':{}}
                flattened.append(single)
                continue
            for faixa in faixas:
                v={'numero_serie':faixa.get('NumeroSerie'),'identificador':faixa.get('NumeroInmetro'),
                   'tipo':group.get('TipoMedidor'),'velocidade_nominal':faixa.get('VelocidadeNominal'),
                   'numero_faixa':faixa.get('NumeroFaixa'),
                   'sentido':faixa.get('Sentido'),'municipio':group.get('Municipio'),'uf':group.get('SiglaUf'),
                   '_inmetro':{'grupo':group,'faixa':faixa}}
                flattened.append(v)
        rows=flattened
    if not rows:raise ValueError('Importação sem registros')
    counts={'received':len(rows),'accepted':0,'rejected':0,'created':0}
    for i,row in enumerate(rows):
        try:
            # SAVEPOINT: erro em um registro não invalida a execução inteira
            with s.begin_nested():
                rid,entities,created=(attach_traffic(s,artifact_id,row,i,sourcecode,sourceid)
                    if sourcecode=='ANTT_TRAFEGO' else attach_evidence(s,artifact_id,row,i,sourcecode,sourceid))
            if entities:counts['accepted']+=1
            else:counts['rejected']+=1
            counts['created']+=int(created)
        except Exception as e:
            counts['rejected']+=1
            new(s,'erro_validacao',execucao_id=run_id,codigo_erro='REGISTRO_INVALIDO',descricao=f'linha {i}: {str(e)[:400]}',severidade='warning',registrado_em=utcnow())
            log.warning('Registro rejeitado na origem %s linha %s: %s',sourcecode,i,e)
    # Falha massiva: impedir publicação de snapshot enganoso
    if counts['accepted']==0:raise ValueError('Nenhum registro reconhecido/aceito, atualizacao abortada')
    if counts['rejected']/counts['received']>.50:raise ValueError('Mais de 50% dos registros rejeitados, atualizacao abortada')
    return counts
