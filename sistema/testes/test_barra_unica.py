# -*- coding: utf-8 -*-
"""A barra única da área de trabalho (web/barra_unica.js) aciona os comandos das telas pelo data-acao /
data-vista do menu delas: cada comando do mapa tem de existir na tela do lado dele (senão o item some
do menu em silêncio)."""
import os
import re

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _ler(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


def test_cada_comando_do_mapa_existe_na_tela_do_lado():
    js = _ler("barra_unica.js")
    telas = {"2d": _ler("cad", "cad.html"), "3d": _ler("editor3d", "editor.html")}
    topo = {k: v[v.index('<header class="topo"'):v.index("</header>")] for k, v in telas.items()}
    faltam = []
    for texto, lado, acao in re.findall(r"I\('([^']+)', '(2d|3d)', '([^']+)'", js):
        if acao in ("desfazer", "refazer"):
            continue
        if 'data-acao="%s"' % acao not in topo[lado]:
            faltam.append((texto, lado, acao))
    for texto, lado, vista in re.findall(r"V\('([^']+)', '(2d|3d)', '([^']+)'", js):
        if 'data-vista="%s"' % vista not in topo[lado]:
            faltam.append((texto, lado, "vista " + vista))
    assert not faltam, faltam
    # as setas de desfazer / refazer usam o Editar das duas telas
    for lado in ("2d", "3d"):
        assert 'data-acao="desfazer"' in topo[lado] and 'data-acao="refazer"' in topo[lado]
