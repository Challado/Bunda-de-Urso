# -*- coding: utf-8 -*-
"""Fonte F01 - INMETRO / PSIE, consulta nacional metrologica.

Portal:   https://servicos.rbmlq.gov.br/
Consulta: https://servicos.rbmlq.gov.br/Instrumento  (HTML + reCAPTCHA)
Orientacao oficial (Inmetro):
  https://www.gov.br/inmetro/pt-br/acesso-a-informacao/perguntas-frequentes/
  metrologia-legal/medidor-de-velocidade-radar/como-obter-acesso-ao-
  certificado-de-verificacao-dos-medidores-de-velocidade
Catalogo dados.gov.br:
  https://dados.gov.br/dados/conjuntos-dados/portal-de-servicos-do-inmetro-nos-estados-psie

------------------------------------------------------------------------------
RECONHECIMENTO (2026-10-10) - EVIDENCIA CRUA
------------------------------------------------------------------------------
A pagina /Instrumento usa POST + reCAPTCHA (input hidden CaptchaResult e
"grecaptcha.render('dvCaptcha', ...)"), portanto a consulta HTML NAO e
automatizavel de forma legitima.

O portal, porem, publica um CONJUNTO DE DADOS ABERTOS em arquivo ESTATICO
por UF, SEM autenticacao e SEM CAPTCHA:

  GET https://servicos.rbmlq.gov.br/dados-abertos/{UF}/medidores.json

  $ curl -sSI .../dados-abertos/AC/medidores.json
  HTTP/1.1 200 OK
  Content-Type: application/json
  Last-Modified: Thu, 01 Oct 2026 00:30:14 GMT
  Server: Microsoft-IIS/7.5

  $ curl -sS .../dados-abertos/AC/medidores.json | head -c 120
  [ { "SiglaUf": "AC", "Estado": "Acre", "Municipio": "RIO BRANCO", ...

Cobertura testada (2026-10-10): 26 de 27 UFs respondem 200 com JSON valido
(AC..TO); DF responde 404 (nao ha arquivo proprio). Total observado no dia:
35.915 registros. O endpoint NAO precisou de contornar CAPTCHA algum.

robots.txt do host: "Crawl-delay: 120"; "Disallow: /Instrumento/*" e
"Allow: /Instrumento". O caminho /dados-abertos/ nao esta bloqueado, mas o
crawl-delay e respeitado (poucas requisicoes, sem varredura massiva).

ATENCAO (spec 2 [F01] e 17.1 [G01]): a URL acima era um "chute" de terceiro
NAO VALIDADO. Foi VALIDADA nesta coleta como recurso publico efetivo.

------------------------------------------------------------------------------
MODELO DO ARQUIVO (por registro = um INSTRUMENTO verificado em um local)
------------------------------------------------------------------------------
{
  "SiglaUf": "AC", "Estado": "Acre", "Municipio": "RIO BRANCO",
  "LocalVerificacao": "BR 364 KM 123,830",
  "DataUltimaVerificacao": "04/08/2026", "DataValidade": "03/08/2027",
  "UltimoResultado": "Aprovado", "TipoMedidor": "Fixo",
  "Faixas":    [{"NumeroFaixa","NumeroInmetro","NumeroSerie","Sentido",
                 "VelocidadeNominal"}, ...],
  "Historico": [{"NumeroCertificado","NumeroEnsaio","Ano","DataLaudo",
                 "DataValidade","TipoServico","Resultado"}, ...],
  "Proprietario": {"Nome","Municipio","Estado"}
}

NAO ha latitude/longitude nem via/km estruturados: LocalVerificacao e texto
livre. Por isso a posicao e exposta como NAO CONFIRMADA (sem POSICAO_GEOGRAFICA).

REGRA G01 / spec 17.4.5: o MESMO NumeroSerie repetido em varias faixas e UM
equipamento com MULTIPLAS faixas, NUNCA varios instrumentos. Aqui a fonte
agrupa por (SiglaUf, NumeroInmetro, NumeroSerie): as faixas e o historico de
verificacoes sao consolidados no mesmo instrumento.

LIMITACAO CONHECIDA: a camada compartilhada coletor.fontes.normalizacao
mapeia UM registro normalizado -> UM ponto + UM equipamento + UMA faixa. O
detalhamento de varias faixas e do historico metrologico NAO e persistido
como entidades proprias por essa camada; ele permanece integral no payload
bruto (REGISTRO_FONTE) e resumido em `observacoes`. Nao se duplica
certificado por faixa.
"""
import datetime
import json
import os
import re

