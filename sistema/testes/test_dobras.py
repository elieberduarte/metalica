# -*- coding: utf-8 -*-
"""Peso dos perfis dobrados com o desconto das dobras (saida/dobras.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saida import dobras  # noqa: E402


def test_desconto_por_dobra_na_linha_media():
    # ri = t, linha neutra no meio da espessura: (4 − 0,75·π)·t
    assert abs(dobras.desconto_por_dobra(2.0) - 3.2876) < 1e-3


def test_regra_de_peso_da_fabrica():
    """a planilha do usuário (14/10): Ue 200×75×25×2,25 = (0,2 + 2·0,075 + 2·0,025 − 8·0,00225) × 18 = 6,876 kg/m —
    2·t por dobra e 8 kg/m² por mm de espessura"""
    assert abs(dobras.pesos("Ue 200x75x25x2,25")["kg_m_desconto"] - 6.876) < 1e-3
    assert abs(dobras.pesos("U 150x50x2,25")["kg_m_desconto"] - (250 - 4 * 2.25) * 2.25 * 8e-3) < 1e-3
    assert abs(dobras.kg_m_do_formado("Ue", 200, 75, 25, 2.25) - 6.876) < 1e-3
    assert abs(dobras.kg_m_do_formado("L", 0, 50, 0, 3.0, b2=50) - (100 - 2 * 3.0) * 3.0 * 8e-3) < 1e-6
    from nucleo import catalogo
    it = catalogo.item("Ue 200×75×25×2,25")
    assert abs(it.massa - 6.876) < 1e-3 and it.dados.get("massa_tabela") and "8 kg/m²" in it.dados.get("massa_regra", "")


def test_teorico_pela_soma_externa_e_desenvolvido():
    r = dobras.pesos("U150X50X2.28", comprimento_m=10.0)
    assert r["soma_externa"] == 250.0 and r["dobras"] == 2
    assert abs(r["desenvolvido"] - (250.0 - 2 * 2 * 2.28)) < 0.1
    assert abs(r["peso_teorico"] - 250.0 * 2.28 * 8e-3 * 10.0) < 1e-6
    assert r["peso_desconto"] < r["peso_teorico"]


def test_bitola_e_familias():
    assert dobras.geometria("C127X50X17X#14")["t"] == 2.0          # #14 = 2,00 mm (fábrica)
    assert dobras.geometria("C127X50X17X#14")["familia"] == "UE"
    assert dobras.geometria("L50X50X2.25")["dobras"] == 1


def test_laminados_e_barras_ficam_fora():
    for nome in ("L1.1/4''X1/8''", "W150X13.00", "FE RED 1/2''", "BARRA ROSCADA Ø 5/8''", "PLATE 400x120x13"):
        assert dobras.geometria(nome) is None, nome


def test_nome_com_bitola_e_mm():
    """o nome para leitura: a bitola e a espessura em mm juntas (pedido do usuário, 05/10)"""
    from saida.dobras import com_bitola_e_mm
    assert com_bitola_e_mm("C127X50X17X#14") == "C127X50X17X#14/2.00mm"
    assert com_bitola_e_mm("C150X50X17X2.25") == "C150X50X17X#13/2.25mm"
    assert com_bitola_e_mm("U150X50X2.28") == "U150X50X#13/2.28mm"
    assert com_bitola_e_mm("W150X13.00") == "W150X13.00" and com_bitola_e_mm("FE RED 1/2''") == "FE RED 1/2''"
    assert com_bitola_e_mm("C150X50X17X#13/2.25mm") == "C150X50X17X#13/2.25mm"     # já no formato
