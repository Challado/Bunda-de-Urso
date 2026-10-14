# -*- coding: utf-8 -*-
"""Fonte MS - Agetran Campo Grande, radares de fiscalizacao eletronica.

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026):
  https://www.campogrande.ms.gov.br/cgnoticias/noticia/novos-radares-operam-em-carater-educativo-ate-14-de-julho/

A pagina (noticia oficial da Prefeitura/Agetran) publica, em uma lista HTML
(<ul class="wp-block-list">), os ENDERECOS dos novos radares de fiscalizacao
eletronica instalados em vias de elevado fluxo (a materia cita "nove
equipamentos"; a lista traz 8 enderecos, um deles "em ambos os sentidos").
A fiscalizacao efetiva comeca em 15/07/2026 (30/06 a 14/07 em carater
educativo). NAO ha coordenada geografica, dataset, PDF, CSV, GeoJSON nem
portal de dados abertos (dados.campogrande.ms.gov.br inexistente).

Semantica: o ENDERECO NAO vira GPS -- nenhuma latitude/longitude e inventada.
Cada endereco entra como cadastro SEM POSICAO_GEOGRAFICA; o texto original da
fonte fica preservado em ``observacoes``. ``tipo_radar`` fica "desconhecido"
(a fonte NAO declara fixo/portatil/movel). Cobre apenas a capital, nao o MS.

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import html
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_HTML = "text/html; charset=utf-8"

_PADRAO_SENTIDO = re.compile(r"sentido\s+([^,;.()]+)", re.I)
_DELIM_LOGRADOURO = (":", "(", ",", " \u2013 ", " \u2014 ", " - ")
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


class ColetorAgetranMS(ColetorBase):

    FONTE = {
        "nome": "Agetran Campo Grande - Radares de fiscalizacao eletronica",
        "organizacao": ("Agencia Municipal de Transporte e Transito (Agetran) "
                        "- Campo Grande"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.campogrande.ms.gov.br/",
        "documentacao_url": ("https://www.campogrande.ms.gov.br/cgnoticias/"
                             "noticia/novos-radares-operam-em-carater-"
                             "educativo-ate-14-de-julho/"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "radares - enderecos (lista HTML) ",
        "url_recurso": ("https://www.campogrande.ms.gov.br/cgnoticias/noticia/"
                        "novos-radares-operam-em-carater-educativo-ate-14-de-"
                        "julho/"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        # lista municipal (capital); sem coordenadas.
        "status_integracao": "parcial",
    }

    PAGINA = RECURSO["url_recurso"]

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (lista em HTML; nao ha arquivo datado)."""
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def extrair_enderecos(cls, html_):
        """Lista de {ordem, texto} dos enderecos publicados (<li> da lista)."""
        if isinstance(html_, bytes):
            html_ = html_.decode("utf-8", "replace")
        ini = (html_ or "").find("Endere")
        if ini >= 0:
            u = html_.find("<ul", ini)
            if u >= 0:
                f = html_.find("</ul>", u)
                bloco = html_[u:f] if f > u else html_[u:]
            else:
                bloco = html_[ini:]
        else:
            bloco = (html_ or "")
        registros = []
        for m in re.finditer(r"(?is)<li\b[^>]*>(.*?)</li>", bloco):
            texto = _texto(m.group(1)).strip().rstrip(";.").strip()
            if not texto:
                continue
            # os itens de endereco comecam por logradouro conhecido
            if not _PREFIXO_LOGRADOURO.match(texto.split(":")[0].strip()):
                continue
            registros.append({"ordem": len(registros) + 1, "texto": texto})
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
                self.extrair_enderecos(conteudo))

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return _logradouro(raw.get("texto"))

    def normalizar(self, idx, raw):
        texto = (raw.get("texto") or "").strip()
        if not texto:
            return None
        sentido, sentido_orig = _sentido(texto)
        observacoes = "; ".join(x for x in (
            ("Endereco publicado (sem coordenada): %s" % texto),
            ("Item %s da lista oficial" % raw.get("ordem"))
            if raw.get("ordem") else None,
            "fiscalizacao efetiva a partir de 15/07/2026 (30/06-14/07"
            " educativo)",
            "cadastro sem POSICAO_GEOGRAFICA (endereco nao vira GPS)",
        ) if x)
        return {
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self.identificador(raw),
            "tipo_identificador": "cadastro_local",
            "latitude": None,
            "longitude": None,
            "qualidade": "desconhecida",
            "metodo_obtencao": "publicacao Agetran Campo Grande (enderecos)",
            "uf": "MS",
            "municipio_nome": "Campo Grande",
            "municipio_ibge": "5002704",
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
