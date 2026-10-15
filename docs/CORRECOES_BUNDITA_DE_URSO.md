# Correções BUNDITA DE URSO

As alterações desta revisão estão identificadas no código por comentários no formato solicitado:

`##-- BUNDITA DE URSO #{NUMERO} -- EXPLICACAO DO PROBLEMA ##`

Um mesmo número aparece nos pontos necessários para resolver o mesmo problema. Os testes de regressão principais estão em `tests/test_reconciliacao.py` e `tests/test_regressoes_operacionais.py`.

| Número | Problema e comportamento corrigido |
|---|---|
| 1 | A API ignorava a consolidação. Buscas geográfica/cadastral, detalhes e contagens agora resolvem aliases, preservando fontes, faixas, instalações, verificações e divergências. |
| 2 | Uma decisão confundia ponto com instrumento. `unificar` e `manter_separados` exigem autor, fundamento e escopo explícito: `ponto`, `equipamento` ou `ambos`. |
| 3 | Reversão encadeada deixava associações inconsistentes. A aplicação/reversão reconstrói os vínculos derivados das decisões ativas numa transação, independentemente da ordem, respeitando separações ativas. |
| 4 | Reexecução misturava evidências antigas e configurações diferentes. A regra passa a `dedup-1.1`, sua configuração é imutável, pesos são validados e a fila padrão seleciona a versão vigente. A ferramenta de auditoria trabalha em cópia temporária. |
| 5 | Série isolada recebia nível moderado; mudança de município invalidava aparelhos portáteis. Série isolada fica fraca; corroboração exige posição próxima, via/km com UF compatível ou fabricante/modelo. Repetição municipal não invalida série. |
| 6 | Arquivo compartilhado suprimia pares de faixas diferentes, enquanto hashes diferentes superestimavam independência. Registros distintos do mesmo arquivo podem ser candidatos sem confirmação independente; cópias idênticas do mesmo arquivo são ignoradas. |
| 7 | Texto como “Decrescente (Norte/Sul)” virava crescente. A normalização testa a negação antes da substring. |
| 8 | Proximidade de contribuição anônima verificava e ocultava o oficial; rótulos padrão também simulavam origem oficial. Proximidade só sugere revisão, a evidência deve ser realmente oficial e substituição exige decisão fundamentada de moderação. Erros no filtro não liberam registros ocultos. O painel permite revisar o status histórico `corroborado`. |
| 9 | Exceções eram tratadas como rejeições silenciosas e lotes rejeitados/vazios publicavam sucesso. Erros de dados têm causa registrada; falhas inesperadas abortam; lote inteiramente rejeitado recebe erro; lote vazio não publica; normalização e snapshot compartilham a transação. Tentativas rejeitadas podem ser repetidas. |
| 10 | Encontrar um ponto prometia cobertura completa e snapshot existente prometia cache fresco. A consulta informa cobertura parcial e atualidade desconhecida quando não há medição que a comprove. |
| 11 | Existência de arquivo bastava para `/health/ready`. Agora é necessário conseguir ler o schema inicializado. |
| 12 | `X-Forwarded-For` arbitrário alterava o IP do rate limit. Só proxies explicitamente confiáveis podem encaminhar essa identidade. |
| 13 | O CLI ANTT podia baixar a página do catálogo como dados. Sem arquivo/URL explícitos, usa o resolvedor do recurso mensal. |
| 14 | Grade em graus perdia vizinhos e mesma rodovia gerava comparação quadrática de toda a via. O índice usa células cartesianas na esfera e blocos de UF/via/km. O filtro final continua sendo Haversine. |
| 15 | Filtro de fiscalização pontual era aplicado depois da paginação. Agora entra antes dos totais/cursor; o total de equipamentos considera todo o resultado, sem contar a mesma identidade física duas vezes. |
| 16 | Coleta sem mudança acumulava backoff de erro. `sem_mudanca` respeita o intervalo normal. |
| 17 | Vínculos derivados e campos mutáveis contaminavam novas comparações e o fallback de UF. A comparação usa entidades originais, com precedência das observações/payload de origem; a UF não vem de vínculos derivados. |
| 18 | NaN e infinito podiam quebrar o índice geográfico. Não são aceitos como números para comparação ou raio. |
| 19 | IDs de submissões anônimas compartilhavam o espaço da ingestão autenticada e permitiam sobrescrever cadastros. A origem pública é separada e os IDs enviados por anônimos não autorizam upsert. |
| 20 | A projeção canônica podia ocultar GPS válido quando o canônico não tinha GPS ou publicava outra posição/UF/via/situação. As marcações divergentes mantêm seus IDs e coordenadas originais, com identificação do ponto canônico. Ausência de informação não é contradição. A auditoria agora verifica inventário e conservação das coordenadas. |
| 21 | A junção de regimes pontual e permanente podia retirar um ponto do filtro de fiscalização permanente. O ponto satisfaz ambos os filtros e o booleano fica indeterminado quando as modalidades são mistas. |
| 22 | O normalizador atual recupera quatro coordenadas ASTT que continuavam ausentes nos cadastros legados. A ferramenta `recuperar_posicoes_legadas.py` reinterpreta o bruto com esse parser, recusa divergências e só escreve em uma nova cópia, preservando IDs, dados originais e GPS existentes. |
| 23 | O mapa carregava só a primeira página, deixando pontos do raio fora da tela. Agora percorre os cursores, acumula as marcações e cancela consultas substituídas. Erros mantêm a consulta identificada como incompleta; respostas antigas não substituem a nova. |
| 24 | Na PRF, `ESTADO=ATIVO/INOPERANTE` encobria a UF real. A comparação valida siglas/nomes de UF, prioriza a observação original sobre o ponto mutável e não calcula distâncias com coordenadas fora da faixa. |
| 25 | Observações históricas equivalentes do mesmo cadastro multiplicavam pares. A geração usa um representante estável por origem, entidades e atributos, mantendo todos os registros equivalentes na evidência. Observações divergentes e faixas distintas permanecem separadas. |
| 26 | A fila misturava identidade de ponto/instrumento e tratava contraditórios como propostas de unificação. `dedup-1.2` avalia cada escopo, separa diagnóstico de revisão e aplica os bloqueadores do escopo escolhido. A fila omite trabalho já resolvido por decisões transitivas e pode ser salva numa cópia para revisão por CLI. |

