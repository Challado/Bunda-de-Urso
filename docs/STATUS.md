# Status de cobertura e leitores

Após a atualização habitual por `instalar-servidor3.sh`, abra
`https://servidor3.lucas.inf.br/openclaw/radar/status.html`.
A página fica fora da home, dos menus e da indexação sugerida aos buscadores.
Seu endereço é público; não exige login. Clicar no estado abre
`status-estado.html?uf=TO` em outra aba. GitHub e contato ficam no rodapé.

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

O painel recolhível de leituras inclui todos os recursos cadastrados e os
conectores agendados ainda sem histórico. Mostra última tentativa, último sucesso
(incluindo “sem alteração”), agendamento, intervalo, atraso, HTTP, contadores,
erros de execução e validação, páginas oficiais e endereços configurados.
O diário operacional complementa a última tentativa com a URL utilizada e a
interrupção, quando registradas para a mesma execução; uma entrada antiga do
diário não substitui a tentativa mais recente no banco. Falhas de leitura do
diário ou da agenda são informadas sem ocultar o histórico disponível.
Credenciais são ocultadas, e textos de fontes/erros são renderizados como texto.

Tudo passa por `api.pse`, sem baixar fontes ou iniciar coletas ao abrir a tela:

| Rota GET (JSON) | Resultado |
|---|---|
| `/api/v1/status/estados` | 27 UFs, totais nacionais, sem UF e critério |
| `/api/v1/status/estados/{uf}` | Estado, municípios, órgãos, fontes e pontos |
| `/api/v1/status/coletores` | Todos os leitores, erros e histórico mais recente |

No nginx use, por exemplo, `api.pse?rota=/api/v1/status/estados/TO`.
O detalhe aceita `limite=1..1000` e `depois`, o ID numérico retornado em
`proximo_depois`; sem mais registros esse campo vem nulo. Respostas não ficam em
cache. A tela tem atualização manual e prazo para a requisição, com nova
tentativa em caso de falha. Nenhum caminho da instalação é fixado no front;
o diário é localizado por `core.caminhos`, conforme `radar.conf`.

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
