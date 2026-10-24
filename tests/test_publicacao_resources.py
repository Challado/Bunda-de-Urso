"""Relatorio publico pela API: sem banco, sem expor credenciais do diario."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.nucleo import handle_request


class TestRelatorioPublico(unittest.TestCase):
    def test_relatorio_json_pela_api_sem_acessar_sqlite(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'status.json'
            arquivo.write_text(json.dumps({'versao_esquema':1,'operacoes':{'bootstrap':{'estado':'ok','token':'nao-expor'}}}))
            with patch('core.caminhos.status_atualizacoes',return_value=str(arquivo)), \
                 patch('web.nucleo._conn',side_effect=AssertionError('nao abrir banco')):
                codigo,headers,corpo=handle_request({'REQUEST_METHOD':'GET','QUERY_STRING':'rota=/api/v1/atualizacoes/status'})
            self.assertEqual(codigo,200)
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertEqual(corpo['operacoes']['bootstrap']['estado'],'ok')
            self.assertEqual(corpo['operacoes']['bootstrap']['token'],'[oculto]')

    def test_relatorio_corrompido_e_metodo_de_escrita_nao_sao_aceitos(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo=Path(pasta)/'status.json'
            arquivo.write_text('{invalido')
            with patch('core.caminhos.status_atualizacoes',return_value=str(arquivo)), \
                 patch('web.nucleo._conn',side_effect=AssertionError('nao abrir banco')):
                env={'REQUEST_METHOD':'GET','QUERY_STRING':'rota=/api/v1/atualizacoes/status'}
                self.assertEqual(handle_request(env)[0],503)
                self.assertEqual(handle_request(dict(env,REQUEST_METHOD='POST'))[0],405)
