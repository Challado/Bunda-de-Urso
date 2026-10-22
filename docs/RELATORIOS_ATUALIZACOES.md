# Relatorios das atualizacoes

Ao aplicar o instalador como root, o aplicativo disponibiliza
`<instalacao.home>/status-atualizacoes.json`. E um link para
`<dados.dir>/atualizacoes/status.json`: o estado e os relatorios individuais
permanecem fora da arvore substituida, inclusive quando ha recuperacao de backup.
Os caminhos seguem o `radar.conf`. Os relatorios nao ficam na pasta web.

No servidor3:

| Arquivo | Conteudo |
|---|---|
| `/openclaw/bin/radar/status-atualizacoes.json` | Estado consolidado de instalacao, bootstrap, coletas por recurso, agenda e processamento da fila. |
| `/var/lib/radar-brasil/atualizacoes/instalacao-<id>.json` | Etapas, comandos, stdout/stderr, checagens, versoes, destinos, backup, observacoes e recuperacao. |
| `/var/lib/radar-brasil/atualizacoes/bootstrap-<id>.json` | Dependencias, download, verificadores, saida completa do `.sh`, etapa da falha e codigo de saida original. |
| `/var/lib/radar-brasil/atualizacoes/coleta-<execucao_id>.json` | Fonte/recurso, origem, hash, bytes, contadores, rejeicoes individuais e excecoes com traceback. |
| `/var/lib/radar-brasil/atualizacoes/sync-<id>.json` | Coleta manual, incluindo tentativas HTTP que falharam. |
| `/var/lib/radar-brasil/atualizacoes/tick-<id>.json` | Passada com coletas ou erros, decisoes de todas as fontes e falhas de pos-processamento. |
| `/var/lib/radar-brasil/atualizacoes/fila-<id>.json` | Processamento com falhas/rejeicoes: protocolo, tentativa e causa. |
| `/var/log/openclaw/radar/atualizacoes.log` | Eventos em JSON por linha: tentativas HTTP, saidas de comandos e tracebacks completos. |
| `/var/log/openclaw/radar/bootstrap.log` | Transcricao do instalador com horario, etapa e ID em cada linha. |

Os logs entram no logrotate existente: semanal, oito rotacoes, compressao.
Os JSONs individuais permanecem no diretorio de dados; nao sao expurgados
automaticamente. Passadas ociosas ficam no estado atual e no log, sem gerar
um arquivo historico por minuto.

## Como analisar

```sh
cat /openclaw/bin/radar/status-atualizacoes.json
tail -n 100 /var/log/openclaw/radar/bootstrap.log
tail -n 100 /var/log/openclaw/radar/atualizacoes.log
```

O consolidado tem `operacoes`, `fontes` e `resumo`. A chave de `fontes` e o ID do
recurso, pois uma fonte pode ter publicacoes independentes. Cada item identifica
a fonte, o recurso e a execucao. `arquivo_relatorio` aponta para o JSON individual;
`bootstrap_id` relaciona a instalacao ao `.sh` que a iniciou.

`erros` preserva falhas observadas mesmo se uma etapa posterior conseguiu
recuperar a operacao. `estado: ok` indica a conclusao, sem apagar erros de
tentativas anteriores. As checagens iniciais podem apontar justamente os
arquivos/permissoes que o instalador corrigiu: confira a checagem final.

Cada coleta preserva `erros_validacao` e `contadores`, com descricao integral e
traceback, mesmo quando o banco armazena uma descricao abreviada. O tick distingue
executado, erro, inativo, nao vencido e sem origem. Erros de pos-coleta aparecem
mesmo se a importacao terminou bem. A fila registra protocolos e causas sem
copiar o pedido original do usuario para o diario.

Lock entre processos e substituicao atomica protegem o JSON. Status corrompido e
preservado em `status-corrompido-<id>.json` e recriado com observacao. Processo
sem conclusao cujo PID terminou passa a `interrompido` na proxima escrita: queda
de energia/SIGKILL nao executam rotina final. SIGTERM/SIGINT no bootstrap encerram
seu grupo de processos e registram 143/130.

## Limites operacionais

O detalhamento comeca depois de instalar esta revisao. Nao recria mensagens de
erros anteriores que nao foram guardadas. O banco preserva seu historico anterior
de execucoes, consultavel pelas operacoes existentes da API.

O bootstrap exige Python 3 basico para abrir o diario antes de preparar o Python
3.13 do aplicativo. Sem Python 3, recusa antes de alterar o servidor. Se a
configuracao/caminhos nao podem ser lidos com seguranca, publica um diario
emergencial temporario e imprime o caminho. Falhas de gravacao sao avisadas no
stderr; nao desfazem uma coleta ja confirmada no banco.

Nao registra ambiente inteiro, arquivos de chaves, pedidos de cadastro nem a
saida de `configuracao mostrar`. Credenciais reconheciveis em mensagens/URLs sao
ocultadas. Logs e JSONs sao locais, 0660, fora do webroot. Simular ou verificar
com o instalador nao cria o diario de instalacao.
