# Cruzamento de campos e regras de harmonização (10/10/2026)

**Natureza da evidência:** este documento é sobre as **FONTES** (o que cada
origem oficial publica e para onde cada campo vai no modelo canônico). NÃO é
validação de download/importação real de todas as fontes em produção: a
disponibilidade de cada endpoint só se confirma na execução do coletor em
ambiente com acesso à rede. A implementação preserva o payload original
íntegro de cada registro em `REGISTRO_FONTE.payload_original` (T59).

Conectores no nosso projeto (caminhos reais):

| Fonte oficial | Conector | Módulo |
| --- | --- | --- |
| F01 INMETRO/PSIE | `ColetorINMETRO` | `coletor/fontes/inmetro.py` |
| F02 ANTT — cadastro de radares | `ColetorANTT` | `coletor/fontes/antt.py` |
| F03 ANTT — tráfego | — **não há conector** | (a confirmar: só tabela T53 + endpoint `/api/v1/trafego`) |
| F04 DNIT — PNCV | `ColetorDNIT` | `coletor/fontes/dnit.py` |
| F05 PRF — fixos | `ColetorPRFFixos` | `coletor/fontes/prf.py` |
| F06 PRF — portáteis | `ColetorPRFPortateis` | `coletor/fontes/prf.py` |
| F07 PRF — trechos críticos | `ColetorPRFTrechos` | `coletor/fontes/prf.py` |
| F08 DER-SP | `ColetorDERSP` | `coletor/fontes/dersp.py` |
| F09 DER-PR | `ColetorDERPR` | `coletor/fontes/derpr.py` |
| F10 DER-MG | `ColetorDERMG` | `coletor/fontes/dermg.py` |
| F11 Curitiba | — **não implementado** | — |
| F12 Recife | `ColetorRecife` | `coletor/fontes/recife.py` |
| F13 Belo Horizonte | `ColetorPBH` | `coletor/fontes/pbh.py` |
| F14 demais 26 UF / DF / municípios | — **não implementado** | — |
| F15 OSM/Overpass (complementar) | `ColetorOSM` | `coletor/fontes/osm.py` |
| F16 Maparadar (comunitária) | — **não implementado** | — |

Infraestrutura compartilhada do cruzamento:
`coletor/base.py` (cache sha256, staging, snapshot atômico),
`coletor/fontes/normalizacao.py` (normaliza → modelo canônico),
`coletor/fontes/planilha.py` (XLSX/CSV/HTML/PDF sem dependências),
`coletor/fontes/ckan.py` (descoberta de recurso em portais CKAN),
`coletor/agenda.py` + `coletor/tick.py` (periodicidade por fonte),
`core/dedup.py` (candidatos/decisão de duplicidade).

---

## F02 — ANTT, cadastro de radares (dado oficial)

Dicionário:
https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17/resource/5e883dd4-48a6-485a-87b4-146327af3c7f/download/radar_dicionario_dados.pdf
Conjunto: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17

O conector lê JSON **ou** CSV; a URL do arquivo mensal não é fixada
(resolvida pela API CKAN, com fallback). Mapeamento conforme
`coletor/fontes/antt.py` + `coletor/fontes/normalizacao.py`:

