# Cobertura estadual e municipal — 22/10/2026

O Brasil tem 26 estados e o Distrito Federal. O catalogo de fontes abrange as 27 UFs; **a coleta ainda nao cobre todos os radares estaduais nem todos os municipios**. Inmetro e fontes federais sao camadas independentes e nao substituem cadastro de cada orgao.

A tabela conta conectores que importam dados. Fontes somente documentais/diagnosticas nao contam como cobertura. Um conector estadual pode publicar apenas locais elegiveis ou parte do seu inventario.

| UF | Estado | Fontes estaduais/distritais | Fontes municipais |
|---|---|---|---|
| AC | Acre | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| AL | Alagoas | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| AP | Amapá | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| AM | Amazonas | Cadastro estadual ainda nao integrado | `immu_am` |
| BA | Bahia | `seinfra_ba` | `salvador_ba` |
| CE | Ceará | Cadastro estadual ainda nao integrado | `amc_ce` |
| DF | Distrito Federal | `detran_df` | Cadastro municipal ainda nao integrado |
| ES | Espírito Santo | `der_es` | `cariacica_es` |
| GO | Goiás | `goinfra` | Cadastro municipal ainda nao integrado |
| MA | Maranhão | `detran_ma` | Cadastro municipal ainda nao integrado |
| MT | Mato Grosso | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| MS | Mato Grosso do Sul | Cadastro estadual ainda nao integrado | `agetran_ms` |
| MG | Minas Gerais | `dermg` | `pbh` |
| PR | Paraná | `derpr` | `curitiba_pr` |
| PB | Paraíba | Cadastro estadual ainda nao integrado | `semob_pb` |
| PA | Pará | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| PE | Pernambuco | `der_pe_lombadas`, `der_pe_mistos` | `recife` |
| PI | Piauí | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| RN | Rio Grande do Norte | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| RS | Rio Grande do Sul | `daer_rs`, `daer_rs_fixos`, `daer_rs_redutores` | Cadastro municipal ainda nao integrado |
| RJ | Rio de Janeiro | `der_rj` | Cadastro municipal ainda nao integrado |
| RO | Rondônia | Cadastro estadual ainda nao integrado | `semtran_ro` |
| RR | Roraima | Cadastro estadual ainda nao integrado | Cadastro municipal ainda nao integrado |
| SC | Santa Catarina | `sie_sc_portateis`, `sie_sc_locais` | `joinville_cadastro_sc` |
| SE | Sergipe | `der_se` | `aracaju_se` |
| SP | São Paulo | `dersp` | `cetsp` |
| TO | Tocantins | `ageto_to` | `araguaiana_to` |

## Publicacoes novas integradas

As contagens abaixo sao registros da publicacao, incluindo historicos/desativados; **nao sao contagem de radares ativos ou de equipamentos fisicos unicos**. Publicacoes diferentes podem descrever o mesmo aparelho, e a identidade exige evidencia.

