# -*- coding: utf-8 -*-
"""O texto de várias linhas (24/10, o MTEXT do AutoCAD): as linhas no texto separadas por "\\n", 1,6 altura uma da outra.
O PDF passa pelo DXF R12 do desenho (Desenho.para_dxf), que só tem TEXT: cada linha sai como um TEXT no lugar dela
(antes saíam todas numa linha só no PDF); o DXF do botão sai com MTEXT."""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ezdxf

from nucleo2d.desenho import Desenho, Texto, linhas_do_texto, ENTRELINHA
from nucleo2d import dxf_cad


def test_linhas_descem_a_partir_do_ponto():
    t = Texto(posicao=(10.0, 50.0), texto="A\nB\nC", altura=2.0, vertical="topo")
    ls = linhas_do_texto(t)
    assert [x for _p, x in ls] == ["A", "B", "C"]
    assert [p for p, _x in ls] == [(10.0, 50.0), (10.0, 50.0 - ENTRELINHA * 2.0), (10.0, 50.0 - 2 * ENTRELINHA * 2.0)]


def test_meio_centra_o_bloco_e_o_giro_acompanha():
    t = Texto(posicao=(0.0, 0.0), texto="A\nB\nC", altura=2.0, vertical="meio")
    assert [round(p[1], 6) for p, _x in linhas_do_texto(t)] == [3.2, 0.0, -3.2]
    g = Texto(posicao=(0.0, 0.0), texto="A\nB", altura=2.0, angulo=90.0)
    (p0, _), (p1, _) = linhas_do_texto(g)
    assert p0 == (0.0, 0.0) and math.isclose(p1[0], 3.2) and abs(p1[1]) < 1e-9, "girado 90°: a 2ª linha à direita"


def test_texto_comum_igual():
    t = Texto(posicao=(1.0, 2.0), texto="UMA", altura=2.5)
    assert linhas_do_texto(t) == [((1.0, 2.0), "UMA")]


def test_pdf_um_text_por_linha():
    d = Desenho(nome="t", escala=1.0)
    d.add(Texto(posicao=(0.0, 50.0), texto="LINHA 1\nLINHA 2\nLINHA 3", altura=3.0, vertical="topo"))
    with tempfile.TemporaryDirectory() as tmp:
        arq = d.para_dxf(1.0, texto_unicode=True).gravar(os.path.join(tmp, "r12.dxf"))
        textos = {t.dxf.text: t for t in ezdxf.readfile(arq).modelspace().query("TEXT")}
    assert set(textos) == {"LINHA 1", "LINHA 2", "LINHA 3"}, sorted(textos)


def test_dxf_do_botao_com_mtext():
    d = Desenho(nome="t", escala=1.0)
    d.add(Texto(posicao=(0.0, 50.0), texto="LINHA 1\nLINHA 2", altura=3.0))
    with tempfile.TemporaryDirectory() as tmp:
        doc = ezdxf.readfile(dxf_cad.exportar(d, os.path.join(tmp, "t.dxf")))
        mts = [m.text for m in doc.modelspace().query("MTEXT")]
    assert mts == ["LINHA 1\\PLINHA 2"]
