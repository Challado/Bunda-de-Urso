"""Reproduz erros publicados pelo servidor em 24/10/2026 sem tocar a producao."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coletor import tick
from coletor.fontes.boavista_rr import ColetorBoaVistaRR
from coletor.fontes.natal_rn import ColetorNatalRN
from coletor.fontes.prf import ColetorPRFFixos
from core import config, db, painel_status
from core.manutencao.reprocessar_fontes_corrigidas import reprocessar

FIX = Path(__file__).parent/'fixtures'


class CorrecaoFontesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='radar-fontes-status-')
        self.addCleanup(self.tmp.cleanup)
        pasta=self.tmp.name
        self.cfg=patch.multiple(config,DATA_DIR=pasta,RAW_DIR=pasta+'/raw',STAGING_DIR=pasta+'/staging',DB_PATH=pasta+'/radar.sqlite3')
        self.cfg.start();self.addCleanup(self.cfg.stop)
        self.con=db.connect();self.addCleanup(self.con.close)
        self.sem_rede=patch('coletor.http.baixar',side_effect=AssertionError('Reprocessamento nao pode baixar fontes'))
        self.sem_rede.start();self.addCleanup(self.sem_rede.stop)

    def test_documental_valido_nao_e_rejeicao_nem_publicacao_de_radar(self):
        for cls,arquivo in [(ColetorBoaVistaRR,FIX/'boavista_rr/noticia_fixture.html'),(ColetorNatalRN,FIX/'natal_rn/pagina_fixture.html')]:
            coletor=cls(conn=self.con)
            r=coletor.sincronizar(str(arquivo))
            self.assertEqual(r['status'],'documentado')
            self.assertEqual(r['rejeitados'],0)
            self.assertEqual(r['evidencias_documentais'],1)
            self.assertIsNone(r['snapshot_id'])
            novamente=coletor.sincronizar(str(arquivo))
            self.assertTrue(novamente['sem_mudanca'])
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),0)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM SNAPSHOT_PUBLICADO'),0)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM ERRO_VALIDACAO'),0)
        self.assertEqual(tick.espera_s(604800,[{'status':'documentado'}]),604800)
        for c in painel_status.coletores(self.con)['coletores']:
            if c['conector'] in ('boavista_rr','natal_rn'):
                self.assertEqual(c['tipo_coleta'],'documental')
                self.assertIsNotNone(c['ultimo_sucesso'])
                self.assertEqual(c['ultima_tentativa']['linhas_validas'],1)

    def test_erro_http_200_ou_layout_vazio_continua_sendo_erro_real(self):
        for texto in ['<html><title>Página não encontrada</title><body>STTU Natal</body></html>',
                      '<html><title>Access denied</title><body>Boa Vista radar</body></html>',
                      '<html><title>Outro portal</title><body>Alterado</body></html>']:
            p=Path(self.tmp.name)/'erro.html';p.write_text(texto)
            with self.assertRaises(ValueError):ColetorNatalRN(conn=self.con).sincronizar(str(p))
        self.assertEqual(db.scalar(self.con,"SELECT COUNT(*) FROM EXECUCAO_COLETA WHERE status='erro'"),3)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),0)

    def test_recupera_documento_legado_rejeitado_sem_apagar_historico(self):
        c=ColetorNatalRN(conn=self.con);p=str(FIX/'natal_rn/pagina_fixture.html')
        with patch.object(c,'MODO_COLETA','cadastro'):
            antigo=c.sincronizar(p)
        self.assertEqual(antigo['status'],'erro')
        # Historico legado declarava ok mesmo sem aproveitar registros.
        self.con.execute("UPDATE EXECUCAO_COLETA SET status='ok' WHERE id=?",(antigo['execucao_id'],));self.con.commit()
        novo=reprocessar(self.con)
        self.assertEqual(next(r['estado'] for r in novo if r['fonte']=='natal_rn'),'documentado')
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM REGISTRO_FONTE'),1)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM ERRO_VALIDACAO'),1)
        self.assertEqual(reprocessar(self.con)[0]['estado'],'ja_corrigido')

    def test_prf_aceita_16_registros_reais_sem_gps_ou_identificador(self):
        p=str(FIX/'novos/prf_fixos_sem_identificador.json')
        c=ColetorPRFFixos(conn=self.con)
        r=c.sincronizar(p)
        self.assertEqual((r['criados'],r['rejeitados']),(16,0))
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM POSICAO_GEOGRAFICA'),0)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO p LEFT JOIN SITUACAO_OPERACIONAL s ON s.id=p.situacao_operacional_id WHERE s.codigo=\'inativo\''),16)
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM EQUIPAMENTO WHERE numero_serie IS NOT NULL'),0)
        self.assertTrue(c.sincronizar(p)['sem_mudanca'])

    def test_prf_reaproveita_mesmo_arquivo_com_rejeicoes_antigas(self):
        p=Path(self.tmp.name)/'prf.json'
        todos=ColetorPRFFixos._parse_json((FIX/'novos/prf_fixos.json').read_bytes())[:1]
        todos+=ColetorPRFFixos._parse_json((FIX/'novos/prf_fixos_sem_identificador.json').read_bytes())
        p.write_text(json.dumps(todos))
        c=ColetorPRFFixos(conn=self.con)
        with patch.object(c,'identificador',side_effect=lambda raw: raw.get('IDENTIFICADOR')):
            velho=c.sincronizar(str(p))
        self.assertEqual(velho['rejeitados'],16)
        ids_antes=[r[0] for r in self.con.execute('SELECT id FROM PONTO_FISCALIZACAO')]
        r=reprocessar(self.con)
        resumo=next(x['resumo'] for x in r if x['fonte']=='prf_fixos')
        self.assertEqual((resumo['criados'],resumo['rejeitados']),(16,0))
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM PONTO_FISCALIZACAO'),17)
        for pid in ids_antes:self.assertIsNotNone(db.scalar(self.con,'SELECT id FROM PONTO_FISCALIZACAO WHERE id=?',(pid,)))
        self.assertEqual(db.scalar(self.con,'SELECT COUNT(*) FROM ERRO_VALIDACAO'),16)
        self.assertEqual(reprocessar(self.con)[0]['estado'],'ja_corrigido')

    def test_operacao_recusa_banco_ausente_sem_criar_arquivo(self):
        from core.contexto_api import atendimento_local
        from core.manutencao.reprocessar_fontes_corrigidas import main
        ausente=Path(self.tmp.name)/'ausente.sqlite3'
        with patch.object(config,'DB_PATH',str(ausente)), atendimento_local():
            with self.assertRaises(FileNotFoundError):main([])
        self.assertFalse(ausente.exists())

    def test_cache_alterado_nao_e_aceito_como_original(self):
        c=ColetorBoaVistaRR(conn=self.con)
        with patch.object(c,'MODO_COLETA','cadastro'):
            velho=c.sincronizar(str(FIX/'boavista_rr/noticia_fixture.html'))
        p=Path(db.scalar(self.con,'SELECT caminho_cache FROM ARTEFATO_COLETA WHERE id=?',(velho['artefato_id'],)))
        p.write_text('cache alterado')
        r=reprocessar(self.con)
        self.assertEqual(r[0]['estado'],'erro')
        self.assertIn('Hash',r[0]['motivo'])
        p.unlink()
        self.assertEqual(reprocessar(self.con)[0]['estado'],'pendente')
