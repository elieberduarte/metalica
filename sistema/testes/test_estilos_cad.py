# -*- coding: utf-8 -*-
"""Estilos do desenho (CAD): o terminador da cota — seta, bola ou traço — vai para o DXF
como no papel, por cota ou pelo padrão do desenho (metadados.estilo)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Cota                            # noqa: E402


def _dxf(terminador=None, estilo=None):
    d = Desenho(nome="t", escala=25.0)
    if estilo:
        d.metadados["estilo"] = estilo
    d.add(Cota(p1=(0.0, 0.0), p2=(3000.0, 0.0), deslocamento=10.0, terminador=terminador))
    return d.para_dxf().dxf()


def test_terminador_seta_bola_e_traco_no_dxf():
    seta = _dxf()
    assert seta.count("SOLID") == 2 and "CIRCLE" not in seta                  # duas setas cheias
    bola = _dxf("bola")
    assert bola.count("CIRCLE") == 2 and "SOLID" not in bola                  # duas bolas
    traco = _dxf("traco")
    assert "SOLID" not in traco and "CIRCLE" not in traco
    # 3 linhas da cota + 2 traços = 5 linhas
    assert traco.count("\nLINE\n") == 5
    # o padrão do desenho vale para a cota sem terminador próprio; o próprio manda
    assert _dxf(None, {"terminador": "bola"}).count("CIRCLE") == 2
    assert _dxf("seta", {"terminador": "bola"}).count("SOLID") == 2


def test_terminador_sobrevive_ao_dict():
    d = Desenho(nome="t", escala=25.0)
    d.add(Cota(p1=(0.0, 0.0), p2=(500.0, 0.0), terminador="traco"))
    d2 = Desenho.de_dict(d.dict())
    c = next(e for e in d2.entidades.values() if isinstance(e, Cota))
    assert c.terminador == "traco"
