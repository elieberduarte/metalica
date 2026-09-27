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


def test_ponta_da_trelica_desce_ate_o_pilar():
    # a treliça começa 80 mm ao lado do topo do pilar (mais que a tolerância de nó), e o topo já
    # tem a viga que chega nele: a ponta do banzo, que só tem o montante da própria treliça, vai
    # até o pilar levando o montante junto
    doc = Documento()
    for x in (0.0, 6000.0):
        for y in (0.0, 5000.0):
            doc.add(barra((x, y, 0.0), (x, y, 6000.0), "pilar", perfil="W 200×19,3"))
        doc.add(barra((x, 0.0, 6000.0), (x, 5000.0, 6000.0), "viga"))
    doc.add(barra((80.0, 0.0, 6000.0), (5920.0, 0.0, 6000.0), "banzo", "T#1"))
    doc.add(barra((80.0, 0.0, 6800.0), (5920.0, 0.0, 6800.0), "banzo", "T#1"))
    for x in (80.0, 5920.0):
        doc.add(barra((x, 0.0, 6000.0), (x, 0.0, 6800.0), "montante", "T#1"))
    r = analitico.analitico(doc)
    topos = {i for i, p in enumerate(r["nos"]) if p[2] == 6000.0 and p[0] in (0.0, 6000.0) and p[1] == 0.0}
    ligados = {b[k] for b in r["barras"] if b["peca"] == "T#1" for k in ("a", "b")}
    assert topos and topos <= ligados, (topos, r["nos"])


def test_terca_com_corrente_na_ponta_ainda_desce_ao_banzo():
    doc = modelo()
    # a terça termina a 15 cm da treliça e a corrente está presa na ponta dela
    doc.add(barra((1500.0, 150.0, 6890.0), (1500.0, 4850.0, 6890.0), "terça"))
    doc.add(barra((1500.0, 150.0, 6890.0), (3000.0, 150.0, 6890.0), "corrente", perfil="Barra redonda 10"))
    r = analitico.analitico(doc)
    nos = r["nos"]
    t = [b for b in r["barras"] if b["papel"] == "terça" and nos[b["a"]][0] == 1500.0]
    ys = sorted(nos[b[k]][1] for b in t for k in ("a", "b"))
    assert ys[0] == 0.0 and ys[-1] == 5000.0                 # das duas pontas até os banzos
    assert not any(s["papel"] == "corrente" for s in r["soltas"])


def test_alma_corta_o_banzo_continuo_da_propria_trelica():
    # a treliça do modelo tem os banzos numa barra só, de 0 a 6000, e o montante do meio em 3000:
    # o banzo ganha o nó do montante (senão a alma fica presa só nas pontas)
    r = analitico.analitico(modelo())
    assert r["resumo"]["alma_no_banzo"] >= 2
    nos = r["nos"]
    meio = [i for i, p in enumerate(nos) if p[0] == 3000.0 and p[1] == 0.0 and p[2] in (6000.0, 6800.0)]
    banzos = [b for b in r["barras"] if b["papel"] == "banzo" and b["peca"] == "T#1"]
    assert meio and all(any(n in (b["a"], b["b"]) for b in banzos) for n in meio)
