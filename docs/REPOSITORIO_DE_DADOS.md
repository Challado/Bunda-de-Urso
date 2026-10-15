# Código e espelho de dados

O código fica em [Bunda-de-Urso](https://github.com/Challado/Bunda-de-Urso); os dados operacionais são mantidos separadamente em [Bunda-de-Urso-Dados](https://github.com/Challado/Bunda-de-Urso-Dados). O espelho é declarado privado e seus arquivos e relatórios reais devem permanecer no ambiente autorizado. Os testes versionados aqui usam fixtures sintéticas ou já públicas neste repositório.

## Organização local

Com acesso ao repositório de dados, mantenha os dois checkouts como irmãos:

```text
workspace/
  Bunda-de-Urso/
  Bunda-de-Urso-Dados/
    INDICE.csv
    execucoes.csv
    bruto/
    base de dados/
```

O `LEIAME.md` do espelho descreve a publicação e a retenção dos backups. `INDICE.csv` relaciona cada bruto ao hash SHA-256, tamanho, fonte, recurso, artefato e execução. `execucoes.csv` registra o histórico de coleta. A data do arquivo de backup e o snapshot de dados podem avançar em momentos diferentes: novas tentativas de coleta não significam necessariamente novos cadastros.

## Auditoria conjunta

Na raiz do código:

```bash
python3 tools/auditar_repositorio_dados.py --repositorio ../Bunda-de-Urso-Dados
python3 tools/auditar_repositorio_dados.py --repositorio ../Bunda-de-Urso-Dados --testar-coletores
```

O comando confere:

- SHA-256 e tamanho de cada bruto, arquivos fora do índice e entradas duplicadas;
- integridade e chaves estrangeiras do backup mais recente;
- correspondência entre índice, fontes, recursos, artefatos e execuções do SQLite;
- correspondência entre o diário CSV e as execuções armazenadas;
- representação das posições elegíveis pela consulta canônica;
- presença da regra de deduplicação vigente no banco.

Com `--testar-coletores`, relê e normaliza os brutos com acesso à rede bloqueado. Para arquivos que possuem registros no snapshot, exige os mesmos hashes e a mesma ordem dos registros brutos parseados. Arquivos históricos sem registros no snapshot são avisos separados; podem corresponder a tentativas antigas rejeitadas, e precisam ser analisados com o diário. Uma releitura diferente de registros existentes é erro da auditoria.

O teste dos coletores exige os mesmos recursos de sistema usados pela coleta, incluindo `pdftotext` do Poppler para os PDFs suportados. A auditoria não grava no espelho, não gera candidatos e não aplica decisões. O backup é descompactado em diretório temporário, aberto em modo somente leitura e removido ao terminar. Erros de integridade/releitura retornam código de saída diferente de zero; os avisos aparecem em `avisos` no JSON.

## INMETRO nacional e correção 27

O caminho `ColetorINMETRO.carregar("TODAS")` conserva as respostas estaduais em sequência no mesmo arquivo. Esse fluxo contém vários documentos JSON, e `json.loads` de um documento único rejeitava o bruto nacional com “Extra data”.

A releitura agora decodifica os documentos até o fim e mantém o agrupamento por resposta estadual, como na coleta original. Respostas com BOM UTF-8 e espaços entre documentos são suportadas. O conteúdo retornado e arquivado permanece com os bytes originais. Um documento truncado ou lixo ao fim faz a releitura falhar, evitando importar só um prefixo do arquivo.

Isso permite reconstruir os registros parseados e suas evidências; a reconstrução completa das entidades relacionais ainda depende da normalização, das migrações e dos passos posteriores de coleta/metrologia. O código não atribui GPS aos instrumentos do INMETRO sem coordenadas publicadas.

## Preparar uma base para testes

Descompacte o backup escolhido para um diretório de trabalho novo. Depois, aponte `RADAR_DB` para esse SQLite ao executar os testes. O aplicativo continua usando seu caminho configurado, independentemente de onde o espelho foi clonado.

A regra de deduplicação presente no espelho pode ser anterior ao código. O aviso `regra_vigente_ausente_na_base` identifica essa situação. Para medir e preparar a fila numa cópia, use:

```bash
python3 tools/auditar_deduplicacao.py --db /caminho/de/trabalho/radar.sqlite3 --salvar-copia /caminho/novo/fila.sqlite3
python3 tools/listar_duplicidades.py --db /caminho/novo/fila.sqlite3 --escopo equipamento
```

Publicar código no GitHub ou atualizar um backup não reexecuta a deduplicação automaticamente. A ferramenta acima prepara a nova geração sem substituir o banco original.

Os arquivos externos de calibração, quando usados, precisam estar em `RADAR_DATA_DIR/calibracao/ancoras_limpas.csv`. Se o espelho não os distribuir, a auditoria do SQLite e dos brutos não comprova a cobertura de posições inferidas por via/km. Essa dependência deve ser conferida separadamente no ambiente servido.
