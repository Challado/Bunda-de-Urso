# Requisitos vigentes — complemento obrigatório ao contrato histórico

1. FONTES: dados públicos oficiais são a fonte PRIMÁRIA. Por autorização posterior do solicitante, OSM pode ser consultado unicamente como fonte comunitária de CANDIDATOS para localizar equipamento já identificado oficialmente, sem comprovar existência/velocidade/operação e sem promoção automática. Waze, MapaRadar e outras fontes comerciais não integram o cadastro oficial.
2. INVENTÁRIO: `config/fontes_nacionais_27ufs.json` contém pelo menos uma referência por UF, mas NÃO demonstra cobertura estadual; as fontes municipais não podem ser extrapoladas para todos os municípios. `config/fontes_oficiais_prioritarias_2026-10-10.json` traz links oficiais com formatos e ressalvas específicos.
3. AUDITORIA: executar `python3 scripts/auditar_fontes_estaduais.py --online --saida /tmp/radar_auditoria_ufs.json` em Debian com internet; revisar candidatos e efetuar a coleta em conectores reais. O auditor somente testa páginas e extrai links; não baixa bases integrais nem altera banco.
4. IMPORTADORES PENDENTES: cada fonte exige confirmar URLs definitivas, data de publicação, MIME/magic, nomes de colunas, EPSG/CRS, histórico, licenciamento, tipo de equipamento, limites de velocidade, distâncias, múltiplas faixas, status, número de série e registros publicados. Não habilitar automaticamente uma fonte só por existir URL.
5. HOMOLOGAÇÃO: antes de classificar UF como coberta, verificar quantas autoridades e municípios são cobertos e qual percentual. Dados de terceiros governamentais têm natureza documental; autorizações, competência fiscalizatória e atualidade devem ser preservadas.
6. DEDUPLICAÇÃO: o mesmo ponto pode ter faixas e instrumentos diferentes. Série igual pode ter mais de uma faixa; mesmo código com série diferente pode representar troca; coordenadas iguais não implicam fusão. Guardar todas as fontes originais, conflitos, histórico e justificativas.
7. COORDENADAS: `latitude`/`longitude` padronizadas em WGS84; dados UTM reprojetados, nunca tratados como graus; GO possui coordenadas inteiras em milionésimos; endereço e km sem GPS não podem ser convertidos arbitrariamente em posição de radar.
8. API: manter GET/POST com TXT delimitado configurável, JSON, NDJSON, XML, DIF e UN/EDIFACT; `/api/v1/ajuda`; indicações de cobertura e cache; preservar velocidade de fiscalização separada da velocidade nominal metrológica e de passagens de veículos.
9. RELATÓRIOS: por UF e por autoridade, registrar última coleta validada, idade de publicação, total de registros, instrumentos físicos consolidados, itens sem GPS, inconsistências, e se existem municípios ainda sem fonte conhecida.
10. BLOQUEIO: nenhuma consulta vazia em local sem dados suficientes deve afirmar inexistência de radar; status `sem_cobertura` ou equivalente.

Este adendo tem precedência sobre qualquer sugestão incompatível nos documentos v1.0/v1.1.

## Emenda v1.4 (posterior e prevalente)

A implementação operacional da resolução de coordenadas e da exceção OSM-CANDIDATOS encontra-se em `docs/LOCALIZADOR_GEOGRAFICO_V1_4.md`. Este adendo posterior prevalece sobre proibições antigas do OSM, apenas para localizar pontos já cadastrados por órgão oficial.
