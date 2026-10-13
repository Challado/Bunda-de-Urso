# Governança da ingestão — contrato e operação

Camada de confiança do **Bunda de Urso**: leitura aberta, criação aberta (com selo),
verificação/edição/remoção só com chave de gestão. **Regra dura: nada escreve direto no
banco — tudo passa pela API** (inclusive o painel).

- Config versionada: `config/governanca.json`
- Esquema aditivo (migração 0001): `sql/migracoes/0001_governanca.sqlite.sql` (+ `.postgres.sql`)
- Lógica/escrita: `core/governanca.py`; rotas: `web/nucleo.py`; CLI: `tools/radar_admin.py`
- Testes: `tests/test_governanca.py`

No servidor, a rota vai no parâmetro `rota` do `.pse`. Exemplos abaixo já nesse formato.

## 1. Submissão pública (sem token)

Publica na hora como `colaborativo`/`nao_verificado`. Se houver ponto oficial no raio de
correspondência (default 150 m), corrobora automaticamente. Rate limit por IP → `429`.
Coordenada dentro de bloqueio ativo → `409` com motivo.

```bash
curl -s -X POST 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares/submeter' \
  -H 'Content-Type: application/json' \
  -d '{"latitude":-23.5501,"longitude":-46.6301,"municipio":"Sao Paulo","uf":"SP","via":"BR-116","tipo_radar":"fixo","velocidade_geral":60}'
# → 201 {"resultado":{"ok":true,"aceitos":1,"corroborados":0,"rejeitados":0,"erros":[]}}
```

Aceita objeto único **ou** array; erro por índice/campo em `erro.detalhes`.

## 2. Login / sessão do painel

```bash
# login (devolve token e define o cookie HttpOnly radar_sessao)
curl -s -c jar.txt -X POST 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/login' \
  -H 'Content-Type: application/json' -d '{"login":"admin","senha":"..."}'
# → 200 {"token":"s_...","usuario":{"papel":"admin","deve_trocar_senha":true}}

# logout
curl -s -b jar.txt -X POST 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/logout'

# troca a propria senha (exige a atual)
curl -s -b jar.txt -X POST 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/minha-senha' \
  -H 'Content-Type: application/json' -d '{"senha_atual":"...","senha_nova":"..."}'
```

Falha de login é **genérica** (`401 credenciais_invalidas`) e o tempo de resposta é
constante (não revela se o login existe). Tokens de API **não** trocam senha.

## 3. Gestão

Autenticação: cookie de sessão **ou** cabeçalho `X-Api-Token`. Escopos:
`contribuidor` (lê) < `moderador` (verifica/edita/desabilita/remove) < `admin`
(usuários, tokens, bloqueios). Sem credencial → `401`; escopo insuficiente → `403`.

```bash
TOKEN=rb_xxxxxxxx
B='https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota='

# fila de colaborativos não verificados
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/pendentes"

# ver / editar um radar
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/radar/123"
curl -s -X PATCH -H "X-Api-Token: $TOKEN" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/radar/123" -d '{"observacoes":"confirmado no local","km":12.5}'

# verificar
curl -s -X POST -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/radar/123/verificar" \
  -H 'Content-Type: application/json' -d '{"motivo":"vistoria"}'

# desabilitar (motivo OBRIGATORIO)
curl -s -X POST -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/radar/123/desabilitar" \
  -H 'Content-Type: application/json' -d '{"motivo":"em manutencao"}'

# remover = TOMBSTONE (motivo OBRIGATORIO; a linha NUNCA e apagada)
curl -s -X POST -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/radar/123/remover" \
  -H 'Content-Type: application/json' -d '{"motivo":"radar inexistente"}'

# historico autenticado (com ip/quem)
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/radar/123/historico"
```

### Bloqueios geográficos (admin)

```bash
# listar ativos
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/bloqueios"

# criar marcacao_falsa (raio menor) ou zona_sombra (raio maior)
curl -s -X POST -H "X-Api-Token: $TOKEN" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/bloqueios" \
  -d '{"tipo":"zona_sombra","latitude":-23.55,"longitude":-46.63,"raio_metros":1000,"motivo":"sabotagem"}'

# desativar (soft: ativo=0, permanece no historico)
curl -s -X DELETE -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/bloqueios/7"
```

### Tokens (admin)

```bash
# emitir — o VALOR aparece UMA unica vez
curl -s -X POST -H "X-Api-Token: $TOKEN" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/tokens" -d '{"nome":"github:fulano","escopo":"moderador"}'
# → 201 {"token_id":3,"token":"rb_...","prefixo":"rb_XXXXXXX","aviso":"guarde..."}

# listar — so prefixo, nunca o valor
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/tokens"

# revogar (marca revogado_em; nao apaga)
curl -s -X POST -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/tokens/3/revogar"
```

### Usuários (admin)

