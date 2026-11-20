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

Para iniciar um checkout local, use o modelo `deploy/radar.conf.exemplo`.

```bash
cp -n deploy/radar.conf.exemplo radar.conf
mkdir -p dados
editor radar.conf
python3 web/api.pse configuracao mostrar
```

Em produção, o instalador coloca o arquivo junto do `api.pse`. Veja a
[migração para a raiz web](MIGRACAO_RAIZ_WEB.md) para instalações antigas.

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
| `logs.dir` | logs do Radar dentro de `dados.dir`, por padrão `logs` |

Extras:

* `dados.dir` relativo é resolvido na pasta do `.conf`. Arquivos operacionais
  relativos, como `sqlite.banco` e `postgres.pgpass`, são resolvidos dentro de `dados.dir`;
* `~` é expandido;
* `sqlite.banco` vazio usa `radar.sqlite3`;
* chaves e seções desconhecidas aparecem como aviso em
  `python3 web/api.pse configuracao mostrar`.

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
* No servidor3, o crontab do `www-data` chama o `api.pse` instalado com
  `cron tick`, `cron fila`, `cron traseiro` e `cron dump`.
* `deploy/api.pse` é a entrada instalada. Usa `[instalacao] home` para
  localizar o código. `web/api.pse` usa o código do próprio checkout quando
  disponível. Ambos leem os parâmetros do `radar.conf` selecionado.
* `api.pse configuracao` reúne as operações `mostrar`, `verificar`,
  `instalar` e `exemplo`, além dos comandos de alteração.

## Diagnóstico

```bash
python3 web/api.pse configuracao mostrar
python3 .github/scripts/verificar_caminhos.py
```

A saída de `mostrar` indica o valor efetivo e a origem de cada chave, que
pode ser o arquivo selecionado ou o padrão da aplicação. Para conferir a
instalação pronta, rode `api.pse configuracao verificar` com a mesma conta
que executa a API.

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

1. Clone o projeto e localize o instalador da sua implantação.
2. Coloque o `radar.conf` na raiz onde ficará o `api.pse`. Ajuste
   `instalacao.home`, `dados.dir`, `dados.motor`, a seção do motor ativo,
   `web.raiz`, `web.url` e `web.origem`.
3. Transfira o diretório de dados existente e dê acesso a ele à conta que
   executará o Radar. Preserve o arquivo ou a conexão do motor ativo.
4. Aplique o instalador e rode `api.pse configuracao verificar` com a conta
   da aplicação.

Nada no código muda entre servidores.

## Leitura e salvamento pela API

A aba **Configuração** do painel de gestão usa
`api.pse?rota=/api/v1/gestao/configuracao` (GET e PUT) e exige sessão ou
token de administrador. Mostra o valor gravado, o valor em uso e sua origem.
Nas seções de banco, mostra apenas o motor ativo.

O painel salva parâmetros como limites de requisição, proxies confiáveis,
regras de coleta e opções de governança. Use a API local para ajustar
caminhos, destinos e arquivos de credenciais. No layout atual, o CGI
grava o `radar.conf` diretamente ao lado de `api.pse`, com as permissões
preparadas pelo instalador. O Nginx permanece sob gestão do operador.
O instalador verifica se o acesso HTTP ao arquivo está bloqueado.

O salvamento usa trava entre processos, revisão SHA-256 contra edição concorrente
e substituição atômica. Guarda `radar.conf.anterior` e
`radar.conf.auditoria.jsonl` em `<dados.dir>/configuracao/`. O registro de
auditoria inclui os nomes das chaves alteradas. Novas chamadas da API e do
cron leem a configuração atualizada. Alterar caminhos pelo painel ou pela
API local requer mover os arquivos separadamente.

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
| `coleta` | `max_bytes`, `timeout`, `tentativas`, `verificar_ssl` |
| `consultas` | regras por fonte e por URL para as consultas externas dos coletores |
| `governanca` | correspondência por proximidade, bloqueios, submissões, sessão e PBKDF2 |
| `geografia` | `malha` e `snv_rotas` opcionais |
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
- **Certificado HTTPS** herda `[coleta] verificar_ssl` ou usa o valor definido
  na regra. O padrão global é `0` (desligado). Use `1` para ligar globalmente,
  ou `true` e `false` nas regras JSON. O cliente HTTP reavalia o certificado
  a cada redirecionamento. No Chromium, a opção vale para a sessão aberta
  pelo coletor.
