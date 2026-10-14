#!/usr/bin/env python3
"""Auditoria independente dos downloads oficiais do PSIE/Inmetro (27 UFs).

Não modifica o banco Radar Brasil; não afirma cobertura pelo simples HTTP 200.
Executar em máquina com acesso à internet: python3 scripts/auditar_psie_27ufs.py
Requer somente a biblioteca padrão Python 3.9+.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import email.utils
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET

UFS = ('AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG',
       'PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO')
BASE = 'https://servicos.rbmlq.gov.br/dados-abertos/{uf}/medidores.{ext}'
USER_AGENT = 'RadarBrasil-PSIE-Auditoria/1.0 (public data integrity check)'
RETRY_CODES = {408,429,500,502,503,504}

class MaxSizeExceeded(Exception):
    pass

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        host = (target.hostname or '').lower()
        if target.scheme != 'https' or (host != 'servicos.rbmlq.gov.br' and
                host != 'psie.inmetro.gov.br'):
            raise urllib.error.URLError('redirecionamento fora dos domínios HTTPS oficiais do PSIE')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

OPENER = urllib.request.build_opener(SafeRedirect)

def official_url(uf, ext='json'):
    if uf not in UFS or ext not in ('json','xml'):
        raise ValueError('UF/formato não permitido')
    return BASE.format(uf=uf, ext=ext)

def _read_limited(fp, limit):
    chunks, total = [], 0
    while True:
        part = fp.read(128*1024)
        if not part:
            break
        total += len(part)
        if total > limit:
            raise MaxSizeExceeded(f'arquivo ultrapassa {limit} bytes')
        chunks.append(part)
    return b''.join(chunks)

def request_with_retries(url, timeout, retries, max_bytes):
    attempts = []
    for n in range(retries+1):
        try:
            req=urllib.request.Request(url, headers={
                'User-Agent':USER_AGENT,
                'Accept':'application/json,application/xml,text/xml,application/octet-stream;q=0.8',
            })
            with OPENER.open(req,timeout=timeout) as res:
                content=_read_limited(res,max_bytes)
                return content,dict(res.headers),res.geturl(),attempts
        except urllib.error.HTTPError as e:
            retry = e.code in RETRY_CODES
            description=f'HTTP_{e.code}'
            attempts.append(description)
            if not retry or n == retries:
                return None,{'http_status':e.code},url,attempts
            ra=e.headers.get('Retry-After','')
            wait=min(30,2**n)
            try: wait=min(30,max(0,int(ra)))
            except (ValueError,TypeError):
                try:
                    when=email.utils.parsedate_to_datetime(ra)
                    wait=min(30,max(0,(when-dt.datetime.now(dt.timezone.utc)).total_seconds()))
                except (ValueError,TypeError,OverflowError):pass
            time.sleep(wait)
        except (urllib.error.URLError,TimeoutError,OSError,MaxSizeExceeded) as e:
            attempts.append(f'{type(e).__name__}: {str(e)[:240]}')
            if isinstance(e,MaxSizeExceeded) or n == retries:
                return None,{},url,attempts
            time.sleep(min(15,2**n))
    return None,{},url,attempts

def _date_iso(v):
    if not isinstance(v,str):return None
    for fmt in ('%d/%m/%Y','%Y-%m-%d','%Y-%m-%dT%H:%M:%S'):
        try:return dt.datetime.strptime(v.strip(),fmt).date().isoformat()
        except ValueError:pass
    return None

def audit_json(raw, uf):
    try: obj=json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError,ValueError) as e:
        return {'valid':False,'error':'JSON malformado: '+str(e)[:170]}
    # PSIE publish record arrays; do not silently accept arbitrary objects or error envelopes.
    if not isinstance(obj,list):
        return {'valid':False,'error':'Resposta JSON não é uma lista de medidores'}
    if obj and not all(isinstance(r,dict) for r in obj):
        return {'valid':False,'error':'Existem elementos não-objeto na lista'}
    keys=sorted({k for rec in obj for k in rec.keys()})
    required={'SiglaUf','Municipio','LocalVerificacao','Faixas','Historico'}
    absent=sorted(required-set(keys))
    if obj and absent:
        return {'valid':False,'error':'Campos essenciais ausentes: '+','.join(absent),'campos':keys}
    wrong=[i for i,rec in enumerate(obj) if str(rec.get('SiglaUf','')).strip().upper()!=uf]
    if wrong:
        return {'valid':False,'error':f'{len(wrong)} registros com UF divergente da UF consultada','indices_divergentes':wrong[:10]}
    series=set();inmetros=set();faixas=0;historicos=0;datas=[];with_coords=0;invalid_arrays=0
    examples=[]
    for idx,rec in enumerate(obj):
        fa=rec.get('Faixas') or []
        hist=rec.get('Historico') or []
        if not isinstance(fa,list) or not isinstance(hist,list):
            invalid_arrays+=1;continue
        faixas+=len(fa);historicos+=len(hist)
        for f in fa:
            if isinstance(f,dict):
                if f.get('NumeroSerie'):series.add(str(f['NumeroSerie']).strip())
                if f.get('NumeroInmetro'):inmetros.add(str(f['NumeroInmetro']).strip())
        if 'latitude' in {k.lower() for k in rec} and 'longitude' in {k.lower() for k in rec}:
            with_coords+=1
        for date in [_date_iso(rec.get('DataUltimaVerificacao'))]+[_date_iso(h.get('DataLaudo')) for h in hist if isinstance(h,dict)]:
            if date:datas.append(date)
        if len(examples)<3:
            examples.append({'municipio':rec.get('Municipio'), 'local':rec.get('LocalVerificacao'),
                             'tipo':rec.get('TipoMedidor'),'data_verificacao':rec.get('DataUltimaVerificacao')})
    if invalid_arrays:
        return {'valid':False,'error':f'{invalid_arrays} registros sem arrays Faixas/Historico válidos'}
    return {'valid':True,'registros':len(obj),'faixas':faixas,'verificacoes_historicas':historicos,
            'series_distintas':len(series),'numeros_inmetro_distintos':len(inmetros),
            'registros_com_coordenadas':with_coords,'ultima_verificacao_no_conteudo':max(datas) if datas else None,
            'campos':keys, 'amostras':examples,
            'aviso':'Arquivo vazio exige confirmação de fonte; HTTP 200 não comprova cobertura' if not obj else
                    ('Poucos registros: investigar possível extração parcial' if len(obj)<5 else None)}

def audit_xml(raw,uf):
    try:root=ET.fromstring(raw)
    except ET.ParseError as e:return {'valid':False,'error':'XML malformado: '+str(e)[:160]}
    tags=sorted({el.tag.split('}')[-1] for el in root.iter()})
    # Parsing XML is not proof of full schema compatibility or correct state.
    return {'valid':True,'raiz':root.tag,'tags':tags[:150],
            'schema_validado':False,
            'aviso':'XML bem formado; contar medidores e validar correspondência por UF antes de importar'}

def _atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp.'+str(os.getpid()))
    try:
        with open(tmp,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def audit_one(uf, ext, args):
    url=official_url(uf,ext)
    start=time.monotonic()
    raw,headers,final,attempts=request_with_retries(url,args.timeout,args.retries,args.max_bytes)
    result={'uf':uf,'formato':ext,'url':url,'url_final':final,
            'testado_em':dt.datetime.now(dt.timezone.utc).isoformat(),
            'http_status':headers.get('http_status'),
            'tentativas_falhas':attempts,'duracao_segundos':round(time.monotonic()-start,2)}
    if raw is None:
        result.update(status='NAO_ACESSIVEL_NESTA_EXECUCAO',validado=False,erro='; '.join(attempts[-3:]) or 'Sem corpo HTTP')
        return result
    result['http_status']=200
    result['bytes']=len(raw)
    result['sha256']=hashlib.sha256(raw).hexdigest()
    result['content_type']=headers.get('Content-Type') or headers.get('content-type')
    result['last_modified_http']=headers.get('Last-Modified') or headers.get('last-modified')
    result['etag']=headers.get('ETag') or headers.get('etag')
    parsed=audit_json(raw,uf) if ext=='json' else audit_xml(raw,uf)
    result.update(parsed)
    result['validado']=bool(parsed.get('valid'))
    result['status']='CONTEUDO_VALIDADO' if result['validado'] else 'CONTEUDO_INVALIDO'
    if result['validado'] and args.salvar_arquivos:
        dest=args.saida/'originais'/uf/f'medidores.{ext}'
        _atomic_write(dest,raw)
        result['arquivo_cache_local']=str(dest)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uf',action='append',choices=UFS,help='Filtrar UF; pode repetir. Padrão: todas as 27 UFs')
    parser.add_argument('--formato',choices=['json','xml','ambos'],default='json')
    parser.add_argument('--saida',type=Path,default=Path('auditoria_psie'))
    parser.add_argument('--timeout',type=float,default=18.0)
    parser.add_argument('--retries',type=int,default=1)
    parser.add_argument('--max-bytes',type=int,default=150_000_000)
    parser.add_argument('--pausa',type=float,default=0.2)
    parser.add_argument('--salvar-arquivos',action='store_true',help='Gravar somente arquivos validados de forma atômica')
    args=parser.parse_args(argv)
    if args.timeout<=0 or args.retries<0 or args.retries>4 or args.max_bytes<1024 or args.pausa<0:
        parser.error('timeout, retries, max-bytes e pausa fora do intervalo permitido')
    ufs=list(dict.fromkeys(args.uf or UFS))
    exts=['json','xml'] if args.formato=='ambos' else [args.formato]
    args.saida.mkdir(parents=True,exist_ok=True)
    results=[]
    for uf in ufs:
        for ext in exts:
            print(f'[{uf}/{ext}] verificando fonte...',file=sys.stderr,flush=True)
            result=audit_one(uf,ext,args)
            results.append(result)
            print(f'[{uf}/{ext}] {result["status"]} http={result.get("http_status")} '
                  f'registros={result.get("registros","?")}',file=sys.stderr,flush=True)
            if args.pausa:time.sleep(args.pausa)
    summary={
        'gerado_em':dt.datetime.now(dt.timezone.utc).isoformat(),
        'total_ufs_solicitadas':len(ufs),'total_consultas':len(results),
        'conteudos_validos':sum(r['status']=='CONTEUDO_VALIDADO' for r in results),
        'inacessiveis':sum(r['status']=='NAO_ACESSIVEL_NESTA_EXECUCAO' for r in results),
        'invalidos':sum(r['status']=='CONTEUDO_INVALIDO' for r in results),
        'avisos':['Fonte metrológica não comprova radares em operação nem coordenadas precisas.',
                  'Resultados de validação local dependem da rede e data do teste.'],
        'resultados':results}
    _atomic_write(args.saida/'relatorio_psie_27ufs.json', (json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode())
    with (args.saida/'relatorio_psie_27ufs.csv').open('w',encoding='utf-8',newline='') as fp:
        fields=('uf','formato','status','http_status','registros','faixas','series_distintas',
                'numeros_inmetro_distintos','ultima_verificacao_no_conteudo','bytes','erro','url')
        writer=csv.DictWriter(fp,fieldnames=fields,delimiter=';',extrasaction='ignore')
        writer.writeheader();writer.writerows(results)
    print(json.dumps({k:v for k,v in summary.items() if k!='resultados'},ensure_ascii=False,indent=2))
    return 0 if summary['inacessiveis']==0 and summary['invalidos']==0 else 2

if __name__=='__main__':
    sys.exit(main())
