# -*- coding: utf-8 -*-
"""A análise global do pré-moldado (nucleo3d/analise_premoldado.py, 09/10): a seção pela face do sólido, o módulo do
concreto, o pórtico de dois pilares e uma viga apoiada nos consolos."""
import math

import numpy as np

from nucleo3d import analise_premoldado as AP
from nucleo3d.modelo import Documento, Solido


def _caixa(nome, x0, y0, z0, x1, y1, z1, tipo_ifc, material="CONCRETE/FCK 40"):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome=nome, material=material, vertices=v, faces=f, atributos={"tipo_ifc": tipo_ifc})


def test_secao_retangular_pela_face():
    """viga 40 × 80 cm ao longo de x: A = 0,32 m², a inércia forte pela altura (bh³/12)"""
    e = _caixa("VIGA", 0, 0, 0, 6000, 400, 800, "IfcBeam")
    s = AP._secao_do_solido(e, np.array([1.0, 0.0, 0.0]))
    assert abs(s["A"] - 0.32) < 1e-9
    assert abs(s["Iz"] - 0.4 * 0.8 ** 3 / 12) < 1e-9 and abs(s["Iy"] - 0.8 * 0.4 ** 3 / 12) < 1e-9
    assert abs(abs(s["ey"][2]) - 1.0) < 1e-9                       # a altura da seção é a vertical


def test_poligono_em_i():
    """o I de 300 × 300 com mesas e alma de 20 mm: a área e o momento de inércia forte batem com a conta à mão"""
    b, h, t = 0.3, 0.3, 0.02
    pts = np.array([[-b / 2, -h / 2], [b / 2, -h / 2], [b / 2, -h / 2 + t], [t / 2, -h / 2 + t], [t / 2, h / 2 - t], [b / 2, h / 2 - t],
                    [b / 2, h / 2], [-b / 2, h / 2], [-b / 2, h / 2 - t], [-t / 2, h / 2 - t], [-t / 2, -h / 2 + t], [-b / 2, -h / 2 + t]])
    pr = AP._poligono_props(pts)
    A = 2 * b * t + (h - 2 * t) * t
    I = b * h ** 3 / 12 - (b - t) * (h - 2 * t) ** 3 / 12
    assert abs(pr["A"] - A) < 1e-12
    assert abs(pr["T"][1, 1] - I) < 1e-12                          # ∫y² dA


def test_modulo_do_concreto():
    eci, ecs = AP.modulo_concreto(40.0)
    assert abs(eci - 5600 * math.sqrt(40) * 1000) < 1e-6
    assert abs(ecs - (0.8 + 0.2 * 40 / 80) * eci) < 1e-6


def test_portico_de_dois_pilares_e_uma_viga():
    """dois pilares de 6 m e a viga apoiada nos consolos: o modelo é de pré-moldado, a viga fica rotulada nas duas
    pontas, os pilares engastados, e o peso próprio fecha com as reações"""
    doc = Documento()
    for i, x in enumerate((0, 8000)):
        p = _caixa("PILAR RETANGULAR", x - 200, -200, 0, x + 200, 200, 6000, "IfcColumn")
        doc.entidades[p.id] = p
    for k in range(9):                                              # o mínimo de peças de concreto para o modelo ser pré-moldado
        v = _caixa("VIGA RETANGULAR", 200, -150, 6000, 7800, 150, 6600, "IfcBeam") if k == 0 else \
            _caixa("PILAR RETANGULAR", 30000 + k * 3000, 0, 0, 30400 + k * 3000, 400, 4000, "IfcColumn")
        doc.entidades[v.id] = v
    assert AP.e_premoldado(doc)
    from nucleo3d import analise_estrutural as AE
    r = AE.calcular(doc, {"vento": False, "segunda_ordem": False})
    assert r["modelo_analise"] == "premoldado" and not r["instavel"]
    viga = [b for b in r["barras"] if b["papel"] == "viga"]
    assert viga and sorted(viga[0]["rotulas"]) == ["a", "b"]
    eq = r["equilibrio"]["PP"]
    assert abs(eq["cargas_kN"][2] + eq["reacoes_kN"][2]) < 1e-6
