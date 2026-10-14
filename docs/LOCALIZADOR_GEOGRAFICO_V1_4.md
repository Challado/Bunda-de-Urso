# RADAR BRASIL — Resolvedor Geográfico v1.4 (coletor + fcgiwrap)

**Estado:** código e testes locais implementados. **Não houve homologação de downloads nacionais em tempo real neste ambiente.**

## Qual problema foi resolvido

A v1.3 importava dados oficiais, mas um instrumento sem latitude/longitude não podia ser recuperado por uma consulta por raio. A v1.4 inclui um programa `radarbrasil.georesolver` capaz de relacionar instrumentos sem GPS com referências OFICIAIS calibradas de rodovia/km, endereços do IBGE CNEFE e identidades de série; consulta OSM apenas como candidato, se solicitado. Mantém ponto/equipamento diferentes e guarda cada decisão de associação com auditoria. Também cria um endpoint de consulta ao estado geográfico de todos os equipamentos, inclusive os sem GPS.

**O que não se pode prometer:** a latitude e a longitude FÍSICAS e EXATAS de todo radar do Brasil não podem ser calculadas quando nenhuma fonte fornece local suficiente. Um número de série, isoladamente, não codifica posição geográfica. Ausências aparecem no relatório com `sem_coordenada` ou `pendente`, nunca como posições inventadas.

## Componentes entregues

- `radarbrasil/georesolver.py`: CLI com importadores e resoluções.
- 5 tabelas novas no modelo relacional: `geo_fonte`, `geo_trecho_calibrado`, `geo_trecho_vertice`, `geo_candidato`, `geo_decisao`. Todas têm PK, e relacionamentos usam FK.
- `radarbrasil/ingest.py` e `radarbrasil/normalization.py`: recuperação de `LocalVerificacao` (ex.: `BR 364 KM 124,4`) do Inmetro; relacionamento do ponto, série e informações administrativas e endereços quando disponíveis.
- `web/api.pse`: mesmo gateway CGI para Nginx/fcgiwrap, novo endpoint `GET/POST /api/v1/geolocalizacoes`, parâmetros `equipamento_id` e `somente_pendentes`, além de campos de evidência na consulta normal de radares.
- Testes determinísticos em `tests/test_georesolver.py`.

## Modelo de qualidade das coordenadas

1. `oficial`: coordenada de instrumento publicada por órgão responsável, se o registro realmente representar a posição do aparelho.
2. `oficial_imprecisa`: coordenada publicada por órgão oficial, explicitamente referencial ou imprecisa.
3. `inferida`: a posição foi derivada de documento externo (SNV/SRE com marcos calibrados, CNEFE). **Não é GPS físico exato.**
4. `desconhecida`: caso ambíguo ou candidato sem confirmação suficiente (inclusive OSM).

Campo `precisao_metros`: sempre NULL quando não houver estimativa fundamentada em metadados técnicos. As pontuações de 0 a 1 são PRIORIDADES heurísticas de revisão, não probabilidades calibradas de certeza.

### Origem e preferência

- Origem PRINCIPAL: cadastro oficial de radares ANTT/DNIT/PRF/Goinfra/DER/Detran/prefeituras, conforme versões públicas.
- Localizador estadual/federal: malhas geográficas OFICIAIS SNV do DNIT e SRE/DER estaduais **desde que contenham KM inicial/final calibrados por segmento e uma polilinha WGS84 compatível**. A mera geometria não determina o km de um aparelho.
- Endereço: IBGE CNEFE oficial, georreferenciado em 2022; só candidato quando município IBGE, logradouro e número coincidem e não há conflito de posições. Posição é de um endereço, não do poste.
- OSM: apenas referência independente, sem concessão de status OFICIAL. Permite extrato GeoJSON offline ou Overpass sob demanda na vizinhança de uma âncora oficial derivada. Jamais substitui coordenadas oficiais, jamais cria radar novo automaticamente, jamais afirma ativo ou calibrado.

## Instalação e atualização do banco

