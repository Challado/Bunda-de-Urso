"""Checa inventário das 27 UFs e importadores geográficos, offline."""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

from radarbrasil.sources import parse_table, SourceError
from radarbrasil.normalization import normalize_record

ROOT=Path(__file__).resolve().parents[1]
UFS=set('AC AL AP AM BA CE DF ES GO MA MG MS MT PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())


def test_catalog_27_ufs_unique_and_no_fictitious_coverage():
    catalog=json.loads((ROOT/'config'/'fontes_nacionais_27ufs.json').read_text())
    assert len(catalog['estados'])==27
    assert {x['uf'] for x in catalog['estados']}==UFS
    assert all(x['url'].startswith('https://') for x in catalog['estados'])
    assert all(x['integracao_automatica_validada'] is False for x in catalog['estados'])
    assert all(x['cobertura_estadual_confirmada'] is False for x in catalog['estados'])


def test_all_catalog_entries_are_registered_but_disabled():
    cat=json.loads((ROOT/'config'/'fontes_nacionais_27ufs.json').read_text())
    src=json.loads((ROOT/'config'/'sources.json').read_text())['sources']
    by_code={x['code']:x for x in src}
    for item in cat['estados']:
        assert item['codigo_fonte'] in by_code
        assert by_code[item['codigo_fonte']]['enabled'] is False


def test_catalog_cli_can_filter_state_without_db_connection():
    cmd=[sys.executable,'-m','radarbrasil.collector','catalogo-nacional','--uf','GO']
    ret=subprocess.run(cmd,env={**os.environ,'PYTHONPATH':str(ROOT)},cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert ret.returncode==0,ret.stderr
    obj=json.loads(ret.stdout)
    assert obj['total_ufs']==1
    assert obj['estados'][0]['uf']=='GO'
    assert obj['estados'][0]['integracao_automatica_validada'] is False


def test_geojson_point_lon_lat_and_properties():
    doc={'type':'FeatureCollection','features':[
      {'type':'Feature','id':'TEST123','geometry':{'type':'Point','coordinates':[-51.060863,-17.625377]},
       'properties':{'rodovia':'GO-174','velocidade_leve':'80','sentido':'Crescente'}},
      {'type':'Feature','geometry':{'type':'LineString','coordinates':[[-51,-17],[-52,-18]]},
       'properties':{'rodovia':'GO-174'}}]}
    rows=parse_table(json.dumps(doc).encode(),'geojson')
    assert len(rows)==1
    assert rows[0]['latitude']==-17.625377 and rows[0]['longitude']==-51.060863
    assert rows[0]['identificador']=='TEST123'
    norm=normalize_record(rows[0],'GOINFRA')
    assert norm['road']=='GO-174' and norm['speed_light']==80


def test_geojson_conflicting_location_fails():
    doc={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[-50,-17]},'properties':{'latitude':-11}}]}
    with pytest.raises(SourceError,match='Conflito'):
        parse_table(json.dumps(doc).encode(),'geojson')


def test_geojson_malformed_and_no_points_fail():
    with pytest.raises(SourceError,match='GeoJSON'):
        parse_table(b'not json','geojson')
    doc={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'LineString','coordinates':[]},'properties':{}}]}
    with pytest.raises(SourceError,match='sem pontos'):
        parse_table(json.dumps(doc).encode(),'geojson')


def test_kml_point_order_and_extended_data():
    kml=b'''<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>RAD100</name><ExtendedData><Data name="velocidade_leve"><value>60</value></Data></ExtendedData>
      <Point><coordinates>-49.52,-16.64,0</coordinates></Point></Placemark></Document></kml>'''
    rows=parse_table(kml,'kml')
    assert len(rows)==1
    assert rows[0]['longitude']==-49.52 and rows[0]['latitude']==-16.64
    assert rows[0]['identificador']=='RAD100'
    assert rows[0]['velocidade_leve']=='60'
    with pytest.raises(SourceError,match='KML'):
        parse_table(b'<kml><broken','kml')


def test_xml_external_entity_rejected():
    payload=b'<!DOCTYPE kml [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><kml><Placemark><name>&xxe;</name></Placemark></kml>'
    with pytest.raises(SourceError):
        parse_table(payload,'kml')
