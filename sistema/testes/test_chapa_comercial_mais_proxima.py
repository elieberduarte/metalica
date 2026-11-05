# -*- coding: utf-8 -*-
"""A chapa do resumo de compra pela regra do usuário de 05/11 (via GESTÃO): de 3/16" para cima, a comercial MAIS PRÓXIMA,
mesmo mais fina, e o kg pela comercial; empate, a maior; abaixo de 4,75, a bitola (a mesma ou a próxima acima) — a mesma
régua da aba Orçamento (`saida.orcamento.chapa_do_orcamento`, uma tabela só).

Antes o resumo usava "a mesma ou a próxima acima" numa série própria: a CH 16 virava 19,05 (Vicente −168 kg, Kaefer −124,
ADM −106 na compra) e o 1/4" saía 6,30 no resumo e 6,35 no orçamento. E a régua do orçamento levava a chapa acima da maior
da série para 76,2 (a de 146,5 mm do Heliponto R00: −3.300 kg) e a #7 de 4,50 para 4,75."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from saida.orcamento import chapa_do_orcamento  # noqa: E402
from saida.resumos import _chapas_por_rotulo  # noqa: E402


@pytest.mark.parametrize("t, tc, rotulo", [
    (15.0, 16.0, '16,00mm - 5/8"'), (20.0, 19.1, '19,10mm - 3/4"'), (16.0, 16.0, '16,00mm - 5/8"'),
    (6.3, 6.35, '6,35mm - 1/4"'), (10.0, 9.5, '9,50mm - 3/8"'), (28.0, 25.4, '25,40mm - 1"'), (31.75, 31.8, '31,80mm - 1.1/4"'),
    (4.5, 4.5, '#7 - 4,50mm'), (3.0, 3.0, '#11 - 3,00mm - 1/8"'), (146.5, 146.5, '146,50mm'),
])
def test_a_chapa_da_compra_e_a_comercial_mais_proxima(t, tc, rotulo):
    j = _chapas_por_rotulo([{"espessura": t, "material": "ASTM A36", "peso": 10.0, "pecas": 2, "area_m2": 1.0}])[0]
    assert abs(j["t"] - tc) < 1e-6 and j["rotulo"] == rotulo, (j["t"], j["rotulo"])
    assert abs(j["kg_compra"] - tc * 7.85) < 1e-6                          # 1 m² pela comercial
    assert abs(chapa_do_orcamento(t)[0] - tc) < 1e-6                       # a mesma régua da aba Orçamento


def test_fora_da_serie_fica_a_do_projeto_e_diz():
    assert chapa_do_orcamento(146.5) == (146.5, "CH 146,5 (fora da série comercial: espessura do projeto)")
    assert chapa_do_orcamento(80.0)[0] == 76.2                              # dentro de meio passo: a maior da série
