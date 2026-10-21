-- A UF da cobertura municipal vem exclusivamente de MUNICIPIO.
CREATE TEMP TABLE VALIDAR_COBERTURA_3FN (ok INTEGER CONSTRAINT cobertura_uf_diverge_do_municipio CHECK(ok=1));
INSERT INTO VALIDAR_COBERTURA_3FN SELECT CASE WHEN EXISTS
 (SELECT 1 FROM COBERTURA_FONTE c JOIN MUNICIPIO m ON m.codigo_ibge=c.municipio_id
  WHERE c.uf_sigla IS NOT NULL AND (c.uf_sigla<>m.uf_sigla OR c.tipo_abrangencia='estadual'))
 THEN 0 ELSE 1 END;
DROP TABLE VALIDAR_COBERTURA_3FN;
UPDATE COBERTURA_FONTE SET uf_sigla=NULL WHERE municipio_id IS NOT NULL;
CREATE VIEW IF NOT EXISTS COBERTURA_FONTE_DETALHE AS
SELECT c.id, c.fonte_id, c.tipo_abrangencia, COALESCE(m.uf_sigla,c.uf_sigla) AS uf_sigla,
       c.municipio_id, c.via_id, c.vigencia_inicio, c.vigencia_fim, c.confirmada
FROM COBERTURA_FONTE c LEFT JOIN MUNICIPIO m ON m.codigo_ibge=c.municipio_id;
ALTER TABLE COBERTURA_FONTE ADD CONSTRAINT CK_COBERTURA_MUNICIPIO_3FN CHECK (municipio_id IS NULL OR uf_sigla IS NULL);
