# -*- coding: utf-8 -*-
"""Importação do .skp (ifc/skp.py, 02/10): as partes de uma barra que o CYPE exporta em pedaços (mesas, alma recortada
na ponta) viram uma peça só; a viga de outro eixo que encosta numa ligação não entra; o perfil sai pelo catálogo."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ifc import skp  # noqa: E402


def _caixa(x0, y0, z0, x1, y1, z1, etq="PIEZA_METALICA_VIGA"):
    vs = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return {"etiqueta": etq, "vertices": vs, "faces": [[0, 1, 3], [0, 3, 2]]}


def test_partes_da_barra_viram_uma_peca():
    # W610X140 em pedaços: mesa de baixo e de cima (230 x 22) e a alma (13 de espessura), a mesa 166 mm mais curta
    mesa_b = _caixa(0, 0, 0, 230, 10000 - 166, 22)
    alma = _caixa(108.5, 0, 22, 121.5, 10000, 595)
    mesa_c = _caixa(0, 0, 595, 230, 10000 - 166, 617)
    outra = _caixa(230, 5000, 0, 10230, 5230, 617)          # a viga do outro eixo, encostada numa ligação
    juntas = skp._juntar_barras([mesa_b, alma, mesa_c, outra])
    partes = sorted(p.get("partes", 1) for p in juntas)
    assert partes == [1, 3], partes
    viga = next(p for p in juntas if p.get("partes") == 3)
    comp, alt, larg = skp._secao_da_barra(viga["vertices"])
    assert round(comp) == 10000 and round(alt) == 617 and round(larg) == 230
    assert skp._perfil_I(skp._catalogo_I(), alt, larg) == "W610X140"
