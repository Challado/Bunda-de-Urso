"""Assistencia com alternativas locais; relatorios nunca alteram registros oficiais."""
import argparse
from contextlib import closing
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid

from . import assistente_ia as ia, caminhos, consultas, db, dedup
from .contexto_api import operacao_local
from .governanca import GovernancaError

TAREFAS = {"documento": "documentos", "correspondencias": "correspondencias",
           "auditoria": "auditoria", "diagnostico": "diagnostico", "explicacao": "explicacoes"}
VERSAO = "assistencia-1"


def _erro(msg, status=422):
    raise GovernancaError(status, "assistencia_invalida", msg)


def _id(valor, prefixo=""):
    texto = str(valor or "")
    if prefixo and texto.upper().startswith(prefixo):
        texto = texto[len(prefixo):]
    if not texto.isdecimal() or not 0 < int(texto) <= 2147483647:
        _erro("Informe um identificador valido.")
    return int(texto)


def _url_publica(valor):
    try:
        url = urllib.parse.urlsplit(valor or "")
        if url.scheme not in ("http", "https") or not url.hostname:
            return ""
        host = url.hostname
        return urllib.parse.urlunsplit((url.scheme, host, url.path, "", ""))
    except ValueError:
        return ""


def resumo_local(ponto):
    """Explicacao publica baseada em fatos; nunca consulta IA ou rede."""
    fatos = []
    for fonte in ponto.get("dados_por_fonte", []):
        registros = fonte.get("registros", [])
        fatos.append({"id": "F%d" % (len(fatos) + 1), "texto": "%s: %d publicacao(oes) vinculada(s)." %
                      (fonte["nome"], len(registros)), "fonte": fonte["nome"],
                      "url": _url_publica(fonte.get("url")),
                      "registros": [r["registro_id"] for r in registros]})
        permitidos = {"latitude", "longitude", "velocidade", "velocidadekmh", "velocidadenominal",
                      "numeroserie", "rodovia", "municipio", "uf", "modelo", "fabricante",
                      "dataverificacao", "datavalidade", "numerocertificado"}
        for registro in registros[:5]:
            publicado = registro.get("dados_publicados")
            if not isinstance(publicado, dict):
                continue
            for campo, valor in publicado.items():
                if re.sub(r"[^a-z0-9]", "", campo.lower()) not in permitidos or isinstance(valor, (dict, list)) or valor is None:
                    continue
                if len(fatos) >= 60:
                    break
                fatos.append({"id": "F%d" % (len(fatos) + 1), "texto": "%s publicou %s = %s (registro %s)." %
                              (fonte["nome"], campo, str(valor)[:240], registro["registro_id"]),
                              "fonte": fonte["nome"], "registro_id": registro["registro_id"],
                              "hash_artefato": registro.get("hash_artefato"),
                              "url": _url_publica(registro.get("recurso_url"))})
    loc = ponto.get("localizacao") or {}
    qualidade = loc.get("qualidade") or "nao informada"
    fatos.append({"id": "F%d" % (len(fatos) + 1), "texto": "Qualidade da posicao consolidada: %s." % qualidade,
                  "origem": "base_consolidada"})
    for conflito in ponto.get("conflitos", [])[:30]:
        valores = conflito.get("valores_kmh")
        texto = ("Velocidades divergentes no mesmo escopo: %s km/h; nenhum valor unico foi escolhido." %
                 ", ".join(map(str, valores))) if valores else "Divergencia registrada no campo %s; confira as publicacoes." % conflito.get("campo", "nao informado")
        fatos.append({"id": "F%d" % (len(fatos) + 1), "texto": texto, "origem": "regras_da_base"})
    if not ponto.get("dados_por_fonte"):
        fatos.append({"id": "F%d" % (len(fatos) + 1), "texto": "Nao ha publicacoes de origem vinculadas para conferir os campos.", "origem": "base"})
    return {"metodo": "regras_locais", "usou_ia": False, "fatos": fatos,
            "texto": " ".join(f["texto"] for f in fatos)}


def _ponto(conn, valor):
    ponto = consultas.buscar_ponto_por_id(conn, _id(valor, "P-"))
    if ponto is None:
        _erro("Ponto nao encontrado.", 404)
    return ponto


