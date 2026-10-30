# -*- coding: utf-8 -*-
"""A peça solta sai na planta de montagem com a marca dela, não com o M#### (Hora Certa · Galpão Existente, 29/10,
montador M07: 239 rótulos M#### na folha 1 — M609, M1104… — que não existem em folha nenhuma; a peça chega como T.O.3).

O numerar dá à peça fora de conjunto um conjunto "solo" próprio (M####, diferente da posição P####); a localização o
tratava como conjunto e escrevia a marca crua.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from nucleo3d import geometria as geo  # noqa: E402
from nucleo2d.detalhe.conjuntos import _itens_de_localizacao  # noqa: E402


def _peca(x, posicao, conjunto, instancia=None):
    s = geo.prisma([(x, 0, 0), (x + 100, 0, 0), (x + 100, 100, 0), (x, 100, 0)], (0, 0, 3000), nome=posicao,
                   camada="Peças", material="Aço")
    m = {"posicao": posicao, "conjunto": conjunto}
    if instancia:
        m["instancia"] = instancia
    s.atributos = {"tipo_ifc": "IfcMember", "marcas": m}
    return s


def test_peca_solta_com_conjunto_solo_leva_a_marca_dela():
    pecas = [_peca(0, "P12", "M609"), _peca(5000, "P12", "M609"), _peca(10000, "P40", "M1104")]
    rotulos = sorted(r for r, _ in _itens_de_localizacao(pecas))
    assert rotulos == ["P12", "P12", "P40"]


def test_conjunto_de_verdade_continua_conjunto():
    pecas = [_peca(0, "P1", "M2"), _peca(100, "P3", "M2"), _peca(9000, "P1", "M2"), _peca(9100, "P3", "M2")]
    itens = _itens_de_localizacao(pecas)
    assert [r for r, _ in itens] == ["M2", "M2"] and all(len(g) == 2 for _, g in itens)
