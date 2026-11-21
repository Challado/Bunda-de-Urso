from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import caminhos, config, db, dump_radares, governanca, politica_acesso
from web import nucleo


class PoliticaAcessoTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.conf = self.raiz / "radar.conf"
        self.banco = self.raiz / "radar.sqlite3"
        self.gravar()
        env = patch.dict(os.environ, RADAR_CONF=str(self.conf))
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(caminhos.recarregar)
        patch_banco = patch.object(config, "DB_PATH", str(self.banco))
        patch_banco.start()
        self.addCleanup(patch_banco.stop)

    def gravar(self, extras=""):
        self.conf.write_text(f"[dados]\ndir = {self.raiz}\n[web]\nurl = /radar/\n" + extras)
        caminhos.recarregar()

    def req(self, rota="/api/v1/radares/busca", query="", metodo="GET", **headers):
        return nucleo.handle_request(dict(REQUEST_METHOD=metodo, PATH_INFO=rota,
                                           QUERY_STRING=query, **headers))

    def test_recusa_limites_e_rotas_internas_sem_abrir_banco(self):
        with patch.object(nucleo, "_conn", side_effect=AssertionError("abriu o banco")):
            for rota in ("/api/v1/status/coletores", "/api/v1/intercambio/identidade",
                         "/api/v1/intercambio/trocar", "/api/v1/gestao/nao-existe",
                         "/api/v1/atualizacoes/status", "/api/v1/radares/envios/inexistente"):
                with self.subTest(rota=rota):
                    self.assertEqual(self.req(rota)[0], 401)
            for limite in (201, 4000, 5000):
                self.assertEqual(self.req(query=f"limite={limite}")[0], 422)
            status, _, corpo = self.req(query="limite=200&cursor=2001")
            self.assertEqual(status, 401)
            self.assertTrue(corpo["erro"]["download_url"].endswith(politica_acesso.ROTA_DUMP))
            self.assertEqual(self.req("/api/v1/interface")[2]["resultado"]["limite_consulta"], 200)

    def test_chave_de_leitura_habilita_cursor_sem_dar_acesso_interno(self):
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
        chave = "chave-local-de-validacao-" + "x" * 24
        (self.raiz / "chaves_leitura.sha256").write_text(hashlib.sha256(chave.encode()).hexdigest()+"\n")
        self.assertEqual(self.req(query="cursor=2000")[0], 200)
        self.assertEqual(self.req(query="cursor=2001", HTTP_X_RADAR_LEITURA="incorreta")[0], 401)
        self.assertEqual(self.req(query="cursor=2001", HTTP_X_RADAR_LEITURA=chave)[0], 200)
        self.assertEqual(self.req("/api/v1/status/coletores", HTTP_X_RADAR_LEITURA=chave)[0], 401)

    def test_liberacoes_e_bloqueios_com_regex_cidr_e_intervalo(self):
        self.gravar('''[abuso]
bloqueios = [
    [{"user_agent_regex":"(?i)coletor"}],
    [{"user_agent_regex":"^bot=v2$","status":429}]
    ]
liberacoes =
    [
    [{"rota":"/api/v1/radares/busca","user_agent_regex":"^Coletor aprovado$","redes":["192.0.2.10-192.0.2.20"]}],
    [{"rota":"/api/v1/radares/envios","redes":["2001:db8::/64"]},
    {"rota":"/api/v1/radares/envios","user_agent_regex":"^ClienteApp/[1-9]$"}]
    ]
janela_segundos = 900
[api]
limite_consulta = 100
''')
        self.assertEqual(caminhos.problemas(), [])
        self.assertEqual(caminhos.inteiro("abuso", "janela_segundos"), 900)
        self.assertEqual(politica_acesso.limite(), 100)
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
        self.assertEqual(self.req(HTTP_USER_AGENT="Coletor aprovado", REMOTE_ADDR="192.0.2.21")[0], 403)
        self.assertEqual(self.req(HTTP_USER_AGENT="bot=v2")[0], 429)
        self.assertEqual(self.req(HTTP_USER_AGENT="Coletor aprovado", REMOTE_ADDR="192.0.2.20")[0], 200)
        self.assertEqual(self.req(query="cursor=2001", HTTP_USER_AGENT="Coletor aprovado",
                                  REMOTE_ADDR="192.0.2.20")[0], 401)
        envio = "/api/v1/radares/envios/identificador"
        self.assertEqual(self.req(envio, REMOTE_ADDR="2001:db8::1")[0], 404)
        self.assertEqual(self.req(envio, HTTP_USER_AGENT="ClienteApp/2")[0], 404)
        self.assertEqual(self.req(envio, REMOTE_ADDR="192.0.2.20", HTTP_USER_AGENT="Coletor aprovado")[0], 401)
        self.assertEqual(self.req(envio, REMOTE_ADDR="192.0.2.21", HTTP_X_FORWARDED_FOR="2001:db8::1")[0], 401)

    def test_listas_agrupadas_e_listas_simples_de_uma_linha(self):
        grupo = '[{"user_agent_regex":"bot","status":429},{"redes":["192.0.2.0/24"]}]'
        terceira = '[{"user_agent_regex":"robo"}]'
        regras = politica_acesso.ler_bloqueios(f'[{grupo},{terceira}]')
        self.assertEqual([regra.status for regra in regras], [429, 403, 403])
        self.assertEqual(politica_acesso.ler_bloqueios(grupo), regras[:2])
        with self.assertRaisesRegex(ValueError, "até 100 regras"):
            politica_acesso.ler_bloqueios(json.dumps([[{"user_agent_regex": "bot"}] * 101]))

    def test_cota_resiste_a_troca_de_agente_e_ip_na_mesma_rede(self):
        self.gravar("[abuso]\nmax_paginas_grandes = 2\n")
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
        with patch('core.politica_acesso.time.time', return_value=640):
            for ip in ("192.0.2.4", "192.0.2.5"):
                self.assertEqual(self.req(query="cursor=100&limite=200", REMOTE_ADDR=ip)[0], 200)
            status, headers, _ = self.req(query="cursor=0&limite=200",
                                          REMOTE_ADDR="192.0.2.6", HTTP_USER_AGENT="outro agente")
            self.assertEqual(status, 429)
            self.assertEqual(headers["Retry-After"], "560")
            self.assertEqual(self.req(query="cursor=100&limite=100", REMOTE_ADDR="192.0.2.7")[0], 200)
        with patch('core.politica_acesso.time.time', return_value=1201):
            self.assertEqual(self.req(query="cursor=100&limite=200", REMOTE_ADDR="192.0.2.4")[0], 200)

    def test_limite_zero_retorna_mais_de_200_pontos(self):
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
            conn.executemany("INSERT INTO PONTO_FISCALIZACAO (id) VALUES (?)",
                             [(pid,) for pid in range(1, 206)])
            conn.commit()
        status, _, corpo = self.req(query="limite=0&cursor=1")
        self.assertEqual(status, 200)
        resultado = json.loads(corpo)["resultado"]
        self.assertEqual([p["id"] for p in resultado["pontos"]], [f"P-{i}" for i in range(2, 206)])
        self.assertIsNone(resultado["proximo_cursor"])

    def test_consulta_sem_limite_usa_a_cota_de_paginas_grandes(self):
        self.gravar("[abuso]\nmax_paginas_grandes = 1\n")
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
        self.assertEqual(self.req(query="limite=0", REMOTE_ADDR="192.0.2.4")[0], 200)
        self.assertEqual(self.req(query="limite=0", REMOTE_ADDR="192.0.2.4")[0], 429)

    def test_dump_diario_publico_condicional_sem_consultar_banco_no_http(self):
        with closing(db.connect(self.banco)) as conn:
            governanca.garantir_esquema(conn)
            conn.execute("INSERT INTO ponto_fiscalizacao(id,km) VALUES (1,10.5)")
            conn.execute("INSERT INTO ponto_fiscalizacao(id,removido_em) VALUES (2,'2026-11-19')")
            conn.commit()
        agora = datetime(2026,11,19,tzinfo=timezone.utc)
        self.assertEqual(dump_radares.gerar(agora)["total_pontos"], 1)
        self.assertEqual(dump_radares.gerar(agora + timedelta(hours=3))["estado"], "atual")
        with patch('core.dump_radares._gravar', side_effect=RuntimeError('falha de geração')):
            with self.assertRaises(RuntimeError):
                dump_radares.gerar(agora + timedelta(days=1))
        rota = politica_acesso.ROTA_DUMP
        with patch.object(nucleo, "_conn", side_effect=AssertionError("abriu banco")):
            status, headers, corpo = self.req(rota)
            self.assertEqual(status,200)
            status_post, headers_post, corpo_post = self.req(rota, metodo="POST")
            saida = io.BytesIO()
            corpo.copiar(saida)
            saida_post = io.BytesIO()
            corpo_post.copiar(saida_post)
            self.assertEqual((status_post, headers_post, saida_post.getvalue()),
                             (status, headers, saida.getvalue()))
            dados = json.loads(gzip.decompress(saida.getvalue()))
            self.assertEqual([p["id"] for p in dados["pontos"]], ["P-1"])
            self.assertIn("licenca", dados["atribuicao"])
            self.assertEqual(self.req(rota, HTTP_IF_NONE_MATCH=headers["ETag"])[0], 304)
            self.assertEqual(self.req(rota, HTTP_IF_MODIFIED_SINCE=headers["Last-Modified"])[0], 304)
            self.assertEqual(self.req(rota, metodo="HEAD")[1]["Content-Length"], headers["Content-Length"])

    def test_prazo_cgi_interrompe_processo_de_consulta(self):
        self.gravar("[api]\ntimeout_consulta = 1\n")
        script = ("import time; from web import nucleo; "
                  "nucleo.handle_request=lambda *a: time.sleep(20); nucleo.main({})")
        resp = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=5, check=True)
        self.assertIn(b"Status: 504", resp.stdout)
        self.assertIn(b"prazo_excedido", resp.stdout)
