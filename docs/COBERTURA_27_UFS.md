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
- Status nosso: `implementado` (existe conector no repo), `parcial` (conector
  cobre apenas parte da circunscricao), `pendente`, `pendente_lai` (so ha dado
  historico), `sem_publicacao` (sem lista publicada; requer LAI/contato).
- A coluna **Modulo** traz o conector do repo. Em `AC`/`AL`/`RN`/`PI` existe um
  conector **diagnostico** (documenta a ausencia de cadastro; `normalizar`→None),
  por isso `nosso_modulo` fica `null` no catalogo.
- Fonte de verdade maquina-legivel: `coletor/catalogo_ufs.json`.

## Tabela por UF

| UF | Fonte | Evidencia | URL oficial | Status nosso | Modulo | O que falta |
|----|-------|-----------|-------------|--------------|--------|-------------|
| AC | Detran-AC - portal institucional / relato historico | institucional_sem_lista (**historico**, 2013) | https://www.detran.ac.gov.br/ | pendente_lai | diagnostico `detran_ac` | Portal so oferece consulta de autos/convênios; noticia de 2013 (agencia.ac.gov.br) esta HTTP 503. Cadastro atual via LAI (Detran-AC/DERACRE) |
| AL | DER-AL - canal institucional | institucional_sem_lista (**sem publicacao de lista**) | https://alagoasdigital.al.gov.br/orgao/49 | sem_publicacao | diagnostico `der_al` | Lista oficial via LAI (DER-AL/DMT Maceio); der.al.gov.br fora do ar; cameras nao provam radar de velocidade |
| AP | CTMac Macapa - pontos publicados | lista_localizacao_historica | https://macapa.ap.gov.br/radares-de-macapa-passam-a-ter-velocidade-maxima-permitida-de-60-km-h-a-partir-desta-terca-21/ | implementado | `ctmac_ap` | Lista de 17 locais (2022); localizar publicacao recente e coordenadas |
| AM | IMMU Manaus - relacao oficial 2026 | lista_localizacao | https://www.manaus.am.gov.br/noticia/transito/fiscalizacao-eletronica-salvar-vidas/ | parcial | `immu_am` | Cobre a capital; validar arquivo/atualizacoes e status posterior |
| BA | SEINFRA Bahia - KML radares fixos (fonte adicional: estaticos) | geoarquivo_oficial | https://www.ba.gov.br/infraestrutura/12046/mapas | parcial | `seinfra_ba` | Conector cobre parte; conferir links atuais do KML e atributos |
| CE | AMC Fortaleza - mapa/dados fiscalizacao eletronica | geoarquivo_oficial | https://mapas.fortaleza.ce.gov.br/mapa/538/equipamentos-de-fiscalizacao-eletronica | implementado | `amc_ce` | GeoJSON/KML/SHP/CSV; separar radares de cameras. CKAN complementar |
| DF | Detran-DF - camada Equipamentos Eletronicos no Geoportal | geoportal_documentado | https://detran.df.gov.br/wp-content/uploads/2022/10/Equipamentos_Eletronicos.pdf | parcial | `detran_df` | Identificar servico WMS/WFS/ArcGIS e termos de acesso |
| ES | Cariacica - mapa, estudos e faixas monitoradas | lista_documentos | https://cariacica.es.gov.br/pagina/ler/861/mapa-radares | implementado | `cariacica_es` | Municipio NAO cobre todo o ES |
| GO | Goinfra - relatorio de equipamentos de monitoramento | relatorio_oficial | https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/ | implementado | `goinfra` | Lista com codigos/series/km/coords (atualizada 07/10/2026) |
| MA | Detran-MA - fiscalizacao eletronica em rodovias estaduais | lista_localizacao | https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582 | implementado | `detran_ma` | Complementar com SMTT Sao Luis |
| MG | DER-MG - radares fixos e portateis | lista_localizacao | https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis | implementado | `dermg` (+ municipal `pbh`) | Conferir sentidos/equipamentos/status. Municipal: `pbh` (Belo Horizonte) |
| MS | Agetran Campo Grande - radares ativados | lista_localizacao | https://www.campogrande.ms.gov.br/cgnoticias/noticia/novos-radares-operam-em-carater-educativo-ate-14-de-julho/ | implementado | `agetran_ms` | Cidades fora da capital nao cobertas |
| MT | Cuiaba - mapa e equipamentos | lista_historica (**historico**, 2015) | https://www.cuiaba.mt.gov.br/noticias/comeca-campanha-de-esclarecimento-sobre-a-fiscalizacao-eletronica | pendente | — | Atualizacao oficial; equipamentos de 2015 nao sao atuais |
| PA | SEGBEL Belem - relacao e portarias | lista_documentos | https://seguranca.belem.pa.gov.br/portarias-de-ativacao-e-desativacao-de-radares/ | parcial | `segbell_pa` | Reunir situacao temporal das portarias; so a capital |
| PB | Semob Joao Pessoa - locais publicados | lista_localizacao | https://www.joaopessoa.pb.gov.br/noticias/secretarias-e-orgaos/semob/semobjp-orienta-populacao-sobre-novos-locais-com-radares-medidores-de-velocidade/ | parcial | `semob_pb` | So a capital; conferir lista completa e versao vigente |
| PR | DER-PR - fiscalizacao de velocidade | lista_localizacao | https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade | implementado | `derpr` | Trechos nao sao operacoes confirmadas. Municipal: Curitiba |
| PE | Recife - equipamentos de fiscalizacao (CSV/dicionario) | conjunto_dados | https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito | implementado | `recife` | Separar radares de cameras de monitoramento. So a capital |
| PI | STRANS Teresina - Localizacao de Radares | lista_historica (**historico**, 2019) | https://antigo.pmt.pi.gov.br/2019/04/10/localizacao-dos-radares-sera-divulgada-mensalmente-no-site-da-prefeitura/ | pendente_lai | diagnostico `teresina_pi` | Noticia de 2019 SO anuncia a lista (nao a publica); STRANS fora do ar. Dado atual via LAI (STRANS/DER-PI) |
| RJ | DER-RJ - radares portateis por local/horario | lista_localizacao (portatil) | https://sgitp.der.rj.gov.br/radares-portateis | implementado | `der_rj` | Trecho elegivel (janela 06-22), nao presenca o dia todo. Adicional: DER_RJ_FIXOS |
| RN | STTU Natal - portal institucional | institucional_sem_lista (**sem publicacao estadual**) | https://www.natal.rn.gov.br/sttu | sem_publicacao | diagnostico `natal_rn` | DER-RN em HTTP 503; STTU Natal tem subpagina municipal com PDFs por equipamento (so a capital). Relacao via LAI (STTU/DER-RN) |
| RS | DAER-RS - locais de fiscalizacao com radar portatil | lista_trechos | https://www.daer.rs.gov.br/radares-moveis | implementado | `daer_rs` | Pontos elegiveis != operacoes pontuais confirmadas. Adicional: DAER_RS_PORTATEIS |
| RO | Porto Velho - relacao de radares fixos e estudos 2026 | lista_documentos | https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos | implementado | `semtran_ro` | PDF com serie/validades 2026.1 (so a capital) |
| RR | Boa Vista - locais de radares | lista_localizacao_historica (**historico**, 2024) | https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-novos-equipamentos-de-fiscalizacao-eletronica-para-reduzir-acidentes-em-boa-vista | pendente | — | Locais publicados apenas em imagem; verificar cadastro vigente |
| SC | Joinville DETRANS - estudos tecnicos 2026 | lista_documentos | https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/ | parcial | `joinville_sc` | Estudos tecnicos nao sao equipamento instalado; nao representa todo o SC |
| SP | DER-SP - dados abertos radar (XLSX) | conjunto_dados | https://dadosabertos.sp.gov.br/dataset/radar | implementado | `dersp` | XLSX de agosto/2026 |
| SE | DER Sergipe - radares fixos e estudos tecnicos | lista_documentos | https://der.se.gov.br/localizacao-de-radares-fixos/ | implementado | `der_se` | Distinguir projeto/estudo de equipamento instalado. Complemento: SMTT Aracaju |
| TO | AGETO - relacao estadual de radares fixos | lista_localizacao | https://www.to.gov.br/ageto/lista-de-radares/l3d43475lu1 | implementado | `ageto_to` | PDF rev01 com 58 equipamentos georreferenciados; ASTT Araguaina permanece no conector municipal `araguaiana_to`; cobertura integral e atividade atual nao comprovadas |

