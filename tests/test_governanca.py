# -*- coding: utf-8 -*-
"""Governanca da ingestao: submissao publica, login/sessao, gestao (tokens,
usuarios, bloqueios), correspondencia com o oficial, rate limit e auditoria.

Tudo roda em banco temporario (tests.common.ambiente_temporario); nenhum
teste acessa rede nem o banco de producao.
"""
import json
import unittest

from core import config
from core import db as dbmod
from core import governanca as gov
from coletor.fontes.base_lwb import ColetorBaseLWB
from coletor.fontes.antt import ColetorANTT
from web import nucleo
import tests.common as common


class BaseGov(unittest.TestCase):

    def setUp(self):
        common.ambiente_temporario()
        con = dbmod.connect(config.DB_PATH)
        try:
            gov.garantir_esquema(con)
        finally:
            con.close()
        # defaults de teste (restaurados no tearDown)
        self._limite_original = config.SUBMISSAO_LIMITE
        config.SUBMISSAO_LIMITE = 1000

    def tearDown(self):
        config.SUBMISSAO_LIMITE = self._limite_original

    # -- helpers ----------------------------------------------------------
    def _req(self, metodo, caminho, corpo=None, query="", headers=None,
             ctype="application/json"):
        if corpo is None:
            corpo_b = b""
        elif isinstance(corpo, bytes):
            corpo_b = corpo
        elif isinstance(corpo, str):
            corpo_b = corpo.encode("utf-8")
        else:
            corpo_b = json.dumps(corpo).encode("utf-8")
        env = {
            "REQUEST_METHOD": metodo, "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(corpo_b)), "CONTENT_TYPE": ctype,
            "PATH_INFO": caminho,
            "REQUEST_URI": caminho + (("?" + query) if query else ""),
            "SCRIPT_NAME": "", "REMOTE_ADDR": "203.0.113.9",
            "HTTP_USER_AGENT": "teste/1.0",
        }
        for k, v in (headers or {}).items():
            env[k] = v
        return nucleo.handle_request(env, corpo_b)

    @staticmethod
    def _doc(resp):
        _status, _h, corpo = resp
        return corpo if isinstance(corpo, dict) else json.loads(corpo)

    def _admin(self, login="admin", senha="SenhaForte123"):
        con = dbmod.connect(config.DB_PATH)
        try:
            gov.criar_usuario(con, login, senha, papel="admin",
                              deve_trocar_senha=False)
        finally:
            con.close()
        return login, senha

    def _sessao(self, login="admin", senha="SenhaForte123"):
        status, headers, corpo = self._req(
            "POST", "/api/v1/login", {"login": login, "senha": senha})
        self.assertEqual(status, 200, corpo)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn("radar_sessao=", cookie)
        return cookie.split(";")[0]

    def _token_cookie(self, escopo="admin", nome="t"):
        con = dbmod.connect(config.DB_PATH)
        try:
            _tid, valor = gov.emitir_token(con, nome, escopo)
        finally:
            con.close()
        return valor

    ##-- BUNDITA DE URSO #{8} -- Fixture oficial precisa de fonte governamental, nao do rotulo padrao da base propria. ##
    def _oficial(self, lat, lon, ident):
        con = dbmod.connect(config.DB_PATH)
        try:
            c = ColetorANTT(conn=con)
            c.ingerir_registros([{"Latitude": lat, "Longitude": lon,
                                  "Codigo": ident}], publicar=False)
        finally:
            con.close()

    def _novo_id(self):
        con = dbmod.connect(config.DB_PATH)
        try:
            return dbmod.scalar(con, "SELECT MAX(id) FROM PONTO_FISCALIZACAO")
        finally:
            con.close()


