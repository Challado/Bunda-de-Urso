# -*- coding: utf-8 -*-
"""Fonte F09 - DER-PR, fiscalizacao fixa e portatil.

Pagina institucional: https://www.der.pr.gov.br/Pagina/Fiscalizacao-de-velocidade
A pagina de equipamento FIXO publica um PDF por concessionaria (ex.: "EPR
Litoral Pioneiro"), cujo nome e datado; a URL e descoberta na propria pagina.
A pagina de equipamento PORTATIL nao publica arquivo baixavel (apenas links
institucionais) -- registrado como limitacao.

O PDF e um relatorio tabular simples; o texto e extraido com a biblioteca
padrao (zlib) por `planilha.ler_pdf_texto` e as linhas sao reconhecidas por
padrao. Aceita arquivo LOCAL (PDF ou texto ja extraido) para testes.
"""
import os
import re
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl

MIME_PDF = "application/pdf"

# Linha do relatorio: concessionaria, tipo, serie, identificacao, municipio,
# rodovia, km+metros, registro IPEM/PR, data verificacao, validade.
PADRAO_LINHA = re.compile(
    r"(?P<concessionaria>[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .\-/&]*?)\s+"
    r"(?P<tipo>Controlador|Redutor|Medidor|Controladores)\s+"
    r"(?P<serie>[A-Z]{2,}\d[\w\-]*)\s+"
    r"(?P<identificacao>\d{3}\.\d{3}\.\d{3}\.\d{2})\s+"
    r"(?P<municipio>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]*?)\s+"
    r"(?P<rodovia>[A-Z]{2}-\s?\d{2,4})\s+"
    r"km\s*(?P<km>\d{1,4})\+(?P<metros>\d{1,3})\s+"
    r"(?P<ipem>\d{5,10})\s+"
    r"(?P<verificacao>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<validade>\d{2}/\d{2}/\d{4})")


class ColetorDERPR(ColetorBase):

    FONTE = {
        "nome": "DER-PR - Fiscalizacao de velocidade (fixa e portatil)",
        "organizacao": ("Departamento de Estradas de Rodagem do Parana"),
        "tipo_organizacao": "orgao_publico",
        "esfera": "estadual",
        "natureza": "oficial",
        "url_institucional": "https://www.der.pr.gov.br/",
        "documentacao_url": ("https://www.der.pr.gov.br/Pagina/"
                             "Fiscalizacao-de-velocidade"),
        "licenca": "documento oficial publicado",
        "periodicidade_declarada": "irregular",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Relacao de medidores de velocidade tipo fixo (PDF)",
        "url_recurso": ("https://www.der.pr.gov.br/Pagina/"
                        "Fiscalizacao-por-Equipamento-Fixo"),
        "formato_origem": "pdf",
        "periodicidade_segundos": 2592000,
        "status_integracao": "parcial",   # so equipamento fixo; portatil sem arquivo
    }

    PAGINA_FIXO = ("https://www.der.pr.gov.br/Pagina/"
                   "Fiscalizacao-por-Equipamento-Fixo")
    URL_FALLBACK = ("https://www.der.pr.gov.br/sites/der/arquivos_restritos/"
                    "files/documento/2026-03/EPRLP_radares_fixos_240326.pdf")

    @classmethod
    def resolver_url(cls):
        """URL do PDF de equipamento fixo descoberta na pagina; fallback fixo."""
        try:
            req = urllib.request.Request(
                cls.PAGINA_FIXO, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                    req, timeout=config.DEFAULT_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", "replace")
            for m in re.finditer(r'href="([^"]+\.pdf)"', html, re.I):
                if "radar" in m.group(1).lower() or "fixo" in m.group(1).lower():
                    return m.group(1)
            for m in re.finditer(r'href="([^"]+\.pdf)"', html, re.I):
                return m.group(1)
        except Exception:                                  # noqa: BLE001
            pass
        return cls.URL_FALLBACK

    def carregar(self, origem):
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower()
        else:
            url = origem or self.resolver_url()
            req = urllib.request.Request(
                url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                    req, timeout=config.DEFAULT_TIMEOUT) as resp:
                conteudo = resp.read()
            ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext in (".txt", ".text"):
            texto = conteudo.decode("utf-8", "replace")
            mime = "text/plain"
        else:
            texto = pl.ler_pdf_texto(conteudo)
            mime = MIME_PDF
        registros = self.extrair_registros(texto)
        return conteudo, (ext or ".pdf"), mime, registros

    @classmethod
    def extrair_registros(cls, texto):
        """Reconhece as linhas do relatorio a partir do texto extraido."""
        if not texto:
            return []
        corte = texto.find("ESTUDO TÉCNICO")
        if corte >= 0:
            texto = texto[corte + len("ESTUDO TÉCNICO"):]
        registros = []
        for m in PADRAO_LINHA.finditer(texto):
            d = m.groupdict()
            d["rodovia"] = re.sub(r"-\s+", "-", d["rodovia"])
            d["km_completo"] = "%s+%s" % (d["km"], d["metros"])
            registros.append(d)
        return registros

    # -- normalizar -------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "identificacao", "identificador", "serie")

    def normalizar(self, idx, raw):
        lat, lon = pl.parse_coordenadas(
            nz.pick(raw, "Coordenadas", "coordenadas", "geometria"))
        # o relatorio NAO traz coordenada: guardado SEM posicao (preservado).
        km = None
        if raw.get("km") is not None:
            try:
                km = float(str(raw["km"]).replace(",", ".")) + \
                    float(str(raw.get("metros") or 0)) / 1000.0
            except ValueError:
                km = None
        return {
            "identificador": self.identificador(raw),
            "latitude": lat,
            "longitude": lon,
            "qualidade": "oficial",
            "metodo_obtencao": "publicacao DER-PR (PDF de medidores fixos)",
            "uf": "PR",
            "municipio_nome": nz.pick(raw, "municipio", "Município"),
            "via_codigo": nz.pick(raw, "rodovia", "Rodovia"),
            "via_tipo": "estadual",
            "km": km,
            "tipo_radar": "fixo",
            "numero_serie": nz.pick(raw, "serie", "numero_serie"),
            "fabricante": None,
            "modelo": None,
            "observacoes": "; ".join(x for x in (
                ("Tipo: %s" % raw.get("tipo")) if raw.get("tipo") else None,
                ("Concessionaria: %s" % raw.get("concessionaria"))
                if raw.get("concessionaria") else None,
                ("Registro IPEM/PR: %s" % raw.get("ipem"))
                if raw.get("ipem") else None,
                ("Verificacao: %s" % raw.get("verificacao"))
                if raw.get("verificacao") else None,
                ("Validade: %s" % raw.get("validade"))
                if raw.get("validade") else None,
            ) if x) or None,
        }