| Fonte | UF | Esfera | Registros | Com coordenadas validas |
|---|---|---|---:|---:|
| [der_es](https://servicos.der.es.gov.br/Radares.aspx) | ES | estadual | 392 | 0 |
| [der_pe_lombadas](https://www.der.pe.gov.br/transito-menu/lombadas-eletronicas/lista-de-trechos-monitorados-2/1382-lista-de-trechos-monitorados-lombadas) | PE | estadual | 119 | 119 |
| [der_pe_mistos](https://www.der.pe.gov.br/transito-menu/equipamentos-de-fiscalizacao-eletronica/lista-de-trechos-2/1383-equipamentos-mistos) | PE | estadual | 61 | 61 |
| [curitiba_pr](https://transito.curitiba.pr.gov.br/fiscalizacaoeletronica) | PR | municipal | 293 | 293 |
| [salvador_ba](https://transonline.salvador.ba.gov.br/equipamentos/index.php) | BA | municipal | 106 | 106 |
| [aracaju_se](https://smtt.aracaju.se.gov.br/medidores-de-velocidade/) | SE | municipal | 44 | 0 |
| [daer_rs_fixos](https://www.daer.rs.gov.br/pardais) | RS | estadual | 60 | 0 |
| [daer_rs_redutores](https://www.daer.rs.gov.br/localizacao-das-lombadas) | RS | estadual | 131 | 0 |
| [joinville_cadastro_sc](https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/) | SC | municipal | 54 | 3 |
| [cetsp](https://www.cetsp.com.br/consultas/fiscalizacao-eletronica-do-transito.aspx) | SP | municipal | 2032 | 2011 |
| [sie_sc_portateis](https://www.sie.sc.gov.br/) | SC | estadual | 38 | 0 |
| [sie_sc_locais](https://www.sie.sc.gov.br/) | SC | estadual | 662 | 0 |

Os dez cadastros locais acrescentam 3.292 registros. Santa Catarina acrescenta um inventario de 38 portateis sem local de uso e 662 locais elegiveis, separados dos pontos instalados. A CET-SP publica 2.126 registros, dos quais 2.032 metrologicos sao importados; 837 destes possuem ativacao sem data de desativacao na publicacao consultada. A CET tambem publica 21 pares numericos fora da faixa de latitude/longitude: ficam no bruto e nao viram posicao. Ha 2.593 coordenadas validas entre os novos cadastros. Em Curitiba, 16 cartoes sem fiscalizacao de velocidade sao excluidos dos 309 publicados. No DER-PE, faixas da mesma linha com rowspan permanecem agrupadas: 119 equipamentos, nao 241 radares.

## Lacunas e resultado da pesquisa

- AC: noticias antigas; ainda nao foi localizado cadastro estadual atual consumivel.
- AL: DER indisponivel na consulta; DMTT Maceio institucional. Controladores educativos de ciclovia nao comprovam radar autuador.
- AP: noticia municipal historica e anuncios de afericao; conector atual apenas documental, sem lista vigente normalizada. SETRAP retornou 503.
- AM: Manaus tem conector municipal; nao foi localizado inventario estadual. SEINFRA retornou 403.
- CE: Fortaleza tem conector municipal. DER/SOP e Detran retornaram 503; portal de dados nao permitiu a consulta.
- MS: Campo Grande tem conector municipal. Detran/AGESUL acessiveis, sem cadastro estadual encontrado nas paginas consultadas.
- MT: publicacao municipal antiga; portal SINFRA/ArcGIS encontrado, sem camada oficial de radares confirmada.
- PA: portarias de Belem 2022 e mapa 2020, sem cadastro vigente confirmado. Detran/dados abertos indisponiveis; SETRAN retornou 403.
- PB: Joao Pessoa tem conector municipal. DER retornou 503, sem cadastro estadual obtido.
- PI: portal DER acessivel, busca publica sem resultado para radares; Teresina antiga apenas anuncia lista.
- RJ: conector de locais portateis existente; pagina de fixos retornou 503.
- RN: indice de busca cita lista da STTU, mas `/sttu/equipamentos` retornou 404; DER retornou 503. Nao importar trechos do indice como cadastro.
- RO: Porto Velho tem conector municipal; DER retornou 503.
- RR: portal Detran acessivel sem cadastro encontrado; noticia de Boa Vista e historica/em imagem.
- SC: dados abertos CKAN sem resultado para radar; portal SIE publicou os dois PDFs estaduais agora integrados. Cadastro de fixos estaduais ainda nao obtido.
- Catalogos CKAN consultados em SC, MG e RS retornaram zero conjuntos na busca por `radar`; isso nao prova ausencia de dados fora desses catalogos.

Falha de acesso significa que a fonte nao foi verificada nesta pesquisa, e nao que o orgao nao possua radares ou que nao publique nada. Os demais municipios de cada UF permanecem pendentes ate haver publicacao individual identificada e conector validado.

## Coleta e validacao

As novas fontes entram na agenda semanal existente, via `api.pse tick`; nao criam outro cron nem dependem de IA. O CLI `api.pse sync --fonte NOME` aceita os mesmos conectores da agenda, inclusive arquivos locais para carga assistida. Todos preservam artefato original e registros de proveniencia; formato vazio/alterado gera erro, sem substituir o ultimo snapshot valido.

O instalador privado continua atualizando o fonte publico. **Codigo integrado nao significa dados ja coletados no servidor 3**. Depois de atualizar o servidor, a agenda coleta as fontes novas. Consulte `/api/v1/atualizacoes` para confirmar resultado, rejeicoes e data.

Fixtures reais e manifesto: `tests/fixtures/cadastros_publicos/`. Testes incluem carga pela API, repeticao sem duplicar, exclusao de cameras, desativacoes, faixas, resposta DSR e separacao entre locais elegiveis e aparelhos. GPS/velocidade/serie nao publicados permanecem ausentes.
