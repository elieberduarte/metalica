# -*- coding: utf-8 -*-
"""O leitor de PDF com os preenchimentos (Edifício Administrativo Hora Certa, 28/10): no Original as folhas do projetista
entram como foram impressas, e na 940 as treliças da marquise são polígonos cheios (traço grosso desenhado como área
preenchida, sem contorno) — o leitor deixava todo caminho só preenchido de fora e a planta da marquise ficava sem as
treliças. Com `preenchimentos=True` eles entram como hachura sólida na cor deles; sem, como antes."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pymupdf = pytest.importorskip("pymupdf")
from nucleo2d import pdf_ler  # noqa: E402
from nucleo3d import lancamento  # noqa: E402

MM = 72 / 25.4


def _pdf():
    doc = pymupdf.open()
    pg = doc.new_page(width=200 * MM, height=100 * MM)
    pg.draw_line(pymupdf.Point(10 * MM, 90 * MM), pymupdf.Point(190 * MM, 90 * MM), color=(0, 0, 0), width=0.5)
    # o "traço grosso" da treliça: um polígono fino, só preenchido de preto (sem contorno)
    sh = pg.new_shape()
    sh.draw_polyline([pymupdf.Point(20 * MM, 50 * MM), pymupdf.Point(120 * MM, 50 * MM), pymupdf.Point(120 * MM, 51 * MM),
                      pymupdf.Point(20 * MM, 51 * MM), pymupdf.Point(20 * MM, 50 * MM)])
    sh.finish(color=None, fill=(0, 0, 0), closePath=True)
    # a máscara branca (o CAD cobre o que está embaixo): não entra
    sh.draw_rect(pymupdf.Rect(150 * MM, 20 * MM, 180 * MM, 40 * MM))
    sh.finish(color=None, fill=(1, 1, 1))
    sh.commit()
    return doc.tobytes()


def test_preenchimento_vira_hachura_solida_so_quando_pedido():
    dados = _pdf()
    des, r = pdf_ler.para_desenho(dados)
    assert not [e for e in des.entidades.values() if e.tipo == "hachura"]          # como antes: fora
    des, r = pdf_ler.para_desenho(dados, preenchimentos=True)
    hs = [e for e in des.entidades.values() if e.tipo == "hachura"]
    assert len(hs) == 1 and hs[0].padrao == "solido" and hs[0].atributos.get("cor") == "#000000"
    xs = [p[0] for p in hs[0].contornos[0]]
    ys = [p[1] for p in hs[0].contornos[0]]
    # papel 200 × 100 mm, y de baixo para cima: o polígono de x 20–120, y (100 − 51) a (100 − 50)
    assert min(xs) == pytest.approx(20.0, abs=0.01) and max(xs) == pytest.approx(120.0, abs=0.01)
    assert min(ys) == pytest.approx(49.0, abs=0.01) and max(ys) == pytest.approx(50.0, abs=0.01)
    assert r["por_tipo"].get("ignorado:preenchimento branco") == 1
    # o traço continua entrando como linha
    assert [e for e in des.entidades.values() if e.tipo == "linha"]


def test_ler_arquitetonico_passa_os_preenchimentos():
    dados = _pdf()
    des, _ = lancamento.ler_arquitetonico(dados, "pdf", escala_pdf=50, preenchimentos=True)
    (h,) = [e for e in des.entidades.values() if e.tipo == "hachura"]
    xs = [p[0] for p in h.contornos[0]]
    assert max(xs) - min(xs) == pytest.approx(100.0 * 50, abs=1.0)               # × 50: tamanho real
    des, _ = lancamento.ler_arquitetonico(dados, "pdf", escala_pdf=50)
    assert not [e for e in des.entidades.values() if e.tipo == "hachura"]
