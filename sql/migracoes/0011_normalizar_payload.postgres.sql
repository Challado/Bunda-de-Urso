CREATE TABLE IF NOT EXISTS PAYLOAD_FONTE (
    hash_registro CHAR(64) PRIMARY KEY NOT NULL,
    payload_original TEXT NOT NULL
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='registro_fonte' AND column_name='payload_original') THEN
        INSERT INTO PAYLOAD_FONTE(hash_registro,payload_original)
        SELECT DISTINCT hash_registro,payload_original FROM REGISTRO_FONTE;
        ALTER TABLE REGISTRO_FONTE DROP COLUMN payload_original;
        ALTER TABLE REGISTRO_FONTE ADD CONSTRAINT FK_REGISTRO_PAYLOAD
            FOREIGN KEY(hash_registro) REFERENCES PAYLOAD_FONTE(hash_registro) ON DELETE RESTRICT;
    END IF;
END $$;
CREATE OR REPLACE VIEW REGISTRO_FONTE_DETALHE AS
SELECT r.*, p.payload_original FROM REGISTRO_FONTE r
LEFT JOIN PAYLOAD_FONTE p ON p.hash_registro=r.hash_registro;
