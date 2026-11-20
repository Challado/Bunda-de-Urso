# Configuração de caminhos (`radar.conf`)

Na instalação atual, o `radar.conf` fica ao lado de `api.pse`. A variável
`RADAR_CONF` seleciona outro arquivo para uma execução. Os valores vêm desse
arquivo, com padrões do código para as opções omitidas.

Quem responde no código é `core/caminhos.py`. Nenhum módulo, conector, script de
manutenção, entrada CGI ou arquivo de deploy decide caminho por conta própria.
O verificador `.github/scripts/verificar_caminhos.py` reprova quem tentar.

> Regra prática: **se você precisou escrever `/var/lib/...`, `/openclaw/...` ou
> `/var/www/...` dentro de um `.py`, `.sh` ou `.pse`, o código está errado.**
> Peça o caminho a `core.caminhos` ou acrescente a chave ao `.conf`.

## O arquivo

Modelo pronto: `deploy/radar.conf.exemplo`. Instalação:

```bash
install -d -m 0755 /etc/radar-brasil
install -m 0644 deploy/radar.conf.exemplo /etc/radar-brasil/radar.conf
editor /etc/radar-brasil/radar.conf
python3 deploy/conf_radar.py --verificar
```

`deploy/conf_radar.py --instalar` também cria o arquivo, mas **nunca sobrescreve**:
se já existir, grava `radar.conf.novo` ao lado para revisão.

## Chaves

| Seção.chave | O que é |
|---|---|
| `instalacao.home` | raiz do código (`core/`, `coletor/`, `web/`, `sql/`) |
| `dados.dir` | diretório dos arquivos operacionais |
| `dados.motor` | motor ativo, `sqlite` ou `postgres` |
| `sqlite.banco` | nome do banco SQLite dentro de `dados.dir`, por padrão `radar.sqlite3` |
| `postgres.host`, `.porta`, `.banco`, `.usuario`, `.esquema` | conexão e esquema do PostgreSQL |
| `postgres.pgpass`, `.sslmode`, `.certificado_ca`, `.connect_timeout` | arquivo de senha, modo TLS, CA opcional e tempo de conexão em segundos |
| `web.raiz` | webroot servido pelo nginx/fcgiwrap |
| `web.url` | prefixo público da consulta |
| `logs.dir` | logs do Radar |

Extras:

* `dados.dir` relativo é resolvido na pasta do `.conf`. Arquivos operacionais
  relativos, como `sqlite.banco` e `postgres.pgpass`, são resolvidos dentro de `dados.dir`;
* `~` é expandido;
* `sqlite.banco` vazio usa `radar.sqlite3`;
* chave ou seção desconhecida **não derruba** nada: vira aviso em
  `python3 deploy/conf_radar.py --mostrar`.

## Configuração do banco

Use `[dados] motor = postgres` para selecionar `[postgres]`. A opção `pgpass`
indica o arquivo de senha dentro de `dados.dir`. A porta padrão é 5432, o
esquema padrão é `radar_brasil` e o tempo de conexão padrão é de 10 segundos.
Para uma instalação SQLite, use `motor = sqlite` e informe o nome do arquivo
em `[sqlite] banco`.

Ao atualizar uma instalação antiga, o instalador converte `dados.banco` em
`sqlite.banco` quando o motor é SQLite. Em PostgreSQL, remove a chave antiga e
continua usando a conexão existente de `[postgres]`.

## O que cada peça faz

* `core/caminhos.py` — a porta única (leitura, precedência, normalização).
* `core/config.py` — reexporta `DATA_DIR`, `RAW_DIR`, `STAGING_DIR`, `DB_PATH`
  vindos da porta. Nada de caminho novo ali.
* `core/manutencao/*.py` — `--db` seleciona um arquivo dentro de `dados.dir` nas instalações SQLite.
* `deploy/radar-tick.sh` — chama o `radar-api.pse` instalado ao lado, com
  `cron tick`. A API resolve a configuração e abre o log; o shell não tem outro parser.
