-- Grafia histórica separada da identidade usada nas junções.
CREATE TABLE IF NOT EXISTS IDENTIFICADOR_GRAFIA (
    identificador_id INTEGER PRIMARY KEY NOT NULL REFERENCES IDENTIFICADOR_EXTERNO(id) ON DELETE RESTRICT,
    valor_original TEXT NOT NULL
);
-- +SE_COLUNA IDENTIFICADOR_EXTERNO valor_normalizado
INSERT INTO IDENTIFICADOR_GRAFIA(identificador_id, valor_original)
SELECT id, valor FROM IDENTIFICADOR_EXTERNO WHERE valor <> valor_normalizado;
ALTER TABLE IDENTIFICADOR_EXTERNO RENAME COLUMN valor TO grafia_legada;
ALTER TABLE IDENTIFICADOR_EXTERNO RENAME COLUMN valor_normalizado TO valor;
ALTER TABLE IDENTIFICADOR_EXTERNO DROP COLUMN grafia_legada;
-- +FIM

-- O hash era derivado do documento e a deduplicação compara o envelope.
ALTER TABLE TRASEIRO_EVENTO DROP COLUMN hash_documento;
