# Configuração de caminhos (`/etc/radar-brasil/radar.conf`)

O programa **não sabe** onde está instalado, onde mora o banco nem qual é o webroot.
Ele pergunta — sempre — a um único lugar:

| Ordem | Fonte | Uso |
|---|---|---|
| 1 | variável de ambiente | emergência, teste, CI, execução pontual |
| 2 | `/etc/radar-brasil/radar.conf` | instalação no servidor (editável pela API) |
| 3 | padrão do checkout | desenvolvimento e CI, sem configurar nada |

Quem responde no código é `core/caminhos.py`. Nenhum módulo, conector, script de
manutenção, entrada CGI ou arquivo de deploy decide caminho por conta própria.
O verificador `.github/scripts/verificar_caminhos.py` reprova quem tentar.

> Regra prática: **se você precisou escrever `/var/lib/...`, `/openclaw/...` ou
> `/var/www/...` dentro de um `.py`, `.sh` ou `.pse`, o código está errado.**
> Peça o caminho a `core.caminhos` ou acrescente a chave ao `.conf`.

## O arquivo

Modelo pronto: `deploy/radar.conf.exemplo`. Instalação:

```bash
sudo install -d -m 0755 /etc/radar-brasil
sudo install -m 0644 deploy/radar.conf.exemplo /etc/radar-brasil/radar.conf
sudo editor /etc/radar-brasil/radar.conf
python3 deploy/conf_radar.py --verificar
```

`deploy/conf_radar.py --instalar` também cria o arquivo, mas **nunca sobrescreve**:
se já existir, grava `radar.conf.novo` ao lado para revisão.

## Chaves

| Seção.chave | O que é | Variável equivalente |
|---|---|---|
| `instalacao.home` | raiz do código (`core/`, `coletor/`, `web/`, `sql/`) | `RADAR_BRASIL_HOME` |
| `dados.dir` | dados: banco, `raw/`, `staging/`, `calibracao/` | `RADAR_DATA_DIR` |
| `dados.banco` | banco SQLite (vazio = `<dados.dir>/radar.sqlite3`) | `RADAR_DB` |
| `web.raiz` | webroot servido pelo nginx/fcgiwrap | `RADAR_WEB_ROOT` |
| `web.url` | prefixo público da consulta | `RADAR_WEB_URL` |
| `logs.dir` | logs do tick e do dados-sync | `RADAR_LOG_DIR` |
| `instalacao.usuario` / `.grupo` | dono esperado (informativo; o verificador confere) | — |

Extras:

* caminho **relativo** no `.conf` é resolvido contra a pasta do próprio `.conf`;
* `~` é expandido;
* chave vazia (`banco =`) cai no padrão daquela chave;
* chave ou seção desconhecida **não derruba** nada: vira aviso em
  `python3 deploy/conf_radar.py --mostrar`.

## O que cada peça faz

* `core/caminhos.py` — a porta única (leitura, precedência, normalização).
* `core/config.py` — reexporta `DATA_DIR`, `RAW_DIR`, `STAGING_DIR`, `DB_PATH`
  vindos da porta. Nada de caminho novo ali.
* `core/manutencao/*.py` — `DB_PADRAO = caminhos.banco()`; `--db` continua mandando.
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
2. `sudo install -d /etc/radar-brasil && sudo install -m 0644 deploy/radar.conf.exemplo /etc/radar-brasil/radar.conf`;
3. ajustar `home`, `dados.dir`, `dados.banco`, `web.raiz`, `logs.dir`;
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
A configuração **não** é um diretório público nem um symlink no webroot.

O instalador mantém a pasta da configuração em `0755` e o arquivo em `0644`, de root.
Autoriza no sudoers um único comando, sem argumentos extras ou SETENV:
`python <home>/web/api.pse configuracao salvar-web --conf <arquivo>`.
O próprio serviço valida a lista restrita de chaves, tipos e limites. O CGI não recebe
escrita em `/etc`. Requer `sudo`/`visudo`. A aplicação só anuncia a gravação no painel
depois de verificar o comando como o usuário real do CGI.

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
| `governanca` | correspondência por proximidade, bloqueios, submissões, sessão e PBKDF2 |
| `geografia` | `malha` opcional |
| `assistente` | URL e modelo do assistente usado em manutenção local |

Senhas, `RADAR_API_TOKEN` e a senha inicial de administração continuam credenciais
separadas. Catálogos de fontes, malhas e tabelas de calibração distribuídos com o código
são dados de referência, não configurações particulares do servidor.

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
não configura cron ou sudo no sistema.

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

Entradas antigas ou duplicadas do cron do coletor são reconhecidas, inclusive chamadas
diretas antigas a `coletor/tick.py` e `api.pse tick`, e consolidadas em um tick por minuto.
Agendamentos dos sincronizadores privados e outros projetos são preservados. Uma falha
ao ler o crontab não é tratada como ausência de crontab.

O perfil privado pode preparar dependências ausentes via apt e iniciar serviços
inativos. A API valida nginx, serviços, arquivos, permissões, rotação de logs,
configuração, autorização restrita do painel e consultas ao banco. Não reescreve
configurações do nginx ou de outros sites. Pacotes instalados e serviços iniciados
não são revertidos pela recuperação dos arquivos do aplicativo.

`web.origem` é a origem HTTP(S) opcional do site, sem prefixo de caminho, por exemplo
`https://exemplo.org`. Com `web.url`, permite conferir prontidão da API e os bytes da
página administrativa pelo nginx. Origem vazia deixa essa checagem explicitamente
como não realizada. A opção inicial `--origem-http` não substitui uma chave existente.
Laboratórios usam somente os destinos temporários e não consultam produção.

`coleta.espera_atualizacao` limita em segundos a espera pela coleta em andamento
(padrão 300); ao esgotar o prazo, a atualização recupera os arquivos anteriores.
