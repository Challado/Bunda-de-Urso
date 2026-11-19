# Migrar o Radar Brasil de SQLite para PostgreSQL

Use o migrador pelo terminal do servidor que tem o arquivo SQLite e consegue
conectar ao PostgreSQL. Ele usa o arquivo de banco de `radar.conf` como origem
e prepara as tabelas, índices, restrições e dados em um esquema PostgreSQL novo.

Tenha um banco PostgreSQL 12 ou superior já criado, com UTF-8, e um usuário
com permissão de conexão, criação de esquema e tabelas temporárias nesse
banco. A conexão verifica o certificado TLS e o nome do servidor. Use o nome
presente no certificado. Para uma CA privada, guarde o certificado da CA em
`[dados] dir` e informe `--certificado-ca nome-do-arquivo.pem`.

No diretório que contém o `api.pse` instalado, crie um ambiente Python para
o driver. O exemplo usa o diretório de dados padrão `dados`. Se a instalação
usa outro caminho, use o diretório indicado pelo `radar.conf`.

```sh
python3 -m venv dados/venv-migracao
dados/venv-migracao/bin/python -m pip install 'psycopg[binary]>=3.2,<4'
dados/venv-migracao/bin/python api.pse ferramenta migrar_postgres
```

O comando pede servidor, banco, usuário e senha. A senha fica oculta durante
a digitação e não é gravada no disco ou passada como argumento. A porta padrão é
5432 e o esquema padrão é `radar_brasil`. Use `--porta` ou `--esquema` para
escolher outros valores. Use `--origem` para selecionar outro SQLite existente
dentro de `[dados] dir`.

- `--simular` executa a importação e as validações no PostgreSQL e reverte a
  transação. As duas modalidades precisam das mesmas permissões.
- A ferramenta lê uma cópia consistente, incluindo as escritas já confirmadas
  no WAL. Migrações de esquema pendentes são executadas na cópia temporária.
  Reserve espaço no diretório de dados para essa cópia e seus arquivos auxiliares.
- A importação é transacional e recusa um esquema existente. Compara tabelas,
  colunas e contagens, conserva IDs e histórico dos sequenciadores e mantém
  PKs, FKs, restrições e verificações relacionais ativas durante a cópia.
- O SQLite permite armazenar mais casas decimais do que as declaradas na DDL.
  A DDL PostgreSQL usa `NUMERIC` sem escala fixa nesses campos para preservar
  coordenadas, distâncias e outras medidas existentes. Datas e instantes são
  carregados nos tipos nativos. Instantes sem fuso são interpretados como UTC.
- Dados adicionados ao SQLite após a cópia ficam para uma nova execução. Para
  uma cópia final, pause os escritores antes de iniciar a transferência.

A API web, a fila, os coletores e o instalador ainda executam sobre SQLite.
A ferramenta prepara os dados no PostgreSQL para conferência e para a etapa
posterior de adaptação do runtime. O banco contém referências a arquivos
locais, como `ARTEFATO_COLETA.caminho_cache`. Fila em disco, cache bruto,
arquivos de configuração, chaves e logs ficam no servidor do aplicativo.
Para mover o aplicativo inteiro, transfira também os arquivos necessários
e ajuste os caminhos como parte da implantação.

A revisão das dependências do modelo está no documento
[Normalização relacional](NORMALIZACAO_RELACIONAL.md).
