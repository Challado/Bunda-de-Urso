"""Dados opcionais enriquecem a consulta sem eliminar a entidade principal."""
from contextlib import closing, contextmanager
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from core import assistencia, config, consultas, db, dedup, governanca
from tests import test_dedup as apoio
from web import nucleo


class TestComplementos(apoio.BaseDedup):
    def setUp(self):
        super().setUp()
        governanca.garantir_esquema(self.con)
        self.p = self.ponto(self.posicao(-25, -54))
        self.e = self.equipamento("LEFT-1234")
        db.insert(self.con, "INSTALACAO", {"ponto_id": self.p, "equipamento_id": self.e})
        self.f = self.fonte("Fonte de teste")
        self.recurso_id = self.recurso(self.f)
        self.r = self.registro(self.artefato(self.recurso_id), {"latitude": -25, "longitude": -54,
            "contato": "privado@example.invalid", "segredo": "nao-expor"})
        self.ligar_ponto(self.r, self.p)
        self.ligar_equip(self.r, self.e)
        self.con.commit()

    @contextmanager
    def legado_incompleto(self):
        # Somente na fixture: simula uma importacao antiga sem FKs validadas.
        self.con.commit()
        self.con.execute("PRAGMA foreign_keys=OFF")
        try:
            yield
            self.con.commit()
        finally:
            self.con.execute("PRAGMA foreign_keys=ON")

    def documento(self, tipo="relatorio", **campos):
        return db.insert(self.con, "DOCUMENTO", {
            "tipo_documento_id": db.domain_id(self.con, "TIPO_DOCUMENTO", tipo), **campos})

    def identificador(self, tabela, coluna, entidade, valor):
        ex = db.insert(self.con, "IDENTIFICADOR_EXTERNO", {"fonte_id": self.f,
            "tipo_identificador_id": db.domain_id(self.con, "TIPO_IDENTIFICADOR", "id_orgao"),
            "valor": valor, "valor_normalizado": valor})
        db.insert(self.con, tabela, {coluna: entidade, "identificador_id": ex,
            "vigencia_inicio": "2026-01-01"})
        return ex

    def verificacao(self, equipamento=None, registro=None, **campos):
        return db.insert(self.con, "VERIFICACAO_METROLOGICA", {
            "equipamento_id": equipamento or self.e, "registro_fonte_id": registro or self.r,
            "tipo_verificacao_id": db.domain_id(self.con, "TIPO_VERIFICACAO", "periodica"),
            "resultado_id": db.domain_id(self.con, "RESULTADO_VERIFICACAO", "conforme"), **campos})

    def detalhe(self):
        return consultas.buscar_ponto_por_id(self.con, self.p)

    def operacao(self):
        return db.insert(self.con, "OPERACAO_FISCALIZACAO", {
            "modalidade_id": db.domain_id(self.con, "MODALIDADE_FISCALIZACAO", "pontual"),
            "situacao_operacao_id": db.domain_id(self.con, "SITUACAO_OPERACAO", "desconhecida")})

    def segunda_observacao(self):
        fonte = self.fonte("Segunda fonte")
        rid = self.registro(self.artefato(self.recurso(fonte)), {
            "numero_serie": "LEFT-1234", "latitude": -25, "longitude": -54})
        ponto = self.ponto(self.posicao(-25, -54, registro_id=rid))
        equipamento = self.equipamento("LEFT-1234")
        self.ligar_ponto(rid, ponto)
        self.ligar_equip(rid, equipamento)
        db.insert(self.con, "INSTALACAO", {"ponto_id": ponto, "equipamento_id": equipamento})
        return ponto, equipamento, rid

    def unificar(self, escopo):
        self.con.commit()
        dedup.gerar_candidatos(self.con)
        cid = db.scalar(self.con, "SELECT id FROM CANDIDATO_DUPLICIDADE")
        dedup.decidir(self.con, cid, "unificar", "revisor", "Mesma entidade nos documentos", escopo=escopo)
        dedup.aplicar(self.con, cid, "revisor")

    def test_ponto_e_equipamento_sem_complementos_continuam_visiveis(self):
        p = self.detalhe()
        self.assertEqual(p["localizacao"]["endereco"], {})
        self.assertEqual(p["equipamentos"][0]["documentos"], [])
        self.assertEqual(p["identificadores_oficiais"], [])
        self.assertEqual(consultas.buscar_pontos(self.con, -25, -54, 100)[1]["total_pontos"], 1)
        self.assertEqual(consultas.buscar_cadastral(self.con)[1]["total_pontos"], 1)

    def test_endereco_relacionado_aparece_sem_precisar_de_documentos(self):
        eid = db.insert(self.con, "ENDERECO", {"logradouro": "Avenida de teste", "numero": "42",
            "bairro": "Centro", "cep": "74000000", "ponto_referencia": "Ao lado da praça"})
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET endereco_id=? WHERE id=?", (eid, self.p))
        p = self.detalhe()
        self.assertEqual(p["localizacao"]["endereco"]["logradouro"], "Avenida de teste")
        self.assertEqual(p["localizacao"]["endereco"]["numero"], "42")
        self.assertEqual(p["localizacao"]["latitude"], -25)
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET posicao_id=NULL WHERE id=?", (self.p,))
        self.assertEqual(self.detalhe()["localizacao"]["endereco"]["cep"], "74000000")

    def test_documentos_nas_cinco_relacoes_com_emissor_e_hash(self):
        org = db.scalar(self.con, "SELECT organizacao_id FROM FONTE WHERE id=?", (self.f,))
        documento = self.documento(titulo="Relatório", url="https://example.invalid/doc.pdf",
                                   orgao_emissor_id=org, hash_conteudo="a" * 64)
        v = self.verificacao()
        op = self.operacao()
        trecho = db.insert(self.con, "TRECHO_ELEGIVEL", {
            "via_id": self.via("BR-277"), "km_inicio": 10, "km_fim": 20})
        for tipo, entidade in (("ponto", self.p), ("equipamento", self.e), ("verificacao", v),
                               ("operacao", op), ("trecho", trecho)):
            tabela, coluna = consultas._VINCULOS_DOCUMENTO[tipo]
            db.insert(self.con, tabela, {coluna: entidade, "documento_id": documento})
        p = self.detalhe()
        listas = [p["documentos"], p["equipamentos"][0]["documentos"],
                  p["equipamentos"][0]["verificacoes_metrologicas"][0]["documentos"],
                  consultas.buscar_operacoes(self.con)[0][0]["documentos"],
                  consultas.buscar_trechos(self.con)[0][0]["documentos"]]
        for lista in listas:
            self.assertEqual(len(lista), 1)
            self.assertEqual(lista[0]["orgao_emissor"], "Org Fonte de teste")
            self.assertEqual(lista[0]["hash_conteudo"], "a" * 64)

    def test_certificado_somente_quando_url_e_inequivoca(self):
        v = self.verificacao(numero_certificado="CERT-1")
        doc = self.documento("certificado", codigo_documento="CERT-1", url="https://example.invalid/a.pdf")
        db.insert(self.con, "DOCUMENTO_VERIFICACAO", {"verificacao_id": v, "documento_id": doc})
        self.assertEqual(self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"][0]["certificado_url"],
                         "https://example.invalid/a.pdf")
        doc2 = self.documento("certificado", codigo_documento="CERT-1", url="https://example.invalid/b.pdf")
        db.insert(self.con, "DOCUMENTO_VERIFICACAO", {"verificacao_id": v, "documento_id": doc2})
        ver = self.detalhe()["equipamentos"][0]["verificacoes_metrologicas"][0]
        self.assertIsNone(ver["certificado_url"])
        self.assertEqual(len(ver["documentos"]), 2)

    def test_primeiro_documento_sem_url_nao_esconde_url_disponivel(self):
        op = self.operacao()
        for url in (None, "https://example.invalid/publicacao.pdf"):
            db.insert(self.con, "DOCUMENTO_OPERACAO", {"operacao_id": op,
                "documento_id": self.documento(url=url)})
        resultado = consultas.buscar_operacoes(self.con)[0][0]
        self.assertEqual(resultado["documento_url"], "https://example.invalid/publicacao.pdf")
        self.assertEqual(len(resultado["documentos"]), 2)

    def test_identificadores_de_ponto_equipamento_e_operacao(self):
        op = self.operacao()
        self.identificador("IDENTIFICADOR_PONTO", "ponto_id", self.p, "LOCAL-1")
        self.identificador("IDENTIFICADOR_EQUIPAMENTO", "equipamento_id", self.e, "APARELHO-1")
        self.identificador("IDENTIFICADOR_OPERACAO", "operacao_id", op, "OPERACAO-1")
        p = self.detalhe()
        for lista, valor in ((p["identificadores_oficiais"], "LOCAL-1"),
                              (p["equipamentos"][0]["identificadores_oficiais"], "APARELHO-1"),
                              (consultas.buscar_operacoes(self.con)[0][0]["identificadores_oficiais"], "OPERACAO-1")):
            self.assertEqual(lista[0]["valor"], valor)
            self.assertEqual(lista[0]["vigencia"]["inicio"], "2026-01-01")

    def test_colecoes_nao_criam_produto_cartesiano(self):
        for i in range(2):
            doc = self.documento(titulo="Documento %d" % i)
            v = self.verificacao(numero_certificado="CERT-%d" % i)
            db.insert(self.con, "DOCUMENTO_EQUIPAMENTO", {"equipamento_id": self.e, "documento_id": doc})
            db.insert(self.con, "DOCUMENTO_VERIFICACAO", {"verificacao_id": v, "documento_id": doc})
        e = self.detalhe()["equipamentos"][0]
        self.assertEqual(len(e["instalacoes"]), 1)
        self.assertEqual(len(e["documentos"]), 2)
        self.assertEqual(len(e["verificacoes_metrologicas"]), 2)
        self.assertTrue(all(len(v["documentos"]) == 1 for v in e["verificacoes_metrologicas"]))

    def test_consolidacao_preserva_documentos_e_fontes_de_verificacoes_equivalentes(self):
        _, e2, r2 = self.segunda_observacao()
        executor = db.scalar(self.con, "SELECT organizacao_id FROM FONTE WHERE id=?", (self.f,))
        for equipamento, registro in ((self.e, self.r), (e2, r2)):
            ver = self.verificacao(equipamento, registro, numero_certificado="CERT-1",
                data_verificacao="2026-06-25", orgao_executor_id=executor)
            doc = self.documento(titulo="Evidência %d" % equipamento)
            db.insert(self.con, "DOCUMENTO_VERIFICACAO", {"verificacao_id": ver, "documento_id": doc})
            db.insert(self.con, "DOCUMENTO_EQUIPAMENTO", {"equipamento_id": equipamento, "documento_id": doc})
        self.unificar("equipamento")
        p = self.detalhe()
        e = p["equipamentos"][0]
        self.assertEqual(len(e["documentos"]), 2)
        self.assertEqual(len(e["verificacoes_metrologicas"]), 1)
        ver = e["verificacoes_metrologicas"][0]
        self.assertEqual(len(ver["documentos"]), 2)
        self.assertEqual({r["fonte_registro_id"] for r in ver["origens"]}, {self.r, r2})
        self.assertEqual({f["nome"] for f in p["dados_por_fonte"]}, {"Fonte de teste", "Segunda fonte"})

    def test_endereco_do_ponto_consolidado_nao_some_no_canonico_sem_endereco(self):
        p2, _, _ = self.segunda_observacao()
        endereco = db.insert(self.con, "ENDERECO", {"logradouro": "Rua preservada"})
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET endereco_id=? WHERE id=?", (endereco, p2))
        self.unificar("ponto")
        p = self.detalhe()
        self.assertEqual(p["localizacao"]["endereco"]["logradouro"], "Rua preservada")
        self.assertEqual(p["proveniencia_campos"]["endereco"]["ponto_origem_id"], "P-%d" % p2)

    def test_catalogo_ausente_na_base_legada_nao_elimina_equipamento(self):
        with self.legado_incompleto():
            self.con.execute("UPDATE EQUIPAMENTO SET tipo_radar_id=999999 WHERE id=?", (self.e,))
        e = self.detalhe()["equipamentos"][0]
        self.assertEqual(e["id"], "E-%d" % self.e)
        self.assertEqual(e["numero_serie"], "LEFT-1234")
        self.assertIsNone(e["tipo_radar"])
        self.assertIsNotNone(consultas.buscar_equipamento_por_id(self.con, self.e))
        self.assertEqual(consultas.buscar_pontos(self.con, -25, -54, 100)[1]["total_pontos"], 1)
        # A tolerancia na leitura nao conserta nem encobre a integridade.
        self.assertTrue(self.con.execute("PRAGMA foreign_key_check").fetchall())

    def test_orgao_ausente_na_base_legada_nao_esconde_fonte_e_publicacao(self):
        with self.legado_incompleto():
            self.con.execute("UPDATE FONTE SET organizacao_id=999999 WHERE id=?", (self.f,))
        p = self.detalhe()
        self.assertEqual(p["fontes"][0]["nome"], "Fonte de teste")
        self.assertEqual(p["dados_por_fonte"][0]["registros"][0]["registro_id"], self.r)
        self.assertIsNone(consultas.listar_fontes(self.con)[0]["organizacao"])

    def test_natureza_ausente_preserva_publicacao_sem_expor_dado_privado(self):
        with self.legado_incompleto():
            self.con.execute("UPDATE FONTE SET natureza_id=999999 WHERE id=?", (self.f,))
        p = self.detalhe()
        r = p["dados_por_fonte"][0]["registros"][0]
        self.assertEqual(r["registro_id"], self.r)
        self.assertEqual(r["dados_publicados"], {"latitude": -25, "longitude": -54})
        self.assertNotIn("nao-expor", json.dumps(p))

    def test_cadeia_de_fonte_incompleta_mantem_registro_sem_fabricar_metadados(self):
        with self.legado_incompleto():
            self.con.execute("UPDATE REGISTRO_FONTE SET artefato_id=999999 WHERE id=?", (self.r,))
        p = self.detalhe()
        self.assertIsNone(p["fontes"][0]["id"])
        self.assertIsNone(p["dados_por_fonte"][0]["nome"])
        self.assertEqual(p["dados_por_fonte"][0]["registros"][0]["registro_id"], self.r)

    def test_documento_sem_catalogo_ou_emissor_na_base_legada_permanece(self):
        doc = self.documento(titulo="Documento preservado")
        db.insert(self.con, "DOCUMENTO_PONTO", {"ponto_id": self.p, "documento_id": doc})
        with self.legado_incompleto():
            self.con.execute("UPDATE DOCUMENTO SET tipo_documento_id=999999, orgao_emissor_id=999999 WHERE id=?", (doc,))
        d = self.detalhe()["documentos"][0]
        self.assertEqual(d["titulo"], "Documento preservado")
        self.assertIsNone(d["tipo_documento"])
        self.assertIsNone(d["orgao_emissor"])

    def test_identificador_sem_catalogo_ou_fonte_na_base_legada_permanece(self):
        ex = self.identificador("IDENTIFICADOR_PONTO", "ponto_id", self.p, "LOCAL-1")
        with self.legado_incompleto():
            self.con.execute("UPDATE IDENTIFICADOR_EXTERNO SET tipo_identificador_id=999999, fonte_id=999999 WHERE id=?", (ex,))
        ident = self.detalhe()["identificadores_oficiais"][0]
        self.assertEqual(ident["valor"], "LOCAL-1")
        self.assertIsNone(ident["fonte"])
        self.assertIsNone(ident["tipo"])

    def test_execucao_sem_recurso_legado_continua_no_historico_e_diagnostico(self):
        ex = db.insert(self.con, "EXECUCAO_COLETA", {"recurso_id": self.recurso_id,
            "iniciada_em": "2026-10-21T10:00:00Z", "status": "erro", "tentativas": 1, "http_status": 503})
        with self.legado_incompleto():
            self.con.execute("UPDATE EXECUCAO_COLETA SET recurso_id=999999 WHERE id=?", (ex,))
        historico, meta = consultas.listar_atualizacoes(self.con)
        self.assertEqual(meta["total_atualizacoes"], 1)
        self.assertEqual(historico[0]["recurso_id"], "RF-999999")
        self.assertIsNone(historico[0]["fonte_id"])
        self.assertEqual(assistencia._diagnostico(self.con, ex)["causa"], "origem_indisponivel")

    def test_filtro_municipio_usa_referencia_conhecida_sem_exigir_nome(self):
        op = self.operacao()
        with self.legado_incompleto():
            self.con.execute("UPDATE PONTO_FISCALIZACAO SET municipio_id='5210208' WHERE id=?", (self.p,))
            self.con.execute("UPDATE OPERACAO_FISCALIZACAO SET municipio_id='5210208' WHERE id=?", (op,))
        pontos, meta = consultas.buscar_cadastral(self.con, {"municipio_ibge": "5210208"})
        self.assertEqual(meta["total_pontos"], 1)
        self.assertEqual(pontos[0]["localizacao"]["codigo_ibge"], "5210208")
        self.assertIsNone(pontos[0]["localizacao"]["municipio"])
        self.assertEqual(consultas.buscar_operacoes(self.con, filtros={"municipio_ibge": "5210208"})[1]["total_operacoes"], 1)

    def test_filtro_fonte_por_id_preserva_execucao_sem_nome_da_fonte(self):
        db.insert(self.con, "EXECUCAO_COLETA", {"recurso_id": self.recurso_id,
            "iniciada_em": "2026-10-21T10:00:00Z", "status": "ok", "tentativas": 1})
        with self.legado_incompleto():
            self.con.execute("UPDATE RECURSO_FONTE SET fonte_id=999999 WHERE id=?", (self.recurso_id,))
        historico, meta = consultas.listar_atualizacoes(self.con, {"fonte_id": 999999})
        self.assertEqual(meta["total_atualizacoes"], 1)
        self.assertEqual(historico[0]["fonte_id"], "S-999999")
        self.assertIsNone(historico[0]["fonte"])

    def test_filtro_uf_preserva_sigla_do_municipio_sem_catalogo_uf(self):
        db.insert(self.con, "MUNICIPIO", {"codigo_ibge": "5210208", "nome": "Iporá", "uf_sigla": "GO"})
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET municipio_id='5210208' WHERE id=?", (self.p,))
        with self.legado_incompleto():
            self.con.execute("DELETE FROM UF WHERE sigla='GO'")
        pontos, meta = consultas.buscar_cadastral(self.con, {"uf": "GO"})
        self.assertEqual(meta["total_pontos"], 1)
        self.assertEqual(pontos[0]["localizacao"]["uf"], "GO")

    def test_api_entrega_complementos_sem_escrita(self):
        endereco = db.insert(self.con, "ENDERECO", {"logradouro": "Rua da API"})
        self.con.execute("UPDATE PONTO_FISCALIZACAO SET endereco_id=? WHERE id=?", (endereco, self.p))
        doc = self.documento(titulo="Documento da API")
        db.insert(self.con, "DOCUMENTO_EQUIPAMENTO", {"equipamento_id": self.e, "documento_id": doc})
        with tempfile.TemporaryDirectory(prefix="radar-complementos-") as pasta:
            banco = Path(pasta) / "teste.sqlite3"
            self.con.commit()
            with closing(db.connect(banco)) as c:
                self.con.backup(c)
            with patch.object(config, "DB_PATH", str(banco)):
                status, _, corpo = nucleo.handle_request({"REQUEST_METHOD": "GET",
                    "QUERY_STRING": "rota=/api/v1/radares/P-%d" % self.p})
            self.assertEqual(status, 200)
            p = json.loads(corpo)["resultado"]["pontos"][0]
            self.assertEqual(p["localizacao"]["endereco"]["logradouro"], "Rua da API")
            self.assertEqual(p["equipamentos"][0]["documentos"][0]["titulo"], "Documento da API")
