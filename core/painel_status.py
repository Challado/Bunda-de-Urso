"""Consultas locais do painel de cobertura e leitores, sem escrita ou rede."""
from collections import Counter, defaultdict
import datetime as dt
from functools import lru_cache
import json
from pathlib import Path

from . import atualizacoes, caminhos, consultas, db, governanca
from .domains import UFS
from .identidade import VisaoCanonica

NOMES = dict(UFS, AP="Amapá", CE="Ceará", ES="Espírito Santo", GO="Goiás",
             MA="Maranhão", PA="Pará", PB="Paraíba", PR="Paraná", PI="Piauí",
             RO="Rondônia", SP="São Paulo")
ESFERAS = ("federal", "estadual", "municipal", "nao_classificado")
REGRA = ("Contamos pontos de fiscalização únicos publicados, incluindo inativos; "
         "faixas e equipamentos no mesmo ponto não multiplicam a contagem. "
         "Removidos e desabilitados não entram. A esfera segue o órgão fiscalizador "
         "ou a fonte oficial do cadastro, nunca o tipo da rodovia. Inmetro é "
         "verificação metrológica e não define esfera. Distritais entram em estaduais. "
         "Esferas conflitantes ou sem comprovação ficam sem classificação. "
         "Zero significa ausência de cadastro nesta base, não ausência de radares no estado.")


def _esfera(valor):
    return "estadual" if valor == "distrital" else valor if valor in ESFERAS[:3] else None


def _uf_payload(texto):
    try:
        dados = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return None
    if isinstance(dados, dict):
        for k, v in dados.items():
            if str(k).lower() in ("uf", "sigla uf", "siglauf", "estado uf", "uf_sigla"):
                uf = str(v).strip().upper()
                if uf in NOMES:
                    return uf
    return None


def _pontos(conn):
    """Reune todas as origens do grupo canonico sem exigir GPS ou metrologia."""
    from coletor.fontes.inmetro import ColetorINMETRO
    visao = VisaoCanonica(conn)
    clausulas, params = governanca.clausulas_consulta(conn)
    sql = consultas._PONTO_SQL
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    aliases = set(visao.aliases("ponto"))
    registros = db.query_all(conn, sql, params)
    rows = {r["ponto_id"]: dict(r) for r in registros if r["ponto_id"] not in aliases}
    for r in registros:
        canonico = rows.get(visao.canonico("ponto", r["ponto_id"]))
        if canonico and not canonico["uf"] and r["uf"]:
            canonico.update(uf=r["uf"], municipio=r["municipio"])
    origens = defaultdict(dict)
    ufs = {}
    for r in conn.execute("""
        SELECT vp.ponto_id, r.payload_original, f.id, f.nome, f.esfera,
               f.url_institucional, n.codigo AS natureza, o.nome AS organizacao
        FROM VINCULO_REGISTRO_PONTO vp
        LEFT JOIN REGISTRO_FONTE r ON r.id=vp.registro_id
        LEFT JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
        LEFT JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
        LEFT JOIN FONTE f ON f.id=rf.fonte_id
        LEFT JOIN NATUREZA_FONTE n ON n.id=f.natureza_id
        LEFT JOIN ORGANIZACAO o ON o.id=f.organizacao_id
        WHERE vp.decisao_id IS NULL ORDER BY r.id DESC
    """):
        pid = visao.canonico("ponto", r["ponto_id"])
        if pid not in rows:
            continue
        if not rows[pid]["uf"] and pid not in ufs:
            uf = _uf_payload(r["payload_original"])
            if uf:
                ufs[pid] = uf
        if r["id"] is not None:
            origens[pid][r["id"]] = {k: r[k] for k in
                ("id", "nome", "esfera", "url_institucional", "natureza", "organizacao")}
    orgs = defaultdict(dict)
    hoje = dt.datetime.now(dt.timezone.utc).isoformat()
    for r in conn.execute("""
        SELECT po.ponto_id, o.id, o.nome, f.esfera
        FROM PONTO_ORGANIZACAO po
        LEFT JOIN ORGANIZACAO o ON o.id=po.organizacao_id
        LEFT JOIN PAPEL_ORGANIZACAO papel ON papel.id=po.papel_id
        LEFT JOIN FONTE f ON f.organizacao_id=o.id AND UPPER(f.nome) NOT LIKE 'INMETRO%' AND f.organizacao_id NOT IN (
            SELECT id FROM ORGANIZACAO WHERE nome=?)
        LEFT JOIN NATUREZA_FONTE n ON n.id=f.natureza_id
        WHERE papel.codigo='fiscalizador'
          AND (po.inicio_em IS NULL OR po.inicio_em<=?)
          AND (po.fim_em IS NULL OR po.fim_em>?)
          AND (f.id IS NULL OR n.codigo='oficial')
    """, (ColetorINMETRO.FONTE["organizacao"], hoje, hoje)):
        pid = visao.canonico("ponto", r["ponto_id"])
        orgs[pid][(r["id"], r["esfera"])] = {"nome": r["nome"], "esfera": _esfera(r["esfera"])}
    pontos = []
    for pid, r in rows.items():
        fontes = sorted(origens[pid].values(), key=lambda f: f["nome"] or "")
        fiscais = list(orgs[pid].values())
        evidencias = fiscais or [{"nome": f["organizacao"] or f["nome"],
                                 "esfera": _esfera(f["esfera"])} for f in fontes
                                if f["natureza"] == "oficial" and not (f["nome"].upper().startswith("INMETRO") or
                                    f["organizacao"] == ColetorINMETRO.FONTE["organizacao"])]
        esferas = {o["esfera"] for o in evidencias if o["esfera"]}
        pontos.append({"id": "P-%d" % pid, "uf": r["uf"] or ufs.get(pid),
                       "municipio": r["municipio"], "via": r["via_codigo"] or r["via_nome"],
                       "km": r["km"], "latitude": r["latitude"], "longitude": r["longitude"],
                       "situacao": r["situacao_operacional"],
                       "esfera": next(iter(esferas)) if len(esferas) == 1 else "nao_classificado",
                       "classificacao": "conflitante" if len(esferas) > 1 else
                           "orgao_fiscalizador" if fiscais and esferas else
                           "fonte_oficial" if esferas else "sem_comprovacao",
                       "organizacoes": sorted({o["nome"] for o in evidencias if o["nome"]}),
                       "fontes": fontes})
    return sorted(pontos, key=lambda p: int(p["id"][2:]))


