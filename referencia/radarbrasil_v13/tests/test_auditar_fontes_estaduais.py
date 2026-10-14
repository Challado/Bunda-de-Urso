import importlib.util, pathlib, sys
p=pathlib.Path(__file__).resolve().parents[1]/'scripts'/'auditar_fontes_estaduais.py'
s=importlib.util.spec_from_file_location('auditar_fontes_estaduais',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_official():
    assert m.official('https://goias.gov.br/goinfra/')
    assert m.official('https://dados.recife.pe.gov.br/dataset/teste')
    assert not m.official('http://goias.gov.br/goinfra')
    assert not m.official('https://goias.gov.br.evil.com/dados')
    assert not m.official('https://127.0.0.1/data')
def test_magic():
    assert m.mime_magic(b'Rar!\x1a\x07')=='rar'
    assert m.mime_magic(b'%PDF-1.5')=='pdf'
    assert m.mime_magic(b'PK\x03\x04...').startswith('zip')
    assert m.mime_magic(b'<html><title>A</title>')=='html'
def test_links():
    raw=b'<a href="/arquivo/radares.csv">Planilha Radares</a><a href="https://evil.com/rad.csv">evil</a><a href="/download/2026.zip">Baixar</a>'
    links=m.candidates('https://goinfra.go.gov.br/lista',raw)
    assert len(links)==2
    assert all(m.official(l['url']) for l in links)
def test_catalog():
    r=m.audit();assert r['quantidade_ufs']==27
    assert all(not x['coordenadas_confirmadas_pelo_script'] for x in r['fontes'])
