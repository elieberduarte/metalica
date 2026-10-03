# -*- coding: utf-8 -*-
"""A variante de furação de uma chapa ("P48 (b)", 01/10) é a mesma peça no lugar: as instâncias do conjunto se
reconhecem pela posição de base (conferência da 0.8.56, 03/10: as 120 M19 do ÁGUA GELADA, 8 delas com uma P48 de
furo redondo, viravam 8 montagens de 15 barras — e "tesoura" no resumo da obra)."""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido  # noqa: E402
from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto, _multiplo, posicao_base  # noqa: E402


def _peca(pos, x):
    vs = [(x, 0.0, 0.0), (x + 50.0, 0.0, 0.0), (x + 50.0, 50.0, 0.0), (x, 50.0, 0.0)]
    return Solido(nome=pos, vertices=vs, faces=[[0, 1, 2, 3]],
                  atributos={"marcas": {"posicao": pos, "conjunto": "M19"}})


def test_posicao_base_tira_so_a_letra_da_variante():
    assert posicao_base(_peca("P48 (b)", 0)) == "P48"
    assert posicao_base(_peca("P48 (c)", 0)) == "P48"
    assert posicao_base(_peca("P48", 0)) == "P48"
    assert posicao_base(_peca("CANTONEIRA (A)", 0)) == "CANTONEIRA (A)"


def test_instancia_com_a_variante_e_instancia_do_conjunto():
    # 3 montagens (cantoneira + 2 chapas), afastadas; a do meio com uma chapa de furo redondo
    pecas = []
    for i, (a, b) in enumerate((("P48", "P48"), ("P48", "P48 (b)"), ("P48", "P48"))):
        x = i * 1000.0
        pecas += [_peca("B18", x + 40.0), _peca(a, x), _peca(b, x + 80.0)]
    unidade = collections.Counter({"B18": 1, "P48": 2})
    grupos = _instancias_do_conjunto(pecas, unidade)
    assert len(grupos) == 3
    assert all(_multiplo(g, unidade) == 1 for g in grupos)
