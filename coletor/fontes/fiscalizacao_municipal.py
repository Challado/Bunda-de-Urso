"""Cadastro de fiscalização publicado pelas prefeituras de Mogi, Porto Alegre e Rio."""
import csv
import html
import io
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from urllib.parse import urlencode, urljoin, urlsplit

from coletor import http
from coletor.fontes import normalizacao as nz
from core import atualizacoes
from coletor.fontes.araguaiana_to import _texto_pdf
from coletor.fontes.cadastros_publicos import CadastroPublicado, cadastro, texto
from coletor.fontes.cetsp import consultar_painel, decodificar_dsr, json_publico


class FiscalizacaoMunicipal(CadastroPublicado):
    def normalizar(self, idx, raw):
        d = super().normalizar(idx, raw)
        tipo = raw["tipo_publicado"]
        d.update(tipo_radar="desconhecido" if raw.get("so_avanco") else "fixo",
                 observacoes=" — ".join(filter(None, (tipo, d["observacoes"]))),
                 tipo_medicao="outra" if raw.get("so_avanco") else "velocidade_instantanea",
                 funcao_equipamento=raw.get("funcao_equipamento"),
                 situacao_original=raw.get("situacao_original"))
        if raw.get("coordenada_por_endereco"):
            d.update(qualidade="inferida", metodo_obtencao="Geocodificador de endereços da Prefeitura do Rio")
        return d


class ColetorMogiSP(FiscalizacaoMunicipal):
    PAGINA = "https://dados.mogidascruzes.sp.gov.br/dataset/b93af036-8ed9-4442-82e4-7bc8c3d6c64f"
    locals().update(cadastro("Mogi das Cruzes - Fiscalizacao eletronica", "SP", PAGINA,
        "Mogi das Cruzes", "csv",
        PAGINA + "/resource/822a6c76-4c9b-413b-8299-abd40f903bf4/download/localizacao_radares2.csv"))

    def carregar(self, origem):
        corpo = Path(origem).read_bytes() if origem and Path(origem).is_file() else http.baixar(origem or self.URL)[0]
        try:
            planilha = corpo.decode("utf-8-sig")
        except UnicodeDecodeError:
            planilha = corpo.decode("cp1252")
        leitor = csv.DictReader(io.StringIO(planilha), delimiter=";")
        campos = {"id_radar", "Logradouro", "subtipo", "latitude", "longitude",
                  "Sentido", "Velocidade", "Status"}
        if not campos.issubset(leitor.fieldnames or ()):
            raise ValueError("Colunas da lista oficial de Mogi das Cruzes mudaram")
        registros = []
        for linha in leitor:
            codigo = linha["id_radar"]
            tipo = linha["subtipo"]
            status = linha["Status"]
            if not codigo or not tipo or not status:
                continue
            funcao = {"FIXO": "controlador", "REDUTOR DE VELOCIDADE": "redutor",
                      "AVANÇO DE SINAL": "outro"}.get(tipo)
            if not funcao:
                continue
            avanco = tipo == "AVANÇO DE SINAL"
            registros.append(dict(linha, identificador=codigo, tipo_publicado=tipo,
                endereco=linha["Logradouro"], latitude=nz.to_float(linha["latitude"]),
                longitude=nz.to_float(linha["longitude"]), sentido_original=linha["Sentido"],
                situacao_original=status, so_avanco=avanco, funcao_equipamento=funcao,
                velocidade_geral=None if avanco else nz.to_float(linha["Velocidade"]),
                situacao={"em operacao": "ativo", "inativo": "inativo"}.get(nz.normalizar_nome_texto(status).lower())))
        if not registros:
            raise ValueError("A lista oficial de Mogi não trouxe equipamentos reconhecidos")
        return corpo, ".csv", "text/csv", registros


