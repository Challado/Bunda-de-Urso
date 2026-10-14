-- RadarBrasil v1.4 DDL SQLite: gerado do MODELO REAL, 83 entidades.
-- Utilize radarbrasil.collector init para SQLite/PostgreSQL/MariaDB e outras engines configuradas.

-- table: alerta_operacional
CREATE TABLE alerta_operacional (
	id INTEGER NOT NULL, 
	recurso_id INTEGER, 
	execucao_id INTEGER, 
	snapshot_id INTEGER, 
	chave_incidente TEXT NOT NULL, 
	nivel TEXT NOT NULL, 
	status TEXT NOT NULL, 
	mensagem TEXT NOT NULL, 
	primeira_ocorrencia DATETIME NOT NULL, 
	ultima_ocorrencia DATETIME NOT NULL, 
	resolvido_em DATETIME, 
	ocorrencias INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_alerta_operacional_0 CHECK (ocorrencias>=1), 
	CONSTRAINT ck_alerta_operacional_1 CHECK (ultima_ocorrencia>=primeira_ocorrencia), 
	FOREIGN KEY(recurso_id) REFERENCES recurso_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(execucao_id) REFERENCES execucao_coleta (id) ON DELETE RESTRICT, 
	FOREIGN KEY(snapshot_id) REFERENCES snapshot_publicado (id) ON DELETE RESTRICT
);

-- table: artefato_coleta
CREATE TABLE artefato_coleta (
	id INTEGER NOT NULL, 
	recurso_id INTEGER NOT NULL, 
	hash_sha256 VARCHAR(64) NOT NULL, 
	caminho_cache TEXT NOT NULL, 
	bytes_arquivo INTEGER NOT NULL, 
	tipo_mime TEXT, 
	etag TEXT, 
	last_modified_http TEXT, 
	data_publicacao_origem DATETIME, 
	baixado_em DATETIME NOT NULL, 
	validado_em DATETIME, 
	resultado_validacao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_artefato_coleta_0 CHECK (bytes_arquivo>=0), 
	CONSTRAINT uq_artefato_coleta_0 UNIQUE (recurso_id, hash_sha256), 
	FOREIGN KEY(recurso_id) REFERENCES recurso_fonte (id) ON DELETE RESTRICT
);

