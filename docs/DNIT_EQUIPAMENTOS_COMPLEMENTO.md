# DNIT: complemento da publicacao PNCV pelo portal de multas

Pagina publica: <https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao>.

O arquivo `TabelaEquipamentosFiscalizacao.xlsx` fornecido pelo operador em
22/10/2026 foi gerado por **SheetJS**, conforme as propriedades internas do XLSX.
O navegador pode gerar um endereco `blob:` temporario; esse endereco nao serve
como URL fixa de coleta. O conector abre a pagina publica em Chromium/Chrome e
aciona sua exportacao Excel. Nao depende de Node, Playwright, login ou IA.

**Limite da verificacao:** a pagina real retornou HTTP 503/timeout neste ambiente
em 22/10/2026, inclusive pelo navegador. A exportacao automatizada foi validada
com um download `blob:` real em pagina de teste e o arquivo enviado pelo operador;
o download do portal DNIT ainda precisa ser confirmado em uma rede onde ele
responda. Falha de acesso gera erro de coleta, sem trocar o snapshot bom por vazio
e sem resolver verificacoes humanas. O exportador procura botoes/links visiveis
de Excel/exportacao; mudanca na interface pode exigir ajuste.

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
vencimento independente da planilha PNCV. Para tentar imediatamente, como root:

```sh
python3 web/api.pse sync --fonte dnit_equipamentos
```

Se o portal estiver indisponivel, um XLSX exportado pelo operador pode ser lido:

```sh
python3 web/api.pse sync --fonte dnit_equipamentos --arquivo TabelaEquipamentosFiscalizacao.xlsx
```

O instalador privado prepara Chromium quando nao encontra um navegador compativel.
Nenhum cron adicional e necessario. Fixtures reais ficam em `tests/fixtures/dnit/`.
Os testes usam banco temporario e incluem carga pela API, idempotencia, preservacao
do ID do instrumento, complementacao metrologica e exportacao real de `blob:`.
