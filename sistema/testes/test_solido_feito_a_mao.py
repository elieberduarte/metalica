# -*- coding: utf-8 -*-
"""O sólido desenhado à mão no editor 3D (retângulo + empurrar), sem tipo de peça, não entra na lista — mas é avisado
no Detalhar; a cota (só arestas) e a face plana de referência não (revisão das ferramentas, 14/10/2026, D6)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                   # noqa: E402
from nucleo2d import detalhar as det                 # noqa: E402
from test_detalhar2d import _modelo                  # noqa: E402

_V = [(x, y, z) for z in (0.0, 50.0) for (x, y) in ((0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0))]
_F = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]


def test_solido_feito_a_mao_e_avisado_e_a_cota_nao():
    doc = _modelo()
    doc.add(Solido(nome="CALCO", camada="Estrutura", vertices=list(_V), faces=[list(f) for f in _F]))
    doc.add(Solido(nome="441 mm", camada="Referência", vertices=_V[:3], faces=[], atributos={"tipo": "cota"}))
    doc.add(Solido(nome="REFERENCIA", camada="Estrutura", vertices=_V[:4], faces=[[0, 1, 2, 3]]))
    avisos = " ".join(det.levantar(doc)["avisos"])
    assert "CALCO (sólido desenhado à mão" in avisos
    assert "441 mm" not in avisos and "REFERENCIA" not in avisos
