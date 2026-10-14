# RadarBrasil v1.4 — Entrega do resolvedor de coordenadas

Data: 2026-10-10. Arquivo baseado no projeto v1.3 que já continha coletor e API `.pse`.

## Código efetivamente entregue

- Lógica de localização de equipamentos sem GPS e candidatos auditáveis em `radarbrasil/georesolver.py`.
- Integração de `LocalVerificacao`, BR/GO/rodovia e quilometragem no ETL do Inmetro.
- Busca por série cruzada, segmentos oficiais calibrados em CSV/GeoJSON WGS84, endereço CNEFE, OSM GeoJSON e consulta pontual Overpass com cache.
- Endpoints `/api/v1/geolocalizacoes` e consulta normal de radar com metadados de coordenada.
- Relatório em JSON ou CSV de TODOS os equipamentos cadastrados, incluindo os sem latitude/longitude.
- Aprovação e rejeição com justificativa e trilha de auditoria. Não existe aprovação automática de OSM nem inferência de GPS exato.
- Novo timer systemd opcional para o resolvedor (sem mudar horário/configuração do coletor preexistente).
- Esquema SQLite gerado novamente a partir de 83 tabelas reais SQLAlchemy; chave primária/estrangeira e CHECK nas entidades novas.

## Resultado de validação local

- `python -m compileall -q radarbrasil`: passou.
- `pytest -q tests/test_national_catalog.py tests/test_psie_auditoria.py tests/test_auditar_fontes_estaduais.py tests/test_enhancements.py`: **32 passaram**.
- `pytest -q tests/test_georesolver.py -k 'not online_osm_mock'`: **8 passaram**.
- `pytest -q tests/test_georesolver.py -k online_osm_mock`: **1 passou**, com Overpass simulado.
- Parte dos testes históricos `tests/test_integration.py` passou, inclusive contrato de formatos, limites de velocidades e parse do Inmetro, mas a execução conjunta da suíte histórica foi interrompida por TIMEOUT do ambiente; não foi contabilizada como regressão integral.
- Banco vazio inicializado localmente: **83 tabelas**.

**IMPORTANTE:** estas verificações NÃO são homologação de downloads reais do SNV, CNEFE, Inmetro, Goinfra ou Overpass. Nenhum aparelho pode ter a posição exata garantida sem documento ou medição de referência. O pacote não inclui coordenadas fictícias de radares reais.

## Pontos para homologar no Debian

1. Faça cópia de segurança do banco antes de criar as cinco tabelas novas.
2. Execute `python -m radarbrasil.collector init` e verifique 83 tabelas em banco novo.
3. Execute `python -m radarbrasil.georesolver preparar-antigos` para registros do Inmetro importados na versão anterior.
4. Importe trechos com quilometragem calibrada e polilinha oficial. Depois execute `resolver-km`.
5. Importe municípios IBGE e arquivos CNEFE somente de unidades necessárias; execute `importar-cnefe`.
6. Para OSM, use apenas a CLI auxiliar de candidato, após existir âncora governamental.
7. Gere `relatorio --formato csv --arquivo /tmp/radares_geoloc.csv`; audite todas as linhas com `sem_coordenada` e `pendente`.
8. Teste `/api/v1/geolocalizacoes?equipamento_id=...` pelo fcgiwrap e confira `localizacao_metadados` no resultado normal da API.
9. Avalie coordenadas inferidas usando estudos técnicos originais; não aprovar inferências automaticamente.

Fonte da documentação completa: `docs/LOCALIZADOR_GEOGRAFICO_V1_4.md`.
