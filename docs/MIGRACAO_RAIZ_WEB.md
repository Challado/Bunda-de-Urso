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
Os envios aguardam processamento em `dados.dir/fila-cadastros`; essa fila pode
ficar dentro da raiz do site, protegida pelo mesmo bloqueio HTTP dos dados.
O editor consolida seções repetidas e preserva comentários e opções existentes.
Não há `usuario` ou `grupo` no arquivo: a execução usa a identidade do processo.

O nginx mantém o handler FastCGI genérico `.pse` do server, sem exceções por
nome de script. O bloqueio geral do prefixo usa `location` sem `^~`, permitindo
que esse handler execute `api.pse` e novos scripts `.pse`. Os demais arquivos
são negados, exceto os estáticos de `resources/`, onde não se executam scripts,
não se seguem links simbólicos e não se listam diretórios. Não existem
aliases dos endereços antigos: as páginas são acessadas em `resources/` e os
endereços antigos retornam 404. A entrada é `resources/index.html`, sem nenhum
redirecionamento da raiz. O descritor do projeto aponta diretamente a essa página. O relatório
é consultado em `api.pse?rota=/api/v1/atualizacoes/status`, que lê o JSON dentro
de `dados.dir`, sem abrir SQLite.
A configuração do nginx pertence ao operador. O instalador não edita seus
arquivos nem instala, inicia, reinicia ou recarrega o nginx. Apenas confere a
sintaxe existente e consulta as URLs por HTTP. Se arquivos privados estiverem
expostos, recusa a atualização e informa o erro, sem tentar mudar as regras.
Recuperações de backups também preservam o nginx, inclusive quando um backup
antigo continha arquivos desse serviço.

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
confere por HTTP a proteção da configuração e das pastas privadas,
pausa as entradas, aguarda os coletores e faz backup SQLite consistente.

A atualização não provoca recarga do nginx. As sondas consultam arquivos reais
com URLs únicas e cabeçalhos sem cache. Só continua quando os privados retornam
403/404. As observações e o relatório final registram o resultado das verificações.

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
subpasta de logs configurada). A rota `api.pse?rota=/api/v1/atualizacoes/status` publica o consolidado. Backups anteriores permanecem nas origens para recuperação.
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