class ColetorEPTC(FiscalizacaoMunicipal):
    locals().update(cadastro("EPTC Porto Alegre - Medidores eletronicos de velocidade", "RS",
        "https://prefeitura.poa.br/eptc/medidores-eletronicos-de-velocidade", "Porto Alegre", "json"))
    API = "https://wabi-north-europe-api.analysis.windows.net"
    ENTIDADE = "BaseMevFluxo"
    CAMPOS = ["IDLocalMEV", "LOCAL", "LATITUDE", "LONGITUDE", "SENTIDO",
              "LIMITEKMH", "CONTROLADOR", "SITUACAO"]

    def carregar(self, origem):
        if origem and origem != self.PAGINA:
            corpo = Path(origem).read_bytes() if Path(origem).is_file() else http.baixar(origem)[0]
        else:
            pagina = http.baixar(self.PAGINA)[0].decode("utf-8", "replace")
            links = re.findall(r'<a\b[^>]*href="(https://app\.powerbi\.com/view\?[^"]+)"[^>]*>(.*?)</a>',
                               pagina, re.I | re.S)
            link = next((html.unescape(url) for url, legenda in links
                         if "localizacao" in nz.normalizar_nome_texto(texto(legenda)).lower()), None)
            if link is None:
                raise ValueError("A página da EPTC não publicou o painel de localização")
            corpo = consultar_painel(link, self.API, self.ENTIDADE, self.CAMPOS)
        registros = []
        for linha in decodificar_dsr(json_publico(corpo), self.CAMPOS):
            tipo = str(linha["CONTROLADOR"] or "")
            tipo_norm = nz.normalizar_nome_texto(tipo).lower()
            funcao = next((valor for prefixo, valor in (("fixo controlador", "controlador"),
                           ("fixo redutor", "redutor"), ("das", "misto"))
                           if tipo_norm.startswith(prefixo)), None)
            if not funcao or linha["IDLocalMEV"] is None:
                continue
            estado = str(linha["SITUACAO"] or "")
            limite = re.fullmatch(r"(\d{2,3})\s*(?:km/?h)?", str(linha["LIMITEKMH"] or ""), re.I)
            registros.append(dict(linha, identificador=str(linha["IDLocalMEV"]), tipo_publicado=tipo,
                endereco=linha["LOCAL"], latitude=nz.to_float(linha["LATITUDE"]),
                longitude=nz.to_float(linha["LONGITUDE"]), sentido_original=linha["SENTIDO"],
                situacao_original=estado, funcao_equipamento=funcao,
                situacao={"ativo": "ativo", "inativo": "inativo"}.get(nz.normalizar_nome_texto(estado).lower()),
                velocidade_geral=int(limite[1]) if limite else None))
        if not registros:
            raise ValueError("O painel da EPTC não trouxe equipamentos fixos reconhecidos")
        comprimido = corpo.startswith(b"\x1f\x8b")
        return corpo, ".json.gz" if comprimido else ".json", (
            "application/gzip" if comprimido else "application/json"), registros


