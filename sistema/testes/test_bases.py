# -*- coding: utf-8 -*-
"""Validação de `nucleo.bases` contra o capítulo 10 do manual.

Tolerância padrão de 1 % (GUIA_SISTEMA.md). Cada teste cita o item ou o exemplo
que reproduz.

Roda com:
    PYTHONIOENCODING=utf-8 python -m pytest testes/test_bases.py -q
    PYTHONIOENCODING=utf-8 python testes/test_bases.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from nucleo import bases
from nucleo import ligacoes as lig
from nucleo import materiais as mat
from nucleo.base import ErroDeDados, GAMA_A1, GAMA_A2, GAMA_C


def perto(obtido, esperado, tol=0.01, msg=""):
    ref = abs(esperado) if esperado else 1.0
    assert abs(obtido - esperado) <= tol * ref, (
        f"{msg}: obtido {obtido:.4f}, manual {esperado:.4f} "
        f"(erro {100*abs(obtido-esperado)/ref:.2f} %)")


# Pilares que não estão no catálogo de perfis são informados por dicionário (mm).
W250x73 = "W 250×73"
W310x79 = {"nome": "W 310×79", "d": 306.0, "bf": 254.0, "tw": 8.8, "tf": 14.6}


# ===========================================================================
# Item 10.4 — pressão de contato no concreto
# ===========================================================================

def test_pressao_concreto_sem_e_com_confinamento():
    """Item 10.4.1 — C25 dá 1,52 kN/cm² sem confinamento e 3,04 kN/cm² no limite."""
    fck = 2.5
    v = bases.pressao_concreto(fck, A1=3600.0, A2=3600.0)
    perto(v.Rd, 1.518, 0.01, "σ_c,Rd sem confinamento (A₂ = A₁)")
    perto(v.Rd * 10, 15.2, 0.01, "em MPa")
    v2 = bases.pressao_concreto(fck, A1=900.0, A2=3600.0)
    perto(v2.Rd, 3.036, 0.01, "σ_c,Rd com √(A₂/A₁) = 2")
    perto(v2.Rd * 10, 30.4, 0.01, "em MPa")
    perto(fck / GAMA_C, 1.786, 0.01, "f_cd de C25")


def test_fator_confinamento_limitado_a_2():
    """Item 10.4.1 — √(A₂/A₁) ≤ 2,0."""
    perto(bases.fator_confinamento(100.0, 10000.0), 2.0, 1e-9, "limite de 2,0")
    perto(bases.fator_confinamento(1600.0, 3600.0), 1.5, 1e-9, "√(3600/1600)")


def test_area_A2_homotetica():
    """Item 10.4.2 — A₂ é homotética e concêntrica, não a área cheia do pedestal.

    Placa 35 × 55 em pedestal 55 × 75: k = mín(55/35 ; 75/55) = 1,364, e NÃO
    √(55·75/(35·55)) = 1,46.
    """
    A2, k = bases.area_A2(35.0, 55.0, 55.0, 75.0)
    perto(k, 1.3636, 0.01, "k homotético")
    perto(A2, 1.3636 ** 2 * 35 * 55, 0.01, "A₂")
    perto(A2, 3580.0, 0.01, "A₂ = 47,7 × 75")
    assert k < math.sqrt(55 * 75 / (35 * 55))      # o erro comum daria 1,46


def test_pressao_concreto_entradas_invalidas():
    """GUIA, princípio 4 — falha explícita."""
    with pytest.raises(ErroDeDados):
        bases.pressao_concreto(25.0, 1600.0, 3600.0)      # f_ck em MPa
    with pytest.raises(ErroDeDados):
        bases.pressao_concreto(2.5, 1600.0, 900.0)        # A₂ < A₁
    with pytest.raises(ErroDeDados):
        bases.area_A2(60.0, 60.0, 50.0, 50.0)             # placa maior que o pedestal


# ===========================================================================
# Item 10.5 — Tabela 10.3: espessura pelo modelo dos balanços
# ===========================================================================

TABELA_10_3 = {
    # ℓ (cm): espessuras em mm para σ = 0,40 / 0,60 / 0,80 / 1,00 / 1,50 / 2,00
    5:  (9.4, 11.5, 13.3, 14.8, 18.2, 21.0),
    6:  (11.3, 13.8, 15.9, 17.8, 21.8, 25.2),
    8:  (15.0, 18.4, 21.2, 23.7, 29.1, 33.6),
    10: (18.8, 23.0, 26.5, 29.7, 36.3, 42.0),
    12: (22.5, 27.6, 31.8, 35.6, 43.6, 50.3),
    15: (28.1, 34.5, 39.8, 44.5, 54.5, 62.9),
}
SIGMAS_10_3 = [0.40, 0.60, 0.80, 1.00, 1.50, 2.00]


@pytest.mark.parametrize("ell,linha", sorted(TABELA_10_3.items()))
def test_tabela_10_3_espessura(ell, linha):
    """Cap. 10, Tabela 10.3 — t = ℓ·√(2σ·γ_a1/f_y) em A36, célula a célula."""
    for sigma, esperado in zip(SIGMAS_10_3, linha):
        t = bases.espessura_placa(float(ell), sigma, 25.0)
        perto(t * 10, esperado, 0.01, f"t (ℓ={ell} cm, σ={sigma})")


def test_formula_simplificada_da_espessura():
    """Item 10.5.2 — t ≥ 0,297·ℓ·√σ em A36 e 0,253·ℓ·√σ em A572 Gr.50."""
    perto(math.sqrt(2 * 1.10 / 25.0), 0.2966, 0.01, "coeficiente A36")
    perto(math.sqrt(2 * 1.10 / 34.5), 0.2525, 0.01, "coeficiente A572 Gr.50")
    perto(bases.espessura_placa(10.0, 1.00, 34.5) /
          bases.espessura_placa(10.0, 1.00, 25.0), 0.851, 0.01,
          "A572 dá ≈ 15 % menos espessura")


def test_espessura_por_momento_equivale_a_espessura_placa():
    """As duas escritas (por σ e por M) têm de coincidir."""
    sigma, ell = 0.375, 9.84
    M = sigma * ell ** 2 / 2
    perto(bases.espessura_por_momento(M, 25.0),
          bases.espessura_placa(ell, sigma, 25.0), 1e-9, "equivalência")


# ===========================================================================
# Exemplo 10.1 — base rotulada W 250×73, N = 600 kN, C25, pedestal 60 × 60
# ===========================================================================

class TestExemplo101:
    """Cap. 10, Exemplo 10.1 → placa 400 × 400 × 19 mm."""

    def base(self, B=None, L=None):
        return bases.placa_base_centrada(
            W250x73, N_Sd=600.0, fck=2.5, pedestal=(60.0, 60.0),
            aco_placa="ASTM A36", B=B, L=L, diametro_chumbador='3/4"',
            borda_chumbador=5.0)

    def test_passo1_area_necessaria(self):
        """A₁,nec = 600/3,036 = 197,6 cm² — menor que o próprio perfil."""
        r = self.base(40.0, 40.0)
        perto(r.dados["A1_necessaria"], 197.6, 0.01, "A₁ necessária")
        assert r.dados["A1_necessaria"] < 25.3 * 25.4   # a geometria é que governa

    def test_passo3_pressao_com_A2_real(self):
        """k = 1,500 ; σ_c,Rd = 2,277 kN/cm² ; σ_Sd = 0,375 (16,5 %)."""
        r = self.base(40.0, 40.0)
        perto(r.dados["k"], 1.500, 0.01, "√(A₂/A₁)")
        perto(r.dados["A2"], 3600.0, 0.01, "A₂")
        perto(r.dados["sigma_c_Rd"], 2.277, 0.01, "σ_c,Rd")
        perto(r.dados["sigma_Sd"], 0.375, 0.01, "σ_Sd")
        v = r.verificacoes[0]
        perto(v.razao, 0.165, 0.02, "utilização do concreto")

    def test_passo4_vaos_dos_balancos(self):
        """m = 7,98 ; n = 9,84 ; n′ = 6,34 ; X = 0,1647 ; λ = 0,424 ; ℓ = 9,84 cm."""
        r = self.base(40.0, 40.0)
        perto(r.dados["m"], 7.98, 0.01, "m")
        perto(r.dados["n"], 9.84, 0.01, "n")
        perto(r.dados["n_linha"], 6.34, 0.01, "n′")
        perto(r.dados["X"], 0.1647, 0.01, "X")
        perto(r.dados["lambda"], 0.424, 0.01, "λ")
        perto(r.dados["l_balanco"], 2.69, 0.02, "λ·n′")
        perto(r.dados["ell"], 9.84, 0.01, "ℓ = máx(m ; n ; λ·n′)")

    def test_passo5_espessura(self):
        """t ≥ 1,788 cm = 17,9 mm → chapa comercial de 19 mm; utilização 89 %."""
        r = self.base(40.0, 40.0)
        perto(r.dados["t_necessaria_mm"], 17.9, 0.01, "t necessária")
        perto(r.dados["t_mm"], 19.0, 0.001, "chapa comercial adotada")
        v = [x for x in r.verificacoes if "Flexão da placa" in x.titulo][0]
        perto(v.Sd, 18.15, 0.01, "M_Sd por cm")
        perto(v.Rd, 20.51, 0.01, "M_Rd por cm")
        perto(v.razao, 0.89, 0.02, "utilização da placa")
        perto(r.dados["peso_kg"], 23.9, 0.02, "peso da placa")

    def test_dimensionamento_automatico_da_placa(self):
        """Sem impor B e L, o roteiro do item 10.4.3 chega à mesma placa 400×400×19."""
        r = self.base()
        assert r.dados["dimensionamento_automatico"]
        perto(r.dados["B"], 40.0, 0.001, "B automático")
        perto(r.dados["L"], 40.0, 0.001, "L automático")
        perto(r.dados["t_mm"], 19.0, 0.001, "espessura automática")
        assert r.ok, r.resumo()

    def test_passo6_solda_pilar_placa(self):
        """Filete 6 mm E70 em ≈ 146 cm de contorno resiste a ≈ 1 200 kN ≫ 25 kN.

        O contorno do W 250×73 são 4 cordões de 25,4 cm (mesas) e 2 de 22,5 cm
        (alma). Cada cordão é curto (L/b < 100), de modo que não há redução de
        cordão longo — se o contorno fosse tratado como um único cordão de 146 cm,
        L/b = 243 e β = 0,71 reduziria indevidamente a resistência.
        """
        v_mesas = lig.filete(0.6, 25.4, "E70XX", 25.0, n_cordoes=4)
        v_alma = lig.filete(0.6, 22.5, "E70XX", 25.0, n_cordoes=2)
        perto(v_mesas.Rd + v_alma.Rd, 1199.0, 0.01, "solda de contorno")
        assert v_mesas.Rd + v_alma.Rd >= 25.0
        _, _, r = lig.resistencia_filete_cm(0.6, "E70XX", 25.0)
        perto(r, 8.18, 0.01, "≈ 8,2 kN/cm do filete de 6 mm")

    def test_passo7_chumbadores(self):
        """2 ø 3/4\" F1554 Gr.36: F_t,Rd = 63,3 kN cada (126,7 no par)."""
        v = lig.tracao_parafuso('3/4"', "ASTM F1554 Gr.36")
        perto(v.Rd, 63.3, 0.01, "F_t,Rd por chumbador")
        perto(2 * v.Rd, 126.7, 0.01, "capacidade do par")
        # furo e arruela da Tabela 10.2
        furo, lado, esp = bases.FUROS_PLACA_BASE['3/4"']
        perto(furo, 33.0, 0.001, "furo da placa")
        perto(lado, 50.0, 0.001, "arruela de chapa")
        # embutimento 12d a 17d
        _, d, _, _ = lig._diam('3/4"')
        perto(12 * d * 10, 229.0, 0.01, "12·d")
        perto(17 * d * 10, 324.0, 0.01, "17·d")

    def test_passo7_sem_tracao_na_combinacao_critica(self):
        """Com N_Sd,mín = 90 kN de compressão ainda não há tração nos chumbadores."""
        r = bases.chumbadores(T_Sd=0.0, V_Sd=0.0, N_Sd=90.0, diametro='3/4"',
                              aco="ASTM F1554 Gr.36", n=2, n_tracionados=2,
                              fck=2.5, h_ef=35.0, espacamento=30.0, borda=15.0)
        v = [x for x in r.verificacoes if "Tração do parafuso" in x.titulo][0]
        assert v.Sd == 0.0 and v.ok

    def test_passo8_atrito_com_a_menor_compressao(self):
        """H_Rd = 0,40 · 90 = 36,0 kN ≥ 25 kN (69 %) — e não 0,40 · 600."""
        r = bases.transferencia_horizontal(H_Sd=25.0, N_Sd_min=90.0, mu=0.40,
                                           diametro_chumbador='3/4"',
                                           n_chumbadores=2, B_placa=40.0)
        assert r.dados["mecanismo"] == "atrito"
        perto(r.dados["H_Rd_atrito"], 36.0, 0.001, "atrito com N mínimo")
        v = [x for x in r.verificacoes if "atrito" in x.titulo][0]
        perto(v.razao, 0.694, 0.02, "utilização do atrito")
        # a reserva dos chumbadores não se soma
        perto(r.dados["H_Rd_chumbadores"], 67.6, 0.01, "2 × F_v,Rd (não somável)")

    def test_ancoragem_por_aderencia_assusta(self):
        """Tabela 10.7 — ø 1\" em C25, barra lisa: l_b ≈ 112 cm = 44·d."""
        _, d1, _, _ = lig._diam('1"')
        ad = bases.comprimento_aderencia(2.5, d1, fy=25.0, eta1=1.0)
        perto(ad["fctd_MPa"], 1.283, 0.01, "f_ctd de C25")
        perto(ad["lb"], 112.0, 0.02, "l_b barra lisa")
        perto(ad["lb_em_diametros"], 44.0, 0.02, "em diâmetros")
        ad14 = bases.comprimento_aderencia(2.5, d1, fy=25.0, eta1=1.4)
        perto(ad14["lb"], 80.0, 0.02, "l_b barra entalhada")
        ad225 = bases.comprimento_aderencia(2.5, d1, fy=25.0, eta1=2.25)
        perto(ad225["lb"], 50.0, 0.02, "l_b barra nervurada (CA-50)")


