# -*- coding: utf-8 -*-
"""A Ajuda e os textos das telas citam menus que existem (P09 e P27 do teste de primeiro uso, 16/10/2026): o engenheiro
novo leu "na tela de projetos, Novo a partir do arquitetônico…" (o botão não existia) e "Desenho → Montar o 3D pela
planta" (o item fica em Vistas do modelo), e a árvore vazia do 3D mandava a "Arquivo → Gerar do galpão".

Cada caminho "Menu → Item" (ou "Menu › Item") escrito em negrito na Ajuda, ou num texto das telas, cujo primeiro nome
é um menu do CAD, do editor 3D ou da barra da tela do projeto, tem de levar a um item desse menu; cada botão "Novo …"
citado tem de existir na tela de projetos."""
import glob
import html
import os
import re

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _ler(rel):
    with open(os.path.join(WEB, rel), encoding="utf-8") as f:
        return f.read()


def _norm(t):
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\s+", " ", t).strip().rstrip(":").rstrip("…").rstrip(".").strip()


def _pares_html(rel):
    """(título do menu, item) dos menus <div class="menu"> do CAD e do editor 3D"""
    out = set()
    for bloco in re.split(r'<div class="menu"[^>]*>', _ler(rel))[1:]:
        bloco = re.split(r'</nav>|<main', bloco)[0]
        botoes = [_norm(b) for b in re.findall(r"<button[^>]*>(.*?)</button>", bloco, re.S)]
        if botoes:
            out |= {(botoes[0], b) for b in botoes[1:]}
            out |= {(botoes[0], _norm(t)) for t in re.findall(r'class="menu-titulo">(.*?)<', bloco)}
    return out


def _pares_barra():
    """(menu, submenu), (menu, item) e (submenu, item) da barra da tela do projeto (barra_unica.js)"""
    out, topo, sub = set(), None, None
    for m in re.finditer(r"\{ nome: '([^']+)'|S\('([^']+)'|I\('([^']+)'|\]\)", _ler("barra_unica.js")):
        if m.group(1):
            topo, sub = _norm(m.group(1)), None
        elif m.group(2):
            sub = _norm(m.group(2))
            out.add((topo, sub))
        elif m.group(3):
            it = _norm(m.group(3))
            out.add((topo, it))
            if sub:
                out.add((sub, it))
        else:
            sub = None
    return out


PARES = _pares_html("cad/cad.html") | _pares_html("editor3d/editor.html") | _pares_barra()
MENUS = {a for a, _b in PARES}
ITENS = {}
for _a, _b in PARES:
    ITENS.setdefault(_a, set()).add(_b)


def _caminho_ok(menu, resto):
    resto = _norm(resto)
    return any(resto == it or resto.startswith(it) or it.startswith(resto) for it in ITENS.get(menu, ()))


def test_leitor_dos_menus_acha_os_menus():
    assert {"Desenho", "Vistas do modelo", "Lançamento", "Arquivo", "Modelo", "Ver"} <= MENUS
    assert ("Vistas do modelo", "Montar o 3D pela planta (projeto recebido)") in PARES


def test_caminhos_da_ajuda_levam_a_um_item_do_menu():
    ruins = []
    for txt in re.findall(r"<b>([^<]*?(?:→|›)[^<]*?)</b>", _ler("ajuda.html")):
        partes = re.split(r"\s*(?:→|›)\s*", txt)
        for i in range(len(partes) - 1):
            a = _norm(partes[i])
            # o item pode ter "→" no próprio nome ("Projeto recebido (DXF/PDF) → modelo 3D e IFC…")
            if a in MENUS and not (_caminho_ok(a, partes[i + 1]) or _caminho_ok(a, " → ".join(partes[i + 1:]))):
                ruins.append(txt)
    assert not ruins, "a Ajuda cita caminhos de menu que não existem: %s" % ruins


def test_botoes_novo_da_ajuda_existem_na_tela_de_projetos():
    inicio = {_norm(b) for b in re.findall(r"<button[^>]*>(.*?)</button>", _ler("inicio.html"), re.S)}
    citados = {_norm(b) for b in re.findall(r"<b>(Novo [^<]+)</b>", _ler("ajuda.html"))}
    assert citados and not (citados - inicio), "a Ajuda cita botões Novo… que a tela de projetos não tem: %s" % (citados - inicio)


def test_textos_das_telas_citam_menus_que_existem():
    arqs = sorted({os.path.join(WEB, "editor3d", "editor.js"), os.path.join(WEB, "cad", "cad.js")}
                  | set(glob.glob(os.path.join(WEB, "editor3d", "modulos", "*.js"))) | set(glob.glob(os.path.join(WEB, "cad", "*.js"))))
    rx = re.compile(r"(%s) (?:→|›) ([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^'`\"();:,.]{2,60})" % "|".join(re.escape(m) for m in sorted(MENUS, key=len, reverse=True)))
    ruins = []
    for arq in arqs:
        with open(arq, encoding="utf-8") as f:
            for n, linha in enumerate(f, 1):
                if linha.lstrip().startswith(("*", "/*", "//")):
                    continue
                for m in rx.finditer(linha):
                    if not _caminho_ok(m.group(1), m.group(2)):
                        ruins.append("%s:%d: %s → %s" % (os.path.relpath(arq, WEB), n, m.group(1), m.group(2)))
    assert not ruins, "textos das telas citam itens de menu que não existem: %s" % ruins
