# -*- coding: utf-8 -*-
"""A conferência do 3D (nucleo3d/conferencia_3d.py, 12/10/2026): as quatro contas que acham no modelo o que o olho
acharia — peças repetidas, pontas soltas, choques e a telha ao lado."""
from nucleo3d.modelo import Barra, Documento, Solido
from nucleo3d import conferencia_3d as C


def _b(doc, a, b, papel="montante", peca="TESOURA 1#1", perfil="U 100×40×2,25 (FF)", sigla=None):
    e = Barra(inicio=a, fim=b, perfil=perfil, papel=papel, camada="Treliças")
    e.atributos = {"origem": {"sigla": sigla} if sigla else {"peca": peca, "planta": peca.split("#")[0]}}
    doc.add(e)
    return e


def test_repetida_pega_as_mesmas_pontas_em_qualquer_sentido():
    doc = Documento()
    _b(doc, (0, 0, 6000), (0, 0, 7000), peca="PAINEL 20#1")
    _b(doc, (0, 0, 7000), (5, 0, 6000), peca="PAINEL 21#2")          # a outra peça, ao contrário, 5 mm ao lado
    _b(doc, (500, 0, 6000), (500, 0, 7000))
    r = C.repetidas(list(doc.barras))
    assert len(r) == 1 and "PAINEL 20" in r[0]["texto"] and "PAINEL 21" in r[0]["texto"]


def test_ponta_solta_mas_nao_a_que_encosta_no_banzo_curvo():
    """a ponta longe de tudo é solta; a que encosta num sólido (o banzo curvo calandrado) e a do chão não"""
    doc = Documento()
    _b(doc, (0, 0, 0), (0, 0, 6000), papel="pilar", peca="P1")
    _b(doc, (0, 0, 6000), (4000, 0, 6000), papel="banzo")
    solta = _b(doc, (8000, 0, 6000), (8000, 0, 7000), papel="montante", peca="PAINEL 8#1")
    curvo = Solido(nome="banzo curvo", camada="Treliças", vertices=[(9000, 0, 7040), (9100, 0, 7040), (9000, 100, 7040)], faces=[[0, 1, 2]])
    doc.add(curvo)
    curvo_m = _b(doc, (9000, 0, 6000), (9000, 0, 7000), papel="montante", peca="PAINEL 9#1")    # encosta no sólido (40 mm)
    r = C.pontas_soltas(list(doc.barras), list(doc.solidos))
    soltas = {(a["ids"][0], tuple(a["ponto"])) for a in r}
    assert (solta.id, (8000, 0, 7000)) in soltas                      # a de cima, longe de tudo
    assert (curvo_m.id, (9000, 0, 7000)) not in soltas                # a que encosta no banzo curvo
    t = Documento()
    _b(t, (0, 0, 6000), (0, 6000, 6000), papel="banzo")
    _b(t, (3000, -1000, 7000), (3000, 5000, 7000), papel="terça", sigla="TC1")
    assert any("TC1 em balanço" in a["texto"] for a in C.pontas_soltas(list(t.barras)))