Exemplo Debian, na pasta do projeto; não instalar arquivos como root dentro do webroot.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export RADAR_DATABASE_URL='sqlite:////var/lib/radarbrasil/radar.sqlite3'
export RADAR_CACHE_DIR=/var/cache/radarbrasil
python -m radarbrasil.collector init
python -m radarbrasil.georesolver relatorio --limite 100000 --arquivo /tmp/geolocalizacoes_antes.json
```

`collector init` cria tabelas novas que não existirem (SQLite/PostgreSQL/MariaDB sob contrato de conexão existente). Faça backup antes de instalar e compare migrações em bases já personalizadas; `create_all` não corrige colunas incompatíveis pré-existentes.

## Fluxo A — receber instrumentos e registrar referência rodoviária

Primeiro importar os dados cadastrais oficiais como de costume. O Inmetro fornece `LocalVerificacao`; `BR 364 KM 124,4` é interpretado como via `BR-364`, km `124.4`. Registros históricos já importados com versão antiga podem ser recuperados:

```bash
python -m radarbrasil.georesolver preparar-antigos
```

Agora importar segmentos calibrados da malha rodoviária oficial. Use CSV com cabeçalho:

```csv
via;km_inicio;km_fim;geometria_json;uf;referencia
BR-277;99.000;101.000;"{""type"":""LineString"",""coordinates"":[[-53.49,-24.96],[-53.48,-24.96],[-53.47,-24.96]]}";PR;CODIGO_SEGMENTO_DO_ORGAO
```

As coordenadas de exemplo são FICTÍCIAS, criadas apenas para ilustrar a estrutura do arquivo e os testes. **Não as importe como posições reais.** Os campos `km_inicio`, `km_fim` e polilinha devem corresponder à mesma versão da referência quilométrica usada no cadastro de equipamento.

```bash
python -m radarbrasil.georesolver importar-trechos \
  --arquivo /dados/segmentos_oficiais_calibrados.csv \
  --fonte DNIT_SNV_2026 --url 'https://www.gov.br/dnit/pt-br/assuntos/atlas-e-mapas/pnv-e-snv'
python -m radarbrasil.georesolver resolver-km
```

Alternativamente: o comando `importar-geojson-oficial --arquivo /dados/trechos.geojson --fonte DER_GO_2026 --url ...` aceita GeoJSON FeatureCollection de `LineString`, com propriedades reais `rodovia`/`via`, `km_inicio`, `km_fim` (sinônimos aceitos). Não importa MultiLineString ambiguamente nem dados sem ambos os marcos.

O resultado é apenas um **candidato** para revisão, pois o km pode não coincidir linearmente com a geometria acumulada. Para precisão de 10 metros é indispensável confirmar coordenada GPS física do equipamento.

## Fluxo B — municípios e endereço georreferenciado (IBGE)

Importe o catálogo municipal IBGE, porque nome de município sem seu código não deve ser tratado como identidade inequívoca.

```bash
# Obtém a relação de municípios da API IBGE; grava JSON bruto no cache
python -m radarbrasil.georesolver baixar-municipios-ibge --cache /var/cache/radarbrasil/municipios_ibge.json

# Alternativa OFFLINE: CSV com codigo_ibge;nome;uf
python -m radarbrasil.georesolver importar-municipios --arquivo /dados/municipios_ibge.csv
```

Fonte oficial: https://servicodados.ibge.gov.br/api/v1/localidades/municipios

Baixe os arquivos oficiais do CNEFE por município ou UF:
https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/

Exemplo:

```bash
python -m radarbrasil.georesolver importar-cnefe \
  --arquivo /dados/4104808_CASCAVEL.csv --municipio-ibge 4104808
