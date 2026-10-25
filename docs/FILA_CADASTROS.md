# Cadastro com recebimento rápido

O formulário salva primeiro um JSON durável pela `api.pse` e recebe um protocolo.
Não espera o SQLite, a busca de proximidade ou o coletor. A tela distingue **envio
recebido** de **radar processado** e só mostra o link do radar depois da conclusão.
Consulta automaticamente por alguns instantes e permite consultar novamente pelo
botão ou pelo link do protocolo. Pode fechar o navegador depois da confirmação.

O navegador guarda somente protocolo e horário, sem coordenadas ou contato.
Se o armazenamento estiver bloqueado, o link do protocolo continua funcionando.
Sem confirmação de gravação, os campos permanecem preenchidos para tentar novamente.

## Arquivos e garantias

Os arquivos ficam em `<dados.dir>/fila-cadastros/`. O caminho vem de `radar.conf`
e não pode escapar de `dados.dir`, inclusive por links simbólicos. Na instalação
com tudo na raiz do site, a fila fica em `dados/fila-cadastros/`, dentro do
diretório da aplicação, com acesso direto por HTTP bloqueado pelo nginx.
Não é necessário mover os dados para fora do site. Diretórios usam 2770 e
arquivos 0660, com o grupo do CGI. O JSON contém dados originais e procedência: exige o mesmo
cuidado de acesso e backup do banco, e não deve ser publicado no repositório.

O recebimento grava um temporário, sincroniza arquivo, faz a troca atômica e
sincroniza o diretório. Só confirma depois de persistir também o índice de reenvio.
Sem espaço, permissão ou capacidade na fila, devolve erro em vez de confirmar.
O protocolo aleatório permite consultar o andamento, mas a consulta pública não
devolve o JSON original, IP, contato ou user-agent.

As pastas são `pendentes`, `processando`, `concluidos`, `rejeitados`, `indices`,
`limites` e `quarentena`. Uma trava curta protege o recebimento; outra garante
um único processador. A trava de recebimento não é mantida durante acesso ao banco.
Reenvio idêntico encontra o mesmo protocolo enquanto ele estiver retido.

O processador aplica as regras existentes de validação, bloqueios, procedência e
proximidade. Complementa o cadastro e sugere correspondência, preservando oficiais;
não torna uma colaboração verificada automaticamente. Não usa IA ou serviços externos.

Pedidos interrompidos voltam à fila. Se o banco já tiver confirmado a gravação
antes de uma queda, a ingestão idempotente encontra o mesmo radar na retomada.
Falhas temporárias têm espera progressiva; após o limite ficam como `falhou`,
preservadas para revisão. Banco ausente ou não inicializado adia o processamento;
não cria uma base vazia. A recepção e a consulta de protocolo não abrem SQLite.

JSON inválido ou com conteúdo divergente fica preservado em `quarentena`, e o
protocolo informa falha. Concluídos e rejeitados pelas regras expiram após o prazo
configurado. Pendentes, falhas não resolvidas e arquivos em quarentena não são
apagados automaticamente. Inclua a fila nos backups operacionais.

## Configuração e operação

O instalador cria pastas, ajusta permissões, completa chaves ausentes e instala
uma chamada independente por minuto: `radar-api.pse cron fila`. Assim, uma coleta
lenta não impede a ingestão. O cron continua entrando pela API e grava `fila.log`
no diretório de logs configurado, coberto pela regra de rotação existente.
Não exige Node, broker, sudo ou outro serviço. Cron de sincronização privada é preservado.

Defaults em `[cadastro]` do `radar.conf`, também editáveis no painel:

| Chave | Padrão | Efeito |
| --- | ---: | --- |
| `max_itens` | 100 | Radares por envio |
| `max_bytes` | 262144 | Tamanho do JSON normalizado, em bytes |
| `max_pendentes` | 10000 | Envios pendentes/em processamento |
| `lote` | 20 | Envios por passada do processador |
| `tentativas` | 5 | Tentativas por envio |
| `retencao_dias` | 30 | Retenção de concluídos/rejeitados |

O limite por IP de `[governanca]` é conferido no recebimento. Reenvio idêntico
não consome outra cota. Uma rodada processa até `lote` pedidos; novas passadas
continuam de onde pararam. A espera de nova tentativa cresce de 60 s até 1 h.

Comandos locais, usando o Python da instalação:

```sh
python3 ./api.pse fila processar
python3 ./api.pse fila consultar --protocolo PROTOCOLO
python3 ./api.pse fila reprocessar --protocolo PROTOCOLO
python3 ./api.pse fila verificar
```

Reprocessar exige revisar a causa e mantém as mesmas regras da ingestão; não
reabre pedidos já concluídos nem aceita automaticamente arquivos em quarentena.
`verificar` prova gravação durável sem criar pedido ou abrir banco. O instalador
executa essa checagem como o usuário real do CGI. Atualizações e recuperação do
código preservam a fila fora do checkout.

## Contrato HTTP

`POST api.pse?rota=/api/v1/radares/submeter`, com `Content-Type: application/json`
e `Prefer: respond-async`, recebe o mesmo payload dos modos simples e expert.
Retorna 202, `Preference-Applied: respond-async` e `Location` com a consulta.

```json
{"sucesso":true,"resultado":{"protocolo":"0123456789abcdef0123456789abcdef","estado":"recebido","recebido_em":"2026-10-21T00:00:00Z","tentativas":0,"consulta_url":"?rota=/api/v1/radares/envios/0123456789abcdef0123456789abcdef"}}
```

`GET api.pse?rota=/api/v1/radares/envios/PROTOCOLO` retorna 200 com o mesmo
envelope. Estados: `recebido`, `processando`, `aguardando_nova_tentativa`,
`processado`, `rejeitado` e `falhou`. `processado` inclui `resultado` da ingestão;
`rejeitado`/`falhou` incluem erro. Protocolo inválido, desconhecido ou expirado
retorna 404. Respostas de andamento e recebimento usam `Cache-Control: no-store`.

Por compatibilidade, clientes sem `Prefer: respond-async` mantêm o contrato
síncrono anterior, com 201 após ingerir. O formulário sempre pede o modo em fila.
