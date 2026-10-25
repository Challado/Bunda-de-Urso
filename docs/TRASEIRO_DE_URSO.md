# TRASEIRO DE URSO

O TRASEIRO DE URSO é a rede de intercâmbio do Radar Brasil, integrada à API,
ao painel e ao cron. Usa o [protocolo genérico de Intercâmbio de Instâncias](INTERCAMBIO_INSTANCIAS.md),
que outros programas também podem implementar. Não usa IA e não muda o nginx.

## Ativação e atualização

Atualize pelo `instalar-servidor3.sh` habitual do repositório privado. O instalador
atualiza os fontes, aplica a migração aditiva 0008, completa parâmetros ausentes
e prepara **três tarefas independentes** no usuário da instalação: coleta,
fila de cadastros e `api.pse cron traseiro`, cada uma uma vez por minuto.
As tarefas do Radar são removidas do root, preservando rotinas externas.

A rede vem desativada. Não baixa dados nem contata pares enquanto
`traseiro.habilitado=0`. Edite o `radar.conf` selecionado pela API ou use a aba
Configuração. O código deriva a URL pública de `web.origem` e `web.url`; `api_url`
pode substituir a URL completa da operação de troca. A URL pode pertencer a
outro sistema e não precisa terminar em `.pse`.

```ini
[traseiro]
habilitado = 1
nome = Minha instancia
api_url =
acesso = tokens
tokens_arquivo = traseiro_tokens.json
pares = https://outro.exemplo.org/openclaw/radar/api.pse?rota=%2Fapi%2Fv1%2Fintercambio%2Ftrocar
intervalo_segundos = 300
inatividade_tipo = tentativas
inatividade_numero = 5
parada_programada = 0
parar_em_segundos = 0
retornar_em_segundos = 0
lote = 100
max_bytes = 2097152
max_pendentes = 10000
max_instancias = 100
pares_por_tick = 4
fontes_por_tick = 1
sondagem_segundos = 86400
timeout = 15
```

`intervalo_segundos` é o mínimo que os outros devem respeitar ao consultar
**esta** instância. Ao consultar outro servidor, este programa respeita o mínimo
que **ele** anunciou. Os dois valores são independentes. `pares` é uma lista de
URLs completas separadas por vírgula. A consulta registra automaticamente os
pares e aprende novas identidades do catálogo remoto, dentro dos limites locais.

Inicialize como o usuário que executa a API, por exemplo:

```sh
runuser -u www-data -- ./api.pse traseiro inicializar
runuser -u www-data -- ./api.pse traseiro status
```

A primeira operação preserva o banco existente, gera identidade persistente e
cria o arquivo de tokens sem sobrescrever arquivo existente. O token aparece
uma vez nessa saída: não é incluído nos relatórios de sincronização.

No modo `tokens`, o arquivo JSON dentro de `dados.dir` contém:

```json
{
  "token_rede": "SUBSTITUA_POR_UM_TOKEN_ALEATORIO_COM_24_OU_MAIS_CARACTERES",
  "entrada": [],
  "saida": {}
}
```

Instâncias com o mesmo `token_rede` formam um grupo autorizado e podem descobrir
pares sem cadastrar uma chave por URL. Não copie o banco/UUID para criar outro
servidor. Para tokens específicos, `entrada` lista tokens aceitos e `saida`
mapeia a URL completa de cada destino para seu token; esse mapeamento prevalece
sobre o token comum. O modo `acesso=livre` dispensa token da rede. Nenhum token de
rede concede privilégios administrativos ou aprovação de radar.

O arquivo de tokens, travas, diário e dados ficam dentro de `dados.dir`. Não se
aceitam caminhos que escapem dessa pasta, inclusive por link simbólico. Dados
operacionais não são gravados na pasta `resources`.

## Inatividade e parada

Há **somente a dupla** de parâmetros do critério de inatividade:

- `inatividade_tipo = dias`: o número conta dias desde o último contato bem sucedido.
- `inatividade_tipo = tentativas`: o número conta tentativas consecutivas sem sucesso.
- `inatividade_numero = X`: valor usado exclusivamente pelo tipo selecionado.

Sucesso zera as falhas. Servidor inativo por erro é sondado no intervalo de
`sondagem_segundos`, respeitando também o mínimo que ele anunciou; pode retornar
sem intervenção manual. O administrador também pode reativar, inativar ou
bloquear um par no painel. Bloqueados não recebem sondagens nem podem registrar-se.

Para anunciar uma parada daqui a uma hora e retorno daqui a duas:

```ini
parada_programada = 1
parar_em_segundos = 3600
retornar_em_segundos = 7200
```

Os prazos partem do mesmo instante. Alterar/armar a programação ancora o relógio
uma vez no banco. Cada mensagem informa os segundos restantes, sem renovar a
contagem. A parada já iniciada com retorno zero é indefinida. O retorno positivo
retoma o contato automaticamente. Pausados não acumulam falhas nem são sondados.

