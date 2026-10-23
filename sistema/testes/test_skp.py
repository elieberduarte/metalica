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
    comp, alt, larg, _da, _dl = skp._secao_da_barra(viga["vertices"])
    assert round(comp) == 10000 and round(alt) == 617 and round(larg) == 230
    assert skp._perfil_I(skp._catalogo_I(), alt, larg) == "W610X140"


def test_viga_dupla_lado_a_lado_vira_duas():
    """Duas W610X217 encostadas pela mesa num sólido só (a diagonal do heliponto, 02/10): 656 de largura não é perfil;
    a metade (328) é — a peça se divide no meio, cada metade com a malha dela."""
    vs = [(x, y, z) for x in (0.0, 328.0, 656.0) for y in (0.0, 10000.0) for z in (0.0, 628.0)]
    idx = {v: i for i, v in enumerate(vs)}
    faces = []
    for x0, x1 in ((0.0, 328.0), (328.0, 656.0)):
        for y in (0.0, 10000.0):
            faces.append([idx[(x0, y, 0.0)], idx[(x1, y, 0.0)], idx[(x1, y, 628.0)], idx[(x0, y, 628.0)]])
        faces.append([idx[(x0, 0.0, 0.0)], idx[(x1, 0.0, 0.0)], idx[(x1, 10000.0, 0.0)], idx[(x0, 10000.0, 0.0)]])
    comp, alt, larg, dir_alt, dir_larg = skp._secao_da_barra(vs)
    assert round(larg) == 628 or round(alt) == 656
    metades = skp._dividir_ao_meio(vs, faces, (1.0, 0.0, 0.0))
    assert [round(max(v[0] for v in m[0]) - min(v[0] for v in m[0])) for m in metades] == [328, 328]
    assert skp._perfil_I(skp._catalogo_I(), 628, 328) == "W610X217"


def _caixa_fechada(x0, y0, z0, x1, y1, z1, base=0):
    """as 8 pontas e as 6 faces (para fora) de uma caixa, com os índices a partir de `base`"""
    vs = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    fs = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    return vs, [[base + i for i in f] for f in fs]


def test_chapas_soldadas_juntas_pesam_pelo_volume():
    """A cartela da base do heliponto v2 (23/10): a chapa 800 × 250 × 11 e as nervuras de 11 que encostam nela vêm do
    .skp numa peça só (mesma etiqueta, se tocam); pela caixa ela era "PLATE 800x250x150" e a lista pesava 235 kg em
    vez de ~20 (4,2 t a mais nas 18). A espessura passa a ser a equivalente pelo volume da malha."""
    va, fa = _caixa_fechada(139.0, 0.0, 0.0, 150.0, 800.0, 250.0)
    vb, fb = _caixa_fechada(0.0, 150.0, 0.0, 139.0, 161.0, 250.0, base=8)
    vc, fc = _caixa_fechada(0.0, 639.0, 0.0, 139.0, 650.0, 250.0, base=16)
    vs, fs = va + vb + vc, fa + fb + fc
    dims = sorted((150.0, 800.0, 250.0))
    nome = skp._nome_da_chapa(vs, fs, dims)
    t = float(nome.split("x")[-1])
    assert nome.startswith("PLATE 800x250x"), nome
    assert 12.0 < t < 15.0, nome                         # 11 + as nervuras (2 × 139 × 11 / 800) ≈ 14,8
    # a chapa que é uma chapa só continua pela caixa
    v1, f1 = _caixa_fechada(0.0, 0.0, 0.0, 7.0, 600.0, 150.0)
    assert skp._nome_da_chapa(v1, f1, sorted((7.0, 600.0, 150.0))) == "PLATE 600x150x7"