| Coluna na fonte | Destino/semântica | Situação |
| --- | --- | --- |
| `Codigo` | `IDENTIFICADOR_EXTERNO` (tipo `id_orgao`) + `IDENTIFICADOR_PONTO` | normalizado |
| `Rodovia` | `VIA.codigo` (tipo via inferido do prefixo) | normalizado |
| `Km` | `PONTO_FISCALIZACAO.km` | normalizado (decimal BR `1.234,5` → `1234.5`) |
| `Latitude` | `POSICAO_GEOGRAFICA.latitude` (`qualidade=oficial`) | normalizado |
| `Longitude` | `POSICAO_GEOGRAFICA.longitude` | normalizado |
| `UF` | casa com `UF.sigla`; **não cria IBGE fictício** | normalizado |
| `Municipio` | texto de município; só persiste como `MUNICIPIO` se houver `CodigoIBGE` | retornado sem IBGE inventado |
| `CodigoIBGE` | `MUNICIPIO.codigo_ibge` (PK) | normalizado quando presente |
| `Sentido` | `FAIXA_FISCALIZACAO.sentido` (+ `sentido_original`) | normalizado com texto original |
| `Pista` | `PONTO_FISCALIZACAO.tipo_pista` + `FAIXA_FISCALIZACAO.descricao` | normalizado |
| `Tipo` / `TipoRadar` | `EQUIPAMENTO.tipo_radar` (fixo/portatil/movel/desconhecido) | classificador de função + original |
| `Situacao` | `SITUACAO_OPERACIONAL` (ativo/inativo/manutencao/suspenso/em_instalacao) | normalizado; nome original preservado |
| `NumeroSerie` | `EQUIPAMENTO.numero_serie` | normalizado |
| `Fabricante` | `ORGANIZACAO` (tipo `fabricante`) | associação relacional |
| `Modelo` | `MODELO_EQUIPAMENTO.nome_modelo` | associação relacional |
| `VelocidadeLeves` | `LIMITE_VELOCIDADE` (categoria `leves`) | normalizado, apenas limite legal |
| `VelocidadePesados` | `LIMITE_VELOCIDADE` (categoria `pesados`) | normalizado, apenas limite legal |
| `Concessionaria` / `Observacao` | vão para `PONTO_FISCALIZACAO.observacoes` + payload | preservado |
| (payload inteiro) | `REGISTRO_FONTE.payload_original` | imutável (sha256) |

Os nomes acima são os do dicionário oficial; o conector aceita variações
(`pick` é case-insensitive e testa aliases). **A coluna real de cada edição
só se confirma baixando o arquivo do mês** — o `dicionario_*.pdf` da versão
vigente deve ser confrontado antes de considerar o mapeamento fechado.

Regras: a designação "redutor"/"controlador" **não** comprova dispositivo
fixo nem operação pontual. Coordenada ausente ⇒ registro preservado em
`REGISTRO_FONTE` e **não posicionado** (sem radar fictício).

## F03 — ANTT, tráfego (conjunto DIFERENTE)

Dicionário:
https://dados.antt.gov.br/dataset/269aebaa-05e7-4d76-a105-408f12bf4094/resource/7d32f5d1-7a5d-403b-8db5-09e7e11addf1/download/dicionario_de_dados_volume_radar.pdf
Conjunto: https://dados.antt.gov.br/dataset/269aebaa-05e7-4d76-a105-408f12bf4094

Colunas publicadas: concessionaria, identificador, rodovia, uf, km_m,
municipio, tipo_de_pista, latitude, longitude, data_da_passagem,
sentido_da_passagem, faixa_da_passagem, velocidade, tipo_de_veiculo,
volume_total.

**Status no nosso projeto:** **não há conector de tráfego** (a confirmar
qualquer importador). O que existe pronto é a estrutura para receber o dado:
tabela `OBSERVACAO_TRAFEGO` (T53) e a consulta `/api/v1/trafego`
(`core/consultas.py` → `buscar_trafego`). O campo `velocidade` da fonte é
**velocidade de passagem/observação, e JAMAIS deve ser usado como limite
regulamentado** — o modelo guarda isso em `OBSERVACAO_TRAFEGO.velocidade_kmh`
/ `velocidade_publicada` separado de `LIMITE_VELOCIDADE`. NUNCA cadastrar
observação de passagem como velocidade regulamentada.

## F04 — DNIT, PNCV

Conjunto: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
Dicionário (PDF):
https://servicos.dnit.gov.br/dadosabertos/dataset/afb1da02-221b-462b-a3e1-1b11dffb495b/resource/fd23a83c-30ac-4bb3-b7a4-7fdc67c8f4a0/download/dicionario-de-dados-controle-de-velocidade.pdf

O conector lê a planilha XLSX/CSV mais recente (a URL datada muda a cada
edição; resolvida por CKAN). Mapeamento conforme `coletor/fontes/dnit.py`:

