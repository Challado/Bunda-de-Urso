# Perfil bilateral Radar Brasil para EDI / UN-EDIFACT

**Escopo:** resposta nos formatos `formato=edi` ou `formato=edifact`
(serializador `core/serializers/edifact_ser.py`, formato `application/EDIFACT`).
É um **perfil bilateral de software** Radar Brasil → consumidor: **não** é
uma mensagem universal de localização de radares validada por terceiros nem
um MIG (Message Implementation Guide) aprovado por entidade externa.

## Envelope de intercâmbio

- Separadores default UNOC (`ISO-8859-1`): elemento `+`, componente `:`,
  terminador de segmento `'`, caractere de liberação `?`.
- **Não** emitimos `UNA` (Service String Advice): os separadores default já
  são os mesmos de UNOC; por isso o `UNB` usa sintaxe nível 3 (`UNOC:3`).
- Envelope: `UNB+UNOC:3+RADARBRASIL:ZZ+RECEPTOR:ZZ+<AAMMDD:HHMM>+<ref>'`
  e, no fim, `UNZ+1+<ref>'`.
- Cada bloco é uma mensagem `UNH+<ref>+GENRAL:D:96A:UN'`, com
  `BGM+RADAR_BRASIL+<ref>'`, `DTM+137+<consultado_em>'` e, opcionalmente,
  `FTX+AAI+1+<nota de layout>'`; fecha com `UNT+<n_segmentos>+<ref>'`.
- **As contagens `UNT`/`UNZ` são calculadas de fato** (não há número fixo).

## Dados

- Um **segmento por ponto/registro**: `RAD0+<col1>+<col2>+...+<col32>'`.
- `RAD0` é um **segmento de projeto (guia bilateral)**. **NÃO** é segmento
  padronizado do diretório UN/EDIFACT e **nunca** é apresentado como tal.
- Ele carrega **exatamente as 32 colunas canônicas do TXT v1** (spec 12.4),
  na mesma ordem imutável publicada em `/api/v1/ajuda`, uma coluna por
  elemento, posição 1..32. Arrays/objetos vão em JSON compacto UTF-8 dentro
  da célula.
- **Elemento vazio** (nada entre dois separadores) = valor **AUSENTE/NULL**.
- Qualquer um dos quatro caracteres reservados dentro de um valor é escapado
  com `?` (`+`→`?+`, `'`→`?'`, `:`→`?:`, `?`→`??`); o leitor desfaz o escape.
- A ajuda (`/api/v1/ajuda`) em `edifact` é envelopada como texto livre: cada
  linha vira um segmento `FTX+AAI+1+<linha>'`.

## Recuperação pelo destinatário

`loads(texto)` devolve, para cada segmento `RAD0`, a lista de elementos já
dessescapados (string) ou `None` para elemento vazio. As linhas de texto
livre (`FTX`) ficam disponíveis em `loads.texto_livre`. Há teste de
ida-e-volta em `tests/test_edifact_dif.py`.

## Divergência em relação ao perfil de referência (registrar)

O perfil de referência descrevia um intercâmbio `UNB+UNOY:4+...`, mensagem
`GENRAL:D:96A:UN`, `BGM+Z99+...`, com o conteúdo JSON codificado em Base64 e
**fragmentado em vários `FTX`/C108 de até 500 caracteres**.

**A nossa implementação NÃO usa esse esquema de Base64/`FTX` fragmentado.**
O que existe hoje (verificado em `core/serializers/edifact_ser.py`) é:
`UNB+UNOC:3+...`, `BGM+RADAR_BRASIL+...` e os dados em **segmentos `RAD0`
com as 32 colunas canônicas** (um elemento por coluna). Esta diferença é
proposital e está documentada no próprio módulo; qualquer contrato com
parceiro EDI externo deve ser reconferido contra o código antes de uso.
(a confirmar: se um consumidor exige o perfil Base64/`FTX` da referência,
isso precisaria ser implementado — não está pronto.)

## Para uso com parceiro EDI externo

Preencher um MIG de fato: identidade `UNB` de remetente/destinatário, regras
de envelope, comprimento, mensagem/tipo, semântica dos segmentos, encoding,
rejeições e política de ACK. **Realizar validação com parser externo antes
de produção.** Não afirmamos conformidade com um tipo de mensagem UN/EDIFACT
padronizado.
