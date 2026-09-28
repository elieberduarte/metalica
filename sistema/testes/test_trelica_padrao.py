# -*- coding: utf-8 -*-
"""A elevação da treliça no padrão do corte das tesouras do projetista (28/09): cada barra só com as bordas
de fora do perfil; a alma pela linha de trabalho — montante no eixo, diagonal ligando os nós."""
import math
import os
import sys
from types import SimpleNamespace

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


def _peca(id_, perfil):
    return SimpleNamespace(id=id_, atributos={"marcas": {"perfil": perfil}})


def test_barra_com_o_perfil_do_banzo_fica_com_contorno():
    """no joelho da Sala: a descida do banzo de baixo (U100X50, o perfil do banzo) ligada na horizontal
    que continua o banzo fica com contorno; a barra de U92X30 da alma, ao lado dela, fica em eixo
    (pedido do usuário, 28/09)"""
    instancia = [_peca("bz", "U100X50X#9"), _peca("hz", "U100X50X3.04"), _peca("desce", "U100X50X3.04"),
                 _peca("d1", "U92X30X#13"), _peca("d2", "U92X30X#13"), _peca("d3", "U92X30X#13"),
                 _peca("d4", "U92X30X#13")]
    camada_de = {"bz": "BANZOS", "hz": "DIAGONAIS", "desce": "MONTANTES", "d1": "DIAGONAIS", "d2": "DIAGONAIS",
                 "d3": "DIAGONAIS", "d4": "DIAGONAIS"}
    banzo = ((2000.0, 600.0), (9000.0, 2000.0))
    alma = {
        "hz": ((1500.0, 600.0), (1990.0, 600.0)),        # continua o banzo até o nó do joelho
        "desce": ((1500.0, 600.0), (1500.0, 100.0)),     # desce do fim da horizontal
        "d1": ((200.0, 520.0), (1500.0, 580.0)),         # a de U92X30 que chega perto dela
        "d2": ((200.0, 100.0), (1500.0, 500.0)),
        "d3": ((200.0, 100.0), (1500.0, 100.0)),
        "d4": ((2500.0, 700.0), (3000.0, 1500.0)),
    }
    assert C._alma_com_contorno(instancia, alma, [banzo], camada_de) == {"hz", "desce"}


def test_banzo_para_na_face_do_montante_de_fechamento():
    """na cumeeira a borda do banzo de baixo entrava no montante de fechamento: o trecho de dentro sai"""
    d = Desenho(nome="t", escala=25.0)
    for a_, b_ in (((0, 0), (0, 1000)), ((0, 1000), (100, 1000)), ((100, 1000), (100, 0)), ((100, 0), (0, 0))):
        d.add(Linha(camada="MONTANTES", a=a_, b=b_, atributos={"origem": "m"}))
    d.add(Linha(camada="BANZOS", a=(-500, 400), b=(60, 500), atributos={"origem": "bz"}))
    d.add(Linha(camada="BANZOS", a=(-500, 300), b=(0, 300), atributos={"origem": "bz"}))    # até a face: fica
    C._esconder_atras_dos_montantes(d, list(d.entidades.values()), {"m"}, {"bz", "m"})
    bz = sorted((e for e in d.entidades.values() if e.atributos["origem"] == "bz"), key=lambda e: e.a[1])
    assert len(bz) == 2
    assert abs(max(bz[1].a[0], bz[1].b[0]) - 1.0) < 0.6          # parou na face (x = 0, 1 mm de folga)
    assert tuple(bz[0].b) == (0, 300)


def test_encadear_telha():
    """as faces de baixo das telhas, uma por peça, viram uma polilinha; a repetida entra uma vez"""
    segs = [((0, 0), (100, 10)), ((100.0, 10.0), (200, 30)), ((300, 60), (200.5, 30.2)), ((0, 0), (100, 10))]
    polis = C._encadear(segs)
    assert len(polis) == 1 and len(polis[0]) == 4
    assert polis[0][0] == (0, 0) or polis[0][-1] == (0, 0)
