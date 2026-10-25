# Histórico de alterações

## Home, navegação e mapas

- Ícone do urso retorna à home em todas as páginas.
- Consulta concluída mostra somente o snapshot, sem resumo técnico de cobertura ou contagens redundantes.
- Links para OpenStreetMap, Google Maps, Street View, Bing Mapas e Streetside no local consultado e nos marcadores, compartilhando os destinos com os detalhes.
- Validação de navegação, coordenadas dos links e busca vazia incluída nos testes de navegador e na matriz de layouts do GitHub Actions.

## Documentação da API e organização do GitHub

- Guia destacado de consulta/exportação, incluindo NDJSON, paginação, XML, TXT, DIF e EDIFACT.
- Notas de estado e histórico retiradas do README e preservadas neste changelog.

## Intercâmbio de Instâncias e TRASEIRO DE URSO

- Contrato genérico HTTPS/JSON, cliente Python independente e negociação dos tipos de documento.
- Rede de radares com identidades persistentes, descoberta de pares, lotes bidirecionais e reenvio sem duplicação.
- Intervalo de consulta independente por servidor, inatividade configurada por tipo/número e parada anunciada com retorno opcional.
- Cadastro separado, validação pela moderação e fonte própria para posições aprovadas.
- Receitas JSON/CSV compartilhadas, desativadas até autorização local.
- Cron independente no usuário da instalação e integração aos relatórios de atualização.

## Links de mapas

Bing Mapas e Bing Streetside acrescentados aos links das coordenadas, com testes de parâmetros e de exibição.

## Histórico de layout preservado do README

## Situação real do desenvolvimento

O projeto implementa a **ESPECIFICACAO_v1.1.txt (10/10/2026)**: coletor/sincronizador, API `.pse`, esquema relacional de **78 tabelas base**, resolvedor geográfico, serializadores em seis formatos, documentação e testes automatizados locais (stdlib `unittest`). Os testes locais não equivalem à homologação das coletas reais em todo o Brasil.

**Ainda precisam de trabalho e validação:** integração e importação real de todas as fontes federais, estaduais e municipais; resolução das coordenadas ausentes; homologação de cada formato e SGBD utilizado; verificação de qualidade e atualização de cada órgão; aferição da cobertura nacional; avaliação de licenças para redistribuição de cada conjunto de dados.

O projeto não deve divulgar percentuais de cobertura, contagens nacionais ou precisão de localização sem medi-los efetivamente. Equipamentos sem coordenada comprovada continuam no inventário para investigação — porque apagar o que não sabemos localizar seria a pior lamúria de todas: esconder o problema debaixo do tapete.

### Layouts e interações no CI

Celular e tablet deixam a página rolar normalmente, com todos os radares abaixo
do mapa. No PC, o mapa e a lista se ajustam à tela, com painel recolhível quando necessário.

O workflow **Layouts e interacoes** valida 18 perfis de celular, tablet e PC em
Chromium, Firefox e WebKit, com 486 verificações de rolagem, clique/toque,
navegação, cadastro e altura do mapa. Roda automaticamente em push/main e PR,
além de permitir acionamento manual. Relatórios, screenshots, medidas e traces
ficam nos artefatos por 14 dias. Veja [a matriz e os cenários](docs/TESTES_LAYOUTS.md).
