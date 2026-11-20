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

- **Linguagem:** Python 3. O modo SQLite usa a biblioteca padrão. O modo
  PostgreSQL e seu migrador usam Psycopg 3 (`psycopg`).
- **Banco:** relacional, com exigência de 3FN para o modelo canônico e
  [revisão das dependências](NORMALIZACAO_RELACIONAL.md). O motor é selecionado em `radar.conf`.
  A [migração para PostgreSQL](MIGRACAO_POSTGRES.md) prepara um esquema e
  valida a cópia das tabelas. A consulta geográfica usa *bounding box* em
  SQL e distância Haversine na aplicação.
- **Web:** **CGI** no padrão da casa — `fcgiwrap` + `nginx` executando um
  arquivo **`.pse`** (entry point fino). Em produção, o acesso HTTP é limitado
  às páginas, aos recursos públicos e às rotas da API.
  **O que é `.pse`:** é só uma **extensão de arquivo** — a convenção histórica
  deste servidor para scripts executáveis do site (`cnpj.pse`, `frase.pse`,
  `pythoninfo.pse`, `api.pse`...), equivalente a um `.cgi`. A API **não** é um
  servidor nem um framework: é um **programa Python 3** que o nginx
  executa **sob demanda** via **fcgiwrap** (FastCGI→CGI), **sem daemon e sem
  porta própria** — cada requisição sobe o processo, responde e termina. Como o
  `fcgiwrap` daqui não define `PATH_INFO`, a rota vai no parâmetro `rota`
  (ex.: `api.pse?rota=/api/v1/radares&lat=..&lon=..&raio=..`).

## Estrutura

```
core/                    pesquisa/comum aos dois lados
  caminhos.py            seleção do radar.conf e resolução de caminhos
  config.py              parâmetros operacionais lidos do radar.conf
  db.py                  conexão com o banco ativo, inicialização do esquema, consultas
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
sql/                     DDL canônica T01..T80 (SQLite e Postgres)
tools/build_schema.py    gerador das duas DDLs a partir de 1 definição
tests/                   unittest (stdlib)
```

## Como rodar

### Entrada única da aplicação

As operações da aplicação entram por `api.pse`: requisições CGI, console,
coleta agendada e manutenção. `web/api.pse` e o wrapper `deploy/api.pse`
usam o mesmo despachante em `core/entrada_api.py`.

Em um checkout novo, crie a configuração local antes de executar os comandos.
Em produção, use o `api.pse` instalado com o usuário que executa o Radar.

```bash
cp -n deploy/radar.conf.exemplo radar.conf
python3 web/api.pse ferramenta inicializar_banco
python3 web/api.pse ferramenta radar_admin listar-usuarios
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

O coletor aceita arquivos locais dentro de `[dados] dir`. Sem `--arquivo`,
busca a publicação oficial e guarda o arquivo bruto por SHA-256.

```bash
mkdir -p dados
cp tests/fixtures/antt_radares_fixture.json dados/
python3 web/api.pse sync --fonte antt --arquivo "$PWD/dados/antt_radares_fixture.json"
python3 web/api.pse sync --fonte antt --help
```

Para trabalhar em outra base, aponte `RADAR_CONF` para o arquivo de
configuração correspondente. Veja os parâmetros dos motores no
[guia de configuração](CONFIGURACAO.md).

### 3. API / CGI

O entry point é `web/api.pse`. Para testar fora do nginx (simulando o CGI):

```bash
REQUEST_METHOD=GET \
QUERY_STRING='rota=/api/v1/radares&lat=-24.9555&lon=-53.4552&raio=5000&formato=txt&delimitador=%7C&limite=0' \
python3 web/api.pse
```

Endpoint → parâmetros (spec §10): `lat`, `lon` (obrigatórios em `/radares`),
`raio` (1..1000000, até 1000 km; padrão 1000), `formato` (`json|ndjson|xml|txt|edi|edifact|dif`),
`delimitador` (só `txt`), `limite` (0 para todos, positivos até o teto da
instância, padrão 100), `cursor`, `uf`,
`municipio_ibge`, `rodovia`, `incluir_inativos`, etc. `GET` e `POST`
(JSON ou form) devolvem o mesmo resultado.

O [guia da API](API_E_EXPORTACAO.md) reúne as rotas, os formatos, a paginação
e o download completo. `GET /api/v1/ajuda` retorna a referência da
versão instalada.

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
na mesma base do Radar. O motor e os caminhos vêm do `radar.conf` instalado.

### 5. Serialização

`json`, `ndjson`, `xml`, `txt` (+ esqueletos `edifact`/`dif`). O **TXT tem
ordem canônica de 32 colunas fixa** (publicada em `/ajuda`), uma linha por
ponto, delimitador trocável, `NULL=\N` e JSON compacto dentro da célula.
A mesma consulta serializada em `json/ndjson/xml/txt` decodifica nos mesmos
valores (testado).

## Status

- [x] Schema canônico T01–T80 + EXECUCAO_ARTEFATO (SQLite + Postgres), PK/FK/UQ/CHECK; dependências revisadas em NORMALIZACAO_RELACIONAL.md
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