* `deploy/api.pse` e `web/api.pse` — descobrem a raiz do código pelo `.conf`;
  o do webroot tenta `RADAR_BRASIL_HOME` → `.conf` → vizinhança; o do checkout
  tenta `RADAR_BRASIL_HOME` → o próprio checkout → `.conf` (teste nunca importa
  código de produção por acidente).
* `deploy/conf_radar.py` — `--mostrar` (efetivo + origem de cada chave),
  `--verificar` (existência, escrita, dono, `core/`, `api.pse`),
  `--instalar`, `--exemplo`.

## Diagnóstico

```bash
python3 deploy/conf_radar.py            # onde o programa acha que tudo está
python3 deploy/conf_radar.py --verificar
python3 .github/scripts/verificar_caminhos.py
```

Saída do `--mostrar` traz, por chave, o valor efetivo e a origem
(`ambiente (VAR)`, o caminho do `.conf` ou `padrao`).

## Como isso quebrava antes

Três layouts conviviam no mesmo repositório e no mesmo servidor:

* `/home/openclaw/bin/radar` (modelo antigo, ainda em `deploy/`);
* `/openclaw/bin/radar` (produção real em outubro/2026);
* `/opt/radarbrasil` + `/var/lib/radarbrasil` (material de `referencia/`, arquivado).

Um script gerado noutro layout mudava o diretório de trabalho de quem o executava —
por exemplo, um `radar-tick.sh` que apontava para um `api.pse` que a versão
instalada não conhecia: o cron rodava a cada minuto e o coletor **não coletava**.
Com o `.conf`, caminho deixa de ser opinião de cada script: é configuração.

## Trocar de servidor

1. `git clone` do código no novo destino;
2. `install -d /etc/radar-brasil && install -m 0644 deploy/radar.conf.exemplo /etc/radar-brasil/radar.conf`;
3. ajustar `home`, `dados.dir`, `dados.motor`, a seção do motor ativo, `web.raiz` e `logs.dir`;
4. `python3 <home>/deploy/conf_radar.py --verificar`;
5. copiar o `api.pse` para o webroot e o `radar-tick.sh` para o diretório do cron.

Nada no código muda entre servidores.

## Leitura e salvamento pela API

A tela **Administração → Configuração** usa exclusivamente
`api.pse?rota=/api/v1/gestao/configuracao` (GET/PUT). Exige sessão ou token **admin**;
moderador e contribuidor não acessam configurações. Cada seção é recolhível e começa
aberta. Mostra o valor gravado, o valor em uso e sua origem. Variáveis de ambiente
continuam tendo precedência explícita e impedem salvar um valor que ficaria oculto.

O painel pode salvar parâmetros operacionais: limites de requisição/download,
proxies confiáveis e parâmetros de governança. Caminhos, usuários,
destinos de instalação e credenciais são exibidos, com alteração somente pela API
local. Isso impede que a conta do painel troque o código que o cron executa como root.
O instalador cria `<web.raiz>/radar.conf` como link simbólico para o arquivo
configurado em `/etc`. A API verifica o destino do link antes de ler ou salvar.
A pasta da configuração fica em `2770`, grupo do CGI (`www-data` no servidor3),
e `radar.conf` em `0660`. O processo CGI grava diretamente, sem elevação de
privilégios nem subprocesso de salvamento. A substituição atômica ocorre no destino
em `/etc`, preservando o link. A regra antiga `sudoers.d/radar-configuracao` é removida;
o aplicativo não exige nem executa sudo/visudo.

Antes de criar o link, o instalador identifica o server do radar na configuração
ativa do nginx por `web.origem` ou pela raiz que contém `web.raiz`, e acrescenta um
bloqueio HTTP exato para `<web.url>/radar.conf`. Guarda os arquivos alterados no
backup, valida `nginx -t` e recarrega nginx. O conteúdo continua acessível ao processo
CGI, mas o download direto retorna 404. A checagem externa confirma também esse
bloqueio. A configuração do nginx é recuperada se a instalação falhar.

