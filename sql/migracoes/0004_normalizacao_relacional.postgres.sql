DO $$ DECLARE incoerente boolean;
BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='snapshot_recurso' AND column_name='recurso_id') THEN
 EXECUTE 'SELECT EXISTS (SELECT 1 FROM SNAPSHOT_RECURSO s JOIN ARTEFATO_COLETA a ON a.id=s.artefato_id WHERE s.recurso_id<>a.recurso_id)' INTO incoerente;
 IF incoerente THEN RAISE EXCEPTION 'snapshot recurso diverge do artefato'; END IF;
END IF;
IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='execucao_coleta' AND column_name='artefato_id') THEN
 EXECUTE 'SELECT EXISTS (SELECT 1 FROM EXECUCAO_COLETA e JOIN ARTEFATO_COLETA a ON a.id=e.artefato_id WHERE e.recurso_id<>a.recurso_id)' INTO incoerente;
 IF incoerente THEN RAISE EXCEPTION 'execucao recurso diverge do artefato'; END IF;
END IF;
END $$;
-- Recurso de snapshot e derivado do artefato, nunca repetido.
DROP VIEW IF EXISTS SNAPSHOT_RECURSO_DETALHE;
CREATE TABLE SNAPSHOT_RECURSO_3FN (
    snapshot_id BIGINT NOT NULL REFERENCES SNAPSHOT_PUBLICADO(id) ON DELETE RESTRICT,
    artefato_id BIGINT NOT NULL REFERENCES ARTEFATO_COLETA(id) ON DELETE RESTRICT,
    PRIMARY KEY (snapshot_id, artefato_id)
);
INSERT INTO SNAPSHOT_RECURSO_3FN SELECT snapshot_id, artefato_id FROM SNAPSHOT_RECURSO;
DROP TABLE SNAPSHOT_RECURSO;
ALTER TABLE SNAPSHOT_RECURSO_3FN RENAME TO SNAPSHOT_RECURSO;
CREATE VIEW IF NOT EXISTS SNAPSHOT_RECURSO_DETALHE AS
SELECT s.snapshot_id, a.recurso_id, s.artefato_id
FROM SNAPSHOT_RECURSO s LEFT JOIN ARTEFATO_COLETA a ON a.id=s.artefato_id;

-- Uma tentativa tem recurso mesmo quando nao chega a receber um artefato.
CREATE TABLE IF NOT EXISTS EXECUCAO_ARTEFATO (
    execucao_id BIGINT PRIMARY KEY REFERENCES EXECUCAO_COLETA(id) ON DELETE RESTRICT,
    artefato_id BIGINT NOT NULL REFERENCES ARTEFATO_COLETA(id) ON DELETE RESTRICT
);
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='execucao_coleta' AND column_name='artefato_id') THEN
    EXECUTE 'INSERT INTO EXECUCAO_ARTEFATO SELECT id, artefato_id FROM EXECUCAO_COLETA WHERE artefato_id IS NOT NULL';
    ALTER TABLE EXECUCAO_COLETA DROP COLUMN artefato_id;
END IF;
END $$;
CREATE VIEW IF NOT EXISTS EXECUCAO_COLETA_DETALHE AS
SELECT e.*, ea.artefato_id FROM EXECUCAO_COLETA e
LEFT JOIN EXECUCAO_ARTEFATO ea ON ea.execucao_id=e.id;
CREATE INDEX IF NOT EXISTS IX_EXECUCAO_ARTEFATO ON EXECUCAO_ARTEFATO(artefato_id, execucao_id);

CREATE OR REPLACE FUNCTION validar_relacoes_coleta() RETURNS trigger AS $$
BEGIN
 IF TG_TABLE_NAME='execucao_artefato' THEN
  IF NOT EXISTS (SELECT 1 FROM EXECUCAO_COLETA e JOIN ARTEFATO_COLETA a ON a.recurso_id=e.recurso_id
                 WHERE e.id=NEW.execucao_id AND a.id=NEW.artefato_id) THEN
   RAISE EXCEPTION 'artefato pertence a outro recurso da execucao';
  END IF;
 ELSIF TG_TABLE_NAME='snapshot_recurso' THEN
  IF EXISTS (SELECT 1 FROM SNAPSHOT_RECURSO s JOIN ARTEFATO_COLETA a ON a.id=s.artefato_id
             JOIN ARTEFATO_COLETA novo ON novo.recurso_id=a.recurso_id
             WHERE s.snapshot_id=NEW.snapshot_id AND novo.id=NEW.artefato_id AND s.artefato_id<>NEW.artefato_id) THEN
   RAISE EXCEPTION 'snapshot ja contem outro artefato deste recurso';
  END IF;
 ELSIF TG_TABLE_NAME='execucao_coleta' THEN
  IF EXISTS (SELECT 1 FROM EXECUCAO_ARTEFATO ea JOIN ARTEFATO_COLETA a ON a.id=ea.artefato_id
             WHERE ea.execucao_id=NEW.id AND a.recurso_id<>NEW.recurso_id) THEN
   RAISE EXCEPTION 'recurso diverge do artefato da execucao';
  END IF;
 ELSIF TG_TABLE_NAME='artefato_coleta' AND OLD.recurso_id<>NEW.recurso_id THEN
  RAISE EXCEPTION 'origem do artefato e imutavel';
 END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS CK_EXECUCAO_ARTEFATO ON EXECUCAO_ARTEFATO;
CREATE TRIGGER CK_EXECUCAO_ARTEFATO BEFORE INSERT OR UPDATE ON EXECUCAO_ARTEFATO
FOR EACH ROW EXECUTE FUNCTION validar_relacoes_coleta();
DROP TRIGGER IF EXISTS CK_SNAPSHOT_RECURSO ON SNAPSHOT_RECURSO;
CREATE TRIGGER CK_SNAPSHOT_RECURSO BEFORE INSERT OR UPDATE ON SNAPSHOT_RECURSO
FOR EACH ROW EXECUTE FUNCTION validar_relacoes_coleta();
DROP TRIGGER IF EXISTS CK_EXECUCAO_RECURSO ON EXECUCAO_COLETA;
CREATE TRIGGER CK_EXECUCAO_RECURSO BEFORE UPDATE OF recurso_id ON EXECUCAO_COLETA
FOR EACH ROW EXECUTE FUNCTION validar_relacoes_coleta();
DROP TRIGGER IF EXISTS CK_ARTEFATO_RECURSO ON ARTEFATO_COLETA;
CREATE TRIGGER CK_ARTEFATO_RECURSO BEFORE UPDATE OF recurso_id ON ARTEFATO_COLETA
FOR EACH ROW EXECUTE FUNCTION validar_relacoes_coleta();
