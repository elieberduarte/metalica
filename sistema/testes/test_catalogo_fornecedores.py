# -*- coding: utf-8 -*-
"""Catálogos dos fornecedores no catálogo de peças e as seções Z e cartola."""
import math

import pytest

from nucleo import catalogo, secoes_frio, nbr14762


def test_z_e_cartola_tem_propriedades_coerentes():
    ze = secoes_frio.propriedades("Ze", 200, 75, 20, 2.0)
    z45 = secoes_frio.propriedades("Z45", 200, 75, 20, 2.0)
    cr = secoes_frio.propriedades("Cr", 100, 50, 20, 2.0)
    # área ≈ desenvolvimento da linha média × espessura (cantos arredondados tiram um pouco)
    desenv = (200 - 2) + 2 * (75 - 2) + 2 * (20 - 1)
    assert ze["A"] == pytest.approx(desenv * 2.0 / 100, rel=0.03)
    assert ze["massa"] == pytest.approx(ze["A"] * 0.785, rel=1e-6)
    # o Z é simétrico em relação a um ponto: produto de inércia não nulo, centro de torção
    # no centroide, eixos principais inclinados
    assert abs(ze["Ixy"]) > 1.0
    assert ze["x0"] == 0.0 and ze["y0"] == 0.0
    assert ze["I1"] >= ze["Ix"] >= ze["I2"] > 0
    assert 0 < abs(ze["alfa"]) < 45
    # o enrijecedor a 45° abre para fora, longe da alma: mais Iy que o de 90°
    assert z45["Iy"] > ze["Iy"]
    # a cartola é simétrica: sem produto de inércia
    assert abs(cr["Ixy"]) < 1e-6
    assert cr["J"] == pytest.approx(cr["A"] * (0.2 ** 2) / 3, rel=1e-6)


def test_u_simples_usa_a_mesa_inteira():
    # U 100×50×2: linha média da mesa até a face externa da alma oposta (bf), não bf − t/2
    s = nbr14762.propriedades_u(100, 50, 2.0)
    assert s.A == pytest.approx(((100 - 2) + 2 * (50 - 1)) * 0.2 / 10 - 0.02, abs=0.08)


def test_familias_novas_no_catalogo():
    r = catalogo.resumo()
    for fam in ("Ze", "Z45", "Cr", "telha"):
        assert r["familias"].get(fam, 0) > 10, fam
    assert r["familias"]["tubo"] > 1000
    assert r["familias"]["I"] > 100


def test_busca_pela_bitola_e_apelido():
    nomes = [i.nome for i in catalogo.buscar("127X50X17X#14")]
    assert "Ue 127×50×17×2,00" in nomes
    assert all("127×50×17×" in n for n in nomes)
    assert catalogo.espessuras_da_bitola("#14") == [1.9, 1.95, 2.0]
    assert [i.nome for i in catalogo.buscar("BR 3/8")] == ['Barra redonda ø 3/8"']


def test_fabricantes_e_tabela_ao_lado():
    w = catalogo.item("W 250×17,9")
    assert "Gerdau" in w.dict()["fabricantes"]
    tq = catalogo.buscar("TQ 100x100x5,0")[0].dict()
    assert len(tq["fabricantes"]) >= 1
    # perfil só de fornecedor, com a tabela de propriedades: vira Perfil de cálculo
    so_forn = [i for i in catalogo.itens("I") if i.dados.get("fornecedor") and i.A]
    assert so_forn
    p = catalogo.perfil_de(so_forn[0])
    assert p is not None and p.A == so_forn[0].A


def test_dimensionamento_automatico_ignora_so_fornecedor():
    from nucleo import tesouras
    tesouras._CACHE.clear()
    nomes = {p.nome for p in tesouras.candidatos(("U", "Ue", "L"))}
    so_forn = {i.nome for f in ("U", "Ue", "L") for i in catalogo.itens(f) if i.dados.get("fornecedor")}
    assert so_forn and not (nomes & so_forn)


def test_telhas_com_larguras_e_massa():
    tp40 = [i for i in catalogo.itens("telha") if i.dados.get("modelo") == "TP40" and i.massa_m2]
    assert tp40
    d = tp40[0].dict()
    assert d["largura_total"] > d["largura_util"] > 0
    assert catalogo.alternativas(tp40[0].nome)            # troca só entre telhas
    assert all(a["familia"] == "telha" for a in catalogo.alternativas(tp40[0].nome))