O salvamento usa trava entre processos, revisão SHA-256 contra edição concorrente,
arquivo temporário e substituição atômica. Guarda `radar.conf.anterior` e os metadados
em `radar.conf.auditoria.jsonl` ao lado do arquivo; nenhum valor de token é retornado.
Novos processos CGI e novas passadas do cron leem a configuração atualizada.
Caminhos são configuração: **alterá-los não move arquivos**.

No terminal:

```bash
python3 web/api.pse configuracao mostrar
python3 web/api.pse configuracao verificar
# JSON com revisao e alteracoes, por exemplo {"governanca.submissao_limite":"10"}:
python3 web/api.pse configuracao salvar < alteracao.json
```

`deploy/conf_radar.py` permanece como cliente de compatibilidade da mesma API.
Os parâmetros operacionais antes distribuídos em `config/governanca.json` agora
pertencem a `[governanca]` do `radar.conf`. O instalador importa os valores do código
antigo somente quando a respectiva chave ainda não existe no arquivo do servidor.
O JSON antigo deixa de ser fonte de configuração e não é mais distribuído.

Seções adicionais no modelo `deploy/radar.conf.exemplo`:

| Seção | Configuração |
|---|---|
| `api` | `token_arquivo` (caminho, nunca o token), `max_body`, `proxies_confiaveis` |
| `coleta` | `max_bytes`, `timeout`, `tentativas` |
| `consultas` | regras por fonte e por URL para as consultas externas dos coletores |
| `governanca` | correspondência por proximidade, bloqueios, submissões, sessão e PBKDF2 |
| `geografia` | `malha` opcional |
| `assistente` | URL e modelo do assistente usado em manutenção local |

Senhas, `RADAR_API_TOKEN` e a senha inicial de administração continuam credenciais
separadas. Catálogos de fontes, malhas e tabelas de calibração distribuídos com o código
são dados de referência, não configurações particulares do servidor.

## Consultas externas dos coletores

Em **Gestão → Configuração → Consultas externas**, adicione uma regra e escolha
a fonte. Deixe o endereço em branco para aplicar à fonte inteira ou informe
uma URL HTTPS ou seu prefixo para ajustar uma etapa específica. Use **Todas as
fontes** para uma regra geral. Defina só os campos desejados. Um prefixo de URL
mais específico prevalece e, no empate, vale a regra da fonte selecionada.

- **Timeout (s)** limita a espera nas operações de rede HTTP. No Chromium,
  limita a execução da consulta.
- **Tentativas HTTP** ajusta as repetições em falhas transitórias.
- **Limite da resposta** é medido em bytes.
- **User-Agent** pode usar a identificação padrão do cliente, sortear um
  User-Agent de navegador por execução da coleta ou enviar um valor personalizado.

A ANTT usa pelo menos 60 segundos para atividades, revisão e catálogo e
120 segundos para o arquivo por padrão. Para ajustar pelo terminal, use
a seção abaixo no `radar.conf`. Mantenha o JSON das regras em uma linha.

```ini
[consultas]
regras = [{"fonte":"antt","timeout":180,"tentativas":2},{"fonte":"antt","url":"https://dados.antt.gov.br/dataset/activity/radar","timeout":90,"user_agent":"sistema"}]
```

## Atualização coordenada

O instalador `.sh` e o perfil do servidor3 ficam no repositório privado de dados.
Ele baixa uma revisão validada do código e chama `api.pse instalacao`; por padrão
apenas simula. Usa o `radar.conf` existente e não o substitui por um modelo.

Ao aplicar, guarda código, páginas, configuração e um backup consistente do SQLite
na pasta `backups/instalacao/` dos dados. Pausa novas chamadas do coletor e da API,
aguarda a coleta em andamento terminar, prepara o código, aplica migrações
aditivas pela API, testa a prontidão e só então instala o wrapper novo. Em falha,
restaura código, páginas e configuração automaticamente; preserva o banco atual.

