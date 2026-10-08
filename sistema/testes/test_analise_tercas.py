# -*- coding: utf-8 -*-
"""As terças na análise (calibração com o Tekla, 08/10/2026): a terça rotulada onde termina sobre a tesoura e a carga do
telhado chegando às tesouras pelas terças — antes ia direto aos nós do banzo de cima e a terça só via o peso próprio.
Duas marquises chumbadas em pilares de concreto, a 6 m uma da outra, com uma terça em cada nó do banzo de cima."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d.geometria import extrudar  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402

U = "U 150×50×3,00 (FF)"
L = 'L 1½"×1/8"'
UE = "Ue 150×60×20×2,00"
VAO = 6000.0
Y = [25.0, 1000.0, 2000.0, 3000.0]


def _pilar(doc, x, marca):
    sol = extrudar([(x - 175.0, -700.0), (x + 175.0, -700.0), (x + 175.0, 0.0), (x - 175.0, 0.0)], (0.0, 0.0, 1.0), 8000.0,
                   origem=(0.0, 0.0, 0.0), nome="Pilar " + marca)
    sol.material = "Concreto"
    sol.atributos = {"elemento": "pilar", "marca": marca, "pre_moldado": True}
    doc.add(sol)


def _barra(doc, a, b, perfil, papel, papel_trelica, t):
    doc.add(Barra(inicio=a, fim=b, perfil=perfil, papel=papel, rotacao=90.0 if papel == "banzo" else 0.0,
                  atributos={"elemento": "trelica", "papel_trelica": papel_trelica, "origem_2d": t, "origem": {"peca": t.upper()},
                             "marca": t.upper()}))


def _cobertura():
    doc = Documento(nome="duas marquises")
    for k, x in enumerate((0.0, VAO)):
        t = "t%d" % (k + 1)
        _pilar(doc, x, "P%d" % (k + 1))
        for i in range(3):
            _barra(doc, (x, Y[i], 5000), (x, Y[i + 1], 5000), U, "banzo", "banzo_inf", t)
            _barra(doc, (x, Y[i], 6000), (x, Y[i + 1], 6000), U, "banzo", "banzo_sup", t)
        for yy in Y:
            _barra(doc, (x, yy, 5000), (x, yy, 6000), L, "montante", "montante", t)
        for i in range(3):
            _barra(doc, (x, Y[i], 6000), (x, Y[i + 1], 5000), L, "diagonal", "diagonal", t)
    for yy in Y:
        doc.add(Barra(inicio=(0.0, yy, 6000), fim=(VAO, yy, 6000), perfil=UE, papel="terça", rotacao=0.0,
                      atributos={"elemento": "terça", "marca": "TC"}))
    return doc


PAR = {"travamento_hipotese": "nao", "segunda_ordem": False, "vento": False}


def _tercas(M):
    return [i for i, br in enumerate(M["barras"]) if br["papel"] == "terça"]


def test_terca_rotulada_nas_pontas_sobre_a_tesoura():
    M = AE.montar(_cobertura(), PAR)
    ts = _tercas(M)
    assert ts and all({4, 5, 10, 11} <= set(M["barras"][i]["soltos"]) for i in ts)
    M2 = AE.montar(_cobertura(), dict(PAR, terca_rotulada=False))
    assert all(not M2["barras"][i]["soltos"] for i in _tercas(M2))


def test_a_carga_do_telhado_chega_pelas_tercas_com_o_mesmo_total():
    novo = AE.cargas(AE.montar(_cobertura(), PAR))[0]
    velho = AE.cargas(AE.montar(_cobertura(), dict(PAR, cargas_pelas_tercas=False)))[0]
    for caso in ("CP", "SC"):
        assert not novo[caso]["nodal"] and novo[caso]["dist"]           # nada direto no banzo: tudo pelas terças
        M = AE.montar(_cobertura(), PAR)
        tot_novo = sum(float(w[2]) * M["barras"][i]["L"] for i, w in novo[caso]["dist"].items())
        tot_velho = sum(2.0 * float(F[2]) for F in velho[caso]["nodal"].values())
        assert tot_novo == pytest.approx(tot_velho, rel=0.01)


def test_momento_no_meio_da_terca_e_o_da_biapoiada():
    M = AE.montar(_cobertura(), PAR)
    casos = AE.cargas(M)[0]
    sol = AE.resolver(M, {"SC": casos["SC"]})
    i = next(i for i in _tercas(M) if abs(M["nos"][M["barras"][i]["a"]][1] - 2.0) < 1e-3)    # a terça do meio (y = 2 m)
    br = M["barras"][i]
    w = float(np.linalg.norm(casos["SC"]["dist"][i]))
    assert w == pytest.approx(0.25 * 1.0, rel=0.02)                     # 0,25 kN/m² × 1 m de faixa
    e = AE.esforcos_em(sol["pontas"][i, 0, :], sol["w"][i, 0, :], np.array([br["L"] / 2.0]))[0]
    assert float(np.hypot(e[4], e[5])) == pytest.approx(w * br["L"] ** 2 / 8.0, rel=0.03)
