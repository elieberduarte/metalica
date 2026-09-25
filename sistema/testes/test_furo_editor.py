# -*- coding: utf-8 -*-
"""Furo feito no editor 3D (ferramenta Furo): o marcador dá o furo no detalhe da barra
(alma) e da chapa do IFC com o diâmetro gravado, anda com o furo da chapa, e não conta
como parafuso em lugar nenhum (posição, conjunto, acessórios, IFC exportado)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Solido                                    # noqa: E402
from nucleo2d import detalhar as det                                  # noqa: E402
from nucleo2d.detalhe.base import _marcas, _autovetores, _fixadores, _so_parafusos, _eh_furo   # noqa: E402
from test_detalhar2d import _modelo                                   # noqa: E402


def _marcador(ponto, eixo, d=14.0, prof=6.0):
    """O que a ferramenta Furo grava: cilindro escuro na camada Furos com `atributos.furo`."""
    L = math.sqrt(sum(x * x for x in eixo))
    a = tuple(x / L for x in eixo)
    u = (0.0, 0.0, 1.0) if abs(a[2]) < 0.9 else (1.0, 0.0, 0.0)
    v = (a[1] * u[2] - a[2] * u[1], a[2] * u[0] - a[0] * u[2], a[0] * u[1] - a[1] * u[0])
    w = (a[1] * v[2] - a[2] * v[1], a[2] * v[0] - a[0] * v[2], a[0] * v[1] - a[1] * v[0])
    vs = []
    for k in (-0.3, prof + 0.3):
        for i in range(16):
            t = 2 * math.pi * i / 16
            vs.append(tuple(ponto[j] + v[j] * d / 2 * math.cos(t) + w[j] * d / 2 * math.sin(t) + a[j] * k for j in range(3)))
    fs = [list(range(16))[::-1], list(range(16, 32))] + [[i, (i + 1) % 16, 16 + (i + 1) % 16, 16 + i] for i in range(16)]
    return Solido(nome="FURO Ø%g" % d, camada="Furos", vertices=vs, faces=fs,
                  atributos={"tipo_ifc": "IfcOpeningElement", "exportar": False, "criado_no_editor": True,
                             "furo": {"d": d, "ponto": list(ponto), "eixo": list(a), "profundidade": prof}})


def _barra_com_marcador():
    doc = _modelo()
    lev = det.levantar(doc)
    pos = next(p for p in lev["posicoes"] if p.classe == "barra" and not p.furos)
    marca = det.marcas_de(pos)[0]
    ent = next(e for e in doc.entidades.values() if str(_marcas(e).get("posicao") or "") == marca)
    c, pca = _autovetores(ent.vertices)
    e1, e3 = pca[0], pca[2]
    # a face de fora da alma: o lado da caixa que tem a camada de vértices da espessura
    # (2,25 mm) logo atrás — do outro lado ficam só as pontas das mesas
    zs = [sum((v[j] - c[j]) * e3[j] for j in range(3)) for v in ent.vertices]
    lado = None
    for z0, sinal in ((min(zs), 1.0), (max(zs), -1.0)):
        if any(abs(z - (z0 + sinal * 2.25)) < 0.3 for z in zs):
            lado = (z0, sinal)
    assert lado is not None
    z0, sinal = lado
    face = tuple(c[j] + e3[j] * z0 + e1[j] * 100.0 for j in range(3))
    doc.add(_marcador(face, tuple(sinal * x for x in e3), d=14.0, prof=2.25))
    return doc, marca


def test_marcador_fura_a_alma_com_o_diametro_gravado():
    doc, marca = _barra_com_marcador()
    lev = det.levantar(doc)
    pos = next(p for p in lev["posicoes"] if marca in det.marcas_de(p))
    furos = [f for f in pos.furos if f.vista == "frente"]
    assert len(furos) == 1 and abs(furos[0].d - 14.0) < 1e-6
    assert any("ferramenta Furo" in o for o in pos.observacoes)
    # não é parafuso: nem na posição, nem nos acessórios, nem na contagem por conjunto
    assert not pos.parafusos and pos.porcas == 0
    assert not any("FURO" in k for k in lev["acessorios"])
    fx = _fixadores(doc)
    assert any(_eh_furo(f) for f in fx) and not any(_eh_furo(f) for f in _so_parafusos(fx))


def test_marcador_fura_a_chapa_do_ifc():
    doc = _modelo()
    ch = next(e for e in doc.entidades.values() if str(_marcas(e).get("posicao") or "") == "P1")
    c, pca = _autovetores(ch.vertices)
    e1, e3 = pca[0], pca[2]
    # chapa 130 × 50 × 3 com um furo de 13 no meio: o marcador vai a 40 mm do centro
    face = tuple(c[j] + e3[j] * 1.5 + e1[j] * 40.0 for j in range(3))
    doc.add(_marcador(face, tuple(-x for x in e3), d=18.0, prof=3.0))
    pos = next(p for p in det.levantar(doc)["posicoes"] if "P1" in det.marcas_de(p))
    ds = sorted(round(f.d, 1) for f in pos.furos)
    assert 18.0 in ds, ds
    assert any("ferramenta Furo" in o for o in pos.observacoes)


def test_marcador_nao_vai_para_o_ifc(tmp_path):
    from ifc import exportar
    doc, _ = _barra_com_marcador()
    caminho = str(tmp_path / "x.ifc")
    exportar.exportar(doc, caminho, "teste")
    with open(caminho, encoding="utf-8", errors="replace") as f:
        texto = f.read()
    assert "FURO" not in texto and "IFCOPENINGELEMENT" not in texto.upper()
