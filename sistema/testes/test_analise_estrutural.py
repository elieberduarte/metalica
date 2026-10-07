"""O motor de análise estrutural (nucleo3d/analise_estrutural.py) contra as soluções de livro: viga bi-engastada e
biapoiada (rótulas por condensação), pilar em balanço nos dois eixos (o giro da peça), treliça (estática), equilíbrio."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo3d import analise_estrutural as AE  # noqa: E402


def _sec(A=0.01, Iz=1e-4, Iy=2e-5, J=1e-6, Wz=1e-3, Wy=2e-4):
    return {"A": A, "Iz": Iz, "Iy": Iy, "J": J, "Wz": Wz, "Wy": Wy, "kg_m": 0.0, "tipo": "I"}


def _modelo(nos, barras, apoios, rot=None):
    nos = np.array(nos, float)
    bs = []
    for k, (a, b) in enumerate(barras):
        R = AE._eixos(nos[a], nos[b], (rot or {}).get(k, 0.0))
        bs.append({"a": a, "b": b, "L": float(np.linalg.norm(nos[b] - nos[a])), "papel": "viga", "sec": _sec(), "R": R,
                   "soltos": [], "papel_trelica": None, "elemento": None, "grupo": None, "marca": None, "perfil": "", "ids": []})
    return {"nos": nos, "barras": bs, "apoios": [{"no": n, "tipo": t, "chave": ""} for n, t in apoios], "par": dict(AE.PARAMETROS_PADRAO)}


def _caso(dist=None, nodal=None):
    return {"dist": dist or {}, "nodal": nodal or {}}


def test_viga_bi_engastada_carga_uniforme():
    L, w = 6.0, 10.0
    M = _modelo([[0, 0, 3], [L / 2, 0, 3], [L, 0, 3]], [(0, 1), (1, 2)], [(0, "engastada"), (2, "engastada")])
    casos = {"q": _caso(dist={0: np.array([0, 0, -w]), 1: np.array([0, 0, -w])})}
    sol = AE.resolver(M, casos)
    e0 = AE.esforcos_em(sol["pontas"][0, 0], sol["w"][0, 0], np.array([0.0, L / 2]))
    EI = AE.E_ACO * 1e-4
    assert e0[0, 5] == pytest.approx(-w * L * L / 12, rel=1e-6)          # momento negativo no engaste
    assert e0[1, 5] == pytest.approx(w * L * L / 24, rel=1e-6)           # positivo no meio
    assert abs(sol["U"][6 * 1 + 2, 0]) == pytest.approx(w * L ** 4 / (384 * EI), rel=1e-6)
    # reações: metade da carga em cada engaste
    assert sol["reacoes"][0][2, 0] == pytest.approx(w * L / 2, rel=1e-6)


def test_rotula_nas_pontas_vira_biapoiada():
    L, w = 6.0, 10.0
    M = _modelo([[0, 0, 3], [L, 0, 3]], [(0, 1)], [(0, "engastada"), (1, "engastada")])
    M["barras"][0]["soltos"] = [4, 5, 10, 11]
    sol = AE.resolver(M, {"q": _caso(dist={0: np.array([0, 0, -w])})})
    e = AE.esforcos_em(sol["pontas"][0, 0], sol["w"][0, 0], np.array([0.0, L / 2, L]))
    assert e[0, 5] == pytest.approx(0, abs=1e-6) and e[2, 5] == pytest.approx(0, abs=1e-6)
    assert e[1, 5] == pytest.approx(w * L * L / 8, rel=1e-6)


@pytest.mark.parametrize("rot,inercia", [(0.0, "x"), (90.0, "y")])
def test_pilar_em_balanco_o_giro_muda_o_eixo(rot, inercia):
    """pilar engastado com força horizontal em X no topo: com giro 0 a altura da seção fica em X (Iz trabalha);
    girado 90°, a força pega a inércia fraca"""
    H, P = 5.0, 2.0
    M = _modelo([[0, 0, 0], [0, 0, H]], [(0, 1)], [(0, "engastada")], rot={0: rot})
    sol = AE.resolver(M, {"p": _caso(nodal={0: np.array([P / 2, 0, 0])})})   # a força nodal vai nas duas pontas: só a do topo conta
    I = 1e-4 if inercia == "x" else 2e-5
    ux = sol["U"][6 * 1 + 0, 0]
    assert ux == pytest.approx(P / 2 * H ** 3 / (3 * AE.E_ACO * I), rel=1e-6)
    assert abs(sol["reacoes"][0][4, 0]) == pytest.approx(P / 2 * H, rel=1e-6)   # momento na base (em torno de Y)


def test_trelica_simples_estatica():
    """treliça triangular rotulada: carga vertical P no topo, apoios no pé — N nas barras inclinadas = P/(2 sen α)"""
    P, b, h = 10.0, 4.0, 3.0
    M = _modelo([[0, 0, 0], [b, 0, 0], [b / 2, 0, h]], [(0, 2), (2, 1), (0, 1)], [(0, "engastada"), (1, "engastada")])
    for br in M["barras"]:
        br["soltos"] = [4, 5, 10, 11]
    sol = AE.resolver(M, {"p": _caso(nodal={0: np.array([0, 0, 0]), 1: np.array([0, 0, -P / 2])})})
    # a força nodal da barra 1 vai nas duas pontas (nó 2 e nó 1); o nó 1 é apoio: só P/2 no topo… somar P no topo:
    sol = AE.resolver(M, {"p": _caso(nodal={0: np.array([0, 0, -P / 2]), 1: np.array([0, 0, -P / 2])})})
    # no topo chegaram P (as duas barras deram P/2 cada); nos pés, cargas que vão direto ao apoio
    sen = h / math.hypot(b / 2, h)
    N = AE.esforcos_em(sol["pontas"][0, 0], sol["w"][0, 0], np.array([0.0]))[0, 0]
    assert N == pytest.approx(-P / (2 * sen), rel=1e-6)                       # compressão


def test_equilibrio_e_combinacao_no_modelo_de_porticos():
    """pórtico com bases engastadas: a soma das reações fecha com a carga em cada caso"""
    M = _modelo([[0, 0, 0], [0, 0, 4], [6, 0, 4], [6, 0, 0]], [(0, 1), (1, 2), (2, 3)], [(0, "articulada"), (3, "engastada")])
    casos = {"q": _caso(dist={1: np.array([0, 0, -5.0])}), "h": _caso(nodal={0: np.array([1.5, 0, 0])})}
    sol = AE.resolver(M, casos)
    Rz = sum(r[2, 0] for r in sol["reacoes"].values())
    Rx = sum(r[0, 1] for r in sol["reacoes"].values())
    assert Rz == pytest.approx(5.0 * 6, rel=1e-6)
    assert Rx == pytest.approx(-3.0, rel=1e-6)
