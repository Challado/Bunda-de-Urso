"""DDL relacional portável (78 tabelas), sem extensões espaciais obrigatórias.
Convenção: id#:i=PK, nome!:s=NOT NULL, fonte_id!@fonte.id:i=FK.
As tabelas de domínio guardam valores novos sem migração destrutiva.
"""
import re
from sqlalchemy import (MetaData, Table, Column, String, Text, Integer, BigInteger,
  Numeric, Date, DateTime, Time, Boolean, ForeignKey, CheckConstraint, UniqueConstraint, Index, create_engine, event)
from sqlalchemy.orm import sessionmaker
from .settings import DATABASE_URL

metadata=MetaData()
TABLES={}
TYPES={'i':BigInteger().with_variant(Integer(),'sqlite'),'n':Numeric(15,7),'d':Date(),'dt':DateTime(timezone=True),'tm':Time(), 'b':Boolean(),'s':Text()}
def T(name, spec, checks=(), uniques=()):
    cols=[]
    # Indexed/unique strings must not be unbounded TEXT on MariaDB/MySQL.
    unique_cols={v for group in uniques for v in group}
    for tok in spec.split():
        m=re.fullmatch(r'(\w+)([#*!]*)(?:@([\w.]+))?(?::(\w+))?',tok)
        if not m: raise ValueError(f'{name}: {tok}')
        field,mods,ref,typ=m.groups();typ=typ or 's'
        datatype=(String(int(typ[1:])) if typ.startswith('s') and len(typ)>1
              else String(512 if field=='url_recurso' else 255) if typ=='s' and (field in unique_cols or field in ('numero_serie','valor_normalizado'))
              else TYPES[typ])
        args=[ForeignKey(ref,ondelete='RESTRICT')] if ref else []
        cols.append(Column(field,datatype,*args,primary_key='#' in mods,nullable=('#' not in mods and '!' not in mods)))
    constraints=[CheckConstraint(v,name=f'ck_{name}_{i}') for i,v in enumerate(checks)]
    constraints += [UniqueConstraint(*u,name=f'uq_{name}_{i}') for i,u in enumerate(uniques)]
    tab=Table(name,metadata,*cols,*constraints)
    TABLES[name]=tab
    return tab

T('uf','sigla#:s2 nome!:s',uniques=[('nome',)])
T('municipio','codigo_ibge#:s7 uf_sigla!@uf.sigla:s2 nome!:s')
T('tipo_via','id#:i codigo!:s descricao!:s',uniques=[('codigo',)])
T('via','id#:i tipo_via_id!@tipo_via.id:i codigo!:s nome:s observacao:s',uniques=[('tipo_via_id','codigo')])
T('via_uf','via_id#@via.id:i uf_sigla#@uf.sigla:s2')
T('tipo_organizacao','id#:i codigo!:s descricao!:s',uniques=[('codigo',)])
T('organizacao','id#:i nome!:s tipo_organizacao_id!@tipo_organizacao.id:i municipio_id@municipio.codigo_ibge:s7 cnpj:s site_oficial:s',uniques=[('cnpj',)])
T('papel_organizacao','id#:i codigo!:s descricao!:s',uniques=[('codigo',)])
for name in ('tipo_radar','funcao_equipamento','tecnologia_medicao','situacao_operacional','modalidade_fiscalizacao', 'tipo_medicao','sentido','categoria_veiculo','situacao_operacao','resultado_verificacao','tipo_verificacao','tipo_documento','tipo_identificador','qualidade_posicao'):
    T(name,'id#:i codigo!:s descricao!:s',uniques=[('codigo',)])