## Decisões e compatibilidade

O schema SQL não foi alterado. O escopo, as entidades de origem e o marco de aplicação ficam nos metadados auditáveis de `DECISAO_DUPLICIDADE`. Os dados originais e IDs continuam armazenados; a visão pública resolve os aliases sem excluir entidades.

Exemplo da API Python existente:

```python
from core import dedup

decisao_id = dedup.decidir(
    conn, candidato_id, "unificar", usuario="revisor",
    motivo="Documentos confirmam o mesmo instrumento",
    escopo="equipamento",
)
dedup.aplicar(conn, candidato_id, usuario="revisor")
dedup.reverter_decisao(conn, decisao_id, usuario="revisor", motivo="Reabrir análise")
```

Esse exemplo associa o instrumento e preserva os pontos. Use `escopo="ponto"` para confirmar um local, e `"ambos"` somente quando as duas identidades estiverem confirmadas. Cada registro precisa ter uma entidade original inequívoca no escopo escolhido. Casos ambíguos continuam exigindo investigação; não se escolhe um ID arbitrariamente.

Uma nova decisão sobre o mesmo candidato exige reverter a anterior. Decisões legadas sem escopo mantêm a interpretação histórica de associação de ponto e equipamento; um banco com histórico legado deve ser auditado antes da atualização, especialmente se houver várias decisões não revertidas sobre o mesmo candidato.

A reversão preserva o histórico e reconstrói a visão das demais decisões. O ID canônico prefere evidência oficial e depois o menor ID do grupo. Um ID antigo continua consultável enquanto a associação estiver ativa. Quando posição e atributos são equivalentes, resolve o alias canônico. Quando uma observação publica outra posição, UF, via ou situação, mantém sua marcação e seu ID, com `ponto_canonico_id` indicando a identidade compartilhada. A consulta por raio e o detalhe preservam essa coordenada; não se desloca nem se oculta uma posição publicada apenas para escolher um ID canônico.

## Regra e fila

A versão vigente é `dedup-1.2`. As versões 1.0 e 1.1 permanecem consultáveis no histórico e não podem ser geradas com a política nova. Alterar pesos, raio ou políticas requer outro identificador de versão, em vez de reutilizar uma regra registrada. A [medição real da correção da fila](AJUSTE_FILA_DEDUP_1_2_2026-10-15.md) descreve os resultados.

`dedup.candidatos(conn)` mostra a geração vigente e omite pendências de diagnóstico. Para uma fila operacional, use `estado="pendente"`; para separar as perguntas, use `escopo="ponto"`, `"equipamento"` ou `"ambos"`. Evidências fracas e contraditórias continuam armazenadas:

```python
dedup.candidatos(conn, estado="pendente", escopo="equipamento")
dedup.candidatos(conn, incluir_diagnosticos=True)
dedup.candidatos(conn, regra=None, incluir_diagnosticos=True)  # todas as versões
```

`incluir_fracos=True` permanece como alias do diagnóstico completo. Os limiares permanecem 0,20 para a pontuação de entrada (bloqueadores também são registrados), 0,30 para moderado e 0,75 para forte, sujeitos às exigências de evidência. A regra calcula níveis por escopo: série isolada não promove instrumento, e coordenada sozinha não vira evidência forte. O nível global resume o melhor escopo sugerido, com todos os conflitos preservados em `avaliacao_escopos`. Nenhum nível provoca fusão automática.

Série curta é uma pista insuficiente para identidade global, não prova de aparelhos diferentes. Série legítima sem GPS pode receber corroboração documental; não se exige posição em todos os casos. UF/via/km apenas encaminha revisão, sem dispensar análise de trecho, sentido, período e documentos.

## Comparar sem alterar o banco informado

Na raiz do checkout:

