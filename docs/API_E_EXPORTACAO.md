# API de consulta e exportação

A consulta pública é aberta. A base atual é consultada localmente; uma requisição
de leitura não dispara downloads de portais externos.

**Endereço da API:** <https://servidor3.lucas.inf.br/openclaw/radar/api.pse>

**Ajuda gerada pelo próprio código:**
<https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/ajuda&formato=json>

Nesta instalação, selecione o endpoint pelo parâmetro `rota`. Isso funciona com
o CGI genérico e não exige outra configuração no nginx.

## Consulta rápida de radares

[Exemplo em JSON](https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-16.32712&lon=-51.35782&raio=2000&formato=json)
· [NDJSON](https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-16.32712&lon=-51.35782&raio=2000&formato=ndjson)
· [XML](https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-16.32712&lon=-51.35782&raio=2000&formato=xml)
· [TXT](https://servidor3.lucas.inf.br/openclaw/radar/api.pse?rota=/api/v1/radares&lat=-16.32712&lon=-51.35782&raio=2000&formato=txt)

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' \
  --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'raio=2000' \
  --data-urlencode 'formato=json'
```

`lat` e `lon` são graus decimais WGS84. `raio` está em **metros**: `2000` significa
2 km. O intervalo aceito é de 1 a 1.000.000 metros (1000 km); padrão de 1000 metros.
Use ponto decimal nas consultas. As vírgulas aceitas pelo formulário não mudam
o contrato desses parâmetros da API.

## Endpoints de leitura

| Endpoint em `rota` | Uso |
| --- | --- |
| `/api/v1/radares` | Radares em torno de latitude/longitude, com raio e filtros. |
| `/api/v1/radares/{id}` | Detalhe de um ponto, por exemplo `P-604`. |
| `/api/v1/radares/busca` | Busca cadastral por UF, município ou rodovia, sem exigir GPS. |
| `/api/v1/equipamentos/{id}` | Equipamento físico, por exemplo `E-604`. |
| `/api/v1/fontes` e `/api/v1/fontes/{id}` | Fontes e recursos de origem. |
| `/api/v1/atualizacoes` | Histórico das execuções de coleta. |
| `/api/v1/operacoes` | Operações de fiscalização publicadas. |
| `/api/v1/trechos` | Trechos elegíveis para fiscalização portátil. |
| `/api/v1/trafego` | Observações de tráfego; velocidade observada não é limite da via. |
| `/api/v1/status` | Estado da base, versão e cobertura. |
| `/api/v1/ajuda` | Parâmetros, campos, formatos e erros, gerados do código. |
| `/api/v1/status/estados` e `/api/v1/status/estados/{uf}` | Contagens e detalhes por estado, em JSON. |
| `/api/v1/status/coletores` | Estado dos leitores e URLs, em JSON. |
| `/api/v1/atualizacoes/status` | Relatório consolidado das atualizações, em JSON. |
| `/health/live` e `/health/ready` | Sinais de vida e prontidão, em JSON. |

Os IDs dependem da base consultada; os exemplos não reservam um ID específico.

### Parâmetros de `/radares`

| Parâmetro | Significado |
| --- | --- |
| `lat`, `lon` | Obrigatórios; latitude -90..90, longitude -180..180. |
| `raio` | Inteiro de 1 a 1.000.000, em metros. |
| `formato` | `json`, `ndjson`, `xml`, `txt`, `dif`, `edi` ou `edifact`. Padrão `json`. |
| `limite` | Itens por página: 1..1000; padrão 100. |
| `cursor` | Cursor opaco devolvido na página anterior; envie com URL encoding. |
| `uf` | Sigla, por exemplo `GO`. |
| `municipio_ibge` | Código IBGE do município, com 7 dígitos. |
| `rodovia` | Código da via, por exemplo `GO-060` ou `BR-277`. |
| `tipo_radar` | Tipo cadastrado: `fixo`, `portatil`, `movel`, `desconhecido`. |
| `sentido` | Código cadastrado do sentido. |
| `modalidade` | Código cadastrado da modalidade de fiscalização. |
| `fiscalizacao_pontual` | Booleano; registros sem essa informação ficam fora do filtro explícito. |
| `incluir_inativos` | Booleano; padrão `false`. |
| `incluir_operacoes` | Booleano; padrão `true`. |
| `incluir_trechos` | Booleano; padrão `false`; devolve coleção separada. |
| `delimitador` | Um caractere, somente no TXT; padrão `\|`. |

Use `true`/`false` nos parâmetros booleanos. A ajuda pública informa os domínios
e a lista completa das opções de cada endpoint.

### Busca sem coordenadas

Use `/api/v1/radares/busca` para consultar cadastros de um estado ou município,
incluindo registros cuja fonte não publicou GPS:

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares/busca' \
  --data-urlencode 'uf=GO' \
  --data-urlencode 'limite=1000' \
  --data-urlencode 'formato=json' \
  --output goias-pagina-1.json
```

Para consultar todo o cadastro disponível, use a busca sem filtro de UF e
percorra as páginas. Uma consulta por raio não cobre automaticamente o Brasil.

## Formatos de exportação

A seleção é feita por `formato=...`, e não pelo nome da extensão do arquivo.

| `formato` | Content-Type | Estrutura de `/radares` |
| --- | --- | --- |
| `json` | `application/json; charset=utf-8` | Envelope com metadados e `resultado.pontos`. |
| `ndjson` | `application/x-ndjson; charset=utf-8` | Uma linha de metadados, um ponto por linha e uma linha de fechamento. |
| `xml` | `application/xml; charset=utf-8` | Raiz `radar_brasil`, metadados e `resultado/pontos/ponto`. |
| `txt` | `text/plain; charset=utf-8` | Uma linha por ponto; 32 colunas fixas, sem cabeçalho, delimitador configurável. |
| `dif` | `text/plain; charset=utf-8` | Data Interchange Format; mesmas 32 colunas do TXT. |
| `edi` ou `edifact` | `application/EDIFACT; charset=utf-8` | Mensagem no perfil bilateral EDIFACT do projeto. São aliases. |

A exportação mantém dados estruturados de equipamento, faixas, velocidades,
fontes e documentos. Um ponto pode conter mais de um equipamento: não trate a
contagem de linhas de pontos como número de instrumentos físicos.

### JSON

Dados estão em `resultado.pontos`; os demais campos descrevem a consulta, a base,
a paginação e a cobertura. Campos ausentes usam `null` quando apropriado.

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'raio=2000' --data-urlencode 'formato=json' \
  --output radares.json
```

### NDJSON: como ler corretamente

Em `/api/v1/radares` e `/api/v1/radares/{id}`, **cada linha é um JSON completo**.
O arquivo inteiro não é um único array JSON. Exemplo reduzido da estrutura:

```ndjson
{"tipo_registro":"meta","sucesso":true,"resultado":{"retornados":1,"proximo_cursor":null,"status":"parcial"},"base":{},"cobertura":{}}
{"tipo_registro":"ponto_fiscalizacao","id":"P-123","localizacao":{"latitude":-16.32712,"longitude":-51.35782},"equipamentos":[]}
{"tipo_registro":"fechamento","retornados":1}
```

- `meta`: consulta, versão, cobertura, base e `resultado.proximo_cursor`.
- `ponto_fiscalizacao`: um radar/ponto por linha, com suas coleções internas.
- `fechamento`: número de pontos efetivamente devolvidos nesta página.

Mesmo uma página sem pontos tem as linhas `meta` e `fechamento`. Ao juntar
páginas, haverá um par de metadados/fechamento por página. O consumidor distingue
as linhas por `tipo_registro`.

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'raio=2000' --data-urlencode 'formato=ndjson' \
  --output radares.ndjson
```

Leitura em Python, sem carregar todas as linhas na memória do consumidor:

```python
import json

with open("radares.ndjson", encoding="utf-8") as arquivo:
    for linha in arquivo:
        registro = json.loads(linha)
        tipo = registro.get("tipo_registro")
        if tipo == "meta":
            proximo_cursor = registro["resultado"].get("proximo_cursor")
        elif tipo == "ponto_fiscalizacao":
            print(registro["id"], registro.get("localizacao"))
        elif tipo == "fechamento":
            print("Pontos nesta página:", registro["retornados"])
```

**Diferença importante entre endpoints:** a busca cadastral `/radares/busca` e os
endpoints tabulares como `/atualizacoes`, `/trechos` e `/operacoes` usam atualmente
NDJSON de envelope: uma linha JSON com a coleção dentro de `resultado`, em vez
de linhas `meta`/ponto/fechamento. Ajuda e status também serializam o objeto
inteiro em uma linha. Use o contrato do endpoint consultado ao escrever o leitor.

### XML

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'formato=xml' --output radares.xml
```

O XML usa UTF-8, valores nulos como `xsi:nil="true"` e coleções aninhadas. Em
`/radares`, os pontos ficam em `resultado/pontos/ponto`. Não obtenha XML por
substituição de texto sobre JSON: use o serializador da API.

### TXT delimitado e importação em planilha

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'formato=txt' --data-urlencode 'delimitador=;' \
  --output radares.txt
```

São **32 colunas, sem linha de cabeçalho**, com uma linha física por ponto:

- `\N` sem aspas representa nulo; a string literal `\N` vem entre aspas.
- Aspas internas são duplicadas; células contendo o delimitador ficam entre aspas.
- Quebras de linha internas são representadas por `\r` e `\n` literais.
- Coleções/objetos ficam em células com JSON compacto.

A ordem das colunas é fixa e está na tabela abaixo e na ajuda da API. Para
importar como CSV, use `formato=txt&delimitador=,` ou `;`, informando ao leitor
que não há cabeçalho. **Não existe `formato=csv` nem `formato=xlsx`** nesta API.
Salvar o TXT como `.csv` não muda as regras de nulos e células JSON.

| Posição | Coluna | Significado |
| --- | --- | --- |
| 1 | `id` | Identificador canonico do ponto (PK da API). |
| 2 | `tipo_registro` | Sempre 'ponto_fiscalizacao'. |
| 3 | `situacao_operacional` | Estado operacional (nao e validade metrologica). |
| 4 | `latitude` | Latitude WGS84 (graus). |
| 5 | `longitude` | Longitude WGS84 (graus). |
| 6 | `distancia_metros` | Distancia calculada ao ponto consultado (Haversine). |
| 7 | `precisao_metros` | Precisao declarada da posicao, em metros. |
| 8 | `uf` | Sigla da UF. |
| 9 | `municipio` | Nome do municipio. |
| 10 | `codigo_ibge` | Codigo IBGE (7 digitos) do municipio. |
| 11 | `via_codigo` | Codigo da via/rodovia. |
| 12 | `km` | Marcador quilometrico da via. |
| 13 | `tipo_pista` | Tipo de pista conforme a fonte. |
| 14 | `tipos_radar_presentes_json` | JSON: tipos de radar presentes no ponto. |
| 15 | `fiscalizacao_pontual` | Triestado derivado: true/false/null. |
| 16 | `regimes_json` | JSON: regimes de fiscalizacao. |
| 17 | `faixas_json` | JSON: faixas de fiscalizacao. |
| 18 | `limites_velocidade_json` | JSON: limites de velocidade. |
| 19 | `equipamentos_json` | JSON: equipamentos instalados. |
| 20 | `operacoes_json` | JSON: operacoes publicadas. |
| 21 | `documentos_json` | JSON: documentos oficiais. |
| 22 | `fontes_json` | JSON: proveniencia/publicacao. |
| 23 | `conflitos_json` | JSON: conflitos entre fontes. |
| 24 | `confianca` | alta/media/baixa/conflitante/nao_avaliada. |
| 25 | `atualizacao_json` | JSON: marcos temporais de atualizacao. |
| 26 | `endereco_json` | JSON: endereco estruturado. |
| 27 | `organizacoes_json` | JSON: organizacoes e papeis. |
| 28 | `localizacao_metadados_json` | JSON: qualidade/metodo da posicao. |
| 29 | `observacoes` | Observacoes textuais. |
| 30 | `proveniencia_campos_json` | JSON: proveniencia por campo. |
| 31 | `estado_temporal_json` | JSON: inicio/inativacao/motivo/situacao original. |
| 32 | `quantidade_faixas_declarada` | Contagem agregada publicada (sem inventar faixas). |

### DIF e EDI/EDIFACT

Troque o parâmetro `formato` para `dif`, `edi` ou `edifact`:

```sh
curl --fail --get 'https://servidor3.lucas.inf.br/openclaw/radar/api.pse' \
  --data-urlencode 'rota=/api/v1/radares' \
  --data-urlencode 'lat=-16.32712' --data-urlencode 'lon=-51.35782' \
  --data-urlencode 'formato=dif' --output radares.dif
```

DIF tem cabeçalho de tabela e mantém nulos por `NA`. EDI/EDIFACT usa o perfil
bilateral definido em [seu serializador](../core/serializers/edifact_ser.py), com
campos e escapes específicos. Integrações EDIFACT precisam combinar esse perfil
com o consumidor. Para paginação, processe cada documento; concatenar arquivos
DIF/EDIFACT completos não produz automaticamente uma única tabela/mensagem válida.

## Paginação e exportação de todas as páginas

`limite=1000` limita uma página, não o conjunto inteiro. Leia
`resultado.proximo_cursor`; enquanto não for `null`, envie esse cursor na próxima
requisição, mantendo os mesmos filtros. O cursor é opaco: não calcule, decodifique
ou substitua por um número de página. Use URL encoding.

Exemplo completo: exportar o cadastro disponível de Goiás como um ponto JSON
por linha, percorrendo a busca cadastral em JSON e produzindo NDJSON no cliente:

```python
import json
from urllib.parse import urlencode
from urllib.request import urlopen

api = "https://servidor3.lucas.inf.br/openclaw/radar/api.pse"
parametros = {"rota": "/api/v1/radares/busca", "uf": "GO", "limite": 1000, "formato": "json"}

with open("goias.ndjson", "w", encoding="utf-8") as destino:
    while True:
        with urlopen(api + "?" + urlencode(parametros), timeout=60) as resposta:
            pagina = json.load(resposta)
        if not pagina.get("sucesso"):
            raise RuntimeError(pagina.get("erro"))
        for ponto in pagina["resultado"]["pontos"]:
            destino.write(json.dumps(ponto, ensure_ascii=False) + "\n")
        cursor = pagina["resultado"].get("proximo_cursor")
        if cursor is None:
            break
        parametros["cursor"] = cursor
```

Esse arquivo do cliente contém apenas pontos. Ele é diferente da exportação
NDJSON nativa de `/radares`, que inclui metadados e fechamento.

## Status, cobertura e erros

Uma consulta válida sem pontos devolve HTTP 200. Confira o resultado e a cobertura:

- `resultado.encontrado`, `total_pontos`, `total_equipamentos` e `retornados`.
- `resultado.status`: a busca pode ser `parcial` ou `sem_cobertura`.
- `cobertura.completude_confirmada`: não presuma que é `true` só porque houve resultado.
- `base`: snapshot, versão e informação de atualização disponíveis.

Os cabeçalhos `X-Radar-Snapshot-ID`, `X-Radar-Base-Updated-At`,
`X-Radar-Cache-Age-Seconds`, `X-Radar-Coverage-Status`, `X-Radar-Total-Points`,
`X-Radar-Total-Equipment` e `X-Radar-Response-Schema-Version` também ajudam a
auditar a resposta, especialmente no TXT. As contagens de cabeçalho não substituem
a paginação descrita acima.

Erros de parâmetros usam HTTP 400/422; ponto inexistente usa 404; base indisponível
usa 503. O corpo de erro é JSON (`sucesso=false`, objeto `erro`), mesmo se você
solicitou outro formato. Verifique HTTP e Content-Type antes de interpretar um
arquivo como exportação bem sucedida.

## Escrita e rede são operações diferentes

- `/api/v1/radares/submeter`: contribuição pública. Com `Prefer: respond-async`,
  retorna 202/protocolo; veja [fila de cadastros](FILA_CADASTROS.md).
- `/api/v1/gestao/*`: sessão ou token de gestão e escopo apropriado.
- POST de ingestão autenticada: veja a ajuda e o contrato de escrita; não é
  necessário para baixar a base pública.
- Troca entre sistemas: [Intercâmbio de Instâncias](INTERCAMBIO_INSTANCIAS.md).
- Rede de radares: [TRASEIRO DE URSO](TRASEIRO_DE_URSO.md).
