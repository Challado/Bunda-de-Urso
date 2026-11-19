-- A origem e a chave são obtidas por meio da revisão a que pertencem.
CREATE TEMP TABLE VALIDAR_IDENTIDADE_MESH (ok INTEGER CONSTRAINT identidade_mesh_divergente CHECK(ok=1));
INSERT INTO VALIDAR_IDENTIDADE_MESH SELECT CASE WHEN EXISTS (SELECT 1 FROM TRASEIRO_CADASTRO c LEFT JOIN TRASEIRO_EVENTO e ON e.seq=c.evento_id
    WHERE e.seq IS NULL OR e.tipo<>'radar.v1' OR c.origem<>e.origem OR c.chave<>e.chave) THEN 0 ELSE 1 END;
DROP TABLE VALIDAR_IDENTIDADE_MESH;
ALTER TABLE TRASEIRO_CADASTRO DROP COLUMN origem;
ALTER TABLE TRASEIRO_CADASTRO DROP COLUMN chave;
ALTER TABLE TRASEIRO_CADASTRO ADD UNIQUE (evento_id);
CREATE FUNCTION validar_traseiro_cadastro() RETURNS trigger SET search_path FROM CURRENT AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(json_build_array(e.origem,e.tipo,e.chave)::text,0))
  FROM TRASEIRO_EVENTO e WHERE e.seq=NEW.evento_id;
  IF NOT EXISTS (SELECT 1 FROM TRASEIRO_EVENTO WHERE seq=NEW.evento_id AND tipo='radar.v1')
 OR EXISTS (SELECT 1 FROM TRASEIRO_CADASTRO d JOIN TRASEIRO_EVENTO a ON a.seq=d.evento_id
     JOIN TRASEIRO_EVENTO b ON b.seq=NEW.evento_id AND b.origem=a.origem AND b.chave=a.chave
     WHERE d.id<>NEW.id) THEN
    RAISE EXCEPTION 'identidade de evento mesh inválida ou duplicada' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER CK_TRASEIRO_CADASTRO AFTER INSERT OR UPDATE ON TRASEIRO_CADASTRO
FOR EACH ROW EXECUTE FUNCTION validar_traseiro_cadastro();
CREATE TEMP TABLE VALIDAR_IDENTIDADE_MESH (ok INTEGER CONSTRAINT identidade_mesh_divergente CHECK(ok=1));
INSERT INTO VALIDAR_IDENTIDADE_MESH SELECT CASE WHEN EXISTS (SELECT 1 FROM TRASEIRO_FONTE c LEFT JOIN TRASEIRO_EVENTO e ON e.seq=c.evento_id
    WHERE e.seq IS NULL OR e.tipo<>'fonte-coleta.v1' OR c.origem<>e.origem OR c.chave<>e.chave) THEN 0 ELSE 1 END;
DROP TABLE VALIDAR_IDENTIDADE_MESH;
ALTER TABLE TRASEIRO_FONTE DROP COLUMN origem;
ALTER TABLE TRASEIRO_FONTE DROP COLUMN chave;
ALTER TABLE TRASEIRO_FONTE ADD UNIQUE (evento_id);
CREATE FUNCTION validar_traseiro_fonte() RETURNS trigger SET search_path FROM CURRENT AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(json_build_array(e.origem,e.tipo,e.chave)::text,0))
  FROM TRASEIRO_EVENTO e WHERE e.seq=NEW.evento_id;
  IF NOT EXISTS (SELECT 1 FROM TRASEIRO_EVENTO WHERE seq=NEW.evento_id AND tipo='fonte-coleta.v1')
 OR EXISTS (SELECT 1 FROM TRASEIRO_FONTE d JOIN TRASEIRO_EVENTO a ON a.seq=d.evento_id
     JOIN TRASEIRO_EVENTO b ON b.seq=NEW.evento_id AND b.origem=a.origem AND b.chave=a.chave
     WHERE d.id<>NEW.id) THEN
    RAISE EXCEPTION 'identidade de evento mesh inválida ou duplicada' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER CK_TRASEIRO_FONTE AFTER INSERT OR UPDATE ON TRASEIRO_FONTE
FOR EACH ROW EXECUTE FUNCTION validar_traseiro_fonte();
