# Migrar o Radar Brasil de SQLite para PostgreSQL

O migrador roda no servidor do Radar. Ele lê a origem escolhida em `radar.conf`,
cria um esquema novo no PostgreSQL e pode ativar esse esquema para toda a instalação.

## Preparar o destino

Use PostgreSQL 12 ou superior, um banco UTF-8 já criado e uma conta dedicada
com acesso ao banco e permissões `CONNECT`, `CREATE` e `TEMP`. A conta que
cria o esquema será sua proprietária. A conexão usa TLS com verificação de
certificado e de nome do servidor. Se o certificado for de uma CA privada,
guarde o certificado da CA dentro de `[dados] dir` e passe
`--certificado-ca nome-do-arquivo.pem`. Use o nome presente no certificado.

O migrador usa o Psycopg 3 disponível no Python do Radar e o `pg_dump` no
`PATH` da conta do serviço. Use um `pg_dump` de versão igual ou superior à
do PostgreSQL remoto.

## Simular e ativar

Na raiz onde o `api.pse` está instalado, execute como root:

```sh
runuser -u www-data -- ./api.pse ferramenta migrar_postgres --simular
```

A simulação solicita servidor, banco, usuário e senha oculta e reverte todo o
esquema ao final. O padrão é porta 5432 e esquema `radar_brasil`. Se necessário,
informe `--porta`, `--esquema` ou `--origem`. A origem escolhida precisa
estar dentro de `[dados] dir`.

Para a cópia definitiva, pause o cron do Radar e demais operações que escrevam
no banco durante a janela de manutenção. Suspenda também o processamento de
cadastros e o acesso de escrita da API. Confira que as operações em andamento
terminaram. Execute:

```sh
runuser -u www-data -- ./api.pse ferramenta migrar_postgres --ativar
```

Digite `ATIVAR` quando solicitado. A ferramenta usa o backup consistente do
SQLite, incluindo transações confirmadas no WAL, e aplica as migrações pendentes
na cópia privada temporária. Ela valida as contagens por tabela e a integridade
do novo esquema, preserva IDs e sequências e só muda `radar.conf` após conferir
a conexão como a conta do serviço. Reserve espaço para a cópia temporária
em `[dados] dir`.

A ativação grava a senha num arquivo `.pgpass` de permissão 0600 dentro de
`[dados] dir`. Nas outras modalidades a senha é usada somente em memória.
O processo recusa um esquema já existente. Se a cópia terminar e a ativação
falhar, o esquema fica disponível para inspeção e a saída registra a falha.

## Depois da ativação

Confira a rota `/health/ready` da API e o banco ativo via CLI:

```sh
runuser -u www-data -- ./api.pse ferramenta espelho_dados --backup pos-migracao
```

O resultado indica `motor: postgres` e aponta para o backup nativo `.pgdump`,
em `dados/backups/espelho-dados/`. Reative os crons e o acesso à API após a
checagem. A fila JSON, os brutos, as chaves e os logs continuam no diretório de
dados do aplicativo. Nenhum componente usa o SQLite como fallback quando
`[dados] motor = postgres`. O arquivo de origem fica como arquivo histórico,
sem participação nas operações do Radar. Após a cópia, qualquer gravação nova
é feita no PostgreSQL. Voltar simplesmente ao arquivo histórico perderia essas
gravações.

Se existe um cron externo que abre o arquivo SQLite diretamente, desative-o
antes da janela. O sincronizador privado atualizado usa
`radar-dados-sync.py --api CAMINHO/api.pse` para seguir o banco ativo.

O esquema e as dependências revistas estão descritos em
[Normalização relacional](NORMALIZACAO_RELACIONAL.md).
