"""Instalacao em laboratorio: preservacao, repeticao, falha e cron alheio."""
from contextlib import closing
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import fcntl
import time

from core import db
from core.instalacao import _cron_tick
from core.instalacao import _esperar_coletor
from core.instalacao import _preparar_servicos
from core import auditoria_instalacao
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TestInstalacaoAPI(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="radar-instalar-teste-")
        self.addCleanup(tmp.cleanup)
        self.lab = Path(tmp.name)
        self.home = self.lab / "bin" / "radar"
        self.home.mkdir(parents=True)
        (self.home / "core").mkdir()
        (self.home / "ANTERIOR").write_text("versao antiga")
        (self.home / "config").mkdir()
        (self.home / "config" / "governanca.json").write_text('{"SUBMISSAO_LIMITE":7}')
        self.web = self.lab / "www" / "radar"
        self.web.mkdir(parents=True)
        (self.web / "api.pse").write_text("# entrada antiga")
        self.dados = self.lab / "dados"
        self.dados.mkdir()
        self.banco = self.dados / "radar.sqlite3"
        with closing(db.connect(self.banco)) as conn:
            db.init_db(conn)
            conn.execute("CREATE TABLE SENTINELA (valor TEXT)")
            conn.execute("INSERT INTO SENTINELA VALUES ('nao perder')")
            conn.commit()
        self.conf = self.lab / "etc" / "radar" / "radar.conf"
        self.conf.parent.mkdir(parents=True)
        self.conf.write_text("# configuracao do servidor\n[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[web]\nraiz = %s\nurl = /teste/\n[logs]\ndir = %s\n" %
                             (self.home, self.dados, self.banco, self.web, self.dados / "logs"))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("RADAR_") and k not in ("REQUEST_METHOD", "GATEWAY_INTERFACE")}
        self.env["RADAR_CONF"] = str(self.conf)
        self.externo = self.home.parent / "radar-dados-sync.py"
        self.externo.write_text("# ESPECIFICO DO SERVIDOR, NAO ALTERAR")

    def instalar(self, aplicar=False, extras=()):
        return subprocess.run([sys.executable, str(ROOT / "web" / "api.pse"), "instalacao", "--conf", str(self.conf),
                               "--laboratorio", str(self.lab), "--usuario-web", getpass.getuser(),
                               *(["--aplicar"] if aplicar else []), *extras], env=self.env,
                              capture_output=True, text=True, timeout=120)

    def test_simulacao_nao_modifica_instalacao(self):
        antes = {str(p.relative_to(self.lab)): p.read_bytes() for p in self.lab.rglob("*") if p.is_file()}
        resultado = self.instalar()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        depois = {str(p.relative_to(self.lab)): p.read_bytes() for p in self.lab.rglob("*") if p.is_file()}
        self.assertEqual(antes, depois)

    def test_aplicar_repetir_preserva_config_banco_e_rotina_externa(self):
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn("submissao_limite = 7", self.conf.read_text())
        self.conf.write_text(self.conf.read_text().replace("submissao_limite = 7", "submissao_limite = 11"))
        conf_antes = self.conf.read_bytes()
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual(self.conf.read_bytes(), conf_antes)
        self.assertIn("NAO ALTERAR", self.externo.read_text())
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='IX_EQUIPAMENTO_SERIE_TIPO'").fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='IX_DOCUMENTO_VERIFICACAO_ALVO'").fetchone())
        self.assertTrue((self.home / "core" / "entrada_api.py").is_file())
        ambiente_cgi = {k: v for k, v in self.env.items() if k != "RADAR_CONF"}
        ambiente_cgi.update(REQUEST_METHOD="GET", QUERY_STRING="rota=/health/ready", SCRIPT_NAME="/api.pse")
        cgi = subprocess.run([sys.executable, str(self.web / "api.pse")], env=ambiente_cgi,
                             capture_output=True, text=True, timeout=15)
        self.assertIn("Status: 200 OK", cgi.stdout)
        self.assertFalse((self.web / "nucleo.py").exists())
        self.assertEqual([p for p in self.web.rglob("*") if p.is_symlink()], [self.web / "radar.conf"])
        self.assertEqual((self.web / "radar.conf").resolve(), self.conf)
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o660)
        self.assertEqual(self.conf.parent.stat().st_mode & 0o7777, 0o2770)
        self.assertEqual(len(list((self.dados / "backups" / "instalacao").glob("*/CONCLUIDO"))), 1)
        self.assertIn("sem nova copia ou backup", resultado.stdout)
        wrapper = self.home.parent / "radar-tick.sh"
        ensaio = subprocess.run(["sh", str(wrapper), "--help"], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(ensaio.returncode, 0, ensaio.stderr)
        self.assertTrue((self.dados / "logs" / "tick.log").is_file())

    def test_recuperacao_explicita_preserva_banco(self):
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        backup = next((self.dados / "backups" / "instalacao").iterdir())
        resultado = subprocess.run([sys.executable, str(ROOT / "web" / "api.pse"), "instalacao", "--conf", str(self.conf),
                                   "--laboratorio", str(self.lab), "--restaurar", str(backup)],
                                  env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertEqual((self.home / "ANTERIOR").read_text(), "versao antiga")
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")

    def test_atualizacao_preserva_link_publico_do_relatorio(self):
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        publico = self.web / "status-atualizacoes.json"
        # Forma usada no servidor: web -> aplicativo -> dados persistentes.
        publico.symlink_to(self.home / "status-atualizacoes.json")
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(publico.is_symlink())
        self.assertEqual(publico.resolve(), self.dados / "atualizacoes" / "status.json")
        self.assertIn("operacoes", json.loads(publico.read_text()))
        # Tambem funciona na copia efetiva do codigo/web, nao apenas no atalho
        # que detecta uma revisao ja instalada.
        (self.home / "core" / "entrada_api.py").write_text("# divergente")
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("operacoes", json.loads(publico.read_text()))
        # Mesmo nome apontando para outro arquivo continua recusado.
        publico.unlink()
        publico.symlink_to(self.conf)
        r = self.instalar(True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Revise o link existente", r.stderr)

    def test_falha_restaura_codigo_web_e_config_sem_apagar_banco(self):
        (self.web / "nucleo.py").write_text("# fonte antigo indevido no webroot")
        antes_conf = self.conf.read_bytes()
        resultado = self.instalar(True)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("restaurados", resultado.stderr)
        self.assertEqual((self.home / "ANTERIOR").read_text(), "versao antiga")
        self.assertEqual((self.web / "api.pse").read_text(), "# entrada antiga")
        self.assertEqual(self.conf.read_bytes(), antes_conf)
        relatorio = json.loads(next((self.dados / "backups" / "instalacao").glob("*/checagem-final.json")).read_text())
        self.assertFalse(relatorio["sucesso"])
        self.assertTrue(relatorio["recuperacao_automatica"])
        self.assertTrue(relatorio["observacoes"])
        self.assertIn("Observacoes:", resultado.stdout)
        status = json.loads((self.home / "status-atualizacoes.json").read_text())["operacoes"]["instalacao"]
        self.assertEqual(status["estado"], "erro")
        self.assertTrue(status["recuperacao_automatica"])
        self.assertTrue(status["erros"])
        self.assertIn("RuntimeError", status["traceback"])
        self.assertTrue(Path(status["arquivo_relatorio"]).is_file())
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")

    def test_cron_preserva_envio_privado_e_outros_projetos(self):
        wrapper = self.home.parent / "radar-tick.sh"
        externo = "*/10 * * * * python3 %s >> /logs/dados-sync.log 2>&1" % self.externo
        outro = "6 1 * * * /outro/projeto/bkpremoto.sh"
        texto = externo + "\n" + outro + "\n* * * * * " + str(wrapper) + " >> /logs/antigo.log 2>&1\n"
        novo = _cron_tick(texto, wrapper)
        self.assertIn(externo + "\n", novo)
        self.assertIn(outro + "\n", novo)
        self.assertEqual(novo, _cron_tick(novo, wrapper))

    def test_cron_corrige_versoes_antigas_duplicadas_e_nao_confunde_avisos(self):
        wrapper = self.home.parent / "radar-tick.sh"
        linhas = ["*/5 * * * * /antigo/bin/radar-tick.sh >> /logs/velho 2>&1",
                  "*/3 * * * * python3 /antigo/radar/coletor/tick.py",
                  "*/2 * * * * python3 /antigo/radar/web/api.pse tick",
                  "*/2 * * * * python3 /antigo/radar-api.pse cron tick",
                  "* * * * * echo /antigo/bin/radar-tick.sh",
                  "# * * * * * /antigo/bin/radar-tick.sh"]
        novo = _cron_tick("\n".join(linhas) + "\n", wrapper)
        self.assertEqual(novo.splitlines(), linhas[-2:] + ["* * * * * " + str(wrapper), "* * * * * " + str(wrapper.with_name("radar-api.pse")) + " cron fila", "* * * * * " + str(wrapper.with_name("radar-api.pse")) + " cron traseiro"])

    def test_cron_fila_independente_e_diretorio_preservado_ao_atualizar(self):
        wrapper = self.home.parent / "radar-tick.sh"
        externo = "*/10 * * * * python3 /servidor/radar-dados-sync.py\n"
        antigo = "*/5 * * * * /velho/radar-api.pse cron fila\n"
        aviso = "* * * * * echo /velho/radar-api.pse cron fila\n"
        novo = _cron_tick(externo + antigo + aviso,wrapper)
        self.assertIn(externo,novo)
        self.assertIn(aviso,novo)
        self.assertNotIn(antigo,novo)
        self.assertEqual(novo,_cron_tick(novo,wrapper))
        self.assertIn("* * * * * " + str(wrapper.with_name("radar-api.pse")) + " cron fila",novo)
        r = self.instalar(True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        fila = self.dados / "fila-cadastros"
        pedido = fila / "pendentes" / "preservar.json"
        pedido.write_text('{"origem":"nao perder"}')
        r = self.instalar(True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(pedido.read_text(),'{"origem":"nao perder"}')
        self.assertEqual(fila.stat().st_mode & 0o7777,0o2770)

    def test_atualiza_esquema_conf_sem_trocar_valor_nem_opcao_vazia(self):
        self.conf.write_text(self.conf.read_text() + "\n[governanca]\nsubmissao_limite =\n[coleta]\ntimeout = 95\n")
        resultado = self.instalar(True)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        texto = self.conf.read_text()
        self.assertIn("submissao_limite =\n", texto)
        self.assertNotIn("submissao_limite = 7", texto)
        self.assertIn("timeout = 95", texto)
        self.assertIn("tentativas = 3", texto)
        self.assertEqual(auditoria_instalacao.opcoes_faltantes(texto), {})

    def test_recria_logrotate_e_pastas_ausentes_mesmo_sem_versao_nova(self):
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        regra = self.lab / "etc" / "logrotate.d" / "openclaw-radar"
        esperado = regra.read_bytes()
        shutil.rmtree(regra.parent)
        shutil.rmtree(self.dados / "logs")
        self.dados.chmod(0o700)
        for nome in ("raw", "staging", "calibracao"):
            shutil.rmtree(self.dados / nome)
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(regra.read_bytes(), esperado)
        for pasta in (self.dados / "logs", self.dados / "raw", self.dados / "staging", self.dados / "calibracao"):
            self.assertEqual(pasta.stat().st_mode & 0o7777, 0o2770)
        self.assertIn("Regra do logrotate criada", r.stdout)
        self.assertIn("Diretorio criado", r.stdout)
        self.assertEqual(self.dados.stat().st_mode & 0o7777, 0o2770)
        self.assertIn("Permissoes ajustadas (2770)", r.stdout)
        relatorio = json.loads(sorted((self.dados / "backups" / "instalacao").glob("*/checagem-final.json"))[-1].read_text())
        self.assertTrue(any("logrotate criada" in a for a in relatorio["observacoes"]))
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sem nova copia ou backup", r.stdout)

    def test_migra_regra_antiga_e_corrige_link_sem_dependencia_de_sudo(self):
        legado = self.lab / "etc" / "sudoers.d" / "radar-configuracao"
        legado.parent.mkdir(parents=True)
        legado.write_text("regra antiga")
        outro = self.lab / "outro.conf"
        outro.write_text("preservar")
        (self.web / "radar.conf").symlink_to(outro)
        r = self.instalar(True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(legado.exists())
        self.assertEqual(outro.read_text(), "preservar")
        self.assertEqual((self.web / "radar.conf").resolve(), self.conf)
        self.assertIn("Regra sudoers antiga removida", r.stdout)
        antes = self.conf.read_bytes()
        cmd = [sys.executable, str(self.web / "api.pse"), "configuracao", "salvar-web"]
        payload = {"revisao": hashlib.sha256(antes).hexdigest(), "alteracoes": {"coleta.timeout": "44"}}
        salvo = subprocess.run(cmd, env=self.env, input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        self.assertEqual(salvo.returncode, 0, salvo.stdout + salvo.stderr)
        self.assertIn("timeout = 44", self.conf.read_text())
        self.assertTrue((self.web / "radar.conf").is_symlink())

    def test_perfil_completa_config_parcial_sem_mudar_valores_existentes(self):
        logs = self.dados / "novos" / "pais" / "logs"
        perfil = self.lab / "perfil.conf"
        perfil.write_text(self.conf.read_text().replace(str(self.dados / "logs"), str(logs)).replace(str(self.banco), str(self.lab / "banco-errado.sqlite3")))
        self.conf.write_text(self.conf.read_text().replace("banco = " + str(self.banco) + "\n", "").replace("[logs]\ndir = " + str(self.dados / "logs") + "\n", "") + "[coleta]\ntimeout = 95\n[web]\norigem =\n")
        extras = ("--perfil-conf", str(perfil))
        antes = {p: p.read_bytes() for p in self.lab.rglob("*") if p.is_file()}
        r = self.instalar(extras=extras)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(antes, {p: p.read_bytes() for p in self.lab.rglob("*") if p.is_file()})
        r = self.instalar(True, extras)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("banco = " + str(self.banco), self.conf.read_text())
        self.assertIn("timeout = 95", self.conf.read_text())
        self.assertIn("origem =\n", self.conf.read_text())
        self.assertIn("url = /teste/", self.conf.read_text())
        self.assertEqual(logs.stat().st_mode & 0o7777, 0o2770)
        self.assertEqual(logs.parent.stat().st_mode & 0o7777, 0o755)
        self.assertIn("Opcao acrescentada do perfil: logs.dir", r.stdout)
        with closing(db.connect_readonly(self.banco)) as conn:
            self.assertEqual(conn.execute("SELECT valor FROM SENTINELA").fetchone()[0], "nao perder")

    def test_cria_config_web_e_pais_ausentes_com_umask_restritiva(self):
        perfil = self.lab / "perfil.conf"
        perfil.write_text(self.conf.read_text())
        self.conf.unlink()
        self.conf.parent.rmdir()
        shutil.rmtree(self.web.parent)
        script = "import os,subprocess,sys;os.umask(0o077);sys.exit(subprocess.call(sys.argv[1:]))"
        cmd = [sys.executable, "-c", script, sys.executable, str(ROOT / "web" / "api.pse"),
               "instalacao", "--conf", str(self.conf), "--perfil-conf", str(perfil),
               "--laboratorio", str(self.lab), "--usuario-web", getpass.getuser(), "--aplicar"]
        r = subprocess.run(cmd, env=self.env, text=True, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.conf.is_file())
        self.assertTrue((self.web / "api.pse").is_file())
        self.assertEqual(self.web.parent.stat().st_mode & 0o7777, 0o755)
        self.assertIn("Configuracao criada a partir do perfil", r.stdout)

    def test_relatorio_cria_pasta_sem_trocar_permissoes_de_pai_existente(self):
        self.lab.chmod(0o750)
        relatorio = self.lab / "relatorios" / "instalacao.json"
        r = self.instalar(True, ("--relatorio", str(relatorio)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lab.stat().st_mode & 0o7777, 0o750)
        self.assertEqual(relatorio.parent.stat().st_mode & 0o7777, 0o700)
        self.assertTrue(json.loads(relatorio.read_text())["observacoes"])

    def test_banco_ausente_nao_e_substituido_por_base_vazia(self):
        self.banco.unlink()
        r = self.instalar(True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.banco.exists())
        self.assertIn("banco configurado nao existe", r.stderr)

    def test_verificacao_detecta_arquivo_corrompido_e_reaplicacao_conserta(self):
        instalado = self.instalar(True)
        self.assertEqual(instalado.returncode, 0, instalado.stdout + instalado.stderr)
        alvo = self.web / "gestao.html"
        alvo.write_text("corrompido")
        cmd = [sys.executable, str(ROOT / "web" / "api.pse"), "instalacao", "--conf", str(self.conf),
               "--laboratorio", str(self.lab), "--verificar"]
        r = subprocess.run(cmd, env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(str(alvo), r.stdout)
        self.assertEqual(alvo.read_text(), "corrompido")
        instalado = self.instalar(True)
        self.assertEqual(instalado.returncode, 0, instalado.stdout + instalado.stderr)
        r = subprocess.run(cmd, env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(alvo.read_text(), "corrompido")

    def test_crontab_ilegivel_nao_e_tratado_como_crontab_vazio(self):
        resposta = subprocess.CompletedProcess(["crontab", "-l"], 1, "", "Permission denied")
        with patch.object(auditoria_instalacao.subprocess, "run", return_value=resposta):
            with self.assertRaisesRegex(RuntimeError, "Nao foi possivel ler"):
                auditoria_instalacao.ler_crontab()

    def test_http_confere_api_e_detecta_pagina_antiga(self):
        conteudo = b"pagina atual"
        pagina = self.lab / "gestao.html"
        pagina.write_bytes(conteudo)
        home = self.lab / 'index.html'
        home.write_bytes(conteudo)
        class Handler(BaseHTTPRequestHandler):
            configuracao_privada = True
            def do_GET(self):
                if self.path == "/radar/radar.conf" and self.configuracao_privada:
                    self.send_error(404)
                    return
                if not self.path.startswith('/radar/api.pse?') and self.path not in ('/radar/','/radar/gestao.html','/radar/radar.conf'):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ready"}' if self.path.startswith("/radar/api.pse?") else conteudo)
            def log_message(self, *args):
                pass
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        try:
            origem = "http://127.0.0.1:%d" % servidor.server_port
            auditoria_instalacao.verificar_http(origem, "/radar/", pagina, configuracao_privada=True, pagina_inicial=home)
            home.write_bytes(b'home desatualizada')
            with self.assertRaisesRegex(RuntimeError, 'pagina inicial atualizada'):
                auditoria_instalacao.verificar_http(origem, '/radar/', pagina, pagina_inicial=home)
            home.write_bytes(conteudo)
            Handler.configuracao_privada = False
            with self.assertRaisesRegex(RuntimeError, "baixar a configuracao"):
                auditoria_instalacao.verificar_http(origem, "/radar/", pagina, configuracao_privada=True)
            pagina.write_bytes(b"outra versao")
            with self.assertRaisesRegex(RuntimeError, "pagina atualizada"):
                auditoria_instalacao.verificar_http(origem, "/radar/", pagina)
        finally:
            servidor.shutdown()
            servidor.server_close()
            thread.join(timeout=2)

    def test_atualizador_aguarda_coleta_sem_matar_processo(self):
        lock = self.dados / "tick.lock"
        with lock.open("a") as coleta, lock.open("a") as atualizador:
            fcntl.flock(coleta, fcntl.LOCK_EX)
            liberou = threading.Event()
            def concluir():
                time.sleep(0.05)
                fcntl.flock(coleta, fcntl.LOCK_UN)
                liberou.set()
            thread = threading.Thread(target=concluir)
            thread.start()
            try:
                _esperar_coletor(atualizador)
                thread.join(timeout=2)
                self.assertTrue(liberou.is_set())
            finally:
                thread.join(timeout=2)

    def test_preparacao_inicia_so_servico_inativo_sem_reiniciar_os_demais(self):
        chamadas = []
        observacoes = []
        def executar(cmd, **kwargs):
            chamadas.append(cmd)
            ativo = cmd[1] == "is-active" and cmd[2] in ("nginx.service", "fcgiwrap.socket")
            return subprocess.CompletedProcess(cmd, 0 if ativo or cmd[1] == "start" else 3)
        with patch.object(auditoria_instalacao, "ambiente_servidor", return_value=[]), \
                patch("core.instalacao.subprocess.run", side_effect=executar):
            _preparar_servicos(observacoes)
        self.assertEqual([c for c in chamadas if c[1] == "start"], [["systemctl", "start", "cron.service"]])
        self.assertFalse(any("restart" in c for c in chamadas))
        self.assertEqual(observacoes, ["Servico iniciado: cron.service"])

    def test_preparacao_nao_inicia_nginx_inativo(self):
        def executar(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 3 if cmd[1] == 'is-active' else 0)
        with patch.object(auditoria_instalacao, 'ambiente_servidor', return_value=[]), \
             patch('core.instalacao.subprocess.run', side_effect=executar) as comandos:
            _preparar_servicos([])
        self.assertFalse(any('nginx.service' in c.args[0] for c in comandos.call_args_list))

    def test_recuperacao_de_backup_antigo_preserva_nginx_atual(self):
        from core.instalacao import _recuperar
        backup = self.dados / 'backups/instalacao/teste'
        backup.mkdir(parents=True)
        nginx = self.lab / 'etc/nginx/default'
        nginx.parent.mkdir(parents=True)
        nginx.write_text('configuracao atual do operador')
        copia = backup / 'nginx-antigo'
        copia.write_text('configuracao antiga que nao deve voltar')
        (backup / 'restauracao.json').write_text(json.dumps([
            {'alvo':str(nginx), 'copia':str(copia), 'tipo':'nginx'}]))
        dirs = dict(dados=self.dados, banco=self.banco, codigo=self.home, web=self.web, conf=self.conf)
        with patch('core.instalacao._esquema_compativel_com_backup', return_value=True):
            self.assertEqual(_recuperar(backup, dirs, self.lab), 0)
        self.assertEqual(nginx.read_text(), 'configuracao atual do operador')

    def test_preparacao_nao_inicia_servicos_com_nginx_invalido(self):
        with patch.object(auditoria_instalacao, "ambiente_servidor", return_value=[
                {"checagem": "nginx.configuracao", "estado": "erro", "detalhe": "invalida"}]), \
                patch("core.instalacao.subprocess.run") as executar:
            with self.assertRaisesRegex(RuntimeError, "nginx.configuracao"):
                _preparar_servicos()
            executar.assert_not_called()
