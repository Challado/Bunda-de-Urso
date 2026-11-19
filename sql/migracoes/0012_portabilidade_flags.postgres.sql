-- Instalações PostgreSQL criadas pelo primeiro migrador usavam BOOLEAN.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='recurso_fonte' AND column_name='ativo' AND data_type='boolean') THEN
        ALTER TABLE RECURSO_FONTE ALTER COLUMN ativo TYPE INTEGER USING ativo::INTEGER;
        ALTER TABLE RECURSO_FONTE ADD CHECK (ativo IN (0,1));
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='cobertura_fonte' AND column_name='confirmada' AND data_type='boolean') THEN
        DROP VIEW COBERTURA_FONTE_DETALHE;
        ALTER TABLE COBERTURA_FONTE ALTER COLUMN confirmada TYPE INTEGER USING confirmada::INTEGER;
        ALTER TABLE COBERTURA_FONTE ADD CHECK (confirmada IN (0,1));
        CREATE VIEW COBERTURA_FONTE_DETALHE AS
        SELECT c.id,c.fonte_id,c.tipo_abrangencia,COALESCE(m.uf_sigla,c.uf_sigla) AS uf_sigla,
               c.municipio_id,c.via_id,c.vigencia_inicio,c.vigencia_fim,c.confirmada
        FROM COBERTURA_FONTE c LEFT JOIN MUNICIPIO m ON m.codigo_ibge=c.municipio_id;
    END IF;
END $$;
