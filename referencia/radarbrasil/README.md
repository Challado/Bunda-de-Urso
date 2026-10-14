# RADAR BRASIL — Coletor e API web Nginx/fcgiwrap (.pse)

**Entrega: código executável e testável, com pendências explicitamente delimitadas.** Este projeto NÃO é apresentado como base nacional já coletada/validada. A validação online das fontes oficiais e certas integrações estaduais/municipais não pôde ser executada no ambiente de construção (sem DNS/acesso à internet). Não criar nem declarar radares reais com dados de teste.

## 1. O que foi implementado (verificável no pacote)

- **Programas separados:** coletor `python -m radarbrasil.collector` e API `web/api.pse` executada via Nginx + fcgiwrap, sem importar o módulo `cgi`.
- **Banco relacional sem PostGIS:** 78 tabelas SQLAlchemy, chaves primárias/estrangeiras, CHECK, UNIQUE, índices B-tree, entidades ponto/equipamento/instalação/faixa/fonte/operação/verificação/documento/organização e tabelas N:N. Latitude e longitude são DECIMAL/NUMERIC comuns; bounding box em SQL e Haversine na aplicação.
- **Banco padrão:** SQLite. DDL compilada em SQLAlchemy para SQLite, PostgreSQL e MariaDB/MySQL; uso real e conformidade em MariaDB/MySQL, PostgreSQL e Firebird requerem homologação por SGBD (PENDENTE abaixo).
- **Coleta:** descoberta de recursos CKAN de ANTT e DNIT, download HTTPS com timeout, limites de bytes, 429/5xx com backoff e Retry-After, redirecionamentos conferidos; PRF portáteis HTML e PRF fixos através da tabela XLSX vinculada pela página oficial; JSON, CSV, XML e XLSX; Inmetro por arquivo JSON/XML obtido legitimamente; OSM opcional; registro de todas as tentativas, falhas e alertas.
- **Integridade e cache:** arquivos originais SHA-256 com persistência; tabelas de importação por registro; restrições SQL; savepoints; não substituir lote válido quando nova versão não passa validação; ETag/Last-Modified/304; data da coleta separada da data de publicação quando disponível; `validate-cache` e `audit`.
- **Deduplicação conservadora:** identifica mesmo equipamento na mesma fonte por ID/série, associa ponto por mesmo rodovia/km/coordenada quando compatíveis, preserva instrumentos distintos; séries iguais entre fontes criam candidatos a revisão. Não realizar fusão automática interfontes com evidências insuficientes.
- **Velocidade:** limitações para leves/pesados/geral são separadas da velocidade nominal por faixa do Inmetro e de velocidade de passagem na base de tráfego ANTT. Divergências viram conflitos sem fabricar valor consolidado.
- **Temporal:** operações pontuais/itinerantes com datas ISO 8601 e timezone EXPLÍCITO, armazenadas como UTC; sem período oficial = desconhecido, não presumir atividade.
- **API:** GET/POST; `/api/v1/radares`, `/api/v1/radares/{id}`, `/api/v1/radares/busca`, `/api/v1/equipamentos/{id}`, `/api/v1/trafego`, `/api/v1/ajuda`, `/api/v1/status`, `/api/v1/fontes`, `/api/v1/atualizacoes`, `/api/v1/trechos`, `/api/v1/operacoes`, `/health/live`, `/health/ready` e `/api/v1/admin/atualizar` (token obrigatório).
- **Formatos de saída:** TXT delimitado (uma linha por radar, delimitador em GET/POST), JSON, NDJSON, XML, Data Interchange Format (.dif) e EDIFACT perfil bilateral RadarBrasil/GENRAL (NÃO mensagem genérica interoperável com todos os parceiros; ver PENDENTES).
- **Operação:** systemd timer horário, logs estruturados via stderr/journald, controle de sessão transacional, cabeçalhos para cobertura incompleta, resposta HTTP 503 se nenhuma base pontual utilizável foi importada.
- **Fontes estaduais e municipais:** cadastradas como fontes *de importação manual* por padrão, sem inventar endpoints automáticos.

**Contrato de saída:** `docs/CONTRATO_v1_1.txt`, `docs/ESPECIFICACAO_COMPLETA_REFERENCIA.txt` se incluído; a ajuda da própria API é a lista de parâmetros e posições das colunas TXT/DIF. **DFD/DER:** `docs/DFD_MODELO.md` e `radarbrasil/schema.py`.

