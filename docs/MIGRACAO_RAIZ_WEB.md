# Configuração e instalação do Radar Brasil

A API seleciona **um único arquivo**: `RADAR_CONF`, quando informada, ou a
constante `CONF_PADRAO` da entrada. Na instalação, o padrão é o `radar.conf`
ao lado de `api.pse`. Não procura automaticamente outro arquivo e não aceita
sobreposição de valores por `RADAR_DB`, `RADAR_DATA_DIR`, `RADAR_LOG_DIR`,
`OLLAMA_URL` ou outras variáveis antigas. Credenciais vêm dos arquivos locais.

## Raiz dos dados

```ini
[instalacao]
home = /caminho/da/aplicacao

[dados]
dir = /caminho/da/aplicacao/dados
banco = radar.sqlite3

[web]
raiz = /caminho/da/aplicacao
url = /prefixo/publico/
origem = https://exemplo.invalid

[logs]
dir = logs

[api]
token_arquivo = api_token

[assistente]
habilitado = 0
chave_arquivo = assistente_chave
```

Os caminhos de implantação acima são exemplos, nunca valores fixados no código.
`dados.dir` relativo resolve contra a pasta do arquivo de configuração. Banco,
logs, tokens, chaves, cache, fila, malha, clone local e temporários resolvem
**dentro de `dados.dir`**. Caminhos que escapem dessa raiz, inclusive por links
simbólicos, são rejeitados. A API de configuração aceita para `banco` somente
um nome de arquivo e não move a base quando um caminho é editado.

Código e o próprio `radar.conf` ficam na raiz da aplicação. As páginas, CSS,
JavaScript, imagens e JSON públicos ficam em `resources/`. Auxiliares
da configuração (lock, backup e auditoria) ficam em `dados.dir/configuracao`.
O editor consolida seções repetidas e preserva comentários e opções existentes.
Não há `usuario` ou `grupo` no arquivo: a execução usa a identidade do processo.

O nginx nega por padrão qualquer caminho dentro do prefixo do Radar. Libera
somente `api.pse` como entrada FastCGI e `resources/` para arquivos estáticos,
sem executar scripts, seguir links simbólicos ou listar diretórios. Os caminhos
antigos das páginas redirecionam para `resources/`, preservando parâmetros como
o ID do radar. O endereço `status-atualizacoes.json` redireciona para a consulta
do relatório pela API, que lê o JSON dentro de `dados.dir`, sem abrir SQLite.
As regras são geradas a partir do prefixo/raiz configurados e preservam o
handler FastCGI existente, sem fixar caminho de socket.

Quando os servers já incluem `/etc/nginx/snippets/radar-brasil.conf`, o
instalador preserva seus blocos literalmente e verifica a proteção por HTTP.
O nginx não é recarregado quando o instalador não alterou sua configuração.
Isso permite manter o Radar em um snippet separado dos certificados, proxies
e demais projetos do servidor.

## Atualizar o servidor

No checkout privado, como root, sem sudo:

```sh
git pull --ff-only
bash instalar-servidor3.sh --aplicar
```

Para a primeira migração da instalação antiga, acrescente `--migrar-raiz-web`.
`--conf ARQUIVO` escolhe a configuração de origem explicitamente. `--verificar`
confere a instalação. A preparação do sistema operacional continua local; não
existe serviço root ou cron de atualização remota.

O instalador baixa o código público e executa a instalação pela API local. Ele
protege configuração e pastas privadas no nginx, testa os bloqueios por HTTP,
pausa as entradas, aguarda os coletores e faz backup SQLite consistente.

A recarga do nginx é assíncrona. Antes de migrar, o instalador espera até
15 segundos pela ativação das regras e consulta sondas reais com URLs únicas
e cabeçalhos sem cache. Só continua quando todas retornam 403/404; uma resposta
200 persistente reprova a instalação. A identificação do server também reconhece
links intermediários na raiz web. As observações mostram os arquivos do nginx
alterados e o diretório de backup usado na preparação.

Se o banco **já estiver em `dados.dir`**, ele é usado nesse local: não é trocado
por uma base vazia ou uma cópia antiga. IDs, decisões e fila são preservados.
Logs, tokens, chaves e caches legados são migrados para a raiz de dados, e os
caminhos dos artefatos são corrigidos. A leitura de destinos antigos só existe
no contexto da migração local; nunca é liberada por variável de ambiente ou HTTP.

Os agendamentos de coleta e processamento da fila são transferidos do crontab
do root para o crontab do **www-data**. Jobs de outros sistemas são preservados
nos dois crontabs. O cron executa a API como seu próprio usuário, sem selecionar
identidade por configuração. O instalador prepara permissões para o usuário CGI,
atualiza logrotate e testa a API com essa identidade. Logrotate usa o proprietário
e grupo reais da pasta de logs, sem campos de identidade no `radar.conf`.

A transferência também ocorre ao atualizar o layout antigo, sem exigir
`--migrar-raiz-web`. A checagem final e `--verificar` conferem separadamente
`cron.root` e `cron.www-data`: não pode restar coletor/fila no root e devem
existir exatamente as duas entradas atualizadas no usuário web. Uma falha de
leitura ou escrita reprova a instalação; os dois crontabs têm backup.
`--sem-cron` desativa explicitamente essa gestão. Os sincronizadores privados
do servidor3 permanecem separados, sem alterações.

Relatórios e logs ficam em `dados.dir/atualizacoes` e `dados.dir/logs` (ou na
subpasta de logs configurada). `status-atualizacoes.json` publica o consolidado
pelo link conhecido. Backups anteriores permanecem nas origens para recuperação.
Falhas anteriores à publicação recuperam arquivos/configuração; depois de
publicar a API, a instalação nova é preservada para não perder envios recebidos.
Consulte o relatório e reaplique após corrigir a causa. Nunca há restauração
automática de um banco antigo sobre dados novos.

O acionamento remoto de `updater.psp` continua descrito em
[PROPOSTA_UPDATER.md](PROPOSTA_UPDATER.md); esta etapa prepara a instalação.

Se o arquivo selecionado não existir, a API recusa a execução (503 no CGI),
sem procurar outra configuração ou criar uma base em outro lugar. A preparação
local com um perfil explícito ainda pode criar o arquivo inicial.

A API local também recusa `--db` e arquivos de importação fora de `dados.dir`.
O bootstrap copia uma planilha fornecida pelo operador para `dados.dir/staging`
antes de chamar a importação; a cópia temporária é removida depois do sucesso.
