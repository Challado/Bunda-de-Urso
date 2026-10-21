# Assistência opcional e alternativas sem IA

O aplicativo funciona sem modelo, chave ou assinatura. A seção `[assistente]` do
`radar.conf` tem `habilitado = 0` por padrão. Esse interruptor bloqueia todas as
chamadas a modelos, inclusive a ferramenta antiga de sugestões de municípios.
Não lê a chave para uma consulta desativada. O coletor, o cadastro e a consulta
pública continuam funcionando pelas regras locais.

## O que está disponível

No painel, entre como administrador e abra **Assistência**. As análises são
solicitadas manualmente, pela API, e geram relatórios para revisão:

| Tarefa | Alternativa local | Ajuda opcional da IA |
|---|---|---|
| Extrair documento | Leitores de PDF/tabelas existentes e linhas com coordenadas rotuladas; campos ausentes ficam nulos | Propõe registros com página, citação literal e valores que precisam existir no trecho |
| Correspondências | Distância e regras de identidade existentes: série, modelo, fonte, conflitos e bloqueadores | Prioriza os candidatos permitidos pelas regras |
| Inconsistências | Divergências publicadas, ausência de GPS, coordenadas fora da envolvente do Brasil e faixa de velocidade | Prioriza achados já sustentados pelas evidências |
| Diagnóstico da coleta | HTTP, timeout, DNS, TLS, formato e ações de recuperação conhecidas | Prioriza essas ações; não executa comandos |
| Explicação do radar | Fatos atribuídos às fontes e registros de origem | Prioriza fatos disponíveis, sem criar informação nova |

O resumo da página pública de detalhes é **sempre local**, com ou sem IA ativada.
Visitas públicas e passadas normais do cron não disparam consultas ao modelo.
Há também a opção **Usar somente regras locais nesta análise**.

Nenhuma dessas análises aplica mudanças no cadastro, funde radares ou substitui
registros oficiais. O resultado local permanece visível mesmo quando a IA responde.
Sugestões de municípios feitas por modelo também ficam para revisão: `--aplicar`
continua limitado às propostas da regra local de aproximação.

## Ativar e escolher o provedor

Em **Administração → Configuração**, seção `assistente`, escolha o provedor,
URL e modelo, e marque **Usar IA (opcional)**. Há interruptores independentes
para documentos, correspondências, auditoria, diagnóstico, explicações e municípios.
Desmarcar o interruptor geral desliga todas as funções, mesmo que as individuais
estejam marcadas.

Ollama local, sem chave:

```ini
[assistente]
habilitado = 1
provedor = ollama
url = http://127.0.0.1:11434
modelo = nome-do-modelo-instalado
```

API externa compatível com OpenAI Chat Completions:

```ini
[assistente]
habilitado = 1
provedor = openai_compativel
url = https://api.openai.com/v1
modelo = nome-do-modelo-disponivel-na-sua-conta
```

O provedor precisa aceitar mensagens, resposta `json_object` e limite de tokens.
Outras APIs compatíveis podem usar sua própria URL HTTPS; APIs com protocolo
nativo diferente precisam de um adaptador. Modelo indisponível, incompatibilidade,
chave ausente, timeout, limite ou resposta inválida mantêm a análise local.

Cadastre a chave no campo separado **IA opcional — chave externa** do painel.
Ela não entra no `radar.conf`, não é devolvida pela API, não vai para relatórios e
não fica no armazenamento do navegador. O campo é apagado ao enviar. Pode ser
substituída ou removida sem ativar a IA.

Por padrão, o arquivo é `assistente_chave`, ao lado do `radar.conf`, fora da pasta
web e do checkout. Usa permissão 0660 e o grupo do arquivo de configuração,
sem sudo. A API local permite configurar outro `assistente.chave_arquivo` absoluto,
com a pasta previamente preparada. Também é possível fornecer `RADAR_IA_API_KEY`
no ambiente do processo; nesse caso o painel apenas informa sua presença.
Nunca coloque o segredo na URL nem em argumentos do terminal.

Ao ativar, análises solicitadas podem enviar trechos de publicações e evidências
ao provedor escolhido. Arquivos brutos de fontes não oficiais ficam apenas na
análise local; mensagens brutas de erro da coleta não são enviadas.

## Limites, evidências e documentos difíceis

Os limites do exemplo de configuração são: timeout de 20 segundos, entrada de
20.000 caracteres, saída de 1.024 tokens e até 10 chamadas **por processo**.
Não são uma franquia diária nem um limite financeiro do provedor. Não há
redirecionamento HTTP de requisições com credenciais.

Documentos são lidos exclusivamente do cache configurado, até 8 MiB, com SHA-256
conferido contra o artefato cadastrado. A análise de PDF limita a leitura às
primeiras 30 páginas e informa a limitação. `pdftotext` tem alternativa local.
Se o PDF não tiver texto, o OCR local opcional usa `pdftoppm` e `tesseract`, com
idiomas `por+eng`, até três páginas. Esse OCR só roda com IA documental habilitada;
o modo sem IA também o desliga. Essas ferramentas opcionais não instalam modelos
nem serviços durante uma análise. No Debian: `poppler-utils`, `tesseract-ocr` e
`tesseract-ocr-por` fornecem as ferramentas de OCR.

Sem texto legível ou evidência suficiente, o documento fica para revisão ou
transcrição. O sistema não inventa coordenadas para aparentar uma extração completa.
Página, citação e presença dos números são validadas; isso não substitui conferir
a associação entre colunas de uma tabela e o significado de cada valor.

Os relatórios ficam em `<dados.dir>/calibracao/assistente/`, fora do código,
com a alternativa local, proposta validada, fontes, hashes, versão das regras,
provedor/modelo e data. São acessíveis somente pela gestão administrativa ou
pela API local. As últimas 50 análises aparecem no painel.

## Console e API

Toda entrada passa por `api.pse`. Exemplos no diretório do código:

```bash
python3 web/api.pse assistente status
python3 web/api.pse assistente analisar --tarefa explicacao --ponto P-1130 --sem-ia
python3 web/api.pse assistente analisar --tarefa correspondencias --ponto P-1130
python3 web/api.pse assistente analisar --tarefa auditoria --ponto P-1130
python3 web/api.pse assistente analisar --tarefa documento --artefato 123
python3 web/api.pse assistente analisar --tarefa diagnostico --execucao 456
python3 web/api.pse assistente listar
python3 web/api.pse assistente mostrar --relatorio ID_DO_RELATORIO
```

A API web oferece `GET/POST /api/v1/gestao/assistente`,
`GET /api/v1/gestao/assistente/relatorios/{id}` e
`PUT/DELETE /api/v1/gestao/assistente/chave`. Exige administrador e, nas gravações,
JSON e o cabeçalho `X-Radar-Configuracao: 1`, com verificação de requisição externa.
O corpo da análise usa `tarefa` e `ponto_id`, `artefato_id` ou `execucao_id`, e aceita
`sem_ia: true`. O painel usa essas mesmas rotas; não abre o banco diretamente.
