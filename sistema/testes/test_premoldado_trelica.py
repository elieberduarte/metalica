# -*- coding: utf-8 -*-
"""Tesoura de aço pelo desenho (nucleo3d/de_planta_estrutura._trelica): as regras de modelagem do usuário (07/10, Docas).
Só no desenvolvimento, como o resto da Estrutura no CAD (fora do git com o pré-moldado)."""
import math

import pytest

from nucleo2d.desenho import Desenho, Linha
from nucleo3d import de_planta_estrutura as P
from nucleo3d.geometria import base_local

# a T1 do Docas: banzos e pontas em linha dupla (a face de dentro 50 mm para dentro), diagonais em linha simples
BARRAS = [
    [0, 350, 0, 0, "montante"], [50, 329, 50, 50, "montante"],                # ponta baixa: face de fora e de dentro
    [0, 0, 4750, 0, "banzo_inf"], [4700, 50, 50, 50, "diagonal"],             # banzo inferior: as duas faces
    [4750, 1400, 350, 700, "banzo_sup"], [4700, 1341, 374, 653, "diagonal"],  # banzo superior
    [350, 700, 0, 350, "diagonal"], [374, 653, 50, 329, "diagonal"],          # a ponta inclinada (continua o banzo)
    [4750, 0, 4750, 1400, "montante"], [4700, 50, 4700, 1341, "montante"],    # ponta alta
    [902, 0, 449, 716, "diagonal"], [449, 716, 449, 0, "montante"], [1810, 0, 1356, 860, "diagonal"],
]
PERFIS = {"banzo_sup": "U 150×50×3,00 (FF)", "banzo_inf": "U 150×50×3,00 (FF)", "diagonal": 'L 1½"×1/8"'}


def _gerar(cantoneira="simples"):
    des = Desenho(nome="planta")
    des.add(Linha(a=(0.0, 0.0), b=(0.0, 4750.0), camada="ESTRUTURA",
                  atributos={"elemento": "trelica", "material": "aco", "marca": "T1", "perfis": PERFIS, "cantoneira": cantoneira,
                             "nivel_base": 5000, "desenho": {"barras": BARRAS, "vao": 4750, "altura": 1400}}))
    doc, avisos = P.modelo_da_planta(des, [])
    assert not avisos
    return [b for b in doc.entidades.values() if b.tipo == "barra"]


def _boca(b):
    """para onde o U abre (o eixo u da seção girada)"""
    return base_local(b.direcao, b.rotacao)[0]


def test_linha_dupla_e_um_perfil_so_e_a_ponta_inclinada_e_banzo():
    bs = _gerar()
    us = [b for b in bs if b.perfil.startswith("U")]
    ls = [b for b in bs if b.perfil.startswith("L")]
    # 5 perfis em U (banzo inferior, banzo superior em 2 trechos, 2 pontas) e as 3 cantoneiras de dentro; as faces de
    # dentro não viram cantoneira
    assert len(us) == 5 and len(ls) == 3
    papeis = sorted(b.atributos["papel_trelica"] for b in us)
    assert papeis == ["banzo_inf", "banzo_sup", "banzo_sup", "extremidade", "extremidade"]
    # no meio das duas faces: o banzo inferior a 25 mm do apoio
    inf = next(b for b in us if b.atributos["papel_trelica"] == "banzo_inf")
    assert inf.inicio[2] == pytest.approx(5025.0, abs=0.5)


def test_boca_do_u_para_o_miolo():
    bs = _gerar()
    centro = (0.0, 2375.0, 5700.0)
    for b in (b for b in bs if b.perfil.startswith("U")):
        meio = [(b.inicio[i] + b.fim[i]) / 2 for i in range(3)]
        para_dentro = [centro[i] - meio[i] for i in range(3)]
        assert sum(x * y for x, y in zip(_boca(b), para_dentro)) > 0, b.atributos["papel_trelica"]
        assert abs(_boca(b)[0]) < 1e-6                        # a boca no plano da tesoura (x = 0)


