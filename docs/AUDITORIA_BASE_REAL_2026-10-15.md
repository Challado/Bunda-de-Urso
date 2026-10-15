# Auditoria do backup real — 15/10/2026

O arquivo auditado foi `base de dados/radar-2026-10-15_144017.sqlite3.gz`, publicado no commit `34dc34e`, snapshot `rb-20261015T173731602108Z`. O horário do nome é de Brasília. Os resultados estruturados estão em [AUDITORIA_BASE_REAL_2026-10-15.json](AUDITORIA_BASE_REAL_2026-10-15.json).

O arquivo compactado foi preservado. O SQLite descompactado foi aberto somente para leitura; geração de candidatos, simulações de decisão e recuperação usaram cópias separadas. O SHA-256 do SQLite original permaneceu `93d0245193cc4e87d62e5e5f6a23ab8dcbd8d415626ee2cf59f4dafd128fca6b`.

## Conservação dos cadastros e marcações

| Medida no backup | Resultado |
|---|---:|
| Pontos de fiscalização | 50.200 |
| Registros de fonte | 56.921 |
| Equipamentos | 50.200 |
| Pontos com GPS armazenado | 7.464 |
| Pontos sem GPS armazenado | 42.736 |
| Marcações com GPS elegíveis para consulta | 7.463 |
| Cadastros elegíveis, incluindo os sem GPS | 50.199 |
| Decisões de duplicidade no original | 0 |
| Marcações elegíveis perdidas na consulta integral | 0 |
| Coordenadas alteradas na consulta integral | 0 |

`integrity_check` retornou `ok`; `foreign_key_check` não encontrou violações. A geração da regra nova preservou as contagens e os hashes de nove tabelas de dados originais, incluindo todas as verificações metrológicas.

O ponto `P-54922` já estava removido no backup, com o motivo “teste de validacao - remover”. Ele explica a diferença entre os 7.464 pontos com GPS armazenado e as 7.463 marcações públicas. Não foi removido nesta revisão.

A consulta integral do backend devolveu as 7.463 marcações elegíveis com as coordenadas originais. Foram feitas também 87 consultas pela API, alternando raios de 1 m e 50 m, com amostras nas 27 UFs e nas fontes com GPS. Os resultados foram comparados com distância esférica calculada diretamente sobre as coordenadas do banco. Três páginas pequenas adicionais devolveram exatamente os sete pontos esperados, sem repetição ou omissão.

Quatro casos reais foram usados em simulações separadas de decidir/aplicar/reverter: mesma posição, posições divergentes, apenas um lado com GPS e ambos sem GPS. Cada ciclo preservou o inventário original, conservou as coordenadas consultáveis, restaurou os vínculos e voltou o candidato a pendente. O histórico dessas simulações ficou somente na cópia de teste.

## Duas correções adicionais

### Problema 22: quatro posições legadas recuperáveis

O parser atual da ASTT Araguaína já entende os formatos malformados publicados pela fonte, mas quatro cadastros do backup continuavam sem posição. Atualizar o parser não reprocessa automaticamente um registro bruto que não mudou.

| Ponto | Registro original | Latitude recuperada | Longitude recuperada |
|---|---|---:|---:|
| P-47770 | 51519 | -7.158138 | -48.192593 |
| P-47803 | 51552 | -7.199534 | -48.218441 |
| P-47804 | 51553 | -7.198739 | -48.217981 |
| P-47805 | 51554 | -7.163786 | -48.191700 |

A ferramenta nova reaplica apenas esse parser à sua fonte, usando os vínculos originais. Ela não substitui posições existentes, não recupera pontos ocultos pela governança e não escolhe uma posição quando observações válidas discordam. Sem `--saida`, apenas lista o plano. Com `--saida`, cria um novo SQLite e recusa sobrescrever arquivos existentes.

Na cópia testada, entraram quatro posições e os quatro vínculos antes vazios. IDs, payloads, posições anteriores e demais dados permaneceram iguais. Todas as quatro marcações foram encontradas em consultas de 1 m. A segunda execução não encontrou mais recuperações pendentes. A quantidade de marcações elegíveis passou de **7.463 para 7.467** nessa cópia.

Existe ainda um ponto PRF, `P-45423`, cujo bruto publica longitude `-48676127`, fora da faixa válida. Ele aparece em três registros históricos. Não aplicamos a ele a convenção decimal específica da ASTT: sua correção depende de evidência da própria fonte.

### Problema 23: o mapa ignorava as páginas seguintes

Uma consulta real com centro `-23.55,-46.63` e raio de 200 km tinha **724 pontos**. O mapa fazia uma única requisição, sem definir limite, e recebia os **100 primeiros**. O aviso para reduzir o raio não carregava as outras 624 marcações.

