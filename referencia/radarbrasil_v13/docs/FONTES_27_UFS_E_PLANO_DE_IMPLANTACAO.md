# Radar Brasil — Inventário nacional das 27 UFs (10/10/2026)

Este é um catálogo **de fontes oficiais localizadas**, não uma comprovação de cobertura completa.
Cada estado pode ter radares de muitos municípios e concessionárias diferentes. Encontrar
uma publicação municipal **não cobre** todas as rodovias/municípios do estado. O campo
`cobertura_estadual_confirmada` permanece false por padrão e deve ser recalculado por
circunscrição efetivamente inventariada.

Os URLs neste documento são páginas/documentos oficiais identificados por pesquisa.
**Nenhum endereço de download ou API está declarado operacional até teste real**.
As fontes novas cadastradas em `config/sources.json` ficam `enabled=false` e
`format=manual_json` até a implementação específica. O formato manual_json NÃO
significa que o órgão publique JSON: o implementador deverá descobrir o recurso real.

Legenda da evidência:
- `conjunto_dados` / `geoarquivo_oficial`: recurso anunciado (CSV/XLSX/KML/GeoJSON).
- `relatorio_oficial` / `lista_documentos` / `lista_localizacao`: documento/lista
  oficial, pode exigir PDF/HTML, descoberta de link, geocodificação verificável.
- `lista_trechos`: trechos onde fiscalização é possível, nunca radar fixo comprovado.
- `lista_historica`: publicação histórica, não prova situação ativa atual.
- `institucional_sem_lista`: órgão oficial encontrado, SEM publicação de lista
  individual de equipamentos comprovada nesta pesquisa. Necessita solicitação de dados.

## Inventário por estado

| UF | Fonte | Evidência | URL oficial |
|----|-------|-----------|-------------|
| AC | Detran-AC - relatório histórico de equipamentos em Rio Branco | lista_historica | https://agencia.ac.gov.br/detran-anuncia-retorno-da-fiscalizacao-eletronica/ |
| AL | DER-AL - canal oficial | institucional_sem_lista | https://alagoasdigital.al.gov.br/orgao/49 |
| AP | CTMac Macapá - pontos publicados | lista_localizacao_historica | https://macapa.ap.gov.br/radares-de-macapa-passam-a-ter-velocidade-maxima-permitida-de-60-km-h-a-partir-desta-terca-21/ |
| AM | IMMU Manaus - relação oficial 2026 | lista_localizacao | https://www.manaus.am.gov.br/noticia/transito/fiscalizacao-eletronica-salvar-vidas/ |
| BA | SEINFRA Bahia - mapas KML radares fixos e estáticos | geoarquivo_oficial | https://www.ba.gov.br/infraestrutura/12046/mapas |
| CE | AMC Fortaleza - mapa e dados fiscalização eletrônica | geoarquivo_oficial | https://mapas.fortaleza.ce.gov.br/mapa/538/equipamentos-de-fiscalizacao-eletronica |
| DF | Detran-DF - mapa de equipamentos eletrônicos no Geoportal | geoportal_documentado | https://detran.df.gov.br/wp-content/uploads/2022/10/Equipamentos_Eletronicos.pdf |
| ES | Cariacica - mapa, estudos e faixas monitoradas | lista_documentos | https://cariacica.es.gov.br/pagina/ler/861/mapa-radares |
| GO | Goinfra - relatório de equipamentos de monitoramento | relatorio_oficial | https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/ |
| MA | Detran-MA - fiscalização eletrônica rodovias estaduais | lista_localizacao | https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582 |
| MG | DER-MG - radares fixos e portáteis | lista_localizacao | https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis |
| MS | Agetran Campo Grande - radares ativados | lista_localizacao | https://www.campogrande.ms.gov.br/cgnoticias/noticia/novos-radares-operam-em-carater-educativo-ate-14-de-julho/ |
| MT | Cuiabá - mapa e equipamentos | lista_historica | https://www.cuiaba.mt.gov.br/noticias/comeca-campanha-de-esclarecimento-sobre-a-fiscalizacao-eletronica |
| PA | SEGBEL Belém - relação/portarias | lista_documentos | https://seguranca.belem.pa.gov.br/portarias-de-ativacao-e-desativacao-de-radares/ |
| PB | Semob João Pessoa - locais publicados | lista_localizacao | https://www.joaopessoa.pb.gov.br/noticias/secretarias-e-orgaos/semob/semobjp-orienta-populacao-sobre-novos-locais-com-radares-medidores-de-velocidade/ |
| PR | DER-PR - fiscalização de velocidade | lista_localizacao | https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade |
| PE | Recife - equipamentos de fiscalização (CSV/dicionário) | conjunto_dados | https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito |
| PI | STRANS Teresina - serviço Localização de Radares | lista_historica | https://antigo.pmt.pi.gov.br/2019/04/10/localizacao-dos-radares-sera-divulgada-mensalmente-no-site-da-prefeitura/ |
| RJ | DER-RJ - radares portáteis por local/horário | lista_localizacao | https://sgitp.der.rj.gov.br/radares-portateis |
| RN | STTU Natal - portal oficial | institucional_sem_lista | https://www.natal.rn.gov.br/sttu |
| RS | DAER-RS - locais de fiscalização com radar portátil | lista_trechos | https://www.daer.rs.gov.br/radares-moveis |
| RO | Porto Velho - relação radares fixos e estudos 2026 | lista_documentos | https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos |
| RR | Boa Vista - locais de radares | lista_localizacao_historica | https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-novos-equipamentos-de-fiscalizacao-eletronica-para-reduzir-acidentes-em-boa-vista |
| SC | Joinville DETRANS - estudos técnicos 2026 | lista_documentos | https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/ |
| SP | DER-SP - dados abertos radar XLSX | conjunto_dados | https://dadosabertos.sp.gov.br/dataset/radar |
| SE | DER Sergipe - localização de radares fixos e estudos técnicos | lista_documentos | https://der.se.gov.br/localizacao-de-radares-fixos/ |
| TO | Araguaína ASTT - relação de radares 2026 | lista_localizacao | https://www.araguaina.to.gov.br/servicos/medidores-de-velocidade-lista-de-enderecos |

