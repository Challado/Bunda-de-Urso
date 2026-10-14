"""Serializações interoperáveis sem lógica de negócios própria.
DIF: VisiCalc/Software Arts DIF; EDIFACT: GENRAL D96A, perfil bilateral,
FTX com payload JSON base64 fragmentado, não segmentos inventados de radar.
"""
import json, csv, io, base64, uuid
from xml.etree.ElementTree import Element,SubElement,tostring,register_namespace
from datetime import datetime,timezone

COLUMNS=['id','tipo_registro','situacao_operacional','latitude','longitude','distancia_metros','precisao_metros','uf','municipio','codigo_ibge','via_codigo','km','tipo_pista','tipos_radar_presentes_json','fiscalizacao_pontual','regimes_json','faixas_json','limites_velocidade_json','equipamentos_json','operacoes_json','documentos_json','fontes_json','conflitos_json','confianca','atualizacao_json','endereco_json','organizacoes_json','localizacao_metadados_json','observacoes','proveniencia_campos_json','estado_temporal_json','quantidade_faixas_declarada','velocidade_leves_kmh','velocidade_pesados_kmh','velocidade_geral_kmh','velocidades_resolvidas_json']
COMPLEX={'tipos_radar_presentes','regimes','faixas','limites_velocidade','equipamentos','operacoes','documentos','fontes','conflitos','atualizacao','endereco','organizacoes','localizacao_metadados','proveniencia_campos','estado_temporal','velocidades_resolvidas'}

MIME={'json':'application/json; charset=utf-8','ndjson':'application/x-ndjson; charset=utf-8','xml':'application/xml; charset=utf-8','txt':'text/plain; charset=utf-8','dif':'application/x-dif; charset=utf-8','edifact':'application/EDIFACT'}

def jsonb(obj):return json.dumps(obj,ensure_ascii=False,separators=(',',':'),default=str)

def rows_from(document):
    if isinstance(document,dict):
        r=document.get('resultado') or {}
        for p in ('radares','operacoes','trechos','itens'):
            if p in r and isinstance(r[p],list):return r[p]
        return [document]
    if isinstance(document,list):return document
    return [{'valor':document}]

def column_value(row,col):
    if col.endswith('_json') and col[:-5] in COMPLEX:return jsonb(row.get(col[:-5]))
    v=row.get(col)
    if isinstance(v,(list,dict)):return jsonb(v)
    if isinstance(v,bool):return 'true' if v else 'false'
    if v is None:return None
    return str(v)

def is_radar_response(document):
    return isinstance(document,dict) and isinstance(document.get('resultado'),dict) and isinstance(document['resultado'].get('radares'),list)

def general_records(document):
    """Para status/fontes/erros, preservar conteúdo em vez de produzir colunas de radar vazias."""
    if isinstance(document,dict) and isinstance(document.get('resultado'),dict):
        group=document['resultado'];typ=next((k for k in ('itens','operacoes','trechos') if isinstance(group.get(k),list)),None)
        if typ:
            return [{'tipo':typ[:-1] if typ.endswith('s') else typ,'id':str(o.get('id','')) if isinstance(o,dict) else '', 'conteudo_json':jsonb(o)} for o in group[typ]]
    return [{'tipo':str(document.get('tipo_resposta','metadados')) if isinstance(document,dict) else 'valor','id':'','conteudo_json':jsonb(document)}]

def generic_txt(document,delim='|'):
    buf=io.StringIO(newline=''); w=csv.writer(buf,delimiter=delim,quotechar='"',lineterminator='\n')
    for row in general_records(document):w.writerow([row['tipo'],row['id'],row['conteudo_json']])
    return buf.getvalue().encode('utf-8')

def generic_dif(document):
    cols=('tipo','id','conteudo_json'); records=general_records(document)
    lines=['TABLE','0,1','"RadarBrasil-Metadados"','VECTORS',f'0,{len(cols)}','""','TUPLES',f'0,{len(records)+1}','""','DATA','0,0','""']
    for row in [dict(zip(cols,cols))]+records:
        lines+=['-1,0','BOT']
        for col in cols:lines+=['1,0','"'+str(row[col]).replace('"','""')+'"']
    lines+=['-1,0','EOD']
    return ('\n'.join(lines)+'\n').encode('utf-8')

