#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera sql/schema.sqlite.sql e sql/schema.postgres.sql a partir de uma unica
definicao canonica (T01..T77 da ESPECIFICACAO v1.1, secoes 4, 5 e 17.3).

Uso:
    python3 tools/build_schema.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SQLDIR = os.path.join(ROOT, "sql")

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
       "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
       "SP", "SE", "TO"]


class C(object):
    def __init__(self, name, typ, nn=False, pk=False, uq=False, fk=None,
                 ck=None, default=None):
        self.name = name
        self.typ = typ
        self.nn = nn
        self.pk = pk
        self.uq = uq
        self.fk = fk          # (tabela, coluna)
        self.ck = ck          # expr SQL portavel OU {'sqlite':..,'postgres':..}
        self.default = default

    def check_for(self, dialect):
        if self.ck is None:
            return None
        if isinstance(self.ck, dict):
            return self.ck[dialect]
        return self.ck


class T(object):
    def __init__(self, num, name, cols, pk=None, uniques=(), checks=()):
        self.num = num
        self.name = name
        self.cols = cols
        self.pk = pk                  # lista p/ PK composta (sem coluna id)
        self.uniques = list(uniques)  # listas de nomes de coluna
        self.checks = list(checks)    # exprs SQL portaveis


def col(name):
    return name


# ---------------------------------------------------------------------------
# Definicao das tabelas
# ---------------------------------------------------------------------------
TABLES = []


def add(t):
    TABLES.append(t)


# --- catalogo simples (id PK, codigo NN UQ, descricao NN) ---
def catalogo(num, name):
    return T(num, name, [
        C("id", "ID", nn=True, pk=True),
        C("codigo", "TEXT", nn=True, uq=True),
        C("descricao", "TEXT", nn=True),
    ])


add(T(1, "UF", [
    C("sigla", "CHAR2", nn=True, pk=True,
      ck="sigla IN (%s)" % ", ".join("'%s'" % u for u in UFS)),
    C("nome", "TEXT", nn=True, uq=True),
]))

add(T(2, "MUNICIPIO", [
    C("codigo_ibge", "CHAR7", nn=True, pk=True),
    C("uf_sigla", "CHAR2", nn=True, fk=("UF", "sigla")),
    C("nome", "TEXT", nn=True),
], uniques=[("uf_sigla", "nome")]))

add(catalogo(3, "TIPO_VIA"))

add(T(4, "VIA", [
    C("id", "ID", nn=True, pk=True),
    C("tipo_via_id", "ID", nn=True, fk=("TIPO_VIA", "id")),
    C("codigo", "TEXT", nn=True),
    C("nome", "TEXT"),
    C("observacao", "TEXT"),
], uniques=[("tipo_via_id", "codigo")]))

add(T(5, "VIA_UF", [
    C("via_id", "ID", nn=True, fk=("VIA", "id")),
    C("uf_sigla", "CHAR2", nn=True, fk=("UF", "sigla")),
], pk=["via_id", "uf_sigla"]))

add(T(6, "ORGANIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("nome", "TEXT", nn=True),
    C("tipo_organizacao_id", "ID", nn=True, fk=("TIPO_ORGANIZACAO", "id")),
    C("municipio_id", "CHAR7", fk=("MUNICIPIO", "codigo_ibge")),
    C("cnpj", "TEXT"),
    C("site_oficial", "TEXT"),
], uniques=[("cnpj",)]))

add(catalogo(7, "TIPO_ORGANIZACAO"))
add(catalogo(8, "PAPEL_ORGANIZACAO"))
add(catalogo(9, "TIPO_RADAR"))
add(catalogo(10, "FUNCAO_EQUIPAMENTO"))
add(catalogo(11, "TECNOLOGIA_MEDICAO"))
add(catalogo(12, "SITUACAO_OPERACIONAL"))
add(catalogo(13, "MODALIDADE_FISCALIZACAO"))
add(catalogo(14, "TIPO_MEDICAO"))
add(catalogo(15, "SENTIDO"))
add(catalogo(16, "CATEGORIA_VEICULO"))
add(catalogo(17, "SITUACAO_OPERACAO"))
add(catalogo(18, "RESULTADO_VERIFICACAO"))
add(catalogo(19, "TIPO_VERIFICACAO"))
add(catalogo(20, "TIPO_DOCUMENTO"))
add(catalogo(21, "TIPO_IDENTIFICADOR"))
add(catalogo(22, "QUALIDADE_POSICAO"))

