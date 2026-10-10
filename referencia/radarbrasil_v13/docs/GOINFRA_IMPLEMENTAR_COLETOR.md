# Integração GOINFRA — contrato detalhado de implementação e aceitação

**PENDENTE: não há coletor GOINFRA homologado neste pacote.** O registro da fonte no catálogo
é indicação para implementação, NÃO um download funcional. A outra IA deve executar todos
os passos abaixo e produzir logs de evidência, sem fingir que o relatório foi processado.

## Fontes institucionais

- Relatório de equipamentos de monitoramento: https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/
- Estudos técnicos por rodovia: https://goias.gov.br/goinfra/operacao-rodoviaria/estudos-tecnicos-2/
- Versão conhecida do relatório de ativos de 02/10/2026 (PDF): https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/10/Lista_de_Equipamento_02_10_2026.xlsx-Equipamentos-Ativos.pdf

A URL pontual do PDF serve para teste de referência; **não** deve ficar fixada como
única fonte porque haverá versões novas. Descobrir o link mais atual na página e conferir
a data de emissão dentro do arquivo. Registrar bytes, URL final, ETag/Last-Modified,
SHA256, timestamp de coleta, total de páginas/linhas e a periodicidade de publicação.

## Campos a conferir um por um no cabeçalho real

A tabela oficial pode listar código do equipamento, tipo, rodovia, km (com formato
`469+594`, que significa km 469,594), faixa, sentido, número de série, município,
código rodoviário SRE, coordenadas, velocidade em km/h, data de autorização,
ativação, vencimento da aferição, lote, nota de instalação, número de documento SEI
e estudo técnico. **Não presumir que toda versão possui todas essas colunas**.
Confrontar a versão atual com o cabeçalho e criar mapeamento explícito de cada
nome, célula e unidade antes de importar.

- `rodovia` => via normalizada GO-XXX; salvar texto original.
- `km` => decimal em quilômetros, converter `469+594` para 469.594 somente quando
  fonte comprovar notação km+metros. Preservar a string `km_original`.
- `latitude`, `longitude` => WGS84 NUMERIC, podendo ser inteiros em microsgraus
  (1e-6) NESTA publicação; por exemplo, -16012001 => -16.012001. Confirmar a
  regra na fonte, não aplicar a outros órgãos. Coordenadas incompatíveis com UF,
  via/quilômetro ou distantes das demais no ponto devem ir para quarentena.
- `velocidade` => limite regulamentado **se o título do campo assim indicar**;
  caso o arquivo seja de passagens/tráfego, nunca preencher limite da via.
- `codigo_equipamento`, `numero_serie`, `sentido`, `faixa` => IDENTIDADES DIFERENTES;
  não transformar linha por faixa em equipamento distinto nem fundir números
  de série diferentes apenas por proximidade.
- `afericao_valida_ate` => validade metrológica publicada; não prova em tempo
  real que o radar opera. Salvar data e fonte originais.
- `operacao_inicio` e `operacao_fim` => preencher somente se publicação indicar
  operação específica. Não confundir ativação com início de fiscalização pontual.

## Fluxo para implementar

1. Adicionar conector `GOINFRA` a `radarbrasil/sources.py` ou módulo novo seguindo
   interface do coletor. Usar SOMENTE Downloader compartilhado, limites e log de erros.
2. Descobrir PDF/XLSX do mês mais atual na página oficial sem inventar endereços.
3. Extrair tabela verificando bordas, linhas que quebram de página, cabeçalhos
   repetidos, colunas multivalor, número de série e faixa; inspecionar o PDF
   VISUALMENTE e testar pelo menos 10 registros contra texto e imagem.
4. Normalizar no fluxo de staging com validação; capturar bytes e metadados
   originais; não substituir snapshot anterior em erro, PDF vazio ou queda
   anormal de quantidade.
5. Comparar IDs de equipamentos e números de série por data; um equipamento
   substituído no mesmo ponto gera histórico, não fusão entre instrumentos.
6. Registrar decisões de deduplicação; avaliar a inconsistência publicada na
   GO-174 km 254+524 com longitudes muito distintas, sem copiar cegamente.
7. Indexar latitude/longitude numéricas, sem PostGIS ou funções espaciais SQL.
8. Ligar o conector somente após download real, conversão auditada e testes
   completos da API. A cobertura é POR VIAS/ÁREAS INCLUÍDAS, não todo GO.

## Teste de regressão obrigatório — cinco POIs (Waze)

| POI | Latitude | Longitude | Correspondência oficial a investigar | Proximidade relatada anteriormente |
|---|---:|---:|---|---:|
| 1 | -17.625377 | -51.060863 | GO-174 / 174L5R129 | 89 m |
| 2 | -17.584521 | -51.089497 | GO-174 / 174L5R127 | 87 m |
| 3 | -17.529214 | -51.111256 | GO-174 / 174L5R125 | 67 m |
| 4 | -16.459361 | -51.671518 | GO-060 / 060L5R091 | 83 m |
| 5 | -16.385100 | -51.564215 | GO-060 / 060L5B058 | 43 m |

Os vínculos POI/equipamento acima foram levantados em consulta anterior, NÃO
foram revalidados neste pacote pela execução do coletor. Usar como hipóteses de
teste, não como correspondências confirmadas automaticamente. Distância haversine
não garante identidade; conferir sentido, faixa, série, km e data.

**Critérios para considerar CONCLUÍDO:** baixar versão atual, extrair sem perder
campos/linhas, gerar relatório de rejeições e duplicidades, confrontar amostra
com original, consultar via GET/POST com raios 100/1.000/5.000 metros e confirmar
status de cobertura por rodovia/trecho, logs e fallback de cache. Testar também
HTTP 429/503, PDF inválido, planilha vazia, quebra de layout e coordenada fora
facilmente detectável. Sem acesso ao dado real, manter estado PENDENTE.
