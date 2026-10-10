# Radar Brasil — Acompanhamento da cobertura das 27 UFs

Tabela de acompanhamento nacional. Este documento **nao** comprova cobertura: a
existencia de uma fonte municipal **nao cobre** todas as rodovias/municipios do
estado. `cobertura_estadual_confirmada` permanece **false** ate auditoria por
circunscricao (municipios/rodovias efetivamente inventariados).

- Legenda de evidencia: `conjunto_dados` / `geoarquivo_oficial` (recurso
  anunciado CSV/XLSX/KML/GeoJSON); `relatorio_oficial` / `lista_documentos` /
  `lista_localizacao` (documento/lista oficial, pode exigir PDF/HTML e
  geocodificacao); `lista_trechos` (trechos elegiveis, nunca radar fixo
  comprovado); `lista_historica` (publicacao historica, nao prova situacao
  atual); `institucional_sem_lista` (orgao oficial sem publicacao de lista —
  requer LAI).
- Status nosso: `implementado` (existe conector no repo), `pendente`,
  `pendente_lai` (so ha dado historico), `sem_publicacao`.
- Fonte de verdade maquina-legivel: `coletor/catalogo_ufs.json`.

## Tabela por UF

| UF | Fonte | Evidencia | URL oficial | Status nosso | O que falta |
|----|-------|-----------|-------------|--------------|-------------|
| AC | Detran-AC - relatorio historico de equipamentos | lista_historica (**historico**, 2013) | https://agencia.ac.gov.br/detran-anuncia-retorno-da-fiscalizacao-eletronica/ | pendente_lai | Cadastro atual via LAI (Detran-AC/DERACRE); dados de 2013 nao valem para 2026 |
| AL | DER-AL - canal institucional | institucional_sem_lista (**sem publicacao de lista**) | https://alagoasdigital.al.gov.br/orgao/49 | sem_publicacao | Lista oficial via LAI; cameras nao provam radar de velocidade |
| AP | CTMac Macapa - pontos publicados | lista_localizacao_historica | https://macapa.ap.gov.br/radares-de-macapa-passam-a-ter-velocidade-maxima-permitida-de-60-km-h-a-partir-desta-terca-21/ | pendente | Publicacao recente, documentos tecnicos e coordenadas (lista de 17 locais e de 2022) |
| AM | IMMU Manaus - relacao oficial 2026 | lista_localizacao | https://www.manaus.am.gov.br/noticia/transito/fiscalizacao-eletronica-salvar-vidas/ | pendente | Validar arquivo/atualizacoes, extrair campos e coordenadas |
| BA | SEINFRA Bahia - KML radares fixos (fonte adicional: estaticos) | geoarquivo_oficial | https://www.ba.gov.br/infraestrutura/12046/mapas | pendente | Descobrir links atuais do KML; testar geometria/atributos |
| CE | AMC Fortaleza - mapa/dados fiscalizacao eletronica | geoarquivo_oficial | https://mapas.fortaleza.ce.gov.br/mapa/538/equipamentos-de-fiscalizacao-eletronica | pendente | Descobrir GeoJSON/KML/SHP/CSV (CKAN complementar); separar radares de cameras |
| DF | Detran-DF - camada Equipamentos Eletronicos no Geoportal | geoportal_documentado | https://detran.df.gov.br/wp-content/uploads/2022/10/Equipamentos_Eletronicos.pdf | pendente | Identificar servico WMS/WFS/ArcGIS e termos de acesso (documento explica consulta, nao e lista) |
| ES | Cariacica - mapa, estudos e faixas monitoradas | lista_documentos | https://cariacica.es.gov.br/pagina/ler/861/mapa-radares | pendente | Descobrir mapa/estudos/PDF de faixas; municipio nao cobre todo o ES |
| GO | Goinfra - relatorio de equipamentos de monitoramento | relatorio_oficial | https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/ | pendente | Extrair lista (codigos, series, km, coords); homologar >=5 pontos (ver testes-alvo GO) |
| MA | Detran-MA - fiscalizacao eletronica em rodovias estaduais | lista_localizacao | https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582 | pendente | Descobrir recurso real; complementar com SMTT Sao Luis |
| MG | DER-MG - radares fixos e portateis | lista_localizacao | https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis | implementado (`dermg`) | Conector existe; conferir sentidos/equipamentos/status. Municipal: `pbh` (Belo Horizonte) tambem implementado |
| MS | Agetran Campo Grande - radares ativados | lista_localizacao | https://www.campogrande.ms.gov.br/cgnoticias/noticia/novos-radares-operam-em-carater-educativo-ate-14-de-julho/ | pendente | Validar arquivo; cidades fora da capital nao cobertas |
| MT | Cuiaba - mapa e equipamentos | lista_historica (**historico**, 2015) | https://www.cuiaba.mt.gov.br/noticias/comeca-campanha-de-esclarecimento-sobre-a-fiscalizacao-eletronica | pendente | Atualizacao oficial; equipamentos de 2015 nao sao atuais |
| PA | SEGBEL Belem - relacao e portarias | lista_documentos | https://seguranca.belem.pa.gov.br/portarias-de-ativacao-e-desativacao-de-radares/ | pendente | Reunir situacao temporal das portarias e complementar com relacao de radares |
| PB | Semob Joao Pessoa - locais publicados | lista_localizacao | https://www.joaopessoa.pb.gov.br/noticias/secretarias-e-orgaos/semob/semobjp-orienta-populacao-sobre-novos-locais-com-radares-medidores-de-velocidade/ | pendente | Conferir lista completa em portal.semobjp.pb.gov.br e versao vigente |
| PR | DER-PR - fiscalizacao de velocidade | lista_localizacao | https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade | implementado (`derpr`) | Conector existe; trechos nao sao operacoes confirmadas. Municipal: Curitiba (fonte adicional) |
| PE | Recife - equipamentos de fiscalizacao (CSV/dicionario) | conjunto_dados | https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito | implementado (`recife`) | Conector existe; separar radares de cameras de monitoramento |
| PI | STRANS Teresina - Localizacao de Radares | lista_historica (**historico**, 2019) | https://antigo.pmt.pi.gov.br/2019/04/10/localizacao-dos-radares-sera-divulgada-mensalmente-no-site-da-prefeitura/ | pendente_lai | Dado atual via LAI (STRANS/DER-PI); publicacao de 2019 nao comprova 2026 |
| RJ | DER-RJ - radares portateis por local/horario | lista_localizacao (portatil) | https://sgitp.der.rj.gov.br/radares-portateis | pendente | Descobrir recurso; tratar como trecho elegivel (janela 06-22, nao presenca o dia todo). Adicional: DER_RJ_FIXOS |
| RN | STTU Natal - portal institucional | institucional_sem_lista (**sem publicacao de lista**) | https://www.natal.rn.gov.br/sttu | sem_publicacao | Relacao de radares/documentos via LAI (STTU/DER-RN) |
| RS | DAER-RS - locais de fiscalizacao com radar portatil | lista_trechos | https://www.daer.rs.gov.br/radares-moveis | pendente | Descobrir recurso; pontos elegiveis != operacoes pontuais confirmadas. Adicional: DAER_RS_PORTATEIS |
| RO | Porto Velho - relacao de radares fixos e estudos 2026 | lista_documentos | https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos | pendente | Extrair PDF (serie/validades 2026.1) |
| RR | Boa Vista - locais de radares | lista_localizacao_historica (**historico**, 2024) | https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-novos-equipamentos-de-fiscalizacao-eletronica-para-reduzir-acidentes-em-boa-vista | pendente | Verificar cadastro vigente; noticia de 2024 e historica |
| SC | Joinville DETRANS - estudos tecnicos 2026 | lista_documentos | https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/ | pendente | Extrair PDFs por equipamento; nao representa todos os municipios de SC |
| SP | DER-SP - dados abertos radar (XLSX) | conjunto_dados | https://dadosabertos.sp.gov.br/dataset/radar | implementado (`dersp`) | Conector existe; XLSX de agosto/2026 |
| SE | DER Sergipe - radares fixos e estudos tecnicos | lista_documentos | https://der.se.gov.br/localizacao-de-radares-fixos/ | pendente | Distinguir projeto/estudo de equipamento instalado; complementar com SMTT Aracaju |
| TO | Araguaina ASTT - relacao de radares 2026 | lista_localizacao | https://www.araguaina.to.gov.br/servicos/medidores-de-velocidade-lista-de-enderecos | pendente | Extrair download de enderecos (jan/2026); nao cobre todas as rodovias estaduais |

