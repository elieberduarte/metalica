# -*- coding: utf-8 -*-
"""Módulos só do desenvolvimento: o que o app.py carrega pelo `_extensoes_dev` fica fora do instalado.

Até 02/11 o gancho `_extensoes_dev` vivia só no app.py de trabalho, fora do git. Com ele no git (base limpa,
VERSÃO N.2), o PyInstaller acha os `import x.web` dentro da função e levaria o módulo para o programa instalado,
a não ser que ele esteja em MODULOS_SO_DEV (e a pasta das telas dele em TELAS_SO_DEV) do empacotar/construir.py.
A arquitetura (30/10) entrou no gancho sem entrar nas listas.
"""
import ast
import fnmatch
import os

SISTEMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTRUIR = os.path.join(os.path.dirname(SISTEMA), "empacotar", "construir.py")


def _listas_do_construir():
    arv = ast.parse(open(CONSTRUIR, encoding="utf-8").read())
    listas = {}
    for no in arv.body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
            if no.targets[0].id in ("MODULOS_SO_DEV", "TELAS_SO_DEV"):
                listas[no.targets[0].id] = ast.literal_eval(no.value)
    return listas["MODULOS_SO_DEV"], listas["TELAS_SO_DEV"]


def _modulos_do_gancho():
    arv = ast.parse(open(os.path.join(SISTEMA, "app.py"), encoding="utf-8").read())
    func = next(n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name == "_extensoes_dev")
    return sorted({a.name for n in ast.walk(func) if isinstance(n, ast.Import) for a in n.names})


def test_o_gancho_carrega_os_modulos_do_dev():
    mods = _modulos_do_gancho()
    assert {"premoldado.web", "arquitetura.web", "celular.web", "painel_dev.web"} <= set(mods), mods


def test_todo_modulo_do_gancho_fica_fora_do_instalado():
    modulos, telas = _listas_do_construir()
    faltam = []
    for m in _modulos_do_gancho():
        pacote = m.split(".")[0]
        if pacote not in modulos:                   # o pacote fora leva os submódulos junto (PyInstaller)
            faltam.append("MODULOS_SO_DEV: " + pacote)
        # as telas do módulo (web/<pacote>/) também ficam de fora
        if os.path.isdir(os.path.join(SISTEMA, "web", pacote)) and not any(fnmatch.fnmatch(pacote, t) for t in telas):
            faltam.append("TELAS_SO_DEV: web/" + pacote)
    assert not faltam, "módulo do dev que iria no instalado: " + "; ".join(faltam)
