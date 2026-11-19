"""Descoberta da edição da ANTT e falhas no fluxo normal do coletor."""

from contextlib import closing
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from coletor import http, tick
from coletor.agenda import AGENDA_PADRAO
from coletor.fontes.antt import ColetorANTT as ANTT
from core import config, db
from tests import common


BASE = ANTT.CKAN_BASE
CATALOGO_API = BASE + "/api/3/action/package_show?id=" + ANTT.CKAN_DATASET
REVISAO = BASE + "/dataset/radar/history/00000000-0000-0000-0000-000000000002"
REVISAO_ANTIGA = BASE + "/dataset/radar?activity_id=00000000-0000-0000-0000-000000000001"
DOWNLOAD = BASE + "/dataset/radar/resource/edicao/download/"
ANTIGO = DOWNLOAD + "dados-dos-radares12_2026.json"
NOVO_JSON = DOWNLOAD + "dados-dos-radares1_2027.json"
NOVO_CSV = DOWNLOAD + "dados-dos-radares1_2027.csv"
BLOQUEIO = http.ErroFonte("HTTP 200 com pagina de bloqueio de acesso")


def pagina(*links):
    return ("<ul>" + "".join(f'<li><a href="{url}">Link</a></li>' for url in links) + "</ul>").encode()


def baixar(respostas):
    def resposta(url, **kwargs):
        corpo = respostas[url]
        if isinstance(corpo, Exception):
            raise corpo
        return corpo, {}, url
    return patch.object(http, "baixar", side_effect=resposta)


class TestANTTAtividades(unittest.TestCase):
    def test_cron_descobre_edicao_da_atividade_e_registra_url_escolhida(self):
        common.ambiente_temporario()
        respostas = {
            ANTT.URL_ATIVIDADES: pagina(REVISAO.removeprefix(BASE), REVISAO_ANTIGA),
            REVISAO: pagina(ANTIGO, NOVO_CSV, NOVO_JSON.removeprefix(BASE)),
            NOVO_JSON: Path(common.ANTT_FIXTURE).read_bytes(),
        }
        with baixar(respostas) as req, patch("core.atualizacoes.registrar") as diario:
            r = tick.executar(agenda={"antt": AGENDA_PADRAO["antt"]})[0]
        self.assertEqual(r["acao"], "executado")
        self.assertEqual(r["criados"], 3)
        self.assertEqual([c.args[0] for c in req.call_args_list], [ANTT.URL_ATIVIDADES, REVISAO, NOVO_JSON])
        coleta = next(c.args[1] for c in diario.call_args_list
                      if c.args[0] == "coleta" and c.args[1].get("estado") == "ok")
        self.assertEqual(coleta["origem"], NOVO_JSON)
        self.assertEqual(coleta["metodo_descoberta"], "atividades")

    def test_atividade_ckan_legada_e_csv_da_mesma_edicao(self):
        respostas = {
            ANTT.URL_ATIVIDADES: pagina(REVISAO_ANTIGA),
            REVISAO_ANTIGA: pagina(ANTIGO, NOVO_JSON, NOVO_CSV.replace("https:", "http:")),
            NOVO_JSON: "<html><title>Em manutenção</title></html>".encode(),
            NOVO_CSV: b"Codigo;Latitude;Longitude\nRADAR;1,25;-50,75\n",
        }
        with baixar(respostas) as req:
            _, ext, mime, registros = ANTT.__new__(ANTT).carregar(None)
        self.assertEqual([c.args[0] for c in req.call_args_list], list(respostas))
        self.assertEqual((ext, mime), (".csv", "text/csv"))
        self.assertEqual(registros[0]["Codigo"], "RADAR")

    def test_catalogo_ckan_tambem_descobre_edicao_nova(self):
        externo = NOVO_JSON.replace(BASE, "https://exemplo.org")
        respostas = {
            ANTT.URL_ATIVIDADES: BLOQUEIO,
            CATALOGO_API: json.dumps({"success": True, "result": {"resources": [
                {"url": NOVO_CSV, "format": "CSV"}, {"url": ANTIGO, "format": "JSON"},
                {"url": externo, "format": "JSON"}]}}).encode(),
            NOVO_CSV: b"Codigo,Latitude,Longitude\nRADAR,1.25,-50.75\n",
        }
        with baixar(respostas) as req:
            self.assertEqual(ANTT.__new__(ANTT).carregar(None)[1], ".csv")
        self.assertEqual([c.args[0] for c in req.call_args_list], list(respostas))

    def test_catalogo_html_descobre_arquivo_quando_atividade_e_api_falham(self):
        respostas = {
            ANTT.URL_ATIVIDADES: BLOQUEIO,
            CATALOGO_API: BLOQUEIO,
            ANTT.URL_CATALOGO: pagina(ANTIGO, NOVO_JSON),
            NOVO_JSON: Path(common.ANTT_FIXTURE).read_bytes(),
        }
        with baixar(respostas) as req:
            self.assertEqual(ANTT.__new__(ANTT).carregar(ANTT.URL_CATALOGO)[1], ".json")
        self.assertEqual([c.args[0] for c in req.call_args_list], list(respostas))

    def test_portal_bloqueado_registra_falha_e_preserva_snapshot(self):
        common.ambiente_temporario()
        respostas = dict.fromkeys((ANTT.URL_ATIVIDADES, CATALOGO_API, ANTT.URL_CATALOGO), BLOQUEIO)
        with closing(db.connect(config.DB_PATH)) as conn:
            coletor = ANTT(conn=conn)
            anterior = coletor.sincronizar(common.ANTT_FIXTURE)
            with baixar(respostas) as req, self.assertRaisesRegex(http.ErroFonte, "descobrir a edição atual"):
                coletor.sincronizar(None)
            self.assertEqual([c.args[0] for c in req.call_args_list], list(respostas))
            self.assertEqual(db.scalar(conn, "SELECT status FROM EXECUCAO_COLETA ORDER BY id DESC LIMIT 1"), "erro")
            self.assertEqual(db.scalar(conn, "SELECT identificador_versao FROM SNAPSHOT_PUBLICADO"), anterior["versao"])
