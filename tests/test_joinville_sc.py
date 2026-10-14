# -*- coding: utf-8 -*-
"""Testes offline do conector Joinville DETRANS - SC (estudos tecnicos).

Nenhum teste acessa a rede: usam a fixture HTML local e substituem
``coletor.http.baixar``. O ponto central: a fonte NAO publica recurso
estruturado de radares; os estudos tecnicos em PDF sao descobertos e
preservados, mas NUNCA viram ponto/trecho/radar inventado.
"""
import os
import unittest
from unittest import mock

from coletor import http
from coletor.fontes.joinville_sc import ColetorJoinville
from core import config
from core import db as dbmod
import tests.common as common

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(nome):
    return os.path.join(FIXTURES, nome)


def _resp(texto, url="https://x/"):
    dados = texto if isinstance(texto, bytes) else texto.encode("utf-8")
    return (dados, {}, url)


class TestJoinvilleSC(unittest.TestCase):

    def test_carregar_descobre_documentos(self):
        c = ColetorJoinville()
        _, ext, mime, regs = c.carregar(fx("joinville_estudos_fixture.html"))
        self.assertEqual(ext, ".html")
        self.assertIn("html", mime)
        self.assertEqual(len(regs), 7)
        self.assertTrue(all(d["url"].endswith(".pdf") for d in regs))
        cats = {d["categoria"] for d in regs}
        self.assertIn("atualizacao_bienal_locais_fiscalizacao", cats)
        self.assertIn("estudo_tecnico_redutor", cats)
        self.assertIn("estudo_tecnico_controlador", cats)

    def test_categoria_e_ano_mes(self):
        html = ('<a href="https://www.joinville.sc.gov.br/wp-content/uploads/'
                '2026/08/Atualizacao-Bienal-dos-Locais-de-Fiscalizacao-com-'
                'Radares.pdf">Atualizacao Bienal</a>')
        docs = ColetorJoinville.descobrir_documentos(html)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["categoria"],
                         "atualizacao_bienal_locais_fiscalizacao")
        self.assertEqual(docs[0]["ano_mes"], "2026-08")

    def test_documentos_deduplicados(self):
        html = ('<a href="/a.pdf">x</a><a href="/a.pdf">x dup</a>'
                '<a href="/b.pdf">y</a>')
        docs = ColetorJoinville.descobrir_documentos(html)
        self.assertEqual(len(docs), 2)

    def test_normalizar_nunca_fabrica_radar(self):
        c = ColetorJoinville()
        _, _, _, regs = c.carregar(fx("joinville_estudos_fixture.html"))
        for i, r in enumerate(regs):
            self.assertIsNone(c.normalizar(i, r))
        # nem mesmo um registro com "radar" no titulo vira ponto
        self.assertIsNone(c.normalizar(0, {
            "url": "https://x/radar.pdf", "titulo": "Radar 60 km/h",
            "categoria": "estudo_tecnico"}))

    def test_resolver_url_pagina_oficial(self):
        url = ColetorJoinville.resolver_url()
        self.assertEqual(url, ColetorJoinville.PAGINA)
        self.assertTrue(url.startswith("https://"))

    def test_download_passa_por_http_baixar(self):
        with open(fx("joinville_estudos_fixture.html"), "rb") as f:
            html = f.read()
        with mock.patch.object(http, "baixar",
                               return_value=_resp(html)) as m:
            _, _, _, regs = ColetorJoinville().carregar(
                ColetorJoinville.PAGINA)
        self.assertTrue(m.called)
        self.assertEqual(len(regs), 7)

    def test_sincronizar_preserva_evidencia_sem_pontos(self):
        common.ambiente_temporario()
        c = ColetorJoinville(db_path=config.DB_PATH)
        try:
            res = c.sincronizar(fx("joinville_estudos_fixture.html"))
            self.assertEqual(res["linhas_recebidas"], 7)
            self.assertEqual(res["criados"], 0)     # nada normalizado
            self.assertEqual(res["rejeitados"], 7)  # documentos: sem destino
            # evidencia bruta preservada; nenhum radar/trecho inventado
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM REGISTRO_FONTE"), 7)
            self.assertEqual(
                dbmod.scalar(c.conn,
                             "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 0)
            self.assertEqual(
                dbmod.scalar(c.conn, "SELECT COUNT(*) FROM TRECHO_ELEGIVEL"),
                0)
        finally:
            c.conn.close()


if __name__ == "__main__":
    unittest.main()