def test_peca_voando_pega_o_grupo_que_so_encosta_nele_mesmo():
    """GER-03, reincidência de 22/10 (Hangar: a castanha CA1 e a aba dela 5 m acima do banzo, uma encostada na outra —
    as pontas_soltas, barra por barra, não viam): o grupo longe de tudo é peça voando; o grupo preso na estrutura pelo
    meio da barra, o do chão e o que encosta no meio de uma laje (o brise do SESI) não"""
    doc = Documento()
    _b(doc, (0, 0, 0), (0, 0, 5000), papel="pilar", peca="P1")
    _b(doc, (6000, 0, 0), (6000, 0, 5000), papel="pilar", peca="P2")
    _b(doc, (0, 0, 5000), (6000, 0, 5000), papel="banzo")
    # a castanha e a aba, encostadas uma na outra, 5 m acima do banzo
    ca = _b(doc, (3000, 0, 9985), (3150, 0, 9985), papel="castanha", peca="CA1 T1")
    aba = _b(doc, (3150, -25, 9985), (3150, 25, 9985), papel="castanha", peca="CA1 T1")
    # a que está no lugar: embaixo do banzo
    _b(doc, (1000, 0, 4960), (1150, 0, 4960), papel="castanha", peca="CA1 T1")
    _b(doc, (1150, -25, 4960), (1150, 25, 4960), papel="castanha", peca="CA1 T1")
    # a terça apoiada no banzo pelo meio dela (as pontas longe dele)
    _b(doc, (2000, -3000, 5100), (2000, 3000, 5100), papel="terça", sigla="TC1")
    # o brise preso no meio da face de uma laje (longe dos vértices dela)
    laje = Solido(nome="laje", camada="ARQ — Lajes", vertices=[(x, y, z) for z in (8000, 8200) for x, y in
                                                               ((20000, 0), (40000, 0), (40000, 20000), (20000, 20000))],
                  faces=[[0, 1, 2, 3], [4, 5, 6, 7]])
    doc.add(laje)
    _b(doc, (30000, 10000, 7900), (30000, 10000, 7000), papel="barra", peca="ARB1")
    r = C.pecas_voando(list(doc.barras), list(doc.solidos), list(doc.chapas))
    assert len(r) == 1 and set(r[0]["ids"]) == {ca.id, aba.id}
    assert "voando" in r[0]["texto"]
    conf = C.conferir(doc, telha=False, posicao=False, cobertura_=False)
    assert conf["contagens"]["pecas_voando"] == 1 and conf["apontamentos"][0]["tipo"] == "peca_voando"
    assert "1 peça(s) voando" in C.avisos(conf)[0]


def test_choque_entre_pecas_mas_nao_o_cruzamento_normal():
    doc = Documento()
    _b(doc, (0, 0, 7000), (0, 6000, 7000), papel="terça", sigla="TC14")
    _b(doc, (-500, 3000, 6500), (500, 3000, 7500), papel="diagonal", peca="PAINEL 11#1")    # a terça passa por dentro
    _b(doc, (-1000, 1000, 7000), (1000, 2000, 7000), papel="contraventamento", peca="CV")   # o contravento cruza: normal
    _b(doc, (-1000, 5000, 7000), (1000, 5000, 7000), papel="pilar", peca="P2")             # no pilar é o nó
    r = C.choques(list(doc.barras))
    assert len(r) == 1 and "TC14" in r[0]["texto"] and "PAINEL 11" in r[0]["texto"]


def test_telha_ao_lado_e_os_avisos():
    """a água reta não aponta; a terça 80 mm acima no meio aponta a dobra, e o aviso traz o ponto no desenho"""
    doc = Documento()
    for i in range(5):
        _b(doc, (i * 1400.0, 0, 7000 + i * 70.0 + (80.0 if i == 2 else 0.0)), (i * 1400.0, 6000, 7000 + i * 70.0 + (80.0 if i == 2 else 0.0)),
           papel="terça", sigla="TC1")
    conf = C.conferir(doc)
    assert conf["contagens"]["telha_dobras"] >= 1 and conf["contagens"]["telha_acima_de_5cm"] >= 1
    av = C.avisos(conf, desl=(1000.0, 0.0))
    assert av[0].startswith("Conferência do 3D:")
    assert any("dobra de 80 mm" in a and "(1800;" in a for a in av)              # 2800 no modelo − 1000 de deslocamento


def test_verificar_apoios_traz_as_regras_da_conferencia():
    """a tela Estrutura › Verificar apoios mostra a peça repetida e o choque (as pontas soltas ficam com as regras dela)"""
    from nucleo3d import apoios
    doc = Documento()
    _b(doc, (0, 0, 0), (0, 0, 6000), papel="pilar", peca="P1")
    _b(doc, (0, 0, 6000), (6000, 0, 6000), papel="banzo", peca="TESOURA 1#1")
    _b(doc, (0, 0, 6000), (6000, 0, 6000), papel="banzo", peca="TESOURA 2#2")
    r = apoios.verificar(doc)
    assert r["resumo"]["por_regra"].get("repetida") == 1
    assert all(a["ids"] for a in r["achados"] if a["regra"] == "repetida")