from core import config
from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz

UFS_BR = ("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS "
          "RO RR SC SP SE TO").split()

#: Endpoint de dados abertos (arquivo estatico JSON por UF).
URL_TEMPLATE = ("https://servicos.rbmlq.gov.br/dados-abertos/{uf}/medidores.json")
URL_PORTAL = "https://servicos.rbmlq.gov.br/"


def _eh_uf(valor):
    return (isinstance(valor, str) and len(valor) == 2
            and valor.strip().upper() in UFS_BR)


def _data_br(valor):
    """Converte 'dd/mm/aaaa' em datetime.date; None se invalida."""
    if not valor or not isinstance(valor, str):
        return None
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$", valor)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _sentido_lista(faixas):
    """Sentidos normalizados (sem repeticao) presentes nas faixas."""
    vistos = []
    for f in faixas:
        s = nz.normalizar_sentido(f.get("Sentido"))
        if s and s not in vistos:
            vistos.append(s)
    return vistos


def _velocidades(faixas):
    """Conjunto (ordenado) de velocidades nominais distintas das faixas."""
    vals = []
    for f in faixas:
        v = nz.to_float(f.get("VelocidadeNominal"))
        if v is not None and v not in vals:
            vals.append(v)
    return vals


class ColetorINMETRO(ColetorBase):

    FONTE = {
        "nome": "INMETRO / PSIE - Instrumentos verificados (medidores de velocidade)",
        "organizacao": "Instituto Nacional de Metrologia, Qualidade e Tecnologia",
        "tipo_organizacao": "orgao_publico",
        "esfera": "federal",
        "natureza": "oficial",
        "url_institucional": "https://www.gov.br/inmetro/pt-br",
        "documentacao_url": ("https://dados.gov.br/dados/conjuntos-dados/"
                             "portal-de-servicos-do-inmetro-nos-estados-psie"),
        "licenca": "dados abertos governamentais",
        "periodicidade_declarada": "diaria/mensal (Last-Modified por UF)",
        "situacao": "ativa",
    }
    RECURSO = {
        "nome": "medidores.json (dados abertos por UF)",
        "url_recurso": URL_TEMPLATE,
        "formato_origem": "json",
        "dicionario_url": ("https://dados.gov.br/dados/conjuntos-dados/"
                           "portal-de-servicos-do-inmetro-nos-estados-psie"),
        "periodicidade_segundos": 86400,   # ~1 dia (arquivo atualizado periodicamente)
        "status_integracao": "ok",
    }

    # UFs com arquivo proprio de dados abertos (DF responde 404)
    UFS_TODAS = ("AC", "AL", "AP", "AM", "BA", "CE", "ES", "GO", "MA",
                 "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ",
                 "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")

    # -- resolucao de URL -------------------------------------------------
    @classmethod
    def resolver_url(cls, uf=None):
        """URL do arquivo de dados abertos.

        uf: sigla (ex.: 'AC'). Sem uf, devolve o template {uf} (nao inventa
        uma UF especifica). A URL e ESTAVEL por UF (nao ha versionamento por
        edicao como no CKAN), por isso nao ha 'fallback' a um arquivo datado.
        """
        if uf is None:
            return URL_TEMPLATE
        u = str(uf).strip().upper()
        if not _eh_uf(u):
            raise ValueError("UF invalida: %r" % (uf,))
        return URL_TEMPLATE.format(uf=u)

    # -- carregar ----------------------------------------------------------
    def carregar(self, origem):
        """origem: caminho local | URL | sigla de UF | "TODAS".

        "TODAS" baixa todas as UFs disponiveis (uma execucao so).
        Retorna (bytes, ext, mime, registros), onde `registros` e a lista de
        INSTRUMENTOS (ja agrupados pela regra G01/17.4.5), nao as faixas.
        """
        if isinstance(origem, str) and origem.strip().upper() in ("TODAS",
                                                                  "*", "ALL"):
            return self._carregar_todas()
        if origem and os.path.exists(origem):
            with open(origem, "rb") as f:
                conteudo = f.read()
            ext = os.path.splitext(origem)[1].lower() or ".json"
        else:
            url = self._url_de(origem)
            conteudo = self._baixar(url)
            ext = ".json"
        ##-- BUNDITA DE URSO #{27} -- A coleta TODAS arquiva documentos JSON concatenados, mas o leitor exigia documento unico e falhava ao restaurar o bruto nacional. ##
        registros = []
        for bruto in self._documentos_json(conteudo):
            if isinstance(bruto, dict):
                for chave in ("dados", "data", "records", "items", "medidores"):
                    if isinstance(bruto.get(chave), list):
                        bruto = bruto[chave]
                        break
                else:
                    bruto = [bruto]
            if not isinstance(bruto, list):
                raise ValueError("estrutura inesperada em medidores.json")
            # A coleta nacional agrupa cada resposta estadual separadamente.
            registros.extend(self.agrupar_instrumentos(bruto))
        return conteudo, ext, "application/json", registros

    @staticmethod
    def _documentos_json(conteudo):
        """Le JSON unico ou fluxo nacional legado sem modificar os bytes.

        Valida ate o fim: um sufixo corrompido impede importar apenas o prefixo.
        Cada resposta pode ter BOM UTF-8, como nos arquivos estaduais isolados.
        """
        try:
            texto = conteudo.decode("utf-8-sig")
            decoder = json.JSONDecoder()
            documentos, inicio = [], 0
            while inicio < len(texto):
                while inicio < len(texto) and texto[inicio] in " \t\r\n\ufeff":
                    inicio += 1
                if inicio == len(texto):
                    break
                documento, inicio = decoder.raw_decode(texto, inicio)
                documentos.append(documento)
            if not documentos:
                raise ValueError("arquivo vazio")
            return documentos
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("resposta de dados abertos nao e JSON valido: %s" % exc) from exc

    def _carregar_todas(self):
        """Baixa todas as UFs (uma por vez, respeitando o host) e combina.

        DF nao publica arquivo proprio -> fica de fora. Uma UF que falhe
        nao derruba as outras.
        """
        import time
        partes = []
        registros = []
        for uf in self.UFS_TODAS:
            try:
                conteudo = self._baixar(self.resolver_url(uf))
                bruto = json.loads(conteudo.decode("utf-8-sig"))
            except Exception:                                  # noqa: BLE001
                continue
            if not isinstance(bruto, list):
                continue
            partes.append(conteudo)
            registros.extend(self.agrupar_instrumentos(bruto))
            time.sleep(1.0)          # cortesia com o host (Crawl-delay)
        return b"\n".join(partes), ".json", "application/json", registros

    def _url_de(self, origem):
        if origem is None:
            raise ValueError("informe uma UF (ex.: 'AC'), uma URL ou um arquivo")
        if isinstance(origem, str) and origem.lower().startswith(("http://",
                                                                  "https://")):
            return origem
        if _eh_uf(origem):
            return self.resolver_url(origem)
        # ultimo recurso: trata como URL mesmo assim
        return origem

    def _baixar(self, url):
        corpo, _headers, _url_final = http.baixar(url)
        return corpo

    # -- agrupamento (regra G01 / 17.4.5) ---------------------------------
    @classmethod
    def agrupar_instrumentos(cls, registros_brutos):
        """Consolida registros por instrumento fisico.

        - Cada registro do arquivo pode conter varias faixas do MESMO
          instrumento (mesmo NumeroSerie) -> vira UM instrumento.
        - Um registro tambem pode conter faixas de SERIAIS DIFERENTES ->
          vira mais de um instrumento (um por serial).
        - Registros que compartilham (SiglaUf, NumeroInmetro, NumeroSerie)
          com serial preenchido sao o MESMO instrumento e sao fundidos
          (faixas e historico unidos; local mais recente prevalece).
        """
        instrumentos = {}
        ordem = []
        for rec in registros_brutos:
            if not isinstance(rec, dict):
                continue
            faixas_por_serial = {}
            for f in (rec.get("Faixas") or []):
                if not isinstance(f, dict):
                    continue
                chave = ((f.get("NumeroInmetro") or "").strip(),
                         (f.get("NumeroSerie") or "").strip())
                faixas_por_serial.setdefault(chave, []).append(f)
            if not faixas_por_serial:
                faixas_por_serial[("", "")] = []

            for (num_inmetro, numero_serie), faixas in faixas_por_serial.items():
                if numero_serie:
                    ident = ((rec.get("SiglaUf") or "").strip().upper(),
                             num_inmetro, numero_serie)
                else:
                    # sem serial: identidade inclui o local para nao fundir
                    ident = ("", "", "", nz.pick(rec, "LocalVerificacao"),
                             rec.get("Municipio"), len(ordem))
                if ident not in instrumentos:
                    instrumentos[ident] = {
                        "SiglaUf": rec.get("SiglaUf"),
                        "Estado": rec.get("Estado"),
                        "Municipio": rec.get("Municipio"),
                        "LocalVerificacao": rec.get("LocalVerificacao"),
                        "DataUltimaVerificacao": rec.get("DataUltimaVerificacao"),
                        "DataValidade": rec.get("DataValidade"),
                        "UltimoResultado": rec.get("UltimoResultado"),
                        "TipoMedidor": rec.get("TipoMedidor"),
                        "NumeroInmetro": num_inmetro,
                        "NumeroSerie": numero_serie,
                        "Faixas": [],
                        "Historico": [],
                        "Proprietario": rec.get("Proprietario"),
                        "LocaisVerificacao": [],
                    }
                    ordem.append(ident)
                inst = instrumentos[ident]
                inst["Faixas"].extend(faixas)
                inst["Historico"].extend(rec.get("Historico") or [])
                local = rec.get("LocalVerificacao")
                if local and local not in inst["LocaisVerificacao"]:
                    inst["LocaisVerificacao"].append(local)
                # local/municipio mais recente prevalece
                if _data_br(rec.get("DataUltimaVerificacao")) and (
                        _data_br(inst.get("DataUltimaVerificacao")) is None
                        or _data_br(rec.get("DataUltimaVerificacao"))
                        > _data_br(inst.get("DataUltimaVerificacao"))):
                    inst["LocalVerificacao"] = local
                    inst["Municipio"] = rec.get("Municipio")
                    inst["Estado"] = rec.get("Estado")
                    inst["DataUltimaVerificacao"] = rec.get("DataUltimaVerificacao")
                    inst["DataValidade"] = rec.get("DataValidade")
                    inst["UltimoResultado"] = rec.get("UltimoResultado")
                    inst["TipoMedidor"] = rec.get("TipoMedidor")

        saida = []
        for ident in ordem:
            inst = instrumentos[ident]
            inst["Faixas"] = cls._dedup_faixas(inst["Faixas"])
            inst["Historico"] = cls._dedup_historico(inst["Historico"])
            saida.append(inst)
        return saida

    @staticmethod
    def _dedup_faixas(faixas):
        vistos = []
        saida = []
        for f in faixas:
            chave = (f.get("NumeroFaixa"), f.get("Sentido"),
                     f.get("VelocidadeNominal"), f.get("NumeroSerie"))
            if chave in vistos:
                continue
            vistos.append(chave)
            saida.append(f)
        return saida

    @staticmethod
    def _dedup_historico(hist):
        vistos = []
        saida = []
        for h in hist:
            if not isinstance(h, dict):
                continue
            chave = (h.get("NumeroCertificado"), h.get("NumeroEnsaio"),
                     h.get("Ano"), h.get("DataLaudo"))
            if chave in vistos:
                continue
            vistos.append(chave)
            saida.append(h)
        return saida

    # -- normalizar --------------------------------------------------------
    def identificador(self, raw):
        return nz.pick(raw, "NumeroInmetro") or None

    def normalizar(self, idx, raw):
        if not isinstance(raw, dict):
            return None
        numero_serie = (raw.get("NumeroSerie") or "").strip() or None
        num_inmetro = (raw.get("NumeroInmetro") or "").strip() or None
        local = raw.get("LocalVerificacao")
        if not numero_serie and not num_inmetro and not local:
            return None   # registro vazio/irrelevante

        faixas = raw.get("Faixas") or []
        sentidos = _sentido_lista(faixas)
        if len(sentidos) > 1:
            sentido = "ambos"
        elif sentidos:
            sentido = sentidos[0]
        else:
            sentido = None
        sentido_original = None
        brutos = [str(f.get("Sentido")).strip() for f in faixas
                  if f.get("Sentido")]
        if brutos:
            sentido_original = " / ".join(sorted(set(brutos)))

        vels = _velocidades(faixas)
        # so adota velocidade unica quando TODAS as faixas concordam;
        # divergencia nao vira velocidade inventada.
        velocidade = vels[0] if len(vels) == 1 else None

        # o historico metrologico NAO vira situacao operacional (spec 11.6).
        cert = self._ultimo_certificado(raw.get("Historico"))

        obs = self._montar_observacoes(raw, faixas, vels, sentido_original, cert)

        return {
            "identificador": num_inmetro,
            "tipo_identificador": "numero_inmetro",
            "numero_serie": numero_serie,
            # sem coordenadas oficiais na fonte -> posicao NAO CONFIRMADA
            "latitude": None,
            "longitude": None,
            "qualidade": "nao_confirmada",
            "metodo_obtencao": "publicacao INMETRO/PSIE (sem coordenadas)",
            "uf": raw.get("SiglaUf"),
            "municipio_nome": raw.get("Municipio"),
            "municipio_ibge": None,
            "via_codigo": None,          # LocalVerificacao e texto livre
            "km": None,
            "tipo_pista": None,
            "situacao": None,            # fonte nao publica situacao operacional
            "tipo_radar": nz.normalizar_tipo_radar(raw.get("TipoMedidor")),
            "fabricante": None,
            "modelo": None,
            "velocidade_leves": velocidade,
            "velocidade_pesados": None,
            "sentido": sentido,
            "sentido_original": sentido_original,
            "observacoes": obs,
        }

    @staticmethod
    def _ultimo_certificado(historico):
        if not historico:
            return None
        def chave(h):
            return (_data_br(h.get("DataLaudo"))
                    or datetime.date.min, h.get("Ano") or "")
        try:
            return sorted([h for h in historico if isinstance(h, dict)],
                          key=chave)[-1]
        except Exception:                                  # noqa: BLE001
            return None

    @staticmethod
    def _montar_observacoes(raw, faixas, vels, sentido_original, cert):
        partes = []
        if raw.get("LocalVerificacao"):
            partes.append("Local: %s" % raw["LocalVerificacao"])
        locais = raw.get("LocaisVerificacao") or []
        if len(locais) > 1:
            partes.append("Outros locais: %s" % "; ".join(locais[1:]))
        prop = raw.get("Proprietario") or {}
        if isinstance(prop, dict) and prop.get("Nome"):
            partes.append("Proprietario: %s (%s/%s)" % (
                prop.get("Nome"), prop.get("Municipio") or "-",
                prop.get("Estado") or "-"))
        partes.append("Faixas: %d" % len(faixas))
        if sentido_original:
            partes.append("Sentidos: %s" % sentido_original)
        if vels:
            partes.append("Velocidades nominais: %s" % ", ".join(
                str(int(v)) if float(v).is_integer() else str(v)
                for v in vels))
        partes.append("TipoMedidor: %s" % (raw.get("TipoMedidor") or "-"))
        partes.append("Resultado: %s" % (raw.get("UltimoResultado") or "-"))
        if raw.get("DataUltimaVerificacao"):
            partes.append("Verificado em: %s" % raw["DataUltimaVerificacao"])
        if raw.get("DataValidade"):
            partes.append("Validade: %s" % raw["DataValidade"])
        if cert:
            partes.append("Certificado: %s (ensaio %s, %s, %s)" % (
                cert.get("NumeroCertificado") or "-",
                cert.get("NumeroEnsaio") or "-",
                cert.get("TipoServico") or "-",
                cert.get("Resultado") or "-"))
        return " | ".join(partes)
