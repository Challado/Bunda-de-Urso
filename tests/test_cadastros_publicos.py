"""Publicacoes reais, exclusoes, historico e carga pela entrada unica da API."""
import copy
import base64
import gzip
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from coletor import agenda, http, sync
from coletor.fontes.cadastros_publicos import NOVAS_FONTES
from coletor.fontes.cetsp import ColetorCETSP, decodificar_dsr, consulta, json_publico
from coletor.fontes.sie_sc import ColetorSIEPortateis, ColetorSIELocais
from core import db
from tests.test_http import _Resp, _roteiro

ROOT = Path(__file__).resolve().parents[1]
PASTA = ROOT / "tests/fixtures/cadastros_publicos"
FONTES = dict(NOVAS_FONTES, cetsp=ColetorCETSP,
              sie_sc_portateis=ColetorSIEPortateis, sie_sc_locais=ColetorSIELocais)
CONTAGENS = dict(der_es=392, der_pe_lombadas=119, der_pe_mistos=61,
                curitiba_pr=293, salvador_ba=106, aracaju_se=44,
                daer_rs_fixos=60, daer_rs_redutores=131,
                joinville_cadastro_sc=54, cetsp=2032,
                sie_sc_portateis=38, sie_sc_locais=662)


def carregar(chave):
    cls = FONTES[chave]
    return cls().carregar(str(PASTA / (chave + "." + cls.FORMATO)))[3]