T('posicao_geografica','id#:i latitude!:n longitude!:n precisao_metros:n qualidade_posicao_id!@qualidade_posicao.id:i metodo_obtencao:s registro_fonte_id@registro_fonte.id:i',checks=['latitude BETWEEN -90 AND 90','longitude BETWEEN -180 AND 180','precisao_metros IS NULL OR precisao_metros>=0'])
T('endereco','id#:i logradouro:s numero:s bairro:s complemento:s cep:s8 ponto_referencia:s')
T('ponto_fiscalizacao','id#:i posicao_id@posicao_geografica.id:i endereco_id@endereco.id:i municipio_id@municipio.codigo_ibge:s7 via_id@via.id:i km:n tipo_pista:s situacao_operacional_id@situacao_operacional.id:i inicio_operacao:dt data_inativacao:d observacoes:s quantidade_faixas_declarada:i',checks=['km IS NULL OR km>=0','quantidade_faixas_declarada IS NULL OR quantidade_faixas_declarada>=0'])
T('ponto_organizacao','id#:i ponto_id!@ponto_fiscalizacao.id:i organizacao_id!@organizacao.id:i papel_id!@papel_organizacao.id:i inicio_em:dt fim_em:dt',checks=['fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em'])
T('faixa_fiscalizacao','id#:i ponto_id!@ponto_fiscalizacao.id:i numero_faixa:i sentido_id@sentido.id:i sentido_original:s descricao:s',checks=['numero_faixa IS NULL OR numero_faixa>=1'])
T('limite_velocidade','id#:i ponto_id@ponto_fiscalizacao.id:i faixa_id@faixa_fiscalizacao.id:i categoria_veiculo_id!@categoria_veiculo.id:i velocidade_kmh:n vigencia_inicio:dt vigencia_fim:dt registro_fonte_id@registro_fonte.id:i',checks=['(ponto_id IS NULL) <> (faixa_id IS NULL)','velocidade_kmh>0 AND velocidade_kmh<=350','vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio'])
T('regime_fiscalizacao','id#:i ponto_id!@ponto_fiscalizacao.id:i modalidade_id!@modalidade_fiscalizacao.id:i tipo_medicao_id@tipo_medicao.id:i situacao_operacional_id@situacao_operacional.id:i inicio_em:dt fim_em:dt fonte_registro_id@registro_fonte.id:i',checks=['fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em'])
T('trecho_elegivel','id#:i via_id!@via.id:i km_inicio:n km_fim:n sentido_id@sentido.id:i criterio_inclusao:s vigencia_inicio:d vigencia_fim:d situacao:s registro_fonte_id@registro_fonte.id:i',checks=['km_inicio IS NULL OR km_inicio>=0','km_fim IS NULL OR km_fim>=0','km_inicio IS NULL OR km_fim IS NULL OR km_fim>=km_inicio','vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio'])
T('trecho_municipio','trecho_id#@trecho_elegivel.id:i municipio_id#@municipio.codigo_ibge:s7')
T('trecho_vertice','trecho_id#@trecho_elegivel.id:i ordem#:i posicao_id!@posicao_geografica.id:i',checks=['ordem>=0'])
T('modelo_equipamento','id#:i fabricante_id@organizacao.id:i nome_modelo!:s tecnologia_id@tecnologia_medicao.id:i registro_aprovacao_inmetro:s portaria_aprovacao_modelo:s')
T('equipamento','id#:i modelo_id@modelo_equipamento.id:i tipo_radar_id!@tipo_radar.id:i numero_serie:s ano_fabricacao:i observacoes:s',checks=['ano_fabricacao IS NULL OR ano_fabricacao BETWEEN 1900 AND 2100'])
T('instalacao','id#:i ponto_id!@ponto_fiscalizacao.id:i equipamento_id!@equipamento.id:i funcao_equipamento_id@funcao_equipamento.id:i situacao_operacional_id@situacao_operacional.id:i inicio_em:dt fim_em:dt data_inicio_autuacao:d data_inicio_educativo:d observacoes:s',checks=['fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em'])
# Velocidade nominal publicada pelo Inmetro pertence à configuração metrológica
# do instrumento/faixa; não equivale automaticamente à velocidade regulamentada.
T('faixa_medicao_equipamento','id#:i equipamento_id!@equipamento.id:i registro_fonte_id!@registro_fonte.id:i numero_faixa:i sentido_id@sentido.id:i velocidade_nominal_kmh:n',checks=['numero_faixa IS NULL OR numero_faixa BETWEEN 1 AND 99','velocidade_nominal_kmh IS NULL OR (velocidade_nominal_kmh>0 AND velocidade_nominal_kmh<=350)'])
T('instalacao_faixa','instalacao_id#@instalacao.id:i faixa_id#@faixa_fiscalizacao.id:i')
T('operacao_fiscalizacao','id#:i modalidade_id!@modalidade_fiscalizacao.id:i situacao_operacao_id!@situacao_operacao.id:i organizacao_id@organizacao.id:i ponto_id@ponto_fiscalizacao.id:i trecho_id@trecho_elegivel.id:i posicao_id@posicao_geografica.id:i via_id@via.id:i municipio_id@municipio.codigo_ibge:s7 km:n descricao:s inicio_em:dt fim_em:dt fuso_original:s publicado_em:dt registro_fonte_id@registro_fonte.id:i',checks=['fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em','km IS NULL OR km>=0'])
T('operacao_equipamento','operacao_id#@operacao_fiscalizacao.id:i equipamento_id#@equipamento.id:i')
T('operacao_faixa','operacao_id#@operacao_fiscalizacao.id:i faixa_id#@faixa_fiscalizacao.id:i')
T('operacao_recorrencia','id#:i operacao_id!@operacao_fiscalizacao.id:i regra_repeticao!:s fuso_horario:s data_inicio:d data_fim:d',checks=['data_fim IS NULL OR data_inicio IS NULL OR data_fim>=data_inicio'])
T('recorrencia_dia','recorrencia_id#@operacao_recorrencia.id:i dia_semana#:i hora_inicio#:tm hora_fim:tm',checks=['dia_semana BETWEEN 1 AND 7'])
T('identificador_externo','id#:i fonte_id!@fonte.id:i tipo_identificador_id!@tipo_identificador.id:i valor!:s valor_normalizado!:s',uniques=[('fonte_id','tipo_identificador_id','valor_normalizado')])
for ent,col,table in [('ponto','ponto_id','ponto_fiscalizacao'),('equipamento','equipamento_id','equipamento'),('operacao','operacao_id','operacao_fiscalizacao')]:
    T(f'identificador_{ent}',f'id#:i identificador_id!@identificador_externo.id:i {col}!@{table}.id:i vigencia_inicio:dt vigencia_fim:dt')