# ===========================================================================
# Exemplo 10.2 — base engastada W 310×79, N = 300 kN, M = 60 kN·m
# ===========================================================================

class TestExemplo102:
    """Cap. 10, Exemplo 10.2 — placa 350 × 550, 4 ø 1\", pedestal 55 × 75."""

    B, L, f = 35.0, 55.0, 23.5
    PEDESTAL = (55.0, 75.0)

    def comb1(self):
        """N = 300 kN com M = 6 000 kN·cm — governa o concreto e a espessura."""
        return bases.placa_base_com_momento(
            W310x79, N_Sd=300.0, M_Sd=6000.0, B=self.B, L=self.L,
            f_chumbador=self.f, fck=2.5, pedestal=self.PEDESTAL,
            aco_placa="ASTM A36", n_chumbadores_tracionados=2)

    def comb2(self):
        """N = 40 kN com M = 6 000 kN·cm — governa a tração no chumbador."""
        return bases.placa_base_com_momento(
            W310x79, N_Sd=40.0, M_Sd=6000.0, B=self.B, L=self.L,
            f_chumbador=self.f, fck=2.5, pedestal=self.PEDESTAL,
            aco_placa="ASTM A36", n_chumbadores_tracionados=2)

    def test_passo1_pressao_resistente(self):
        """k = 1,364 (governa o lado maior) → σ_c,Rd = 2,070 kN/cm²."""
        r = self.comb1()
        perto(r.dados["sigma_c_Rd"], 2.070, 0.01, "σ_c,Rd")
        A2, k = bases.area_A2(self.B, self.L, *self.PEDESTAL)
        perto(k, 1.364, 0.01, "k")

    def test_passo2_regime_e_pressao(self):
        """e = 20 cm, L/6 < e < L/2 → T = 0, Y = 22,5 cm, σ_máx = 0,762 kN/cm²."""
        r = self.comb1()
        perto(r.dados["e"], 20.0, 0.001, "excentricidade")
        perto(r.dados["nucleo_central"], 9.167, 0.01, "L/6")
        assert r.dados["T"] == 0.0
        perto(r.dados["Y"], 22.5, 0.001, "comprimento comprimido")
        perto(r.dados["sigma_max"], 0.762, 0.01, "σ_máx")
        perto(r.dados["sigma_max"] * 10, 7.62, 0.01, "σ_máx em MPa")
        v = r.verificacoes[0]
        perto(v.razao, 0.368, 0.02, "utilização do concreto")

    def test_passo3_espessura_lado_comprimido(self):
        """m = 12,97 ; n = 7,34 ; M_Sd = 51,7 kN·cm/cm ; t = 30,2 mm → 31,5 mm."""
        r = self.comb1()
        perto(r.dados["m"], 12.97, 0.01, "m")
        perto(r.dados["n"], 7.34, 0.01, "n")
        v = [x for x in r.verificacoes if "balanço comprimido" in x.titulo][0]
        perto(v.Sd, 51.7, 0.01, "M_Sd exato (pressão triangular)")
        perto(r.dados["t_comprimido_mm"], 30.2, 0.01, "t necessária")
        perto(r.dados["t_mm"], 31.5, 0.001, "chapa comercial (1 1/4\")")

    def test_passo3_pressao_uniforme_seria_24_por_cento_maior(self):
        """Nota do Passo 3 — com σ_máx uniforme o momento daria 64,0 (+24 %)."""
        sig, m = 0.762, 12.965
        perto(sig * m ** 2 / 2, 64.0, 0.01, "com σ uniforme")
        exato = sig * (m ** 2 / 2 - m ** 3 / (6 * 22.5))
        perto(64.0 / exato - 1, 0.24, 0.05, "acréscimo de 24 %")

    def test_passo4_tracao_pelo_metodo_do_binario(self):
        """x_C = 12,93 ; d′ = 38,07 ; C = 182,3 ; T = 142,3 kN (71,1 por chumbador)."""
        r = self.comb2()
        perto(r.dados["e"], 150.0, 0.001, "e = 6 000/40")
        assert r.dados["regime"].startswith("e ≥ L/2")
        perto(r.dados["x_C"], 12.93, 0.01, "centro da mesa comprimida")
        perto(r.dados["d_linha"], 38.07, 0.01, "braço do binário d′")
        perto(r.dados["C"], 182.3, 0.01, "compressão C")
        perto(r.dados["T"], 142.3, 0.01, "tração total T")
        perto(r.dados["T_por_chumbador"], 71.1, 0.01, "T por chumbador")

    def test_passo4_conferencia_pelo_modelo_triangular(self):
        """q = 72,44 ; Y² − 153·Y + 574,8 = 0 → Y = 3,86 ; C = 139,6 ; T = 99,6 kN."""
        r = self.comb2()
        tri = r.dados["modelo_triangular"]
        perto(tri["q"], 72.44, 0.01, "q = σ_c,Rd·B")
        perto(6 * (6000 + 40 * 23.5) / tri["q"], 574.8, 0.01, "termo independente")
        perto(tri["Y"], 3.86, 0.01, "Y (menor raiz)")
        perto(tri["C"], 139.6, 0.01, "C pelo triangular")
        perto(tri["T"], 99.6, 0.01, "T pelo triangular")
        # o binário dá 43 % mais tração
        perto(r.dados["T"] / tri["T"] - 1, 0.43, 0.05, "o binário é 43 % maior")

    def test_passo5_chumbadores_1_polegada(self):
        """F_t,Rd = 112,6 kN ≥ 71,1 kN (63 %); Gr.55 daria 145,5 kN."""
        v36 = lig.tracao_parafuso('1"', "ASTM F1554 Gr.36")
        perto(v36.Rd, 112.6, 0.01, "F_t,Rd Gr.36")
        perto(71.1 / v36.Rd, 0.63, 0.02, "utilização")
        v55 = lig.tracao_parafuso('1"', "ASTM F1554 Gr.55")
        perto(v55.Rd, 145.5, 0.01, "F_t,Rd Gr.55")
        # Tabela 10.6 — corte
        perto(lig.cisalhamento_parafuso('1"', "ASTM F1554 Gr.36").Rd, 60.1, 0.01,
              "F_v,Rd Gr.36")

    def test_passo5_comprimento_comprimido_equivalente(self):
        """Y_eq = 2·C/(σ_c,Rd·B) = 5,0 cm — cabe sob a mesa."""
        r = self.comb2()
        perto(r.dados["Y_equivalente"], 5.0, 0.02, "Y equivalente")

    def test_passo6_espessura_pelo_lado_tracionado(self):
        """Braço 8,97 cm; M = 36,5 kN·cm/cm; t = 25,3 mm — o comprimido governa."""
        r = self.comb2()
        perto(r.dados["braco_tracionado"], 8.97, 0.01, "braço do chumbador")
        perto(r.dados["M_tracionado"], 36.5, 0.01, "M por cm")
        perto(r.dados["t_tracionado_mm"], 25.3, 0.01, "t pelo lado tracionado")
        assert r.dados["t_tracionado_mm"] < 30.2

    def test_passo7_cone_de_arrancamento(self):
        """N_b = 477 kN isolado, mas ψ_ed = 0,76 e os cones se sobrepõem.

        Divergência conhecida: o manual informa A_Nc/A_Nco = 0,246 (→ N_cbg ≈ 89 kN
        característico e ≈ 63 kN de cálculo). A área projetada calculada a partir da
        geometria declarada (pedestal 55 × 75, h_ef = 45 cm, chumbadores a 20 cm um
        do outro e a 14 cm da borda) é A_Nc = 55 × 75 = 4 125 cm², razão 0,226 —
        8 % menor. A conclusão é a mesma: o concreto simples não ancora a base.
        """
        r = bases.chumbadores(T_Sd=142.3, V_Sd=0.0, N_Sd=40.0, diametro='1"',
                              aco="ASTM F1554 Gr.36", n=4, n_tracionados=2,
                              fck=2.5, h_ef=45.0, espacamento=20.0,
                              borda=14.0, borda_oposta=61.0,
                              borda_lateral=17.5, borda_lateral_oposta=17.5)
        cone = r.dados["cone"]
        perto(cone["Nb"], 477.0, 0.01, "N_b do chumbador isolado")
        perto(cone["psi_ed"], 0.762, 0.01, "ψ_ed")
        perto(cone["ANco"], 18225.0, 0.001, "A_Nco = 9·h_ef²")
        assert cone["sobreposicao"], "os cones se sobrepõem (s = 20 < 3·h_ef = 135)"
        assert cone["cortado_pela_borda"], "o cone é cortado pela borda do pedestal"
        # conclusão do manual
        assert cone["Ncbg_Rd"] < 142.3
        v = [x for x in r.verificacoes if "cone de concreto" in x.titulo][0]
        assert not v.ok
        assert "armadura de suspensão" in v.observacao
        # a razão calculada, para registro
        perto(cone["razao"], 4125.0 / 18225.0, 0.01, "A_Nc/A_Nco calculado")

    def test_passo6_balanco_comprimido_na_combinacao_de_succao(self):
        """Com tração nos chumbadores, o balanço comprimido usa o Y do triangular.

        O método do binário concentra C no centro da mesa comprimida — a rigor não
        sobra balanço comprimido nenhum. Quem dá o diagrama de pressões (e, com ele,
        a flexão da placa do lado comprimido) é o modelo triangular com o concreto
        no limite: Y = 3,86 cm e C = 139,6 kN. Misturar os dois modelos produziria
        uma espessura fictícia. A combinação 2 chega então aos mesmos 31,5 mm da
        combinação 1, confirmando a conclusão do manual.
        """
        r = self.comb2()
        perto(r.dados["Y"], 3.86, 0.01, "Y do modelo triangular")
        perto(r.dados["Y_equivalente"], 5.0, 0.02, "Y_eq do binário (conferência)")
        perto(r.dados["t_mm"], 31.5, 0.001, "mesma chapa da combinação 1")
        assert r.dados["t_comprimido_mm"] > r.dados["t_tracionado_mm"]

    def test_resultado_final(self):
        """Resultado — placa 350 × 550 × 31,5 mm (47,6 kg)."""
        r = self.comb1()
        perto(r.dados["t_mm"], 31.5, 0.001, "espessura")
        perto(r.dados["peso_kg"], 47.6, 0.02, "peso da placa")
        assert r.ok, r.resumo()