A operação modifica somente a linha do coletor no crontab de root. O envio ao
repositório privado e seus scripts pertencem ao servidor3, ficam fora do aplicativo
e não são migrados nem alterados pelo instalador.

Reaplicar preserva a configuração e os dados. Backups de instalação não são podados.
`--restaurar <backup>` recupera arquivos da instalação, preservando o banco e os outros
agendamentos. `--laboratorio <pasta>` restringe todos os destinos à pasta indicada e
não configura cron nem altera o nginx do sistema.

O descritor estático `projeto.json` é gerado pelo instalador com `web.url` do `.conf`.
Ao mudar o prefixo público pela API local, reaplique o instalador para atualizar o descritor;
o roteamento do nginx permanece uma configuração do servidor.

A seção legada `[sincronizacao]`, quando já existe no arquivo do servidor, é preservada
sem edição pelo aplicativo. O painel e o diagnóstico não configuram nem exigem o espelho privado.

## Atualizador recorrente e auditoria

O `.sh` privado passa a buscar a `main` pública atual em cada execução. Seleciona
um único commit para toda a operação e registra essa revisão em `VERSAO`; não mistura
arquivos de revisões diferentes. `--versao` permite fixar uma revisão compatível.

O plano compara hashes dos arquivos instalados e mostra novas opções de configuração.
Ao aplicar, somente acrescenta padrões ausentes; valores existentes e chaves vazias
são preservados. `--verificar` audita a instalação, sem aplicar alterações, e retorna
falha se existem divergências. `--relatorio` salva a auditoria em JSON; a atualização
sempre guarda `checagem-final.json` no backup.

O perfil privado é enviado à API por `--perfil-conf`: também completa caminhos e
opções de instalação ausentes em um `radar.conf` parcial. O plano usa uma cópia
temporária; o arquivo definitivo só é gravado ao aplicar, depois do backup. Se
`sqlite.banco` foi omitido numa instalação SQLite, usa `radar.sqlite3` dentro de `dados.dir`.

Ao aplicar, diretórios operacionais ausentes são criados e recebem grupo e
permissões adequados, inclusive os pais novos para permitir acesso pelo CGI.
São recriados também a regra do logrotate, link de configuração do painel, páginas e entradas
da API/coletor. Pastas ausentes ou com permissões divergentes impedem o resultado
de "já atualizado", mesmo quando a revisão não mudou. Um destino vazio do código
pode ser preenchido; arquivos e pastas de outros aplicativos continuam protegidos.

No final aparece **Observações**, com diretórios criados, permissões ajustadas,
opções e padrões acrescentados, pacotes preparados, serviços iniciados e regras
gerenciadas criadas/atualizadas. O JSON contém a lista em `observacoes`; falhas após
o backup também guardam essa lista e `recuperacao_automatica`. Os arquivos anteriores
são recuperados em falha, mas pastas preparadas podem permanecer. O banco existente
é preservado e um banco ausente não é substituído silenciosamente por uma base vazia.

A regra do logrotate informa `su` com `instalacao.usuario` e `instalacao.grupo`
do `radar.conf`, permitindo rotacionar a pasta de logs gravável pelo grupo do CGI.
A validação usa `logrotate --debug`, sem girar os arquivos. Em falha, o relatório
registra o comando, código de saída e mensagens de erro (saída limitada a 16 KiB por
canal). A recuperação também restaura a regra anterior: se ela não existia antes da
tentativa, ficará ausente após a recuperação. O relatório no backup descreve a
checagem antes dessa recuperação, não o estado posterior do servidor.

Entradas antigas ou duplicadas do cron do coletor são reconhecidas, inclusive chamadas
diretas antigas a `coletor/tick.py` e `api.pse tick`, e consolidadas em um tick por minuto.
Agendamentos dos sincronizadores privados e outros projetos são preservados. Uma falha
ao ler o crontab não é tratada como ausência de crontab.

