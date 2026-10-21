# Normalização relacional e identidade dos equipamentos

A exigência é 1FN, 2FN e 3FN, conforme a seção 3 da especificação. Separar
arquivos ou criar FKs não demonstra, por si só, essas formas normais. Esta
revisão corrige dependências redundantes identificadas no núcleo da coleta e
corrige, separadamente, a resolução de identidade na escrita.

## Dependências corrigidas

| Relação | Dependência e problema anterior | Representação atual |
|---|---|---|
| Snapshot | `artefato_id → recurso_id`; repetir o recurso na associação permitia contradições | `SNAPSHOT_RECURSO(snapshot_id, artefato_id)`, chave composta; recurso por JOIN com o artefato |
| Execução | Quando havia artefato, seu recurso era repetido junto ao recurso da tentativa | `EXECUCAO_COLETA` registra a tentativa e o recurso solicitado; `EXECUCAO_ARTEFATO(execucao_id PK/FK, artefato_id FK)` registra o resultado opcional |
| Cobertura municipal | `municipio_id → uf_sigla`; a cobertura armazenava os dois | Guarda o município; obtém a UF por JOIN. Cobertura estadual continua guardando sua UF |

`SNAPSHOT_RECURSO_DETALHE`, `EXECUCAO_COLETA_DETALHE` e
`COBERTURA_FONTE_DETALHE` são **views**, sem cópia persistida dos campos derivados.
Usam LEFT JOIN para preservar relações sem complemento. A API mantém seus campos
públicos; clientes SQL internos devem usar as views para os campos derivados.

A restrição de um artefato por recurso em cada snapshot continua valendo. O banco
também recusa associar a uma execução um artefato de outro recurso, mudar o recurso
da execução para contradizer seu artefato e mudar a origem de um artefato. As
restrições existem na DDL e nas migrações, além da validação do coletor.

## Chaves e separação de responsabilidades

- Catálogos: `id` e `codigo` único; nomes e descrições ficam no catálogo.
  Municípios referenciam UF, modelos referenciam fabricante e instalações
  referenciam equipamento e ponto. Os textos dessas entidades não são copiados
  para substituir suas FKs.
- Associações N:N: chaves compostas dos participantes; cada coleção de faixas,
  documentos, municípios, licenças e equipamentos tem sua própria relação.
- Entidades temporais: datas e situação pertencem ao evento, instalação ou
  observação correspondente. A identidade do aparelho não depende da instalação.
- Proveniência: `REGISTRO_FONTE` preserva o original e os vínculos identificam
  as entidades observadas. Uma divergência publicada não é um atributo global
  que possa sobrescrever indiscriminadamente as outras fontes.
- Operações: local publicado da operação e referência a um ponto/trecho são
  informações com papéis próprios. Não se presume que toda operação herde
  automaticamente todos os atributos da instalação cadastrada.
- Brutos JSON e textos originais permanecem na ingestão para auditoria,
  conforme a seção 3.7. Não substituem as tabelas canônicas; listas da resposta
  HTTP são montadas a partir de relações, não gravadas como coleções canônicas.

Uma sequência de números de série repetidos, por si só, não comprova violação da
3FN: é também necessário resolver corretamente a identidade das entidades.
Não se declara `UNIQUE(numero_serie)` global, pois há séries ausentes, genéricas,
reutilizadas por fabricantes diferentes e conflitos entre publicações.

## Identidade na escrita

O importador não restringe mais a busca de equipamento ao ponto atual. Reuso
entre publicações exige natureza oficial, tipo conhecido, série exata (apenas
caixa e espaços externos são desconsiderados), ausência de conflitos de modelo,
fabricante e ano, e evidência adicional:

1. fabricante conhecido coincidente; ou
2. município, rodovia e marco quilométrico coincidentes, explicitamente publicados.

Número de série sozinho, município sozinho e distância não bastam. Mais de um
candidato elegível impede a escolha automática. Cadastros públicos continuam
separados dos oficiais e sujeitos à revisão. Identificadores ambíguos no lote
não autorizam o reuso entre pontos. Fabricante/modelo conflitantes no mesmo
ponto também não são encobertos pela idempotência.

