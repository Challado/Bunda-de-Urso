#!/usr/bin/env python3
"""Verificação de integração real, ONLINE e OPT-IN; não publica registros no banco.
Exemplo: python scripts/validar_fontes_reais.py --source ANTT_RADARES --out /tmp/antt-validacao.json
Usar somente sobre recursos públicos e conforme termos da fonte.
"""
import argparse, hashlib, json, sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from radarbrasil.collector import sources
from radarbrasil.sources import Downloader,ckan_discover,prf_fixed_discover,parse_table,osm_parse,OVERPASS_QUERY
from radarbrasil.normalization import normalize_record

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True)
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    cfg=next((x for x in sources() if x['code']==args.source),None)
    if not cfg:
        print(json.dumps({'erro':'fonte não cadastrada','fonte':args.source}),file=sys.stderr);return 2
    result={'fonte':args.source,'testado_em':datetime.now(timezone.utc).isoformat(),
            'integracao_validada':False,'download_ok':False,'importacao_efetuada':False}
    try:
        dl=Downloader()
        if cfg['format']=='ckan':resource=ckan_discover(cfg,dl)
        elif cfg['format']=='prf_fixos':resource=prf_fixed_discover(cfg,dl)
        elif cfg['format']=='manual_json':raise RuntimeError('Origem manual; usar import-file depois de obter arquivo público legítimo')
        else:resource={'url':cfg['url'],'format':cfg['format']}
        raw,headers,final=dl.fetch(resource['url'],method='POST' if resource['format']=='osm_overpass' else 'GET',
                                     data={'data':OVERPASS_QUERY} if resource['format']=='osm_overpass' else None)
        typ=resource['format'].lower()
        rows=osm_parse(raw) if typ=='osm_overpass' else parse_table(raw,typ)
        if not rows:raise RuntimeError('Nenhum registro retornado')
        keys=sorted({key for r in rows[:1000] for key in r})
        normalized=[normalize_record(r,args.source) for r in rows[:1000]]
        result.update(integracao_validada=True,download_ok=True,url_final=final,
            formato=typ,hash_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
            linhas_recebidas=len(rows),colunas=keys,
            amostra_ate=1000,
            registros_com_latlon_amostra=sum(v['latitude'] is not None for v in normalized),
            registros_com_limite_leves_amostra=sum(v['speed_light'] is not None for v in normalized),
            registros_com_limite_pesados_amostra=sum(v['speed_heavy'] is not None for v in normalized),
            aviso='Teste de download + layout somente. Validação humana de amostra ainda necessária; NÃO cria registros no banco.')
    except Exception as exc:
        result.update(erro_tipo=type(exc).__name__,erro=str(exc)[:1200])
    body=json.dumps(result,ensure_ascii=False,indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(body+'\n',encoding='utf-8')
    print(body)
    return 0 if result['integracao_validada'] else 2

if __name__=='__main__':raise SystemExit(main())
