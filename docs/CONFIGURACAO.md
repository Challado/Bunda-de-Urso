# Configuração de caminhos (`/etc/radar-brasil/radar.conf`)

O programa **não sabe** onde está instalado, onde mora o banco nem qual é o webroot.
Ele pergunta — sempre — a um único lugar:

| Ordem | Fonte | Uso |
|---|---|---|
| 1 | variável de ambiente | emergência, teste, CI, execução pontual |
| 2 | `/etc/radar-brasil/radar.conf` | instalação no servidor (editável) |
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
| `sincronizacao.clone` | clone local do repositório privado de dados | `RADAR_SYNC_CLONE` |
| `sincronizacao.remoto` | URL do repositório privado de dados | `RADAR_SYNC_REMOTO` |
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
* `deploy/radar-tick.sh` — lê o `.conf` em `sh` (sem `python` antes do `python`) e
  executa `api.pse tick`; sem `.conf`, usa o checkout ao lado do script.
* `deploy/api.pse` e `web/api.pse` — descobrem a raiz do código pelo `.conf`;
  o do webroot tenta `RADAR_BRASIL_HOME` → `.conf` → vizinhança; o do checkout
  tenta `RADAR_BRASIL_HOME` → o próprio checkout → `.conf` (teste nunca importa
  código de produção por acidente).
* `deploy/conf_radar.py` — `--mostrar` (efetivo + origem de cada chave),
  `--verificar` (existência, escrita, dono, `core/`, `api.pse`, clone),
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