## 2. Instalar nativamente no Debian

Todos os caminhos são exemplos ajustáveis, mas precisam ser iguais para coletor e web. Teste primeiro sem disponibilizar a API publicamente.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx fcgiwrap unzip
sudo useradd --system --home /var/lib/radarbrasil --shell /usr/sbin/nologin radarbrasil 2>/dev/null || true
sudo install -d -o radarbrasil -g www-data -m 2770 /var/lib/radarbrasil /var/lib/radarbrasil/cache
sudo install -d -o radarbrasil -g radarbrasil -m 0750 /var/log/radarbrasil
sudo install -d -o root -g root -m 0755 /opt/radarbrasil
# Copie os arquivos do ZIP para /opt/radarbrasil (a pasta raiz do projeto).
cd /opt/radarbrasil
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo chmod 755 web/api.pse
sudo sed -i '1c#!/opt/radarbrasil/.venv/bin/python3' web/api.pse
```

Crie `/etc/radarbrasil/radarbrasil.env` com permissão 0640 (`root:radarbrasil`), por exemplo:

```ini
RADAR_DATABASE_URL=sqlite:////var/lib/radarbrasil/radares.sqlite3
RADAR_CACHE_DIR=/var/lib/radarbrasil/cache
RADAR_CONFIG=/opt/radarbrasil/config/sources.json
RADAR_LOG_DIR=/var/log/radarbrasil
RADAR_LOG_LEVEL=INFO
RADAR_CACHE_WARNING_HOURS=24
RADAR_CACHE_CRITICAL_HOURS=168
RADAR_ADMIN_TOKEN=
RADAR_USER_AGENT=RadarBrasil/1.0 (+contato-real-do-operador)
```

Inicialize como o usuário do serviço (carregar environment file sem expor segredos no terminal; use `sudo -u radarbrasil env RADAR_DATABASE_URL=...` ou um shell de manutenção controlado). Exemplo quando o sistema não tiver outro banco:

```bash
sudo -u radarbrasil env RADAR_DATABASE_URL=sqlite:////var/lib/radarbrasil/radares.sqlite3 \
  /opt/radarbrasil/.venv/bin/python -m radarbrasil.collector init
sudo -u radarbrasil env RADAR_DATABASE_URL=sqlite:////var/lib/radarbrasil/radares.sqlite3 \
  /opt/radarbrasil/.venv/bin/python -m radarbrasil.collector audit
```

O processo `fcgiwrap` normalmente roda como `www-data` e precisa de leitura sobre `/var/lib/radarbrasil` e sobre o banco, mas **não** de permissão irrestrita. Adicione `fastcgi_param RADAR_DATABASE_URL sqlite:////var/lib/radarbrasil/radares.sqlite3;` e `fastcgi_param RADAR_CONFIG /opt/radarbrasil/config/sources.json;` às localizações do Nginx **apenas para SQLite sem credenciais**. Para outros bancos, disponibilize as variáveis no serviço do fcgiwrap, não no arquivo público do Nginx. Para SQLite, conceda acesso de leitura ao usuário fcgiwrap e mantenha as gravações no coletor. Não usar chmod 777.

Inclua as `location` de `deploy/nginx/radarbrasil.conf` no `server` existente, ajustando socket e caminho. Verifique `systemctl status fcgiwrap`, `nginx -t` e `systemctl reload nginx`.

```bash
sudo cp deploy/systemd/radarbrasil-coletor.service /etc/systemd/system/
sudo cp deploy/systemd/radarbrasil-coletor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now radarbrasil-coletor.timer
systemctl list-timers radarbrasil-coletor.timer
journalctl -u radarbrasil-coletor.service -n 100 --no-pager
```

### Banco alternativo

O contrato permite PostgreSQL, MariaDB/MySQL, Firebird ou SQLite SEM extensão espacial. URL de conexão e driver devem ser configurados no environment; dependências em `requirements-databases.txt`. Um `init` cria as tabelas para o dialeto disponibilizado. **Não mudar a URL de um banco em uso sem migração**: `create_all()` não migra nem copia os registros existentes. Gerar DDL, criar base limpa, aplicar CHECK/FK e executar auditoria antes de homologar outros SGBDs; ver item PENDENTE 5.