class CadastrosPublicosTest(unittest.TestCase):
    def test_publicacoes_reais_com_ids_unicos_e_sem_geocodificacao_inventada(self):
        for chave, total in CONTAGENS.items():
            with self.subTest(chave=chave):
                cls = FONTES[chave]
                raw = carregar(chave)
                self.assertEqual(len(raw), total)
                self.assertEqual(len({r["identificador"] for r in raw}), total)
                for i, r in enumerate(raw):
                    n = cls().normalizar(i, r)
                    self.assertEqual(n["uf"], cls.UF)
                    lat, lon = r.get("latitude"), r.get("longitude")
                    if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        self.assertIsNone(n.get("latitude"))
                        self.assertIsNone(n.get("longitude"))
                    else:
                        self.assertEqual(n.get("latitude"), lat)
                    self.assertEqual(n.get("numero_serie"), r.get("numero_serie"))

    def test_der_es_inativos_e_series_multiplas_nao_viram_serie_unica(self):
        raw = carregar("der_es")
        self.assertTrue(any(r["situacao"] == "inativo" for r in raw))
        removidos = [r for r in raw if "Removido em" in r["endereco"]]
        self.assertTrue(removidos)
        self.assertTrue(all(r["situacao"] == "inativo" for r in removidos))
        self.assertTrue(any("/" in r["serie_publicada"] and r["numero_serie"] is None for r in raw))

    def test_pe_rowspan_agrupa_faixas_sem_duplicar_equipamento(self):
        raw = carregar("der_pe_lombadas")
        self.assertEqual(raw[0]["identificador"], "DERPE1348")
        self.assertEqual(raw[0]["numero_serie"], "R15086")
        self.assertEqual(raw[0]["latitude"], -8.082805)
        self.assertEqual(len(raw[0]["faixas_publicadas"]), 2)
        self.assertEqual(raw[0]["velocidade_geral"], 60)

    def test_curitiba_exclui_16_cameras_sem_fiscalizacao_de_velocidade(self):
        publicado = (PASTA / "curitiba_pr.html").read_text()
        self.assertEqual(publicado.count('lblIdentificacao_'), 309)
        self.assertEqual(len(carregar("curitiba_pr")), 293)

    def test_nao_inventa_validade_atividade_ou_velocidade_nao_publicada(self):
        for chave in ("salvador_ba", "daer_rs_fixos", "joinville_cadastro_sc"):
            for i, r in enumerate(carregar(chave)):
                n = FONTES[chave]().normalizar(i, r)
                self.assertIsNone(n["situacao"])
                if chave != "salvador_ba":
                    self.assertIsNone(n["velocidade_geral"])
        self.assertIsNone(carregar("aracaju_se")[0].get("numero_serie"))
        self.assertEqual(carregar("aracaju_se")[0]["numero_inmetro"], "13392023")

    def test_dsr_com_nulos_repeticao_indices_e_literais(self):
        doc = json.loads((PASTA / "cetsp.json").read_text())
        raw = decodificar_dsr(doc)
        self.assertEqual(len(raw), 2126)
        # A linha 101 alterna indice de dicionario e literal na mesma coluna.
        self.assertEqual(raw[100]["CÓDIGO LOCAL"], "2686")
        self.assertEqual(raw[100]["TIPO"], "FIXO")
        normalizados = carregar("cetsp")
        self.assertEqual(sum(r["situacao"] == "ativo" for r in normalizados), 837)
        self.assertEqual(normalizados[0]["situacao"], "inativo")
        self.assertTrue(any(r["velocidade_geral"] is None for r in normalizados))
        for incompleto in (False, None):
            alterado = copy.deepcopy(doc)
            alterado["results"][0]["result"]["data"]["dsr"]["DS"][0]["IC"] = incompleto
            with self.assertRaisesRegex(ValueError, "incompleta"):
                decodificar_dsr(alterado)

    def test_consulta_cet_so_colunas_publicas_de_equipamentos(self):
        comando = consulta(123)["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]
        self.assertNotIn("Where", comando["Query"])
        nomes = [x["Column"]["Property"] for x in comando["Query"]["Select"]]
        self.assertNotIn("Nº DOCUMENTO/SOLICITANTE", nomes)
        self.assertIn("DESATIVAÇÃO", nomes)

    def test_cet_descobre_painel_e_modelo_quando_tick_passa_pagina(self):
        referencia = base64.b64encode(json.dumps({"k": "11111111-1111-1111-1111-111111111111"}).encode()).decode()
        pagina = ('<a href="https://app.powerbi.com/view?r=' + referencia + '">Mapa</a>').encode()
        original = (PASTA / "cetsp.json").read_bytes()
        with patch('coletor.fontes.cetsp.http.baixar', side_effect=[
                (pagina, {}, ''), (gzip.compress(b'{"models":[{"id":123}]}'), {}, ''), (original, {}, '')]) as baixar:
            c = ColetorCETSP()
            corpo, ext, mime, linhas = c.carregar(c.resolver_url())
        self.assertEqual(corpo, original)
        self.assertEqual(len(linhas), 2032)
        chamada = baixar.call_args_list[-1]
        self.assertEqual(chamada.kwargs['method'], 'POST')
        self.assertEqual(json.loads(chamada.kwargs['data'])['modelId'], 123)

    def test_cet_preserva_resposta_gzip_original_e_le_sem_perder_registros(self):
        original = gzip.compress((PASTA / "cetsp.json").read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "cet.json.gz"
            p.write_bytes(original)
            corpo, ext, mime, linhas = ColetorCETSP().carregar(str(p))
        self.assertEqual(corpo, original)
        self.assertEqual(ext, '.json.gz')
        self.assertEqual(len(linhas), 2032)
        with patch('coletor.http.MAX_BYTES_PADRAO', 10):
            with self.assertRaisesRegex(ValueError, 'excede o limite'):
                json_publico(original)

    def test_agenda_e_cli_oferecem_mesmas_fontes_sem_rotina_externa(self):
        for chave, cls in FONTES.items():
            self.assertIs(sync.FONTES[chave], cls)
            self.assertIs(agenda.AGENDA_PADRAO[chave]["conector"], cls)
            self.assertEqual(agenda.AGENDA_PADRAO[chave]["intervalo_s"], agenda.SEMANA)

    def test_formato_alterado_nao_publica_cadastro_vazio(self):
        for chave, cls in FONTES.items():
            with self.subTest(chave=chave), tempfile.TemporaryDirectory() as temp:
                p = Path(temp) / "pagina.html"
                p.write_text('<html>servico indisponivel</html>')
                if cls.FORMATO != "json":
                    with self.assertRaises(ValueError):
                        cls().carregar(str(p))

    def test_sc_inventario_sem_gps_separado_de_662_locais_elegiveis(self):
        self.assertTrue(all(r["numero_serie"] for r in carregar("sie_sc_portateis")))
        n = ColetorSIEPortateis().normalizar(0, carregar("sie_sc_portateis")[0])
        self.assertEqual(n["tipo_radar"], "portatil")
        self.assertIsNone(n["latitude"])
        r = carregar("sie_sc_locais")[0]
        self.assertEqual(r["velocidade_regulamentada"], 80)
        self.assertEqual(r["velocidade_considerada"], 88)
        n = ColetorSIELocais().normalizar(0, r)
        self.assertEqual(n["tipo_registro"], "trecho_elegivel")
        self.assertEqual(n["vigencia_inicio"], "2023-05-16")
        self.assertEqual(n["sentido"], "decrescente")
        self.assertIsNone(n["radar_instalado_confirmado"])
        self.assertNotIn("municipio_ibge", n)

    def test_carga_api_idempotente_das_doze_publicacoes(self):
        with tempfile.TemporaryDirectory() as temp:
            conf = Path(temp) / "radar.conf"
            conf.write_text('[dados]\ndir = ' + temp + '\n')
            env = dict(os.environ, RADAR_CONF=str(conf))
            banco = Path(temp) / "teste.sqlite3"
            # Cadastro de municipios real do projeto, sem inventar codigo IBGE.
            with closing(db.connect(str(banco))) as conn:
                db.init_db(conn)
                for m in json.loads((ROOT / 'config/municipios_ibge.json').read_text())["municipios"]:
                    db.insert(conn, 'MUNICIPIO', {k: m[k] for k in ('codigo_ibge', 'nome', 'uf_sigla')})
                conn.commit()
            for chave, total in CONTAGENS.items():
                cls = FONTES[chave]
                entrada = Path(temp) / (chave + "." + cls.FORMATO)
                entrada.write_bytes((PASTA / entrada.name).read_bytes())
                comando = [sys.executable, str(ROOT / "web/api.pse"), "sync", "--fonte", chave,
                    "--arquivo", str(entrada), "--db", str(banco), "--sem-publicar"]
                with self.subTest(chave=chave):
                    p = subprocess.run(comando, capture_output=True, text=True, env=env, timeout=120)
                    self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                    resumo = json.loads(p.stdout)
                    self.assertEqual(resumo["rejeitados"], 0)
                    self.assertEqual(resumo["criados"], total)
                    p = subprocess.run(comando, capture_output=True, text=True, env=env, timeout=120)
                    self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                    self.assertTrue(json.loads(p.stdout)["sem_mudanca"])
            with closing(db.connect(str(banco))) as conn:
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM FONTE').fetchone()[0], 12)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM PONTO_FISCALIZACAO').fetchone()[0], 3330)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM TRECHO_ELEGIVEL').fetchone()[0], 662)
                from core.manutencao.auditar_coleta import medir, comparar
                pisos = json.loads((ROOT / 'config/cobertura_minima.json').read_text())
                self.assertEqual(comparar(medir(conn), pisos, 1.0), [])


