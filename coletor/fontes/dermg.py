# -*- coding: utf-8 -*-
"""Fonte F10 - DER-MG, localizacao de radares fixos e portateis.

Pagina: https://der.mg.gov.br/transportes/localizacao-de-radares-fixos-e-portateis
A propria pagina HTML publica a tabela ("LOCALIZACAO DOS 710 RADARES FIXOS
EM OPERACAO..."), com URG, Rodovia, km, Municipio, Velocidade, Nº do
Equipamento, Nº de Serie, datas de inicio e responsaveis.

A tabela NAO traz coordenadas: os registros sao preservados sem posicao
(normalizar devolve None), conforme a regra de nao posicionar sem evidencia.
Aceita arquivo LOCAL (HTML de fixture) ou baixa a pagina.
"""
import os
import re
import unicodedata
import urllib.request

from core import config
from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_HTML = "text/html"

# chave canonica -> palavras (sem acento) que identificam a coluna.
# Quando ha mais de uma palavra, TODAS precisam aparecer no cabecalho.
MAPA_CABECALHO = (
    ("urg", ("urg",)),
    ("rodovia", ("rodovia",)),
    ("km", ("km",)),
    ("municipio", ("munic",)),
    ("velocidade", ("velocidade",)),
    ("equipamento", ("equipamento",)),
    ("serie", ("serie",)),
    ("inicio_educativo", ("educativo",)),
    ("inicio_autuacao", ("autua",)),
    ("resp_equipamento", ("respons", "equipamento")),
    ("resp_via", ("respons", "via")),
)


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").lower()


class ColetorDERMG(ColetorBase):

    FONTE = {
        "nome": "DER-MG - Localizacao de radares fixos e portateis",
        "organizacao": ("Departamento de Edificacoes e Estradas de Rodagem "
                        "de Minas Gerais"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://der.mg.gov.br/",
        "documentacao_url": ("https://der.mg.gov.br/transportes/"
                             "localizacao-de-radares-fixos-e-portateis"),
        "licenca": "pagina institucional publica",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Tabela de radares fixos (pagina HTML)",
        "url_recurso": ("https://der.mg.gov.br/transportes/"
                        "localizacao-de-radares-fixos-e-portateis"),
        "formato_origem": "html",
        "periodicidade_segundos": 2592000,
        "status_integracao": "ok",
    }

    PAGINA = ("https://der.mg.gov.br/transportes/"
              "localizacao-de-radares-fixos-e-portateis")
    URL_FALLBACK = PAGINA

    @classmethod
    def resolver_url(cls):
        """URL do recurso. Se a pagina expuser um arquivo (xlsx/csv/pdf),
        devolve esse arquivo; senao a propria pagina (fonte do dado)."""
        try:
            req = urllib.request.Request(
                cls.PAGINA, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                    req, timeout=config.DEFAULT_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", "replace")
            for m in re.finditer(
                    r'href="([^"]+\.(?:xlsx|xls|csv|pdf))"', html, re.I):
                if "radar" in m.group(1).lower():
                    return m.group(1)
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    # -- carregar ---------------------------------------------------------
    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            url = origem or self.resolver_url()
            conteudo, _headers, _url_final = http.baixar(url)
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        registros = self._extrair_tabela(conteudo)
        return conteudo, (ext or ".html"), MIME_HTML, registros

    @staticmethod
    def _mapear_cabecalho(celulas):
        mapa = {}
        normalizadas = [_sem_acento(re.sub(r"\s+", " ",
                                           c.replace("\xa0", " ")).strip())
                        for c in celulas]
        for chave, pistas in MAPA_CABECALHO:
            for i, texto in enumerate(normalizadas):
                if all(p in texto for p in pistas):
                    mapa[chave] = i
                    break
        return mapa

    def _extrair_tabela(self, conteudo, cabecalho=None):
        if conteudo[:2] == b"PK":
            linhas = pl.ler_xlsx(conteudo)
            return pl.dicts_de_linhas(linhas)
        texto = conteudo.decode("utf-8", "replace") \
            if isinstance(conteudo, bytes) else conteudo
        tabelas = pl.ler_tabelas_html(texto)
        alvo = None
        for tab in sorted(tabelas, key=len, reverse=True):
            for linha in tab[:6]:
                if self._mapear_cabecalho(linha).get("rodovia") is not None \
                        and self._mapear_cabecalho(linha).get("km") is not None:
                    alvo = tab
                    break
            if alvo is not None:
                break
        if alvo is None:
            return []
        # localiza a linha de cabecalho dentro da tabela
        idx_cab = None
        for i, linha in enumerate(alvo):
            mapa = self._mapear_cabecalho(linha)
            if mapa.get("rodovia") is not None and mapa.get("km") is not None:
                idx_cab, mapa_cab = i, mapa
                break
        if idx_cab is None:
            return []
        registros = []
        for linha in alvo[idx_cab + 1:]:
            if len(linha) < 4:
                continue
            d = {}
            for chave, pos in mapa_cab.items():
                d[chave] = linha[pos].replace("\xa0", " ").strip() \
                    if pos < len(linha) else ""
            # ignora linhas de rodape/observacao (sem rodovia plausivel)
            if not re.search(r"[A-Z]{2,}\d", d.get("rodovia", "")):
                continue
            registros.append(d)
        return registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "equipamento", "Nº do Equipamento")

    @staticmethod
    def _velocidades(texto):
        nums = [float(x.replace(",", "."))
                for x in re.findall(r"\d+(?:[.,]\d+)?", texto or "")]
        nums = [n for n in nums if 0 < n <= 350]
        if not nums:
            return None, None
        if len(nums) == 1:
            return nums[0], None
        # regra da fonte: maior se aplica a leves, menor a pesados
        return max(nums), min(nums)

    def normalizar(self, idx, raw):
        lat, lon = pl.parse_coordenadas(
            nz.pick(raw, "Coordenadas", "coordenadas", "latitude"))
        # a tabela nao traz coordenada: o registro e guardado SEM posicao
        # (preservado, nunca posicionado por chute).
        leves, pesados = self._velocidades(raw.get("velocidade"))
        serie = (raw.get("serie") or "").strip()
        # a fonte pode listar VARIOS numeros por linha; nao presumir 1:1
        series = serie.split()
        numero_serie = series[0] if len(series) == 1 else None
        return {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao DER-MG",
            "uf": "MG",
            "municipio_nome": nz.pick(raw, "municipio", "Município"),
            "via_codigo": nz.pick(raw, "rodovia", "Rodovia"),
            "via_tipo": "estadual",
            "km": nz.to_float(nz.pick(raw, "km", "Km")),
            "tipo_radar": "fixo",
            "numero_serie": numero_serie,
            "velocidade_leves": leves,
            "velocidade_pesados": pesados,
            "observacoes": "; ".join(x for x in (
                ("URG: %s" % raw.get("urg")) if raw.get("urg") else None,
                ("Equipamento(s): %s" % raw.get("equipamento"))
                if raw.get("equipamento") else None,
                ("Serie(s): %s" % serie) if serie else None,
                ("Inicio educativo: %s" % raw.get("inicio_educativo"))
                if raw.get("inicio_educativo") else None,
                ("Inicio autuacao: %s" % raw.get("inicio_autuacao"))
                if raw.get("inicio_autuacao") else None,
                ("Responsavel equipamento: %s" % raw.get("resp_equipamento"))
                if raw.get("resp_equipamento") else None,
                ("Responsavel via: %s" % raw.get("resp_via"))
                if raw.get("resp_via") else None,
            ) if x) or None,
        }
