# -*- coding: utf-8 -*-
"""Regras de apoio do modelo 3D (nucleo3d/apoios.py): peça voando, ponta de treliça sem
apoio, terça em balanço e fora do nó, pilar sem carga, viga sem apoio."""
from nucleo3d import apoios
from nucleo3d.modelo import Barra, Documento


def barra(p0, p1, papel, peca=None, perfil="U 100×40×2,25 (FF)"):
    b = Barra(nome=perfil, inicio=p0, fim=p1, perfil=perfil, papel=papel)
    b.atributos = {"origem": {"peca": peca} if peca else {}}
    return b


def trelica(doc, y, x0, x1, peca, h=800.0, passo=1000.0):
    """treliça plana ao longo de x no nível 6000: banzos, montantes a cada `passo`"""
    doc.add(barra((x0, y, 6000.0), (x1, y, 6000.0), "banzo", peca))
    doc.add(barra((x0, y, 6000.0 + h), (x1, y, 6000.0 + h), "banzo", peca))
    x = x0
    while x <= x1 + 1.0:
        doc.add(barra((x, y, 6000.0), (x, y, 6000.0 + h), "montante", peca))
        x += passo


def modelo_certo():
    doc = Documento()
    for x in (0.0, 6000.0):
        for y in (0.0, 5000.0):
            doc.add(barra((x, y, 0.0), (x, y, 6000.0), "pilar", perfil="W 200×19,3"))
    trelica(doc, 0.0, 0.0, 6000.0, "T#1")
    trelica(doc, 5000.0, 0.0, 6000.0, "T#2")
    for x in (1000.0, 3000.0, 5000.0):                  # terças nos nós
        doc.add(barra((x, 0.0, 6870.0), (x, 5000.0, 6870.0), "terça"))
    return doc


def test_modelo_certo_passa_em_tudo():
    v = apoios.verificar(modelo_certo())
    assert v["achados"] == [], v["achados"]
    assert v["resumo"]["pontas_apoiadas"] == 4 and v["resumo"]["tercas_ok"] == 3


def test_acha_cada_regra():
    doc = modelo_certo()
    doc.add(barra((2000.0, 2000.0, 9000.0), (2500.0, 2000.0, 9000.0), "viga"))         # voando
    doc.add(barra((1000.0, 5000.0, 6870.0), (1000.0, 7000.0, 6870.0), "terça"))        # 2 m em balanço
    doc.add(barra((3500.0, 0.0, 6870.0), (3500.0, 5000.0, 6870.0), "terça"))           # no meio do painel
    doc.add(barra((9000.0, 0.0, 0.0), (9000.0, 0.0, 6000.0), "pilar", perfil="W 200×19,3"))  # nada em cima
    trelica(doc, 2500.0, 6000.0, 8000.0, "T#3")                                         # ponta solta em x=8000
    regras = {a["regra"] for a in apoios.verificar(doc)["achados"]}
    assert {"voando", "terca_em_balanco", "terca_fora_do_no", "pilar_sem_carga", "viga_sem_apoio",
            "ponta_sem_apoio"} <= regras
