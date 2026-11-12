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


def test_viga_deitada_sobre_as_trelicas_ganha_no_em_cada_banzo():
    # a VM do piso da caixa d'água: 125 mm acima do eixo do banzo de cima, apoiada nas treliças
    # das pontas e passando por cima da do meio: ganha nó também no banzo do meio
    doc = modelo()
    trelica(doc, 2500.0, "T#3")
    doc.add(barra((1500.0, -60.0, 6925.0), (1500.0, 5060.0, 6925.0), "viga", perfil="Ue 200×70×20×2,65"))
    r = analitico.analitico(doc)
    nos = r["nos"]
    vigas = [b for b in r["barras"] if b["papel"] == "viga"]
    assert len(vigas) == 2, vigas                            # cortada no banzo do meio
    ys = sorted(round(nos[b[k]][1]) for b in vigas for k in ("a", "b"))
    assert ys == [0, 2500, 2500, 5000]


def test_canto_de_vigas_ao_lado_do_pilar_apoia_nele():
    # o canto do patamar: duas vigas se encontram a 15 cm do eixo de um pilar, na metade da altura
    # dele — as duas juntas não chegam ao chão; o canto vai para o pilar
    doc = modelo()
    doc.add(barra((10000.0, 0.0, 0.0), (10000.0, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((13000.0, 0.0, 0.0), (13000.0, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((10150.0, 0.0, 1500.0), (13000.0, 0.0, 1500.0), "viga"))
    doc.add(barra((10150.0, 0.0, 1500.0), (10150.0, 2000.0, 1500.0), "viga"))
    r = analitico.analitico(doc)
    nos = r["nos"]
    vigas = [b for b in r["barras"] if b["papel"] == "viga"]
    cantos = {tuple(round(c) for c in nos[b[k]]) for b in vigas for k in ("a", "b") if round(nos[b[k]][2]) == 1500}
    assert (10000, 0, 1500) in cantos, cantos
    pilar = [b for b in r["barras"] if b["papel"] == "pilar" and round(nos[b["a"]][0]) == 10000]
    assert len(pilar) == 2                                   # o pilar ganhou o nó do canto


def test_dois_banzos_que_se_encontram_no_eixo_do_espigao_cortam_o_espigao():
    # Residencial Madrid, opção B (10/11): os banzos das duas águas vizinhas terminam juntos em cima do eixo do espigão
    # (o espigão passa exatamente pelo ponto). Os dois "apoiavam" um no outro e o espigão seguia inteiro — o encontro
    # ficava solto e o caibro levava a força de um banzo ao outro
    doc = Documento()
    for x, y in ((0.0, 0.0), (6000.0, 6000.0)):
        doc.add(barra((x, y, 0.0), (x, y, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((0.0, 0.0, 3000.0), (6000.0, 6000.0, 4800.0), "banzo", "E.1", perfil="TR 150×100×2,65"))
    # o ponto do espigão a 1/3: (2000, 2000, 3600); um banzo chega por x, o outro por y
    doc.add(barra((2000.0, -400.0, 3000.0), (2000.0, 2000.0, 3600.0), "banzo", "BS.1", perfil="TR 100×50×2,00"))
    doc.add(barra((-400.0, 2000.0, 3000.0), (2000.0, 2000.0, 3600.0), "banzo", "BS.2", perfil="TR 100×50×2,00"))
    r = analitico.analitico(doc)
    nos = r["nos"]
    enc = [i for i, p in enumerate(nos) if [round(c) for c in p] == [2000, 2000, 3600]]
    assert len(enc) == 1, nos
    esp = [b for b in r["barras"] if b["peca"] == "E.1"]
    assert len(esp) == 2 and any(enc[0] in (b["a"], b["b"]) for b in esp), esp    # o espigão cortado no encontro
    assert r["resumo"]["ponta_no_eixo"] >= 1


def _ligada(r, i):
    """as duas pontas da barra i chegam em nó de outra barra"""
    b = r["barras"][i]
    return all(any(j != i and n in (o["a"], o["b"]) for j, o in enumerate(r["barras"])) for n in (b["a"], b["b"]))


def test_linha_de_travamento_no_banzo_inferior_se_liga_as_tesouras():
    # Cobertura Filipin (12/11): a linha de travamento do banzo inferior (papel "travamento", Barra redonda ø 1/2") com a
    # ponta EM CIMA do eixo do banzo, a 100 mm do nó do montante — o papel não estava em APOIA_EM e o passo 3c pulava a
    # ponta "bem do lado" do nó: as linhas ficavam soltas no ar e a estrutura inteira saía instável (matriz singular)
    doc = modelo()
    for x in (2900.0, 6000.0 - 100.0):
        doc.add(barra((x, 0.0, 6000.0), (x, 5000.0, 6000.0), "travamento", perfil='Barra redonda ø 1/2"'))
    r = analitico.analitico(doc)
    trav = [i for i, b in enumerate(r["barras"]) if b["papel"] == "travamento"]
    assert len(trav) == 2 and all(_ligada(r, i) for i in trav), [r["barras"][i] for i in trav]


def test_ponta_perto_do_eixo_mas_fora_dele_nao_corta_a_peca():
    # a mesma ponta 40 mm fora do eixo (mais que TOL_NA_LINHA): o passo novo não liga nada sozinho — quem decide é o passo 3
    doc = Documento()
    doc.add(barra((0.0, 0.0, 0.0), (0.0, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((6000.0, 0.0, 0.0), (6000.0, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
    doc.add(barra((0.0, 0.0, 3000.0), (6000.0, 0.0, 3000.0), "viga", perfil="W 200×19,3"))
    doc.add(barra((3000.0, 40.0, 3000.0), (3000.0, 3000.0, 3000.0), "viga"))
    doc.add(barra((3000.0, 40.0, 3000.0), (3000.0, 40.0, 4000.0), "viga"))
    r = analitico.analitico(doc)
    assert r["resumo"]["ponta_no_eixo"] == 0


def test_dois_trechos_curtos_seguidos_da_mesma_peca_nao_viram_perfil_duplo():
    # Residencial Madrid (10/11): a cinta partida a 150 mm (no toco e na chapa de apoio) — dois trechos seguidos da mesma peça, os
    # dois com menos de TOL_DUPLO, eram tomados pelo par lado a lado e fundidos na média (os nós saíam do lugar e o apoio caía)
    doc = Documento()
    for x in (0.0, 6000.0):
        doc.add(barra((x, 0.0, 0.0), (x, 0.0, 3000.0), "pilar", perfil="W 200×19,3"))
    for x0, x1 in ((0.0, 2000.0), (2000.0, 2150.0), (2150.0, 2300.0), (2300.0, 6000.0)):
        doc.add(barra((x0, 0.0, 3000.0), (x1, 0.0, 3000.0), "viga", "CI.1"))
    r = analitico.analitico(doc)
    xs = sorted(round(p[0]) for p in r["nos"] if round(p[2]) == 3000)
    assert r["resumo"]["duplos_juntados"] == 0 and xs == [0, 2000, 2150, 2300, 6000], (r["resumo"], xs)


def test_perfil_duplo_lado_a_lado_ainda_vira_uma_barra():
    doc = Documento()
    doc.add(barra((0.0, -16.0, 3000.0), (150.0, -16.0, 3000.0), "diagonal", "T#1", perfil='L 1"×1/8"'))
    doc.add(barra((0.0, 16.0, 3000.0), (150.0, 16.0, 3000.0), "diagonal", "T#1", perfil='L 1"×1/8"'))
    assert analitico.analitico(doc)["resumo"]["duplos_juntados"] == 1