O mapa agora solicita páginas de até 1.000 pontos, segue todos os cursores e atualiza a exibição durante o carregamento. Uma consulta substituída é cancelada e sua resposta atrasada não sobrescreve a nova. Falhas de páginas posteriores não disparam a apresentação de consulta concluída ou de ausência de radares. Cursores repetidos encerram com erro explícito.

Os testes executam o JavaScript real da página em sete cenários, incluindo 2.005 marcações em três páginas, duplicação de IDs, cursor repetido, erro HTTP, cancelamento, respostas fora de ordem e falha depois da primeira página.

Além desses cenários, o paginador JavaScript foi ligado à API local lendo o backup real: no raio de 500 km em torno do mesmo centro, carregou **2.685 marcações em três páginas**. Todos os IDs e coordenadas coincidiram com o cálculo independente sobre o banco, sem omissões. A prova exercita o JavaScript e o handler da API, sem renderização visual de navegador.

## A fila nova não encolheu

**Atualização posterior:** a causa foi corrigida em `dedup-1.2`; veja [AJUSTE_FILA_DEDUP_1_2_2026-10-15.md](AJUSTE_FILA_DEDUP_1_2_2026-10-15.md). Os números desta seção registram o diagnóstico anterior.

A previsão anterior de redução da fila não se confirmou neste backup.

| Resultado | dedup-1.0 armazenada | dedup-1.1 gerada na cópia |
|---|---:|---:|
| Candidatos totais | 5.575 | 48.067 |
| Moderados | 4.157 | 8.160 |
| Fracos | 1.418 | 14.522 |
| Contraditórios | 0 | 25.385 |
| Fortes | 0 | 0 |

Os números da coluna antiga são os níveis **persistidos neste backup**, não uma recomputação do relato anterior. A fila padrão da regra nova omite fracos, mas inclui contraditórios: fica com 33.545 pendências.

Dos 48.067 pares novos, 36.148 comparam registros da mesma fonte; 11.919 cruzam fontes diferentes. Dos 8.160 moderados, 5.220 são da mesma fonte e 2.940 cruzam fontes. PRF e Belo Horizonte concentram grande parte dos contraditórios. Os principais bloqueadores são sentidos opostos e séries diferentes; um par pode ter mais de um bloqueador.

Dos 5.575 pares antigos, 1.030 reaparecem como moderados, 3.194 como fracos e 108 como contraditórios. Outros 1.243 não são regenerados pelos critérios atuais. Os candidatos antigos continuam preservados no histórico.

Permitir comparações dentro da mesma fonte recupera casos legítimos de faixas e observações históricas, mas amplia muito o trabalho de revisão. **Esta medição não homologa a fila como limpa nem autoriza fusões.** A próxima melhoria deve distinguir a revisão de ponto da revisão de instrumento e organizar contraditórios e repetições históricas. Nada disso deve remover marcações publicadas apenas por pontuação baixa ou número de série genérico.

## Reproduzir

Na raiz do projeto, descompacte o backup para um diretório de trabalho:

```bash
gzip -dc 'base de dados/radar-2026-10-15_144017.sqlite3.gz' > /tmp/radar-auditoria.sqlite3
/usr/bin/python3 tools/auditar_deduplicacao.py --db /tmp/radar-auditoria.sqlite3
RADAR_DB=/tmp/radar-auditoria.sqlite3 /usr/bin/python3 .github/scripts/rodar_suite.py
/usr/bin/python3 tools/recuperar_posicoes_legadas.py --db /tmp/radar-auditoria.sqlite3
/usr/bin/python3 tools/recuperar_posicoes_legadas.py --db /tmp/radar-auditoria.sqlite3 --saida /tmp/radar-recuperado.sqlite3
node tests/test_paginacao_mapa.js
```

Os comandos de redirecionamento pressupõem nomes de trabalho ainda não usados. A recuperação recusa substituir o arquivo de origem ou um destino existente. Nenhum comando nesta auditoria substituiu o banco em produção.

## Limites

A suíte final executou **681 testes, sem falhas, erros ou testes pulados**, incluindo a medição de cobertura da base real e as novas regressões. Os sete cenários JavaScript são executados por um desses testes quando Node está disponível.

O backup não inclui o arquivo externo de âncoras rodoviárias usado pelo referenciamento linear em produção. A conservação integral desta auditoria mede o GPS armazenado; não homologa posições que dependem desse arquivo externo.

A ausência de GPS em 42.736 cadastros precede as mudanças: 40.248 são registros do INMETRO. Esses cadastros permanecem pesquisáveis, mas a validação não permite colocá-los no mapa sem localização sustentada pela fonte. Quatro casos ASTT foram recuperados na cópia, conforme descrito acima.

A montagem integral de 7.463 registros levou cerca de 94 segundos neste ambiente. Isso indica custo elevado para consultas e exportações extensas; os testes de conservação não equivalem a uma homologação de desempenho. A cobertura geográfica das fontes e a existência física de cada radar também não são comprovadas apenas pela integridade do banco.
