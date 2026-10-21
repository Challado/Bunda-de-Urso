-- Candidatos pelo marco publicado, sem varrer a base nem depender de GPS.
CREATE INDEX IF NOT EXISTS IX_PONTO_LOCAL_CADASTRAL ON PONTO_FISCALIZACAO(municipio_id, via_id, km);
CREATE INDEX IF NOT EXISTS IX_FAIXA_PONTO_SENTIDO ON FAIXA_FISCALIZACAO(ponto_id, sentido_id);
