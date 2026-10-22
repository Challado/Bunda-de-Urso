"""SIE/PMRv: inventario portatil e locais elegiveis sao fontes distintas.

PDFs publicados pelo portal SIE em seu componente de radares portateis.
Nao existe vinculo publicado entre cada serie e cada local; nao o inventamos.
Codigo municipal de quatro digitos da lista NAO e codigo IBGE.
"""
import re
from datetime import datetime

from coletor.fontes import normalizacao as nz
from coletor.fontes.cadastros_publicos import CadastroPublicado, cadastro

BASE = "https://www.sie.sc.gov.br/webdocs/sie/consultamultas/radares/"


class ColetorSIEPortateis(CadastroPublicado):
    locals().update(cadastro("SIE-SC/PMRv - Inventario de radares portateis", "SC",
        "https://www.sie.sc.gov.br/", formato="pdf", url=BASE +
        "Relacao_medidores_velocidade_portateis_em_operacao_na_SIE_PMRv_ATUALIZADO_EM_02-09-2025.pdf"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for linha in conteudo.splitlines():
            if not linha.startswith("Medidor de velocidade"):
                continue
            partes = re.split(r"\s{2,}", linha.strip())
            if len(partes) != 4 or not re.fullmatch(r"[A-Z0-9]+", partes[3]):
                raise ValueError("Inventario SIE alterou o formato da serie")
            tipo, marca, modelo, serie = partes
            registros.append(dict(identificador=serie, numero_serie=serie,
                marca=marca, modelo=modelo, tipo_publicado=tipo,
                endereco="Inventario de medidores portateis; local de uso nao publicado"))
        return registros

    def normalizar(self, idx, raw):
        dados = super().normalizar(idx, raw)
        dados.update(tipo_radar="portatil", qualidade="desconhecida",
                     tipo_identificador="serie", modalidade="desconhecida")
        return dados


class ColetorSIELocais(CadastroPublicado):
    locals().update(cadastro("SIE-SC/PMRv - Locais elegiveis de fiscalizacao portatil", "SC",
        "https://www.sie.sc.gov.br/", formato="pdf", url=BASE +
        "Novos%20Locais_de_Operacao_Radares_Portateis%20-%2029-01-2026.pdf"))

    @staticmethod
    def extrair_registros(conteudo):
        validade = re.search(r"COM VALIDADE A PARTIR\s+(\d{2}/\d{2}/\d{4})", conteudo)
        if not validade:
            raise ValueError("Lista SIE sem inicio de validade publicado")
        inicio = datetime.strptime(validade.group(1), "%d/%m/%Y").date().isoformat()
        registros = []
        for linha in conteudo.splitlines():
            if not re.match(r"\s*P-\d+\s+\d+", linha):
                continue
            m = re.fullmatch(r"\s*(P-\d+)\s+(\d+)\s+(.+?)\s{2,}(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s*", linha)
            if not m:
                raise ValueError("Local elegivel SIE com formato desconhecido")
            posto, codigo, local, cidade, codigo_municipal, velocidade, considerada = m.groups()
            km = re.search(r"\bKM\s*(\d+(?:\.\d+)?)", local)
            via = re.search(r"\bSC\s*(\d{3})", local)
            if not km:
                raise ValueError("Local elegivel SIE sem quilometro publicado")
            registros.append(dict(identificador=codigo, posto=posto, endereco=local,
                municipio_nome=cidade, codigo_municipal_publicado=codigo_municipal,
                via_codigo="SC-" + via.group(1) if via else local.split(" KM ")[0].removeprefix("ROD. "),
                km=float(km.group(1)), velocidade_regulamentada=int(velocidade),
                velocidade_considerada=int(considerada),
                vigencia_inicio=inicio,
                sentido_original=local[km.end():].strip()))
        return registros

    def normalizar(self, idx, raw):
        sentido = raw["sentido_original"].replace("DESCRESCENTE", "DECRESCENTE")
        return {"tipo_registro": "trecho_elegivel", "uf": "SC",
                "via_codigo": raw["via_codigo"], "via_tipo": "estadual",
                "km_inicio": raw["km"], "km_fim": raw["km"],
                "sentido": nz.normalizar_sentido(sentido), "situacao": "vigente",
                "indicador": "pode_haver_fiscalizacao", "radar_instalado_confirmado": None,
                "vigencia_inicio": raw["vigencia_inicio"],
                "criterio_inclusao": "Local elegivel publicado pela SIE/PMRv; nao confirma operacao nem radar fixo"}
