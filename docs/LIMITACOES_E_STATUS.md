# Limitações e status reais do Radar Brasil (10/10/2026)

Estado verificado **no nosso código** (`README.md`, `sql/schema.sqlite.sql`,
`tools/build_schema.py`, `coletor/`, `core/`, `web/`, `tests/`). Nada aqui é
copiado de outra entrega: cada item abaixo foi checado neste repositório. O
que não pôde ser confirmado está marcado **a confirmar** (não inventado).

## Execução funcional verificada localmente

- **Stack:** Python 3, **só stdlib** (`urllib`, `sqlite3`, `csv`, `json`,
  `xml.etree`, `zlib`, `html.parser`). **Sem SQLAlchemy, sem pip, sem
  dependências externas.** Consequência de projeto, não limitação.
- **Schema:** **77 tabelas (T01..T77)** — `grep -c "CREATE TABLE"
  sql/schema.sqlite.sql` = 77. PK/FK/UNIQUE/CHECK/NOT NULL. Fonte única em
  `tools/build_schema.py`, que gera `sql/schema.sqlite.sql` (SQLite) e
  `sql/schema.postgres.sql` (Postgres). SQLite é o alvo exercitado
  (coletor e testes carregam o schema).
- **Coletor** (`coletor/`): cache imutável por sha256, staging, snapshot
  atômico, `SAVEPOINT` por registro (um registro ruim não derruba a fonte),
  idempotência por hash de artefato. Agenda por fonte + tick
  (`coletor/agenda.py`, `coletor/tick.py`) com backoff exponencial em erro e
  lockfile (duas passadas não se sobrepõem).
- **Conectores implementados** (e cobertos por teste com fixture local):
  `ColetorANTT` (F02), `ColetorRecife` (F12), `ColetorDNIT` (F04),
  `ColetorDERSP` (F08), `ColetorDERPR` (F09), `ColetorDERMG` (F10),
  `ColetorPBH` (F13), `ColetorPRFFixos`/`ColetorPRFPortateis`/
  `ColetorPRFTrechos` (F05/F06/F07), `ColetorINMETRO` (F01) e `ColetorOSM`
  (F15, complementar, **desligado por padrão** na agenda).
- **API/CGI** (`web/nucleo.py` + `web/api.pse`, GET e POST devolvem o mesmo
  resultado). Endpoints **com handler e teste**:
  `/api/v1/radares`, `/api/v1/radares/busca`, `/api/v1/radares/{id}`,
  `/api/v1/trafego`, `/api/v1/trechos`, `/api/v1/operacoes`,
  `/api/v1/equipamentos/{id}`, `/api/v1/fontes`, `/api/v1/fontes/{id}`,
  `/api/v1/atualizacoes`, `/api/v1/ajuda`, `/api/v1/status`, `/health/live`,
  `/health/ready`.
- **Serialização** (`core/serializers/`): `json`, `ndjson`, `xml`, `txt`
  (ordem canônica de **32 colunas**, `NULL=\N`, delimitador trocável) e os
  esqueletos funcionais `edi`/`edifact` e `dif`. Há teste de paridade
  json/ndjson/xml/txt.
- **Deduplicação** (`core/dedup.py`): módulo implementado com cadeia de
  evidência, `gerar_candidatos`, `decidir`, `aplicar`, `reverter_decisao`,
  `verificacoes_duplicadas`, `registrar_regra`.
- **Testes:** `python3 -m unittest discover -s tests` → **185 testes, OK**
  (executado localmente em 10/10/2026). Cobrem schema, geo, TXT, paridade,
  CGI, dedup, tick, conectores com fixture de arquivo, PRF/OSM, INMETRO,
  CKAN, endpoints e EDIFACT/DIF.

## Divergências entre o README e o código (a corrigir/observar)

- O checklist "Status" do `README.md` marca como **pendentes** `/trechos`,
  `/operacoes`, `/equipamentos/{id}` e `/atualizacoes` — mas esses endpoints
  **estão implementados e testados** (`tests/test_endpoints.py`). O checklist
  do README está **desatualizado** frente ao código.
- O bloco "Estrutura" do README cita só `fontes/antt.py` e `fontes/recife.py`,
  mas existem conectores para 10 fontes (acima).