```bash
curl -s -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/usuarios"

# criar (sem senha -> temporaria devolvida UMA vez, deve_trocar_senha=1)
curl -s -X POST -H "X-Api-Token: $TOKEN" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/usuarios" -d '{"login":"mod1","papel":"moderador"}'

# papel / ativo
curl -s -X PATCH -H "X-Api-Token: $TOKEN" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/usuarios/2" -d '{"papel":"admin","ativo":true}'

# reset de senha (gera temporaria, deve_trocar_senha=1)
curl -s -X POST -H "X-Api-Token: $TOKEN" "${B}/api/v1/gestao/usuarios/2/senha"
```

### Contexto da sessão e vínculo de correspondência (apoio ao painel)

```bash
# quem sou eu (login/papel) — o painel usa para decidir o que exibir
curl -s -b jar.txt "${B}/api/v1/gestao/eu"
# -> 200 {"autenticado":true,"escopo":"admin","rotulo":"admin","tipo":"usuario"}

# resolver o vínculo com o ponto oficial (moderador)
curl -s -X POST -H "X-Api-Token: ***" -H 'Content-Type: application/json' \
  "${B}/api/v1/gestao/correspondencias/5" \
  -d '{"status":"colaborativo_vence","motivo":"o ponto correto e o colaborativo"}'
# status: oficial_vence (remove o colaborativo) | colaborativo_vence
```

## 4. Histórico público (transparência)

```bash
curl -s 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares/123/historico'
# → 200 {"historico":[{"tipo":"criado",...},{"tipo":"removido","motivo":"..."}]}
```

## 5. Como ficou a consulta pública

Em `core.consultas` a consulta (`/api/v1/radares`, `/api/v1/radares/busca`) passa a:

1. **Esconder** pontos com `removido_em` (tombstone) ou `verificacao_status='desabilitado'`.
2. **Preferir o colaborativo**: quando um colaborativo ativo tem vínculo
   `CORRESPONDENCIA_PONTO` com status `corroborado`/`colaborativo_vence`, o ponto
   **oficial correspondente é omitido** da resposta (o colaborativo é o exibido).
   Se o vínculo for resolvido como `oficial_vence`, o colaborativo é removido
   (tombstone) e o oficial volta a aparecer.

Os pontos agora expõem `procedencia` e `verificacao_status` no JSON; a ordem canônica
TXT/EDIFACT/DIF permanece intacta (as colunas de governança são aditivas, fora das 32
colunas canônicas). Bases antigas (sem a camada) continuam respondendo normalmente.

## 6. Configuração e migração

`config/governanca.json`:

```json
{"RAIO_CORRESPONDENCIA_M":150,"RAIO_ZONA_SOMBRA_M":1000,
 "SUBMISSAO_LIMITE":20,"SUBMISSAO_JANELA_SEGUNDOS":3600,
 "SESSAO_TTL_SEGUNDOS":28800,"GOV_ITERACOES":200000}
```

Override por ambiente: `RADAR_GOV_<CHAVE>` (ex.: `RADAR_GOV_SUBMISSAO_LIMITE=5`).

A migração é **aditiva e idempotente** (`core.governanca.aplicar_migracoes`), aplicada na
primeira chamada de governança e registrada em `MIGRACAO_GOVERNANCA`. Não altera o
esquema canônico T01..T77 nem o `init_db`.

## 7. CLI de administração (anti-lockout)

Roda no host, fora do painel: `tools/radar_admin.py` (usa as MESMAS funções do app e o
mesmo banco). A senha inicial **não mora no repositório** — vem de `--senha`, do stdin
(`getpass`) ou de `RADAR_ADMIN_SENHA`.

```bash
python3 tools/radar_admin.py criar-admin admin            # deve_trocar_senha=1
python3 tools/radar_admin.py reset-senha admin            # senha temporaria, 1x
python3 tools/radar_admin.py listar-usuarios
python3 tools/radar_admin.py criar-token --nome github:fulano --escopo moderador
python3 tools/radar_admin.py revogar-token 3
```

## 8. Painel HTML de administração

Fica em `web/gestao.html` (painel) e `web/usuarios.html` (usuários + tokens). HTML/CSS/JS
vanilla, sem CDN, **falando sempre pela API** (`api.pse?rota=...`) com
`credentials:'same-origin'` (cookie de sessão) — nunca lê o banco direto.

- `gestao.html` — login quando não há sessão; fila de pendentes (com filtro de status);
detalhe do radar (km, observações, velocidade, tipo de pista); verificar; desabilitar e
remover (motivo obrigatório, tombstone); histórico/auditoria; vínculos de correspondência;
bloqueios geográficos; emitir/revogar tokens; trocar a própria senha; link para usuários.
As ações aparecem conforme o escopo do login (contribuidor = leitura; moderador = moderação;
admin = bloqueios/tokens/usuários).
- `usuarios.html` — criar usuário (papel admin/moderador; senha em branco gera temporária
exibida uma única vez), mudar papel, ativar/desativar, resetar senha, e emitir/revogar
tokens. Exige escopo admin; sem sessão, aponta para o painel.

O valor de um token/senha temporária aparece **uma única vez** na emissão; depois só o
prefixo. As duas rotas de apoio (`/api/v1/gestao/eu` e
`/api/v1/gestao/correspondencias/{id}`) vivem em `web/nucleo.py`, junto das demais de
governança.
