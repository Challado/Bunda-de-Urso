# BUNDA DE URSO


Configuração atual: só `RADAR_CONF` seleciona o arquivo. Banco, logs, tokens,
chaves, fila e cache ficam dentro de `[dados] dir`; `banco = radar.sqlite3`
é apenas o nome do arquivo. A configuração não contém usuário/grupo e a
instalação transfere os agendamentos do Radar ao crontab do `www-data`.

A instalação com `radar.conf` junto aos scripts e caminhos relativos está
descrita em [Migração para a raiz web](docs/MIGRACAO_RAIZ_WEB.md). A migração
é feita pelo instalador privado, preservando o banco e preparando www-data.
## Cadastro nacional aberto, rastreável e auditável de radares e fiscalização eletrônica de trânsito

[![Validação](https://github.com/Challado/Bunda-de-Urso/actions/workflows/testes.yml/badge.svg)](https://github.com/Challado/Bunda-de-Urso/actions/workflows/testes.yml)

[Acessar Radar Brasil](https://servidor3.lucas.inf.br/openclaw/radar/) · [Código no GitHub](https://github.com/Challado/Bunda-de-Urso)

![Bunda de Urso — a bunda do urso com o radar tatuado](docs/bunda-de-urso.png)

> **O nome é uma provocação; o propósito é sério.**

> **🤖 Autoria:** este repositório — código, documentação e este README — foi **feito pelo Jarvis**, o assistente de IA (OpenClaw). Detalhes na seção [Autoria e proveniência](#autoria-e-proveniência), no fim.
>
> **🌐 No ar:** a consulta pública roda em <https://servidor3.lucas.inf.br/openclaw/radar/> (mapa e raio por localização); a API responde em <https://servidor3.lucas.inf.br/openclaw/radar/api.pse>.

## Por que “Bunda de Urso”?

Bunda de Urso nasceu de um daqueles momentos em que a estrada te deixa na mão. Você vem no limite certo, confiando no navegador, no app de alerta, no radarzinho do painel — e, de repente, um flash. Ou pior: você passa por um equipamento que deveria estar ali, marcado, avisado, e não está. Nenhuma placa, nenhum aviso no aplicativo, nada. É aquela sensação de murchar por dentro, de “bunda flácida”, de ter sido deixado sozinho justamente pela informação que prometia te proteger.

E tem o outro lado, que dói igual: o radar que já morreu há anos, desligado, sucateado, arrancado do chão — e continua firme no mapa, como se estivesse lá. Aí você freia no vazio, por nada, todo dia no mesmo lugar, feito bobo.

A proposta é transformar essa frustração em infraestrutura pública de informação: descobrir onde estão os equipamentos de fiscalização, identificar sua situação real e permitir que aplicativos, navegadores, pesquisadores e cidadãos consultem uma base consolidada, verificável e atualizada — em vez de depender de achismo, de rumor e de cadastro comunitário para saber onde tem radar.

Não se trata de incentivar excesso de velocidade nem de escapar da fiscalização. Quem quer correr, que responda por isso. A ideia é aumentar a transparência, facilitar o respeito aos limites, reduzir informação incorreta e permitir auditoria pública de dados que, em tese, já são públicos.

## As lamúrias (ou: por que a gente ainda está aqui)

A lista é longa, e todo mundo que dirige tem a sua. A nossa está aqui embaixo:

- **O radar que não existe no mapa.** Está lá, na beira da pista, e o navegador jura que não há nada. O app de alerta, idem. Você só descobre na hora do flash.
- **O radar fantasma.** Desativado, removido, sucateado — e ainda marcado como ativo. Aí você freia por um poste vazio, todo dia, no mesmo lugar, feito palhaço.
- **A velocidade errada.** A placa (quando existe) diz uma coisa, o app diz outra, o cadastro diz uma terceira. Quarenta onde é sessenta, sessenta onde é quarenta. Ninguém sabe ao certo — e o bolso paga a conta.
- **O cadastro oficial sem coordenada.** O órgão publica, com orgulho, “KM 027+244M”. Ótimo. E onde fica isso, exatamente? A resposta, com sorte, é um trecho de 400 km de rodovia.
- **O dado espalhado em 27 portais.** Cada estado no seu formato: um em CSV, outro em PDF escaneado, outro numa página que só abre em navegador antigo, outro sem endereço nenhum.
- **A planilha sem cabeçalho e o PDF torto.** A fonte “oficial” chega sem coluna definida, com coordenada misturando grau decimal e grau/minuto/segundo — e, às vezes, com o sinal do oeste perdido no caminho.
- **A base comunitária decidindo se o radar existe.** Quando o órgão não publica, sobra o mapa colaborativo — que é útil, mas erra, e não deveria ser a única testemunha da existência de um equipamento.
- **O radar que aparece do nada.** Sem obra, sem aviso, atrás de uma placa, num trecho que ontem não tinha nada.
- **O órgão que publica a relação... de vez em quando.** Às vezes atualiza, às vezes esquece, às vezes tira do ar. E a multa continua chegando na sua casa.
- **O cidadão que só quer respeitar o limite.** Ele só quer saber qual é o limite, e o sistema inteiro parece fazer questão de esconder.

Ninguém aqui quer passar a mão na cabeça de quem corre. Queremos é que a informação deixe de ser favor, rumor ou PDF ilegível — e vire dado de verdade, com procedência e rastro.

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

A implementação é em **Python 3, só stdlib** (`urllib`, `sqlite3`, `csv`, `json`, `xml.etree`) — sem pip, sem dependência externa. Não utiliza `import cgi`.

### O que é o “`.pse`”? (o servidor web, explicado)

Quem esbarra em `api.pse` não tem como adivinhar o que é — e não precisa: **`.pse` é apenas uma extensão de arquivo**, uma convenção histórica **deste servidor** (não é formato, linguagem nem produto). Todo script executável do site usa `.pse` — por exemplo `cnpj.pse`, `frase.pse`, `pythoninfo.pse` e, aqui, `api.pse`. É o equivalente local de um `.cgi`.

Na prática, a API é:

- um **programa Python 3** (só a biblioteca padrão), guardado **fora** da pasta pública;
- que o **nginx** executa **sob demanda** via **`fcgiwrap`** (o adaptador FastCGI→CGI do servidor);
- **sem servidor de aplicação, sem daemon e sem porta própria** — cada requisição sobe o processo, responde (*JSON*, *XML*, *TXT*, *NDJSON*, *EDIFACT* ou *DIF*) e termina;
- com a **rota no parâmetro `rota`**, porque o `fcgiwrap` deste servidor não define `PATH_INFO`:

```
https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-24.9555&lon=-53.4552&raio=5000&formato=json
```

Resumindo: **nginx + fcgiwrap + Python** executando um arquivo `.pse`. Nada mais exótico que isso.

O esquema é **SQL canônico, sem ORM** — nada de SQLAlchemy por aqui. São **78 tabelas no esquema base** (T01..T77 + EXECUCAO_ARTEFATO) definidas uma única vez em `core/manutencao/build_schema.py` (o comando `tools/build_schema.py` encaminha a geração pela API), que gera as duas DDLs gêmeas (`sql/schema.sqlite.sql` e `sql/schema.postgres.sql`), com chaves primárias/estrangeiras, `CHECK`, `UNIQUE` e índices, incluindo equipamentos, pontos, instalações, faixas, órgãos, fontes, documentos, verificações, operações, evidências e candidatos geográficos. O banco padrão é SQLite, sem PostGIS. A compatibilidade efetiva com outros SGBDs requer homologação específica.

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

A relação estadual da **AGETO/TO** também é coletada semanalmente, com GPS,
rodovia/km, série e número Inmetro. A carga pode usar o PDF local quando o
portal estiver indisponível. Veja [a fonte AGETO e os comandos pela API](docs/FONTE_AGETO_TO.md).

No painel de gestão, **Cruzamentos** confere novamente as contribuições ativas,
inclusive as já verificadas, com as fontes oficiais importadas. A tela de cada
contribuição também oferece **Cruzar com fontes oficiais**. As sugestões mostram
a fonte, a distância e divergências; a confirmação **Usar cadastro oficial** mantém
o ponto oficial no mapa e preserva o histórico da contribuição duplicada.
O cruzamento funciona sem IA. Veja [o fluxo e os endpoints](docs/CRUZAMENTOS.md).

## Assistência opcional

IA vem **desligada por padrão**. O painel administrativo oferece extração de documentos,
correspondências, auditoria, diagnóstico de coleta e explicações, sempre com alternativa
local e propostas para revisão. Aceita Ollama ou API externa compatível com OpenAI,
com chave cadastrada separadamente. O resumo público usa regras locais e fontes.
Veja [configuração, limites e funcionamento sem IA](docs/ASSISTENTE.md).

## O desafio central: onde diabos fica o radar

Nem todo cadastro governamental contém GPS. É o pecado original do setor: o órgão sabe que o radar existe, sabe a rodovia, sabe o quilômetro — e, mesmo assim, te deixa procurando um ponto no meio do nada. Por isso, Bunda de Urso possui um **resolvedor geográfico** que tenta localizar cada equipamento oficial:

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

A [normalização relacional e a identidade na escrita](docs/NORMALIZACAO_RELACIONAL.md)
foram revisadas: a atualização migra as relações redundantes e reconcilia
equipamentos comprovados, preservando fontes, histórico e IDs antigos.

O detalhe do radar e do equipamento faz a [junção da metrologia entre fontes oficiais](docs/JUNCAO_METROLOGICA.md)
pela série, tipo e município. Assim, uma instalação da GOINFRA pode mostrar o
histórico do Inmetro mesmo quando as duas publicações têm IDs de origem distintos.
As fontes e os valores divergentes continuam separados para conferência.
Quando a fonte não publica série, o detalhe também apresenta correspondência
cadastral por município, rodovia, km, sentido e velocidade, explicitando que a
identidade física ainda não foi confirmada. O instalador repara campos perdidos
lendo os brutos existentes, sem apagar ou recriar a base.
As [consultas de complementos](docs/CONSULTAS_E_COMPLEMENTOS.md) preferem
`LEFT JOIN`: ausência de endereço, documento, catálogo ou metadado não deve
eliminar o registro principal.

## Velocidades e fiscalização

O cadastro diferencia obrigatoriamente:

- Velocidade regulamentada geral, para veículos leves e para pesados.
- Limites específicos por faixa ou sentido, quando oficialmente publicados.
- Velocidade nominal do instrumento no Inmetro, que não equivale automaticamente ao limite da via.
- Velocidades observadas em estudos de tráfego, que não são limites regulamentados.

O tipo de equipamento (fixo, portátil), a função (controlador, redutor), o sentido, as faixas e a natureza da fiscalização (permanente ou pontual) são atributos distintos. Fiscalizações pontuais só recebem data/hora de início e fim quando isso constar de fonte verificável; não presumir operação ativa.

## API e formatos

A API web (arquivo `.pse`: **nginx + fcgiwrap + Python**, explicado acima) oferece consultas por latitude, longitude e raio (até **1000 km**); identificação do equipamento; UF, rodovia e quilômetro; além de fontes, atualizações, situação do serviço, operações, trechos e tráfego.

Os endpoints da API são:

- `/api/v1/radares`
- `/api/v1/radares/{id}`
- `/api/v1/radares/busca`
- `/api/v1/equipamentos` e `/api/v1/equipamentos/{id}`
- `/api/v1/fontes` e `/api/v1/fontes/{id}`
- `/api/v1/atualizacoes`
- `/api/v1/operacoes`
- `/api/v1/trechos`
- `/api/v1/trafego`
- `/api/v1/status`
- `/api/v1/ajuda`
- `/api/v1/radares/submeter` (submissão pública, sem token)
- `/api/v1/radares/{id}/historico` (auditoria pública do ponto)
- `/api/v1/login` e `/api/v1/logout` (sessão do painel)
- `/api/v1/minha-senha` (troca da própria senha)
- `/api/v1/gestao/*` (pendentes, radar, correspondências, bloqueios, tokens, usuários — exige sessão ou `X-Api-Token`)
- `/api/v1/gestao/eu` (contexto da sessão: login/papel — o painel usa para decidir o que exibir)
- `/api/v1/admin/sincronizar` e `/api/v1/admin/rollback`
- `/health/live` e `/health/ready` (também em `/api/v1/health/live|ready`)

Os retornos incluem **TXT delimitado em linha única por registro** (delimitador configurável por GET/POST), JSON, NDJSON, XML, DIF (Data Interchange Format) e EDI/EDIFACT no perfil bilateral do projeto. O perfil EDIFACT precisa de homologação com cada consumidor; não se declara interoperabilidade universal.

O endpoint de ajuda documenta parâmetros, tipos, formatos, exemplos, significado dos campos e códigos de erro. Campos ausentes não devem ser substituídos por zeros ou valores presumidos.

**Sem resultado não é sinônimo de ausência de radar.** Se a região não possui fonte suficiente, o sistema informa `sem_cobertura` e `completude_confirmada=false`, em vez de garantir falsamente que a via está livre de fiscalização. (É o reverso da lamúria: melhor dizer “não sei” do que jurar que a pista está limpa e te entregar de bandeja.)

## Governança da ingestão (camadas de confiança)

Toda escrita passa pela **API**; nenhuma tela nem ferramenta toca o banco por fora do
app. As camadas de confiança são:

- **Leitura aberta** (site + API), sem cadastro.
- **Criação aberta** por `POST /api/v1/radares/submeter` (sem token): o formulário
  usa `Prefer: respond-async`, salva um JSON durável e recebe **202 com protocolo**.
  O processamento posterior valida, procura correspondências e publica como
  `colaborativo` **não verificado**, com selo, procedência e limite por IP.
  Recebido não significa publicado. Clientes antigos sem esse cabeçalho continuam
  recebendo 201 após processamento síncrono. Veja [fila de cadastros](docs/FILA_CADASTROS.md).
- **Verificação / edição / remoção** exigem **sessão do painel** ou **`X-Api-Token`**.
  Escopos: `contribuidor` (lê) < `moderador` (verifica/edita/remove) < `admin`
  (usuários, tokens, bloqueios). A remoção é **tombstone** (soft delete com motivo
  obrigatório): o radar sai do mapa/consulta, mas a linha e o histórico permanecem.
- **Correspondência com o oficial:** ao ingerir um colaborativo, procura-se um ponto
  OFICIAL no raio `RAIO_CORRESPONDENCIA_M` (default 150 m). Havendo, o colaborativo é
  ligado a uma **sugestão de correspondência**, permanecendo **não verificado**.
  Uma decisão fundamentada de moderador é necessária para substituir o oficial.
- **Anti-sabotagem:** coordenada dentro de um `BLOQUEIO_GEOGRAFICO` ativo
  (`marcacao_falsa` | `zona_sombra`) é **recusada (409)** com o motivo.
- **Consulta pública:** preserva o oficial até decisão explícita de moderação e
  **esconde** pontos removidos/desabilitados. `GET /api/v1/radares/{id}/historico` é
  público (transparência: “removido em X por Y, motivo Z”).

Submissões públicas possuem fonte própria e não podem atualizar a base autenticada
por meio de IDs enviados pelo usuário. As correções de reconciliação e operação
estão descritas em `docs/CORRECOES_BUNDITA_DE_URSO.md`.

A configuração operacional mora em `[governanca]` do `radar.conf`, fora do checkout; o esquema aditivo da
camada em `sql/migracoes/`. Detalhes e exemplos `curl` em `docs/GOVERNANCA.md`.

O **painel HTML** mora em `web/gestao.html` (login, fila de pendentes, detalhe/verificar/
editar/desabilitar/remover, histórico, correspondências, bloqueios, tokens e troca de
senha) e `web/usuarios.html` (usuários e tokens). É HTML/CSS/JS vanilla, sem CDN, e fala
só pela API (`api.pse?rota=...`) com o cookie de sessão — nunca lê o banco direto. O que a
tela mostra acompanha o escopo do login (contribuidor = leitura; moderador = moderação;
admin = bloqueios/tokens/usuários).

## Atualizações, observabilidade e auditoria

O coletor pode ser agendado via systemd, com verificações periódicas, cache persistente e atualização incremental. O resolvedor geográfico possui execução independente. A periodicidade deve respeitar a publicação efetiva de cada fonte e suas limitações de acesso.

Registrar logs de download, parsing, validação, importação, deduplicação, alterações, falhas, idade do cache e cobertura territorial. Relatórios devem distinguir equipamentos com GPS oficial, posição referencial, posição derivada, candidato em revisão e sem coordenada.

Os dados devem permitir rastrear cada resposta da API até a publicação original. Isso é indispensável para correção de erros e transparência pública.

## No ar (consulta pública)

O serviço publicado responde em:

- **Página de consulta (mapa + raio por localização):** <https://servidor3.lucas.inf.br/openclaw/radar/>
- **API:** <https://servidor3.lucas.inf.br/openclaw/radar/api.pse> (rotas em `/api/v1/*`)

**Palavras-chave:** radar de velocidade, radares, fiscalização eletrônica, trânsito, dados abertos, Brasil, API, mapa, segurança viária.

## Instalação e operação

A especificação funcional é o `ESPECIFICACAO_v1.1.txt`; a referência técnica do código está em `docs/README_TECNICO.md`, `docs/LOCALIZADOR_GEOGRAFICO_V1_4.md`, `docs/CRUZAMENTO_DE_CAMPOS.md` e `docs/REQUISITOS_VIGENTES_2026-10-10.md`.

Sem pip, sem instalação: basta ter Python 3. Gera as DDLs, sincroniza uma fonte e serve a API:

```bash
python3 tools/build_schema.py
python3 -m coletor.sync --fonte antt
python3 -m coletor.sync --fonte recife --arquivo tests/fixtures/recife_equipamentos.csv
```

**Caminhos: um arquivo só.** A instalação (código, banco, dados, webroot, logs,
espelho de dados) é declarada em **`/etc/radar-brasil/radar.conf`** e lida por
`core/caminhos.py`. Precedência: variável de ambiente > `.conf` > padrão do
checkout. Nenhum script decide diretório por conta própria — quem escrever
caminho fixo é reprovado por `.github/scripts/verificar_caminhos.py`. Modelo,
chaves e diagnóstico em [`docs/CONFIGURACAO.md`](docs/CONFIGURACAO.md):

```bash
python3 deploy/conf_radar.py            # caminhos efetivos e de onde vieram
python3 deploy/conf_radar.py --verificar
```

Variáveis de ambiente equivalentes: `RADAR_BRASIL_HOME`, `RADAR_DATA_DIR`,
`RADAR_DB`, `RADAR_WEB_ROOT`, `RADAR_WEB_URL`, `RADAR_LOG_DIR`,
`RADAR_SYNC_CLONE`, `RADAR_SYNC_REMOTO` (e `RADAR_CONF` para apontar outro
arquivo). O entry point web é `web/api.pse`; os testes rodam com:

```bash
python3 -m unittest discover -s tests
```

O ambiente web requer Nginx, fcgiwrap, Python e permissão controlada de acesso ao banco local. Antes de colocar em produção, testar autenticação administrativa, configurações, permissões, atualização, formatos e recuperação de falhas.

## Situação real do desenvolvimento

O projeto implementa a **ESPECIFICACAO_v1.1.txt (10/10/2026)**: coletor/sincronizador, API `.pse`, esquema relacional de **78 tabelas base**, resolvedor geográfico, serializadores em seis formatos, documentação e testes automatizados locais (stdlib `unittest`). Os testes locais não equivalem à homologação das coletas reais em todo o Brasil.

**Ainda precisam de trabalho e validação:** integração e importação real de todas as fontes federais, estaduais e municipais; resolução das coordenadas ausentes; homologação de cada formato e SGBD utilizado; verificação de qualidade e atualização de cada órgão; aferição da cobertura nacional; avaliação de licenças para redistribuição de cada conjunto de dados.

O projeto não deve divulgar percentuais de cobertura, contagens nacionais ou precisão de localização sem medi-los efetivamente. Equipamentos sem coordenada comprovada continuam no inventário para investigação — porque apagar o que não sabemos localizar seria a pior lamúria de todas: esconder o problema debaixo do tapete.

## Validação automática (CI)

O workflow **Navegadores** testa o cadastro em Firefox e Chromium, com desktop
e tela estreita/toque, CGI e SQLite reais. Inclui rede indisponível, prazo de
resposta, reenvio e preservação do oficial. Veja [como executar e limites da
cobertura Android](docs/TESTES_NAVEGADOR.md).

Todo push no `main`, todo pull request e um disparo manual rodam a validação
rígida no GitHub Actions (`.github/workflows/testes.yml`). Nada passa por
"parece que está bom": cada checagem reprova o build.

**Suíte de testes** — Python 3.13, `compileall` de todo o código e a suíte
completa (`unittest`). O runner roda com piso de testes: se a coleta quebrar e
a suíte rodar "verde vazio", o job reprova.

**Rígido (contratos e invariantes)** — verificadores em `.github/scripts/`:

- **Paridade dos esquemas SQL** (`verificar_sql.py`): as tabelas e colunas dos
dois dialetos (`sqlite` × `postgres`) são as mesmas, e o DDL do SQLite executa
de verdade num banco em memória.
- **JSON** (`verificar_json.py`): todo JSON versionado parseia e não tem chave
repetida.
- **Segredos** (`verificar_segredos.py`): tokens do GitHub, AWS, Google, Slack
  e Telegram, chaves privadas e JWT; e arquivos que nunca podem entrar no git
  (`.env`, `config.php`, `*.pem`, `*.key`, credencial de conta de serviço).
- **Front** (`verificar_web.py`): todo `href`/`src` local existe, toda página
tem `viewport` (celular/tablet/PC) e as rotas que o front chama são atendidas
pela API (`web/nucleo.py`).
- **Escrita no banco** (`verificar_banco.py`): telas, console, cron e ferramentas
entram por `api.pse`; `tools/` contém clientes, sem isenção de acesso direto.
As operações locais de manutenção não são rotas HTTP. A única conexão física fica em
`core/db.py`.
- **Estrutura** (`verificar_estrutura.py`): arquivos obrigatórios presentes e
nenhum artefato de build/execução versionado (`__pycache__`, `.pyc`, bancos,
logs).

## Transparência e segurança viária

A Resolução CONTRAN nº 798/2020 prevê a publicidade da relação de medidores pelos órgãos responsáveis, incluindo a localização dos fixos, nos termos de seu art. 9º, parágrafo único. Isso não implica que cada órgão publique coordenadas GPS exatas, nem significa autorização irrestrita para qualquer uso de qualquer base de terceiros.

Fonte normativa: https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-contran/resolucoes/resolucao798-2020.pdf

O projeto apoia informação pública, fiscalização transparente, respeito aos limites e segurança viária. Alertas de navegação não substituem placas, regras de trânsito ou atenção do condutor.

## Visão de futuro

Queremos que qualquer pessoa ou aplicativo possa perguntar: **“Existe equipamento de fiscalização perto desta latitude e longitude? Qual é, qual velocidade fiscaliza, em que sentido, desde quando, e qual documento comprova isso?”** — e receber uma resposta verificável, inclusive quando a resposta responsável for **“ainda não conseguimos confirmar”**.

No fim das contas, é isso: transformar a lamúria em dado. Para que ninguém mais freie no vazio, ninguém mais leve um flash por falta de aviso, e ninguém mais fique na mão por causa de informação que deveria ser pública e não é.

**Bunda de Urso: para que a informação sobre radares não deixe mais ninguém na mão.**

## Licença

O Bunda de Urso é **código-fonte disponível**, não software livre: o código está à vista, mas tem dono e regras de uso. Em resumo (o que vale é o texto do [`LICENSE`](LICENSE)):

| ✅ Pode | ❌ Não pode |
|---|---|
| instalar e usar para você, a sua família ou a sua organização | criar um projeto novo baseado neste código, no todo ou em parte, nem reescrito em outra linguagem |
| alterar o código da sua instalação | distribuir o código, original ou alterado, fora deste repositório |
| propor melhorias por pull request aqui | oferecer o sistema como serviço para outras pessoas |
| fazer fork no GitHub para preparar essas propostas | manter um fork como projeto separado |
| consultar e usar os **dados** publicados (mapa e API), sob CC BY 4.0 | apresentar os dados sem atribuição, ou como se fossem de outra origem |

Para qualquer outro uso, peça autorização pelo GitHub ([Challado](https://github.com/Challado)).

> 💡 **Contribua, não copie.** Ser contribuidor do Bunda de Urso é muito melhor que fazer um fork: a sua melhoria entra
> para todos, com o seu nome no histórico, e você não corre risco nenhum. Já um fork que vira projeto próprio viola a
> licença, e os direitos sobre este código são defendidos: pedido de remoção nas plataformas, ação judicial com
> indenização e até ação penal (a Lei 9.609/98 trata a violação de direito de autor de software como crime). Mesmo quem
> acha que está certo pode ter de se defender, e isso custa tempo e advogado. **Na dúvida, pergunte antes:** a resposta é
> de graça, a discussão depois não é.

- **Dados:** o cadastro é compilado a partir de fontes oficiais públicas. A compilação e a estrutura são oferecidas sob **[CC BY 4.0](LICENSE-DATA.md)** (atribuição), respeitando os termos de cada fonte original.
- **Terceiros:** a pasta `referencia/` é material de terceiros e mantém a licença de origem.

## Autoria e proveniência

- **Contato:** [fale com o mantenedor](https://servidor.lucas.inf.br/site/contato).
- **Quem fez:** este repositório — o código, a documentação e este README — foi **escrito e mantido pelo Jarvis**, o assistente de IA (**OpenClaw**), a pedido do mantenedor do projeto. Os commits e os pushes também foram feitos pelo Jarvis.
- **Como foi feito:** em colaboração direta com o mantenedor, no dia a dia, a partir da especificação do projeto e de material de referência. O código é Python 3 puro (só stdlib), sem dependências externas.
- **Onde está no ar:** a consulta pública roda em <https://servidor3.lucas.inf.br/openclaw/radar/> e a API em <https://servidor3.lucas.inf.br/openclaw/radar/api.pse> (rotas em `/api/v1/*`).
- **O que não é nosso:** a pasta `referencia/` reúne material de referência de terceiros, guardado apenas para estudo e comparação; não é de autoria deste projeto nem do Jarvis.

A configuração da instalação pode ser consultada no painel **Administração →
Configuração** ou em `api.pse configuracao mostrar`. O painel salva os parâmetros
operacionais pela API; caminhos e credenciais são administrados pela mesma API no
terminal. Atualizações preservam o arquivo do servidor. Veja `docs/CONFIGURACAO.md`.

A página de status por UF e dos leitores é acessada diretamente, sem link na
home. Consulte [o funcionamento e as regras de contagem](docs/STATUS.md).

### Layouts e interações no CI

Celular e tablet deixam a página rolar normalmente, com todos os radares abaixo
do mapa. No PC, o mapa e a lista se ajustam à tela, com painel recolhível quando necessário.

O workflow **Layouts e interacoes** valida 18 perfis de celular, tablet e PC em
Chromium, Firefox e WebKit, com 432 verificações de rolagem, clique/toque,
navegação, cadastro e altura do mapa. Roda automaticamente em push/main e PR,
além de permitir acionamento manual. Relatórios, screenshots, medidas e traces
ficam nos artefatos por 14 dias. Veja [a matriz e os cenários](docs/TESTES_LAYOUTS.md).
