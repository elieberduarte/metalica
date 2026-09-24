# -*- coding: utf-8 -*-
"""Peso dos perfis dobrados com o desconto das dobras (saida/dobras.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import dobras  # noqa: E402


def test_desconto_por_dobra_na_linha_media():
    # ri = t, linha neutra no meio da espessura: (4 − 0,75·π)·t
    assert abs(dobras.desconto_por_dobra(2.0) - 3.2876) < 1e-3


def test_bate_com_a_tabela_da_nbr_6355():
    # U 150×50×2,25 = 4,28 kg/m e Ue 150×50×17×2,25 = 4,75 kg/m na norma
    assert abs(dobras.pesos("U 150x50x2,25")["kg_m_desconto"] - 4.28) < 0.01
    assert abs(dobras.pesos("C150X50X17X2.25")["kg_m_desconto"] - 4.75) < 0.01


def test_teorico_pela_soma_externa_e_desenvolvido():
    r = dobras.pesos("U150X50X2.28", comprimento_m=10.0)
    assert r["soma_externa"] == 250.0 and r["dobras"] == 2
    assert abs(r["desenvolvido"] - (250.0 - 2 * dobras.desconto_por_dobra(2.28))) < 0.1
    assert abs(r["peso_teorico"] - 250.0 * 2.28 * 7.85e-3 * 10.0) < 1e-6
    assert r["peso_desconto"] < r["peso_teorico"]


def test_bitola_e_familias():
    assert dobras.geometria("C127X50X17X#14")["t"] == 2.0          # #14 = 2,00 mm (fábrica)
    assert dobras.geometria("C127X50X17X#14")["familia"] == "UE"
    assert dobras.geometria("L50X50X2.25")["dobras"] == 1


def test_laminados_e_barras_ficam_fora():
    for nome in ("L1.1/4''X1/8''", "W150X13.00", "FE RED 1/2''", "BARRA ROSCADA Ø 5/8''", "PLATE 400x120x13"):
        assert dobras.geometria(nome) is None, nome
