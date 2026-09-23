# -*- coding: utf-8 -*-
"""Perfis pelo nome de fábrica (TecnoMETAL) e o U simples na NBR 14762."""
import os
import sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from nucleo import materiais, nbr8800, nbr14762                      # noqa: E402
from nucleo.perfis_fabrica import (perfil_de_fabrica, polegadas_mm,  # noqa: E402
                                   secao_frio, tipo_de_verificacao)


@pytest.mark.parametrize("texto, mm", [
    ("1/8", 3.175), ('1/8"', 3.175), ("1.1/4", 31.75), ("1 1/4''", 31.75), ("2", 50.8), ("2 1/2''", 63.5),
])
def test_polegadas(texto, mm):
    assert abs(polegadas_mm(texto) - mm) < 1e-6


def test_u_simples_formado_a_frio():
    p = perfil_de_fabrica("U92X40X2.25")
    assert p is not None and p.tipo == "Ue" and p.nome == "U 92×40×2,25 (FF)"
    assert 3.4 < p.A < 3.9               # linha média: (92 + 2·40 − cantos)·2,25 mm ≈ 3,7 cm²
    assert p.rx > p.ry > 0
    assert tipo_de_verificacao(p) == "frio"
    sec = secao_frio(p)
    assert sec.d == 0 and sec.d_plano == 0
    # sem enrijecedor: mesa AL (k = 0,43) e nenhum modo distorcional
    tens = nbr14762.tensoes_criticas_locais(sec, "compressao")
    assert tens["k_mesa"] == pytest.approx(0.43)
    assert nbr14762.forca_critica_distorcional(sec) == float("inf")
    v = nbr14762.compressao_mrd(sec, "CIVIL 300", N_Sd=20, KxLx=150, KyLy=150)
    assert 0 < v.Rd < sec.A * 30.0 / 1.10
    ef = nbr14762.secao_efetiva(sec, "CIVIL 300", "compressao")
    assert 0 < ef["Aef"] < sec.A


def test_ue_e_catalogo():
    p = perfil_de_fabrica("C150X75X20X2.25")
    assert p.nome == "Ue 150×75×20×2,25" and p.tipo == "Ue" and 7.0 < p.A < 7.6
    assert perfil_de_fabrica("W150X13.00").nome == "W 150×13,0"
    assert perfil_de_fabrica("TQ50X50X2.00").tipo == "tubo"


def test_cantoneiras():
    assert perfil_de_fabrica("L2''X1/8''").nome == 'L 2"×1/8"'            # do catálogo
    assert perfil_de_fabrica("L 2 1/2'' X 1/4' '").nome == 'L 2½"×1/4"'    # grafia solta do exportador
    fria = perfil_de_fabrica("L50X50X2.25")
    assert fria.tipo == "L" and fria.dados.get("formado_a_frio") and fria.rmin < fria.ry
    desigual = perfil_de_fabrica("L50X75X2.25")
    assert desigual.dados["b"] == 75 and desigual.dados["b2"] == 50
    r = nbr8800.compressao(fria, "CIVIL 300", Lx=120, N_Sd=10, cantoneira_simplificada=True)
    assert r.razao > 0


def test_redondas_e_nao_barras():
    fe = perfil_de_fabrica("FE RED 3/8''")
    assert fe.tipo == "barra" and abs(fe.dados["d"] - 9.525) < 0.01 and not fe.dados.get("rosqueada")
    br = perfil_de_fabrica("BARRA ROSCADA Ø 5/8''")
    assert br.dados.get("rosqueada") and abs(br.dados["d"] - 15.875) < 0.01
    for nome in ("TELHA TP40 0.50MM", "PLATE 80x80x8", "BOLT (A) 12x35", ""):
        assert perfil_de_fabrica(nome) is None
    assert perfil_de_fabrica("XYZ 12") is None


def test_aco_civil_300():
    a = materiais.aco("CIVIL 300")
    assert a.fy == 30.0 and a.fu == 40.0
