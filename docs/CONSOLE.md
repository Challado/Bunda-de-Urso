# Console — o `api.pse` no terminal do servidor

O **mesmo** `api.pse` serve a web e o terminal. Rodando sob o nginx ele é CGI;
rodando na linha de comando (sem `GATEWAY_INTERFACE`/`REQUEST_METHOD`) ele
**percebe que está no console do servidor** e abre as opções de console.

```bash
cd /var/www/html/openclaw/radar
./api.pse                 # menu interativo
./api.pse ajuda           # lista os comandos
```

A lógica de console mora no app (`web/terminal.py`, em `/home/openclaw/bin/radar`),
não no webroot — o webroot só tem a porta de entrada. Usa a mesma camada do app
(`core.governanca`), então não é um caminho paralelo para o banco.

## Comandos

```bash
./api.pse pendentes                 # cadastros nao verificados (a fila)
./api.pse cadastro P-1130           # detalhes de um cadastro (aceita --json)
./api.pse usuarios                  # usuarios do painel
./api.pse senha admin               # define nova senha (pede e confirma, min. 8)
./api.pse resetar-senha admin       # gera temporaria (aparece 1x; troca obrigatoria)
./api.pse tokens                    # tokens de API (so prefixo)
./api.pse bloqueios                 # bloqueios geograficos (--todos inclui inativos)
./api.pse historico P-1130          # historico/auditoria do ponto (--publico)
```

O menu (sem argumentos, num terminal) é um atalho para os mesmos itens.

Exemplo:

```
Radar Brasil — modo console (servidor)
  1) Cadastros pendentes (nao verificados)
  2) Detalhes de um cadastro
  3) Trocar senha de um usuario
  4) Resetar senha (gera temporaria)
  5) Listar usuarios
  6) Tokens de API
  7) Bloqueios geograficos
  8) Historico de um ponto
  0) Sair
Opcao:
```

## Senha — as três portas

1. **Painel web:** em `gestao.html`, botão **Trocar senha** (ou o link no aviso de
   senha temporária). Exige a atual + uma nova de **mínimo 8 caracteres**.
2. **Console (este):** `./api.pse senha <login>` — define a nova senha (não exige a
   atual, pois quem está no servidor já tem acesso ao banco; use com cuidado).
3. **Emergência / não sei a atual:** `radar-admin reset-senha <login>` — gera uma
   temporária e obriga a troca. O `radar-admin` é o CLI fora do painel e também da
   API (usa `core.governanca` direto), para o caso de a única senha admin se perder.

Regras: login web é genérico (`401`, sem revelar se o login existe); nova senha com
menos de 8 caracteres → `senha_fraca`.

## Web continua igual

Nada mudou para quem chama pela web:

```bash
curl -s 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/ajuda'
curl -s 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-23.55&lon=-46.63&raio=1000&formato=json'
```

A detecção é só o ambiente: com `GATEWAY_INTERFACE`/`REQUEST_METHOD` presentes →
CGI; sem eles → console.
