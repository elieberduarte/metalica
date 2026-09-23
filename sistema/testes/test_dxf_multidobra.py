# -*- coding: utf-8 -*-
"""DXF do CAD pela ezdxf (cotas DIMENSION, cores, grupos) e telha multi-dobra reconhecida."""
import math
import os
import tempfile

import pytest

from nucleo2d.desenho import Desenho, Linha, Cota, Texto
from nucleo3d.modelo import Solido

ezdxf = pytest.importorskip("ezdxf")


def test_dxf_com_cotas_funcionais_cores_e_grupo():
    from nucleo2d import dxf_cad
    d = Desenho(nome="t", escala=10.0)
    atr = {"posicao": "P1", "detalhe": "posicao", "nome": "S.T.2"}
    d.add(Linha(camada="VISTA", a=(0, 0), b=(270, 0), atributos=dict(atr)))
    d.add(Cota(modo="h", p1=(0, 0), p2=(270, 0), deslocamento=-10.0, atributos=dict(atr)))
    d.add(Cota(modo="alinhada", p1=(0, 0), p2=(300, 400), deslocamento=10.0))
    d.add(Texto(posicao=(0, 50), texto="S.T.2 – 49x", altura=3.5, atributos=dict(atr)))
    with tempfile.TemporaryDirectory() as tmp:
        caminho = dxf_cad.exportar(d, os.path.join(tmp, "t.dxf"))
        doc = ezdxf.readfile(caminho)
    msp = doc.modelspace()
    dims = [e for e in msp if e.dxftype() == "DIMENSION"]
    assert len(dims) == 2
    assert sorted(round(x.get_measurement()) for x in dims) == [270, 500]
    assert doc.layers.get("COTA").rgb is not None                 # a cor do CAD, em RGB
    txt = next(e for e in msp if e.dxftype() == "TEXT")
    assert txt.dxf.style == "METALICA" and abs(txt.dxf.height - 35.0) < 1e-6
    assert len(doc.groups) == 1 and next(iter(doc.groups))[0] == "S_T_2"


def _caixa(centro, eixos, ext, marcas):
    """Sólido-caixa com os eixos (u, w, n) e extensões dadas."""
    vs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs.append(tuple(centro[k] + sx * eixos[0][k] * ext[0] / 2 + sy * eixos[1][k] * ext[1] / 2
                                + sz * eixos[2][k] * ext[2] / 2 for k in range(3)))
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return Solido(vertices=vs, faces=faces, atributos={"tipo_ifc": "IfcBeam", "marcas": marcas})


def test_multidobra_reconhecida():
    from nucleo2d.detalhe.telhas import multidobras
    pecas = []
    R, h = 800.0, 40.0
    for inst, y in enumerate((0.0, 1100.0)):
        m = lambda pos: {"posicao": pos, "conjunto": "M9", "perfil": "TELHA TP40 0.65MM"}   # noqa: E731
        w = (0.0, 1.0, 0.0)
        # parede: reta vertical de 600 que termina em (0, 0); arco de 90° com centro (R, 0);
        # cobertura: reta horizontal de 3000 partindo de (R, R)
        pecas.append(_caixa((0.0, y, -300.0), ((0, 0, 1), w, (1, 0, 0)), (600.0, 1000.0, h), m("PA")))
        n = 9
        for i in range(n):
            a0, a1 = math.pi - i * (math.pi / 2) / n, math.pi - (i + 1) * (math.pi / 2) / n
            p0 = (R + R * math.cos(a0), R * math.sin(a0))
            p1 = (R + R * math.cos(a1), R * math.sin(a1))
            c = ((p0[0] + p1[0]) / 2, y, (p0[1] + p1[1]) / 2)
            d = (p1[0] - p0[0], 0.0, p1[1] - p0[1])
            L = math.hypot(d[0], d[2])
            u = (d[0] / L, 0.0, d[2] / L)
            nn = (-u[2], 0.0, u[0])
            pecas.append(_caixa(c, (u, w, nn), (L, 1000.0, h), m("FA")))
        pecas.append(_caixa((R + 1500.0, y, R), ((1, 0, 0), w, (0, 0, 1)), (3000.0, 1000.0, h), m("CO")))
    r = multidobras(pecas)
    assert len(r["telhas"]) == 1
    t = r["telhas"][0]
    assert t["instancias"] == 2 and abs(t["angulo"] - 90.0) < 1.0
    assert abs(t["reta1"] - 600.0) < 25 or abs(t["reta2"] - 600.0) < 25
    assert abs(max(t["reta1"], t["reta2"]) - 3000.0) < 25
    assert abs(t["raio"] - R) < 0.03 * R
    assert t["desenv_ext"] > t["desenv_int"]
    assert r["posicoes"] == {"PA", "FA", "CO"}
