# -*- coding: utf-8 -*-
"""A Montagem por eixos (11/10/2026, web/cad/implantacao.js): os elementos lançados no quadro da Implantação — em mm de
papel, na escala do quadro — voltam à medida real pelo mapa dele (nucleo3d/de_planta_estrutura.planta_real), e o 3D sai
igual ao da mesma estrutura lançada numa planta comum."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d.desenho import Desenho, Linha, Polilinha, Texto  # noqa: E402
from nucleo3d import de_planta_estrutura as DPE  # noqa: E402

S = 200.0                                     # a escala do quadro
Q = {"id": "qi", "tipo": "implantacao", "escala": S, "x": 10.0, "y": -40.0, "w": 400.0, "h": 300.0,
     "mapa": {"X0": 0.0, "Y0": 20000.0, "ox": 25.0, "oy": -45.0, "giro": 0.0}}


def papel(g, p, q=Q):
    mp = q["mapa"]
    return (q["x"] + mp["ox"] + (g - mp["X0"]) / q["escala"], q["y"] + mp["oy"] + (p - mp["Y0"]) / q["escala"])


def _montagem(*ents, quadros=(Q,)):
    des = Desenho(nome="Montagem", escala=1.0, metadados={"montagem": {"versao": 1, "quadros": [dict(q) for q in quadros]}})
    for e in ents:
        des.add(e)
    return des


BARRAS = [[0, 0, 20000, 0, "banzo_inf"], [0, 0, 10000, 1500, "banzo_sup"], [10000, 1500, 20000, 0, "banzo_sup"],
          [10000, 0, 10000, 1500, "montante"]]


def _trelica(a, b, quadro="qi"):
    return Linha(a=a, b=b, camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T1", "quadro": quadro, "nivel_base": 6000,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": BARRAS, "vao": 20000, "altura": 1500}})


def test_planta_real_leva_o_elemento_da_implantacao_a_medida_real():
    t = _trelica(papel(6000, 0), papel(6000, 20000))
    texto = Texto(posicao=papel(0, 0), texto="1", atributos={"quadro": "qi", "gerado": "implantacao"})
    fora = _trelica((0.0, 0.0), (100.0, 0.0), quadro="outro")
    real = DPE.planta_real(_montagem(t, texto, fora))
    assert list(real.entidades) == [t.id]                       # só o elemento da implantação; o gerado e o de fora não
    e = real.entidades[t.id]
    assert math.dist(e.a, (6000, 0)) < 1e-6 and math.dist(e.b, (6000, 20000)) < 1e-6


def test_o_3d_pela_implantacao_e_o_mesmo_da_planta_comum():
    t = _trelica(papel(6000, 0), papel(6000, 20000))
    doc_m, av_m = DPE.modelo_da_planta(_montagem(t), [])
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(6000.0, 0.0), b=(6000.0, 20000.0), camada="ESTRUTURA", atributos={k: v for k, v in t.atributos.items() if k != "quadro"}))
    doc_c, _ = DPE.modelo_da_planta(comum, [])
    pts = lambda d: sorted((tuple(round(c, 3) for c in b.inicio), tuple(round(c, 3) for c in b.fim)) for b in d.entidades.values())
    assert len(doc_m.entidades) == len(doc_c.entidades) > 0
    assert pts(doc_m) == pts(doc_c)
    zs = [b.inicio[2] for b in doc_m.entidades.values()] + [b.fim[2] for b in doc_m.entidades.values()]
    assert min(zs) >= 6000 - 200 and max(zs) <= 6000 + 1500 + 200


def test_pilar_e_giro_dos_eixos():
    # os eixos girados 90°: o g da implantação corre no Y da planta
    q = dict(Q, mapa=dict(Q["mapa"], giro=90.0))
    lado = 150 / S
    c = papel(6000, 0, q)
    pil = Polilinha(vertices=[(c[0] - lado, c[1] - lado), (c[0] + lado, c[1] - lado), (c[0] + lado, c[1] + lado), (c[0] - lado, c[1] + lado)],
                    fechada=True, camada="ESTRUTURA", atributos={"elemento": "pilar", "material": "aco", "marca": "P1", "quadro": "qi",
                                                                 "secao": {"perfil": "W 200×15", "aco": "ASTM A572 Gr.50"},
                                                                 "nivel_base": 0, "nivel_topo": 6000, "centro": list(c)})
    real = DPE.planta_real(_montagem(pil, quadros=(q,)))
    e = real.entidades[pil.id]
    cx = sum(v[0] for v in e.vertices) / 4
    cy = sum(v[1] for v in e.vertices) / 4
    assert abs(cx - 0.0) < 1e-6 and abs(cy - 6000.0) < 1e-6         # (g, p) = (6000, 0) girado 90° → (0, 6000)
    lados = [math.dist(e.vertices[i], e.vertices[(i + 1) % 4]) for i in range(4)]
    assert all(abs(L - 300.0) < 1e-6 for L in lados)                  # 300 mm reais
    assert math.dist(e.atributos["centro"], (0.0, 6000.0)) < 1e-6


def test_fora_da_montagem_a_planta_e_a_mesma():
    des = Desenho(nome="planta", escala=100.0)
    assert DPE.planta_real(des) is des
