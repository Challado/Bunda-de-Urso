# Proposta: updater.psp executado como www-data

Estado: a preparação da raiz web já foi implementada; o acionamento HTTP de
`updater.psp` continua proposto e ainda não foi implementado.
Esta revisão substitui a proposta anterior de serviço root e agendamento.

## Objetivo e fluxo principal

O próprio aplicativo recebe um pedido autenticado pela web e inicia sua
atualização como `www-data`, imediatamente. O acionamento da atualização não
usa serviço root, sudo ou cron.

1. O usuário pede a atualização pelo chat.
2. O assistente envia o código à main e aguarda os testes do commit exato.
3. O assistente faz um GET autenticado à API indicando essa versão aprovada.
4. A API, atendida como www-data, grava o protocolo e inicia um processo filho
   independente, também como www-data, para executar `updater.psp`.
5. A API devolve HTTP 202 imediatamente, com protocolo e URL de acompanhamento.
6. O processo baixa os fontes/pacote da versão, valida, faz backup, aplica,
   confere e publica o resultado. O assistente acompanha e confirma pelo
   servidor a versão instalada e a prontidão antes de informar conclusão.

O worker é iniciado pela própria requisição. Continua após o encerramento do
CGI, com entrada/saídas desacopladas da conexão HTTP e logs próprios. A fila e
os checkpoints persistem em disco; a fila não precisa de um consumidor agendado.

## Entrega dos fontes

A opção principal é baixar o arquivo de fontes do repositório público
`Challado/Bunda-de-Urso` fixado no commit aprovado. Assim a atualização não
muda de versão se outro commit chegar à main durante o download e não depende
exclusivamente de um novo mecanismo de Releases.

Também será possível enviar um pacote ao endpoint autenticado ou usar um
pacote já colocado na entrada local. Arquivo completo e validado é necessário
antes de tocar na instalação. URLs aceitas ficam restritas ao repositório/canal
permitido; o pedido não transporta comandos de shell ou destinos de instalação.
Extração rejeita caminhos absolutos, travessia de diretórios e links indevidos.
Pacotes com manifesto têm arquivos e hashes conferidos. O arquivo de fontes
oficial é obtido por HTTPS com identidade do commit e integridade de transporte
verificadas; um hash local isolado não é tratado como assinatura do publicador.

## Interface web e credencial

Exemplo proposto para solicitar a atualização:

```text
https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/gestao/atualizacoes/solicitar&versao=COMMIT
```

O token vai no cabeçalho `X-Api-Token`, com permissão específica de atualização,
e a chave de idempotência também vai em cabeçalho. Repetir um pedido retorna
seu protocolo; não abre outra instalação. Cookie de sessão ou visita comum a
um link não autoriza a atualização. Solicitações e andamento usam no-store.

Uma vez, a credencial será cadastrada no servidor e como segredo no ambiente
do projeto usado pelo chat, sem expô-la na URL, nos commits ou na conversa.
Esse acionamento ainda não existe; o acesso de leitura disponível hoje não
substitui sua autorização.

## Arquivos, permissões e limites do usuário www-data

`updater.psp` será um programa Python executável, com esse nome exato. Sua
lógica continua em uma operação local da API. Configuração e caminhos passam
por `radar.conf` e `core.caminhos`.

```text
<raiz da instalação>/
  radar.conf                  # arquivo regular, não servido por HTTP
  api.pse
  updater.psp                 # próxima etapa
  core/, coletor/, web/, sql/, config/, deploy/, tools/
  dados/
    radar.sqlite3
    raw/, fila-cadastros/, segredos/
    atualizacoes/
  logs/
```

O `radar.conf` fica junto aos scripts. `home = .`, `web.raiz = .`,
`dados.dir = dados`, `dados.banco = radar.sqlite3` e `logs.dir = logs` (dentro de `dados.dir`).
Todo caminho relativo se resolve contra a pasta do arquivo, independentemente
do diretório atual do processo. A instalação não substitui essa raiz inteira.
A preparação root está em [MIGRACAO_RAIZ_WEB.md](MIGRACAO_RAIZ_WEB.md):
`instalar-servidor3.sh --migrar-raiz-web --aplicar` lê o webroot existente,
protege pastas privadas no nginx antes de copiar, preserva dados e prepara
posse/permissões para www-data. Não há caminho de implantação fixo no código.