T('verificacao_metrologica','id#:i equipamento_id!@equipamento.id:i tipo_verificacao_id!@tipo_verificacao.id:i resultado_id!@resultado_verificacao.id:i orgao_executor_id@organizacao.id:i data_verificacao:d validade_ate:d numero_certificado:s norma_aplicada:s observacoes:s registro_fonte_id@registro_fonte.id:i',checks=['validade_ate IS NULL OR data_verificacao IS NULL OR validade_ate>=data_verificacao'])
T('documento','id#:i tipo_documento_id!@tipo_documento.id:i codigo_documento:s titulo:s url:s orgao_emissor_id@organizacao.id:i data_emissao:d validade_ate:d hash_conteudo:s descricao:s',checks=['validade_ate IS NULL OR data_emissao IS NULL OR validade_ate>=data_emissao'])
for ent,field,table in [('ponto','ponto_id','ponto_fiscalizacao'),('equipamento','equipamento_id','equipamento'),('verificacao','verificacao_id','verificacao_metrologica'),('operacao','operacao_id','operacao_fiscalizacao'),('trecho','trecho_id','trecho_elegivel')]:
    T(f'documento_{ent}',f'documento_id#@documento.id:i {field}#@{table}.id:i')
T('observacao_trafego','id#:i registro_fonte_id!@registro_fonte.id:i equipamento_id@equipamento.id:i ponto_id@ponto_fiscalizacao.id:i faixa_id@faixa_fiscalizacao.id:i categoria_veiculo_id@categoria_veiculo.id:i sentido_id@sentido.id:i instante_observacao:dt data_observacao:d velocidade_publicada:s velocidade_kmh:n volume_total:i',checks=['volume_total IS NULL OR volume_total>=0','velocidade_kmh IS NULL OR velocidade_kmh>=0'])
T('fonte','id#:i organizacao_id!@organizacao.id:i natureza_id!@natureza_fonte.id:i nome!:s url_institucional!:s esfera!:s licenca:s documentacao_url:s situacao!:s periodicidade_declarada:s observacoes:s',checks=["esfera IN ('federal','estadual','municipal','distrital','outra','desconhecida')"],uniques=[('nome',)])
T('cobertura_fonte','id#:i fonte_id!@fonte.id:i tipo_abrangencia!:s uf_sigla@uf.sigla:s2 municipio_id@municipio.codigo_ibge:s7 via_id@via.id:i vigencia_inicio:d vigencia_fim:d confirmada!:b',checks=["tipo_abrangencia IN ('nacional','estadual','municipal','rodoviaria','desconhecida')",'vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio',"tipo_abrangencia<>'municipal' OR municipio_id IS NOT NULL","tipo_abrangencia<>'estadual' OR uf_sigla IS NOT NULL","tipo_abrangencia<>'rodoviaria' OR via_id IS NOT NULL"])
T('recurso_fonte','id#:i fonte_id!@fonte.id:i nome!:s url_recurso!:s formato_origem!:s dicionario_url:s periodicidade_segundos:i ativo!:b tamanho_maximo_bytes:i status_integracao!:s',checks=['periodicidade_segundos IS NULL OR periodicidade_segundos>0','tamanho_maximo_bytes IS NULL OR tamanho_maximo_bytes>0'],uniques=[('fonte_id','url_recurso')])
T('artefato_coleta','id#:i recurso_id!@recurso_fonte.id:i hash_sha256!:s64 caminho_cache!:s bytes_arquivo!:i tipo_mime:s etag:s last_modified_http:s data_publicacao_origem:dt baixado_em!:dt validado_em:dt resultado_validacao!:s',checks=['bytes_arquivo>=0'],uniques=[('recurso_id','hash_sha256')])
T('execucao_coleta','id#:i recurso_id!@recurso_fonte.id:i artefato_id@artefato_coleta.id:i iniciada_em!:dt terminada_em:dt status!:s http_status:i tentativas!:i linhas_recebidas:i linhas_validas:i linhas_rejeitadas:i registros_criados:i registros_alterados:i erro_codigo:s erro_detalhe:s',checks=['tentativas>=0','terminada_em IS NULL OR terminada_em>=iniciada_em','http_status IS NULL OR http_status BETWEEN 100 AND 599'])
T('registro_fonte','id#:i artefato_id!@artefato_coleta.id:i numero_ordem!:i identificador_na_fonte:s payload_original!:s hash_registro!:s64 status_validacao!:s',checks=['numero_ordem>=0'],uniques=[('artefato_id','numero_ordem')])
T('erro_validacao','id#:i execucao_id@execucao_coleta.id:i registro_id@registro_fonte.id:i campo_origem:s codigo_erro!:s descricao!:s severidade!:s registrado_em!:dt',checks=['execucao_id IS NOT NULL OR registro_id IS NOT NULL'])
T('snapshot_publicado','id#:i anterior_id@snapshot_publicado.id:i publicado_em!:dt status!:s resumo_validacao:s identificador_versao!:s',uniques=[('identificador_versao',)])
T('snapshot_recurso','snapshot_id#@snapshot_publicado.id:i recurso_id#@recurso_fonte.id:i artefato_id@artefato_coleta.id:i')
for ent,field,table in [('ponto','ponto_id','ponto_fiscalizacao'),('equipamento','equipamento_id','equipamento'),('operacao','operacao_id','operacao_fiscalizacao'),('trecho','trecho_id','trecho_elegivel'),('verificacao','verificacao_id','verificacao_metrologica')]:
    T(f'vinculo_registro_{ent}',f'registro_id#@registro_fonte.id:i {field}#@{table}.id:i'+(' confianca:n decisao_id@decisao_duplicidade.id:i' if ent!='verificacao' else ''),checks=[] if ent=='verificacao' else ['confianca IS NULL OR confianca BETWEEN 0 AND 1'])
