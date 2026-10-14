# Auditoria nacional PSIE/Inmetro — 10/10/2026

## Resultado VERIFICADO nesta sessão de pesquisa

A consulta em tempo real pelo navegador de pesquisa foi realizada nos URLs
`https://servicos.rbmlq.gov.br/dados-abertos/{UF}/medidores.json` para todas as
27 UFs. Somente AC produziu conteúdo JSON legível na ferramenta; GO, SP, PR,
DF e as demais 22 UFs não produziram conteúdo acessível nessa ferramenta.

**NÃO equiparar falha da ferramenta a HTTP 404, ausência de publicação, ausência de
radares ou inexistência da base nacional.** Esta sessão não forneceu os códigos HTTP
originais das 26 falhas. O domínio PSIE abre normalmente para a tela de consulta.

O arquivo AC continha 2 objetos na data pesquisada, incluindo a verificação de
04/08/2026 e os campos `SiglaUf`, `Estado`, `Municipio`, `LocalVerificacao`,
`DataUltimaVerificacao`, `DataValidade`, `UltimoResultado`, `TipoMedidor`,
`Faixas[]` (NumeroFaixa, NumeroInmetro, NumeroSerie, Sentido, VelocidadeNominal),
`Historico[]` (NumeroCertificado, NumeroEnsaio, Ano, DataLaudo, DataValidade,
TipoServico, Resultado), `Proprietario` (Nome, Municipio, Estado).

Estes dois objetos **não provam completude de cobertura do AC**, muito menos do
Brasil. O exemplo não contém latitude/longitude; `VelocidadeNominal` não deve
ser atribuída automaticamente a velocidade regulamentada da via. Várias faixas
podem ter o mesmo `NumeroSerie` e `NumeroInmetro`: não multiplicar o instrumento.

A página de consulta oficial `https://psie.inmetro.gov.br/Instrumento` exibe
'Para ter acesso aos instrumentos no site Dados Abertos clique aqui'. O catálogo
no portal de dados abertos lista medidores de velocidade JSON/XML por UF e
periodicidade declarada mensal, mas a disponibilidade atual de cada recurso não
foi comprovada na sessão de pesquisa.

## Executar a verificação VERDADEIRA na máquina de produção

O script independente `scripts/auditar_psie_27ufs.py` exige só Python 3 e
biblioteca padrão. Não acessa banco nem apaga cache existente.

```sh
python3 scripts/auditar_psie_27ufs.py --saida /tmp/auditoria_psie --salvar-arquivos
cat /tmp/auditoria_psie/relatorio_psie_27ufs.csv
```

Para testar JSON e XML em todas as UFs:

```sh
python3 scripts/auditar_psie_27ufs.py --formato ambos --saida /tmp/auditoria_psie --salvar-arquivos
```

Para GO/PR/SP/DF isoladamente:

```sh
python3 scripts/auditar_psie_27ufs.py --uf GO --uf PR --uf SP --uf DF --saida /tmp/auditoria_psie
```

Retorna JSON e CSV com status HTTP se recebido, mensagens de falha, tamanho,
hash, quantidade de registros, faixas, séries distintas, certificados/verificações,
última data encontrada, campos observados e exemplos não sensíveis. Só salva
os arquivos originais após validação estrutural, de forma atômica; não muda o
banco. Retorna exit code 2 se qualquer UF não pôde ser auditada.

**Para homologar:** executar de rede externa com acesso real, verificar dados
concretos em ao menos uma amostra por UF, contagens e datas, reconciliar
números de série do PSIE com Goinfra e outra fonte local e comparar com o portal
de consulta de instrumentos. Não marcar cobertura completa por HTTP 200. Se
houve bloqueio, registrar código/resposta/horário e solicitar ao Inmetro a
extração oficial consolidada e atual, mencionando o conjunto de dados PSIE.

## Integração na implantação existente

- Mantenha `INMETRO_IMPORT` manual disponível até que o endpoint seja validado.
- Não habilite os 27 URLs para sincronização automática antes da auditoria.
- Se a auditoria for positiva, carregar os arquivos pelo importador PSIE
  mantendo arrays `Faixas[]`, `Historico[]`, identificadores e proveniência.
- Reconciliar por conjunto número de série, número Inmetro, fabricante/modelo
  quando disponível, município, via e sentido. Mesmo número em múltiplas faixas
  não corresponde a equipamentos separados.
- Nunca inferir GPS nem `situacao_operacional=ativo` de aferição aprovada.
- Se uma fonte estiver indisponível, preservar o último snapshot aprovado e
  informar idade, última confirmação e erro. Não converter falha em zero radar.

## Referências

- https://psie.inmetro.gov.br/Instrumento
- https://dados.gov.br/dados/conjuntos-dados/portal-de-servicos-do-inmetro-nos-estados-psie
- https://servicos.rbmlq.gov.br/dados-abertos/AC/medidores.json
- https://www.gov.br/inmetro/pt-br/acesso-a-informacao/dados-abertos
