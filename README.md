# BUNDA DE URSO
## Cadastro nacional aberto, rastreável e auditável de radares e fiscalização eletrônica de trânsito

> **O nome é uma provocação; o propósito é sério.**

## Por que “Bunda de Urso”?

Bunda de Urso nasceu da sensação de frustração de passar por um radar que deveria estar corretamente identificado nos sistemas de navegação e alerta, mas não está. É aquela sensação de ficar desanimado, murcho, de “bunda flácida”, como se a informação tivesse deixado o motorista na mão.

A proposta é transformar essa frustração em infraestrutura pública de informação: descobrir onde estão os equipamentos de fiscalização, identificar sua situação e permitir que aplicativos, navegadores, pesquisadores e cidadãos consultem uma base consolidada, verificável e atualizada.

Não se trata de incentivar excesso de velocidade ou escapar da fiscalização. A ideia é aumentar a transparência, facilitar o respeito aos limites de velocidade, reduzir informações incorretas e permitir auditoria pública de dados já divulgados por órgãos competentes.

## Missão

Construir um cadastro nacional independente de fornecedores comerciais, com foco em **latitude e longitude de cada equipamento**, complementadas por identificação física, órgão responsável, velocidade regulamentada, rodovia, quilômetro, sentido, faixas, tipo, datas, aferições e documentos de origem.

O objetivo é que Bunda de Urso seja uma referência que outros serviços — inclusive ferramentas de navegação e projetos cartográficos — possam consultar ou aproveitar conforme seus próprios processos e licenças, em vez de depender de cadastros comunitários para estabelecer a existência de um radar.

**Princípio essencial:** não inventar coordenadas, velocidades, situação operacional ou datas. Um registro sem posição exata permanece identificável e investigável, com localização candidata e grau de certeza explícitos.

## Cobertura pretendida

Todo o Brasil: União, 26 estados, Distrito Federal e municípios, em vias urbanas e rurais. Abrange controladores e redutores fixos, equipamentos portáteis, pontos autorizados de fiscalização, operações pontuais quando oficialmente publicadas e outros dispositivos de fiscalização eletrônica quando claramente identificados. Cada categoria deve ser diferenciada; uma câmera de monitoramento comum não é automaticamente um radar de velocidade.

A cobertura pretendida **não significa cobertura nacional completa já homologada**. O sistema deve declarar lacunas, fontes desatualizadas e áreas sem dados suficientes.

## Fontes de dados e política de confiabilidade

A fonte primária de existência, identidade, velocidade e situação de cada equipamento deve ser oficial: DNIT, PRF, ANTT, Inmetro/PSIE, DERs, Detrans, órgãos estaduais, concessionárias responsáveis por cadastros oficiais, órgãos municipais e portais governamentais de dados abertos.

Também são usados, para localizar geograficamente cadastros oficiais, dados cartográficos públicos como o Sistema Nacional de Viação (SNV/DNIT), sistemas rodoviários estaduais (SRE), serviços geográficos oficiais (ArcGIS REST, WFS, GeoJSON, KML e Shapefile) e o Cadastro Nacional de Endereços para Fins Estatísticos (CNEFE/IBGE).

OpenStreetMap não é fonte oficial para afirmar que um equipamento existe, está ativo ou fiscaliza certa velocidade. No módulo v1.4, o OSM pode ser consultado **somente como candidato auxiliar de localização**, quando já houver uma referência documental governamental, com revisão e identificação da proveniência. Waze e bases comerciais não alimentam automaticamente o cadastro oficial. Não são utilizados serviços pagos como dependência da coleta.

Os arquivos de origem são preservados com hash SHA-256, URL, data de coleta e, quando disponível, data de publicação. Registros conflitantes permanecem rastreáveis; o sistema não escolhe arbitrariamente um valor.

## Arquitetura

O projeto separa duas responsabilidades:

1. **Coletor e normalizador:** processo independente que descobre recursos oficiais, baixa documentos, interpreta formatos, valida campos, registra alterações e alimenta o banco relacional.
2. **Aplicação web/API:** interface de consulta que lê o banco local, sem consultar portais governamentais a cada requisição.

A implementação de referência está em Python. A aplicação web é servida por **Nginx + fcgiwrap**, por meio de um executável Python com extensão **`.pse`**, preservando a convenção histórica do servidor. Não utiliza `import cgi`.

O esquema de referência v1.4 inicializa 83 tabelas SQLAlchemy, incluindo equipamentos, pontos, instalações, faixas, órgãos, fontes, documentos, verificações, operações, evidências e candidatos geográficos. O banco padrão é SQLite, sem PostGIS. A compatibilidade efetiva com outros SGBDs requer homologação específica.