**Complementos de última verificação:** para Sergipe, priorizar o DER-SE e manter a SMTT Aracaju como fonte municipal adicional; no DF, o documento do Detran-DF ensina a consultar uma camada geográfica pública, cujo serviço e possibilidade de exportação ainda precisam ser identificados; em AC e PI, os dados publicados encontrados são históricos (2013 e 2019), NÃO comprovam radares em 2026.

## Fontes federais comuns a todas as UFs

- INMETRO PSIE: https://servicos.rbmlq.gov.br/Instrumento (Instrumentos aferidos; não necessariamente coordenadas GPS nem operação ativa)
- PRF radares fixos: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
- DNIT PNCV: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
- ANTT radares: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17

## Instruções operacionais EXATAS para completar cada UF

Para cada `codigo_fonte` listado em `config/fontes_nacionais_27ufs.json`:

1. Abrir URL oficial e registrar timestamp da verificação, URL final, contato e
   órgão com circunscrição. Se não houver arquivo, procurar nos links da página,
   no portal de dados abertos e na LAI do órgão; jamais inventar URL por padrão.
2. Classificar documento em CADASTRO_DE_EQUIPAMENTO, OPERACAO_REAL,
   TRECHO_ELEGIVEL, ESTUDO_TECNICO, CERTIFICADO_METROLOGICO ou ESTATISTICA.
   Cada categoria tem entidades relacionais e semântica diferentes.
3. Identificar formato de cada recurso (CSV, XLSX, JSON, GeoJSON, KML, HTML, PDF).
   Para XLSX checar cada aba e todas as colunas; para PDF, tabela legível com
   extração de layout validada por inspeção visual e amostragem independente.
   Tabela escaneada só com OCR assistido e quarentena, nunca ingestão cega.
