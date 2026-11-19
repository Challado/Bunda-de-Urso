CREATE TABLE IF NOT EXISTS CONTEUDO_ARTEFATO (
    hash_sha256 CHAR(64) PRIMARY KEY NOT NULL,
    bytes_arquivo BIGINT NOT NULL CHECK(bytes_arquivo >= 0)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='artefato_coleta' AND column_name='bytes_arquivo') THEN
        INSERT INTO CONTEUDO_ARTEFATO(hash_sha256,bytes_arquivo)
        SELECT DISTINCT hash_sha256,bytes_arquivo FROM ARTEFATO_COLETA;
        ALTER TABLE ARTEFATO_COLETA ADD FOREIGN KEY (hash_sha256)
            REFERENCES CONTEUDO_ARTEFATO(hash_sha256) ON DELETE RESTRICT;
        ALTER TABLE ARTEFATO_COLETA DROP COLUMN bytes_arquivo;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='alerta_operacional' AND column_name='recurso_id') THEN
        IF EXISTS (SELECT 1 FROM ALERTA_OPERACIONAL a JOIN EXECUCAO_COLETA e ON e.id=a.execucao_id
                   WHERE a.recurso_id<>e.recurso_id) THEN
            RAISE EXCEPTION 'o recurso do alerta diverge da execução' USING ERRCODE='23514';
        END IF;
        UPDATE ALERTA_OPERACIONAL SET recurso_id=NULL WHERE execucao_id IS NOT NULL;
        ALTER TABLE ALERTA_OPERACIONAL RENAME COLUMN recurso_id TO recurso_direto_id;
        ALTER TABLE ALERTA_OPERACIONAL ADD CHECK (execucao_id IS NULL OR recurso_direto_id IS NULL);
    END IF;
END $$;
CREATE OR REPLACE VIEW ARTEFATO_COLETA_DETALHE AS
SELECT a.*, c.bytes_arquivo FROM ARTEFATO_COLETA a
LEFT JOIN CONTEUDO_ARTEFATO c ON c.hash_sha256=a.hash_sha256;
CREATE OR REPLACE VIEW ALERTA_OPERACIONAL_DETALHE AS
SELECT a.*, COALESCE(e.recurso_id, a.recurso_direto_id) AS recurso_id
FROM ALERTA_OPERACIONAL a LEFT JOIN EXECUCAO_COLETA e ON e.id=a.execucao_id;