def _contagem(pontos):
    total = Counter(p["esfera"] for p in pontos)
    return dict(total=len(pontos), **{e: total[e] for e in ESFERAS})


def cobertura(conn, uf=None, limite=100, depois=0):
    if uf is not None and uf not in NOMES:
        raise ValueError("UF desconhecida")
    pontos = _pontos(conn)
    estados = [{"numero": i, "uf": sigla, "nome": NOMES[sigla],
                **_contagem([p for p in pontos if p["uf"] == sigla])}
               for i, (sigla, _) in enumerate(UFS, 1)]
    resultado = {"gerado_em": atualizacoes.agora(), "criterio": REGRA,
                 "totais": _contagem(pontos),
                 "sem_uf": _contagem([p for p in pontos if p["uf"] not in NOMES])}
    if uf is None:
        return dict(resultado, estados=estados)
    pontos = [p for p in pontos if p["uf"] == uf]
    fontes, municipios, orgaos = {}, Counter(), Counter()
    for p in pontos:
        municipios[p["municipio"] or "Município não informado"] += 1
        for nome in p["organizacoes"]:
            orgaos[nome] += 1
        for f in p["fontes"]:
            fontes.setdefault(f["id"], dict(f, pontos=0))["pontos"] += 1
    pagina = [p for p in pontos if int(p["id"][2:]) > depois][:limite + 1]
    return dict(resultado, estado=next(e for e in estados if e["uf"] == uf),
                municipios=[{"nome": n, "pontos": v} for n, v in sorted(municipios.items())],
                organizacoes=[{"nome": n, "pontos": v} for n, v in sorted(orgaos.items())],
                fontes=atualizacoes.limpar(sorted(fontes.values(), key=lambda f: f["nome"])),
                pontos=atualizacoes.limpar(pagina[:limite]),
                proximo_depois=int(pagina[limite - 1]["id"][2:]) if len(pagina) > limite else None)


