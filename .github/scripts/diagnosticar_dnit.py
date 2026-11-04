#!/usr/bin/env python3
"""Coleta real do DNIT por HTTP, sem navegador, login ou banco de producao."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', default='test-results/dnit-ao-vivo')
    args = parser.parse_args()
    pasta = Path(args.saida).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    conf = pasta / 'radar.conf'
    conf.write_text('[dados]\ndir = ' + str(pasta) + '\n', encoding='utf-8')
    os.environ['RADAR_CONF'] = str(conf)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from coletor.fontes.dnit import ColetorDNITEquipamentos
    from core import atualizacoes

    relatorio = {
        'url': ColetorDNITEquipamentos.URL_API,
        'iniciado_em': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'transporte': 'HTTP', 'navegador': False, 'sucesso': False,
    }
    try:
        coletor = ColetorDNITEquipamentos()
        corpo, ext, mime, registros = coletor.carregar(coletor.resolver_url())
        for i, registro in enumerate(registros):
            coletor.normalizar(i, registro)
        arquivo = pasta / ('equipamentos' + ext)
        arquivo.write_bytes(corpo)
        relatorio.update(sucesso=True, registros=len(registros), bytes=len(corpo),
                         sha256=hashlib.sha256(corpo).hexdigest(),
                         formato=mime, arquivo=arquivo.name)
    except Exception as exc:
        relatorio.update(erro_tipo=type(exc).__name__, erro=atualizacoes.limpar(str(exc)))
    relatorio['terminado_em'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2)
    (pasta / 'coletor.json').write_text(texto + '\n', encoding='utf-8')
    print(texto)
    return 0 if relatorio['sucesso'] else 1


if __name__ == '__main__':
    sys.exit(main())