def txt(document,delim='|'):
    buf=io.StringIO(newline='');writer=csv.writer(buf,delimiter=delim,quotechar='"',doublequote=True,lineterminator='\n',quoting=csv.QUOTE_MINIMAL)
    for row in rows_from(document):
        cells=[]
        for c in COLUMNS:
            x=column_value(row,c)
            if x is None:cells.append('\\N')
            else:
                x=x.replace('\\','\\\\').replace('\r','\\r').replace('\n','\\n')
                if x=='\\N':x='\\\\N'
                cells.append(x)
        writer.writerow(cells)
    return buf.getvalue().encode('utf-8')

NS_XSI='http://www.w3.org/2001/XMLSchema-instance'
register_namespace('xsi',NS_XSI)
def xml(document):
    root=Element('resposta')
    def populate(node,value):
        if value is None:node.set('{'+NS_XSI+'}nil','true')
        elif isinstance(value,dict):
            for k,v in value.items():
                name=str(k).replace(' ','_')
                if not name or name[0].isdigit():name='campo_'+name
                child=SubElement(node,name);populate(child,v)
        elif isinstance(value,list):
            for v in value:populate(SubElement(node,'item'),v)
        elif isinstance(value,bool):node.text='true' if value else 'false'
        else:node.text=str(value)
    populate(root,document)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n'+tostring(root,encoding='utf-8')

def dif(document):
    """Arquivo DIF com campos em ordem do TXT; NULL -> literal especial \\N.
    String usa tipo 1 com aspas duplicadas; número tipo 0 com V.
    """
    records=rows_from(document)
    out=['TABLE','0,1','"RadarBrasil"','VECTORS',f'0,{len(COLUMNS)}','""','TUPLES',f'0,{len(records)+1}','""','DATA','0,0','""']
    def cell(value):
        if value is None:value='\\N'
        value=str(value).replace('"','""').replace('\r','\\r').replace('\n','\\n')
        return ['1,0',f'"{value}"']
    for record in ([{x:x for x in COLUMNS}]+records):
        out+=['-1,0','BOT']
        for c in COLUMNS:
            out+=cell(c if record.get(c)==c else column_value(record,c))
    out+=['-1,0','EOD']
    return ('\n'.join(out)+'\n').encode('utf-8')

def edifact(document):
    """D96A GENRAL, acordo bilateral RadarBrasil v1:
    1 GENRAL por conjunto de meta e por registro; mensagem text-only baseada
    em FTX AAI, payload JSON UTF-8 base64, podendo reconstituir sem perda.
    SEGMENTOS limitados: <=100 grupos FTX por mensagem, 5 x 500 caracteres
    em C108 por FTX; mensagens divididas se necessário.
    """
    recordlist=rows_from(document)
    payload=[]
    meta={k:v for k,v in document.items() if k!='resultado'} if isinstance(document,dict) else {'tipo':'lista'}
    if isinstance(document,dict) and 'resultado' in document:meta['resultado_meta']={k:v for k,v in document['resultado'].items() if not isinstance(v,list)}
    payload.append({'tipo':'meta','payload':meta})
    payload.extend({'tipo':'registro','payload':r} for r in recordlist)
    ref=uuid.uuid4().hex[:12].upper();now=datetime.now(timezone.utc)
    # UNOY:4 = syntax level 4 UTF-8; payload é base64 ASCII, evitando repertório ambíguo
    seg=['UNA:+.? ',f"UNB+UNOY:4+RADARBRASIL+CLIENTE+{now.strftime('%y%m%d')}:{now.strftime('%H%M')}+{ref}'"]
    count=0
    for p in payload:
        encoded=base64.b64encode(jsonb(p).encode('utf-8')).decode('ascii')
        # chunk cada FTX carrega ate 5 elementos de texto com 500 caracteres
        slices=[encoded[i:i+500] for i in range(0,len(encoded),500)] or ['']
        batches=[slices[i:i+500] for i in range(0,len(slices),500)]
        for part,chunks in enumerate(batches):
            count+=1;reference=str(count)
            # codigo Z99 usado como acordo bilateral, não como mensagem oficial customizada
            msg=[f"UNH+{reference}+GENRAL:D:96A:UN'",f"BGM+Z99+{reference}+9'"]
            for i in range(0,len(chunks),5):
                parttext=':'.join(chunks[i:i+5])
                msg.append(f"FTX+AAI+++{parttext}'")
            msg.append(f"UNT+{len(msg)+1}+{reference}'")
            seg.extend(msg)
    seg.append(f"UNZ+{count}+{ref}'")
    return ('\n'.join(seg)+'\n').encode('ascii')