O Inmetro passa a mapear rodovia/km de `LocalVerificacao` quando há uma única
rodovia e um único marco com metros explícitos, como `GO060 KM249+100M` ou
`BR 364 KM 123,830`. Texto incompleto, intervalo ou referência múltipla continua
sem esse mapeamento. Não se cria GPS a partir desse texto.

A busca de modelos com fabricante nulo usa comparação correta com NULL;
reprocessar o mesmo modelo incompleto não cria outra linha a cada importação.
A carga metrológica mantém origem e conteúdo na chave de idempotência, para
não descartar divergências entre publicações do equipamento compartilhado.

## Migração e atualização

O instalador aplica as migrações 0004–0006 pela API e executa a reconciliação dos
equipamentos com backup. Não exige apagar a base ou baixar tudo novamente.
SQLite **3.35+** é necessário; o instalador confere isso antes de alterar a
instalação. As duas DDLs são geradas juntas; a execução PostgreSQL ainda requer
homologação própria, como o restante do projeto.

A reconciliação exige compatibilidade entre **todos** os membros do grupo.
Casos ambíguos, natureza não oficial, atributos conflitantes, registros
compartilhados que causariam perda de metadados e qualquer decisão humana
anterior são mantidos para revisão. O relatório informa grupos pendentes e
quantos cadastros foram reconciliados; isso não significa erro de instalação.

Para os casos comprovados, move FKs de instalações, verificações, identificadores,
documentos, operações e observações para um equipamento comum. Não elimina
publicações, pontos, instalações ou verificações. `EQUIPAMENTO_ALIAS` preserva
os IDs públicos antigos como rótulos históricos que resolvem para a entidade
atual; eles não representam outros equipamentos ativos.

Em bases anteriores, o marco do Inmetro pode ainda estar somente no bruto. A
reconciliação lê essa evidência sem reescrever o ponto e sem inventar coordenadas.
As duas fontes aparecem no detalhe pelo equipamento compartilhado, inclusive
quando ainda não há uma verificação metrológica carregada.

Operação manual, sempre pela API local (o padrão apenas simula):

```sh
python3 web/api.pse ferramenta reconciliar_equipamentos
python3 web/api.pse ferramenta reconciliar_equipamentos --aplicar
```

Os caminhos vêm de `radar.conf`. A simulação desfaz suas escritas; a aplicação
faz backup SQLite consistente, incluindo WAL, em `dados.dir/backups/identidade/`,
e executa a reconciliação em transação. Integridade e FKs são verificadas.

A migração recusa relações antigas contraditórias em vez de descartar um dos
valores. O backup anterior é preservado. Depois de remover colunas redundantes,
o instalador não reinstala automaticamente código antigo que dependa delas:
se uma checagem posterior falhar, mantém o código compatível e registra o motivo
no relatório para corrigir a checagem e reaplicar. Restauração explícita de um
backup de código incompatível também é recusada sem alterar o banco.

## Validação automatizada

`tests/test_normalizacao_relacional.py` verifica as dependências corrigidas,
restrições na escrita, migração populada com FK ativa, recusa de contradições,
NULL em modelos, releitura, ambiguidades, separação de contribuições públicas,
proveniência, aliases, decisões humanas, backup e simulação. Esses testes entram
na suíte obrigatória do GitHub Actions. Não se usa comparação de nomes de
colunas como prova geral de 3FN; as regras de negócio e dependências acima
fazem parte do contrato revisado.

### Reparo de mapeamentos após a revisão inicial

O instalador também completa campos desconhecidos usando os registros arquivados
de ANTT/Inmetro/PRF, dentro da transação e do backup da reconciliação. Não recria
as tabelas nem altera os originais. A [correspondência cadastral sem série](JUNCAO_METROLOGICA.md#correspondência-cadastral-quando-a-fonte-não-publica-série)
é derivada na leitura, com origem e ambiguidades explícitas; não cria identidade
física nem substitui os relacionamentos normalizados por cópias de atributos.
