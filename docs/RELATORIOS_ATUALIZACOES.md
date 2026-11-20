# Relatórios das atualizações

O instalador imprime os caminhos do status consolidado e do log de
bootstrap. O consolidado fica em `atualizacoes/status.json` dentro de
`[dados] dir`. Os relatórios ficam no diretório operacional configurado,
que é preservado durante a atualização dos fontes.

A tabela usa `<dados.dir>` e `<logs.dir>` para os caminhos resolvidos a
partir do `radar.conf`. Por padrão, o diretório de logs é `<dados.dir>/logs`.

| Arquivo | Conteudo |
|---|---|
| `<dados.dir>/atualizacoes/status.json` | Estado consolidado da instalação, do bootstrap, das coletas por recurso, da agenda e da fila. |
| `<dados.dir>/atualizacoes/instalacao-<id>.json` | Etapas, checagens, versões, destinos, backup, observações e recuperação. |
| `<dados.dir>/atualizacoes/bootstrap-<id>.json` | Dependências, download, verificadores, saída completa do instalador, etapa da falha e código de saída. |
| `<dados.dir>/atualizacoes/coleta-<execucao_id>.json` | Fonte, recurso, origem, hash, bytes, contagens, rejeições e exceções. |
| `<dados.dir>/atualizacoes/sync-<id>.json` | Coleta manual, incluindo tentativas HTTP que falharam. |
| `<dados.dir>/atualizacoes/tick-<id>.json` | Coletas ou erros da rodada, decisões de agendamento e falhas de pós-processamento. |
| `<dados.dir>/atualizacoes/fila-<id>.json` | Protocolo, tentativa e causa de falhas ou rejeições. |
| `<logs.dir>/atualizacoes.log` | Eventos em JSON por linha, com tentativas HTTP, saídas de comandos e exceções. |
| `<logs.dir>/bootstrap.log` | Transcrição do instalador com horário, etapa e ID em cada linha. |

Os logs entram no logrotate existente: semanal, oito rotacoes, compressao.
Os JSONs individuais permanecem no diretorio de dados; nao sao expurgados
automaticamente. Passadas ociosas ficam no estado atual e no log, sem gerar
um arquivo historico por minuto.

## Como analisar

No servidor3, com os caminhos padrão do layout atual:

```sh
cd /var/www/html/openclaw/radar
cat dados/atualizacoes/status.json
tail -n 100 dados/logs/bootstrap.log
tail -n 100 dados/logs/atualizacoes.log
```

Pelo navegador, abra o diagnóstico com a sessão de moderador ou
administrador. A mesma credencial permite consultar
`api.pse?rota=/api/v1/atualizacoes/status`. A rota retorna HTTP 401 sem
credencial e 503 se o relatório ainda estiver indisponível.
[Painel de status e diagnóstico](STATUS.md)

O consolidado tem `operacoes`, `fontes` e `resumo`. A chave de `fontes` e o ID do
recurso, pois uma fonte pode ter publicacoes independentes. Cada item identifica
a fonte, o recurso e a execucao. `arquivo_relatorio` aponta para o JSON individual;
`bootstrap_id` relaciona a instalacao ao `.sh` que a iniciou.

O instalador executa `api.pse tick --dry-run` ao terminar. Esta passada nao
consulta a internet: inclui a ultima execucao de todos os recursos cadastrados,
mesmo anterior a criacao do diario, usando LEFT JOIN. `resumo.falhas_atuais`
identifica fonte, recurso e causa; `recursos_nunca_coletados` distingue ausencia
de coleta de sucesso. A agenda atualiza esse panorama em cada passada e preserva
tracebacks novos quando a execucao ja tem detalhamento completo.
Se o processo terminou depois de confirmar o resultado no banco e antes de
finalizar o diario, o resultado terminal do banco corrige o consolidado e o
JSON individual, preservando o traceback e registrando `estado_anterior_diario`.

`codigo_esperado` identifica retornos normais de sondagem: systemctl pode devolver
3 para unidade inativa e 4 para inexistente. Essas respostas continuam no log,
mas nao entram em `erros` se houver uma alternativa ativa. Se nenhuma unidade
do servico estiver ativa, a checagem agregada continua reprovada.

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

A primeira versao do diario incluia somente fontes executadas depois da
instalacao. A revisao de 22/10 corrige isso: o ultimo estado historico de cada
recurso tambem aparece no consolidado, com `origem_diagnostico: historico_do_banco`.
O banco preserva mensagens antigas limitadas a 500 caracteres; nao e possivel
reconstruir tracebacks antigos inexistentes. Fontes sem dataset estruturado
mantem `status_integracao: pendente`, sem gerar radares a partir de noticias.

Depois de falha, a espera exponencial usa base de ate uma hora e multiplicador
de ate oito: entre cinco minutos e oito horas, conforme a fonte e as tentativas.
A periodicidade semanal/anual continua igual depois de sucesso. Isso impede
que uma falha de publicacao anual adie a proxima tentativa por anos.

O bootstrap exige Python 3 basico para abrir o diario antes de preparar o Python
3.13 do aplicativo. Sem Python 3, recusa antes de alterar o servidor. Se a
configuracao/caminhos nao podem ser lidos com seguranca, publica um diario
emergencial temporario e imprime o caminho. Falhas de gravacao sao avisadas no
stderr; nao desfazem uma coleta ja confirmada no banco.

O diário omite o ambiente completo, os arquivos de chaves, os pedidos de
cadastro e a saída de `configuracao mostrar`. Credenciais reconhecíveis em
mensagens e URLs são ocultadas. Logs e JSONs são arquivos privados. Quando
`[dados] dir` está sob a raiz web, a proteção HTTP da instalação cobre esses
arquivos. A simulação e a verificação do instalador dispensam o diário de
instalação.
