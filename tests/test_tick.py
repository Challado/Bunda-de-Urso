# -*- coding: utf-8 -*-
"""Tick do coletor: agenda por fonte, vencimento, backoff e lock.

O tick le a ultima tentativa do proprio banco (iniciada_em). Por isso os
testes ancoram o "agora" no relogio real (base) e so deslocam a partir dele.
"""
import datetime
import os
import unittest

from coletor import tick
from coletor.fontes.antt import ColetorANTT
from tests import common

TZ = datetime.timezone.utc

AGENDA = {
    "antt": {
        "rotulo": "ANTT (teste)",
        "conector": ColetorANTT,
        "intervalo_s": 3600,
        "url_direta": None,
        "ativo": True,
    }
}


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


class TestTick(unittest.TestCase):

    def setUp(self):
        self.tmp = common.ambiente_temporario()
        self.db = os.path.join(self.tmp, "radar.sqlite3")
        self.base = tick.agora_utc()

    def _agora(self, **delta):
        return self.base + datetime.timedelta(**delta)

    def _run(self, **kw):
        kw.setdefault("agora", self.base)
        kw.setdefault("agenda", AGENDA)
        kw.setdefault("db_path", self.db)
        return tick.executar(**kw)

    def _primeira(self):
        return self._run(arquivos={"antt": common.ANTT_FIXTURE})

    # -- decisao -----------------------------------------------------------
    def test_primeira_execucao_roda(self):
        res = self._primeira()
        self.assertEqual(res[0]["acao"], "executado")
        self.assertEqual(res[0]["criados"], 3)

    def test_dentro_do_intervalo_nao_roda(self):
        self._primeira()
        res = self._run(arquivos={"antt": common.ANTT_FIXTURE},
                        agora=self._agora(minutes=30))
        self.assertEqual(res[0]["acao"], "nao_vencido")
        self.assertAlmostEqual(res[0]["faltam_s"], 1800, delta=5)

    def test_intervalo_vencido_roda(self):
        self._primeira()
        res = self._run(arquivos={"antt": common.ANTT_FIXTURE},
                        agora=self._agora(hours=2))
        self.assertEqual(res[0]["acao"], "executado")

    def test_forcar_ignora_agenda(self):
        self._primeira()
        res = self._run(arquivos={"antt": common.ANTT_FIXTURE},
                        agora=self._agora(minutes=1), forcar=["antt"])
        self.assertEqual(res[0]["acao"], "executado")

    def test_sem_url_direta_pula(self):
        res = self._run()
        self.assertEqual(res[0]["acao"], "pulado")
        self.assertEqual(res[0]["motivo"], "sem_url_direta")

    def test_dry_run_nao_coleta(self):
        res = self._run(arquivos={"antt": common.ANTT_FIXTURE}, dry_run=True)
        self.assertEqual(res[0]["acao"], "executaria")

    def test_inativo(self):
        agenda = {"antt": dict(AGENDA["antt"], ativo=False)}
        res = self._run(agenda=agenda)
        self.assertEqual(res[0]["acao"], "inativo")

    # -- erro e backoff ----------------------------------------------------
    def test_erro_na_ingestao_e_backoff(self):
        ruim = os.path.join(self.tmp, "ruim.json")
        with open(ruim, "w", encoding="utf-8") as f:
            f.write("{{{ isso nao e json")
        res = self._run(arquivos={"antt": ruim})
        self.assertEqual(res[0]["acao"], "erro")
        # na passada seguinte (1 min depois) o backoff impede nova tentativa
        res2 = self._run(arquivos={"antt": ruim},
                         agora=self._agora(minutes=1))
        self.assertEqual(res2[0]["acao"], "nao_vencido")

    # -- unidade -----------------------------------------------------------
    def test_espera_backoff_exponencial(self):
        hist_ok = [{"status": "ok", "iniciada_em": _ts(self.base)}]
        self.assertEqual(tick.espera_s(600, hist_ok), 600)
        hist_err1 = [{"status": "erro", "iniciada_em": _ts(self.base)}]
        self.assertEqual(tick.espera_s(600, hist_err1), 600)
        hist_err3 = [{"status": "erro", "iniciada_em": _ts(self.base)}] * 3
        self.assertEqual(tick.espera_s(600, hist_err3), 2400)
        hist_err9 = [{"status": "erro", "iniciada_em": _ts(self.base)}] * 9
        self.assertEqual(tick.espera_s(600, hist_err9), 600 * 8)

    def test_espera_minimo_em_erro(self):
        hist = [{"status": "erro", "iniciada_em": _ts(self.base)}]
        self.assertEqual(tick.espera_s(10, hist), 300)


if __name__ == "__main__":
    unittest.main()
