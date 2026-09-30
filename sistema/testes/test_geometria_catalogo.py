# -*- coding: utf-8 -*-
"""A malha do 3D para perfis que só o catálogo completo conhece (tubos TQ/TR dos fornecedores, cantoneira dobrada
de abas desiguais). Antes a geometria recusava o nome ("fora do catálogo") e o editor caía no desenho dele, que faz
todo tubo redondo; e a cantoneira L 100×50 saía com as duas abas de 100 (portaria, 30/09/2026)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d import geometria  # noqa: E402
from nucleo3d.modelo import Barra  # noqa: E402


def _caixa(perfil):
    v, _f = geometria.malha_barra(Barra(inicio=(0.0, 0.0, 0.0), fim=(1000.0, 0.0, 0.0), perfil=perfil))
    ys = [p[1] for p in v]
    zs = [p[2] for p in v]
    return round(max(ys) - min(ys), 1), round(max(zs) - min(zs), 1), len(v)


def test_tubo_quadrado_e_retangular_do_catalogo():
    assert _caixa("TQ 40×40×1,5")[:2] == (40.0, 40.0)
    assert _caixa("TQ 100×100×2,0")[:2] == (100.0, 100.0)
    larg, alt, _n = _caixa("TR 100×50×1,5")
    assert sorted((larg, alt)) == [50.0, 100.0]
    assert geometria._dims(geometria.resolver_perfil("TQ 40×40×1,5"))["forma"] == "tubo_retangular"


def test_cantoneira_de_abas_desiguais():
    larg, alt, _n = _caixa("L 100×50×3,75 (FF)")
    assert sorted((larg, alt)) == [50.0, 100.0]
    # a de abas iguais continua igual
    assert _caixa("L 32×3 (FF)")[:2] == (32.0, 32.0)