class ColetorCETRio(FiscalizacaoMunicipal):
    locals().update(cadastro("CET-Rio - Locais de fiscalizacao eletronica", "RJ",
        "https://cetrio.prefeitura.rio/fiscalizacao-eletronica/", "Rio de Janeiro", "pdf"))
    GEOCODIFICADOR = ("https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/"
                      "Geocode_NP/GeocodeServer/findAddressCandidates")

    @classmethod
    def resolver_url(cls):
        pagina = http.baixar(cls.PAGINA)[0].decode("utf-8", "replace")
        links = re.findall(r'href\s*=\s*["\']([^"\']+\.pdf)(?:[?#][^"\']*)?["\']', pagina, re.I)
        oficiais = []
        for link in links:
            url = urljoin(cls.PAGINA, html.unescape(link))
            partes = urlsplit(url)
            dominio = partes.hostname or ""
            if (partes.scheme == "https" and
                (dominio.endswith(".prefeitura.rio") or dominio.endswith(".rio.rj.gov.br"))
                and partes.path.lower().endswith("listagemsmtr.pdf")):
                oficiais.append(url)
        if not oficiais:
            titulo = re.search(r"<title[^>]*>(.*?)</title>", pagina, re.I | re.S)
            detalhe = texto(titulo[1])[:90] if titulo else "sem título"
            raise ValueError(f"A CET-Rio não retornou o link da listagem em PDF (página: {detalhe})")
        return max(oficiais)

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        tipo = None
        acumulado = []
        for linha in conteudo.splitlines():
            linha = linha.strip()
            if not linha:
                continue
            chave = nz.normalizar_nome_texto(linha).lower()
            if "(" not in linha and not acumulado:
                if chave.startswith(("lombada eletr", "medidor velocidade", "medidor de velocidade",
                                     "avanco de sinal")):
                    tipo = linha
                    continue
                if chave.startswith(("faixa exclusiva", "conversao", "retorno", "restricao",
                                     "circulacao", "transito", "fiscalizacao de")):
                    tipo = None
            if tipo is None or linha != linha.upper() or not linha[0].isalpha():
                continue
            acumulado.append(linha)
            item = re.match(r"^(.+?)\s*\((\d{6,})\)(?:\s+(\d{2,3})(?!\d))?", " ".join(acumulado))
            if item is None:
                if sum(map(len, acumulado)) > 350:
                    acumulado.clear()
                continue
            acumulado.clear()
            endereco, codigo, velocidade = item.groups()
            avanco = "avanco" in nz.normalizar_nome_texto(tipo).lower()
            registros.append(dict(identificador=codigo, endereco=endereco, tipo_publicado=tipo,
                so_avanco=avanco, funcao_equipamento="outro" if avanco else
                    "redutor" if "lombada" in nz.normalizar_nome_texto(tipo).lower() else "controlador",
                velocidade_geral=int(velocidade) if not avanco and velocidade and
                    20 <= int(velocidade) <= 130 else None))
        return registros

    def localizar(self, endereco):
        numero = re.search(r"\bN[º°O]?\.?\s*(\d{1,5})\b", endereco, re.I)
        if not numero:
            return None
        consulta = urlencode({"SingleLine": endereco.split(",")[0] + " " + numero[1],
                              "outSR": "4326", "f": "json", "maxLocations": 2})
        dados = json.loads(http.baixar(self.GEOCODIFICADOR + "?" + consulta, tentativas=1)[0])
        candidatos = dados.get("candidates")
        if candidatos is None:
            raise ValueError("Geocodificador municipal indisponível")
        if not candidatos or candidatos[0]["score"] < 95:
            return None
        if len(candidatos) > 1 and candidatos[1]["score"] == candidatos[0]["score"]:
            return None
        posicao = candidatos[0]["location"]
        lat, lon = posicao["y"], posicao["x"]
        return (lat, lon) if -23.2 < lat < -22.65 and -43.9 < lon < -43.05 else None

    def carregar(self, origem):
        corpo = Path(origem).read_bytes() if origem and Path(origem).is_file() else http.baixar(
            self.resolver_url() if not origem or origem == self.PAGINA else origem)[0]
        if corpo.startswith(b"PK"):
            with ZipFile(io.BytesIO(corpo)) as pacote:
                registros = json.loads(pacote.read("locais.json"))
            return corpo, ".zip", "application/zip", registros
        registros = self.extrair_registros(_texto_pdf(corpo))
        if not registros:
            raise ValueError("O PDF oficial da CET-Rio não trouxe locais reconhecidos")
        localizados = {}
        for r in registros:
            endereco = r["endereco"]
            try:
                if endereco not in localizados:
                    localizados[endereco] = self.localizar(endereco)
                posicao = localizados[endereco]
            except (http.ErroFonte, ValueError) as exc:
                atualizacoes.evento("cet_rio.geocodificacao_indisponivel", erro=str(exc))
                break
            if posicao:
                r.update(latitude=posicao[0], longitude=posicao[1], coordenada_por_endereco=True)
        # A origem PDF e as posições obtidas da prefeitura compõem a mesma edição.
        # Um retorno posterior do geocodificador gera um novo artefato, mesmo com PDF idêntico.
        saida = io.BytesIO()
        with ZipFile(saida, "w") as pacote:
            pacote.writestr(ZipInfo("listagem.pdf"), corpo, compress_type=ZIP_DEFLATED)
            pacote.writestr(ZipInfo("locais.json"),
                            json.dumps(registros, ensure_ascii=False).encode(), compress_type=ZIP_DEFLATED)
        return saida.getvalue(), ".zip", "application/zip", registros