def _auditoria(ponto):
    achados = []
    for fato in resumo_local(ponto)["fatos"]:
        if fato.get("origem") in ("regras_da_base", "base"):
            achados.append(fato)
    loc = ponto.get("localizacao") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        achados.append({"texto": "Coordenadas ausentes: preservar como nao informado, sem inventar GPS."})
    elif not (-34 <= lat <= 6 and -74 <= lon <= -28):
        achados.append({"texto": "Coordenadas fora da envolvente do Brasil: conferir a publicacao original."})
    for limite in ponto.get("limites_velocidade", []):
        velocidade = limite.get("velocidade_kmh")
        if velocidade is not None and not 1 <= velocidade <= 160:
            achados.append({"texto": "Velocidade fora de 1..160 km/h: revisar o valor e seu escopo.",
                            "valor": velocidade, "fonte_registro_id": limite.get("fonte_registro_id")})
    if not achados:
        achados.append({"texto": "Nenhuma inconsistencia detectada pelas regras executadas; isso nao certifica os dados."})
    for i, achado in enumerate(achados):
        achado["id"] = "A%d" % (i + 1)
    return {"ponto_id": ponto["id"], "achados": achados}


def _correspondencias(conn, ponto):
    loc = ponto.get("localizacao") or {}
    if loc.get("latitude") is None or loc.get("longitude") is None:
        return {"ponto_id": ponto["id"], "candidatos": [], "observacao": "Sem GPS: use a fila de deduplicacao por identidade de instrumento; nao inferir proximidade."}
    vizinhos, _ = consultas.buscar_pontos(conn, loc["latitude"], loc["longitude"],
                                         caminhos.inteiro("governanca", "raio_correspondencia_m"), limite=21)
    origens = [r["registro_id"] for f in ponto.get("dados_por_fonte", []) for r in f["registros"]][:3]
    candidatos = []
    for vizinho in vizinhos:
        if vizinho["id"] == ponto["id"]:
            continue
        outro = _ponto(conn, vizinho["id"])
        registros = [r["registro_id"] for f in outro.get("dados_por_fonte", []) for r in f["registros"]][:3]
        comparacoes = [dedup.pontuar(dedup.atributos_registro(conn, a), dedup.atributos_registro(conn, b))
                       for a in origens for b in registros]
        fortes = [c for c in comparacoes if not c["bloqueadores"]]
        melhor = max(fortes or comparacoes, key=lambda c: c["score"], default=None)
        candidatos.append({"id": vizinho["id"], "distancia_metros": vizinho.get("distancia_metros"),
                           "evidencia": melhor, "fontes": [f["nome"] for f in outro.get("dados_por_fonte", [])],
                           "encaminhamento": "revisar" if fortes else "inconclusivo_ou_contraditorio"})
    candidatos.sort(key=lambda c: (c["encaminhamento"] != "revisar", -(c["evidencia"] or {}).get("score", 0), c["id"]))
    return {"ponto_id": ponto["id"], "candidatos": candidatos[:20],
            "observacao": "Proximidade e indicio, nao identidade. Registros oficiais permanecem separados."}


def _diagnostico(conn, valor):
    row = conn.execute("""SELECT e.*, r.url_recurso, f.nome AS fonte FROM EXECUCAO_COLETA e
        LEFT JOIN RECURSO_FONTE r ON r.id=e.recurso_id LEFT JOIN FONTE f ON f.id=r.fonte_id WHERE e.id=?""", (_id(valor),)).fetchone()
    if row is None:
        _erro("Execucao nao encontrada.", 404)
    texto = str(row["erro_detalhe"] or "").lower()
    codigo, http = str(row["erro_codigo"] or ""), row["http_status"]
    if http in (401, 403):
        causa, acao = "acesso_recusado", "Conferir permissao/URL publica na origem; manter o ultimo snapshot valido."
    elif http == 429:
        causa, acao = "limite_da_fonte", "Respeitar Retry-After e o backoff do coletor."
    elif http and http >= 500:
        causa, acao = "origem_indisponivel", "Repetir com backoff; preservar cache e ultimo snapshot."
    elif "timeout" in texto or "timed out" in texto or "Timeout" in codigo:
        causa, acao = "tempo_esgotado", "Conferir disponibilidade e timeout; repetir com limite de tentativas."
    elif any(t in texto for t in ("ssl", "certificate", "certificado")):
        causa, acao = "tls", "Conferir certificado e cadeia de confianca; manter verificacao TLS."
    elif any(t in texto for t in ("resolve", "name resolution", "dns")):
        causa, acao = "dns", "Conferir DNS e disponibilidade da origem."
    elif codigo or row["status"] == "erro":
        causa, acao = "formato_ou_validacao", "Comparar o artefato original com o parser, campos e rejeicoes; revisar o conector."
    else:
        causa, acao = "sem_falha", "A execucao nao registra erro; conferir os contadores e a proxima coleta."
    # Mensagens de excecao podem conter credenciais. Nunca as manda ao provedor.
    return {"execucao_id": row["id"], "fonte": row["fonte"], "url": _url_publica(row["url_recurso"]),
            "status": row["status"], "http_status": http, "causa": causa,
            "acoes": [{"id": "D1", "texto": acao},
                      {"id": "D2", "texto": "Conferir o hash e o conteudo do artefato em cache e as rejeicoes da execucao."},
                      {"id": "D3", "texto": "Preservar o ultimo snapshot valido durante a investigacao; testar ajustes com fixtures antes de publicar."}],
            "artefato_id": row["artefato_id"]}