## 3. Comandos do coletor e testes da API

```bash
python -m radarbrasil.collector init
python -m radarbrasil.collector sources
python -m radarbrasil.collector status
python -m radarbrasil.collector audit
python -m radarbrasil.collector validate-cache
python -m radarbrasil.collector update --source ANTT_RADARES
python -m radarbrasil.collector update --source DNIT_PNCV
python -m radarbrasil.collector update --source PRF_PORTATEIS
python -m radarbrasil.collector update --source PRF_FIXOS
python -m radarbrasil.collector import-file --source INMETRO_IMPORT --format json --file /caminho/oficial/inmetro.json
python -m radarbrasil.collector import-file --source DER_PR --format xlsx --file /caminho/oficial/der-pr.xlsx
```

Use os mesmos `RADAR_*` do ambiente do serviço, inclusive em comandos manuais. Para recarregar fonte depois de vencer o intervalo, `update --source FONTE --force`. **Um erro retorna código de processo 2 e aparece em `status`, `audit` e journald.** Se a fonte estiver inacessível, o coletor mantém o último snapshot íntegro e a API consulta a base local.

```bash
curl -fsS 'http://localhost/api/v1/ajuda?formato=json'
curl -i 'http://localhost/api/v1/radares?lat=-24.9555&lon=-53.4552&raio=1000&formato=txt&delimitador=%3B'
curl -fsS 'http://localhost/api/v1/radares/busca?uf=PR&rodovia=BR-277&formato=json'
curl -fsS 'http://localhost/api/v1/status?formato=json'
curl -fsS -X POST 'http://localhost/api/v1/radares' -H 'Content-Type: application/json' \
  --data '{"lat":-24.9555,"lon":-53.4552,"raio":1000,"formato":"xml"}'
```

Para testar `.pse` localmente sem Nginx (somente com ambiente configurado):

```bash
REQUEST_METHOD=GET PATH_INFO=/api/v1/ajuda QUERY_STRING=formato=json \
  /opt/radarbrasil/.venv/bin/python /opt/radarbrasil/web/api.pse
```

`/api/v1/radares` sem nenhum ponto no banco -> 503. Banco com pontos, mas nenhum dentro do raio -> JSON com `encontrado=null` e cobertura parcial; TXT com corpo vazio e HTTP 200, indicando cobertura insuficiente nos cabeçalhos. **Nunca interpretar vazio como prova de inexistência de radar.**

## 4. Integridade dos dados e velocidades

- ANTT `tipo_de_radar=controlador/redutor` classifica FUNÇÃO, NÃO prova equipamento fixo. Velocidades `velocidade_leve` e `velocidade_pesado` são limites de velocidade por categoria.
- DNIT `CEV/CEM/REV` são categorias funcionais; não declarar radar móvel/fixo sem evidência específica. Não inventar velocidade regulamentada quando a coluna não existe.
- Inmetro `VelocidadeNominal` é propriedade metrológica da faixa, não limite legal. `Faixas[]` com mesma série = um instrumento, não um por faixa. Histórico de certificados fica em `verificacao_metrologica`.
- ANTT tráfego `velocidade` é velocidade observada dos veículos; importada somente em `observacao_trafego` e exposta em `/api/v1/trafego`, jamais em `limite_velocidade`. Fonte `ANTT_TRAFEGO` desligada por padrão por volume e falta de homologação real.
- Mesma série em dois órgãos sem prova do mesmo instrumento: gravar `candidato_duplicidade`, não fundir. Mesmo ponto da via pode conter dois instrumentos legítimos; a identidade física e os sentidos/faixas determinam a consolidação.
- Sem fonte oficial de data/hora, não gerar operação pontual. Quando os campos `inicio_fiscalizacao` e `fim_fiscalizacao` são ISO 8601 com fuso e modalidade `pontual`/`itinerante`, a operação é persistida; `em=` consulta apenas operações com intervalo comprovado, NÃO interpreta ausência de operação como impossibilidade de fiscalização.

## 5. (PENDENTE 1 — Homologação ONLINE dos conectores federais; NÃO pode ser concluída sem acesso real)

**Responsável técnico deve seguir exatamente estes passos no servidor com internet e guardar evidências do resultado.** A rede de construção não resolve os domínios oficiais; por isso esta fase não foi declarada concluída.