def help_rows(document):
    out=[]
    for p in document['parametros']:
        out.append({'endpoint':'/api/v1/radares','parametro':p['nome'],'tipo':p['tipo'],'obrigatorio':str(p['obrigatorio_em_radares']).lower(),'descricao':p['descricao'],'exemplo':str(p['exemplo'])})
    for ep,desc in document['endpoints'].items():
        out.append({'endpoint':ep,'parametro':'','tipo':'endpoint','obrigatorio':'','descricao':desc,'exemplo':''})
    for col in document['colunas_txt_dif']:
        out.append({'endpoint':'/api/v1/radares','parametro':'COLUNA_'+str(col['posicao'])+'_'+col['nome'],'tipo':col['tipo'],'obrigatorio':'saida','descricao':'Coluna '+str(col['posicao'])+' no TXT/DIF; valores nulos: \\N','exemplo':''})
    return out

def help_tabular(document,fmt,delimiter='|'):
    columns=['endpoint','parametro','tipo','obrigatorio','descricao','exemplo']
    rows=help_rows(document)
    if fmt=='txt':
        buff=io.StringIO(newline=''); w=csv.writer(buff,delimiter=delimiter,lineterminator='\n')
        for row in rows:w.writerow([row.get(c,'') for c in columns])
        return buff.getvalue().encode('utf-8')
    # DIF da ajuda usa seis colunas, não as 32 da consulta de radares.
    lines=['TABLE','0,1','"RadarBrasil-Ajuda"','VECTORS',f'0,{len(columns)}','""','TUPLES',f'0,{len(rows)+1}','""','DATA','0,0','""']
    for row in [dict(zip(columns,columns))]+rows:
        lines+=['-1,0','BOT']
        for col in columns:lines+=['1,0','"'+str(row.get(col,'')).replace('"','""')+'"']
    lines+=['-1,0','EOD']
    return ('\n'.join(lines)+'\n').encode('utf-8')

def serialize(document,fmt,delimiter='|'):
    fmt='edifact' if fmt=='edi' else fmt
    if isinstance(document,dict) and document.get('tipo_resposta')=='ajuda' and fmt in ('txt','dif'):
        return help_tabular(document,fmt,delimiter),MIME[fmt]
    if fmt=='json':return jsonb(document).encode('utf-8'),MIME['json']
    if fmt=='ndjson':
        if isinstance(document,dict) and isinstance(document.get('resultado'),dict):
            content=[{'tipo_registro':'meta',**{k:v for k,v in document.items() if k!='resultado'},'resultado_meta':{k:v for k,v in document['resultado'].items() if not isinstance(v,list)}}]
            content.extend({'tipo_registro':'radar' if 'radares' in document['resultado'] else 'registro','dados':row} for row in rows_from(document))
        else:content=[document]
        return ('\n'.join(jsonb(x) for x in content)+'\n').encode('utf-8'),MIME['ndjson']
    if fmt=='txt':return (txt(document,delimiter) if is_radar_response(document) else generic_txt(document,delimiter)),MIME['txt']
    if fmt=='dif':return (dif(document) if is_radar_response(document) else generic_dif(document)),MIME['dif']
    if fmt=='xml':return xml(document),MIME['xml']
    if fmt=='edifact':return edifact(document),MIME['edifact']
    raise ValueError('Formato não suportado')