def _numero(v):
    try:
        n = float(str(v).replace(",", "."))
        return n if math.isfinite(n) and not isinstance(v, bool) else None
    except (ValueError, TypeError):
        return None


def extrair_texto(texto):
    """Leitor conservador local de linhas rotuladas; mantem pagina e trecho."""
    registros = []
    padroes = {"latitude": r"\blat(?:itude)?\s*[:=]\s*(-?\d{1,2}(?:[.,]\d+)?)",
               "longitude": r"\b(?:lon(?:gitude)?|lng)\s*[:=]\s*(-?\d{1,3}(?:[.,]\d+)?)",
               "velocidade": r"(?:\bvel(?:ocidade)?\s*[:=]\s*|\b)(\d{1,3})\s*km\s*/\s*h\b"}
    for pagina, conteudo in enumerate(texto.split("\f"), 1):
        for linha in conteudo.splitlines():
            valores = {k: m.group(1) for k, p in padroes.items() if (m := re.search(p, linha, re.I))}
            if "latitude" in valores and "longitude" in valores:
                registro = _validar_registro({**valores, "pagina": pagina, "trecho": linha}, texto)
                if registro:
                    registros.append(registro)
    return registros


def _validar_registro(registro, texto):
    if not isinstance(registro, dict) or isinstance(registro.get("pagina"), bool):
        return None
    pagina, trecho = registro.get("pagina"), registro.get("trecho")
    paginas = texto.split("\f")
    if not isinstance(pagina, int) or not 1 <= pagina <= len(paginas) or not isinstance(trecho, str) or not 5 <= len(trecho) <= 2500:
        return None
    if trecho not in paginas[pagina - 1]:
        return None
    saida = {"pagina": pagina, "trecho": trecho, "revisao_necessaria": True}
    for campo in ("latitude", "longitude", "velocidade"):
        valor = registro.get(campo)
        if valor in (None, ""):
            saida[campo] = None
            continue
        numero = _numero(valor)
        # Exige que o numero proposto conste literalmente no trecho citado.
        numeros = [_numero(n) for n in re.findall(r"(?<![\w.])-?\d+(?:[.,]\d+)?", trecho)]
        faixa = {"latitude": (-34, 6), "longitude": (-74, -28), "velocidade": (1, 160)}[campo]
        if numero is None or numero not in numeros or not faixa[0] <= numero <= faixa[1]:
            return None
        saida[campo] = numero
    if saida["latitude"] is None or saida["longitude"] is None:
        return None
    return saida


def _ocr_local(arquivo):
    """OCR conservador e limitado: tres paginas, sem servico remoto."""
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="radar-ocr-") as pasta:
            prefixo = str(Path(pasta) / "pagina")
            subprocess.run(["pdftoppm", "-f", "1", "-l", "3", "-scale-to", "1800", "-png", str(arquivo), prefixo],
                           check=True, capture_output=True, timeout=8)
            textos = []
            for imagem in sorted(Path(pasta).glob("pagina-*.png"))[:3]:
                r = subprocess.run(["tesseract", str(imagem), "stdout", "-l", "por+eng"],
                                   capture_output=True, check=True, timeout=6)
                textos.append(r.stdout.decode("utf-8", errors="replace"))
            return "\f".join(textos)
    except (OSError, subprocess.SubprocessError):
        return ""


