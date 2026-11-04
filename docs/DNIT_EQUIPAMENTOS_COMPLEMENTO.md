# DNIT: complemento da publicacao PNCV pelo portal de multas

Pagina publica: <https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao>.

## Coleta atual por HTTP direto — 04/11/2026

A API publica usada pela propria pagina fornece um GeoJSON:

<https://servicos.dnit.gov.br/services-sior/portal-multas/pncv/equipamentos>.

O JavaScript do portal consulta essa URL e seu metodo `downloadTable()` gera
`TabelaEquipamentosFiscalizacao.xlsx` com os mesmos registros. O conector
`dnit_equipamentos` baixa o GeoJSON por `coletor.http`, usando os limites,
retentativas e verificacao HTTPS existentes. Nao precisa de Chromium, Node,
Playwright, login ou IA. A pagina antiga, se passada como origem, e resolvida
para a API. XLSX e GeoJSON locais continuam aceitos pela mesma entrada.

Em 04/11/2026 a chamada por HTTP na rede configurada respondeu 200 com
**1.682 registros**, todos com codigo preenchido e unico. Houve timeout antes
do sucesso: a disponibilidade da origem continua sujeita a falhas de rede.
Esse teste nao equivale a uma sincronizacao ja executada no servidor.

A resposta precisa ser `FeatureCollection` nao vazia, com `Feature`, geometria
`Point`, campos publicados, codigos unicos e coordenadas numericas validas no
Brasil. HTML de erro, mudanca de esquema, dados vazios e coordenadas invertidas
ou invalidas interrompem a coleta. Uma falha nao e substituida por fixture,
arquivo antigo ou tentativa de exportacao pelo navegador.

O artefato bruto e o registro original preservam o GeoJSON, incluindo campos
adicionais da origem. A normalizacao interpreta coordenadas GeoJSON em
**longitude/latitude** e aplica as mesmas regras do XLSX para serie e registro
Inmetro. As duas publicacoes continuam complementando-se pelo codigo DNIT;
nenhum ponto ausente de uma edicao e removido ou declarado desativado.

O nome historico do recurso foi preservado para reutilizar seu ID, historico
de execucoes e artefatos. URL, formato e status de integracao sao atualizados
para a coleta da API, sem migracao de banco ou criacao de uma terceira fonte.

## Validacao no GitHub Actions

O workflow manual `.github/workflows/dnit.yml` executa
`.github/scripts/diagnosticar_dnit.py` com o mesmo conector da instalacao,
sem instalar navegador. Guarda o GeoJSON recebido e `coletor.json`, com URL,
contagem, SHA-256, datas e erro em caso de falha. Nao escreve em banco real e
nao troca erro de rede por uma fixture de sucesso.

Os testes locais cobrem validacao do esquema e da ordem de coordenadas,
independencia do navegador, XLSX local e complemento da PNCV sem duplicacao
de pontos, instrumentos ou recursos.

## Publicacoes historicas usadas nos testes

O XLSX fornecido pelo operador em 22/10/2026 foi gerado por SheetJS. Sua URL
`blob:` era temporaria e nao podia ser usada como arquivo fixo. O conector
anterior acionava a exportacao pela pagina; em 04/11 o servidor registrava
falha ao iniciar o Chromium (`chrome_crashpad_handler: --database is required`).
A coleta atual elimina essa dependencia do DNIT.

A planilha fornecida permanece em `importacoes/dnit/2026-10-22/` no repositorio
privado, com manifesto e hash. O bootstrap continua aceitando a opcao explicita
`--dnit-arquivo CAMINHO.xlsx`. Ela nao serve como substituto automatico de um
download novo e nao e apresentada como consulta atual ao DNIT.

## Dados que se complementam

| Publicacao | Registros | Campos exclusivos relevantes |
|---|---:|---|
| PNCV, julho/2026, ja coletada | 1.774 | Faixas, marca/modelo, contrato, inicio de operacao, estudos ET/EV |
| Exportacao do portal de multas fornecida pelo operador | 1.655 | Serie e registro Inmetro |

Ha 1.631 codigos comuns, 24 exclusivos do portal de multas e 143 exclusivos da
PNCV. Nos 1.631 comuns, UF, municipio, BR, km e coordenadas conferem. A PNCV
publica latitude/longitude; a exportacao do portal publica **longitude/latitude**.
O coletor diferencia os formatos pelo cabecalho e nao adivinha a ordem pelo sinal.
Coordenadas incompatíveis com o formato brasileiro geram rejeicao do registro.

As duas publicacoes pertencem a mesma fonte DNIT e possuem recursos/artefatos
separados. A chave do ponto continua sendo o codigo DNIT, com o mesmo tipo de
identificador usado nas cargas anteriores. A carga conjunta produz **1.798 pontos**,
sem apagar os 143 ausentes da exportacao e sem presumir desativacao/validade atual.
O material e federal e nao entra nas contagens exclusivamente estaduais/municipais.

Um cadastro sem serie pode receber identificacao quando codigo oficial, municipio,
BR e km coincidem e ha um unico instrumento compativel. Series conhecidas
divergentes, certificados anteriores, locais divergentes, ambiguidades e decisoes
de revisao nao sao sobrescritos. Uma republicacao PNCV sem serie conserva o
instrumento ja identificado. Os campos brutos e as origens permanecem consultaveis.

`0`, `nao informado`, nomes de fabricantes no campo Inmetro e outras formas nao
reconhecidas permanecem somente no original. Series multiplas nao viram uma
serie artificial. Registro Inmetro e identificador secundario do instrumento,
nao numero de certificado; a verificacao continua exigindo evidencia metrologica.

## Coleta pelo ponto de entrada existente

O recurso `dnit_equipamentos` entra na agenda semanal do `api.pse tick`, com
vencimento independente da planilha PNCV. Para tentar imediatamente, como root, na raiz da instalacao:

```sh
runuser -u www-data -- ./api.pse sync --fonte dnit_equipamentos
```

Um XLSX ja exportado pelo operador pode ser importado explicitamente (o arquivo deve ficar dentro de `[dados] dir`):

```sh
runuser -u www-data -- ./api.pse sync --fonte dnit_equipamentos --arquivo TabelaEquipamentosFiscalizacao.xlsx
```

O instalador privado prepara Chromium quando nao encontra um navegador compativel.
Nenhum cron adicional e necessario. Fixtures reais ficam em `tests/fixtures/dnit/`.
Os testes usam banco temporario e incluem carga pela API, idempotencia, preservacao
do ID do instrumento, complementacao metrologica e exportacao real de `blob:`.