## UFs sem publicacao de lista (requerem LAI/contato)

- **AL — DER-AL**: apenas canal institucional; dados de cameras nao provam radar
  de velocidade. Sem listagem publicada. Conector diagnostico `der_al`.
- **RN — STTU Natal**: sem cadastro ESTADUAL publicado (DER-RN em HTTP 503). Ha
  apenas publicacao MUNICIPAL de Natal (subpagina `/sttu/equipamentos`, PDFs por
  equipamento, so a capital). Conector diagnostico `natal_rn`; relacao via LAI
  (STTU/DER-RN).

## UFs em estado historico (nao comprovam operacao atual)

- **AC** — publicacao de 2013 (offline/HTTP 503). Depende de LAI
  (Detran-AC/DERACRE). Conector diagnostico `detran_ac`.
- **PI** — publicacao de 2019, que apenas anuncia a lista. Depende de LAI
  (STRANS/DER-PI). Conector diagnostico `teresina_pi`.
- **MT** — publicacao de 2015 (Cuiaba). Depende de atualizacao oficial.
- **RR** — noticia de 2024 (Boa Vista), locais apenas em imagem.

## Estado de integracao (resumo)

- implementado: **15** UFs — GO (`goinfra`), CE (`amc_ce`), RJ (`der_rj`),
  RS (`daer_rs`), ES (`cariacica_es`), AP (`ctmac_ap`), MS (`agetran_ms`),
  RO (`semtran_ro`), MA (`detran_ma`), SE (`der_se`), TO (`araguaiana_to`),
  SP (`dersp`), PR (`derpr`), MG (`dermg` + municipal `pbh`), PE (`recife`).
- parcial: **6** UFs — BA (`seinfra_ba`), SC (`joinville_sc`), AM (`immu_am`),
  PB (`semob_pb`), PA (`segbell_pa`), DF (`detran_df`).
- pendente_lai: **2** UFs — AC (`detran_ac`), PI (`teresina_pi`).
- sem_publicacao: **2** UFs — AL (`der_al`), RN (`natal_rn`).
- pendente: **2** UFs — MT, RR.

## Fontes federais (comuns a todas as UFs)

- INMETRO PSIE: https://servicos.rbmlq.gov.br/Instrumento
- PRF radares fixos: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
- DNIT PNCV: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
- ANTT radares: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17
