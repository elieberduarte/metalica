# -*- coding: utf-8 -*-
"""O comprimento da telha reta de 5 em 5 cm, sempre para cima, no sistema todo (usuário, 13/11, o padrão do Fábio: a
relação, a compra, o resumo e a lista; era de 5 em 5 mm). A multidobra continua no desenvolvido exato (o passo fino) e a
cumeeira na chapa de 1,00 m.

Os casos são os da Sala de Compressores (SOORO COMPRESSORES N.2, 13/11): TL9 2.675 → 2.700; TL2 960 → 1.000; TL18
8.050 fica igual. Os comprimentos do modelo abaixo caem nos intervalos que davam aqueles números no passo de 5 mm."""
import pytest

from nucleo2d.detalhe.base import PASSO_DOBRADA, PASSO_TELHA, arredondar_telha, compra_da_telha


class _Pos:
    classe = "telha"
    perfil = ""
    H, local, peso, saia = 1031.0, None, 10.0, 0.0

    def __init__(self, L):
        self.L = self.comprimento = L


@pytest.mark.parametrize("nome, modelo, antes, agora", [
    ("TL9", 2671.4, 2675.0, 2700.0),
    ("TL2", 957.2, 960.0, 1000.0),
    ("TL18", 8047.9, 8050.0, 8050.0),
])
def test_casos_da_sala_de_compressores(nome, modelo, antes, agora):
    assert arredondar_telha(modelo, 5.0) == antes                     # o que a Sala tinha
    c = compra_da_telha(_Pos(modelo))
    assert c["comprimento"] == agora, nome
    assert c["peso"] == pytest.approx(10.0 * agora / modelo)          # o peso acompanha a chapa comprada


def test_sempre_para_cima_e_nunca_um_passo_a_mais_por_decimo():
    assert PASSO_TELHA == 50.0
    assert arredondar_telha(3101.7) == 3150.0       # o oitão do CD Bom Dia: o múltiplo de 50 logo acima
    assert arredondar_telha(3100.0) == 3100.0
    assert arredondar_telha(3100.04) == 3100.0      # o décimo da malha não vira 3150
    assert arredondar_telha(0.0) == 0.0


def test_a_dobrada_fica_no_passo_fino():
    # as retas da multidobra (o desenvolvido exato) e as pernas da cumeeira
    assert PASSO_DOBRADA == 5.0
    assert arredondar_telha(1576.3, PASSO_DOBRADA) == 1580.0
    assert arredondar_telha(423.0, PASSO_DOBRADA) == 425.0


# ---------------------------------------------------------------------------------------------------------------------
# O mm inteiro MAIS PRÓXIMO antes do passo de 50, só na telha reta (usuário, 14/11 ~12h35, "Ok, concordo", pelo GESTÃO N.10):
# com o passo de 50 o ruído da geometria virava 5 cm de telha — no Depósito Químico 7 das 97 TL1 medem 1.550,1 no corte, a
# 0,05 mm de virar 1.600 (97 × 50 = 4,85 m de telha a mais). A conta antiga só perdoava 0,05 mm (1.550,06 → 1.600).
@pytest.mark.parametrize("modelo, compra", [
    (1550.00, 1550.0),
    (1550.06, 1550.0),          # o ruído do Depósito: antes 1.600
    (1550.49, 1550.0),
    (1550.50, 1600.0),          # meio mm sobe (o mais próximo, empate para cima: a regra do maior)
    (1550.6, 1600.0),
    (1551.0, 1600.0),
    (1550.4999999999, 1600.0),  # o ponto flutuante de um 1.550,5 de verdade: conta como 1.550,5 (até 1e-6 mm)
    (1550.5000000001, 1600.0),
    (1550.4990, 1550.0),        # um milésimo abaixo do meio mm é medida, não ruído: desce
])
def test_mm_inteiro_mais_proximo_antes_do_passo_de_50(modelo, compra):
    assert arredondar_telha(modelo) == compra
    c = compra_da_telha(_Pos(modelo))
    assert c["comprimento"] == compra                                   # a lista, a compra, o resumo e o orçamento
    assert c["peso"] == pytest.approx(10.0 * compra / modelo)


def test_a_dobrada_nao_muda_com_o_mm_mais_proximo():
    # a multidobra e a cumeeira seguem a conta de antes (DET-03: o desenvolvido exato, para cima)
    assert arredondar_telha(2223.2, PASSO_DOBRADA) == 2225.0
    assert arredondar_telha(2220.06, PASSO_DOBRADA) == 2225.0           # no passo fino o 0,06 continua subindo
    assert arredondar_telha(2220.04, PASSO_DOBRADA) == 2220.0
