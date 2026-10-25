"""Operacao local pela mesma entrada api.pse, sem sudo e sem outro servico."""
import argparse
import json
import os
import secrets
import sys
from . import db, config, traseiro as tr
from .contexto_api import operacao_local


@operacao_local
def main(argv=None):
    p=argparse.ArgumentParser(description='TRASEIRO DE URSO - rede mesh')
    sub=p.add_subparsers(dest='acao',required=True)
    sub.add_parser('status'); sub.add_parser('sincronizar'); sub.add_parser('inicializar')
    for nome in ('cadastros','fontes'):
        q=sub.add_parser(nome); q.add_argument('--depois',type=int,default=0)
    q=sub.add_parser('ensinar-fonte'); q.add_argument('chave'); q.add_argument('arquivo')
    q=sub.add_parser('decidir'); q.add_argument('id',type=int); q.add_argument('acao',choices=['aprovar','rejeitar']); q.add_argument('--evento',type=int,required=True); q.add_argument('--motivo',required=True)
    q=sub.add_parser('ativar-fonte'); q.add_argument('id',type=int); q.add_argument('--evento',type=int,required=True); q.add_argument('--desativar',action='store_true')
    args=p.parse_args(argv)
    if args.acao=='sincronizar' and not tr.habilitado():
        print(json.dumps({'estado':'desativado'}))
        return 0
    con=db.connect_existing(config.DB_PATH)
    ctx={'escopo':'admin','rotulo':'operador local'}
    try:
        tr.identidade(con)
        if args.acao=='status':
            saida=tr.status(con)
        elif args.acao=='sincronizar':
            from .traseiro_sync import executar
            saida=executar(con)
        elif args.acao=='inicializar':
            arq=tr.arquivo_tokens(); arq.parent.mkdir(parents=True,exist_ok=True)
            valor=secrets.token_urlsafe(36)
            try:
                fd=os.open(arq,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o660)
            except FileExistsError:
                saida={'identidade':tr.identidade(con),'observacao':'Arquivo de tokens existente preservado.'}
            else:
                with os.fdopen(fd,'w') as f:
                    json.dump({'token_rede':valor,'entrada':[],'saida':{}},f,indent=2)
                saida={'identidade':tr.identidade(con),'token_entrada':valor,'observacao':'Guarde o token; nao vai para logs de sincronizacao.'}
        elif args.acao in ('cadastros','fontes'):
            saida={'itens':tr.listar(con,args.acao,args.depois)}
        elif args.acao=='ensinar-fonte':
            arq=tr.caminhos.dentro_dados(args.arquivo,'receita mesh')
            if os.path.getsize(arq)>32768:
                raise ValueError('Receita excede 32 KiB.')
            with open(arq,encoding='utf-8') as f:
                doc=tr.validar_fonte(json.load(f))
            saida={'evento_id':tr.publicar(con,'fonte',args.chave,doc)}
        elif args.acao=='decidir':
            saida=tr.decidir(con,args.id,args.acao,ctx,args.motivo,args.evento)
        else:
            tr.ativar_fonte(con,args.id,not args.desativar,ctx,args.evento); saida={'ok':True}
        print(json.dumps(saida,ensure_ascii=False,indent=2))
        return 1 if saida.get('estado')=='erro' else 0
    except (tr.gov.GovernancaError,ValueError,OSError) as exc:
        print('TRASEIRO DE URSO: '+str(exc),file=sys.stderr)
        return 1
    finally:
        con.close()
