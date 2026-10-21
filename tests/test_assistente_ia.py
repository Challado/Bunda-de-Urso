"""IA opcional: rede zero desligada, contrato HTTP real e segredo fora das respostas."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from core import assistente_ia as ia, caminhos
from core.manutencao import consultar_nomes_pendentes as municipios


class AmbienteIA(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="radar-ia-teste-")
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.conf = self.raiz / "radar.conf"
        self.web = self.raiz / "web"
        self.web.mkdir()
        self.env = patch.dict(os.environ, {**{k: v for k, v in os.environ.items() if not k.startswith(("RADAR_", "OLLAMA_"))},
                                          "RADAR_CONF": str(self.conf)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(caminhos.recarregar)
        self.addCleanup(setattr, ia, "_chamadas", ia._chamadas)
        ia._chamadas = 0
        self.escrever()

    def escrever(self, habilitado=0, provedor="ollama", url="http://127.0.0.1:11434", extras=""):
        self.conf.write_text("[web]\nraiz = %s\n[dados]\ndir = %s\n[assistente]\nhabilitado = %s\nprovedor = %s\nurl = %s\nmodelo = modelo-teste\n%s" %
                             (self.web, self.raiz / "dados", habilitado, provedor, url, extras))
        caminhos.recarregar()


class TestClienteIA(AmbienteIA):
    def setUp(self):
        super().setUp()
        self.pedidos = []
        self.modo = "ok"
        caso = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                caso.pedidos.append((self.path, dict(self.headers), corpo))
                if caso.modo == "redirecionar":
                    self.send_response(302)
                    self.send_header("Location", "/outro-destino")
                    self.end_headers()
                    return
                self.send_response(429 if caso.modo == "erro" else 200)
                self.end_headers()
                if caso.modo == "erro":
                    self.wfile.write(b'erro com conteudo sensivel do provedor')
                elif caso.modo == "excessivo":
                    self.wfile.write(b"x" * 131073)
                elif caso.modo == "invalido":
                    self.wfile.write(b"nao e JSON")
                else:
                    texto = json.dumps({"ordem": ["F1"]})
                    self.wfile.write(json.dumps({"response": texto, "choices": [{"message": {"content": texto}}]}).encode())
            def log_message(self, *args):
                pass
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.fechar)
        self.url = "http://127.0.0.1:%d" % self.servidor.server_port

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(timeout=3)

    def test_desligada_nao_le_chave_nao_cria_cliente_e_alcanca_ferramenta_antiga(self):
        with patch.object(ia, "_chave", side_effect=AssertionError("nao ler chave")), \
                patch.object(ia.urllib.request, "build_opener", side_effect=AssertionError("nao montar rede")):
            for funcao in ia.FUNCOES:
                self.assertFalse(ia.consultar_json(funcao, "instrucao", {})["usou_ia"])
            self.assertIsNone(municipios.perguntar_modelo(self.url, "teste", "Cidade", "PR"))
        self.assertEqual(self.pedidos, [])

    def test_bloqueio_por_funcao_e_sem_ia_independente_do_interruptor(self):
        self.escrever(1, url=self.url, extras="documentos = 0\n")
        self.assertFalse(ia.consultar_json("documentos", "i", {})["usou_ia"])
        self.assertFalse(ia.consultar_json("explicacoes", "i", {}, sem_ia=True)["usou_ia"])
        self.assertEqual(self.pedidos, [])

    def test_proposta_de_municipio_por_modelo_nao_e_aplicada_automaticamente(self):
        propostas = [{"codigo": "4106902", "origem": "modelo_validado", "pontos": [1]}]
        with patch.object(municipios.shutil, "copy2", side_effect=AssertionError("nao alterar banco")):
            self.assertEqual(municipios.aplicar(propostas, str(self.raiz / "inexistente.sqlite3")), 0)

    def test_ollama_http_real_sem_chave(self):
        self.escrever(1, url=self.url)
        r = ia.consultar_json("explicacoes", "Ordenar fatos", {"fatos": [{"id": "F1"}]})
        self.assertTrue(r["usou_ia"])
        caminho, cabecalhos, corpo = self.pedidos[0]
        self.assertEqual(caminho, "/api/generate")
        self.assertNotIn("Authorization", cabecalhos)
        self.assertEqual(corpo["model"], "modelo-teste")

    def test_api_externa_http_local_de_teste_e_chave_somente_no_cabecalho(self):
        self.escrever(1, "openai_compativel", self.url + "/v1")
        segredo = "chave_apenas_de_teste_12345"
        ia.salvar_chave({"chave": segredo})
        r = ia.consultar_json("explicacoes", "Ordenar", {"fatos": [{"id": "F1"}]})
        self.assertTrue(r["usou_ia"])
        caminho, cabecalhos, corpo = self.pedidos[0]
        self.assertEqual(caminho, "/v1/chat/completions")
        self.assertEqual(cabecalhos["Authorization"], "Bearer " + segredo)
        self.assertNotIn(segredo, json.dumps(corpo))
        self.assertNotIn(segredo, json.dumps(r))
        self.assertNotIn(segredo, json.dumps(ia.status()))
        self.assertNotIn(segredo, self.conf.read_text())
        self.assertEqual(ia.arquivo_chave().stat().st_mode & 0o777, 0o660)

    def test_sem_chave_sem_https_ou_limite_nao_faz_requisicao(self):
        self.escrever(1, "openai_compativel", self.url)
        self.assertEqual(ia.consultar_json("explicacoes", "i", {})["motivo"], "chave_ausente")
        self.escrever(1, "openai_compativel", "http://exemplo.invalid/v1")
        self.assertEqual(ia.consultar_json("explicacoes", "i", {})["motivo"], "configuracao_invalida")
        self.escrever(1, url=self.url, extras="max_entrada = 1000\n")
        self.assertEqual(ia.consultar_json("explicacoes", "i", {"grande": "x" * 1200})["motivo"], "limite_entrada")
        self.assertEqual(self.pedidos, [])

    def test_erros_redirecionamento_e_resposta_excessiva_usam_alternativa(self):
        self.escrever(1, url=self.url)
        for modo in ("erro", "invalido", "redirecionar", "excessivo"):
            with self.subTest(modo=modo):
                self.modo = modo
                self.assertFalse(ia.consultar_json("explicacoes", "i", {})["usou_ia"])
        self.assertEqual(len(self.pedidos), 4)

    def test_limite_de_chamadas(self):
        self.escrever(1, url=self.url, extras="max_chamadas = 1\n")
        self.assertTrue(ia.consultar_json("explicacoes", "i", {})["usou_ia"])
        self.assertEqual(ia.consultar_json("explicacoes", "i", {})["motivo"], "limite_chamadas")
        self.assertEqual(len(self.pedidos), 1)
