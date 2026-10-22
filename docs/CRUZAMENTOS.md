# Cruzar novamente contribuições com fontes oficiais

Depois de importar uma fonte nova ou atualizá-la, entre no painel de gestão como
moderador ou administrador. Abra **Cruzamentos → Cruzar todos os cadastros ativos**,
ou abra uma contribuição em **Radar → Cruzar com fontes oficiais**. Não precisa
reenviar o cadastro nem desfazer sua verificação manual.

A busca usa as fontes oficiais já importadas no banco local e o raio configurado
em `radar.conf`, seção `governanca`, chave `raio_correspondencia_m`. Não consulta a
internet nem exige IA. Somente registros com cadeia documental de fonte oficial
são candidatos. Fontes sem município, via ou velocidade continuam na comparação;
dados ausentes não são tratados como iguais. Cadastros sem coordenadas são
indicados para revisão manual. Removidos e desabilitados ficam fora da busca.

O resultado informa o cadastro oficial, fonte, distância, rodovia, quilômetro e
divergências de localização cadastral ou velocidade comparável. Proximidade gera
sugestão, inclusive se houver vários candidatos ou conflitos. Não confirma
automaticamente identidade de aparelho, número de série ou certificado Inmetro.
A verificação manual e os campos do cadastro permanecem como estavam.
Se as coordenadas mudarem e o par sair do raio configurado, ou se a fonte
for removida/desabilitada, a sugestão antiga continua no histórico, mas fica
indisponível para confirmação. A distância exibida usa as coordenadas atuais.

Ao conferir as evidências, **Usar cadastro oficial** mantém o ponto oficial no
mapa e retira a contribuição duplicada da consulta pública por remoção lógica;
os registros de origem e o histórico da contribuição permanecem. **Manter
contribuição** conserva o colaborativo e oculta o ponto oficial correspondente,
exigindo justificativa. Recruzar não desfaz nem reabre decisões anteriores.

## API

As operações passam por `web/api.pse` e exigem sessão ou token com escopo
`moderador` ou `admin`:

- `POST /api/v1/gestao/radar/{id}/cruzar`, corpo `{}`: recruza uma contribuição
  ativa, verificada ou não, e retorna `resultado` e `radar` atualizado.
- `POST /api/v1/gestao/cruzamentos`, corpo `{}`: inicia uma passagem pelas
  contribuições ativas, em lotes de até 20. Retorna `resultado.resultados`,
  `processados`, `ate_id` e `proximo_cursor`. Enquanto houver cursor, envie
  `{"cursor": <proximo_cursor>, "ate_id": <ate_id>}`. `limite` opcional aceita
  1 a 20. IDs novos acima do teto ficam para a próxima execução.
- `POST /api/v1/gestao/correspondencias/{id}`: confirma a decisão revisada,
  usando `status` igual a `oficial_vence` ou `colaborativo_vence` e `motivo`.

Cada radar conferido registra o resultado na auditoria existente. O lote faz
chamadas curtas com progresso e permite parar entre chamadas. Se houver falha,
os cadastros já conferidos permanecem salvos; repetir não duplica sugestões.
No esquema legado, a sugestão pendente é armazenada com status `corroborado` e
`resolvido_em` vazio. O painel a exibe como **aguardando revisão**; esse estado
não torna a contribuição oficial. Não há mudança de esquema nem novo cron.

## Validação

`tests/test_cruzamentos.py` cobre fonte importada depois da verificação, fontes
sem cadeia oficial, candidatos ambíguos, divergências, preservação de decisões,
remoção lógica, permissões e paginação. `tests/e2e/gestao.spec.cjs` exercita os
botões reais, o menu, confirmação e falhas da API em Chromium e Firefox no
workflow de navegadores, em desktop e tela estreita.