A preparação inicial também assegura que rotinas automatizadas do radar
executem esses fontes mutáveis como www-data, antes de carregar o código do
aplicativo. Os crons de outros projetos e rotinas específicas são preservados.
Isso evita que um agendamento root existente transforme a atualização web em
execução privilegiada indireta.

O updater pode trocar fontes, páginas e assets, atualizar o banco por migrações
compatíveis, acrescentar opções de configuração ausentes e executar os
reprocessamentos do aplicativo. Não fará apt-get, chown de arquivos protegidos,
edição de configuração do nginx/systemd ou alteração do crontab pela web.
Se uma versão exigir privilégio de sistema, a conferência inicial interrompe
antes de aplicar e informa precisamente a preparação necessária ao operador.
Dependências de sistema já preparadas continuam sendo usadas normalmente.

## Aplicação, falhas e recuperação

1. Confere identidade da versão, conteúdo do pacote, requisitos, espaço,
   permissões de escrita e compatibilidade das migrações.
2. Obtém uma trava exclusiva e coordena os coletores/processadores do radar.
3. Faz backup consistente do banco e dos arquivos que serão alterados.
4. Prepara os arquivos em área temporária e aplica trocas controladas, mantendo
   o ponto de entrada e a recuperação do updater disponíveis.
5. Executa migrações/reprocessamentos suportados, sem inventar dados ou apagar
   decisões humanas, e verifica a API/HTTP, versão e arquivos publicados.
6. Registra a versão aplicada e o resultado no protocolo, JSON e log.

Preserva IDs, configuração existente, fila de envios, dados brutos e histórico.
Versão já instalada apenas confere e informa; pedidos simultâneos não duplicam
a atualização. Download incompleto ou validação reprovada mantém a versão atual.

Falha na aplicação aciona recuperação dos arquivos quando o banco continuar
compatível. Mudança incompatível com recuperação automática fica pendente antes
da aplicação. O banco não é restaurado por cima de dados recentes.
Interrupções deixam checkpoints para diagnóstico e retomada/recuperação pelo
próximo acionamento; não se presume que exista um daemon para reiniciar o job.
A consulta ao updater deve continuar disponível se a nova API do aplicativo
não subir, para permitir recuperar a instalação pelo mesmo mecanismo web.

## Preparação inicial e observabilidade

O `instalar-servidor3.sh` atualizado prepara uma vez os arquivos, permissões,
entradas de recuperação e credencial necessários. Não instala serviço root nem
cron de atualização. Depois, o usuário solicita pelo chat e o assistente aciona
a API; também haverá comandos locais para verificar, aplicar pacote e recuperar.

A página de status, o JSON operacional e os logs registrarão usuário efetivo,
versão anterior/disponível/aplicada, protocolo, etapas e tempos, contadores,
backup, migrações, reprocessamentos, erros e recuperação. Instalação do código
e falhas de fontes externas continuam sendo resultados separados.

## Implementação e aceite

Será criado um caminho de atualização da aplicação adequado a www-data,
reaproveitando verificações, backup e rotinas internas existentes. O instalador
atual exige root e usa git rev-parse; essas suposições precisam ser separadas
das operações de atualização por pacote. As operações de sistema continuam na
preparação inicial feita pelo operador.

Os testes devem rodar efetivamente com permissões de www-data, cobrindo pedido
autenticado, processo após resposta HTTP, idempotência, permissão negada,
pacote incompleto/inválido, concorrência, interrupção, migração, recuperação e
preservação dos dados. O aceite exige pedir pelo chat e verificar atualização
concluída pelo usuário www-data, sem abrir terminal no servidor a cada versão.
