# Instalação com configuração na raiz

A primeira etapa reúne código, páginas, configuração, dados e logs na raiz web
que já está declarada em `[web] raiz` do `radar.conf` existente. O código não
contém o caminho de instalação do servidor. O arquivo de exemplo usa caminhos
relativos; ele não deve substituir a configuração de uma base existente.

No repositório privado atualizado, execute como root, sem sudo:

```sh
bash instalar-servidor3.sh --migrar-raiz-web             # simula
bash instalar-servidor3.sh --migrar-raiz-web --aplicar  # migra
```

Se necessário, acrescente `--conf /caminho/ao/radar.conf` para selecionar a
configuração de origem. Sem override, o shell procura junto ao próprio script,
no diretório atual e, para instalações anteriores, no local legado em `/etc`.
Ele baixa o código público atual e executa a instalação pela API local.

## Resultado

```text
<web.raiz>/
  radar.conf
  api.pse
  *.html, *.css, *.js, projeto.json
  core/, coletor/, web/, sql/, config/, deploy/, tools/
  dados/
    radar.sqlite3
    raw/, staging/, calibracao/, fila-cadastros/
    segredos/api_token, segredos/assistente_chave
    atualizacoes/status.json
  logs/
  status-atualizacoes.json -> dados/atualizacoes/status.json
```

A configuração efetiva torna-se um arquivo regular na raiz, com `home = .`,
`web.raiz = .`, `dados.dir = dados`, `dados.banco = dados/radar.sqlite3` e
`logs.dir = logs`. As opções e comentários existentes são preservados; limites
ausentes recebem os padrões da aplicação. A IA continua opcional. Chaves ficam
em arquivos separados na pasta privada de segredos. O ambiente explícito ainda
tem precedência; o instalador limpa overrides de caminhos ao chamar a API.

O aplicativo e seus dados ficam com o usuário CGI (`www-data` por padrão).
Pastas usam 2770, arquivos 0660 e a entrada executável 0770. O painel continua
salvando a configuração pela API, agora no arquivo local. Os caminhos são
relativos **à pasta do radar.conf**, nunca ao diretório do terminal.

## O que o script faz

- Valida o banco existente, impede sobrescrever duas bases divergentes e mantém
  as origens antigas. Não cria uma base vazia para substituir a produção.
- Instala bloqueios nginx para configuração e auxiliares, dados, logs e fontes
  internos. Valida sintaxe, recarrega e testa por HTTP com arquivos de prova,
  antes de copiar dados privados. Exige `[web] origem` ou `--origem-http`.
- Pausa as entradas gerenciadas, aguarda as travas de coleta e fila, faz backup
  SQLite consistente (incluindo dados em WAL), copia fila/cache/segredos/logs e
  ajusta referências dos artefatos ao novo cache. IDs e decisões são preservados.
- Copia somente fontes/assets gerenciados; nunca troca/apaga a raiz inteira.
- Executa migrações e checagens pela API, como o usuário CGI. O nginx mantém o
  handler CGI existente. Não cria serviço root nem cron de atualização.
- Ajusta cron de coleta/fila para baixar privilégios com `runuser` antes de
  carregar fontes graváveis pelo CGI. Entradas antigas recebem encaminhadores
  de compatibilidade com a mesma queda de privilégios. Outras rotinas são
  preservadas, inclusive sincronizadores específicos do servidor.
- Cria ou atualiza logrotate com a pasta de logs e usuário da configuração.
- Registra JSON da checagem, backup e logs. O shell continua executando o
  reprocessamento das fontes corrigidas depois da instalação.

Backups anteriores ficam na origem; não são duplicados junto à base migrada.
A migração registra o backup em `<dados de origem>/backups/raiz-web/<data>/`.
Há recuperação de arquivos/configuração para falhas anteriores à publicação.
Depois de liberar a API nova, preserva a instalação e a base para não perder
novos envios; uma reprovação fica no relatório e deve ser corrigida por uma
reaplicação. Nunca restaura automaticamente um banco antigo sobre dados novos.

## Próximas execuções

```sh
bash instalar-servidor3.sh --aplicar
bash instalar-servidor3.sh --verificar
```

O shell reconhece o arquivo da raiz a partir da configuração antiga. Também é
possível indicar diretamente `--conf /caminho/da/raiz/radar.conf`. O instalador
antigo não será usado para substituir a árvore contendo a base.

Essa etapa prepara a execução e escrita como www-data. O acionamento remoto
de `updater.psp` ainda depende da implementação descrita em
[PROPOSTA_UPDATER.md](PROPOSTA_UPDATER.md).
