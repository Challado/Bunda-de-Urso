# Testes de navegador do cadastro

O workflow [Navegadores](https://github.com/Challado/Bunda-de-Urso/actions/workflows/navegadores.yml)
roda em cada push na `main`, pull request e execução manual. Há jobs separados
para Firefox e Chromium, com perfis desktop e tela estreita/toque. Uma falha
reprova o job, sem repetição automática para esconder intermitências.

Os testes abrem o formulário real em `/openclaw/radar/cadastro.html`, no mesmo
formato de subdiretório da instalação. Cada teste recebe um servidor e banco
SQLite temporários novos. O servidor executa `api.pse` como CGI, sem `PATH_INFO`,
e inicializa uma fonte oficial pela própria API local. Não consulta produção,
não exige chave de IA e não deixa um endpoint de teste no aplicativo.

## Cobertura

- Simplificado: somente latitude, longitude e velocidade, incluindo vírgula decimal.
- Confirmação do cadastro pela leitura da API, complemento por proximidade e
  preservação da velocidade/coordenada do oficial.
- Reenvio idêntico retorna o mesmo cadastro e não cria duplicata.
- Expert sem GPS e retorno ao simples sem enviar campos escondidos.
- Campos obrigatórios/inválidos não geram requisição.
- GPS negado permite preencher e enviar manualmente.
- Falha de rede e HTTP 503 liberam o botão e mantêm os campos.
- API grava, mas a resposta não chega: em 20 segundos a espera termina;
  repetir confirma o mesmo cadastro. Resposta atrasada não substitui o resultado
  da segunda tentativa. Há cobertura também sem `AbortController`.
- Erros JavaScript reprovam; o formulário não deve causar rolagem horizontal.

A interrupção da resposta e os erros de rede/HTTP são simulados pelo teste;
os cenários de sucesso, consulta e reenvio usam o CGI e o banco reais.
O relógio do navegador é avançado no teste de prazo, evitando aguardar 20
segundos reais. O prazo inclui a leitura do corpo da resposta.

**Limite da cobertura:** Firefox com tela estreita e toque testa o motor Gecko
no desktop. Playwright não automatiza o aplicativo Firefox para Android. Isso
não substitui uma verificação em aparelho Android, GPS e teclado reais; os jobs
não devem ser apresentados como homologação nativa de Android.

A suíte Python também testa a busca de proximidade com 3.000 registros extras e
um orçamento de instruções SQLite, independente da velocidade do runner.
Esse teste reprova a consulta antiga, que repetia a varredura de origem para
cada ponto. A consulta atual calcula o conjunto de origens oficiais uma vez.

## Executar no desenvolvimento

Requisitos: Python 3.13+, Node 22+ e dependências Linux dos navegadores.
As dependências JavaScript são somente de desenvolvimento; o aplicativo e o
instalador de produção continuam sem precisar de Node/Playwright.

```bash
npm ci --ignore-scripts
npx playwright install --with-deps firefox chromium
npm run test:e2e
```

Para um único motor:

```bash
npx playwright test --project='firefox-*'
```

`RADAR_TEST_PYTHON` permite escolher o Python de teste.
`RADAR_TEST_CHROMIUM` permite usar um Chromium já instalado no desenvolvimento;
no Actions são usados os navegadores correspondentes à versão fixada no lockfile.
Relatório HTML fica em `playwright-report/`; capturas e rastreamentos de falha em
`test-results/`. O workflow guarda esses artefatos por sete dias.