4. Documentar dicionário de dados REAL para aquela versão, tipo, nulos, unidade,
   encoding, número de linhas, datas de publicação, nome de arquivo e hash SHA256.
5. Implementar conector **específico** que passe pelo Downloader compartilhado;
   limite de taxa, cache persistente, ETag/Last-Modified, retries, publicação
   atômica, preservação de arquivo original e relatório de rejeições.
6. Normalizar coordenadas WGS84; GeoJSON/KML usam ordem LONGITUDE,LATITUDE;
   converter integer em microssegundos de grau (10^-6) **somente para fonte cujo
   dicionário comprovar**. Endereço/rodovia/km isolados NÃO viram GPS artificial.
7. Normalizar velocidade regulamentada leve/pesado/geral/faixa em km/h,
   diferenciando `VelocidadeNominal` Inmetro de limite da via e velocidade medida
   em tráfego de veículos. Conflito fica preservado, nunca escolhe arbitrariamente.
8. Conferir número de série, modelo, fabricante, ID de órgão, equipamento físico,
   ponto de fiscalização, faixas e sentidos; não deduplicar apenas pela distância;
   manter lista de candidatos e resolução humana auditável.
9. Comparar >=5 registros não triviais por UF contra o PDF/tabela original, com
   casos de sentidos opostos, séries repetidas, múltiplas faixas e desativação;
   comparar totais por município/rodovia.
10. Executar testes automatizados de parsing e integração com snapshots/fixtures
    capturados LEGITIMAMENTE; executar um download real autorizado. Só então
    habilitar a fonte na configuração; registrar data e evidências de homologação.
11. A cobertura exige saber QUAIS municípios e rodovias cada fonte cobre,
    não apenas a sigla UF. Continuar mostrando `sem_cobertura` para locais sem
    cobertura documentada e `completude_confirmada=false` até auditoria.
12. Se a fonte não disponibilizar dados públicos, abrir pedido LAI e registrar
    protocolo. Não contornar autenticação, CAPTCHA ou bloqueios de acesso.

### Pendências pontuais por UF

#### AC — DERACRE - contato institucional

Fonte: https://deracre.ac.gov.br/contato/

Procurar DERACRE, Detran-AC e RBTRANS; solicitar via LAI inventário de equipamentos, certificados, estudos, coordenadas, limites e vigência.

**Estado:** coletor não homologado; sem_listagem_confirmada. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### AL — DER-AL - canal oficial

Fonte: https://alagoasdigital.al.gov.br/orgao/49

DER-AL e DMTT Maceió: dados de câmeras não provam radar de velocidade; solicitar lista oficial via LAI.

**Estado:** coletor não homologado; sem_listagem_confirmada. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### AP — CTMac Macapá - pontos publicados

Fonte: https://macapa.ap.gov.br/radares-de-macapa-passam-a-ter-velocidade-maxima-permitida-de-60-km-h-a-partir-desta-terca-21/

Lista de 17 locais divulgada em 2022; localizar publicação recente, documentos técnicos e coordenadas.

**Estado:** coletor não homologado; validar_atualidade. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### AM — IMMU Manaus - relação oficial 2026

Fonte: https://www.manaus.am.gov.br/noticia/transito/fiscalizacao-eletronica-salvar-vidas/

Lista de equipamentos e locais de 2026; checar atualizações e status posterior.

**Estado:** coletor não homologado; validar_arquivo. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### BA — SEINFRA Bahia - mapas KML radares fixos e estáticos

Fonte: https://www.ba.gov.br/infraestrutura/12046/mapas

Página oficial oferece KML, mapa web e PDF; descobrir links atuais e testar geometria/atributos.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### CE — AMC Fortaleza - mapa e dados fiscalização eletrônica

Fonte: https://mapas.fortaleza.ce.gov.br/mapa/538/equipamentos-de-fiscalizacao-eletronica

