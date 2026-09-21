# -*- coding: utf-8 -*-
"""Testes do módulo `nucleo.nbr8800`.

Os dez exemplos resolvidos do Capítulo 7 do manual (`../manual/capitulos/
cap07_dimensionamento.html`) são reproduzidos com tolerância de 1 %, além de
testes próprios de coerência (monotonicidade, extremos da curva χ, continuidade
entre os regimes de FLT e a busca automática de perfil).

Roda com `python -m pytest testes/test_nbr8800.py -q` e também com
`python testes/test_nbr8800.py`.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import materiais as mat            # noqa: E402
from nucleo import nbr8800 as n                # noqa: E402
from nucleo.base import ErroDeDados            # noqa: E402
from nucleo.perfis import Perfil, perfil       # noqa: E402

A36 = mat.aco("ASTM A36")
A572 = mat.aco("ASTM A572 Gr.50")
VMB250 = mat.aco("VMB 250")


def perto(obtido, esperado, tol=0.01, o=""):
    """Compara com tolerância relativa (padrão 1 %, como manda o guia)."""
    ref = abs(esperado) if esperado else 1.0
    assert abs(obtido - esperado) <= tol * ref, \
        f"{o}: obtido {obtido:.6g}, esperado {esperado:.6g} (tol {tol:.1%})"


# --- perfis que o manual usa e que não estão no catálogo do sistema ---------

def tubo_100x100x475():
    """Tubo quadrado 100×100×4,75 do Exemplo 7.5 (catálogo Vallourec)."""
    return Perfil("TQ 100×100×4,75", "tubo",
                  {"nome": "TQ 100×100×4,75", "tipo": "quadrado", "h": 100.0,
                   "b": 100.0, "t": 4.75, "A": 17.5, "Ix": 267.0, "Iy": 267.0,
                   "Wx": 53.4, "Wy": 53.4, "rx": 3.91, "ry": 3.91, "J": 410.0,
                   "massa": 13.7})


def viga_soldada_vs600(tw=4.75):
    """Viga soldada VS 600 do Exemplo 7.9(b): h = 580 mm, alma de 4,75 mm."""
    return Perfil(f"VS 600×{tw:g}", "I",
                  {"d": 600.0, "bf": 250.0, "tw": tw, "tf": 10.0, "A": 78.5,
                   "Ix": 50000.0, "Iy": 2604.0, "Wx": 1666.0, "Zx": 1900.0,
                   "rx": 25.2, "ry": 5.76, "massa": 61.6})


def w360x51_catalogo_gerdau():
    """W 360×51 com o J do catálogo Gerdau (24,7 cm⁴), usado no Exemplo 7.8.

    O `dados/perfis.json` do sistema traz J = 21,92 cm⁴, calculado pela soma de
    retângulos (despreza os raios de concordância, a favor da segurança).
    """
    p = perfil("W 360×51,0")
    return Perfil(p.nome, "I", dict(p.dados, J=24.7))


# ===========================================================================
# Exemplo 7.1 — classificação do W 310×38,7
# ===========================================================================

def test_ex71_classificacao_w310x387():
    p = perfil("W 310×38,7")
    perto(p.esbeltez_mesa, 8.51, o="b/t da mesa")
    perto(p.esbeltez_alma, 50.1, o="h/tw da alma")

    for aco in (A36, A572):
        r = n.classificar(p, aco, "flexao")
        assert r.dados["mesa"].classe == "compacta"
        assert r.dados["alma"].classe == "compacta"
        assert r.dados["classe"] == "compacta"       # pode usar Mpl = Zx·fy

    # limites da Tabela 7.3 para flexão
    r36 = n.classificar(p, A36, "flexao")
    perto(r36.dados["mesa"].lam_p, 10.7, o="λp mesa A36")
    perto(r36.dados["mesa"].lam_r, 28.1, o="λr mesa A36")
    perto(r36.dados["alma"].lam_p, 106.0, o="λp alma A36")
    perto(r36.dados["alma"].lam_r, 161.0, o="λr alma A36")
    r50 = n.classificar(p, A572, "flexao")
    perto(r50.dados["mesa"].lam_p, 9.15, o="λp mesa A572")
    perto(r50.dados["mesa"].lam_r, 23.9, o="λr mesa A572")
    perto(r50.dados["alma"].lam_p, 90.5, o="λp alma A572")
    perto(r50.dados["alma"].lam_r, 137.0, o="λr alma A572")

    # compressão axial: mesa com Qs = 1, alma esbelta nos dois aços
    c36 = n.classificar(p, A36, "compressao")
    perto(c36.dados["mesa"].lam_r, 15.8, o="λr mesa compressão A36")
    perto(c36.dados["alma"].lam_r, 42.1, o="λr alma compressão A36")
    assert c36.dados["mesa"].classe == "compacta"
    assert c36.dados["alma"].classe == "esbelta"
    c50 = n.classificar(p, A572, "compressao")
    perto(c50.dados["mesa"].lam_r, 13.5, o="λr mesa compressão A572")
    perto(c50.dados["alma"].lam_r, 35.9, o="λr alma compressão A572")
    assert c50.dados["classe"] == "esbelta"          # exige Qa < 1 (Ex. 7.6)


def test_tabela_73_outros_limites():
    """Demais linhas da Tabela 7.3 do manual."""
    perto(1.40 * math.sqrt(20000 / 25.0), 39.6, o="parede de tubo A36")
    perto(1.40 * math.sqrt(20000 / 34.5), 33.7, o="parede de tubo A572")
    L = perfil('L 2"×1/4"')
    perto(n.classificar_mesa(L, A36, "compressao").lam_r, 12.7, o="aba de L, A36")
    perto(n.classificar_mesa(L, A572, "compressao").lam_r, 10.8, o="aba de L, A572")
    # alma em cisalhamento (kv = 5)
    perto(1.10 * math.sqrt(5 * 20000 / 25.0), 69.6, o="λp cisalhamento A36")
    perto(1.37 * math.sqrt(5 * 20000 / 25.0), 86.6, o="λr cisalhamento A36")
    perto(1.10 * math.sqrt(5 * 20000 / 34.5), 59.2, o="λp cisalhamento A572")
    perto(1.37 * math.sqrt(5 * 20000 / 34.5), 73.8, o="λr cisalhamento A572")


# ===========================================================================
# Exemplo 7.2 — tirante em cantoneira L 2"×1/4" com 2 parafusos de 1/2"
# ===========================================================================

def test_ex72_tirante_cantoneira():
    L = perfil('L 2"×1/4"')
    r = n.tracao(L, A36, N_Sd=100.0, L=280.0, n_furos=1, d_parafuso=1.27,
                 t_furo=0.635, ec=1.50, lc=6.0)
    perto(r.dados["N_Rd_escoamento"], 137.7, o="escoamento da seção bruta")
    perto(r.dados["An"], 5.03, o="área líquida")
    perto(r.dados["Ct"], 0.75, o="coeficiente Ct")
    perto(r.dados["Ae"], 3.77, o="área líquida efetiva")
    perto(r.dados["N_Rd_ruptura"], 111.8, o="ruptura da seção líquida")
    perto(r.dados["N_Rd"], 111.8, o="Nt,Rd adotado")
    assert r.dados["governa"] == "ruptura"
    perto(r.dados["esbeltez"], 283.0, o="L/r")
    assert r.ok                                       # 283 ≤ 300 e 100 ≤ 111,8

    # com 3 parafusos (lc = 12 cm) o manual dá Ct = 0,875 e Nt,Rd ≈ 130 kN
    r3 = n.tracao(L, A36, L=280.0, n_furos=1, d_parafuso=1.27, t_furo=0.635,
                  ec=1.50, lc=12.0)
    perto(r3.dados["Ct"], 0.875, o="Ct com 3 parafusos")
    perto(r3.dados["N_Rd_ruptura"], 130.0, tol=0.015, o="Nt,Rd com 3 parafusos")


# ===========================================================================
# Exemplo 7.3 — barra redonda ø 16 mm de contraventamento
# ===========================================================================

def test_ex73_barra_redonda_16mm():
    Ag = math.pi * 1.6 ** 2 / 4.0
    perto(Ag, 2.01, o="área bruta")
    barra = Perfil("ø 16 mm", "barra", {"A": Ag, "d": 16.0, "tw": 1.6, "rmin": 0.4})
    r = n.tracao(barra, A36, N_Sd=40.0, L=450.0, rosqueada=True, pretensionada=True)
    perto(r.dados["N_Rd_escoamento"], 45.7, o="escoamento")
    perto(r.dados["Ae"], 1.51, o="Ae = 0,75·Ag na rosca")
    perto(r.dados["N_Rd_ruptura"], 44.7, o="ruptura na rosca")
    perto(r.dados["N_Rd"], 44.7, o="Nt,Rd")
    assert r.dados["governa"] == "ruptura"
    # L/r = 1 125 >> 300, mas a barra é pré-tensionada: a norma dispensa o limite
    esb = [v for v in r.verificacoes if "Esbeltez" in v.titulo][0]
    assert esb.dispensada and r.ok


# ===========================================================================
# Exemplo 7.4 — pilar W 250×73, L = 6 m, K = 1,0, A572 → Nc,Rd ≈ 1 550 kN
# ===========================================================================

def test_ex74_pilar_w250x73():
    p = perfil("W 250×73,0")
    r = n.compressao(p, A572, Lx=600.0, Ly=600.0, N_Sd=1000.0)
    perto(r.dados["Q"], 1.0, o="fator Q")
    perto(r.dados["lambda_x"], 54.3, tol=0.015, o="KL/rx")
    perto(r.dados["lambda_y"], 92.7, o="KL/ry")
    perto(r.dados["modos_Ne"]["Ney"], 2129.0, o="Ney")
    assert r.dados["modo_critico"] == "Ney"           # flexão em y governa
    perto(r.dados["lambda_0"], 1.226, o="λ0")
    perto(r.dados["chi"], 0.533, o="χ")
    perto(r.dados["N_Rd"], 1550.0, o="Nc,Rd")
    assert r.ok

    # travado no meio na direção fraca: passa a governar o eixo x (manual: 2 343 kN).
    # A viga que trava o eixo fraco no meio da altura também impede o giro da
    # seção, então KtLt = 300 cm (sem informar Lt o módulo adotaria 600 cm, a
    # favor da segurança, e a flambagem por torção passaria a governar).
    r2 = n.compressao(p, A572, Lx=600.0, Ly=300.0, Lt=300.0)
    perto(r2.dados["lambda_0"], 0.718, tol=0.015, o="λ0 com travamento")
    perto(r2.dados["chi"], 0.806, tol=0.015, o="χ com travamento")
    perto(r2.dados["N_Rd"], 2343.0, tol=0.015, o="Nc,Rd com travamento")


# ===========================================================================
# Exemplo 7.5 — banzo em tubo 100×100×4,75, L = 2,5 m → ≈ 320 kN
# ===========================================================================

def test_ex75_tubo_treliça():
    t = tubo_100x100x475()
    c = n.classificar(t, VMB250, "compressao")
    perto(c.dados["mesa"].lam, 18.1, o="(B − 3t)/t")
    perto(c.dados["mesa"].lam_r, 39.6, o="limite da parede do tubo")
    assert c.dados["classe"] == "compacta"

    r = n.compressao(t, VMB250, Lx=250.0, N_Sd=250.0)
    perto(r.dados["Q"], 1.0, o="Q")
    perto(r.dados["esbeltez"], 63.9, o="KL/r")
    perto(r.dados["lambda_0"], 0.720, o="λ0")
    perto(r.dados["chi"], 0.805, o="χ")
    perto(r.dados["N_Rd"], 320.0, o="Nc,Rd")
    assert r.ok

    # comparação do manual: 2L 2½"×1/4" com KL/r ≈ 128 rende menos da metade
    assert r.dados["N_Rd"] > 2 * 148.0 * 0.95


# ===========================================================================
# Exemplo 7.6 — fator Q do W 310×38,7 → Q ≈ 0,923
# ===========================================================================

def test_ex76_fator_q():
    p = perfil("W 310×38,7")
    Q, Qs, Qa, passos = n.fator_Q(p, A572)
    perto(Qs, 1.0, o="Qs")
    perto(Qa, 0.923, o="Qa")
    perto(Q, 0.923, o="Q")
    assert passos and all(x.norma for x in passos)

    # largura efetiva da alma: 22,4 cm (manual, passo 2)
    bef = n.largura_efetiva(29.06, 0.58, A572.fy, ca=0.34)
    perto(bef, 22.4, o="bef da alma")

    # em A36 o efeito é menor (manual: Q ≈ 0,96)
    Q36 = n.fator_Q(p, A36)[0]
    perto(Q36, 0.96, tol=0.015, o="Q em A36")
    assert Q36 > Q


# ===========================================================================
# Exemplo 7.7 — viga W 360×51, L = 7 m, Lb = 0 → MRd ≈ 282 kN·m, δ = 1,87 cm
# ===========================================================================

def test_ex77_viga_w360x51_travada():
    p = perfil("W 360×51,0")
    qd, L = 0.25, 700.0                                # 25 kN/m, 7 m
    M_Sd, V_Sd = n.esforcos_viga("biapoiada_distribuida", L, qd)
    perto(M_Sd, 15312.5, o="MSd")
    perto(V_Sd, 87.5, o="VSd")

    r = n.flexao(p, A572, M_Sd=M_Sd, Lb=0.0)
    perto(r.dados["Mpl"], 31016.0, o="Mpl")
    perto(r.dados["M_Rd"], 28196.0, o="MRd")
    perto(r.dados["M_Rd"] / 100.0, 282.0, o="MRd em kN·m")
    perto(1.5 * p.Wx * A572.fy / 1.10, 37683.0, o="teto 1,5·W·fy/γa1")
    perto(r.razao, 0.54, tol=0.02, o="razão de momento")
    assert r.ok

    v = n.cisalhamento(p, A572, V_Sd=V_Sd)
    perto(p.Aw, 25.6, o="Aw = d·tw")
    perto(v.Rd, 481.0, o="VRd")
    assert v.ok and "plástico" in v.observacao

    f = n.flecha(p, L, caso="biapoiada_distribuida", q=0.17, limite="L/350")
    perto(f.Sd, 1.87, o="flecha")
    perto(f.Rd, 2.00, o="limite L/350")
    assert f.ok
    perto(f.razao, 0.93, tol=0.02, o="uso da flecha")

    # o W 360×44,6 (Ix = 12 258 cm⁴) é reprovado por flecha, como diz o manual
    p44 = perfil("W 360×44,6")
    f44 = n.flecha(p44, L, q=0.17, limite="L/350")
    perto(f44.Sd, 2.17, tol=0.015, o="flecha do W 360×44,6")
    assert not f44.ok
    r44 = n.flexao(p44, A572, M_Sd=M_Sd, Lb=0.0)
    perto(r44.dados["M_Rd"] / 100.0, 246.0, o="MRd do W 360×44,6")
    assert r44.ok


# ===========================================================================
# Exemplo 7.8 — mesma viga com Lb = 3,5 m e Cb = 1,30
# ===========================================================================

def test_ex78_cb():
    # momentos do trecho destravado de 0 a 3,5 m (manual, passo 3)
    cb = n.calcular_cb((153.1, 67.0, 114.8, 143.6))
    perto(cb, 1.30, o="Cb calculado")
    # mesma resposta partindo dos cinco momentos do trecho
    q, L = 25.0, 7.0
    ms = [q * x * (L - x) / 2.0 for x in (0.0, 0.875, 1.75, 2.625, 3.5)]
    perto(n.calcular_cb(ms), 1.30, o="Cb pelos 5 momentos")
    # valores tabelados (Tabela 7.7)
    perto(n.cb_tabelado("uniforme"), 1.00, o="Cb uniforme")
    perto(n.cb_tabelado("distribuida"), 1.14, o="Cb distribuída")
    perto(n.cb_tabelado("concentrada_meio"), 1.32, o="Cb carga concentrada")
    perto(n.calcular_cb((1.0, 0.75, 1.0, 0.75)), 1.14, o="Cb da viga biapoiada")
    perto(n.calcular_cb((1.0, 0.5, 1.0, 0.5)), 1.32, o="Cb da carga concentrada")
    perto(n.calcular_cb((1.0, 0.75, 0.5, 0.25)), 1.67, o="Cb do momento linear")
    perto(n.calcular_cb((1.0, 0.5, 0.0, 0.5)), 2.27, o="Cb da curvatura reversa")


def test_ex78_viga_w360x51_lb35():
    p = w360x51_catalogo_gerdau()
    perto(n.comprimento_Lp(p, A572), 164.0, o="Lp")
    perto(n.comprimento_Lr(p, A572), 475.0, o="Lr")

    M_Sd = 15312.5
    r = n.flexao(p, A572, M_Sd=M_Sd, Lb=350.0, Cb=1.30)
    perto(r.dados["M_Rd"] / 100.0, 282.0, o="MRd com Cb = 1,30")
    assert r.ok and r.razao <= 0.55

    # passo 5 do manual: ignorando o Cb, MRd cai para ≈ 218 kN·m
    r1 = n.flexao(p, A572, M_Sd=M_Sd, Lb=350.0, Cb=1.0)
    perto(r1.dados["M_Rd"] / 100.0, 218.0, o="MRd com Cb = 1,0")
    assert r1.ok

    # passo 6: sem nenhum travamento (Lb = 7 m > Lr) a viga é reprovada
    r2 = n.flexao(p, A572, M_Sd=M_Sd, Lb=700.0, Cb=1.14)
    perto(r2.dados["M_Rd"] / 100.0, 113.0, o="MRd com Lb = 7 m")
    perto(r2.razao, 1.35, tol=0.02, o="razão com Lb = 7 m")
    assert not r2.ok
    assert "lateral" in r2.critica.titulo


def test_j_conservador_do_catalogo():
    """O J do catálogo do sistema é conservador — e o resultado, a favor da segurança.

    `dados/perfis.json` calcula J pela soma de retângulos (21,92 cm⁴ no
    W 360×51) enquanto o catálogo Gerdau usado pelo manual traz 24,7 cm⁴.
    A diferença aparece no Lr e no regime elástico da FLT.
    """
    cat = perfil("W 360×51,0")
    ger = w360x51_catalogo_gerdau()
    assert cat.J < ger.J
    assert n.comprimento_Lr(cat, A572) < n.comprimento_Lr(ger, A572)
    m_cat = n.flexao(cat, A572, Lb=700.0, Cb=1.14).dados["M_Rd"]
    m_ger = n.flexao(ger, A572, Lb=700.0, Cb=1.14).dados["M_Rd"]
    assert m_cat < m_ger                      # conservador
    assert abs(m_cat - m_ger) / m_ger < 0.05  # e próximo (3,6 %)


# ===========================================================================
# Exemplo 7.9 — cisalhamento em viga laminada e em viga soldada
# ===========================================================================

def test_ex79a_cortante_w410x461():
    p = perfil("W 410×46,1")
    perto(p.Aw, 28.2, o="Aw")
    v = n.cisalhamento(p, A572, V_Sd=320.0)
    perto(0.60 * p.Aw * A572.fy, 584.0, o="Vpl")
    perto(p.esbeltez_alma, 54.4, o="h/tw")
    perto(v.Rd, 531.0, o="VRd")
    perto(v.razao, 0.60, tol=0.02, o="razão")
    assert v.ok


def test_ex79b_cortante_viga_soldada():
    vs = viga_soldada_vs600()
    perto(vs.esbeltez_alma, 122.0, tol=0.015, o="h/tw da alma esbelta")
    v = n.cisalhamento(vs, A572)
    perto(0.60 * vs.Aw * A572.fy, 590.0, o="Vpl")
    perto(v.Rd, 156.0, o="VRd sem enrijecedores")
    assert "elástico" in v.observacao

    # com enrijecedores a cada a = h: kv = 10 e VRd dobra
    kv, _ = n.coeficiente_kv(58.0, 0.475, a_enrij=58.0)
    perto(kv, 10.0, o="kv com a/h = 1")
    perto(1.10 * math.sqrt(kv * 20000 / 34.5), 83.7, o="λp com kv = 10")
    perto(1.37 * math.sqrt(kv * 20000 / 34.5), 104.0, o="λr com kv = 10")
    v2 = n.cisalhamento(vs, A572, a_enrij=58.0)
    perto(v2.Rd, 313.0, o="VRd com enrijecedores")

    # alternativa do manual: alma de 8 mm → regime inelástico
    v3 = n.cisalhamento(viga_soldada_vs600(tw=8.0), A572)
    perto(v3.Rd, 738.0, o="VRd com alma de 8 mm")
    assert "inelástico" in v3.observacao


# ===========================================================================
# Exemplo 7.10 — flexo-compressão do W 310×38,7 → interação ≈ 0,51
# ===========================================================================

def test_ex710_flexo_compressao():
    p = perfil("W 310×38,7")
    # mãos-francesas travam as duas mesas a cada 1,5 m: Lb = KLy = KtLt = 150 cm
    r = n.flexao_composta(p, A572, N_Sd=120.0, Mx_Sd=9000.0, Lx=600.0, Ly=150.0,
                          Lt=150.0, Lb=150.0, Cb=1.0)
    perto(r.dados["Q"], 0.923, o="Q")
    perto(r.dados["lambda_0"], 0.580, o="λ0")
    perto(r.dados["chi"], 0.869, o="χ")
    perto(r.dados["N_Rd"], 1249.0, o="Nc,Rd")
    perto(r.dados["Mx_Rd"] / 100.0, 193.0, o="Mx,Rd")
    perto(r.dados["razao_N"], 0.096, tol=0.02, o="NSd/NRd")
    assert r.dados["ramo"].startswith("N/N_Rd < 0,2")
    perto(r.dados["interacao"], 0.514, o="equação de interação")
    assert r.ok

    # passo 2: Lp = 162 cm ≥ Lb = 150 cm, logo não há FLT
    perto(n.comprimento_Lp(p, A572), 162.0, o="Lp")
    flt = [v for v in r.verificacoes if "lateral" in v.titulo][0]
    assert flt.dispensada or flt.Rd >= r.dados["Mx_Rd"] - 1e-6

    # passo 4: análise de 1ª ordem com Kx = 2,0 (o manual chega a 0,54)
    r2 = n.flexao_composta(p, A572, N_Sd=120.0, Mx_Sd=9000.0, Lx=600.0, Kx=2.0,
                           Ly=150.0, Lt=150.0, Lb=150.0, Cb=1.0)
    perto(r2.dados["N_Rd"], 819.0, tol=0.015, o="Nc,Rd com Kx = 2,0")
    perto(r2.dados["interacao"], 0.54, tol=0.02, o="interação com Kx = 2,0")


def test_flexao_composta_ramo_superior_e_tracao():
    p = perfil("W 310×38,7")
    # força axial alta → ramo NSd/NRd ≥ 0,2 (eq. 7.20)
    r = n.flexao_composta(p, A572, N_Sd=600.0, Mx_Sd=5000.0, Lx=600.0, Ly=150.0,
                          Lt=150.0, Lb=150.0)
    assert r.dados["ramo"].startswith("N/N_Rd ≥ 0,2")
    esperado = r.dados["razao_N"] + (8.0 / 9.0) * r.dados["razao_Mx"]
    perto(r.dados["interacao"], esperado, tol=1e-9, o="eq. 7.20")

    # flexo-tração usa Nt,Rd
    rt = n.flexao_composta(p, A572, N_Sd=400.0, Mx_Sd=5000.0, tipo_axial="tracao",
                           Lx=600.0, Lb=150.0)
    perto(rt.dados["N_Rd"], p.A * A572.fy / 1.10, tol=1e-9, o="Nt,Rd")
    assert rt.dados["interacao"] > 0


# ===========================================================================
# Curva χ, Lp/Lr e monotonicidade (testes próprios)
# ===========================================================================

def test_chi_extremos_e_tabela_76():
    perto(n.fator_chi(0.0), 1.000, tol=1e-9, o="χ(0)")
    # Tabela 7.6 do manual
    tabela = {0.1: 0.996, 0.2: 0.983, 0.5: 0.901, 0.8: 0.765, 1.0: 0.658,
              1.2: 0.547, 1.5: 0.390, 1.8: 0.271, 2.0: 0.219, 2.5: 0.140,
              3.0: 0.097}
    for lam0, chi in tabela.items():
        perto(n.fator_chi(lam0), chi, tol=0.005, o=f"χ({lam0})")
    # os dois ramos se encontram em λ0 = 1,5 (é por isso que a norma troca ali)
    perto(0.658 ** 2.25, 0.877 / 1.5 ** 2, tol=0.001, o="continuidade em λ0 = 1,5")
    # monotonicidade
    valores = [n.fator_chi(x / 10.0) for x in range(0, 31)]
    assert all(b <= a for a, b in zip(valores, valores[1:]))


def test_lp_lr_coerencia_com_a_figura_712():
    """Curva MRd × Lb do W 360×51 (Figura 7.12 do manual)."""
    p = w360x51_catalogo_gerdau()
    Lp = n.comprimento_Lp(p, A572)
    Lr = n.comprimento_Lr(p, A572)
    assert 0 < Lp < Lr
    Mpl = p.Zx * A572.fy
    Mr = 0.7 * A572.fy * p.Wx

    # em Lb = Lp a viga ainda plastifica; em Lb = Lr o momento nominal vale Mr
    perto(n.flexao(p, A572, Lb=Lp, Cb=1.0).dados["M_Rd"], Mpl / 1.10,
          tol=0.002, o="MRd em Lb = Lp")
    perto(n.flexao(p, A572, Lb=Lr, Cb=1.0).dados["M_Rd"], Mr / 1.10,
          tol=0.005, o="MRd em Lb = Lr")
    # continuidade entre a interpolação e o Mcr elástico em Lb = Lr
    m_dentro = n.flexao(p, A572, Lb=Lr * 0.999, Cb=1.0).dados["M_Rd"]
    m_fora = n.flexao(p, A572, Lb=Lr * 1.001, Cb=1.0).dados["M_Rd"]
    perto(m_fora, m_dentro, tol=0.01, o="continuidade em Lr")

    # MRd cai quando Lb cresce e nunca passa de Mpl/γa1
    anterior = None
    for Lb in (0.0, 100.0, Lp, 250.0, 350.0, Lr, 600.0, 700.0, 900.0):
        M = n.flexao(p, A572, Lb=Lb, Cb=1.0).dados["M_Rd"]
        assert M <= Mpl / 1.10 + 1e-6
        if anterior is not None:
            assert M <= anterior + 1e-6
        anterior = M
    # Lp ≈ 42·ry em A572, como diz o manual
    perto(Lp / p.ry, 42.4, tol=0.02, o="Lp/ry em A572")


def test_monotonicidade_perfis_mais_pesados():
    """Perfil mais pesado da mesma série resiste mais (flexão e compressão)."""
    serie = ["W 360×32,9", "W 360×39,0", "W 360×44,6", "W 360×51,0", "W 360×57,8"]
    momentos, forcas, cortantes = [], [], []
    for nome in serie:
        p = perfil(nome)
        momentos.append(n.flexao(p, A572, Lb=200.0, Cb=1.0).dados["M_Rd"])
        forcas.append(n.compressao(p, A572, Lx=400.0).dados["N_Rd"])
        cortantes.append(n.cisalhamento(p, A572).Rd)
    for lista, nome in ((momentos, "MRd"), (forcas, "NcRd"), (cortantes, "VRd")):
        assert all(b > a for a, b in zip(lista, lista[1:])), f"{nome} não cresceu: {lista}"


def test_compressao_cai_com_o_comprimento():
    p = perfil("W 250×73,0")
    anterior = None
    for L in (100.0, 300.0, 400.0, 500.0, 600.0, 800.0):
        N = n.compressao(p, A572, Lx=L).dados["N_Rd"]
        if anterior is not None:
            assert N < anterior
        anterior = N
    # o limite superior é o escoamento da seção
    assert n.compressao(p, A572, Lx=50.0).dados["N_Rd"] < p.A * A572.fy / 1.10


# ===========================================================================
# Tabelas 7.10 e 7.12 do manual
# ===========================================================================

def test_tabela_710_momento_e_cortante():
    casos = {                      # perfil: (MRd A36, VRd A36, MRd A572, VRd A572)
        "W 250×73,0": (224, 297, 309, 409),
        "W 310×38,7": (140, 245, 193, 338),
        "W 360×51,0": (204, 349, 282, 481),
        "W 410×46,1": (203, 385, 279, 531),
        "W 200×46,1": (113, 199, 155, 275),   # mesa semicompacta em A572 (*)
        "W 310×97,0": (362, 416, 491, 574),   # idem (*)
    }
    for nome, (m36, v36, m50, v50) in casos.items():
        p = perfil(nome)
        for aco, m, v in ((A36, m36, v36), (A572, m50, v50)):
            M = n.flexao(p, aco, Lb=0.0).dados["M_Rd"] / 100.0
            perto(M, m, tol=0.015, o=f"MRd de {nome} em {aco.nome}")
            V = n.cisalhamento(p, aco).Rd
            perto(V, v, tol=0.015, o=f"VRd de {nome} em {aco.nome}")


def test_tabela_712_pilares():
    casos = {                      # perfil: Nc,Rd para KL = 3, 4, 5, 6 e 8 m
        "W 200×46,1": (1430, 1176, 915, 672, 378),
        "W 250×73,0": (2484, 2198, 1878, 1550, 954),
        "W 310×38,7": (948, 686, 457, 317, 178),
        "W 310×97,0": (3467, 3179, 2843, 2480, 1753),
        "W 250×32,7": (727, 465, 297, 207, 116),
    }
    for nome, valores in casos.items():
        p = perfil(nome)
        for KL, esperado in zip((300.0, 400.0, 500.0, 600.0, 800.0), valores):
            r = n.compressao(p, A572, Lx=KL, Ly=KL)
            perto(r.dados["N_Rd"], esperado, tol=0.015, o=f"Nc,Rd de {nome} com KL = {KL/100} m")


def test_fator_q_da_tabela_712():
    perto(n.fator_Q(perfil("W 200×46,1"), A572)[0], 1.00, o="Q do W 200×46,1")
    perto(n.fator_Q(perfil("W 250×73,0"), A572)[0], 1.00, o="Q do W 250×73")
    perto(n.fator_Q(perfil("W 310×97,0"), A572)[0], 1.00, o="Q do W 310×97")
    perto(n.fator_Q(perfil("W 310×38,7"), A572)[0], 0.923, o="Q do W 310×38,7")
    perto(n.fator_Q(perfil("W 250×32,7"), A572)[0], 0.976, tol=0.015, o="Q do W 250×32,7")


# ===========================================================================
# Estados-limites de serviço
# ===========================================================================

def test_flecha_casos_usuais():
    p = perfil("W 360×51,0")
    I, L, q, P = p.Ix, 700.0, 0.17, 100.0
    d, _, _ = n.flecha_caso("biapoiada_distribuida", L, I, q=q)
    perto(d, 5 * q * L ** 4 / (384 * 20000 * I), tol=1e-9, o="biapoiada distribuída")
    d, _, _ = n.flecha_caso("biapoiada_concentrada", L, I, P=P)
    perto(d, P * L ** 3 / (48 * 20000 * I), tol=1e-9, o="carga concentrada")
    d, _, _ = n.flecha_caso("balanco_distribuida", L, I, q=q)
    perto(d, q * L ** 4 / (8 * 20000 * I), tol=1e-9, o="balanço")
    d, _, _ = n.flecha_caso("biengastada_distribuida", L, I, q=q)
    perto(d, q * L ** 4 / (384 * 20000 * I), tol=1e-9, o="biengastada")
    # a biengastada tem 1/5 da flecha da biapoiada
    perto(n.flecha_caso("biengastada_distribuida", L, I, q=q)[0] * 5.0,
          n.flecha_caso("biapoiada_distribuida", L, I, q=q)[0], tol=1e-9,
          o="relação biapoiada/biengastada")

    # regra de bolso do manual: δ ≈ 0,65·qs·L⁴/Ix (qs em kN/m, L em m)
    perto(0.65 * 17 * 7 ** 4 / p.Ix, 1.87, tol=0.01, o="regra de bolso da flecha")


def test_flecha_limites_do_anexo_c():
    p = perfil("W 360×51,0")
    v350 = n.flecha(p, 700.0, q=0.17, limite="L/350")
    v250 = n.flecha(p, 700.0, q=0.17, limite="L/250")
    v180 = n.flecha(p, 700.0, q=0.17, limite="L/180")
    perto(v350.Rd, 2.00, o="L/350")
    perto(v250.Rd, 2.80, o="L/250")
    perto(v180.Rd, 3.89, o="L/180")
    assert v350.ok and v250.ok and v180.ok
    # nomes do Anexo C e denominador numérico
    perto(n.flecha(p, 700.0, q=0.17, limite="viga_piso").Rd, 2.00, o="viga_piso")
    perto(n.flecha(p, 700.0, q=0.17, limite=500).Rd, 1.40, o="L/500")
    assert not n.flecha(p, 700.0, q=0.17, limite="viga_alvenaria").ok
    # balanço: vão equivalente 2L (Anexo C, Tabela C.1)
    vb = n.flecha(p, 200.0, caso="balanco_distribuida", q=0.17, limite="L/250")
    perto(vb.Rd, 400.0 / 250.0, tol=1e-9, o="limite do balanço")
    # contraflecha desconta da flecha verificada
    vc = n.flecha(p, 700.0, q=0.17, limite="L/350", contraflecha=1.0)
    perto(vc.Sd, v350.Sd - 1.0, tol=1e-9, o="contraflecha")


# ===========================================================================
# Busca automática de perfil
# ===========================================================================

def test_dimensionar_viga_devolve_perfil_que_passa():
    r = n.dimensionar_viga(A572, L=700.0, q_Sd=0.25, q_servico=0.17, Lb=0.0,
                           limite="L/350")
    assert r.dados["encontrado"] and r.ok and r.razao <= 1.0
    cand = r.dados["candidatos"]
    assert len(cand) > 10 and all("perfil" in c for c in cand)

    # o perfil adotado é o mais leve entre os que passam
    aprovados = [c for c in cand if c["ok"]]
    assert aprovados
    assert r.perfil == min(aprovados, key=lambda c: c["massa"])["perfil"]

    # e reverificado isoladamente ele realmente passa
    conf = n.verificar_viga(perfil(r.perfil), A572, 700.0, q_Sd=0.25,
                            q_servico=0.17, Lb=0.0, limite="L/350")
    assert conf.ok
    perto(conf.razao, r.razao, tol=1e-9, o="reverificação do perfil adotado")

    # todos os perfis mais leves que o adotado foram reprovados
    massa = perfil(r.perfil).massa
    for c in cand:
        if c["massa"] < massa and c["razao"] is not None:
            assert not c["ok"], f"{c['perfil']} é mais leve e passaria"


def test_dimensionar_viga_sem_travamento_pede_perfil_maior():
    """Sem contenção lateral (Lb = L) o perfil necessário é mais pesado."""
    travada = n.dimensionar_viga(A572, L=700.0, q_Sd=0.25, q_servico=0.17, Lb=0.0)
    solta = n.dimensionar_viga(A572, L=700.0, q_Sd=0.25, q_servico=0.17, Lb=700.0,
                               Cb=1.14)
    assert solta.dados["encontrado"]
    assert perfil(solta.perfil).massa >= perfil(travada.perfil).massa


def test_dimensionar_pilar():
    r = n.dimensionar_pilar(A572, N_Sd=1500.0, Lx=600.0, Ly=600.0)
    assert r.dados["encontrado"] and r.ok
    conf = n.verificar_pilar(perfil(r.perfil), A572, N_Sd=1500.0, Lx=600.0, Ly=600.0)
    assert conf.ok and conf.dados["N_Rd"] >= 1500.0
    # o manual (Tabela 7.12) mostra o W 250×73 com 1 550 kN em KL = 6 m
    assert perfil(r.perfil).massa <= 73.0 + 1e-9

    # pilar com momento cai na flexão composta
    rc = n.dimensionar_pilar(A572, N_Sd=120.0, Lx=600.0, Ly=150.0, Lt=150.0,
                             Mx_Sd=9000.0, Lb=150.0)
    assert rc.dados["encontrado"] and rc.ok
    assert any("Interação" in v.titulo for v in rc.verificacoes)


def test_dimensionar_sem_solucao():
    """Carga absurda: devolve o menos ruim, marcado como não encontrado."""
    r = n.dimensionar_viga(A572, L=1200.0, q_Sd=5.0, q_servico=3.5, Lb=1200.0,
                           familia="W")
    assert r.dados["encontrado"] is False
    assert not r.ok


# ===========================================================================
# Memória de cálculo, unidades e falhas explícitas
# ===========================================================================

def test_memoria_de_calculo_completa():
    p = perfil("W 310×38,7")
    r = n.flexao_composta(p, A572, N_Sd=120.0, Mx_Sd=9000.0, Lx=600.0, Ly=150.0,
                          Lt=150.0, Lb=150.0)
    assert r.verificacoes
    for v in r.verificacoes:
        assert v.norma, f"{v.titulo} sem item de norma"
        if v.dispensada:
            assert v.observacao
            continue
        assert v.passos, f"{v.titulo} sem memória de cálculo"
        for passo in v.passos:
            assert passo.texto and passo.formula and passo.valor
            assert passo.norma, f"passo sem norma em {v.titulo}: {passo.texto}"
        assert 0.0 <= v.razao < 10.0
        assert v.resumo()


def test_ziguezague_e_ct_explicito():
    chapa = Perfil("chapa 200×12,5", "chapa", {"A": 25.0, "tw": 1.25, "rmin": 0.36})
    # três furos em ziguezague, dois trechos inclinados (s = 6 cm, g = 5 cm)
    r = n.tracao(chapa, A36, n_furos=3, d_parafuso=1.905, t_furo=1.25,
                 ziguezague=[(6.0, 5.0), (6.0, 5.0)], Ct=1.0)
    esperado = 25.0 - 3 * (1.905 + 0.35) * 1.25 + 2 * (6.0 ** 2 / (4 * 5.0)) * 1.25
    perto(r.dados["An"], esperado, tol=1e-9, o="An com ziguezague")
    perto(r.dados["Ct"], 1.0, tol=1e-9, o="Ct explícito")

    # adota-se sempre a menor An entre as linhas de ruptura possíveis:
    # com s = 6 cm e g = 5 cm a linha reta por dois furos é a crítica...
    reto = n.tracao(chapa, A36, n_furos=2, d_parafuso=1.905, t_furo=1.25, Ct=1.0)
    assert reto.dados["An"] < r.dados["An"]
    # ...mas com furos mais próximos (s = 3 cm) o ziguezague passa a governar
    zig = n.tracao(chapa, A36, n_furos=3, d_parafuso=1.905, t_furo=1.25,
                   ziguezague=[(3.0, 5.0), (3.0, 5.0)], Ct=1.0)
    assert zig.dados["An"] < reto.dados["An"]


def test_erros_explicitos():
    p = perfil("W 360×51,0")
    for chamada in (
        lambda: n.flexao(p, A572, Lb=-1.0),
        lambda: n.flexao(p, A572, Lb=100.0, Cb=0.9),
        lambda: n.flexao(p, A572, eixo="z"),
        lambda: n.flexao(perfil('L 2"×1/4"'), A36, Lb=100.0),
        lambda: n.classificar(p, A572, "torcao"),
        lambda: n.compressao(p, A572, Lx=0.0),
        lambda: n.tracao(p, A572, n_furos=2),
        lambda: n.calcular_cb((1.0, 2.0)),
        lambda: n.cb_tabelado("inexistente"),
        lambda: n.flecha_caso("inexistente", 700.0, 1000.0, q=0.1),
        lambda: n.flecha(p, 700.0, q=0.1, limite="muito"),
        lambda: mat.aco("ASTM A999"),
    ):
        try:
            chamada()
        except ErroDeDados:
            continue
        raise AssertionError("deveria ter levantado ErroDeDados")


def test_unidades_e_conversoes():
    """Dimensões do catálogo em mm; propriedades e cálculo em cm."""
    p = perfil("W 360×51,0")
    assert p.d == 355.0 and p.tw == 7.2          # mm
    perto(p.Aw, 35.5 * 0.72, tol=1e-9, o="Aw em cm²")
    v = n.cisalhamento(p, A572)
    perto(v.Rd, 0.60 * 35.5 * 0.72 * 34.5 / 1.10, tol=1e-9, o="VRd em kN")
    r = n.flexao(p, A572, Lb=0.0)
    perto(r.dados["Mpl"], 899.0 * 34.5, tol=1e-9, o="Mpl em kN·cm")


if __name__ == "__main__":
    falhas = 0
    for nome, func in sorted(list(globals().items())):
        if nome.startswith("test_") and callable(func):
            try:
                func()
                print(f"ok   {nome}")
            except Exception as exc:                     # noqa: BLE001
                falhas += 1
                print(f"FALHA {nome}: {exc}")
    print(f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)
