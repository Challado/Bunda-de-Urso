"""Rotas mesh e gestao; sincronizacao externa acontece somente no cron."""
import urllib.parse
from core import traseiro as tr, governanca as gov


def atender(conn,caminho,metodo,environ,raw):
    from .nucleo import _corpo_json, _resp, _gov_erro
    publico='/api/v1/intercambio'
    gestao='/api/v1/gestao/traseiro'
    administrativo=caminho==gestao or caminho.startswith(gestao+'/')
    if not administrativo and not (caminho==publico or caminho.startswith(publico+'/')):
        return None
    local=consultante=None
    try:
        partes=caminho[len(gestao if administrativo else publico):].strip('/').split('/')
        if administrativo:
            ctx=gov.contexto_autenticacao(conn,environ); gov.exigir(ctx,'contribuidor')
        else:
            tr.autenticar(environ)
            local=tr.identidade(conn)
            consultante=tr.ler_cabecalho(environ)
        if metodo not in ('GET','POST','PATCH'):
            tr.erro(405,'metodo_invalido','Metodo nao permitido na rede.')
        if metodo!='GET':
            if environ.get('CONTENT_TYPE','').split(';')[0].strip()!='application/json' or environ.get('HTTP_SEC_FETCH_SITE')=='cross-site':
                tr.erro(403,'origem_invalida','Envie JSON pelo painel ou pelo protocolo mesh.')
            if len(raw)>tr.numero('max_bytes'):
                tr.erro(413,'corpo_grande','Lote mesh excede max_bytes.')
            dados=_corpo_json(raw)
            if not isinstance(dados,dict):
                tr.erro(422,'corpo_invalido','Envie um objeto JSON.')
        else:
            dados={}
        local=tr.identidade(conn)
        query=urllib.parse.parse_qs(environ.get('QUERY_STRING',''))
        try:
            depois=int(query.get('depois',['0'])[0]); limite=int(query.get('limite',[str(tr.numero('lote'))])[0])
            if depois<0 or not 1<=limite<=1000:
                raise ValueError()
        except (ValueError,TypeError):
            tr.erro(422,'cursor_invalido','Use depois>=0 e limite entre 1 e 1000.')
        if administrativo:
            if partes==[''] and metodo=='GET':
                resultado=tr.status(conn)
            elif partes[0] in ('cadastros','fontes') and len(partes)==1 and metodo=='GET':
                itens=tr.listar(conn,partes[0],depois,limite)
                resultado={'itens':itens,'depois':itens[-1]['id'] if itens else depois}
            elif partes==['fontes'] and metodo=='POST':
                gov.exigir(ctx,'admin'); receita=tr.validar_fonte(dados.get('receita'))
                chave=dados.get('chave')
                if not isinstance(chave,str):
                    tr.erro(422,'chave_invalida','Informe uma chave estavel para a fonte.')
                resultado={'evento_id':tr.publicar(conn,'fonte',chave,receita)}
            elif len(partes)==2 and partes[0]=='cadastros' and metodo=='POST':
                resultado=tr.decidir(conn,int(partes[1]),dados.get('acao'),ctx,dados.get('motivo'),dados.get('evento_id'))
            elif len(partes)==2 and partes[0]=='fontes' and metodo=='PATCH':
                tr.ativar_fonte(conn,int(partes[1]),dados.get('ativo'),ctx,dados.get('evento_id')); resultado={'ok':True}
            elif len(partes)==2 and partes[0]=='instancias' and metodo=='PATCH':
                gov.exigir(ctx,'admin')
                ident=tr.id_uuid(partes[1]); estado=dados.get('estado')
                if estado not in ('ativo','inativo','bloqueado'):
                    tr.erro(422,'estado_invalido','Use ativo, inativo ou bloqueado.')
                if not conn.execute('SELECT 1 FROM TRASEIRO_INSTANCIA WHERE uuid=?',(ident,)).fetchone():
                    tr.erro(404,'instancia_ausente','Instancia nao cadastrada.')
                conn.execute('UPDATE TRASEIRO_INSTANCIA SET estado=?,falhas=0,ultima_tentativa=NULL WHERE uuid=?',(estado,ident)); conn.commit()
                resultado={'ok':True}
            else:
                tr.erro(404,'rota_ausente','Rota de gestao mesh nao encontrada.')
        else:
            info=tr.validar_informacoes(consultante.get('configuracao') if isinstance(consultante,dict) else None)
            if tr.pausada(info):
                tr.erro(403,'consultante_parado','Uma instancia declarada parada nao pode consultar a rede. Cancele a parada e volte a aceitar consultas.')
            par=tr.registrar_instancia(conn,consultante)
            from core.traseiro_sync import contato, inativar_vencidas
            if partes==['identidade'] and metodo=='GET':
                resultado=local
            elif partes==['trocar'] and metodo=='POST':
                resultado=trocar(conn,par,local,dados)
                contato(conn,par['uuid']); inativar_vencidas(conn)
            else:
                tr.erro(404,'rota_ausente','Use identidade ou trocar no protocolo mesh.')
            return _resp(tr.intercambio.responder(local,consultante,resultado))
        return _resp({'sucesso':True,'resultado':resultado})
    except gov.GovernancaError as exc:
        status,headers,body=_gov_erro(exc)
        if not administrativo and local is not None and consultante is not None:
            body['rede']={'consultado':local,'consultante':consultante}
        return status,headers,body
    except (ValueError,TypeError,OverflowError):
        return _gov_erro(gov.GovernancaError(422,'traseiro_parametro_invalido','Parametros da rede invalidos.'))


def trocar(conn,par,local,dados):
    try:
        tr.intercambio.validar_pedido(dados,local)
    except tr.intercambio.ErroIntercambio as exc:
        tr.erro(422,'pedido_invalido',str(exc))
    intervalo=local['configuracao']['intervalo_segundos']
    ultima=par['ultima_consulta_recebida']
    if tr.pausada(local['configuracao']):
        return {'pausado':True,'retornar_em_segundos':local['configuracao']['retornar_em_segundos']}
    if ultima and (tr.datetime.datetime.now(tr.datetime.timezone.utc)-tr.datetime.datetime.fromisoformat(ultima)).total_seconds()<intervalo:
        return {'adiado':True,'intervalo_segundos':intervalo}
    cursor=dados.get('depois',0); limite=dados.get('limite',tr.numero('lote'))
    if type(cursor) is not int or not 0<=cursor<2**63 or type(limite) is not int or not 1<=limite<=1000:
        tr.erro(422,'cursor_invalido','Cursor/limite invalidos.')
    # Reserva atomica impede duas chamadas simultaneas de furarem o intervalo.
    atualizada=conn.execute('UPDATE TRASEIRO_INSTANCIA SET ultima_consulta_recebida=? WHERE uuid=? AND ultima_consulta_recebida IS ?',
        (tr.agora(),par['uuid'],ultima)).rowcount
    conn.commit()
    if not atualizada:
        return {'adiado':True,'intervalo_segundos':intervalo}
    recebidos=tr.receber(conn,dados.get('eventos'),par['uuid'])
    orcamento=max(8192,(min(par['max_bytes'],tr.numero('max_bytes'))-16384)//2)
    pagina=tr.pagina(conn,cursor,limite,max_bytes=orcamento+8192,tipos=tr.tipos_par(conn,par['uuid']))
    return {**recebidos,**pagina,'instancias':tr.instancias_publicas(conn,max_bytes=orcamento)}
