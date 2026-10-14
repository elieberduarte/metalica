# -*- coding: utf-8 -*-
"""As bordas do motor de análise do modelo 3D (nucleo3d/analise_estrutural.py e verificacao_pecas.py) — achados de 14/10/2026:

* M3: o pilar com o pé numa cota diferente da mais baixa ficava sem apoio (pendurado na estrutura, "estável", sem aviso);
* M4: o galpão fechado (NBR 6123:2023, Tabelas 6 e 7 + C_pi), ligado sozinho quando o modelo tem longarinas ou telha de
  parede — antes o vento era sempre o da cobertura isolada e o pilar só via o arrasto da própria seção;
* M5: pressão/sucção do caso de vento pelo sinal efetivo (o carregamento 2 da Tabela 24 com o vento do lado alto empurra
  para baixo e era tratado como sucção pelo nome);
* N1: o C_t da tração pela ligação parafusada do 3D (os furos marcados na peça)."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import cargas as C  # noqa: E402
from nucleo3d import analise_estrutural as AE  # noqa: E402
from nucleo3d import verificacao_pecas as VP  # noqa: E402
from nucleo3d.geometria import extrudar  # noqa: E402
from nucleo3d.modelo import Barra, Documento, Solido  # noqa: E402

W = "W 250×32,7"
U = "U 150×50×3,00 (FF)"
L = 'L 1½"×1/8"'
UE = "Ue 150×60×20×2,00"


# ------------------------------------------------------------------ M3: as bases em cotas diferentes

def _portico(z_pes, pilarete=True, x_no_pe=False):
    """4 pilares (6 × 5 m) até +4,00 com vigas no topo; os pés nas cotas `z_pes` (mm). Pilarete de 1 m em pé no meio da
    viga de y = 0. `x_no_pe`: um contraventamento que nasce no pé do pilar (6000, 5000) e sobe até o topo do (6000, 0)"""
    doc = Documento(nome="m3")
    P = [(0, 0), (6000, 0), (0, 5000), (6000, 5000)]
    for (x, y), z in zip(P, z_pes):
        doc.add(Barra(inicio=(x, y, z), fim=(x, y, 4000), perfil=W, papel="pilar"))
    for a, b in ((0, 1), (2, 3), (0, 2), (1, 3)):
        doc.add(Barra(inicio=(*P[a], 4000), fim=(*P[b], 4000), perfil=W, papel="viga"))
    if pilarete:
        doc.add(Barra(inicio=(3000, 0, 4000), fim=(3000, 0, 5000), perfil=W, papel="pilar"))
    if x_no_pe:
        doc.add(Barra(inicio=(6000, 5000, z_pes[3]), fim=(6000, 0, 4000), perfil="Barra redonda 12,5", papel="contraventamento"))
    return doc


def _cotas_dos_apoios(M):
    return sorted(round(float(M["nos"][a["no"]][2]) * 1000) for a in M["apoios"])


def test_m3_pes_em_cotas_diferentes_viram_apoios_com_aviso():
    """2 pés em ±0 e 2 em +300 mm: antes só 2 apoios (os de ±0) e nenhum aviso — os outros 2 pilares ficavam pendurados
    nas vigas. Agora 4 apoios e o aviso com as duas cotas; o pilarete sobre a viga não vira apoio"""
    M = AE.montar(_portico((0, 0, 300, 300)), {"segunda_ordem": False})
    assert _cotas_dos_apoios(M) == [0, 0, 300, 300]
    av = [a for a in M["avisos"] if "cotas diferentes" in a]
    assert len(av) == 1 and "+0,00 m (2 pilares)" in av[0] and "+0,30 m (2 pilares)" in av[0]
    pe_pilarete = [i for i, n in enumerate(M["nos"]) if np.allclose(n, (3.0, 0.0, 4.0))]
    assert pe_pilarete and not {a["no"] for a in M["apoios"]} & set(pe_pilarete)
    # a carga vertical no topo chega às 4 bases (as de +300 levam a parte delas)
    casos = {"g": {"dist": {i: np.array([0.0, 0.0, -10.0]) for i, br in enumerate(M["barras"]) if br["papel"] == "viga"},
                   "nodal": {}}}
    sol = AE.resolver(M, casos)
    assert sol["instavel"] is None
    Rz = {round(float(M["nos"][n][2]) * 1000): 0.0 for n in sol["reacoes"]}
    for n, r in sol["reacoes"].items():
        Rz[round(float(M["nos"][n][2]) * 1000)] += float(r[2, 0])
    total = 10.0 * sum(br["L"] for br in M["barras"] if br["papel"] == "viga")
    assert Rz[0] + Rz[300] == pytest.approx(total, rel=1e-6)
    assert Rz[300] > 0.3 * total                                # simétrico: cada lado leva perto da metade


def test_m3_mesma_cota_nao_muda():
    """todos os pés em ±0: os mesmos 4 apoios de antes, sem aviso de cotas"""
    M = AE.montar(_portico((0, 0, 0, 0)), {"segunda_ordem": False})
    assert _cotas_dos_apoios(M) == [0, 0, 0, 0]
    assert not [a for a in M["avisos"] if "cotas diferentes" in a]


def test_m3_contraventamento_que_sobe_do_pe_nao_impede_a_base():
    """a barra que só sobe do pé (o X que nasce na base) não sustenta o pilar: o pé de +300 continua base"""
    M = AE.montar(_portico((0, 0, 300, 300), pilarete=False, x_no_pe=True), {"segunda_ordem": False})
    assert _cotas_dos_apoios(M) == [0, 0, 300, 300]


# ------------------------------------------------------------------ M4: o galpão fechado

XS = [0.0, 6000.0, 12000.0, 18000.0]
YS = [0.0, 3000.0, 6000.0, 9000.0, 12000.0]
ZS = [6000.0, 6500.0, 7000.0, 6500.0, 6000.0]          # tesoura de duas águas: tg θ = 1/6 (θ = 9,46°)


def _trel(doc, a, b, perfil, papel, pt, t):
    doc.add(Barra(inicio=a, fim=b, perfil=perfil, papel=papel, rotacao=90.0 if papel == "banzo" else 0.0,
                  atributos={"elemento": "trelica", "papel_trelica": pt, "origem_2d": t, "origem": {"peca": t.upper()},
                             "marca": t.upper()}))


def _galpao(longarinas=False, telha_parede=False, testeira=False, banzo_inteiro=False):
    """galpão 12 m (vão, em y) × 18 m (em x, 4 pórticos a cada 6 m), pé-direito 6 m, tesouras de duas águas com 1 m de
    flecha, 5 terças. Com longarinas: 2 fiadas (+2,00 e +4,00) nas duas faces longas (y = 0 e 12 m), o pilar partido nas
    fiadas (o esqueleto liga a longarina no nó do pilar). Telha de parede: as duas faces longas fechadas do chão ao beiral;
    testeira: só uma faixa vertical de +5,00 a +6,00 (não fecha a parede)"""
    doc = Documento(nome="galpão")
    for k, x in enumerate(XS):
        t = "t%d" % (k + 1)
        zs = [0.0, 2000.0, 4000.0, 6000.0] if longarinas else [0.0, 6000.0]
        for y in (0.0, 12000.0):
            for z0, z1 in zip(zs, zs[1:]):
                doc.add(Barra(inicio=(x, y, z0), fim=(x, y, z1), perfil=W, papel="pilar"))
        if banzo_inteiro:                               # o banzo de baixo numa peça só (o esqueleto parte nos nós)
            _trel(doc, (x, YS[0], 6000.0), (x, YS[-1], 6000.0), U, "banzo", "banzo_inf", t)
        for i in range(4):
            if not banzo_inteiro:
                _trel(doc, (x, YS[i], 6000.0), (x, YS[i + 1], 6000.0), U, "banzo", "banzo_inf", t)
            _trel(doc, (x, YS[i], ZS[i]), (x, YS[i + 1], ZS[i + 1]), U, "banzo", "banzo_sup", t)
        for i in (1, 2, 3):
            _trel(doc, (x, YS[i], 6000.0), (x, YS[i], ZS[i]), L, "montante", "montante", t)
        _trel(doc, (x, YS[1], ZS[1]), (x, YS[2], 6000.0), L, "diagonal", "diagonal", t)
        _trel(doc, (x, YS[3], ZS[3]), (x, YS[2], 6000.0), L, "diagonal", "diagonal", t)
    for y, z in zip(YS, ZS):
        doc.add(Barra(inicio=(0.0, y, z), fim=(18000.0, y, z), perfil=UE, papel="terça", atributos={"elemento": "terça"}))
    if longarinas:
        for y in (0.0, 12000.0):
            for z in (2000.0, 4000.0):
                for x0, x1 in zip(XS, XS[1:]):
                    doc.add(Barra(inicio=(x0, y, z), fim=(x1, y, z), perfil=UE, papel="longarina"))
    if telha_parede or testeira:
        z0, h = (0.0, 6000.0) if telha_parede else (5000.0, 1000.0)
        # por fora dos pilares, longe dos nós (o esqueleto toma o sólido da telha como uma linha e junta pontas a até
        # 60 mm: encostada no pilar, ela puxava o nó do pé)
        for y in (-400.0, 12360.0):
            doc.add(extrudar([(0.0, y), (18000.0, y), (18000.0, y + 40.0), (0.0, y + 40.0)], (0.0, 0.0, 1.0), h,
                             origem=(0.0, 0.0, z0), nome="TELHA TP40"))
    return doc


PAR = {"segunda_ordem": False}


def _q_do_galpao():
    """q pela 4.2 da NBR 6123:2023 com as premissas padrão (V0 45 m/s, S1 = S3 = 1, categoria III): z = topo − base =
    7,0 m; classe pela maior dimensão (18 m → A)"""
    S2 = C.fator_s2("III", "A", 7.0)
    return C.pressao_dinamica(C.velocidade_caracteristica(45.0, 1.0, S2, 1.0))


def _pilar(M, x, y):
    return [i for i, br in enumerate(M["barras"]) if br["papel"] == "pilar" and AE.chave_do_pilar(M["nos"], br) == "%d,%d" % (x, y)]


def test_m4_sem_longarina_nem_telha_de_parede_continua_isolada():
    M = AE.montar(_galpao(), PAR)
    casos, info, _ = AE.cargas(M)
    v = info["vento"]
    assert v["modo"] == "isolada" and v["modo_pedido"] == "auto" and "não tem longarinas" in v["motivo"]
    assert {"V1→", "V2→", "Vat↑"} <= set(casos)


def test_m4_testeira_nao_fecha_a_parede():
    """a telha vertical só no alto (a testeira, o beiral dobrado do Posto CB) não fecha o galpão"""
    M = AE.montar(_galpao(testeira=True), PAR)
    f = M["fechamento"]
    assert f["telhas_parede"] == 0 and f["telhas_altas"] == 2
    _, info, _ = AE.cargas(M)
    assert info["vento"]["modo"] == "isolada" and "acima da metade" in info["vento"]["motivo"]


def test_m4_telha_de_parede_liga_o_fechado_e_o_pilar_de_borda_recebe_a_parede():
    """a telha de parede do chão ao beiral liga o galpão fechado. b = 12 m, a = 18 m, h = 6 m → h/b = 0,5 (faixa ≤ 1/2),
    a/b = 1,5: Tabela 6, vento perpendicular à face maior (A/B): C_e = +0,7 a barlavento e −0,4 a sotavento. C_pi pela
    6.3.2.1-a (duas faces opostas): +0,2 e −0,3.

    Pilar de borda do meio da face de barlavento (x = 6 m, y = 0), largura de influência 6 m (3 + 3):
        V→ C_pi −0,3: w = (0,7 − (−0,3)) · q · 6 = 6·q        (q = 1,021 kN/m² → 6,128 kN/m, no sentido do vento)
        V→ C_pi +0,2: w = (0,7 − 0,2) · q · 6 = 3·q              (3,064 kN/m)
    Sotavento (x = 6 m, y = 12 m), C_pi +0,2: (−0,4 − 0,2)·q·6 = −3,6·q de sucção, puxando para fora — no sentido do
    vento: +3,6·q (3,677 kN/m). O pilar do canto (x = 0) tem metade da largura (3 m)."""
    M = AE.montar(_galpao(telha_parede=True), PAR)
    assert M["fechamento"]["telhas_parede"] == 2
    casos, info, _ = AE.cargas(M)
    v = info["vento"]
    assert v["modo"] == "fechado" and "telha(s) de parede" in v["motivo"]
    q = _q_do_galpao()
    assert v["q_kN_m2"] == pytest.approx(q, abs=5e-4)
    assert (v["b"], v["a"], v["h"]) == (12.0, 18.0, 6.0) and v["cpi"] == [0.2, -0.3]
    assert v["coeficientes"]["transversal A"] == 0.7 and v["coeficientes"]["transversal B"] == -0.4
    assert set(casos) >= {"V→ cpi+0,2", "V→ cpi−0,3", "V← cpi+0,2", "V↑ cpi+0,2", "V↓ cpi−0,3"}
    # o vento → é +y (o vão das tesouras)
    for caso, ix, iy, w_esp in (("V→ cpi−0,3", 6000, 0, 6.0 * q), ("V→ cpi+0,2", 6000, 0, 3.0 * q),
                                ("V→ cpi+0,2", 6000, 12000, 3.6 * q), ("V→ cpi−0,3", 0, 0, 3.0 * q)):
        bs = _pilar(M, ix, iy)
        assert bs
        for i in bs:
            w = casos[caso]["dist"][i]
            assert w[1] == pytest.approx(w_esp, rel=1e-9), (caso, ix, iy)
            assert w[2] == 0.0
    # dentro do fechamento: sem o arrasto da 8.1 nas barras (só pilares de borda e o telhado carregados)
    assert all(M["barras"][i]["papel"] in ("pilar", "terça") for i in casos["V→ cpi+0,2"]["dist"])


def test_m4_o_momento_de_base_cresce_em_relacao_a_isolada():
    """o mesmo galpão (com as paredes) nos dois modos, 1ª ordem: o maior momento na base dos pilares entre os casos de
    vento. Na isolada o pilar só via o arrasto da seção (8.1) e o que a cobertura passa; fechado, a parede inteira"""
    def m_base(modo):
        M = AE.montar(_galpao(telha_parede=True), dict(PAR, modelo_vento=modo))
        casos, info, _ = AE.cargas(M)
        assert info["vento"]["modo"] == ("isolada" if modo == "isolada" else "fechado")
        sol = AE.resolver(M, casos)
        assert sol["instavel"] is None
        return max(float(np.hypot(r[3, c], r[4, c])) for c, nome in enumerate(sol["casos"]) if nome.startswith("V")
                   for r in sol["reacoes"].values())
    isolada, fechado = m_base("isolada"), m_base("auto")
    assert fechado > 1.8 * isolada                       # 56,4 × 28,0 kN·m neste modelo


def test_m4_longarinas_ligam_o_fechado_e_recebem_a_faixa_da_parede():
    """com longarinas em duas fiadas (+2,00 e +4,00) a face longa recebe a pressão nas longarinas: a faixa de cada fiada
    vai de meio caminho até a vizinha (0 → 3 m e 3 → 6 m = o beiral): 3 m. V→ C_pi +0,2 na face de barlavento (y = 0):
    w = (0,7 − 0,2) · q · 3 = 1,5·q por metro de longarina, para dentro (+y). Os pilares dessas faces não recebem parede
    direto; os do oitão (sem longarina) recebem"""
    M = AE.montar(_galpao(longarinas=True), PAR)
    assert M["fechamento"]["longarinas"] == 12
    casos, info, avisos = AE.cargas(M)
    v = info["vento"]
    assert v["modo"] == "fechado" and "12 longarina(s)" in v["motivo"]
    assert not [a for a in avisos if "sem ligação" in a]
    q = _q_do_galpao()
    d = casos["V→ cpi+0,2"]["dist"]
    long_barl = [i for i, br in enumerate(M["barras"]) if br["papel"] == "longarina" and abs(M["nos"][br["a"]][1]) < 1e-6]
    assert len(long_barl) == 6
    for i in long_barl:
        assert d[i][1] == pytest.approx(1.5 * q, rel=1e-9) and d[i][0] == 0.0 and d[i][2] == 0.0
    # o pilar do meio da face longa (6, 0) não leva a parede no vento → (só nas faces sem longarina)
    assert all(i not in d for i in _pilar(M, 6000, 0))
    sol = AE.resolver(M, casos)
    assert sol["instavel"] is None


def test_m4_premissa_escolhe_o_modo():
    """a premissa vence o automático: isolada no galpão com parede; fechado no galpão sem nada (com pilares)"""
    _, i1, _ = AE.cargas(AE.montar(_galpao(telha_parede=True), dict(PAR, modelo_vento="isolada")))
    assert i1["vento"]["modo"] == "isolada" and i1["vento"]["motivo"] == "escolhido nas premissas"
    _, i2, _ = AE.cargas(AE.montar(_galpao(), dict(PAR, modelo_vento="fechado")))
    assert i2["vento"]["modo"] == "fechado" and i2["vento"]["modo_pedido"] == "fechado"


# ------------------------------------------------------------------ M5: pressão ou sucção pelo sinal efetivo

def _marquise_uma_agua():
    """a marquise de uma água do teste da chumbada (Docas): tg θ ≈ 0,168, chumbada no pilar de concreto"""
    doc = Documento(nome="uma agua")
    sol = extrudar([(-175.0, -700.0), (175.0, -700.0), (175.0, 0.0), (-175.0, 0.0)], (0.0, 0.0, 1.0), 8000.0,
                   origem=(0.0, 0.0, 0.0), nome="Pilar P1")
    sol.material = "Concreto"
    sol.atributos = {"elemento": "pilar", "marca": "P1", "pre_moldado": True}
    doc.add(sol)
    y = [25.0, 1000.0, 2000.0, 3000.0]
    zs = [6000.0, 5833.0, 5666.0, 5500.0]
    for x in (0.0, 3000.0):
        for i in range(3):
            _trel(doc, (x, y[i], 5000), (x, y[i + 1], 5000), U, "banzo", "banzo_inf", "t%d" % round(x))
            _trel(doc, (x, y[i], zs[i]), (x, y[i + 1], zs[i + 1]), U, "banzo", "banzo_sup", "t%d" % round(x))
        for yy, zz in zip(y, zs):
            _trel(doc, (x, yy, 5000), (x, yy, zz), L, "montante", "montante", "t%d" % round(x))
    return doc


def test_m5_carregamento_2_do_lado_alto_e_pressao_e_entra_com_a_sobrecarga():
    """Tabela 24: com o vento do lado alto o carregamento 1 levanta (sucção) e o 2 empurra para baixo (pressão). Antes o
    "V2" era sucção pelo nome: só "permanentes favoráveis + vento". Agora o V2 do lado alto ganha as combinações com a
    sobrecarga (vento principal + sobrecarga e sobrecarga principal + vento) e a de sucção; o V1 do lado alto, que
    levanta, fica só com os permanentes favoráveis"""
    M = AE.montar(_marquise_uma_agua(), {"travamento_hipotese": "nao", "vento_nas_barras": False})
    casos, info, _ = AE.cargas(M)
    alto = "V1→" if casos["V1→"]["vem_do"] == "lado alto" else "V1←"
    v2 = alto.replace("1", "2")
    assert casos[v2]["sentido_vertical"] == "pressao" and casos[v2]["Fz_kN"] < 0
    assert casos[alto]["sentido_vertical"] == "succao" and casos[alto]["Fz_kN"] > 0
    cb = AE.combinacoes(casos)
    assert cb["ELU %s" % v2]["fatores"]["SC"] == pytest.approx(C.GAMA_Q["sobrecarga"][0] * C.PSI["cobertura"][0])
    assert cb["ELU %s" % v2]["fatores"]["PP"] == C.GAMA_G["metálica"][0]
    assert cb["ELU SC+%s" % v2]["fatores"][v2] == pytest.approx(C.GAMA_Q["vento"][0] * C.PSI["vento"][0])
    assert "ELU %s suc" % v2 in cb
    assert cb["ELU %s" % alto]["fatores"] == {"PP": 1.0, "CP": 1.0, alto: C.GAMA_Q["vento"][0]}
    assert "ELU SC+%s" % alto not in cb
    # só com os nomes (a calibração exporta assim): a regra antiga, pelo nome
    cb_nomes = AE.combinacoes(list(casos))
    assert "ELU SC+%s" % v2 not in cb_nomes and "ELU SC+%s" % alto in cb_nomes


# ------------------------------------------------------------------ N1: o C_t pela ligação parafusada do 3D

def _furo(doc, barra, x_mm, parafuso=None, d_furo=17.5, lateral=0.0):
    """o marcador de furo na barra a x_mm do início (o eixo do furo em z; `lateral` desloca em y)"""
    a = np.array(barra.inicio, float)
    e = (np.array(barra.fim, float) - a) / np.linalg.norm(np.array(barra.fim, float) - a)
    p = a + e * x_mm + np.array([0.0, lateral, 0.0])
    s = Solido(nome="FURO", vertices=[tuple(p), tuple(p + [1, 0, 0]), tuple(p + [0, 1, 0]), tuple(p + [0, 0, 1])],
               faces=[[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
    s.atributos = {"furo": {"d": d_furo, "ponto": list(p), "eixo": [0.0, 0.0, 1.0], "profundidade": 3.0, "peca": barra.id,
                            "parafuso": parafuso}}
    doc.add(s)


def test_n1_ligacao_pelos_furos_do_3d():
    """a cantoneira de 2 m com 3 parafusos M16 numa ponta (a 40, 100 e 160 mm: ℓc = 12 cm) e 2 na outra (a 40 e 100 mm do
    fim: ℓc = 6 cm), mais um furo no meio (a 1 m, de outra ligação: a mais de 300 mm, 6.3.10, não entra). Vale a ponta de
    menor ℓc: 2 parafusos na linha, ℓc = 6 cm, Ø 16 mm (o furo-padrão 17,5 = 16 + 1,5). Os dois furos lado a lado (o
    mesmo x) contam uma vez na linha"""
    doc = Documento(nome="n1")
    b = Barra(inicio=(0.0, 0.0, 0.0), fim=(2000.0, 0.0, 0.0), perfil=L, papel="diagonal")
    doc.add(b)
    for x in (40.0, 100.0, 160.0):
        _furo(doc, b, x)
    _furo(doc, b, 1000.0)
    for x in (1960.0, 1900.0):
        _furo(doc, b, x)
        _furo(doc, b, x, lateral=40.0)                  # a segunda linha de gabarito
    furos = AE._furos_das_pecas(doc)
    assert len(furos[b.id]["furos"]) == 8 and furos[b.id]["L"] == pytest.approx(2.0)
    M = {"barras": [{"ids": [b.id]}], "furos_por_peca": furos}
    lig = VP.ligacao_da_peca(M, {"barras": [0]})
    assert lig["lc"] == pytest.approx(6.0) and lig["n_parafusos"] == 2 and lig["d_parafuso"] == pytest.approx(1.6)
    assert lig["soldada"] is False and "parafusos do 3D" in lig["fonte"]
    # sem furos: nada (o núcleo adota C_t = 0,60)
    assert VP.ligacao_da_peca({"barras": [{"ids": ["x"]}], "furos_por_peca": furos}, {"barras": [0]}) is None


def test_n1_resistencia_a_tracao_com_a_ligacao_e_sem_ela():
    """a cantoneira L 1½"×1/8" com ℓc = 6 cm: C_t = 1 − e_c/ℓc (NBR 8800:2024, 5.2.5-c); sem a ligação, o piso do núcleo
    (nbr8800.ct_sem_ligacao). A chave do cache separa as duas"""
    from nucleo import nbr8800
    lig = {"lc": 6.0, "n_parafusos": 2, "d_parafuso": 1.6, "soldada": False, "fonte": "parafusos do 3D (teste)"}
    cache = {}
    com = VP.resistencias(L, "ASTM A36", 1.0, 1.0, 1.0, cache, ligacao=lig)
    sem = VP.resistencias(L, "ASTM A36", 1.0, 1.0, 1.0, cache)
    assert com["erro"] is None and sem["erro"] is None and len(cache) == 2
    ec = nbr8800.excentricidade_ligacao(nbr8800._perfil_obj(L))[0]
    assert com["Ct"] == pytest.approx(round(1.0 - ec / 6.0, 4), abs=1e-4)
    # sem a ligação no modelo: o piso do núcleo (cantoneira laminada: A_c/A_g, decisão do usuário de 14/10)
    assert sem["Ct"] == pytest.approx(round(nbr8800.ct_sem_ligacao(nbr8800._perfil_obj(L)), 4), abs=1e-4)
    assert com["ligacao"] == lig["fonte"] and any("pela ligação" in o for o in com["obs"])
    assert any("sem parafusos na peça" in o and "adotado" in o for o in sem["obs"])


def test_n1_banzo_continuo_ruptura_so_nas_pontas():
    """decisão do usuário (14/10): no banzo contínuo a ruptura da seção líquida só vale nas pontas da peça — os trechos
    extremos da cadeia ficam com a resistência de ponta ligada e os do meio com ligacao = {"ponta_ligada": False} (a outra
    entrada do cache de resistências); a alma (diagonal, montante) é peça de ponta ligada"""
    r = AE.calcular(_galpao(banzo_inteiro=True), dict(PAR, vento=False))
    ver = r["verificacao"]
    banzos = [pc for pc in ver["pecas"] if pc["papel"] == "banzo_inf"]
    assert all(pc["nb"] == 4 for pc in banzos)                          # partido nos 3 montantes
    almas = [pc for pc in ver["pecas"] if pc["papel"] in ("diagonal", "montante")]
    assert banzos and almas
    assert all("res_meio" in pc and pc["res_meio"] != pc["res"] for pc in banzos)
    assert all("res_meio" not in pc for pc in almas)
    assert VP._chave_ligacao(VP.PONTA_CORRIDA) == (("ponta_ligada", False),)
    assert VP.banzo_continuo([{"papel_trelica": "banzo_sup", "papel": "banzo"}] * 2, {"barras": [0, 1]})
    assert not VP.banzo_continuo([{"papel_trelica": "banzo_sup", "papel": "banzo"}], {"barras": [0]})


def test_m4_terca_de_parede_presa_na_lateral_dos_pilares_liga_o_fechado():
    """as fiadas de fechamento lançadas como "terça" (presas só na lateral dos pilares, sem banzo nem viga): terças de
    parede — o fechado liga; as terças do telhado (nos banzos) não contam"""
    doc = _galpao(longarinas=True)
    for e in doc.barras:
        if e.papel == "longarina":
            e.papel = "terça"
    M = AE.montar(doc, PAR)
    assert M["fechamento"]["longarinas"] == 0 and M["fechamento"]["tercas_parede"] == 12
    _, info, _ = AE.cargas(M)
    assert info["vento"]["modo"] == "fechado" and "terça(s) de parede" in info["vento"]["motivo"]
