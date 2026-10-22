"""Cadastros oficiais encontrados em 22/10/2026.

Cada publicacao e um recurso independente. HTML/JS sao lidos como dados,
sem executar scripts. Ausencia de GPS, velocidade ou situacao fica NULL;
datas de vistoria antigas nao atestam validade metrologica atual.
"""
import hashlib
import html
import json
import os
import re
from urllib.parse import urljoin

from coletor import http
from coletor.base import ColetorBase
from coletor.fontes import normalizacao as nz
from coletor.fontes import planilha as pl
from coletor.fontes.araguaiana_to import _texto_pdf


def texto(valor):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", valor)).split())


def identidade(local):
    return hashlib.sha256(nz.normalizar_nome_texto(local).encode()).hexdigest()[:24]


def cadastro(nome, uf, pagina, municipio=None, formato="html", url=None):
    """Metadados comuns; a circunscricao vem do orgao, nunca do nome da UF."""
    return {
        "FONTE": {"nome": nome, "organizacao": nome.split(" - ")[0],
                  "tipo_organizacao": "orgao_publico", "natureza": "oficial",
                  "esfera": "municipal" if municipio else "estadual",
                  "url_institucional": pagina, "documentacao_url": pagina,
                  "licenca": "publicacao institucional publica",
                  "periodicidade_declarada": "irregular", "situacao": "ativa"},
        "RECURSO": {"nome": nome, "url_recurso": url or pagina,
                    "formato_origem": formato, "periodicidade_segundos": 604800,
                    "status_integracao": "ok"},
        "UF": uf, "MUNICIPIO": municipio, "PAGINA": pagina,
        "URL": url or pagina, "FORMATO": formato,
    }


class CadastroPublicado(ColetorBase):
    """Persiste o original e entrega campos canonicos ao mesmo fluxo da API."""

    @classmethod
    def resolver_url(cls):
        return cls.URL

    def carregar(self, origem):
        if origem and os.path.isfile(origem):
            with open(origem, "rb") as arquivo:
                corpo = arquivo.read()
        else:
            corpo = http.baixar(origem or self.resolver_url())[0]
        conteudo = (_texto_pdf(corpo) if self.FORMATO == "pdf"
                    else corpo.decode("utf-8-sig"))
        registros = self.extrair_registros(conteudo)
        if not registros:
            raise ValueError("Cadastro oficial vazio ou formato alterado: " + self.PAGINA)
        mime = {"pdf": "application/pdf", "html": "text/html", "json": "application/json"}
        return corpo, "." + self.FORMATO, mime[self.FORMATO], registros

    def identificador(self, raw):
        return raw["identificador"]

    def normalizar(self, idx, raw):
        d = {k: raw.get(k) for k in (
            "identificador", "latitude", "longitude", "numero_serie", "km",
            "via_codigo", "municipio_nome", "situacao", "velocidade_geral",
            "sentido_original", "velocidade_leves", "velocidade_pesados")}
        d.update(uf=self.UF, municipio_nome=raw.get("municipio_nome") or self.MUNICIPIO,
                 tipo_identificador="cadastro_local", tipo_radar="fixo",
                 qualidade="oficial", metodo_obtencao="publicacao " + self.FONTE["organizacao"],
                 observacoes=raw.get("endereco"),
                 via_tipo=nz.tipo_via_de_rodovia(raw.get("via_codigo")))
        if d["sentido_original"]:
            d["sentido"] = nz.normalizar_sentido(d["sentido_original"])
        lat, lon = d["latitude"], d["longitude"]
        if lat is not None and lon is not None and not (
                -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0 or lon != 0)):
            # O painel CET tem valores sem separador decimal. Sem prova da
            # escala correta, mantemos o original e nao inventamos GPS.
            d["latitude"] = d["longitude"] = None
        return d


def local_rodoviario(endereco):
    rodovia = re.search(r"\b(?:BR|ES|PE|ERS|RSC)[- ]?\d{2,3}\b", endereco, re.I)
    km = re.search(r"\bkm\s*(\d+(?:[,.]\d+)?(?:\+\d{3})?)", endereco, re.I)
    km = km.group(1).replace("+", ".") if km else None
    return {"via_codigo": rodovia.group().upper().replace(" ", "-") if rodovia else None,
            "km": nz.to_float(km)}


