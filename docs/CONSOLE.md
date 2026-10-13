# Console (Linux) — comandos prontos da API

Cliente de terminal: **`radar-api`** (instalado em `/home/openclaw/bin/radar-api`).
Ele fala com a API pública do site (`api.pse`) por HTTPS e guarda a sessão num
cookie jar local — **não** acessa o banco (tudo passa pela API, como manda a regra).

- Código-fonte: `tools/radar_api.py` (só biblioteca padrão do Python 3)
- Sessão: `~/.config/radar-api/cookies.txt` (modo 600)
- Token de API: `~/.config/radar-api/token.txt`
- Base: variável `RADAR_API_URL` (default: produção)

```bash
radar-api ajuda            # lista tudo
```

## Sessão

```bash
radar-api login admin            # pede a senha (não aparece na tela)
radar-api login admin --senha '...'   # (opcional; fica no histórico do shell, evite)
radar-api eu                     # quem sou eu (login/papel/escopo)
radar-api senha                  # troca a própria senha (pede atual e nova)
radar-api logout                 # encerra a sessão
```

## Ver cadastros e consultar

```bash
radar-api pendentes                          # fila de colaborativos NÃO verificados
radar-api radar P-1130                       # um ponto por id
radar-api radares --lat -23.55 --lon -46.63 --raio 1000 --limite 50
radar-api radares --uf SP --rodovia BR-116
radar-api historico P-1130                   # histórico/auditoria público
```

## Moderar (moderador+)

```bash
radar-api verificar P-1234 --motivo vistoria
radar-api editar P-1234 --km 12.5 --observacoes 'confirmado no local'
radar-api desabilitar P-1234 --motivo 'em manutenção'      # motivo OBRIGATÓRIO
radar-api remover P-1234 --motivo 'radar inexistente'      # tombstone, nunca apaga a linha
radar-api vinculo 5 --status oficial_vence --motivo 'o ponto oficial é o correto'
```

## Admin — usuários, tokens, bloqueios

```bash
radar-api usuarios
radar-api criar-usuario mod1 --papel moderador            # sem --senha -> temporária (1x)
radar-api editar-usuario 2 --papel admin --ativo 1
radar-api resetar-senha 2                                  # gera temporária (troca obrigatória)

radar-api tokens
radar-api criar-token github:fulano --escopo moderador      # o VALOR aparece 1x
radar-api revogar-token 3

radar-api bloqueios
radar-api bloquear --tipo zona_sombra --lat -23.55 --lon -46.63 --raio 1000 --motivo sabotagem
radar-api desbloquear 7
```

## Autenticar com token de API (em vez do cookie)

```bash
radar-api usar-token rb_xxxxxxxx     # a partir daqui usa o cabeçalho X-Api-Token
radar-api limpar-token               # volta a usar só a sessão
```

## Sem o cliente (curl cru)

```bash
B='https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota='
J=jar.txt

curl -s -c $J -X POST "$B/api/v1/login" -H 'Content-Type: application/json' \
  -d '{"login":"admin","senha":"..."}'

curl -s -b $J -X POST "$B/api/v1/minha-senha" -H 'Content-Type: application/json' \
  -d '{"senha_atual":"...","senha_nova":"aNovaSenha123"}'

curl -s -b $J "$B/api/v1/gestao/pendentes"
```

---

## Perdi/errei a senha — como destravar

1. **Pelo painel:** em `gestao.html`, botão **Trocar senha** (ou o link no aviso de senha
   temporária). Exige a senha atual + uma nova de **mínimo 8 caracteres**.
2. **Pelo terminal:** `radar-api senha` (pede a atual e a nova).
3. **Emergência (sem saber a senha atual), no host:**

   ```bash
   radar-admin reset-senha admin     # imprime uma senha temporária UMA vez (troca obrigatória)
   ```

   Diferente do `radar-api` (que fala pela API), o `radar-admin` roda fora do painel e
   usa o próprio banco — é a saída se a única senha admin se perder.

Regras: login é genérico (`401`, sem revelar se o login existe); token de API **não**
troca senha (só a sessão do painel); nova senha com menos de 8 caracteres → `senha_fraca`.
