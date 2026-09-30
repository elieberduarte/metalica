# -*- coding: utf-8 -*-
"""O encaixe de fábrica da alma no banzo (nucleo3d/alma_na_face.encaixar) e o corte no ângulo da
barra (`cortes_inicio`/`cortes_fim`, nucleo3d/geometria): a ponta deita na face do banzo que
passa na faixa dela, a diagonal ganha o bico encostado no montante do mesmo nó e duas diagonais
sem montante se cortam na bissetriz. Pedido de 30/09 (portaria Hermes): "os recortes precisariam
seguir como vai ser feito na indústria... parece que eles não têm física, um entra dentro do outro"."""
import math
from collections import Counter

import pytest

from nucleo3d import alma_na_face as A
from nucleo3d import geometria as G
from nucleo3d.modelo import Barra, Documento

BANZO = "U 100×40×2,25 (FF)"
ALMA_L = 'L 1"×1/8"'


def _b(p0, p1, perfil, papel, rot=0.0, peca="TESOURA 1#0"):
    b = Barra(nome=perfil, inicio=p0, fim=p1, perfil=perfil, rotacao=rot, papel=papel)
    b.atributos = {"origem": {"peca": peca}}
    return b


def _fechada(v, f) -> bool:
    c = Counter()
    for face in f:
        for i in range(len(face)):
            c[(face[i], face[(i + 1) % len(face)])] += 1
    return all(c.get((b, a), 0) == n for (a, b), n in c.items())


def _faces_do_banzo(banzo):
    """(z da ponta das abas, z da alma por dentro) do banzo de baixo (abas para cima)"""
    v, _f = G.malha_barra(banzo)
    topo = max(q[2] for q in v)
    # a alma do U por dentro: o fundo mais a espessura
    return topo, min(q[2] for q in v) + 2.25


# ------------------------------------------------------------------ a barra cortada

def test_meia_esquadria_fecha_e_tem_o_volume_da_barra():
    reta = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO)
    corte = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO,
                  cortes_inicio=[{"normal": [0, 0, 1], "ponto": [0, 0, 0]}],
                  cortes_fim=[{"normal": [0, 0, -1], "ponto": [0, 0, 0]}])
    v, f = G.malha_barra(corte)
    assert _fechada(v, f)
    assert min(q[2] for q in v) == pytest.approx(0.0, abs=1e-6)          # deitada no plano
    assert max(q[2] for q in v) == pytest.approx(1000.0, abs=1e-6)
    # a meia-esquadria pelo nó não muda o volume (a seção inteira gira em torno do centroide)
    assert G.volume_malha(v, f) == pytest.approx(G.volume_malha(*G.malha_barra(reta)), rel=1e-6)
    medio, de_corte = G.comprimentos_da_barra(corte)
    assert medio == pytest.approx(1000 * math.sqrt(2), abs=0.5)
    assert de_corte > medio                                               # a ponta comprida
    assert G.peso_barra(corte) == pytest.approx(G.peso_barra(reta), rel=1e-6)


def test_bico_com_dois_planos_fecha_e_respeita_os_dois():
    b = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO,
              cortes_inicio=[{"normal": [0, 0, 1], "ponto": [0, 0, 0]},
                             {"normal": [1, 0, 0], "ponto": [30, 0, 0]}])
    v, f = G.malha_barra(b)
    assert _fechada(v, f)
    assert min(q[0] for q in v) >= 30.0 - 1e-6 and min(q[2] for q in v) >= -1e-6
    # o volume pela malha e pela integral das pontas são o mesmo
    area = sum(G.area_contorno(p) for p, _f in G._tampas(*G._normalizar_contorno(G.secao_com_furos(BANZO)),
                                                           *G.alturas_de_corte(b))[1])
    assert G.volume_malha(v, f) == pytest.approx(G.comprimentos_da_barra(b)[0] * area, rel=1e-6)


def test_corte_que_come_a_peca_volta_para_a_ponta_reta():
    b = Barra(inicio=(0, 0, 0), fim=(0, 0, 100), perfil=BANZO,
              cortes_inicio=[{"normal": [0.3, 0, 1], "ponto": [0, 0, 400]}])
    v, _f = G.malha_barra(b)
    assert min(q[2] for q in v) == pytest.approx(0.0, abs=1e-6)          # ignorou o corte


def test_girar_leva_o_corte_junto():
    b = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO,
              cortes_inicio=[{"normal": [0, 0, 1], "ponto": [0, 0, 0]}])
    g = G.girar(b, (0, 0, 1), (0, 0, 0), 90.0)
    v0, f0 = G.malha_barra(b)
    v1, f1 = G.malha_barra(g)
    assert G.volume_malha(v1, f1) == pytest.approx(G.volume_malha(v0, f0), rel=1e-6)
    assert min(q[2] for q in v1) == pytest.approx(0.0, abs=1e-6)


def test_ifc_grava_o_corte_como_meio_espaco():
    from ifc.exportar import para_texto
    doc = Documento(nome="t")
    b = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO, papel="barra",
              cortes_inicio=[{"normal": [0, 0, 1], "ponto": [0, 0, 0]}])
    doc.entidades[b.id] = b
    txt = para_texto(doc)
    assert "IFCBOOLEANCLIPPINGRESULT(.DIFFERENCE." in txt and "IFCHALFSPACESOLID(" in txt
    assert "'Clipping'" in txt