Enquanto estiver declarado parado, o servidor **não consulta pares**. Os outros
servidores também recusam consultas dele se ainda anuncia esse estado. Para
voltar de uma parada sem retorno, cancele e zere os dados:

```ini
parada_programada = 0
parar_em_segundos = 0
retornar_em_segundos = 0
```

Isso reabre as consultas recebidas e as saídas, anunciando o cancelamento. Uma
programação com retorno concluído é de execução única: não volta a armar a cada
reinício. Para outra parada, altere/rearme os parâmetros.

## Cadastro separado e validação

A aba **TRASEIRO DE URSO** na gestão mostra instâncias, disponibilidade,
parâmetros anunciados, falhas, cadastros recebidos e fontes ensinadas. Ela tem
paginação e os mesmos controles de acesso da gestão: leitura para contribuidores,
aprovação/rejeição para moderadores e fontes/bloqueios de pares para administradores.

Receber/reenviar não publica radar no mapa. A fila mesh é separada do cadastro
Bundita de Urso. Para aprovar uma posição, informe como conferiu a coordenada;
o servidor exige latitude/longitude válidas, respeita bloqueios geográficos e
normaliza pelo mesmo pipeline de ingestão. O registro passa a
`procedencia=oficial` e `verificacao_status=verificado` nesta instância, em fonte
**TRASEIRO DE URSO - posições validadas**, preservando a origem da rede.
A natureza dessa fonte é cadastro da rede, sem fingir publicação governamental.

Uma revisão nova retorna à fila; não sobrescreve automaticamente a posição
validada. A decisão usa o ID da revisão para impedir aprovação de uma tela antiga.
A retirada recebida também precisa de revisão. Tombstones e desabilitações locais
são preservados: outra revisão remota não ressuscita o radar.

A outbox é alimentada na mesma transação das alterações canônicas (pontos,
coordenadas, faixas, limites e regimes). Exporta somente campos públicos de radar,
sem contatos, credenciais, usuários ou cópia do banco. Documentos de rede têm
UUID, origem e revisões imutáveis. Voltar por outro caminho da malha não cria
outro radar. Um radar já importado conserva sua origem em vez de ser reexportado
como criação local.

## Fontes ensinadas

O administrador pode compartilhar uma receita declarativa JSON ou CSV:

```json
{
  "nome": "Lista publica do orgao",
  "url": "https://orgao.exemplo.org/dados/radares.csv",
  "formato": "csv",
  "campos": {
    "identificador": "codigo",
    "latitude": "lat",
    "longitude": "lon",
    "velocidade_geral": "velocidade"
  },
  "delimitador": ";",
  "intervalo_segundos": 86400
}
```

Para JSON, `caminho_itens` pode indicar chaves simples separadas por ponto até a
lista (por exemplo `dados.radares`). O mapeamento usa nomes de colunas/chaves,
sem expressões executáveis. PDF/HTML e formatos especiais continuam exigindo
conector revisado no código local; a rede não instala programas de outro servidor.

Receitas recebidas e revisões novas ficam **desativadas**. O cron prioriza a troca
de dados entre instâncias. Se a origem sair do ar, o administrador pode ativar
uma receita pela gestão; a alteração vale apenas neste servidor. O cron passa a
baixar a URL com timeout, limite de bytes e validação de destino público. Os
registros entram na mesma fila mesh e continuam exigindo validação local.

A rede não herda ativação de outro servidor, não executa Python/SQL/comandos de
receitas e não transporta credenciais de download.

## Operação e diagnóstico

```sh
./api.pse traseiro --help
./api.pse traseiro sincronizar
./api.pse traseiro cadastros --depois 0
./api.pse traseiro fontes --depois 0
./api.pse traseiro ensinar-fonte chave-estavel receita.json
./api.pse traseiro decidir 1 aprovar --evento 123 --motivo 'Coordenada conferida no estudo publico'
./api.pse traseiro ativar-fonte 1 --evento 124
./api.pse traseiro ativar-fonte 1 --evento 124 --desativar
```

`receita.json` é resolvido dentro de `dados.dir`. A sincronização manual respeita
intervalos anunciados e paradas. Ela não oferece uma forma de furar limites.
O cron tem trava entre processos e é independente da coleta e da fila pública.

O relatório existente de atualizações recebe a operação `traseiro`, com erros
por etapa/par/fonte e contadores. Eventos detalhados ficam no diário da operação;
a saída do cron fica em `logs/traseiro.log`, dentro de `dados.dir`. As decisões
locais têm histórico no banco, com quem, quando, motivo e revisão aprovada.

As tabelas de identidade, pares, capacidades, eventos, fila, receitas, decisões e
outbox usam PK/FK, unicidade e restrições. JSON preserva o documento original do
evento; estados e vínculos ficam em tabelas separadas. A migração é aditiva e não
requer recriar a base ou apagar dados.