1. Execute `curl -I --max-time 15 'https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17'` e `curl -I --max-time 15 'https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade'`; verificar TLS, redirect e códigos HTTP.
2. Rode primeiro `python scripts/validar_fontes_reais.py --source ANTT_RADARES --out /tmp/antt-validacao.json`, repetindo para DNIT_PNCV, PRF_PORTATEIS e PRF_FIXOS. Só depois execute o coletor, inicialmente ANTT, DNIT, PRF portáteis e PRF fixos **um por vez**, com `--force`; registre número de linhas e amostras do payload, inclusive identificador, latitude, longitude, km e velocidades. Nunca assumir sucesso só por HTTP 200; `status=ok` requer linhas importadas e válidas.
3. O **DNIT** publica XLSX Julho/2026 no conjunto acima. Verificar coluna por coluna e abas reais contra `docs/CRUZAMENTO_DE_CAMPOS.md`; se cabeçalhos divergirem, incluir aliases em `radarbrasil/normalization.py:normalize_record()` e `sources.py:parse_table()` e teste fixo em `tests/` antes de habilitar a fonte em produção.
4. A **ANTT** publica cadastro dos radares no conjunto acima; `ckan_discover` seleciona recurso de dados JSON/CSV mais recente, sem usar o dicionário PDF como planilha. Conferir `velocidade_leve` e `velocidade_pesado` e verificar que campos desconhecidos permaneçam em `registro_fonte.payload_original`. Em caso de divergência de velocidades entre fontes, a API deverá devolver conflito, não valor inventado.
5. Na **PRF**, a página de radares fixos aponta para tabela dinâmica em `https://mapas-html.vercel.app/tabela.html`, com download de planilha Google XLSX; `prf_fixed_discover` segue esses dois links. Confirme no servidor que a planilha ainda é disponibilizada publicamente por `docs.google.com`, e se os cabeçalhos são exatamente os previstos. Se mudar a hospedagem ou o XLSX exigir login, registrar falha de conector e configurar importação manual autorizada; NÃO contornar autenticação.
6. Na **PRF portáteis**, importar `https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/lista-de-radares` e conferir pares como `REF181`/`REF184` com série `TC005867`, sem transformar os dois IDs administrativos em dois equipamentos físicos, nem transformar série igual entre marcas diferentes em fusão sem comprovação.
7. Simule indisponibilidade de cada domínio por bloqueio temporário no ambiente de teste; execute `update`; confirme código de falha/log/alerta e permanência do último snapshot e da resposta da API. Não alterar rede de produção para esse teste.
8. Salve no registro de homologação: URL final, hash SHA256, data de publicação declarada, data da coleta, número de linhas, chaves de coluna, registros aceitos/rejeitados e 3 casos reais comparados manualmente ao órgão. Marcar fonte `VALIDADA_EM_PRODUCAO` SOMENTE após esses critérios.

## 6. (PENDENTE 2 — Inmetro nacional automático; importação de arquivo já funciona)

Portal: `https://servicos.rbmlq.gov.br/Instrumento`; catálogo PSIE em `https://dados.gov.br/dados/conjuntos-dados/portal-de-servicos-do-inmetro-nos-estados-psie`.

1. Confirmar se o portal oferece **download público JSON/XML atual** por UF e o termo de acesso. Exemplo visto em repositório terceiro, **NÃO certificado como endpoint público atual**: `https://servicos.rbmlq.gov.br/dados-abertos/AC/medidores.json`. Rodar `curl -i --max-time 20` em ambiente autorizado e verificar `Content-Type`, cabeçalho, 200 e conteúdo efetivo; não prosseguir se 403, CAPTCHA ou autenticação restrita.
2. Se existir endpoint oficial público, criar uma entrada `INMETRO_UF_XX` para cada UF (27 entradas) em `config/sources.json` com `format=json` ou `xml`, `enabled=false` até teste. A URL deve ser descoberta na origem, não presumida pelo padrão de nome.
3. Validar os campos `NumeroInmetro`, `NumeroSerie`, `Faixas[]`, `Historico[]`, `Proprietario`, `LocalVerificacao` e `DataValidade` contra a documentação; adaptar a transformação no início de `ingest_rows()` se a estrutura real for diferente. Não atribuir GPS a localidades textuais.
4. Rodar pelo menos uma UF (por exemplo AC) manualmente e comparar 5 números de série e 3 certificados com consultas individuais no PSIE. Certificar que faixas múltiplas não duplicam equipamento e que a velocidade nominal não alimenta limite legal.
5. Para UFs sem API pública permitida, exportar arquivos oficiais de forma autorizada e rodar `import-file --source INMETRO_IMPORT --format json --file ARQUIVO` (também aceita `xml`). Registre data e origem do arquivo e limite a cadência ao permitido pelo órgão.
6. Depois de validar as 27 UFs, habilitar somente os conectores aprovados; testar falha individual e manter cache por UF. Não declarar cobertura completa sem evidências.