| Coluna na fonte | Destino | Situação |
| --- | --- | --- |
| `Código Identificação` | `IDENTIFICADOR_EXTERNO` | normalizado |
| `UF` | `UF.sigla` | normalizado |
| `Rodovia` | `VIA.codigo` (prefixo `BR-`) | normalizado |
| `Km` | `PONTO_FISCALIZACAO.km` | normalizado |
| `Município` | `MUNICIPIO` (se houver código) | texto preservado |
| `Faixas` | `PONTO_FISCALIZACAO.tipo_pista` | normalizado |
| `Tipo` (CEV/CEM/REV) | `EQUIPAMENTO.tipo_radar = fixo` + `observacoes` | preservado no texto |
| `Marca / Modelo` | `ORGANIZACAO` (fabricante) + `MODELO_EQUIPAMENTO` | separado por `/` |
| `Coordenadas (Lat/Long)` | `POSICAO_GEOGRAFICA` (`qualidade=oficial`) | normalizado (`"lat, lon"` → float) |
| `Contrato` / `Edital · Lote` / `Cód. ET` / `Cód. EV` | `PONTO_FISCALIZACAO.observacoes` + payload | preservado |

Generalidades documentadas (nomes físicos podem variar entre abas/edições):
UF, rodovia, km, tipo de equipamento (CEV/CEM/REV), faixas controladas,
sentido, código de estudo técnico, código do equipamento, situação.
**Não presumir que o DNIT publique velocidade regulamentada** nessa planilha
— o conector não grava `LIMITE_VELOCIDADE` para esta fonte. Sem coordenada,
o registro é preservado e **não posicionado**.

## F05 — PRF, radares fixos

https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos

A página gov.br **não** traz a tabela no HTML: embute iframes
(`MAPA DE RADARES FIXOS`) que montam a tabela por JavaScript a partir de um
Google Apps Script (JSON). O conector (`ColetorPRFFixos`) segue o iframe do
mapa → extrai a URL do Apps Script → baixa o JSON. Também aceita tabela HTML
estática (testes). Campos observados (fixture `tests/fixtures/novos/prf_fixos.json`):
`IDENTIFICADOR`, `UF`, `MUNICÍPIO`, `BR`, `LOCAL` (km), `SENTIDO`, `FAIXAS`,
`MARCA`, `MODELO`, `EQUIPAMENTO`, `CONCESSIONÁRIA`, `TIPO EQUIPAMENTO`,
`ESTADO`, `LATITUDE`, `LONGITUDE`, `VELOCIDADE LEVE`, `VELOCIDADE PESADO`,
`VALIDADE DO CERTIFICADO`, `Estudo Técnico`.

Mapeamento: `IDENTIFICADOR` → `IDENTIFICADOR_EXTERNO` (tipo
`codigo_equipamento`); `BR`+`LOCAL` → `VIA`/`PONTO_FISCALIZACAO.km`;
`TIPO EQUIPAMENTO` → função (controlador/redutor/misto);
`ESTADO` → situação; `VELOCIDADE LEVE/PESADO` → `LIMITE_VELOCIDADE`;
`MARCA`/`MODELO` → fabricante/modelo; `CONCESSIONÁRIA`/`VALIDADE`/`Estudo` →
observações. `FAIXAS` entra como `quantidade_faixas_declarada`.

Pode haver identificadores administrativos distintos associados ao mesmo
número de série, mas isso isolado **NÃO** comprova duplicidade sem fabricante
e histórico. A relação usa link oficial de tabela dinâmica; se o link mudar,
o conector falha com mensagem explícita.

## F06 — PRF, radares portáteis

https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/lista-de-radares

Três `<table>` estáticas; a maior lista `IDENTIFICADOR DO EQUIPAMENTO` e
`Nº DE SÉRIE`. **Não há posição nem hora** (spec F06): o conector grava
`EQUIPAMENTO.numero_serie`, `IDENTIFICADOR_EXTERNO` (administrativo) e deixa
`POSICAO_GEOGRAFICA` ausente de propósito (`posicao_confirmada = False`).
Identificador administrativo **≠** número de série.