T('regra_deduplicacao','id#:i versao!:s descricao!:s configuracao_serializada!:s inicio_validade!:dt',uniques=[('versao',)])
T('candidato_duplicidade','id#:i registro_a_id!@registro_fonte.id:i registro_b_id!@registro_fonte.id:i regra_id!@regra_deduplicacao.id:i score:n estado!:s evidencias_resumo:s gerado_em!:dt',checks=['registro_a_id<registro_b_id','score IS NULL OR score BETWEEN 0 AND 1'],uniques=[('registro_a_id','registro_b_id','regra_id')])
T('decisao_duplicidade','id#:i candidato_id!@candidato_duplicidade.id:i decisao!:s fundamentacao!:s ator!:s decidida_em!:dt revertida_em:dt observacoes:s',checks=["decisao IN ('unificar','manter_separados','revisar')"])
T('catalogo_campo','id#:i entidade_logica!:s nome_campo!:s tipo_dado!:s descricao!:s',uniques=[('entidade_logica','nome_campo')])
T('valor_observado','id#:i registro_id!@registro_fonte.id:i campo_id!@catalogo_campo.id:i valor_original:s valor_normalizado:s linha_origem:s pontuacao_qualidade:n',checks=['pontuacao_qualidade IS NULL OR pontuacao_qualidade BETWEEN 0 AND 1'])
T('decisao_valor_canonico','id#:i valor_observado_id!@valor_observado.id:i ponto_id@ponto_fiscalizacao.id:i equipamento_id@equipamento.id:i instalacao_id@instalacao.id:i operacao_id@operacao_fiscalizacao.id:i trecho_id@trecho_elegivel.id:i verificacao_id@verificacao_metrologica.id:i status_decisao!:s justificativa:s decidida_em!:dt',checks=['(CASE WHEN ponto_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN equipamento_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN instalacao_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN operacao_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN trecho_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN verificacao_id IS NOT NULL THEN 1 ELSE 0 END)=1'])
T('alerta_operacional','id#:i recurso_id@recurso_fonte.id:i execucao_id@execucao_coleta.id:i snapshot_id@snapshot_publicado.id:i chave_incidente!:s nivel!:s status!:s mensagem!:s primeira_ocorrencia!:dt ultima_ocorrencia!:dt resolvido_em:dt ocorrencias!:i',checks=['ocorrencias>=1','ultima_ocorrencia>=primeira_ocorrencia'])
# Entidades T75..T77, como especificação v1.1
T('natureza_fonte','id#:i codigo!:s nome!:s descricao:s',checks=["codigo IN ('oficial','comunitaria','academica','privada','outra','desconhecida')"],uniques=[('codigo',)])
T('licenca_dados','id#:i codigo!:s nome!:s url_licenca:s versao:s requisitos_atribuicao:s observacoes:s',uniques=[('codigo',)])
T('recurso_licenca','id#:i recurso_id!@recurso_fonte.id:i licenca_id!@licenca_dados.id:i vigencia_inicio:d vigencia_fim:d observacoes:s',checks=['vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio'])

