# -*- coding: utf-8 -*-
"""A elevação da treliça no padrão do corte das tesouras do projetista (28/09): cada barra só com as bordas
de fora do perfil; a alma pela linha de trabalho — montante no eixo, diagonal ligando os nós."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Polilinha                      # noqa: E402
from nucleo2d.detalhe import conjuntos as C                                 # noqa: E402


def test_barra_fica_so_com_as_bordas_de_fora():
    """o banzo em U visto de lado: o contorno (100 de altura) e a aresta da espessura, 3 mm para
    dentro, que saía como uma segunda linha colada na borda — ela e a cópia fina saem"""
    d = Desenho(nome="t", escala=25.0)
    atr = {"origem": "b1"}
    d.add(Polilinha(camada="BANZOS", vertices=[(0, 0), (1000, 0), (1000, 100), (0, 100)], fechada=True, atributos=dict(atr)))
    d.add(Linha(camada="BANZOS", a=(0, 97), b=(1000, 97), atributos=dict(atr)))            # a espessura
    d.add(Linha(camada="VISTA-FINA", a=(0, 100.02), b=(1000, 100.02), atributos=dict(atr)))  # a cópia fina
    C._so_bordas_externas(d, list(d.entidades.values()), {"b1"}, {"b1": "BANZOS"})
    ys = sorted(round((e.a[1] + e.b[1]) / 2) for e in d.entidades.values() if abs(e.a[1] - e.b[1]) < 1e-6)
    assert ys == [0, 100]                               # as duas bordas horizontais, uma vez cada
    assert all(e.camada == "BANZOS" for e in d.entidades.values())


def test_alma_liga_os_nos():
    """a diagonal que chega no banzo liga na ponta do montante (o nó); a barra que encosta no meio do
    montante fica no cruzamento e continua reta"""
    d = Desenho(nome="t", escala=25.0)
    alma = {
        "m": ((0.0, 0.0), (0.0, 1000.0)),               # montante
        "d": ((800.0, 100.0), (45.0, 985.0)),           # diagonal que chega no banzo de cima, ao lado do montante
        "h": ((-600.0, 500.0), (-12.0, 500.0)),         # barra horizontal que encosta no meio do montante
    }
    camada_de = {"m": "MONTANTES", "d": "DIAGONAIS", "h": "DIAGONAIS"}
    banzo = ((-1000.0, 1050.0), (1000.0, 1050.0))       # o eixo do banzo de cima
    nos = C._alma_em_eixo(d, [], alma, camada_de, apoios=[banzo])
    linhas = {e.atributos["origem"]: e for e in d.entidades.values()}
    assert tuple(linhas["d"].b) == (0.0, 1000.0) or tuple(linhas["d"].a) == (0.0, 1000.0)
    h = linhas["h"]
    assert abs(h.a[1] - 500.0) < 1e-6 and abs(h.b[1] - 500.0) < 1e-6          # reta
    assert min(abs(h.a[0]), abs(h.b[0])) < 1e-6                                 # até o eixo do montante
    assert (0.0, 1000.0) in [tuple(q) for q in nos]
