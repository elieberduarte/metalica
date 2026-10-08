# -*- coding: utf-8 -*-
"""A tesoura chumbada no pilar de concreto e a dobra da alma (nucleo3d/analise_estrutural.montar) — Docas, 08/10: a
marquise em balanço com os dois banzos chumbados no pilar pré-moldado e uma barra quebrada no meio da tesoura."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d.geometria import extrudar  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402

U = "U 150×50×3,00 (FF)"
L = 'L 1½"×1/8"'


def _pilar(doc):
    """o pilar de concreto 350×700 mm, de 0 a 8 m, com a face em y = 0 (a tesoura sai para y > 0)"""
    sol = extrudar([(-175.0, -700.0), (175.0, -700.0), (175.0, 0.0), (-175.0, 0.0)], (0.0, 0.0, 1.0), 8000.0,
                   origem=(0.0, 0.0, 0.0), nome="Pilar P1")
    sol.material = "Concreto"
    sol.atributos = {"elemento": "pilar", "marca": "P1", "pre_moldado": True}
    doc.add(sol)


def _barra(doc, a, b, perfil, papel, papel_trelica):
    doc.add(Barra(inicio=a, fim=b, perfil=perfil, papel=papel, rotacao=90.0 if papel == "banzo" else 0.0,
                  atributos={"elemento": "trelica", "papel_trelica": papel_trelica, "origem_2d": "t1", "origem": {"peca": "T1"},
                             "marca": "T1"}))


def _marquise(com_dobra=False):
    """tesoura em balanço de 3 m (painéis de 1 m), 1 m de altura, presa no pilar pela ponta de y = 25 mm"""
    doc = Documento(nome="marquise")
    _pilar(doc)
    y = [25.0, 1000.0, 2000.0, 3000.0]
    for i in range(3):
        _barra(doc, (0, y[i], 5000), (0, y[i + 1], 5000), U, "banzo", "banzo_inf")
        _barra(doc, (0, y[i], 6000), (0, y[i + 1], 6000), U, "banzo", "banzo_sup")
    for yy in y:
        _barra(doc, (0, yy, 5000), (0, yy, 6000), L, "montante", "montante")
    for i in range(3):
        _barra(doc, (0, y[i], 6000), (0, y[i + 1], 5000), L, "diagonal", "diagonal")
    if com_dobra:
        # a barra quebrada: do banzo de baixo a um ponto solto e dele ao banzo de cima (duas almas e mais nada no ponto)
        _barra(doc, (0, 1000.0, 5000), (0, 1500.0, 5450), L, "diagonal", "diagonal")
        _barra(doc, (0, 1500.0, 5450), (0, 2000.0, 6000), L, "diagonal", "diagonal")
    return doc


def test_tesoura_chumbada_no_pilar_de_concreto():
    M = AE.montar(_marquise(), {"travamento_hipotese": "nao"})
    chumbadas = [a for a in M["apoios"] if a.get("chumbada")]
    # os dois nós da ponta (banzo de baixo e de cima) na face do pilar; nada nos nós mais baixos da tesoura
    assert len(chumbadas) == 2 and len(M["apoios"]) == 2
    assert {a["chumbada"] for a in chumbadas} == {"P1"} and all(a["tipo"] == "engastada" for a in chumbadas)
    assert not any("fora do catálogo" in a or "nós mais baixos" in a for a in M["avisos"])


def test_balanco_fica_de_pe_e_o_binario_nos_banzos():
    r = AE.calcular(_marquise(), {"travamento_hipotese": "nao", "segunda_ordem": False})
    assert not any("instável" in a for a in r["avisos"])


def test_dobra_da_alma_e_continua():
    M = AE.montar(_marquise(com_dobra=True), {"travamento_hipotese": "nao"})
    # as duas almas que se encontram no ponto solto não soltam o giro ali (o joelho girava: mecanismo)
    no = {i for i, p in enumerate(M["nos"]) if abs(p[1] - 1.5) < 1e-3 and abs(p[2] - 5.45) < 1e-3}
    assert len(no) == 1
    n = no.pop()
    for br in M["barras"]:
        if n in (br["a"], br["b"]):
            base = 0 if br["a"] == n else 6
            assert not any(base <= s < base + 6 for s in br["soltos"])
    r = AE.calcular(_marquise(com_dobra=True), {"travamento_hipotese": "nao", "segunda_ordem": False})
    assert not any("instável" in a for a in r["avisos"])
