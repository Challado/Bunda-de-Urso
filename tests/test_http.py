# -*- coding: utf-8 -*-
"""Testes do downloader duro (coletor.http) - offline, sem rede.

Substituem a camada de I/O (``coletor.http._abrir``) e o sleep
(``coletor.http._dormir``) por dublês, exercitando as regras: HTTPS obrigatorio,
redirects salto-a-salto (>5 falha, 303 -> GET), HTTP 304, retry com
Retry-After, corte por max_bytes e corpo vazio.
"""
import io
import unittest
from unittest import mock

import urllib.error

from coletor import http

URL = "https://exemplo.org/arquivo.bin"


class _Resp(object):
    """Resposta HTTP falsa (status/headers/read incremental)."""

    def __init__(self, status=200, corpo=b"", headers=None):
        self.status = status
        self.code = status
        self.headers = headers if headers is not None else {}
        self._corpo = corpo
        self._pendente = True
        self.fechado = False

    def read(self, n=-1):
        if not self._pendente:
            return b""
        self._pendente = False
        return self._corpo

    def close(self):
        self.fechado = True


def _erro(url, code, headers=None, msg="erro"):
    return urllib.error.HTTPError(url, code, msg, headers or {},
                                  io.BytesIO(b""))


def _roteiro(respostas):
    """Devolve (abrir, chamadas) consumindo ``respostas`` em ordem."""
    fila = list(respostas)
    chamadas = []

    def abrir(req, timeout, verificar_ssl):
        chamadas.append((req, timeout, verificar_ssl))
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return abrir, chamadas


# ==========================================================================
# url_checada
# ==========================================================================
class TestUrlChecada(unittest.TestCase):

    def test_aceita_https_publico(self):
        self.assertEqual(http.url_checada(URL), URL)
        self.assertEqual(http.url_checada("https://exemplo.org:443/x"),
                         "https://exemplo.org:443/x")

    def test_rejeita_http(self):
        with self.assertRaises(http.ErroFonte):
            http.url_checada("http://exemplo.org/x")

    def test_rejeita_localhost(self):
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://localhost/x")
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://servico.local/x")
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://algo.internal/x")

    def test_rejeita_ip_literal(self):
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://127.0.0.1/x")
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://[::1]/x")
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://192.168.0.10/dados.csv")

    def test_rejeita_credenciais_embutidas(self):
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://user:senha@exemplo.org/x")

    def test_rejeita_porta_alternativa(self):
        with self.assertRaises(http.ErroFonte):
            http.url_checada("https://exemplo.org:8443/x")