## 7. (PENDENTE 3 — DERs, Detrans, prefeituras e cobertura nacional)

Fontes cadastradas/desabilitadas em `config/sources.json`: DER-SP, DER-PR, DER-MG, Curitiba, Recife e Belo Horizonte. Não afirmar integração automática concluída: atualmente `format=manual_json` representa **somente a modalidade manual**.

Procedimento obrigatório para CADA nova fonte: confirmar URL oficial e licença -> localizar link de dados em CSV/XLSX/JSON/XML -> guardar arquivo original -> verificar cabeçalhos/valores -> registrar correspondência coluna por coluna em `docs/CRUZAMENTO_DE_CAMPOS.md` -> implementar conector (reutilizar `ckan_discover()` se for CKAN com recursos públicos, ou acrescentar adaptador de portal específico em `sources.py`) -> acrescentar fixtures obtidas legitimamente e testes com falhas de layout -> fazer importação de uma amostra -> validar 5 radares no site oficial -> habilitar `enabled=true` -> registrar o grau de cobertura por estado/município na tabela `cobertura_fonte`. Não declarar município sem radar simplesmente porque fonte não publicou cadastro.

A cobertura completa exige prospecção e testes em outros 26 estados/DF e milhares de municípios; **não existe no pacote uma comprovação universal dessa cobertura**. Nunca criar endereço de download fictício. Trechos críticos da PRF devem ir para `trecho_elegivel`, não para `ponto_fiscalizacao`.

## 8. (PENDENTE 4 — Funcionalidades de modelo ainda não integralmente povoadas)

As 78 tabelas estão criadas, mas nem todos os conectores preenchem todos os agregados. Para completar:

- **Municípios:** importar tabela IBGE oficial código/UF/nome em `municipio`, casar nome+UF somente quando unívoco; caso contrário preservar texto original e não inventar `codigo_ibge`.
- **Datas de instalação, inativação, estado, propriedade e modelo:** usar `ponto_fiscalizacao`, `instalacao`, `modelo_equipamento`, `ponto_organizacao` e `verificacao_metrologica`, sob evidência explícita no arquivo. `data_da_inativacao` da ANTT NÃO prova retirada física do aparelho. Vincular fabricante via `modelo_equipamento.fabricante_id`; preservar origem.
- **Operações móveis/itinerantes e trechos:** importar fonte oficial com ponto, intervalo, fuso, situação e vínculo do instrumento para `operacao_fiscalizacao`, `operacao_equipamento`, `trecho_elegivel` e vértices, quando disponíveis. Nunca inferir agenda a partir da relação de trechos críticos.
- **Deduplicação interfontes:** relatório `collector audit` lista candidatos. Projetar rotina administrativa auditável que exija comprovação fabricante + modelo + série ou identidade comprovada por documento; aceitar revisão por humano, transacionar reatribuição de FKs para ID canônico, impedir conflitos UNIQUE e manter histórico reversível em `decisao_duplicidade`. Testar explicitamente PRF `REF181` vs `REF184` e dois aparelhos com sentidos diferentes no mesmo ponto. Até existir essa rotina, NÃO fundir automaticamente casos ambíguos.
- **Proveniência detalhada por campo:** tabelas `catalogo_campo`, `valor_observado`, `decisao_valor_canonico` estão declaradas; conectar cada transformação mapeada a um valor original e registrar decisão de escolha. O payload original de cada observação JÁ é preservado integralmente em `registro_fonte`.
- **Importação volumosa e retenção:** `parse_table` atualmente carrega o arquivo em memória e `ingest_rows` percorre a lista; migrar CSV e XLSX para iteradores com lotes e critérios quantitativos específicos por fonte. Definir política de retenção para tráfego ANTT, que pode ter volume elevado.
- **Validação de queda abrupta:** manter histórico de contagem por recurso e recusar publicação quando a nova planilha tiver redução improvável ou erro semântico mesmo com menos de 50% de registros inválidos; permitir override SOMENTE documentado e auditado.
- **Backup/restore e migrações:** implementar migrations versionadas e rotina de backup comprovada/restauração, especialmente em upgrades de schema. O `init` atual é criação de base, não ferramenta de migração de banco já existente.

