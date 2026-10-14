"""Testes determinísticos, sem acessar portais externos."""
import io, json, os, subprocess, sys
from pathlib import Path
import pytest
from radarbrasil.sources import Downloader, SourceError, prf_fixed_discover
from radarbrasil.normalization import normalize_record
ROOT=Path(__file__).resolve().parents[1]

class DummyDownloader:
    def fetch(self,url,**kwargs):
        if 'radares-fixos' in url:
            return b'<a href="https://mapas-html.vercel.app/tabela.html">TABELA DE RADARES FIXOS</a>',{},url
        if 'tabela.html' in url:
            return b'<a href="https://docs.google.com/spreadsheets/d/ABCDEF/export?format=xlsx">Baixar</a>',{},url
        raise AssertionError(url)

def test_prf_discover_real_layout_google_sheet():
    result=prf_fixed_discover({'url':'https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos'},DummyDownloader())
    assert result['format']=='xlsx'
    assert result['url'].startswith('https://docs.google.com/spreadsheets/d/')

def test_prf_missing_export_explains_failure():
    class Missing(DummyDownloader):
        def fetch(self,url,**kw):
            if 'tabela.html' in url:return b'<div>Dinamic JS without xlsx link</div>',{},url
            return super().fetch(url,**kw)
    with pytest.raises(SourceError,match='planilha XLSX'):
        prf_fixed_discover({'url':'https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos'},Missing())

def test_public_https_guard():
    for u in ['http://www.gov.br','https://127.0.0.1/api','https://localhost/a','https://admin:pw@www.gov.br/a','https://www.gov.br:8181/api']:
        with pytest.raises(SourceError):Downloader.checked_url(u)
    assert Downloader.checked_url('https://www.gov.br/foo')

def test_antts_function_distinct_from_physical_type():
    val=normalize_record({'tipo_de_radar':'Controlador','velocidade_leve':'100','velocidade_pesado':'80'},'ANTT_RADARES')
    assert val['radar_type']=='desconhecido'
    assert val['function']=='controlador'
    assert val['speed_light']==100
    assert val['speed_heavy']==80

