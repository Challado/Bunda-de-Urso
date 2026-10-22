"""DNIT: duas publicacoes reais, complemento por codigo e exportacao blob."""
import base64
from contextlib import closing
import csv
import http.server as servidor_http
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from coletor import agenda, http, sync
from coletor.exportacao_publica import baixar_xlsx
from coletor.fontes.dnit import ColetorDNIT, ColetorDNITEquipamentos
from core import config, consultas, db

ROOT = Path(__file__).resolve().parents[1]
PNCV = ROOT / 'tests/fixtures/dnit/pncv_julho_2026.xlsx'
MULTAS = ROOT / 'tests/fixtures/dnit/equipamentos_multas.xlsx'


class DNITComplementoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pncv = ColetorDNIT().carregar(str(PNCV))[3]
        cls.multas = ColetorDNITEquipamentos().carregar(str(MULTAS))[3]

    def test_comparacao_real_e_gps_invertido_apenas_no_layout_multas(self):
        self.assertEqual(len(self.pncv), 1774)
        self.assertEqual(len(self.multas), 1655)
        a = {r['Código Identificação']: r for r in self.pncv}
        b = {r['Código do Equipamento']: r for r in self.multas}
        self.assertEqual(len(a.keys() & b.keys()), 1631)
        self.assertEqual(len(b.keys() - a.keys()), 24)
        self.assertEqual(len(a.keys() - b.keys()), 143)
        for codigo in a.keys() & b.keys():
            antigo = ColetorDNIT().normalizar(0, a[codigo])
            novo = ColetorDNITEquipamentos().normalizar(0, b[codigo])
            self.assertEqual(antigo['identificador'], novo['identificador'])
            self.assertAlmostEqual(antigo['latitude'], novo['latitude'], places=6)
            self.assertAlmostEqual(antigo['longitude'], novo['longitude'], places=6)
        for r in self.multas:
            d = ColetorDNITEquipamentos().normalizar(0, r)
            self.assertTrue(-34 <= d['latitude'] <= 6)
            self.assertTrue(-74 <= d['longitude'] <= -34)

    def test_series_multiplas_e_registros_inmetro_invalidos_ficam_no_bruto(self):
        c = ColetorDNITEquipamentos()
        r = dict(self.multas[0])
        for valor in ('0', 'não informado', 'FISCALTECH', '1562849-4'):
            d = c.normalizar(0, dict(r, **{'Registro INMETRO': valor}))
            self.assertIsNone(d['numero_inmetro'])
        for valor in ('123/456', 'não informado', '0', ''):
            d = c.normalizar(0, dict(r, **{'Nº de Série': valor}))
            self.assertIsNone(d['numero_serie'])
            self.assertIsNone(d['numero_inmetro'])

    def test_agenda_independente_e_fonte_comum(self):
        self.assertIs(agenda.AGENDA_PADRAO['dnit_equipamentos']['conector'], ColetorDNITEquipamentos)
        self.assertIs(sync.FONTES['dnit_equipamentos'], ColetorDNITEquipamentos)
        self.assertEqual(ColetorDNIT.FONTE, ColetorDNITEquipamentos.FONTE)
        self.assertNotEqual(ColetorDNIT.RECURSO['nome'], ColetorDNITEquipamentos.RECURSO['nome'])

    def test_nao_refina_instrumento_com_local_divergente_certificado_ou_decisao(self):
        from core.equipamentos import complementar_cadastro
        with tempfile.TemporaryDirectory() as temp, patch.multiple(config,
                RAW_DIR=str(Path(temp) / 'raw'), DATA_DIR=temp):
            with closing(db.connect(':memory:')) as conn:
                db.init_db(conn)
                municipio = next(m for m in json.loads((ROOT / 'config/municipios_ibge.json').read_text())['municipios']
                                 if m['nome'] == 'Rio Branco' and m['uf_sigla'] == 'AC')
                db.insert(conn, 'MUNICIPIO', {k: municipio[k] for k in ('codigo_ibge','nome','uf_sigla')})
                raws = [r for r in self.pncv if r['Código Identificação'] in ('ACB26040003','ACB26050004')]
                c = ColetorDNIT(conn=conn)
                c.ingerir_registros(raws)
                fid = db.scalar(conn, 'SELECT id FROM FONTE')
                iid = db.scalar(conn, "SELECT id FROM IDENTIFICADOR_EXTERNO WHERE valor='ACB26040003'")
                pid = db.scalar(conn, 'SELECT ponto_id FROM IDENTIFICADOR_PONTO WHERE identificador_id=?', (iid,))
                eid = db.scalar(conn, 'SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?', (pid,))
                local = dict(db.query_one(conn, 'SELECT municipio_id, via_id, km FROM PONTO_FISCALIZACAO WHERE id=?', (pid,)))
                dados = dict(db.query_one(conn, 'SELECT * FROM EQUIPAMENTO WHERE id=?', (eid,)))
                dados['numero_serie'] = 'FLICD0426A01117'
                def resolver(atual=None):
                    return complementar_cadastro(conn, fid, None, pid, iid, dados, local, atual or local)
                self.assertEqual(resolver(), eid)
                self.assertIsNone(resolver(dict(local, km=local['km'] + 1)))
                conn.execute('SAVEPOINT caso')
                db.insert(conn, 'VERIFICACAO_METROLOGICA', {'equipamento_id':eid,
                    'tipo_verificacao_id':db.scalar(conn,'SELECT id FROM TIPO_VERIFICACAO LIMIT 1'),
                    'resultado_id':db.scalar(conn,'SELECT id FROM RESULTADO_VERIFICACAO LIMIT 1')})
                self.assertIsNone(resolver())
                conn.execute('ROLLBACK TO caso'); conn.execute('RELEASE caso')
                regs = [r[0] for r in conn.execute('SELECT id FROM REGISTRO_FONTE ORDER BY id')]
                regra = db.insert(conn, 'REGRA_DEDUPLICACAO', {'versao':'teste', 'descricao':'teste',
                    'configuracao_serializada':'{}','inicio_validade':'2026-01-01'})
                candidato = db.insert(conn,'CANDIDATO_DUPLICIDADE', {'registro_a_id':regs[0], 'registro_b_id':regs[1],
                    'regra_id':regra,'estado':'decidido','gerado_em':'2026-01-01'})
                db.insert(conn,'DECISAO_DUPLICIDADE', {'candidato_id':candidato,'decisao':'manter_separados',
                    'fundamentacao':'identidade nao confirmada','ator':'teste','decidida_em':'2026-01-01'})
                self.assertIsNone(resolver())
                self.assertIsNone(db.scalar(conn, 'SELECT numero_serie FROM EQUIPAMENTO WHERE id=?', (eid,)))

    def test_online_usa_exportacao_da_pagina_e_valida_cabecalho(self):
        with patch('coletor.exportacao_publica.baixar_xlsx', return_value=MULTAS.read_bytes()) as baixar:
            c = ColetorDNITEquipamentos()
            b, ext, mime, r = c.carregar(c.resolver_url())
            self.assertEqual(len(r), 1655)
            self.assertEqual(b, MULTAS.read_bytes())
            baixar.assert_called_once_with(c.PAGINA)
        for b in (b'<html>erro</html>', PNCV.read_bytes()):
            with patch('coletor.exportacao_publica.baixar_xlsx', return_value=b):
                with self.assertRaises(ValueError):
                    ColetorDNITEquipamentos().carregar(None)

    def test_api_duas_publicacoes_preservam_pontos_ids_modelos_e_origens(self):
        with tempfile.TemporaryDirectory() as temp:
            conf, banco = Path(temp) / 'radar.conf', Path(temp) / 'teste.sqlite3'
            conf.write_text('[dados]\ndir = ' + temp + '\n')
            env = dict(os.environ, RADAR_CONF=str(conf), RADAR_DATA_DIR=temp)
            with closing(db.connect(str(banco))) as conn:
                db.init_db(conn)
                for m in json.loads((ROOT / 'config/municipios_ibge.json').read_text())['municipios']:
                    db.insert(conn, 'MUNICIPIO', {k: m[k] for k in ('codigo_ibge', 'nome', 'uf_sigla')})
                conn.commit()

            def importar(fonte, arquivo):
                p = subprocess.run([sys.executable, str(ROOT / 'web/api.pse'), 'sync', '--fonte', fonte,
                    '--arquivo', str(arquivo), '--db', str(banco), '--sem-publicar'],
                    capture_output=True, text=True, env=env, timeout=120)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                return json.loads(p.stdout)

            self.assertEqual(importar('dnit', PNCV)['criados'], 1774)
            with closing(db.connect(str(banco))) as conn:
                pid = db.scalar(conn, "SELECT ip.ponto_id FROM IDENTIFICADOR_PONTO ip JOIN IDENTIFICADOR_EXTERNO e ON e.id=ip.identificador_id WHERE e.valor='ACB26040003'")
                eid = db.scalar(conn, 'SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?', (pid,))
                modelo = db.scalar(conn, 'SELECT modelo_id FROM EQUIPAMENTO WHERE id=?', (eid,))
            res = importar('dnit_equipamentos', MULTAS)
            self.assertEqual((res['criados'], res['atualizados'], res['rejeitados']), (24, 1631, 0))
            self.assertTrue(importar('dnit_equipamentos', MULTAS)['sem_mudanca'])
            # Nova edicao PNCV sem serie nao pode criar outro equipamento ou apagar a serie.
            r = next(dict(x) for x in self.pncv if x['Código Identificação'] == 'ACB26040003')
            r['Contrato'] += ' - edicao de teste'
            arquivo = Path(temp) / 'pncv.csv'
            with arquivo.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(r), delimiter=';'); w.writeheader(); w.writerow(r)
            self.assertEqual(importar('dnit', arquivo)['atualizados'], 1)
            with closing(db.connect(str(banco))) as conn:
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'), 1798)
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM FONTE'), 1)
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM RECURSO_FONTE'), 2)
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM INSTALACAO WHERE ponto_id=?', (pid,)), 1)
                self.assertEqual(db.scalar(conn, 'SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?', (pid,)), eid)
                self.assertEqual(db.scalar(conn, 'SELECT modelo_id FROM EQUIPAMENTO WHERE id=?', (eid,)), modelo)
                self.assertEqual(db.scalar(conn, 'SELECT numero_serie FROM EQUIPAMENTO WHERE id=?', (eid,)), 'FLICD0426A01117')
                from core.metrologia import numeros_inmetro
                self.assertEqual(numeros_inmetro(conn, eid), {'15030378'})
                detalhe = consultas.buscar_ponto_por_id(conn, 'P-' + str(pid))
                origens = detalhe['dados_por_fonte'][0]['registros']
                self.assertTrue(any('Faixas' in x['dados_publicados'] for x in origens))
                self.assertTrue(any('Registro INMETRO' in x['dados_publicados'] for x in origens))
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            # A serie e o registro publicados permitem juntar a verificacao.
            metrologia = json.loads((ROOT / 'tests/fixtures/novos/inmetro_medidores_fixture.json').read_text())[:1]
            arquivo_inmetro = Path(temp) / 'inmetro.json'
            arquivo_inmetro.write_text(json.dumps(metrologia, ensure_ascii=False))
            importar('inmetro', arquivo_inmetro)
            p = subprocess.run([sys.executable, str(ROOT / 'web/api.pse'), 'ferramenta',
                'carregar_verificacao_metrologica', '--db', str(banco)], env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
            r['Contrato'] += ' - apos Inmetro'
            with arquivo.open('w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(r), delimiter=';'); w.writeheader(); w.writerow(r)
            importar('dnit', arquivo)
            with closing(db.connect(str(banco))) as conn:
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM INSTALACAO WHERE ponto_id=?', (pid,)), 1)
                detalhe = consultas.buscar_ponto_por_id(conn, 'P-' + str(pid))
                self.assertTrue(any(v['numero_certificado'] == '15020223' for e in detalhe['equipamentos']
                                    for v in e['verificacoes_metrologicas']))


class ExportacaoPublicaTest(unittest.TestCase):
    def test_erro_de_navegador_ausente_e_url_privada(self):
        with patch('coletor.exportacao_publica.shutil.which', return_value=None):
            with self.assertRaisesRegex(http.ErroFonte, 'Chromium'):
                baixar_xlsx(ColetorDNITEquipamentos.PAGINA)
        with self.assertRaises(http.ErroFonte):
            baixar_xlsx('http://127.0.0.1/privado')

    @unittest.skipUnless(shutil.which('chromium') or os.environ.get('RADAR_TEST_CHROMIUM'), 'Chromium necessario para testar exportacao blob real')
    def test_blob_real_sem_node_ou_playwright_no_coletor(self):
        exportar_blob_real()

    @unittest.skipUnless(shutil.which('chromium') or os.environ.get('RADAR_TEST_CHROMIUM'), 'Chromium necessario para os cenarios de exportacao')
    def test_menu_icone_iframe_carregamento_e_diagnostico_reais(self):
        verificar_exportacao_robusta()


def exportar_blob_real():
    """Tambem chamado pelo Actions Chromium, onde o navegador ja foi instalado."""
    corpo = MULTAS.read_bytes()
    b64 = base64.b64encode(corpo).decode()

    class Handler(servidor_http.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(('''<button onclick="exportar()">Exportar Excel</button><script>
                function exportar(){const b=Uint8Array.from(atob(''' + repr(b64) + '''),c=>c.charCodeAt(0));
                const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([b]));
                a.download='TabelaEquipamentosFiscalizacao.xlsx';a.click();}</script>''').encode())

        def log_message(self, *args):
            pass

    servidor = servidor_http.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True); thread.start()
    real_which = shutil.which
    navegador = os.environ.get('RADAR_TEST_CHROMIUM') or real_which('chromium')
    try:
        with patch('coletor.exportacao_publica.http.url_checada'), patch(
                'coletor.exportacao_publica.shutil.which', side_effect=lambda n: navegador if n == 'chromium' else real_which(n)):
            recebido = baixar_xlsx('http://127.0.0.1:' + str(servidor.server_port), timeout=60)
        if recebido != corpo:
            raise AssertionError('A exportacao blob nao preservou o arquivo XLSX')
    finally:
        servidor.shutdown(); servidor.server_close(); thread.join()


def verificar_exportacao_robusta():
    """Navegador real: fluxos comuns que antes viravam apenas timeout generico."""
    corpo = MULTAS.read_bytes()
    b64 = base64.b64encode(corpo).decode()
    script = '''<script>function baixar(){const a=document.createElement('a');
        a.href=URL.createObjectURL(new Blob([Uint8Array.from(atob(%s),c=>c.charCodeAt(0))]));
        a.download='TabelaEquipamentosFiscalizacao.xlsx';a.click();}</script>''' % repr(b64)

    class Handler(servidor_http.BaseHTTPRequestHandler):
        def do_GET(self):
            paginas = {
                '/menu': '''<button aria-label="Baixar" onclick="this.insertAdjacentHTML('afterend',
                    '<div role=menuitem onclick=baixar()>Excel</div>')"><img alt="Baixar"></button>''',
                '/assincrono': '''<button mattooltip="Exportar Excel" onclick="window.n=(window.n||0)+1;if(n>1)baixar()">Arquivo</button>''',
                '/frame': '<iframe src="/filho" width="600" height="300"></iframe>',
                '/frame-reload': '<iframe id="f" src="/esperar" width="600" height="300"></iframe><script>setTimeout(()=>{f.src="/filho"},600)</script>',
                '/esperar': 'Carregando dados publicos',
                '/filho': '<button onclick="baixar()"><mat-icon>file_download</mat-icon></button>',
                '/api-erro': '<script>fetch("/api-indisponivel")</script>',
                '/javascript': '<script>setTimeout(()=>{throw Error("Falha demonstrativa na pagina")},250)</script>',
                '/bloqueio': '<title>Request Rejected</title><p>The requested URL was rejected</p>',
            }
            self.send_response(503 if self.path == '/api-indisponivel' else 200)
            self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            self.wfile.write((paginas.get(self.path, 'Indisponivel') + script).encode())

        def log_message(self, *args):
            pass

    servidor = servidor_http.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True); thread.start()
    real_which = shutil.which
    navegador = os.environ.get('RADAR_TEST_CHROMIUM') or real_which('chromium')
    try:
        with patch('coletor.exportacao_publica.http.url_checada'), patch(
                'coletor.exportacao_publica.shutil.which', side_effect=lambda n: navegador if n == 'chromium' else real_which(n)):
            base = 'http://127.0.0.1:' + str(servidor.server_port)
            for rota in ('/menu', '/assincrono', '/frame', '/frame-reload'):
                if baixar_xlsx(base + rota, timeout=15) != corpo:
                    raise AssertionError('Exportacao falhou: ' + rota)
            for rota, esperado in (('/api-erro', '503'), ('/javascript', 'Falha demonstrativa'), ('/bloqueio', 'bloqueou acesso')):
                try:
                    baixar_xlsx(base + rota, timeout=8)
                except http.ErroFonte as exc:
                    if esperado not in str(exc):
                        raise AssertionError('Diagnostico omitiu a causa: ' + str(exc)) from exc
                else:
                    raise AssertionError('Pagina com falha nao pode retornar planilha: ' + rota)
    finally:
        servidor.shutdown(); servidor.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
