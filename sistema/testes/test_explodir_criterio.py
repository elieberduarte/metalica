# -*- coding: utf-8 -*-
"""Explodir com critério (usuário, 12/11: "explodir os elementos — não todos peçinha por peçinha, mas com um critério: o que
está junto por um motivo fica junto; a tesoura pode ser UM elemento"; "pode seguir, preciso explodir o galpão viena").

O IFC do SketchUp chega como UM sólido com tudo dentro; nucleo3d/explodir_criterio separa: a treliça (banzos paralelos
ligados por diagonais) inteira, com as presilhas; o resto uma peça cada, com o perfil lido na seção; a viga dupla numa malha
só em dois perfis. Aqui um modelo feito à mão, longe da origem (como os importados), e o Galpão Viena de verdade quando
o arquivo existe nesta máquina."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.explodir_criterio import explodir           # noqa: E402

LONGE = (137526.0, 72917.0, 6427.0)


def _prisma(p0, p1, secao, cima=(0.0, 0.0, 1.0)):
    """Malha do prisma de p0 a p1 com a seção (lista de (u, v) em mm, u na horizontal ⟂, v em `cima`)."""
    a = [p1[i] - p0[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in a))
    a = [x / L for x in a]
    if abs(a[2]) > 0.9:
        e1 = [1.0, 0.0, 0.0]
    else:
        e1 = [-a[1], a[0], 0.0]
        n = math.hypot(e1[0], e1[1])
        e1 = [e1[0] / n, e1[1] / n, 0.0]
    e2 = [a[1] * e1[2] - a[2] * e1[1], a[2] * e1[0] - a[0] * e1[2], a[0] * e1[1] - a[1] * e1[0]]
    vs = []
    for p in (p0, p1):
        for (u, v) in secao:
            vs.append([p[i] + u * e1[i] + v * e2[i] for i in range(3)])
    n = len(secao)
    fs = [list(range(n))[::-1], list(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        fs.append([i, j, n + j, n + i])
    return vs, fs


def _I(h, b, tw, tf):
    return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + tf), (tw / 2, -h / 2 + tf), (tw / 2, h / 2 - tf), (b / 2, h / 2 - tf),
            (b / 2, h / 2), (-b / 2, h / 2), (-b / 2, h / 2 - tf), (-tw / 2, h / 2 - tf), (-tw / 2, -h / 2 + tf), (-b / 2, -h / 2 + tf)]


def _U(h, b, t):
    return [(0, -h / 2), (b, -h / 2), (b, -h / 2 + t), (t, -h / 2 + t), (t, h / 2 - t), (b, h / 2 - t), (b, h / 2), (0, h / 2)]


def _ret(b, h):
    return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]


def _redondo(d, n=12):
    return [(d / 2 * math.cos(2 * math.pi * k / n), d / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _juntar(pecas):
    V, F = [], []
    for vs, fs in pecas:
        k = len(V)
        V += vs
        F += [[i + k for i in f] for f in fs]
    return V, F


def _p(x, y, z):
    return (LONGE[0] + x, LONGE[1] + y, LONGE[2] + z)


def _modelo():
    """Uma treliça de 6 m (2 banzos U 150×50×3, 6 diagonais 50×50 maciças em zigue-zague, 4 presilhas nos banzos), um pilar
    PS 500×300×8×12,5, um contravento Ø16, uma viga dupla (2 I 400×200×8×12,5 encostados numa malha só) e uma chapa solta."""
    pecas = []
    H = 1000.0                                                         # altura da treliça (eixo a eixo dos banzos)
    pecas.append(_prisma(_p(0, 0, 0), _p(6000, 0, 0), _U(150, 50, 3)))           # banzo de baixo
    pecas.append(_prisma(_p(0, 0, H), _p(6000, 0, H), _U(150, 50, 3)))           # banzo de cima
    for k in range(6):                                                 # diagonais encostadas nos banzos
        x0, x1 = k * 1000.0, (k + 1) * 1000.0
        z0, z1 = (75.0, H - 75.0) if k % 2 == 0 else (H - 75.0, 75.0)
        pecas.append(_prisma(_p(x0 + 30, 25, z0), _p(x1 - 30, 25, z1), _ret(50, 50)))
    for x in (500.0, 2500.0, 4500.0, 5500.0):                          # presilhas (chapinhas 50×5×160) nos banzos
        pecas.append(_prisma(_p(x, -5, -80), _p(x, -5, 80), _ret(50, 5)))
    pecas.append(_prisma(_p(-2000, 3000, -500), _p(-2000, 3000, 7500), _I(500, 300, 8, 12.5)))   # pilar
    pecas.append(_prisma(_p(-2000, 3200, 0), _p(4000, 9000, 6000), _redondo(15.88)))             # contravento
    # viga dupla: dois I 400×200 lado a lado, encostados (uma malha só: os vértices do meio são os mesmos)
    s1 = [(u - 100, v) for (u, v) in _I(400, 200, 8, 12.5)]
    s2 = [(u + 100, v) for (u, v) in _I(400, 200, 8, 12.5)]
    v1, f1 = _prisma(_p(0, 6000, 7000), _p(9000, 6000, 7000), s1)
    v2, f2 = _prisma(_p(0, 6000, 7000), _p(9000, 6000, 7000), s2)
    vd = v1 + v2
    fd = f1 + [[i + len(v1) for i in f] for f in f2]
    # liga as duas metades pelos vértices iguais (o meio): troca os de v2 pelos de v1 na mesma posição
    for f in fd:
        for i, j in enumerate(f):
            if j >= len(v1):
                for k, q in enumerate(v1):
                    if all(abs(q[c] - vd[j][c]) < 1e-6 for c in range(3)):
                        f[i] = k
                        break
    pecas.append((vd, fd))
    pecas.append(_prisma(_p(8000, 9000, 0), _p(8000, 9000, 25), _ret(400, 300)))                 # chapa solta 400×300×25
    return _juntar(pecas)


def test_a_trelica_fica_inteira_e_o_resto_vira_pecas():
    V, F = _modelo()
    r = explodir(V, F, "Galpão.dxf#1")
    assert r["resumo"]["trelicas"] == 1, r["resumo"]
    (g,) = r["grupos"]
    nomes = [r["pecas"][i]["nome"] for i in g["membros"]]
    assert sorted(nomes).count("U 150×50×3") == 2, nomes                    # os dois banzos
    assert len([n for n in nomes if n.startswith("PLATE")]) == 4, nomes     # as presilhas dentro da treliça
    assert len(nomes) == 2 + 6 + 4, nomes                                  # banzos + diagonais + presilhas
    assert all(r["pecas"][i]["camada"] == "Treliças" for i in g["membros"])
    assert g["atributos"]["treliça"]["comprimento"] == 6000
    fora = [p for i, p in enumerate(r["pecas"]) if i not in set(g["membros"])]
    por = {p["nome"]: p["camada"] for p in fora}
    assert por.get("PS 500×300×8×12,5") == "Pilares", por
    assert por.get("Barra redonda Ø16") == "Contraventos", por               # 15,88 (5/8"): mm inteiro, o maior
    assert por.get("PLATE 400x300x25") == "Chapas" or por.get("PLATE 300x400x25") == "Chapas" or \
        any(n.startswith("PLATE") and c == "Chapas" for n, c in por.items()), por
    duplas = [p for p in fora if p["nome"] == "PS 400×200×8×12,5"]
    assert len(duplas) == 2 and r["resumo"]["vigas_duplas"] == 1, (por, r["resumo"])
    # cada peça com a marca e o nome do sólido de origem; os vértices no lugar (longe da origem)
    for p in r["pecas"]:
        assert p["atributos"]["marcas"]["perfil"] == p["nome"] and p["atributos"]["explodido_de"]["nome"] == "Galpão.dxf#1"
        assert all(abs(v[0] - LONGE[0]) < 20000 for v in p["vertices"])
    assert r["resumo"]["pedacos"] == len(r["pecas"])


def test_sem_diagonais_nao_ha_trelica():
    """Duas barras paralelas sem alma entre elas não são treliça (as vigas de um pórtico)."""
    V, F = _juntar([_prisma(_p(0, 0, 0), _p(6000, 0, 0), _I(300, 150, 6, 9)),
                    _prisma(_p(0, 0, 1000), _p(6000, 0, 1000), _I(300, 150, 6, 9))])
    r = explodir(V, F)
    assert r["resumo"]["trelicas"] == 0 and len(r["pecas"]) == 2
    assert {p["nome"] for p in r["pecas"]} <= {"PS 300×150×6×9", "W 310×21,0", "W 310×23,8"}


# o sólido único do Galpão Viena como chegou do SketchUp (12/11, antes de explodir), copiado do histórico da obra para cá:
# o teste nunca lê a obra do usuário (ela já foi explodida e muda — GESTÃO N.8, 13/11)
VIENA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cad", "viena_solido_unico.json.gz")


def viena_solido_unico():
    """{nome, vertices, faces} do sólido único do Galpão Viena (cópia fixa em dados_cad)."""
    import gzip
    with gzip.open(VIENA, "rt", encoding="utf-8") as f:
        return json.load(f)


def test_galpao_viena():
    """O caso que pediu a ferramenta: o IFC do SketchUp 2025 (1 proxy, 1.907 pedaços). A treliça da frente (135 m) inteira
    com as 1.014 presilhas; as do mezanino; os contraventos Ø16; os pilares PS; as 4 vigas mestras duplas separadas."""
    e = viena_solido_unico()
    r = explodir(e["vertices"], e["faces"], e["nome"])
    R = r["resumo"]
    assert R["trelicas"] >= 11 and R["vigas_duplas"] == 4, R
    frente = max(r["grupos"], key=lambda g: g["atributos"]["treliça"]["comprimento"])
    assert frente["atributos"]["treliça"] == {"banzos": 4, "alma": 253, "presilhas": 1014, "comprimento": 135000}
    nomes = [p["nome"] for p in r["pecas"]]
    assert nomes.count("Barra redonda Ø16") == 142
    assert nomes.count("PS 500×300×8×12,7") == 39
    assert R["por_camada"]["A confirmar"] <= 40, R                  # as placas de 12,7 da cobertura e o steel deck
