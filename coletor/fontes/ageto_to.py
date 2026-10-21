"""Relacao estadual de equipamentos fixos publicada pela AGETO/TO.

O PDF geral publica GPS, rodovia/km, municipio, tipo, limite, contagem de
faixas, serie e numero Inmetro. Estudos individuais nao substituem a lista.
O artefato original e preservado pelo pipeline comum; nao ha consulta externa
durante a requisicao publica nem inferencia de GPS, sentido ou estado ativo.
"""
import os
import re
import subprocess
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz


_LINHA = re.compile(
    r"^(?P<rodovia>TO-\d{3})\s+(?P<km>\d+(?:[.,]\d+)?)\s+"
    r"(?P<coordenadas>.*?)\s{2,}(?P<municipio>.*?)\s{2,}"
    r"(?P<tipo>BARREIRA ELETR[ÔO]NICA|RADAR FIXO|RADAR MISTO)\s+"
    r"(?P<velocidade>\d+)\s+(?P<faixas>\d+)\s+"
    r"(?P<numero_serie>[A-Z0-9]+)\s+(?P<numero_inmetro>[\d.]+)\s*$")
_COORD = re.compile(r"^\s*(-?\d+\.\d+)\s*[°º]?\s*[,;]?\s+"
                    r"(-?\d+\.\d+)\s*[°º]?\s*$")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.rotulo = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.rotulo = []

    def handle_data(self, data):
        if self.href:
            self.rotulo.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.rotulo)))
            self.href = None


class ColetorAGETOTO(ColetorBase):
    URL_PAGINA = "https://www.to.gov.br/ageto/lista-de-radares/l3d43475lu1"
    # Relacao geral conferida em 21/10/2026; nunca usar um estudo CEV aqui.
    URL_FALLBACK = "https://central.to.gov.br/download/482949"
    FONTE = {
        "nome": "AGETO-TO - Relacao dos equipamentos fixos medidores de velocidade",
        "organizacao": "Agencia de Transportes, Obras e Infraestrutura do Tocantins (AGETO)",
        "tipo_organizacao": "orgao_publico", "esfera": "estadual",
        "natureza": "oficial", "url_institucional": "https://www.to.gov.br/ageto",
        "documentacao_url": URL_PAGINA, "licenca": "publicacao oficial publica",
        "periodicidade_declarada": "irregular", "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Relacao geral de radares fixos (PDF)",
        "url_recurso": URL_FALLBACK, "formato_origem": "pdf",
        "periodicidade_segundos": 604800, "status_integracao": "ok",
    }

    @classmethod
    def descobrir_recursos(cls, html):
        parser = _Links()
        parser.feed(html)
        for href, rotulo in parser.links:
            nome = nz.normalizar_nome_texto(rotulo)
            if "LISTA RADARES" not in nome or "AGETO" not in nome:
                continue
            url = urljoin(cls.URL_PAGINA, href)
            partes = urlparse(url)
            if (partes.scheme == "https" and partes.hostname in
                    ("www.to.gov.br", "to.gov.br", "central.to.gov.br")
                    and not partes.username and not partes.password
                    and partes.port in (None, 443)):
                return {"pdf": url}
        return {}

    @classmethod
    def resolver_url(cls):
        try:
            html = http.baixar(cls.URL_PAGINA)[0].decode("utf-8", "replace")
            return cls.descobrir_recursos(html).get("pdf", cls.URL_FALLBACK)
        except http.ErroFonte:
            return cls.URL_FALLBACK

    def carregar(self, origem):
        if origem and os.path.isfile(origem):
            with open(origem, "rb") as arquivo:
                conteudo = arquivo.read()
            url = self.URL_FALLBACK
            texto_local = os.path.splitext(origem)[1].lower() == ".txt"
        else:
            url = origem or self.resolver_url()
            if url == self.URL_PAGINA:
                url = self.resolver_url()
            conteudo, _, url = http.baixar(url)
            texto_local = False
        # Instancia propria: nao muda os metadados da classe ou de outra coleta.
        self.RECURSO = dict(type(self).RECURSO, url_recurso=url)
        if texto_local:
            texto, ext, mime = conteudo.decode("utf-8-sig"), ".txt", "text/plain"
        else:
            if not conteudo.startswith(b"%PDF-"):
                raise ValueError("AGETO: a resposta nao e um PDF da relacao de radares")
            try:
                proc = subprocess.run(["pdftotext", "-layout", "-", "-"], input=conteudo,
                                      capture_output=True, timeout=60, check=True)
            except FileNotFoundError as exc:
                raise ValueError("AGETO: instale poppler-utils (pdftotext) para ler a tabela") from exc
            texto, ext, mime = proc.stdout.decode("utf-8", "replace"), ".pdf", "application/pdf"
        return conteudo, ext, mime, self.extrair_registros(texto)

    def sincronizar(self, origem, publicar=True):
        origem = origem or self.resolver_url()
        if origem == self.URL_PAGINA:
            origem = self.resolver_url()
        url = self.URL_FALLBACK if os.path.isfile(origem) else origem
        self.RECURSO = dict(type(self).RECURSO, url_recurso=url)
        return super().sincronizar(origem, publicar=publicar)

    @staticmethod
    def extrair_registros(texto):
        linhas = texto.splitlines()
        registros = []

        def complemento(i):
            if i < 0 or i >= len(linhas):
                return ""
            linha = linhas[i]
            inicio = len(linha) - len(linha.lstrip())
            # Celula de municipio quebrada em ate tres linhas no PDF geral.
            return (linha.strip() if 40 <= inicio < 60
                    and re.fullmatch(r"[A-ZÀ-Ü ]+", linha.strip()) else "")

        for i, linha in enumerate(linhas):
            if not re.match(r"^TO-\d{3}\b", linha):
                continue
            m = _LINHA.fullmatch(linha)
            if m is None:
                raise ValueError("AGETO: formato de linha nao reconhecido; ultimo lote preservado")
            raw = m.groupdict()
            raw["municipio"] = raw["municipio"].strip() or " ".join(p for p in
                (complemento(i - 1), complemento(i + 1)) if p)
            raw["linha_publicada"] = linha.strip()
            registros.append(raw)
        if not registros:
            raise ValueError("AGETO: PDF sem tabela reconhecida; ultimo lote preservado")
        return registros

    def identificador(self, raw):
        # Pontos/zeros de formatacao nao alteram o numero Inmetro (000.770 = 770).
        return str(int(raw["numero_inmetro"].replace(".", "")))

    def normalizar(self, idx, raw):
        m = _COORD.fullmatch(raw["coordenadas"])
        lat, lon = (map(float, m.groups()) if m else (None, None))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            lat = lon = None
        return {
            "identificador": self.identificador(raw), "tipo_identificador": "numero_inmetro",
            "numero_serie": raw["numero_serie"], "latitude": lat, "longitude": lon,
            "qualidade": "oficial" if lat is not None else "nao_confirmada",
            "metodo_obtencao": "coordenadas publicadas na relacao geral da AGETO-TO",
            "uf": "TO", "municipio_nome": raw["municipio"],
            "via_codigo": raw["rodovia"], "via_tipo": "estadual",
            "km": nz.to_float(raw["km"]), "tipo_radar": "fixo",
            "velocidade_geral": nz.to_velocidade(raw["velocidade"]),
            "situacao": None, "sentido": None,
            "observacoes": ("Tipo publicado: %s; Faixas declaradas: %s" %
                            (raw["tipo"], raw["faixas"])),
        }
