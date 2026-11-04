# Publicacoes DNIT usadas nos testes

- `equipamentos_api.geojson`: recorte de tres registros da API publica
  `https://servicos.dnit.gov.br/services-sior/portal-multas/pncv/equipamentos`,
  consultada por HTTP em 04/11/2026 (1.682 registros na resposta integral).
  Apenas `guidET`, referencia opaca de download do estudo, foi omitido no
  recorte. Coordenadas GeoJSON em longitude/latitude, campos e identificadores
  preservados. SHA-256 da resposta integral:
  `ddee662bd4992c55ad0b44ce1015794da30d5a686758f2c759aaef574441bb09`.
- `pncv_julho_2026.xlsx`: arquivo original coletado em 10/10/2026 pelo conector
  PNCV, preservado no repositorio privado de dados. SHA-256
  `770bdba412a6f52a74cab5f3b78b13eb86e89bfe5260548aebc1dd36cfdee664`.
- `equipamentos_multas.xlsx`: `TabelaEquipamentosFiscalizacao.xlsx` enviado pelo
  operador em 22/10/2026, exportado da pagina publica do DNIT Multas. SHA-256
  `1634544d482876849ead82a734eff7398c48d737c5712f23ae5f8bd99d4f5308`.

Pagina da exportacao:
<https://servicos.dnit.gov.br/multas/informacoes/equipamentos-fiscalizacao>.
Fonte PNCV: <https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade>.

Os dois XLSX sao integrais e historicos; o GeoJSON e um recorte documentado.
A exportacao XLSX tem ordem longitude/latitude,
155 celulas de serie com `/` e registros Inmetro com lacunas/placeholders. Os
registros ausentes de uma das listas nao sao declarados removidos. Nao usar estas
fixtures automaticamente como fallback de producao para uma coleta nova.