# ---------------------------------------------------------------------------
class TestLoginSessao(BaseGov):

    def test_login_ok_cria_sessao(self):
        self._admin()
        status, headers, corpo = self._req(
            "POST", "/api/v1/login", {"login": "admin",
                                      "senha": "SenhaForte123"})
        self.assertEqual(status, 200)
        self.assertIn("radar_sessao=", headers.get("Set-Cookie", ""))
        doc = self._doc((status, headers, corpo))
        self.assertTrue(doc["sucesso"])
        self.assertEqual(doc["usuario"]["papel"], "admin")

    def test_login_falha_generica(self):
        self._admin()
        status, _h, corpo = self._req(
            "POST", "/api/v1/login", {"login": "admin", "senha": "errada"})
        self.assertEqual(status, 401)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["erro"]["codigo"], "credenciais_invalidas")
        # nao revela se o usuario existe
        status2, _h2, corpo2 = self._req(
            "POST", "/api/v1/login", {"login": "naoexiste", "senha": "x"})
        self.assertEqual(status2, 401)
        self.assertEqual(self._doc((status2, _h2, corpo2))["erro"]["codigo"],
                         "credenciais_invalidas")

    def test_sessao_expirada_e_recusada(self):
        self._admin()
        cookie = self._sessao()
        # força a expiracao no banco
        con = dbmod.connect(config.DB_PATH)
        try:
            con.execute("UPDATE SESSAO SET expira_em='2000-01-01T00:00:00+00:00'")
            con.commit()
        finally:
            con.close()
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 401)
        self.assertIn(self._doc((status, _h, corpo))["erro"]["codigo"],
                      ("sessao_invalida",))

    def test_logout_invalida_sessao(self):
        self._admin()
        cookie = self._sessao()
        status, _h, _c = self._req("POST", "/api/v1/logout",
                                   headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200)
        status2, _h2, _c2 = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status2, 401)


# ---------------------------------------------------------------------------
class TestSubmissaoPublica(BaseGov):

    def test_submissao_valida_cria_colaborativo(self):
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": -23.55, "longitude": -46.63, "municipio": "Sao Paulo",
             "uf": "SP", "via": "BR-116"})
        self.assertEqual(status, 201, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["resultado"]["aceitos"], 1)
        self.assertEqual(doc["resultado"]["corroborados"], 0)
        con = dbmod.connect(config.DB_PATH)
        try:
            row = con.execute(
                "SELECT procedencia, verificacao_status FROM "
                "PONTO_FISCALIZACAO").fetchone()
            self.assertEqual(row["procedencia"], "colaborativo")
            self.assertEqual(row["verificacao_status"], "nao_verificado")
            # auditoria registrada
            self.assertEqual(dbmod.scalar(
                con, "SELECT COUNT(*) FROM RADAR_ALTERACAO WHERE tipo='criado'"),
                1)
            # procedencia publica
            self.assertEqual(dbmod.scalar(
                con, "SELECT COUNT(*) FROM SUBMISSAO_PUBLICA"), 1)
        finally:
            con.close()

    def test_payload_invalido_422(self):
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": "abc", "longitude": "xyz"})
        self.assertEqual(status, 422, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["erro"]["codigo"], "payload_invalido")
        self.assertTrue(doc["erro"]["detalhes"])

    def test_array_com_um_invalido_marca_o_indice(self):
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            [{"latitude": -23.55, "longitude": -46.63},
             {"latitude": 999, "longitude": 0}])
        self.assertEqual(status, 201)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["resultado"]["aceitos"], 1)
        self.assertEqual(len(doc["resultado"]["erros"]), 1)
        self.assertEqual(doc["resultado"]["erros"][0]["indice"], 1)

    def test_zona_sombra_recusa_409(self):
        con = dbmod.connect(config.DB_PATH)
        try:
            gov.criar_bloqueio(con, "zona_sombra", -23.55, -46.63, 1000,
                               "sabotagem", None)
        finally:
            con.close()
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": -23.5501, "longitude": -46.6301})
        self.assertEqual(status, 409, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["erro"]["codigo"], "area_bloqueada")
        self.assertEqual(doc["erro"]["detalhes"][0]["tipo"], "zona_sombra")

    def test_marcacao_falsa_recusa_409(self):
        con = dbmod.connect(config.DB_PATH)
        try:
            gov.criar_bloqueio(con, "marcacao_falsa", -23.55, -46.63, 150,
                               "cadastro falso", None)
        finally:
            con.close()
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": -23.55, "longitude": -46.63})
        self.assertEqual(status, 409, corpo)
        self.assertEqual(self._doc((status, _h, corpo))["erro"]["detalhes"][0]
                         ["tipo"], "marcacao_falsa")

    def test_correspondencia_com_oficial_apenas_sugere_revisao(self):
        self._oficial(-23.5500, -46.6300, "OFICIAL-1")
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": -23.5501, "longitude": -46.6301})
        self.assertEqual(status, 201, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["resultado"]["corroborados"], 0)
        self.assertEqual(doc["resultado"]["correspondencias_sugeridas"], 1)
        con = dbmod.connect(config.DB_PATH)
        try:
            colab = con.execute(
                "SELECT id FROM PONTO_FISCALIZACAO WHERE procedencia="
                "'colaborativo'").fetchone()["id"]
            self.assertEqual(con.execute(
                "SELECT verificacao_status FROM PONTO_FISCALIZACAO WHERE id=?",
                (colab,)).fetchone()[0], "nao_verificado")
            cp = con.execute(
                "SELECT * FROM CORRESPONDENCIA_PONTO WHERE "
                "ponto_colaborativo_id=?", (colab,)).fetchone()
            self.assertIsNotNone(cp)
            self.assertEqual(cp["status"], "corroborado")
            self.assertLessEqual(cp["distancia_metros"],
                                 config.RAIO_CORRESPONDENCIA_M)
        finally:
            con.close()

    def test_rate_limit_429(self):
        config.SUBMISSAO_LIMITE = 2
        for _ in range(2):
            status, _h, corpo = self._req(
                "POST", "/api/v1/radares/submeter",
                {"latitude": -23.55, "longitude": -46.63})
            self.assertEqual(status, 201, corpo)
        status, _h, corpo = self._req(
            "POST", "/api/v1/radares/submeter",
            {"latitude": -23.56, "longitude": -46.64})
        self.assertEqual(status, 429, corpo)
        self.assertEqual(self._doc((status, _h, corpo))["erro"]["codigo"],
                         "limite_submissao")


