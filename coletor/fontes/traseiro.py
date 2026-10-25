"""Publica somente posicoes conferidas pela moderacao local."""
from .base_lwb import ColetorBaseLWB

class ColetorTraseiro(ColetorBaseLWB):
    FONTE=dict(ColetorBaseLWB.FONTE,nome='TRASEIRO DE URSO - posicoes validadas',
               organizacao='Rede TRASEIRO DE URSO',natureza='outra')
    RECURSO=dict(ColetorBaseLWB.RECURSO,nome='Validacoes locais da rede mesh')

    def normalizar(self,idx,raw):
        doc=super().normalizar(idx,raw)
        if doc is not None:
            doc['procedencia']='oficial'
            doc['metodo_obtencao']='posicao da rede mesh conferida pela moderacao local'
        return doc
