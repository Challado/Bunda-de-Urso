"""PDF oficial AGETO, carga pela API e juncao com a metrologia do PSIE."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from coletor import agenda, http
from coletor.fontes.ageto_to import ColetorAGETOTO
from coletor.fontes.inmetro import ColetorINMETRO
from core import config, consultas, db, governanca
from core.manutencao.carregar_verificacao_metrologica import carregar_do_banco
from tests import common

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "tests/fixtures/ageto_to/lista_radares.pdf"


def municipios_to(conn):
    db.init_db(conn)
    # Cadastro oficial que ja existe na instalacao; nao usar nome como PK ficticia.
    for m in json.loads((ROOT / "config/municipios_ibge.json").read_text())["municipios"]:
        if m["uf_sigla"] == "TO":
            db.insert(conn, "MUNICIPIO", {k: m[k] for k in ("codigo_ibge", "nome", "uf_sigla")})
    conn.commit()


@unittest.skipUnless(shutil.which("pdftotext"), "poppler-utils necessario para ler o PDF oficial")
class TestAGETO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registros = ColetorAGETOTO().carregar(str(PDF))[3]

    def test_pdf_real_preserva_58_instrumentos_e_municipios_quebrados(self):
        self.assertEqual(len(self.registros), 58)
        c = ColetorAGETOTO()
        mapa = {r["numero_serie"]: c.normalizar(i, r) for i, r in enumerate(self.registros)}
        self.assertEqual(mapa["0013"]["municipio_nome"], "PALMAS")
        self.assertEqual(mapa["0014"]["municipio_nome"], "MIRACEMA DO TOCANTINS")
        self.assertEqual(mapa["0015"]["municipio_nome"], "PALMAS")
        self.assertEqual(mapa["0055"]["municipio_nome"], "DIVINÓPOLIS DO TOCANTINS")
        self.assertEqual(mapa["D0245"]["municipio_nome"], "MONTE SANTO DO TOCANTINS")
        self.assertEqual(mapa["D0246"]["municipio_nome"], "PARAÍSO DO TOCANTINS")
        self.assertEqual(mapa["0061"]["municipio_nome"], "SÃO BENTO DO TOCANTINS")
        # Formas diferentes realmente publicadas: sem virgula e com grau.
        self.assertEqual(mapa["0050"]["latitude"], -5.70112)
        self.assertEqual(mapa["0055"]["longitude"], -49.20464)
        self.assertEqual(mapa["D0743"]["latitude"], -12.246564)
        self.assertEqual(mapa["D0830"]["longitude"], -48.8671231)

    def test_caseara_dados_publicados_sem_inferir_atividade_ou_sentidos(self):
        raw = next(r for r in self.registros if r["numero_serie"] == "0049")
        d = ColetorAGETOTO().normalizar(0, raw)
        self.assertEqual((d["latitude"], d["longitude"]), (-9.265766, -49.956937))
        self.assertEqual(d["identificador"], "770")
        self.assertEqual(d["via_codigo"], "TO-080")
        self.assertEqual(d["km"], 251)
        self.assertEqual(d["velocidade_geral"], 40)
        self.assertEqual(raw["faixas"], "2")
        self.assertIsNone(d["situacao"])
        self.assertIsNone(d["sentido"])

    def test_gps_ilegivel_preserva_registro_sem_inventar_posicao(self):
        raw = dict(self.registros[23], coordenadas="NAO INFORMADO")
        d = ColetorAGETOTO().normalizar(0, raw)
        self.assertIsNone(d["latitude"])
        self.assertIsNone(d["longitude"])
        self.assertEqual(d["numero_serie"], "0049")

    def test_formato_alterado_ou_pdf_escaneado_nao_vira_lote_vazio(self):
        for texto in ("", "Estudo tecnico TO-080 km 251", "TO-080 251 tabela alterada"):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                ColetorAGETOTO.extrair_registros(texto)

    def test_carga_real_pela_api_e_reingestao_idempotente(self):
        with tempfile.TemporaryDirectory() as pasta:
            env = {k: v for k, v in os.environ.items() if k not in
                   ("REQUEST_METHOD", "GATEWAY_INTERFACE", "QUERY_STRING", "PATH_INFO")}
            env.update(RADAR_DB=str(Path(pasta) / "radar.sqlite3"), RADAR_DATA_DIR=pasta)
            conf = Path(pasta) / "radar.conf"
            conf.write_text("[dados]\ndir = %s\nbanco = radar.sqlite3\n" % pasta)
            env["RADAR_CONF"] = str(conf)
            with closing(db.connect(env["RADAR_DB"])) as conn:
                municipios_to(conn)
            comando = [sys.executable, str(ROOT / "web/api.pse"), "sync", "--fonte", "ageto_to",
                       "--arquivo", str(PDF)]
            primeira = subprocess.run(comando, env=env, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(primeira.returncode, 0, primeira.stderr)
            resumo = json.loads(primeira.stdout)
            self.assertEqual(resumo["criados"], 58)
            self.assertEqual(resumo["rejeitados"], 0)
            self.assertEqual(resumo["hash_sha256"], hashlib.sha256(PDF.read_bytes()).hexdigest())
            segunda = subprocess.run(comando, env=env, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(segunda.returncode, 0, segunda.stderr)
            self.assertEqual(json.loads(segunda.stdout)["criados"], 0)
            alterado = Path(pasta) / "formato_alterado.txt"
            alterado.write_text("TO-080 251 formato nao reconhecido")
            falha = subprocess.run(comando[:-1] + [str(alterado)], env=env, cwd=ROOT,
                                   capture_output=True, text=True, timeout=30)
            self.assertNotEqual(falha.returncode, 0)
            with closing(db.connect_readonly(env["RADAR_DB"])) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM PONTO_FISCALIZACAO").fetchone()[0], 58)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM PONTO_FISCALIZACAO WHERE municipio_id IS NOT NULL").fetchone()[0], 58)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM POSICAO_GEOGRAFICA").fetchone()[0], 58)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM IDENTIFICADOR_EQUIPAMENTO").fetchone()[0], 58)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM FAIXA_FISCALIZACAO").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM SNAPSHOT_PUBLICADO").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT status FROM EXECUCAO_COLETA ORDER BY id DESC LIMIT 1").fetchone()[0], "erro")
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_juncao_ageto_inmetro_e_comunitario_separado(self):
        antiga = {k: getattr(config, k) for k in ("DATA_DIR", "RAW_DIR", "STAGING_DIR", "DB_PATH")}
        pasta = common.ambiente_temporario()
        self.addCleanup(shutil.rmtree, pasta)
        for k, valor in antiga.items():
            self.addCleanup(setattr, config, k, valor)
        con = db.connect(config.DB_PATH)
        self.addCleanup(con.close)
        governanca.garantir_esquema(con)
        municipios_to(con)
        ag = ColetorAGETOTO(conn=con)
        ag.sincronizar(str(PDF))
        pid = db.scalar(con, "SELECT p.id FROM PONTO_FISCALIZACAO p JOIN MUNICIPIO m "
                        "ON m.codigo_ibge=p.municipio_id WHERE m.nome='Caseara'")
        psie = ColetorINMETRO(conn=con)
        bruto = {"NumeroInmetro": "770", "NumeroSerie": "0049", "SiglaUf": "TO",
                 "Municipio": "CASEARA", "TipoMedidor": "Fixo", "LocalVerificacao": "TO-080 KM251",
                 "Faixas": [{"NumeroFaixa": "1", "Sentido": "DIVISA TO/PA", "VelocidadeNominal": "40"}],
                 "Historico": [{"NumeroCertificado": "15773453", "DataLaudo": "13/04/2026",
                                "DataValidade": "12/04/2027", "Resultado": "Aprovado"}]}
        psie.ingerir_registros([bruto])
        carregar_do_banco(con)
        ponto = consultas.buscar_ponto_por_id(con, pid)
        self.assertEqual(ponto["localizacao"]["latitude"], -9.265766)
        eq = ponto["equipamentos"][0]
        self.assertEqual(eq["numero_serie"], "0049")
        self.assertEqual(eq["verificacoes_metrologicas"][0]["numero_certificado"], "15773453")
        self.assertEqual(eq["verificacoes_metrologicas"][0]["validade_ate"], "2027-04-12")
        self.assertEqual(len(ponto["dados_por_fonte"]), 2)
        self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM PONTO_FISCALIZACAO"), 59)
        self.assertEqual(db.scalar(con, "SELECT COUNT(*) FROM EQUIPAMENTO"), 59)
        # Producao antiga: numero Inmetro vinculado apenas ao ponto.
        con.execute("DELETE FROM IDENTIFICADOR_EQUIPAMENTO WHERE equipamento_id=59")
        self.assertEqual(len(consultas.buscar_ponto_por_id(con, pid)["equipamentos"][0]["verificacoes_metrologicas"]), 1)
        con.execute("UPDATE EQUIPAMENTO SET numero_serie='0050' WHERE id=59")
        self.assertEqual(consultas.buscar_ponto_por_id(con, pid)["equipamentos"][0]["verificacoes_metrologicas"], [])
        con.execute("UPDATE EQUIPAMENTO SET numero_serie='0049' WHERE id=59")
        # Um numero Inmetro diferente nao e ignorado por coincidir a serie curta.
        con.execute("UPDATE IDENTIFICADOR_EXTERNO SET valor='771' WHERE fonte_id="
                    "(SELECT id FROM FONTE WHERE nome LIKE 'INMETRO%')")
        self.assertEqual(consultas.buscar_ponto_por_id(con, pid)["equipamentos"][0]["verificacoes_metrologicas"], [])
        con.execute("UPDATE IDENTIFICADOR_EXTERNO SET valor='00.000.770' WHERE fonte_id="
                    "(SELECT id FROM FONTE WHERE nome LIKE 'INMETRO%')")
        self.assertEqual(len(consultas.buscar_ponto_por_id(con, pid)["equipamentos"][0]["verificacoes_metrologicas"]), 1)
        from coletor.fontes.submissao_publica import ColetorSubmissaoPublica
        comunitario = ColetorSubmissaoPublica(conn=con).ingerir_registros(
            [{"latitude": -9.265218, "longitude": -49.956872, "velocidade_geral": 40}])
        cid = comunitario["detalhes"][0]["ponto_id"]
        publicado = consultas.buscar_ponto_por_id(con, cid)
        self.assertEqual(publicado["localizacao"]["latitude"], -9.265218)
        self.assertEqual(publicado["equipamentos"][0]["verificacoes_metrologicas"], [])
        # A ausencia do Inmetro nao remove o equipamento oficial da AGETO.
        con.execute("UPDATE PONTO_FISCALIZACAO SET removido_em='2026-10-21' WHERE id<>? AND id<>?", (pid, cid))
        self.assertIsNotNone(consultas.buscar_ponto_por_id(con, pid))


class TestAGETODescoberta(unittest.TestCase):
    def test_escolhe_lista_geral_e_rejeita_estudos_e_dominio_estranho(self):
        html = '''<a href="https://central.to.gov.br/download/482935">12 - CEV 049 - TO 080 - KM 251.pdf</a>
        <a href="https://outro.example/lista.pdf">LISTA RADARES - AGETO.rev01.pdf</a>
        <a href='https://central.to.gov.br/download/999999'><span>LISTA RADARES - AGETO.rev02.pdf</span></a>'''
        self.assertEqual(ColetorAGETOTO.descobrir_recursos(html),
                         {"pdf": "https://central.to.gov.br/download/999999"})
        with patch("coletor.fontes.ageto_to.http.baixar", side_effect=http.ErroFonte("fora")):
            self.assertEqual(ColetorAGETOTO.resolver_url(), ColetorAGETOTO.URL_FALLBACK)

    def test_resposta_html_nao_e_importada_como_pdf(self):
        with patch("coletor.fontes.ageto_to.http.baixar", return_value=(b"<html>erro</html>", {}, ColetorAGETOTO.URL_FALLBACK)):
            with self.assertRaisesRegex(ValueError, "nao e um PDF"):
                ColetorAGETOTO().carregar(ColetorAGETOTO.URL_FALLBACK)

    def test_agendada_semanalmente_sem_outra_entrada_da_aplicacao(self):
        item = agenda.AGENDA_PADRAO["ageto_to"]
        self.assertTrue(item["ativo"])
        self.assertEqual(item["intervalo_s"], agenda.SEMANA)
        self.assertIs(item["conector"], ColetorAGETOTO)