# ==========================================================================
# baixar
# ==========================================================================
class TestBaixar(unittest.TestCase):

    def _patch(self, abrir, dormidas=None):
        pilha = [mock.patch.object(http, "_abrir", abrir)]
        if dormidas is not None:
            pilha.append(mock.patch.object(
                http, "_dormir", lambda s: dormidas.append(s)))
        return pilha

    def test_sucesso_devolve_tripla(self):
        abrir, chamadas = _roteiro([_Resp(200, b"conteudo",
                                          {"Content-Type": "text/plain"})])
        with mock.patch.object(http, "_abrir", abrir):
            corpo, headers, final = http.baixar(URL, etag="abc")
        self.assertEqual(corpo, b"conteudo")
        self.assertEqual(headers.get("Content-Type"), "text/plain")
        self.assertEqual(final, URL)
        # cabeçalhos condicionais enviados
        self.assertEqual(chamadas[0][0].get_header("If-none-match"), "abc")

    def test_https_obrigatorio_sem_rede(self):
        def abrir(*a, **k):
            raise AssertionError("nao deveria chamar a rede")
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.ErroFonte):
                http.baixar("http://exemplo.org/x")

    def test_redirect_mais_de_cinco(self):
        def abrir(req, timeout, verificar_ssl):
            raise _erro(req.full_url, 302, {"Location": URL})
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.ErroFonte) as ctx:
                http.baixar(URL)
        self.assertIn("cinco", str(ctx.exception))

    def test_redirect_303_vira_get(self):
        abrir, chamadas = _roteiro([
            _erro(URL, 303, {"Location": "https://exemplo.org/destino"}),
            _Resp(200, b"ok"),
        ])
        with mock.patch.object(http, "_abrir", abrir):
            corpo, _, final = http.baixar(URL, method="POST", data=b"x=1")
        self.assertEqual(corpo, b"ok")
        self.assertEqual(final, "https://exemplo.org/destino")
        self.assertEqual(chamadas[0][0].get_method(), "POST")
        self.assertEqual(chamadas[1][0].get_method(), "GET")
        self.assertIsNone(chamadas[1][0].data)

    def test_304_nao_modificado_sem_retry(self):
        abrir, chamadas = _roteiro([
            _erro(URL, 304), _erro(URL, 304), _erro(URL, 304),
        ])
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.NaoModificado):
                http.baixar(URL, etag="v1")
        self.assertEqual(len(chamadas), 1)

    def test_429_respeita_retry_after(self):
        dormidas = []
        abrir, chamadas = _roteiro([
            _erro(URL, 429, {"Retry-After": "2"}),
            _Resp(200, b"ok"),
        ])
        with mock.patch.object(http, "_abrir", abrir), \
                mock.patch.object(http, "_dormir", lambda s: dormidas.append(s)):
            corpo, _, _ = http.baixar(URL)
        self.assertEqual(corpo, b"ok")
        self.assertEqual(dormidas, [2])
        self.assertEqual(len(chamadas), 2)

    def test_retry_esgota_em_erro_fonte(self):
        dormidas = []
        abrir, chamadas = _roteiro([_erro(URL, 503)] * 3)
        with mock.patch.object(http, "_abrir", abrir), \
                mock.patch.object(http, "_dormir", lambda s: dormidas.append(s)):
            with self.assertRaises(http.ErroFonte):
                http.baixar(URL)
        self.assertEqual(len(chamadas), 3)
        # backoff exponencial com teto: min(15, 2**tentativa) -> 1, 2
        self.assertEqual(dormidas, [1, 2])

    def test_corte_por_max_bytes(self):
        abrir, _ = _roteiro([_Resp(200, b"0123456789")])
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.ErroFonte):
                http.baixar(URL, max_bytes=5)
        abrir, _ = _roteiro([_Resp(200, b"0123456789")])
        with mock.patch.object(http, "_abrir", abrir):
            corpo, _, _ = http.baixar(URL, max_bytes=10)
        self.assertEqual(corpo, b"0123456789")

    def test_corpo_vazio_em_200_e_erro(self):
        abrir, _ = _roteiro([_Resp(200, b"")])
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.ErroFonte):
                http.baixar(URL)

    def test_400_nao_retenta(self):
        abrir, chamadas = _roteiro([_erro(URL, 404)])
        with mock.patch.object(http, "_abrir", abrir):
            with self.assertRaises(http.ErroFonte):
                http.baixar(URL)
        self.assertEqual(len(chamadas), 1)


# ==========================================================================
# Retry-After
# ==========================================================================
class TestRetryAfter(unittest.TestCase):

    def test_segundos(self):
        self.assertEqual(http._espera_retry_after("12"), 12)

    def test_teto_30_segundos(self):
        self.assertEqual(http._espera_retry_after("999"), 30)

    def test_data_http(self):
        import email.utils
        import datetime
        quando = datetime.datetime.now(datetime.timezone.utc) \
            + datetime.timedelta(seconds=5)
        valor = email.utils.format_datetime(quando)
        espera = http._espera_retry_after(valor)
        self.assertIsNotNone(espera)
        self.assertLessEqual(espera, 30)

    def test_invalido(self):
        self.assertIsNone(http._espera_retry_after(""))
        self.assertIsNone(http._espera_retry_after("nao-e-data"))


if __name__ == "__main__":
    unittest.main()
