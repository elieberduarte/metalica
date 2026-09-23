# -*- coding: utf-8 -*-
"""Ajustes da 0.7.12: telha arredondada para cima, #14 = 2,00, furos das terças seguindo
os da chapa de suporte (posição e formato)."""
import math
import os

import pytest

from nucleo2d import detalhar as det
from nucleo2d.detalhe.base import arredondar_telha, compra_da_telha
from nucleo3d.modelo import Documento, Solido, Chapa


def test_telha_arredondada_para_cima_de_5_em_5():
    assert arredondar_telha(1449.0) == 1450.0
    assert arredondar_telha(1450.0) == 1450.0
    assert arredondar_telha(1450.02) == 1450.0          # décimo de malha não vira 5 mm
    assert arredondar_telha(1450.3) == 1455.0
    assert arredondar_telha(1891.0) == 1895.0
    assert arredondar_telha(2087.0) == 2090.0

    class P:
        L, comprimento, H, local, peso, saia = 1449.0, 1449.0, 1031.0, None, 10.0, 0.0
    c = compra_da_telha(P())
    assert c["comprimento"] == 1450.0 and c["peso"] == pytest.approx(10.0 * 1450 / 1449)


def test_bitola_14_e_2mm():
    from nucleo.perfis_fabrica import BITOLAS
    assert BITOLAS[14] == 2.0


def _modelo_real():
    import json
    caminho = os.path.join(os.path.dirname(__file__), "..", "projetos", "modelos", "compressores-ar.modelo.json")
    if not os.path.exists(caminho):
        pytest.skip("modelo de exemplo do IFC não está nesta máquina")
    with open(caminho, encoding="utf-8") as f:
        return Documento.de_dict(json.load(f))


def test_furos_da_terca_seguem_a_chapa_de_suporte():
    """A chapinha P36 ganha furos oblongos e um deles anda 10 mm: as terças parafusadas
    nela passam a ter o furo no mesmo lugar e oblongo; repetir não mexe."""
    doc = _modelo_real()
    det.converter_chapas(doc, "P36")
    chapas = [e for e in doc.entidades.values() if isinstance(e, Chapa) and det._marcas(e).get("posicao") == "P36"]
    assert chapas
    for ch in chapas:
        novos = []
        for i, f in enumerate(ch.furos):
            x = float(f["x"]) + (10.0 if i == 0 else 0.0)
            novos.append({"x": x, "y": float(f["y"]), "largura": 25.0, "altura": 13.0})
        ch.furos = novos
    r = det.alinhar_furos_das_barras_as_chapas(doc)
    assert r["barras"] >= 10 and r["oblongos"] >= 20 and "M13" in r["posicoes"]
    e = next(x for x in doc.entidades.values() if isinstance(x, Solido) and det._marcas(x).get("posicao") == "M13")
    pos = det._posicao_bruta(e, "M13")
    pos.tipo_ifc = det._tipo_ifc(e)
    det.analisar(pos)
    oblongos = [f for f in pos.furos if f.tipo == "oblongo" and abs(max(f.larg, f.alt) - 25.0) < 1.0]
    assert len(oblongos) >= 2
    assert det.alinhar_furos_das_barras_as_chapas(doc)["furos"] == 0
