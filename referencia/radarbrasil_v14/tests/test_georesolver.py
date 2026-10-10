"""Testes offline de geolocalização; dados e coordenadas fictícios."""
import csv,io,json,os,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def env(tmp_path):
    e=os.environ.copy();e.update(PYTHONPATH=str(ROOT),RADAR_DATABASE_URL='sqlite:///'+str(tmp_path/'geo.db'),
        RADAR_CACHE_DIR=str(tmp_path/'cache'),RADAR_CONFIG=str(ROOT/'config/sources.json'))
    return tmp_path,e

def run(e,mod,*args):
    return subprocess.run([sys.executable,'-m',f'radarbrasil.{mod}',*map(str,args)],env=e,cwd=ROOT,text=True,capture_output=True,timeout=40)

def imported(env,road=True):
    d,e=env
    f=d/'source.csv'
    f.write_text('Identificador;Numero Serie;Rodovia;KM;Tipo;Velocidade Leves;UF;Municipio\n'
                 'ATEST01;ABC123;BR-277;100;Fixo;60;PR;Cascavel\n')
    p=run(e,'collector','import-file','--source','ANTT_RADARES','--file',f,'--format','csv')
    assert p.returncode==0,(p.stdout,p.stderr)
    if road:
        seg=d/'seg.csv'
        with seg.open('w',newline='') as out:
            w=csv.DictWriter(out,fieldnames=['via','km_inicio','km_fim','geometria_json','uf'],delimiter=';');w.writeheader()
            w.writerow({'via':'BR-277','km_inicio':'99','km_fim':'101','geometria_json':json.dumps({'type':'LineString','coordinates':[[-53.49,-24.96],[-53.48,-24.96],[-53.47,-24.96]]}),'uf':'PR'})
        p=run(e,'georesolver','importar-trechos','--arquivo',seg,'--fonte','DNIT_SNV_CALIBRADO','--url','https://www.gov.br/dnit/')
        assert p.returncode==0,(p.stdout,p.stderr)
    return d,e

def web(e,path,params=''):
    ee={**e,'REQUEST_METHOD':'GET','PATH_INFO':path,'QUERY_STRING':params}
    ret=subprocess.run([sys.executable,str(ROOT/'web/api.pse')],env=ee,cwd=ROOT,input=b'',capture_output=True,timeout=40)
    h,b=ret.stdout.split(b'\r\n\r\n',1)
    return h,json.loads(b)

def test_km_to_candidate_and_review_with_api(env):
    d,e=imported(env)
    p=run(e,'georesolver','resolver-km')
    assert p.returncode==0,(p.stdout,p.stderr)
    j=json.loads(p.stdout);assert j['candidatos']==1
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert b'200 OK' in h
    item=j['resultado']['itens'][0]
    assert item['status']=='pendente' and not item['locais']
    cid=item['candidatos'][0]['id']
    assert item['candidatos'][0]['metodo']=='km_calibrado'
    # Sem aprovação, consulta por raio NÃO inclui radar com coordenada estimada.
    p=run(e,'georesolver','aprovar','--candidato',cid,'--autor','auditor','--justificativa','Segmento verificado manualmente no SNV vigente')
    assert p.returncode==0,(p.stdout,p.stderr)
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='localizado'
    h,j=web(e,'/api/v1/radares','lat=-24.96&lon=-53.48&raio=1500')
    assert j['resultado']['total']==1
    assert j['resultado']['radares'][0]['localizacao_metadados']['qualidade']=='inferida'
    assert j['resultado']['radares'][0]['localizacao_metadados']['coordinate_of_equipment_exact'] is False

def test_osm_never_autopromotes_and_missing_anchor_rejected(env):
    d,e=imported(env)
    osm=d/'osm.geojson'
    osm.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','id':'node/12345','properties':{'highway':'speed_camera','maxspeed':'60'},'geometry':{'type':'Point','coordinates':[-53.4802,-24.9602]}}]}))
    p=run(e,'georesolver','importar-osm','--arquivo',osm)
    assert json.loads(p.stdout)['candidatos']==0
    assert run(e,'georesolver','resolver-km').returncode==0
    p=run(e,'georesolver','importar-osm','--arquivo',osm,'--raio','1000')
    assert p.returncode==0,(p.stdout,p.stderr)
    assert json.loads(p.stdout)['candidatos']==1
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='pendente'
    methods={x['metodo'] for x in j['resultado']['itens'][0]['candidatos']}
    assert methods=={'km_calibrado','osm_comunitario'}

def test_no_clobber_official_coordinates(env):
    d,e=env
    f=d/'coord.csv'
    f.write_text('Identificador;Numero Serie;Latitude;Longitude;Rodovia;KM;Tipo\nR1;S1;-24.955;-53.455;BR-277;100;fixo\n')
    assert run(e,'collector','import-file','--source','ANTT_RADARES','--file',f,'--format','csv').returncode==0
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='localizado'
    assert j['resultado']['itens'][0]['locais'][0]['latitude']==-24.955