def test_modelo_guarda_os_cortes():
    doc = Documento(nome="t")
    b = Barra(inicio=(0, 0, 0), fim=(1000, 0, 1000), perfil=BANZO,
              cortes_fim=[{"normal": [0, 0, -1], "ponto": [0, 0, 0]}])
    doc.entidades[b.id] = b
    de_volta = Documento.de_dict(doc.dict()).entidades[b.id]
    assert de_volta.cortes_fim == b.cortes_fim and de_volta.cortes_inicio == []


# ------------------------------------------------------------------ o encaixe na treliça

def _l_dupla(p0, p1, papel, peca="TESOURA 1#0"):
    """a alma de duas L 1" soldadas nas paredes do U (uma de cada lado, dentro da boca)"""
    res = []
    for lado in (1.0, -1.0):
        melhor = None
        for rot in (0.0, 90.0, 180.0, 270.0):
            v, _f = G.malha_barra(Barra(inicio=(p0[0], 0.0, p0[2]), fim=(p1[0], 0.0, p1[2]), perfil=ALMA_L,
                                        rotacao=rot))
            hi = max(lado * q[1] for q in v)
            if melhor is None or hi < melhor[0]:
                melhor = (hi, rot)
        hi, rot = melhor
        y = lado * (50.0 - 2.25) - lado * hi                               # a aba em pé na parede
        res.append(_b((p0[0], y, p0[2]), (p1[0], y, p1[2]), ALMA_L, papel, rot, peca))
    return res


def _trelica():
    baixo = _b((0.0, 0.0, 0.0), (6000.0, 0.0, 0.0), BANZO, "banzo", 90.0)
    cima = _b((0.0, 0.0, 1500.0), (6000.0, 0.0, 1500.0), BANZO, "banzo", 270.0)
    return baixo, cima


def test_l_dupla_entra_na_boca_do_u_e_deita_na_alma_dele():
    baixo, cima = _trelica()
    diag = _l_dupla((1000.0, 0.0, 0.0), (2500.0, 0.0, 1500.0), "diagonal")
    r = A.encaixar([baixo, cima] + diag)
    assert r["pontas"] == 4 and r["barras"] == 2
    topo_abas, alma_dentro = _faces_do_banzo(baixo)
    assert alma_dentro < topo_abas - 20.0
    for d in diag:
        assert d.recorte_inicio == d.recorte_fim == 0.0 and d.cortes_inicio and d.cortes_fim
        assert d.inicio == (1000.0, d.inicio[1], 0.0)                     # o nó continua no eixo
        v, f = G.malha_barra(d)
        assert _fechada(v, f)
        # a ponta desce na boca do U até a alma dele por dentro (a curva da dobra segura um pouco
        # acima): passa da ponta das abas, é a solda na parede
        assert alma_dentro - 0.1 <= min(q[2] for q in v) <= alma_dentro + 2.5


def test_alma_larga_para_na_ponta_das_abas_e_o_bico_encosta_no_montante():
    baixo, cima = _trelica()
    # montante e diagonal de U 100×40 com os 100 fora do plano (a largura toda do banzo),
    # saindo do mesmo nó
    mont = _b((3000.0, 0.0, 0.0), (3000.0, 0.0, 1500.0), BANZO, "montante", 90.0)
    diag = _b((3000.0, 0.0, 0.0), (4500.0, 0.0, 1500.0), BANZO, "diagonal", 90.0)
    r = A.encaixar([baixo, cima, mont, diag])
    assert r["bicos"] >= 1
    topo_abas, _alma = _faces_do_banzo(baixo)
    vm, _ = G.malha_barra(mont)
    vd, fd = G.malha_barra(diag)
    assert _fechada(vd, fd)
    assert min(q[2] for q in vm) == pytest.approx(topo_abas, abs=0.6)    # o montante deita nas abas
    assert min(q[2] for q in vd) >= topo_abas - 0.6                       # a diagonal não entra no banzo
    face_mont = max(q[0] for q in vm)
    # e não entra no montante: perto do banzo, todo ponto da diagonal fica do lado de fora dele
    perto = [q for q in vd if q[2] < 300.0]
    assert perto and min(q[0] for q in perto) >= face_mont - 0.6
    assert min(q[0] for q in perto) == pytest.approx(face_mont, abs=0.6)  # encostada


def test_duas_diagonais_sem_montante_se_cortam_na_bissetriz():
    baixo, cima = _trelica()
    d1 = _b((3000.0, 0.0, 0.0), (1500.0, 0.0, 1500.0), BANZO, "diagonal", 90.0)
    d2 = _b((3000.0, 0.0, 0.0), (4500.0, 0.0, 1500.0), BANZO, "diagonal", 90.0)
    r = A.encaixar([baixo, cima, d1, d2])
    assert r["bissetrizes"] == 2
    v1, _ = G.malha_barra(d1)
    v2, _ = G.malha_barra(d2)
    assert max(q[0] for q in v1 if q[2] < 300.0) <= 3000.0 + 0.6
    assert min(q[0] for q in v2 if q[2] < 300.0) >= 3000.0 - 0.6


def test_encaixe_so_no_proprio_bloco():
    baixo, cima = _trelica()
    diag = _b((1000.0, 0.0, 0.0), (2500.0, 0.0, 1500.0), BANZO, "diagonal", 0.0, peca="TESOURA 2#1")
    A.encaixar([baixo, cima, diag])
    assert not diag.cortes_inicio and not diag.cortes_fim
