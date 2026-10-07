# -*- coding: utf-8 -*-
"""A faixa de ferramentas da área de trabalho (web/faixa_ferramentas.js) junta as colunas do 2D e do 3D por uma
tabela de grupos e equivalências: cada id que ela cita tem de existir na ferramenta daquele lado (senão o botão
some em silêncio), e cada ferramenta das colunas tem de estar na tabela ou cair nas sobras (o ▾ de Modificar,
que a faixa monta sozinha). O comportamento na tela: testes/verificadores/verif_faixa_ui.py."""
import glob
import os
import re

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _ler(*p):
    with open(os.path.join(WEB, *p), encoding="utf-8") as f:
        return f.read()


def _ids_2d():
    return set(re.findall(r"static id = '([^']+)'", _ler("cad", "ferramentas.js")))


def _ids_3d():
    out = set()
    for arq in glob.glob(os.path.join(WEB, "editor3d", "ferramentas", "*.js")):
        with open(arq, encoding="utf-8") as f:
            out |= set(re.findall(r"static id = '([^']+)'", f.read()))
    return out


def _tabela():
    js = _ler("faixa_ferramentas.js")
    grupos = js[js.index("var GRUPOS = ["):js.index("// a disciplina")]
    itens = re.findall(r"F\('([^']+)', (null|\[[^\]]*\]), (\[[^\]]*\])?\)|F\('([^']+)', (null|\[[^\]]*\])\)", grupos)
    out = []
    for m in itens:
        chave = m[0] or m[3]
        d2 = re.findall(r"'([^']+)'", m[1] if m[0] else m[4])
        d3 = re.findall(r"'([^']+)'", m[2]) if m[0] else []
        out.append((chave, d2, d3))
    return out


def test_os_ids_da_tabela_existem_nas_ferramentas():
    i2, i3 = _ids_2d(), _ids_3d()
    faltam = []
    for chave, d2, d3 in _tabela():
        faltam += ["2d:%s (%s)" % (i, chave) for i in d2 if i not in i2]
        faltam += ["3d:%s (%s)" % (i, chave) for i in d3 if i not in i3]
    assert not faltam, faltam


def test_a_tabela_cobre_as_ferramentas_da_coluna():
    # o que a tabela não conhece ainda aparece (no ▾ de Modificar), mas a coluna de hoje está toda nos grupos
    na_tabela2 = {i for _c, d2, _d3 in _tabela() for i in d2}
    na_tabela3 = {i for _c, _d2, d3 in _tabela() for i in d3}
    col2 = set(re.findall(r"export const FERRAMENTAS = \[([^\]]+)\]", _ler("cad", "ferramentas.js"))[0].replace("\n", " ").split(", "))
    assert len(na_tabela2) >= 24 and len(col2) >= 24
    # a estrutura do 3D entra à parte (a lista ESTRUTURA_3D da faixa)
    estrutura3 = set(re.findall(r"'([a-z_]+)'", re.search(r"var ESTRUTURA_3D = \[([^\]]+)\]", _ler("faixa_ferramentas.js")).group(1)))
    assert {"barra", "chapa", "furo", "parafuso", "encaixar", "virar"} <= estrutura3
    fora3 = _ids_3d() - na_tabela3 - estrutura3 - {"ferramenta"}
    assert not fora3, fora3


def test_a_faixa_na_area_de_trabalho():
    html = _ler("dividida.html")
    assert 'id="faixa-ferramentas"' in html and '<script src="/faixa_ferramentas.js"></script>' in html
    # a linha que o dev do pré-moldado usa para injetar o script dele não pode mudar
    assert '<script src="/barra_unica.js"></script>' in html
    area = _ler("area.js")
    assert ":root.barra-unica #barra-ferramentas" in area and "#barra-disciplina" in area
    # 07/10: o padrão são as colunas ao lado (como nas telas sozinhas); a faixa só com a escolha em Ver › Tela
    assert "naFaixa && document.documentElement.classList.contains('barra-unica')" in area
    assert "if (!naFaixa) { caixa.hidden = true;" in _ler("faixa_ferramentas.js")
    assert "'ferramentas-faixa'" in _ler("barra_unica.js")
