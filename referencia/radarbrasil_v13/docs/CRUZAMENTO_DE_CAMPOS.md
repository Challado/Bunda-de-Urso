# Conferência de campos e regras de harmonização (10/10/2026)

**Natureza da evidência:** revisão de dicionários e páginas públicas, NÃO validação de download/importação real de todas as fontes. A disponibilidade de cada endpoint somente pode ser confirmada durante a execução do coletor. A implementação preserva o payload original de cada registro.

## ANTT — cadastro de radares, dado oficial
Dicionário: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17/resource/5e883dd4-48a6-485a-87b4-146327af3c7f/download/radar_dicionario_dados.pdf
Conjunto: https://dados.antt.gov.br/dataset/79d287f4-f5ca-4385-a17c-f61f53831f17

| Coluna na fonte | Destino/semântica | Situação |
| --- | --- | --- |
| concessionaria | organizacao/concessionária; também payload original | associação relacional em ponto_organizacao quando há ponto e concessionária |
| ano_do_pnv_snv | versão do sistema rodoviário, NÃO data instalação | preservado no payload original |
| tipo_de_radar | função controlador/redutor, NÃO tipo físico fixo/móvel | classificador de função + original |
| rodovia | via.codigo | normalizado |
| uf | uf.sigla | normalizado como UF; cadastros IBGE não inventados |
| km_m | ponto_fiscalizacao.km | normalizado |
| municipio | texto original de município | retornado sem criar IBGE fictício |
| tipo_de_pista | ponto_fiscalizacao.tipo_pista | normalizado |
| sentido | faixa_fiscalizacao.sentido | normalizado com texto original |
| situacao | ponto_fiscalizacao.situacao_operacional | normalizado; nome original preservado |
| data_da_inativacao | data de inativação; não inferir remoção física | original preservado; transposição relacional pendente |
| latitude | posicao_geografica.latitude | normalizado |
| longitude | posicao_geografica.longitude | normalizado |
| velocidade_leve | limite_velocidade: categoria leves | normalizado, apenas limite legal |
| velocidade_pesado | limite_velocidade: categoria pesados | normalizado, apenas limite legal |

A designação "redutor" ou "controlador" não comprova que o dispositivo seja fixo, nem se a operação é pontual.

## ANTT — tráfego, conjunto DIFERENTE
Dicionário: https://dados.antt.gov.br/dataset/269aebaa-05e7-4d76-a105-408f12bf4094/resource/7d32f5d1-7a5d-403b-8db5-09e7e11addf1/download/dicionario_de_dados_volume_radar.pdf

Colunas: concessionaria, identificador, rodovia, uf, km_m, municipio, tipo_de_pista, latitude, longitude, data_da_passagem, sentido_da_passagem, faixa_da_passagem, velocidade, tipo_de_veiculo, volume_total. **O campo velocidade é velocidade de passagem/observação, e JAMAIS deve ser usado como limite regulamentado.** O importador de tráfego agregado está implementado em `observacao_trafego`, desligado por padrão para homologação e volume elevado. NUNCA cadastrar observação de passagem como velocidade regulamentada.

## DNIT — PNCV
Conjunto: https://servicos.dnit.gov.br/dadosabertos/dataset/controle-de-velocidade
Último arquivo listado nesta revisão: "Controle de Velocidade - Julho/2026", XLSX.
Colunas gerais documentadas: UF, rodovia, km, tipo de equipamento (CEV/CEM/REV), faixas controladas, sentido, código de estudo técnico, código do equipamento, situação. Os nomes físicos das colunas do XLSX e a variabilidade entre abas devem ser validados pelo coletor em execução real. Não presumir que DNIT publique velocidade regulamentada nessa planilha.

## PRF — radares fixos, portáteis e trechos críticos
Fontes: https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/radares-fixos
https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/lista-de-radares
https://www.gov.br/prf/pt-br/assuntos/fiscalizacao-de-velocidade/trechos-criticos

Pode haver identificadores administrativos distintos associados ao mesmo número de série, mas isso sozinho NÃO comprova duplicidade se fabricante e histórico não estiverem disponíveis. Trecho crítico não implica radar instalado ou operação com horário confirmado. A relação de radares fixos utiliza link oficial para tabela dinâmica, a qual oferece exportação XLSX; `prf_fixed_discover` identifica a planilha e falha com mensagem explícita se o link mudar.

## INMETRO/PSIE — medidores
https://servicos.rbmlq.gov.br/Instrumento

Campos exemplificativos identificados em estrutura de projeto independente e sujeitos a validação com origem oficial: SiglaUf, Municipio, LocalVerificacao, DataUltimaVerificacao, DataValidade, UltimoResultado, TipoMedidor, Faixas[].{NumeroFaixa,NumeroInmetro,NumeroSerie,Sentido,VelocidadeNominal}, Historico[].{NumeroCertificado,NumeroEnsaio,Ano,DataLaudo,DataValidade,TipoServico,Resultado}, Proprietario. **VelocidadeNominal não é automaticamente velocidade regulamentada.** Importador de arquivo existe, mas o endpoint de download por UF **não foi validado como API pública atualmente operacional**. Não proclamar integração automática pronta.

## Governos estaduais e municipais
Configurar novas origens individualmente a partir dos arquivos de cada órgão. Nesta versão não há importadores autenticados e testados de todos os DERs e municípios; a cobertura nacional é PARCIAL. A ausência de resultado NÃO prova ausência de fiscalização.

## Duplicidade, fonte e confiança
1. Identificador oficial pode identificar um ponto, um equipamento ou uma faixa; a origem determina o escopo.
2. Número de série identifica instrumento somente com contexto de fabricante/modelo. Coincidência isolada gera candidato, não certeza.
3. Coordenadas próximas + mesma rodovia/km podem identificar UM PONTO e DOIS instrumentos, sem confundir ponto com equipamento.
4. Não fundir sentidos opostos se as evidências apontarem dispositivos físicos distintos.
5. Múltiplas faixas com mesmo instrumento não constituem radares físicos duplicados.
6. Guardar todos os registros originais e seus hashes, datas e URLs.
7. Limites distintos para mesma categoria/faixa geram conflito explícito; não arbitrar um valor.
8. Dados não mapeados devem continuar disponíveis no payload original exposto no retorno detalhado.
9. Dados que exigem confirmação de origem ou API são marcados como não validados, nunca simulados.

## Referências externas de engenharia (não são fontes oficiais)
- https://github.com/GabrielHiro/consulta-instrumentos-INMETRO (utiliza dados de exemplo; não comprova integração oficial)
- https://github.com/zyadhpl/velox (OSM/Overpass)
- https://github.com/tomsnunes/peugeot_citroen_rt6_maparadar_updater (conversão de radares e direções)
- https://github.com/datascry/alpr2osmand (estratégias de cache; câmeras ALPR não são radares de velocidade)
