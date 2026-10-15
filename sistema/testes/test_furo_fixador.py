# -*- coding: utf-8 -*-
"""O detalhe da chapa mostra o que entra em cada furo e a folga (15/10, o usuário: "colocar a bitola do parafuso no
detalhe"; padrão de 1,5 mm de folga no mínimo, o furo cotado pelo projetista fica e só é avisado)."""
from saida.detalhamento import Furo, Posicao, mm_da_bitola, polegada_de, FOLGA_MINIMA_FURO


def test_bitolas():
    assert polegada_de(15.875) == '5/8"' and polegada_de(19.05) == '3/4"' and polegada_de(25.4) == '1"'
    assert polegada_de(16.0) == "" and polegada_de(12.0) == ""
    assert abs(mm_da_bitola('1"') - 25.4) < 1e-6 and abs(mm_da_bitola('5/8"') - 15.875) < 1e-6
    assert abs(mm_da_bitola('1.1/4"') - 31.75) < 1e-6 and abs(mm_da_bitola('1 1/4"') - 31.75) < 1e-6
    assert mm_da_bitola("16 mm") == 16.0 and mm_da_bitola("x") == 0.0
    assert FOLGA_MINIMA_FURO == 1.5


def test_rotulo_dos_furos_com_o_que_entra_e_a_folga():
    p = Posicao(marca="A3.1", tipo_ifc="IfcPlate")
    p.furos = [Furo("redondo", 50, 50, d=27, fixador='barra roscada Ø1"', fixador_d=25.4) for _ in range(4)]
    assert p.rotulo_furos_fixadores() == ['4x Ø27 – barra roscada Ø1" (folga 1,6)']
    # o furo justo (o Ø14 da arruela, cotado no projeto) sai avisado; o furo sem fixador achado, só com a medida
    p.furos = [Furo("redondo", 0, 0, d=14, fixador='chumbador Ø1/2"', fixador_d=12.7), Furo("redondo", 0, 0, d=18)]
    assert p.rotulo_furos_fixadores() == ['1x Ø14 – chumbador Ø1/2" (folga 1,3 < 1,5)', "1x Ø18"]
    # oblongo: a folga pela largura menor
    p.furos = [Furo("oblongo", 0, 0, larg=31, alt=14, fixador='parafuso Ø1/2"', fixador_d=12.7)]
    assert p.rotulo_furos_fixadores() == ['1x OBL 31x14 – parafuso Ø1/2" (folga 1,3 < 1,5)']
    # sem fixador nenhum: vazio (fica o rótulo de sempre)
    p.furos = [Furo("redondo", 0, 0, d=18)]
    assert p.rotulo_furos_fixadores() == []
