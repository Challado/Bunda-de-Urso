"""Coleta de documentos e portais: leitura comprovada, sem inventar radares."""
from html.parser import HTMLParser
import re
import unicodedata

from coletor.base import ColetorBase


def _simples(texto):
    simples = ''.join(c for c in unicodedata.normalize('NFKD', texto).casefold()
                      if not unicodedata.combining(c))
    return ' '.join(simples.split())


class _TextoPagina(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.textos, self.titulos = [], []
        self.oculto = 0
        self.titulo = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.oculto += 1
        if tag in ('title', 'h1'):
            self.titulo = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.oculto = max(0, self.oculto - 1)
        if tag in ('title', 'h1'):
            self.titulo = False

    def handle_data(self, texto):
        if not self.oculto:
            self.textos.append(texto)
            if self.titulo:
                self.titulos.append(texto)


class ColetorDocumental(ColetorBase):
    MODO_COLETA = 'documental'
    MARCADORES_DOCUMENTAIS = ()
    DESCRICAO_COLETA = 'Documentação pública; cadastro de radares ainda pendente.'

    def validar_coleta(self, conteudo, registros):
        texto = conteudo.decode('utf-8', 'replace') if isinstance(conteudo, bytes) else conteudo
        pagina = _TextoPagina()
        pagina.feed(texto)
        titulo = _simples(' '.join(pagina.titulos))
        visivel = _simples(' '.join(pagina.textos))
        if re.search(r'nao encontrad|not found|access denied|acesso negado|forbidden|captcha|service unavailable', titulo):
            raise ValueError('A fonte devolveu uma pagina de erro ou bloqueio, mesmo que o HTTP seja 200: ' + titulo[:180])
        if not self.MARCADORES_DOCUMENTAIS or not all(re.search(m, visivel) for m in self.MARCADORES_DOCUMENTAIS):
            raise ValueError('Pagina documental nao reconhecida; a origem pode ter mudado ou retornado erro.')
        if not registros or any(not isinstance(r, dict) or not r for r in registros):
            raise ValueError('Pagina reconhecida, mas nenhum documento ou registro de evidencia foi extraido.')
