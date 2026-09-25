# -*- coding: utf-8 -*-
"""Cantos redondos (nucleo3d.cantos): a barra calandrada por anéis (como o TecnoMETAL
exporta) é reconhecida — raio, ângulo, trechos retos —, as opções de quebra dão o desvio
certo, a malha reconstruída tem os nós na tangente e fecha, a barra redonda fica de fora,
e no 2D a peça quebrada ganha os nós de chanfro nas quinas."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo3d.modelo import Documento, Solido                        # noqa: E402
from nucleo3d import cantos                                          # noqa: E402
from nucleo3d.geometria import volume_malha                          # noqa: E402

R, ANG = 600.0, 80.0
SECAO = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (96.0, 50.0), (96.0, 4.0), (4.0, 4.0), (4.0, 50.0), (0.0, 50.0)]   # U 100×50×4 (m, b)


def _joelho(reto_antes=500.0, reto_depois=400.0, passos=25, raio=R, angulo=ANG, perfil="U100X50X4.18", nome="P15"):
    """Barra em U ao longo de x que vira para +y num arco no plano xy: anéis de 8 vértices,
    quadriláteros entre eles e as duas tampas — a malha que o IFC do TecnoMETAL traz."""
    th = math.radians(angulo)
    # eixo: reto ao longo de x, arco de centro (reto_antes, raio, 0), reto tangente no fim
    eixo, tangentes = [], []
    if reto_antes > 0:
        eixo.append((0.0, 0.0, 0.0)); tangentes.append((1.0, 0.0, 0.0))
    eixo.append((reto_antes, 0.0, 0.0)); tangentes.append((1.0, 0.0, 0.0))
    C = (reto_antes, raio, 0.0)
    for k in range(1, passos + 1):
        a = th * k / passos
        eixo.append((C[0] + raio * math.sin(a), C[1] - raio * math.cos(a), 0.0))
        tangentes.append((math.cos(a), math.sin(a), 0.0))
    t = tangentes[-1]
    if reto_depois > 0:
        eixo.append((eixo[-1][0] + t[0] * reto_depois, eixo[-1][1] + t[1] * reto_depois, 0.0)); tangentes.append(t)
    vertices, faces = [], []
    b = (0.0, 0.0, 1.0)
    for c, t in zip(eixo, tangentes):
        m = (-t[1], t[0], 0.0)                     # normal no plano, para o lado do centro
        base = len(vertices)
        for x, y in SECAO:
            vertices.append((c[0] + m[0] * (x - 50.0) + b[0] * (y - 25.0), c[1] + m[1] * (x - 50.0) + b[1] * (y - 25.0), c[2] + b[2] * (y - 25.0)))
    n = len(SECAO)
    faces.append(list(range(n))[::-1])
    faces.append([len(vertices) - n + i for i in range(n)])
    for r in range(len(eixo) - 1):
        a0, a1 = r * n, (r + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append([a0 + i, a0 + j, a1 + j, a1 + i])
    return Solido(nome=perfil, camada="Vigas", vertices=vertices, faces=faces,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"posicao": nome, "conjunto": "M2", "perfil": perfil, "nome": "B.13"}})


def test_reconhece_o_arco_e_os_trechos_retos():
    an = cantos.analisar_peca(_joelho())
    assert an is not None
    arco = an["arco"]
    assert abs(arco["raio"] - R) < 0.02 * R, arco["raio"]
    assert abs(arco["angulo"] - ANG) < 1.5, arco["angulo"]
    assert abs(arco["comprimento"] - R * math.radians(ANG)) < 0.02 * R * math.radians(ANG)
    retos = sorted(round(r[2]) for r in an["retos"])
    assert retos == [400, 500], retos


def test_opcoes_de_quebra_e_desvio():
    op = {o["n"]: o for o in cantos.opcoes_de_quebra(R, ANG)}
    th = math.radians(ANG)
    assert abs(op[1]["desvio"] - R * (1 / math.cos(th / 4) - 1)) < 1e-6
    assert abs(op[2]["desvio"] - R * (1 / math.cos(th / 4) - 1)) < 1e-6         # os nós de 2 retas saem tanto quanto as pontas de 1
    assert abs(op[3]["desvio"] - R * (1 / math.cos(th / 6) - 1)) < 1e-6
    assert op[4]["desvio"] < op[3]["desvio"] < op[2]["desvio"]


def test_quebra_poe_os_nos_na_tangente_e_fecha_a_malha():
    for n in (1, 2, 3):
        e = _joelho()
        v0 = volume_malha(e.vertices, e.faces)
        q = cantos.quebrar_peca(e, n)
        assert q and q["n"] == n and len(q["nos"]) == n + 1
        C = (500.0, R, 0.0)
        th = math.radians(ANG)
        # nós das pontas a R/cos(θ/4N), os do meio a R/cos(θ/2N) do centro
        for k, no in enumerate(q["nos"]):
            esperado = R / math.cos(th / (4 * n)) if k in (0, n) else R / math.cos(th / (2 * n))
            assert abs(math.dist(no, C) - esperado) < 1.0, (n, k, math.dist(no, C), esperado)
        # os anéis retos ficaram (2 + 2), os do arco viraram os n + 1 nós
        assert len(e.vertices) == 8 * (4 + n + 1)
        assert all(0 <= i < len(e.vertices) for f in e.faces for i in f)
        assert sum(1 for f in e.faces if len(f) == 8) == 2
        v1 = volume_malha(e.vertices, e.faces)
        assert 0.95 * v0 < v1 < 1.15 * v0, (v0, v1)             # por fora do arco: um pouco maior
        assert e.atributos["quebras"]["n"] == n
        assert cantos.analisar_peca(e) is None                   # já não tem arco


def test_modelo_analisa_por_posicao_e_pula_barra_redonda():
    doc = Documento(nome="t")
    doc.add(_joelho(nome="P15"))
    doc.add(_joelho(nome="P15"))
    doc.add(_joelho(nome="P51", perfil="FE RED 3/8''"))
    an = cantos.analisar_modelo(doc)
    assert [a["marca"] for a in an] == ["P15"] and an[0]["instancias"] == 2
    assert an[0]["perfil"] == "U100X50X4.18" and len(an[0]["opcoes"]) == 4
    r = cantos.quebrar_modelo(doc, {"P15": 2, "P99": 1})
    assert r["pecas"] == 2 and r["posicoes"] == ["P15"] and not r["falhas"]
    assert cantos.analisar_modelo(doc) == []                     # quebradas não voltam à lista


def test_nos_das_quebras_no_2d():
    from nucleo2d.desenho import Polilinha
    from nucleo2d.detalhe.conjuntos import _nos_das_quebras
    reta = Polilinha(vertices=[(0, 0), (100, 0), (200, 0)], atributos={"origem": "a"})
    quina = Polilinha(vertices=[(0, 0), (100, 0), (150, 40), (250, 120)], atributos={"origem": "a"})
    outra = Polilinha(vertices=[(0, 0), (100, 0), (150, 40)], atributos={"origem": "b"})
    _nos_das_quebras([reta, quina, outra], {"a"})
    assert not reta.atributos.get("nos_chanfro")
    assert quina.atributos.get("chanfro") == "quebra" and quina.atributos["nos_chanfro"] == [[100.0, 0.0]]
    assert not outra.atributos.get("nos_chanfro")


def _caixa_barra(a, b, largura=92.0, altura=30.0, nome="U92X30X2.25", posicao="P9", conjunto="M2"):
    """Barra reta de `a` a `b` como caixa por anéis de 4 vértices (tampa em cada ponta)."""
    d = [b[i] - a[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in d))
    d = [x / L for x in d]
    up = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = [d[1] * up[2] - d[2] * up[1], d[2] * up[0] - d[0] * up[2], d[0] * up[1] - d[1] * up[0]]
    n1 = math.sqrt(sum(x * x for x in e1)) or 1.0
    e1 = [x / n1 for x in e1]
    e2 = [d[1] * e1[2] - d[2] * e1[1], d[2] * e1[0] - d[0] * e1[2], d[0] * e1[1] - d[1] * e1[0]]
    vs = []
    oct_ = [(math.cos(2 * math.pi * k / 8), math.sin(2 * math.pi * k / 8)) for k in range(8)]
    for c in (a, b):
        for sx, sy in oct_:
            vs.append(tuple(c[i] + e1[i] * sx * largura / 2 + e2[i] * sy * altura / 2 for i in range(3)))
    faces = [list(range(8))[::-1], list(range(8, 16))] + [[i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i] for i in range(8)]
    return Solido(nome=nome, camada="Vigas", vertices=vs, faces=faces,
                  atributos={"tipo_ifc": "IfcBeam", "marcas": {"posicao": posicao, "conjunto": conjunto, "perfil": nome}})


def test_joelho_que_termina_no_arco_acaba_no_no_e_o_banzo_vem_ate_ele():
    """Sem trecho reto depois do arco (o joelho encosta no banzo): a peça passa a terminar
    no nó, em meia-esquadria, e o banzo que encostava na ponta antiga é esticado até o nó;
    a diagonal que apontava para o meio do arco vira uma diagonal do nó de baixo a cada nó."""
    doc = Documento(nome="t")
    joelho = _joelho(reto_antes=500.0, reto_depois=0.0)
    doc.add(joelho)
    th = math.radians(ANG)
    C = (500.0, R, 0.0)
    # ponta antiga do arco e a tangente que sai dele
    p1 = (C[0] + R * math.sin(th), C[1] - R * math.cos(th), 0.0)
    t1 = (math.cos(th), math.sin(th), 0.0)
    banzo = doc.add(_caixa_barra(p1, tuple(p1[i] + t1[i] * 3000.0 for i in range(3)), largura=100.0, altura=50.0, nome="U100X50X4.18", posicao="P20"))
    # diagonal do canto: do nó de baixo até o meio do arco (por dentro, a meia altura do perfil)
    meio = (C[0] + (R - 20.0) * math.sin(th / 2), C[1] - (R - 20.0) * math.cos(th / 2), 0.0)
    A = (500.0, -1500.0, 0.0)
    doc.add(_caixa_barra(A, meio, posicao="P13"))
    r = cantos.quebrar_modelo(doc, {"P15": 2})
    assert r["pecas"] == 1 and r["estendidas"] == 1 and r["diagonais"] == 3, r
    # o joelho: anéis 0 e 1 (o trecho reto) + os 3 nós; o último nó é a tampa
    assert len(joelho.vertices) == 8 * (2 + 3)
    q = joelho.atributos["quebras"]
    no_fim = q["nos"][-1]
    # o banzo veio até o nó: a ponta encostada andou R·tan(θ/8) para trás, sobre o seu eixo
    recuo = R * math.tan(th / 8)
    xs = [_dot3(v, t1) for v in banzo.vertices[:8]]                      # o anel da ponta, cortado em meia-esquadria
    assert abs(sum(xs) / 8 - (_dot3(p1, t1) - recuo)) < 2.0, (sum(xs) / 8, _dot3(p1, t1) - recuo)
    assert max(xs) - min(xs) > 5.0                                        # a ponta ficou inclinada (meia-esquadria)
    assert banzo.atributos.get("estendida_ate_no")
    # a diagonal antiga saiu; as novas vão do nó de baixo a cada nó
    marcas = sorted(str(e.atributos["marcas"]["posicao"]) for e in doc.entidades.values() if isinstance(e, Solido))
    assert "P13" not in marcas and marcas.count("P13-Q1") == 1 and "P13-Q3" in marcas
    for k, no in enumerate(q["nos"]):
        d = next(e for e in doc.entidades.values() if isinstance(e, Solido) and e.atributos["marcas"]["posicao"] == "P13-Q%d" % (k + 1))
        pa, pb = cantos._pontas_da_barra(d)
        assert min(math.dist(pa, A), math.dist(pb, A)) < 1.0
        assert min(math.dist(pa, no), math.dist(pb, no)) < 1.0
    assert abs(math.dist(no_fim, C) - R / math.cos(th / 8)) < 1.0


def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
