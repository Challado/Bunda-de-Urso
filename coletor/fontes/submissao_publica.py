# -*- coding: utf-8 -*-
"""Normalizacao compartilhada, com origem e identidade publicas isoladas."""
from .base_lwb import ColetorBaseLWB


##-- BUNDITA DE URSO #{19} -- Submissao anonima podia reutilizar ID da ingestao autenticada e sobrescrever seu ponto. ##
class ColetorSubmissaoPublica(ColetorBaseLWB):
    FONTE = dict(ColetorBaseLWB.FONTE,
                 nome="Contribuicoes publicas do Bunda de Urso",
                 organizacao="Contribuicoes publicas",
                 natureza="comunitaria")
    RECURSO = dict(ColetorBaseLWB.RECURSO, nome="submissoes-publicas (POST JSON)")

    def identificador(self, raw):
        # IDs enviados por anonimos sao evidencia, nunca autoridade para upsert.
        return None

    def normalizar(self, idx, raw):
        normalizado = super().normalizar(idx, raw)
        if normalizado is not None:
            normalizado["procedencia"] = "colaborativo"
            normalizado["natureza_fonte"] = "comunitaria"
        return normalizado