def test_cantoneira_do_mesmo_lado_e_dupla_uma_em_cada_aba():
    simples = [b for b in _gerar() if b.perfil.startswith("L")]
    # a aba de pé sempre para o mesmo lado do plano, desenhada num sentido ou no outro (regras_trelica 2.4)
    from nucleo3d import regras_trelica
    assert {regras_trelica.lado_da_aba(b, (1.0, 0.0, 0.0)) for b in simples} == {1}
    dupla = [b for b in _gerar("dupla") if b.perfil.startswith("L") and b.papel != "presilha"]
    assert len(dupla) == 2 * len(simples)
    xs = sorted(round(b.inicio[0], 1) for b in dupla)
    # uma de cada lado, encostadas nas abas do U (75 − 3 − 38,1/2 = 52,95 mm do plano)
    assert xs[0] == pytest.approx(-52.95, abs=0.1) and xs[-1] == pytest.approx(52.95, abs=0.1)
    assert math.isclose(sum(xs), 0.0, abs_tol=0.5)


def _fora_do_contorno(bs, contorno=((0, 0), (4750, 0), (4750, 1400), (350, 700), (0, 350))):
    """quanto (mm) cada barra passa para fora do contorno de fora da tesoura (a linha da planta está no eixo y, em x = 0)"""
    from nucleo3d.geometria import malha_barra
    n = len(contorno)
    pior = []
    for b in bs:
        m = 0.0
        for q in malha_barra(b)[0]:
            u, v = q[1], q[2] - 5000.0
            for i in range(n):
                p1, p2 = contorno[i], contorno[(i + 1) % n]
                ex, ey = p2[0] - p1[0], p2[1] - p1[1]
                m = max(m, (ex * (v - p1[1]) - ey * (u - p1[0])) / math.hypot(ex, ey) * -1.0)
        if m > 0.6:
            pior.append((round(m, 1), b.perfil, b.atributos["papel_trelica"]))
    return pior


@pytest.mark.parametrize("cantoneira", ["simples", "dupla"])
def test_nada_atravessa_o_banzo(cantoneira):
    """o encaixe de fábrica (alma_na_face.encaixar): a cantoneira entra na boca do U e para na alma dele, cortada no
    ângulo — antes a ponta ficava na linha de fora e atravessava o banzo (até 24,5 mm para fora, 08/10)"""
    bs = _gerar(cantoneira)
    assert _fora_do_contorno(bs) == []
    assert all(b.cortes_inicio or b.cortes_fim for b in bs if b.perfil.startswith("L") and b.papel != "presilha")


def test_cantos_dos_u_em_meia_esquadria():
    us = [b for b in _gerar() if b.perfil.startswith("U")]
    # 5 cantos (2 do banzo de baixo com as pontas, a ponta baixa com o trecho inclinado, os dois trechos de cima, a
    # ponta alta com o banzo de cima): 10 pontas cortadas
    assert sum(bool(b.cortes_inicio) + bool(b.cortes_fim) for b in us) == 10


def test_barra_secundaria_de_um_lado_so_por_fora_do_u():
    """"L22x22#11 - Um lado só" (Docas, 08/10): a barra que atravessa a tesoura é uma cantoneira só, por fora da aba do U
    (o U 100: aba a 50 mm do plano; L 22: o centro a 50 + 11), com as pontas cortadas rente à face do banzo — no canto,
    nas duas faces"""
    global BARRAS, PERFIS
    antes, antes_p = BARRAS, PERFIS
    try:
        BARRAS = antes + [[1810, 0, 2180, 466, "secundaria"], [2180, 466, 4300, 700, "secundaria"], [4300, 700, 4750, 0, "secundaria"]]
        PERFIS = dict(antes_p, banzo_sup="U 100×50×3,00 (FF)", banzo_inf="U 100×50×3,00 (FF)", secundaria="L 22×3,00 (FF)")
        bs = _gerar("dupla")
    finally:
        BARRAS, PERFIS = antes, antes_p
    sec = [b for b in bs if b.atributos["papel_trelica"] == "secundaria"]
    assert len(sec) == 3 and all(b.perfil.startswith("L 22") for b in sec)
    assert {round(abs(b.inicio[0]), 1) for b in sec} == {61.0}
    assert _fora_do_contorno(bs) == []
    canto = next(b for b in sec if b.fim[2] == pytest.approx(5000.0, abs=0.5) and b.fim[1] > 4700)
    assert len(canto.cortes_fim) == 2
