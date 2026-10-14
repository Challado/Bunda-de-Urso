# Estado verificado do código e pendências de homologação

Consulte o README, seções 5 a 10: cada pendência tem URL de origem, passos técnicos e critérios de aceite. **Não são pendências genéricas para outra IA adivinhar**.

## Execução funcional testada localmente

- 78 tabelas SQLAlchemy com PK/FK/CHECK/UNIQUE e índices; PostgreSQL, SQLite e MySQL compilam DDL; apenas SQLite foi testado com conexão real.
- Coletor e API `.pse` independentes, sem `cgi` e sem PostGIS.
- Coleta com descoberta CKAN, PRF portáteis e descoberta XLSX da tabela de fixos PRF; parser CSV/JSON/XML/XLSX e cache de artefatos por hash, retentativas e logs.
- Inmetro importação manual JSON de grupos e faixas, certificados e histórico; outros XMLs preservados como estruturas aninhadas, mas cada leiaute externo ainda exige adaptador específico.
- Importador de tráfego ANTT separado de limite regulamentado; desligado por padrão.
- Consultas por distância, ID, cadastro, operações, trechos e tráfego; TXT, JSON, NDJSON, XML, DIF, EDI/EDIFACT bilateral; ajuda em todos os formatos.
- Fontes com status, idade de sincronização, idade de publicação quando declarada, erros e alertas, sem cobertura fictícia.

## Pendências que exigem acesso/integração/homologação adicional

1. **Coletas HTTP reais ANTT/DNIT/PRF:** impossíveis de testar integralmente no ambiente sem resolução DNS. Execute `scripts/validar_fontes_reais.py` num servidor com acesso e compare com 3–5 registros oficiais.
2. **Inmetro automático em 27 UFs:** endpoint de JSON por UF visto em terceiros, mas não homologado/confirmado diretamente no PSIE. Respeitar acesso e CAPTCHA; usar exportação oficial manual se necessário.
3. **Municípios e estados:** seis fontes oficiais com configuração inicial de importação manual; não há conectores testados para todas as unidades federativas/prefeituras.
4. **Homologação outros SGBDs:** PostgreSQL/MariaDB/MySQL/Firebird necessitam criação real, testes de integridade e migrations; apenas SQLAlchemy compilou DDL para SQLite, PostgreSQL e MySQL.
5. **Operações e trechos:** importação relacional de operações pontuais quando os dois timestamps com fuso são publicados está pronta; correlação de trechos críticos com geometria exige publicação/ETL própria.
6. **Aprimoramento do histórico:** outros campos originais estão disponíveis como payload no banco e nas respostas detalhadas; vários ainda não alimentam uma entidade canônica específica.
7. **Deduplicação com intervenção:** candidatos são gerados; rotina de aprovação de fusão interfontes transacional e reversível com evidência de identidade ainda é pendente.
8. **EDIFACT:** foi implementado perfil bilateral GENRAL/FTX Base64, NÃO um MIG universal aceito por terceiros. DIF não foi homologado com todos os leitores de planilha.
9. **Carga/streaming/migrations:** ingestão de planilhas grandes usa lista em memória; não foi homologada para datasets de milhões de observações. Não há gerenciador de migrations para esquema já em produção.
10. **Notificações externas:** alertas locais/journald existem; envio por e-mail/webhook e painel administrativo precisam implantação adicional.

**Qualquer integração não testada deve constar como não validada; não criar dados de fonte fictícios para ocultar falhas.**