# ---------------------------------------------------------------------------
class TestGestaoRadar(BaseGov):

    def _colab(self, lat=-23.55, lon=-46.63, ip="203.0.113.9"):
        self._req("POST", "/api/v1/radares/submeter",
                  {"latitude": lat, "longitude": lon},
                  headers={"HTTP_X_FORWARDED_FOR": ip})
        return self._novo_id()

    def test_verificar_radar(self):
        self._admin()
        cookie = self._sessao()
        pid = self._colab()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/radar/%d/verificar" % pid,
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        con = dbmod.connect(config.DB_PATH)
        try:
            self.assertEqual(con.execute(
                "SELECT verificacao_status FROM PONTO_FISCALIZACAO WHERE id=?",
                (pid,)).fetchone()[0], "verificado")
        finally:
            con.close()

    def test_editar_radar(self):
        self._admin()
        cookie = self._sessao()
        pid = self._colab()
        status, _h, corpo = self._req(
            "PATCH", "/api/v1/gestao/radar/%d" % pid,
            {"observacoes": "confirmado no local", "km": 12.5},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        con = dbmod.connect(config.DB_PATH)
        try:
            row = con.execute(
                "SELECT observacoes, km FROM PONTO_FISCALIZACAO WHERE id=?",
                (pid,)).fetchone()
            self.assertEqual(row["observacoes"], "confirmado no local")
            self.assertEqual(row["km"], 12.5)
            self.assertEqual(dbmod.scalar(
                con, "SELECT COUNT(*) FROM RADAR_ALTERACAO WHERE "
                "ponto_id=? AND tipo='editado'", (pid,)), 1)
        finally:
            con.close()

    def test_remover_exige_motivo_e_e_tombstone(self):
        self._admin()
        cookie = self._sessao()
        pid = self._colab()
        # sem motivo -> 422
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/radar/%d/remover" % pid, {},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 422, corpo)
        # com motivo -> tombstone, linha preservada
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/radar/%d/remover" % pid,
            {"motivo": "nao existe radar aqui"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        con = dbmod.connect(config.DB_PATH)
        try:
            row = con.execute(
                "SELECT removido_em, removido_por, motivo_remocao FROM "
                "PONTO_FISCALIZACAO WHERE id=?", (pid,)).fetchone()
            self.assertIsNotNone(row)          # NAO apagou
            self.assertIsNotNone(row["removido_em"])
            self.assertEqual(row["motivo_remocao"], "nao existe radar aqui")
        finally:
            con.close()
        # historico publico mostra a remocao com motivo
        status, _h, corpo = self._req(
            "GET", "/api/v1/radares/%d/historico" % pid)
        self.assertEqual(status, 200, corpo)
        hist = self._doc((status, _h, corpo))["historico"]
        self.assertTrue(any(h["tipo"] == "removido" and
                            h["motivo"] == "nao existe radar aqui"
                            for h in hist))

    def test_removidos_e_desabilitados_nao_abrem_por_id_publico(self):
        self._admin()
        cookie = self._sessao()
        for i, acao in enumerate(("remover", "desabilitar")):
            with self.subTest(acao=acao):
                pid = self._colab(lat=-23.55-i/100)
                rota = "/api/v1/radares/P-%d" % pid
                antes = self._req("GET", rota)
                self.assertEqual(antes[0], 200)
                self.assertEqual(antes[1]["Cache-Control"], "no-store")
                self.assertEqual(self._req("POST", "/api/v1/gestao/radar/%d/%s" % (pid, acao),
                    {"motivo": "cadastro inexistente"}, headers={"HTTP_COOKIE": cookie})[0], 200)
                # A consulta por ID não pode contornar a exclusão, nem com cookie admin.
                for headers in ({}, {"HTTP_COOKIE": cookie}):
                    publico = self._req("GET", rota, query="incluir_ocultos=1", headers=headers)
                    self.assertEqual(publico[0], 404, publico[2])
                administrativo = self._req("GET", "/api/v1/gestao/radar/%d" % pid,
                                           headers={"HTTP_COOKIE": cookie})
                self.assertEqual(administrativo[0], 200, administrativo[2])
                self.assertEqual(administrativo[1]["Cache-Control"], "no-store")
                if acao == "remover":
                    for status in (None, "nao_verificado", "verificado", "desabilitado"):
                        lista = self._doc(self._req("GET", "/api/v1/gestao/pendentes",
                            query=("status=" + status) if status else "",
                            headers={"HTTP_COOKIE": cookie}))
                        self.assertNotIn("P-%d" % pid, [p["id"] for p in lista["pendentes"]])
                    self.assertTrue(self._doc(administrativo)["radar"]["governanca"]["removido_em"])

    def test_contribuidor_nao_remove(self):
        self._admin()
        pid = self._colab()
        token = self._token_cookie("contribuidor")
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/radar/%d/remover" % pid,
            {"motivo": "x"}, headers={"HTTP_X_API_TOKEN": token})
        self.assertEqual(status, 403, corpo)
        self.assertEqual(self._doc((status, _h, corpo))["erro"]["codigo"],
                         "permissao_negada")

    def test_pendentes_lista_colaborativo(self):
        self._admin()
        cookie = self._sessao()
        self._colab()
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertGreaterEqual(doc["resultado"]["total"], 1)

    def test_consulta_publica_preserva_oficial_ate_revisao(self):
        self._admin()
        cookie = self._sessao()
        # oficial + dois colaborativos (um correspondente, outro removido)
        self._oficial(-23.5500, -46.6300, "OFICIAL-1")
        pid = self._colab(-23.5500, -46.6300)
        removido = self._colab(-23.9, -46.9, ip="198.51.100.7")
        self._req("POST", "/api/v1/gestao/radar/%d/remover" % removido,
                  {"motivo": "duplicado"},
                  headers={"HTTP_COOKIE": cookie})
        # Proximidade nao substitui o cadastro oficial. O removido fica oculto.
        status, _h, corpo = self._req(
            "GET", "/api/v1/radares",
            query="lat=-23.5500&lon=-46.6300&raio=500")
        self.assertEqual(status, 200, corpo)
        doc = self._doc((status, _h, corpo))
        ids = [p["id"] for p in doc["resultado"]["pontos"]]
        self.assertEqual(ids, ["P-1", "P-%d" % pid])
        # a coordenada removida nao aparece
        status, _h, corpo = self._req(
            "GET", "/api/v1/radares",
            query="lat=-23.9&lon=-46.9&raio=500")
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["resultado"]["pontos"], [])


