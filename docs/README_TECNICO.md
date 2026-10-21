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

- **Linguagem:** Python 3 (só stdlib — `urllib`, `sqlite3`, `csv`, `json`,
  `xml.etree`). Sem pip, sem dependências externas.
- **Banco:** relacional, com exigência de 3FN e [revisão das dependências](NORMALIZACAO_RELACIONAL.md). SQLite em produção; Postgres
  suportado pela DDL gêmea. **Sem PostGIS** — a consulta geográfica usa
  *bounding box* em SQL + distância Haversine na aplicação.
- **Web:** **CGI** no padrão da casa — `fcgiwrap` + `nginx` executando um
  arquivo **`.pse`** (entry point fino); toda a lógica mora fora do webroot.
  **O que é `.pse`:** é só uma **extensão de arquivo** — a convenção histórica
  deste servidor para scripts executáveis do site (`cnpj.pse`, `frase.pse`,
  `pythoninfo.pse`, `api.pse`...), equivalente a um `.cgi`. A API **não** é um
  servidor nem um framework: é um **programa Python 3 (só stdlib)** que o nginx
  executa **sob demanda** via **fcgiwrap** (FastCGI→CGI), **sem daemon e sem
  porta própria** — cada requisição sobe o processo, responde e termina. Como o
  `fcgiwrap` daqui não define `PATH_INFO`, a rota vai no parâmetro `rota`
  (ex.: `api.pse?rota=/api/v1/radares&lat=..&lon=..&raio=..`).

## Estrutura

```
core/                    pesquisa/comum aos dois lados
  config.py              caminhos e variáveis de ambiente
  db.py                  conexão SQLite (FK=ON), init do schema, helpers
  geo.py                 Haversine + bounding box (sem dependências)
  consultas.py           consulta read-only (bbox em SQL + Haversine)
  domains.py             catálogos (T03, T07..T22, T75, T76) e UFs
  serializers/           json, ndjson, xml, txt (32 colunas) + edifact/dif
coletor/                 sincronizador (processo independente da web)
  base.py                cache imutável (sha256), staging, snapshot atômico
  fontes/antt.py         conector ANTT (F02/F03) — JSON/CSV
  fontes/recife.py       conector Recife (F12) — CSV
  fontes/normalizacao.py normalização compartilhada → modelo canônico
  sync.py                CLI: python3 -m coletor.sync
web/                     entry point CGI (.pse) + roteamento/response
sql/                     DDL canônica T01..T77 (SQLite e Postgres)
tools/build_schema.py    gerador das duas DDLs a partir de 1 definição
tests/                   unittest (stdlib)
```

## Como rodar

### Entrada única da aplicação

As operações da aplicação entram por `api.pse`: requisições CGI, console,
coleta agendada e manutenção. `web/api.pse` e o wrapper `deploy/api.pse`
usam o mesmo despachante em `core/entrada_api.py`.

No próprio servidor, os comandos são locais:

```bash
python3 web/api.pse ferramenta inicializar_banco
python3 web/api.pse ferramenta radar_admin listar-usuarios
python3 web/api.pse sync --fonte antt --arquivo tests/fixtures/antt_radares_fixture.json
python3 web/api.pse tick --help
```

Os caminhos antigos em `tools/` e `coletor/sync.py`/`tick.py` permanecem como
clientes que chamam `api.pse`, preservando argumentos e código de saída.
As implementações de manutenção ficam em `core/manutencao/`, o console em
`core/console_api.py`, e todas as conexões físicas passam por `core/db.py`.
O modo local exige acesso de operador ao servidor e não é exposto por rotas
HTTP. A autenticação das rotas administrativas web continua obrigatória.

`verificar_banco.py` fiscaliza também ferramentas, deploy e arquivos novos,
incluindo aliases de importação de conexões. Testes podem montar e inspecionar
bases temporárias para verificar os resultados da API.

### 1. Schema

As DDLs já estão geradas em `sql/`. A definição única fica em
`core/manutencao/build_schema.py`; o cliente `tools/build_schema.py` chama
essa operação pela API. Para regenerá-las e conferir as tabelas no SQLite:

```bash
python3 tools/build_schema.py     # gera sql/schema.sqlite.sql e sql/schema.postgres.sql
```

O schema é carregado automaticamente pelo coletor (`core.db.init_db`) e pelos
testes. Para um banco novo:

```bash
python3 web/api.pse ferramenta inicializar_banco
```

### 2. Coletor / sincronização

Aceita arquivo local (testes sem rede) ou baixa da URL publicada:

```bash
# ANTT a partir de uma fixture local
python3 -m coletor.sync --fonte antt --arquivo tests/fixtures/antt_radares_fixture.json

# Recife a partir do CSV
python3 -m coletor.sync --fonte recife --arquivo tests/fixtures/recife_equipamentos.csv

# sem --arquivo baixa da URL do portal oficial (urllib), com cache por sha256
python3 -m coletor.sync --fonte antt

# banco alternativo
python3 -m coletor.sync --fonte antt --arquivo fixture.json --db /caminho/radar.sqlite3
```