```bash
/usr/bin/python3 tools/auditar_deduplicacao.py --db /caminho/para/radar.sqlite3
```

A ferramenta abre a origem em modo somente leitura, faz backup consistente em diretório temporário, gera candidatos na cópia e retorna contagens antes/depois por regra, estado e nível. Não aplica decisões, não substitui o banco original e remove a cópia ao terminar. A seção `conservacao` compara contagens e hashes dos registros originais e identifica marcações não representadas pela projeção da consulta. Falha nessa conservação faz o CLI terminar com código diferente de zero. Exclusões explícitas de aliases equivalentes são contadas separadamente.

A ferramenta foi exercitada com fixtures e, posteriormente, com o backup real dos 5.575 candidatos publicado no repositório. Os resultados estão em [AUDITORIA_BASE_REAL_2026-10-15.md](AUDITORIA_BASE_REAL_2026-10-15.md). A geração ocorreu em cópia temporária; nenhuma decisão foi aplicada no original.

## Governança e ingestão

Uma sugestão automática continua usando o status histórico `corroborado` no armazenamento, por compatibilidade. O painel apresenta “aguardando revisão”. Ela não marca o cadastro como verificado nem oculta o ponto oficial. `colaborativo_vence` exige motivo, data de resolução e verificação pelo moderador.

A resposta de submissão mantém `corroborados` e `corroborados_ids` sem promover envios automaticamente. Os novos campos `correspondencias_sugeridas` e `correspondencias_sugeridas_ids` informam sugestões.

Contribuições públicas pertencem à fonte `Contribuicoes publicas do Bunda de Urso`, com natureza comunitária. A base autenticada mantém sua fonte e seus identificadores próprios. Não há migração silenciosa de registros legados: contribuições verificadas automaticamente pela versão antiga continuam exigindo auditoria de seu histórico.

Para proxy reverso, configure opcionalmente `RADAR_TRUSTED_PROXIES` com IPs/CIDRs separados por vírgula. Sem essa configuração, o rate limit usa `REMOTE_ADDR`. A cadeia encaminhada é lida da direita para a esquerda, até o primeiro salto não confiável.

Rejeições de dados ficam em `ERRO_VALIDACAO` e `REGISTRO_FONTE.status_validacao`. Uma falha inesperada gera execução com erro e rollback. Um lote vazio recebe `sem_dados`, sem declarar atualização do último snapshot válido. O CLI devolve código diferente de zero para lote inteiramente rejeitado.

## Verificação

As regressões cobrem consolidação nos resultados, preservação de faixas/fontes/instalações, escopos separados, reversões encadeadas, ordem de aplicação, idempotência, rollback, separações transitivas, configurações imutáveis, contexto de séries, busca espacial contra comparação exaustiva, escrita pública isolada, precedência oficial, quota por IP, falhas de coleta, lotes vazios, prontidão e paginação.

A revisão também executa a suíte completa e os verificadores do CI. Testes com fixtures não homologam fontes governamentais atuais, cobertura nacional, desempenho na base de produção ou execução PostgreSQL.


## Auditoria específica de conservação de marcações

A comparação offline usou o código original do commit `1705dc93517c8ae10d5e9f7e8833226c322a27de` e o código corrigido. Nos **39 cenários de coleta**, os dois produziram os mesmos inventários de registros, pontos e trechos, as mesmas rejeições e as mesmas **431 ocorrências de coordenadas**, preservando também coordenadas repetidas. São fixtures de regressão, não uma medição de cobertura nacional.

A referência independente está em `tests/fixtures/conservacao_fontes.json`. O teste `tests/test_conservacao_fontes.py` exige essas contagens e coordenadas e verifica que cada localização da referência é encontrada numa consulta por raio de um metro, incluindo dados inativos para verificar também sua conservação.

Os testes de `tests/test_conservacao_marcacoes.py` reproduziram falhas da primeira correção e passaram após o ajuste: canônico sem GPS; coordenadas divergentes; detalhe do alias; filtros por UF, rodovia e situação; coordenada inferida; paginação; fila fraca; remoções explícitas; modalidades mistas. Uma varredura determinística verifica **120 consultas antes/depois** de unificações e reversões em posições diferentes.

Essa verificação é adicional à conservação física dos registros. Preservar uma linha no banco não basta se a coordenada desaparecer da consulta do mapa. Por isso a seleção só troca uma marcação por uma representação equivalente; divergências permanecem visíveis, com sua proveniência.

Para repetir:

```bash
/usr/bin/python3 -m unittest tests.test_conservacao_fontes tests.test_conservacao_marcacoes
/usr/bin/python3 tools/auditar_deduplicacao.py --db /caminho/para/radar.sqlite3
```

O backup real de 15/10/2026 foi disponibilizado depois dessa primeira verificação. A [auditoria específica](AUDITORIA_BASE_REAL_2026-10-15.md) confirmou a conservação de todas as 7.463 marcações com GPS elegíveis, identificou quatro posições legadas recuperáveis e corrigiu o carregamento incompleto das páginas no mapa.