# Resolvedor geografico v1.4 - referencias e candidatos NORMALIZADOS; migracao aditiva.
T('geo_fonte','id#:i nome!:s255 tipo!:s20 url:s registrado_em!:dt',checks=["tipo IN ('oficial','comunitaria')"],uniques=[('nome',)])
T('geo_trecho_calibrado','id#:i via_id!@via.id:i fonte_geo_id!@geo_fonte.id:i km_inicio!:n km_fim!:n uf@uf.sigla:s2 hash_origem!:s64 referencia:s importado_em!:dt',checks=['km_inicio>=0','km_fim>km_inicio'],uniques=[('hash_origem',)])
T('geo_trecho_vertice','trecho_id#@geo_trecho_calibrado.id:i ordem#:i latitude!:n longitude!:n',checks=['ordem>=0','latitude BETWEEN -90 AND 90','longitude BETWEEN -180 AND 180'])
T('geo_candidato','id#:i ponto_id@ponto_fiscalizacao.id:i equipamento_id@equipamento.id:i posicao_id!@posicao_geografica.id:i fonte_geo_id!@geo_fonte.id:i metodo!:s40 status!:s20 score!:n referencia_externa:s255 evidencia!:s detalhe_json:s hash_identidade!:s64 criado_em!:dt',checks=["status IN ('revisar','aprovado','rejeitado')",'score BETWEEN 0 AND 1','(ponto_id IS NOT NULL) <> (equipamento_id IS NOT NULL)'],uniques=[('hash_identidade',)])
T('geo_decisao','id#:i candidato_id!@geo_candidato.id:i decisao!:s20 ator!:s justificativa!:s decidida_em!:dt',checks=["decisao IN ('aprovado','rejeitado')"])
Index('ix_geo_candidato_ponto',TABLES['geo_candidato'].c.ponto_id,TABLES['geo_candidato'].c.status)
Index('ix_geo_candidato_eq',TABLES['geo_candidato'].c.equipamento_id,TABLES['geo_candidato'].c.status)
Index('ix_geo_trecho_km',TABLES['geo_trecho_calibrado'].c.via_id,TABLES['geo_trecho_calibrado'].c.km_inicio,TABLES['geo_trecho_calibrado'].c.km_fim)

Index('ix_posicao_lat_lon',TABLES['posicao_geografica'].c.latitude,TABLES['posicao_geografica'].c.longitude)
Index('ix_ponto_via_km',TABLES['ponto_fiscalizacao'].c.via_id,TABLES['ponto_fiscalizacao'].c.km)
Index('ix_equip_serie',TABLES['equipamento'].c.numero_serie)
Index('ix_exec_recurso_inicio',TABLES['execucao_coleta'].c.recurso_id,TABLES['execucao_coleta'].c.iniciada_em)
Index('ix_registro_hash',TABLES['registro_fonte'].c.hash_registro)

