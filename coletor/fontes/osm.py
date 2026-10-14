# -*- coding: utf-8 -*-
"""Fonte F15 - OpenStreetMap / Overpass (COMPLEMENTAR, NAO OFICIAL).

O OSM e uma base colaborativa (licenca ODbL 1.0): serve para SUGERIR pontos
candidatos e complementar posicao com qualidade indicada, nunca como
confirmacao governamental (spec 17.2 / 17.4).  Este coletor NAO faz parte da
lista de fontes oficiais e seus registros saem marcados como
"nao_confirmado".

Evidencia coletada em 10/10/2026 (POST data=<query> em
https://overpass-api.de/api/interpreter, User-Agent "RadarBrasil/1.0",
bbox de teste de Sao Paulo -23.70,-46.80,-23.45,-46.45):

  HTTP 200, 1064 elementos (1010 node, 54 relation).  Tags observadas:
    highway=speed_camera ................. 999
    type=enforcement + enforcement=maxspeed .. 31
    type=enforcement + enforcement=traffic_signals .. 23
    highway=speed_camera + enforcement=red_light_camera .. 9
    highway=speed_camera + enforcement=traffic_signals .. 1
    highway=speed_camera + enforcement=maxspeed ..... 1
  Cameras de semaforo / luz vermelha (red_light_camera, traffic_signals) NAO
  sao radares de velocidade e por isso sao descartadas (spec 17.2).

Regras implementadas:
  - id OSM guardado JUNTO com o tipo de elemento: "osm:<node|way|relation>/<id>"
    (ids de tipos diferentes nunca colidem) + versao/data quando houver;
  - respeita rate limit: backoff exponencial e Retry-After em 429/5xx;
  - area limitada a uma bbox (nao faz consulta global);
  - atribuicao ODbL nos metadados (FONTE.licenca + campo ATRIBUICAO).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from core import config
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

ATRIBUICAO = "(c) OpenStreetMap contributors, ODbL 1.0"
LICENCA = "ODbL 1.0"

# Termos de enforcement que NAO sao fiscalizacao de velocidade.
_ENFORCEMENT_NAO_VELOCIDADE = (
    "traffic_signals", "red_light", "red_light_camera", "access",
    "plate", "alpr", "anpr", "bus_lane", "toll", "weight",
)
# Termos de enforcement que sao fiscalizacao de velocidade.
_ENFORCEMENT_VELOCIDADE = ("maxspeed", "average_speed", "speed")


def _espera_backoff(tentativa, retry_after=None):
    """Segundos de espera: Retry-After se valido, senao 2^n com teto."""
    if retry_after is not None:
        try:
            return max(0.0, float(str(retry_after).strip()))
        except ValueError:
            pass
    return min(60.0, 2.0 ** max(0, tentativa - 1))


class ColetorOSM(ColetorBase):

    FONTE = {
        "nome": "OpenStreetMap / Overpass - radares de velocidade (complementar)",
        "organizacao": "OpenStreetMap contributors",
        "tipo_organizacao": "outro",
        "esfera": "outra",            # esfera != natureza: base colaborativa
        "natureza": "comunitaria",    # NAO oficial (spec 17.2)
        "url_institucional": "https://www.openstreetmap.org/",
        "documentacao_url": "https://wiki.openstreetmap.org/wiki/Overpass_API",
        "licenca": LICENCA,
        "licenca_codigo": "odbl",
        "atribuicao": ATRIBUICAO,
        "periodicidade_declarada": "continuada",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "Overpass highway=speed_camera + type=enforcement",
        "url_recurso": "https://overpass-api.de/api/interpreter",
        "formato_origem": "json",
        "periodicidade_segundos": 604800,   # ~7 dias
        "status_integracao": "ok",
        "dicionario_url": "https://wiki.openstreetmap.org/wiki/Key:highway",
    }

    ENDPOINT = RECURSO["url_recurso"]
    TENTATIVAS = 3
    # bbox de teste (Sao Paulo).  Nao fazer consulta global (spec 17.5).
    BBOX_TESTE = (-23.70, -46.80, -23.45, -46.45)

    @classmethod
    def resolver_url(cls):
        return cls.ENDPOINT

    # -- consulta ----------------------------------------------------------
    def montar_query(self, bbox=None):
        sul, oeste, norte, leste = bbox or self.BBOX_TESTE
        area = "(%.2f,%.2f,%.2f,%.2f)" % (sul, oeste, norte, leste)
        return (
            "[out:json][timeout:25];\n"
            "(\n"
            "  node[\"highway\"=\"speed_camera\"]%s;\n"
            "  way[\"highway\"=\"speed_camera\"]%s;\n"
            "  relation[\"highway\"=\"speed_camera\"]%s;\n"
            "  relation[\"type\"=\"enforcement\"]%s;\n"
            ");\n"
            "out meta center;\n" % (area, area, area, area)
        )

    def _consultar_overpass(self, query, bbox=None):
        """POST na Overpass com backoff/Retry-After (rate limit)."""
        corpo = urllib.parse.urlencode({"data": query}).encode("utf-8")
        ultimo_erro = None
        for tentativa in range(1, self.TENTATIVAS + 1):
            req = urllib.request.Request(
                self.ENDPOINT, data=corpo,
                headers={"User-Agent": config.USER_AGENT,
                         "Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(
                        req, timeout=config.DEFAULT_TIMEOUT) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                ultimo_erro = exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    if tentativa == self.TENTATIVAS:
                        raise
                    time.sleep(_espera_backoff(
                        tentativa, exc.headers.get("Retry-After")))
                    continue
                raise
        raise ultimo_erro                                  # pragma: no cover

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        """origem: arquivo local (json) ou None/endpoint (consulta Overpass)."""
        if origem and self._e_arquivo(origem):
            conteudo = self._ler(origem)
        elif origem and str(origem).startswith("http") \
                and not str(origem).rstrip("/").endswith("interpreter"):
            conteudo = self._ler(origem)
        else:
            conteudo = self._consultar_overpass(self.montar_query())
        elementos = self._parse(conteudo)
        return conteudo, ".json", "application/json", elementos

    @staticmethod
    def _e_arquivo(ref):
        import os
        return os.path.exists(ref)

    def _ler(self, ref):
        import os
        if os.path.exists(ref):
            with open(ref, "rb") as f:
                return f.read()
        req = urllib.request.Request(ref,
                                     headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(
                req, timeout=config.DEFAULT_TIMEOUT) as resp:
            return resp.read()

    @staticmethod
    def _parse(conteudo):
        dados = json.loads(conteudo.decode("utf-8-sig"))
        if isinstance(dados, dict):
            return dados.get("elements", [])
        return dados

    def identificador(self, raw):
        return self._chave(raw)

    @staticmethod
    def _chave(raw):
        tipo = (raw.get("type") or "").strip()
        return "osm:%s/%s" % (tipo, raw.get("id"))

    # -- classificacao -----------------------------------------------------
    @staticmethod
    def _tipo_osm(tags):
        """Retorna o rotulo OSM aceito, ou None se NAO for velocidade."""
        tags = tags or {}
        hw = str(tags.get("highway") or "").strip().lower()
        tipo = str(tags.get("type") or "").strip().lower()
        enf = str(tags.get("enforcement") or "").strip().lower()
        # câmera de placa (ALPR/ANPR) nunca e radar de velocidade
        for chave in ("camera:type", "surveillance:type", "surveillance"):
            if str(tags.get(chave) or "").strip().lower() in (
                    "alpr", "anpr", "plate", "plate_reader"):
                return None
        if hw == "speed_camera":
            if any(t in enf for t in _ENFORCEMENT_NAO_VELOCIDADE):
                return None            # semaforo/luz vermelha, nao velocidade
            return "speed_camera"
        if tipo == "enforcement":
            if any(enf == t or enf.startswith(t)
                   for t in _ENFORCEMENT_VELOCIDADE):
                return "enforcement:%s" % (enf or "velocidade")
        return None

    def _coordenadas(self, raw):
        if raw.get("type") == "node":
            return nz.to_float(raw.get("lat")), nz.to_float(raw.get("lon")), \
                   "estimada"
        centro = raw.get("center") or {}
        return (nz.to_float(centro.get("lat")),
                nz.to_float(centro.get("lon")), "inferida")

    # -- normalizar --------------------------------------------------------
    def normalizar(self, idx, raw):
        tags = raw.get("tags") or {}
        tipo_osm = self._tipo_osm(tags)
        if tipo_osm is None:
            # NAO e fiscalizacao de velocidade (semaforo/ALPR/surveillance):
            # fica de fora do cadastro; o payload bruto permanece em
            # REGISTRO_FONTE para auditoria.
            return None
        # pode estar presente, mas dado colaborativo: nao tratamos como oficial
        for chave in ("camera:type", "surveillance:type"):
            if tags.get(chave):
                return None
        lat, lon, qualidade = self._coordenadas(raw)
        if lat is None or lon is None:
            return None
        return {
            "procedencia": "comunitaria",
            "natureza_fonte": "comunitaria",
            # NUNCA apresentar OSM como confirmado por orgao oficial
            "confiabilidade": "nao_confirmada",
            "tipo_registro": "ponto_fiscalizacao",
            "identificador": self._chave(raw),
            "tipo_identificador": "outro",
            "osm_tipo_elemento": raw.get("type"),
            "osm_id": raw.get("id"),
            "osm_versao": raw.get("version"),
            "osm_timestamp": raw.get("timestamp"),
            "osm_tipo": tipo_osm,
            "osm_tags": dict(tags),
            "latitude": lat,
            "longitude": lon,
            "qualidade": qualidade,
            "metodo_obtencao": "OpenStreetMap/Overpass (%s/%s)"
                               % (raw.get("type"), raw.get("id")),
            "licenca": LICENCA,
            "atribuicao": ATRIBUICAO,
            # sem evidencia oficial: nao inferimos tipo/situacao/velocidade
            "tipo_radar": "desconhecido",
            "situacao": None,
            "velocidade_osm": nz.to_float(tags.get("maxspeed")),
            "observacoes": ("origem comunitaria OSM; nao confirmado por orgao "
                            "oficial; highway=%s" % (tags.get("highway")
                                                     or tags.get("type"))),
        }