# ===========================================================================
# Exemplo 10.3 — transferência horizontal: H = 150 kN, N = 80 kN
# ===========================================================================

class TestExemplo103:
    """Cap. 10, Exemplo 10.3 — placa 450 × 450, C25, grout 30 mm, pedestal 700 × 700."""

    def resultado(self):
        return bases.transferencia_horizontal(
            H_Sd=150.0, N_Sd_min=80.0, mu=0.40, diametro_chumbador='3/4"',
            aco_chumbador="ASTM F1554 Gr.36", n_chumbadores=4,
            arruelas_soldadas=False, B_placa=45.0, fck=2.5, t_grout=3.0,
            aco_chave="ASTM A36", eletrodo="E70XX",
            lado_pedestal=70.0)

    def test_passo1_o_atrito_nao_basta(self):
        """μ = 0,40 · 80 = 32,0 kN — 21 % de 150 kN."""
        r = self.resultado()
        perto(r.dados["H_Rd_atrito"], 32.0, 0.001, "atrito")
        perto(32.0 / 150.0, 0.213, 0.02, "21 % de H_Sd")
        perto(0.55 * 80.0, 44.0, 0.001, "mesmo com μ = 0,55")
        v = [x for x in r.verificacoes if "atrito" in x.titulo][0]
        assert v.dispensada and "descartado" in v.observacao

    def test_passo2_chumbadores_nao_resolvem(self):
        """4 × 33,8 = 135,1 kN < 150 kN; e 4 × ø 1\" daria 240 kN, mas com folga de 21 mm."""
        r = self.resultado()
        perto(r.dados["H_Rd_chumbadores"], 135.1, 0.01, "4 × ø 3/4\" Gr.36")
        perto(lig.cisalhamento_parafuso('3/4"', "ASTM F1554 Gr.36").Rd, 33.8, 0.01,
              "F_v,Rd por chumbador")
        perto(4 * lig.cisalhamento_parafuso('1"', "ASTM F1554 Gr.36").Rd, 240.0,
              0.01, "4 × ø 1\"")
        v = [x for x in r.verificacoes if "chumbadores" in x.titulo][0]
        assert v.dispensada and "arruelas de chapa forem soldadas" in v.observacao
        assert r.dados["mecanismo"] == "chave de cisalhamento"

    def test_passo3_pressao_da_chave_no_concreto(self):
        """σ_Rd = 1,518 ; A_nec = 98,8 cm² ; chave 40 × 8 → σ = 0,469 (31 %)."""
        r = self.resultado()
        perto(r.dados["sigma_Rd_chave"], 1.518, 0.01, "σ_Rd sem confinamento")
        perto(r.dados["A_necessaria_chave"], 98.8, 0.01, "área necessária")
        perto(r.dados["w_chave"], 40.0, 0.001, "largura da chave")
        perto(r.dados["h_emb"], 8.0, 0.001, "altura embutida")
        perto(r.dados["sigma_chave"], 0.469, 0.01, "pressão de cálculo")
        perto(r.dados["sigma_chave"] * 10, 4.7, 0.01, "em MPa")
        v = [x for x in r.verificacoes if "apoio no concreto" in x.titulo][0]
        perto(v.razao, 0.309, 0.03, "utilização de 31 %")

    def test_passo4_espessura_da_chave(self):
        """M_Sd = 150 · 7,0 = 1 050 kN·cm; t = 21,5 mm → chapa de 25,4 mm.

        Divergência de arredondamento do manual: ele calcula Z com t = 2,5 cm
        (Z = 62,5 cm³, M_Rd = 1 420 kN·cm) embora a chapa adotada seja de 1" =
        25,4 mm. Com a espessura correta, Z = 40 · 2,54²/4 = 64,52 cm³ e
        M_Rd = 1 466 kN·cm (utilização 72 % em vez dos 74 % do manual). No mesmo
        exemplo o manual usa 2,54 cm no cisalhamento da chapa (V_Rd = 1 385 kN),
        o que confirma o lapso.
        """
        r = self.resultado()
        perto(r.dados["M_chave"], 1050.0, 0.001, "momento na chave")
        perto(r.dados["t_chave_necessaria_mm"], 21.5, 0.02, "espessura necessária")
        perto(r.dados["t_chave_mm"], 25.4, 0.001, "chapa adotada (1\")")
        # a tentativa de 22,4 mm do manual: utilização 92 % — apertado
        M_Rd_224 = (40 * 2.24 ** 2 / 4) * 25.0 / GAMA_A1
        perto(M_Rd_224, 1140.0, 0.01, "M_Rd com 22,4 mm")
        perto(1050.0 / M_Rd_224, 0.92, 0.02, "utilização de 92 %")
        # com 25,4 mm (valor correto, não os 2,5 cm do manual)
        v = [x for x in r.verificacoes if "flexão da chapa" in x.titulo][0]
        perto(v.Rd, (40 * 2.54 ** 2 / 4) * 25.0 / GAMA_A1, 0.001, "M_Rd com 25,4 mm")
        perto(v.Rd, 1466.0, 0.01, "M_Rd correto")
        assert abs(v.Rd - 1420.0) / 1420.0 > 0.01, (
            "divergência de arredondamento do manual, documentada no docstring")

    def test_passo4_cisalhamento_da_chapa_nunca_governa(self):
        """V_Rd = 0,6 · 25 · (40 · 2,54)/1,10 = 1 385 kN ≫ 150 kN."""
        r = self.resultado()
        v = [x for x in r.verificacoes if "cisalhamento da chapa" in x.titulo][0]
        perto(v.Rd, 1385.0, 0.01, "V_Rd da chave")
        assert v.razao < 0.15

    def test_passo5_solda_da_chave(self):
        """f_M = 10,33 ; f_V = 1,88 ; f = 10,50 kN/cm → filete de 8 mm.

        O manual usa S = 100 cm² (t = 2,5 cm) e chega a f = 10,67 kN/cm; com
        t = 2,54 cm, S = 101,6 cm² e f = 10,50 kN/cm. A perna necessária é
        0,69 cm contra 0,70 cm — o filete de 8 mm é o mesmo.
        """
        r = self.resultado()
        S = 2 * 40.0 * (2.54 / 2)
        f_M = 1050.0 / S
        f_V = 150.0 / (2 * 40.0)
        f = math.hypot(f_M, f_V)
        perto(f_V, 1.88, 0.01, "força por cm do cortante")
        perto(f, 10.50, 0.01, "resultante")
        perto(0.6 * 48.5 * 0.707 / 1.35, 15.24, 0.01, "kN/cm por cm de perna E70")
        perto(f / 15.24, 0.689, 0.01, "perna necessária")
        perto(r.dados["perna_solda_chave_mm"], 8.0, 0.001, "filete adotado")

    def test_passo6_detalhes_de_execucao(self):
        """Rasgo 20 a 30 mm maior em cada direção; ≥ 150 mm de concreto à frente."""
        r = self.resultado()
        perto(r.dados["altura_total_chave_mm"], 110.0, 0.001, "altura total da chapa")
        rw, rh = r.dados["rasgo_mm"]
        perto(rw, 440.0, 0.001, "largura do rasgo")
        perto(rh, 140.0, 0.001, "altura do rasgo")
        v = [x for x in r.verificacoes if "Concreto à frente" in x.titulo][0]
        perto(v.Rd, 15.0, 0.001, "(70 − 40)/2 = 15 cm de concreto à frente")
        assert v.ok

    def test_mecanismos_nao_se_somam(self):
        """Item 10.10 — atrito + chumbador + chave não somam; escolhe-se um."""
        r = self.resultado()
        ativos = [v for v in r.verificacoes if not v.dispensada]
        titulos = " ".join(v.titulo for v in ativos)
        assert "atrito" not in titulos and "cisalhamento nos chumbadores" not in titulos
        assert r.dados["mecanismo"] == "chave de cisalhamento"


