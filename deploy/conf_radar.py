#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostico e instalacao do /etc/radar-brasil/radar.conf.

Nao e cliente da API e nao abre banco: so le a configuracao e o sistema de
arquivos. Serve para responder "onde este programa acha que estao as coisas?"

    python3 deploy/conf_radar.py                 # mostra os caminhos efetivos
    python3 deploy/conf_radar.py --verificar     # confere se existem/usam
    python3 deploy/conf_radar.py --instalar      # cria o .conf a partir do exemplo
    python3 deploy/conf_radar.py --exemplo       # imprime o exemplo na tela

--instalar NUNCA sobrescreve: se o arquivo existe, grava ao lado como
``radar.conf.novo`` para revisao. Configuracao nao se troca por acidente.
"""
import argparse
import os
import pwd
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from core import caminhos  # noqa: E402

EXEMPLO = os.path.join(RAIZ, "deploy", "radar.conf.exemplo")


def mostrar():
    print("Arquivo de configuracao: %s%s" % (
        caminhos.conf_path(),
        "" if caminhos.existe_conf() else "  (AUSENTE — usando padroes do checkout)"))
    print()
    largura = max(len("%s.%s" % (i["secao"], i["chave"])) for i in caminhos.resumo())
    for item in caminhos.resumo():
        nome = "%s.%s" % (item["secao"], item["chave"])
        print("  %-*s  %-46s  [%s]" % (largura, nome, item["valor"] or "-", item["origem"]))
    problemas = caminhos.problemas()
    if problemas:
        print()
        print("Problemas no arquivo:")
        for p in problemas:
            print("  - %s" % p)
    return 0


def _checar_caminho(problemas, rotulo, caminho, tipo="dir", escrita=False):
    if not caminho:
        problemas.append("%s: nao configurado" % rotulo)
        return
    if tipo == "dir" and not os.path.isdir(caminho):
        problemas.append("%s: diretorio nao existe (%s)" % (rotulo, caminho))
        return
    if tipo == "arq" and not os.path.isfile(caminho):
        problemas.append("%s: arquivo nao existe (%s)" % (rotulo, caminho))
        return
    if escrita and not os.access(caminho, os.W_OK):
        problemas.append("%s: sem permissao de escrita (%s)" % (rotulo, caminho))


def verificar():
    problemas = list(caminhos.problemas())
    if not caminhos.existe_conf():
        problemas.append("arquivo %s nao existe (o programa usa os padroes do checkout)"
                         % caminhos.conf_path())

    _checar_caminho(problemas, "instalacao.home", caminhos.home())
    if not os.path.isdir(os.path.join(caminhos.home(), "core")):
        problemas.append("instalacao.home nao tem core/ (%s)" % caminhos.home())
    _checar_caminho(problemas, "dados.dir", caminhos.data_dir(), escrita=True)
    _checar_caminho(problemas, "dados.banco", caminhos.banco(), tipo="arq")
    _checar_caminho(problemas, "web.raiz", caminhos.web_raiz())
    _checar_caminho(problemas, "web.raiz/api.pse",
                    os.path.join(caminhos.web_raiz(), "api.pse"), tipo="arq")
    _checar_caminho(problemas, "logs.dir", caminhos.log_dir(), escrita=True)

    clone = caminhos.sync_clone()
    if clone and not os.path.isdir(clone):
        problemas.append("sincronizacao.clone nao existe (%s)" % clone)

    _, origem = caminhos.valor("instalacao", "usuario")
    esperado = caminhos.valor("instalacao", "usuario")[0]
    if esperado:
        try:
            alvo = pwd.getpwnam(esperado).pw_uid
            dono = os.stat(caminhos.home()).st_uid
            if dono != alvo:
                problemas.append("instalacao.home pertence a uid %d, configuracao espera %s (uid %d)"
                                 % (dono, esperado, alvo))
        except KeyError:
            problemas.append("instalacao.usuario: usuario %s nao existe" % esperado)

    if not problemas:
        print("Configuracao coerente. Nada a corrigir.")
        return 0

    print("%d problema(s):" % len(problemas))
    for p in problemas:
        print("  - %s" % p)
    print()
    print("Corrija em %s e rode de novo com --verificar." % caminhos.conf_path())
    return 1


def instalar():
    destino = caminhos.conf_path()
    if not os.path.isfile(EXEMPLO):
        print("exemplo ausente: %s" % EXEMPLO, file=sys.stderr)
        return 1
    if os.path.exists(destino):
        novo = destino + ".novo"
        shutil.copyfile(EXEMPLO, novo)
        print("Ja existe %s — nada foi sobrescrito." % destino)
        print("Exemplo gravado em %s para comparacao (revise e renomeie se quiser)." % novo)
        return 0
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copyfile(EXEMPLO, destino)
    os.chmod(destino, 0o644)
    print("Criado %s a partir do exemplo." % destino)
    print("Revise os caminhos e rode: python3 deploy/conf_radar.py --verificar")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Configuracao de caminhos do Radar Brasil")
    ap.add_argument("--mostrar", action="store_true", help="mostra os caminhos efetivos (padrao)")
    ap.add_argument("--verificar", action="store_true", help="confere arquivos, permissoes e dono")
    ap.add_argument("--instalar", action="store_true", help="cria o .conf a partir do exemplo")
    ap.add_argument("--exemplo", action="store_true", help="imprime o exemplo na tela")
    args = ap.parse_args(argv)

    if args.exemplo:
        with open(EXEMPLO, "r", encoding="utf-8") as f:
            sys.stdout.write(f.read())
        return 0
    if args.instalar:
        return instalar()
    if args.verificar:
        return verificar()
    return mostrar()


if __name__ == "__main__":
    raise SystemExit(main())