def _documento(conn, valor, sem_ia=False):
    row = conn.execute("""SELECT a.*, f.nome AS fonte, n.codigo AS natureza, r.url_recurso FROM ARTEFATO_COLETA a
        LEFT JOIN RECURSO_FONTE r ON r.id=a.recurso_id LEFT JOIN FONTE f ON f.id=r.fonte_id
        LEFT JOIN NATUREZA_FONTE n ON n.id=f.natureza_id WHERE a.id=?""", (_id(valor),)).fetchone()
    if row is None:
        _erro("Artefato nao encontrado.", 404)
    arquivo = Path(row["caminho_cache"]).resolve()
    if not arquivo.is_relative_to(Path(caminhos.bruto()).resolve()) or not arquivo.is_file() or arquivo.stat().st_size > 8 * 1024 * 1024:
        _erro("Artefato deve estar no cache bruto configurado, ate 8 MiB.")
    conteudo = arquivo.read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != row["hash_sha256"]:
        _erro("Hash do artefato diverge do original; nao analisar.")
    metodo = "texto_publicado"
    if conteudo.startswith(b"%PDF"):
        metodo = "pdftotext"
        try:
            r = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", "30", "-", "-"], input=conteudo,
                               capture_output=True, timeout=10, check=True)
            texto = r.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError):
            from coletor.fontes.planilha import ler_pdf_texto
            texto = ler_pdf_texto(conteudo)
            metodo = "leitor_pdf_local"
        if not texto.strip() and ia.ativo("documentos") and not sem_ia:
            texto = _ocr_local(arquivo)
            metodo = "ocr_local_3_paginas" if texto.strip() else "pdf_sem_texto_legivel"
    else:
        texto = conteudo.decode("utf-8", errors="replace")
    limite = max(1000, caminhos.inteiro("assistente", "max_entrada") - 2000)
    completo = len(texto) <= limite
    texto = texto[:limite]
    registros = extrair_texto(texto)
    # Os leitores especificos de tabelas continuam disponiveis sem IA.
    leitores = {"DETRAN-MA": ("detran_ma", "ColetorDetranMA"), "ASTT": ("araguaiana_to", "ColetorASTTAraguaina")}
    estruturados = []
    for nome, (modulo, classe) in leitores.items():
        if nome.casefold() in row["fonte"].casefold():
            import importlib
            leitor = getattr(importlib.import_module("coletor.fontes." + modulo), classe)
            estruturados = leitor.extrair_registros(texto)[:200]
    return {"artefato_id": row["id"], "fonte": row["fonte"], "natureza": row["natureza"], "url": _url_publica(row["url_recurso"]),
            "hash_sha256": row["hash_sha256"], "texto": texto, "trecho_integral": completo,
            "metodo_leitura": metodo, "limite_paginas_pdf": 3 if "ocr" in metodo else 30,
            "registros": registros[:200], "registros_do_leitor_oficial": estruturados,
            "estado": "propostas_para_revisao" if registros or estruturados else "revisar_documento",
            "observacao": "PDF sem texto exige transcricao/OCR e revisao; campos ausentes permanecem ausentes."}