## F07 — PRF, trechos críticos

https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/trechos-criticos

A página lista planilhas publicadas do Google ("Lista válida a partir de
..."). O conector pega a mais recente e lê a exportação CSV
(`output=csv`). Colunas: `ESTADO (UF)`, `RODOVIA (BR)`, `KM INICIAL`,
`KM FINAL` → gravadas em `TRECHO_ELEGIVEL` (T30), **nunca** como operação
confirmada nem radar instalado (`radar_instalado_confirmado = NULL`,
`indicador = pode_haver_fiscalizacao`). **Trecho crítico não implica radar
instalado ou operação com horário confirmado.**

## F01 — INMETRO / PSIE (medidores)

Portal: https://servicos.rbmlq.gov.br/
Consulta: https://servicos.rbmlq.gov.br/Instrumento (HTML + reCAPTCHA)
Orientação oficial:
https://www.gov.br/inmetro/pt-br/acesso-a-informacao/perguntas-frequentes/metrologia-legal/medidor-de-velocidade-radar/como-obter-acesso-ao-certificado-de-verificacao-dos-medidores-de-velocidade
Catálogo dados.gov.br:
https://dados.gov.br/dados/conjuntos-dados/portal-de-servicos-do-inmetro-nos-estados-psie

A consulta `/Instrumento` usa POST + reCAPTCHA (**não automatizável de forma
legítima** — não contornar). O conector usa o conjunto **estático por UF**
`https://servicos.rbmlq.gov.br/dados-abertos/{UF}/medidores.json`
(sem CAPTCHA). Modelo do arquivo (por registro = um instrumento):

```
SiglaUf, Estado, Municipio, LocalVerificacao,
DataUltimaVerificacao, DataValidade, UltimoResultado, TipoMedidor,
Faixas[].{NumeroFaixa, NumeroInmetro, NumeroSerie, Sentido, VelocidadeNominal},
Historico[].{NumeroCertificado, NumeroEnsaio, Ano, DataLaudo, DataValidade,
             TipoServico, Resultado},
Proprietario.{Nome, Municipio, Estado}
```

Mapeamento (`coletor/fontes/inmetro.py`): `NumeroInmetro` →
`IDENTIFICADOR_EXTERNO` (tipo `numero_inmetro`); `NumeroSerie` →
`EQUIPAMENTO.numero_serie`; sentidos das faixas → `FAIXA_FISCALIZACAO`
(múltiplos sentidos = `ambos`); `VelocidadeNominal` **só** vira
`LIMITE_VELOCIDADE` quando **todas** as faixas concordam (divergência não
gera velocidade inventada). **`LocalVerificacao` é texto livre** (ex.:
"BR 364 KM 123,830") — o conector **não** cria via/km nem coordenada a partir
dele; `POSICAO_GEOGRAFICA` fica ausente (`qualidade = nao_confirmada`). O
histórico metrológico **não** vira situação operacional (spec 11.6). O
endpoint por UF foi validado como recurso público; a cobertura e a
atualidade devem ser reconferidas a cada execução.

## F08/F09/F10/F12/F13 — estaduais e municipais

- **DER-SP** (`ColetorDERSP`): dataset CKAN
  https://dadosabertos.sp.gov.br/dataset/radar → XLSX. Campos: `Código`,
  `Coordenadas`, `Município`, `Rodovia`, `Km`, `Tipo`, `Tipo da Rodovia`,
  `Faixas`, `Marca/Modelo`, `Operadora`, `Início Operação`, `Cancelamento`.
  Sem coordenada ⇒ não posiciona.
- **DER-PR** (`ColetorDERPR`): página
  https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade → PDF por
  concessionária (fixo). Relatório tabular (concessionária, tipo, série,
  identificação, município, rodovia, `km+metros`, registro IPEM/PR, datas).
  **Sem coordenada** → `POSICAO_GEOGRAFICA` ausente; `km` = km + metros/1000.
  A página de **portátil** não publica arquivo baixável (limitação registrada).
- **DER-MG** (`ColetorDERMG`): página
  https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis
  → tabela HTML (`URG`, `Rodovia`, `km`, `Município`, `Velocidade`, `Nº do
  Equipamento`, `Nº de Série`, datas e responsáveis). **Sem coordenadas**;
  um registro pode listar VÁRIOS números/séries — o conector **não** assume
  correspondência 1:1 (`numero_serie` só quando há série única; senão vai
  para observações). Velocidade: maior→leves, menor→pesados (regra da fonte).
- **Recife** (`ColetorRecife`): CKAN
  https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito
  → CSV. Publica **uma** velocidade fiscalizada (sem separar leve/pesado):
  vai como `velocidade_geral`. `bairro` → observações.
- **Belo Horizonte** (`ColetorPBH`): CKAN
  https://dados.pbh.gov.br/pt_BR/dataset/fiscalizacao-eletronica → CSV mensal.
  A coluna `GEOMETRIA` traz ponto projetado (EPSG:31983 = SIRGAS 2000 / UTM
  23S); o conector converte para graus decimais com matemática da stdlib
  (sem `pyproj`). `DESC_TIPO_CONTROLADOR_TRANSITO`, `VELOCIDADE_REGULAMENTAR`,
  `SENTIDO`(FISCALIZADO), `NUM_SERIE_ATUAL`.

Nesta versão **não** há conectores para **Curitiba (F11)**, **demais 26 UF /
DF / municípios (F14)** nem para a base comunitária **Maparadar (F16)**. A
cobertura nacional é **PARCIAL**. **A ausência de resultado NÃO prova
ausência de fiscalização.**

## F15 — OpenStreetMap / Overpass (complementar, NÃO oficial)

`ColetorOSM`: Overpass API (`highway=speed_camera`; `enforcement=maxspeed`).
Base colaborativa (ODbL 1.0). Serve para **sugerir** pontos candidatos e
complementar posição, com qualidade marcada e nunca como confirmação
governamental. Câmeras de semáforo / luz vermelha (`traffic_signals`,
`red_light_camera`) **não** são radares de velocidade e são descartadas. O
ID do OSM é guardado como `osm:<node|way|relation>/<id>`. fonte **desligada
por padrão** na agenda (`ativo: False`, opt-in).

---

## Duplicidade, fonte e confiança

Regras aplicadas (spec §8 / §17.4), coerentes com `core/dedup.py`:

1. Identificador oficial pode identificar um **ponto**, um **equipamento** ou
   uma **faixa**; a origem determina o escopo.
2. Número de série identifica instrumento **somente com contexto** de
   fabricante/modelo. Coincidência isolada gera **candidato**, não certeza.
3. Coordenadas próximas + mesma rodovia/km podem identificar **UM PONTO** e
   **DOIS instrumentos** — sem confundir ponto com equipamento.
4. Não fundir sentidos opostos se as evidências apontarem dispositivos
   físicos distintos.
5. Múltiplas faixas com mesmo instrumento **não** constituem radares físicos
   duplicados.
6. Guardar todos os registros originais e seus hashes, datas e URLs
   (`ARTEFATO_COLETA` T57, `REGISTRO_FONTE` T59).
7. Limites distintos para mesma categoria/faixa geram **conflito explícito**;
   não arbitrar um valor (`DECISAO_VALOR_CANONICO` T73).
8. Dados não mapeados continuam disponíveis no payload original exposto no
   retorno detalhado (`CATALOGO_CAMPO` T71 / `VALOR_OBSERVADO` T72).
9. Dados que exigem confirmação de origem ou API são marcados como **não
   validados**, nunca simulados.

## Referências externas de engenharia (não são fontes oficiais)

- https://github.com/GabrielHiro/consulta-instrumentos-INMETRO (dados de
  exemplo; não comprova integração oficial)
- https://github.com/zyadhpl/velox (OSM/Overpass)
- https://github.com/tomsnunes/peugeot_citroen_rt6_maparadar_updater
  (conversão de radares e direções)
- https://github.com/datascry/alpr2osmand (estratégias de cache; câmeras ALPR
  **não** são radares de velocidade)