@lru_cache(maxsize=1)
def _catalogo_localidades():
    """Jurisdicao declarada dos conectores; independe de haver leitura ou GPS."""
    raiz = Path(caminhos.ROOT)
    catalogo = json.loads((raiz / 'coletor/catalogo_ufs.json').read_text(encoding='utf-8'))
    municipios = {m['codigo_ibge']: m for m in json.loads(
        (raiz / 'config/municipios_ibge.json').read_text(encoding='utf-8'))['municipios']}
    locais = {}
    for estado in catalogo['ufs']:
        for lista in ('fontes_estaduais', 'modulos_municipais'):
            for fonte in estado[lista]:
                codigo = fonte.get('municipio_ibge')
                municipio = municipios.get(codigo) if codigo else None
                if codigo and (not municipio or municipio['uf_sigla'] != estado['uf']):
                    raise ValueError('Municipio do catalogo incoerente com a UF: ' + fonte['modulo'])
                locais[fonte['modulo']] = dict(uf=estado['uf'], nome_uf=NOMES[estado['uf']],
                    municipio_ibge=codigo, municipio=municipio['nome'] if municipio else None,
                    origem='catalogo_fonte')
    return locais


def _localidades_fontes(conn):
    """LEFT JOIN conserva abrangencias parciais; UF municipal vem do municipio."""
    locais = defaultdict(list)
    hoje = dt.datetime.now(dt.timezone.utc).date().isoformat()
    for row in conn.execute('''
        SELECT c.fonte_id, c.tipo_abrangencia, c.confirmada, c.municipio_id,
               COALESCE(m.uf_sigla,c.uf_sigla) AS uf, m.nome AS municipio
        FROM COBERTURA_FONTE c LEFT JOIN MUNICIPIO m ON m.codigo_ibge=c.municipio_id
        WHERE (c.vigencia_inicio IS NULL OR c.vigencia_inicio<=?)
          AND (c.vigencia_fim IS NULL OR c.vigencia_fim>=?)
        ORDER BY c.id
    ''', (hoje, hoje)):
        local = dict(uf=row['uf'], nome_uf=NOMES.get(row['uf']),
            municipio_ibge=row['municipio_id'], municipio=row['municipio'],
            tipo_abrangencia=row['tipo_abrangencia'], confirmada=bool(row['confirmada']),
            origem='abrangencia_cadastrada')
        if local not in locais[row['fonte_id']]:
            locais[row['fonte_id']].append(local)
    return locais


def coletores(conn, agenda=None):
    from coletor.agenda import carregar_agenda
    erro_agenda = None
    if agenda is None:
        try:
            agenda = carregar_agenda()
        except (OSError, ValueError) as exc:
            erro_agenda = atualizacoes.limpar(str(exc))
            agenda = {}
    itens = {(v["conector"].FONTE["nome"], v["conector"].RECURSO["nome"]): (k, v)
             for k, v in agenda.items() if v.get("conector")}
    recursos = [dict(r) for r in conn.execute("""
        SELECT rf.id, rf.nome AS recurso, rf.url_recurso, rf.ativo,
               rf.status_integracao, rf.periodicidade_segundos,
               f.id AS fonte_id, f.nome AS fonte, f.esfera, f.situacao, f.url_institucional
        FROM RECURSO_FONTE rf LEFT JOIN FONTE f ON f.id=rf.fonte_id ORDER BY rf.id
    """)]
    diario, erro_relatorio = {}, None
    try:
        diario = json.loads(Path(caminhos.status_atualizacoes()).read_text(encoding="utf-8")).get("fontes", {})
        if not isinstance(diario, dict):
            raise ValueError("Formato de relatorio de leituras invalido")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as exc:
        diario, erro_relatorio = {}, atualizacoes.limpar(str(exc))
    vistos = set()
    leitores = []
    fontes_cadastradas = {f['nome']: f['id'] for f in conn.execute('SELECT id,nome FROM FONTE')}
    for r in recursos:
        chave, item = itens.get((r["fonte"], r["recurso"]), (None, {}))
        if chave:
            vistos.add(chave)
        leitores.append(_leitor(conn, r, chave, item, diario.get(str(r["id"]))))
    for (fonte, recurso), (chave, item) in itens.items():
        if chave in vistos:
            continue
        cls = item["conector"]
        leitores.append(_leitor(conn, dict(id=None, fonte_id=fontes_cadastradas.get(fonte), fonte=fonte, recurso=recurso,
            esfera=cls.FONTE.get("esfera"), situacao=cls.FONTE.get("situacao", "ativa"),
            ativo=True, status_integracao=cls.RECURSO.get("status_integracao"),
            url_recurso=cls.RECURSO.get("url_recurso"),
            url_institucional=cls.FONTE.get("url_institucional"),
            periodicidade_segundos=cls.RECURSO.get("periodicidade_segundos")), chave, item, None))
    # Nomes/codigos sao metadados de jurisdicao, nao uma inferencia da rodovia
    # ou dos radares recebidos. Tambem funcionam para fontes nunca coletadas.
    from coletor.agenda import AGENDA_PADRAO
    erro_localidades = None
    try:
        catalogo = _catalogo_localidades()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Falta de metadado territorial nao pode ocultar o historico do leitor.
        catalogo = {}
        erro_localidades = atualizacoes.limpar(str(exc))
    por_nome = defaultdict(list)
    for chave, item in {**AGENDA_PADRAO, **agenda}.items():
        cls = item.get('conector')
        if cls and chave in catalogo and catalogo[chave] not in por_nome[cls.FONTE['nome']]:
            por_nome[cls.FONTE['nome']].append(catalogo[chave])
    cadastrados = _localidades_fontes(conn)
    for leitor in leitores:
        leitor['localidades'] = cadastrados.get(leitor['fonte_id']) or por_nome.get(leitor['fonte'], [])
    leitores.sort(key=lambda r: (r["fonte"] or "", r["recurso"] or ""))
    return {"gerado_em": atualizacoes.agora(), "total": len(leitores), "erro_agenda": erro_agenda, "erro_relatorio": erro_relatorio,
            "erro_localidades": erro_localidades,
            "resumo": dict(Counter(r["estado"] for r in leitores)),
            "estados": [{"uf": uf, "nome": NOMES[uf]} for uf, _ in UFS],
            "coletores": atualizacoes.limpar(leitores)}


