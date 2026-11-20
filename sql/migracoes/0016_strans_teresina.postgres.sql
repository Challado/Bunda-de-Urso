-- Atualiza o leitor da STRANS sem trocar os IDs da fonte e do recurso.
UPDATE ORGANIZACAO SET nome='STRANS Teresina'
WHERE nome='STRANS Teresina / DER-PI'
  AND NOT EXISTS (SELECT 1 FROM ORGANIZACAO WHERE nome='STRANS Teresina');

UPDATE RECURSO_FONTE
SET nome='Mapa de fiscalizacao eletronica (KML)',
    url_recurso='https://www.teresina.pi.gov.br/strans/localizacao-de-radares/',
    formato_origem='kml', periodicidade_segundos=604800, status_integracao='ok'
WHERE nome='noticia historica anunciando divulgacao da lista (2019)'
  AND fonte_id IN (
      SELECT id FROM FONTE WHERE nome='STRANS Teresina - Localizacao de radares (noticia 2019)'
  );

UPDATE FONTE
SET nome='STRANS Teresina - Localizacao de radares',
    organizacao_id=COALESCE(
        (SELECT id FROM ORGANIZACAO WHERE nome='STRANS Teresina'), organizacao_id),
    url_institucional='https://www.teresina.pi.gov.br/strans/',
    documentacao_url='https://www.teresina.pi.gov.br/strans/localizacao-de-radares/'
WHERE nome='STRANS Teresina - Localizacao de radares (noticia 2019)';
