# -*- coding: utf-8 -*-
"""A composição do conjunto na prancha com a variante de furação (Hora Certa · Galpão Existente, montador N03, 30/10):
as treliças da marquise levam o S.T.5 (CH1 + CH34 = "P693 (b)") e o bloco PARA MONTAR pedia "PL14.1 12x · total 04x" —
a composição conta pela posição de base ("P693"), cujo nome é o da chapa do pilar W530. A posição cujas peças do conjunto
são todas de uma variante vai com a marca (e o nome) dela."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Chapa, Solido          # noqa: E402
from nucleo2d.detalhar import detalhar                        # noqa: E402


def _caixa(x0, y0, z0, x1, y1, z1, posicao, conjunto):
    v = [(x, y, z) for z in (z0, z1) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return Solido(nome="U100X50X3.04", camada="Vigas", vertices=v, faces=f,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"posicao": posicao, "conjunto": conjunto, "perfil": "U100X50X3.04"}})


def _modelo():
    cont = [(0, 0), (125, 0), (125, 110), (0, 110)]
    a = [{"x": 30, "y": 30, "diametro": 14.0}, {"x": 95, "y": 30, "diametro": 14.0}]
    b = [{"x": 30, "y": 30, "diametro": 14.0}, {"x": 95, "y": 80, "diametro": 14.0}]
    doc = Documento()
    # a marca de base: 2 chapas soltas (o pilar W530 da obra)
    for i in range(2):
        doc.add(Chapa(id="a%d" % i, nome="PLATE 125x110x8", contorno=cont, espessura=8.0, furos=a,
                      origem=(-5000.0, 1000.0 * i, 0.0), atributos={"marcas": {"posicao": "P693", "conjunto": "M50"}}))
    # o conjunto M1, duas instâncias: 2 barras + 2 chapas da outra furação (a treliça da marquise)
    for k, y in enumerate((0.0, 3000.0)):
        doc.add(_caixa(0, y - 50, 0, 6000, y + 50, 100, "P1", "M1"))
        doc.add(_caixa(0, y - 50, 800, 6000, y + 50, 900, "P2", "M1"))
        for j, x in enumerate((1000.0, 5000.0)):
            doc.add(Chapa(id="b%d%d" % (k, j), nome="PLATE 125x110x8", contorno=cont, espessura=8.0, furos=b,
                          origem=(x, y, 100.0), atributos={"marcas": {"posicao": "P693", "conjunto": "M1"}}))
    return doc


def _itens(r):
    out = {}
    for d in (r.get("desenhos") or {}).values():
        out.update(((getattr(d, "metadados", {}) or {}).get("detalhamento") or {}).get("itens") or {})
    return out


def test_a_composicao_do_conjunto_leva_a_variante():
    r = detalhar(_modelo(), grupos=["conjuntos", "chaparias", "completo"], regra_tercas=False, converter=False)
    ifc = r["nomes"]["ifc"]
    assert ifc.get("P693") and ifc.get("P693 (b)") and ifc["P693"] != ifc["P693 (b)"]
    it = next(v for k, v in _itens(r).items() if "M1" in (v.get("marcas") or [k]))
    comp = {x["marca"]: (x["nome"], x["qtd"]) for x in it.get("composicao") or []}
    assert "P693" not in comp, comp
    assert comp.get("P693 (b)") == (ifc["P693 (b)"], 2), comp
