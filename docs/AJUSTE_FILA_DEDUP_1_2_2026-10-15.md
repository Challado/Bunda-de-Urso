# Correção da fila de deduplicação — dedup-1.2

A medição usa o mesmo backup real `radar-2026-10-15_144017.sqlite3.gz` da auditoria anterior: 50.200 pontos, 56.921 registros e nenhuma decisão. As alterações 24, 25 e 26 estão identificadas no código. O resultado estruturado está em [AJUSTE_FILA_DEDUP_1_2_2026-10-15.json](AJUSTE_FILA_DEDUP_1_2_2026-10-15.json).

## O que estava errado

1. **UF confundida com situação operacional.** A PRF publica `ESTADO=ATIVO`, `INOPERANTE` e `E/L OU CERTIFICADO VENCIDOS`, além do campo `UF`. O extrator escolhia o primeiro alias encontrado e usava a situação como UF. Isso atingia 4.767 registros históricos: 2.481 “ATIVO”, 1.473 “INOPERANTE” e 813 “E/L OU CERTIFICADO VENCIDOS”. A comparação agora aceita somente siglas/nomes de UF válidos e prioriza os campos de UF explícitos. Coordenadas fora da faixa também não entram no Haversine. Dados originais publicados continuam armazenados como estavam.
2. **Observação histórica contada como entidade nova.** Coletas com mudança apenas em campos como “dias sem imagens” geravam novas combinações entre registros que já apontavam para o mesmo cadastro. Agora observações da mesma fonte/recurso, mesmas entidades originais e mesmos atributos de comparação usam o menor ID como representante estável. Os IDs de todas as observações ficam em `observacoes_equivalentes`. Campos divergentes, qualidades/precisões diferentes e entidades distintas não são agrupados; cadastros sem entidade original também não são presumidos equivalentes.
3. **Local e instrumento tratados como uma única identidade.** Série diferente pode impedir unir instrumentos no mesmo local; um instrumento pode mudar de local. A fila antiga misturava esses casos com contraditórios e pistas insuficientes. Agora cada par traz avaliação e bloqueadores separados para `ponto` e `equipamento`, além de `escopos_sugeridos`. Aplicar uma decisão respeita os bloqueadores do escopo explicitamente escolhido. Decisões transitivas retiram da fila trabalho já resolvido, sem transformar a própria decisão em nova evidência.

## Resultado medido

| Medida no mesmo backup | dedup-1.1 anterior | dedup-1.2 |
|---|---:|---:|
| Comparações armazenadas | 48.067 | 27.482 |
| Propostas na fila operacional pendente | 33.545 | **2.133** |
| Diagnósticos fora da fila operacional | 14.522 | 25.349 |
| Marcações elegíveis com GPS preservadas | 7.463 | **7.463** |
| Decisões aplicadas | 0 | 0 |

A coluna 1.1 é a geração medida na [auditoria anterior](AUDITORIA_BASE_REAL_2026-10-15.md), não um conjunto adicional gravado no backup. A diferença da fila inclui a mudança de encaminhamento: contraditórios deixam de aparecer como propostas de união. As comparações negativas geradas pela 1.2 ficam disponíveis como diagnóstico.

Foram agrupadas **3.148 observações equivalentes**, preservando todos os 56.921 registros. Há 53.773 representantes de comparação. A geração 1.2 tem 2.133 moderados, 9.062 fracos e 16.287 contraditórios; nenhum forte. Dos 2.133 pares em revisão, 912 cruzam fontes diferentes e 1.221 comparam entidades distintas da mesma fonte. Comparar a mesma fonte continua necessário para possíveis faixas/instalações duplicadas; isso não conta como prova independente.

| Escopo sugerido, sem sobreposição | Propostas |
|---|---:|
| Somente ponto | 1.755 |
| Somente equipamento | 125 |
| Ponto e equipamento | 253 |
| Total | 2.133 |

Assim, a consulta por ponto tem 2.008 propostas e a consulta por instrumento tem 378, com 253 em comum. Esses números são propostas de revisão, não uma contagem de radares comprovadamente duplicados.

## Critérios operacionais