add(T(23, "POSICAO_GEOGRAFICA", [
    C("id", "ID", nn=True, pk=True),
    C("latitude", "NUM10_7", nn=True),
    C("longitude", "NUM10_7", nn=True),
    C("precisao_metros", "NUM12_3"),
    C("qualidade_posicao_id", "ID", nn=True, fk=("QUALIDADE_POSICAO", "id")),
    C("metodo_obtencao", "TEXT"),
    C("registro_fonte_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=[
    "latitude >= -90 AND latitude <= 90",
    "longitude >= -180 AND longitude <= 180",
    "precisao_metros IS NULL OR precisao_metros >= 0",
]))

add(T(24, "ENDERECO", [
    C("id", "ID", nn=True, pk=True),
    C("logradouro", "TEXT"),
    C("numero", "TEXT"),
    C("bairro", "TEXT"),
    C("complemento", "TEXT"),
    C("cep", "CHAR8"),
    C("ponto_referencia", "TEXT"),
], checks=[{
    "sqlite": "cep IS NULL OR (length(cep) = 8 AND cep NOT GLOB '*[^0-9]*')",
    "postgres": "cep IS NULL OR cep ~ '^[0-9]{8}$'",
}]))

add(T(25, "PONTO_FISCALIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("posicao_id", "ID", fk=("POSICAO_GEOGRAFICA", "id")),
    C("endereco_id", "ID", fk=("ENDERECO", "id")),
    C("municipio_id", "CHAR7", fk=("MUNICIPIO", "codigo_ibge")),
    C("via_id", "ID", fk=("VIA", "id")),
    C("km", "NUM10_3"),
    C("tipo_pista", "TEXT"),
    C("situacao_operacional_id", "ID", fk=("SITUACAO_OPERACIONAL", "id")),
    C("inicio_operacao", "TS"),
    C("data_inativacao", "DATE"),
    C("observacoes", "TEXT"),
], checks=["km IS NULL OR km >= 0"]))

add(T(26, "PONTO_ORGANIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("organizacao_id", "ID", nn=True, fk=("ORGANIZACAO", "id")),
    C("papel_id", "ID", nn=True, fk=("PAPEL_ORGANIZACAO", "id")),
    C("inicio_em", "TS"),
    C("fim_em", "TS"),
], checks=["fim_em IS NULL OR inicio_em IS NULL OR fim_em >= inicio_em"]))

add(T(27, "FAIXA_FISCALIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("numero_faixa", "INT"),
    C("sentido_id", "ID", fk=("SENTIDO", "id")),
    C("sentido_original", "TEXT"),
    C("descricao", "TEXT"),
], checks=["numero_faixa IS NULL OR numero_faixa >= 1"]))

