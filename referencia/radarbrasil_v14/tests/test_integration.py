import os,sys,subprocess,json,csv,io
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def sandbox(tmp_path):
    env=os.environ.copy();env.update({
      'PYTHONPATH':str(ROOT),
      'RADAR_DATABASE_URL':'sqlite:///'+str(tmp_path/'db.sqlite3'),
      'RADAR_CACHE_DIR':str(tmp_path/'cache'),'RADAR_CONFIG':str(ROOT/'config/sources.json')})
    return tmp_path,env

def cli(env,*args):
    return subprocess.run([sys.executable,'-m','radarbrasil.collector',*args],cwd=ROOT,env=env,text=True,capture_output=True)

def request(env,params,path='/api/v1/radares',post=None):
    e=env.copy();e.update({'PATH_INFO':path,'REQUEST_METHOD':'POST' if post else 'GET','QUERY_STRING':params})
    if post:
        body=json.dumps(post).encode();e.update({'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body))})
    else:body=b''
    proc=subprocess.run([sys.executable,str(ROOT/'web/api.pse')],cwd=ROOT,input=body,env=e,capture_output=True)
    head,body=proc.stdout.split(b'\r\n\r\n',1)
    return head.decode(),body

def sample(sandbox):
    tmp,env=sandbox
    path=tmp/'sample.csv'
    with path.open('w',newline='') as f:
        writer=csv.writer(f,delimiter=';')
        writer.writerow(['Identificador','Numero Serie','Latitude','Longitude','UF','Municipio','Rodovia','KM','Tipo','Sentido','Velocidade Leves','Velocidade Pesados'])
        writer.writerow(['X-001','SER-01','-24.9555','-53.4552','PR','Cascavel','BR-277','120.000','Fixo','Crescente','60','50'])
        writer.writerow(['X-002','SER-02','-24.955501','-53.455199','PR','Cascavel','BR-277','120.000','Fixo','Crescente','60','50'])
        writer.writerow(['X-003','SER-03','-24.9000','-53.4000','PR','Cascavel','BR-277','130.000','Fixo','Decrescente','80','70'])
    r=cli(env,'import-file','--source','ANTT_RADARES','--file',str(path),'--format','csv')
    assert r.returncode==0,(r.stdout,r.stderr)
    return r

def test_schema_and_help(sandbox):
    _,env=sandbox
    assert cli(env,'init').returncode==0
    header,body=request(env,'formato=json',path='/api/v1/ajuda')
    assert '200 OK' in header
    obj=json.loads(body)
    assert len(obj['colunas_txt_dif'])==36
    assert any(i['nome']=='lat' for i in obj['parametros'])

def test_import_dedup_formats(sandbox):
    _,env=sandbox
    sample(sandbox)
    head,body=request(env,'lat=-24.9555&lon=-53.4552&raio=1000')
    assert '200 OK' in head,(head,body)
    result=json.loads(body)
    assert result['resultado']['total']==1
    radar=result['resultado']['radares'][0]
    assert len(radar['equipamentos'])==2
    assert radar['municipio']=='Cascavel'
    assert radar['uf']=='PR'
    assert radar['fiscalizacao_pontual'] is None
    for fmt in ('txt','ndjson','xml','edifact','dif'):
        header,body=request(env,f'lat=-24.9555&lon=-53.4552&raio=100&formato={fmt}')
        assert '200 OK' in header,(fmt,header,body[:200])
        assert body
        if fmt=='txt':
            row=next(csv.reader(io.StringIO(body.decode()),delimiter='|'))
            assert len(row)==36
        elif fmt=='edifact':assert b'UNB+' in body and b'UNZ+' in body and b'GENRAL:D:96A' in body
        elif fmt=='dif':assert b'VECTORS\n0,36' in body and b'EOD' in body
    head,body=request(env,'',post={'lat':-24.9555,'lon':-53.4552,'raio':1000,'formato':'json'})
    assert json.loads(body)['resultado']['total']==1

def test_failure_no_data_not_false_negative(sandbox):
    _,env=sandbox
    assert cli(env,'init').returncode==0
    header,body=request(env,'lat=-24.95&lon=-53.4&raio=100')
    assert '503 Service Unavailable' in header
    assert json.loads(body)['erro']['codigo']=='BASE_INDISPONIVEL'

def test_validation(sandbox):
    _,env=sandbox
    header,body=request(env,'lat=999&lon=1&raio=100')
    assert '422 Unprocessable' in header
    header,body=request(env,'lat=1&lon=2&raio=-10')
    assert '422 Unprocessable' in header
    header,body=request(env,'lat=1&lon=2&formato=txt&delimitador=%0A')
    assert '422 Unprocessable' in header

def test_prf_portable_same_serial(sandbox):
    tmp,env=sandbox
    file=tmp/'prf.html'
    file.write_text('<html><table><tr><th>Identificador</th><th>Série</th></tr><tr><td>REF181</td><td>TC005867</td></tr><tr><td>REF184</td><td>TC005867</td></tr></table></html>')
    result=cli(env,'import-file','--source','PRF_PORTATEIS','--file',str(file),'--format','prf_portateis')
    assert result.returncode==0,(result.stdout,result.stderr)
    status=json.loads(cli(env,'status').stdout)
    assert status['contadores']['equipamento']==1
    assert status['contadores']['ponto_fiscalizacao']==0


def test_speed_normalization_exact_sources():
    from radarbrasil.normalization import normalize_record, speed_kmh
    a=normalize_record({'identificador':'01','velocidade_leve':'110',
       'velocidade_pesado':'90 km/h','velocidade':'135 km/h',
       'km_m':'317,940','latitude':'-24.95','longitude':'-53.45'},'ANTT_RADARES')
    assert float(a['speed_light'])==110
    assert float(a['speed_heavy'])==90
    assert a['speed_general'] is None  # ANTT trafego e limite nao sao sinonimos
    assert float(a['km'])==317.94
    assert speed_kmh('80,5 km/h')==80.5
    assert speed_kmh('55 mph') is None
    assert speed_kmh('80/100') is None
    assert speed_kmh('0') is None


def test_speed_return_all_formats_and_conflicts(sandbox):
    tmp,env=sandbox
    sample(sandbox)
    _,body=request(env,'lat=-24.9555&lon=-53.4552&raio=1000&formato=json')
    r=json.loads(body)['resultado']['radares'][0]
    assert r['velocidade_leves_kmh']==60
    assert r['velocidade_pesados_kmh']==50
    assert r['velocidade_geral_kmh'] is None
    assert not r['conflitos']
    _,raw=request(env,'lat=-24.9555&lon=-53.4552&raio=1000&formato=txt&delimitador=%3B')
    line=next(csv.reader(io.StringIO(raw.decode()),delimiter=';'))
    assert line[-4:-1]==['60.0','50.0','\\N']
    assert json.loads(line[-1])[0]['velocidade_kmh']==60 or len(json.loads(line[-1]))>=2
    # A 2a fonte tem o mesmo ponto e publica valor diferente: nao esconder a divergencia.
    other=tmp/'other.csv'
    other.write_text('Identificador;Latitude;Longitude;Rodovia;KM;Velocidade Leves;Velocidade Pesados\n'
      'Y-901;-24.955500;-53.455200;BR-277;120.000;80;50\n',encoding='utf-8')
    res=cli(env,'import-file','--source','PRF_FIXOS','--file',str(other),'--format','csv')
    assert res.returncode==0,(res.stdout,res.stderr)
    _,body=request(env,'lat=-24.9555&lon=-53.4552&raio=100&formato=json')
    obj=json.loads(body)['resultado']['radares'][0]
    assert obj['velocidade_leves_kmh'] is None
    assert obj['velocidade_pesados_kmh']==50
    assert obj['confianca']=='conflitante'
    assert obj['conflitos'][0]['valores_kmh']==[60.0,80.0]
    for fmt in ('xml','ndjson','txt','dif','edifact'):
        hdr,data=request(env,f'lat=-24.9555&lon=-53.4552&raio=100&formato={fmt}')
        assert '200 OK' in hdr
        assert data


def test_inmetro_nominal_not_legal_speed(sandbox):
    tmp,env=sandbox
    original=[{'SiglaUf':'AC','Municipio':'RIO BRANCO','TipoMedidor':'Fixo',
      'Faixas':[{'NumeroFaixa':'1','NumeroInmetro':'14826019','NumeroSerie':'FLICD2106A00575','Sentido':'CRESCENTE','VelocidadeNominal':'40'},
                {'NumeroFaixa':'2','NumeroInmetro':'14826019','NumeroSerie':'FLICD2106A00575','Sentido':'CRESCENTE','VelocidadeNominal':'60'}],
      'Historico':[{'NumeroCertificado':'2020202','DataLaudo':'03/07/2025','DataValidade':'02/07/2026','TipoServico':'Periódica','Resultado':'Aprovado'}]}]
    src=tmp/'inmetro.json';src.write_text(json.dumps(original),encoding='utf-8')
    r=cli(env,'import-file','--source','INMETRO_IMPORT','--file',str(src),'--format','json')
    assert r.returncode==0,(r.stdout,r.stderr)
    summary=json.loads(cli(env,'status').stdout)
    assert summary['contadores']['equipamento']==1
    assert summary['contadores']['ponto_fiscalizacao']==0
    h,data=request(env,'',path='/api/v1/equipamentos/1')
    assert '200 OK' in h,(h,data)
    equip=json.loads(data)['resultado']['itens'][0]
    assert sorted(x['velocidade_nominal_kmh'] for x in equip['faixas_medicao_nominal'])==[40,60]
    assert 'velocidade_leves_kmh' not in equip


def test_antts_real_field_spellings_and_distinct_semantics(sandbox):
    tmp,env=sandbox
    # Estrutura da ANTT segundo dicionário de radar (não tráfego).
    f=tmp/'antt_real.csv'
    f.write_text('concessionaria;ano_do_pnv_snv;tipo_de_radar;rodovia;uf;km_m;municipio;tipo_de_pista;sentido;situacao;data_da_inativacao;latitude;longitude;velocidade_leve;velocidade_pesado\n'
       'Concessionaria Teste;2024;Redutor;BR-116;SP;317,940;Taubate;principal;crescente;Ativo;;-23.020000;-45.560000;110;90\n',encoding='utf-8')
    r=cli(env,'import-file','--source','ANTT_RADARES','--file',str(f),'--format','csv')
    assert r.returncode==0,(r.stdout,r.stderr)
    _,body=request(env,'lat=-23.02&lon=-45.56&raio=1000&formato=json')
    point=json.loads(body)['resultado']['radares'][0]
    assert point['km']==317.94
    assert point['tipo_pista']=='principal'
    assert point['velocidade_leves_kmh']==110
    assert point['velocidade_pesados_kmh']==90
    assert point['fontes'][0]['dados_originais']['tipo_de_radar']=='Redutor'
    assert point['tipos_radar_presentes']==[]  # redutor != fixo
    assert point['fontes'][0]['dados_originais']['ano_do_pnv_snv']=='2024'


def test_cross_source_equal_serial_creates_review_candidate(sandbox):
    tmp,env=sandbox
    a=tmp/'prf.html'
    a.write_text('<table><tr><th>Identificador</th><th>Serie</th></tr><tr><td>REF181</td><td>TC005867</td></tr></table>')
    assert cli(env,'import-file','--source','PRF_PORTATEIS','--file',str(a),'--format','prf_portateis').returncode==0
    b=tmp/'inmetro.json'
    b.write_text(json.dumps([{'NumeroSerie':'TC005867','NumeroInmetro':'9999','TipoMedidor':'portatil',
            'Faixas':[{'NumeroSerie':'TC005867','NumeroInmetro':'9999','NumeroFaixa':'1','VelocidadeNominal':'60'}]}]))
    result=cli(env,'import-file','--source','INMETRO_IMPORT','--file',str(b),'--format','json')
    assert result.returncode==0,(result.stdout,result.stderr)
    from sqlalchemy import create_engine,text
    with create_engine(env['RADAR_DATABASE_URL']).connect() as c:
        assert c.execute(text('select count(*) from equipamento')).scalar()==2
        assert c.execute(text('select count(*) from candidato_duplicidade')).scalar()>=1

def test_generic_status_formats_not_empty_schema(sandbox):
    _,env=sandbox
    assert cli(env,'init').returncode==0
    h,body=request(env,'formato=txt',path='/api/v1/status')
    assert '200 OK' in h
    assert b'metadados|' in body and b'contadores' in body
    h,body=request(env,'formato=dif',path='/api/v1/status')
    assert b'RadarBrasil-Metadados' in body
