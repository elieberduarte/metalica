# -*- coding: utf-8 -*-
"""Esforços na estrutura inteira (nucleo3d/esforcos.py): pórtico espacial no esqueleto — a barra
contra a fórmula, o equilíbrio, as reações por pilar ao lado das cargas da locação — e a
leitura das cargas por pilar na locação (de_planta._cargas_da_locacao)."""
import numpy as np
import pytest

from nucleo3d import de_planta, esforcos
from nucleo3d.modelo import Barra, Documento

from test_analitico import barra, modelo


def test_barra_em_balanco_bate_com_a_formula():
    L, I_forte, I_fraca = 2.0, 2e-6, 1e-6
    k = esforcos._rigidez_local(np.array([L]), np.array([1e-3]), np.array([I_forte]), np.array([I_fraca]),
                                np.array([1e-7]))[0]
    assert np.allclose(k, k.T)
    # engastada no início, 1 kN na ponta: flecha PL³/3EI na direção de cada inércia
    for grau, I in ((2, I_forte), (1, I_fraca)):
        F = np.zeros(6)
        F[grau] = 1.0
        u = np.linalg.solve(k[6:, 6:], F)
        assert u[grau] == pytest.approx(L ** 3 / (3 * esforcos.E_ACO * I))


def test_equilibrio_e_simetria_no_portico_de_duas_trelicas():
    r = esforcos.calcular(modelo())
    for caso, c in r["casos"].items():
        assert c["erro"] < 1e-6, (caso, c)
    assert len(r["pilares"]) == 4
    pp = sorted(p["reacoes_kN"]["PP"][2] for p in r["pilares"])
    assert pp[0] > 0 and pp[-1] - pp[0] < 0.05 * pp[-1]            # simétrico: os quatro iguais
    # a terça do meio leva a cobertura: faixa sem vizinha (só uma terça) fica sem carga, com aviso
    assert r["casos"]["SC"]["carga_kN"] == 0 and any("sem outra terça" in a for a in r["avisos"])


def test_largura_de_influencia_das_tercas():
    doc = modelo()
    for x in (1500.0, 4500.0):
        doc.add(barra((x, -300.0, 6890.0), (x, 5300.0, 6890.0), "terça"))
    r = esforcos.calcular(doc, {"sobrecarga": 1.0, "telha": 0.0})
    # três terças a 1,5 m: a do meio com 1,5 m, as de fora com 0,75 m; 5,0 m de uma treliça à
    # outra (a pontinha de 30 cm além do banzo o esqueleto leva até ele)
    assert r["casos"]["SC"]["carga_kN"] == pytest.approx((1.5 + 0.75 * 2) * 5.0, rel=0.02)
    assert r["casos"]["SC"]["erro"] < 1e-6


def test_peca_sem_caminho_ate_o_pilar_fica_de_fora_com_aviso():
    doc = modelo()
    doc.add(barra((20000.0, 0.0, 6000.0), (24000.0, 0.0, 6000.0), "viga"))
    r = esforcos.calcular(doc)
    assert any("sem caminho" in a for a in r["avisos"])
    assert r["casos"]["PP"]["erro"] < 1e-6


def test_base_engastada_onde_a_locacao_da_momento():
    doc = modelo()
    doc.metadados["de_planta"] = {"cargas_locacao": {"pilares": [
        {"Fz": 3.0, "Mx": 1.0, "pilar": "PM1", "x": 0.0, "y": 0.0},
        {"Fz": 2.0, "pilar": "PM1", "x": 6000.0, "y": 0.0}]}}
    r = esforcos.calcular(doc)
    por_xy = {(p["x"], p["y"]): p for p in r["pilares"]}
    assert por_xy[(0, 0)]["engastado"] and not por_xy[(6000, 0)]["engastado"]
    assert por_xy[(0, 0)]["locacao"]["Fz"] == 3.0 and por_xy[(6000, 0)]["locacao"]["Fz"] == 2.0
    assert "locacao" not in por_xy[(0, 5000)]