- O **CLI** `python3 -m coletor.sync` só conhece `antt` e `recife`
  (`FONTES` em `coletor/sync.py`); para as demais fontes use o `tick`
  (`python3 -m coletor.tick --forcar <fonte> --arquivo <FONTE=path>`).

## Pendências reais (o que ainda falta)

1. **Coleta HTTP real ponta a ponta:** não foi executada neste ambiente
   (sem acesso às fontes governamentais). Os conectores foram exercitados
   com **arquivos fixture locais**. Rodar o `tick`/`sync` em host com rede e
   comparar com alguns registros oficiais antes de considerar homologado.
2. **F03 ANTT — tráfego:** **sem conector**. Existem a tabela
   `OBSERVACAO_TRAFEGO` (T53) e o endpoint `/api/v1/trafego`, mas nenhum
   importador de tráfego. Velocidade de passagem jamais deve virar limite
   regulamentado.
3. **F11 Curitiba, F14 (demais 26 UF/DF/municípios), F16 Maparadar:** **sem
   conector**. A cobertura nacional é **PARCIAL**; ausência de resultado não
   prova ausência de fiscalização.
4. **Endpoints administrativos:** `web/nucleo.py` **declara**
   `/api/v1/admin/sincronizar` e `/api/v1/admin/rollback` em
   `ENDPOINTS_ADMINISTRATIVOS`, mas **a confirmar** — não localizei o
   handler correspondente no roteamento de `handle_request`; a autenticação
   também não está implementada.
5. **Dedup não ligada ao pipeline:** `core/dedup.py` existe, mas
   `coletor/base.py::sincronizar` **não chama** a dedup. Logo, **candidatos
   não são gerados automaticamente durante a coleta**; a rotina exige
   invocação explícita. A aprovação de fusão interfontes (transacional e
   reversível) é o próximo passo.
6. **INMETRO automático:** usa o conjunto **estático** por UF
   `https://servicos.rbmlq.gov.br/dados-abertos/{UF}/medidores.json`. Na
   verificação, **26 de 27 UFs** responderam 200 (DF respondeu 404 — não há
   arquivo próprio). A consulta `/Instrumento` é POST + reCAPTCHA e **não é
   contornada**. Reconfirmar a disponibilidade/atualidade a cada execução.
7. **Documentos sem dados estruturados:** DER-PR (PDF) usa extração de texto
   "best-effort" (stdlib `zlib`); a página de portátil do DER-PR não publica
   arquivo baixável. PDFs/layouts externos podem exigir adaptador específico.
8. **Sem posição na fonte:** INMETRO (`LocalVerificacao` é texto livre),
   DER-PR, DER-MG e PRF-portáteis não trazem coordenada; esses registros são
   preservados em `REGISTRO_FONTE` e **não posicionados** (sem radar
   fictício). Isso é regra, não falha.
9. **Postgres:** a DDL é gerada (`sql/schema.postgres.sql`), mas **a
   confirmar** execução/carga reais em Postgres — só SQLite foi exercitado.
10. **Migrations / volume:** o esquema canônico (T01..T77) é criado por
   `init_db`; a camada de **governança** (USUARIO, API_TOKEN, SESSAO,
   RADAR_ALTERACAO, BLOQUEIO_GEOGRAFICO, CORRESPONDENCIA_PONTO,
   SUBMISSAO_PUBLICA) entra por **migração aditiva versionada**
   (`sql/migracoes/`, aplicada e registrada em `MIGRACAO_GOVERNANCA`).
   Ingestão processa a lista em memória (não homologada para datasets de
   milhões de observações).
11. **EDIFACT/DIF:** perfis/esqueletos **funcionais**, mas **não
    homologados** com parser/leitor externo. O EDIFACT é perfil bilateral
    (ver `docs/EDIFACT_PERFIL.md`), **não** um MIG aceito por terceiros; e
    **não** implementa o esquema Base64/`FTX` da referência.
12. **Notificações externas:** não há envio por e-mail/webhook. O painel
    administrativo é servido pela própria API de governança
    (`/api/v1/gestao/*`); a única ferramenta fora do painel é a CLI
    `tools/radar_admin.py` (anti-lockout).

## Regra de ouro

**Qualquer integração não testada deve constar como NÃO validada; não criar
dados de fonte fictícios para ocultar falhas.** Campos sem origem oficial
ficam como `a confirmar` e o payload bruto é sempre preservado em
`REGISTRO_FONTE.payload_original`.
