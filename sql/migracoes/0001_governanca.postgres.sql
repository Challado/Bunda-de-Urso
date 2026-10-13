-- Radar Brasil - migracao de GOVERNANCA da ingestao (versao 0001) - PostgreSQL
--
-- Paridade com 0001_governanca.sqlite.sql. NAO e executada pela API (o host
-- roda SQLite); existe para manter os dois dialetos em sincronia, como os
-- demais arquivos de sql/. Postgres tem ADD COLUMN IF NOT EXISTS, entao as
-- colunas de PONTO_FISCALIZACAO entram direto.

ALTER TABLE PONTO_FISCALIZACAO ADD COLUMN IF NOT EXISTS procedencia TEXT DEFAULT 'oficial';
ALTER TABLE PONTO_FISCALIZACAO ADD COLUMN IF NOT EXISTS verificacao_status TEXT DEFAULT 'verificado';
ALTER TABLE PONTO_FISCALIZACAO ADD COLUMN IF NOT EXISTS removido_em TEXT;
ALTER TABLE PONTO_FISCALIZACAO ADD COLUMN IF NOT EXISTS removido_por TEXT;
ALTER TABLE PONTO_FISCALIZACAO ADD COLUMN IF NOT EXISTS motivo_remocao TEXT;

CREATE TABLE IF NOT EXISTS USUARIO (
    id SERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS API_TOKEN (
    id SERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS SESSAO (
    id SERIAL PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    usuario_id INTEGER NOT NULL REFERENCES USUARIO (id) ON DELETE RESTRICT,
    criado_em TEXT NOT NULL,
    expira_em TEXT NOT NULL,
    ultimo_uso TEXT,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS IX_SESSAO_TOKEN ON SESSAO (token_hash);

CREATE TABLE IF NOT EXISTS RADAR_ALTERACAO (
    id SERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS BLOQUEIO_GEOGRAFICO (
    id SERIAL PRIMARY KEY,
    tipo TEXT NOT NULL,
    latitude NUMERIC (10, 7) NOT NULL,
    longitude NUMERIC (10, 7) NOT NULL,
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

CREATE TABLE IF NOT EXISTS CORRESPONDENCIA_PONTO (
    id SERIAL PRIMARY KEY,
    ponto_colaborativo_id INTEGER NOT NULL REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    ponto_oficial_id INTEGER NOT NULL REFERENCES PONTO_FISCALIZACAO (id) ON DELETE RESTRICT,
    distancia_metros NUMERIC (12, 3),
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

CREATE TABLE IF NOT EXISTS SUBMISSAO_PUBLICA (
    id SERIAL PRIMARY KEY,
    ip TEXT,
    user_agent TEXT,
    quando TEXT NOT NULL,
    contato TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    aceitos INTEGER NOT NULL DEFAULT 0,
    rejeitados INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS IX_SUBMISSAO_PUBLICA_IP ON SUBMISSAO_PUBLICA (ip, quando);
