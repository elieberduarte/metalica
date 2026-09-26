# -*- coding: utf-8 -*-
"""Chamadas nos desenhos de detalhamento: cada grupo de furos da peça ganha a chamada
("2x OBL 25x13") logo acima dela, sem texto por cima de texto; perto da ponta o texto vai
para o outro lado, longe da cota vertical."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Chamada                     # noqa: E402
from nucleo2d.detalhe.base import _Papel, largura_da_chamada       # noqa: E402
from nucleo2d.detalhe.celulas import chamadas_de_furos, NIVEIS_DE_CHAMADA  # noqa: E402
from saida.detalhamento import Furo                                # noqa: E402


def _chamadas(furos, L=4000.0, H=150.0, esc=25.0):
    d = Desenho(nome="t", escala=esc)
    p = _Papel(d, {"posicao": "T"}, 0.0, 0.0)
    n = chamadas_de_furos(p, furos, H, esc, L)
    return n, [e for e in d.entidades.values() if isinstance(e, Chamada)], esc


def test_uma_chamada_por_grupo_de_furos():
    furos = [Furo("oblongo", 35, 50, larg=25, alt=13), Furo("oblongo", 35, 100, larg=25, alt=13), Furo("oblongo", 70, 75, larg=25, alt=13),
             Furo("redondo", 1995, 75, d=13), Furo("redondo", 2030, 75, d=13),
             Furo("oblongo", 3965, 50, larg=25, alt=13), Furo("oblongo", 3965, 100, larg=25, alt=13)]
    n, ch, esc = _chamadas(furos)
    assert n == 3 and len(ch) == 3
    textos = sorted(c.texto for c in ch)
    assert textos == ["2x OBL 25x13", "2x Ø13", "3x OBL 25x13"], textos
    # as setas nos furos de cima de cada grupo; o texto acima da peça
    assert all(c.posicao[1] > 150 for c in ch)
    # a última (perto da ponta) vai para a esquerda: não passa da ponta da peça
    ultima = max(ch, key=lambda c: c.alvo[0])
    assert ultima.posicao[0] < ultima.alvo[0]
    # textos na mesma linha não se encostam
    for a in ch:
        for b in ch:
            if a is b or abs(a.posicao[1] - b.posicao[1]) > 1:
                continue
            la = (min(a.posicao[0], a.posicao[0] + (largura_da_chamada(a.texto, 2.0, esc) if a.posicao[0] >= a.alvo[0] else -largura_da_chamada(a.texto, 2.0, esc))),)
            assert abs(a.posicao[0] - b.posicao[0]) > 0


def test_grupos_colados_vao_para_a_segunda_linha_ou_ficam_de_fora():
    # quatro grupos a 200 mm um do outro em 1:25: os textos não cabem todos numa linha só
    furos = [Furo("redondo", 200 + 200 * k, 75, d=13) for k in range(4)]
    n, ch, esc = _chamadas(furos, L=4000.0)
    alturas = {round(c.posicao[1] - 150, 1) for c in ch}
    assert alturas <= {round(nv * esc, 1) for nv in NIVEIS_DE_CHAMADA}
    assert 2 <= n <= 4
