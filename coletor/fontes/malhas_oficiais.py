"""Referências quilométricas publicadas pela IDE-Sisema e pelo DNIT."""
from collections import defaultdict
import io
from itertools import groupby
import json
import math
import re
import struct
from urllib.parse import urlencode
from zipfile import ZipFile

from coletor import http
from core.geo import haversine_m

IDE_MG = "https://geoserver.meioambiente.mg.gov.br/IDE/ows"
DNIT_SNV = "https://www.gov.br/dnit/pt-br/assuntos/atlas-e-mapas/pnv-e-snv"


def rodovia(valor):
    return re.sub(r"[-\s]", "", str(valor or "").upper())


def _medidas_da_linha(pontos, inicio, fim):
    distancias = [0.0]
    for a, b in zip(pontos, pontos[1:]):
        distancias.append(distancias[-1] + haversine_m(*a, *b))
    if not distancias[-1]:
        return []
    return [(inicio + d / distancias[-1] * (fim - inicio), p)
            for p, d in zip(pontos, distancias)]


def malha_mg(documento):
    linhas = defaultdict(list)
    for feicao in documento["features"]:
        props = feicao["properties"]
        codigo = str(props.get("codigo_sre") or props.get("codigo_snv") or "")
        match = re.fullmatch(r"(\d{3})EMG\d+(?:-\d+)?", codigo)
        geometria = feicao.get("geometry") or {}
        inicio, fim = props.get("quilometra"), props.get("quilometr0")
        if not match or not isinstance(inicio, (int, float)) or not isinstance(fim, (int, float)) or inicio == fim:
            continue
        if geometria.get("type") == "LineString":
            partes = [geometria["coordinates"]]
        elif geometria.get("type") == "MultiLineString":
            partes = geometria["coordinates"]
        else:
            continue
        if any(a[-1] != b[0] for a, b in zip(partes, partes[1:])):
            continue  # partes descontínuas não definem a fração do km
        pontos = [(p[1], p[0]) for parte in partes for p in parte]
        linha = _medidas_da_linha(pontos, inicio, fim)
        if linha:
            linhas[("MG", "MG" + match[1])].append(linha if inicio < fim else linha[::-1])
    return linhas


def baixar_mg(rodovias):
    numeros = sorted({v[2:].zfill(3) for v in map(rodovia, rodovias) if re.fullmatch(r"MG\d{1,3}", v)})
    features = []
    for inicio in range(0, len(numeros), 15):
        lote = numeros[inicio:inicio + 15]
        filtro = " OR ".join(f"codigo_sre LIKE '{codigo}EMG%'" for codigo in lote)
        params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                  "typeNames": "IDE:ide_0401_mg_rodovias_lin", "srsName": "EPSG:4326",
                  "sortBy": "id", "outputFormat": "application/json", "count": 100,
                  "propertyName": "id,codigo_sre,codigo_snv,quilometra,quilometr0,geom",
                  "CQL_FILTER": filtro}
        offset = 0
        while True:
            parametros = dict(params, startIndex=offset)
            pagina = json.loads(http.baixar(IDE_MG + "?" + urlencode(parametros))[0])
            total = pagina["numberMatched"]
            lote_feicoes = pagina["features"]
            features.extend(lote_feicoes)
            offset += len(lote_feicoes)
            if offset == total:
                break
            if not lote_feicoes or offset > total:
                raise ValueError("A IDE-Sisema devolveu uma malha incompleta")
    if len({f["id"] for f in features}) != len(features):
        raise ValueError("A IDE-Sisema repetiu feições na paginação")
    return json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")).encode()


def _codigos_dbf(corpo):
    quantidade, cabecalho, largura = struct.unpack_from("<IHH", corpo, 4)
    offset = 1
    campo = None
    for i in range(32, cabecalho - 1, 32):
        largura_campo = corpo[i + 16]
        if corpo[i:i + 11].split(b"\0", 1)[0].lower().startswith(b"vl_codigo"):
            campo = slice(offset, offset + largura_campo)
            break
        offset += largura_campo
    if campo is None or cabecalho + quantidade * largura > len(corpo):
        raise ValueError("O DBF do SNV não contém o código da rota")
    for i in range(quantidade):
        inicio = cabecalho + i * largura
        yield corpo[inicio:inicio + largura][campo].decode("ascii", "replace").strip() if corpo[inicio] == 32 else ""


