# -*- coding: utf-8 -*-
"""Testes do módulo de análise estrutural (`nucleo/analise.py`).

Cada teste confronta o solver de rigidez com uma solução fechada da Resistência dos
Materiais ou com um exemplo resolvido do manual:

    Capítulo 4  — fórmulas de viga e Exemplo 4.4 (treliça de três barras);
    Capítulo 16 — Tabela 16.4 (pórtico do galpão de 20 m, resolvido por software).

Tolerância padrão de 0,5 % contra fórmula fechada e de 2 % contra o Capítulo 16
(lá o modelo tem mísula e a comparação é com outro solver).

Rodar com:  PYTHONIOENCODING=utf-8 python -m pytest testes/test_analise.py -q
        ou  PYTHONIOENCODING=utf-8 python testes/test_analise.py
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import E, ErroDeDados                                   # noqa: E402
from nucleo.analise import (Modelo, amplificar, Andar, DadosSegundaOrdem,  # noqa: E402
                            coeficiente_Cm, conferir_por_formula, envoltoria,
                            Misula, portico_galpao, resolver, trelica,
                            viga_continua)

# Perfil de referência dos testes de viga: I soldado do Exemplo 4.1 do manual
A_REF = 46.8        # cm²
I_REF = 7407.6      # cm⁴


def perto(obtido, esperado, tol_pct=0.5, o_que=""):
    """Confere `obtido` contra `esperado` dentro de `tol_pct` por cento."""
    if esperado == 0:
        assert abs(obtido) < 1e-6, f"{o_que}: esperado 0, obtido {obtido}"
        return
    dif = abs(obtido - esperado) / abs(esperado) * 100.0
    assert dif <= tol_pct, (f"{o_que}: obtido {obtido:.6g}, esperado {esperado:.6g} "
                            f"(diferença {dif:.3f} % > {tol_pct} %)")


def viga(L, apoio_esq, apoio_dir, n=4, A=A_REF, I=I_REF):
    """Viga reta dividida em n elementos, para ler a flecha no meio do vão."""
    m = Modelo("viga")
    for k in range(n + 1):
        ap = apoio_esq if k == 0 else (apoio_dir if k == n else None)
        m.add_no(L * k / n, 0.0, ap, f"n{k}")
        if k:
            m.add_barra(f"n{k - 1}", f"n{k}", A, I, rotulo=f"t{k}")
    return m


def carregar(m, caso, q):
    """Carga uniforme vertical de cima para baixo (q > 0) em todas as barras."""
    m.caso(caso)
    for k in range(len(m.barras)):
        m.distribuida(caso, k, -abs(q), "global_y")
    return m


# =====================================================================================
# Vigas isoladas — fórmulas fechadas do Capítulo 4
# =====================================================================================

def test_biapoiada_uniforme():
    """Biapoiada com carga distribuída: M = qL²/8, V = qL/2, δ = 5qL⁴/384EI."""
    L, q = 600.0, 0.10
    m = carregar(viga(L, "rotulado", "movel"), "q", q)
    r = resolver(m, "q", 41)
    formula = conferir_por_formula("biapoiada_uniforme", q=q, L=L, E=E, I=I_REF)

    M_max = max(b.diagrama.M_max.valor for b in r.barras)
    perto(M_max, q * L ** 2 / 8, 0.5, "M = qL²/8")
    perto(M_max, formula["M"], 0.5, "M contra fórmula fechada")
    perto(r.barra("t1").V_i, q * L / 2, 0.5, "V = qL/2")
    perto(r.reacao("n0")[1], q * L / 2, 0.5, "reação")
    flecha = -r.deslocamento(len(m.nos) // 2)[1]
    perto(flecha, 5 * q * L ** 4 / (384 * E * I_REF), 0.5, "flecha 5qL⁴/384EI")
    perto(flecha, formula["flecha"], 0.5, "flecha contra fórmula fechada")
    # o exemplo 4.2 do manual dá 1,14 cm para esta viga
    perto(flecha, 1.14, 1.0, "flecha do Exemplo 4.2 do manual")


def test_biapoiada_carga_concentrada():
    """Biapoiada com carga no meio do vão: M = PL/4, δ = PL³/48EI."""
    L, P = 600.0, 60.0
    m = viga(L, "rotulado", "movel", n=2)
    m.caso("P")
    m.concentrada("P", "t1", -P, L / 2, "global_y")
    r = resolver(m, "P", 41)
    formula = conferir_por_formula("biapoiada_concentrada", P=P, L=L, E=E, I=I_REF)
    M_max = max(b.diagrama.M_max.valor for b in r.barras)
    perto(M_max, P * L / 4, 0.5, "M = PL/4")
    perto(M_max, formula["M"], 0.5, "M contra fórmula")
    perto(-r.deslocamento("n1")[1], P * L ** 3 / (48 * E * I_REF), 0.5, "δ = PL³/48EI")


def test_biengastada_uniforme():
    """Biengastada: M_apoio = qL²/12, M_vão = qL²/24, δ = qL⁴/384EI."""
    L, q = 600.0, 0.10
    m = carregar(viga(L, "engastado", "engastado"), "q", q)
    r = resolver(m, "q", 41)
    formula = conferir_por_formula("biengastada_uniforme", q=q, L=L, E=E, I=I_REF)

    M_apoio = -r.barra("t1").M_i
    perto(M_apoio, q * L ** 2 / 12, 0.5, "M_apoio = qL²/12")
    perto(M_apoio, formula["M_apoio"], 0.5, "M_apoio contra fórmula")
    M_vao = max(b.diagrama.M_max.valor for b in r.barras)
    perto(M_vao, q * L ** 2 / 24, 0.5, "M_vão = qL²/24")
    perto(M_vao, formula["M_vao"], 0.5, "M_vão contra fórmula")
    flecha = -r.deslocamento(len(m.nos) // 2)[1]
    perto(flecha, q * L ** 4 / (384 * E * I_REF), 0.5, "δ = qL⁴/384EI")
    # momento do engaste é o dobro do de vão e os apoios levam qL/2 cada
    perto(r.reacao("n0")[1], q * L / 2, 0.5, "reação do engaste")


def test_balanco_uniforme():
    """Balanço: M = qL²/2 no engaste, δ = qL⁴/8EI na ponta."""
    L, q = 300.0, 0.10
    m = carregar(viga(L, "engastado", None), "q", q)
    r = resolver(m, "q", 41)
    formula = conferir_por_formula("balanco_uniforme", q=q, L=L, E=E, I=I_REF)
    M_eng = -r.barra("t1").M_i
    perto(M_eng, q * L ** 2 / 2, 0.5, "M = qL²/2")
    perto(M_eng, formula["M"], 0.5, "M contra fórmula")
    perto(r.barra("t1").V_i, q * L, 0.5, "V = qL")
    flecha = -r.deslocamento(len(m.nos) - 1)[1]
    perto(flecha, q * L ** 4 / (8 * E * I_REF), 0.5, "δ = qL⁴/8EI")
    perto(flecha, formula["flecha"], 0.5, "flecha contra fórmula")


def test_viga_continua_dois_vaos():
    """Dois vãos iguais: M sobre o apoio central = qL²/8 e R_central = 1,25 qL."""
    L, q = 500.0, 0.12
    m = viga_continua([L, L], A=A_REF, I=I_REF)
    carregar(m, "q", q)
    r = resolver(m, "q", 81)
    formula = conferir_por_formula("continua_dois_vaos_uniforme", q=q, L=L, E=E, I=I_REF)

    M_apoio = -r.barra("vao1").M_f
    perto(M_apoio, q * L ** 2 / 8, 0.5, "M_apoio = qL²/8")
    perto(M_apoio, formula["M_apoio"], 0.5, "M_apoio contra fórmula")
    perto(r.reacao("apoio2")[1], 1.25 * q * L, 0.5, "R_central = 1,25 qL")
    perto(r.reacao("apoio1")[1], 0.375 * q * L, 0.5, "R_extremo = 0,375 qL")
    M_vao = r.barra("vao1").diagrama.M_max
    perto(M_vao.valor, 9 * q * L ** 2 / 128, 0.5, "M_vão = 9qL²/128")
    perto(M_vao.x, 0.375 * L, 1.0, "posição do M_vão")
    # continuidade: o momento sobre o apoio é o mesmo visto pelos dois vãos
    perto(-r.barra("vao2").M_i, M_apoio, 0.01, "continuidade do momento")


def test_engastada_apoiada():
    """Engastada-apoiada: M_engaste = qL²/8 e reações 5qL/8 e 3qL/8."""
    L, q = 500.0, 0.12
    m = carregar(viga(L, "engastado", "movel", n=8), "q", q)
    r = resolver(m, "q", 41)
    formula = conferir_por_formula("engastada_apoiada_uniforme", q=q, L=L, E=E, I=I_REF)
    perto(-r.barra("t1").M_i, q * L ** 2 / 8, 0.5, "M_engaste = qL²/8")
    perto(r.reacao("n0")[1], 5 * q * L / 8, 0.5, "R_engaste = 5qL/8")
    perto(r.reacao("n8")[1], 3 * q * L / 8, 0.5, "R_apoio = 3qL/8")
    M_vao = max(b.diagrama.M_max.valor for b in r.barras)
    perto(M_vao, formula["M_vao"], 1.0, "M_vão = 9qL²/128")


# =====================================================================================
# Treliça — Exemplo 4.4 do manual (método dos nós)
# =====================================================================================

def test_trelica_tres_barras_exemplo_4_4():
    """Manual, Exemplo 4.4: vão 4,0 m, altura 1,5 m, P = 30 kN na cumeeira.

    Resultado do método dos nós: barras inclinadas com 25 kN de compressão e
    tirante com 20 kN de tração; reações de 15 kN em cada apoio.
    """
    m = trelica(coordenadas=[(0.0, 0.0), (400.0, 0.0), (200.0, 150.0)],
                barras=[(0, 2, None, "AC"), (1, 2, None, "BC"), (0, 1, None, "AB")],
                apoios={0: "rotulado", 1: "movel"},
                A=10.0, nomes=["A", "B", "C"])
    m.caso("P")
    m.nodal("P", "C", Fy=-30.0)
    r = resolver(m, "P")

    perto(r.reacao("A")[1], 15.0, 0.1, "R_A")
    perto(r.reacao("B")[1], 15.0, 0.1, "R_B")
    assert abs(r.reacao("A")[0]) < 1e-9, "H_A deve ser nulo"

    perto(r.barra("AC").N_i, -25.0, 0.1, "F_AC (compressão)")
    perto(r.barra("BC").N_i, -25.0, 0.1, "F_BC (compressão)")
    perto(r.barra("AB").N_i, +20.0, 0.1, "F_AB (tração)")
    assert r.barra("AC").N_i < 0 and r.barra("AB").N_i > 0

    # barra de treliça só tem esforço normal: momento nulo em todo o comprimento
    for b in r.barras:
        assert max(abs(v) for v in b.diagrama.M) < 1e-6, f"{b.rotulo} com momento"
        assert abs(b.N_i - b.N_f) < 1e-6, f"{b.rotulo} com N variável"
    for res in r.equilibrio():
        assert abs(res) < 1e-8


# =====================================================================================
# Pórtico do Capítulo 16 — comparação com outro solver (tolerância 2 %)
# =====================================================================================

def portico_cap16(misula=None):
    """Pórtico da Tabela 16.4: 20 m × 6 m, 10 %, base rotulada.

    Pilar W 360×44,6 (I = 12 258 cm⁴), viga W 360×32,9 (I = 8 358 cm⁴).
    Cargas por pórtico da Tabela 16.3 (faixa de 5,0 m), em kN/cm.
    """
    m = portico_galpao(vao=2000.0, pe_direito=600.0, inclinacao=0.10,
                       base_rotulada=True, misula=misula,
                       A_pilar=57.7, I_pilar=12258.0,
                       A_viga=42.1, I_viga=8358.0, nome="pórtico do Capítulo 16")
    vigas = m.dados["barras_viga"]
    esq = [b for b in vigas if b.endswith("esq")]
    dir_ = [b for b in vigas if b.endswith("dir")]

    # C1 — gravidade: 1,4 G + 1,5 Q = 3,39 kN/m de projeção horizontal
    m.caso("C1")
    for b in vigas:
        m.distribuida("C1", b, -0.0339, "projetada_y")

    # C2 — sucção (Cpi = +0,2): 1,0 G + 1,4 V
    m.caso("C2")
    for b in vigas:
        m.distribuida("C2", b, -0.0108, "projetada_y")
    for b in esq:
        m.distribuida("C2", b, +0.0757, "perpendicular")      # sucção normal ao telhado
    for b in dir_:
        m.distribuida("C2", b, +0.0395, "perpendicular")
    m.distribuida("C2", "pilar_esq", +0.0329, "global_x")
    m.distribuida("C2", "pilar_dir", +0.0461, "global_x")

    # C3 — vento + gravidade (Cpi = −0,3): 1,4 G + 1,4 V + 1,05 Q
    m.caso("C3")
    for b in vigas:
        m.distribuida("C3", b, -0.0282, "projetada_y")
    for b in esq:
        m.distribuida("C3", b, +0.0428, "perpendicular")
    for b in dir_:
        m.distribuida("C3", b, +0.0066, "perpendicular")
    m.distribuida("C3", "pilar_esq", +0.0658, "global_x")
    m.distribuida("C3", "pilar_dir", +0.0132, "global_x")

    # S2 — serviço, vento nominal (deslocamento horizontal)
    m.caso("S2")
    for b in vigas:
        m.distribuida("S2", b, -0.0108, "projetada_y")
    for b in esq:
        m.distribuida("S2", b, +0.0305, "perpendicular")
    for b in dir_:
        m.distribuida("S2", b, +0.0047, "perpendicular")
    m.distribuida("S2", "pilar_esq", +0.0470, "global_x")
    m.distribuida("S2", "pilar_dir", +0.0094, "global_x")
    return m


def test_portico_cap16_gravidade():
    """Tabela 16.4, C1: M_joelho = −95,0 kN·m e M_cumeeira = +58,5 kN·m."""
    m = portico_cap16()
    r = resolver(m, "C1", 51)
    perto(r.barra("pilar_esq").M_f / 100.0, -95.0, 2.0, "C1 M de joelho")
    perto(r.barra("pilar_dir").M_i / 100.0, -95.0, 2.0, "C1 M de joelho (direito)")
    perto(r.barra("viga_esq").M_f / 100.0, +58.5, 2.0, "C1 M de cumeeira")
    perto(r.reacao("A")[0], +15.8, 2.0, "C1 reação horizontal")
    perto(r.reacao("A")[1], +33.9, 2.0, "C1 reação vertical")
    perto(-r.deslocamento("C")[1], 10.7, 2.0, "C1 flecha da cumeeira")
    # conferência à mão do manual: M_joelho ≈ 0,5 a 0,6 M0
    checagem = conferir_por_formula("portico_duas_aguas_biarticulado", q=0.0339, L=2000.0)
    lim = checagem.faixa["M_joelho"]
    assert lim[0] <= abs(r.barra("pilar_esq").M_f) <= lim[1], "fora da faixa 0,50–0,60 M0"


def test_portico_cap16_succao():
    """Tabela 16.4, C2: M_joelho = +190,1 kN·m e M_cumeeira = −77,6 kN·m."""
    m = portico_cap16()
    r = resolver(m, "C2", 51)
    perto(r.barra("pilar_esq").M_f / 100.0, +190.1, 2.0, "C2 M de joelho a barlavento")
    perto(r.barra("viga_esq").M_f / 100.0, -77.6, 2.0, "C2 M de cumeeira")
    perto(r.barra("pilar_dir").M_i / 100.0, +69.7, 2.0, "C2 M de joelho a sotavento")
    perto(r.reacao("A")[0], -41.5, 2.0, "C2 reação horizontal")
    perto(r.reacao("A")[1], -61.8, 2.0, "C2 arrancamento na base")
    perto(r.reacao("E")[1], -31.8, 2.0, "C2 arrancamento na base direita")
    perto(r.deslocamento("B")[0], +9.7, 2.0, "C2 deslocamento do topo")
    # sob sucção o momento de joelho dobra e inverte de sinal (manual, "Vento manda")
    r1 = resolver(m, "C1", 51)
    assert r.barra("pilar_esq").M_f * r1.barra("pilar_esq").M_f < 0


def test_portico_cap16_demais_combinacoes():
    """Tabela 16.4: C3 e S2 (deslocamento de serviço)."""
    m = portico_cap16()
    r3 = resolver(m, "C3", 51)
    perto(r3.barra("pilar_esq").M_f / 100.0, +52.0, 3.0, "C3 M de joelho")
    perto(r3.barra("pilar_dir").M_i / 100.0, -68.4, 3.0, "C3 M de joelho direito")
    perto(r3.reacao("A")[0], -28.4, 3.0, "C3 reação horizontal")

    rs = resolver(m, "S2", 51)
    perto(rs.deslocamento("B")[0], 6.21, 2.0, "S2 deslocamento horizontal (H/97)")
    # limite do manual: 0,3 × 6,2 = 1,9 cm ≤ H/300 = 2,0 cm
    assert 0.3 * rs.deslocamento("B")[0] <= 600.0 / 300.0


def test_portico_cap16_com_misula():
    """A mísula reduz o deslocamento em cerca de 10 % (manual, Passos 5-h e 6-e).

    A mísula de 1,80 m é representada pela inércia efetiva de 1,5·I_viga que o
    próprio manual adota no Passo 6-a (a seção da raiz, I = 38 290 cm⁴, valeria
    4,6·I_viga e, aplicada ao trecho inteiro, superestimaria o enrijecimento).
    """
    sem = resolver(portico_cap16(), "S2", 31)
    com = resolver(portico_cap16(misula=Misula(180.0, fator=1.5)), "S2", 31)
    u_sem = sem.deslocamento("B")[0]
    u_com = com.deslocamento("B")[0]
    reducao = (u_sem - u_com) / u_sem * 100.0
    assert 5.0 <= reducao <= 15.0, f"redução de {reducao:.1f} % fora do esperado (~10 %)"

    # "simplificação a favor da segurança para o momento de cumeeira e ligeiramente
    #  contra para o momento de joelho, diferença < 5 %" (manual, Passo 4)
    g_sem = resolver(portico_cap16(), "C1", 31)
    g_com = resolver(portico_cap16(misula=Misula(180.0, fator=1.5)), "C1", 31)
    joelho = abs(g_com.barra("pilar_esq").M_f / g_sem.barra("pilar_esq").M_f - 1) * 100
    assert joelho < 5.0, f"momento de joelho variou {joelho:.1f} % com a mísula"
    assert abs(g_com.barra("viga_esq").M_f) < abs(g_sem.barra("viga_esq").M_f)


def test_envoltoria_cap16():
    """A envoltória guarda o extremo de cada esforço e o caso que o governa."""
    m = portico_cap16()
    env = envoltoria(m, ["C1", "C2", "C3"], n_pontos=41)
    pilar = env.barra("pilar_esq")
    perto(pilar.M_max.valor / 100.0, 190.1, 2.0, "envoltória M+ do pilar")
    assert pilar.M_max.caso == "C2", "o momento máximo do pilar tem de vir da sucção"
    perto(pilar.M_min.valor / 100.0, -95.0, 2.0, "envoltória M− do pilar")
    assert pilar.M_min.caso == "C1"
    assert env.barra("pilar_esq").absoluto("M").caso == "C2"
    # arrancamento da base — o que vai para o projetista de fundações
    perto(env.reacao("A")["Ry_min"].valor, -61.8, 2.0, "arrancamento da base")
    assert env.reacao("A")["Ry_min"].caso == "C2"
    assert set(env.casos) == {"C1", "C2", "C3"}


# =====================================================================================
# Rótulas e condensação estática
# =====================================================================================

def test_rotula_na_base_da_momento_nulo():
    """Pórtico com base rotulada: momento nulo na base, pelos dois caminhos."""
    r = resolver(portico_cap16(), "C2", 31)
    for no in ("A", "E"):
        assert abs(r.reacao(no)[2]) < 1e-6, f"momento na base {no} deveria ser nulo"
    for barra, x in (("pilar_esq", 0.0), ("pilar_dir", None)):
        rb = r.barra(barra)
        pos = rb.L if x is None else x
        assert abs(rb.esforcos(pos, lado=-1 if x is None else 1)[2]) < 1e-6

    # mesmo pórtico com apoio engastado e rótula na extremidade da barra:
    # a condensação estática tem de dar exatamente o mesmo resultado
    m2 = portico_cap16()
    for no in ("A", "E"):
        m2.nos[m2.indice_no(no)].apoio = (True, True, True)
    m2.barras[m2.indice_barra("pilar_esq")].rotula_i = True
    m2.barras[m2.indice_barra("pilar_dir")].rotula_f = True
    r2 = resolver(m2, "C2", 31)
    for no in ("A", "E"):
        assert abs(r2.reacao(no)[2]) < 1e-6, "rótula na barra não zerou o momento"
        for j in range(2):
            perto(r2.reacao(no)[j], r.reacao(no)[j], 0.01,
                  f"reação {no}[{j}] com rótula na barra")
    perto(r2.barra("pilar_esq").M_f, r.barra("pilar_esq").M_f, 0.01, "M de joelho")


def test_rotula_reproduz_viga_biapoiada():
    """Viga engastada nas duas pontas, mas com rótulas nas barras: vira biapoiada."""
    L, q = 600.0, 0.10
    m = viga(L, "engastado", "engastado", n=2)
    m.barras[0].rotula_i = True
    m.barras[1].rotula_f = True
    carregar(m, "q", q)
    r = resolver(m, "q", 41)
    assert abs(r.reacao("n0")[2]) < 1e-6, "a rótula não zerou o momento de engaste"
    M_max = max(b.diagrama.M_max.valor for b in r.barras)
    perto(M_max, q * L ** 2 / 8, 0.5, "M = qL²/8 com rótulas nas extremidades")
    perto(-r.deslocamento("n1")[1], 5 * q * L ** 4 / (384 * E * I_REF), 0.5, "flecha")


def test_portico_tres_rotulas():
    """Rótula na cumeeira: momento nulo lá, e maior no joelho que no pórtico rígido."""
    rig = portico_galpao(2000.0, 600.0, 0.10, A_pilar=57.7, I_pilar=12258.0,
                         A_viga=42.1, I_viga=8358.0)
    tri = portico_galpao(2000.0, 600.0, 0.10, A_pilar=57.7, I_pilar=12258.0,
                         A_viga=42.1, I_viga=8358.0, rotula_cumeeira=True)
    for m in (rig, tri):
        m.caso("g")
        for b in m.dados["barras_viga"]:
            m.distribuida("g", b, -0.0339, "projetada_y")
    r_rig = resolver(rig, "g", 31)
    r_tri = resolver(tri, "g", 31)
    assert abs(r_tri.barra("viga_esq").M_f) < 1e-6, "a cumeeira rotulada tem M = 0"
    assert abs(r_tri.barra("pilar_esq").M_f) > abs(r_rig.barra("pilar_esq").M_f)
    for res in r_tri.equilibrio():
        assert abs(res) < 1e-6


# =====================================================================================
# Conferência por fórmula fechada e pórtico retangular biarticulado
# =====================================================================================

def test_portico_biarticulado_contra_formula():
    """Pórtico retangular biarticulado: H = qL²/[4h(2k+3)] (fórmula fechada)."""
    L, h, q = 800.0, 400.0, 0.15
    Iv, Ip, Av, Ap = 8358.0, 12258.0, 42.1, 57.7
    m = Modelo("portal")
    m.add_no(0.0, 0.0, "rotulado", "A")
    m.add_no(0.0, h, None, "B")
    m.add_no(L, h, None, "C")
    m.add_no(L, 0.0, "rotulado", "D")
    m.add_barra("A", "B", Ap, Ip, rotulo="pilar_esq")
    m.add_barra("B", "C", Av, Iv, rotulo="viga")
    m.add_barra("D", "C", Ap, Ip, rotulo="pilar_dir")
    m.caso("q")
    m.distribuida("q", "viga", -q, "global_y")
    r = resolver(m, "q", 41)
    f = conferir_por_formula("portico_biarticulado", q=q, L=L, h=h,
                             I_viga=Iv, I_pilar=Ip)
    # a fórmula despreza a deformação axial das barras: 1 % de tolerância
    perto(abs(r.reacao("A")[0]), f["H"], 1.0, "empuxo horizontal H")
    perto(abs(r.barra("viga").M_i), f["M_joelho"], 1.0, "momento de canto")
    perto(r.barra("viga").diagrama.M_max.valor, f["M_vao"], 1.0, "momento de vão")
    perto(r.reacao("A")[1], q * L / 2, 0.5, "reação vertical")


def test_conferir_por_formula_catalogo():
    """As fórmulas fechadas do módulo batem com as regras de bolso do Capítulo 4."""
    q, L, P = 0.10, 600.0, 60.0
    bi = conferir_por_formula("biapoiada_uniforme", q=q, L=L, I=I_REF)
    bal = conferir_por_formula("balanco_uniforme", q=q, L=L, I=I_REF)
    eng = conferir_por_formula("biengastada_uniforme", q=q, L=L, I=I_REF)
    # "Balanço: momento qL²/2 — quatro vezes o de uma biapoiada de mesmo vão"
    perto(bal["M"] / bi["M"], 4.0, 0.1, "M_balanço / M_biapoiada")
    # "flecha qL⁴/8EI — 9,6 vezes a da biapoiada e 48 vezes a da biengastada"
    perto(bal["flecha"] / bi["flecha"], 9.6, 0.1, "δ_balanço / δ_biapoiada")
    perto(bal["flecha"] / eng["flecha"], 48.0, 0.1, "δ_balanço / δ_biengastada")
    # "a carga concentrada equivalente no meio dá o dobro"
    pc = conferir_por_formula("biapoiada_concentrada", P=q * L, L=L, I=I_REF)
    perto(pc["M"] / bi["M"], 2.0, 0.1, "M_concentrada / M_distribuída")
    # memória de cálculo presente em todos os casos
    for caso in ("biapoiada_uniforme", "biengastada_uniforme", "balanco_uniforme",
                 "continua_dois_vaos_uniforme", "portico_biarticulado"):
        c = conferir_por_formula(caso, q=q, L=L, h=400.0, I=I_REF,
                                 I_viga=8358.0, I_pilar=12258.0)
        assert c.passos and all(p.formula for p in c.passos), caso
        assert c.fonte


# =====================================================================================
# Efeitos de segunda ordem (NBR 8800, Anexo D)
# =====================================================================================

def test_amplificacao_B2_cap16():
    """Manual, Passo 6-a: B2 = 1/[1 − (8,3/600)·30/43,8] ≈ 1,01 → pequena deslocabilidade."""
    m = portico_cap16()
    r = resolver(m, "C3", 31)
    dados = DadosSegundaOrdem(
        andares=[Andar(h=600.0, delta_h=8.3, soma_N=30.0, soma_H=43.8, nome="pórtico")],
        Rs=1.0)                       # o manual usa Rs = 1,0 nesta conta
    amp = amplificar(r, dados)
    perto(amp.B2["pórtico"], 1.01, 1.0, "B2 do pórtico")
    assert amp.classificacao == "pequena deslocabilidade"
    assert amp.aplicavel
    assert amp.passos and any("B₂" in p.texto for p in amp.passos)
    assert any("nocionais" in p for p in [amp.observacao])
    # esforços praticamente iguais aos de 1ª ordem (N pequeno)
    perto(amp.barra("pilar_esq").diagrama.absoluto("M").valor,
          r.barra("pilar_esq").diagrama.absoluto("M").valor, 2.0, "M amplificado")


def test_amplificacao_classificacao_e_B1():
    """B2 cresce com ΣN e Δh; B1 = Cm/(1 − N/Ne1) ≥ 1."""
    m = portico_cap16()
    r = resolver(m, "C1", 31)
    # pórtico flexível e muito carregado: média/grande deslocabilidade
    media = amplificar(r, DadosSegundaOrdem(
        andares=[Andar(600.0, delta_h=8.0, soma_N=400.0, soma_H=40.0)], Rs=0.85))
    assert media.classificacao == "média deslocabilidade", media.B2
    assert 1.1 < media.B2["pórtico"] <= 1.4
    assert "0,8" in media.observacao or "0,8·EI" in media.observacao

    grande = amplificar(r, DadosSegundaOrdem(
        andares=[Andar(600.0, delta_h=20.0, soma_N=400.0, soma_H=40.0)], Rs=0.85))
    assert grande.classificacao == "grande deslocabilidade"
    assert not grande.aplicavel and "rigorosa" in grande.observacao

    for b in media.barras:
        assert b.B1 >= 1.0, "B1 nunca pode ser menor que 1,0"
        assert b.Ne1 > 0


def test_coeficiente_Cm():
    """NBR 8800, D.2.1: Cm = 0,60 − 0,40(M1/M2), com sinal conforme a curvatura."""
    cm, _ = coeficiente_Cm(M1=100.0, M2=100.0)          # curvatura simples, M1/M2 = −1
    perto(cm, 1.0, 0.1, "Cm de curvatura simples")
    cm, _ = coeficiente_Cm(M1=100.0, M2=-100.0)         # curvatura reversa, M1/M2 = +1
    perto(cm, 0.2, 0.1, "Cm de curvatura reversa")
    cm, _ = coeficiente_Cm(M1=0.0, M2=100.0)
    perto(cm, 0.6, 0.1, "Cm com um momento nulo")
    cm, just = coeficiente_Cm(carga_transversal=True, extremos_restritos=False)
    perto(cm, 1.0, 0.1, "Cm com carga transversal e extremos livres")
    assert "D.2.1" in just


# =====================================================================================
# Equilíbrio global — teste automático sobre modelos aleatórios
# =====================================================================================

def modelos_aleatorios(n=24, semente=20260911):
    """Gera modelos variados (viga contínua, pórtico, treliça) com cargas aleatórias."""
    rnd = random.Random(semente)
    saida = []
    for k in range(n):
        familia = k % 4
        if familia == 0:                                  # viga contínua
            vaos = [rnd.uniform(200, 800) for _ in range(rnd.randint(1, 4))]
            m = viga_continua(vaos, A=rnd.uniform(20, 90), I=rnd.uniform(2000, 40000),
                              engaste_esq=rnd.random() < 0.4,
                              balanco_dir=rnd.choice([0.0, rnd.uniform(50, 200)]))
        elif familia == 1:                                # pórtico de galpão
            m = portico_galpao(rnd.uniform(1000, 3000), rnd.uniform(400, 900),
                               rnd.uniform(0.05, 0.30),
                               base_rotulada=rnd.random() < 0.7,
                               misula=(rnd.choice([None, Misula(rnd.uniform(100, 250),
                                                                fator=rnd.uniform(1.5, 4))])),
                               A_pilar=rnd.uniform(40, 90), I_pilar=rnd.uniform(8000, 30000),
                               A_viga=rnd.uniform(30, 70), I_viga=rnd.uniform(5000, 20000),
                               rotula_cumeeira=rnd.random() < 0.25)
        elif familia == 2:                                # treliça Pratt de 4 painéis
            d, h = rnd.uniform(150, 300), rnd.uniform(100, 250)
            coords, barras = [], []
            for i in range(5):
                coords.append((i * d, 0.0))
            for i in range(1, 4):
                coords.append((i * d, h))
            inf = list(range(5))
            sup = [5, 6, 7]
            for i in range(4):
                barras.append((inf[i], inf[i + 1]))
            barras += [(5, 6), (6, 7), (0, 5), (5, 1), (1, 6), (6, 2),
                       (2, 7), (7, 3), (4, 7)]
            m = trelica(coords, barras, {0: "rotulado", 4: "movel"},
                        A=rnd.uniform(5, 30))
        else:                                             # pórtico retangular engastado
            L, h = rnd.uniform(400, 1200), rnd.uniform(300, 700)
            m = Modelo("portal")
            m.add_no(0.0, 0.0, "engastado", "A")
            m.add_no(0.0, h, None, "B")
            m.add_no(L, h, None, "C")
            m.add_no(L, 0.0, rnd.choice(["engastado", "rotulado"]), "D")
            A_, I_ = rnd.uniform(20, 80), rnd.uniform(3000, 25000)
            m.add_barra("A", "B", A_, I_, rotulo="p1")
            m.add_barra("B", "C", A_, I_, rotulo="v",
                        rotula_i=rnd.random() < 0.3, rotula_f=rnd.random() < 0.3)
            m.add_barra("D", "C", A_, I_, rotulo="p2")

        # cargas aleatórias de todos os tipos
        m.caso("aleatorio")
        for j in range(len(m.barras)):
            if m.barras[j].rotula_i and m.barras[j].rotula_f and rnd.random() < 0.5:
                continue                                   # treliça: carrega nos nós
            escolha = rnd.random()
            if escolha < 0.45:
                m.distribuida("aleatorio", j, rnd.uniform(-0.2, 0.2),
                              rnd.choice(["perpendicular", "global_y", "global_x",
                                          "projetada_y", "projetada_x", "axial"]))
            elif escolha < 0.75:
                L = m.comprimento(j)
                m.concentrada("aleatorio", j, rnd.uniform(-40, 40), rnd.uniform(0.05, 0.95) * L,
                              rnd.choice(["perpendicular", "global_y", "global_x", "axial"]))
        for i in range(len(m.nos)):
            if rnd.random() < 0.35:
                so_forca = any(b.rotula_i and b.rotula_f for b in m.barras)
                m.nodal("aleatorio", i, Fx=rnd.uniform(-25, 25), Fy=rnd.uniform(-25, 25),
                        Mz=0.0 if so_forca else rnd.uniform(-2000, 2000))
        saida.append(m)
    return saida


def test_equilibrio_global_modelos_aleatorios():
    """Em todo caso de carga, ΣReações + ΣCargas aplicadas = 0."""
    for k, m in enumerate(modelos_aleatorios()):
        r = resolver(m, "aleatorio", 15)
        fx, fy, mz = r.equilibrio()
        carga = r.cargas_aplicadas()
        escala_f = max(abs(carga[0]), abs(carga[1]), 1.0)
        escala_m = max(abs(carga[2]), 1.0)
        assert abs(fx) < 1e-6 * escala_f, f"modelo {k}: ΣFx = {fx}"
        assert abs(fy) < 1e-6 * escala_f, f"modelo {k}: ΣFy = {fy}"
        assert abs(mz) < 1e-5 * escala_m, f"modelo {k}: ΣMz = {mz}"


def test_equilibrio_de_no_e_de_barra():
    """Equilíbrio local: os esforços de extremidade fecham com a carga da barra."""
    for m in modelos_aleatorios(8, semente=7):
        r = resolver(m, "aleatorio", 9)
        for rb in r.barras:
            # resultante das cargas da barra em eixos locais
            Rx = rb.qx * rb.L + sum(px for _, px, _ in rb.pontos)
            Ry = rb.qy * rb.L + sum(py for _, _, py in rb.pontos)
            f = rb.f_local
            escala = max(abs(Rx), abs(Ry), abs(f[0]), abs(f[1]), abs(f[4]), 1.0)
            assert abs(f[0] + f[3] + Rx) < 1e-6 * escala, rb.rotulo
            assert abs(f[1] + f[4] + Ry) < 1e-6 * escala, rb.rotulo
            # N e V das extremidades coerentes com f_local
            assert abs(rb.N_f - f[3]) < 1e-6 * escala
            assert abs(rb.V_f + f[4]) < 1e-6 * escala


# =====================================================================================
# Validação de dados (princípio 4 do guia: falha explícita)
# =====================================================================================

def test_erro_barra_de_comprimento_zero():
    m = Modelo()
    m.add_no(0.0, 0.0, "engastado", "A")
    m.add_no(0.0, 0.0, None, "B")
    m.add_barra("A", "B", 10.0, 100.0, rotulo="nula")
    m.caso("c")
    try:
        resolver(m, "c")
    except ErroDeDados as e:
        assert "comprimento nulo" in str(e), str(e)
    else:
        assert False, "deveria ter levantado ErroDeDados"


def test_erro_no_solto():
    m = viga(400.0, "rotulado", "movel", n=2)
    m.add_no(200.0, 300.0, None, "solto")
    m.caso("c")
    try:
        m.validar("c")
    except ErroDeDados as e:
        assert "Nó solto" in str(e), str(e)
    else:
        assert False, "deveria ter acusado nó solto"


def test_erro_estrutura_hipostatica():
    # apoios de menos
    m = viga(400.0, "movel", "movel", n=2)
    carregar(m, "c", 0.1)
    try:
        resolver(m, "c")
    except ErroDeDados as e:
        assert "hipostática" in str(e), str(e)
    else:
        assert False, "faltou acusar a falta de apoio horizontal"

    # apoios suficientes em número, mas mecanismo (rótulas demais)
    m2 = viga(400.0, "rotulado", "movel", n=2)
    m2.barras[0].rotula_f = True
    m2.barras[1].rotula_i = True
    carregar(m2, "c", 0.1)
    try:
        resolver(m2, "c")
    except ErroDeDados as e:
        assert "hipostática" in str(e), str(e)
    else:
        assert False, "faltou acusar o mecanismo criado pelas rótulas"


def test_erros_de_entrada_diversos():
    m = viga(400.0, "rotulado", "movel", n=2)
    carregar(m, "c", 0.1)
    for chamada, trecho in (
            (lambda: resolver(m, "inexistente"), "não existe"),
            (lambda: m.distribuida("c", "t1", 0.1, "diagonal"), "desconhecida"),
            (lambda: m.concentrada("c", "t1", 10.0, 1e6), "fora da barra"),
            (lambda: conferir_por_formula("viga_magica", q=1, L=1), "desconhecido"),
            (lambda: conferir_por_formula("biapoiada_uniforme", q=0.1, L=600), "faltam"),
            (lambda: portico_galpao(2000, 600, 0.1), "informe o perfil"),
            (lambda: portico_galpao(2000, 600, 5.0, A_pilar=50, I_pilar=1e4,
                                    A_viga=40, I_viga=8e3), "Inclinação"),
            (lambda: viga_continua([0.0], A=10, I=100), "positivos"),
    ):
        try:
            chamada()
        except ErroDeDados as e:
            assert trecho.lower() in str(e).lower(), f"mensagem inesperada: {e}"
        else:
            assert False, f"deveria ter levantado ErroDeDados ({trecho})"


def test_diagramas_amostrados():
    """Os diagramas trazem n pontos, os extremos e a posição de cada extremo."""
    L, q = 600.0, 0.10
    m = carregar(viga(L, "rotulado", "movel", n=1), "q", q)
    r = resolver(m, "q", 21)
    d = r.barra("t1").diagrama
    assert len(d.x) >= 21 and d.x[0] == 0.0 and abs(d.x[-1] - L) < 1e-6
    assert len(d.N) == len(d.V) == len(d.M) == len(d.x)
    perto(d.M_max.x, L / 2, 1.0, "posição do momento máximo")
    perto(d.M_max.valor, q * L ** 2 / 8, 0.5, "momento máximo")
    perto(d.V_max.valor, q * L / 2, 0.5, "cortante no apoio")
    perto(d.V_min.valor, -q * L / 2, 0.5, "cortante no apoio oposto")
    assert abs(d.absoluto("N").valor) < 1e-9, "viga sem carga axial"


if __name__ == "__main__":
    falhas = 0
    for nome, fn in sorted(list(globals().items())):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nome}")
            except AssertionError as erro:
                falhas += 1
                print(f"  FALHA {nome}: {erro}")
            except Exception as erro:                    # noqa: BLE001
                falhas += 1
                print(f"  ERRO  {nome}: {type(erro).__name__}: {erro}")
    print("todos os testes passaram" if not falhas else f"{falhas} teste(s) com problema")
    sys.exit(1 if falhas else 0)
