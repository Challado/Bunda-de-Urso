# Consultas e relações opcionais

Nas consultas de apresentação, a entidade principal deve sobreviver à ausência
de complementos. A preferência é `LEFT JOIN` para endereço, catálogos, modelo,
fabricante, organização, documentos, identificadores e metadados de procedência.
Valores ausentes permanecem nulos ou coleções vazias, sem substituir por dados
inventados. Filtros sobre a tabela opcional ficam no `ON` quando fazem parte do
enriquecimento: colocá-los no `WHERE` pode voltar a eliminar a linha principal.

Filtros pedidos pelo usuário, como UF/tipo/raio, restringem resultados de forma
intencional. Uma busca geográfica exige posição; a cadastral e o detalhe
continuam disponíveis sem GPS. Autenticação e consultas de prova de identidade
continuam exigindo os vínculos necessários. Os `JOIN`s da seleção de candidatos
metrológicos validam a procedência/contexto da associação, e não filtram o radar
principal: sem correspondência, ele permanece com sua metrologia própria.
Filtros por um ID conhecido usam a FK do registro principal ou do vínculo
(`p.municipio_id`, `o.municipio_id`, `rf.fonte_id`), sem exigir que o nome esteja
disponível no catálogo complementar. A sigla da UF vem do município cadastrado.

## Ligações recuperadas na revisão

| Entidade | Dados que passam a ser apresentados |
| --- | --- |
| Ponto | Endereço estruturado de `ENDERECO` e identificadores de `IDENTIFICADOR_PONTO` |
| Equipamento | Documentos de `DOCUMENTO_EQUIPAMENTO` |
| Verificação | Documentos de `DOCUMENTO_VERIFICACAO` e URL de certificado inequívoco |
| Documento | Tipo, código, título, URL, emissor, datas, hash e descrição |
| Operação | Lista completa de documentos e identificadores oficiais, mantendo `documento_url` |
| Trecho | Documentos completos e municípios associados com metadados opcionais |
| Fonte/execução | Registro principal preservado mesmo com metadados incompletos numa base legada |

O endereço somente aparece quando está relacionado ao ponto no banco. Não há
extração arbitrária de endereço a partir de observações nem conversão em GPS.
Um certificado sem documento/URL continua sem link; havendo URLs conflitantes,
a lista de documentos é preservada e nenhum link único é escolhido.

As coleções são consultadas separadamente pelo proprietário. Juntar faixas,
verificações e documentos numa única consulta poderia multiplicar linhas e
inflar contagens; a revisão mantém essas coleções independentes e ordenadas.

Na consolidação explícita, endereço disponível em outro membro pode completar
o endereço ausente, indicando sua origem. Endereços divergentes são mantidos
como conflito. Verificações documentalmente equivalentes mantêm todos os
documentos e registros/fontes originais, mesmo quando apresentadas uma vez.

As respostas ricas JSON/NDJSON/XML mantêm as coleções. As colunas tabulares
versionadas permanecem compatíveis: endereço/documentos/equipamentos continuam
nas colunas já existentes. Campos adicionais não mudam a ordem dessas colunas.

## Validação e instalação

`tests/test_consultas_complementos.py` verifica relações presentes/ausentes,
coleções sem multiplicação, certificados ambíguos, consolidação e API CGI.
Fixtures de legado simulam referências incompletas somente em bancos temporários;
a leitura tolerante não altera as FKs nem faz passar uma checagem de integridade
de um banco inconsistente. Natureza de fonte desconhecida continua sem conferir
origem oficial e os dados privados do payload permanecem filtrados.

A migração aditiva `0003_complementos` cria índices para buscar documentos,
identificadores e publicações por entidade. O instalador habitual chama a
inicialização/migração pela API, preservando banco, configuração e dados originais.
Não há recarga obrigatória das fontes nem requisito de IA.
