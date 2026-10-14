# -*- coding: utf-8 -*-
"""Dominios canonicos (T03, T07..T22, T75, T76) e UFs (T01).

Catalogos sao cadastros relacionais com FK real (spec 5, nota de
normalizacao), nao ENUM fechado no codigo.
"""

# (codigo, descricao)
DOMINIOS = {
    "TIPO_VIA": [
        ("federal", "Via federal"),
        ("estadual", "Via estadual"),
        ("municipal", "Via municipal"),
        ("urbana", "Via urbana"),
        ("outra", "Outro tipo de via"),
        ("desconhecida", "Tipo de via desconhecido"),
    ],
    "TIPO_ORGANIZACAO": [
        ("orgao_publico", "Orgao publico"),
        ("concessionaria", "Concessionaria"),
        ("fabricante", "Fabricante"),
        ("laboratorio", "Laboratorio"),
        ("operador_privado", "Operador privado"),
        ("mantenedora", "Mantenedora"),
        ("outro", "Outro"),
        ("desconhecido", "Desconhecido"),
    ],
    "PAPEL_ORGANIZACAO": [
        ("fiscalizador", "Fiscalizador"),
        ("titular_via", "Titular da via"),
        ("concessionaria", "Concessionaria"),
        ("operador", "Operador"),
        ("mantenedor", "Mantenedor"),
        ("fabricante", "Fabricante"),
        ("verificador", "Verificador metrologico"),
        ("emissor_documento", "Emissor de documento"),
    ],
    "TIPO_RADAR": [
        ("fixo", "Radar fixo"),
        ("portatil", "Radar portatil"),
        ("movel", "Radar movel"),
        ("desconhecido", "Tipo desconhecido"),
    ],
    "FUNCAO_EQUIPAMENTO": [
        ("controlador", "Controlador"),
        ("redutor", "Redutor"),
        ("misto", "Misto"),
        ("outro", "Outra funcao"),
        ("desconhecido", "Funcao desconhecida"),
    ],
    "TECNOLOGIA_MEDICAO": [
        ("doppler", "Radar Doppler"),
        ("laser", "Laser"),
        ("laco_indutivo", "Laco indutivo"),
        ("otico", "Otico"),
        ("outra", "Outra tecnologia"),
        ("desconhecida", "Tecnologia desconhecida"),
    ],
    "SITUACAO_OPERACIONAL": [
        ("ativo", "Ativo"),
        ("inativo", "Inativo"),
        ("manutencao", "Em manutencao"),
        ("em_instalacao", "Em instalacao"),
        ("suspenso", "Suspenso"),
        ("desconhecido", "Situacao desconhecida"),
    ],
    "MODALIDADE_FISCALIZACAO": [
        ("permanente", "Permanente"),
        ("pontual", "Pontual"),
        ("itinerante", "Itinerante"),
        ("por_trecho", "Por trecho"),
        ("desconhecida", "Modalidade desconhecida"),
    ],
    "TIPO_MEDICAO": [
        ("velocidade_instantanea", "Velocidade instantanea"),
        ("velocidade_media_trecho", "Velocidade media de trecho"),
        ("outra", "Outra medicao"),
        ("desconhecida", "Medicao desconhecida"),
    ],
    "SENTIDO": [
        ("crescente", "Crescente"),
        ("decrescente", "Decrescente"),
        ("ambos", "Ambos os sentidos"),
        ("sentido_geografico", "Sentido geografico"),
        ("desconhecido", "Sentido desconhecido"),
    ],
    "CATEGORIA_VEICULO": [
        ("leves", "Veiculos leves"),
        ("pesados", "Veiculos pesados"),
        ("geral", "Geral"),
        ("categoria_original", "Categoria conforme publicacao original"),
        ("desconhecida", "Categoria desconhecida"),
    ],
    "SITUACAO_OPERACAO": [
        ("planejada", "Planejada"),
        ("confirmada", "Confirmada"),
        ("encerrada", "Encerrada"),
        ("cancelada", "Cancelada"),
        ("desconhecida", "Situacao desconhecida"),
    ],
    "RESULTADO_VERIFICACAO": [
        ("conforme", "Conforme"),
        ("nao_conforme", "Nao conforme"),
        ("outro", "Outro"),
        ("desconhecido", "Desconhecido"),
    ],
    "TIPO_VERIFICACAO": [
        ("inicial", "Inicial"),
        ("periodica", "Periodica"),
        ("apos_reparo", "Apos reparo"),
        ("outra", "Outra"),
        ("desconhecida", "Desconhecida"),
    ],
    "TIPO_DOCUMENTO": [
        ("estudo_tecnico", "Estudo tecnico"),
        ("certificado", "Certificado"),
        ("portaria", "Portaria"),
        ("relatorio", "Relatorio"),
        ("edital", "Edital"),
        ("outro", "Outro"),
    ],
    "TIPO_IDENTIFICADOR": [
        ("id_orgao", "Identificador do orgao"),
        ("codigo_equipamento", "Codigo de equipamento"),
        ("serie", "Numero de serie"),
        ("codigo_et", "Codigo ET"),
        ("cadastro_local", "Cadastro local"),
        ("outro", "Outro"),
    ],
    "QUALIDADE_POSICAO": [
        ("oficial", "Oficial"),
        ("oficial_imprecisa", "Oficial imprecisa"),
        ("inferida", "Inferida"),
        ("estimada", "Estimada"),
        ("conflitante", "Conflitante"),
        ("desconhecida", "Desconhecida"),
    ],
    "NATUREZA_FONTE": [
        ("oficial", "Fonte oficial"),
        ("comunitaria", "Fonte comunitaria"),
        ("academica", "Fonte academica"),
        ("privada", "Fonte privada"),
        ("outra", "Outra natureza"),
        ("desconhecida", "Natureza desconhecida"),
    ],
    "LICENCA_DADOS": [
        ("odbl", "Open Database License (ODbL) 1.0"),
        ("cc_by_4_0", "Creative Commons BY 4.0"),
        ("dominio_publico", "Dominio publico"),
        ("desconhecida", "Licenca desconhecida"),
    ],
}

UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapa"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceara"), ("DF", "Distrito Federal"),
    ("ES", "Espirito Santo"), ("GO", "Goias"), ("MA", "Maranhao"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Para"), ("PB", "Paraiba"), ("PR", "Parana"), ("PE", "Pernambuco"),
    ("PI", "Piaui"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondonia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "Sao Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]
