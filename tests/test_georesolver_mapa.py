# -*- coding: utf-8 -*-
"""Resolvedor km->coordenada ligado ao mapa/raio na API.

Pontos sem POSICAO_GEOGRAFICA mas com via+km ganham coordenada INFERIDA pelo
referenciamento linear; so entram quando resolvem de forma inequivoca
(status 'ok'). Ambiguo / fora_de_faixa / sem_calibracao NAO entram.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import consultas as C                        # noqa: E402
from core import db as dbmod                           # noqa: E402
from core import georesolver                           # noqa: E402
from tests.common import banco_memoria                 # noqa: E402


def _ancora(km, lat, lon, seg=1, pid=None):
    return {"km": km, "lat": lat, "lon": lon, "ponto_id": pid,
            "uf": None, "fonte": None, "segmento": seg}


# BR-000: duas ancoras num unico segmento -> km 5 interpola para -50.05.
CALIB = {
    "BR-000": [_ancora(0.0, -20.0, -50.0), _ancora(10.0, -20.0, -50.1)],
    # BR-AMB: dois segmentos cobrindo o km 5 -> ambiguo.
    "BR-AMB": [_ancora(0.0, -20.0, -50.0, seg=1),
               _ancora(10.0, -20.0, -50.1, seg=1),
               _ancora(0.0, -21.0, -51.0, seg=2),
               _ancora(10.0, -21.0, -51.1, seg=2)],
}


class TestResolvedorNoMapa(unittest.TestCase):
    def setUp(self):
        self.con = banco_memoria()
        self.tipo_via = dbmod.domain_id(self.con, "TIPO_VIA", "federal")
        dbmod.insert(self.con, "MUNICIPIO", {
            "codigo_ibge": "3170206", "uf_sigla": "MG", "nome": "Teste"})
        self.mun = "3170206"          # PK TEXT: usar o codigo explicito
        self.con.commit()
        self._patch = mock.patch.object(georesolver, "calibracao",
                                        return_value=CALIB)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def tearDown(self):
        self.con.close()

    def _via(self, codigo):
        return dbmod.insert(self.con, "VIA", {
            "tipo_via_id": self.tipo_via, "codigo": codigo})

    def _ponto(self, via_id, km, posicao_id=None):
        return dbmod.insert(self.con, "PONTO_FISCALIZACAO", {
            "via_id": via_id, "km": km, "posicao_id": posicao_id,
            "municipio_id": self.mun})

    def test_ponto_sem_posicao_entra_como_inferida(self):
        via = self._via("BR-000")
        pid = self._ponto(via, 5.0)
        recs, meta = C.buscar_pontos(self.con, -20.0, -50.05, 2000)
        self.assertEqual(meta["total_pontos"], 1)
        self.assertEqual(meta["total_inferidos"], 1)
        loc = recs[0]["localizacao"]
        self.assertEqual(loc["qualidade"], "inferida")
        self.assertEqual(loc["metodo_obtencao"], "linear_km")
        self.assertAlmostEqual(loc["latitude"], -20.0)
        self.assertAlmostEqual(loc["longitude"], -50.05)
        self.assertEqual(recs[0]["id"], "P-%d" % pid)

    def test_fora_de_faixa_nao_entra(self):
        via = self._via("BR-000")
        self._ponto(via, 99.0)          # nenhum segmento cobre
        recs, meta = C.buscar_pontos(self.con, -20.0, -50.05, 500000)
        self.assertEqual(meta["total_pontos"], 0)
        self.assertEqual(recs, [])
        self.assertEqual(meta["total_inferidos"], 0)

    def test_ambiguo_nao_entra(self):
        via = self._via("BR-AMB")
        self._ponto(via, 5.0)           # dois segmentos cobrem -> nao escolhe
        recs, meta = C.buscar_pontos(self.con, -20.0, -50.05, 500000)
        self.assertEqual(meta["total_pontos"], 0)

    def test_sem_calibracao_nao_entra(self):
        via = self._via("BR-XXX")
        self._ponto(via, 5.0)           # via desconhecida na calibracao
        recs, meta = C.buscar_pontos(self.con, -20.0, -50.05, 500000)
        self.assertEqual(meta["total_pontos"], 0)

    def test_fora_do_raio_nao_entra(self):
        via = self._via("BR-000")
        self._ponto(via, 5.0)
        recs, meta = C.buscar_pontos(self.con, 10.0, 10.0, 1000)  # longe
        self.assertEqual(meta["total_pontos"], 0)

    def test_convive_com_ponto_com_posicao(self):
        # Um ponto com POSICAO real perto + um inferido no mesmo raio.
        via = self._via("BR-000")
        pos = dbmod.insert(self.con, "POSICAO_GEOGRAFICA", {
            "latitude": -20.0, "longitude": -50.0,
            "qualidade_posicao_id": dbmod.domain_id(
                self.con, "QUALIDADE_POSICAO", "oficial")})
        dbmod.insert(self.con, "PONTO_FISCALIZACAO", {
            "via_id": via, "km": 0.0, "posicao_id": pos,
            "municipio_id": self.mun})
        self._ponto(via, 5.0)
        recs, meta = C.buscar_pontos(self.con, -20.0, -50.0, 8000)
        self.assertEqual(meta["total_pontos"], 2)
        self.assertEqual(meta["total_inferidos"], 1)
        quals = sorted(r["localizacao"]["qualidade"] for r in recs)
        self.assertEqual(quals, ["inferida", "oficial"])


if __name__ == "__main__":
    unittest.main()
