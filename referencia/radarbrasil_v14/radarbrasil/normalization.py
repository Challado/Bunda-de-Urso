"""Normalização defensiva; nunca preenche campos sem evidência."""
import re, unicodedata, math, json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

def tidy(s):
    if s is None:return None
    t=str(s).strip().replace('\u00a0',' ')
    return t or None

def key(s):
    s=tidy(s) or ''
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii').lower())

def decimal(value, lo=None,hi=None):
    if value is None or str(value).strip()=='':return None
    if isinstance(value,str):
        s=value.strip().replace(' ','')
        if s.count(',')==1 and s.count('.')>0:
            if s.rfind(',')>s.rfind('.'):s=s.replace('.','').replace(',','.')
            else:s=s.replace(',','')
        else:s=s.replace(',','.')
    else:s=str(value)
    try:
        val=Decimal(s)
        if not val.is_finite():return None
        if lo is not None and val<lo:return None
        if hi is not None and val>hi:return None
        return val
    except (InvalidOperation,ValueError):return None

def speed_kmh(value):
    """Limite em km/h, somente número ou número com unidade explicitamente km/h.

    Rejeita mph, listas, percentuais e textos ambiguos; 0/desconhecido -> None.
    Não deve ser chamado em velocidades observadas no tráfego como limite legal.
    """
    if value is None or str(value).strip() == '':
        return None
    if isinstance(value, str):
        token = value.strip().replace('\u00a0', ' ')
        m = re.fullmatch(r'(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:km\s*/\s*h|kmh)?', token, re.I)
        if not m:
            return None
        value = m.group(1)
    v=decimal(value,1,350)
    return v

def coord(x,latitude=True):
    val=decimal(x,-90 if latitude else -180,90 if latitude else 180)
    if val is None:return None
    return val

def get(row,*keys):
    if not isinstance(row,dict):return None
    normal={key(k):v for k,v in row.items()}
    for k in keys:
        v=normal.get(key(k))
        if v is not None and tidy(v) is not None:return v
    return None

def classify_radar(s):
    k=key(s)
    if any(w in k for w in ('portatil','portateis')):return 'portatil'
    if 'movel' in k:return 'movel'
    if 'fixo' in k:return 'fixo'
    return 'desconhecido'

def classify_function(s):
    k=key(s)
    if 'misto' in k or 'ambos' in k:return 'misto'
    if 'redutor' in k or 'rev'==k:return 'redutor'
    if 'controlador' in k or k in ('cev','cem'):return 'controlador'
    return 'desconhecido'

def classify_mode(s):
    k=key(s)
    if not k:return 'desconhecida'
    if 'pontual' in k:return 'pontual'
    if 'itinerante' in k:return 'itinerante'
    if 'permanente' in k:return 'permanente'
    if 'trecho' in k:return 'por_trecho'
    return 'desconhecida'

def official_datetime(s):
    """Não supor fuso: instante sem offset permanece sem interpretação temporal."""
    if not s:return None
    try:
        parsed=datetime.fromisoformat(str(s).strip().replace('Z','+00:00'))
    except (ValueError,TypeError):return None
    if parsed.tzinfo is None:return None
    return parsed.astimezone(timezone.utc)

def class_status(s):
    k=key(s)
    if any(w in k for w in ('inativ','desativ','desligad','retirad')):return 'inativo'
    if 'manutencao' in k:return 'manutencao'
    if any(w in k for w in ('ativo','operacional','emoperacao')):return 'ativo'
    return 'desconhecido'

def class_direction(s):
    k=key(s)
    if 'decrescente' in k:return 'decrescente'
    if 'crescente' in k:return 'crescente'
    if 'ambos' in k or 'bidirecional' in k:return 'ambos'
    return None

def road(s):
    t=tidy(s)
    if not t:return None
    k=re.sub(r'\s+','',t.upper()).replace('/','-')
    m=re.search(r'\b(BR|PR|SP|MG|RJ|RS|SC|BA|GO|DF|MT|MS|ES|PE|CE|PA|AM|AC|AL|AP|MA|PB|PI|RN|RO|RR|SE|TO)[\s\-]*(\d{2,4})',k)
    return f'{m.group(1)}-{m.group(2)}' if m else t[:120].upper()

