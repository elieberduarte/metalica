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


def test_canto_de_vigas_no_ar_nao_se_apoiam():
    """duas vigas que se encontram em L longe do pilar: uma não segura a outra (o canto do
    mezanino do Posto CB); a viga que apoia no meio de outra continua apoiada"""
    doc = Documento()
    for x, y in ((0.0, 0.0), (6000.0, 6000.0), (0.0, 6000.0)):
        doc.add(barra((x, y, 0.0), (x, y, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((0.0, 0.0, 3000.0), (6000.0, 0.0, 3000.0), "viga", perfil="W 250×25,3"))   # canto em (6000, 0)
    doc.add(barra((6000.0, 0.0, 3000.0), (6000.0, 6000.0, 3000.0), "viga", perfil="W 250×25,3"))
    doc.add(barra((0.0, 6000.0, 3000.0), (6000.0, 6000.0, 3000.0), "viga", perfil="W 250×25,3"))
    doc.add(barra((3000.0, 6000.0, 3000.0), (3000.0, 9000.0, 3000.0), "viga", perfil="W 150×13"))  # no meio da outra
    doc.add(barra((3000.0, 9000.0, 0.0), (3000.0, 9000.0, 3000.0), "pilar", perfil="W 200×19,3"))
    soltas = [a["ponto"][:2] for a in apoios.verificar(doc)["achados"] if a["regra"] == "viga_sem_apoio"]
    assert sorted(soltas) == [[6000, 0], [6000, 0]]


def test_viga_partida_no_cruzamento_segura_a_que_chega():
    """a linha da viga interrompida onde a outra chega (o desenho corta a linha dupla) continua
    sendo viga contínua: a que chega em T fica apoiada"""
    doc = Documento()
    for y in (0.0, 8000.0):
        doc.add(barra((0.0, y, 0.0), (0.0, y, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((0.0, 0.0, 3000.0), (0.0, 3930.0, 3000.0), "viga", perfil="W 250×25,3"))
    doc.add(barra((0.0, 4070.0, 3000.0), (0.0, 8000.0, 3000.0), "viga", perfil="W 250×25,3"))
    doc.add(barra((5000.0, 4000.0, 0.0), (5000.0, 4000.0, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((5000.0, 4000.0, 3000.0), (70.0, 4000.0, 3000.0), "viga", perfil="W 150×13"))
    assert not [a for a in apoios.verificar(doc)["achados"] if a["regra"] == "viga_sem_apoio"]


def test_ponta_de_trelica_ligada_em_diagonal():
    """a ponta que chega no meio de uma diagonal de outra treliça (não num nó do banzo) é
    apontada; a que chega num montante (um nó) não. A treliça de apoio é mais alta (2 m), e
    a que chega tem os banzos no meio dela: só a diagonal fica ao alcance da ponta"""
    def cena(x_ponta):
        doc = Documento()
        for x in (0.0, 6000.0):
            doc.add(barra((x, 0.0, 0.0), (x, 0.0, 6000.0), "pilar", perfil="W 200×19,3"))
        trelica(doc, 0.0, 0.0, 6000.0, "T#1", h=2000.0)                 # montantes em x = 0, 1000, …
        doc.add(barra((0.0, 0.0, 6000.0), (1000.0, 0.0, 8000.0), "diagonal", "T#1"))   # passa por (500, 0, 7000)
        for z in (6800.0, 7200.0):
            doc.add(barra((x_ponta, -3000.0, z), (x_ponta, 0.0, z), "banzo", "T#9"))
        for y in (-3000.0, 0.0):
            doc.add(barra((x_ponta, y, 6800.0), (x_ponta, y, 7200.0), "montante", "T#9"))
        doc.add(barra((x_ponta, -3000.0, 0.0), (x_ponta, -3000.0, 6800.0), "pilar", perfil="W 200×19,3"))
        return doc
    r = apoios.verificar(cena(500.0))
    em_diag = [a for a in r["achados"] if a["regra"] == "ponta_em_diagonal"]
    # o nome exibido é o da treliça de origem sem o "#n" ("T#9" → "T")
    assert len(em_diag) == 1 and em_diag[0]["peca"] == "T" and 400 <= em_diag[0]["dist_mm"] <= 600, r["achados"]
    r2 = apoios.verificar(cena(1000.0))                                # no montante de x = 1000: um nó
    assert not [a for a in r2["achados"] if a["regra"] in ("ponta_em_diagonal", "ponta_sem_apoio") and a["peca"] == "T#9"], r2["achados"]
