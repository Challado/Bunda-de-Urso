# PRF — registros sem IDENTIFICADOR ou GPS

Recorte de 16 registros publicado no mapa oficial de radares fixos da PRF,
consultado em 24/10/2026. Entrada oficial:
https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos

A página incorpora https://mapas-html.vercel.app/ e a tabela que consulta o
JSON público do Google Apps Script. A resposta consultada tinha 1.591 registros.
Os 16 deste recorte declaram EQUIPAMENTO, UF, município, BR, km, sentido e
ESTADO=INOPERANTE, mas IDENTIFICADOR/LATITUDE/LONGITUDE são nulos.
Preservam-se os campos publicados. O código EQUIPAMENTO é identificador
administrativo; não é número de série. O teste exige 16 cadastros inativos,
sem posições inventadas, mantendo os dados e as rejeições históricas.