def _linhas_shp(corpo):
    if len(corpo) < 100 or struct.unpack_from(">i", corpo)[0] != 9994:
        raise ValueError("Cabeçalho SHP inválido")
    arquivo = io.BytesIO(corpo)
    arquivo.seek(100)
    while cabecalho := arquivo.read(8):
        _, tamanho = struct.unpack(">ii", cabecalho)
        if tamanho < 2:
            raise ValueError("Registro SHP inválido")
        registro = arquivo.read(tamanho * 2)
        if len(registro) != tamanho * 2:
            raise ValueError("Registro SHP incompleto")
        yield registro


def _partes_medidas(registro):
    tipo = struct.unpack_from("<i", registro)[0]
    if tipo not in (13, 23):  # PolyLineZ com M ou PolyLineM
        return
    partes, pontos = struct.unpack_from("<ii", registro, 36)
    if not 0 < partes <= pontos:
        raise ValueError("Partes inválidas no SNV")
    vertices_offset = 44 + 4 * partes
    medidas_offset = vertices_offset + 16 * pontos + (16 + 8 * pontos if tipo == 13 else 0) + 16
    if len(registro) < medidas_offset + 8 * pontos:
        return
    indices = (*struct.unpack_from(f"<{partes}i", registro, 44), pontos)
    if indices[0] != 0 or any(a >= b for a, b in zip(indices, indices[1:])):
        raise ValueError("Índice de partes inválido no SNV")
    for a, b in zip(indices, indices[1:]):
        linha = []
        for i in range(a, b):
            lon, lat = struct.unpack_from("<dd", registro, vertices_offset + 16 * i)
            km = struct.unpack_from("<d", registro, medidas_offset + 8 * i)[0]
            if not (0 <= km <= 10000 and -35 <= lat <= 6 and -75 <= lon <= -30):
                linha = []
                break
            linha.append((km, (lat, lon)))
        if len(linha) < 2:
            continue
        if linha[0][0] > linha[-1][0]:
            linha.reverse()
        if all(x[0] <= y[0] for x, y in zip(linha, linha[1:])):
            yield linha


def malha_snv(corpo):
    linhas = defaultdict(list)
    with ZipFile(io.BytesIO(corpo)) as pacote:
        shps = [n for n in pacote.namelist() if n.lower().endswith(".shp")]
        if len(shps) != 1:
            raise ValueError("Informe o ZIP oficial das rotas SNV, com uma única camada")
        arquivos = {n.lower(): n for n in pacote.namelist()}
        shp = shps[0]
        dbf = arquivos.get(shp[:-4].lower() + ".dbf")
        if dbf is None or sum(pacote.getinfo(n).file_size for n in (shp, dbf)) > 300 * 1024 * 1024:
            raise ValueError("Arquivos da malha SNV ausentes ou maiores que o limite")
        for codigo, registro in zip(_codigos_dbf(pacote.read(dbf)), _linhas_shp(pacote.read(shp)), strict=True):
            match = re.match(r"^(\d{3})B([A-Z]{2})", codigo)
            if match:
                linhas[(match[2], "BR" + match[1])].extend(_partes_medidas(registro))
    if not linhas:
        raise ValueError("A malha do DNIT não trouxe rotas com medidas quilométricas")
    return linhas


def _interpolar(linha, km):
    for (a, p), (b, q) in zip(linha, linha[1:]):
        if a <= km <= b and b > a:
            ratio = (km - a) / (b - a)
            return tuple(round(x + (y - x) * ratio, 7) for x, y in zip(p, q))
    return None


def geometria(linhas, inicio, fim):
    if inicio is None or fim is None or not (math.isfinite(inicio) and math.isfinite(fim)) or inicio > fim:
        return None
    opcoes = set()
    for linha in linhas:
        if not linha[0][0] <= inicio <= fim <= linha[-1][0]:
            continue
        a, b = _interpolar(linha, inicio), _interpolar(linha, fim)
        if a is None or b is None:
            continue
        meio = tuple(p for km, p in linha if inicio < km < fim)
        opcoes.add(tuple(p for p, _ in groupby((a, *meio, b))))
    return next(iter(opcoes)) if len(opcoes) == 1 else None
