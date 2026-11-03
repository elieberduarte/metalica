# -*- coding: utf-8 -*-
"""Pré-moldado (em desenvolvimento, só no modo dev): NBR 6118 (flexão, cisalhamento, pilar com
2ª ordem), NBR 9062 (cálice, içamento) e o galpão pré-moldado de ponta a ponta."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from premoldado import galpao as G
from premoldado import nbr6118 as N
from premoldado import nbr9062 as N9
from premoldado.concreto import Concreto, aco, cobrimento
from nucleo.base import ErroDeDados


def test_materiais_c30():
    c = Concreto(30, "granito")
    assert c.fcd == pytest.approx(3.0 / 1.4)
    assert c.fctm_MPa == pytest.approx(0.3 * 30 ** (2 / 3))
    assert c.Eci * 10 == pytest.approx(5600 * math.sqrt(30))
    assert c.Ecs == pytest.approx((0.8 + 0.2 * 30 / 80) * c.Eci)
    assert c.eta_c == 1.0 and Concreto(50).eta_c == pytest.approx((40 / 50) ** (1 / 3))
    assert cobrimento("II", "pilar", pre_fabricado=True) == pytest.approx(2.5)


def test_flexao_simples_caso_de_livro():
    # 20 × 50, d = 45, Md = 100 kN·m, C25 / CA-50 → As ≈ 5,6 cm²
    v, dd = N.flexao_simples(20, 50, 45, 10000, Concreto(25), aco("CA-50"))
    assert dd["As"] == pytest.approx(5.62, abs=0.05)
    assert dd["x_d"] < 0.45


def test_cisalhamento_modelo_I():
    c = Concreto(25)
    vs, dd = N.cisalhamento(20, 45, 150, c, aco("CA-50"))
    assert dd["VRd2"] == pytest.approx(0.27 * (1 - 25 / 250) * c.fcd * 20 * 45)
    assert dd["Vc"] == pytest.approx(0.6 * c.fctd * 20 * 45)
    fi, s = N.estribos(dd["asw"], dd["s_max"])
    assert s >= 7.5 and 2 * {5.0: 0.196, 6.3: 0.312, 8.0: 0.503, 10.0: 0.785}[fi] / s * 100 >= dd["asw"] - 1e-6


def test_momento_resistente_sem_normal_bate_com_a_conta():
    c, a = Concreto(30), aco("CA-50")
    sec = N.SecaoRetangular.simetrica(40, 40, 6.03, 4.0)            # 3 ø16 em cada face
    M, x = N.momento_resistente(sec, 0.0, c, a)
    # As·fyd·z com z ≈ d − 0,4x (a armadura de compressão quase não trabalha)
    assert M == pytest.approx(6.03 * a.fyd * (36 - 0.4 * x), rel=0.05)


def test_diagrama_mnr_vetorizado_igual_ao_escalar():
    c, a = Concreto(30), aco("CA-50")
    sec = N.ArmaduraPilar(3, 1, 16.0).secao(40, 40, 4.0)
    ks, Ms = N.diagrama_mnr(sec, 1000.0, c, a)
    for k in (1e-5, 5e-5, 1e-4):
        assert float(np.interp(k, ks, Ms)) == pytest.approx(N.momento_curvatura(sec, 1000.0, k, c, a), rel=0.01)


def test_pilar_curto_sem_segunda_ordem_e_esbelto_com():
    c, a = Concreto(30), aco("CA-50")
    arm = N.ArmaduraPilar(3, 1, 16.0)
    # curto: λ = 300·√12/40 = 26 < λ1 → Md,tot = M1
    v, dd = N.pilar_direcao(40, 40, arm, 4.0, 300, 300, 800, 4000, 1.0, c, a)
    assert dd["lambda"] < dd["lambda1"] and v.Sd == pytest.approx(max(4000, 800 * (1.5 + 0.03 * 40)))
    # esbelto (λ ≈ 104): o momento total cresce e a fluência entra
    v2, d2 = N.pilar_direcao(40, 40, arm, 4.0, 600, 1200, 800, 4000, 1.0, c, a, Nsg=600, phi=2.0)
    assert d2["lambda"] > 90 and d2["ecc"] > 0 and v2.Sd > 4000


def test_calice_tabela15_e_hsfd():
    assert N9.embutimento_tabela15(10, 1000, 50, "rugosa") == pytest.approx(1.5 * 50)
    assert N9.embutimento_tabela15(1e6, 10, 50, "rugosa") == pytest.approx(2.0 * 50)
    assert N9.embutimento_tabela15(1.075 * 1000 * 50, 1000, 50, "chaves") == pytest.approx((1.2 + 0.2) * 50)
    # a forma geral com enb = h/4, a = Lemb/10 reproduz a expressão impressa (7.7.3.1)
    Md, Nd, Vd, h, L, mu = 20000.0, 300.0, 40.0, 50.0, 100.0, 0.6
    Hs, Nb = N9._hsfd_geral(Md, Nd, Vd, h, L, mu, h / 4, L / 10)
    k = 0.1 * L - 0.75 * mu * h
    impresso = (Md - Nd * (0.25 * h + mu * k / (1 + mu ** 2)) + Vd * (L - k / (1 + mu ** 2))) / (0.8 * L + mu * h)
    assert Hs == pytest.approx(impresso) and Nb == pytest.approx((Nd - mu * Vd) / (1 + mu ** 2))
    # pequena excentricidade, interface lisa (μ = 0): 1,5·Md/Lemb + 1,25·Vd
    Hp, _ = N9._hsfd_geral(Md, Nd, Vd, h, L, 0.0, 0.0, L / 6)
    assert Hp == pytest.approx(1.5 * Md / L + 1.25 * Vd)


def test_icamento_carga_dinamica():
    c, a = Concreto(35), aco("CA-50")
    r = N9.icamento_pilar(50, 45, 1000, 6.03, 40, c, a)
    gk = 25 * 0.5 * 0.45 / 100
    assert r.dados["Md"] == pytest.approx(1.3 * 1.3 * 0.0214 * gk * 1000 ** 2)
    assert r.ok


def test_galpao_da_sala_dos_compressores():
    """o caso de teste do usuário: a Sala dos Compressores com pilares de concreto de 9 m em Cascavel"""
    d = G.DadosGalpaoPM(nome="Sala dos Compressores (teste)", local="Cascavel-PR")
    p = G.dimensionar(d)
    assert p.erros == [] and p.ok, (p.erros, [(q.tipo, q.resultado.razao) for q in p.pilares])
    tipos = {q.tipo: q for q in p.pilares}
    assert set(tipos) == {"canto", "intermediário"}
    for q in p.pilares:
        lam = 2 * d.altura_pilar * 100 * math.sqrt(12) / min(q.b, q.h)
        assert lam <= 140
        assert q.comprimento_total > d.altura_pilar
    assert sum(q.quantidade for q in p.pilares) == 2 * d.n_porticos
    assert any(l["marca"].startswith("CL") for l in p.lista)
    assert all(r.ok for r in p.calices + p.icamento)
    # o cintamento do topo (NBR 9062, 6.2.3): γn·Hd/fyd, uma verificação por tipo de pilar
    cint = [r for r in p.icamento if r.elemento.startswith("Cintamento")]
    assert len(cint) == 2
    for r in cint:
        v = r.verificacoes[0]
        assert 0 < v.Sd <= v.Rd


def test_pre_fabricado_usa_os_coeficientes_da_9062():
    assert N9.coeficientes(True) == (1.3, 1.10) and N9.coeficientes(False) == (1.4, 1.15)


def test_consolo_curto_tirante_pela_9062():
    c, a = Concreto(35), aco("CA-50")
    r = N9.consolo(40, 50, 25, 300, c, a, apoio="elastômero")
    d = 50 - (3.0 + 12.5 / 20)
    gn = 1.2
    Asv = (0.1 + 25 / d) * gn * 300 / a.fyd
    As_tir = Asv + gn * 0.16 * 300 / a.fyd
    assert r.dados["a_d"] == pytest.approx(25 / d)
    assert r.verificacoes[0].Sd == pytest.approx(As_tir)
    assert r.dados["As_tir"] >= As_tir and r.ok


def test_consolo_muito_curto_e_longo():
    c, a = Concreto(35), aco("CA-50")
    assert "muito curto" in N9.consolo(40, 60, 10, 200, c, a).dados["tipo"]
    assert "balanço" in N9.consolo(40, 30, 40, 50, c, a).dados["tipo"]
    r = N9.consolo(40, 20, 60, 50, c, a)          # a/d > 2: é viga
    assert not r.ok and r.indeterminada


def test_elastomero_simples():
    e = N9.elastomero_simples(15, 30, 1.0, 150, 60, 20, 60)
    assert e.ok
    assert e.verificacoes[0].Sd == pytest.approx(210 / 450 * 10)       # σ = N/(ab) em MPa
    ruim = N9.elastomero_simples(10, 10, 1.0, 150, 60, 20, 60)
    assert not ruim.ok


def test_catalogo_valores_da_norma():
    from premoldado import catalogo as C
    c = C.catalogo("basalto")
    c35 = next(k for k in c["concretos"] if k["fck"] == 35)
    assert c35["fcd_14"] == pytest.approx(25.0) and c35["fcd_13"] == pytest.approx(35 / 1.3)
    assert c35["Eci"] == pytest.approx(1.2 * 5600 * math.sqrt(35))
    ca50 = next(a for a in c["acos"] if a["nome"] == "CA-50")
    assert ca50["fyd_115"] == pytest.approx(500 / 1.15) and ca50["fyd_110"] == pytest.approx(500 / 1.10)
    # ℓb do ø16 em C35 (boa aderência): (1,6/4)·43,48/(2,25·0,7·0,321/1,4) ≈ 48,2 → 49 cm
    b16 = next(b for b in c["bitolas"] if b["bitola"] == 16.0)
    assert b16["lb"]["C35"] == 49
    cob = next(k for k in c["cobrimentos"] if k["caa"] == "II")
    assert (cob["viga_pilar"], cob["viga_pilar_pf"], cob["classe_minima"]) == (30, 25, "C25")
    s = next(x for x in c["secoes_pilar"] if (x["b"], x["h"]) == (45, 50))
    assert s["L140"] == pytest.approx(140 * 45 / math.sqrt(12) / 2 / 100)


def test_ligacoes_avulsas_iguais_as_rotinas():
    from premoldado import ligacoes as L
    from premoldado.concreto import aco as aco_armadura
    r = L.calcular("calice", {"b": 45, "h": 50, "Nd": "150", "Md": "200", "Vd": "30,0", "fck": 35})
    direto = N9.calice(45, 50, 150, 20000, 30, Concreto(35), aco_armadura("CA-50"), 16)
    assert r["dados"]["Lemb"] == direto.dados["Lemb"] and r["razao"] == pytest.approx(direto.razao, abs=1e-3)
    assert r["dados"]["barras"]["vertical"] == list(direto.dados["barras"]["vertical"])
    r = L.calcular("consolo", {"b": 40, "h": 50, "a": 25, "Fd": 300, "Hd": ""})
    assert r["ok"] and r["dados"]["Hd"] == pytest.approx(0.16 * 300)
    assert not L.calcular("elastomero", {"a": 15, "b": 30, "h": 1, "Ngk": 600, "Nqk": 60})["ok"]
    # pré-fabricado: γc 1,3 e γs 1,10
    rp = L.calcular("consolo", {"b": 40, "h": 50, "a": 25, "Fd": 300, "pre_fabricado": True})
    assert rp["dados"]["gn"] == pytest.approx(1.1)
    with pytest.raises(Exception):
        L.calcular("calice", {"b": "x", "h": 50, "Nd": 1, "Md": 1})


def test_vaos_do_galpao_pelos_eixos_da_planta():
    from premoldado import web as W
    eixos = {"eixo_g": [1, 0], "numeros": [{"nome": "1", "pos": 0}, {"nome": "2", "pos": 6000}, {"nome": "3", "pos": 12500}],
             "letras": [{"nome": "A", "pos": 0}, {"nome": "B", "pos": 4000}, {"nome": "C", "pos": 10000}]}
    r = W.vaos_dos_eixos(eixos)
    assert r["vao"] == pytest.approx(10.0) and r["vaos_longitudinais"] == [6.0, 6.5]
    assert r["avisos"] and "intermediários" in r["avisos"][0]         # 3 eixos com letra: só os extremos
    with pytest.raises(Exception):
        W.vaos_dos_eixos(None)


# ------------------------------------------------------------------ vigas (NBR 6118 e NBR 9062)

from premoldado import vigas as V


def _meio(fck=35):
    return V.MeioViga(Concreto(fck, "basalto"), aco("CA-50"), 2.5)


def test_secoes_de_viga_propriedades():
    s = V.secao_I(30, 10, 12, 80)
    A = 2 * 30 * 10 + 12 * 60
    assert s.A == pytest.approx(A) and s.yc == pytest.approx(40)
    I = 2 * (30 * 10 ** 3 / 12 + 300 * 35 ** 2) + 12 * 60 ** 3 / 12
    assert s.I == pytest.approx(I)
    u = V.secao_U(60, 45, 8, 10)
    assert u.A == pytest.approx(60 * 10 + 16 * 35) and u.almas == 2 and u.bw == 16
    assert u.perimetro == pytest.approx(60 + 2 * 45 + 2 * 8 + 2 * 35 + 44)
    assert len(u.contorno()) == 8
    assert V.secao_retangular(20, 50).invertida().camadas == [(20, 50)]


def test_flexao_da_secao_composta_igual_a_retangular():
    c, a = Concreto(25), aco("CA-50")
    v, dd = V.flexao(V.secao_retangular(20, 50), 45, 10000, c, a)
    _v, ref = N.flexao_simples(20, 50, 45, 10000, c, a)
    assert dd["As"] == pytest.approx(ref["As"], rel=1e-4)
    # T com a linha neutra na mesa: igual à retangular com a largura da mesa
    vt, dt = V.flexao(V.secao_T(80, 12, 20, 50), 45, 10000, c, a)
    y = 45 - math.sqrt(45 ** 2 - 2 * 10000 / (c.sigma_cd * 80))       # λx dentro da mesa (12 cm)
    assert y < 12 and dt["As"] == pytest.approx(10000 / (a.fyd * (45 - y / 2)), rel=1e-3)


def test_estadio2_retangular_pela_equacao_do_2o_grau():
    s = V.secao_retangular(20, 50)
    As, d, ae = 6.0, 45.0, 15.0
    x, I2 = V.estadio2(s, As, d, 0.0, 4.0, ae)
    # b·x²/2 = αe·As·(d − x)
    xa = (-ae * As + math.sqrt((ae * As) ** 2 + 2 * 20 * ae * As * d)) / 20
    assert x == pytest.approx(xa, rel=1e-6)
    assert I2 == pytest.approx(20 * xa ** 3 / 3 + ae * As * (d - xa) ** 2, rel=1e-6)


def test_estatica_e_flecha_elastica():
    xs = np.linspace(0, 600, 41)
    w = np.full_like(xs, 0.2)                                  # 20 kN/m
    RA, RB, V_, M = V.estatica(xs, w)
    assert RA == pytest.approx(60) and RB == pytest.approx(60) and M.max() == pytest.approx(0.2 * 600 ** 2 / 8, rel=1e-3)
    EI = np.full_like(xs, 3000.0 * 20 * 50 ** 3 / 12)
    f, th = V._integral_unitaria(xs, M, EI)
    assert f == pytest.approx(5 * 0.2 * 600 ** 4 / (384 * EI[0]), rel=2e-3)
    assert th == pytest.approx(0.2 * 600 ** 3 / (24 * EI[0]), rel=2e-3)


def test_tabelas_de_tempo_e_retracao():
    assert V.xi_tempo(1) == pytest.approx(0.68 * 0.996, rel=1e-6) and V.xi_tempo(80) == 2.0
    assert V.xi_tempo(20) == pytest.approx(1.64, abs=0.01)             # Tabela 17.1
    assert V.retracao(75, 30, 20) == pytest.approx(0.33) and V.retracao(55, 5, 60) == pytest.approx(0.43)
    assert V.retracao(75, 30, 40) == pytest.approx(0.32)                # interpolação


def test_viga_de_travamento_completa():
    caso = V.CasoViga("VT", "viga de travamento", 6.0, 5.9, g=15, q=10, psi_q=(0.7, 0.6, 0.4))
    v = V.verificar_viga(caso, lambda x: V.secao_retangular(20, 60), _meio())
    titulos = [x.titulo for x in v.resultado.verificacoes]
    for t in ("Flexão", "Cisalhamento", "Abertura de fissuras", "Flecha", "Estabilidade lateral", "Içamento", "Alças"):
        assert any(x.startswith(t) for x in titulos), t
    assert v.armadura["As_inf"] * 1.0 >= 0 and v.ok, [x.resumo() for x in v.resultado.verificacoes if not x.ok]
    # 7.5.1: Asd = (Fd/1,2 + 0,16·Fd)/fyd
    Fd = v.reacoes["Fd"]
    assert v.apoio.verificacoes[0].Sd == pytest.approx((Fd / 1.2 + 0.16 * Fd) / aco("CA-50").fyd)
    # a mais leve que passa entre candidatas
    cand = [("a", lambda x: V.secao_retangular(15, 30)), ("b", lambda x: V.secao_retangular(20, 60))]
    esc = V.dimensionar_viga(caso, cand, _meio())
    assert esc.secao.texto() == "20 × 60" and len(esc.alternativas) == 2 and not esc.alternativas[0]["ok"]


def test_dente_gerber_suspensao_e_consolo():
    caso = V.CasoViga("VT", "viga de travamento", 6.0, 5.9, g=15, q=10, extremidade="dente Gerber")
    v = V.verificar_viga(caso, lambda x: V.secao_retangular(20, 60), _meio())
    tit = [x.titulo for x in v.apoio.verificacoes]
    assert any("suspensão" in t for t in tit) and any(t.startswith("Consolo") for t in tit)
    sus = next(x for x in v.apoio.verificacoes if "suspensão" in x.titulo)
    assert sus.Sd == pytest.approx(1.2 * v.reacoes["Fd"] / aco("CA-50").fyd)       # γn = 1,2 (pré-moldado)
    assert v.apoio.dados["h_dente"] == 30


def test_calha_leve_trava_com_pino():
    caso = V.CasoViga("VC", "viga-calha", 6.3, 6.2, q=1.1, limite_flecha=400)
    v = V.verificar_viga(caso, lambda x: V.secao_U(50, 40, 8, 8), _meio())
    assert v.ok
    pino = [x for x in v.elastomero.verificacoes if x.titulo.startswith("Chumbador")]
    assert pino and v.elastomero.dados["chumbador"] == 16.0
    assert next(x for x in v.elastomero.verificacoes if "tensão mínima" in x.titulo).dispensada


def test_galpao_com_vigas_calha_e_cobertura():
    base = G.dimensionar(G.DadosGalpaoPM())
    d = G.DadosGalpaoPM(vigas_longitudinais="calha", viga_cobertura=True, extremidade_vigas="dente Gerber")
    p = G.dimensionar(d)
    assert p.erros == [] and p.ok, [v.resultado.resumo() for v in p.vigas]
    assert {v.funcao for v in p.vigas} == {"viga-calha", "viga de cobertura"}
    vc = next(v for v in p.vigas if v.funcao == "viga-calha")
    assert vc.quantidade == 2 * len(d.vaos_longitudinais)
    cob = next(v for v in p.vigas if v.funcao == "viga de cobertura")
    assert cob.secao.h > cob.secao_apoio.h                   # a altura acompanha a água
    # as vigas pesam no pilar: a normal máxima cresce
    nd = lambda pp: max(s["Nd"] for q in pp.pilares for s in q.esforcos["situacoes"])
    assert nd(p) > nd(base)
    # os consolos: um no pilar de canto, dois no intermediário
    assert sorted(r.dados["por_pilar"] for r in p.ligacoes) == [1, 2]
    marcas = [l["marca"] for l in p.lista]
    assert any(m.startswith("VC-") for m in marcas) and "VCO" in marcas and "EL-VC" in marcas
    # o momento dos consolos na direção longitudinal (pórtico de canto: uma viga só)
    e = G._excentricidade_consolos(d, 0, 45.0, p.cargas_vigas)
    assert e["PP"] == pytest.approx(p.cargas_vigas["pp_long"] * d.vaos_longitudinais[0] / 2 * (22.5 + d.consolo_a))


def test_modelo3d_pilar_orientado_e_vigas():
    from premoldado import modelo3d
    p = G.dimensionar(G.DadosGalpaoPM(vigas_longitudinais="travamento", viga_cobertura=True))
    doc = modelo3d.documento(p)
    ents = list(doc.entidades.values()) if isinstance(doc.entidades, dict) else list(doc.entidades)
    pil = next(e for e in ents if e.nome.startswith("Pilar canto"))
    v = np.array(pil.vertices)
    q = next(x for x in p.pilares if x.tipo == "canto")
    assert v[:, 0].max() - v[:, 0].min() == pytest.approx(q.b * 10)     # b no comprimento (X)
    assert v[:, 1].max() - v[:, 1].min() == pytest.approx(q.h * 10)     # h no vão (Y)
    assert any(e.camada == modelo3d.CAMADA_VIGAS for e in ents) and any(e.camada == modelo3d.CAMADA_CONSOLOS for e in ents)


# ------------------------------------------------------------------ fundação (NBR 6118, 22.6 e 22.7)

from premoldado import fundacao as FU


def test_distribuicao_no_solo_formulas_classicas():
    r = FU.distribuicao(200, 100, 500, 500 * 20, 0)                  # e = a/10: tudo comprimido
    assert r[0] == 1.0 and r[1] == pytest.approx(500 / 2e4 * (1 + 6 * 20 / 200), rel=1e-3)
    r = FU.distribuicao(200, 100, 500, 500 * 50, 0, n=80)             # e = a/4: triângulo em 3(a/2 − e)
    assert r[0] == pytest.approx(0.75, abs=0.01) and r[1] == pytest.approx(2 * 500 / (3 * 100 * 50), rel=5e-3)
    assert FU.distribuicao(200, 100, 500, 500 * 120, 0) is None      # a resultante fora da base


def test_sapata_rigida_e_solo():
    c, a = Concreto(30), aco("CA-50")
    par = FU.ParametrosFundacao(sigma_adm=150.0)
    sk = [FU.Situacao("G + W", 150.0, 6000.0, 1000.0, 10.0, 2.0)]
    sd = [FU.Situacao("ELU", 210.0, 8400.0, 1400.0, 14.0, 2.8)]
    r = FU.sapata(95, 100, 110, 45, 50, sk, sd, c, a, par)
    dd = r.dados
    assert r.ok and dd["hf"] >= max((dd["ah"] - 100) / 3, (dd["ab"] - 95) / 3, 20)
    solo = r.verificacoes[0]
    assert solo.Sd <= 150.0 + 1e-6
    frac = r.verificacoes[1]
    assert frac.Rd >= 2 / 3 - 1e-9


def test_bloco_sobre_estacas_reacoes_e_tirante():
    c, a = Concreto(30), aco("CA-50")
    par = FU.ParametrosFundacao(tipo="estacas", estaca_carga=400.0, estaca_tracao=50.0)
    sk = [FU.Situacao("G + Q", 600.0, 0.0, 0.0)]
    sd = [FU.Situacao("ELU", 840.0, 0.0, 0.0)]
    r = FU.bloco(95, 100, 110, 45, 50, sk, sd, c, a, par)
    dd = r.dados
    assert r.ok and dd["n_estacas"] == 2 and dd["hf"] >= 20
    # 2 estacas, carga centrada: R = (N + W)/2 e o tirante de Blévot T = R·(e/2 − h/4)/d
    R = (600.0 + dd["W"]) / 2
    assert r.verificacoes[0].Sd == pytest.approx(R, rel=1e-6)
    e = dd["estacas"][1][0] * 2
    d = dd["hf"] - 10.0
    T = 840.0 / 2 * (e / 2 - 50 / 4) / d
    tir = next(v for v in r.verificacoes if "tirante" in v.titulo)
    assert tir.Sd == pytest.approx(T / a.fyd, rel=1e-6)


def test_galpao_com_sapatas_e_estacas():
    p = G.dimensionar(G.DadosGalpaoPM(fundacao="sapata"))
    assert p.ok and len(p.fundacoes) == 2
    assert {l["marca"] for l in p.lista} >= {"SP-C", "SP-I"}
    # o colarinho passa a ter só a altura do embutimento (a base do pilar no topo da sapata)
    cl = next(l for l in p.lista if l["marca"] == "CL-C")
    cal = next(r for r in p.calices if r.dados["direcao"] == "x" and "canto" in r.elemento)
    assert cl["comprimento_m"] == pytest.approx(cal.dados["Lemb_adotado"] / 100, abs=0.01)
    pe = G.dimensionar(G.DadosGalpaoPM(fundacao="estacas", estaca_tracao=100.0))
    assert pe.ok and any(l["marca"].startswith("EST") for l in pe.lista)
    from premoldado import modelo3d
    doc = modelo3d.documento(pe)
    assert any(e.camada == modelo3d.CAMADA_FUNDACOES and e.nome.startswith("Estaca") for e in doc.entidades.values())


# ------------------------------------------------------------------ ponte rolante

def _dados_ponte(**kw):
    base = dict(ponte_rolante=True, pr_roda_max=60, pr_roda_min=20, pr_impacto=0.25, pr_transversal=12, pr_longitudinal=12, pr_altura=6.0)
    base.update(kw)
    return G.DadosGalpaoPM(**base)


def test_fator_das_rodas_pela_linha_de_influencia():
    d = _dados_ponte()
    # canto: uma roda no apoio e a outra a 3 m dentro do vão de 4 m → 1 + 1/4
    assert G.fator_rodas(d, 0) == pytest.approx(1.25, abs=1e-3)
    # entre os vãos de 4 e 6,3 m: a outra roda a 3 m dentro do de 6,3 → 1 + 3,3/6,3
    assert G.fator_rodas(d, 1) == pytest.approx(1 + 3.3 / 6.3, abs=1e-3)
    assert G.fator_rodas(_dados_ponte(pr_rodas=1), 3) == pytest.approx(1.0)


def test_portico_com_ponte_equilibrio_e_excentricidade():
    d = _dados_ponte(pr_transversal=0.0, pr_roda_min=0.0, pr_impacto=0.0)
    from premoldado.concreto import Concreto as C_
    por = G._portico(d, 5.0, 45, 50, C_(35), G._vento(d), {}, 1.0)
    c = por["PR esq →"]
    # a roda de 60 kN só no pilar da esquerda: toda a normal nele
    assert c["pilar_esq"]["N"] == pytest.approx(60.0, abs=0.5) and abs(c["pilar_dir"]["N"]) < 0.5
    # o momento da excentricidade (60 kN × 60 cm) se reparte entre os dois pilares pela cobertura rotulada
    assert abs(c["pilar_esq"]["M_base"]) + abs(c["pilar_dir"]["M_base"]) == pytest.approx(60 * 60, rel=0.02)


def test_galpao_com_ponte_consolo_fadiga_e_els():
    p = G.dimensionar(_dados_ponte())
    assert p.erros == [] and p.ok
    cons = [r for r in p.ligacoes if r.dados.get("ponte")]
    assert len(cons) == 2
    for r in cons:
        fad = next(v for v in r.verificacoes if "fadiga do tirante" in v.titulo)
        assert fad.Rd == 85 and fad.ok
    assert any("viga de rolamento" in r.elemento for r in p.icamento)
    # as combinações da ponte chegam aos pilares
    assert any("PR" in s["comb"] for q in p.pilares for s in q.esforcos["situacoes"])
    with pytest.raises(Exception):
        G.DadosGalpaoPM(ponte_rolante=True).validar()                  # sem a carga da roda


# ------------------------------------------------------------------ detalhamento 2D dos pilares

def test_detalhamento_pilares_quadro_e_desenho():
    from premoldado import detalhe2d as D
    from nucleo2d.desenho import Desenho
    assert D._suplementares(3, 40, 5.0) == 1              # a do meio a 20 cm do canto > 20φt = 10 cm
    assert D._suplementares(4, 30, 10.0) == 0             # 20φt = 20 cm cobre as duas intermediárias
    p = G.dimensionar(_dados_ponte(vigas_longitudinais="calha"))
    for pil in p.pilares:
        pos = D.posicoes(p, pil)
        n1 = pos[0]
        assert n1["qtd"] == pil.armadura.n_total and n1["fi"] == pil.armadura.bitola
        assert n1["comp"] == pytest.approx(pil.comprimento_total * 100 - 2 * 2.5)
        assert any(q["N"] == 3 for q in pos)                  # o cintamento do topo
        kg = sum(k for _f, _m, k in D.resumo_aco(pos, pil.quantidade))
        assert kg > 0
    des = D.desenho(p)
    assert des.tamanho > 100
    volta = Desenho.de_dict(des.dict())                      # o CAD lê o que foi gravado
    assert volta.tamanho == des.tamanho
    textos = " ".join(e.texto for e in des.por_tipo("texto"))
    assert "QUADRO DE FERROS" in textos and "CORTE A-A" in textos and "consolo da ponte" in textos


def test_planta_de_locacao_dos_pilares():
    """A planta de locação (pedido do usuário, 29/09): um pilar em corte em cada cruzamento dos eixos e em cada
    posição de oitão, os eixos com as bolinhas, a cadeia entre eixos com a total, o quadro e o detalhe de cada tipo."""
    from premoldado import locacao as LC
    from nucleo2d.desenho import Desenho, Cota
    d = G.DadosGalpaoPM(fundacao="sapata", pilares_oitao=[(1, 4.0)])
    p = G.dimensionar(d)
    des = LC.desenho(p)
    pilares = [e for e in des.por_tipo("polilinha") if e.camada == "CORTE" and (e.atributos or {}).get("eixo")]
    assert len(pilares) == 2 * d.n_porticos + 1
    assert {(e.atributos or {}).get("eixo") for e in pilares} >= {"1/A", "1/B", "%d/B" % d.n_porticos, "1/oitão 4,00"}
    # o pilar centrado no cruzamento: 2/A em (vão 1, 0)
    p2a = next(e for e in pilares if e.atributos["eixo"] == "2/A")
    cx = sum(v[0] for v in p2a.vertices) / 4
    cy = sum(v[1] for v in p2a.vertices) / 4
    assert cx == pytest.approx(d.vaos_longitudinais[0] * 1000.0) and cy == pytest.approx(0.0)
    cotas = [round(abs(c.p2[0] - c.p1[0])) for c in des.entidades.values() if isinstance(c, Cota) and c.modo == "h" and not c.texto]
    assert round(d.comprimento * 1000.0) in cotas                                   # a total
    textos = " ".join(e.texto for e in des.por_tipo("texto"))
    assert "PLANTA DE LOCAÇÃO DOS PILARES" in textos and "QUADRO DOS PILARES" in textos and "P-O" in textos
    assert "LOCAÇÃO P-C" in textos and "sapata" in textos
    assert Desenho.de_dict(des.dict()).tamanho == des.tamanho                       # o CAD lê o que foi gravado


# ------------------------------------------------------------------ protensão (pré-tração)

from premoldado import protensao as PR


def test_protensao_tabelas_e_diagrama():
    assert PR.psi1000(0.7) == pytest.approx(2.5) and PR.psi1000(0.75) == pytest.approx(3.0) and PR.psi1000(0.45) == 0.0
    assert PR.fluencia(35, 75, 30, 20) == pytest.approx(2.2) and PR.fluencia(60, 55, 5, 60) == pytest.approx(2.1)
    # diagrama bilinear: elástico até fpyd = 0,9·190/1,15
    assert PR.sigma_p(5.0, 190.0) == pytest.approx(PR.EP * 0.005)
    assert PR.sigma_p(35.0, 190.0) == pytest.approx(190 / 1.15)
    assert PR.cobrimento_protendido("II") == pytest.approx(3.0) and PR.cobrimento_protendido("I") == pytest.approx(2.5)


def test_viga_protendida_perdas_e_verificacoes():
    m = V.MeioViga(Concreto(40, "basalto"), aco("CA-50"), 2.5)
    caso = V.CasoViga("VCO", "viga de cobertura", 15.0, 15.0, g=3.0, q=2.0, psi_q=(0.8, 0.7, 0.6), succao=3.0)
    v = PR.verificar(caso, lambda x: V.secao_I(40, 15, 12, 90), m, PR.Protensao(n=4))
    assert v.ok, [x.resumo() for x in v.resultado.verificacoes if not x.ok]
    pe = v.perdas
    assert pe["sigma_pi"] == pytest.approx(0.74 * 190)
    assert pe["sigma_pi"] > pe["sigma_pa"] > pe["sigma_p0"] > pe["sigma_pinf"] > 0
    assert 0.10 < pe["perda_total"] < 0.35
    tit = " ".join(x.titulo for x in v.resultado.verificacoes)
    for t in ("Ato da protensão", "ELS-F", "ELS-D", "ELU — flexão com a armadura ativa", "Contraflecha", "Cisalhamento"):
        assert t in tit
    # mais cordoalhas numa seção baixa: a tração no topo na liberação passa do limite
    ruim = PR.verificar(caso, lambda x: V.secao_I(30, 12, 10, 70), m, PR.Protensao(n=6))
    assert not next(x for x in ruim.resultado.verificacoes if x.titulo.startswith("Ato da protensão — tração")).ok


def test_galpao_com_tercas_e_viga_protendidas():
    d = G.DadosGalpaoPM(viga_cobertura=True, viga_cobertura_protendida=True, tercas_protendidas=True, cobertura_permanente=0.12)
    p = G.dimensionar(d)
    assert p.ok, [(v.funcao, v.alternativas) for v in p.vigas]
    funcoes = {v.funcao: v for v in p.vigas}
    assert isinstance(funcoes["terça"], PR.VigaProtendida) and isinstance(funcoes["viga de cobertura"], PR.VigaProtendida)
    assert p.cargas_vigas["cp_tercas"] > 0
    assert any(l["marca"].startswith("TR") for l in p.lista)
    with pytest.raises(Exception):
        G.DadosGalpaoPM(tercas_protendidas=True).validar()               # sem a viga de cobertura
    from premoldado import modelo3d
    doc = modelo3d.documento(p)
    assert any(e.nome.startswith("Terça") for e in doc.entidades.values())


def test_json_da_tela_sem_infinito():
    """o navegador não lê Infinity/NaN: uma seção tentada que reprova tem razão infinita"""
    import json
    from premoldado import web as W
    p = G.dimensionar(G.DadosGalpaoPM(viga_cobertura=True, viga_cobertura_protendida=True, tercas_protendidas=True, cobertura_permanente=0.12))
    texto = json.dumps(W.para_json(p), allow_nan=False)
    assert "lista" in json.loads(texto)


# ------------------------------------------------------------------ cobertura de outra obra e níveis

def test_cobertura_de_outra_obra_alinhada_pelos_eixos(tmp_path):
    import json as _j
    from projetos import Projetos
    from nucleo3d.modelo import Documento
    from nucleo3d.geometria import extrudar
    from premoldado import cobertura as CB, modelo3d
    g = Projetos(str(tmp_path))
    r = g.criar("Cobertura teste", "", "", "", tipo="ifc")
    s = r["slug"]
    # a obra da cobertura com os numerados ao longo de Y (como a da Sooro) e os apoios em x = 20000 e 11720 (8,28 m)
    g._atualizar(s, eixos={"eixo_g": [0.0, 1.0], "numeros": [{"nome": "1", "pos": 1000.0}, {"nome": "2", "pos": 5000.0}],
                           "letras": [{"nome": "A", "pos": -20000.0}, {"nome": "B", "pos": -11720.0}], "origem": "usuario"})
    doc = Documento(nome="cob")
    doc.add(extrudar([(-50, -50), (50, -50), (50, 50), (-50, 50)], (0.0, 0.0, 1.0), 100.0, origem=(15000.0, 3000.0, 6000.0), nome="peça"))
    g.salvar_modelo(s, doc.dict())
    nos = [{"nome": "a", "p": [20000.0, 5000.0, 4700.0], "apoiado": True}, {"nome": "b", "p": [11720.0, 5000.0, 6500.0], "apoiado": True}]
    open(os.path.join(g.pasta(s), "calculo.json"), "w", encoding="utf-8").write(_j.dumps({"resultado": {"portico": {"nos": nos}}}))
    info = CB.alinhamento(g, s)
    ap = sorted(info["apoios"], key=lambda a: a[1])
    assert ap[0][0] == pytest.approx(4000.0, abs=1) and ap[0][1] == pytest.approx(0.0, abs=1)        # eixo 2 em X = 4 m; fila A
    assert ap[1][1] == pytest.approx(8280.0, abs=1) and info["vao_apoios"] == pytest.approx(8280.0)
    p = G.dimensionar(G.DadosGalpaoPM())
    alvo = modelo3d.documento(p)
    n0 = len(alvo.entidades)
    info = CB.trazer(g, s, alvo)
    assert len(alvo.entidades) == n0 + 2                      # a peça e o grupo da cobertura
    grupo = alvo.entidades[info["grupo"]]
    peca = next(e for e in alvo.entidades.values() if e.camada == info["camada"] and e.tipo != "grupo")
    assert grupo.tipo == "grupo" and grupo.filhos == [peca.id] and peca.grupo == grupo.id
    v = np.array(peca.vertices)
    assert v[:, 0].mean() == pytest.approx(2000.0, abs=1) and v[:, 1].mean() == pytest.approx(5000.0, abs=1)
    apont = CB.conferir(info, CB.pilares_em_planta(p), 9000.0, 8280.0)
    assert any("2 níveis" in t for t in apont) and any("acima" in t for t in apont)
    nomes = [n["nome"] for n in CB.niveis(p, info)]
    assert "Boca do cálice" in nomes and "Topo dos pilares" in nomes and "Apoio da cobertura 1" in nomes


def test_geometria_da_cobertura_pelos_chumbadores_e_pilares_de_oitao(tmp_path):
    """duas filas de apoios a 14,67 m com 7 pórticos, dois apoios no oitão: o galpão que a cobertura pede"""
    from premoldado import cobertura as CB
    xs = [0.0, 4000.0, 10300.0, 14300.0, 19235.0, 24170.0, 29102.0]
    ap = [(x, 0.0, 5100.0) for x in xs] + [(x, 14670.0, 5100.0) for x in xs] + [(0.0, 3200.0, 5100.0), (29102.0, 9450.0, 5100.0)]
    geo = CB.geometria({"apoios": ap, "fonte": "teste"})
    assert geo["vao"] == pytest.approx(14.67) and geo["altura_pilar"] == pytest.approx(5.1)
    assert geo["vaos_longitudinais"] == pytest.approx([4.0, 6.3, 4.0, 4.935, 4.935, 4.932])
    assert geo["pilares_oitao"] == [(1, 3.2), (7, 9.45)]
    d = G.DadosGalpaoPM(vao=geo["vao"], vaos_longitudinais=geo["vaos_longitudinais"], altura_pilar=geo["altura_pilar"],
                        pilares_oitao=geo["pilares_oitao"], fundacao="sapata")
    p = G.dimensionar(d)
    assert p.ok and {q.tipo for q in p.pilares} == {"canto", "intermediário", "oitão"}
    oit = next(q for q in p.pilares if q.tipo == "oitão")
    assert oit.quantidade == 2 and any(l["marca"] == "P-O" for l in p.lista) and any(l["marca"] == "SP-O" for l in p.lista)
    assert not CB.conferir({"apoios": ap, "fonte": "teste", "vao_apoios": 14670.0}, CB.pilares_em_planta(p), 5100.0, 14670.0)
    from premoldado import modelo3d
    doc = modelo3d.documento(p)
    assert sum(1 for e in doc.entidades.values() if e.nome.startswith("Pilar oitão")) == 2


def test_planta_de_locacao_do_detalhe2d():
    from premoldado import detalhe2d as D
    from nucleo2d.desenho import Desenho
    p = G.dimensionar(G.DadosGalpaoPM(fundacao="sapata", pilares_oitao=[(1, 3.0)]))
    des = D.planta_locacao(p)
    assert des.escala == 100.0
    marcas = [e.atributos.get("peca") for e in des.entidades.values() if e.atributos.get("peca")]
    assert marcas.count("P-C") == 4 and marcas.count("P-I") == 10 and marcas.count("P-O") == 1
    assert any(m.startswith("SP-") for m in marcas) and any(m.startswith("CL-") for m in marcas)
    assert len(des.por_tipo("circulo")) >= 2 * (len(p.dados.vaos_longitudinais) + 1) + 4        # os balões dos eixos
    assert Desenho.de_dict(des.dict()).tamanho == des.tamanho


# ------------------------------------------------------------------ a estrutura lançada na planta → 3D

def test_planta_estrutura_vira_modelo_3d():
    from nucleo2d.desenho import Desenho, Polilinha, Linha
    from nucleo3d import de_planta_estrutura as D
    des = Desenho(nome="t")
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(-150, -200), (150, -200), (150, 200), (-150, 200)], fechada=True,
                      atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 30, "h": 40},
                                 "nivel_base": -1100, "nivel_topo": "Topo", "marca": "P1", "centro": [0, 0]}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(3850, -150), (4150, -150), (4150, 150), (3850, 150)], fechada=True,
                      atributos={"elemento": "pilar", "material": "aco", "secao": {"perfil": "W 310×38,7"}, "nivel_base": 0, "nivel_topo": 5100,
                                 "marca": "P2", "centro": [4000, 0]}))
    des.add(Linha(camada="ESTRUTURA", a=(0, 0), b=(4000, 0), atributos={"elemento": "viga", "material": "concreto",
                  "secao": {"tipo": "T", "bf": 30, "hf": 10, "bw": 12, "h": 50}, "nivel_topo": 5100, "marca": "V1"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000)], fechada=True,
                      atributos={"elemento": "fundacao", "tipo": "sapata", "altura": 500, "nivel_topo": -1100, "marca": "S1"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(9000, 0), (9300, 0), (9300, 300), (9000, 300)], fechada=True,
                      atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 30, "h": 30},
                                 "nivel_base": 100, "nivel_topo": 50, "marca": "P9"}))
    doc, avisos = D.modelo_da_planta(des, [{"nome": "Topo", "z": 5100}])
    assert doc.estatisticas()["barras"] == 1 and doc.estatisticas()["solidos"] == 3
    assert avisos and "P9" in avisos[0]
    p1 = next(e for e in doc.entidades.values() if e.nome == "Pilar P1")
    v = np.array(p1.vertices)
    assert (v[:, 0].min(), v[:, 0].max()) == (-150, 150) and (v[:, 1].min(), v[:, 1].max()) == (-200, 200)     # b no X, h no Y
    assert (v[:, 2].min(), v[:, 2].max()) == (-1100, 5100) and p1.volume > 0 and p1.atributos["origem_2d"]
    v1 = next(e for e in doc.entidades.values() if e.nome == "Viga V1")
    vv = np.array(v1.vertices)
    assert vv[:, 2].max() == pytest.approx(5100) and vv[:, 2].min() == pytest.approx(4600) and v1.volume > 0
    p2 = next(e for e in doc.entidades.values() if e.nome == "Pilar P2")
    assert p2.tipo == "barra" and p2.papel == "pilar" and p2.fim[2] == 5100


# ------------------------------------------------------------------ R3: filas com alturas diferentes, uma água, a planta lançada

def test_filas_com_alturas_diferentes_e_cobertura_de_uma_agua():
    """R3 (30/09): a fila B mais alta vira um tipo de pilar à parte (P-CB, P-IB) com a própria altura; a cobertura
    de uma água tem a inclinação pelas alturas; o oitão tem o topo na água; o 3D, as plantas e os níveis seguem."""
    from premoldado import modelo3d as M3, locacao as LC, detalhe2d as D2, cobertura as CB
    d = G.DadosGalpaoPM(vao=14.671, vaos_longitudinais=[4.0, 6.3, 4.0, 4.935], altura_pilar=5.10, altura_pilar_b=6.60, cobertura="uma água",
                        v0=47.0, fundacao="sapata", pilares_oitao=[(1, 3.195)], vigas_longitudinais="travamento")
    assert d.filas_diferentes and d.uma_agua and d.inclinacao_efetiva == pytest.approx(math.degrees(math.atan2(1.5, 14.671)))
    assert d.altura_cumeeira == 6.6 and d.altura_oitao(3.195) == pytest.approx(5.10 + 1.5 * 3.195 / 14.671)
    assert G.tipos_de_pilar(d) == ["canto", "intermediário", "canto B", "intermediário B"]
    p = G.dimensionar(d)
    assert not p.erros
    tipos = {q.tipo: q for q in p.pilares}
    assert set(tipos) == {"canto", "intermediário", "canto B", "intermediário B", "oitão"}
    assert tipos["canto"].quantidade == 2 and tipos["intermediário"].quantidade == 3 and tipos["canto B"].quantidade == 2
    assert tipos["canto B"].comprimento_total > tipos["canto"].comprimento_total + 1.4        # a fila B 1,5 m mais alta
    # o cálice e a fundação de cada tipo, pela marca guardada nos dados
    assert {r.dados["tipo_pilar"] for r in p.calices} == set(tipos)
    assert {r.dados["tipo_pilar"] for r in p.fundacoes} == set(tipos)
    marcas = [l["marca"] for l in p.lista]
    assert {"P-C", "P-I", "P-CB", "P-IB", "P-O", "CL-CB"} <= set(marcas)
    # o 3D: cada fila no seu topo, o oitão na água, as vigas de travamento apoiadas em cada fila
    doc = M3.documento(p)
    pil = {(e.atributos["peca"], e.atributos["topo_mm"]) for e in doc.entidades.values() if (e.nome or "").startswith("Pilar")}
    assert ("P-C", 5100) in pil and ("P-CB", 6600) in pil and ("P-O", round(d.altura_oitao(3.195) * 1000)) in pil
    vig = [e for e in doc.entidades.values() if "travamento" in (e.nome or "").lower()]
    topos = {round(float(np.array(e.vertices)[:, 2].max())) for e in vig}
    assert topos == {5100, 6600}
    nomes = [n["nome"] for n in CB.niveis(p, None)]
    assert "Topo dos pilares — fila A" in nomes and "Topo dos pilares — fila B" in nomes and "Apoio das vigas — fila B" in nomes
    # as plantas
    des = LC.desenho(p)
    pecas = [e.atributos.get("peca") for e in des.entidades.values() if e.atributos.get("peca")]
    assert pecas.count("P-CB") >= 2 and pecas.count("P-IB") >= 2 and "CL-IB" in pecas
    assert D2.desenho(p).tamanho > 100
    # a conferência da cobertura pilar a pilar: cada pilar com o próprio topo
    pl = CB.pilares_em_planta(p)
    assert len(pl[0]) == 4 and {q[3] for q in pl if q[0].endswith("/B")} == {6600.0}


def test_conferir_cobertura_pilar_a_pilar():
    """com o topo de cada pilar, o desnível é apontado no pilar certo (e não contra um topo único)"""
    from premoldado import cobertura as CB
    info = {"apoios": [(0.0, 0.0, 5100.0), (0.0, 14671.0, 6600.0), (4000.0, 0.0, 5100.0), (4000.0, 14671.0, 6200.0)]}
    pil = [("1/A", 0.0, 0.0, 5100.0), ("1/B", 0.0, 14671.0, 6600.0), ("2/A", 4000.0, 0.0, 5100.0), ("2/B", 4000.0, 14671.0, 6600.0)]
    out = CB.conferir(info, pil, 5100.0, 14671.0)
    assert len(out) == 1 and "2/B" in out[0] and "0,40 m" in out[0] and "acima" in out[0]
    # sem o topo por pilar: o aviso antigo, contra o topo único
    out = CB.conferir(info, [q[:3] for q in pil], 5100.0, 14671.0)
    assert any("níveis" in t and "todos com o topo a 5,10 m" in t for t in out)


def test_dados_do_galpao_lidos_da_planta_de_lancamento():
    """R3: a planta lançada no CAD (menu Estrutura) vira os dados do galpão: filas, pórticos, alturas por fila (uma
    água), oitão, seções lançadas, vigas, consolo e fundação; o resto vem dos dados do projeto."""
    from nucleo2d.desenho import Desenho, Polilinha, Linha
    from premoldado import da_planta as DP
    des = Desenho(nome="t")
    xs = [1000, 5000, 11300, 15300, 20235]
    ys = [(2000, 5100), (16671, 6600)]
    for i, x in enumerate(xs):
        for j, (y, z) in enumerate(ys):
            des.add(Polilinha(camada="ESTRUTURA", vertices=[(x - 150, y - 200), (x + 150, y - 200), (x + 150, y + 200), (x - 150, y + 200)], fechada=True,
                              atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 30, "h": 40},
                                         "nivel_base": -1100, "nivel_topo": z if j else "Topo A", "marca": "P%d" % (2 * i + j + 1), "centro": [x, y]}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(850, 4995), (1150, 4995), (1150, 5395), (850, 5395)], fechada=True,
                      atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 40, "h": 30},
                                 "nivel_base": -1100, "nivel_topo": 5300, "rotacao": 90, "marca": "PO", "centro": [1000, 5195]}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(7850, 8000), (8150, 8000), (8150, 8400), (7850, 8400)], fechada=True,
                      atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 30, "h": 40},
                                 "nivel_base": -1100, "nivel_topo": 5100, "marca": "PX", "centro": [8000, 8200]}))
    des.add(Linha(camada="ESTRUTURA", a=(1000, 2000), b=(5000, 2000), atributos={"elemento": "viga", "material": "concreto",
                  "secao": {"tipo": "retangular", "b": 20, "h": 50}, "nivel_topo": 5100, "marca": "V1"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(1150, 1850), (1450, 1850), (1450, 2150), (1150, 2150)], fechada=True,
                      atributos={"elemento": "consolo", "altura": 400, "nivel_topo": 4500, "marca": "C1"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(0, 1000), (2000, 1000), (2000, 3000), (0, 3000)], fechada=True,
                      atributos={"elemento": "fundacao", "tipo": "bloco", "altura": 800, "nivel_topo": -1100, "marca": "B1"}))
    base = G.DadosGalpaoPM(nome="Sooro", v0=47.0, fck=40.0)
    d, avisos = DP.dados_da_planta(des, [{"nome": "Boca do cálice", "z": 0}, {"nome": "Topo A", "z": 5100}], base)
    assert d.nome == "Sooro" and d.v0 == 47.0 and d.fck == 40.0                          # o resto vem do projeto
    assert d.vao == 14.671 and d.vaos_longitudinais == [4.0, 6.3, 4.0, 4.935]
    assert d.altura_pilar == 5.1 and d.altura_pilar_b == 6.6 and d.cobertura == "uma água"
    assert d.pilares_oitao == [(1, 3.195)]
    assert d.secoes_pilar == [(30.0, 40.0)]                                              # o 40×30 girado 90° é o mesmo 30×40
    assert d.vigas_longitudinais == "travamento" and d.secoes_travamento == [(20.0, 50.0)]
    assert d.consolo_altura == 40.0 and d.consolo_a == 15.0 and d.fundacao == "estacas"
    assert avisos[0].startswith("10 pilares nas filas (5 pórticos), 1 de oitão")
    assert any("PX" in a and "fica de fora" in a for a in avisos)
    assert DP.deslocamento(des) == (1000.0, 2000.0)
    # o cálculo verifica o que foi lançado: o 30 × 40 serve na fila A (5,10 m) e não na B (6,60 m) — vira erro, não troca sozinho
    p = G.dimensionar(d)
    assert {q.tipo for q in p.pilares} == {"canto", "intermediário", "oitão"}
    assert len(p.erros) == 2 and all("B: nenhuma seção candidata passa" in e for e in p.erros)
    # poucos pilares: erro claro
    with pytest.raises(ErroDeDados):
        DP.dados_da_planta(Desenho(nome="v"), [], base)


# ------------------------------------------------------------------ R4: as plantas de saída e as pranchas

def test_plantas_de_saida_e_pranchas():
    """R4 (30/09): fôrmas da cobertura, cálices e fundações, corte transversal e longitudinais (um por fila quando as
    alturas diferem), montados no jogo de pranchas; as fundações que se sobrepõem viram apontamento."""
    from premoldado import plantas_saida as PS
    from nucleo2d.desenho import Desenho, Cota, Hachura
    from nucleo2d.pranchas import montar_pranchas
    d = G.DadosGalpaoPM(vao=14.671, vaos_longitudinais=[4.0, 6.3, 4.0, 4.935], altura_pilar=5.10, altura_pilar_b=6.60, cobertura="uma água",
                        v0=47.0, fundacao="sapata", pilares_oitao=[(1, 3.195)], vigas_longitudinais="travamento")
    p = G.dimensionar(d)
    ds = dict(PS.desenhos(p))
    assert list(ds) == ["formas-da-cobertura", "calices-e-fundacoes", "corte-transversal", "corte-longitudinal-fila-a", "corte-longitudinal-fila-b"]
    assert ds["corte-transversal"].escala == 50.0 and ds["formas-da-cobertura"].escala == 100.0
    # a fôrma: os pilares cortados com a marca, as vigas com a marca da lista, o topo das duas filas
    f = ds["formas-da-cobertura"]
    pecas = [e.atributos.get("peca") for e in f.entidades.values() if e.atributos.get("peca")]
    assert pecas.count("P-CB") >= 2 and any(m.startswith("VT-") for m in pecas) and "consolo" in pecas
    textos = " ".join(e.texto for e in f.por_tipo("texto"))
    assert "TOPO DOS PILARES +5,10" in textos and "TOPO DOS PILARES +6,60" in textos and "uma água" in textos
    # os cortes: o topo de cada fila e o fundo da fundação nos níveis; tudo cortado hachurado
    ct = ds["corte-transversal"]
    tt = " ".join(e.texto for e in ct.por_tipo("texto"))
    assert "+5,10 topo fila A" in tt and "+6,60 topo fila B" in tt and "fundo da fundação" in tt and "±0,00 boca do cálice" in tt
    assert len(ct.por_tipo("hachura")) >= 6 and ct.por_tipo("cota")
    zs = [v[1] for e in ct.por_tipo("polilinha") if (e.atributos or {}).get("peca", "").startswith("P-") for v in e.vertices]
    assert max(zs) == pytest.approx(6600.0)
    # o quadro das fundações
    qf = " ".join(e.texto for e in ds["calices-e-fundacoes"].por_tipo("texto"))
    assert "CL-CB" in qf and "sapata" in qf
    for des in ds.values():
        assert Desenho.de_dict(des.dict()).tamanho == des.tamanho
    folhas = montar_pranchas([{"nome": s, "desenho": x} for s, x in ds.items()], formato="A1", carimbo={"obra": "t"})
    assert 1 <= len(folhas) <= 3
    # a sobreposição das fundações: o oitão a 1 m da fila A cai em cima da sapata do canto
    p2 = G.dimensionar(G.DadosGalpaoPM(fundacao="sapata", pilares_oitao=[(1, 1.0)]))
    conf = PS.conflitos(p2)
    assert conf and "SP-C (1/A)" in conf[0] and "SP-O" in conf[0]
    assert not PS.conflitos(G.dimensionar(G.DadosGalpaoPM(fundacao="sapata")))


# ------------------------------------------------------------------ R5: a ida e volta 2D ↔ 3D

def test_volta_do_3d_para_a_planta():
    """R5 (30/09): o pilar movido e com outra seção no 3D volta para a planta (o rótulo junto), o topo segue o 3D, a peça
    lançada no 3D entra na planta com o id ligado, e a que sumiu do 3D vira apontamento."""
    from nucleo2d.desenho import Desenho, Polilinha, Linha, Texto
    from nucleo3d import de_planta_estrutura as D
    from nucleo3d.geometria import extrudar, mover
    des = Desenho(nome="t")
    p1 = des.add(Polilinha(camada="ESTRUTURA", vertices=[(-150, -200), (150, -200), (150, 200), (-150, 200)], fechada=True,
                           atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 30, "h": 40},
                                      "nivel_base": -1100, "nivel_topo": "Topo", "marca": "P1", "centro": [0, 0]}))
    rot = des.add(Texto(camada="ESTRUTURA", posicao=(300, 300), texto="P1", atributos={"rotulo_de": p1.id}))
    v1 = des.add(Linha(camada="ESTRUTURA", a=(0, 0), b=(4000, 0), atributos={"elemento": "viga", "material": "concreto",
                       "secao": {"tipo": "retangular", "b": 20, "h": 50}, "nivel_topo": 5100, "marca": "V1"}))
    doc, _ = D.modelo_da_planta(des, [{"nome": "Topo", "z": 5100}])
    # nada mudou: nada muda
    r = D.planta_do_modelo(des, doc, [{"nome": "Topo", "z": 5100}])
    assert r["alteracoes"] == [] and r["sem_peca"] == [] and r["novos"] == []
    # no 3D: o P1 vai 500 mm em X, vira 35 × 40 e sobe o topo para 5600; a viga some; um pilar novo pela ferramenta do 3D
    pil = next(e for e in doc.entidades.values() if e.nome == "Pilar P1")
    novo_p1 = extrudar([(-200, -175), (200, -175), (200, 175), (-200, 175)], (0.0, 0.0, 1.0), 6700.0, origem=(500.0, 0.0, -1100.0), nome="Pilar P1")
    pil.vertices = novo_p1.vertices
    pil.faces = novo_p1.faces
    viga = next(e for e in doc.entidades.values() if e.nome == "Viga V1")
    doc.remover(viga.id) if hasattr(doc, "remover") else doc.entidades.pop(viga.id)
    extra = extrudar([(-200, -150), (200, -150), (200, 150), (-200, 150)], (0.0, 0.0, 1.0), 6000.0, origem=(8000.0, 0.0, -900.0), nome="Pilar 30 × 40")
    extra.atributos = {"pre_moldado": True, "peca": "P", "tipo_ifc": "IfcColumn"}
    doc.add(extra)
    r = D.planta_do_modelo(des, doc, [{"nome": "Topo", "z": 5100}])
    a = des.entidades[p1.id].atributos
    assert a["centro"] == [500.0, 0.0] and a["secao"]["b"] == 35.0 and a["secao"]["h"] == 40.0 and a["nivel_topo"] == 5600
    xs = [v[0] for v in des.entidades[p1.id].vertices]
    assert (min(xs), max(xs)) == (325.0, 675.0)
    assert des.entidades[rot.id].posicao == (800.0, 300.0)                                       # o rótulo foi junto
    assert r["sem_peca"] == ["V1"] and v1.id in des.entidades                          # a viga fica, vira apontamento
    assert len(r["novos"]) == 1 and r["modelo_mudou"] == [extra.id]
    n = des.entidades[r["novos"][0]]
    assert n.atributos["elemento"] == "pilar" and n.atributos["marca"] == "P2" and n.atributos["centro"] == [8000.0, 0.0]
    assert n.atributos["secao"] == {"tipo": "retangular", "b": 30.0, "h": 40.0} and n.atributos["nivel_base"] == -900
    assert extra.atributos["origem_2d"] == n.id
    assert any("P1" in t and "movido 500 mm" in t and "seção 35 × 40 cm" in t and "topo Topo → 5600" in t for t in r["alteracoes"])


def test_galpao_da_planta_leva_o_id_do_elemento():
    """R5: os dados lidos da planta guardam o elemento de cada pilar pelo eixo; o 3D do galpão e as plantas de saída
    levam o id (origem_2d), o mesmo que a tela dividida usa para achar a peça dos dois lados."""
    from nucleo2d.desenho import Desenho, Polilinha
    from premoldado import da_planta as DP, modelo3d as M3, plantas_saida as PS, locacao as LC
    des = Desenho(nome="t")
    ids = {}
    for i, x in enumerate([0, 5000, 10000, 15000]):
        for j, y in enumerate([0, 10000]):
            e = des.add(Polilinha(camada="ESTRUTURA", vertices=[(x - 150, y - 200), (x + 150, y - 200), (x + 150, y + 200), (x - 150, y + 200)], fechada=True,
                                  atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 40, "h": 50},
                                             "nivel_base": -1100, "nivel_topo": 6000, "marca": "P%d" % (2 * i + j + 1), "centro": [x, y]}))
            ids["%d/%s" % (i + 1, "AB"[j])] = e.id
    d, _ = DP.dados_da_planta(des, [], G.DadosGalpaoPM(v0=40.0))
    assert {k: v["id"] for k, v in d.origem_planta.items()} == ids
    p = G.dimensionar(d)
    doc = M3.documento(p)
    pil = {e.atributos["eixo"]: e.atributos.get("origem_2d") for e in doc.entidades.values() if (e.nome or "").startswith("Pilar")}
    assert pil == ids
    loc = LC.desenho(p)
    assert {e.atributos.get("origem_2d") for e in loc.entidades.values() if e.atributos.get("origem_2d")} == set(ids.values())
    formas = dict(PS.desenhos(p))["formas-da-cobertura"]
    assert {e.atributos.get("origem_2d") for e in formas.entidades.values() if e.atributos.get("origem_2d")} == set(ids.values())


# ------------------------------------------------------------------ a barra da disciplina: tesoura, chapa, furo, parafuso

def test_tesoura_chapa_furo_parafuso_da_planta():
    """30/09 (a barra da direita do CAD): a tesoura de concreto vira a viga de cobertura em I (mais alta no meio nas
    duas águas; reta de um apoio ao outro na de uma água); a chapa vira Chapa com o furo que cai nela; o parafuso vira
    o cilindro com a cabeça no nível; a tesoura entra no galpão lido da planta como viga de cobertura."""
    from nucleo2d.desenho import Desenho, Polilinha, Linha, Circulo
    from nucleo3d import de_planta_estrutura as D
    from nucleo3d.modelo import Chapa
    des = Desenho(nome="t")
    t1 = des.add(Linha(camada="ESTRUTURA", a=(0, 0), b=(0, 14000), atributos={"elemento": "tesoura", "material": "concreto", "forma": "duas águas",
                 "secao": {"tipo": "I", "bf": 30, "hf": 10, "bw": 12, "h": 60, "h_meio": 120}, "nivel_base": 6000, "nivel_fim": 6000, "marca": "TC1"}))
    des.add(Linha(camada="ESTRUTURA", a=(5000, 0), b=(5000, 14000), atributos={"elemento": "tesoura", "material": "concreto", "forma": "uma água",
            "secao": {"tipo": "I", "bf": 30, "hf": 10, "bw": 12, "h": 60, "h_meio": 60}, "nivel_base": 5100, "nivel_fim": 6600, "marca": "TC2"}))
    ch = des.add(Polilinha(camada="ESTRUTURA", vertices=[(-200, -200), (200, -200), (200, 200), (-200, 200)], fechada=True,
                           atributos={"elemento": "chapa", "material": "aco", "espessura": 16, "aco": "ASTM A36", "nivel_topo": 0, "marca": "CH1"}))
    des.add(Circulo(camada="FURO", centro=(100, 100), raio=11, atributos={"elemento": "furo", "diametro": 22, "centro": [100, 100], "marca": "F1"}))
    des.add(Circulo(camada="FURO", centro=(900, 900), raio=11, atributos={"elemento": "furo", "diametro": 22, "centro": [900, 900], "marca": "F2"}))
    pf = des.add(Circulo(camada="PARAFUSO", centro=(-100, -100), raio=10, atributos={"elemento": "parafuso", "material": "aco", "diametro": 20,
                         "comprimento": 70, "nivel_topo": 30, "marca": "PF1", "centro": [-100, -100]}))
    doc, avisos = D.modelo_da_planta(des, [])
    assert any("F2" in a and "fora" in a for a in avisos)
    tc1 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Tesoura TC1")]
    assert len(tc1) == 4 and all(e.volume > 0 for e in tc1)                            # mesa de baixo, alma, duas mesas de cima
    zs = [v[2] for e in tc1 for v in e.vertices]
    assert min(zs) == pytest.approx(6000) and max(zs) == pytest.approx(7200)             # 1,20 m no meio
    tc2 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Tesoura TC2")]
    assert len(tc2) == 3
    vs = [v for e in tc2 for v in e.vertices]
    assert max(v[2] for v in vs if abs(v[1]) < 1) == pytest.approx(5700) and max(v[2] for v in vs if abs(v[1] - 14000) < 1) == pytest.approx(7200)
    chapa = next(e for e in doc.entidades.values() if isinstance(e, Chapa))
    assert chapa.espessura == 16 and chapa.origem[2] == pytest.approx(-8) and len(chapa.furos) == 1 and chapa.furos[0]["diametro"] == 22
    assert chapa.camada == "Chapas" and chapa.atributos["origem_2d"] == ch.id
    par = next(e for e in doc.entidades.values() if (e.nome or "").startswith("Parafuso PF1"))
    pz = [v[2] for v in par.vertices]
    assert (min(pz), max(pz)) == (pytest.approx(-40), pytest.approx(30)) and par.material == "Aço" and par.volume > 0
    # a volta: nada mudou; depois o parafuso e a tesoura andam no 3D
    assert D.planta_do_modelo(des, doc, [])["alteracoes"] == []
    for v_ in (par,):
        v_.vertices = [(x + 50, y, z) for x, y, z in v_.vertices]
    for e in tc1:
        e.vertices = [(x + 300, y, z) for x, y, z in e.vertices]
    r = D.planta_do_modelo(des, doc, [])
    assert des.entidades[pf.id].centro == (-50, -100) and des.entidades[t1.id].a == pytest.approx((300, 0))
    assert r["sem_peca"] == []                                                             # o furo não conta
    # o galpão lido da planta: a tesoura de A a B é a viga de cobertura
    from premoldado import da_planta as DP
    g = Desenho(nome="g")
    for i, x in enumerate([0, 5000, 10000, 15000]):
        for j, y in enumerate([0, 14000]):
            g.add(Polilinha(camada="ESTRUTURA", vertices=[(x - 150, y - 200), (x + 150, y - 200), (x + 150, y + 200), (x - 150, y + 200)], fechada=True,
                            atributos={"elemento": "pilar", "material": "concreto", "secao": {"tipo": "retangular", "b": 40, "h": 50},
                                       "nivel_base": -1100, "nivel_topo": 6000, "marca": "P%d" % (2 * i + j + 1), "centro": [x, y]}))
        g.add(Linha(camada="ESTRUTURA", a=(x, 0), b=(x, 14000), atributos={"elemento": "tesoura", "material": "concreto", "forma": "duas águas",
              "secao": {"tipo": "I", "bf": 30, "hf": 10, "bw": 12, "h": 60, "h_meio": 120}, "nivel_base": 6000, "nivel_fim": 6000, "marca": "TC%d" % (i + 1)}))
    d, _ = DP.dados_da_planta(g, [], G.DadosGalpaoPM(v0=40.0))
    assert d.viga_cobertura and d.secoes_viga_cobertura == [(30.0, 10.0, 12.0, 60.0)]


def test_armaduras_dos_pilares_no_3d():
    """30/09 (Ver → Armaduras): cada pilar calculado leva as barras longitudinais (N1) e os estribos (N2) numa camada própria,
    desligada ao abrir, dentro do cobrimento, do pé ao topo."""
    from premoldado import modelo3d as M3
    from premoldado.concreto import cobrimento
    d = G.DadosGalpaoPM(fundacao="sapata")
    p = G.dimensionar(d)
    doc = M3.documento(p)
    assert doc.camadas["Armaduras"].visivel is False and "Armadura" in doc.materiais
    arm = [e for e in doc.entidades.values() if e.camada == "Armaduras"]
    pil = next(q for q in p.pilares if q.tipo == "canto")
    esp = [e for e in arm if e.atributos["eixo"] == "1/A" and e.atributos["peca"].startswith("P-")]
    n1 = [e for e in esp if e.atributos["posicao"] == "N1"]
    n2 = [e for e in esp if e.atributos["posicao"] == "N2"]
    assert len(n1) == pil.armadura.n_total and len(n2) >= 10 and all(e.material == "Armadura" and e.volume > 0 for e in esp)
    c = cobrimento(d.caa, "pilar", pre_fabricado=True) * 10
    V = np.array([v for e in esp for v in e.vertices])
    assert V[:, 0].min() == pytest.approx(-pil.b * 5 + c) and V[:, 1].max() == pytest.approx(pil.h * 5 - c)
    assert V[:, 2].max() <= d.altura_pilar * 1000 - c + 1e-6


def test_armaduras_dos_calices_e_das_fundacoes_no_3d():
    """30/09: o cálice leva os laços horizontais (principais no topo, secundários na altura) e as verticais nos cantos, no
    eixo das paredes; a sapata, a malha das duas direções no fundo; o bloco, os tirantes sobre as estacas — tudo dentro da peça."""
    from premoldado import modelo3d as M3
    for fund, pref in (("sapata", "SP"), ("estacas", "BL")):
        p = G.dimensionar(G.DadosGalpaoPM(fundacao=fund))
        doc = M3.documento(p)
        arm = [e for e in doc.entidades.values() if e.camada == "Armaduras" and e.atributos.get("eixo") == "1/A"]
        for pr in ("CL", pref):
            barras = [e for e in arm if e.atributos["peca"] == "%s-C" % pr]
            pecas = [e for e in doc.entidades.values() if e.camada != "Armaduras" and e.atributos.get("peca") == "%s-C" % pr and e.atributos.get("eixo") == "1/A"]
            assert barras and pecas and all(e.volume > 0 for e in barras)
            P = np.array([v for e in pecas for v in e.vertices])
            B = np.array([v for e in barras for v in e.vertices])
            assert (B.min(0) > P.min(0) - 1e-6).all() and (B.max(0) < P.max(0) + 1e-6).all()
        cal = {e.atributos["posicao"] for e in arm if e.atributos["peca"] == "CL-C"}
        assert cal == {"horizontal principal", "horizontal secundária", "vertical"}
        f = {e.atributos["posicao"] for e in arm if e.atributos["peca"] == "%s-C" % pref}
        assert f == ({"malha do vão", "malha do comprimento"} if fund == "sapata" else {"tirante do vão", "tirante do comprimento"})


def test_placa_de_fechamento_laje_e_escada_da_planta():
    """30/09: a placa de fechamento vira os painéis (em pé na largura do módulo, o último fechando o comprimento; ou deitados,
    empilhados); a laje alveolar, as placas no sentido pedido e a capa; a maciça, uma peça; a escada, os degraus iguais pelo
    desnível; e a volta do 3D move a escada."""
    from nucleo2d.desenho import Desenho, Polilinha, Linha
    from nucleo3d import de_planta_estrutura as D
    des = Desenho(nome="t")
    des.add(Linha(camada="ESTRUTURA", a=(0, 0), b=(6000, 0), atributos={"elemento": "painel", "material": "concreto", "tipo": "alveolar",
            "orientacao": "vertical", "espessura": 150, "modulo": 1250, "nivel_base": 0, "nivel_topo": 5000, "marca": "PN1"}))
    des.add(Linha(camada="ESTRUTURA", a=(0, 10000), b=(6000, 10000), atributos={"elemento": "painel", "material": "concreto", "tipo": "maciço",
            "orientacao": "horizontal", "espessura": 120, "modulo": 2000, "nivel_base": 0, "nivel_topo": 5000, "marca": "PN2"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(0, 0), (6000, 0), (6000, 4000), (0, 4000)], fechada=True,
                      atributos={"elemento": "laje", "material": "concreto", "tipo": "alveolar", "espessura": 200, "capa": 50, "sentido": "x",
                                 "modulo": 1250, "nivel_topo": 3000, "marca": "L1"}))
    des.add(Polilinha(camada="ESTRUTURA", vertices=[(0, 5000), (3000, 5000), (3000, 8000), (0, 8000)], fechada=True,
                      atributos={"elemento": "laje", "material": "concreto", "tipo": "maciça", "espessura": 120, "capa": 0,
                                 "nivel_topo": 3000, "marca": "L2"}))
    esc = des.add(Linha(camada="ESTRUTURA", a=(8000, 0), b=(8000, 4800), atributos={"elemento": "escada", "material": "concreto", "largura": 1200,
                        "espelho_max": 180, "espessura": 120, "nivel_base": 0, "nivel_topo": 3000, "marca": "E1"}))
    doc, avisos = D.modelo_da_planta(des, [])
    pn1 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Fechamento PN1")]
    assert len(pn1) == 5 and all(e.volume > 0 for e in pn1)                  # 4 × 1,25 m + 1 de 1,0 m
    xs = sorted({round(max(v[0] for v in e.vertices)) for e in pn1})
    assert xs[-1] == 6000
    pn2 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Fechamento PN2")]
    assert len(pn2) == 3                                                    # 2 + 2 + 1 m deitados
    l1 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Laje L1")]
    assert len(l1) == 5 and any("capa" in e.nome for e in l1)              # 4 placas (4 m / 1,25) + a capa
    zs = [v[2] for e in l1 for v in e.vertices]
    assert max(zs) == pytest.approx(3000) and min(zs) == pytest.approx(2750)
    l2 = [e for e in doc.entidades.values() if (e.nome or "").startswith("Laje L2")]
    assert len(l2) == 1 and l2[0].volume == pytest.approx(3000 * 3000 * 120, rel=1e-6)
    deg = [e for e in doc.entidades.values() if (e.nome or "").startswith("Escada E1")]
    assert len(deg) == 17 and all(e.volume > 0 for e in deg)               # 3000 / 180 → 17 degraus de 176,5
    assert deg[0].atributos["degraus"]["n"] == 17 and deg[0].atributos["degraus"]["piso"] == pytest.approx(4800 / 17, abs=0.1)
    assert max(v[2] for e in deg for v in e.vertices) == pytest.approx(3000)
    assert D.planta_do_modelo(des, doc, [])["alteracoes"] == []
    for e in deg:
        e.vertices = [(x + 500, y, z) for x, y, z in e.vertices]
    r = D.planta_do_modelo(des, doc, [])
    assert des.entidades[esc.id].a == pytest.approx((8500, 0)) and any("E1" in t for t in r["alteracoes"])
