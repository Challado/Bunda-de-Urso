# Status de cobertura e leitores

O painel de cobertura é público e acessível pelo endereço direto. Clicar
em um estado abre os detalhes em outra aba. GitHub e contato ficam no
rodapé. [Painel de status](https://servidor3.lucas.inf.br/openclaw/radar/status.html)

A tabela numera de 1 a 27 todos os estados e o DF, por nome, inclusive sem
cadastros. Conta **pontos únicos publicados**, não linhas recebidas, faixas,
instrumentos ou total presumido de radares existentes no estado. Inclui
inativos; exclui removidos, desabilitados e registros ocultados por decisões
de governança. Unificações aplicadas contam uma vez; reversões voltam a separar.
GPS, município e correspondência no Inmetro não são pré-requisitos da contagem.
A UF vem do município normalizado, de um membro do grupo unificado ou da UF
publicada na origem. Pontos sem UF aparecem à parte no total nacional.

A esfera vem dos vínculos vigentes de órgão fiscalizador. Na ausência deles,
usa a esfera da fonte oficial que cadastrou o ponto. **Inmetro comprova
metrologia, não esfera de fiscalização**. Também não se infere esfera pelo
prefixo BR/rodovia. Distrital entra em estadual. Esferas divergentes e cadastros
sem comprovação ficam na coluna “Sem classificação”, sem duplicar contagens.
**Zero indica falta de cadastro nesta base, não inexistência de radares.**

O detalhe do estado mostra municípios, órgãos/publicadores, fontes e uma lista
paginada de pontos (100 por página), com links para o detalhe de cada radar.
As listas de fontes e órgãos podem incluir o mesmo ponto em mais de uma origem.

Em **Status das leituras**, abra os menus aninhados de Brasil (federal),
estados e municípios. Dentro de cada localidade ficam os órgãos e seus
leitores. A busca aceita nomes de fontes e localidades. **Só com erro**
abre os grupos que contêm falhas. O contador de erros de um grupo filtra
somente os leitores desse grupo. [Leituras das fontes](https://servidor3.lucas.inf.br/openclaw/radar/status.html#leituras)

O modo público mostra última tentativa, último sucesso (incluindo “sem
alteração”), agendamento, intervalo, atraso, código HTTP, contagens e
links oficiais do catálogo. Inclui leitores ainda sem histórico.

**Diagnóstico da equipe** abre o painel com uma sessão de moderador ou
administrador. Mostra as mensagens de erro e os endereços configurados
ou efetivamente usados. O diário complementa a última tentativa quando
o ID da execução coincide com o do banco. Se a sessão expirar, o painel
mostra as informações públicas e oferece o link para entrar novamente.
[Diagnóstico da equipe](https://servidor3.lucas.inf.br/openclaw/radar/status.html?diagnostico=1#leituras)

Abrir ou atualizar a página consulta o histórico armazenado pela API.

| Rota GET (JSON) | Resultado |
|---|---|
| `/api/v1/status/estados` | 27 UFs, totais nacionais, sem UF e critério |
| `/api/v1/status/estados/{uf}` | Estado, municípios, órgãos, fontes e pontos |
| `/api/v1/status/leituras` | Leituras públicas das fontes oficiais |
| `/api/v1/status/coletores` | Diagnóstico técnico, com sessão ou token de moderador ou administrador |
| `/api/v1/atualizacoes/status` | Relatório consolidado, com a mesma credencial |

Use `api.pse?rota=/api/v1/status/estados/TO`. O detalhe aceita `limite=0`
para todos os pontos após `depois`. Valores positivos seguem o teto da
instância, por padrão 200, e valores acima do teto retornam HTTP 422. Passe
o ID numérico de `proximo_depois` em `depois` para continuar a paginação.
O campo vem nulo na última página. As respostas do painel usam
`Cache-Control: no-store`. As rotas protegidas retornam HTTP 401 sem
credencial. [Relatórios de atualização](RELATORIOS_ATUALIZACOES.md)

O instalador existente publica os dois HTMLs, CSS, JavaScript e implementação
da API, preservando configuração, banco e rotinas específicas do servidor.
Não precisa nova tabela, novo cron ou dependência em produção.
Os testes do Actions cobrem classificação, identidade, remoções, paginação,
leitores sem coleta/com erro e navegação em Chromium e Firefox, nas telas larga
e estreita. Firefox com tela estreita é teste Gecko; não emula Firefox Android.

## Leituras documentais e rejeições antigas (24/10/2026)

O status consultado no servidor mostrava 50 recursos: 48 leituras sem erro e
2 erros `lote_sem_registros_validos`, em Boa Vista e STTU Natal. O OSM aparecia
adicionalmente como nunca coletado, mas está desativado. A PRF constava como
leitura OK com 16 linhas rejeitadas, entre 1.591 recebidas.

Boa Vista, Natal, Joinville (estudos), Belém (portarias), Macapá, Cuiabá,
DER-AL, Detran-AC e Teresina são leitores de documentação. Suas páginas são
validadas e os registros ficam preservados, com resultado `documentado`,
zero radares criados e integração ainda pendente. Uma repetição documental
mantém o aviso **Cadastro de radares pendente**. Erros HTTP, títulos de erro
mesmo com HTTP 200, página desconhecida ou extração vazia continuam falhando;
nenhum snapshot de radares é publicado por esses leitores.

A PRF publica 16 registros inoperantes sem IDENTIFICADOR nem GPS, mas com
código em EQUIPAMENTO. Esse código é aceito como identificador administrativo,
sem preencher série ou posição. A leitura atual de 1.591 registros foi
validada pela API em banco temporário: 1.591 aceitos, zero rejeições.
O portal atual de Natal também foi lido pela API: documentação aceita, sem
publicar radar. Boa Vista foi verificada por fixture da notícia; o download
dessa origem retornou 503 neste ambiente, enquanto a tentativa registrada
no servidor tinha HTTP 200.

O `instalar-servidor3.sh` atualizado do repositório privado executa pela API
`ferramenta reprocessar_fontes_corrigidas` após aplicar os fontes. A operação
reconhece as fontes afetadas, confere o hash e reprocessa somente o necessário
no cache original local. Não usa rede, não remove histórico de rejeições e
não recria pontos já vinculados. Repetir é idempotente. Se o cache estiver
inexistente ou inválido, informa a pendência/erro no JSON e no log; não inventa
uma coleta bem-sucedida. A coleta normal também pode reaproveitar o mesmo
arquivo para recuperar as rejeições da PRF, após a correção do parser.
