# -*- coding: utf-8 -*-
"""Paridade: a MESMA consulta em json/ndjson/xml/txt decodifica nos mesmos
valores (spec 12, 17.5)."""
import json
import unittest
import xml.etree.ElementTree as ET

from core.serializers import serialize
from core.serializers import campos
from tests.common import exemplo_ponto


def _meta():
    return {
        "sucesso": True, "versao_api": "1.0", "versao_esquema": "1.0",
        "consultado_em": "2026-10-10T12:00:00+00:00",
        "consulta": {"lat": -24.9555, "lon": -53.4552, "raio_metros": 1000},
        "resultado": {"total_pontos": 1, "total_equipamentos": 1,
                      "retornados": 1, "proximo_cursor": None,
                      "status": "completo", "total_operacoes": 0},
        "cobertura": {}, "base": {"snapshot_id": "rb-1"},
    }


def _unquote(celula):
    if len(celula) >= 2 and celula[0] == '"' and celula[-1] == '"':
        return celula[1:-1].replace('""', '"')
    return celula


class TestParidade(unittest.TestCase):

    def setUp(self):
        self.ponto = exemplo_ponto()
        self.records = [self.ponto]
        self.meta = _meta()

    def test_json_roundtrip(self):
        ctype, corpo = serialize("json", self.records, self.meta)
        self.assertIn("application/json", ctype)
        env = json.loads(corpo)
        self.assertTrue(env["sucesso"])
        self.assertEqual(env["resultado"]["pontos"][0]["id"], "P-EXEMPLO-1")

    def test_ndjson_meta_e_ponto(self):
        _, corpo = serialize("ndjson", self.records, self.meta)
        linhas = corpo.rstrip("\n").split("\n")
        self.assertEqual(json.loads(linhas[0])["tipo_registro"], "meta")
        self.assertEqual(json.loads(linhas[1])["id"], "P-EXEMPLO-1")
        self.assertEqual(json.loads(linhas[-1])["tipo_registro"], "fechamento")

    def test_xml_parseavel(self):
        _, corpo = serialize("xml", self.records, self.meta)
        root = ET.fromstring(corpo.split("?>", 1)[-1])
        p = root.find("./resultado/pontos/ponto")
        self.assertIsNotNone(p)
        self.assertEqual(p.find("id").text, "P-EXEMPLO-1")

    def test_valores_iguais_entre_formatos(self):
        _, cj = serialize("json", self.records, self.meta)
        _, cn = serialize("ndjson", self.records, self.meta)
        _, cx = serialize("xml", self.records, self.meta)
        _, ct = serialize("txt", self.records, self.meta, delimitador="|")

        rec_json = json.loads(cj)["resultado"]["pontos"][0]
        rec_ndjson = json.loads(cn.rstrip("\n").split("\n")[1])

        root = ET.fromstring(cx.split("?>", 1)[-1])
        p = root.find("./resultado/pontos/ponto")
        xml_vals = {
            "id": p.find("id").text,
            "tipo_registro": p.find("tipo_registro").text,
            "lat": p.find("localizacao/latitude").text,
            "lon": p.find("localizacao/longitude").text,
            "uf": p.find("localizacao/uf").text,
            "municipio": p.find("localizacao/municipio").text,
        }

        celulas = ct.rstrip("\n").split("|")
        txt_vals = {
            "id": _unquote(celulas[0]),
            "tipo_registro": _unquote(celulas[1]),
            "lat": _unquote(celulas[3]),
            "lon": _unquote(celulas[4]),
            "uf": _unquote(celulas[7]),
            "municipio": _unquote(celulas[8]),
            "tipos_radar_presentes_json": json.loads(_unquote(celulas[13])),
        }

        # json e ndjson: objetos identicos
        self.assertEqual(rec_json, rec_ndjson)
        self.assertEqual(rec_json["id"], "P-EXEMPLO-1")
        self.assertEqual(rec_json["tipo_registro"], "ponto_fiscalizacao")
        self.assertEqual(rec_json["localizacao"]["uf"], "PR")
        self.assertEqual(rec_json["localizacao"]["municipio"], "Cascavel")

        # xml reflete os MESMOS valores
        self.assertEqual(xml_vals["id"], rec_json["id"])
        self.assertEqual(xml_vals["tipo_registro"], rec_json["tipo_registro"])
        self.assertEqual(float(xml_vals["lat"]),
                         rec_json["localizacao"]["latitude"])
        self.assertEqual(float(xml_vals["lon"]),
                         rec_json["localizacao"]["longitude"])
        self.assertEqual(xml_vals["uf"], rec_json["localizacao"]["uf"])
        self.assertEqual(xml_vals["municipio"],
                         rec_json["localizacao"]["municipio"])

        # txt reflete os MESMOS valores (nas 32 colunas canonicas)
        self.assertEqual(txt_vals["id"], rec_json["id"])
        self.assertEqual(txt_vals["tipo_registro"], rec_json["tipo_registro"])
        self.assertEqual(float(txt_vals["lat"]),
                         rec_json["localizacao"]["latitude"])
        self.assertEqual(float(txt_vals["lon"]),
                         rec_json["localizacao"]["longitude"])
        self.assertEqual(txt_vals["uf"], rec_json["localizacao"]["uf"])
        self.assertEqual(txt_vals["municipio"],
                         rec_json["localizacao"]["municipio"])
        self.assertEqual(txt_vals["tipos_radar_presentes_json"],
                         rec_json["tipos_radar_presentes"])

    def test_txt_tem_32_colunas_na_ordem(self):
        _, ct = serialize("txt", self.records, self.meta, delimitador="|")
        self.assertEqual(len(ct.rstrip("\n").split("|")), 32)
        self.assertEqual(campos.TXT_COLUMNS[3], "latitude")
        self.assertEqual(campos.TXT_COLUMNS[4], "longitude")


if __name__ == "__main__":
    unittest.main()
