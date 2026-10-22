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

### Investigacao da coleta e da instalacao em 22/10

O status publico do servidor, atualizado as 21:08 UTC, mostrou que o bootstrap
de 21:06 UTC recusou o link `status-atualizacoes.json` na pasta web. Assim,
o exportador corrigido anteriormente ainda nao estava instalado: o erro do
DNIT continuava sendo a tentativa X-358 das 17:54 UTC, com timeout apos 90 s.
A validacao do instalador foi corrigida para aceitar esse link apenas quando
leva ao relatorio persistente configurado, incluindo a cadeia pelo diretorio
do aplicativo. A verificacao de permissoes tambem o preserva durante a troca
dos fontes. Outros destinos continuam recusados.

Ha uma etapa anterior a exportacao que o conector nao acionava: **Mostrar
Tabela**. Esse fluxo foi identificado tambem em um
[coletor publico independente](https://github.com/patarruda/if697_acidentesPRF/blob/HEAD/radares_scrapTable.py).
Agora o conector DNIT abre a tabela antes de procurar o Excel. O teste com
navegador real so disponibiliza a exportacao depois desse clique.

O workflow manual `.github/workflows/dnit.yml` verifica o **portal real** em
separado dos testes locais. Guarda captura de tela, controles visiveis, status
de rede, falhas JavaScript e scripts publicos do proprio DNIT; executa o mesmo
conector da instalacao e confere todas as linhas recebidas. O XLSX baixado
fica no artefato, sem importar em producao. Falha externa reprova a verificacao;
ela nunca usa a fixture como substituto de um download atual.

Resultado do [teste externo de 22/10, 21:13 UTC](https://github.com/Challado/Bunda-de-Urso/actions/runs/39855409278):
o navegador do GitHub nao recebeu resposta HTTP do DNIT em 45 s; depois, o
conector tambem esgotou seus 90 s durante a navegacao inicial. Nao houve HTML,
script ou XLSX recebido. Portanto, a coleta online continua **nao confirmada**.
Timeout de socket agora tambem inclui contexto no erro registrado, em vez de
apenas `TimeoutError: timed out`; ha um teste com servidor que nao responde.

O teste Chromium no Actions tambem revelou uma corrida na inicializacao:
`DevToolsActivePort` podia existir vazio ou com apenas a porta, causando
`ValueError` antes de navegar. O coletor agora espera as duas linhas completas
e validas dentro do prazo original. Um teste reproduz essas escritas parciais;
o encerramento do processo continua garantido em caso de falha.

Para permitir a complementacao sem depender dessa disponibilidade, a planilha
exatamente como fornecida pelo operador fica em `importacoes/dnit/2026-10-22/`
no repositorio privado, com manifesto de origem e SHA-256. O bootstrap aceita
`--aplicar --dnit-arquivo CAMINHO.xlsx`: primeiro instala e verifica, depois
importa pela API e registra a etapa. A opcao e explicita; nunca e acionada como
substituto silencioso de um download. O teste do bootstrap importa as 1.655
linhas sem rejeicoes e repete sem duplicacao. A data original da exportacao
nao foi confirmada e nao e apresentada como uma consulta atual ao DNIT.

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
/openclaw/bin/radar-api.pse sync --fonte dnit_equipamentos
```

Se o portal estiver indisponivel, um XLSX exportado pelo operador pode ser lido:

```sh
/openclaw/bin/radar-api.pse sync --fonte dnit_equipamentos --arquivo TabelaEquipamentosFiscalizacao.xlsx
```

O instalador privado prepara Chromium quando nao encontra um navegador compativel.
Nenhum cron adicional e necessario. Fixtures reais ficam em `tests/fixtures/dnit/`.
Os testes usam banco temporario e incluem carga pela API, idempotencia, preservacao
do ID do instrumento, complementacao metrologica e exportacao real de `blob:`.
