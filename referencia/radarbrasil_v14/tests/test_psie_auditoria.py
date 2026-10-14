import importlib.util
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1] / 'scripts' / 'auditar_psie_27ufs.py'
spec=importlib.util.spec_from_file_location('auditar_psie',SCRIPT)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def test_uf_whitelist():
    assert len(mod.UFS)==27 and 'DF' in mod.UFS and 'GO' in mod.UFS
    assert mod.official_url('GO')=='https://servicos.rbmlq.gov.br/dados-abertos/GO/medidores.json'
    try:mod.official_url('../secret')
    except ValueError:pass
    else:raise AssertionError('URL arbitrary accepted')

def test_usable_json_two_faixas_one_instrument():
    import json
    data=[{'SiglaUf':'GO','Municipio':'X','LocalVerificacao':'GO-060 KM 20',
           'Faixas':[{'NumeroFaixa':'1','NumeroSerie':'S1','NumeroInmetro':'R1'},
                     {'NumeroFaixa':'2','NumeroSerie':'S1','NumeroInmetro':'R1'}],
           'Historico':[{'DataLaudo':'04/08/2026'}], 'DataUltimaVerificacao':'03/08/2026'}]
    r=mod.audit_json(json.dumps(data).encode(),'GO')
    assert r['valid'] is True
    assert r['registros']==1 and r['faixas']==2 and r['series_distintas']==1
    assert r['ultima_verificacao_no_conteudo']=='2026-08-04'

def test_reject_wrong_state_and_html():
    import json
    sample=[{'SiglaUf':'AC','Municipio':'Rio Branco','LocalVerificacao':'BR364','Faixas':[],'Historico':[]}]
    assert not mod.audit_json(json.dumps(sample).encode(),'GO')['valid']
    assert not mod.audit_json(b'<html>erro</html>','AC')['valid']

def test_no_assumptions_empty_payload():
    result=mod.audit_json(b'[]','AC')
    assert result['valid'] and result['registros']==0 and result['aviso']

def test_xml_is_only_syntactically_validated():
    r=mod.audit_xml(b'<Medidores><Medidor><SiglaUf>AC</SiglaUf></Medidor></Medidores>','AC')
    assert r['valid'] and not r['schema_validado']
    assert not mod.audit_xml(b'<Medidores>','AC')['valid']