class ColetorDERES(CadastroPublicado):
    locals().update(cadastro("DER-ES - Equipamentos de fiscalizacao", "ES",
                            "https://servicos.der.es.gov.br/Radares.aspx"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for tabela in pl.ler_tabelas_html(conteudo):
            for r in tabela:
                if len(r) != 8 or not re.fullmatch(r"[A-Z]{3,6}\s*-\s*\d+", r[0]):
                    continue
                codigo, endereco, faixas, tipo, funcoes, velocidade, serie, _ = r
                situacao = "inativo" if any(x in (tipo + " " + endereco).upper() for x in (
                    "DESATIVADO", "REMANEJADO", "SUBSTITUÍDO", "REMOVIDO")) else None
                municipio = re.search(r" - (.+?) - (?:sentido|pr[oó]x)", endereco, re.I)
                registros.append(dict(
                    identificador=re.sub(r"\s+", "", codigo) + ":" + identidade(endereco), codigo=codigo,
                    endereco=endereco, faixas=faixas, tipo=tipo, funcoes=funcoes,
                    velocidade_geral=nz.to_velocidade(velocidade), serie_publicada=serie,
                    numero_serie=serie if re.fullmatch(r"[A-Za-z0-9]+", serie) else None,
                    situacao=situacao, municipio_nome=municipio.group(1) if municipio else None,
                    **local_rodoviario(endereco)))
        return registros


class ColetorDERPELombadas(CadastroPublicado):
    locals().update(cadastro("DER-PE - Lombadas eletronicas", "PE",
        "https://www.der.pe.gov.br/transito-menu/lombadas-eletronicas/lista-de-trechos-monitorados-2/1382-lista-de-trechos-monitorados-lombadas"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for tabela in pl.ler_tabelas_html(conteudo):
            ultimo = None
            for r in tabela:
                if len(r) == 10 and re.search(r"DERPE\d+", r[0]):
                    codigo = re.search(r"DERPE\d+", r[0]).group()
                    ultimo = dict(identificador=codigo, endereco=r[4],
                        numero_serie=r[2] or None, tipo=r[3], municipio_nome=r[6],
                        velocidade_geral=nz.to_velocidade(r[7]),
                        latitude=nz.to_float(r[8]), longitude=nz.to_float(r[9]),
                        faixas_publicadas=[{"processador": r[1], "sentido": r[5]}],
                        **local_rodoviario(r[4]))
                    registros.append(ultimo)
                elif ultimo and len(r) == 2 and re.fullmatch(r"\d+-\d+", r[0]):
                    ultimo["faixas_publicadas"].append({"processador": r[0], "sentido": r[1]})
        # Sentidos diferentes por faixa nao viram um sentido unico inventado.
        for r in registros:
            sentidos = set(x["sentido"] for x in r["faixas_publicadas"])
            r["sentido_original"] = next(iter(sentidos)) if len(sentidos) == 1 else None
        return registros


class ColetorDERPEMistos(CadastroPublicado):
    locals().update(cadastro("DER-PE - Equipamentos mistos", "PE",
        "https://www.der.pe.gov.br/transito-menu/equipamentos-de-fiscalizacao-eletronica/lista-de-trechos-2/1383-equipamentos-mistos"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for tabela in pl.ler_tabelas_html(conteudo):
            for r in tabela:
                if len(r) == 3 and r[0].isdigit():
                    lat, lon = pl.parse_coordenadas(r[2])
                    registros.append(dict(identificador=r[0], endereco=r[1],
                        latitude=lat, longitude=lon, **local_rodoviario(r[1])))
        return registros


class ColetorCuritiba(CadastroPublicado):
    locals().update(cadastro("Setran Curitiba - Fiscalizacao eletronica", "PR",
        "https://transito.curitiba.pr.gov.br/fiscalizacaoeletronica", "Curitiba"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for bloco in conteudo.split('<div class="item-lista">')[1:]:
            if "icone-velocidade'" not in bloco and 'icone-velocidade"' not in bloco:
                continue
            codigo = re.search(r"DetalheEquipamento\.aspx\?codigo=(\d+)", bloco)
            local = re.search(r'lblLocal_\d+">(.*?)</span>', bloco, re.S)
            trecho = re.search(r'lblTrecho_\d+">(.*?)</span>', bloco, re.S)
            nome = re.search(r'lblIdentificacao_\d+">(.*?)</span>', bloco, re.S)
            gps = re.search(r"verNoMapa\('(-?[\d.]+)'\s*,\s*'(-?[\d.]+)'", html.unescape(bloco))
            velocidade = re.search(r"icn-velocidade-(\d+)", bloco)
            if not codigo or not local:
                raise ValueError("Cartao de Curitiba sem codigo/local")
            registros.append(dict(identificador=codigo.group(1),
                endereco=texto(local.group(1)) + (" / " + texto(trecho.group(1)) if trecho else ""),
                codigo_publicado=texto(nome.group(1)) if nome else None,
                latitude=float(gps.group(1)) if gps else None,
                longitude=float(gps.group(2)) if gps else None,
                velocidade_geral=int(velocidade.group(1)) if velocidade else None))
        return registros


class ColetorSalvador(CadastroPublicado):
    locals().update(cadastro("Transalvador - Mapa de equipamentos", "BA",
        "https://transonline.salvador.ba.gov.br/equipamentos/index.php", "Salvador",
        url="https://transonline.salvador.ba.gov.br/geral_sistema/web/index.php/mapa/mapa-porticos"))

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for bloco in re.split(r"var gmarker\d+ = ", conteudo)[1:]:
            if "/markers/radar.png" not in bloco:
                continue
            gps = re.search(r"LatLng\((-?[\d.]+),\s*(-?[\d.]+)\)", bloco)
            info = re.search(r"setContent\('((?:\\.|[^'\\])*)'\)", bloco)
            if not gps or not info:
                raise ValueError("Marcador de Salvador sem coordenada ou informacoes")
            partes = re.split(r"<br\s*/?>", info.group(1), flags=re.I)
            endereco = texto(partes[0]).replace("\\'", "'")
            dados = texto(info.group(1))
            serie = re.search(r"Série:\s*([A-Z0-9]+)", dados)
            velocidade = re.search(r"Velocidade:\s*(\d+)", dados)
            registros.append(dict(identificador=identidade(endereco) + ":" + (serie.group(1) if serie else "sem-serie"), endereco=endereco,
                dados_publicados=dados, numero_serie=serie.group(1) if serie else None,
                latitude=float(gps.group(1)), longitude=float(gps.group(2)),
                velocidade_geral=int(velocidade.group(1)) if velocidade else None))
        return registros


class ColetorAracaju(CadastroPublicado):
    locals().update(cadastro("SMTT Aracaju - Medidores de velocidade", "SE",
        "https://smtt.aracaju.se.gov.br/medidores-de-velocidade/", "Aracaju", "json",
        "https://smtt.aracaju.se.gov.br/wp-json/smtt/v1/radares"))

    @staticmethod
    def extrair_registros(conteudo):
        dados = json.loads(conteudo)
        registros = []
        for r in dados["items"]:
            if not r.get("codigo_equipamento") or not r.get("endereco"):
                raise ValueError("Medidor de Aracaju sem codigo/endereco")
            registros.append(dict(r, identificador=r["codigo_equipamento"],
                situacao=nz.normalizar_situacao(r.get("situacao")),
                velocidade_geral=nz.to_velocidade(r.get("velocidade"))))
        return registros


class ColetorDAERFixos(CadastroPublicado):
    locals().update(cadastro("DAER-RS - Controladores fixos", "RS",
        "https://www.daer.rs.gov.br/pardais", formato="pdf",
        url="https://www.daer.rs.gov.br/upload/arquivos/202404/18094710-localizacao-controladores-daer.pdf"))

    @classmethod
    def resolver_url(cls):
        pagina = http.baixar(cls.PAGINA)[0].decode("utf-8", "replace")
        links = re.findall(r'href=[\"\']([^\"\']+\.pdf)[\"\']', pagina, re.I)
        alvo = "localizacao-controladores" if cls is ColetorDAERFixos else "localizacao-redutores"
        links = sorted((x for x in links if alvo in x), reverse=True)
        if not links:
            raise ValueError("DAER nao publicou o link do cadastro esperado")
        return urljoin(cls.PAGINA, links[0])

    @staticmethod
    def extrair_registros(conteudo):
        padrao = re.compile(r"^\s*(Pardal|Lombada)\s+([A-Z]{3}-\d+)\s+([\d,]+)\s+"
            r"(.+?)\s+(\d{8}|Decl\.\s*Conf\.\*+)\s+(\w+)\s+(.+?)\s+(\d+)\s*$", re.M)
        registros = []
        for m in padrao.finditer(conteudo):
            tipo, via, km, municipio, inmetro, serie, codigo, faixas = m.groups()
            registros.append(dict(identificador=re.sub(r"\s+", "", codigo),
                endereco=via + " km " + km, via_codigo=via, km=nz.to_float(km),
                municipio_nome=municipio.strip(), numero_serie=serie, tipo=tipo,
                numero_inmetro=inmetro if inmetro.isdigit() else None,
                declaracao_conformidade=inmetro if not inmetro.isdigit() else None,
                faixas=int(faixas), codigo_publicado=codigo))
        esperadas = len(re.findall(r"^\s*(?:Pardal|Lombada)\s+[A-Z]{3}-\d+", conteudo, re.M))
        if len(registros) != esperadas:
            raise ValueError("Formato DAER alterado: linha de equipamento nao reconhecida")
        return registros


class ColetorDAERRedutores(ColetorDAERFixos):
    locals().update(cadastro("DAER-RS - Redutores de velocidade", "RS",
        "https://www.daer.rs.gov.br/localizacao-das-lombadas", formato="pdf",
        url="https://www.daer.rs.gov.br/upload/arquivos/202410/16161517-localizacao-redutores-de-velocidade.pdf"))


class ColetorJoinvilleCadastro(CadastroPublicado):
    locals().update(cadastro("Detrans Joinville - Cadastro bienal de radares", "SC",
        "https://www.joinville.sc.gov.br/publicacoes/estudos-tecnicos-equipamentos-de-fiscalizacao-eletronica-radares-e-lombadas/",
        "Joinville", "pdf"))

    @classmethod
    def resolver_url(cls):
        pagina = http.baixar(cls.PAGINA)[0].decode("utf-8", "replace")
        links = re.findall(r'href=[\"\']([^\"\']+\.pdf)[\"\']', pagina, re.I)
        links = sorted((x for x in links if "Atualizacao-Bienal-dos-Locais-de-Fiscalizacao-com-Radares-e-da-Sinalizacao" in x), reverse=True)
        if not links:
            raise ValueError("Joinville sem cadastro bienal de locais de radar")
        return urljoin(cls.PAGINA, links[0])

    @staticmethod
    def extrair_registros(conteudo):
        registros = []
        for linha in conteudo.splitlines():
            if not re.match(r"\s*JR\d+", linha):
                continue
            partes = re.split(r"\s{2,}", linha.strip())
            if len(partes) < 3 or not re.fullmatch(r"\d{2}/\d{2}/\d{2}", partes[2]):
                raise ValueError("Linha do cadastro de Joinville nao reconhecida")
            codigo, endereco, inicio = partes[:3]
            gps = re.search(r"(-\d{2}\.\d+)\s*,\s*(-\d{2}\.\d+)", endereco)
            registros.append(dict(identificador=re.sub(r"\s+", "", codigo),
                codigo_publicado=codigo, endereco=endereco, inicio_operacao=inicio,
                diagnosticos=partes[3:], latitude=float(gps.group(1)) if gps else None,
                longitude=float(gps.group(2)) if gps else None))
        return registros


NOVAS_FONTES = {
    "der_es": ColetorDERES, "der_pe_lombadas": ColetorDERPELombadas,
    "der_pe_mistos": ColetorDERPEMistos, "curitiba_pr": ColetorCuritiba,
    "salvador_ba": ColetorSalvador, "aracaju_se": ColetorAracaju,
    "daer_rs_fixos": ColetorDAERFixos, "daer_rs_redutores": ColetorDAERRedutores,
    "joinville_cadastro_sc": ColetorJoinvilleCadastro,
}
