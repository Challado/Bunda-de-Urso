"""API publica do DNIT: dados originais, validacao e complemento sem navegador."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coletor import http
from coletor.fontes.dnit import ColetorDNIT, ColetorDNITEquipamentos
from core import config, db

FIXTURES = Path(__file__).parent / 'fixtures/dnit'
API = FIXTURES / 'equipamentos_api.geojson'


class DNITHTTPTest(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(API.read_bytes())
        self.coletor = ColetorDNITEquipamentos()

    def carregar(self, documento):
        with patch.object(self.coletor, '_baixar', return_value=json.dumps(documento).encode()):
            return self.coletor.carregar(None)

    def test_pagina_anterior_e_origem_automatica_usam_api(self):
        with patch.object(self.coletor, '_baixar', return_value=API.read_bytes()) as baixar:
            for origem in (None, self.coletor.PAGINA, self.coletor.PAGINA + '/', self.coletor.resolver_url()):
                self.coletor.carregar(origem)
                self.assertEqual(baixar.call_args.args, (self.coletor.URL_API,))

    def test_geojson_local_preserva_feature_e_ordem_longitude_latitude(self):
        with patch.object(self.coletor, '_baixar', side_effect=AssertionError('Arquivo nao usa rede')):
            corpo, ext, mime, registros = self.coletor.carregar(str(API))
        self.assertEqual(corpo, API.read_bytes())
        self.assertEqual((ext, mime), ('.geojson', 'application/geo+json'))
        self.assertEqual(registros, self.doc['features'])
        raw = next(r for r in registros if r['properties']['codigo'] == 'ACB26040003')
        antes = deepcopy(raw)
        d = self.coletor.normalizar(0, raw)
        self.assertEqual(raw, antes)
        self.assertEqual(d['identificador'], 'ACB26040003')
        self.assertEqual((d['latitude'], d['longitude']), (-10.011417, -67.794678))
        self.assertEqual((d['numero_serie'], d['numero_inmetro']), ('FLICD0426A01117', '15030378'))
        self.assertEqual(d['km'], 123.83)
        self.assertEqual(d['via_codigo'], 'BR-364')

    def test_api_e_planilha_publicam_mesma_normalizacao(self):
        linhas = self.coletor.carregar(str(FIXTURES / 'equipamentos_multas.xlsx'))[3]
        por_codigo = {self.coletor.identificador(r): r for r in linhas}
        for raw in self.doc['features']:
            codigo = self.coletor.identificador(raw)
            if codigo in por_codigo:
                self.assertEqual(self.coletor.normalizar(0, raw),
                                 self.coletor.normalizar(0, por_codigo[codigo]))

    def test_falha_http_nao_usa_chromium_nem_fixture(self):
        with patch.object(self.coletor, '_baixar', side_effect=http.ErroFonte('HTTP 503')), patch(
                'coletor.exportacao_publica.baixar_xlsx', side_effect=AssertionError('Nao usar navegador')):
            with self.assertRaisesRegex(http.ErroFonte, '503'):
                self.coletor.carregar(None)

    def test_erro_html_json_invalido_e_estrutura_alterada_sao_recusados(self):
        for corpo in (b'<html>Request Rejected</html>', b'{}', b'[]', b'{', b'\xff'):
            with self.subTest(corpo=corpo), patch.object(self.coletor, '_baixar', return_value=corpo):
                with self.assertRaisesRegex(ValueError, 'API DNIT'):
                    self.coletor.carregar(None)

    def test_coleta_vazia_codigos_ausentes_e_duplicados_sao_recusados(self):
        casos = [dict(type='FeatureCollection', features=[])]
        d = deepcopy(self.doc); d['features'][0]['properties']['codigo'] = ''; casos.append(d)
        d = deepcopy(self.doc); d['features'][1]['properties']['codigo'] = d['features'][0]['properties']['codigo'].lower(); casos.append(d)
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaisesRegex(ValueError, 'vazia|codigos'):
                self.carregar(caso)

    def test_geometrias_invalidas_nao_viram_coordenadas_inventadas(self):
        for geometria in (None, {}, {'type': 'LineString', 'coordinates': []},
                          {'type': 'Point', 'coordinates': None},
                          {'type': 'Point', 'coordinates': [-10, -67]},
                          {'type': 'Point', 'coordinates': [-67, True]},
                          {'type': 'Point', 'coordinates': [-67, float('nan')]},
                          {'type': 'Point', 'coordinates': [-67, '10']}):
            d = deepcopy(self.doc); d['features'][0]['geometry'] = geometria
            with self.subTest(geometria=geometria), self.assertRaisesRegex(ValueError, 'geometria|coordenadas'):
                self.carregar(d)

    def test_campos_e_features_alterados_interrompem_coleta(self):
        for valor in (None, [], {'type': 'Outro'}, {'type': 'Feature', 'properties': None}):
            d = deepcopy(self.doc); d['features'][0] = valor
            with self.subTest(valor=valor), self.assertRaisesRegex(ValueError, 'Feature|campos'):
                self.carregar(d)
        d = deepcopy(self.doc); del d['features'][0]['properties']['serie']
        with self.assertRaisesRegex(ValueError, 'campos obrigatorios'):
            self.carregar(d)

    def test_api_complementa_pncv_sem_trocar_ponto_instrumento_ou_recurso(self):
        with tempfile.TemporaryDirectory() as temp, patch.multiple(config, DATA_DIR=temp, RAW_DIR=temp):
            with closing(db.connect(':memory:')) as conn:
                db.init_db(conn)
                municipios = json.loads((FIXTURES.parents[2] / 'config/municipios_ibge.json').read_text())['municipios']
                municipio = next(m for m in municipios if m['nome'] == 'Rio Branco' and m['uf_sigla'] == 'AC')
                db.insert(conn, 'MUNICIPIO', {k: municipio[k] for k in ('codigo_ibge', 'nome', 'uf_sigla')})
                pncv = ColetorDNIT(conn=conn)
                linhas = pncv.carregar(str(FIXTURES / 'pncv_julho_2026.xlsx'))[3]
                linha = next(r for r in linhas if r['Código Identificação'] == 'ACB26040003')
                pncv.ingerir_registros([linha])
                ponto = db.scalar(conn, 'SELECT id FROM PONTO_FISCALIZACAO')
                equipamento = db.scalar(conn, 'SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?', (ponto,))
                anterior = ColetorDNITEquipamentos(conn=conn)
                anterior.RECURSO = dict(anterior.RECURSO, url_recurso=anterior.PAGINA, formato_origem='xlsx', status_integracao='parcial')
                _, recurso = anterior.garantir_referencias()
                coletor = ColetorDNITEquipamentos(conn=conn)
                feature = next(r for r in self.doc['features'] if r['properties']['codigo'] == 'ACB26040003')
                self.assertEqual(coletor.ingerir_registros([feature])['atualizados'], 1)
                repetida = coletor.ingerir_registros([feature])
                self.assertEqual((repetida['criados'], repetida['atualizados'], repetida['ignorados']), (0, 0, 1))
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'), 1)
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM INSTALACAO'), 1)
                self.assertEqual(db.scalar(conn, 'SELECT equipamento_id FROM INSTALACAO WHERE ponto_id=?', (ponto,)), equipamento)
                self.assertEqual(db.scalar(conn, 'SELECT numero_serie FROM EQUIPAMENTO WHERE id=?', (equipamento,)), 'FLICD0426A01117')
                self.assertEqual(coletor.garantir_referencias()[1], recurso)
                self.assertEqual(db.scalar(conn, 'SELECT formato_origem FROM RECURSO_FONTE WHERE id=?', (recurso,)), 'geojson|xlsx')
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM FONTE'), 1)
                self.assertEqual(db.scalar(conn, 'SELECT COUNT(*) FROM RECURSO_FONTE'), 2)
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
