# -*- coding: utf-8 -*-
"""Cálculo corrigido pela revisão geral de 24/09 (0.8.14): γ = 1,20 na compressão do
formado a frio, cantoneira de treliça plana, esbeltez 200 no frio, "não verificada" que
não aprova, combinações com vento completas, 2ª ordem no pórtico e massas do catálogo."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import galpao, nbr8800, nbr14762, perfis_fabrica, verificar   # noqa: E402
from nucleo.base import ErroDeDados, Resultado, nao_verificada         # noqa: E402
from nucleo.modelo_galpao import DadosGalpao                           # noqa: E402
from nucleo.perfis import banco                                        # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_compressao_do_frio_com_gama_1_20():
    ue = perfis_fabrica.perfil_de_fabrica("UE127X50X17X2.00")
    r = verificar.verificar_membro(ue, "CIVIL 300", 50.0, 0.0, 0.0, 150.0, 150.0, 1, "banzo")
    vc = next(v for v in r.verificacoes if v.titulo.startswith("Compressão"))
    assert abs(vc.Rd - 66.7) < 0.3                  # 72,7 kN com o 1,10 de antes
    assert nbr14762.GAMA_COMPRESSAO == 1.20 and nbr14762.GAMA == 1.10
    # U simples formado a frio pela NBR 8800: o mesmo 1,20
    u = perfis_fabrica.perfil_de_fabrica("L50X50X2.25")
    assert u.dados.get("formado_a_frio")
    rc = nbr8800.compressao(u, "CIVIL 300", Lx=100.0, N_Sd=1.0)
    lam = rc.dados["chi"] * rc.dados["Q"] * u.A * 30.0 / rc.dados["N_Rd"]
    assert abs(lam - 1.20) < 1e-6


def test_cantoneira_de_trelica_plana():
    L2 = next(p for p in banco().perfis.values() if p.tipo == "L" and p.nome.startswith('L 2"') and "3/16" in p.nome)
    plana = [round(nbr8800.compressao(L2, "ASTM A36", Lx=L, N_Sd=1, cantoneira_simplificada=True).dados["N_Rd"], 1)
             for L in (100, 150, 200)]
    espacial = [round(nbr8800.compressao(L2, "ASTM A36", Lx=L, N_Sd=1, cantoneira_simplificada=True,
                                         trelica="espacial").dados["N_Rd"], 1) for L in (100, 150, 200)]
    assert plana == [48.7, 31.4, 19.7]
    assert espacial == [54.2, 36.5, 24.3]
    # as duas expressões se encontram em L/r = 80 (plana) e 75 (espacial)
    ef80, _ = nbr8800.esbeltez_equivalente_cantoneira(L2, 80 * L2.rx)
    assert abs(ef80 - 132.0) < 1e-6
    ef75, _ = nbr8800.esbeltez_equivalente_cantoneira(L2, 75 * L2.rx, "espacial")
    assert abs(ef75 - 120.0) < 1e-6


def test_frio_comprimido_esbelto_nao_passa():
    u = perfis_fabrica.perfil_de_fabrica("U92X40X2.25")
    r = verificar.verificar_membro(u, "CIVIL 300", 0.5, 0.0, 0.0, 600.0, 600.0, 1, "diagonal")
    esb = next(v for v in r.verificacoes if v.titulo.startswith("Esbeltez"))
    assert esb.Sd > 400 and not esb.ok and not r.ok
    # tracionado, a esbeltez da compressão não entra
    r = verificar.verificar_membro(u, "CIVIL 300", 0.0, 0.5, 0.0, 600.0, 600.0, 1, "diagonal")
    assert r.ok


def test_nao_verificada_nao_aprova():
    r = Resultado("x")
    r.add(nao_verificada(ErroDeDados("perfil sem rx")))
    assert not r.ok and r.indeterminada and r.razao == 0.0
    ser = verificar.serializar_resultado(r)
    assert ser["ok"] is False and ser["indeterminada"] is True
    json.dumps(ser, allow_nan=False)                 # sem Infinity no JSON da tela


def test_combinacoes_com_vento_completas():
    combos = galpao.combinacoes_com_vento("V")
    fatores = {n: f for n, f, _ in combos}
    assert fatores["C3 SC+vento"] == {"PP": 1.25, "SC": 1.5, "V": 1.4 * 0.6}
    assert fatores["C4 vento+SC"] == {"PP": 1.25, "SC": 1.5 * 0.8, "V": 1.4}
    assert fatores["C5 vento+PP"] == {"PP": 1.25, "V": 1.4}
    p = galpao.dimensionar(DadosGalpao())
    nomes = [c for c in p.esforcos["combinacoes"] if c.startswith("C")]
    assert {"C4 vento+SC (cpi+)", "C4 vento+SC (cpi-)", "C3 SC+vento (cpi+)", "C5 vento+PP (cpi-)"} <= set(nomes)
    # o memorial mostra as mesmas: a do vento principal com a sobrecarga reduzida
    docs = [c for c in p.combinacoes if c.principal == "Vento (sucção no telhado)" and len(c.parcelas) == 3]
    assert any(abs(pa.coef - 1.2) < 1e-9 for c in docs for pa in c.parcelas if pa.acao == "Sobrecarga de cobertura")


def test_segunda_ordem_no_portico():
    p = galpao.dimensionar(DadosGalpao())
    so = p.esforcos["segunda_ordem"]
    assert 1.0 < so["B2"] < 1.4 and so["classificacao"] in ("pequena deslocabilidade", "média deslocabilidade")
    assert so["fator_pilar"] >= so["B2"] and so["soma_N_kN"] > 0
    # a força nocional está na combinação de gravidade: 0,3 % de ΣN, no topo dos pilares
    modelo = p.esforcos["modelo"]
    nodais = [c for c in modelo.casos["C1 gravidade"] if c.tipo == "nodal" and c.Fx]
    assert len(nodais) == 2 and abs(sum(c.Fx for c in nodais) - 0.003 * so["soma_N_kN"]) < 0.02 * so["soma_N_kN"] * 0.003 + 1e-6
    # o pilar é verificado com o momento amplificado
    env_M = max(abs(p.esforcos["envoltoria"].barra(r).absoluto("M").valor) for r in ("pilar_esq", "pilar_dir"))
    assert abs(p.esforcos["pilar"]["M"] - env_M * so["fator_pilar"]) < 1e-6 * env_M + 1e-6


def test_massas_do_catalogo_conferidas_com_a_area():
    with open(os.path.join(BASE, "dados", "catalogo.json"), encoding="utf-8") as f:
        cat = json.load(f)
    it = {i["nome"]: i for i in cat["itens"]}
    assert it['L 5"×7/16"']["massa"] == 21.16 and it['L 5"×7/16"']["massa_fornecedor"] == 23.52
    assert it["TC 42,4×1,35"]["massa"] == 1.367
    assert abs(it["TQ 30×30×1,8"]["massa"] - 1.528) < 0.002          # canto arredondado
    assert it["CH 2 mm"]["bitola_msg"].startswith("14") and it["CH 3,35 mm"]["bitola_msg"].startswith("10")
    for i in cat["itens"]:
        if i.get("A") and i.get("massa") and i.get("familia") not in ("chapa", "telha", "parafuso"):
            if i.get("familia") == "tubo" and i.get("tipo") != "redondo":
                continue                                            # entre canto vivo e arredondado
            assert abs(i["massa"] / (i["A"] * 0.785) - 1) <= 0.05 + 1e-3, i["nome"]
