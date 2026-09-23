# -*- coding: utf-8 -*-
"""0.7.16: furo fechado some da malha sem deixar ponta nem face degenerada."""
from nucleo3d.modelo import Solido
from nucleo2d.detalhe.celulas import _limpar_faces


def test_furo_fechado_sai_do_poligono():
    # quadrado 100×100 com um "furo" já fechado: a ponte vai do canto (0,0) ao centro e
    # volta, e o anel do furo (três pontos) está todo no centro
    P = [(0, 0, 0), (100, 0, 0), (100, 100, 0), (0, 100, 0), (50, 50, 0), (50, 50, 0), (50, 50, 0), (0, 0, 0)]
    s = Solido(id="x", nome="t", vertices=P, faces=[[0, 4, 5, 6, 7, 1, 2, 3], [4, 5, 6]])
    assert _limpar_faces(s) == 2
    assert s.faces == [[7, 1, 2, 3]] or s.faces == [[0, 1, 2, 3]]
    assert _limpar_faces(s) == 0
