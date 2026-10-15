# -*- coding: utf-8 -*-
"""Visao canonica derivada das decisoes aplicadas, sem alterar a origem.

Pontos e instrumentos formam grafos separados. A visao e reconstruida em
cada operacao: remover uma aresta nao pode deixar aliases de outra decisao
apontando para um grupo que deixou de existir.
"""
import json

from . import db


##-- BUNDITA DE URSO #{2} -- Identidade do instrumento nao implica identidade do ponto de instalacao. ##
TIPOS = {
    "ponto": ("VINCULO_REGISTRO_PONTO", "ponto_id"),
    "equipamento": ("VINCULO_REGISTRO_EQUIPAMENTO", "equipamento_id"),
}
ESCOPOS = {"ponto": ("ponto",), "equipamento": ("equipamento",),
           "ambos": ("ponto", "equipamento")}


def objeto(texto):
    try:
        valor = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}
    return valor if isinstance(valor, dict) else {}


def originais(conn, tipo, registro_id):
    tabela, coluna = TIPOS[tipo]
    return [r[0] for r in conn.execute(
        "SELECT %s FROM %s WHERE registro_id=? AND decisao_id IS NULL "
        "ORDER BY %s" % (coluna, tabela, coluna), (registro_id,))]


##-- BUNDITA DE URSO #{1} -- A API ignorava os aliases e continuava exibindo pontos e instrumentos duplicados. ##
class VisaoCanonica:
    def __init__(self, conn):
        self.mapas = {tipo: {} for tipo in TIPOS}
        self.grupos = {tipo: {} for tipo in TIPOS}
        self.decisoes = []
        rows = db.query_all(conn, """
            SELECT d.*, c.registro_a_id, c.registro_b_id, c.estado,
                   c.evidencias_resumo
            FROM DECISAO_DUPLICIDADE d
            JOIN CANDIDATO_DUPLICIDADE c ON c.id=d.candidato_id
            WHERE d.revertida_em IS NULL AND d.decisao='unificar'
              AND NOT EXISTS (
                SELECT 1 FROM DECISAO_DUPLICIDADE posterior
                WHERE posterior.candidato_id=d.candidato_id
                  AND posterior.revertida_em IS NULL AND posterior.id>d.id)
            ORDER BY d.id""")
        for row in rows:
            obs = objeto(row["observacoes"])
            # Compatibilidade com decisoes aplicadas antes de existir escopo.
            legado = ("escopo" not in obs and row["estado"] == "consolidado"
                      and objeto(row["evidencias_resumo"]).get("aplicado_em"))
            if not obs.get("aplicada_em") and not legado:
                continue
            tipos = ESCOPOS.get(obs.get("escopo", "ambos"), ())
            entidades = obs.get("entidades")
            if entidades is None:
                entidades = {
                    tipo: {str(rid): originais(conn, tipo, rid)
                           for rid in (row["registro_a_id"], row["registro_b_id"])}
                    for tipo in tipos}
            self.decisoes.append({"id": row["id"],
                                  "candidato_id": row["candidato_id"],
                                  "entidades": entidades, "tipos": tipos})

        for tipo, (tabela, coluna) in TIPOS.items():
            parents = {}

            def raiz(item):
                parents.setdefault(item, item)
                while parents[item] != item:
                    parents[item] = parents[parents[item]]
                    item = parents[item]
                return item

            for decisao in self.decisoes:
                if tipo not in decisao["tipos"]:
                    continue
                ids = sorted({item for valores in
                              decisao["entidades"].get(tipo, {}).values()
                              for item in valores})
                for item in ids[1:]:
                    parents[raiz(item)] = raiz(ids[0])
                if ids:
                    raiz(ids[0])
            if not parents:
                continue
            oficiais = {r[0] for r in conn.execute("""
                SELECT DISTINCT v.%s FROM %s v
                JOIN REGISTRO_FONTE r ON r.id=v.registro_id
                JOIN ARTEFATO_COLETA a ON a.id=r.artefato_id
                JOIN RECURSO_FONTE rf ON rf.id=a.recurso_id
                JOIN FONTE f ON f.id=rf.fonte_id
                JOIN NATUREZA_FONTE n ON n.id=f.natureza_id
                WHERE v.decisao_id IS NULL AND n.codigo='oficial'
                """ % (coluna, tabela))}
            componentes = {}
            for item in parents:
                componentes.setdefault(raiz(item), []).append(item)
            for membros in componentes.values():
                canonico = min(membros, key=lambda i: (i not in oficiais, i))
                self.grupos[tipo][canonico] = sorted(membros)
                self.mapas[tipo].update({item: canonico for item in membros})
        self._validar_separacoes(conn)

    ##-- BUNDITA DE URSO #{3} -- Unificacoes transitivas nao podem contrariar uma decisao ativa de manter separados. ##
    def _validar_separacoes(self, conn):
        for row in conn.execute("""
                SELECT d.*, c.registro_a_id, c.registro_b_id
                FROM DECISAO_DUPLICIDADE d
                JOIN CANDIDATO_DUPLICIDADE c ON c.id=d.candidato_id
                WHERE d.decisao='manter_separados' AND d.revertida_em IS NULL
                  AND NOT EXISTS (SELECT 1 FROM DECISAO_DUPLICIDADE posterior
                    WHERE posterior.candidato_id=d.candidato_id
                      AND posterior.revertida_em IS NULL AND posterior.id>d.id)
                """):
            obs = objeto(row["observacoes"])
            for tipo in ESCOPOS.get(obs.get("escopo") or "ambos", ()):
                entidades = obs.get("entidades", {}).get(tipo, {})
                a, b = (entidades.get(str(row[chave]), originais(conn, tipo, row[chave]))
                        for chave in ("registro_a_id", "registro_b_id"))
                if {self.canonico(tipo, i) for i in a} & {self.canonico(tipo, i) for i in b}:
                    raise ValueError("unificacao conflita com decisao ativa de manter separados (%s)" % row["id"])

    def canonico(self, tipo, entidade_id):
        return self.mapas[tipo].get(entidade_id, entidade_id)

    def membros(self, tipo, entidade_id):
        canonico = self.canonico(tipo, entidade_id)
        return self.grupos[tipo].get(canonico, [canonico])

    def aliases(self, tipo):
        return sorted(i for i, c in self.mapas[tipo].items() if i != c)


##-- BUNDITA DE URSO #{3} -- Reverter A-B deixava B-C ativo com vinculos inconsistentes; recalcular o grafo restante. ##
def reconstruir_vinculos(conn):
    """Reconstroi apenas os vinculos derivados, dentro da transacao do chamador."""
    visao = VisaoCanonica(conn)
    for tipo, (tabela, coluna) in TIPOS.items():
        conn.execute("DELETE FROM %s WHERE decisao_id IN "
                     "(SELECT id FROM DECISAO_DUPLICIDADE)" % tabela)
        for decisao in visao.decisoes:
            if tipo not in decisao["tipos"]:
                continue
            for rid, entidades in decisao["entidades"].get(tipo, {}).items():
                for entidade in entidades:
                    conn.execute(
                        "INSERT OR IGNORE INTO %s (registro_id, %s, decisao_id) "
                        "VALUES (?,?,?)" % (tabela, coluna),
                        (int(rid), visao.canonico(tipo, entidade), decisao["id"]))
    return visao
