# -*- coding: utf-8 -*-
"""Os suportes de terça pelo detalhe "SUPORTE DE TERÇA ST1 - 400X" (nucleo3d/suportes_terca.py; Posto CB, 23/10/2026:
os do projeto no lugar do L 3" padrão, decisão do usuário)."""
import math

from nucleo3d import suportes_terca as ST
from nucleo3d.modelo import Barra, Documento


def _detalhe(tx, nome, qtd, H):
    """o detalhe como o da folha 12 do Posto: a vista frontal 150 × H com os oblongos (dois arcos cada), a nervura à
    direita na vista lateral, a espessura nas notas"""
    e = [{"tipo": "texto", "texto": "SUPORTE DE TERÇA %s - %dX" % (nome, qtd), "posicao": [tx, 0, 0]},
         {"tipo": "texto", "texto": "CHAPAS # 3,0mm", "posicao": [tx + 2, 143, 0]},
         {"tipo": "polilinha", "fechada": True, "vertices": [[tx + 41, 390, 0], [tx + 191, 390, 0], [tx + 191, 390 + H, 0], [tx + 41, 390 + H, 0]]}]
    for x in (76, 156):
        for y in (420, 390 + H - 20):
            e += [{"tipo": "arco", "centro": [tx + x - 6, y, 0], "raio": 6.35}, {"tipo": "arco", "centro": [tx + x + 6, y, 0], "raio": 6.35}]
    e.append({"tipo": "polilinha", "fechada": False, "vertices": [[tx + 648, 405, 0], [tx + 648, 385 + H, 0], [tx + 663, 385 + H, 0],
                                                                   [tx + 718, 405, 0], [tx + 718, 390, 0], [tx + 663, 390, 0], [tx + 648, 405, 0]]})
    return e


def test_detalhe_do_suporte():
    d = ST.detalhes(_detalhe(0.0, "ST1", 400, 90.0) + _detalhe(5000.0, "ST2", 72, 120.0))
    assert set(d) == {"ST1", "ST2"} and d["ST1"]["qtd"] == 400 and (d["ST1"]["B"], d["ST1"]["H"], d["ST1"]["t"]) == (150.0, 90.0, 3.0)
    assert sorted((f["x"], f["y"]) for f in d["ST1"]["furos"]) == [(35.0, 30.0), (35.0, 70.0), (115.0, 30.0), (115.0, 70.0)]
    assert all(f["largura"] == 24.7 and f["altura"] == 12.7 for f in d["ST1"]["furos"])        # o oblongo 12,7 × 25
    assert d["ST1"]["nervura"][1] == (0.0, 85.0) and d["ST2"]["H"] == 120.0


def test_um_suporte_por_apoio_e_a_emenda_leva_um_so():
    """cada terça que apoia num banzo ganha o suporte ali, encostado nas costas da alma e no topo do banzo; as duas pontas
    da emenda sobre o mesmo banzo dividem um (dois furos de cada lado); a U 100 leva o ST1 (90), a U 127 o ST2 (120)"""
    dets = ST.detalhes(_detalhe(0.0, "ST1", 400, 90.0) + _detalhe(5000.0, "ST2", 72, 120.0))
    doc = Documento()
    banzos = []
    for y in (0.0, 6000.0, 12000.0):                        # três banzos U 100×40 de boca para baixo, topo em 6000
        b = Barra(nome="b", inicio=(0.0, y, 6000.0 - 9.9), fim=(10000.0, y, 6000.0 - 9.9), perfil="U 100×40×2,25 (FF)",
                  papel="banzo", rotacao=270.0)
        doc.add(b)
        banzos.append(b)
    tercas = []
    for y0, y1 in ((-200.0, 6000.0), (6000.0, 12200.0)):   # emenda sobre o banzo do meio
        t = Barra(nome="t", inicio=(5000.0, y0, 6050.0), fim=(5000.0, y1, 6050.0), perfil="U 100×40×2,25 (FF)", papel="terça")
        doc.add(t)
        tercas.append(t)
    chapas, avisos = [], []
    r = ST.lancar(doc, tercas, banzos, dets, "ASTM A36", chapas, avisos)
    assert r["suportes"] == 3 and r["por_nome"] == {"ST1": 3}, r
    sup = [c for c in chapas if c.nome == "Suporte de terça ST1"]
    assert len(sup) == 3 and all(abs(c.origem[2] - 6000.0) < 1.0 for c in sup)          # no topo do banzo
    assert len([c for c in chapas if c.nome.startswith("Nervura")]) == 3
    # a chapa encosta nas costas da alma da terça (a alma da U fica xg do eixo, do lado de u)
    from nucleo3d.geometria import base_local, secao
    from nucleo3d.de_planta import _perfil
    u, _v, _w = base_local((0.0, 1.0, 0.0), 0.0)
    xmin = min(x for x, _y in secao(_perfil("U 100×40×2,25 (FF)")))
    for c in sup:
        meio = (c.origem[0] + c.eixo_x[0] * 75.0, c.origem[1] + c.eixo_x[1] * 75.0)
        assert abs(((meio[0] - 5000.0) * u[0] + (meio[1] - 0.0) * u[1]) - (xmin - 1.5)) < 0.01
    # a U 127 leva o ST2
    t2 = Barra(nome="t", inicio=(8000.0, -200.0, 6063.5), fim=(8000.0, 6000.0, 6063.5), perfil="U 127×50×3,04 (FF)", papel="terça")
    doc.add(t2)
    r = ST.lancar(doc, [t2], banzos, dets, "ASTM A36", [], [])
    assert r["por_nome"] == {"ST2": 2}, r
