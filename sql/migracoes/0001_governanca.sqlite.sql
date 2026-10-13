-- Radar Brasil - migracao de GOVERNANCA da ingestao (versao 0001) - SQLite
--
-- Aplicada de forma ADITIVA e IDEMPOTENTE por core/governanca.py
-- (funcao aplicar_migracoes). O repositorio nao tem gerenciador de
-- migrations para base ja em producao: o esquema canonico (T01..T77) e
-- criado por core/db.init_db a partir de sql/schema.sqlite.sql; esta
-- migracao ACRESCENTA a camada de governanca sem tocar no esquema canonico.
--
-- Diretivas "-- +COLUNA <tabela> <coluna> <definicao>" sao aplicadas pelo
-- runner como ALTER TABLE ADD COLUMN somente quando a coluna falta (SQLite
-- nao tem ADD COLUMN IF NOT EXISTS). Todo o demais e SQL puro.
--
-- Regra do dono: NADA escreve direto no banco por fora do app. O unico
-- caminho de escrita e a API (core/governanca.py).

-- +COLUNA PONTO_FISCALIZACAO procedencia TEXT DEFAULT 'oficial'
-- +COLUNA PONTO_FISCALIZACAO verificacao_status TEXT DEFAULT 'verificado'
-- +COLUNA PONTO_FISCALIZACAO removido_em TEXT
-- +COLUNA PONTO_FISCALIZACAO removido_por TEXT
-- +COLUNA PONTO_FISCALIZACAO motivo_remocao TEXT

-- T78 USUARIO (painel: quem opera a gestao)
CREATE TABLE IF NOT EXISTS USUARIO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    nome TEXT,
    email TEXT,
    senha_hash TEXT NOT NULL,
    senha_salt TEXT NOT NULL,
    iteracoes INTEGER NOT NULL DEFAULT 200000,
    papel TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    ultimo_login TEXT,
    deve_trocar_senha INTEGER NOT NULL DEFAULT 0,
    CHECK (papel IN ('admin', 'moderador')),
    CHECK (ativo IN (0, 1)),
    CHECK (deve_trocar_senha IN (0, 1)),
    CHECK (iteracoes >= 200000),
    CHECK (length(senha_hash) > 0),
    CHECK (length(senha_salt) > 0)
);

-- T79 API_TOKEN (chaves de gestao; valor NUNCA guardado, so o hash)
CREATE TABLE IF NOT EXISTS API_TOKEN (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    dono TEXT,
    escopo TEXT NOT NULL,
    valor_hash TEXT NOT NULL UNIQUE,
    prefixo TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    expira_em TEXT,
    revogado_em TEXT,
    ultimo_uso TEXT,
    observacoes TEXT,
    CHECK (escopo IN ('contribuidor', 'moderador', 'admin'))
);
CREATE INDEX IF NOT EXISTS IX_API_TOKEN_HASH ON API_TOKEN (valor_hash);

-- T80 SESSAO (sessao do painel; guarda o HASH do token de sessao)
CREATE TABLE IF NOT EXISTS SESSAO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    usuario_id INTEGER NOT NULL REFERENCES USUARIO (id) ON DELETE RESTRICT,
    criado_em TEXT NOT NULL,
    expira_em TEXT NOT NULL,
    ultimo_uso TEXT,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS IX_SESSAO_TOKEN ON SESSAO (token_hash);

-- T81 RADAR_ALTERACAO (auditoria imutavel: quem, quando, o que, por que)
CREATE TABLE IF NOT EXISTS RADAR_ALTERACAO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ponto_id INTEGER REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    quem_usuario_id INTEGER REFERENCES USUARIO (id) ON DELETE RESTRICT,
    quem_token_id INTEGER REFERENCES API_TOKEN (id) ON DELETE RESTRICT,
    quem_rotulo TEXT,
    quando TEXT NOT NULL,
    tipo TEXT NOT NULL,
    motivo TEXT,
    campos_json TEXT,
    ip TEXT,
    CHECK (tipo IN ('criado', 'editado', 'verificado', 'desabilitado',
                    'removido', 'bloqueio_criado', 'bloqueio_removido'))
);
CREATE INDEX IF NOT EXISTS IX_RADAR_ALTERACAO_PONTO ON RADAR_ALTERACAO (ponto_id);

-- T82 BLOQUEIO_GEOGRAFICO (anti-sabotagem: marcacao falsa / zona sombra)
CREATE TABLE IF NOT EXISTS BLOQUEIO_GEOGRAFICO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    latitude DECIMAL (10, 7) NOT NULL,
    longitude DECIMAL (10, 7) NOT NULL,
    raio_metros INTEGER NOT NULL,
    motivo TEXT,
    criado_por_usuario_id INTEGER REFERENCES USUARIO (id) ON DELETE RESTRICT,
    criado_em TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    origem_ponto_id INTEGER REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    CHECK (tipo IN ('marcacao_falsa', 'zona_sombra')),
    CHECK (ativo IN (0, 1)),
    CHECK (raio_metros > 0),
    CHECK (latitude >= -90 AND latitude <= 90),
    CHECK (longitude >= -180 AND longitude <= 180)
);
CREATE INDEX IF NOT EXISTS IX_BLOQUEIO_GEO_ATIVO ON BLOQUEIO_GEOGRAFICO (ativo);

-- T83 CORRESPONDENCIA_PONTO (vinculo colaborativo <-> oficial)
CREATE TABLE IF NOT EXISTS CORRESPONDENCIA_PONTO (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ponto_colaborativo_id INTEGER NOT NULL REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    ponto_oficial_id INTEGER NOT NULL REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    distancia_metros DECIMAL (12, 3),
    status TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    resolvido_por TEXT,
    resolvido_em TEXT,
    motivo TEXT,
    CHECK (status IN ('corroborado', 'oficial_vence', 'colaborativo_vence')),
    CHECK (ponto_colaborativo_id <> ponto_oficial_id),
    UNIQUE (ponto_colaborativo_id, ponto_oficial_id)
);
CREATE INDEX IF NOT EXISTS IX_CORRESPONDENCIA_COLAB ON CORRESPONDENCIA_PONTO (ponto_colaborativo_id);
CREATE INDEX IF NOT EXISTS IX_CORRESPONDENCIA_OFICIAL ON CORRESPONDENCIA_PONTO (ponto_oficial_id);

-- T84 SUBMISSAO_PUBLICA (procedencia + rate limit da submissao aberta)
CREATE TABLE IF NOT EXISTS SUBMISSAO_PUBLICA (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT,
    user_agent TEXT,
    quando TEXT NOT NULL,
    contato TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    aceitos INTEGER NOT NULL DEFAULT 0,
    rejeitados INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS IX_SUBMISSAO_PUBLICA_IP ON SUBMISSAO_PUBLICA (ip, quando);