def _leitor(conn, r, chave, item, diario):
    ultima = sucesso = None
    classe = item.get("conector")
    modo = getattr(classe, "MODO_COLETA", "cadastro")
    if r["id"] is not None:
        ultima = db.query_one(conn, "SELECT * FROM EXECUCAO_COLETA WHERE recurso_id=? ORDER BY id DESC LIMIT 1", (r["id"],))
        sucessos = "status IN ('documentado','sem_mudanca') AND linhas_validas>0" if modo == "documental" else "status IN ('ok','sem_mudanca')"
        sucesso = db.query_one(conn, "SELECT * FROM EXECUCAO_COLETA WHERE recurso_id=? AND " + sucessos + " ORDER BY id DESC LIMIT 1", (r["id"],))
    ativo = bool(r["ativo"]) and r["situacao"] == "ativa" and item.get("ativo", True)
    estado = ultima["status"] if ultima else "nunca_coletado"
    diario = diario if isinstance(diario, dict) and ultima and diario.get("execucao_id") == ultima["id"] else {}
    if diario.get("estado") == "interrompido":
        estado = "interrompido"
    origem = diario.get("origem")
    url_lida = origem if isinstance(origem, str) and origem.startswith(("https://", "http://")) else None
    intervalo = item.get("intervalo_s", r["periodicidade_segundos"])
    atraso = None
    if ativo and ultima and estado in ("ok", "sem_mudanca", "documentado") and intervalo:
        try:
            ts = dt.datetime.fromisoformat(ultima["iniciada_em"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            # Um tick por minuto e tolerancia de 5 minutos antes de sinalizar.
            atraso = dt.datetime.now(dt.timezone.utc) > ts + dt.timedelta(seconds=intervalo + 300)
        except (ValueError, TypeError):
            pass
    erros = []
    if ultima:
        erros = [dict(e) for e in conn.execute("""
            SELECT codigo_erro, descricao, severidade, registrado_em
            FROM ERRO_VALIDACAO WHERE execucao_id=? ORDER BY id
        """, (ultima["id"],))]
    return dict(r, conector=chave, agendado=chave is not None, ativo=ativo,
                tipo_coleta=modo, descricao_coleta=getattr(classe, "DESCRICAO_COLETA", None),
                intervalo_s=intervalo, estado=estado, leitura_atrasada=atraso,
                ultima_tentativa=dict(ultima) if ultima else None,
                ultimo_sucesso=dict(sucesso) if sucesso else None,
                url_configurada=item.get("url_direta") or r["url_recurso"],
                url_ultima_tentativa=url_lida, erro_relatorio_coleta=diario.get("erro"), erros=erros)
