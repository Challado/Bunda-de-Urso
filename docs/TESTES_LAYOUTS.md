# Testes de layouts no GitHub Actions

O workflow `Layouts e interacoes` roda em cada push no main, pull request e
acionamento manual. A matriz é definida em `tests/e2e/resolucoes.cjs`:
18 perfis × 3 motores × 8 testes = **432 verificações**, distribuídas em nove
jobs (navegador × celular/tablet/PC). Cada grupo continua mesmo se outro falhar.
Não usa dados, credenciais, nginx ou banco da produção.

## Perfis de tela

Dimensões em pixels CSS; densidade e toque são emulados. O Firefox recebe o
viewport e o toque, pois Playwright não oferece o modo isMobile nesse motor.
WebKit testa o motor usado pelo Safari, sem representar um iPhone físico.

| Grupo | Perfil | Viewport | Densidade | Toque |
| --- | --- | --- | --- | --- |
| celular | compacto | 320 × 568 | 2 | sim |
| celular | pequeno | 360 × 640 | 3 | sim |
| celular | padrao | 390 × 844 | 3 | sim |
| celular | grande | 412 × 915 | 2.625 | sim |
| celular | paisagem | 844 × 390 | 3 | sim |
| celular | paisagem-grande | 915 × 412 | 2.625 | sim |
| tablet | compacto | 600 × 960 | 2 | sim |
| tablet | retrato | 768 × 1024 | 2 | sim |
| tablet | retrato-grande | 820 × 1180 | 2 | sim |
| tablet | paisagem | 1024 × 768 | 2 | sim |
| tablet | paisagem-grande | 1180 × 820 | 2 | sim |
| pc | pequeno | 1024 × 768 | 1 | não |
| pc | notebook | 1280 × 720 | 1 | não |
| pc | notebook-hd | 1366 × 768 | 1 | não |
| pc | hidpi | 1440 × 900 | 2 | não |
| pc | full-hd | 1920 × 1080 | 1 | não |
| pc | qhd | 2560 × 1440 | 1 | não |
| pc | 4k | 3840 × 2160 | 1 | não |

## O que reprova a execução

- Conteúdo vazando horizontalmente, mapa abaixo do mínimo ou rolagem da página
  nas telas onde o conteúdo deveria caber.
- Lista longa sem rolagem, rolagem da lista movendo a página por trás, último
  radar inacessível, falha ao recolher/abrir ou perda de registros.
- Falha ao clicar/tocar em Consultar, Usar minha localização, Mostrar radares
  aqui, envio simplificado, links de detalhes ou estados do status.
- Cadastro sem HTTP 202/protocolo, fila sem processamento, detalhes inacessíveis
  ou popup do estado que não abre.
- Aviso que não muda ao passar de radares para nenhum radar e de volta, ou aviso
  repetido quando a categoria da busca permanece a mesma.
- Layout que não se recompõe após orientação, redução do viewport (incluindo o
  espaço ocupado por teclado virtual) ou restauração do tamanho.
- Falha da configuração pública ou da consulta deixando controles presos,
  resultados antigos ou sem possibilidade de tentar novamente.
- Erro JavaScript não tratado na página.

O gesto de arrastar a lista é enviado como toque nativo ao Chromium em celulares
e tablets. Os demais casos exercitam roda do mouse e teclado. WebKit mobile não
oferece roda do mouse no Playwright: nele a rolagem é exercitada por eventos reais
de teclado, mantendo a emulação mobile e os testes de toque nos controles.
As medidas de layout são verificadas sobre o DOM real, sem simular scrollTop
como substituto da interação do usuário.

A API CGI, SQLite, fila e o processamento de cadastro são reais no laboratório.
Somente as respostas de busca/configuração da home são controladas para gerar
cenários previsíveis. Leaflet usa a versão local fixa e os mapas não precisam de
rede externa. Os fluxos funcionais completos anteriores continuam no workflow
`Navegadores`, separado desta matriz.

## Relatórios

Cada job publica `layouts-<navegador>-<grupo>-<tentativa>`, retido por 14 dias, contendo:

- relatório HTML com cada teste e perfil;
- screenshots dos cenários e medidas em JSON, mesmo quando passam;
- captura de tela e trace Playwright quando falham;
- resumo completo em `test-results-layouts/resumo.json`.

Abra Actions → Layouts e interacoes → execução → Artifacts. O trace permite
reproduzir os passos, requisições e DOM do momento da falha.

## Executar em desenvolvimento

```sh
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install --with-deps chromium firefox webkit
npx playwright test --config=playwright.layouts.config.cjs
```

Para limitar a um grupo:

```sh
npx playwright test --config=playwright.layouts.config.cjs --project="chromium-tablet-*"
```

Os testes não configuram o servidor de produção nem precisam ser executados lá.
