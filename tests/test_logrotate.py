"""Regressao da regra em pasta gravavel pelo CGI, usando logrotate real."""
import grp
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from core import auditoria_instalacao as auditoria, caminhos

ROOT = Path(__file__).resolve().parents[1]


class TestLogrotateReal(unittest.TestCase):
    def test_pasta_do_cgi_exige_su_sem_rotacionar_no_diagnostico(self):
        binario = os.environ.get("RADAR_TEST_LOGROTATE") or shutil.which("logrotate")
        if not binario:
            self.skipTest("logrotate nao instalado (o CI instala o pacote)")
        gid = os.getgid() or grp.getgrnam("www-data").gr_gid
        prefixo = []
        if os.geteuid() != 0:
            alternativas = []
            if shutil.which("unshare"):
                alternativas.append(["unshare", "--user", "--map-user", "0", "--map-group", str(gid)])
            if shutil.which("sudo"):
                alternativas.append(["sudo", "-n"])
            prefixo = next((p for p in alternativas if subprocess.run(
                p + ["true"], capture_output=True, timeout=10).returncode == 0), None)
            if prefixo is None:
                self.skipTest("requer root, namespace de usuario ou sudo sem senha")
        with tempfile.TemporaryDirectory(prefix="radar-logrotate-") as pasta:
            base = Path(pasta)
            logs = base / "logs"
            logs.mkdir()
            if os.geteuid() == 0:
                os.chown(logs, 0, gid)
            logs.chmod(0o2770)
            log = logs / "tick.log"
            log.write_text("log preservado\n")
            conf = base / "radar.conf"
            conf.write_text("[instalacao]\nusuario = root\ngrupo = " + grp.getgrgid(gid).gr_name + "\n")
            with patch.dict(os.environ, RADAR_CONF=str(conf)):
                caminhos.recarregar()
                try:
                    regra = auditoria.render_logrotate(ROOT, logs)
                finally:
                    caminhos.recarregar()
            antiga = base / "antiga.conf"
            antiga.write_text("\n".join(l for l in regra.splitlines() if not l.strip().startswith("su ")) + "\n")
            nova = base / "nova.conf"
            nova.write_text(regra)
            # O logrotate exige que a regra pertença a root. No CI, sudo pode
            # ser a alternativa ao namespace bloqueado pelo AppArmor do runner.
            subprocess.run(prefixo + ["chown", "0", str(antiga), str(nova)],
                           check=True, capture_output=True, timeout=10)
            for arquivo, esperado in ((antiga, False), (nova, True)):
                r = subprocess.run(prefixo + [binario, "--debug", "--state", "/dev/null", str(arquivo)],
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode == 0, esperado, r.stdout + r.stderr)
                if not esperado:
                    self.assertIn("insecure permissions", r.stderr)
            self.assertEqual(log.read_text(), "log preservado\n")
            self.assertEqual(list(logs.iterdir()), [log])


class TestDiagnosticoLogrotate(unittest.TestCase):
    def test_erro_exato_preservado_inclusive_arquivo_ausente(self):
        erro = "error: cannot stat /etc/logrotate.d/openclaw-radar: Arquivo ou diretório inexistente\n"
        r = subprocess.CompletedProcess([], 1, "", erro + "Creating new state\n" * 2000)
        with patch.object(auditoria.subprocess, "run", return_value=r):
            resultado = auditoria.validar_logrotate(Path("/etc/logrotate.d/openclaw-radar"))
        self.assertEqual(resultado["estado"], "erro")
        self.assertEqual(resultado["codigo_saida"], 1)
        self.assertIn(erro.strip(), resultado["detalhe"])
        self.assertTrue(resultado["saida_truncada"])
        self.assertLessEqual(len(resultado["stderr"]), 16384)

    def test_aviso_normal_do_debug_nao_e_erro(self):
        r = subprocess.CompletedProcess([], 0, "", "warning: logrotate in debug mode does nothing\n")
        with patch.object(auditoria.subprocess, "run", return_value=r):
            resultado = auditoria.validar_logrotate(Path("regra.conf"))
        self.assertEqual(resultado["estado"], "ok")
        self.assertEqual(resultado["codigo_saida"], 0)

    def test_comando_indisponivel_gera_diagnostico(self):
        with patch.object(auditoria.subprocess, "run", side_effect=FileNotFoundError("logrotate ausente")):
            resultado = auditoria.validar_logrotate(Path("regra.conf"))
        self.assertEqual(resultado["estado"], "erro")
        self.assertIn("logrotate ausente", resultado["detalhe"])