```

Compatível com o cabeçalho IBGE `COD_MUNICIPIO;NOM_TIPO_SEGLOGR;NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE;COD_UNICO_ENDERECO;NV_GEO_COORD`. Pode receber CSV UTF-8 ou ZIP contendo 1 CSV. Não copia todos os domicílios para o DB: percorre os arquivos e só registra endereços que possam ser associados com ponto cadastrado que tenha logradouro, número e município IBGE.

**Se o cadastro de origem tiver apenas descrição textual sem número, não é permitido atribuir uma coordenada exata com o CNEFE.** Para casos ambíguos o sistema registra `ambiguos`, não escolhe casa aleatória.

## Fluxo C — número de série compartilhado em fontes oficiais

```bash
python -m radarbrasil.georesolver resolver-series
```

Confronta instrumentos com a mesma série e, quando existe equipamento com coordenada oficial e mesmo contexto de via/km ou município, cria um candidato. Séries idênticas de fabricantes diferentes, instrumentos substituídos e radares móveis não são fundidos silenciosamente. É necessário revisar fabricante/modelo/histórico antes de aprovar.

## Fluxo D — OpenStreetMap apenas como candidato secundário

A pedido do mantenedor, consultar OSM é permitido **somente para tentar LOCALIZAR um equipamento que já tenha cadastro oficial**. Não usar o OSM como prova da existência, velocidade regulamentada ou estado do radar. Não importar dados comerciais.

Extrato nacional (offline, sem depender do servidor Overpass em cada consulta):

```bash
sudo apt-get install osmium-tool
wget -c https://download.geofabrik.de/south-america/brazil-latest.osm.pbf
osmium tags-filter brazil-latest.osm.pbf n/highway=speed_camera -o radares_osm.osm.pbf
osmium export radares_osm.osm.pbf -o radares_osm.geojson
python -m radarbrasil.georesolver importar-osm --arquivo radares_osm.geojson --raio 700
```

Atenção: `osmium tags-filter` coleta nós que têm `highway=speed_camera`; outras relações enforcement do OSM exigem tratamento adicional no extrato. O comando não garante todos os radares nacionais.

Consulta pontual on-line, APENAS se o equipamento já tiver uma âncora derivada oficial única:

```bash
python -m radarbrasil.georesolver consultar-osm --ponto-id 123 --raio 700 \
  --cache /var/cache/radarbrasil/overpass
```

`consultar-osm`: serviço HTTPS Overpass definido no código, corpo de resposta limitado, timeout, cache em disco por 24h. Evite disparar milhares de chamadas individuais; para volume nacional utilize o extrato OSM local. As posições OSM ficam em `geo_candidato.status=revisar` e podem exigir cumprimento da licença ODbL caso sejam aproveitadas/publicadas. A base pública derivada exclusivamente de oficiais não deve ficar misturada sem rastreabilidade de licença.

## Resolver em lote e revisar

```bash
python -m radarbrasil.georesolver resolver-tudo \
  --cnefe /dados/cnefe_cascavel.csv \
  --osm /dados/radares_osm.geojson --raio-osm 700

python -m radarbrasil.georesolver relatorio --formato json \
  --arquivo /var/tmp/radar-localizacao.json
python -m radarbrasil.georesolver relatorio --formato csv \
  --arquivo /var/tmp/radar-localizacao.csv
```

O `resolver-tudo` primeiro prepara vínculos antigos, tenta série e KM, depois CNEFE e por último o OSM. **Não há aprovação automática** de candidatos inferidos ou comunitários.

Avalie os candidatos no relatório e escolha conforme evidências oficiais, sem sobrescrever coordenadas originais:

```bash
python -m radarbrasil.georesolver aprovar --candidato 123 \
  --autor 'responsavel_tecnico' --justificativa 'Estudo tecnico e KM verificados manualmente no cadastro oficial'
python -m radarbrasil.georesolver rejeitar --candidato 124 \
  --autor 'responsavel_tecnico' --justificativa 'Referencia divergente do cadastro oficial'
