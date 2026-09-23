# -*- coding: utf-8 -*-
"""Cálculo do modelo importado: tesoura sintética de sólidos, terças e troca de perfil."""
import math
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo3d import calculo_ifc                        # noqa: E402
from nucleo3d.modelo import Documento, Solido           # noqa: E402


def _caixa(a, b, h=100.0, w=50.0, **marcas):
    """Sólido em caixa com o eixo de a a b (mm), altura h (z) e largura w."""
    d = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in d))
    d = [x / L for x in d]
    up = [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0]
    n = [d[1] * up[2] - d[2] * up[1], d[2] * up[0] - d[0] * up[2], d[0] * up[1] - d[1] * up[0]]
    v = [n[1] * d[2] - n[2] * d[1], n[2] * d[0] - n[0] * d[2], n[0] * d[1] - n[1] * d[0]]
    verts = []
    for p in (a, b):
        for sv, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(p[i] + v[i] * sv * h / 2 + n[i] * sn * w / 2 for i in range(3)))
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    s = Solido(nome=marcas.get("perfil", "U100X50X3.04"), camada="Vigas", vertices=verts, faces=faces)
    s.atributos = {"tipo_ifc": "IfcBeam", "marcas": marcas}
    return s


def _tesoura(doc, x, conj, vao=6000.0, altura=600.0, paineis=6):
    """Treliça Pratt no plano y·z, em x, banzos contínuos de a a b."""
    dx = vao / paineis
    inf = [(x, i * dx, 0.0) for i in range(paineis + 1)]
    sup = [(x, i * dx, altura) for i in range(paineis + 1)]
    doc.add(_caixa(inf[0], inf[-1], posicao="P1", conjunto=conj, perfil="U100X50X3.04"))
    doc.add(_caixa(sup[0], sup[-1], posicao="P2", conjunto=conj, perfil="U100X50X3.04"))
    for i in range(paineis + 1):
        doc.add(_caixa(inf[i], sup[i], h=50, w=50, posicao="P3", conjunto=conj, perfil="L50X50X2.25"))
    for i in range(paineis):
        a, b = (inf[i], sup[i + 1]) if i < paineis // 2 else (sup[i], inf[i + 1])
        doc.add(_caixa(a, b, h=50, w=50, posicao="P4", conjunto=conj, perfil="L50X50X2.25"))
    return sup


@pytest.fixture(scope="module")
def modelo():
    doc = Documento(nome="teste")
    xs = [0.0, 3000.0, 6000.0]
    topos = [_tesoura(doc, x, "M%d" % (k + 1)) for k, x in enumerate(xs)]
    # terças ao longo de x sobre cada nó do banzo superior, 100 mm acima do eixo
    for i, no in enumerate(topos[0]):
        a = (-300.0, no[1], no[2] + 100.0)
        b = (6300.0, no[1], no[2] + 100.0)
        doc.add(_caixa(a, b, h=150, w=75, posicao="P10", conjunto="", perfil="C150X75X20X2.25"))
    nomes = {"tipos": {"P10": "terca_cobertura"}, "tipos_conjuntos": {"M1 / M2 / M3": "tesoura"},
             "posicoes": {"P1": "B.1", "P2": "B.2", "P3": "B.3", "P4": "B.4", "P10": "T.C.1"},
             "conjuntos": {"M1 / M2 / M3": "T1"}, "ifc": {}, "ifc_conjuntos": {"M1": "T1", "M2": "T1", "M3": "T1"}}
    return doc, nomes


def test_geometria(modelo):
    doc, nomes = modelo
    g = calculo_ifc.geometria_do_modelo(doc, nomes)
    assert g["tesouras"] == 3 and g["vao_m"] == pytest.approx(6.0, abs=0.05)
    assert abs(g["inclinacao_graus"]) < 0.5


def test_calculo_completo(modelo):
    doc, nomes = modelo
    r = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "sobrecarga": 0.25})
    assert r["ok"] and r["origem"] == "ifc"
    els = r["elementos"]
    assert {"P1", "P2", "P3", "P4", "P10"} <= set(els)
    assert els["P2"]["tipo"] == "banzo" and els["P2"]["posicao"] == "superior"
    assert els["P1"]["posicao"] == "inferior"
    assert els["P10"]["tipo"] == "terca" and els["P10"]["diagrama"]["vao_m"] == pytest.approx(3.0, abs=0.05)
    # o banzo superior comprime sob gravidade; a envoltória guarda o esforço
    assert els["P2"]["dimensionamento"]["N"] > 0
    assert 0 < els["P2"]["aproveitamento"] < 5
    assert els["P2"]["norma"].startswith("NBR 14762")
    assert els["P4"]["norma"].startswith("NBR 8800")
    # uma tesoura típica desenhada, com as barras em coordenadas reais (plano x = 0)
    assert r["portico"]["tesouras"][0]["nome"] == "T1"
    assert len(r["portico"]["barras"]) > 15
    assert all(abs(b["ini"][0] - b["fim"][0]) < 1e-6 for b in r["portico"]["barras"])
    assert r["servico"]["deslocamento"]["criterio"] == "L/250"
    assert r["combinacoes"][0]["chave"] == "envoltoria"
    assert any("banzo inferior" in v.get("dados", {}).get("observacao", "") for v in r["verificacoes"]
               if v["marca"] == "P1")
    assert r["resumo"]["tesouras"] == 3 and r["resumo"]["tercas"] == 1


def test_troca_de_perfil(modelo):
    doc, nomes = modelo
    base = calculo_ifc.calcular(doc, nomes, {"v0": 35.0})
    troca = calculo_ifc.calcular(doc, nomes, {"v0": 35.0, "trocas": {"P2": "U150X60X4.75"}})
    assert troca["elementos"]["P2"]["perfil"] == "U 150×60×4,75 (FF)"
    assert troca["elementos"]["P2"]["aproveitamento"] < base["elementos"]["P2"]["aproveitamento"]
    assert troca["resumo"]["trocas"] == {"P2": "U150X60X4.75"}


def test_sem_detalhamento():
    doc = Documento(nome="vazio")
    with pytest.raises(Exception):
        calculo_ifc.calcular(doc, {}, {})
