# -*- coding: utf-8 -*-
"""Espessura pela bitola no nome do perfil (#14) e telha pela chapa inteira de compra."""
from nucleo import perfis_fabrica as pf
from nucleo2d.detalhe.base import compra_da_telha, LARGURA_COMPRA_TELHA
from saida.detalhamento import Posicao


def test_bitola_14_no_nome_do_perfil():
    p = pf.perfil_de_fabrica("C127X50X17X#14")
    assert p is not None
    assert p.dados["d"] == 127.0 and p.dados["bf"] == 50.0 and abs(p.dados["t"] - 2.0) < 1e-9


def test_bitola_colada_na_medida_anterior():
    p = pf.perfil_de_fabrica("C127X50X17#14")          # sem o X antes da bitola
    assert p is not None and abs(p.dados["t"] - 2.0) < 1e-9


def test_bitola_desconhecida_nao_vira_numero():
    assert pf.perfil_de_fabrica("C127X50X17X#99") is None


def _telha(pontos, L=3000.0, H=1031.0):
    return Posicao(marca="T", tipo_ifc="IfcPlate", classe="telha", L=L, H=H, peso=10.0,
                   local=[(x, y, 0.0) for x, y in pontos])


def test_telha_retangular_nao_tem_corte():
    c = compra_da_telha(_telha([(0, 0), (3000, 0), (3000, 1031), (0, 1031)]))
    assert not c["cortada"]
    assert c["largura"] == LARGURA_COMPRA_TELHA == 980.0
    assert c["peso"] == 10.0


def test_telha_cortada_em_angulo_pesa_a_chapa_inteira():
    # trapézio: uma ponta cortada em ângulo, metade de um triângulo de 500 mm de base
    c = compra_da_telha(_telha([(0, 0), (3000, 0), (2500, 1031), (0, 1031)]))
    assert c["cortada"]
    assert c["comprimento"] == 3000.0
    area = 3000.0 * 1031.0 - 0.5 * 500.0 * 1031.0
    assert abs(c["peso"] - 10.0 * 3000.0 * 1031.0 / area) < 1e-6