class PublicacaoHTTPTest(unittest.TestCase):
    def test_json_publico_no_downloader_centralizado(self):
        abrir, chamadas = _roteiro([_Resp(corpo=b'{}')])
        with patch('coletor.http._abrir', abrir):
            http.baixar('https://publico.example/dados', method='POST', data=b'{}',
                        headers={'Content-Type': 'application/json', 'X-PowerBI-ResourceKey': 'publico'})
        h = {k.lower(): v for k, v in chamadas[0][0].header_items()}
        self.assertEqual(h['content-type'], 'application/json')

    def test_nao_repassa_referencia_publica_em_redirect_para_outro_host(self):
        abrir, chamadas = _roteiro([_Resp(status=302, headers={'Location': 'https://outro.example/x'}), _Resp(corpo=b'{}')])
        with patch('coletor.http._abrir', abrir):
            http.baixar('https://publico.example/dados', headers={'X-PowerBI-ResourceKey': 'publico'})
        self.assertNotIn('x-powerbi-resourcekey', {k.lower() for k, _ in chamadas[1][0].header_items()})

    def test_rejeita_cabecalho_arbitrario_credencial_e_injecao(self):
        for h in ({'Host': 'outro'}, {'Authorization': 'x'}, {'Cookie': 'x'}, {'Accept': 'x\r\ny'}):
            with self.assertRaises(http.ErroFonte):
                http.baixar('https://publico.example/dados', headers=h)