# ---------------------------------------------------------------------------
class TestTokens(BaseGov):

    def test_token_emitido_aparece_uma_vez_e_depois_so_prefixo(self):
        self._admin()
        cookie = self._sessao()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/tokens",
            {"nome": "github:fulano", "escopo": "moderador"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 201, corpo)
        doc = self._doc((status, _h, corpo))
        valor = doc["token"]
        self.assertTrue(valor.startswith("rb_"))
        self.assertEqual(doc["prefixo"], valor[:10])
        # listagem NAO traz o valor, so o prefixo
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/tokens",
            headers={"HTTP_COOKIE": cookie})
        lista = self._doc((status, _h, corpo))["tokens"]
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["prefixo"], valor[:10])
        self.assertNotIn("token", lista[0])
        self.assertNotIn("valor_hash", lista[0])
        # a tabela guarda apenas o hash
        con = dbmod.connect(config.DB_PATH)
        try:
            armazenado = con.execute(
                "SELECT valor_hash FROM API_TOKEN").fetchone()[0]
            self.assertNotEqual(armazenado, valor)
            self.assertEqual(armazenado, gov.hash_token(valor))
        finally:
            con.close()

    def test_token_revogado_nao_autentica(self):
        self._admin()
        cookie = self._sessao()
        token = self._token_cookie("moderador")
        # autentica
        status, _h, _c = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_X_API_TOKEN": token})
        self.assertEqual(status, 200)
        # revoga
        con = dbmod.connect(config.DB_PATH)
        try:
            tid = dbmod.scalar(con, "SELECT id FROM API_TOKEN")
        finally:
            con.close()
        status, _h, _c = self._req(
            "POST", "/api/v1/gestao/tokens/%d/revogar" % tid,
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200)
        # agora falha
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_X_API_TOKEN": token})
        self.assertEqual(status, 401)
        self.assertEqual(self._doc((status, _h, corpo))["erro"]["codigo"],
                         "token_invalido")

    def test_token_invalido_401(self):
        self._admin()
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/pendentes",
            headers={"HTTP_X_API_TOKEN": "rb_nao_existe"})
        self.assertEqual(status, 401)


