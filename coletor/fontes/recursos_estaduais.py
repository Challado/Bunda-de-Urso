"""Fontes complementares publicadas pela ARTESP e pelo Detran-DF."""
import json
from pathlib import Path
from urllib.parse import urlencode

from coletor import http
from coletor.fontes import normalizacao as nz, planilha
from coletor.fontes.cadastros_publicos import CadastroPublicado, cadastro
from coletor.fontes.dersp import MIME_XLSX
from coletor.fontes.detran_df import ColetorDetranDF


class ColetorArtesp(CadastroPublicado):
    PAGINA = "https://dadosabertos.artesp.sp.gov.br/dataset/491d79c5-ee09-4fe8-a3ce-1b425fe60bbe"
    locals().update(cadastro("ARTESP - Medidores de velocidade em rodovias concedidas", "SP", PAGINA,
        formato="xlsx", url=PAGINA + "/resource/8b3212ff-1647-42ad-8a45-39e9934c92e1/download/recursos.xlsx"))

    def carregar(self, origem):
        corpo = Path(origem).read_bytes() if origem and Path(origem).is_file() else http.baixar(origem or self.URL)[0]
        linhas = planilha.dicts_de_linhas(planilha.ler_xlsx(corpo))
        registros = []
        for linha in linhas:
            tipo = nz.normalizar_nome_texto(linha.get("Desc_Componente")).lower()
            if not tipo.startswith(("medidor de velocidade (radar fixo)", "radar fixo", "lombada eletr")):
                continue
            id_local = linha.get("ID")
            if not id_local:
                continue
            km = str(linha.get("Localizacao") or "").lower().removeprefix("km").strip().replace("+", ".")
            estado = nz.normalizar_nome_texto(linha.get("Cod_Status")).lower()
            situacao = {"ativo": "ativo", "inativo": "inativo", "desativado": "inativo"}.get(estado)
            if nz.normalizar_nome_texto(linha.get("Em_Implantacao")).lower() == "sim":
                situacao = "em_instalacao"
            registros.append(dict(linha, identificador=id_local, latitude=nz.to_float(linha.get("Latitude")),
                longitude=nz.to_float(linha.get("Longitude")), km=nz.to_float(km),
                via_codigo=linha.get("Rodovia"), municipio_nome=linha.get("Municipio"), situacao=situacao,
                sentido_original=linha.get("Sentido"), endereco=linha.get("Localizacao")))
        if not registros:
            raise ValueError("A planilha da ARTESP não trouxe medidores reconhecidos")
        return corpo, ".xlsx", MIME_XLSX, registros


class ColetorDFArcGIS(CadastroPublicado):
    URL = "https://services.arcgis.com/4CZwpdWHGNPLU7QQ/arcgis/rest/services/Base_DETRAN/FeatureServer"
    locals().update(cadastro("Detran-DF - ArcGIS histórico", "DF", ColetorDetranDF.URL_PAGINA,
                             formato="json", url=URL))
    FONTE = dict(ColetorDetranDF.FONTE)
    RECURSO = dict(RECURSO, nome="ArcGIS Base_DETRAN (cadastro histórico)")
    CAMPOS = "OBJECTID,Velocidade,Validacao,DataInstalacao,ra_num,nome"

    @classmethod
    def _baixar_camada(cls, base, camada):
        endpoint = base.rstrip("/") + f"/{camada}/query?"

        def consultar(**params):
            corpo = http.baixar(endpoint + urlencode({"f": "json", **params}))[0]
            obj = json.loads(corpo)
            if "error" in obj:
                raise ValueError("Erro ao consultar Base_DETRAN")
            return obj

        campos = cls.CAMPOS + (",Tipo,VEL_NORM" if camada == 1 else "")
        ids = sorted(consultar(where="1=1", returnIdsOnly="true")["objectIds"])
        features = []
        for inicio in range(0, len(ids), 500):
            lote = ids[inicio:inicio + 500]
            obj = consultar(where=f"OBJECTID >= {lote[0]} AND OBJECTID <= {lote[-1]}",
                            outFields=campos, outSR=4326)
            if {f["attributes"]["OBJECTID"] for f in obj["features"]} != set(lote):
                raise ValueError("A camada do Detran-DF devolveu uma lista incompleta")
            features.extend(sorted(obj["features"], key=lambda f: f["attributes"]["OBJECTID"]))
        return features

    def carregar(self, origem):
        if origem and Path(origem).is_file():
            corpo = Path(origem).read_bytes()
            camadas = json.loads(corpo)
        else:
            camadas = {str(camada): self._baixar_camada(origem or self.URL, camada) for camada in (1, 2)}
            corpo = json.dumps(camadas, ensure_ascii=False, separators=(",", ":")).encode()
        registros = []
        for camada, features in camadas.items():
            for feature in features:
                d = feature["attributes"]
                posicao = feature.get("geometry") or {}
                registros.append(dict(d, identificador=f'arcgis-{camada}-{d["OBJECTID"]}',
                    latitude=nz.to_float(posicao.get("y")), longitude=nz.to_float(posicao.get("x")),
                    velocidade_geral=nz.to_float(d.get("VEL_NORM") or d.get("Velocidade")),
                    endereco=d.get("nome")))
        if not registros:
            raise ValueError("O ArcGIS histórico do Detran-DF não trouxe equipamentos")
        return corpo, ".json", "application/json", registros
