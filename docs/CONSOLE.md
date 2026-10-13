# Console — comandos prontos da API

Duas formas de falar com a API sem abrir o painel: **console do navegador** (helper `rb`)
e **curl no shell**. A sessão usa o cookie do painel (`credenciais:'same-origin'`); a
senha **nunca** fica em arquivo. A rota vai no parâmetro `rota` do `api.pse`.

---

## 1. Console do navegador (helper `rb`)

Abra qualquer página do radar, ex.: `https://servidor3.lucas.inf.br/openclaw/radar/gestao.html`,
abra o console (F12 → Console) e carregue o helper:

```js
await import('/openclaw/radar/console.js')
```

Pronto. Agora `rb.*` funciona. (Alternativa: `fetch('console.js').then(r=>r.text()).then(eval)`.)

### Sessão

```js
rb.login('admin', 'sua-senha')        // entra (define o cookie de sessão)
rb.eu()                               // {autenticado, escopo, rotulo} — quem sou eu
rb.senha('atual', 'aNovaSenha123')    // TROCA a própria senha (mín. 8 caracteres)
rb.logout()                           // sai
```

### Ver cadastros / consulta

```js
rb.pendentes()                        // fila de colaborativos NÃO verificados (o que você pediu "ver cadastros")
rb.gestaoRadar('P-54922')             // um radar por id, visão de gestão
rb.radares({lat:-23.55, lon:-46.63, raio:1000, limite:50})   // consulta por raio (pública)
rb.radar('P-1130')                    // um ponto por id (público)
rb.historico('P-54922')               // histórico/auditoria público
rb.busca({uf:'SP', rodovia:'BR-116'}) // busca cadastral (sem coordenada)
rb.fontes(); rb.status()              // fontes e estado da base
```

### Moderar (moderador+)

```js
rb.verificar('P-54922', 'vistoria')
rb.editar('P-54922', {observacoes:'confirmado no local', km:12.5})
rb.desabilitar('P-54922', 'em manutenção')   // motivo obrigatório
rb.remover('P-54922', 'radar inexistente')   // tombstone, motivo obrigatório (nunca apaga a linha)
rb.vinculo(5, 'oficial_vence', 'o ponto oficial é o correto')  // ou 'colaborativo_vence'
```

### Admin — bloqueios, tokens, usuários

```js
rb.bloqueios()
rb.bloquear({tipo:'zona_sombra', latitude:-23.55, longitude:-46.63, raio_metros:1000, motivo:'sabotagem'})
rb.desbloquear(7)

rb.tokens()
rb.criarToken('github:fulano', 'moderador')   // o VALOR do token aparece UMA vez
rb.revogarToken(3)

rb.usuarios()
rb.criarUsuario({login:'mod1', papel:'moderador'})          // sem senha -> temporária devolvida uma vez
rb.editarUsuario(2, {papel:'admin', ativo:true})
rb.resetarSenha(2)                                          // gera temporária (deve_trocar_senha=1)
```

### Token de API em vez de cookie

```js
rb.usarToken('rb_xxxxxxxx')   // a partir daqui os pedidos usam X-Api-Token
```

### Depurar

```js
rb._url('/api/v1/gestao/pendentes')   // a URL crua que seria chamada
rb._log()                             // últimos pedidos (rota + status)
```

---

## 2. Shell (curl)

```bash
B='https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota='
J=jar.txt

# login (guarda o cookie)
curl -s -c $J -X POST "$B/api/v1/login" -H 'Content-Type: application/json' \
  -d '{"login":"admin","senha":"..."}'

# trocar a própria senha
curl -s -b $J -X POST "$B/api/v1/minha-senha" -H 'Content-Type: application/json' \
  -d '{"senha_atual":"...","senha_nova":"aNovaSenha123"}'

# fila de cadastros não verificados
curl -s -b $J "$B/api/v1/gestao/pendentes"

# verificar / remover um radar
curl -s -b $J -X POST "$B/api/v1/gestao/radar/P-54922/verificar" \
  -H 'Content-Type: application/json' -d '{"motivo":"vistoria"}'
curl -s -b $J -X POST "$B/api/v1/gestao/radar/P-54922/remover" \
  -H 'Content-Type: application/json' -d '{"motivo":"radar inexistente"}'
```

Com token de API troque `-b $J` por `-H "X-Api-Token: rb_..."`.

---

## 3. Perdi/errei a senha — como destravar

1. **Pelo painel:** em `gestao.html`, botão **Trocar senha** (ou o link no aviso de senha temporária).
   Exige a senha atual + uma nova de **mínimo 8 caracteres**.
2. **Pelo console:** `rb.senha('senha-atual', 'novaSenha123')`.
3. **Emergência (sem saber a senha atual), no host:**

   ```bash
   radar-admin reset-senha admin     # imprime uma senha temporária UMA vez (troca obrigatória)
   ```

   O `radar-admin` roda fora do painel de propósito: é a saída se a única senha admin se perder.

Regras: login é genérico (`401`, sem revelar se o login existe); token de API **não** troca
senha (só sessão do painel); nova senha com menos de 8 caracteres → `senha_fraca`.