ENGINE=create_engine(DATABASE_URL,pool_pre_ping=True,connect_args={'timeout':30} if DATABASE_URL.startswith('sqlite:') else {})
if ENGINE.dialect.name=='sqlite':
    @event.listens_for(ENGINE,'connect')
    def enable_fk(dbapi_connection, connection_record):
        cursor=dbapi_connection.cursor();cursor.execute('PRAGMA foreign_keys=ON');cursor.execute('PRAGMA busy_timeout=30000');cursor.close()
Session=sessionmaker(ENGINE,future=True)

def init_db():
    metadata.create_all(ENGINE)
    return len(TABLES)

def get_code(session,name,code,description=None):
    from sqlalchemy import select
    t=TABLES[name];v=session.execute(select(t.c.id).where(t.c.codigo==code)).scalar_one_or_none()
    if v is None:
        return session.execute(t.insert().values(codigo=code,descricao=description or code)).inserted_primary_key[0]
    return v

def seed_domains(session):
    vals={'tipo_via':['federal','estadual','municipal','urbana','outra','desconhecida'],
      'tipo_organizacao':['orgao_publico','concessionaria','fabricante','laboratorio','operador_privado','outro','desconhecido'],
      'papel_organizacao':['fiscalizador','concessionaria','operador','mantenedor','fabricante','verificador'],
      'tipo_radar':['fixo','portatil','movel','desconhecido'],
      'funcao_equipamento':['controlador','redutor','misto','outro','desconhecido'],
      'tecnologia_medicao':['radar','laser','indutivo','outro','desconhecido'],
      'situacao_operacional':['ativo','inativo','manutencao','em_instalacao','suspenso','desconhecido'],
      'modalidade_fiscalizacao':['permanente','pontual','itinerante','por_trecho','desconhecida'],
      'tipo_medicao':['velocidade_instantanea','velocidade_media_trecho','outra','desconhecida'],
      'sentido':['crescente','decrescente','ambos','sentido_geografico','desconhecido'],
      'categoria_veiculo':['leves','pesados','geral','categoria_original','desconhecida'],
      'situacao_operacao':['planejada','confirmada','encerrada','cancelada','desconhecida'],
      'resultado_verificacao':['conforme','nao_conforme','outro','desconhecido'],
      'tipo_verificacao':['inicial','periodica','apos_reparo','outra','desconhecida'],
      'tipo_documento':['estudo_tecnico','certificado','portaria','relatorio','edital','outro'],
      'tipo_identificador':['id_orgao','codigo_equipamento','serie','codigo_et','cadastro_local','outro'],
      'qualidade_posicao':['oficial','oficial_imprecisa','inferida','estimada','conflitante','desconhecida'],
      }
    for code in ('oficial','comunitaria','academica','privada','outra','desconhecida'):
        if not session.execute(TABLES['natureza_fonte'].select().where(TABLES['natureza_fonte'].c.codigo==code)).first():
            session.execute(TABLES['natureza_fonte'].insert().values(codigo=code,nome=code))
    for key,values in vals.items():
        for v in values:get_code(session,key,v)
    for code,nome in [('AC','Acre'),('AL','Alagoas'),('AP','Amapá'),('AM','Amazonas'),('BA','Bahia'),('CE','Ceará'),('DF','Distrito Federal'),('ES','Espírito Santo'),('GO','Goiás'),('MA','Maranhão'),('MT','Mato Grosso'),('MS','Mato Grosso do Sul'),('MG','Minas Gerais'),('PA','Pará'),('PB','Paraíba'),('PR','Paraná'),('PE','Pernambuco'),('PI','Piauí'),('RJ','Rio de Janeiro'),('RN','Rio Grande do Norte'),('RS','Rio Grande do Sul'),('RO','Rondônia'),('RR','Roraima'),('SC','Santa Catarina'),('SP','São Paulo'),('SE','Sergipe'),('TO','Tocantins')]:
        if not session.execute(TABLES['uf'].select().where(TABLES['uf'].c.sigla==code)).first():session.execute(TABLES['uf'].insert().values(sigla=code,nome=nome))
    if not session.execute(TABLES['regra_deduplicacao'].select()).first():
        from datetime import datetime,timezone
        session.execute(TABLES['regra_deduplicacao'].insert().values(versao='1.0',descricao='match conservador por identidade, serie e coordenada',configuracao_serializada='{"automatico":"somente alta certeza"}',inicio_validade=datetime.now(timezone.utc)))

if __name__=='__main__':
    init_db(); print(len(TABLES))