def analisar(conn, dados, autor="local"):
    if not isinstance(dados, dict) or not isinstance(dados.get("tarefa"), str) or dados["tarefa"] not in TAREFAS or set(dados) - {"tarefa", "ponto_id", "artefato_id", "execucao_id", "sem_ia"}:
        _erro("Escolha documento, correspondencias, auditoria, diagnostico ou explicacao.")
    if "sem_ia" in dados and not isinstance(dados["sem_ia"], bool):
        _erro("sem_ia deve ser booleano.")
    tarefa = dados["tarefa"]
    if tarefa == "documento":
        local = _documento(conn, dados.get("artefato_id"), sem_ia=dados.get("sem_ia", False))
        entrada = {k: local[k] for k in ("artefato_id", "fonte", "url", "hash_sha256", "texto")}
        instrucao = 'Extraia radares somente do texto. Retorne {"registros":[{"latitude":numero,"longitude":numero,"velocidade":numero_ou_null,"pagina":inteiro,"trecho":"citacao literal"}]}. Nao inferir coordenadas de enderecos. Paginas separadas por form feed.'
    elif tarefa == "diagnostico":
        local = _diagnostico(conn, dados.get("execucao_id"))
        entrada, instrucao = local, 'Ordene as acoes por relevancia. Retorne {"ordem":["D1"]}, somente IDs recebidos.'
    else:
        ponto = _ponto(conn, dados.get("ponto_id"))
        local = (_correspondencias(conn, ponto) if tarefa == "correspondencias" else
                 _auditoria(ponto) if tarefa == "auditoria" else resumo_local(ponto))
        entrada = local
        instrucao = 'Priorize apenas os IDs de candidatos/fatos/achados recebidos. Retorne {"ordem":["ID"]}. Nao unifique registros nem produza fatos novos.'
    # Arquivos comunitarios brutos podem conter contatos; analisa-os apenas localmente.
    somente_local = dados.get("sem_ia", False) or tarefa == "documento" and local["natureza"] != "oficial"
    consulta = ia.consultar_json(TAREFAS[tarefa], instrucao, entrada, sem_ia=somente_local)
    if tarefa == "documento" and local["natureza"] != "oficial":
        consulta["motivo"] = "documento_nao_oficial_local"
    sugestao = None
    if consulta["usou_ia"]:
        resposta = consulta["resposta"]
        if tarefa == "documento":
            itens = resposta.get("registros")
            if isinstance(itens, list):
                sugestao = {"registros": [v for r in itens[:200] if (v := _validar_registro(r, local["texto"]))]}
                if not sugestao["registros"]:
                    sugestao = None
        else:
            campo = {"correspondencias": "candidatos", "auditoria": "achados", "diagnostico": "acoes", "explicacao": "fatos"}[tarefa]
            permitidos = {v["id"]: v for v in local[campo] if v.get("encaminhamento") != "inconclusivo_ou_contraditorio"}
            ordem = resposta.get("ordem")
            if isinstance(ordem, list) and ordem and all(isinstance(v, str) and v in permitidos for v in ordem):
                ordem = list(dict.fromkeys(ordem))
                sugestao = {campo: [permitidos[v] for v in ordem], "tipo": "priorizacao_de_evidencias"}
        if sugestao is None:
            consulta.update(usou_ia=False, motivo="sugestao_nao_validada")
    local.pop("texto", None)
    referencia = hashlib.sha256(json.dumps(local, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    relatorio = {"id": uuid.uuid4().hex, "tarefa": tarefa, "criado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "versao_regras": VERSAO, "autor": autor, "referencia_sha256": referencia,
                 "estado": "proposta", "dados_oficiais_alterados": False, "alternativa_local": local,
                 "ia": {k: v for k, v in consulta.items() if k != "resposta"}, "sugestao_ia": sugestao}
    _gravar(relatorio)
    return relatorio


def _pasta():
    return Path(caminhos.data_dir()) / "calibracao" / "assistente"


def _gravar(relatorio):
    pasta = _pasta()
    pasta.mkdir(parents=True, exist_ok=True)
    pasta.chmod(0o2770)
    fd, tmp = tempfile.mkstemp(prefix=".relatorio-", dir=pasta)
    try:
        with os.fdopen(fd, "w") as saida:
            os.fchmod(saida.fileno(), 0o660)
            json.dump(relatorio, saida, ensure_ascii=False, indent=2)
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(tmp, pasta / (relatorio["id"] + ".json"))
    finally:
        Path(tmp).unlink(missing_ok=True)


def listar():
    arquivos = sorted(_pasta().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
    lista = []
    for arquivo in arquivos:
        if arquivo.is_symlink() or arquivo.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            doc = json.loads(arquivo.read_text())
            lista.append({k: doc[k] for k in ("id", "tarefa", "criado_em", "estado", "ia")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return lista


def obter(ident):
    if not re.fullmatch(r"[a-f0-9]{32}", str(ident)):
        _erro("Relatorio invalido.")
    arquivo = _pasta() / (ident + ".json")
    if not arquivo.is_file() or arquivo.is_symlink() or arquivo.stat().st_size > 2 * 1024 * 1024:
        _erro("Relatorio nao encontrado.", 404)
    return json.loads(arquivo.read_text())


@operacao_local
def main(argv=None):
    parser = argparse.ArgumentParser(description="Assistencia opcional; alternativas locais sempre disponiveis.")
    parser.add_argument("acao", choices=("status", "analisar", "listar", "mostrar", "chave"))
    parser.add_argument("--tarefa", choices=TAREFAS)
    parser.add_argument("--ponto")
    parser.add_argument("--artefato")
    parser.add_argument("--execucao")
    parser.add_argument("--relatorio")
    parser.add_argument("--sem-ia", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.acao == "status":
            resultado = ia.status()
        elif args.acao == "chave":
            resultado = ia.salvar_chave(json.load(sys.stdin))
        elif args.acao == "listar":
            resultado = listar()
        elif args.acao == "mostrar":
            resultado = obter(args.relatorio)
        else:
            with closing(db.connect_readonly(caminhos.banco())) as conn:
                resultado = analisar(conn, {"tarefa": args.tarefa, "ponto_id": args.ponto,
                                            "artefato_id": args.artefato, "execucao_id": args.execucao, "sem_ia": args.sem_ia})
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0
    except (GovernancaError, OSError, ValueError) as exc:
        print(exc.mensagem if isinstance(exc, GovernancaError) else "Nao foi possivel concluir a assistencia local.", file=sys.stderr)
        return 1