```

No cadastro de instrumentos móveis/portáteis, a aprovação de posição estática de um equipamento é bloqueada: exige vincular explicitamente uma operação e seu período, com fonte adequada. O mesmo número de série pode se deslocar ao longo do tempo.

## API fcgiwrap / PSE

Nginx e `web/api.pse` permanecem configurados conforme o pacote anterior. A API mantém GET e POST e todos os formatos pré-existentes (TXT delimitado, JSON, NDJSON, XML, EDIFACT e DIF), além de:

```http
GET /api/v1/geolocalizacoes?equipamento_id=123&formato=json
GET /api/v1/geolocalizacoes?somente_pendentes=true&limite=100&formato=txt&delimitador=%7C
GET /api/v1/radares?lat=-24.955&lon=-53.455&raio=1000&formato=json
GET /api/v1/ajuda?formato=json
```

`geolocalizacoes`: para cada equipamento retorna `status=localizado|pendente|sem_coordenada`, sua série, pontos cadastrados, coordenadas e candidatos com método, status, score e evidência. O modo TXT deste endpoint utiliza a saída tabular genérica `tipo|id|conteudo_json`; o endpoint normal `/radares` continua com seu contrato fixo de 36 campos. No resultado detalhado de `/radares`, `localizacao_metadados` agora inclui candidatos e aviso quando a posição não é GPS instrumental exato.

**Importante:** consulta de proximidade usa posições aceitas no cadastro. Não considera candidatos em revisão; consulte `/geolocalizacoes` para ver os que ainda não podem entrar na busca radial.

## Critérios de aceitação

1. Rodovia/km sem GPS => cadastro válido, ponto com `posicao_id=NULL` e candidatos derivados se houver trecho calibrado oficial.
2. CNEFE com endereço exato => candidato `cnefe_endereco`; múltiplos endereços incompatíveis => sem escolha automática.
3. OSM aparece como candidato, nunca cria/inativa radar oficial.
4. Distâncias na consulta radial são calculadas por Haversine, sem PostGIS.
5. Medidor portátil não recebe posição permanente por dedução.
6. Nunca preenche `precisao_metros` com valor arbitrário.
7. Os instrumentos sem localização continuam visíveis no relatório e na API.
8. Todas as decisões de promover/rejeitar preservam justificativa, ator e data na tabela `geo_decisao`.
9. Sistema de importação principal (ANTT, DNIT etc.) e formatos da web continuam passando nos testes de regressão.

## Pendências reais e indispensáveis em produção

**(PENDENTE — validação externa, não é falha ignorada):** baixar camadas atuais do SNV/DERs com marcos KM aferíveis; nem toda malha de rodovia possui calibração exata e cada variante de CSV/GeoJSON deve ser conferida antes de habilitar uma fonte. Sem marco, não inferir a coordenada.

**(PENDENTE — extração oficial):** obter coordenada física diretamente para aparelhos cujo cadastro forneça apenas um endereço/quilômetro pouco preciso; pedir planilha georreferenciada ou estudo/levantamento técnico ao órgão. Não existe derivação matemática exata a partir só do número de série.

**(PENDENTE — base CNEFE real):** executar download e importação municipal/estadual em servidor com acesso à internet, verificar cabeçalhos e encoding da versão publicada, validar amostras e níveis de geocodificação.

**(PENDENTE — OSM real):** baixar extrato e conferir quantos POIs estão mapeados. A ausência em OSM não comprova ausência de radar. Não publicar dados de origem OSM em uma base redistribuível sem analisar a ODbL e a separação de licença.

**(PENDENTE — operação nacional):** conciliar cobertura de órgãos responsáveis nas 27 UFs e municípios, validar data e confiabilidade de cada dispositivo antes de declarar cobertura completa, consultar documentação oficial de operação de radares portáteis quando houver.

## Diagnóstico final

`sem_coordenada` = ainda não há fonte/identidade suficientes. É uma resposta honesta; jamais devolver latitude/longitude = 0,0, centróide municipal, geocode aproximado disfarçado de radar ou ponto no marco quilométrico sem informar estimativa. Instrumentos podem continuar sem coordenada exata, e essas pendências devem ser rastreadas para pesquisa manual/documental.