def _texto(t, x, y, i):
    return {"id": "t%d" % i, "tipo": "texto", "texto": t, "posicao": [x, y], "altura": 10.0}


def test_cargas_da_locacao_embaixo_do_nome_e_na_placa_livre():
    textos = [_texto("PM1(250X70X25X3,0)", 1000, 1289, 1), _texto("7,0tf", 1000, 1000, 2),
              # o pilar em quadro: o bloco completo embaixo do nome, e o da outra placa sem nome
              _texto("PM8(250X125X25X4,75)", 5000, 1378, 3), _texto("Fz: 3,00 tf", 5000, 1000, 4),
              _texto("Fx:-1,00 tf", 5000, 650, 5), _texto("Fy:-1,00 tf", 5000, 290, 6),
              _texto("MX: 2,00 tf.m", 4989, -49, 7), _texto("My:-1,00 tf.m", 4989, -371, 8),
              _texto("Fz: 9,00 tf", 2000, 1000, 9), _texto("Fx: 4,00 tf", 2000, 650, 10)]
    locados = [{"nome": "PM1(250X70X25X3,0)", "x": 1000.0, "y": 1000.0, "_texto": "t1"},
               {"nome": "PM8(250X125X25X4,75)", "x": 5000.0, "y": 1000.0, "_texto": "t3"}]
    out = de_planta._cargas_da_locacao(textos, (-1e5, -1e5, 1e5, 1e5), [(3900.0, 1500.0)], (0.0, 289.0),
                                       (10.0, 20.0), locados)
    por = {c["Fz"]: c for c in out}
    assert por[7.0]["pilar"] == "PM1(250X70X25X3,0)" and locados[0]["cargas"] == {"Fz": 7.0}
    assert por[3.0] ["pilar"].startswith("PM8") and locados[1]["cargas"] == {"Fz": 3.0, "Fx": -1.0, "Fy": -1.0,
                                                                             "Mx": 2.0, "My": -1.0}
    assert por[9.0]["pilar"] is None and (por[9.0]["x"], por[9.0]["y"]) == (3910.0, 1520.0)
    assert por[9.0]["Fx"] == 4.0


def test_s2_e_s3_da_6123_2023():
    # Tabela 3: categoria II, classe C — 0,89 até 5 m e 0,95 a 10 m; no meio, interpolado
    assert esforcos.s2_2023(4.0, "II", "C") == pytest.approx(0.89)
    assert esforcos.s2_2023(7.5, "II", "C") == pytest.approx(0.92)
    assert esforcos.s2_2023(10.0, "IV", "A") == pytest.approx(0.86)
    assert esforcos.classe_por_dimensao(60.0) == "C" and esforcos.classe_por_dimensao(30.0) == "B"
    assert esforcos.S3_2023[1] == 1.11 and esforcos.S3_2023[3] == 1.00


def test_tramos_do_telhado_multiplo_e_coeficientes_da_tabela_10():
    # três tramos de 10 m: calhas em 10 e 20, cumeeiras no meio de cada um
    u = np.arange(0.0, 30.01, 0.5)
    z = 7.0 + 0.3 * (1.0 - np.abs(((u % 10.0) - 5.0) / 5.0))
    calhas, cumeeiras, _u0, _u1 = esforcos._tramos(u, z)
    assert calhas == pytest.approx([10.0, 20.0], abs=0.6) and cumeeiras == pytest.approx([5.0, 15.0, 25.0], abs=0.6)
    cpe = [esforcos._cpe_alfa0(x, calhas, cumeeiras) for x in (2.0, 8.0, 12.0, 18.0, 28.0)]
    assert cpe == [-0.9, -0.6, -0.4, -0.3, -0.3]


