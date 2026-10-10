# -*- coding: utf-8 -*-
"""Fonte AM - IMMU Manaus, fiscalizacao eletronica (lista de locais).

Pagina institucional (HTTPS, HTTP 200 em 10/10/2026; publicada 01/02/2026):
  https://www.manaus.am.gov.br/noticia/transito/fiscalizacao-eletronica-salvar-vidas/

A pagina (noticia oficial da Prefeitura/IMMU) publica a RELACAO dos 34 NOVOS
pontos de fiscalizacao eletronica, agrupados por categoria declarada:
  - "Detector de Eixo:" (itens 1-10)
  - "Controle de velocidade (60 quilometros):" (itens 11-17)
  - "Lombada Eletronica (40 quilometros):" (itens 18-19)
  - "Avanco de sinal de vermelho:" (itens 20-34)
Cada item e um ENDERECO/TRECHO urbano (avenida/rua + bairro + sentido), SEM
coordenada geografica. A pagina NAO publica dataset, PDF, CSV, GeoJSON nem
portal de dados abertos (https://dados.manaus.am.gov.br inexistente).

Semantica: o ENDERECO NAO vira GPS -- nenhuma latitude/longitude e inventada.
Cada item entra como cadastro SEM POSICAO_GEOGRAFICA; a categoria declarada e o
texto original da fonte ficam preservados em ``observacoes``. ``tipo_radar``
fica "desconhecido" (a fonte NAO declara fixo/portatil/movel).

A pagina cita 61 equipamentos no total e descreve somente os 34 novos: a lista
e, por construcao, PARCIAL (27 preexistentes nao publicados aqui).

Aceita arquivo LOCAL (HTML de fixture) para testes offline.
"""
import html
import os
import re

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

MIME_HTML = "text/html; charset=utf-8"

# item numerado da lista: "12. Avenida Pedro Teixeira ..."
_ITEM = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.+)$", re.S)
# etiqueta de categoria: paragrafo curto terminando em ":"
_CATEGORIA = re.compile(r"^(?P<nome>[^.:]{3,80}):$")
_PADRAO_SENTIDO = re.compile(r"sentido\s+([^,;.()]+)", re.I)
_DELIM_LOGRADOURO = ("(", ",", ":", " \u2013 ", " \u2014 ", " - ")
_PREFIXO_LOGRADOURO = re.compile(
    r"^(Avenida|Av\.?|Rua|Travessa|Alameda|Rodovia|Estrada|Pra\u00e7a|Via)\b",
    re.I)


def _texto(fragmento):
    """Remove tags, decodifica entidades e normaliza espacos."""
    if isinstance(fragmento, bytes):
        fragmento = fragmento.decode("utf-8", "replace")
    t = re.sub(r"(?is)<[^>]+>", " ", fragmento or "")
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def _logradouro(texto):
    """Extrai o logradouro inicial do endereco (ou None se nao reconhecido)."""
    s = (texto or "").strip()
    cortes = [s.find(d) for d in _DELIM_LOGRADOURO if s.find(d) > 0]
    if cortes:
        s = s[:min(cortes)]
    s = s.strip().rstrip(";.").strip()
    if s and _PREFIXO_LOGRADOURO.match(s):
        return s
    return None


def _sentido(texto):
    """(sentido_canonico, sentido_original) a partir de 'sentido X'."""
    t = texto or ""
    if re.search(r"ambos os sentidos", t, re.I):
        return "ambos", "ambos os sentidos"
    m = _PADRAO_SENTIDO.search(t)
    if not m:
        return None, None
    orig = m.group(1).strip()
    return nz.normalizar_sentido(orig), orig