- **User-Agent** pode usar a identificação padrão do cliente, sortear um
  User-Agent de navegador por execução da coleta ou enviar um valor personalizado.

O coletor da ANTT procura a edição mais recente nas atividades do conjunto
e também consulta o catálogo CKAN. Por padrão, reserva pelo menos 60 segundos
para atividades, revisão e catálogo e 120 segundos para o arquivo. Para
ajustar pelo terminal, use a seção abaixo no `radar.conf`. [Atividades da ANTT](https://dados.antt.gov.br/dataset/activity/radar)

```ini
[coleta]
verificar_ssl = 0

[consultas]
regras = [{"fonte":"antt","timeout":180,"tentativas":2,"verificar_ssl":true},{"fonte":"antt","url":"https://dados.antt.gov.br/dataset/activity/radar","timeout":90,"user_agent":"sistema"}]
```

Se a validação global estiver ligada, uma regra
`{"fonte":"der_rj","verificar_ssl":false}` na lista existente permite que o
DER-RJ seja consultado durante um problema no certificado. A regra
restringe a alteração a esse leitor. Depois de salvar, rode a coleta manual
como o usuário da aplicação e confira a tentativa nova no status.

```sh
cd /var/www/html/openclaw/radar
runuser -u www-data -- ./api.pse sync --fonte der_rj
```

## Atualização coordenada

O instalador `.sh` e o perfil do servidor3 ficam no repositório privado de dados.
Ele baixa uma revisão validada do código e chama `api.pse instalacao`; por padrão
apenas simula. Usa o `radar.conf` existente e não o substitui por um modelo.

Ao aplicar no layout atual, guarda código, páginas, configuração e uma cópia
consistente do banco ativo em `<dados.dir>/backups/raiz-web/`. Pausa novas
chamadas da API, aguarda o coletor e a fila, prepara o código e aplica
migrações. O relatório registra o ponto da falha e se houve recuperação
automática. [Atualização na raiz web](MIGRACAO_RAIZ_WEB.md)

A operação retira as tarefas do Radar do crontab do root e instala coleta,
fila, rede e geração do arquivo diário no crontab do `www-data`. Preserva
as tarefas dos outros sistemas e os sincronizadores privados.

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
São preparados também a regra do logrotate, configuração do painel, páginas e entradas
da API/coletor. Pastas ausentes ou com permissões divergentes impedem o resultado
de "já atualizado", mesmo quando a revisão não mudou. Um destino vazio do código
pode ser preenchido; arquivos e pastas de outros aplicativos continuam protegidos.

No final aparece **Observações**, com diretórios criados, permissões ajustadas,
opções e padrões acrescentados, pacotes preparados, serviços iniciados e regras
gerenciadas criadas/atualizadas. O JSON contém a lista em `observacoes`; falhas após
o backup também guardam essa lista e `recuperacao_automatica`. Os arquivos anteriores
são recuperados em falha, mas pastas preparadas podem permanecer. O banco existente
é preservado e um banco ausente não é substituído silenciosamente por uma base vazia.

A regra do logrotate usa o proprietário e o grupo da pasta de logs para
rotacioná-la com as permissões do usuário da aplicação.
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
Para o Nginx, verifica a sintaxe e faz sondagens HTTP. A configuração e
o serviço ficam sob responsabilidade do operador. A recuperação de arquivos
do aplicativo mantém os pacotes e os demais serviços preparados.

`web.origem` é a origem HTTP(S) opcional do site, sem prefixo de caminho, por exemplo
`https://exemplo.org`. Com `web.url`, permite conferir prontidão da API e os bytes da
página administrativa pelo nginx. Origem vazia deixa essa checagem explicitamente
como não realizada. A opção inicial `--origem-http` não substitui uma chave existente.
Laboratórios usam somente os destinos temporários e não consultam produção.

`coleta.espera_atualizacao` limita em segundos a espera pela coleta em andamento
(padrão 300); ao esgotar o prazo, a atualização recupera os arquivos anteriores.

## Política de acesso da instância pública

O servidor limita pedidos com `limite` positivo a `api.limite_consulta` (padrão
e máximo de 200). O valor `limite=0` retorna todos os resultados, respeitando
os filtros, o cursor e a cota das buscas de radares.
Acima de `api.cursor_publico_max` (2.000 por padrão), as consultas paginadas
exigem `X-Radar-Leitura`. O arquivo `api.chaves_leitura_arquivo` fica dentro
de `dados.dir` e contém um SHA-256 hexadecimal por linha. Emissão e revogação
são manuais. Gere um token aleatório para cada integração, entregue o token
diretamente ao responsável e grave somente seu SHA-256 no arquivo. A chave
de leitura serve à paginação e é independente dos tokens de gestão e da rede.

As listas em `[abuso]` aceitam JSON de uma linha ou formatado em várias linhas.
Indente todas as linhas após `= [`, incluindo o `]` final. Os endereços abaixo
são reservados para documentação. Preencha com os endereços e agentes aprovados.
Você pode agrupar regras em listas internas, como `[[{...}], [{...}]]`.
Os grupos são avaliados na ordem em que aparecem, com até 100 regras por opção.

```ini
[abuso]
bloqueios = [
    [{"user_agent_regex": "(?i)^ExemploBot/", "status": 403}],
    [{"redes": ["198.51.100.0/24"], "status": 403}]
    ]
liberacoes = [
    {
      "rota": "/api/v1/radares/envios",
      "redes": ["192.0.2.10-192.0.2.20"],
      "user_agent_regex": "^ClienteAutorizado/1[.]0$"
    }
    ]
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
  segundos. O download usa um arquivo já gerado. No servidor3, o agendamento
  chama `api.pse cron dump` a cada 15 minutos e publica uma cópia por dia UTC
  em `<dados.dir>/exportacao/radares.json.gz`. Se a geração falhar, mantém a
  cópia anterior.

## Radares e trechos de fontes governamentais

Os coletores `mogi_sp`, `eptc_poa`, `cet_rio` e `artesp` consultam
as publicações dos respectivos órgãos e seguem a agenda normal.

O leitor `teresina_pi` acompanha o mapa que a STRANS publica na página
municipal. Descobre o identificador do mapa a cada coleta e baixa o KML.
O PDF na mesma página serve de referência complementar. A coleta preserva
os códigos, os endereços, as coordenadas e os sentidos publicados. Velocidade
e situação operacional ficam em branco quando a fonte não as informa.
[Localização de radares da STRANS](https://www.teresina.pi.gov.br/strans/localizacao-de-radares/)

O leitor `detran_df` usa a lista vigente da página de equipamentos. A revisão
da URL reaproveita o mesmo recurso e preserva o histórico das leituras.
A camada histórica `detran_df_arcgis` é um leitor distinto, disponível para
coleta manual. A camada contém registros antigos cuja operação atual
precisa de confirmação. [Lista oficial do Detran-DF](https://geoservicos.detran.df.gov.br/geoserver/styles/lista_equipto/index.html)

A atualização do esquema recupera a UF já publicada nos trechos antigos.
A coleta agendada do DER-MG tenta localizar os radares por rodovia e
quilômetro na IDE-Sisema. Para antecipar essa etapa, execute a ferramenta
abaixo como o usuário de execução da API. Sem `--aplicar`, ela informa
quantos registros poderiam ser localizados.

```bash
./api.pse ferramenta georreferenciar_oficiais --mg --aplicar
```

Para as rodovias federais, informe o ZIP de **rotas** do Sistema Nacional de
Viação do DNIT. Pode ser a URL HTTPS do arquivo em `servicos.dnit.gov.br`
ou o caminho para a cópia oficial dentro de `[dados] dir`. Preencha
`snv_rotas` em `[geografia]` para executar o cruzamento após a coleta
agendada dos trechos da PRF.

```bash
./api.pse ferramenta georreferenciar_oficiais --snv calibracao/rotas-snv.zip --aplicar
```

O cruzamento federal exige UF, rodovia e quilometragem compatíveis. O de
Minas Gerais também confere o município pela malha do IBGE. As posições e
os traçados calculados ficam identificados como inferidos, com referência à
malha usada. Os vértices de um trecho elegível indicam onde pode haver
fiscalização portátil, sem afirmar que há um equipamento instalado.
