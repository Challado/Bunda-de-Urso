# Radar Brasil

Coletor + API de consulta de **radares de velocidade** (fiscalização) no Brasil.

Implementação da especificação `ESPECIFICACAO_v1.1.txt` (Radar Brasil — especificação
funcional, relacional e de integração, v1.1 10/10/2026).

O projeto é dividido em **duas partes independentes**:

1. **COLETOR/SINCRONIZADOR** — descobre as fontes, baixa o arquivo bruto, valida,
   persiste imutavelmente, normaliza, deduplica e publica um *snapshot*.
2. **APLICAÇÃO WEB/API DE CONSULTA** — serve os dados consolidados em GET/POST,
   em seis formatos.

## Stack

- **Linguagem:** Python 3 (nos dois lados — o mesmo `core` é usado pelo coletor e
  pela API, garantindo paridade de serialização entre os formatos).
- **Banco:** relacional normalizado (3FN). SQLite para desenvolvimento; Postgres,
  MySQL/MariaDB e Firebird suportados pelas mesmas DDLs. **Sem PostGIS** — a consulta
  geográfica usa *bounding box* em SQL + distância Haversine na aplicação.
- **Web:** **CGI** no padrão da casa — `fcgiwrap` + nginx executando um `.pse`
  (entry point fino no webroot); toda a lógica mora fora do webroot.

## Estrutura

```
core/        modelos, serializadores (json/ndjson/xml/txt/edifact/dif), geo, banco
coletor/     conectores por fonte + orquestração de sincronização
web/         entry point CGI (.pse) + roteamento + resposta
sql/         DDL e migrações (SQLite / Postgres / ...)
tests/       testes de integridade, geo e paridade de serialização
```

## API

Endpoints previstos (spec §9):

```
GET/POST /api/v1/radares      GET /api/v1/radares/{id}
GET/POST /api/v1/trechos      GET /api/v1/equipamentos/{id}
GET/POST /api/v1/operacoes    GET /api/v1/fontes
GET/POST /api/v1/ajuda        GET /api/v1/atualizacoes
GET/POST /api/v1/status
```

Formatos: `json`, `ndjson`, `xml`, `txt`, `edifact`, `dif`.
`txt` tem **ordem canônica de 32 colunas fixa** (publicada em `/ajuda`),
delimitador trocável, `\N` para NULL e JSON compacto dentro da célula.

## Status

- [x] Especificação versionada
- [ ] Schema canônico (T01–T77)
- [ ] Coletor: conectores por fonte
- [ ] API: `/radares` (json/ndjson/txt) + `/ajuda`
- [ ] Deduplicação rastreável
- [ ] Formatos edifact/dif
- [ ] Testes de aceitação
