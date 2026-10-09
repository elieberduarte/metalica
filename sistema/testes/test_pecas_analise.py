# -*- coding: utf-8 -*-
"""O PDF das peças marcadas na análise (saida/pecas_analise.py, 09/10): no pórtico de dois pilares e uma viga apoiada
nos consolos, a normal na base do pilar pelo peso próprio é metade do peso da viga mais o peso do pilar, e o momento da
viga biapoiada no meio do vão é pL²/8."""
import json

import numpy as np

from nucleo3d.modelo import Documento
from saida import pecas_analise as PA
from testes.test_analise_premoldado import _caixa


def _portico():
    doc = Documento()
    for x in (0, 8000):
        p = _caixa("PILAR RETANGULAR", x - 200, -200, 0, x + 200, 200, 6000, "IfcColumn")
        doc.entidades[p.id] = p
    for k in range(9):
        v = _caixa("VIGA RETANGULAR", 200, -150, 6000, 7800, 150, 6600, "IfcBeam") if k == 0 else \
            _caixa("PILAR RETANGULAR", 30000 + k * 3000, 0, 0, 30400 + k * 3000, 400, 4000, "IfcColumn")
        doc.entidades[v.id] = v
    from nucleo3d import analise_estrutural as AE
    r = AE.calcular(doc, {"vento": False, "segunda_ordem": False})
    conv = lambda o: o.tolist() if isinstance(o, np.ndarray) else float(o) if isinstance(o, np.floating) else int(o)
    return doc, json.loads(json.dumps(r, default=conv))


def test_esforcos_do_pilar_e_da_viga():
    doc, an = _portico()
    viga = next(b for b in an["barras"] if b["papel"] == "viga")
    pilar = next(b for b in an["barras"] if b["papel"] == "pilar" and an["nos"][b["a"]][0] < 1000 and an["nos"][b["a"]][2] < 1)
    pcs = {pc["id"]: pc for pc in PA.pecas(an, [viga["ids"][0], pilar["ids"][0]])}
    pv, pp = pcs[viga["ids"][0]], pcs[pilar["ids"][0]]
    assert pp["pilar"] and not pv["pilar"]
    c = list(an["casos"]).index("PP")
    w = abs(an["w_local"][pv["barras"][0]][c][1]) + abs(an["w_local"][pv["barras"][0]][c][2])     # kN/m, peso da viga
    tv = PA.tabela_da_peca(an, pv)["casos"][c]
    L = pv["L"]
    assert abs(tv["M_vao"][0] - w * L * L / 8 / PA.TF) < 0.01 * w * L * L / 8 / PA.TF
    assert abs(tv["M_vao"][1] - L / 2) < L / 10
    tp = PA.tabela_da_peca(an, pp)["casos"][c]
    peso_pilar = 0.4 * 0.4 * 25.0 * 6.0
    base = -tp["ini"][0] * PA.TF
    assert abs(base - (w * L / 2 + peso_pilar)) < 0.03 * base                  # comprime a base
    assert abs(-tp["fim"][0] * PA.TF - w * L / 2) < 0.05 * base                # no topo, só a viga
    # a envoltória das combinações últimas comprime mais que o característico
    env = PA.tabela_da_peca(an, pp)["env"]
    assert env["N_min"][0] < tp["ini"][0]


def test_html_com_os_nomes():
    doc, an = _portico()
    ids = [b["ids"][0] for b in an["barras"] if b["papel"] == "pilar"][:2]
    h = PA.html_pecas(an, ids, {"nome": "teste"}, {ids[0]: "P7"}, [])
    assert "P7" in h and "Envoltória de cálculo" in h and h.count("<section") == 2
