# Migrar o Radar Brasil de SQLite para PostgreSQL

O migrador roda no servidor do Radar. Ele lê o arquivo de origem de `[sqlite]
banco` em `radar.conf`, cria um esquema no PostgreSQL e pode ativá-lo para toda a
instalação.

## Preparar o destino

Use PostgreSQL 12 ou superior, um banco UTF-8 já criado e uma conta dedicada
com acesso ao banco e permissões `CONNECT`, `CREATE` e `TEMP`. A conta que
cria o esquema será sua proprietária. A conexão padrão é em texto simples,
com `sslmode=disable`. O servidor PostgreSQL decide o método de autenticação.
No pedido de senha, pressione Enter se o servidor dispensar senha.

Para usar TLS, passe `--sslmode verify-full`. Com CA privada, guarde o
certificado dentro de `[dados] dir` e use `--certificado-ca nome-do-arquivo.pem`.
Essa opção também ativa a verificação TLS quando usada sozinha. O modo
escolhido é gravado no `radar.conf` para a API, o cron e os backups.

O migrador e o backup SQL usam o Psycopg 3 disponível no Python do Radar.

## Simular e ativar

Na raiz onde o `api.pse` está instalado, execute como root:

```sh
runuser -u www-data -- ./api.pse ferramenta migrar_postgres --simular
```

A simulação solicita servidor, banco, usuário e senha oculta e reverte todo o
esquema ao final. O padrão é porta 5432 e esquema `radar_brasil`. Se necessário,
informe `--porta`, `--esquema` ou `--origem`. A origem escolhida precisa
estar dentro de `[dados] dir`.

Para a cópia definitiva, execute:

```sh
runuser -u www-data -- ./api.pse ferramenta migrar_postgres --ativar
```

Digite `ATIVAR` quando solicitado. Depois de verificar a conexão, o migrador
pausa as operações da API e do cron, aguarda as que já estavam em andamento
e reserva a escrita no SQLite até mudar a configuração. O Radar volta a
aceitar operações assim que a pausa é liberada, inclusive se a migração
falhar. A ferramenta usa o backup consistente do SQLite, incluindo
transações confirmadas no WAL, e aplica as migrações pendentes
na cópia privada temporária. Ela valida as contagens por tabela e a integridade
do novo esquema, preserva IDs e sequências e só muda `radar.conf` após conferir
a conexão como a conta do serviço. Reserve espaço para a cópia temporária
em `[dados] dir`.

A ativação define `[dados] motor = postgres` e grava a conexão em `[postgres]`.
A opção `postgres.pgpass` aponta para o arquivo de senha de permissão 0600
dentro de `[dados] dir`. Nas outras modalidades a senha é usada em memória.
O modo `--recriar-destino` com `--ativar` substitui o esquema dedicado do
Radar na mesma transação da cópia. A ferramenta recusa tabelas alheias e
dependências externas. Se a cópia falhar, o esquema anterior é recuperado
pelo rollback. Se apenas a ativação falhar, a cópia fica no PostgreSQL.

## Depois da ativação

Confira a rota `/health/ready` da API e o banco ativo via CLI:

```sh
runuser -u www-data -- ./api.pse ferramenta espelho_dados --backup pos-migracao
```

O resultado indica `motor: postgres` e aponta para um arquivo `.sql.gz` em
`dados/backups/espelho-dados/`. O Radar consulta o catálogo do banco ativo e gera
o SQL com a definição das tabelas, todos os registros, sequências, índices,
restrições, views, rotinas e gatilhos do esquema. A leitura usa um snapshot
consistente. A fila JSON, os brutos, as chaves e os logs ficam no diretório
de dados do aplicativo. Nenhum componente usa o SQLite como fallback quando
`[dados] motor = postgres`. O arquivo de origem fica como arquivo histórico,
sem participação nas operações do Radar. Após a cópia, qualquer gravação nova
é feita no PostgreSQL. Voltar simplesmente ao arquivo histórico perderia essas
gravações.

Se existe um cron externo que abre o arquivo SQLite diretamente, desative-o
antes da janela. O sincronizador privado atualizado usa
`radar-dados-sync.py --api CAMINHO/api.pse` para seguir o banco ativo.

## Restaurar o backup SQL

Use a conta que vai ser dona das tabelas no destino. Para validar uma cópia,
restaure primeiro em outro banco PostgreSQL UTF-8.

```bash
set -o pipefail
gzip -dc dados/backups/espelho-dados/pos-migracao.sql.gz |
    psql -X -v ON_ERROR_STOP=1 -d banco_de_teste
```

O SQL começa uma transação e executa `DROP TABLE IF EXISTS` nas tabelas do
arquivo antes de recriá-las. Dependências fora desse conjunto, como uma view
externa que use uma delas, fazem a restauração parar e reverter a transação.
Para restaurar sobre uma instalação ativa, pause as operações do Radar
durante a troca. A conta de destino deve ter as permissões de conexão e
gravação adequadas. Contas, senhas e permissões do servidor PostgreSQL são
configuradas no destino.

Use uma versão do PostgreSQL que suporte as definições do esquema de origem.
O arquivo SQL pode ser inspecionado e adaptado se o destino usar outro
dialeto. Backups antigos `.pgdump` continuam restauráveis com `pg_restore`.

O esquema e as dependências revistas estão descritos em
[Normalização relacional](NORMALIZACAO_RELACIONAL.md).