2026: GeoJSON, KML, SHP e CSV, campos sitio/status/finalidade/endereco/viasentido/bairro/faixas_via/faixas_fis.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### DF — DER-DF - lista histórica equipamento/velocidade

Fonte: https://www.der.df.gov.br/wp-content/uploads/2018/01/Pardais_2011.pdf

Documento de 2011 NÃO deve ser importado como equipamentos ativos de 2026. Pedir relação atual ao DER-DF e Detran-DF.

**Estado:** coletor não homologado; validar_atualidade. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### ES — Cariacica - mapa, estudos e faixas monitoradas

Fonte: https://cariacica.es.gov.br/pagina/ler/861/mapa-radares

Publica mapa, estudos técnicos e PDF de faixas; município não cobre todo o Espírito Santo.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### GO — Goinfra - relatório de equipamentos de monitoramento

Fonte: https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/

Atualizado 07/10/2026: lista com códigos, séries, tipos, rodovias, km, coordenadas, velocidades, datas, estudos e notas; links e formato variam.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### MA — Detran-MA - fiscalização eletrônica rodovias estaduais

Fonte: https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582

Detran-MA declara divulgar localização e informações de radares estaduais.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### MG — DER-MG - radares fixos e portáteis

Fonte: https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis

Conferir sentidos, equipamentos e status em cada publicação.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### MS — Agetran Campo Grande - radares ativados

Fonte: https://www.campogrande.ms.gov.br/cgnoticias/noticia/novos-radares-operam-em-carater-educativo-ate-14-de-julho/

Publicação 26/06/2026 informa locais e entrada em fiscalização em 15/07; cidades fora da capital não estão cobertas.

**Estado:** coletor não homologado; validar_arquivo. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### MT — Cuiabá - mapa e equipamentos

Fonte: https://www.cuiaba.mt.gov.br/noticias/comeca-campanha-de-esclarecimento-sobre-a-fiscalizacao-eletronica

Publicação 2015: não considerar equipamentos atuais sem atualização oficial.

**Estado:** coletor não homologado; validar_atualidade. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### PA — SEGBEL Belém - relação/portarias

Fonte: https://seguranca.belem.pa.gov.br/portarias-de-ativacao-e-desativacao-de-radares/

Portarias de ativação/desativação com identificadores; reunir situação temporal e complementar com relação de radares.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### PB — Semob João Pessoa - locais publicados

Fonte: https://www.joaopessoa.pb.gov.br/noticias/secretarias-e-orgaos/semob/semobjp-orienta-populacao-sobre-novos-locais-com-radares-medidores-de-velocidade/

Prefeitura aponta portal.semobjp.pb.gov.br para lista completa; conferir versão vigente.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### PR — DER-PR - fiscalização de velocidade

Fonte: https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade

Fontes fixos e portáteis; trechos possíveis não são operações confirmadas.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### PE — Recife - equipamentos de fiscalização (CSV/dicionário)

Fonte: https://dados.recife.pe.gov.br/dataset/equipamentos-de-monitoramento-e-fiscalizacao-de-transito

CSV e dicionário JSON, licença ODbL; separar radares de câmeras de monitoramento.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### PI — STRANS Teresina - canal institucional

Fonte: https://www.transparencia.teresina.pi.gov.br/secretarias

Nenhum arquivo oficial completo de radar comprovado nesta pesquisa; consultar STRANS e DER-PI via LAI.

**Estado:** coletor não homologado; sem_listagem_confirmada. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### RJ — DER-RJ - radares portáteis por local/horário

Fonte: https://sgitp.der.rj.gov.br/radares-portateis

Lista com rodovia/km/velocidade/sentido e janela 06-22; NÃO significa equipamento presente o dia todo.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### RN — STTU Natal - portal oficial

Fonte: https://www.natal.rn.gov.br/sttu

Não foi identificada listagem estruturada atual; solicitar relação de radares e documentos à STTU/DER-RN.

**Estado:** coletor não homologado; sem_listagem_confirmada. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### RS — DAER-RS - locais de fiscalização com radar portátil

