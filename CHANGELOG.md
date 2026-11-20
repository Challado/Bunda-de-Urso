# Histórico de alterações

## Consultas com limite zero

- `limite=0` remove o teto de registros onde esse parâmetro existe, mantendo filtros e posição de início. A busca segue a política de acesso e o intercâmbio segue o orçamento de bytes de cada rodada.

## Leituras públicas e fontes oficiais

- A página de status usa um resumo público das fontes oficiais. A equipe pode abrir o diagnóstico detalhado com a credencial do painel de gestão.
- Cada coletor pode ajustar timeout, tentativas, tamanho da resposta, User-Agent e validação do certificado HTTPS por fonte ou URL. Por padrão, a validação do certificado começa desligada.
- O Detran-DF usa a lista oficial de equipamentos e mantém o histórico do leitor. A camada ArcGIS histórica fica disponível para coleta manual.
- Foram integradas publicações oficiais da CET-Rio, Mogi das Cruzes, EPTC de Porto Alegre e ARTESP. O cruzamento de trechos usa a UF e pode recorrer às malhas da IDE-Sisema, do IBGE e do SNV/DNIT, com indicação de geometria inferida.

## Política da instância pública

- Publica a política de uso e oferece um arquivo diário comprimido com as fontes e a atribuição do cadastro.
- Limita a paginação pública, exige chave para consultas profundas e aplica bloqueios e liberações por IP, faixa ou User-Agent.
- Protege os diagnósticos dos leitores, os relatórios de atualização, a rede e o acompanhamento de envios com credenciais ou a liberação prevista para a rota.

## Consultas em lote de radares e leitores

- Buscas carregam faixas, limites, instrumentos, documentos e operações só para os pontos da página. Totais e filtros consideram todos os resultados, inclusive os registros vinculados a aliases.
- A agenda lê o histórico dos recursos cadastrados em lote. O painel e o cron compartilham a visão da última execução por recurso.
- Novos índices atendem as buscas por posição, as junções dos pontos e a leitura das execuções recentes em PostgreSQL e SQLite.

## Configuração por motor de banco

- `[dados]` define o diretório operacional e o motor ativo. `[postgres]` define a conexão com o servidor e `[sqlite]` define o arquivo local.
- O instalador converte configurações antigas e informa o motor ativo no relatório. Em PostgreSQL, a instalação valida o esquema PostgreSQL e omite o campo de arquivo SQLite de origem.

## Descoberta das edições da ANTT

- O coletor acompanha as atividades do conjunto de radares e segue o link da revisão mais recente. O catálogo CKAN também pode indicar a edição atual.
- JSON e CSV da mesma edição podem ser usados na coleta. Uma falha na descoberta ou no arquivo fica no histórico de leituras e preserva os dados já publicados.

## Backup SQL do PostgreSQL

- O backup PostgreSQL agora gera SQL compactado com a estrutura e os dados do esquema ativo. A restauração recria as tabelas em uma transação.

## Ativação do PostgreSQL e normalização do esquema

- A ferramenta local `api.pse ferramenta migrar_postgres` pede dados de conexão e senha oculta. Transfere a base e o histórico para um esquema novo e valida a importação em transação.
- O migrador preserva os IDs, as referências e a precisão decimal do SQLite. Recusa sobrescrita e permite simular a transferência com rollback.
- Com `--ativar`, a API, os coletores, os crons e a manutenção passam a usar o PostgreSQL.
- As migrações separam grafias originais, documentos brutos e tamanho dos artefatos. Origem da revisão mesh e recurso da execução de um alerta são obtidos pelos vínculos relacionais.

## Inmetro: seleção de UFs na coleta automática — 04/11/2026

- Corrige o bloqueio de `TODAS` pela validação de arquivos locais na API/cron. O seletor nacional e seus aliases são reconhecidos pelo conector; siglas de UF são resolvidas para as URLs oficiais.
- Arquivos de importação continuam restritos a `[dados] dir`, incluindo a resolução de links simbólicos. Outros conectores não recebem exceções para os seletores do Inmetro.
- Testes do fluxo completo de sincronização local reproduzem o erro anterior, verificam a coleta por UF/nacional e preservam o bloqueio de arquivos externos. Executados também no GitHub Actions pela suíte existente.
- A correção não exige alterar `radar.conf` nem recriar o banco. Uma sincronização manual do Inmetro antecipa a próxima leitura agendada e atualiza o status com o resultado real.

## DNIT por HTTP direto — 04/11/2026

- Coletor de equipamentos consulta a API pública GeoJSON usada pelo portal de multas, sem Chromium ou exportação `blob:`.
- Mantém a identidade do recurso instalado, as junções por código DNIT e a importação de XLSX local; preserva os registros GeoJSON originais e a ordem longitude/latitude.
- Recusa respostas vazias, esquemas alterados, códigos ausentes/duplicados e coordenadas inválidas, mantendo o tratamento de falhas e retentativas HTTP.
- Workflow manual do DNIT usa o mesmo coletor por HTTP, salva GeoJSON e relatório e dispensa Node/Playwright/Chromium.

