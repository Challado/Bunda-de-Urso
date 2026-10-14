# Perfil bilateral RadarBrasil para EDI/UN-EDIFACT

**Escopo:** resposta `formato=edi` ou `formato=edifact`, intercâmbio da mesma informação de JSON. Não é uma mensagem universal de localização de radares validada por todos os parceiros.

- Envelope de intercâmbio: `UNA:+.? `, `UNB+UNOY:4+RADARBRASIL+CLIENTE+...`, `UNZ+N+ref`.
- Cada bloco é uma mensagem `UNH+ref+GENRAL:D:96A:UN`, `BGM+Z99+ref+9`, um ou mais `FTX+AAI+++...`, `UNT+segmentos+ref`.
- Conteúdo: objeto JSON UTF-8 compactado (não compressão), codificado em Base64 ASCII e fragmentado em partes de no máximo 500 caracteres; cada elemento C108 contém até 500 caracteres; os elementos são separados por `:` dentro de um mesmo FTX.
- Primeira mensagem descreve metadados, as demais contêm um registro de saída; cada registro tem atributo `tipo` (`meta` ou `registro`) e `payload` JSON.
- Parser destinatário: validar UNA/UNB/UNZ, conferir contagens e UNH/UNT, concatenar os componentes de todos os FTX de uma mensagem, decodificar Base64 e depois JSON. Não interpretar texto de FTX sem validação.
- Mensagens muito grandes podem ser divididas entre blocos de FTX conforme implementação. A segmentação, identificação de destinatário, tipos BGM e versão D96A foram adotados como acordo bilateral de software, **não representam guia de implementação aprovado por entidade terceira**.
- Para uso com parceiro EDI externo, preencher MIG: identidade UNB de remetente/destinatário, regras de envelope, comprimento, mensagem/tipo, semântica dos segmentos, encoding, rejeições e política de ACK. Realizar validação com parser externo antes de produção.
