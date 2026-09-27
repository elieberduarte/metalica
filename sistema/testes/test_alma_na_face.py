# -*- coding: utf-8 -*-
"""A alma da treliça para na face interna do banzo (nucleo3d/alma_na_face.py): o nó continua no
eixo, a peça termina antes (recorte), com a quina fora do banzo e folga."""
import math

import pytest

from nucleo3d import alma_na_face as A
from nucleo3d.geometria import malha_barra
from nucleo3d.modelo import Barra, Solido

BANZO = "U 100×40×2,25 (FF)"
ALMA = 'L 1"×1/8"'


def _b(p0, p1, perfil, papel, rot=0.0, peca="TESOURA 1#0"):
    b = Barra(nome=perfil, inicio=p0, fim=p1, perfil=perfil, rotacao=rot, papel=papel)
    b.atributos = {"origem": {"peca": peca}}
    return b


def _trelica(peca="TESOURA 1#0"):
    """banzos de 6 m a 0 e 1500 (o de baixo com as abas para cima, o de cima para baixo), uma
    diagonal e um montante no plano y = 0"""
    baixo = _b((0.0, 0.0, 0.0), (6000.0, 0.0, 0.0), BANZO, "banzo", 90.0, peca)
    cima = _b((0.0, 0.0, 1500.0), (6000.0, 0.0, 1500.0), BANZO, "banzo", 270.0, peca)
    diag = _b((1000.0, 0.0, 0.0), (2500.0, 0.0, 1500.0), ALMA, "diagonal", 0.0, peca)
    mont = _b((4000.0, 0.0, 0.0), (4000.0, 0.0, 1500.0), ALMA, "montante", 0.0, peca)
    return baixo, cima, diag, mont


def _min_z_da_ponta(b):
    v, _f = malha_barra(b)
    return min(q[2] for q in v), max(q[2] for q in v)


def test_diagonal_e_montante_param_na_face_com_folga():
    baixo, cima, diag, mont = _trelica()
    r = A.aparar([baixo, cima, diag, mont])
    assert r == {"pontas": 4, "barras": 2}
    # o nó continua no eixo
    assert diag.inicio == (1000.0, 0.0, 0.0) and diag.fim == (2500.0, 0.0, 1500.0)
    # a peça (a malha) fica entre as faces internas dos banzos, com a folga
    face_baixo = max(q[2] for q in malha_barra(baixo)[0])
    face_cima = min(q[2] for q in malha_barra(cima)[0])
    for b in (diag, mont):
        zmin, zmax = _min_z_da_ponta(b)
        assert zmin >= face_baixo + A.FOLGA - 0.5 and zmax <= face_cima - A.FOLGA + 0.5
        assert zmin <= face_baixo + A.FOLGA + 25.0            # e não recua além do preciso
    # o montante reto: o recorte é a face mais a folga, mais nada
    assert mont.recorte_fim == pytest.approx(1500.0 - face_cima + A.FOLGA, abs=0.5)


def test_so_o_banzo_do_proprio_bloco():
    baixo, cima, diag, mont = _trelica()
    outro = _trelica("TESOURA 2#1")
    A.aparar([baixo, cima, outro[2], outro[3]])
    assert outro[2].recorte_inicio == outro[2].recorte_fim == 0.0


def test_a_tesoura_de_cima_apoia_no_banzo_da_viga_de_transicao():
    baixo, cima, _d, _m = _trelica("TRANSICAO 2#5")
    mont = _b((3000.0, 0.0, 1500.0), (3000.0, 0.0, 2500.0), ALMA, "montante", 0.0, "TRANSICAO 2 (tesoura de cima)#5")
    A.aparar([baixo, cima, mont])
    assert mont.recorte_inicio > 0.0


def test_a_alma_que_sai_pela_ponta_do_toco_nao_e_recortada_por_ele():
    """o toco de apoio (banzo curto na ponta) termina onde a diagonal começa: ela desce para
    longe dele — não conta"""
    toco = _b((-400.0, 0.0, 1300.0), (0.0, 0.0, 1300.0), BANZO, "banzo", 270.0)
    diag = _b((0.0, 0.0, 1440.0), (1300.0, 0.0, 0.0), ALMA, "diagonal")
    assert A.recorte_da_ponta(diag, 0, [toco]) == 0.0


def test_banzo_calandrado_pelo_eixo_guardado():
    pts = [(5000.0 * math.cos(a), 5000.0 * math.sin(a), 1500.0) for a in [i * math.pi / 40 for i in range(11)]]
    sol = Solido(nome=BANZO, vertices=[(0.0, 0.0, 0.0)], faces=[])
    sol.atributos = {"origem": {"peca": "PAINEL 1#0"}, "banzo": {"perfil": BANZO, "rotacao": 270.0, "eixo": [list(p) for p in pts]}}
    x, y = pts[3][0], pts[3][1]
    mont = _b((x, y, 0.0), (x, y, 1500.0), ALMA, "montante", 0.0, "PAINEL 1#0")
    A.aparar([sol, mont])
    assert mont.recorte_fim > A.FOLGA and mont.recorte_inicio == 0.0