def test_reject_ambiguous_km_sections(env):
    d,e=imported(env)
    second=d/'second.csv'
    with second.open('w',newline='') as out:
        w=csv.DictWriter(out,fieldnames=['via','km_inicio','km_fim','geometria_json','uf'],delimiter=';');w.writeheader()
        w.writerow({'via':'BR-277','km_inicio':'99','km_fim':'101','geometria_json':json.dumps({'type':'LineString','coordinates':[[-53.49,-24.96],[-53.48,-24.95]]}),'uf':'PR'})
    assert run(e,'georesolver','importar-trechos','--arquivo',second,'--fonte','SNV_TEST','--url','https://www.gov.br/dnit/').returncode==0
    result=json.loads(run(e,'georesolver','resolver-km').stdout)
    assert result['ambiguos']==1 and result['candidatos']==0

def test_prohibits_unsupported_coords(env):
    d,e=imported(env,road=False)
    bad=d/'bad.csv';bad.write_text('via;km_inicio;km_fim;geometria_json\nBR-277;0;1;"[]"\n')
    result=json.loads(run(e,'georesolver','importar-trechos','--arquivo',bad,'--fonte','D','--url','https://www.gov.br').stdout)
    assert result['criadas']==0 and result['rejeitadas']==1

def test_cross_source_serial_candidates(env):
    d,e=env
    a=d/'first.csv';a.write_text('identificador;numero serie;latitude;longitude;rodovia;km;tipo\nAA;Z9;-24.955;-53.455;BR-277;100;fixo\n')
    b=d/'second.csv';b.write_text('identificador;numero serie;rodovia;km;tipo\nBB;Z9;BR-277;100;fixo\n')
    assert run(e,'collector','import-file','--source','ANTT_RADARES','--file',a,'--format','csv').returncode==0
    assert run(e,'collector','import-file','--source','DER_PR','--file',b,'--format','csv').returncode==0
    p=run(e,'georesolver','resolver-series');assert p.returncode==0,(p.stdout,p.stderr)
    assert json.loads(p.stdout)['candidatos']>=1


def test_cnefe_strict_address_and_ambiguity(env):
    d,e=env
    mun=d/'municipios.csv'
    mun.write_text('codigo_ibge;nome;uf\n4104808;Cascavel;PR\n')
    assert run(e,'georesolver','importar-municipios','--arquivo',mun).returncode==0
    sample=d/'end.csv'
    sample.write_text('identificador;numero serie;tipo;UF;municipio;logradouro;numero_end\n'
                      'ET1;SER-ADDR;fixo;PR;Cascavel;Rua Luz;55\n')
    p=run(e,'collector','import-file','--source','DER_PR','--format','csv','--file',sample)
    assert p.returncode==0,(p.stdout,p.stderr)
    cnefe=d/'cnefe.csv'
    cnefe.write_text('COD_MUNICIPIO;NOM_TIPO_SEGLOGR;NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE;COD_UNICO_ENDERECO;NV_GEO_COORD\n'
        '4104808;RUA;LUZ;55;-24.955;-53.455;1234;1\n')
    out=run(e,'georesolver','importar-cnefe','--arquivo',cnefe)
    assert out.returncode==0,(out.stdout,out.stderr)
    assert json.loads(out.stdout)['candidatos']==1
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='pendente'
    assert j['resultado']['itens'][0]['candidatos'][0]['metodo']=='cnefe_endereco'


def test_inmetro_localverificacao_becomes_road_km(env):
    d,e=env
    sample=d/'inmetro.json'
    sample.write_text(json.dumps([{'SiglaUf':'AC','Municipio':'Rio Branco','LocalVerificacao':'BR 364 KM 124,4 - RIO BRANCO',
       'TipoMedidor':'Fixo','Faixas':[{'NumeroFaixa':'1','NumeroInmetro':'123','NumeroSerie':'SER1','VelocidadeNominal':'50'}],
       'Historico':[]}]))
    p=run(e,'collector','import-file','--source','INMETRO_IMPORT','--format','json','--file',sample)
    assert p.returncode==0,(p.stdout,p.stderr)
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='sem_coordenada'
    import sqlite3
    with sqlite3.connect(d/'geo.db') as con:
        code=con.execute('select codigo from via').fetchone()[0]
        km=con.execute('select km from ponto_fiscalizacao').fetchone()[0]
    assert code=='BR-364' and abs(km-124.4)<1e-8


def test_online_osm_mock_uses_anchored_point_without_promoting(env):
    d,e=imported(env)
    assert run(e,'georesolver','resolver-km').returncode==0
    script=f'''import json
from radarbrasil.georesolver import consult_osm_online
response=json.dumps({{'elements':[{{'type':'node','id':123,'lat':-24.9601,'lon':-53.4801,'tags':{{'highway':'speed_camera'}}}}]}}).encode()
print(json.dumps(consult_osm_online(1,700,{str(d/'overpass')!r},request_func=lambda q:response)))'''
    p=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=e,capture_output=True,text=True)
    assert p.returncode==0,(p.stdout,p.stderr)
    assert json.loads(p.stdout)['candidatos_novos']==1
    h,j=web(e,'/api/v1/geolocalizacoes','equipamento_id=1')
    assert j['resultado']['itens'][0]['status']=='pendente'
    assert len(j['resultado']['itens'][0]['candidatos'])==2
