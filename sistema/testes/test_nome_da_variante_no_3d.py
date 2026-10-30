# -*- coding: utf-8 -*-
"""O nome de produção no 3D vai pela variante de furação (Hora Certa · Galpão Existente, auditor N12, 29/10): a chapa
da mesma marca do modelo com furação diferente vira "P842 (b)" só no detalhamento, e o nome gravado no modelo
(marcas.nome) vinha da marca do modelo — as 28 CH35 se chamavam "PL13.3" no 3D, e a composição das tesouras dizia
"4× P842" quando eram P842 (b)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app                                                   # noqa: E402
from nucleo3d.modelo import Documento, Chapa                 # noqa: E402
from nucleo2d.detalhar import detalhar                       # noqa: E402


def _modelo():
    cont = [(0, 0), (125, 0), (125, 110), (0, 110)]
    a = [{"x": 100, "y": 25, "diametro": 14.0}, {"x": 100, "y": 85, "diametro": 14.0},
         {"x": 25, "y": 85, "diametro": 14.0}, {"x": 25, "y": 25, "diametro": 14.0}]
    b = [{"x": 100, "y": 23, "diametro": 14.0}, {"x": 100, "y": 83, "diametro": 14.0},
         {"x": 25, "y": 85, "diametro": 14.0}, {"x": 25, "y": 25, "diametro": 14.0}]    # uma coluna 2 mm abaixo
    doc = Documento()
    for i, furos in enumerate((a, a, b, a, b)):
        doc.add(Chapa(id="c%d" % i, nome="PLATE 125x110x8", contorno=cont, espessura=8.0, furos=furos,
                      origem=(0.0, 1000.0 * i, 0.0), atributos={"marcas": {"posicao": "P842"}}))
    return doc


def test_as_chapas_da_variante_ganham_o_nome_dela_no_3d():
    doc = _modelo()
    r = detalhar(doc, grupos=["chapas"], regra_tercas=False, converter=False)
    nomes = r["nomes"]
    assert set(nomes.get("variantes") or {}) == {"c2", "c4"}
    n_base, n_var = nomes["ifc"]["P842"], nomes["ifc"]["P842 (b)"]
    assert n_base and n_var and n_base != n_var
    app._nomes_no_modelo(doc, nomes)
    nome = {i: doc.entidades[i].atributos["marcas"]["nome"] for i in ("c0", "c1", "c2", "c3", "c4")}
    assert nome == {"c0": n_base, "c1": n_base, "c2": n_var, "c3": n_base, "c4": n_var}, nome
    # a marca do modelo não muda: só o nome de produção
    assert doc.entidades["c2"].atributos["marcas"]["posicao"] == "P842"
