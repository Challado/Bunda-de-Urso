-- Chaves de consulta entre cadastros oficiais; nao altera registros de origem.
CREATE INDEX IF NOT EXISTS IX_EQUIPAMENTO_SERIE_TIPO
    ON EQUIPAMENTO (UPPER(TRIM(numero_serie)), tipo_radar_id);
CREATE INDEX IF NOT EXISTS IX_INSTALACAO_EQUIPAMENTO_PONTO
    ON INSTALACAO (equipamento_id, ponto_id);
CREATE INDEX IF NOT EXISTS IX_VINCULO_EQUIPAMENTO_REGISTRO
    ON VINCULO_REGISTRO_EQUIPAMENTO (equipamento_id, registro_id, decisao_id);
CREATE INDEX IF NOT EXISTS IX_VERIFICACAO_EQUIPAMENTO
    ON VERIFICACAO_METROLOGICA (equipamento_id, registro_fonte_id);
