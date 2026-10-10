#!/usr/bin/env python3
"""Audita páginas oficiais e descobre downloads; não insere registros nem inventa cobertura.
Só stdlib. Uso: python3 scripts/auditar_fontes_estaduais.py --uf GO --online --saida /tmp/uf_go.json
Para todas: --online --saida /tmp/estados.json. Sem --online não faz requisições.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, html, ipaddress, json, pathlib, re, socket, ssl, sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError, URLError

ROOT=pathlib.Path(__file__).resolve().parents[1]
CATALOG=ROOT/'config'/'fontes_nacionais_27ufs.json'
KEYWORDS=('radar','velocidade','fiscaliza','equipamento','medidor','monitoramento','kml','csv','json','xlsx','shape','download','baixar','mapa')
DOWNLOAD_EXT=('.csv','.xlsx','.xls','.json','.geojson','.xml','.kml','.kmz','.zip','.rar','.pdf','.shp','.gpkg')
MAX_BYTES=1024*1024*2

def official(url):
    try:
        x=urlparse(url)
        if x.scheme != 'https' or not x.hostname or x.username or x.password: return False
        host=x.hostname.lower().rstrip('.')
        return host.endswith('.gov.br') or host=='gov.br' or host.endswith('.go.gov.br')
    except ValueError:return False

def public_dns(host):
    try:
        ips={row[4][0] for row in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)}
        return bool(ips) and all(ipaddress.ip_address(ip).is_global for ip in ips)
    except (OSError,ValueError): return False

class Guard(HTTPRedirectHandler):
    def __init__(self,network_guard=True): super().__init__();self.hops=0;self.network_guard=network_guard
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.hops+=1
        if self.hops>5 or not official(newurl):raise ValueError('Redirecionamento não-oficial/bloqueado')
        if self.network_guard and not public_dns(urlparse(newurl).hostname):raise ValueError('Redirecionamento DNS não-público/bloqueado')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,timeout=20,max_bytes=MAX_BYTES,network_guard=True):
    if not official(url):raise ValueError('URL de origem não é domínio governamental HTTPS')
    if network_guard and not public_dns(urlparse(url).hostname):raise ValueError('Host DNS não-público ou sem DNS disponível')
    opener=build_opener(Guard(network_guard),HTTPSHandler(context=ssl.create_default_context()))
    req=Request(url,headers={'User-Agent':'RadarBrasil-OfficialSourceAudit/1.0 (+public-research)','Accept':'text/html,application/json,application/geo+json,text/csv,application/octet-stream;q=0.8'})
    with opener.open(req,timeout=timeout) as res:
        data=res.read(max_bytes+1)
        if len(data)>max_bytes:raise ValueError('Resposta excede limite de auditoria (não inferir arquivo inválido)')
        return {'url':res.url,'status':res.status,'mime':res.headers.get('Content-Type',''),'modified':res.headers.get('Last-Modified'),'etag':res.headers.get('ETag'),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},data

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.current={'href':dict(attrs).get('href',''),'text':''}
    def handle_data(self,data):
        if self.current:self.current['text']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current:
            self.links.append(self.current);self.current=None

def candidates(page,raw):
    parser=Links();parser.feed(raw.decode('utf-8','replace'))
    found=[];seen=set()
    for item in parser.links:
        address=urljoin(page,html.unescape(item['href']));p=urlparse(address)
        if not official(address) or address in seen:continue
        label=' '.join(item['text'].split());score=1 if p.path.lower().endswith(DOWNLOAD_EXT) else 0
        joined=(label+' '+p.path).lower()
        score+=sum(1 for key in KEYWORDS if key in joined)
        if score>0:
            seen.add(address)
            found.append({'url':address,'descricao':label[:160],'formato_sugerido':next((v[1:] for v in DOWNLOAD_EXT if p.path.lower().endswith(v)),'desconhecido'),'prioridade':score})
    return sorted(found,key=lambda x:(-x['prioridade'],x['url']))[:80]

def mime_magic(raw):
    s=raw.lstrip()[:200].lower()
    if raw.startswith(b'%PDF-'):return 'pdf'
    if raw.startswith(b'PK\x03\x04'):return 'zip/xlsx/kmz (verificar arquivo interno)'
    if raw.startswith(b'Rar!'):return 'rar'
    if raw.startswith(b'\x1f\x8b'):return 'gzip'
    if s.startswith((b'{',b'[')):return 'json_possivel'
    if s.startswith(b'<?xml') or s.startswith(b'<kml'):return 'xml/kml_possivel'
    if s.startswith((b'<!doctype html',b'<html')):return 'html'
    return 'nao_identificado'

def audit(uf=None,online=False,timeout=20):
    inventory=json.loads(CATALOG.read_text(encoding='utf-8'))
    allrows=inventory['estados']+inventory.get('fontes_adicionais',[])
    rows=[r for r in allrows if not uf or r['uf']==uf]
    answer={'data_auditoria':dt.datetime.now(dt.timezone.utc).isoformat(),'modo':'online' if online else 'inventario_sem_rede','escopo':'somente fontes oficiais; portal estadual/municipal não garante cobertura estadual','fontes':[]}
    for row in rows:
        result={'uf':row['uf'],'fonte':row.get('codigo_fonte'),'url':row['url'],'classificacao_previa':row.get('classificacao_evidencia'),'coordenadas_confirmadas_pelo_script':False,'cobertura_estadual_confirmada':False,'situacao':'nao_testada'}
        if online:
            try:
                meta,body=fetch(row['url'],timeout=timeout)
                result.update({'situacao':'pagina_acessivel','http':meta,'conteudo_detectado':mime_magic(body)})
                if result['conteudo_detectado']=='html' or 'text/html' in meta['mime'].lower():
                    result['candidatos_download']=candidates(meta['url'],body)
            except (ValueError,URLError,HTTPError,TimeoutError,OSError) as exc:
                result.update({'situacao':'falha_verificacao','erro':f'{type(exc).__name__}: {str(exc)[:400]}'})
        answer['fontes'].append(result)
    answer['quantidade_fontes']=len(answer['fontes'])
    answer['quantidade_ufs']=len({x['uf'] for x in answer['fontes']})
    return answer

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--online',action='store_true',help='Consulta URLs oficiais e descobre links; NÃO importa dados')
    p.add_argument('--uf',help='UF a conferir (AC, GO...)')
    p.add_argument('--timeout',type=float,default=20)
    p.add_argument('--saida',help='Arquivo JSON de saída; sem ele imprime no stdout')
    a=p.parse_args(argv)
    ufs={e['uf'] for e in json.loads(CATALOG.read_text(encoding='utf-8'))['estados']}
    if a.uf and a.uf.upper() not in ufs:p.error('UF desconhecida')
    out=audit(a.uf.upper() if a.uf else None,a.online,a.timeout)
    raw=json.dumps(out,ensure_ascii=False,indent=2)+'\n'
    if a.saida:
        target=pathlib.Path(a.saida);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(raw,encoding='utf-8')
    else:print(raw)
    return 0
if __name__=='__main__':sys.exit(main())