## 9. (PENDENTE 5 — Homologação dos outros bancos e interoperabilidade EDI)

1. Gerar e executar DDL em bases limpas PostgreSQL, MariaDB, MySQL e Firebird; validar PK/FK/CHECK/UNIQUE, criação de índices, Unicode, DECIMAL, transações, locks de atualização, e UPSERT sem extensões espaciais. O SQLAlchemy compila a definição para SQLite/PostgreSQL/MySQL, mas teste de conexão/DDL/CRUD em outros bancos não foi executado.
2. Instalar somente o driver pertinente de `requirements-databases.txt`; configurar `RADAR_DATABASE_URL` e executar `init`, `audit`, `import-file`, `query` e os testes em cada SGBD. Não considerar suporte homologado apenas porque o dialeto compila.
3. DIF: abrir exportação real em LibreOffice Calc e em importadores pretendidos, validar 36 colunas e nulos `\\N`, sem perder objetos JSON serializados.
4. EDIFACT: foi implementado como **perfil bilateral documentado**, usando GENRAL D96A e FTX com JSON Base64. Para interoperabilidade com parceiro externo, escolher implementação/convenção de mensagem, formalizar MIG (Message Implementation Guidelines), validar envelope/segmentos/encoding/contagens com validador EDIFACT independente e documentar identificação de remetente/destinatário. Não alegar conformidade universal já obtida.
5. Controles operacionais adicionais: alertas e-mail/webhook, dashboard administrativo e medição de desempenho com carga real ainda requerem desenvolvimento/homologação se forem requisitos de produção.

## 10. Testes automatizados, integridade e proibições

```bash
python -m pip install -r requirements-dev.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_integration.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_enhancements.py
python -m radarbrasil.collector audit
python -m radarbrasil.collector validate-cache
```

Testes usam **dados explicitamente fictícios**. Não importar fixtures para produção. `audit` verifica, no SQLite, `PRAGMA foreign_key_check` e `PRAGMA integrity_check`, e relata candidatos de duplicidade, fontes e alertas.

**Regras de não regressão para qualquer agente ou desenvolvedor:** não remover funcionalidades para simplificar testes; não criar radars fictícios ou localizações inferidas; não alterar limites regulamentados a partir de velocidades observadas; não presumir situação de operação móvel; não apagar snapshot bom após falha; não preencher silenciosamente campos de origem sem evidência; não declarar cobertura nacional sem fonte comprovada. Cada pendência só é encerrada depois de existir teste automatizado e validação com dados reais demonstrável.

## 11. Fontes oficiais verificadas na pesquisa (páginas/catálogos, não acesso ponta-a-ponta do código)

- ANTT radares: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17
- ANTT tráfego: https://dados.antt.gov.br/dataset/269aebaa-05e7-4d76-a105-408f12bf4094
- DNIT PNCV: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
- PRF fixos: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
- PRF portáteis: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/lista-de-radares
- PRF trechos críticos: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/trechos-criticos
- Inmetro PSIE: https://servicos.rbmlq.gov.br/Instrumento
- Catálogo PSIE: https://dados.gov.br/dados/conjuntos-dados/portal-de-servicos-do-inmetro-nos-estados-psie
- DER-SP: https://dadosabertos.sp.gov.br/dataset/radar
- DER-PR: https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade
- DER-MG: https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis
- Curitiba: https://transito.curitiba.pr.gov.br/fiscalizacaoeletronica
- Recife: https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito
- Belo Horizonte: https://dados.pbh.gov.br/pt_BR/dataset/fiscalizacao-eletronica

**Licença:** consultar licença individual de cada origem e não redistribuir dados restritos. OSM é opcional e comunitário (com regras de atribuição e licenciamento próprias); não confundir com validação oficial.
