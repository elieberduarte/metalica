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


def test_banzo_em_linha_de_centro_fica_com_a_boca_para_o_miolo():
    """Regra do usuário (07/10): o U do banzo abre para o miolo da tesoura — também o banzo que chega em linha de
    centro (o esqueleto do leitor do desenho detalhado, sem as duas faces). O de cima abre para baixo, o de baixo
    para cima; antes ele ia pela regra da cantoneira, com a boca para fora do plano (CD Bom Dia, 11/10)."""
    from nucleo3d.geometria import base_local
    comum = Desenho(nome="planta", escala=100.0)
    t = _trelica((6000.0, 0.0), (6000.0, 20000.0))
    comum.add(Linha(a=t.a, b=t.b, camada="ESTRUTURA", atributos={k: v for k, v in t.atributos.items() if k != "quadro"}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    vistos = set()
    for b in doc.entidades.values():
        papel = (b.atributos or {}).get("papel_trelica")
        if papel not in ("banzo_sup", "banzo_inf"):
            continue
        w = tuple(b.fim[c] - b.inicio[c] for c in range(3))
        u, _v, _w = base_local(w, b.rotacao)
        assert (u[2] < -0.9) if papel == "banzo_sup" else (u[2] > 0.9), (papel, b.rotacao, u)
        assert abs(u[0]) < 1e-6                                   # no plano da tesoura (x = 6000)
        vistos.add(papel)
    assert vistos == {"banzo_sup", "banzo_inf"}


def test_tesouras_encostadas_cada_montante_de_ponta_abre_para_a_sua():
    """Duas tesouras no mesmo desenho, encostadas no apoio (o CD Bom Dia: A–B e B–C com os montantes de ponta lado a lado,
    a 330 mm): o U de cada montante de ponta abre para a tesoura dele — o lado das diagonais ligadas —, e não para o
    meio do desenho inteiro."""
    from nucleo3d.geometria import base_local
    barras = []
    for x0, x1 in ((0, 10000), (10330, 20330)):
        barras += [[x0, 0, x1, 0, "banzo_inf"], [x0, 1500, x1, 1500, "banzo_sup"],
                   [x0, 0, x0, 1500, "extremidade"], [x1, 0, x1, 1500, "extremidade"],
                   [x0, 0, x0 + 2500, 1500, "diagonal"], [x1, 0, x1 - 2500, 1500, "diagonal"]]
    comum = Desenho(nome="planta", escala=100.0)
    comum.add(Linha(a=(0.0, 0.0), b=(20330.0, 0.0), camada="ESTRUTURA", atributos={
        "elemento": "trelica", "material": "aco", "marca": "T", "nivel_base": 0,
        "perfis": {"banzo_sup": "U 150×50×3,0", "banzo_inf": "U 150×50×3,0", "diagonal": "L 50,8×4,76"},
        "desenho": {"barras": barras, "vao": 20330, "altura": 1500}}))
    doc, _ = DPE.modelo_da_planta(comum, [])
    abre = {}
    for b in doc.entidades.values():
        if (b.atributos or {}).get("papel_trelica") != "extremidade":
            continue
        w = tuple(b.fim[c] - b.inicio[c] for c in range(3))
        u, _v, _w = base_local(w, b.rotacao)
        abre[round(b.inicio[0])] = round(u[0])
    # as pontas de fora abrem para dentro; no apoio do meio, a de 10000 abre para trás (−x) e a de 10330 para frente (+x)
    assert abre == {0: 1, 10000: -1, 10330: 1, 20330: -1}, abre
