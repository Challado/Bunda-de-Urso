"""Servidor de laboratorio: arquivos reais e CGI api.pse com SQLite temporario.

Nao abre o banco. Inicializacao e cada requisicao passam pela entrada da API.
Nao se conecta ao servidor de producao nem precisa de credenciais.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / 'web' / 'api.pse'
PREFIXO = '/openclaw/radar'


def main():
    with tempfile.TemporaryDirectory(prefix='radar-browser-') as pasta:
        base = Path(pasta)
        conf = base / 'radar.conf'
        conf.write_text('[instalacao]\nhome = %s\n[dados]\ndir = %s\nbanco = %s\n[governanca]\nsubmissao_limite = 100\n' %
                        (ROOT, base, base / 'radar.sqlite3'))
        ambiente = {k:v for k,v in os.environ.items() if not k.startswith(('RADAR_', 'OLLAMA_')) and
                    k not in ('REQUEST_METHOD','GATEWAY_INTERFACE','QUERY_STRING','PATH_INFO')}
        ambiente.update(RADAR_CONF=str(conf), PYTHONDONTWRITEBYTECODE='1')
        fixture = base / 'oficial.json'
        fixture.write_text(json.dumps([{'Codigo':'E2E-OFICIAL', 'Latitude':-24.9556,
            'Longitude':-53.4552, 'Rodovia':'BR-277', 'Km':580.5, 'VelocidadeLeves':80}]))
        subprocess.run([sys.executable, str(API), 'sync', '--fonte','antt', '--arquivo',str(fixture),
                        '--sem-publicar'], env=ambiente, check=True, capture_output=True, timeout=15)

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,directory=str(ROOT / 'web'),**kwargs)

            def log_message(self,*args):
                pass

            def api(self):
                url=urlsplit(self.path)
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                env=dict(ambiente, REQUEST_METHOD=self.command, QUERY_STRING=url.query,
                         SCRIPT_NAME=PREFIXO+'/api.pse', CONTENT_LENGTH=str(len(body)),
                         CONTENT_TYPE=self.headers.get('Content-Type',''), REMOTE_ADDR='127.0.0.1')
                env.update({'HTTP_'+k.upper().replace('-','_'):v for k,v in self.headers.items()})
                try:
                    r=subprocess.run([sys.executable,str(API)],env=env,input=body,
                                     capture_output=True,check=True,timeout=10)
                    head,payload=r.stdout.split(b'\r\n\r\n',1)
                    linhas=head.decode().split('\r\n')
                    status=int(linhas[0].split()[1])
                    self.send_response(status)
                    for linha in linhas[1:]:
                        k,v=linha.split(':',1)
                        self.send_header(k,v.strip())
                    self.end_headers()
                    self.wfile.write(payload)
                except (subprocess.SubprocessError, ValueError) as erro:
                    print('Erro no CGI de teste: '+str(erro),file=sys.stderr,flush=True)
                    self.send_error(502)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                url=urlsplit(self.path)
                if url.path == PREFIXO+'/api.pse':
                    return self.api()
                if not url.path.startswith(PREFIXO+'/'):
                    return self.send_error(404)
                self.path=self.path[len(PREFIXO):]
                return super().do_GET()

            def do_POST(self):
                if urlsplit(self.path).path != PREFIXO+'/api.pse':
                    return self.send_error(404)
                return self.api()

        parar = threading.Event()
        def consumir_fila():
            while not parar.wait(0.2):
                try:
                    subprocess.run([sys.executable,str(API),'fila','processar'],env=ambiente,
                                   capture_output=True,check=True,timeout=10)
                except subprocess.SubprocessError as erro:
                    print('Erro no processador de teste: '+str(erro),file=sys.stderr,flush=True)
        worker = threading.Thread(target=consumir_fila,daemon=True)
        if '--sem-fila' not in sys.argv:
            worker.start()

        def interromper(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,interromper)
        with ThreadingHTTPServer(('127.0.0.1',0),Handler) as servidor:
            print(json.dumps({'url':'http://127.0.0.1:%d%s/' % (servidor.server_port,PREFIXO)}),flush=True)
            try:
                servidor.serve_forever(poll_interval=0.05)
            except KeyboardInterrupt:
                pass
            finally:
                parar.set()
                if worker.is_alive():
                    worker.join(timeout=12)


if __name__=='__main__':
    main()