# ===========================================================================
# Orquestrador e coerência geral
# ===========================================================================

def test_dimensionar_base_rotulada_completa():
    """O orquestrador reproduz o Exemplo 10.1 e entrega geometria e material."""
    r = bases.dimensionar_base(W250x73, N_Sd=600.0, H_Sd=25.0, N_Sd_min=90.0,
                               fck=2.5, pedestal=(60.0, 60.0),
                               diametro_chumbador='3/4"', n_chumbadores=2,
                               h_ef=35.0, t_grout=3.0)
    assert r.ok, r.resumo()
    perto(r.dados["B"], 40.0, 0.001, "B")
    perto(r.dados["L"], 40.0, 0.001, "L")
    perto(r.dados["t_mm"], 19.0, 0.001, "espessura")
    assert r.dados["transferencia_horizontal"]["mecanismo"] == "atrito"
    g = r.dados["geometria"]
    assert g["B_mm"] == 400.0 and g["L_mm"] == 400.0 and g["t_mm"] == 19.0
    assert g["grout_mm"] == 30.0 and g["h_ef_mm"] == 350.0
    itens = {m["peca"] for m in r.dados["lista_material"]}
    assert {"placa de base", "chumbador", "arruela de chapa", "grout"} <= itens


def test_dimensionar_base_engastada_com_chave():
    """Base engastada com H grande: o orquestrador escolhe a chave de cisalhamento."""
    r = bases.dimensionar_base(W310x79, N_Sd=300.0, M_Sd=6000.0, H_Sd=150.0,
                               N_Sd_min=40.0, fck=2.5, pedestal=(70.0, 90.0),
                               diametro_chumbador='1"', n_chumbadores=4,
                               B=35.0, L=55.0, f_chumbador=23.5, h_ef=45.0)
    tr = r.dados["transferencia_horizontal"]
    assert tr["mecanismo"] == "chave de cisalhamento"
    assert any("chave de cisalhamento" in m["peca"]
               for m in r.dados["lista_material"])
    # a tração do binário é levada aos chumbadores
    perto(r.dados["T"], 142.3, 0.02, "tração do binário (combinação de sucção)")


def test_chapa_comercial():
    """Tabela 10.4 — a espessura sobe para a chapa comercial imediatamente acima."""
    perto(bases.chapa_comercial(1.788), 1.90, 0.001, "17,9 mm → 19 mm")
    perto(bases.chapa_comercial(3.02), 3.15, 0.001, "30,2 mm → 31,5 mm")
    perto(bases.chapa_comercial(0.5), 1.27, 0.001, "mínimo prático de 12,7 mm")
    perto(bases.chapa_comercial(0.5, minimo=bases.ESPESSURA_MINIMA_ENGASTADA), 1.60,
          0.001, "mínimo de base engastada")
    with pytest.raises(ErroDeDados):
        bases.chapa_comercial(10.0)


def test_memoria_de_calculo_presente():
    """GUIA, princípio 2 — toda verificação com passos e citação de norma."""
    r = bases.placa_base_centrada(W250x73, 600.0, 2.5, (60.0, 60.0))
    for v in r.verificacoes:
        if v.dispensada:
            continue
        assert v.passos, f"{v.titulo} sem memória de cálculo"
        assert v.norma, f"{v.titulo} sem norma"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