## Como a coleta funciona

- Descobrir fontes e recursos oficiais cadastrados, inclusive catálogos CKAN e publicações geográficas.
- Baixar com limites de tamanho, timeout, tentativas progressivas, tratamento de 429/5xx, Retry-After, redirecionamentos e cache HTTP (ETag/Last-Modified/304).
- Preservar o arquivo bruto e registrar seu hash, metadados e histórico de tentativas.
- Ler CSV, JSON, XML, XLSX e formatos geográficos suportados; tratar formatos especiais por adaptadores específicos.
- Mapear os campos originais para entidades normalizadas sem descartar os valores brutos.
- Validar coordenadas, unidades, datas, limites de velocidade, identificadores e relacionamentos.
- Identificar possíveis duplicatas, preservando números de série, identificadores administrativos, faixas, sentidos e trocas de equipamento.
- Publicar apenas dados validados e manter o último lote íntegro quando uma atualização falhar.

Uma falha no portal de origem não deve derrubar a API. O cache e a base local continuam disponíveis, mas o sistema informa a idade dos dados e eventuais problemas de atualização.

## O desafio central: encontrar latitude e longitude

Nem todo cadastro governamental contém GPS. Por isso, Bunda de Urso possui um **resolvedor geográfico** que tenta localizar cada equipamento oficial:

**1. Coordenada oficial direta:** utilizar a latitude/longitude publicada pelo órgão, preservando a precisão declarada e o documento.

**2. Correspondência entre cadastros oficiais:** cruzar série, registro Inmetro, órgão, instalação, endereço, rodovia, quilômetro e período para aproveitar a coordenada presente em outra publicação do mesmo equipamento.

**3. Rodovia e quilômetro:** localizar um trecho georreferenciado oficial com referências quilométricas calibradas e calcular uma posição candidata sobre sua geometria. Não interpolar arbitrariamente sobre a extensão total da rodovia.

**4. Endereço:** buscar referência geográfica em cadastros oficiais municipais ou no CNEFE/IBGE. A coordenada de um endereço não é automaticamente a posição exata do poste do radar.

**5. Candidato comunitário opcional:** quando já existir identificação oficial suficiente, consultar OSM como pista de localização, nunca como comprovação autônoma da identidade ou da velocidade do radar.

**6. Revisão e pendência:** registrar candidatos, evidências, conflitos, aprovação ou rejeição e motivo. Se a localização exata não puder ser comprovada, conservar `latitude=null` e `longitude=null` ou uma posição estimada claramente marcada, sem fabricar exatidão.

A consulta por raio usa coordenadas em colunas numéricas comuns, filtragem por caixa delimitadora e distância geodésica por Haversine, sem exigir PostGIS. Para raios pequenos, como 10 m, a incerteza de uma coordenada derivada deve ser considerada explicitamente.

## Deduplicação e integridade

Dois registros próximos não são necessariamente o mesmo radar; duas faixas também não representam obrigatoriamente dois instrumentos físicos. A identidade é avaliada por série, fabricante/modelo, registro Inmetro, código administrativo, órgão, ponto, sentido, faixa e período de instalação.

- Duplicidade comprovada: unificar logicamente, mantendo todas as referências e o histórico.
- Equipamentos distintos: preservar registros separados, mesmo que estejam no mesmo ponto.
- Evidência insuficiente: gerar candidato para revisão, sem fusão silenciosa.
- Substituição de equipamento: registrar histórico temporal da instalação.

O banco usa chaves primárias e estrangeiras, restrições de integridade e relacionamentos normalizados. Não eliminar dados originais durante a consolidação.

## Velocidades e fiscalização

O cadastro diferencia obrigatoriamente:

- Velocidade regulamentada geral, para veículos leves e para pesados.
- Limites específicos por faixa ou sentido, quando oficialmente publicados.
- Velocidade nominal do instrumento no Inmetro, que não equivale automaticamente ao limite da via.
- Velocidades observadas em estudos de tráfego, que não são limites regulamentados.

O tipo de equipamento (fixo, portátil), a função (controlador, redutor), o sentido, as faixas e a natureza da fiscalização (permanente ou pontual) são atributos distintos. Fiscalizações pontuais só recebem data/hora de início e fim quando isso constar de fonte verificável; não presumir operação ativa.

## API e formatos

A API web `.pse` oferece consultas por latitude, longitude e raio; identificação do equipamento; UF, rodovia e quilômetro; além de fontes, atualizações, cobertura, situação do serviço, operações e geolocalizações.

Entre os endpoints previstos/implementados na referência estão:

