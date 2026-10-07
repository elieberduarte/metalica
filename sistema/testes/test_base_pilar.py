"""Base de pilar pela ABNT NBR 8800:2024, 6.7 (nucleo/base_pilar.py) e as bases com as reações da análise
(nucleo3d/bases_analise.py): contas de mão dos casos C1, C3, T1 e T2, a geometria da Tabela 18 (com a Errata 1:2025) e a
reação levada aos eixos do pilar."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo import base_pilar as B  # noqa: E402
from nucleo3d import bases_analise as BA  # noqa: E402

W360 = {"d": 352.0, "bf": 171.0, "tw": 6.9, "tf": 9.8}       # W 360×44,6


def test_geometria_e_bloco_pela_tabela_18():
    g = B.geometria(W360, 1, 6, '1"')
    assert g["lx"] == pytest.approx(352 + 4 * 50) and g["a"] == pytest.approx(176 + 50)
    assert g["ly"] == pytest.approx(max(2 * 100 + 2 * 50, 171 + 25))
    assert g["m"] == pytest.approx((552 - 0.95 * 352) / 2) and g["n"] == pytest.approx((300 - 0.8 * 171) / 2)
    k = B.bloco(g)                                              # nota e com a errata: N_b,mín = 900 para 1"
    assert k["Nb"] == pytest.approx(max(900, 552 + 2 * 60, 552 + 2 * (160 - 50)))
    assert k["Bb"] == pytest.approx(max(300 + 2 * 60, 300 + 2 * (160 - 50)))
    assert k["Ab"] == pytest.approx(max(465 + 100, k["Nb"]))
    assert B.TABELA_18['1.1/4"']["Nb_min"] == 1100 and B.TABELA_18['2"']["Nb_min"] == 1800      # errata


def test_caso_c1_a_mao():
    g = B.geometria(W360, 1, 4, '1"')
    r = B.caso(g, 300.0, 0.0, 10.0, 25.0, 250.0)
    A1 = g["lx"] * g["ly"]
    blk = B.bloco(g)
    A2 = A1 * min(blk["Nb"] / g["lx"], blk["Bb"] / g["ly"]) ** 2
    sRd = min(0.85 * 25 / 1.4 * math.sqrt(A2 / A1), 1.7 * 25 / 1.4)
    X = 4 * 352 * 171 / (352 + 171) ** 2 * 300e3 / (A1 * sRd)
    lam = min(2 * math.sqrt(X) / (1 + math.sqrt(1 - X)), 1.0)
    tp = max(g["m"], g["n"], lam * g["n0"]) * math.sqrt(2 * (300e3 / A1) / (250 / 1.1))
    assert r["caso"] == "C1" and r["tp_min"] == pytest.approx(tp, rel=1e-9)
    assert r["V_Rd"] == pytest.approx(min(0.45 * 300 / 1.35, min(0.2 * 25 / 1.4, 4.0) * A1 / 1e3), rel=1e-9)


def test_caso_c3_fecha_o_equilibrio():
    """grande excentricidade: a compressão no concreto (σc,Rd·ℓc·ℓy) = N + a tração dos chumbadores de um lado, e o
    momento em torno da linha dos tracionados fecha"""
    g = B.geometria(W360, 1, 6, '1"')
    N, M = 96.3, 150.0
    r = B.caso(g, N, M, 20.0, 25.0, 250.0)
    assert r["caso"] == "C3"
    C = r["sigma_c_Rd"] * r["lc"] * g["ly"] / 1e3              # kN
    T = r["Ft"] * g["nb"] / 2                                   # kN, os n_b/2 do lado tracionado
    assert C == pytest.approx(N + T, rel=1e-9)
    k = g["lx"] / 2 + g["a"]                                    # mm: da linha tracionada à borda comprimida
    assert C * (k - r["lc"] / 2) == pytest.approx(N * (M * 1e3 / N + g["a"]), rel=1e-9)
    assert r["db_min"] == pytest.approx(math.sqrt(4 * r["Ft"] * 1e3 / (0.75 * math.pi * 400 / 1.35)), rel=1e-9)


def test_casos_t1_e_t2():
    g = B.geometria(W360, 1, 4, '7/8"')
    r1 = B.caso(g, -80.0, 0.0, 5.0, 25.0, 250.0)
    assert r1["caso"] == "T1" and r1["Ft"] == pytest.approx(80.0 / 4) and r1["V_Rd"] == 0.0
    M = 0.5 * 80.0 * g["a"] / 1e3                               # e = a/2 < a: T2
    r2 = B.caso(g, -80.0, M, 5.0, 25.0, 250.0)
    assert r2["caso"] == "T2" and r2["Ft"] == pytest.approx(80.0 / 4 + M * 1e3 / (g["a"] * 4))
    tp = math.sqrt(2 * 4 * r2["Ft"] * 1e3 * (g["m"] - g["a1"]) / (g["ly"] * 250 / 1.1))
    assert r2["tp_min"] == pytest.approx(tp, rel=1e-9)


def test_dimensionar_escolhe_a_mais_leve_que_passa():
    combs = [{"comb": "G", "N": 200.0, "M": 0.0, "V": 10.0}, {"comb": "V", "N": 60.0, "M": 40.0, "V": 15.0},
             {"comb": "S", "N": -30.0, "M": 20.0, "V": 12.0}]
    r = B.dimensionar(W360, combs)
    assert r["ok"] and r["tp"] >= r["tp_min"]
    # toda geometria mais leve que também passa teria sido escolhida
    for d in B.DIAMETROS:
        for nb in (4, 6, 8):
            v = B.verificar(W360, combs, 1, nb, d)
            if v["ok"]:
                g = v["geometria"]
                peso = v["peso_placa_kg"] + nb * math.pi * g["db"] ** 2 / 4 * (v["tabela"]["h1"] + 300) * 7.85e-6
                assert peso >= r["peso_kg"] - 0.05


def test_reacao_nos_eixos_do_pilar():
    """o momento em torno do eixo forte é a componente do vetor momento na direção ez da seção (a largura)"""
    r = {"barras": [{"a": 0, "b": 1, "papel": "pilar", "perfil": "W 360×44,6", "ey": [1, 0, 0], "ez": [0, 1, 0]}],
         "apoios": [{"no": 0, "tipo": "engastada", "chave": "0,0"}],
         "combinacoes": {"ELU V": {"tipo": "ELU"}, "ELS V": {"tipo": "ELS"}},
         "por_comb": {"ELU V": {"reacoes": {"0": [3.0, 4.0, 50.0, 10.0, 80.0, 1.0]}}, "ELS V": {"reacoes": {"0": [0] * 6}}}}
    e = BA.reacoes_por_base({"": r})["0,0"]
    assert len(e["combinacoes"]) == 1
    c = e["combinacoes"][0]
    assert c["N"] == 50.0 and c["V"] == pytest.approx(5.0) and c["M"] == pytest.approx(80.0) and c["M_fraco"] == pytest.approx(10.0)


TC141 = {"nome": "TC 141,3×4,5", "tipo": "tubo", "d": 141.3, "bf": 0.0}


def test_base_de_pilar_tubular_pela_nbr_16239():
    """C1 à mão pela 8.2.2-a (ℓ_máx = máx(m, n), V_Rd sem γ_a2) e a placa circular tipo 3 (n_b,eq = 2/3·n_b)"""
    g = B.geometria_tubo(TC141, 2, 4, '7/8"')
    assert g["lx"] == pytest.approx(141.3 + 4 * 45) and g["m"] == pytest.approx((g["lx"] - 0.8 * 141.3) / 2)
    assert g["ly"] == pytest.approx(max(90 + 90, 141.3 + 25)) and g["a"] == pytest.approx(141.3 / 2 + 45)
    r = B.caso(g, 120.0, 0.0, 5.0, 25.0, 250.0)
    s = 120e3 / (g["lx"] * g["ly"])
    assert r["caso"] == "C1" and r["tp_min"] == pytest.approx(max(g["m"], g["n"]) * math.sqrt(2 * s / (250 / 1.1)), rel=1e-9)
    assert r["V_Rd"] == pytest.approx(min(0.45 * 120.0, min(0.2 * 25 / 1.4, 4.0) * g["lx"] * g["ly"] / 1e3), rel=1e-9)
    g3 = B.geometria_tubo(TC141, 3, 8, '7/8"')
    assert g3["nb_eq"] == pytest.approx(16 / 3) and g3["lx"] == pytest.approx(0.9 * (141.3 + 180))
    # tração com momento pequeno: T2 com F_t = N/n_b + M/(a·n_b,eq)
    r2 = B.caso(g, -60.0, 3.0, 5.0, 25.0, 250.0)
    assert r2["caso"] == "T2" and r2["Ft"] == pytest.approx(60 / 4 + 3e3 / (g["a"] * 4), rel=1e-9)
    v = B.dimensionar(TC141, [{"comb": "a", "N": 97.3, "M": 0.5, "V": 5}, {"comb": "b", "N": -80.6, "M": 3.0, "V": 4}], tipos=(2, 3))
    assert v["ok"] and v["norma"].startswith("NBR 16239")
