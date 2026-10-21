#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica api.pse e o acesso unico a conexoes em core/db.py.

Inclui ferramentas, console, deploy e arquivos novos no checkout. Operacoes
de manutencao sao servicos internos; tools/ contem apenas clientes da API.
"""
import ast
import re
import sys

from comum import RAIZ, terminar

PASTAS = ("core", "coletor", "web", "tools", "deploy")
ENTRADAS = {"web/api.pse", "deploy/api.pse"}


def verificar_arquivo(rel, texto):
    problemas = []
    if rel.endswith(".html"):
        if re.search(r"\bsqlite3\b|\bsqlite3?\.connect\s*\(", texto):
            problemas.append(f"{rel}: a tela deve usar api.pse, sem acesso direto ao banco")
        return problemas
    if rel.endswith(".sh"):
        if re.search(r"coletor/(?:tick|sync)\.py|(?:^|\s)sqlite3\s", texto):
            problemas.append(f"{rel}: deploy deve executar api.pse")
        return problemas
    try:
        arvore = ast.parse(texto, filename=rel)
    except SyntaxError as exc:
        return [f"{rel}: sintaxe invalida: {exc}"]
    sqlite, conectar, clientes = {"sqlite3"}, set(), set()
    e_cliente = rel.startswith("tools/") or rel == "web/terminal.py"
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    sqlite.add(alias.asname or alias.name)
                if e_cliente and alias.name.split(".")[0] in ("core", "coletor", "sqlite3"):
                    problemas.append(f"{rel}: cliente nao pode importar camada de dados ({alias.name})")
        if isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                conectar.update(alias.asname or alias.name for alias in node.names
                                if alias.name in ("connect", "Connection"))
            if node.module == "core.cliente_api":
                clientes.update(alias.asname or alias.name for alias in node.names if alias.name == "executar")
            elif e_cliente and (node.module or "").split(".")[0] in ("core", "coletor", "sqlite3"):
                problemas.append(f"{rel}: cliente nao pode importar servico interno ({node.module})")
    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        fisica = (isinstance(fn, ast.Name) and fn.id in conectar) or (
            isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
            and fn.value.id in sqlite and fn.attr in ("connect", "Connection"))
        if fisica and rel != "core/db.py":
            problemas.append(f"{rel}:{node.lineno}: conexao fisica permitida somente em core/db.py")
        if e_cliente and isinstance(fn, ast.Attribute) and fn.attr in ("execute", "executemany", "executescript"):
            problemas.append(f"{rel}:{node.lineno}: cliente nao pode executar SQL")
    if e_cliente and not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id in clientes for node in ast.walk(arvore)):
        problemas.append(f"{rel}: comando deve encaminhar a core.cliente_api.executar")
    if rel.startswith("core/manutencao/") or rel in ("core/console_api.py", "core/configuracao.py", "core/instalacao.py", "coletor/tick.py", "coletor/sync.py"):
        for node in arvore.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("main", "_main_servico"):
                if rel.startswith("coletor/") and node.name == "main":
                    continue  # cliente de compatibilidade
                if not any(isinstance(d, ast.Name) and d.id == "operacao_local" for d in node.decorator_list):
                    problemas.append(f"{rel}: servico local precisa do contexto de api.pse")
    if rel in ENTRADAS and not any(isinstance(n, ast.ImportFrom) and n.module == "core.entrada_api"
                                   for n in ast.walk(arvore)):
        problemas.append(f"{rel}: entrada deve usar o despachante comum core.entrada_api")
    return problemas


def arquivos(raiz):
    # Examina o checkout atual, inclusive implementacoes novas ainda nao adicionadas ao Git.
    for pasta in PASTAS:
        for path in sorted((raiz / pasta).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".pse", ".html", ".sh"):
                yield path


def main():
    problemas = []
    for path in arquivos(RAIZ):
        problemas.extend(verificar_arquivo(path.relative_to(RAIZ).as_posix(), path.read_text(encoding="utf-8")))
    return terminar(problemas, "Entradas e clientes passam por api.pse; conexoes fisicas somente em core/db.py.")


if __name__ == "__main__":
    sys.exit(main())
