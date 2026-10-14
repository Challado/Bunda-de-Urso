# -*- coding: utf-8 -*-
"""Fonte PB - Semob Joao Pessoa, medidores de velocidade (locais).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026; publicada 19/11/2024):
  https://www.joaopessoa.pb.gov.br/noticias/secretarias-e-orgaos/semob/semobjp-orienta-populacao-sobre-novos-locais-com-radares-medidores-de-velocidade/

A pagina (noticia oficial da Prefeitura/SemobJP) publica a lista dos locais
dos QUAIS a cidade ganha medidores de velocidade novos, em dois cruzamentos
(Rua Bancario Waldemar de Mesquita Accioly, no Parque das Tres Ruas/Bancarios,
e Avenida Epitacio Pessoa x Rua Paulino Pinto), 6 entradas por sentido. A
pagina remete a relacao COMPLETA ao portal oficial
(https://portal.semobjp.pb.gov.br), onde existe o PDF
"NOVA_RELACAO_PDF_DOS_MEDIDORES_DE_VELOCIDADE_ATUALIZADA_29_01_2025.pdf".

LIMITE REAL (nao escondido): o PDF oficial da relacao completa e um documento
digitalizado / com fonte de subconjunto (codigos de glifo binarios) -- a
extracao de texto "best-effort" da biblioteca padrao
(``planilha.ler_pdf_texto``) devolve string VAZIA/ilegivel (conferido em
10/10/2026). Logo, a relacao completa NAO e legivel aqui; o que e legivel e a
lista desta noticia, por isso o recurso e PARCIAL.

Semantica: o ENDERECO NAO vira GPS -- nenhuma latitude/longitude e inventada.
Cada local entra como cadastro SEM POSICAO_GEOGRAFICA; o texto original fica
em ``observacoes``. ``tipo_radar`` fica "desconhecido" (a fonte NAO declara
fixo/portatil/movel). Cobre apenas a capital, nao a Paraiba.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import html
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_HTML = "text/html; charset=utf-8"

_INICIO_LISTA = "Cruzamentos com novos equipamentos"
_DASHES = "\u2013\u2014-"
_PADRAO_SENTIDO = re.compile(r"sentido\s+([^,;.()]+)", re.I)
_DELIM_LOGRADOURO = ("(", ",", ":", " \u2013 ", " \u2014 ", " - ")
_PREFIXO_LOGRADOURO = re.compile(
    r"^(Avenida|Av\.?|Rua|Travessa|Alameda|Rodovia|Estrada|Pra\u00e7a|Via)\b",
    re.I)


def _texto(fragmento):
    if isinstance(fragmento, bytes):
        fragmento = fragmento.decode("utf-8", "replace")
    t = re.sub(r"(?is)<[^>]+>", " ", fragmento or "")
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def _logradouro(texto):
    s = (texto or "").strip()
    cortes = [s.find(d) for d in _DELIM_LOGRADOURO if s.find(d) > 0]
    if cortes:
        s = s[:min(cortes)]
    s = s.strip().rstrip(";.").strip()
    if s and _PREFIXO_LOGRADOURO.match(s):
        return s
    return None


def _sentido(texto):
    t = texto or ""
    if re.search(r"ambos os sentidos", t, re.I):
        return "ambos", "ambos os sentidos"
    m = _PADRAO_SENTIDO.search(t)
    if not m:
        return None, None
    orig = m.group(1).strip()
    return nz.normalizar_sentido(orig), orig


class ColetorSemobPB(ColetorBase):

    FONTE = {
        "nome": "Semob Joao Pessoa - Medidores de velocidade (locais)",
        "organizacao": ("Superintendencia Executiva de Mobilidade Urbana de "
                        "Joao Pessoa (SemobJP)"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.joaopessoa.pb.gov.br/",
        "documentacao_url": ("https://www.joaopessoa.pb.gov.br/noticias/"
                             "secretarias-e-orgaos/semob/semobjp-orienta-"
                             "populacao-sobre-novos-locais-com-radares-"
                             "medidores-de-velocidade/"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "locais de medidores de velocidade (lista HTML da noticia)",
        "url_recurso": ("https://www.joaopessoa.pb.gov.br/noticias/"
                        "secretarias-e-orgaos/semob/semobjp-orienta-populacao-"
                        "sobre-novos-locais-com-radares-medidores-de-"
                        "velocidade/"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        # relacao completa esta em PDF no portal, porem ilegivel aqui.
        "status_integracao": "parcial",
    }

    PAGINA = RECURSO["url_recurso"]
    PORTAL = "https://portal.semobjp.pb.gov.br"
    URL_RELACAO_OFICIAL = ("https://portal.semobjp.pb.gov.br/wp-content/"
                           "uploads/2025/01/NOVA_RELACAO_PDF_DOS_MEDIDORES_"
                           "DE_VELOCIDADE_ATUALIZADA_29_01_2025.pdf")

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (lista em HTML; nao ha arquivo datado)."""
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def extrair_locais(cls, html_):
        """Lista de {ordem, texto} dos locais publicados (paragrafos com '-').

        Os itens comecam por travessao ('-' / en dash) e terminam em ';'. O
        bloco comeca em "Cruzamentos com novos equipamentos".
        """
        if isinstance(html_, bytes):
            html_ = html_.decode("utf-8", "replace")
        ini = (html_ or "").find(_INICIO_LISTA)
        bloco = html_[ini:] if ini >= 0 else (html_ or "")
        registros = []
        for m in re.finditer(r"(?is)<p\b[^>]*>(.*?)</p>", bloco):
            texto = _texto(m.group(1)).strip()
            if not texto or texto[0] not in _DASHES:
                if registros and not texto.startswith(_INICIO_LISTA):
                    # paragrafo que nao e item encerra a lista
                    break
                continue
            item = texto.lstrip(_DASHES + " ").strip().rstrip(";.").strip()
            if not item:
                continue
            registros.append({"ordem": len(registros) + 1, "texto": item})
        return registros

    # -- carregar ---------------------------------------------------------
    def _ler(self, ref):
        if ref and os.path.exists(str(ref)):
            with open(ref, "rb") as f:
                return f.read()
        return http.baixar(ref)[0]

    def carregar(self, origem):
        alvo = origem or self.PAGINA
        conteudo = self._ler(alvo)
        return (conteudo, ".html", MIME_HTML,
                self.extrair_locais(conteudo))

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return _logradouro(raw.get("texto"))

    def normalizar(self, idx, raw):
        texto = (raw.get("texto") or "").strip()
        if not texto:
            return None
        sentido, sentido_orig = _sentido(texto)
        observacoes = "; ".join(x for x in (
            ("Local publicado (sem coordenada): %s" % texto),
            ("Item %s da lista oficial" % raw.get("ordem"))
            if raw.get("ordem") else None,
            ("Relacao completa em %s (PDF ilegivel pela stdlib)"
             % self.URL_RELACAO_OFICIAL),
            "cadastro sem POSICAO_GEOGRAFICA (endereco nao vira GPS)",
        ) if x)
        return {
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self.identificador(raw),
            "tipo_identificador": "cadastro_local",
            "latitude": None,
            "longitude": None,
            "qualidade": "desconhecida",
            "metodo_obtencao": "publicacao Semob Joao Pessoa (locais)",
            "uf": "PB",
            "municipio_nome": "Joao Pessoa",
            "municipio_ibge": "2507507",
            "via_codigo": _logradouro(texto),
            "via_tipo": "municipal",
            "km": None,
            "tipo_pista": None,
            "situacao": None,
            "tipo_radar": "desconhecido",
            "numero_serie": None,
            "fabricante": None,
            "modelo": None,
            "sentido": sentido,
            "sentido_original": sentido_orig,
            "observacoes": observacoes,
        }