def test_vento_levanta_a_cobertura_e_entra_nas_combinacoes():
    doc = modelo()
    for x in (1500.0, 4500.0):
        doc.add(barra((x, -300.0, 6890.0), (x, 5300.0, 6890.0), "terça"))
    r = esforcos.calcular(doc, {"sobrecarga": 0.25, "telha": 0.05}, vento={"v0": 45.0, "grupo": 3, "categoria": "II"})
    v = r["vento"]
    assert v["s3"] == 1.00 and len(v["casos"]) == 8
    # cpi +0,8 com cpe negativo: força para cima em toda a cobertura
    assert all(c["para_cima_kN"] > 0 for c in v["casos"][::2])
    assert all(x["erro"] < 1e-6 for x in r["casos"].values())
    nomes = [c["nome"] for c in r["combinacoes"]]
    assert "ELU[SC]" in nomes and "ELU[V1]-levantamento" in nomes
    p = r["pilares"][0]
    assert p["envoltoria_kN"]["min"] < 0 < p["envoltoria_kN"]["max"]         # arrancamento e compressão


def test_piso_do_mezanino_pelos_barrotes():
    # quatro pilares de 3 m, duas vigas em x a y = 0 e 3000, seis barrotes em y a cada 600 mm
    doc = Documento()
    for x in (0.0, 3000.0):
        for y in (0.0, 3000.0):
            doc.add(barra((x, y, 0.0), (x, y, 3000.0), "pilar", perfil="W 200×19,3"))
    for y in (0.0, 3000.0):
        v = barra((0.0, y, 3000.0), (3000.0, y, 3000.0), "viga", perfil="W 200×19,3")
        v.camada = "Mezanino"
        doc.add(v)
    for k in range(6):
        b = barra((300.0 + 480.0 * k, 0.0, 3000.0), (300.0 + 480.0 * k, 3000.0, 3000.0), "viga", perfil="Ue 150×70×20×2,65")
        b.camada = "Mezanino"
        doc.add(b)
    sem = esforcos.calcular(doc)
    assert sem["mezanino"]["barrotes"] == ["Ue 150×70×20×2,65"] and any("mezanino sem carga" in a for a in sem["avisos"])
    r = esforcos.calcular(doc, {"mezanino_peso": 0.3, "mezanino_sobrecarga": 2.0})
    area = r["mezanino"]["area_m2"]
    assert area == pytest.approx(0.48 * 5 * 3.0, rel=0.05)                  # 5 vãos de 0,48 m × 3 m
    assert r["casos"]["SM"]["carga_kN"] == pytest.approx(2.0 * area, rel=1e-3) and r["casos"]["SM"]["erro"] < 1e-6
    assert any(c["nome"] == "ELU[SM]" for c in r["combinacoes"])


def test_sobrecarga_da_passarela_na_trelica_deitada():
    # a passarela: treliça deitada de 6 m e 1,5 m de largura, presa pela lateral no banzo de baixo
    # da treliça do pórtico (a 100 mm dele), no mesmo nível
    doc = modelo()
    for y in (-100.0, -1600.0):
        b = barra((0.0, y, 6000.0), (6000.0, y, 6000.0), "banzo", "P#9")
        b.atributos["origem"]["sentido"] = "deitada: a planta desenha a treliça vista de cima"
        doc.add(b)
    for x in (0.0, 3000.0, 6000.0):
        m = barra((x, -100.0, 6000.0), (x, -1600.0, 6000.0), "montante", "P#9")
        m.atributos["origem"]["sentido"] = "deitada"
        doc.add(m)
    sem = esforcos.calcular(doc)
    assert sem["passarela"]["area_m2"] == pytest.approx(9.0, rel=0.05) and any("passarela sem" in a for a in sem["avisos"])
    r = esforcos.calcular(doc, {"passarela_sobrecarga": 1.0})
    assert r["casos"]["SP"]["carga_kN"] == pytest.approx(9.0, rel=0.05) and r["casos"]["SP"]["erro"] < 1e-6
