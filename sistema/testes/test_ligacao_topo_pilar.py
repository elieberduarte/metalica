"""A ligação da viga apoiada no topo do pilar por duas chapas parafusadas (nucleo/ligacao_topo_pilar.py), o chumbador
em J (NBR 6118:2023, 9.4.2) e a base com abas (nucleo/base_pilar.py): contas de mão pela NBR 8800:2024."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nucleo import base_pilar as B  # noqa: E402
from nucleo import ligacao_topo_pilar as LT  # noqa: E402

TC141 = {"nome": "TC 141,3×4,5", "tipo": "tubo", "d": 141.3, "bf": 0.0, "tw": 4.5, "tf": 4.5}
W200 = {"nome": "W 200×41,7", "tipo": "I", "d": 205.0, "bf": 166.0, "tw": 7.2, "tf": 11.8, "r": 12.0}
W360 = {"nome": "W 360×44,6", "tipo": "I", "d": 352.0, "bf": 171.0, "tw": 6.9, "tf": 9.8}


def test_forcas_no_grupo_de_parafusos():
    pts = LT.grupo(4, 200.0, 200.0)
    # só momento em torno de y (tração variando em x): F = M·x/Σx² = M/(4·100)
    ft, fv = LT.forcas_nos_parafusos(pts, 0.0, 0.0, 40e6, 0.0, 0.0)
    assert ft == pytest.approx(40e6 * 100 / (4 * 100 ** 2))
    # compressão alivia; cortante + torção somam no parafuso do canto
    ft2, _ = LT.forcas_nos_parafusos(pts, 80e3, 0.0, 40e6, 0.0, 0.0)
    assert ft2 == pytest.approx(ft - 80e3 / 4)
    _, fv2 = LT.forcas_nos_parafusos(pts, 0.0, 0.0, 0.0, 8e3, 4e6)
    r2 = 4 * 2 * 100 ** 2
    assert fv2 == pytest.approx(math.hypot(8e3 / 4 + 4e6 * 100 / r2, 4e6 * 100 / r2))


def test_alavanca_pela_6_3_5():
    Ft0, Ftrd, b, a, db, df, fu = 30e3, 90e3, 40.0, 35.0, 19.05, 20.6, 400.0
    r = LT.alavanca(Ft0, Ftrd, b, a, 32.0, 200.0, db, df, fu, 16.0)
    p = min(32.0, 1.75 * b) + min(100.0, 1.75 * b)
    delta = 1 - df / p
    beta = ((min(a, 1.25 * b) + 0.5 * db) / (b - 0.5 * db)) * (Ftrd / Ft0 - 1)
    alfa = 1.0 if beta >= 1 else min(1.0, beta / (delta * (1 - beta)))
    assert r["p"] == pytest.approx(p) and r["beta"] == pytest.approx(beta)
    assert r["t_rigida"] == pytest.approx(math.sqrt(4 * (b - 0.5 * db) * Ft0 * 1.10 / (p * fu)))
    assert r["t_flexivel"] == pytest.approx(math.sqrt(4 * (b - 0.5 * db) * Ft0 * 1.10 / (p * fu * (1 + delta * alfa))))
    assert r["t_flexivel"] <= r["t_rigida"]
    # tração acima da resistência: β < 0, trocar o parafuso
    assert not LT.alavanca(100e3, 90e3, b, a, 32.0, 200.0, db, df, fu, 16.0)["ok_parafuso"]


def test_alma_da_viga_5_7_3_e_5_7_4():
    r = LT.alma_da_viga(W200, 100e3, 150.0, False, 345.0)
    k = 11.8 + 12.0
    assert r["F_esc"] == pytest.approx(1.10 * (5 * k + 150) * 345 * 7.2 / 1.10 / 1e3)
    enr = 0.66 * 7.2 ** 2 / 1.10 * (1 + 3 * (150 / 205) * (7.2 / 11.8) ** 1.5) * math.sqrt(200000 * 345 * 11.8 / 7.2) / 1e3
    assert r["F_enr"] == pytest.approx(enr)
    r2 = LT.alma_da_viga(W200, 100e3, 150.0, True, 345.0)            # na ponta: 2,5k e o enrugamento de ℓn/d > 0,2
    assert r2["F_esc"] == pytest.approx(1.10 * (2.5 * k + 150) * 345 * 7.2 / 1.10 / 1e3)


def test_dimensionar_a_ligacao_no_topo_do_tubo():
    combs = [{"comb": "a", "N": 95.8, "Mz": 10.2, "My": 0.0, "V": 2.5, "T": 0.0},
             {"comb": "b", "N": -81.8, "Mz": 5.0, "My": 3.0, "V": 2.0, "T": 0.0}]
    r = LT.dimensionar(TC141, W200, combs, viga_continua=True, viga_ao_longo="x")
    assert r["ok"] and r["n"] == 4 and r["pior"]["int"] <= 1.0
    assert r["t_pilar"] >= r["pior"]["tp"] - 1e-9 and r["perna_solda"] >= 3.0


def test_chumbador_j_pela_6118():
    j = B.chumbador_j(50.0, 19.0, 25.0, 450.0)
    fctd = 0.7 * 0.3 * 25 ** (2 / 3) / 1.4
    fyd = 250 / 1.15
    lb = max(19 / 4 * fyd / fctd, 25 * 19)
    As = math.pi * 19 ** 2 / 4
    lb_nec = max(0.7 * lb * 50e3 / (As * fyd), max(0.3 * lb, 190.0, 100.0))
    assert j["fbd"] == pytest.approx(fctd) and j["lb"] == pytest.approx(lb) and j["lb_nec"] == pytest.approx(lb_nec)
    assert j["ok"] == (lb_nec <= 450.0) and j["ponta_reta_min"] == pytest.approx(38.0) and j["pino_dobramento_min"] == pytest.approx(76.0)


def test_abas_nao_engrossam_a_placa():
    combs = [{"comb": "v", "N": 60.0, "M": 80.0, "V": 15.0}, {"comb": "s", "N": -30.0, "M": 40.0, "V": 12.0}]
    sem = B.dimensionar(W360, combs)
    com = B.com_abas(W360, combs, sem["geometria"])
    assert com["tp_min"] <= sem["tp_min"] + 1e-6