O perfil privado pode preparar dependências ausentes via apt e iniciar serviços
inativos. A API valida nginx, serviços, arquivos, permissões, rotação de logs,
configuração, gravação do painel como o usuário real do CGI e consultas ao banco.
No nginx acrescenta somente o bloqueio HTTP do link de configuração; preserva as
demais rotas e configurações dos sites. Pacotes instalados e serviços iniciados
não são revertidos pela recuperação dos arquivos do aplicativo.

`web.origem` é a origem HTTP(S) opcional do site, sem prefixo de caminho, por exemplo
`https://exemplo.org`. Com `web.url`, permite conferir prontidão da API e os bytes da
página administrativa pelo nginx. Origem vazia deixa essa checagem explicitamente
como não realizada. A opção inicial `--origem-http` não substitui uma chave existente.
Laboratórios usam somente os destinos temporários e não consultam produção.

`coleta.espera_atualizacao` limita em segundos a espera pela coleta em andamento
(padrão 300); ao esgotar o prazo, a atualização recupera os arquivos anteriores.

## Política de acesso da instância pública

O servidor limita cada página a `api.limite_consulta` (padrão e máximo de 200).
Acima de `api.cursor_publico_max` (2.000 por padrão), as consultas paginadas
exigem `X-Radar-Leitura`. O arquivo `api.chaves_leitura_arquivo` fica dentro
de `dados.dir` e contém um SHA-256 hexadecimal por linha. Emissão e revogação
são manuais. Gere um token aleatório para cada integração, entregue o token
diretamente ao responsável e grave somente seu SHA-256 no arquivo. A chave
de leitura serve à paginação e é independente dos tokens de gestão e da rede.

As listas em `[abuso]` são JSON de uma linha. Os endereços abaixo são exemplos
reservados para documentação. Preencha com os endereços e agentes aprovados.

```ini
[abuso]
bloqueios = [{"rota":"/api/v1/radares/busca","user_agent_regex":"(?i)^ExemploBot/","status":403}]
liberacoes = [{"rota":"/api/v1/radares/envios","redes":["192.0.2.10-192.0.2.20"],"user_agent_regex":"^ClienteAutorizado/1[.]0$"}]
janela_segundos = 600
max_paginas_grandes = 12
pagina_grande_min = 150
```

- Em `redes`, use endereços individuais, CIDR como `192.0.2.0/24` ou
  intervalos inclusivos. IPv4 e IPv6 são aceitos. `user_agent_regex` permite
  uma expressão regular de até 256 caracteres. IP e regex podem ser usados
  separadamente. Quando ambos aparecem na mesma regra, ambos são exigidos.
- As regras de leitura aceitam as rotas públicas de busca, download, histórico
  de coleta, trechos, operações, tráfego e cobertura por estado. Para detalhes,
  use `/api/v1/radares/{id}`, `/api/v1/equipamentos/{id}` ou
  `/api/v1/status/estados/{uf}`. Uma liberação vale somente para sua rota, tem
  prioridade sobre o bloqueio manual e a cota, e mantém o teto e a chave da
  paginação profunda. Um bloqueio sem `rota` vale para todas essas leituras.
  O bloqueio também pode usar `limite_minimo` e `cursor_minimo` e retorna
  `403` por padrão ou `429` se configurado. As regras usam o IP reconhecido
  pela API, que só aceita encaminhamento de proxies confiáveis.
- Para aprovar acesso ao andamento do cadastro simplificado, use
  `/api/v1/radares/envios` em `liberacoes`. Os moderadores também podem
  consultar com a credencial habitual. O recebimento do cadastro é público.
- A cota agrupa páginas grandes pela chave válida ou pela
  rede de origem, `/24` no IPv4 e `/64` no IPv6. Ao excedê-la, a API responde
  `429` com `Retry-After`. Use `max_paginas_grandes = 0` para desativar a cota.
- `api.timeout_consulta` define o prazo da requisição CGI, com máximo de 60
  segundos. O download usa um arquivo já gerado. `api.pse cron dump` verifica
  a cada 15 minutos e gera uma cópia por dia UTC em
  `dados/exportacao/radares.json.gz`, mantendo a cópia anterior se a geração falhar.
