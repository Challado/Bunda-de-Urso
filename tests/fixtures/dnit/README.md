# Publicacoes DNIT usadas nos testes

- `pncv_julho_2026.xlsx`: arquivo original coletado em 10/10/2026 pelo conector
  PNCV, preservado no repositorio privado de dados. SHA-256
  `770bdba412a6f52a74cab5f3b78b13eb86e89bfe5260548aebc1dd36cfdee664`.
- `equipamentos_multas.xlsx`: `TabelaEquipamentosFiscalizacao.xlsx` enviado pelo
  operador em 22/10/2026, exportado da pagina publica do DNIT Multas. SHA-256
  `1634544d482876849ead82a734eff7398c48d737c5712f23ae5f8bd99d4f5308`.

Pagina da exportacao:
<https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao>.
Fonte PNCV: <https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade>.

Os arquivos sao integrais. Nao representam download online confirmado hoje:
o portal retornou 503 nesta rede. A segunda publicacao tem ordem longitude/latitude,
155 celulas de serie com `/` e registros Inmetro com lacunas/placeholders. Os
registros ausentes de uma das listas nao sao declarados removidos. Nao usar estas
fixtures automaticamente como fallback de producao para uma coleta nova.
