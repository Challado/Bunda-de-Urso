ALTER TABLE TRECHO_ELEGIVEL ADD COLUMN IF NOT EXISTS uf_sigla CHAR(2) REFERENCES UF(sigla) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS IX_TRECHO_UF ON TRECHO_ELEGIVEL(uf_sigla);

WITH declarada AS (
    SELECT t.id, CASE
        WHEN f.nome = 'SIE-SC/PMRv - Locais elegiveis de fiscalizacao portatil' THEN 'SC'
        WHEN f.nome = 'DAER-RS - Locais de fiscalizacao com radar portatil' THEN 'RS'
        WHEN f.nome = 'DER-RJ - Radares portateis (locais de fiscalizacao)' THEN 'RJ'
        WHEN f.nome = 'PRF - Trechos criticos para radar portatil'
            THEN upper(split_part(trim(r.identificador_na_fonte), ' ', 1))
        END AS sigla
    FROM TRECHO_ELEGIVEL t
    JOIN REGISTRO_FONTE r ON r.id=t.registro_fonte_id
    JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
    JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
    JOIN FONTE f ON f.id=rf.fonte_id
    WHERE t.uf_sigla IS NULL
)
UPDATE TRECHO_ELEGIVEL AS t SET uf_sigla=u.sigla
FROM declarada d JOIN UF u ON u.sigla=d.sigla
WHERE d.id=t.id AND t.uf_sigla IS NULL;
