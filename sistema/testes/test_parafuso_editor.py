# -*- coding: utf-8 -*-
"""Parafuso colocado no editor 3D (ferramenta Parafuso) numa barra sem furo: o furo entra
no detalhe da barra (alma), e os parafusos que vieram do IFC não criam furo novo."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                   # noqa: E402
from nucleo2d import detalhar as det                 # noqa: E402
from nucleo2d.detalhe.base import _marcas, _autovetores   # noqa: E402
from test_detalhar2d import _modelo                  # noqa: E402


def _parafuso(base, eixo, u, criado=True, d=12.0, L=35.0):
    v = (eixo[1] * u[2] - eixo[2] * u[1], eixo[2] * u[0] - eixo[0] * u[2], eixo[0] * u[1] - eixo[1] * u[0])
    vs = []
    for k in (0.0, L):
        for i in range(12):
            t = 2 * math.pi * i / 12
            vs.append(tuple(base[j] + u[j] * d / 2 * math.cos(t) + v[j] * d / 2 * math.sin(t) + eixo[j] * k for j in range(3)))
    fs = [list(range(12))[::-1], list(range(12, 24))] + [[i, (i + 1) % 12, 12 + (i + 1) % 12, 12 + i] for i in range(12)]
    atr = {"tipo_ifc": "IfcMechanicalFastener"}
    if criado:
        atr["criado_no_editor"] = True
    return Solido(nome="BOLT (A) %gx%g" % (d, L), camada="Parafusos", vertices=vs, faces=fs, atributos=atr)


def _barra_e_parafuso(criado):
    doc = _modelo()
    lev = det.levantar(doc)
    pos = next(p for p in lev["posicoes"] if p.classe == "barra" and not p.furos)
    marca = det.marcas_de(pos)[0]
    ent = next(e for e in doc.entidades.values() if str(_marcas(e).get("posicao") or "") == marca)
    c, pca = _autovetores(ent.vertices)
    e1, e3 = pca[0], pca[2]
    base = tuple(c[j] - e3[j] * 17.5 + e1[j] * 100.0 for j in range(3))
    doc.add(_parafuso(base, e3, e1, criado))
    return next(p for p in det.levantar(doc)["posicoes"] if marca in det.marcas_de(p))


def test_parafuso_do_editor_fura_a_alma():
    pos = _barra_e_parafuso(True)
    furos = [f for f in pos.furos if f.vista == "frente"]
    assert len(furos) == 1 and abs(furos[0].d - 13.0) < 1e-6
    assert any("pelo parafuso do modelo" in o for o in pos.observacoes)


def test_parafuso_do_ifc_nao_cria_furo_em_barra():
    pos = _barra_e_parafuso(False)
    assert not pos.furos
