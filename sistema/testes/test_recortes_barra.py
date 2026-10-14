# -*- coding: utf-8 -*-
"""Recortes de encaixe da barra (o cope, F8 de 14/10/2026): a malha tira exatamente o bloco da seção acima (ou abaixo,
ou ao lado) da linha do recorte, nas duas pontas; o peso sai pelo volume; o IFC leva o bloco tirado."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Barra, Documento          # noqa: E402
from nucleo3d import geometria as g                   # noqa: E402
from ifc.exportar import para_texto                   # noqa: E402

W = "W 250×32,7"


def _volume(vs, fs):
    v = 0.0
    for f in fs:
        a = vs[f[0]]
        for k in range(1, len(f) - 1):
            b, c = vs[f[k]], vs[f[k + 1]]
            v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return abs(v)


def _area_acima(ext, a, b, c):
    return abs(g.area_assinada(g._recortar_convexo(ext, a, b, c)))


def test_recorte_tira_o_bloco_certo_nas_duas_pontas_e_nos_lados():
    ext, _ = g._normalizar_contorno(g.secao_com_furos(W))
    xs, ys = [p[0] for p in ext], [p[1] for p in ext]
    x1, y0, y1 = max(xs), min(ys), max(ys)
    cheia = _volume(*g.malha_barra(Barra(inicio=(0, 0, 0), fim=(2000, 0, 0), perfil=W)))
    casos = [
        ([{"ponta": "fim", "lado": "cima", "comprimento": 150, "altura": 40}], _area_acima(ext, 0, 1, -(y1 - 40)) * 150),
        ([{"ponta": "inicio", "lado": "baixo", "comprimento": 100, "altura": 30}], _area_acima(ext, 0, -1, y0 + 30) * 100),
        ([{"ponta": "fim", "lado": "esquerda", "comprimento": 120, "altura": 20}], _area_acima(ext, 1, 0, -(x1 - 20)) * 120),
    ]
    for rec, tirado in casos:
        b = Barra(inicio=(0, 0, 0), fim=(2000, 0, 0), perfil=W, recortes=rec)
        vs, fs = g.malha_barra(b)
        assert abs((cheia - _volume(vs, fs)) - tirado) < 1.0, rec
        medio, corte = g.comprimentos_da_barra(b)
        assert abs(medio - _volume(vs, fs) / (cheia / 2000.0)) < 0.5 and abs(corte - 2000.0) < 1e-6


def test_o_ifc_leva_o_recorte_como_bloco_tirado():
    doc = Documento()
    doc.add(Barra(nome="secundaria", inicio=(0, 0, 0), fim=(2000, 0, 0), perfil=W, papel="viga",
                  recortes=[{"ponta": "fim", "lado": "cima", "comprimento": 72, "altura": 19}]))
    txt = para_texto(doc)
    assert "IFCBLOCK" in txt and "IFCBOOLEANRESULT(.DIFFERENCE." in txt


def test_barra_sem_recorte_nao_muda():
    b = Barra(inicio=(0, 0, 0), fim=(2000, 0, 0), perfil=W)
    assert not g.tem_corte_no_angulo(b) and g.recortes_locais(b, [(0, 0), (1, 0), (1, 1)]) == ([], [])
