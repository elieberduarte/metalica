# -*- coding: utf-8 -*-
"""Modelo analítico (nucleo3d/analitico.py): o esqueleto de nós e barras — perfil duplo numa
linha só, pontas juntadas no nó, a terça levada ao banzo em que apoia, a ponta que sobra solta."""
from nucleo3d import analitico
from nucleo3d.modelo import Barra, Documento


def barra(p0, p1, papel, peca=None, perfil="U 100×40×2,25 (FF)"):
    b = Barra(nome=perfil, inicio=p0, fim=p1, perfil=perfil, papel=papel)
    b.atributos = {"origem": {"peca": peca} if peca else {}}
    return b


def trelica(doc, y, peca):
    """banzos de 0 a 6000 no nível 6000 e 6800, montantes nas pontas e no meio, e uma diagonal
    em cantoneira dupla (duas barras a 16 mm do plano)"""
    doc.add(barra((0.0, y, 6000.0), (6000.0, y, 6000.0), "banzo", peca))
    doc.add(barra((0.0, y, 6800.0), (6000.0, y, 6800.0), "banzo", peca))
    for x in (0.0, 3000.0, 6000.0):
        doc.add(barra((x, y, 6000.0), (x, y, 6800.0), "montante", peca))
    for dy in (-16.0, 16.0):
        doc.add(barra((0.0, y + dy, 6000.0), (3000.0, y + dy, 6800.0), "diagonal", peca, perfil='L 1"×1/8"'))


def modelo():
    doc = Documento()
    for x in (0.0, 6000.0):
        for y in (0.0, 5000.0):
            doc.add(barra((x, y, 0.0), (x, y, 6000.0), "pilar", perfil="W 200×19,3"))
    trelica(doc, 0.0, "T#1")
    trelica(doc, 5000.0, "T#2")
    # terça 90 mm acima do banzo (meia altura dos dois perfis), passando por cima das duas
    doc.add(barra((3000.0, -300.0, 6890.0), (3000.0, 5300.0, 6890.0), "terça"))
    return doc


def test_duplo_vira_uma_barra_e_tudo_se_liga():
    r = analitico.analitico(modelo())
    assert r["resumo"]["duplos_juntados"] == 2               # uma diagonal dupla em cada treliça
    diagonais = [b for b in r["barras"] if b["papel"] == "diagonal"]
    assert len(diagonais) == 2 and all(b["duplo"] and len(b["ids"]) == 2 for b in diagonais)
    # a terça desce até o banzo de cima: nó nas duas treliças, no x 3000 (ela passa dos apoios
    # 30 cm de cada lado: as duas pontinhas ficam soltas, como a terça em balanço do projeto)
    nos = r["nos"]
    tercas = [b for b in r["barras"] if b["papel"] == "terça"]
    zs = {round(nos[b[k]][2]) for b in tercas for k in ("a", "b")}
    assert 6800 in zs
    soltas = {s["papel"] for s in r["soltas"]}
    assert soltas <= {"terça"}, r["soltas"]


def test_ponta_solta_aparece():
    doc = modelo()
    doc.add(barra((10000.0, 0.0, 6000.0), (12000.0, 0.0, 6000.0), "viga"))    # viga no ar
    r = analitico.analitico(doc)
    assert any(s["papel"] == "viga" for s in r["soltas"])
