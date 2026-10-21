# AGETO — radares fixos de Tocantins

A fonte `ageto_to` coleta a [relação geral publicada pela AGETO](https://www.to.gov.br/ageto/lista-de-radares/l3d43475lu1).
O [PDF rev01](https://central.to.gov.br/download/482949), conferido em 21/10/2026,
contém 58 equipamentos, com coordenadas, município, rodovia, km, tipo publicado,
velocidade, quantidade de faixas, série e número Inmetro. Não publica data de
atualização, precisão do GPS ou situação operacional de cada equipamento.

A agenda padrão consulta semanalmente essa fonte. O conector descobre o link
da **lista geral** na página; estudos individuais CEV não são usados como lista
de equipamentos. Se a página não responder, tenta a URL conhecida da rev01.
Falha de download ou mudança no formato registra erro e preserva a carga
anterior. O conector requer `pdftotext` (pacote `poppler-utils`, já verificado
pelo instalador). Não depende de IA ou de serviço pago.

## Carga pela entrada única da aplicação

No diretório da instalação, como operador root:

```sh
python3 web/api.pse sync --fonte ageto_to
```

Quando o portal estiver indisponível, baixe o PDF da relação geral e informe
seu caminho. O exemplo abaixo supõe que o arquivo foi salvo nesse diretório:

```sh
python3 web/api.pse sync --fonte ageto_to --arquivo lista_radares_agetorev01pdf.pdf
```

Banco e cache continuam definidos pelo `radar.conf`, por `core.caminhos`.
A importação preserva o PDF por SHA-256 e os valores publicados por linha.
Repetir a mesma carga não duplica pontos ou instrumentos. Não precisa apagar
a base, criar cron adicional, mudar tabelas ou usar `sudo`.

## Vínculo com o Inmetro

O número Inmetro é persistido como identificador do ponto e do equipamento,
sempre associado à fonte que o publicou. A consulta metrológica relaciona
instrumentos oficiais com série exata, tipo e município compatíveis; números
Inmetro divergentes ou ambíguos impedem a junção. Séries numéricas curtas
precisam também do mesmo número Inmetro. Pontos, instalações, coordenadas e
registros de origem permanecem separados. A consulta preserva o radar AGETO
quando nenhuma verificação estiver disponível.

Caso de referência: TO-080 km 251, Caseara, 40 km/h, duas faixas, série `0049`,
número Inmetro `00.000.770` (equivalente ao `770` do PSIE), coordenadas
`-9.265766, -49.956937`. O estudo individual CEV 049 documenta ambos os sentidos,
mas essa informação não é inferida para os demais equipamentos da relação geral.
A contagem de faixas é preservada no registro da fonte; não são criadas faixas
numeradas ou sentidos que a tabela não publica.

O P-54923 comunitário foi cadastrado em `-9.265218, -49.956872`, cerca de 61 m
do ponto oficial. A proximidade sustenta revisão de correspondência; não atribui
automaticamente identidade física ou certificados ao cadastro comunitário.

## Transparência

A [Resolução CONTRAN nº 798/2020](https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-contran/resolucoes/resolucao798-2020.pdf),
art. 9º, prevê publicidade da relação de medidores e da localização dos fixos.
A [Lei de Acesso à Informação](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm),
art. 8º, §3º, II e III, prevê formatos que facilitem a análise e o acesso
automatizado por sistemas externos. CSV, JSON ou uma API pública com os mesmos
identificadores facilitariam manter o cadastro atualizado. Não foi enviado
pedido de informação ao órgão nesta integração.

## Verificação

`tests/test_ageto_to.py` lê o PDF oficial completo, verifica as 58 posições e
municípios, importa pela `api.pse`, repete a importação e consulta o caso de
Caseara com uma publicação do PSIE. Também cobre números Inmetro divergentes,
preservação do comunitário, formato inválido e descoberta da lista geral.
Esses testes fazem parte da suíte existente no GitHub Actions.
