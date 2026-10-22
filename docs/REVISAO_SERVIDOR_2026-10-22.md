# Revisao do relatorio do servidor3 — 22/10/2026

Leitura real pela API publica, com a versao `bcf06de` instalada. Prontidao
`ready`; as 27 checagens finais da instalacao estavam aprovadas. O consolidado
mostrava 13 recursos acompanhados, 12 com sucesso e um com erro. A consulta de
todo o historico revelou 50 recursos: 18 ultimos resultados `ok`, 25
`sem_mudanca` e **sete com erro**. Esses estados foram preservados: consultar
somente tentativas com erro tambem mostraria falhas ja recuperadas.

| Recurso | Ultimo problema no servidor | Verificacao nesta revisao |
|---|---|---|
| ANTT | Conexao reiniciada pelo destino | Catalogo/API devolveram HTTP 200 com pagina `Request Rejected`. Bloqueio passa a ser identificado como tal. |
| Recife | Timeout do CSV | Portal/CKAN responderam 503. Corrigido tambem o caminho da coleta manual, que baixava a pagina do dataset em vez de resolver o CSV. |
| DNIT Multas | XLSX nao apareceu no prazo | Portal respondeu 503 nesta rede. Exportador agora trata menus, icones, iframes, recarregamento e repeticao limitada; registra rede, JavaScript e stderr do navegador. Coleta real ainda precisa ser confirmada no servidor. |
| Detran-MA | Timeout no PDF | Host do recurso respondeu erro de conexao/502. Sem arquivo novo confirmado. |
| IMMU Manaus | Timeout da pagina | Pagina respondeu 200; importacao pela API em banco temporario: 34 criados, zero rejeitados, sem inventar coordenadas. |
| Boa Vista | Lote sem registros normalizaveis | Noticia historica com lista em imagem; integracao permanece pendente, sem inventar cadastro atual. |
| STTU Natal | HTTP 500 do portal institucional | Endereco respondeu 404 e nao fornece cadastro estruturado confirmado. Integracao pendente. |

O [registro JSON da verificacao](REVISAO_ATUALIZACOES_2026-10-22.json) inclui
horarios e mensagens retornados pela API. Testes locais e downloads de
verificacao nao alteraram o banco do servidor.

## Correcoes preparadas

- Retorno 4 de `crond.service` inexistente fica como sondagem esperada quando
  `cron.service` esta ativo. Se nenhuma alternativa estiver ativa, permanece erro.
- Consolidado inclui todos os recursos do banco, inclusive falhas anteriores ao
  diario, e identifica fontes sem coleta. Um tick ocioso preserva o ultimo erro.
- O instalador atualiza o consolidado pela API, sem downloads, ao terminar.
- Retentativa apos falha deixa de multiplicar intervalos semanais/anuais:
  base limitada a uma hora, multiplicador ate oito. Sucesso segue a agenda normal.
- HTTP 200 com pagina de bloqueio nao e aceito como JSON/CSV. Falhas da
  descoberta CKAN ficam no diario mesmo quando ha URL alternativa.
- Exportacao XLSX registra causas de falha e encerra o grupo de processos do
  navegador antes de remover o perfil temporario.
- Parametros sensiveis como `user_content_key` sao ocultados nos relatorios.

Aplicar com o instalador privado atualizado, como root. A revisao nao modifica
schema, nao apaga cadastros e nao executa sincronizadores do repositorio privado.