@pytest.fixture
def install(tmp_path):
    env=os.environ.copy()
    env.update(PYTHONPATH=str(ROOT),RADAR_DATABASE_URL='sqlite:///'+str(tmp_path/'db.sqlite3'),
        RADAR_CACHE_DIR=str(tmp_path/'cache'),RADAR_CONFIG=str(ROOT/'config/sources.json'))
    def call(*args):
        return subprocess.run([sys.executable,'-m','radarbrasil.collector',*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
    def api(query,method='GET',path='/api/v1/radares',body=b''):
        e=dict(env,REQUEST_METHOD=method,PATH_INFO=path,QUERY_STRING=query,CONTENT_LENGTH=str(len(body)),CONTENT_TYPE='application/json')
        r=subprocess.run([sys.executable,str(ROOT/'web/api.pse')],cwd=ROOT,env=e,input=body,capture_output=True,timeout=30)
        return r.stdout.split(b'\r\n\r\n',1)
    return tmp_path,call,api

def test_txt_empty_partial_is_not_error(install):
    d,call,api=install
    f=d/'one.csv'
    f.write_text('identificador;latitude;longitude;rodovia;km;velocidade_leve\nABC;-24.9555;-53.4552;BR-277;120;60\n')
    assert call('import-file','--source','ANTT_RADARES','--format','csv','--file',str(f)).returncode==0
    h,b=api('lat=-1&lon=-1&raio=100&formato=txt')
    assert b==b''
    assert b'200 OK' in h
    assert b'X-RadarBrasil-Cobertura: parcial' in h
    assert b'X-RadarBrasil-Encontrado: desconhecido' in h

def test_inmetro_equipment_has_full_provenance(install):
    d,call,api=install
    f=d/'medidores.json'
    f.write_text(json.dumps([{'SiglaUf':'AC','Municipio':'Rio Branco','LocalVerificacao':'BR 364',
            'Proprietario':{'Nome':'EMPRESA EXEMPLO'},'Faixas':[{'NumeroFaixa':'1','NumeroInmetro':'100',
            'NumeroSerie':'A123','VelocidadeNominal':'50'}],
            'Historico':[{'NumeroCertificado':'C1','DataLaudo':'01/01/2025','DataValidade':'01/01/2026','Resultado':'Aprovado'}]}]))
    assert call('import-file','--source','INMETRO_IMPORT','--format','json','--file',str(f)).returncode==0
    h,b=api('',path='/api/v1/equipamentos/1')
    assert b'200 OK' in h
    eq=json.loads(b)['resultado']['itens'][0]
    assert eq['evidencias'][0]['dados_originais']['_inmetro']['grupo']['Proprietario']['Nome']=='EMPRESA EXEMPLO'
    assert eq['verificacoes_metrologicas'][0]['numero_certificado']=='C1'

def test_concessionaria_stored_relationally(install):
    d,call,api=install
    f=d/'antt.csv';f.write_text('Identificador;Latitude;Longitude;Rodovia;KM;Concessionaria;Estudo Tecnico\nA;-24.1;-53.1;BR-277;100;CONCESSIONARIA C;ET-009\n')
    assert call('import-file','--source','ANTT_RADARES','--format','csv','--file',str(f)).returncode==0
    h,b=api('lat=-24.1&lon=-53.1&raio=100')
    j=json.loads(b)['resultado']['radares'][0]
    assert any(o['nome']=='CONCESSIONARIA C' for o in j['organizacoes'])
    assert any(o['codigo']=='ET-009' for o in j['documentos'])

def test_official_punctual_period_and_timezone_filter(install):
    d,call,api=install
    f=d/'operations.csv'
    f.write_text('Identificador;Latitude;Longitude;Rodovia;KM;Modalidade de Fiscalizacao;inicio_fiscalizacao;fim_fiscalizacao\n'
      'PT-01;-24.9555;-53.4552;BR-277;120;pontual;2026-10-15T14:00:00-03:00;2026-10-15T17:00:00-03:00\n')
    r=call('import-file','--source','DER_PR','--file',str(f),'--format','csv')
    assert r.returncode==0,(r.stderr,r.stdout)
    h,b=api('lat=-24.9555&lon=-53.4552&raio=100')
    assert b'200 OK' in h
    pt=json.loads(b)['resultado']['radares'][0]
    assert pt['fiscalizacao_pontual'] is True
    assert pt['operacoes'][0]['inicio'].startswith('2026-10-15T17:00:00')
    h,b=api('lat=-24.9555&lon=-53.4552&raio=100&em=2026-10-15T15%3A00%3A00-03%3A00')
    assert json.loads(b)['resultado']['total']==1
    h,b=api('lat=-24.9555&lon=-53.4552&raio=100&em=2026-10-16T15%3A00%3A00-03%3A00')
    assert json.loads(b)['resultado']['total']==0

def test_http_retry_429_then_success_and_304():
    class Response:
        def __init__(self,status,body=b'',headers=None):
            self.status_code=status;self.content=body;self.headers=headers or {}
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,chunk_size=65536):yield self.content
    class Session:
        def __init__(self,results):self.headers={};self.results=iter(results);self.calls=[]
        def request(self,method,url,**kwargs):
            self.calls.append((method,url,kwargs));return next(self.results)
    session=Session([Response(429,headers={'Retry-After':'0'}),Response(200,b'csv')])
    waits=[]
    response=Downloader(session=session,sleep=waits.append,attempts=2).fetch('https://www.gov.br/base.csv')
    assert response[0]==b'csv' and len(session.calls)==2 and waits==[0]
    with pytest.raises(Exception,match='HTTP 304'):
        Downloader(session=Session([Response(304)]),attempts=1).fetch('https://www.gov.br/base.csv',etag='"a"')

def test_http_redirect_to_private_blocked():
    class Response:
        status_code=302
        headers={'Location':'https://127.0.0.1/admin'}
        def __enter__(self):return self
        def __exit__(self,*a):pass
    class Session:
        headers={}
        def request(self,*args,**kwargs):return Response()
    with pytest.raises(SourceError,match='IP literal'):
        Downloader(session=Session(),attempts=1).fetch('https://www.gov.br/start')

def test_antt_traffic_observed_velocity_not_legal_limit(install):
    d,call,api=install
    f=d/'traffic.csv'
    f.write_text('Identificador;Latitude;Longitude;Rodovia;km_m;data_da_passagem;sentido_da_passagem;faixa_da_passagem;velocidade;tipo_de_veiculo;volume_total\n'
      'R-01;-24.1;-53.1;BR-277;120.0;2026-10-10;crescente;1;121;leve;17\n')
    r=call('import-file','--source','ANTT_TRAFEGO','--format','csv','--file',str(f))
    assert r.returncode==0,(r.stdout,r.stderr)
    status=json.loads(call('status').stdout)
    assert status['contadores']['ponto_fiscalizacao']==0
    from sqlalchemy import create_engine,text
    with create_engine('sqlite:///'+str(d/'db.sqlite3')).connect() as c:
        assert c.execute(text('select count(*) from observacao_trafego')).scalar()==1
        assert c.execute(text('select velocidade_kmh from observacao_trafego')).scalar()==121
        assert c.execute(text('select count(*) from limite_velocidade')).scalar()==0

def test_traffic_api_and_format(install):
    d,call,api=install
    f=d/'traffic.csv';f.write_text('Identificador;data_da_passagem;velocidade;volume_total\nX1;2026-10-10;92;5\n')
    assert call('import-file','--source','ANTT_TRAFEGO','--format','csv','--file',str(f)).returncode==0
    h,b=api('formato=json',path='/api/v1/trafego')
    assert b'200 OK' in h
    assert json.loads(b)['resultado']['itens'][0]['velocidade_observada_kmh']==92
    h,b=api('formato=txt',path='/api/v1/trafego')
    assert b'200 OK' in h and b'92.0' in b

def test_detail_and_catalog_search_without_coordinates(install):
    d,call,api=install
    f=d/'p.csv';f.write_text('Identificador;Latitude;Longitude;UF;Rodovia;KM\nZ;-24;-53;PR;BR-277;120\n')
    assert call('import-file','--source','ANTT_RADARES','--format','csv','--file',str(f)).returncode==0
    h,b=api('formato=json',path='/api/v1/radares/1')
    assert b'200 OK' in h and json.loads(b)['resultado']['radares'][0]['id']==1
    h,b=api('uf=PR&rodovia=BR-277',path='/api/v1/radares/busca')
    assert b'200 OK' in h and json.loads(b)['resultado']['total_retornado']==1

def test_geo_cursor_does_not_skip_equal_rounded_distance(install):
    d,call,api=install
    f=d/'p.csv'
    f.write_text('Identificador;Latitude;Longitude;UF;Rodovia;KM\n'
      'A;-24.0000000;-53.0000000;PR;BR-277;100\n'
      'B;-24.0000001;-53.0000001;PR;BR-277;200\n'
      'C;-24.0000002;-53.0000002;PR;BR-277;300\n')
    assert call('import-file','--source','DER_PR','--format','csv','--file',str(f)).returncode==0
    params='lat=-24&lon=-53&raio=1000&limite=1'
    visited=[];cursor=None
    for _ in range(3):
        qs=params+('&cursor='+cursor if cursor else '')
        h,b=api(qs);j=json.loads(b)
        assert b'200 OK' in h,(h,b)
        visited.append(j['resultado']['radares'][0]['id'])
        cursor=j['resultado']['proximo_cursor']
    assert len(set(visited))==3

def test_xml_source_keeps_nested_original_fields():
    from radarbrasil.sources import parse_table
    xml=b'<Medidores><Medidor><NumeroSerie>AA1</NumeroSerie><Faixas><Faixa><NumeroFaixa>1</NumeroFaixa></Faixa><Faixa><NumeroFaixa>2</NumeroFaixa></Faixa></Faixas></Medidor></Medidores>'
    rows=parse_table(xml,'xml')
    assert rows[0]['NumeroSerie']=='AA1'
    assert rows[0]['Faixas']['Faixa'][1]['NumeroFaixa']=='2'