# ---------------------------------------------------------------------------
class TestUsuariosSenha(BaseGov):

    def test_senha_em_claro_nao_aparece_na_tabela(self):
        segredo = "Sup3r-Segredo-4017"
        con = dbmod.connect(config.DB_PATH)
        try:
            gov.criar_usuario(con, "chefe", segredo, papel="admin")
            row = con.execute("SELECT * FROM USUARIO").fetchone()
            for valor in tuple(row):
                self.assertNotIn(segredo, str(valor))
            self.assertNotEqual(row["senha_hash"], segredo)
        finally:
            con.close()

    def test_admin_reseta_senha_e_gera_temporaria(self):
        self._admin()
        cookie = self._sessao()
        con = dbmod.connect(config.DB_PATH)
        try:
            uid = dbmod.scalar(con, "SELECT id FROM USUARIO WHERE login='admin'")
        finally:
            con.close()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/usuarios/%d/senha" % uid, {},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        doc = self._doc((status, _h, corpo))
        temp = doc["senha_temporaria"]
        self.assertTrue(temp)
        # senha antiga nao vale mais; temporaria vale
        status, _h, _c = self._req(
            "POST", "/api/v1/login", {"login": "admin",
                                      "senha": "SenhaForte123"})
        self.assertEqual(status, 401)
        status, _h, _c = self._req(
            "POST", "/api/v1/login", {"login": "admin", "senha": temp})
        self.assertEqual(status, 200)

    def test_minha_senha_exige_atual(self):
        self._admin()
        cookie = self._sessao()
        status, _h, corpo = self._req(
            "POST", "/api/v1/minha-senha",
            {"senha_atual": "errada", "senha_nova": "NovaSenha123"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 401, corpo)
        status, _h, corpo = self._req(
            "POST", "/api/v1/minha-senha",
            {"senha_atual": "SenhaForte123", "senha_nova": "NovaSenha123"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        status, _h, _c = self._req(
            "POST", "/api/v1/login", {"login": "admin",
                                      "senha": "NovaSenha123"})
        self.assertEqual(status, 200)

    def test_criar_usuario_por_api_devolve_temporaria(self):
        self._admin()
        cookie = self._sessao()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/usuarios",
            {"login": "mod1", "papel": "moderador"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 201, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertIn("senha_temporaria", doc["usuario"])


# ---------------------------------------------------------------------------
class TestPainelAPI(BaseGov):
    """Rotas de apoio ao painel HTML: contexto da sessao e resolucao do
    vinculo de correspondencia."""

    def _colab(self, lat=-23.55, lon=-46.63, ip="203.0.113.9"):
        self._req("POST", "/api/v1/radares/submeter",
                  {"latitude": lat, "longitude": lon},
                  headers={"HTTP_X_FORWARDED_FOR": ip})
        return self._novo_id()

    def test_eu_sem_credencial_401(self):
        status, _h, corpo = self._req("GET", "/api/v1/gestao/eu")
        self.assertEqual(status, 401, corpo)

    def test_eu_com_sessao_devolve_escopo(self):
        self._admin()
        cookie = self._sessao()
        status, _h, corpo = self._req("GET", "/api/v1/gestao/eu",
                                      headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertTrue(doc["autenticado"])
        self.assertEqual(doc["escopo"], "admin")
        self.assertEqual(doc["rotulo"], "admin")
        self.assertEqual(doc["tipo"], "usuario")

    def test_eu_com_token_devolve_escopo_do_token(self):
        token = self._token_cookie("moderador")
        status, _h, corpo = self._req("GET", "/api/v1/gestao/eu",
                                      headers={"HTTP_X_API_TOKEN": token})
        self.assertEqual(status, 200, corpo)
        doc = self._doc((status, _h, corpo))
        self.assertEqual(doc["escopo"], "moderador")
        self.assertEqual(doc["tipo"], "token")

    def test_correspondencia_colaborativo_vence(self):
        self._admin()
        cookie = self._sessao()
        self._oficial(-23.5500, -46.6300, "OFICIAL-1")
        pid = self._colab(-23.5501, -46.6301)   # corrobora automatico
        con = dbmod.connect(config.DB_PATH)
        try:
            cid = dbmod.scalar(con, "SELECT id FROM CORRESPONDENCIA_PONTO")
        finally:
            con.close()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/correspondencias/%d" % cid,
            {"status": "colaborativo_vence", "motivo": "o ponto correto"},
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)
        con = dbmod.connect(config.DB_PATH)
        try:
            self.assertEqual(dbmod.scalar(
                con, "SELECT status FROM CORRESPONDENCIA_PONTO WHERE id=?",
                (cid,)), "colaborativo_vence")
        finally:
            con.close()
        # o colaborativo continua vivo
        status, _h, corpo = self._req(
            "GET", "/api/v1/gestao/radar/%d" % pid,
            headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 200, corpo)

    def test_correspondencia_status_invalido_422(self):
        self._admin()
        cookie = self._sessao()
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/correspondencias/999",
            {"status": "qualquer"}, headers={"HTTP_COOKIE": cookie})
        self.assertEqual(status, 422, corpo)

    def test_correspondencia_exige_moderador(self):
        self._admin()
        token = self._token_cookie("contribuidor")
        status, _h, corpo = self._req(
            "POST", "/api/v1/gestao/correspondencias/1",
            {"status": "oficial_vence"},
            headers={"HTTP_X_API_TOKEN": token})
        self.assertEqual(status, 403, corpo)


# ---------------------------------------------------------------------------
class TestAjuda(BaseGov):

    def test_ajuda_lista_rotas_de_governanca(self):
        status, _h, corpo = self._req("GET", "/api/v1/ajuda",
                                      query="formato=json")
        self.assertEqual(status, 200)
        doc = self._doc((status, _h, corpo))
        self.assertIn("/api/v1/radares/submeter", doc["endpoints"])
        self.assertIn("/api/v1/login", doc["endpoints"])
        self.assertIn("/api/v1/gestao/pendentes",
                      doc["endpoints_administrativos"])
        self.assertIn("/api/v1/gestao/eu",
                      doc["endpoints_administrativos"])
        self.assertIn("/api/v1/gestao/correspondencias/{id}",
                      doc["endpoints_administrativos"])

    def test_ajuda_texto_mostra_governanca(self):
        status, _h, corpo = self._req("GET", "/api/v1/ajuda", query="formato=txt")
        self.assertEqual(status, 200)
        self.assertIn("GOVERNANCA DA INGESTAO", corpo)
        self.assertIn("/api/v1/gestao/tokens", corpo)


if __name__ == "__main__":
    unittest.main()
