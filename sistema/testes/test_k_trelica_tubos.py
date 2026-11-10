# -*- coding: utf-8 -*-
"""O K = 0,9 da ABNT NBR 16239:2013, 4.8 só vale na treliça de tubos (com alma). Residencial Madrid, opção B (calculista,
10/11): os espigões, banzos inclinados e a cumeeira de uma cobertura sem tesouras têm papel "banzo superior" e ganhavam
K = 0,9 — o E.2 (TR 150×100×2,65, L 5,89) com Nc,Rd 174 em vez de 158 kN."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nucleo3d import verificacao_pecas as VP  # noqa: E402


def _caso(com_alma):
    barras = [{"a": 0, "b": 1, "elemento": "trelica", "grupo": "T1", "papel_trelica": "banzo_sup"},
              {"a": 1, "b": 2, "elemento": "trelica", "grupo": "T1", "papel_trelica": "banzo_sup"}]
    pecas = [{"barras": [0, 1], "perfil": "TR 150×100×2,65", "papel": "banzo_sup", "nos": [0, 1, 2], "Lx": 5.89, "Ly": 5.89}]
    if com_alma:
        barras.append({"a": 1, "b": 3, "elemento": "trelica", "grupo": "T1", "papel_trelica": "montante"})
        pecas.append({"barras": [2], "perfil": "TQ 100×100×3,00", "papel": "montante", "nos": [1, 3], "Lx": 0.8, "Ly": 0.8})
    return {"barras": barras}, pecas


def test_banzo_sem_alma_fica_com_k_1():
    M, pecas = _caso(com_alma=False)
    VP._k_trelicas_tubulares(M, pecas)
    assert "K" not in pecas[0] and abs(pecas[0]["Lx"] - 5.89) < 1e-9


def test_treliça_de_tubos_com_alma_segue_com_k_09():
    M, pecas = _caso(com_alma=True)
    VP._k_trelicas_tubulares(M, pecas)
    assert pecas[0]["K"] == 0.9 and abs(pecas[0]["Lx"] - 0.9 * 5.89) < 1e-9
