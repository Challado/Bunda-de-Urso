# -*- coding: utf-8 -*-
"""Fonte propria do cadastro LWB — ingestao pela API de escrita.

Nao e uma publicacao de orgao: e o NOSSO cadastro (a "base nossa"). Por isso
a fonte entra com natureza "outra" (nem oficial, nem comunitaria) e o metodo
de obtencao e explicito. O objetivo e que um radar ingerido pela API se
comporte EXATAMENTE como um radar coletado: mesma normalizacao
(``coletor.fontes.normalizacao``), mesma resolucao de municipio/UF, mesmo
fallback geografico e o MESMO upsert idempotente (identidade externa ->
IDENTIFICADOR_EXTERNO + IDENTIFICADOR_PONTO).

Nada e inventado: campo ausente no payload vira NULL; a coordenada so entra
em POSICAO_GEOGRAFICA se for plausivel (regra compartilhada). O payload bruto
fica em REGISTRO_FONTE.payload_original.
"""
import re

from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


class ColetorBaseLWB(ColetorBase):

    FONTE = {
        "nome": "Bundita de Urso - A base do Bunda de urso",
        "organizacao": "Bundita de Urso",
        "tipo_organizacao": "outro",
        "esfera": "desconhecida",
        "natureza": "outra",
        "url_institucional": "",
        "documentacao_url": "",
        "licenca": None,
        "periodicidade_declarada": "continuada",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "api-v1-radares (POST JSON)",
        "url_recurso": "",
        "formato_origem": "json",
        "periodicidade_segundos": None,
        "status_integracao": "ok",
    }

    # -- a API alimenta por lista de registros ja parseados -----------------
    def carregar(self, origem):
        raise NotImplementedError(
            "a ingestao pela API usa ColetorBase.ingerir_registros")

    def identificador(self, raw):
        if not isinstance(raw, dict):
            return None
        return nz.pick(raw, "identificador", "id_orgao", "codigo", "id", "ID")

    @staticmethod
    def _via_codigo(v):
        if v is None or str(v).strip() == "":
            return None
        return re.sub(r"(?i)^br\s*-?\s*", "BR-", str(v).strip())

    def normalizar(self, idx, raw):
        if not isinstance(raw, dict):
            return None
        lat = nz.to_float(nz.pick(raw, "latitude", "lat"))
        lon = nz.to_float(nz.pick(raw, "longitude", "lon", "lng"))
        municipio = nz.pick(raw, "municipio", "municipio_nome", "cidade")
        ibge = nz.pick(raw, "municipio_ibge", "codigo_ibge", "ibge")
        via_codigo = self._via_codigo(nz.pick(raw, "via", "via_codigo",
                                              "rodovia", "br"))
        # sem coordenada E sem municipio+via, nao ha o minimo para cadastrar
        if lat is None and lon is None:
            if not (municipio or ibge) or not via_codigo:
                return None
        situacao_txt = nz.pick(raw, "situacao", "status")
        return {
            "procedencia": "cadastro_proprio",
            "natureza_fonte": "outra",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self.identificador(raw),
            "tipo_identificador": nz.pick(raw, "tipo_identificador") or "id_orgao",
            "latitude": lat,
            "longitude": lon,
            "precisao_metros": nz.to_float(
                nz.pick(raw, "precisao_metros", "precisao")),
            "qualidade": nz.pick(raw, "qualidade", "qualidade_posicao")
                         or "desconhecida",
            "metodo_obtencao": nz.pick(raw, "metodo_obtencao")
                               or "cadastro proprio Base LWB",
            "uf": nz.pick(raw, "uf", "UF", "estado"),
            "municipio_nome": municipio,
            "municipio_ibge": ibge,
            "via_codigo": via_codigo,
            "km": nz.to_float(nz.pick(raw, "km", "quilometro")),
            "tipo_pista": nz.pick(raw, "tipo_pista", "pista", "faixa"),
            # situacao ausente NAO vira "desconhecido" gravado: fica NULL.
            "situacao": (nz.normalizar_situacao(situacao_txt)
                         if situacao_txt else None),
            "tipo_radar": nz.normalizar_tipo_radar(
                nz.pick(raw, "tipo_radar", "tipo")),
            "modalidade": nz.pick(raw, "modalidade"),
            "numero_serie": nz.pick(raw, "numero_serie", "serie"),
            "fabricante": nz.pick(raw, "fabricante", "marca"),
            "modelo": nz.pick(raw, "modelo"),
            "ano_fabricacao": nz.to_int(nz.pick(raw, "ano_fabricacao")),
            "velocidade_leves": nz.to_velocidade(
                nz.pick(raw, "velocidade_leves")),
            "velocidade_pesados": nz.to_velocidade(
                nz.pick(raw, "velocidade_pesados")),
            "velocidade_geral": nz.to_velocidade(
                nz.pick(raw, "velocidade_geral", "velocidade")),
            "sentido": nz.normalizar_sentido(nz.pick(raw, "sentido")),
            "sentido_original": nz.pick(raw, "sentido"),
            "observacoes": nz.pick(raw, "observacoes"),
        }