class ColetorIMMUAM(ColetorBase):

    FONTE = {
        "nome": "IMMU Manaus - Fiscalizacao eletronica (locais)",
        "organizacao": ("Instituto Municipal de Mobilidade Urbana (IMMU) - "
                        "Manaus"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "municipal",
        "natureza": "oficial",
        "url_institucional": "https://www.manaus.am.gov.br/",
        "documentacao_url": ("https://www.manaus.am.gov.br/noticia/transito/"
                             "fiscalizacao-eletronica-salvar-vidas/"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular (por ampliacao)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "locais de fiscalizacao eletronica (lista HTML por categoria)",
        "url_recurso": ("https://www.manaus.am.gov.br/noticia/transito/"
                        "fiscalizacao-eletronica-salvar-vidas/"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,   # ~30 dias (verificacao)
        # publica so os 34 novos pontos (ha 61 no total); sem coordenadas.
        "status_integracao": "parcial",
    }

    PAGINA = RECURSO["url_recurso"]

    @classmethod
    def resolver_url(cls):
        """URL da pagina oficial (lista em HTML; nao ha arquivo datado)."""
        return cls.PAGINA

    # -- descoberta (offline-testavel) ------------------------------------
    @classmethod
    def extrair_pontos(cls, html_):
        """Lista de {ordem, categoria, texto} dos locais publicados.

        Percorre os paragrafos do bloco "Locais de instalacao dos novos
        equipamentos": cada paragrafo numerado e um item; cada paragrafo curto
        terminado em ':' e a etiqueta de categoria dos itens seguintes.
        """
        if isinstance(html_, bytes):
            html_ = html_.decode("utf-8", "replace")
        ini = (html_ or "").find("Locais de instala")
        if ini < 0:
            return []
        bloco = html_[ini:]
        registros = []
        categoria = None
        for m in re.finditer(r"(?is)<p\b[^>]*>(.*?)</p>", bloco):
            texto = _texto(m.group(1))
            if not texto:
                continue
            if texto[0].isdigit():
                mm = _ITEM.match(texto)
                if not mm:
                    break
                item = mm.group(2).strip().rstrip(";.").strip()
                if not item:
                    break
                registros.append({"ordem": int(mm.group(1)),
                                  "categoria": categoria, "texto": item})
                continue
            cat = _CATEGORIA.match(texto)
            if cat:
                categoria = cat.group("nome").strip()
                continue
            if registros:
                # primeiro paragrafo que nao e item nem categoria encerra
                break
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
                self.extrair_pontos(conteudo))

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return _logradouro(raw.get("texto"))

    def normalizar(self, idx, raw):
        texto = (raw.get("texto") or "").strip()
        if not texto:
            return None
        categoria = raw.get("categoria")
        sentido, sentido_orig = _sentido(texto)
        observacoes = "; ".join(x for x in (
            ("Categoria na fonte: %s" % categoria) if categoria else None,
            ("Local publicado (sem coordenada): %s" % texto),
            ("Item %s da lista oficial" % raw.get("ordem"))
            if raw.get("ordem") else None,
            "cadastro sem POSICAO_GEOGRAFICA (endereco nao vira GPS)",
        ) if x)
        return {
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self.identificador(raw),
            "tipo_identificador": "cadastro_local",
            # endereco NAO vira GPS: nada de latitude/longitude inventada
            "latitude": None,
            "longitude": None,
            "qualidade": "desconhecida",
            "metodo_obtencao": "publicacao IMMU Manaus (lista de locais)",
            "uf": "AM",
            "municipio_nome": "Manaus",
            "municipio_ibge": "1302603",
            "via_codigo": _logradouro(texto),
            "via_tipo": "municipal",
            "km": None,
            "tipo_pista": None,
            # a fonte NAO declara situacao atual de cada ponto
            "situacao": None,
            # a fonte NAO declara fixo/portatil/movel -> nada e inventado
            "tipo_radar": "desconhecido",
            "numero_serie": None,
            "fabricante": None,
            "modelo": None,
            "sentido": sentido,
            "sentido_original": sentido_orig,
            "observacoes": observacoes,
        }
