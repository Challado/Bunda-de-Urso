# Junção de metrologia entre fontes oficiais

A consulta anterior seguia somente `INSTALACAO.equipamento_id` até
`VERIFICACAO_METROLOGICA.equipamento_id`. A ingestão reaproveita o equipamento
no mesmo ponto, mas preserva IDs diferentes entre publicações. Isso deixava um
radar localizado pela GOINFRA sem o histórico já armazenado no cadastro do Inmetro.

O detalhe agora junta os equipamentos pela série publicada, tipo de instrumento
e código IBGE do município. Usa `JOIN` sobre as entidades normalizadas, com
índices, sem varrer JSON para tentar descobrir correspondências em cada visita.
Espaços externos e caixa na série são normalizados para comparação. Não faz
comparação aproximada, nem usa proximidade ou IA para identificar o instrumento.

As duas pontas precisam ter procedência oficial e a verificação deve apontar
para seu registro oficial de origem. Séries vazias/genéricas, município ausente,
tipos diferentes e conflitos de fabricante/modelo não geram associação. Decisões
ativas de manter equipamentos separados prevalecem. A consulta respeita a
remoção/desabilitação do ponto associado.

Essa junção apresenta o histórico do instrumento: preserva o ID, GPS, limites
da via e instalações do radar consultado. Não funde pontos, não aplica decisões
de deduplicação e não altera a origem no banco durante um GET. As verificações
trazem `equipamento_origem_id`, fonte e registro; `juncao_metrologica` informa
o critério e os equipamentos de origem. Fontes metrológicas também entram em
`fontes` e `dados_por_fonte`, com `escopo_vinculo= "equipamento"` na publicação.
A página identifica esse vínculo e mantém cada bloco de fonte aberto/recolhível.

## Caso de Iporá, GO-060

Na cópia `radar-2026-10-21_144002.sqlite3.gz`, as consultas pela API corrigida unem:

| Radar localizado | Série | Cadastro metrológico | Verificação | Validade |
| --- | --- | --- | --- | --- |
| P-48880 / E-48880 | 118690160 | P-14151 / E-14151 | Aprovado em 25/06/2026 | 24/06/2027 |
| P-48879 / E-48879 | 118690346 | P-14150 / E-14150 | Aprovado em 25/06/2026 | 24/06/2027 |

A fonte da verificação é Inmetro/PSIE. A GOINFRA publica validade 25/06/2027
para a série 118690160; seu valor continua no bloco original, sem substituir
24/06/2027 publicado pelo Inmetro. As posições oficiais da GOINFRA e os 40 km/h
permanecem preservados. O cadastro do Inmetro continua sem GPS publicado.

## Atualização e validação

O instalador executa pela API a migração aditiva `0002_juncao_metrologica`,
criando índices de série/tipo, instalações, vínculos e verificações. O `.sh`
privado já busca o código atual e aplica a migração; não precisa limpar o banco,
rebaixar fontes ou executar unificações manuais para apresentar essa metrologia.

Comando equivalente em uma instalação administrada, com o Python configurado:

```sh
python3 web/api.pse ferramenta inicializar_banco
```

Os testes de `tests/test_juncao_metrologica.py` cobrem o caso positivo, leitura
sem alteração, origens divergentes, séries diferentes/genéricas, contexto ausente,
modelo/fabricante conflitantes, decisões, remoção e origem não oficial. O plano
SQL deve usar o índice de série. O teste de navegador usa API CGI, dois coletores,
banco temporário e carregador metrológico reais, sem produção ou IA.

A [revisão da normalização e da escrita](NORMALIZACAO_RELACIONAL.md) acrescenta
reuso e reconciliação persistente de equipamentos comprovados. A junção descrita
aqui permanece para observações legadas ainda separadas e não comprova fusão
da identidade física.