- `/api/v1/radares`
- `/api/v1/radares/{id}`
- `/api/v1/radares/busca`
- `/api/v1/equipamentos/{id}`
- `/api/v1/geolocalizacoes`
- `/api/v1/fontes`
- `/api/v1/atualizacoes`
- `/api/v1/operacoes`
- `/api/v1/trechos`
- `/api/v1/trafego`
- `/api/v1/status`
- `/api/v1/ajuda`
- `/health/live` e `/health/ready`

Os retornos incluem **TXT delimitado em linha única por registro** (delimitador configurável por GET/POST), JSON, NDJSON, XML, DIF (Data Interchange Format) e EDI/EDIFACT no perfil bilateral do projeto. O perfil EDIFACT precisa de homologação com cada consumidor; não se declara interoperabilidade universal.

O endpoint de ajuda documenta parâmetros, tipos, formatos, exemplos, significado dos campos e códigos de erro. Campos ausentes não devem ser substituídos por zeros ou valores presumidos.

**Sem resultado não é sinônimo de ausência de radar.** Se a região não possui fonte suficiente, o sistema informa `sem_cobertura` e `completude_confirmada=false`, em vez de garantir falsamente que a via está livre de fiscalização.

## Atualizações, observabilidade e auditoria

O coletor pode ser agendado via systemd, com verificações periódicas, cache persistente e atualização incremental. O resolvedor geográfico possui execução independente. A periodicidade deve respeitar a publicação efetiva de cada fonte e suas limitações de acesso.

Registrar logs de download, parsing, validação, importação, deduplicação, alterações, falhas, idade do cache e cobertura territorial. Relatórios devem distinguir equipamentos com GPS oficial, posição referencial, posição derivada, candidato em revisão e sem coordenada.

Os dados devem permitir rastrear cada resposta da API até a publicação original. Isso é indispensável para correção de erros e transparência pública.

## Instalação e operação

A referência técnica está no pacote Radar Brasil v1.4, em especial `README.md`, `docs/LOCALIZADOR_GEOGRAFICO_V1_4.md`, `docs/CRUZAMENTO_DE_CAMPOS.md` e `docs/REQUISITOS_VIGENTES_2026-10-10.md`.

Exemplo de inicialização e resolução, após configurar dependências, banco e ambiente:

```bash
python -m radarbrasil.collector init
python -m radarbrasil.georesolver preparar-antigos
python -m radarbrasil.georesolver resolver-tudo
python -m radarbrasil.georesolver relatorio --formato csv --arquivo /tmp/radares_geolocalizacao.csv
```

O ambiente web requer Nginx, fcgiwrap, Python e permissão controlada de acesso ao banco local. Antes de colocar em produção, testar autenticação administrativa, configurações, permissões, atualização, formatos e recuperação de falhas.

## Situação real do desenvolvimento

A versão técnica de referência é **Radar Brasil v1.4 (10/10/2026)**, com coletor, API `.pse`, esquema relacional, módulo de resolução geográfica, documentação e testes automatizados locais. Os testes locais não equivalem à homologação das coletas reais em todo o Brasil.

**Ainda precisam de trabalho e validação:** integração e importação real de todas as fontes federais, estaduais e municipais; resolução das coordenadas ausentes; homologação de cada formato e SGBD utilizado; verificação de qualidade e atualização de cada órgão; aferição da cobertura nacional; avaliação de licenças para redistribuição de cada conjunto de dados.

O projeto não deve divulgar percentuais de cobertura, contagens nacionais ou precisão de localização sem medi-los efetivamente. Equipamentos sem coordenada comprovada continuam no inventário para investigação.

## Transparência e segurança viária

A Resolução CONTRAN nº 798/2020 prevê a publicidade da relação de medidores pelos órgãos responsáveis, incluindo a localização dos fixos, nos termos de seu art. 9º, parágrafo único. Isso não implica que cada órgão publique coordenadas GPS exatas, nem significa autorização irrestrita para qualquer uso de qualquer base de terceiros.

Fonte normativa: https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-contran/resolucoes/resolucao798-2020.pdf

O projeto apoia informação pública, fiscalização transparente, respeito aos limites e segurança viária. Alertas de navegação não substituem placas, regras de trânsito ou atenção do condutor.

## Visão de futuro

Queremos que qualquer pessoa ou aplicativo possa perguntar: **“Existe equipamento de fiscalização perto desta latitude e longitude? Qual é, qual velocidade fiscaliza, em que sentido, desde quando, e qual documento comprova isso?”** — e receber uma resposta verificável, inclusive quando a resposta responsável for **“ainda não conseguimos confirmar”**.

**Bunda de Urso: para que a informação sobre radares não deixe mais ninguém na mão.**