Variáveis de ambiente: `RADAR_DATA_DIR` (padrão `dados/`), `RADAR_DB`
(padrão `dados/radar.sqlite3`), `RADAR_BRASIL_HOME`.

### 3. API / CGI

O entry point é `web/api.pse`. Para testar fora do nginx (simulando o CGI):

```bash
export RADAR_DB=/tmp/radar.sqlite3
python3 -m coletor.sync --fonte antt --arquivo tests/fixtures/antt_radares_fixture.json

REQUEST_METHOD=GET \
QUERY_STRING='lat=-24.9555&lon=-53.4552&raio=5000&formato=txt&delimitador=%7C' \
PATH_INFO='/api/v1/radares' python3 web/api.pse
```

Endpoint → parâmetros (spec §10): `lat`, `lon` (obrigatórios em `/radares`),
`raio` (1..1000000, até 1000 km; padrão 1000), `formato` (`json|ndjson|xml|txt|edi|edifact|dif`),
`delimitador` (só `txt`), `limite` (1..1000, padrão 100), `cursor`, `uf`,
`municipio_ibge`, `rodovia`, `incluir_inativos`, etc. `GET` e `POST`
(JSON ou form) devolvem o mesmo resultado.

Endpoints: `/api/v1/radares`, `/api/v1/radares/{id}`, `/api/v1/ajuda`,
`/api/v1/status`, `/api/v1/fontes`, `/health/live`, `/health/ready`.

### 4. Testes

```bash
python3 -m unittest discover -s tests
```

### Cadastro público

`web/cadastro.html` abre no modo **simplificado**, com apenas latitude,
longitude e velocidade. O modo **expert** acrescenta identificação, tipo,
município, via, km, sentido, observações e contato; permite município + via
quando as coordenadas não são conhecidas. Campos ocultos não são enviados.

O formulário envia `POST /api/v1/radares/submeter`. A resposta de sucesso é
HTTP 201, com os contadores e IDs dentro de `resultado`. Reenvios idênticos
retornam o cadastro existente em `cadastros` e `ja_cadastrados`, sem duplicá-lo.

Após salvar, a base procura candidatos oficiais no raio configurado em
`RAIO_CORRESPONDENCIA_M` (150 m por padrão). Com um único candidato e sem
divergência de município/via, preenche apenas lacunas de município, via, km
e pista. Coordenadas, velocidade informada, identidade e situação do radar
não são copiadas. A origem do complemento fica na auditoria e na proveniência
do detalhe; o novo ponto continua não verificado. Vários candidatos geram
sugestões de correspondência, sem complementação automática.

O cadastro próprio Bundita e as contribuições públicas são fontes distintas
na mesma base SQLite, definida por `RADAR_DB` (padrão `dados/radar.sqlite3`).
O wrapper de produção em `deploy/api.pse` usa por padrão
`/var/lib/radar-brasil/radar.sqlite3`.

### 5. Serialização

`json`, `ndjson`, `xml`, `txt` (+ esqueletos `edifact`/`dif`). O **TXT tem
ordem canônica de 32 colunas fixa** (publicada em `/ajuda`), uma linha por
ponto, delimitador trocável, `NULL=\N` e JSON compacto dentro da célula.
A mesma consulta serializada em `json/ndjson/xml/txt` decodifica nos mesmos
valores (testado).

## Status

- [x] Schema canônico T01–T77 + EXECUCAO_ARTEFATO (SQLite + Postgres), PK/FK/UQ/CHECK; dependências revisadas em NORMALIZACAO_RELACIONAL.md
- [x] Coletor: cache imutável sha256, staging, snapshot atômico, conectores ANTT/Recife
- [x] API: `/radares`, `/radares/{id}`, `/ajuda`, `/status`, `/fontes` (GET/POST)
- [x] TXT 32 colunas + paridade json/ndjson/xml/txt; esqueletos edifact/dif
- [x] Testes (stdlib unittest) — schema, geo, TXT, paridade, CGI
- [ ] Dedup rastreável (T68–T70 tabelas prontas; algoritmo de matching a evoluir)
- [ ] Conectores das demais fontes (§2: F01, F04–F11, F13–F16)
- [ ] `/trechos`, `/operacoes`, `/equipamentos/{id}`, `/atualizacoes`

## Limitações conhecidas (nada é inventado)

- Sem `codigo_ibge` na fonte, o município não é criado (PK é o código IBGE) e,
  por conseguinte, **UF/município não são persistidos** — a spec §3.6 proíbe
  duplicar a UF fora do município. Coordenada ausente ⇒ registro preservado em
  `REGISTRO_FONTE` e **não posicionado** (sem radar fictício).
- `REGISTRO_FONTE` guarda o payload original íntegro; campos oficiais ainda não
  mapeados ficam lá (catálogo de mapeamento T71 para evolução).
- Os esqueletos EDIFACT/DIF são funcionais (envelope válido, uma linha por
  ponto, 32 colunas), documentados no próprio módulo; não afirmam conformidade
  com um tipo de mensagem UN/EDIFACT padronizado.
