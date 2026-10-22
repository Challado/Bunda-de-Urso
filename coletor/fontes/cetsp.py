"""Dados do painel publico de fiscalizacao da CET-SP, sem login ou navegador.

O identificador ResourceKey esta no proprio link publico divulgado pela CET;
nao e chave de conta. Consulta somente colunas publicadas de equipamentos.
Datas de desativacao sao preservadas. Nao importa cameras nao metrologicas.
"""
import base64
import gzip
import html
import io
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from coletor import http
from coletor.fontes import normalizacao as nz
from coletor.fontes.cadastros_publicos import CadastroPublicado, cadastro

API = "https://wabi-brazil-south-b-primary-api.analysis.windows.net"
ENTIDADE = "tblFiscalizacaoEletronica"
CAMPOS = ["ID", "TIPO", "ATIVAÇÃO", "DESATIVAÇÃO", "NÚMERO DE SÉRIE",
          "CÓDIGO LOCAL", "DESCRIÇÃO DO LOCAL", "LATITUDE", "LONGITUDE",
          "VELOCIDADE", "METROLÓGICO", "ENQUADRAMENTOS", "FAIXAS", "WebDoc"]


def json_publico(corpo):
    if isinstance(corpo, bytes) and corpo.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(corpo)) as arquivo:
            corpo = arquivo.read(http.MAX_BYTES_PADRAO + 1)
        if len(corpo) > http.MAX_BYTES_PADRAO:
            raise ValueError("JSON publico descomprimido excede o limite de coleta")
    return json.loads(corpo)


def decodificar_dsr(documento):
    """DSR com dicionarios, repeticao e nulos; recusa janela incompleta."""
    dados = documento["results"][0]["result"]["data"]
    dataset = dados["dsr"]["DS"][0]
    if dataset.get("IC") is not True:
        raise ValueError("Painel CET devolveu janela incompleta; cadastro nao publicado")
    campos = [x["Name"].split(".", 1)[1] for x in dados["descriptor"]["Select"]]
    if campos != CAMPOS:
        raise ValueError("Colunas do painel CET mudaram")
    registros = []
    for grupo in dataset["PH"]:
        anterior, esquema = [], None
        for linha in grupo["DM0"]:
            esquema = linha.get("S", esquema)
            if esquema is None or len(esquema) != len(campos):
                raise ValueError("Esquema DSR invalido")
            valores = iter(linha.get("C", []))
            repetidos, nulos = linha.get("R", 0), linha.get("Ø", 0)
            crus = [anterior[i] if repetidos & (1 << i) else None
                    if nulos & (1 << i) else next(valores)
                    for i in range(len(esquema))]
            # DSR usa indice inteiro OU literal, inclusive na mesma coluna.
            decodificados = [dataset["ValueDicts"][c["DN"]][v]
                if c.get("DN") and isinstance(v, int) else v
                for c, v in zip(esquema, crus)]
            registros.append(dict(zip(campos, decodificados)))
            anterior = crus
    return registros


def consulta(modelo):
    selecoes = [{"Column": {"Expression": {"SourceRef": {"Source": "t"}},
                             "Property": campo},
                 "Name": ENTIDADE + "." + campo} for campo in CAMPOS]
    comando = {"Query": {"Version": 2,
        "From": [{"Name": "t", "Entity": ENTIDADE, "Type": 0}], "Select": selecoes},
        "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(CAMPOS)))}]},
                    "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 10000}}},
                    "Version": 1}, "ExecutionMetricsKind": 1}
    return {"version": "1.0.0", "queries": [{"Query": {"Commands": [
        {"SemanticQueryDataShapeCommand": comando}]}}], "cancelQueries": [], "modelId": modelo}


class ColetorCETSP(CadastroPublicado):
    locals().update(cadastro("CET Sao Paulo - Fiscalizacao eletronica", "SP",
        "https://www.cetsp.com.br/consultas/fiscalizacao-eletronica-do-transito.aspx",
        "São Paulo", "json"))

    def carregar(self, origem):
        # O tick passa resolver_url() (pagina HTML), o CLI passa None.
        if origem and origem != self.PAGINA:
            if os.path.isfile(origem):
                with open(origem, "rb") as arquivo:
                    resposta = arquivo.read()
            else:
                resposta = http.baixar(origem)[0]
            return self._resposta(resposta)
        pagina = http.baixar(self.PAGINA)[0].decode("utf-8", "replace")
        links = re.findall(r'https://app\.powerbi\.com/view\?[^\s"<>]+', html.unescape(pagina))
        if not links:
            raise ValueError("CET nao publicou link do painel")
        parametro = parse_qs(urlsplit(links[0]).query)["r"][0]
        referencia = json.loads(base64.urlsafe_b64decode(parametro + "=" * (-len(parametro) % 4)))
        chave = referencia["k"]
        if not re.fullmatch(r"[a-fA-F0-9-]{36}", chave):
            raise ValueError("Identificador publico de painel invalido")
        headers = {"X-PowerBI-ResourceKey": chave, "Content-Type": "application/json"}
        metadados = json_publico(http.baixar(API + "/public/reports/" + chave +
                                "/modelsAndExploration", headers=headers)[0])
        modelo = metadados["models"][0]["id"]
        resposta = http.baixar(API + "/public/reports/querydata?synchronous=true",
            method="POST", data=json.dumps(consulta(modelo), ensure_ascii=False).encode(),
            headers=headers)[0]
        # O artefato e a resposta original, nao uma reserializacao dos pontos.
        return self._resposta(resposta)

    def _resposta(self, resposta):
        registros = self.extrair_registros(resposta)
        if not registros:
            raise ValueError("CET nao devolveu equipamentos metrologicos")
        comprimida = resposta.startswith(b"\x1f\x8b")
        return resposta, ".json.gz" if comprimida else ".json", (
            "application/gzip" if comprimida else "application/json"), registros

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for r in decodificar_dsr(json_publico(conteudo)):
            if str(r["METROLÓGICO"]).strip().upper() != "SIM":
                continue
            serie = str(r["NÚMERO DE SÉRIE"] or "").strip()
            velocidades = re.findall(r"\d+", r["VELOCIDADE"] or "")
            inicio = r["ATIVAÇÃO"]
            ativado = inicio is not None and datetime.fromtimestamp(
                inicio / 1000, timezone.utc) <= datetime.now(timezone.utc)
            situacao = "inativo" if r["DESATIVAÇÃO"] is not None else "ativo" if ativado else None
            registros.append(dict(r, identificador=str(r["ID"]),
                endereco=r["DESCRIÇÃO DO LOCAL"], latitude=nz.to_float(r["LATITUDE"]),
                longitude=nz.to_float(r["LONGITUDE"]), situacao=situacao,
                numero_serie=serie if re.fullmatch(r"[A-Za-z0-9]+", serie) else None,
                # Varias velocidades por faixa/categoria ficam no original.
                velocidade_geral=int(velocidades[0]) if len(set(velocidades)) == 1 else None))
        return registros
