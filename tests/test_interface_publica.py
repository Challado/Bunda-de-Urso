"""A home recebe somente limites de layout pela API, sem banco ou segredos."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import caminhos, configuracao, governanca
from web.nucleo import handle_request


class TestInterfacePublica(unittest.TestCase):
    def pedir(self, texto='', metodo='GET', extra=''):
        with tempfile.TemporaryDirectory() as pasta:
            conf=Path(pasta)/'radar.conf'
            conf.write_text(texto)
            with patch.dict(os.environ, {'RADAR_CONF':str(conf)}), \
                 patch('web.nucleo._conn',side_effect=AssertionError('sem banco')):
                return handle_request({'REQUEST_METHOD':metodo,'QUERY_STRING':'rota=/api/v1/interface'+extra})

    def test_apenas_limites_publicos_sem_banco(self):
        codigo, _, doc=self.pedir('[interface]\nmapa_min_percentual = 65\nmapa_min_altura_px = 220\n[assistente]\nchave_arquivo = segredo-privado\n')
        self.assertEqual(codigo,200)
        self.assertEqual(doc,{'sucesso':True,'resultado':{'mapa_min_percentual':65,'mapa_min_altura_px':220}})
        self.assertNotIn('segredo',json.dumps(doc))

    def test_padroes_e_limites_para_edicao_manual_invalida(self):
        self.assertEqual(self.pedir()[2]['resultado'],{'mapa_min_percentual':50,'mapa_min_altura_px':180})
        _, _, doc=self.pedir('[interface]\nmapa_min_percentual = 500\nmapa_min_altura_px = -1\n')
        self.assertEqual(doc['resultado'],{'mapa_min_percentual':90,'mapa_min_altura_px':120})
        self.assertEqual(self.pedir('[interface]\nmapa_min_percentual = invalido\n')[2]['resultado']['mapa_min_percentual'],50)

    def test_metodo_e_formato_incorretos_sao_recusados(self):
        self.assertEqual(self.pedir(metodo='PUT')[0],405)
        self.assertEqual(self.pedir(extra='&formato=xml')[0],400)

    def test_editor_de_configuracao_valida_os_limites(self):
        configuracao._validar({('interface','mapa_min_percentual'):'65',('interface','mapa_min_altura_px'):'240'})
        for par,valor in [(('interface','mapa_min_percentual'),'0'),(('interface','mapa_min_altura_px'),'9999')]:
            with self.subTest(par=par), self.assertRaises(governanca.GovernancaError):
                configuracao._validar({par:valor})