-- table: candidato_duplicidade
CREATE TABLE candidato_duplicidade (
	id INTEGER NOT NULL, 
	registro_a_id INTEGER NOT NULL, 
	registro_b_id INTEGER NOT NULL, 
	regra_id INTEGER NOT NULL, 
	score NUMERIC(15, 7), 
	estado TEXT NOT NULL, 
	evidencias_resumo TEXT, 
	gerado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_candidato_duplicidade_0 CHECK (registro_a_id<registro_b_id), 
	CONSTRAINT ck_candidato_duplicidade_1 CHECK (score IS NULL OR score BETWEEN 0 AND 1), 
	CONSTRAINT uq_candidato_duplicidade_0 UNIQUE (registro_a_id, registro_b_id, regra_id), 
	FOREIGN KEY(registro_a_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_b_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(regra_id) REFERENCES regra_deduplicacao (id) ON DELETE RESTRICT
);

-- table: catalogo_campo
CREATE TABLE catalogo_campo (
	id INTEGER NOT NULL, 
	entidade_logica VARCHAR(255) NOT NULL, 
	nome_campo VARCHAR(255) NOT NULL, 
	tipo_dado TEXT NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_catalogo_campo_0 UNIQUE (entidade_logica, nome_campo)
);

-- table: categoria_veiculo
CREATE TABLE categoria_veiculo (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_categoria_veiculo_0 UNIQUE (codigo)
);

-- table: cobertura_fonte
CREATE TABLE cobertura_fonte (
	id INTEGER NOT NULL, 
	fonte_id INTEGER NOT NULL, 
	tipo_abrangencia TEXT NOT NULL, 
	uf_sigla VARCHAR(2), 
	municipio_id VARCHAR(7), 
	via_id INTEGER, 
	vigencia_inicio DATE, 
	vigencia_fim DATE, 
	confirmada BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_cobertura_fonte_0 CHECK (tipo_abrangencia IN ('nacional','estadual','municipal','rodoviaria','desconhecida')), 
	CONSTRAINT ck_cobertura_fonte_1 CHECK (vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio), 
	CONSTRAINT ck_cobertura_fonte_2 CHECK (tipo_abrangencia<>'municipal' OR municipio_id IS NOT NULL), 
	CONSTRAINT ck_cobertura_fonte_3 CHECK (tipo_abrangencia<>'estadual' OR uf_sigla IS NOT NULL), 
	CONSTRAINT ck_cobertura_fonte_4 CHECK (tipo_abrangencia<>'rodoviaria' OR via_id IS NOT NULL), 
	FOREIGN KEY(fonte_id) REFERENCES fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(uf_sigla) REFERENCES uf (sigla) ON DELETE RESTRICT, 
	FOREIGN KEY(municipio_id) REFERENCES municipio (codigo_ibge) ON DELETE RESTRICT, 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT
);

-- table: decisao_duplicidade
CREATE TABLE decisao_duplicidade (
	id INTEGER NOT NULL, 
	candidato_id INTEGER NOT NULL, 
	decisao TEXT NOT NULL, 
	fundamentacao TEXT NOT NULL, 
	ator TEXT NOT NULL, 
	decidida_em DATETIME NOT NULL, 
	revertida_em DATETIME, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_decisao_duplicidade_0 CHECK (decisao IN ('unificar','manter_separados','revisar')), 
	FOREIGN KEY(candidato_id) REFERENCES candidato_duplicidade (id) ON DELETE RESTRICT
);

-- table: decisao_valor_canonico
CREATE TABLE decisao_valor_canonico (
	id INTEGER NOT NULL, 
	valor_observado_id INTEGER NOT NULL, 
	ponto_id INTEGER, 
	equipamento_id INTEGER, 
	instalacao_id INTEGER, 
	operacao_id INTEGER, 
	trecho_id INTEGER, 
	verificacao_id INTEGER, 
	status_decisao TEXT NOT NULL, 
	justificativa TEXT, 
	decidida_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_decisao_valor_canonico_0 CHECK ((CASE WHEN ponto_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN equipamento_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN instalacao_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN operacao_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN trecho_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN verificacao_id IS NOT NULL THEN 1 ELSE 0 END)=1), 
	FOREIGN KEY(valor_observado_id) REFERENCES valor_observado (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(instalacao_id) REFERENCES instalacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT, 
	FOREIGN KEY(verificacao_id) REFERENCES verificacao_metrologica (id) ON DELETE RESTRICT
);

-- table: documento
CREATE TABLE documento (
	id INTEGER NOT NULL, 
	tipo_documento_id INTEGER NOT NULL, 
	codigo_documento TEXT, 
	titulo TEXT, 
	url TEXT, 
	orgao_emissor_id INTEGER, 
	data_emissao DATE, 
	validade_ate DATE, 
	hash_conteudo TEXT, 
	descricao TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_documento_0 CHECK (validade_ate IS NULL OR data_emissao IS NULL OR validade_ate>=data_emissao), 
	FOREIGN KEY(tipo_documento_id) REFERENCES tipo_documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(orgao_emissor_id) REFERENCES organizacao (id) ON DELETE RESTRICT
);

-- table: documento_equipamento
CREATE TABLE documento_equipamento (
	documento_id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	PRIMARY KEY (documento_id, equipamento_id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT
);

-- table: documento_operacao
CREATE TABLE documento_operacao (
	documento_id INTEGER NOT NULL, 
	operacao_id INTEGER NOT NULL, 
	PRIMARY KEY (documento_id, operacao_id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: documento_ponto
CREATE TABLE documento_ponto (
	documento_id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	PRIMARY KEY (documento_id, ponto_id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: documento_trecho
CREATE TABLE documento_trecho (
	documento_id INTEGER NOT NULL, 
	trecho_id INTEGER NOT NULL, 
	PRIMARY KEY (documento_id, trecho_id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT
);

-- table: documento_verificacao
CREATE TABLE documento_verificacao (
	documento_id INTEGER NOT NULL, 
	verificacao_id INTEGER NOT NULL, 
	PRIMARY KEY (documento_id, verificacao_id), 
	FOREIGN KEY(documento_id) REFERENCES documento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(verificacao_id) REFERENCES verificacao_metrologica (id) ON DELETE RESTRICT
);

-- table: endereco
CREATE TABLE endereco (
	id INTEGER NOT NULL, 
	logradouro TEXT, 
	numero TEXT, 
	bairro TEXT, 
	complemento TEXT, 
	cep VARCHAR(8), 
	ponto_referencia TEXT, 
	PRIMARY KEY (id)
);

-- table: equipamento
CREATE TABLE equipamento (
	id INTEGER NOT NULL, 
	modelo_id INTEGER, 
	tipo_radar_id INTEGER NOT NULL, 
	numero_serie VARCHAR(255), 
	ano_fabricacao INTEGER, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_equipamento_0 CHECK (ano_fabricacao IS NULL OR ano_fabricacao BETWEEN 1900 AND 2100), 
	FOREIGN KEY(modelo_id) REFERENCES modelo_equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tipo_radar_id) REFERENCES tipo_radar (id) ON DELETE RESTRICT
);

-- table: erro_validacao
CREATE TABLE erro_validacao (
	id INTEGER NOT NULL, 
	execucao_id INTEGER, 
	registro_id INTEGER, 
	campo_origem TEXT, 
	codigo_erro TEXT NOT NULL, 
	descricao TEXT NOT NULL, 
	severidade TEXT NOT NULL, 
	registrado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_erro_validacao_0 CHECK (execucao_id IS NOT NULL OR registro_id IS NOT NULL), 
	FOREIGN KEY(execucao_id) REFERENCES execucao_coleta (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: execucao_coleta
CREATE TABLE execucao_coleta (
	id INTEGER NOT NULL, 
	recurso_id INTEGER NOT NULL, 
	artefato_id INTEGER, 
	iniciada_em DATETIME NOT NULL, 
	terminada_em DATETIME, 
	status TEXT NOT NULL, 
	http_status INTEGER, 
	tentativas INTEGER NOT NULL, 
	linhas_recebidas INTEGER, 
	linhas_validas INTEGER, 
	linhas_rejeitadas INTEGER, 
	registros_criados INTEGER, 
	registros_alterados INTEGER, 
	erro_codigo TEXT, 
	erro_detalhe TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_execucao_coleta_0 CHECK (tentativas>=0), 
	CONSTRAINT ck_execucao_coleta_1 CHECK (terminada_em IS NULL OR terminada_em>=iniciada_em), 
	CONSTRAINT ck_execucao_coleta_2 CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599), 
	FOREIGN KEY(recurso_id) REFERENCES recurso_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(artefato_id) REFERENCES artefato_coleta (id) ON DELETE RESTRICT
);

-- table: faixa_fiscalizacao
CREATE TABLE faixa_fiscalizacao (
	id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	numero_faixa INTEGER, 
	sentido_id INTEGER, 
	sentido_original TEXT, 
	descricao TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_faixa_fiscalizacao_0 CHECK (numero_faixa IS NULL OR numero_faixa>=1), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(sentido_id) REFERENCES sentido (id) ON DELETE RESTRICT
);

-- table: faixa_medicao_equipamento
CREATE TABLE faixa_medicao_equipamento (
	id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	registro_fonte_id INTEGER NOT NULL, 
	numero_faixa INTEGER, 
	sentido_id INTEGER, 
	velocidade_nominal_kmh NUMERIC(15, 7), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_faixa_medicao_equipamento_0 CHECK (numero_faixa IS NULL OR numero_faixa BETWEEN 1 AND 99), 
	CONSTRAINT ck_faixa_medicao_equipamento_1 CHECK (velocidade_nominal_kmh IS NULL OR (velocidade_nominal_kmh>0 AND velocidade_nominal_kmh<=350)), 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(sentido_id) REFERENCES sentido (id) ON DELETE RESTRICT
);

-- table: fonte
CREATE TABLE fonte (
	id INTEGER NOT NULL, 
	organizacao_id INTEGER NOT NULL, 
	natureza_id INTEGER NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	url_institucional TEXT NOT NULL, 
	esfera TEXT NOT NULL, 
	licenca TEXT, 
	documentacao_url TEXT, 
	situacao TEXT NOT NULL, 
	periodicidade_declarada TEXT, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_fonte_0 CHECK (esfera IN ('federal','estadual','municipal','distrital','outra','desconhecida')), 
	CONSTRAINT uq_fonte_0 UNIQUE (nome), 
	FOREIGN KEY(organizacao_id) REFERENCES organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(natureza_id) REFERENCES natureza_fonte (id) ON DELETE RESTRICT
);

-- table: funcao_equipamento
CREATE TABLE funcao_equipamento (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_funcao_equipamento_0 UNIQUE (codigo)
);

-- table: geo_candidato
CREATE TABLE geo_candidato (
	id INTEGER NOT NULL, 
	ponto_id INTEGER, 
	equipamento_id INTEGER, 
	posicao_id INTEGER NOT NULL, 
	fonte_geo_id INTEGER NOT NULL, 
	metodo VARCHAR(40) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	score NUMERIC(15, 7) NOT NULL, 
	referencia_externa VARCHAR(255), 
	evidencia TEXT NOT NULL, 
	detalhe_json TEXT, 
	hash_identidade VARCHAR(64) NOT NULL, 
	criado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_geo_candidato_0 CHECK (status IN ('revisar','aprovado','rejeitado')), 
	CONSTRAINT ck_geo_candidato_1 CHECK (score BETWEEN 0 AND 1), 
	CONSTRAINT ck_geo_candidato_2 CHECK ((ponto_id IS NOT NULL) <> (equipamento_id IS NOT NULL)), 
	CONSTRAINT uq_geo_candidato_0 UNIQUE (hash_identidade), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(posicao_id) REFERENCES posicao_geografica (id) ON DELETE RESTRICT, 
	FOREIGN KEY(fonte_geo_id) REFERENCES geo_fonte (id) ON DELETE RESTRICT
);

-- table: geo_decisao
CREATE TABLE geo_decisao (
	id INTEGER NOT NULL, 
	candidato_id INTEGER NOT NULL, 
	decisao VARCHAR(20) NOT NULL, 
	ator TEXT NOT NULL, 
	justificativa TEXT NOT NULL, 
	decidida_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_geo_decisao_0 CHECK (decisao IN ('aprovado','rejeitado')), 
	FOREIGN KEY(candidato_id) REFERENCES geo_candidato (id) ON DELETE RESTRICT
);

-- table: geo_fonte
CREATE TABLE geo_fonte (
	id INTEGER NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	url TEXT, 
	registrado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_geo_fonte_0 CHECK (tipo IN ('oficial','comunitaria')), 
	CONSTRAINT uq_geo_fonte_0 UNIQUE (nome)
);

-- table: geo_trecho_calibrado
CREATE TABLE geo_trecho_calibrado (
	id INTEGER NOT NULL, 
	via_id INTEGER NOT NULL, 
	fonte_geo_id INTEGER NOT NULL, 
	km_inicio NUMERIC(15, 7) NOT NULL, 
	km_fim NUMERIC(15, 7) NOT NULL, 
	uf VARCHAR(2), 
	hash_origem VARCHAR(64) NOT NULL, 
	referencia TEXT, 
	importado_em DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_geo_trecho_calibrado_0 CHECK (km_inicio>=0), 
	CONSTRAINT ck_geo_trecho_calibrado_1 CHECK (km_fim>km_inicio), 
	CONSTRAINT uq_geo_trecho_calibrado_0 UNIQUE (hash_origem), 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT, 
	FOREIGN KEY(fonte_geo_id) REFERENCES geo_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(uf) REFERENCES uf (sigla) ON DELETE RESTRICT
);

-- table: geo_trecho_vertice
CREATE TABLE geo_trecho_vertice (
	trecho_id INTEGER NOT NULL, 
	ordem INTEGER NOT NULL, 
	latitude NUMERIC(15, 7) NOT NULL, 
	longitude NUMERIC(15, 7) NOT NULL, 
	PRIMARY KEY (trecho_id, ordem), 
	CONSTRAINT ck_geo_trecho_vertice_0 CHECK (ordem>=0), 
	CONSTRAINT ck_geo_trecho_vertice_1 CHECK (latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_geo_trecho_vertice_2 CHECK (longitude BETWEEN -180 AND 180), 
	FOREIGN KEY(trecho_id) REFERENCES geo_trecho_calibrado (id) ON DELETE RESTRICT
);

-- table: identificador_equipamento
CREATE TABLE identificador_equipamento (
	id INTEGER NOT NULL, 
	identificador_id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	vigencia_inicio DATETIME, 
	vigencia_fim DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(identificador_id) REFERENCES identificador_externo (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT
);

-- table: identificador_externo
CREATE TABLE identificador_externo (
	id INTEGER NOT NULL, 
	fonte_id INTEGER NOT NULL, 
	tipo_identificador_id INTEGER NOT NULL, 
	valor TEXT NOT NULL, 
	valor_normalizado VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_identificador_externo_0 UNIQUE (fonte_id, tipo_identificador_id, valor_normalizado), 
	FOREIGN KEY(fonte_id) REFERENCES fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tipo_identificador_id) REFERENCES tipo_identificador (id) ON DELETE RESTRICT
);

-- table: identificador_operacao
CREATE TABLE identificador_operacao (
	id INTEGER NOT NULL, 
	identificador_id INTEGER NOT NULL, 
	operacao_id INTEGER NOT NULL, 
	vigencia_inicio DATETIME, 
	vigencia_fim DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(identificador_id) REFERENCES identificador_externo (id) ON DELETE RESTRICT, 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: identificador_ponto
CREATE TABLE identificador_ponto (
	id INTEGER NOT NULL, 
	identificador_id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	vigencia_inicio DATETIME, 
	vigencia_fim DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(identificador_id) REFERENCES identificador_externo (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: instalacao
CREATE TABLE instalacao (
	id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	funcao_equipamento_id INTEGER, 
	situacao_operacional_id INTEGER, 
	inicio_em DATETIME, 
	fim_em DATETIME, 
	data_inicio_autuacao DATE, 
	data_inicio_educativo DATE, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_instalacao_0 CHECK (fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(funcao_equipamento_id) REFERENCES funcao_equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(situacao_operacional_id) REFERENCES situacao_operacional (id) ON DELETE RESTRICT
);

-- table: instalacao_faixa
CREATE TABLE instalacao_faixa (
	instalacao_id INTEGER NOT NULL, 
	faixa_id INTEGER NOT NULL, 
	PRIMARY KEY (instalacao_id, faixa_id), 
	FOREIGN KEY(instalacao_id) REFERENCES instalacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(faixa_id) REFERENCES faixa_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: licenca_dados
CREATE TABLE licenca_dados (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	nome TEXT NOT NULL, 
	url_licenca TEXT, 
	versao TEXT, 
	requisitos_atribuicao TEXT, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_licenca_dados_0 UNIQUE (codigo)
);

-- table: limite_velocidade
CREATE TABLE limite_velocidade (
	id INTEGER NOT NULL, 
	ponto_id INTEGER, 
	faixa_id INTEGER, 
	categoria_veiculo_id INTEGER NOT NULL, 
	velocidade_kmh NUMERIC(15, 7), 
	vigencia_inicio DATETIME, 
	vigencia_fim DATETIME, 
	registro_fonte_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_limite_velocidade_0 CHECK ((ponto_id IS NULL) <> (faixa_id IS NULL)), 
	CONSTRAINT ck_limite_velocidade_1 CHECK (velocidade_kmh>0 AND velocidade_kmh<=350), 
	CONSTRAINT ck_limite_velocidade_2 CHECK (vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(faixa_id) REFERENCES faixa_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(categoria_veiculo_id) REFERENCES categoria_veiculo (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: modalidade_fiscalizacao
CREATE TABLE modalidade_fiscalizacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_modalidade_fiscalizacao_0 UNIQUE (codigo)
);

-- table: modelo_equipamento
CREATE TABLE modelo_equipamento (
	id INTEGER NOT NULL, 
	fabricante_id INTEGER, 
	nome_modelo TEXT NOT NULL, 
	tecnologia_id INTEGER, 
	registro_aprovacao_inmetro TEXT, 
	portaria_aprovacao_modelo TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(fabricante_id) REFERENCES organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tecnologia_id) REFERENCES tecnologia_medicao (id) ON DELETE RESTRICT
);

-- table: municipio
CREATE TABLE municipio (
	codigo_ibge VARCHAR(7) NOT NULL, 
	uf_sigla VARCHAR(2) NOT NULL, 
	nome TEXT NOT NULL, 
	PRIMARY KEY (codigo_ibge), 
	FOREIGN KEY(uf_sigla) REFERENCES uf (sigla) ON DELETE RESTRICT
);

-- table: natureza_fonte
CREATE TABLE natureza_fonte (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	nome TEXT NOT NULL, 
	descricao TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_natureza_fonte_0 CHECK (codigo IN ('oficial','comunitaria','academica','privada','outra','desconhecida')), 
	CONSTRAINT uq_natureza_fonte_0 UNIQUE (codigo)
);

-- table: observacao_trafego
CREATE TABLE observacao_trafego (
	id INTEGER NOT NULL, 
	registro_fonte_id INTEGER NOT NULL, 
	equipamento_id INTEGER, 
	ponto_id INTEGER, 
	faixa_id INTEGER, 
	categoria_veiculo_id INTEGER, 
	sentido_id INTEGER, 
	instante_observacao DATETIME, 
	data_observacao DATE, 
	velocidade_publicada TEXT, 
	velocidade_kmh NUMERIC(15, 7), 
	volume_total INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_observacao_trafego_0 CHECK (volume_total IS NULL OR volume_total>=0), 
	CONSTRAINT ck_observacao_trafego_1 CHECK (velocidade_kmh IS NULL OR velocidade_kmh>=0), 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(faixa_id) REFERENCES faixa_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(categoria_veiculo_id) REFERENCES categoria_veiculo (id) ON DELETE RESTRICT, 
	FOREIGN KEY(sentido_id) REFERENCES sentido (id) ON DELETE RESTRICT
);

-- table: operacao_equipamento
CREATE TABLE operacao_equipamento (
	operacao_id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	PRIMARY KEY (operacao_id, equipamento_id), 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT
);

-- table: operacao_faixa
CREATE TABLE operacao_faixa (
	operacao_id INTEGER NOT NULL, 
	faixa_id INTEGER NOT NULL, 
	PRIMARY KEY (operacao_id, faixa_id), 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(faixa_id) REFERENCES faixa_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: operacao_fiscalizacao
CREATE TABLE operacao_fiscalizacao (
	id INTEGER NOT NULL, 
	modalidade_id INTEGER NOT NULL, 
	situacao_operacao_id INTEGER NOT NULL, 
	organizacao_id INTEGER, 
	ponto_id INTEGER, 
	trecho_id INTEGER, 
	posicao_id INTEGER, 
	via_id INTEGER, 
	municipio_id VARCHAR(7), 
	km NUMERIC(15, 7), 
	descricao TEXT, 
	inicio_em DATETIME, 
	fim_em DATETIME, 
	fuso_original TEXT, 
	publicado_em DATETIME, 
	registro_fonte_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_operacao_fiscalizacao_0 CHECK (fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em), 
	CONSTRAINT ck_operacao_fiscalizacao_1 CHECK (km IS NULL OR km>=0), 
	FOREIGN KEY(modalidade_id) REFERENCES modalidade_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(situacao_operacao_id) REFERENCES situacao_operacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(organizacao_id) REFERENCES organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT, 
	FOREIGN KEY(posicao_id) REFERENCES posicao_geografica (id) ON DELETE RESTRICT, 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT, 
	FOREIGN KEY(municipio_id) REFERENCES municipio (codigo_ibge) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: operacao_recorrencia
CREATE TABLE operacao_recorrencia (
	id INTEGER NOT NULL, 
	operacao_id INTEGER NOT NULL, 
	regra_repeticao TEXT NOT NULL, 
	fuso_horario TEXT, 
	data_inicio DATE, 
	data_fim DATE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_operacao_recorrencia_0 CHECK (data_fim IS NULL OR data_inicio IS NULL OR data_fim>=data_inicio), 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT
);

-- table: organizacao
CREATE TABLE organizacao (
	id INTEGER NOT NULL, 
	nome TEXT NOT NULL, 
	tipo_organizacao_id INTEGER NOT NULL, 
	municipio_id VARCHAR(7), 
	cnpj VARCHAR(255), 
	site_oficial TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_organizacao_0 UNIQUE (cnpj), 
	FOREIGN KEY(tipo_organizacao_id) REFERENCES tipo_organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(municipio_id) REFERENCES municipio (codigo_ibge) ON DELETE RESTRICT
);

-- table: papel_organizacao
CREATE TABLE papel_organizacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_papel_organizacao_0 UNIQUE (codigo)
);

-- table: ponto_fiscalizacao
CREATE TABLE ponto_fiscalizacao (
	id INTEGER NOT NULL, 
	posicao_id INTEGER, 
	endereco_id INTEGER, 
	municipio_id VARCHAR(7), 
	via_id INTEGER, 
	km NUMERIC(15, 7), 
	tipo_pista TEXT, 
	situacao_operacional_id INTEGER, 
	inicio_operacao DATETIME, 
	data_inativacao DATE, 
	observacoes TEXT, 
	quantidade_faixas_declarada INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_ponto_fiscalizacao_0 CHECK (km IS NULL OR km>=0), 
	CONSTRAINT ck_ponto_fiscalizacao_1 CHECK (quantidade_faixas_declarada IS NULL OR quantidade_faixas_declarada>=0), 
	FOREIGN KEY(posicao_id) REFERENCES posicao_geografica (id) ON DELETE RESTRICT, 
	FOREIGN KEY(endereco_id) REFERENCES endereco (id) ON DELETE RESTRICT, 
	FOREIGN KEY(municipio_id) REFERENCES municipio (codigo_ibge) ON DELETE RESTRICT, 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT, 
	FOREIGN KEY(situacao_operacional_id) REFERENCES situacao_operacional (id) ON DELETE RESTRICT
);

-- table: ponto_organizacao
CREATE TABLE ponto_organizacao (
	id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	organizacao_id INTEGER NOT NULL, 
	papel_id INTEGER NOT NULL, 
	inicio_em DATETIME, 
	fim_em DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_ponto_organizacao_0 CHECK (fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(organizacao_id) REFERENCES organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(papel_id) REFERENCES papel_organizacao (id) ON DELETE RESTRICT
);

-- table: posicao_geografica
CREATE TABLE posicao_geografica (
	id INTEGER NOT NULL, 
	latitude NUMERIC(15, 7) NOT NULL, 
	longitude NUMERIC(15, 7) NOT NULL, 
	precisao_metros NUMERIC(15, 7), 
	qualidade_posicao_id INTEGER NOT NULL, 
	metodo_obtencao TEXT, 
	registro_fonte_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_posicao_geografica_0 CHECK (latitude BETWEEN -90 AND 90), 
	CONSTRAINT ck_posicao_geografica_1 CHECK (longitude BETWEEN -180 AND 180), 
	CONSTRAINT ck_posicao_geografica_2 CHECK (precisao_metros IS NULL OR precisao_metros>=0), 
	FOREIGN KEY(qualidade_posicao_id) REFERENCES qualidade_posicao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: qualidade_posicao
CREATE TABLE qualidade_posicao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_qualidade_posicao_0 UNIQUE (codigo)
);

-- table: recorrencia_dia
CREATE TABLE recorrencia_dia (
	recorrencia_id INTEGER NOT NULL, 
	dia_semana INTEGER NOT NULL, 
	hora_inicio TIME NOT NULL, 
	hora_fim TIME, 
	PRIMARY KEY (recorrencia_id, dia_semana, hora_inicio), 
	CONSTRAINT ck_recorrencia_dia_0 CHECK (dia_semana BETWEEN 1 AND 7), 
	FOREIGN KEY(recorrencia_id) REFERENCES operacao_recorrencia (id) ON DELETE RESTRICT
);

-- table: recurso_fonte
CREATE TABLE recurso_fonte (
	id INTEGER NOT NULL, 
	fonte_id INTEGER NOT NULL, 
	nome TEXT NOT NULL, 
	url_recurso VARCHAR(512) NOT NULL, 
	formato_origem TEXT NOT NULL, 
	dicionario_url TEXT, 
	periodicidade_segundos INTEGER, 
	ativo BOOLEAN NOT NULL, 
	tamanho_maximo_bytes INTEGER, 
	status_integracao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_recurso_fonte_0 CHECK (periodicidade_segundos IS NULL OR periodicidade_segundos>0), 
	CONSTRAINT ck_recurso_fonte_1 CHECK (tamanho_maximo_bytes IS NULL OR tamanho_maximo_bytes>0), 
	CONSTRAINT uq_recurso_fonte_0 UNIQUE (fonte_id, url_recurso), 
	FOREIGN KEY(fonte_id) REFERENCES fonte (id) ON DELETE RESTRICT
);

-- table: recurso_licenca
CREATE TABLE recurso_licenca (
	id INTEGER NOT NULL, 
	recurso_id INTEGER NOT NULL, 
	licenca_id INTEGER NOT NULL, 
	vigencia_inicio DATE, 
	vigencia_fim DATE, 
	observacoes TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_recurso_licenca_0 CHECK (vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio), 
	FOREIGN KEY(recurso_id) REFERENCES recurso_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(licenca_id) REFERENCES licenca_dados (id) ON DELETE RESTRICT
);

-- table: regime_fiscalizacao
CREATE TABLE regime_fiscalizacao (
	id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	modalidade_id INTEGER NOT NULL, 
	tipo_medicao_id INTEGER, 
	situacao_operacional_id INTEGER, 
	inicio_em DATETIME, 
	fim_em DATETIME, 
	fonte_registro_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_regime_fiscalizacao_0 CHECK (fim_em IS NULL OR inicio_em IS NULL OR fim_em>=inicio_em), 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(modalidade_id) REFERENCES modalidade_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tipo_medicao_id) REFERENCES tipo_medicao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(situacao_operacional_id) REFERENCES situacao_operacional (id) ON DELETE RESTRICT, 
	FOREIGN KEY(fonte_registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: registro_fonte
CREATE TABLE registro_fonte (
	id INTEGER NOT NULL, 
	artefato_id INTEGER NOT NULL, 
	numero_ordem INTEGER NOT NULL, 
	identificador_na_fonte TEXT, 
	payload_original TEXT NOT NULL, 
	hash_registro VARCHAR(64) NOT NULL, 
	status_validacao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_registro_fonte_0 CHECK (numero_ordem>=0), 
	CONSTRAINT uq_registro_fonte_0 UNIQUE (artefato_id, numero_ordem), 
	FOREIGN KEY(artefato_id) REFERENCES artefato_coleta (id) ON DELETE RESTRICT
);

-- table: regra_deduplicacao
CREATE TABLE regra_deduplicacao (
	id INTEGER NOT NULL, 
	versao VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	configuracao_serializada TEXT NOT NULL, 
	inicio_validade DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_regra_deduplicacao_0 UNIQUE (versao)
);

-- table: resultado_verificacao
CREATE TABLE resultado_verificacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_resultado_verificacao_0 UNIQUE (codigo)
);

-- table: sentido
CREATE TABLE sentido (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_sentido_0 UNIQUE (codigo)
);

-- table: situacao_operacao
CREATE TABLE situacao_operacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_situacao_operacao_0 UNIQUE (codigo)
);

-- table: situacao_operacional
CREATE TABLE situacao_operacional (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_situacao_operacional_0 UNIQUE (codigo)
);

-- table: snapshot_publicado
CREATE TABLE snapshot_publicado (
	id INTEGER NOT NULL, 
	anterior_id INTEGER, 
	publicado_em DATETIME NOT NULL, 
	status TEXT NOT NULL, 
	resumo_validacao TEXT, 
	identificador_versao VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_snapshot_publicado_0 UNIQUE (identificador_versao), 
	FOREIGN KEY(anterior_id) REFERENCES snapshot_publicado (id) ON DELETE RESTRICT
);

-- table: snapshot_recurso
CREATE TABLE snapshot_recurso (
	snapshot_id INTEGER NOT NULL, 
	recurso_id INTEGER NOT NULL, 
	artefato_id INTEGER, 
	PRIMARY KEY (snapshot_id, recurso_id), 
	FOREIGN KEY(snapshot_id) REFERENCES snapshot_publicado (id) ON DELETE RESTRICT, 
	FOREIGN KEY(recurso_id) REFERENCES recurso_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(artefato_id) REFERENCES artefato_coleta (id) ON DELETE RESTRICT
);

-- table: tecnologia_medicao
CREATE TABLE tecnologia_medicao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tecnologia_medicao_0 UNIQUE (codigo)
);

-- table: tipo_documento
CREATE TABLE tipo_documento (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_documento_0 UNIQUE (codigo)
);

-- table: tipo_identificador
CREATE TABLE tipo_identificador (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_identificador_0 UNIQUE (codigo)
);

-- table: tipo_medicao
CREATE TABLE tipo_medicao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_medicao_0 UNIQUE (codigo)
);

-- table: tipo_organizacao
CREATE TABLE tipo_organizacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_organizacao_0 UNIQUE (codigo)
);

-- table: tipo_radar
CREATE TABLE tipo_radar (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_radar_0 UNIQUE (codigo)
);

-- table: tipo_verificacao
CREATE TABLE tipo_verificacao (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_verificacao_0 UNIQUE (codigo)
);

-- table: tipo_via
CREATE TABLE tipo_via (
	id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	descricao TEXT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tipo_via_0 UNIQUE (codigo)
);

-- table: trecho_elegivel
CREATE TABLE trecho_elegivel (
	id INTEGER NOT NULL, 
	via_id INTEGER NOT NULL, 
	km_inicio NUMERIC(15, 7), 
	km_fim NUMERIC(15, 7), 
	sentido_id INTEGER, 
	criterio_inclusao TEXT, 
	vigencia_inicio DATE, 
	vigencia_fim DATE, 
	situacao TEXT, 
	registro_fonte_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_trecho_elegivel_0 CHECK (km_inicio IS NULL OR km_inicio>=0), 
	CONSTRAINT ck_trecho_elegivel_1 CHECK (km_fim IS NULL OR km_fim>=0), 
	CONSTRAINT ck_trecho_elegivel_2 CHECK (km_inicio IS NULL OR km_fim IS NULL OR km_fim>=km_inicio), 
	CONSTRAINT ck_trecho_elegivel_3 CHECK (vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim>=vigencia_inicio), 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT, 
	FOREIGN KEY(sentido_id) REFERENCES sentido (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: trecho_municipio
CREATE TABLE trecho_municipio (
	trecho_id INTEGER NOT NULL, 
	municipio_id VARCHAR(7) NOT NULL, 
	PRIMARY KEY (trecho_id, municipio_id), 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT, 
	FOREIGN KEY(municipio_id) REFERENCES municipio (codigo_ibge) ON DELETE RESTRICT
);

-- table: trecho_vertice
CREATE TABLE trecho_vertice (
	trecho_id INTEGER NOT NULL, 
	ordem INTEGER NOT NULL, 
	posicao_id INTEGER NOT NULL, 
	PRIMARY KEY (trecho_id, ordem), 
	CONSTRAINT ck_trecho_vertice_0 CHECK (ordem>=0), 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT, 
	FOREIGN KEY(posicao_id) REFERENCES posicao_geografica (id) ON DELETE RESTRICT
);

-- table: uf
CREATE TABLE uf (
	sigla VARCHAR(2) NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	PRIMARY KEY (sigla), 
	CONSTRAINT uq_uf_0 UNIQUE (nome)
);

-- table: valor_observado
CREATE TABLE valor_observado (
	id INTEGER NOT NULL, 
	registro_id INTEGER NOT NULL, 
	campo_id INTEGER NOT NULL, 
	valor_original TEXT, 
	valor_normalizado VARCHAR(255), 
	linha_origem TEXT, 
	pontuacao_qualidade NUMERIC(15, 7), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_valor_observado_0 CHECK (pontuacao_qualidade IS NULL OR pontuacao_qualidade BETWEEN 0 AND 1), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(campo_id) REFERENCES catalogo_campo (id) ON DELETE RESTRICT
);

-- table: verificacao_metrologica
CREATE TABLE verificacao_metrologica (
	id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	tipo_verificacao_id INTEGER NOT NULL, 
	resultado_id INTEGER NOT NULL, 
	orgao_executor_id INTEGER, 
	data_verificacao DATE, 
	validade_ate DATE, 
	numero_certificado TEXT, 
	norma_aplicada TEXT, 
	observacoes TEXT, 
	registro_fonte_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_verificacao_metrologica_0 CHECK (validade_ate IS NULL OR data_verificacao IS NULL OR validade_ate>=data_verificacao), 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tipo_verificacao_id) REFERENCES tipo_verificacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(resultado_id) REFERENCES resultado_verificacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(orgao_executor_id) REFERENCES organizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(registro_fonte_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT
);

-- table: via
CREATE TABLE via (
	id INTEGER NOT NULL, 
	tipo_via_id INTEGER NOT NULL, 
	codigo VARCHAR(255) NOT NULL, 
	nome TEXT, 
	observacao TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_via_0 UNIQUE (tipo_via_id, codigo), 
	FOREIGN KEY(tipo_via_id) REFERENCES tipo_via (id) ON DELETE RESTRICT
);

-- table: via_uf
CREATE TABLE via_uf (
	via_id INTEGER NOT NULL, 
	uf_sigla VARCHAR(2) NOT NULL, 
	PRIMARY KEY (via_id, uf_sigla), 
	FOREIGN KEY(via_id) REFERENCES via (id) ON DELETE RESTRICT, 
	FOREIGN KEY(uf_sigla) REFERENCES uf (sigla) ON DELETE RESTRICT
);

-- table: vinculo_registro_equipamento
CREATE TABLE vinculo_registro_equipamento (
	registro_id INTEGER NOT NULL, 
	equipamento_id INTEGER NOT NULL, 
	confianca NUMERIC(15, 7), 
	decisao_id INTEGER, 
	PRIMARY KEY (registro_id, equipamento_id), 
	CONSTRAINT ck_vinculo_registro_equipamento_0 CHECK (confianca IS NULL OR confianca BETWEEN 0 AND 1), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(equipamento_id) REFERENCES equipamento (id) ON DELETE RESTRICT, 
	FOREIGN KEY(decisao_id) REFERENCES decisao_duplicidade (id) ON DELETE RESTRICT
);

-- table: vinculo_registro_operacao
CREATE TABLE vinculo_registro_operacao (
	registro_id INTEGER NOT NULL, 
	operacao_id INTEGER NOT NULL, 
	confianca NUMERIC(15, 7), 
	decisao_id INTEGER, 
	PRIMARY KEY (registro_id, operacao_id), 
	CONSTRAINT ck_vinculo_registro_operacao_0 CHECK (confianca IS NULL OR confianca BETWEEN 0 AND 1), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(operacao_id) REFERENCES operacao_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(decisao_id) REFERENCES decisao_duplicidade (id) ON DELETE RESTRICT
);

-- table: vinculo_registro_ponto
CREATE TABLE vinculo_registro_ponto (
	registro_id INTEGER NOT NULL, 
	ponto_id INTEGER NOT NULL, 
	confianca NUMERIC(15, 7), 
	decisao_id INTEGER, 
	PRIMARY KEY (registro_id, ponto_id), 
	CONSTRAINT ck_vinculo_registro_ponto_0 CHECK (confianca IS NULL OR confianca BETWEEN 0 AND 1), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(ponto_id) REFERENCES ponto_fiscalizacao (id) ON DELETE RESTRICT, 
	FOREIGN KEY(decisao_id) REFERENCES decisao_duplicidade (id) ON DELETE RESTRICT
);

-- table: vinculo_registro_trecho
CREATE TABLE vinculo_registro_trecho (
	registro_id INTEGER NOT NULL, 
	trecho_id INTEGER NOT NULL, 
	confianca NUMERIC(15, 7), 
	decisao_id INTEGER, 
	PRIMARY KEY (registro_id, trecho_id), 
	CONSTRAINT ck_vinculo_registro_trecho_0 CHECK (confianca IS NULL OR confianca BETWEEN 0 AND 1), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(trecho_id) REFERENCES trecho_elegivel (id) ON DELETE RESTRICT, 
	FOREIGN KEY(decisao_id) REFERENCES decisao_duplicidade (id) ON DELETE RESTRICT
);

-- table: vinculo_registro_verificacao
CREATE TABLE vinculo_registro_verificacao (
	registro_id INTEGER NOT NULL, 
	verificacao_id INTEGER NOT NULL, 
	PRIMARY KEY (registro_id, verificacao_id), 
	FOREIGN KEY(registro_id) REFERENCES registro_fonte (id) ON DELETE RESTRICT, 
	FOREIGN KEY(verificacao_id) REFERENCES verificacao_metrologica (id) ON DELETE RESTRICT
);

-- index: ix_equip_serie
CREATE INDEX ix_equip_serie ON equipamento (numero_serie);

-- index: ix_exec_recurso_inicio
CREATE INDEX ix_exec_recurso_inicio ON execucao_coleta (recurso_id, iniciada_em);

-- index: ix_geo_candidato_eq
CREATE INDEX ix_geo_candidato_eq ON geo_candidato (equipamento_id, status);

-- index: ix_geo_candidato_ponto
CREATE INDEX ix_geo_candidato_ponto ON geo_candidato (ponto_id, status);

-- index: ix_geo_trecho_km
CREATE INDEX ix_geo_trecho_km ON geo_trecho_calibrado (via_id, km_inicio, km_fim);

-- index: ix_ponto_via_km
CREATE INDEX ix_ponto_via_km ON ponto_fiscalizacao (via_id, km);

-- index: ix_posicao_lat_lon
CREATE INDEX ix_posicao_lat_lon ON posicao_geografica (latitude, longitude);

-- index: ix_registro_hash
CREATE INDEX ix_registro_hash ON registro_fonte (hash_registro);