- **Ponto:** o escore considera posição, via/km, sentido e independência; série não aumenta o escore do local. A posição precisa estar a até 200 m, ou haver contexto de via/km/UF, e o escore precisa atingir 0,30. Via/UF divergentes, sentidos opostos, km incompatível ou posição além dessa tolerância bloqueiam a sugestão de ponto. Coordenada isolada nunca dá nível forte.
- **Instrumento:** exige série não genérica igual e corroboração por posição próxima, via/km/UF ou fabricante/modelo. Séries, fabricantes e modelos conflitantes bloqueiam esse escopo. Mudança de local ou sentido não invalida por si só a identidade do instrumento. Evidência forte exige também cadeias independentes.
- **Diagnóstico:** reúne pistas fracas ou pares sem escopo sustentado, preservando os conflitos. Não decide “manter separados” automaticamente: divergências de rodovia podem exigir examinar o documento, a geometria e o período.
- **Aplicação:** continua exigindo autor, fundamentação e escopo. Uma exceção a bloqueadores continua explícita e auditável. Nada é unificado por atingir um limiar.

Os critérios e limiares são persistidos na configuração imutável da versão 1.2. `pontuar` fornece a medição comum; `avaliar_escopos` produz o encaminhamento operacional. Versões antigas continuam consultáveis, sem recalcular suas evidências com a política nova.

## Validação de conservação e reexecução

A geração manteve contagens e SHA-256 das nove tabelas de dados originais. Todas as 7.463 marcações elegíveis continuaram representadas na consulta. O ponto de teste já removido no backup permanece removido.

Uma segunda geração na cópia encontrou **27.482 candidatos existentes e criou zero novos**. A fila permaneceu com 2.133 propostas; nenhuma decisão foi criada. O SHA-256 do SQLite de entrada permaneceu `93d0245193cc4e87d62e5e5f6a23ab8dcbd8d415626ee2cf59f4dafd128fca6b`.

Foram feitas mais 54 chamadas da API, antes/depois da geração, com raio de 1 m e amostras nas 27 UFs. Todos os IDs e coordenadas coincidiram com o cálculo independente sobre o banco.

As regressões cobrem UF operacional da PRF, coordenadas inválidas, preservação de observações divergentes, crescimento de histórico sem novos pares, ponto compartilhado com séries diferentes, instrumento em locais distintos, vias conflitantes, diagnóstico, decisões transitivas, aplicação por escopo e geração/listagem em cópia com paginação.

A suíte final executou **701 testes, sem falhas, erros ou testes pulados**, incluindo a medição de cobertura do backup real. Os seis verificadores do projeto também passaram.

## Preparar e consultar a fila

Foi preparada neste ambiente uma cópia local em `dados/auditoria/fila-dedup-1.2.sqlite3`. Ela é ignorada pelo Git e contém a nova fila, com zero decisões e os dados originais preservados. Não substitui o SQLite em produção. Para reproduzir em um diretório novo:

```bash
mkdir /tmp/revisao-dedup-1.2
gzip -dc 'base de dados/radar-2026-10-15_144017.sqlite3.gz' > /tmp/revisao-dedup-1.2/original.sqlite3
/usr/bin/python3 tools/auditar_deduplicacao.py --db /tmp/revisao-dedup-1.2/original.sqlite3 --salvar-copia /tmp/revisao-dedup-1.2/fila.sqlite3
/usr/bin/python3 tools/listar_duplicidades.py --db /tmp/revisao-dedup-1.2/fila.sqlite3 --escopo equipamento
/usr/bin/python3 tools/listar_duplicidades.py --db /tmp/revisao-dedup-1.2/fila.sqlite3 --escopo ponto
/usr/bin/python3 tools/listar_duplicidades.py --db /tmp/revisao-dedup-1.2/fila.sqlite3 --escopo ambos
```

A listagem abre o banco somente para leitura, aceita `--limite` e `--cursor` e informa o próximo cursor. `--diagnosticos` inclui também as comparações de diagnóstico, mostrando a avaliação do escopo. `auditar_deduplicacao.py` recusa sobrescrever a origem ou um destino existente e só publica a cópia se a verificação de conservação passar.

Na API Python:

```python
dedup.candidatos(conn, estado="pendente", escopo="equipamento")
dedup.candidatos(conn, estado="pendente", escopo="ponto")
dedup.candidatos(conn, incluir_diagnosticos=True)
dedup.candidatos(conn, regra=None, incluir_diagnosticos=True)  # histórico completo
```

Para pontos sem GPS e sem evidência suficiente, a regra não inventa localização. Os quatro cadastros ASTT recuperáveis descritos na auditoria anterior continuam sendo uma operação separada, pela ferramenta específica; esta geração mede a conservação do backup original.
