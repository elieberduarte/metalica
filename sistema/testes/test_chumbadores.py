# -*- coding: utf-8 -*-
"""Hardbolt na ancoragem da análise pelo critério conservador do usuário (08/10/2026): a carga permissível do
fabricante, sem converter; f_ck, espaçamento e borda pela linha de baixo da tabela, sem interpolar."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import chumbadores as CH                                    # noqa: E402

KN = 9.80665 / 1000.0


def test_permissivel_direto_longe_da_borda():
    r = CH.resistencia("M12", 100, 30)
    assert r["erro"] is None and r["fck_tabela"] == 30
    assert abs(r["T_kN"] - 1275 * KN) < 0.01 and abs(r["V_kN"] - 1055 * KN) < 0.01          # 12,50 e 10,35 kN
    assert any("S ≥ Scr" in a for a in r["avisos"])                                      # sem as distâncias: dito no resultado


def test_fck_cai_para_a_coluna_de_baixo():
    assert CH.resistencia("M12", 100, 35)["fck_tabela"] == 30                            # sem interpolar
    assert CH.resistencia("M12", 100, None)["fck_tabela"] == 20                          # sem f_ck: a menor
    r = CH.resistencia("M12", 100, 50)
    assert r["fck_tabela"] == 40 and any("não recomenda" in a for a in r["avisos"])
    assert CH.resistencia("M12", 100, 15)["erro"]                                        # abaixo de 20: sem valor


def test_espacamento_e_borda_pela_linha_de_baixo():
    # M12: S = 80 mm → linha de 75 (Fn 0,63, Fv 0,81); C = 70 mm → borda tração linha 65 (0,84), corte linha 60 (0,33)
    r = CH.resistencia("M12", 100, 30, S=80, C=70)
    assert abs(r["Fn"] - 0.63 * 0.84) < 1e-3 and abs(r["Fv"] - 0.81 * 0.33) < 1e-3
    assert abs(r["T_kN"] - 1275 * KN * 0.63 * 0.84) < 0.01
    assert CH.resistencia("M12", 100, 30, S=40)["erro"]                                  # abaixo do mínimo (50)


def test_embutimento_fora_da_tabela_e_opcoes():
    assert CH.resistencia("M12", 90, 30)["erro"]
    o = CH.opcoes()
    m16 = next(d for d in o["diametros"] if d["diametro"] == "M16")
    assert m16["embutimentos"] == [95, 125] and m16["Scr"] == 185 and m16["Smin"] == 60 and o["coeficiente"] == 4.0
