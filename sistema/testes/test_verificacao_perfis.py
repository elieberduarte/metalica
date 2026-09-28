# -*- coding: utf-8 -*-
"""Verificação dos perfis com os esforços do esqueleto (nucleo3d/verificacao_perfis.py): o momento
da barra biapoiada somado ao das pontas, a terça travada pela telha, o banzo em U deitado, a
cantoneira dupla da alma e os três cenários de vento."""
import numpy as np
import pytest

from nucleo3d import esforcos, verificacao_perfis
from nucleo3d.modelo import Documento

from test_analitico import modelo


def _r(papel, perfil, f=None, m0=1.0, L=4.0, duplo=False, deitada=False, combs=None):
    """o resultado de esforços de uma barra só (horizontal, em x), para a verificação"""
    return {"esqueleto": {"nos": [[0.0, 0.0, 0.0], [L * 1000.0, 0.0, 0.0]],
                          "barras": [{"a": 0, "b": 1, "papel": papel, "perfil": perfil, "ids": ["b1"], "duplo": duplo,
                                      "peca": None, "deitada": deitada}]},
            "_usadas": [0], "_L": np.array([L]), "_d": np.array([[L, 0.0, 0.0]]), "_casos": ["PP"],
            "_m0": {"PP": np.array([m0])}, "esforcos": {0: {"PP": list(f or [0.0] * 12)}},
            "combinacoes": combs or [{"nome": "ELU", "fatores": {"PP": 1.25}}]}


def test_momento_da_barra_biapoiada_soma_ao_das_pontas():
    # sem momento nas pontas: o do vão (1 kN·m característico × 1,25)
    v = verificacao_perfis.verificar(Documento(), _r("viga", "W 200×19,3"))
    assert v["barras"][0]["M_kNm"] == pytest.approx(1.25)
    # ponta 1 com −2 (momento negativo, f4) e ponta 2 com −2 (f10 = +2): no meio −2 + 1 = −1; o maior é 2
    f = [0.0] * 12
    f[4], f[10] = -2.0, 2.0
    v = verificacao_perfis.verificar(Documento(), _r("viga", "W 200×19,3", f=f, combs=[{"nome": "E", "fatores": {"PP": 1.0}}]))
    assert v["barras"][0]["M_kNm"] == pytest.approx(2.0)


def test_terca_travada_pela_telha_na_gravidade():
    # o mesmo momento positivo (gravidade) passa melhor que o negativo (sucção, mesa de baixo livre)
    pos = verificacao_perfis.verificar(Documento(), _r("terça", "U 100×40×2,65 (FF)", m0=1.0))["barras"][0]
    neg = verificacao_perfis.verificar(Documento(), _r("terça", "U 100×40×2,65 (FF)", m0=-1.0))["barras"][0]
    assert pos["M_kNm"] == pytest.approx(neg["M_kNm"])
    assert pos["razao"] < neg["razao"]


def test_banzo_em_u_deitado_flete_no_eixo_fraco():
    viga = verificacao_perfis.verificar(Documento(), _r("viga", "U 100×40×2,25 (FF)", L=1.0))["barras"][0]
    banzo = verificacao_perfis.verificar(Documento(), _r("banzo", "U 100×40×2,25 (FF)", L=1.0))["barras"][0]
    assert banzo["MRd_kNm"] < 0.5 * viga["MRd_kNm"]


def test_cantoneira_dupla_resiste_mais_que_duas_simples():
    f = [0.0] * 12
    f[6] = -10.0                                         # 10 kN de compressão
    dupla = verificacao_perfis.verificar(Documento(), _r("diagonal", 'L 1"×1/8"', f=f, L=1.3, duplo=True))["barras"][0]
    assert dupla["NcRd_kN"] > 5.0 and dupla["verificacao"] == "compressão"
    r_sim = verificacao_perfis._Resistencias().de('L 1"×1/8"', "ASTM A36", 130.0, 130.0)
    assert dupla["NcRd_kN"] > 2 * r_sim["Nc"]


def test_tres_cenarios_na_estrutura_inteira():
    doc = modelo()
    r = esforcos.calcular(doc, {"sobrecarga": 0.25}, vento={"v0": 45.0})
    v = verificacao_perfis.verificar_cenarios(doc, r)
    chaves = [c["chave"] for c in v["cenarios"]]
    assert chaves == ["gravidade", "vento_leve", "todas"]
    assert all(c["resumo"]["barras"] == v["cenarios"][0]["resumo"]["barras"] for c in v["cenarios"])
    # mais combinações nunca melhoram a pior razão de uma peça
    for p in v["pecas"]:
        rz = p["razoes"]
        assert rz.get("todas", 0) >= rz.get("vento_leve", 0) - 1e-9 >= rz.get("gravidade", 0) - 2e-9
