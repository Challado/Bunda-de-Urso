CREATE TABLE IF NOT EXISTS IDENTIFICADOR_GRAFIA (
    identificador_id BIGINT PRIMARY KEY NOT NULL REFERENCES IDENTIFICADOR_EXTERNO(id) ON DELETE RESTRICT,
    valor_original TEXT NOT NULL
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
               AND table_name='identificador_externo' AND column_name='valor_normalizado') THEN
        INSERT INTO IDENTIFICADOR_GRAFIA(identificador_id, valor_original)
        SELECT id, valor FROM IDENTIFICADOR_EXTERNO WHERE valor <> valor_normalizado;
        ALTER TABLE IDENTIFICADOR_EXTERNO RENAME COLUMN valor TO grafia_legada;
        ALTER TABLE IDENTIFICADOR_EXTERNO RENAME COLUMN valor_normalizado TO valor;
        ALTER TABLE IDENTIFICADOR_EXTERNO DROP COLUMN grafia_legada;
    END IF;
END $$;
ALTER TABLE TRASEIRO_EVENTO DROP COLUMN hash_documento;