## Caixas aninhadas no status

- Menus de fontes apresentados como caixas recolhíveis uma dentro da outra: Federal → estado → município → fonte → leitura.
- Federal ocupa toda a largura e começa aberto; as 27 UFs aparecem fechadas, com cabeçalhos, bordas e contadores próprios.
- Recolher uma caixa oculta seu conteúdo e preserva a abertura dos filhos para a próxima consulta; busca, atualização e controles gerais continuam disponíveis.
- GitHub Actions valida as bordas, a largura e o encaixe dos cinco níveis em celular, tablet e PC, além de clique, toque e teclado.

## Fontes do status por esfera e local

- Árvore recolhível Federal → 27 estados/DF → municípios → fontes → leituras.
- Situações agregadas de OK, erro, pendência e desativação em cada nível, com detalhes e URLs preservados.
- Busca por UF, estado e município abre os caminhos correspondentes, além dos filtros por fonte e situação.
- Abrangências cadastradas obtidas por LEFT JOIN, com catálogo territorial explícito para fontes conhecidas ainda não coletadas; fontes sem localização continuam visíveis.
- Estados sem fonte cadastrada aparecem explicitamente; fontes documentais não são apresentadas como cadastro de radares concluído.

## Retorno à consulta anterior

- Links dos radares na lista e no mapa abrem os detalhes em nova aba, preservando a consulta original.
- Botões de voltar no topo e no fim dos detalhes, acessíveis também no celular.
- Se o navegador bloquear o fechamento da aba, o retorno recompõe as coordenadas e o raio consultados.
- Testes de clique/toque e preservação de busca e rolagem integrados à matriz de layouts.

## Home, navegação e mapas

- Ícone do urso retorna à home em todas as páginas.
- Consulta concluída mostra somente o snapshot, sem resumo técnico de cobertura ou contagens redundantes.
- Links para OpenStreetMap, Google Maps, Street View, Bing Mapas e Streetside no local consultado e nos marcadores, compartilhando os destinos com os detalhes.
- Validação de navegação, coordenadas dos links e busca vazia incluída nos testes de navegador e na matriz de layouts do GitHub Actions.

## Documentação da API e organização do GitHub

- Guia destacado de consulta/exportação, incluindo NDJSON, paginação, XML, TXT, DIF e EDIFACT.
- Notas de estado e histórico retiradas do README e preservadas neste changelog.

## Intercâmbio de Instâncias e TRASEIRO DE URSO

- Contrato genérico HTTPS/JSON, cliente Python independente e negociação dos tipos de documento.
- Rede de radares com identidades persistentes, descoberta de pares, lotes bidirecionais e reenvio sem duplicação.
- Intervalo de consulta independente por servidor, inatividade configurada por tipo/número e parada anunciada com retorno opcional.
- Cadastro separado, validação pela moderação e fonte própria para posições aprovadas.
- Receitas JSON/CSV compartilhadas, desativadas até autorização local.
- Cron independente no usuário da instalação e integração aos relatórios de atualização.

## Links de mapas

Bing Mapas e Bing Streetside acrescentados aos links das coordenadas, com testes de parâmetros e de exibição.

## Histórico de layout preservado do README

## Situação real do desenvolvimento

O projeto implementa a **ESPECIFICACAO_v1.1.txt (10/10/2026)**: coletor/sincronizador, API `.pse`, esquema relacional de **78 tabelas base**, resolvedor geográfico, serializadores em seis formatos, documentação e testes automatizados locais (stdlib `unittest`). Os testes locais não equivalem à homologação das coletas reais em todo o Brasil.

**Ainda precisam de trabalho e validação:** integração e importação real de todas as fontes federais, estaduais e municipais; resolução das coordenadas ausentes; homologação de cada formato e SGBD utilizado; verificação de qualidade e atualização de cada órgão; aferição da cobertura nacional; avaliação de licenças para redistribuição de cada conjunto de dados.

O projeto não deve divulgar percentuais de cobertura, contagens nacionais ou precisão de localização sem medi-los efetivamente. Equipamentos sem coordenada comprovada continuam no inventário para investigação — porque apagar o que não sabemos localizar seria a pior lamúria de todas: esconder o problema debaixo do tapete.

### Layouts e interações no CI

Celular e tablet deixam a página rolar normalmente, com todos os radares abaixo
do mapa. No PC, o mapa e a lista se ajustam à tela, com painel recolhível quando necessário.

O workflow **Layouts e interacoes** valida 18 perfis de celular, tablet e PC em
Chromium, Firefox e WebKit, com 486 verificações de rolagem, clique/toque,
navegação, cadastro e altura do mapa. Roda automaticamente em push/main e PR,
além de permitir acionamento manual. Relatórios, screenshots, medidas e traces
ficam nos artefatos por 14 dias. Veja [a matriz e os cenários](docs/TESTES_LAYOUTS.md).