Fonte: https://www.daer.rs.gov.br/radares-moveis

Atualização declarada semanal; pontos elegíveis não equivalem a operações pontuais confirmadas.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### RO — Porto Velho - relação radares fixos e estudos 2026

Fonte: https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos

PDF detalhado e série/validades atualizados em 2026.1.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### RR — Boa Vista - locais de radares

Fonte: https://boavista.rr.gov.br/noticias/2024/1/prefeitura-instala-novos-equipamentos-de-fiscalizacao-eletronica-para-reduzir-acidentes-em-boa-vista

Notícia municipal de 2024 descreve locais; verificar cadastro vigente.

**Estado:** coletor não homologado; validar_atualidade. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### SC — Joinville DETRANS - estudos técnicos 2026

Fonte: https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/

Atualização agosto/2026 e PDFs por equipamento; não representa todos municípios SC.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### SP — DER-SP - dados abertos radar XLSX

Fonte: https://dadosabertos.sp.gov.br/dataset/radar

XLSX de localização e informações dos radares DER, atualizado agosto/2026.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### SE — Aracaju SMTT - lista de radares e velocidades

Fonte: https://smtt.aracaju.se.gov.br/smttsite/Medidores%20de%20Velocidade/equipamentos%20de%20fiscalizao%20eletrnica%20smtt%20aracaju.pdf

PDF com séries, números Inmetro, tipo, sensor e velocidade km/h; testar atualização da lista.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

#### TO — Araguaína ASTT - relação de radares 2026

Fonte: https://www.araguaina.to.gov.br/servicos/medidores-de-velocidade-lista-de-enderecos

Página atualizada jan/2026, oferece download de endereços; não cobre todas rodovias estaduais.

**Estado:** coletor não homologado; recurso_para_descobrir. Abrir recurso oficial, levantar campos, preparar testes reais, publicar cobertura por órgão/segmento.

## Testes-alvo obrigatórios para Goiás

Pontos Waze fornecidos pelo usuário (coordenadas, não IDs oficiais):

- -17.625377,-51.060863
- -17.584521,-51.089497
- -17.529214,-51.111256
- -16.459361,-51.671518
- -16.385100,-51.564215

Homologar contra o relatório atual da Goinfra, verificando cada correspondência
com código, série, km, sentido, limite regulamentado, datas e distância
Haversine; usar tolerâncias 100 m / 1 km / 2 km / 5 km / 20 km. A publicação
Goinfra esclarece que coordenadas e marcos são referenciais do trecho fiscalizado,
não coordenadas de precisão garantida. Resultados próximos não são prova de
identidade do POI comunitário com o equipamento oficial.

Confirmação independente necessária para cada ponto antes de afirmar o match.

## Modelo de solicitação pela Lei de Acesso à Informação

"Solicito, em formato aberto reutilizável (CSV, XLSX, GeoJSON ou JSON), a
relação integral e atualizada dos equipamentos de fiscalização eletrônica de
velocidade sob circunscrição desse órgão. Para cada equipamento e faixa,
solicito identificador, número de série, fabricante/modelo, tipo,
localização geográfica WGS84 (ou rodovia/km/endereço), município, sentido,
faixas, velocidade regulamentada geral/leves/pesados, situação, data de
instalação e ativação, inativações/substituições, data de aferição,
certificado, estudo técnico, periodicidade da atualização e dicionário dos
campos, com indicação da situação operacional atual. Solicito também a relação
de pontos/trechos autorizados para fiscalização portátil, diferenciando-os
explicitamente das operações efetivamente realizadas. Favor informar a URL
pública ou endpoint para futuras atualizações automatizadas e a licença de uso."

## Controle da completude

A lista não equivale a 27 conectores operacionais e menos ainda 5.570 municípios.
Checklist final por fonte: endpoint validado, importação real, contagem reconciliada,
campos e velocidades verificados, identidades auditadas, período de vigência,
licença, série temporal, cache testado, teste de consulta espacial, cobertura por
jurisdição e status local confirmado.