## UFs sem publicacao de lista (requerem LAI/contato)

- **AL — DER-AL**: apenas canal institucional; dados de cameras nao provam radar
  de velocidade. Sem listagem publicada.
- **RN — STTU Natal**: nao foi identificada listagem estruturada atual; pedir a
  STTU/DER-RN.

## UFs em estado historico (nao comprovam operacao atual)

- **AC** — publicacao de 2013. Depende de LAI (Detran-AC/DERACRE).
- **PI** — publicacao de 2019. Depende de LAI (STRANS/DER-PI).
- **MT** — publicacao de 2015 (Cuiaba). Depende de atualizacao oficial.
- **RR** — noticia de 2024 (Boa Vista). Depende de cadastro vigente.

## Estado de integracao (resumo)

- implementado: **SP** (`dersp`), **PR** (`derpr`), **MG** (`dermg` + municipal `pbh`), **PE** (`recife`) — 4 UFs.
- sem_publicacao: **AL**, **RN** — 2 UFs.
- pendente_lai: **AC**, **PI** — 2 UFs.
- pendente: as demais **19** UFs.

## Fontes federais (comuns a todas as UFs)

- INMETRO PSIE: https://servicos.rbmlq.gov.br/Instrumento
- PRF radares fixos: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
- DNIT PNCV: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
- ANTT radares: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17