add(T(28, "LIMITE_VELOCIDADE", [
    C("id", "ID", nn=True, pk=True),
    C("ponto_id", "ID", fk=("PONTO_FISCALIZACAO", "id")),
    C("faixa_id", "ID", fk=("FAIXA_FISCALIZACAO", "id")),
    C("categoria_veiculo_id", "ID", nn=True, fk=("CATEGORIA_VEICULO", "id")),
    C("velocidade_kmh", "NUM6_2", nn=True),
    C("vigencia_inicio", "TS"),
    C("vigencia_fim", "TS"),
    C("registro_fonte_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=[
    "(ponto_id IS NULL) <> (faixa_id IS NULL)",
    "velocidade_kmh > 0 AND velocidade_kmh <= 350",
    "vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim >= vigencia_inicio",
]))

add(T(29, "REGIME_FISCALIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("modalidade_id", "ID", nn=True, fk=("MODALIDADE_FISCALIZACAO", "id")),
    C("tipo_medicao_id", "ID", fk=("TIPO_MEDICAO", "id")),
    C("situacao_operacional_id", "ID", fk=("SITUACAO_OPERACIONAL", "id")),
    C("inicio_em", "TS"),
    C("fim_em", "TS"),
    C("fonte_registro_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=["fim_em IS NULL OR inicio_em IS NULL OR fim_em >= inicio_em"]))

add(T(30, "TRECHO_ELEGIVEL", [
    C("id", "ID", nn=True, pk=True),
    C("via_id", "ID", nn=True, fk=("VIA", "id")),
    C("km_inicio", "NUM10_3"),
    C("km_fim", "NUM10_3"),
    C("sentido_id", "ID", fk=("SENTIDO", "id")),
    C("criterio_inclusao", "TEXT"),
    C("vigencia_inicio", "DATE"),
    C("vigencia_fim", "DATE"),
    C("situacao", "TEXT"),
    C("registro_fonte_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=[
    "km_inicio IS NULL OR km_inicio >= 0",
    "km_fim IS NULL OR km_fim >= 0",
    "km_inicio IS NULL OR km_fim IS NULL OR km_fim >= km_inicio",
    "vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim >= vigencia_inicio",
]))

add(T(31, "TRECHO_MUNICIPIO", [
    C("trecho_id", "ID", nn=True, fk=("TRECHO_ELEGIVEL", "id")),
    C("municipio_id", "CHAR7", nn=True, fk=("MUNICIPIO", "codigo_ibge")),
], pk=["trecho_id", "municipio_id"]))

add(T(32, "TRECHO_VERTICE", [
    C("trecho_id", "ID", nn=True, fk=("TRECHO_ELEGIVEL", "id")),
    C("ordem", "INT", nn=True),
    C("posicao_id", "ID", nn=True, fk=("POSICAO_GEOGRAFICA", "id")),
], pk=["trecho_id", "ordem"], checks=["ordem >= 0"]))

add(T(33, "MODELO_EQUIPAMENTO", [
    C("id", "ID", nn=True, pk=True),
    C("fabricante_id", "ID", fk=("ORGANIZACAO", "id")),
    C("nome_modelo", "TEXT", nn=True),
    C("tecnologia_id", "ID", fk=("TECNOLOGIA_MEDICAO", "id")),
    C("registro_aprovacao_inmetro", "TEXT"),
    C("portaria_aprovacao_modelo", "TEXT"),
], uniques=[("fabricante_id", "nome_modelo")]))

add(T(34, "EQUIPAMENTO", [
    C("id", "ID", nn=True, pk=True),
    C("modelo_id", "ID", fk=("MODELO_EQUIPAMENTO", "id")),
    C("tipo_radar_id", "ID", nn=True, fk=("TIPO_RADAR", "id")),
    C("numero_serie", "TEXT"),
    C("ano_fabricacao", "INT"),
    C("observacoes", "TEXT"),
], checks=["ano_fabricacao IS NULL OR (ano_fabricacao >= 1900 AND ano_fabricacao <= 2100)"]))

add(T(35, "INSTALACAO", [
    C("id", "ID", nn=True, pk=True),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
    C("funcao_equipamento_id", "ID", fk=("FUNCAO_EQUIPAMENTO", "id")),
    C("situacao_operacional_id", "ID", fk=("SITUACAO_OPERACIONAL", "id")),
    C("inicio_em", "TS"),
    C("fim_em", "TS"),
    C("data_inicio_autuacao", "DATE"),
    C("data_inicio_educativo", "DATE"),
    C("observacoes", "TEXT"),
], checks=["fim_em IS NULL OR inicio_em IS NULL OR fim_em >= inicio_em"]))

add(T(36, "INSTALACAO_FAIXA", [
    C("instalacao_id", "ID", nn=True, fk=("INSTALACAO", "id")),
    C("faixa_id", "ID", nn=True, fk=("FAIXA_FISCALIZACAO", "id")),
], pk=["instalacao_id", "faixa_id"]))

add(T(37, "OPERACAO_FISCALIZACAO", [
    C("id", "ID", nn=True, pk=True),
    C("modalidade_id", "ID", nn=True, fk=("MODALIDADE_FISCALIZACAO", "id")),
    C("situacao_operacao_id", "ID", nn=True, fk=("SITUACAO_OPERACAO", "id")),
    C("organizacao_id", "ID", fk=("ORGANIZACAO", "id")),
    C("ponto_id", "ID", fk=("PONTO_FISCALIZACAO", "id")),
    C("trecho_id", "ID", fk=("TRECHO_ELEGIVEL", "id")),
    C("posicao_id", "ID", fk=("POSICAO_GEOGRAFICA", "id")),
    C("via_id", "ID", fk=("VIA", "id")),
    C("municipio_id", "CHAR7", fk=("MUNICIPIO", "codigo_ibge")),
    C("km", "NUM10_3"),
    C("descricao", "TEXT"),
    C("inicio_em", "TS"),
    C("fim_em", "TS"),
    C("fuso_original", "TEXT"),
    C("publicado_em", "TS"),
    C("registro_fonte_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=[
    "fim_em IS NULL OR inicio_em IS NULL OR fim_em >= inicio_em",
    "km IS NULL OR km >= 0",
]))

add(T(38, "OPERACAO_EQUIPAMENTO", [
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
], pk=["operacao_id", "equipamento_id"]))

add(T(39, "OPERACAO_FAIXA", [
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
    C("faixa_id", "ID", nn=True, fk=("FAIXA_FISCALIZACAO", "id")),
], pk=["operacao_id", "faixa_id"]))

add(T(40, "OPERACAO_RECORRENCIA", [
    C("id", "ID", nn=True, pk=True),
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
    C("regra_repeticao", "TEXT", nn=True),
    C("fuso_horario", "TEXT"),
    C("data_inicio", "DATE"),
    C("data_fim", "DATE"),
], checks=["data_fim IS NULL OR data_inicio IS NULL OR data_fim >= data_inicio"]))

add(T(41, "RECORRENCIA_DIA", [
    C("recorrencia_id", "ID", nn=True, fk=("OPERACAO_RECORRENCIA", "id")),
    C("dia_semana", "INT", nn=True),
    C("hora_inicio", "TIME", nn=True),
    C("hora_fim", "TIME"),
], pk=["recorrencia_id", "dia_semana", "hora_inicio"],
    checks=["dia_semana >= 1 AND dia_semana <= 7"]))

add(T(42, "IDENTIFICADOR_EXTERNO", [
    C("id", "ID", nn=True, pk=True),
    C("fonte_id", "ID", nn=True, fk=("FONTE", "id")),
    C("tipo_identificador_id", "ID", nn=True, fk=("TIPO_IDENTIFICADOR", "id")),
    C("valor", "TEXT", nn=True),
    C("valor_normalizado", "TEXT", nn=True),
], uniques=[("fonte_id", "tipo_identificador_id", "valor_normalizado")]))

add(T(43, "IDENTIFICADOR_PONTO", [
    C("id", "ID", nn=True, pk=True),
    C("identificador_id", "ID", nn=True, fk=("IDENTIFICADOR_EXTERNO", "id")),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("vigencia_inicio", "TS"),
    C("vigencia_fim", "TS"),
], uniques=[("identificador_id", "ponto_id", "vigencia_inicio")]))

add(T(44, "IDENTIFICADOR_EQUIPAMENTO", [
    C("id", "ID", nn=True, pk=True),
    C("identificador_id", "ID", nn=True, fk=("IDENTIFICADOR_EXTERNO", "id")),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
    C("vigencia_inicio", "TS"),
    C("vigencia_fim", "TS"),
]))

add(T(45, "IDENTIFICADOR_OPERACAO", [
    C("id", "ID", nn=True, pk=True),
    C("identificador_id", "ID", nn=True, fk=("IDENTIFICADOR_EXTERNO", "id")),
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
    C("vigencia_inicio", "TS"),
    C("vigencia_fim", "TS"),
]))

add(T(46, "VERIFICACAO_METROLOGICA", [
    C("id", "ID", nn=True, pk=True),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
    C("tipo_verificacao_id", "ID", nn=True, fk=("TIPO_VERIFICACAO", "id")),
    C("resultado_id", "ID", nn=True, fk=("RESULTADO_VERIFICACAO", "id")),
    C("orgao_executor_id", "ID", fk=("ORGANIZACAO", "id")),
    C("data_verificacao", "DATE"),
    C("validade_ate", "DATE"),
    C("numero_certificado", "TEXT"),
    C("norma_aplicada", "TEXT"),
    C("observacoes", "TEXT"),
    C("registro_fonte_id", "ID", fk=("REGISTRO_FONTE", "id")),
], checks=["validade_ate IS NULL OR data_verificacao IS NULL OR validade_ate >= data_verificacao"]))

add(T(47, "DOCUMENTO", [
    C("id", "ID", nn=True, pk=True),
    C("tipo_documento_id", "ID", nn=True, fk=("TIPO_DOCUMENTO", "id")),
    C("codigo_documento", "TEXT"),
    C("titulo", "TEXT"),
    C("url", "TEXT"),
    C("orgao_emissor_id", "ID", fk=("ORGANIZACAO", "id")),
    C("data_emissao", "DATE"),
    C("validade_ate", "DATE"),
    C("hash_conteudo", "TEXT"),
    C("descricao", "TEXT"),
], checks=["validade_ate IS NULL OR data_emissao IS NULL OR validade_ate >= data_emissao"]))

add(T(48, "DOCUMENTO_PONTO", [
    C("documento_id", "ID", nn=True, fk=("DOCUMENTO", "id")),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
], pk=["documento_id", "ponto_id"]))

add(T(49, "DOCUMENTO_EQUIPAMENTO", [
    C("documento_id", "ID", nn=True, fk=("DOCUMENTO", "id")),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
], pk=["documento_id", "equipamento_id"]))

add(T(50, "DOCUMENTO_VERIFICACAO", [
    C("documento_id", "ID", nn=True, fk=("DOCUMENTO", "id")),
    C("verificacao_id", "ID", nn=True, fk=("VERIFICACAO_METROLOGICA", "id")),
], pk=["documento_id", "verificacao_id"]))

add(T(51, "DOCUMENTO_OPERACAO", [
    C("documento_id", "ID", nn=True, fk=("DOCUMENTO", "id")),
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
], pk=["documento_id", "operacao_id"]))

add(T(52, "DOCUMENTO_TRECHO", [
    C("documento_id", "ID", nn=True, fk=("DOCUMENTO", "id")),
    C("trecho_id", "ID", nn=True, fk=("TRECHO_ELEGIVEL", "id")),
], pk=["documento_id", "trecho_id"]))

add(T(53, "OBSERVACAO_TRAFEGO", [
    C("id", "ID", nn=True, pk=True),
    C("registro_fonte_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("equipamento_id", "ID", fk=("EQUIPAMENTO", "id")),
    C("ponto_id", "ID", fk=("PONTO_FISCALIZACAO", "id")),
    C("faixa_id", "ID", fk=("FAIXA_FISCALIZACAO", "id")),
    C("categoria_veiculo_id", "ID", fk=("CATEGORIA_VEICULO", "id")),
    C("sentido_id", "ID", fk=("SENTIDO", "id")),
    C("instante_observacao", "TS"),
    C("data_observacao", "DATE"),
    C("velocidade_publicada", "TEXT"),
    C("velocidade_kmh", "NUM6_2"),
    C("volume_total", "INT"),
], checks=[
    "volume_total IS NULL OR volume_total >= 0",
    "velocidade_kmh IS NULL OR velocidade_kmh >= 0",
]))

add(T(54, "FONTE", [
    C("id", "ID", nn=True, pk=True),
    C("organizacao_id", "ID", nn=True, fk=("ORGANIZACAO", "id")),
    C("natureza_id", "ID", nn=True, fk=("NATUREZA_FONTE", "id")),
    C("nome", "TEXT", nn=True),
    C("url_institucional", "TEXT", nn=True),
    C("esfera", "TEXT", nn=True),
    C("licenca", "TEXT"),
    C("documentacao_url", "TEXT"),
    C("situacao", "TEXT", nn=True),
    C("periodicidade_declarada", "TEXT"),
    C("observacoes", "TEXT"),
], checks=[
    "esfera IN ('federal','estadual','municipal','distrital','outra','desconhecida')",
]))

add(T(55, "COBERTURA_FONTE", [
    C("id", "ID", nn=True, pk=True),
    C("fonte_id", "ID", nn=True, fk=("FONTE", "id")),
    C("tipo_abrangencia", "TEXT", nn=True),
    C("uf_sigla", "CHAR2", fk=("UF", "sigla")),
    C("municipio_id", "CHAR7", fk=("MUNICIPIO", "codigo_ibge")),
    C("via_id", "ID", fk=("VIA", "id")),
    C("vigencia_inicio", "DATE"),
    C("vigencia_fim", "DATE"),
    C("confirmada", "BOOL", nn=True),
], checks=[
    "tipo_abrangencia IN ('nacional','estadual','municipal','rodoviaria','desconhecida')",
    "vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim >= vigencia_inicio",
    "(tipo_abrangencia <> 'municipal' OR municipio_id IS NOT NULL)",
    "(tipo_abrangencia <> 'estadual' OR uf_sigla IS NOT NULL)",
    "(tipo_abrangencia <> 'rodoviaria' OR via_id IS NOT NULL)",
]))

add(T(56, "RECURSO_FONTE", [
    C("id", "ID", nn=True, pk=True),
    C("fonte_id", "ID", nn=True, fk=("FONTE", "id")),
    C("nome", "TEXT", nn=True),
    C("url_recurso", "TEXT", nn=True),
    C("formato_origem", "TEXT", nn=True),
    C("dicionario_url", "TEXT"),
    C("periodicidade_segundos", "INT"),
    C("ativo", "BOOL", nn=True),
    C("tamanho_maximo_bytes", "BIGINT"),
    C("status_integracao", "TEXT", nn=True),
], checks=[
    "periodicidade_segundos IS NULL OR periodicidade_segundos > 0",
    "tamanho_maximo_bytes IS NULL OR tamanho_maximo_bytes > 0",
]))

add(T(57, "ARTEFATO_COLETA", [
    C("id", "ID", nn=True, pk=True),
    C("recurso_id", "ID", nn=True, fk=("RECURSO_FONTE", "id")),
    C("hash_sha256", "CHAR64", nn=True),
    C("caminho_cache", "TEXT", nn=True),
    C("bytes_arquivo", "BIGINT", nn=True),
    C("tipo_mime", "TEXT"),
    C("etag", "TEXT"),
    C("last_modified_http", "TEXT"),
    C("data_publicacao_origem", "TS"),
    C("baixado_em", "TS", nn=True),
    C("validado_em", "TS"),
    C("resultado_validacao", "TEXT", nn=True),
], uniques=[("recurso_id", "hash_sha256")], checks=["bytes_arquivo >= 0"]))

add(T(58, "EXECUCAO_COLETA", [
    C("id", "ID", nn=True, pk=True),
    C("recurso_id", "ID", nn=True, fk=("RECURSO_FONTE", "id")),
    C("artefato_id", "ID", fk=("ARTEFATO_COLETA", "id")),
    C("iniciada_em", "TS", nn=True),
    C("terminada_em", "TS"),
    C("status", "TEXT", nn=True),
    C("http_status", "INT"),
    C("tentativas", "INT", nn=True),
    C("linhas_recebidas", "INT"),
    C("linhas_validas", "INT"),
    C("linhas_rejeitadas", "INT"),
    C("registros_criados", "INT"),
    C("registros_alterados", "INT"),
    C("erro_codigo", "TEXT"),
    C("erro_detalhe", "TEXT"),
], checks=[
    "terminada_em IS NULL OR terminada_em >= iniciada_em",
    "tentativas >= 0",
    "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
    "linhas_recebidas IS NULL OR linhas_recebidas >= 0",
    "linhas_validas IS NULL OR linhas_validas >= 0",
    "linhas_rejeitadas IS NULL OR linhas_rejeitadas >= 0",
    "registros_criados IS NULL OR registros_criados >= 0",
    "registros_alterados IS NULL OR registros_alterados >= 0",
]))

add(T(59, "REGISTRO_FONTE", [
    C("id", "ID", nn=True, pk=True),
    C("artefato_id", "ID", nn=True, fk=("ARTEFATO_COLETA", "id")),
    C("numero_ordem", "INT", nn=True),
    C("identificador_na_fonte", "TEXT"),
    C("payload_original", "TEXT", nn=True),
    C("hash_registro", "CHAR64", nn=True),
    C("status_validacao", "TEXT", nn=True),
], uniques=[("artefato_id", "numero_ordem")], checks=["numero_ordem >= 0"]))

add(T(60, "ERRO_VALIDACAO", [
    C("id", "ID", nn=True, pk=True),
    C("execucao_id", "ID", fk=("EXECUCAO_COLETA", "id")),
    C("registro_id", "ID", fk=("REGISTRO_FONTE", "id")),
    C("campo_origem", "TEXT"),
    C("codigo_erro", "TEXT", nn=True),
    C("descricao", "TEXT", nn=True),
    C("severidade", "TEXT", nn=True),
    C("registrado_em", "TS", nn=True),
], checks=["execucao_id IS NOT NULL OR registro_id IS NOT NULL"]))

add(T(61, "SNAPSHOT_PUBLICADO", [
    C("id", "ID", nn=True, pk=True),
    C("anterior_id", "ID", fk=("SNAPSHOT_PUBLICADO", "id")),
    C("publicado_em", "TS", nn=True),
    C("status", "TEXT", nn=True),
    C("resumo_validacao", "TEXT"),
    C("identificador_versao", "TEXT", nn=True, uq=True),
]))

add(T(62, "SNAPSHOT_RECURSO", [
    C("snapshot_id", "ID", nn=True, fk=("SNAPSHOT_PUBLICADO", "id")),
    C("recurso_id", "ID", nn=True, fk=("RECURSO_FONTE", "id")),
    C("artefato_id", "ID", nn=True, fk=("ARTEFATO_COLETA", "id")),
], pk=["snapshot_id", "recurso_id"]))

add(T(63, "VINCULO_REGISTRO_PONTO", [
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("ponto_id", "ID", nn=True, fk=("PONTO_FISCALIZACAO", "id")),
    C("confianca", "NUM5_4"),
    C("decisao_id", "ID", fk=("DECISAO_DUPLICIDADE", "id")),
], pk=["registro_id", "ponto_id"],
    checks=["confianca IS NULL OR (confianca >= 0 AND confianca <= 1)"]))

add(T(64, "VINCULO_REGISTRO_EQUIPAMENTO", [
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("equipamento_id", "ID", nn=True, fk=("EQUIPAMENTO", "id")),
    C("confianca", "NUM5_4"),
    C("decisao_id", "ID", fk=("DECISAO_DUPLICIDADE", "id")),
], pk=["registro_id", "equipamento_id"],
    checks=["confianca IS NULL OR (confianca >= 0 AND confianca <= 1)"]))

add(T(65, "VINCULO_REGISTRO_OPERACAO", [
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("operacao_id", "ID", nn=True, fk=("OPERACAO_FISCALIZACAO", "id")),
    C("confianca", "NUM5_4"),
    C("decisao_id", "ID", fk=("DECISAO_DUPLICIDADE", "id")),
], pk=["registro_id", "operacao_id"],
    checks=["confianca IS NULL OR (confianca >= 0 AND confianca <= 1)"]))

add(T(66, "VINCULO_REGISTRO_TRECHO", [
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("trecho_id", "ID", nn=True, fk=("TRECHO_ELEGIVEL", "id")),
    C("confianca", "NUM5_4"),
    C("decisao_id", "ID", fk=("DECISAO_DUPLICIDADE", "id")),
], pk=["registro_id", "trecho_id"],
    checks=["confianca IS NULL OR (confianca >= 0 AND confianca <= 1)"]))

add(T(67, "VINCULO_REGISTRO_VERIFICACAO", [
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("verificacao_id", "ID", nn=True, fk=("VERIFICACAO_METROLOGICA", "id")),
], pk=["registro_id", "verificacao_id"]))

add(T(68, "REGRA_DEDUPLICACAO", [
    C("id", "ID", nn=True, pk=True),
    C("versao", "TEXT", nn=True, uq=True),
    C("descricao", "TEXT", nn=True),
    C("configuracao_serializada", "TEXT", nn=True),
    C("inicio_validade", "TS", nn=True),
]))

add(T(69, "CANDIDATO_DUPLICIDADE", [
    C("id", "ID", nn=True, pk=True),
    C("registro_a_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("registro_b_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("regra_id", "ID", nn=True, fk=("REGRA_DEDUPLICACAO", "id")),
    C("score", "NUM5_4"),
    C("estado", "TEXT", nn=True),
    C("evidencias_resumo", "TEXT"),
    C("gerado_em", "TS", nn=True),
], uniques=[("registro_a_id", "registro_b_id", "regra_id")],
    checks=["registro_a_id < registro_b_id",
            "score IS NULL OR (score >= 0 AND score <= 1)"]))

add(T(70, "DECISAO_DUPLICIDADE", [
    C("id", "ID", nn=True, pk=True),
    C("candidato_id", "ID", nn=True, fk=("CANDIDATO_DUPLICIDADE", "id")),
    C("decisao", "TEXT", nn=True),
    C("fundamentacao", "TEXT", nn=True),
    C("ator", "TEXT", nn=True),
    C("decidida_em", "TS", nn=True),
    C("revertida_em", "TS"),
    C("observacoes", "TEXT"),
], checks=["decisao IN ('unificar','manter_separados','revisar')"]))

add(T(71, "CATALOGO_CAMPO", [
    C("id", "ID", nn=True, pk=True),
    C("entidade_logica", "TEXT", nn=True),
    C("nome_campo", "TEXT", nn=True),
    C("tipo_dado", "TEXT", nn=True),
    C("descricao", "TEXT", nn=True),
], uniques=[("entidade_logica", "nome_campo")]))

add(T(72, "VALOR_OBSERVADO", [
    C("id", "ID", nn=True, pk=True),
    C("registro_id", "ID", nn=True, fk=("REGISTRO_FONTE", "id")),
    C("campo_id", "ID", nn=True, fk=("CATALOGO_CAMPO", "id")),
    C("valor_original", "TEXT"),
    C("valor_normalizado", "TEXT"),
    C("linha_origem", "TEXT"),
    C("pontuacao_qualidade", "NUM5_4"),
], checks=["pontuacao_qualidade IS NULL OR (pontuacao_qualidade >= 0 AND pontuacao_qualidade <= 1)"]))

add(T(73, "DECISAO_VALOR_CANONICO", [
    C("id", "ID", nn=True, pk=True),
    C("valor_observado_id", "ID", nn=True, fk=("VALOR_OBSERVADO", "id")),
    C("ponto_id", "ID", fk=("PONTO_FISCALIZACAO", "id")),
    C("equipamento_id", "ID", fk=("EQUIPAMENTO", "id")),
    C("instalacao_id", "ID", fk=("INSTALACAO", "id")),
    C("operacao_id", "ID", fk=("OPERACAO_FISCALIZACAO", "id")),
    C("trecho_id", "ID", fk=("TRECHO_ELEGIVEL", "id")),
    C("verificacao_id", "ID", fk=("VERIFICACAO_METROLOGICA", "id")),
    C("status_decisao", "TEXT", nn=True),
    C("justificativa", "TEXT"),
    C("decidida_em", "TS", nn=True),
], checks=[
    "((CASE WHEN ponto_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN equipamento_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN instalacao_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN operacao_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN trecho_id IS NULL THEN 0 ELSE 1 END)"
    " + (CASE WHEN verificacao_id IS NULL THEN 0 ELSE 1 END)) = 1",
]))

add(T(74, "ALERTA_OPERACIONAL", [
    C("id", "ID", nn=True, pk=True),
    C("recurso_id", "ID", fk=("RECURSO_FONTE", "id")),
    C("execucao_id", "ID", fk=("EXECUCAO_COLETA", "id")),
    C("snapshot_id", "ID", fk=("SNAPSHOT_PUBLICADO", "id")),
    C("chave_incidente", "TEXT", nn=True),
    C("nivel", "TEXT", nn=True),
    C("status", "TEXT", nn=True),
    C("mensagem", "TEXT", nn=True),
    C("primeira_ocorrencia", "TS", nn=True),
    C("ultima_ocorrencia", "TS", nn=True),
    C("resolvido_em", "TS"),
    C("ocorrencias", "INT", nn=True),
], checks=["ocorrencias >= 1", "ultima_ocorrencia >= primeira_ocorrencia"]))

add(T(75, "NATUREZA_FONTE", [
    C("id", "ID", nn=True, pk=True),
    C("codigo", "TEXT", nn=True, uq=True),
    C("nome", "TEXT", nn=True),
    C("descricao", "TEXT"),
], checks=["codigo IN ('oficial','comunitaria','academica','privada','outra','desconhecida')"]))

add(T(76, "LICENCA_DADOS", [
    C("id", "ID", nn=True, pk=True),
    C("codigo", "TEXT", nn=True, uq=True),
    C("nome", "TEXT", nn=True),
    C("url_licenca", "TEXT"),
    C("versao", "TEXT"),
    C("requisitos_atribuicao", "TEXT"),
    C("observacoes", "TEXT"),
]))

add(T(77, "RECURSO_LICENCA", [
    C("id", "ID", nn=True, pk=True),
    C("recurso_id", "ID", nn=True, fk=("RECURSO_FONTE", "id")),
    C("licenca_id", "ID", nn=True, fk=("LICENCA_DADOS", "id")),
    C("vigencia_inicio", "DATE"),
    C("vigencia_fim", "DATE"),
    C("observacoes", "TEXT"),
], uniques=[("recurso_id", "licenca_id", "vigencia_inicio")],
    checks=["vigencia_fim IS NULL OR vigencia_inicio IS NULL OR vigencia_fim >= vigencia_inicio"]))


# ---------------------------------------------------------------------------
# Ordenacao topologica (FK < tabela)
# ---------------------------------------------------------------------------
def topo_order(tables):
    by_name = {t.name: t for t in tables}
    result = []
    temp = set()
    done = set()

    def visit(name):
        if name in done:
            return
        if name in temp:
            # ciclo: mantem a ordem de declaracao (self-ref eh tratada inline)
            return
        temp.add(name)
        t = by_name[name]
        deps = []
        for c in t.cols:
            if c.fk and c.fk[0] != name:
                deps.append(c.fk[0])
        for d in sorted(set(deps)):
            if d in by_name:
                visit(d)
        temp.discard(name)
        done.add(name)
        result.append(t)

    for t in tables:
        visit(t.name)
    return result


# ---------------------------------------------------------------------------
# Emissao
# ---------------------------------------------------------------------------
SQLITE_TYPES = {
    "ID": "INTEGER", "TEXT": "TEXT", "CHAR2": "CHAR(2)", "CHAR7": "CHAR(7)",
    "CHAR8": "CHAR(8)", "CHAR64": "CHAR(64)", "DATE": "DATE", "TS": "TEXT",
    "TIME": "TEXT", "INT": "INTEGER", "BIGINT": "INTEGER", "BOOL": "INTEGER",
    "NUM10_7": "DECIMAL(10,7)", "NUM10_3": "DECIMAL(10,3)",
    "NUM12_3": "DECIMAL(12,3)", "NUM6_2": "DECIMAL(6,2)",
    "NUM5_4": "DECIMAL(5,4)",
}
PG_TYPES = {
    "ID": "BIGINT", "TEXT": "TEXT", "CHAR2": "CHAR(2)", "CHAR7": "CHAR(7)",
    "CHAR8": "CHAR(8)", "CHAR64": "CHAR(64)", "DATE": "DATE",
    "TS": "TIMESTAMPTZ", "TIME": "TIME", "INT": "INTEGER", "BIGINT": "BIGINT",
    "BOOL": "BOOLEAN",
    "NUM10_7": "DECIMAL(10,7)", "NUM10_3": "DECIMAL(10,3)",
    "NUM12_3": "DECIMAL(12,3)", "NUM6_2": "DECIMAL(6,2)",
    "NUM5_4": "DECIMAL(5,4)",
}


def _is_surrogate(c):
    # PK surrogada autogerada: coluna chamada 'id' de tipo logico ID.
    return c.pk and c.name == "id" and c.typ == "ID"


def col_sql(c, dialect, tname, is_composite_pk_col):
    if dialect == "sqlite":
        if _is_surrogate(c):
            return "%s INTEGER PRIMARY KEY AUTOINCREMENT" % c.name
        parts = ["%s %s" % (c.name, SQLITE_TYPES[c.typ])]
        if c.pk:
            parts.append("PRIMARY KEY")
    else:
        if _is_surrogate(c):
            return "%s BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" % c.name
        parts = ["%s %s" % (c.name, PG_TYPES[c.typ])]
        if c.pk:
            parts.append("PRIMARY KEY")
    if c.nn:
        parts.append("NOT NULL")
    if c.uq and not c.pk:
        parts.append("UNIQUE")
    if c.fk:
        parts.append("REFERENCES %s(%s) ON DELETE RESTRICT" % (c.fk[0], c.fk[1]))
    if c.ck:
        parts.append("CHECK (%s)" % c.check_for(dialect))
    if dialect == "sqlite" and c.typ == "BOOL":
        # SQLite nao possui boolean nativo: 0/1 com CHECK
        parts.append("CHECK (%s IN (0,1))" % c.name)
    return " ".join(parts)


def emit(dialect):
    defs = []
    for t in topo_order(TABLES):
        is_comp = bool(t.pk)
        lines = ["-- T%02d %s" % (t.num, t.name)]
        lines.append("CREATE TABLE %s (" % t.name)
        body = []
        for c in t.cols:
            body.append("    " + col_sql(c, dialect, t.name,
                                         c.pk and is_comp))
        if is_comp:
            body.append("    PRIMARY KEY (%s)" % ", ".join(t.pk))
        for uq in t.uniques:
            body.append("    UNIQUE (%s)" % ", ".join(uq))
        for ck in t.checks:
            expr = ck[dialect] if isinstance(ck, dict) else ck
            body.append("    CHECK (%s)" % expr)
        lines.append(",\n".join(body))
        lines.append(");")
        defs.append("\n".join(lines))

    header = [
        "-- Radar Brasil - esquema canonico v1 (T01..T77) - dialeto %s" % dialect,
        "-- Gerado por tools/build_schema.py a partir da ESPECIFICACAO v1.1.",
        "-- PK/FK/UQ/CHECK/NOT NULL. Sem PostGIS/recursos proprietarios.",
        "-- ON DELETE RESTRICT por padrao (dados historicos nao sofrem cascata).",
        "",
    ]
    return "\n".join(header) + "\n\n".join(defs) + "\n"


def main():
    os.makedirs(SQLDIR, exist_ok=True)
    sqlite_sql = emit("sqlite")
    pg_sql = emit("postgres")
    with open(os.path.join(SQLDIR, "schema.sqlite.sql"), "w", encoding="utf-8") as f:
        f.write(sqlite_sql)
    with open(os.path.join(SQLDIR, "schema.postgres.sql"), "w", encoding="utf-8") as f:
        f.write(pg_sql)
    # auto-verificacao: garante que o SQLite carrega
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.executescript(sqlite_sql)
    n = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    con.close()
    if n != len(TABLES):
        print("ERRO: %d tabelas criadas, esperado %d" % (n, len(TABLES)))
        sys.exit(1)
    print("OK: %d tabelas em ambos os dialetos." % n)


if __name__ == "__main__":
    main()