def normalize_record(row,source):
    """O mapeamento não transforma título de coluna desconhecida em localização."""
    lat=coord(get(row,'latitude','lat','coord_latitude','latitude geográfica','latitude_geo'))
    lon=coord(get(row,'longitude','lon','lng','coord_longitude','longitude geográfica','longitude_geo'),False)
    if (lat is None)!=(lon is None):lat=lon=None
    if lat==0 and lon==0:lat=lon=None
    # NÃO confundir `velocidade` da base ANTT de TRÁFEGO com limite regulamentado.
    # Nesse dataset ela representa a velocidade observada dos veículos, e não o limite.
    speed_keys = {
        'speed_light': ('velocidade_leves','velocidade_leve','velocidade_regulamentada_veiculos_leves','velocidade leves','velocidadeveiculosleves','velocidade de leves','velocidade leves km/h','velocidade_regulamentada_leves','vmaxleves'),
        'speed_heavy': ('velocidade_pesados','velocidade_pesado','velocidade_regulamentada_veiculos_pesados','velocidade pesados','velocidadeveiculospesados','velocidade de pesados','velocidade pesados km/h','velocidade_regulamentada_pesados','vmaxpesados'),
        'speed_general': ('velocidade regulamentada','velocidade_regulamentada','limite_velocidade','velocidade_maxima','maxspeed','limite velocidade','velocidade regulamentar'),
        'speed_nominal': ('velocidade nominal','velocidadenominal','velocidade_nominal'),
    }
    if source == 'OSM_COMPLEMENTAR':
        speed_keys['speed_general'] += ('velocidade',)
    invalid_speeds=[]
    values={}
    for field, names in speed_keys.items():
        original=get(row,*names)
        values[field]=speed_kmh(original)
        if original is not None and values[field] is None:
            invalid_speeds.append({'campo':field,'valor':str(original)[:120], 'motivo':'Velocidade inválida ou unidade não comprovada em km/h'})
    local=get(row,'local verificacao','localverificacao','local de instalacao','local_instalacao','localização')
    via_origem=get(row,'rodovia','br','via','rodovia_snv')
    if not via_origem and local:
        m=re.search(r'\b(BR|GO|PR|SP|MG|BA|RS|SC|RJ|MT|MS|DF|PE|CE|PA|AM|AC|AL|AP|MA|PB|PI|RN|RO|RR|SE|TO)[\s\-/]*(\d{2,4})\b',str(local),flags=re.I)
        if m:via_origem=f'{m.group(1)}-{m.group(2)}'
    km_origem=get(row,'km','km_m','km_+_m','quilometro','quilômetro','km_snv','quilometragem')
    if km_origem is None and local:
        m=re.search(r'\bKM\s*[:\-]?\s*(\d{1,5}(?:[,\.]\d{1,3})?)\b',str(local),flags=re.I)
        if m:km_origem=m.group(1)
    r={'source':source,'original':row,
        'identifier':tidy(get(row,'identificador','id','codigo equipamento','código do equipamento','codigo radar','número do equipamento','numero equipamento','codigo_equipamento')),
        'serial':tidy(get(row,'numero serie','nº de série','n de serie','numero_serie','serial','serie')),
        'latitude':lat,'longitude':lon,
        'original_radar_type':tidy(get(row,'tipo medidor','tipo de radar','tipo_de_radar','tipo', 'TipoMedidor')),
        'fabricante':tidy(get(row,'fabricante','marca')),
        'modelo':tidy(get(row,'modelo','modelo equipamento','modelo do equipamento')),
        'uf':tidy(get(row,'uf','sigla uf','siglauf','estado uf')),
        'municipio':tidy(get(row,'municipio','município','cidade')),
        'road':road(via_origem) if via_origem else None,
        'km':decimal(km_origem,0,999999),
        'direction':class_direction(get(row,'sentido','sentido_rodovia','sentido da rodovia','sentido de fiscalizacao','sentidofiscalizacao')),
        'direction_original':tidy(get(row,'sentido','sentido de fiscalizacao')),
        'lane_count':decimal(get(row,'quantidade de faixas','quantidade de faixas de trafego controladas','numero faixas','número de faixas','faixas controladas','qtd faixas'),0,99),
        'speed_light':values['speed_light'],
        'speed_heavy':values['speed_heavy'],
        'speed_general':values['speed_general'],
        'speed_nominal':values['speed_nominal'],
        'invalid_speeds':invalid_speeds,
        'lane_number':decimal(get(row,'numero_faixa','numero faixa','faixa','faixa da fiscalizacao'),1,99),
        'radar_type':classify_radar(get(row,'tipo de radar','tipo_de_radar','tipo','tipo equipamento','tipomedidor') or ('portatil' if source=='PRF_PORTATEIS' else None)),
        'function':classify_function(get(row,'tipo_de_radar','tipo de radar','tipo equipamento','tipo')),
        'type_pista':tidy(get(row,'tipo_de_pista','tipo de pista')),
        'year_pnv':decimal(get(row,'ano_do_pnv_snv','ano do pnv snv'),1900,2100),
        'date_inactive':tidy(get(row,'data_da_inativacao','data de inativacao')), 
        'original_type':tidy(get(row,'tipo de radar','tipo_de_radar','tipo','tipo equipamento','tipomedidor')),
        'status':class_status(get(row,'situacao','situação','status','status equipamento','situacao_radar')),
        'original_status':tidy(get(row,'situacao','situação','status')),
        'endereco_logradouro':tidy(get(row,'logradouro','rua','avenida','logradouro_instalacao')),
        'endereco_numero':tidy(get(row,'numero_endereco','numero do endereco','numero_end','numero_predial')),
        'endereco_bairro':tidy(get(row,'bairro','bairro_instalacao')),
        'municipio_ibge':tidy(get(row,'codigo_ibge','codigo_municipio','cod_municipio')),
        'operator':tidy(get(row,'concessionaria','concessionária','operador')),
        'tech_study':tidy(get(row,'estudo tecnico','estudo técnico','codigo_et')),
        'certificate_valid':tidy(get(row,'validade certificado','validade do certificado','datavalidade')),
        'certificate_url':tidy(get(row,'link certificado','url certificado','certificado_url')),
        'tech_study_url':tidy(get(row,'url estudo tecnico','url estudo técnico','link do estudo tecnico')),
        'inicio_pontual':tidy(get(row,'inicio_fiscalizacao','datahora_inicio','inicio_operacao_pontual')),
        'fim_pontual':tidy(get(row,'fim_fiscalizacao','datahora_fim','fim_operacao_pontual')),
        'modalidade_original':tidy(get(row,'modalidade de fiscalizacao','modalidade_fiscalizacao'))}
    if r['uf']:
        u=r['uf'].upper().strip();r['uf']=u if len(u)==2 else None
    r['lane_count']=int(r['lane_count']) if r['lane_count'] is not None else None
    return r

def haversine(lat1,lon1,lat2,lon2):
    a,b,c,d=map(math.radians,(float(lat1),float(lon1),float(lat2),float(lon2)))
    z=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 2*6371008.8*math.asin(min(1,math.sqrt(z)))

def bbox(lat,lon,meters):
    """Conservador, lida com polos e cruzamento de ±180°."""
    radius=6371008.8
    phi=math.radians(lat);delta=meters/radius+1e-9
    latmin=max(-90,math.degrees(phi-delta));latmax=min(90,math.degrees(phi+delta))
    if latmin<=-90 or latmax>=90:return latmin,latmax,-180,180,False
    span=math.degrees(math.asin(min(1,math.sin(delta)/max(1e-12,math.cos(phi)))))
    a=(lon-span+180)%360-180;b=(lon+span+180)%360-180
    return latmin,latmax,a,b,a>b
