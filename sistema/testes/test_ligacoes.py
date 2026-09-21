# -*- coding: utf-8 -*-
"""Validação de `nucleo.ligacoes` contra os capítulos 8 e 9 do manual.

Tolerância padrão de 1 % (GUIA_SISTEMA.md). Cada teste cita o capítulo, a tabela
ou o exemplo que reproduz.

Roda com:
    PYTHONIOENCODING=utf-8 python -m pytest testes/test_ligacoes.py -q
    PYTHONIOENCODING=utf-8 python testes/test_ligacoes.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from nucleo import ligacoes as lig
from nucleo import materiais as mat
from nucleo.base import ErroDeDados, GAMA_A1, GAMA_A2


def perto(obtido, esperado, tol=0.01, msg=""):
    """Compara com tolerância relativa de 1 % (padrão do sistema)."""
    ref = abs(esperado) if esperado else 1.0
    assert abs(obtido - esperado) <= tol * ref, (
        f"{msg}: obtido {obtido:.4f}, manual {esperado:.4f} "
        f"(erro {100*abs(obtido-esperado)/ref:.2f} %)")


# ===========================================================================
# Capítulo 8 — Tabela 8.5: protensão mínima (NBR 8800, Tabela 15)
# ===========================================================================

TABELA_8_5 = {
    # diâmetro: (A325, A490)
    '1/2"': (53, 66), '5/8"': (85, 106), '3/4"': (125, 156),
    '7/8"': (173, 218), '1"': (227, 285), '1.1/8"': (250, 356),
    '1.1/4"': (317, 454),
    "M16": (91, 114), "M20": (142, 179), "M22": (176, 221),
    "M24": (205, 257), "M27": (267, 334), "M30": (326, 408),
}


@pytest.mark.parametrize("diam,valores", sorted(TABELA_8_5.items()))
def test_tabela_8_5_protensao(diam, valores):
    """Cap. 8, Tabela 8.5 — protensão mínima F_Tb de A325 e A490."""
    a325, a490 = valores
    perto(mat.PROTENSAO["ASTM A325"][diam], a325, 0.01, f"F_Tb A325 {diam}")
    perto(mat.PROTENSAO["ASTM A490"][diam], a490, 0.01, f"F_Tb A490 {diam}")


# ===========================================================================
# Capítulo 8 — Tabela 8.6: resistências por parafuso
# ===========================================================================

# diâmetro: (Ab, A307 Fv, A307 Ft,
#            A325 Fv rosca no plano, A325 Fv rosca fora, A325 Ft,
#            A490 Fv rosca no plano, A490 Fv rosca fora, A490 Ft)
TABELA_8_6 = {
    '1/2"':  (1.27, 15.6, 29.2, 31.0, 38.7, 58.1, 38.8, 48.6, 72.8),
    '5/8"':  (1.98, 24.3, 45.6, 48.4, 60.5, 90.7, 60.7, 75.9, 113.8),
    '3/4"':  (2.85, 35.0, 65.7, 69.7, 87.1, 130.6, 87.4, 109.3, 163.9),
    '7/8"':  (3.88, 47.7, 89.4, 94.8, 118.5, 177.8, 119.0, 148.7, 223.1),
    '1"':    (5.07, 62.3, 116.8, 108.8, 136.1, 204.1, 155.4, 194.2, 291.4),
    "M12":   (1.13, 13.9, 26.1, 27.6, 34.6, 51.8, 34.7, 43.4, 65.0),
    "M16":   (2.01, 24.7, 46.4, 49.1, 61.4, 92.2, 61.7, 77.1, 115.6),
    "M20":   (3.14, 38.6, 72.4, 76.8, 96.0, 144.0, 96.3, 120.4, 180.6),
    "M24":   (4.52, 55.6, 104.3, 110.6, 138.2, 207.3, 138.7, 173.4, 260.1),
}


@pytest.mark.parametrize("diam,linha", sorted(TABELA_8_6.items()))
def test_tabela_8_6_celula_a_celula(diam, linha):
    """Cap. 8, Tabela 8.6 — resistências de cálculo por parafuso, célula a célula.

    Nota da tabela: para 1" (d > 24 mm) a NBR 8800 adota f_ub = 72,5 kN/cm² no A325.
    """
    Ab, v307, t307, v325r, v325f, t325, v490r, v490f, t490 = linha
    _, d, Ab_calc, _ = lig._diam(diam)
    perto(Ab_calc, Ab, 0.01, f"A_b {diam}")

    perto(lig.cisalhamento_parafuso(diam, "ASTM A307").Rd, v307, 0.01,
          f"F_v,Rd A307 {diam}")
    perto(lig.tracao_parafuso(diam, "ASTM A307").Rd, t307, 0.01,
          f"F_t,Rd A307 {diam}")

    perto(lig.cisalhamento_parafuso(diam, "ASTM A325", rosca_no_plano=True).Rd,
          v325r, 0.01, f"F_v,Rd A325 rosca no plano {diam}")
    perto(lig.cisalhamento_parafuso(diam, "ASTM A325", rosca_no_plano=False).Rd,
          v325f, 0.01, f"F_v,Rd A325 rosca fora {diam}")
    perto(lig.tracao_parafuso(diam, "ASTM A325").Rd, t325, 0.01,
          f"F_t,Rd A325 {diam}")

    perto(lig.cisalhamento_parafuso(diam, "ASTM A490", rosca_no_plano=True).Rd,
          v490r, 0.01, f"F_v,Rd A490 rosca no plano {diam}")
    perto(lig.cisalhamento_parafuso(diam, "ASTM A490", rosca_no_plano=False).Rd,
          v490f, 0.01, f"F_v,Rd A490 rosca fora {diam}")
    perto(lig.tracao_parafuso(diam, "ASTM A490").Rd, t490, 0.01,
          f"F_t,Rd A490 {diam}")


def test_tabela_8_6_a307_ignora_posicao_da_rosca():
    """Cap. 8, item 8.4.2 — o A307 usa sempre 0,4."""
    a = lig.cisalhamento_parafuso('3/4"', "ASTM A307", rosca_no_plano=True)
    b = lig.cisalhamento_parafuso('3/4"', "ASTM A307", rosca_no_plano=False)
    assert a.Rd == pytest.approx(b.Rd)
    assert "sempre o coeficiente 0,4" in b.observacao


def test_tabela_8_6_corte_duplo_dobra():
    """Cap. 8, nota da Tabela 8.6 — corte duplo multiplica F_v,Rd por 2."""
    simples = lig.cisalhamento_parafuso('3/4"', "ASTM A325", planos=1)
    duplo = lig.cisalhamento_parafuso('3/4"', "ASTM A325", planos=2)
    perto(duplo.Rd, 2 * simples.Rd, 1e-9, "corte duplo")
    perto(duplo.Rd, 139.3, 0.01, "3/4\" A325 corte duplo (Exemplo 8.1)")


# ===========================================================================
# Capítulo 8 — Tabela 8.7: esmagamento máximo em chapa A36
# ===========================================================================

# diâmetro: (kN por mm de espessura, t=6,3 / 8,0 / 9,5 / 12,5 / 16,0 mm, lf mín mm)
TABELA_8_7 = {
    '1/2"': (9.03, 56.9, 72.2, 85.8, 112.9, 144.5, 25),
    '5/8"': (11.29, 71.1, 90.3, 107.2, 141.1, 180.6, 32),
    '3/4"': (13.55, 85.3, 108.4, 128.7, 169.3, 216.7, 38),
    '7/8"': (15.80, 99.6, 126.4, 150.1, 197.6, 252.9, 44),
    '1"':   (18.06, 113.8, 144.5, 171.6, 225.8, 289.0, 51),
    "M12":  (8.53, 53.8, 68.3, 81.1, 106.7, 136.5, 24),
    "M16":  (11.38, 71.7, 91.0, 108.1, 142.2, 182.0, 32),
    "M20":  (14.22, 89.6, 113.8, 135.1, 177.8, 227.6, 40),
    "M24":  (17.07, 107.5, 136.5, 162.1, 213.3, 273.1, 48),
}
ESPESSURAS_8_7 = [0.63, 0.80, 0.95, 1.25, 1.60]     # cm


@pytest.mark.parametrize("diam,linha", sorted(TABELA_8_7.items()))
def test_tabela_8_7_esmagamento(diam, linha):
    """Cap. 8, Tabela 8.7 — F_c,Rd = 2,4·d·t·f_u/γ_a2 em chapa A36, célula a célula."""
    por_mm, *valores = linha
    lf_min_mm = valores.pop()
    _, d, _, _ = lig._diam(diam)
    fu = mat.aco("ASTM A36").fu

    # kN por mm de espessura
    perto(2.4 * d * 0.1 * fu / GAMA_A2, por_mm, 0.01, f"kN/mm {diam}")

    # cada espessura da tabela, com l_f generoso para atingir o limite superior
    for t, esperado in zip(ESPESSURAS_8_7, valores):
        v = lig.esmagamento(diam, t, fu, distancia_borda=10.0, n_borda=1, n_interno=0)
        perto(v.Rd, esperado, 0.01, f"F_c,Rd {diam} t={t*10:.1f} mm")

    # l_f mínimo para o valor pleno: l_f = 2·d (a tabela arredonda para o mm)
    assert abs(2 * d * 10 - lf_min_mm) <= 0.5, (
        f"l_f mínimo {diam}: obtido {2*d*10:.1f} mm, manual {lf_min_mm} mm")


def test_tabela_8_7_regime_de_rasgamento():
    """Cap. 8, Tabela 8.7, nota — 3,56 kN por mm de espessura e por cm de l_f (A36)."""
    fu = mat.aco("ASTM A36").fu
    # 1,2·l_f·t·f_u/γ_a2 com l_f = 1 cm e t = 1 mm → 3,56 kN
    perto(1.2 * 1.0 * 0.1 * fu / GAMA_A2, 3.56, 0.01, "kN por mm de t e cm de l_f")
    # e o próprio módulo, com l_f pequeno, fica no regime de rasgamento
    dh = lig.furo_padrao(lig._diam('3/4"')[1])
    v = lig.esmagamento('3/4"', 0.8, fu, distancia_borda=dh / 2 + 1.0, n_borda=1)
    perto(v.Rd, 3.56 * 8.0 * 1.0, 0.01, "regime 1,2·l_f·t·f_u")
    # A572 Gr.50 é 1,125 vez o A36
    perto(mat.aco("ASTM A572 Gr.50").fu / fu, 1.125, 0.001, "fator A572/A36")


def test_furo_padrao_e_espacamentos():
    """Cap. 8, itens 8.3.1 a 8.3.3 — furo-padrão, espaçamento e bordas."""
    _, d34, _, _ = lig._diam('3/4"')
    perto(lig.furo_padrao(d34) * 10, 20.55, 0.01, "furo-padrão 3/4\"")
    perto(lig.espacamento_minimo(d34) * 10, 2.7 * 19.05, 0.001, "2,7·d")
    perto(lig.espacamento_recomendado(d34) * 10, 3 * 19.05, 0.001, "3·d")
    # Tabela 8.3 (NBR 8800, Tabela 14)
    e_lam, _ = lig.distancia_borda_minima('3/4"', "laminada")
    e_mac, _ = lig.distancia_borda_minima('3/4"', "maçarico")
    perto(e_lam * 10, 26, 0.001, "borda laminada 3/4\"")
    perto(e_mac * 10, 32, 0.001, "borda a maçarico 3/4\"")
    perto(lig.distancia_borda_minima("M20", "maçarico")[0] * 10, 34, 0.001, "M20")
    # máximos
    perto(lig.distancia_borda_maxima(0.8) * 10, 96, 0.001, "12·t")
    perto(lig.distancia_borda_maxima(2.0) * 10, 150, 0.001, "limite 150 mm")
    perto(lig.espacamento_maximo(0.8) * 10, 192, 0.001, "24·t")
    perto(lig.espacamento_maximo(0.8, patinavel_exposto=True) * 10, 112, 0.001, "14·t")


def test_furos_alargado_e_oblongo():
    """Cap. 8, Tabela 8.2 — dimensões dos furos para 3/4\"."""
    _, d, _, _ = lig._diam('3/4"')
    perto(lig.diametro_furo(d, "alargado")[0] * 10, 24.05, 0.01, "alargado 3/4\"")
    larg, comp = lig.diametro_furo(d, "oblongo curto")
    perto(larg * 10, 20.55, 0.01, "oblongo curto largura")
    perto(comp * 10, 25.05, 0.01, "oblongo curto comprimento")
    perto(lig.diametro_furo(d, "oblongo longo")[1] * 10, 2.5 * 19.05, 0.01,
          "oblongo longo 2,5·d")


def test_entrada_inconsistente_levanta_erro():
    """GUIA, princípio 4 — falha explícita com mensagem em português."""
    with pytest.raises(ErroDeDados):
        lig.diametro_furo(1.905, "quadrado")
    with pytest.raises(ErroDeDados):
        # borda menor que o raio do furo
        lig.esmagamento('3/4"', 0.8, 40.0, distancia_borda=0.5)
    with pytest.raises(ErroDeDados):
        lig.bloco_cisalhamento(10, 8, 3, 2, 25, 40, Cts=0.8)
    with pytest.raises(ErroDeDados):
        lig.deslizamento('3/4"', "ASTM A307")


# ===========================================================================
# Capítulo 8 — deslizamento (ligação por atrito)
# ===========================================================================

def test_deslizamento_atrito():
    """Cap. 8, eq. 8.1 — F_f,Rd = 1,13·μ·C_h·F_Tb·n_s/γ."""
    v = lig.deslizamento('3/4"', "ASTM A325", planos=1,
                         superficie="A (jateada, sem pintura)", furo="padrão",
                         estado_limite="serviço")
    esperado = 1.13 * 0.35 * 1.0 * 125 * 1 / 1.20
    perto(v.Rd, esperado, 0.001, "F_f,Rd 3/4\" A325 classe A")
    perto(v.Rd, 41.15, 0.01, "F_f,Rd numérico")
    # furo alargado reduz C_h para 0,85 e o ELU usa γ = 1,35
    v2 = lig.deslizamento('3/4"', "ASTM A325", furo="alargado",
                          estado_limite="último")
    perto(v2.Rd, 1.13 * 0.35 * 0.85 * 125 / 1.35, 0.001, "alargado, ELU")


def test_deslizamento_com_tracao():
    """Cap. 8, item 8.5.4 — tração reduz o atrito por (1 − F_t,Sd/(1,13·F_Tb))."""
    sem = lig.deslizamento('3/4"', "ASTM A325")
    com = lig.deslizamento('3/4"', "ASTM A325", Ft_Sd=50.0)
    perto(com.Rd / sem.Rd, 1 - 50.0 / (1.13 * 125), 0.001, "redução por tração")


# ===========================================================================
# Capítulo 8 — Exemplo 8.1: dupla cantoneira
# ===========================================================================

class TestExemplo81:
    """Cap. 8, Exemplo 8.1 — W 360×51, 2 L 76×76×7,9, 3 ø 3/4\" A325, V_Sd = 120 kN."""

    def liga(self, recorte=False):
        return lig.dupla_cantoneira(
            "W 360×51", V_Sd=120.0, n_parafusos=3, diametro='3/4"',
            parafuso="ASTM A325", t_cantoneira=0.79, aba=7.6, gabarito=4.4,
            passo=7.6, borda_vertical=3.0, dist_extremidade_viga=3.5,
            aco_viga="ASTM A36", aco_cantoneira="ASTM A36",
            rosca_no_plano=True, recorte=recorte, borda_recorte=4.0)

    def test_passo1_parafusos_na_alma_corte_duplo(self):
        """Passo 1 — 3 × 139,3 = 418 kN."""
        r = self.liga()
        v = [x for x in r.verificacoes if "alma da viga (corte duplo)" in x.titulo][0]
        perto(v.Rd, 418.0, 0.01, "3 parafusos em corte duplo")
        assert v.ok and v.razao == pytest.approx(120.0 / v.Rd)

    def test_passo2_parafusos_no_apoio_corte_simples(self):
        """Passo 2 — 6 × 69,7 = 418 kN."""
        r = self.liga()
        v = [x for x in r.verificacoes if "apoio (corte simples)" in x.titulo][0]
        perto(v.Rd, 418.0, 0.01, "6 parafusos em corte simples")

    def test_passo3_esmagamento_na_alma(self):
        """Passo 3 — 63,3 + 2 × 97,5 = 258 kN na alma (t_w = 7,2 mm)."""
        r = self.liga()
        v = [x for x in r.verificacoes if "alma da viga" in x.titulo
             and "Esmagamento" in x.titulo][0]
        perto(v.Rd, 258.0, 0.01, "esmagamento na alma")
        # parcelas
        fu = mat.aco("ASTM A36").fu
        limite = 2.4 * 1.905 * 0.72 * fu / GAMA_A2
        perto(limite, 97.5, 0.01, "limite 2,4·d·t·f_u/γ")
        lf_borda = 3.5 - 2.055 / 2
        perto(1.2 * lf_borda * 0.72 * fu / GAMA_A2, 63.3, 0.015, "furo de extremidade")

    def test_passo4_esmagamento_nas_cantoneiras(self):
        """Passo 4 — 2 × (55,4 + 2 × 107,0) = 539 kN."""
        r = self.liga()
        v = [x for x in r.verificacoes if "cantoneiras" in x.titulo
             and "Esmagamento" in x.titulo][0]
        perto(v.Rd, 539.0, 0.01, "esmagamento nas 2 cantoneiras")

    def test_passo5_bloco_de_cisalhamento_na_cantoneira(self):
        """Passo 5 — 208 kN por cantoneira (escoamento governa), 417 kN no par."""
        r = self.liga()
        perto(r.dados["bloco_cantoneira_por_peca"], 208.0, 0.01,
              "bloco de cisalhamento por cantoneira")
        v = [x for x in r.verificacoes if "Bloco de cisalhamento — cantoneira" in x.titulo][0]
        perto(v.Rd, 417.0, 0.01, "bloco nas 2 cantoneiras")
        assert "escoamento" in v.observacao

    def test_passo5_areas_do_bloco(self):
        """Passo 5 — A_gv = 14,38 ; A_nv = 9,93 ; A_nt = 1,64 cm²."""
        t = 0.79
        Lv = 3.0 + 2 * 7.6
        w = 2.055 + 0.2
        perto(Lv * t, 14.38, 0.01, "A_gv")
        perto((Lv - 2.5 * w) * t, 9.93, 0.01, "A_nv")
        perto((7.6 - 4.4 - w / 2) * t, 1.64, 0.02, "A_nt")

    def test_passo6_bloco_na_alma_com_recorte(self):
        """Passo 6 — com recorte de mesa: 180 kN (escoamento governa)."""
        r = self.liga(recorte=True)
        v = [x for x in r.verificacoes if "alma da viga recortada" in x.titulo][0]
        perto(v.Rd, 180.0, 0.015, "bloco na alma recortada")
        assert v.ok

    def test_passo6_sem_recorte_dispensa(self):
        """Passo 6 — sem recorte não há bloco livre na alma."""
        r = self.liga()
        v = [x for x in r.verificacoes
             if x.titulo == "Bloco de cisalhamento na alma da viga"][0]
        assert v.dispensada and "sem recorte" in v.observacao

    def test_passo7_cisalhamento_das_cantoneiras(self):
        """Passo 7 — bruta 457 kN, líquida 406 kN."""
        r = self.liga()
        v = [x for x in r.verificacoes if x.titulo == "Cisalhamento das cantoneiras"][0]
        perto(v.Rd, 406.0, 0.01, "cisalhamento líquido das cantoneiras")
        ac = mat.aco("ASTM A36")
        perto(2 * 0.6 * ac.fy * (21.2 * 0.79) / GAMA_A1, 457.0, 0.01, "seção bruta")

    def test_conclusao_governa_o_esmagamento_da_alma(self):
        """Conclusão — a ligação passa e o esmagamento da alma governa (46 %)."""
        r = self.liga()
        assert r.ok
        assert "alma da viga" in r.critica.titulo
        perto(r.razao, 120.0 / 258.0, 0.02, "utilização crítica")
        perto(r.dados["comprimento_cantoneira_mm"], 212.0, 0.001, "L da cantoneira")

    def test_passo8_alternativa_soldada(self):
        """Passo 8 — filete 6 mm E70 em A36: ≈ 8,2 kN/cm; 2 × 21,2 cm → 348 kN."""
        r_solda, r_base, r = lig.resistencia_filete_cm(0.6, "E70XX", 25.0)
        perto(r, 8.18, 0.01, "filete 6 mm A36+E70")
        v = lig.filete(0.6, 21.2, "E70XX", 25.0, n_cordoes=2, F_Sd=120.0)
        perto(v.Rd, 347.0, 0.01, "2 cordões de 212 mm")
        assert v.ok


# ===========================================================================
# Capítulo 8 — Exemplo 8.2: emenda de tirante
# ===========================================================================

class TestExemplo82:
    """Cap. 8, Exemplo 8.2 — chapa 120×8, talas 2×(120×6), 4 ø 5/8\", N_Sd = 180 kN."""

    fu = mat.aco("ASTM A36").fu
    fy = mat.aco("ASTM A36").fy

    def test_1_verificacoes_geometricas(self):
        _, d, _, _ = lig._diam('5/8"')
        perto(lig.espacamento_minimo(d) * 10, 43.0, 0.02, "2,7·d")
        perto(lig.distancia_borda_minima('5/8"', "laminada")[0] * 10, 22.0, 0.001,
              "borda serrada mínima")
        assert 3.0 <= lig.distancia_borda_maxima(0.6)

    def test_2_corte_duplo_dos_parafusos(self):
        """48,4 kN/plano → 96,8 por parafuso → 4 × 96,8 = 387 kN."""
        perto(lig.cisalhamento_parafuso('5/8"', "ASTM A325", planos=1).Rd, 48.4,
              0.01, "F_v,Rd por plano")
        perto(lig.cisalhamento_parafuso('5/8"', "ASTM A325", planos=2, n=4).Rd,
              387.0, 0.01, "4 parafusos em corte duplo")

    def test_3_esmagamento_na_chapa_do_tirante(self):
        """2 × 60,6 + 2 × 90,3 = 302 kN; nas talas 453 kN."""
        v = lig.esmagamento('5/8"', 0.8, self.fu, distancia_borda=3.0,
                            espacamento=5.0, n_borda=2, n_interno=2)
        perto(v.Rd, 302.0, 0.01, "esmagamento no tirante")
        v_talas = lig.esmagamento('5/8"', 1.2, self.fu, distancia_borda=3.0,
                                  espacamento=5.0, n_borda=2, n_interno=2)
        perto(v_talas.Rd, 453.0, 0.01, "esmagamento nas talas (2 × 6 mm)")

    def test_4_area_liquida_do_tirante(self):
        """A_n = 6,50 cm² → 192,5 kN (governa); escoamento 218 kN."""
        dh = lig.furo_padrao(lig._diam('5/8"')[1])
        w = lig.largura_desconto_furo(dh)
        perto(w * 10, 19.4, 0.02, "largura de desconto por furo")
        An = (12.0 - 2 * w) * 0.8
        perto(An, 6.50, 0.01, "A_n do tirante")
        perto(An * self.fu / GAMA_A2, 192.5, 0.01, "N_t,Rd ruptura")
        perto(9.6 * self.fy / GAMA_A1, 218.0, 0.01, "N_t,Rd escoamento")
        An_talas = 2 * (12.0 - 2 * w) * 0.6
        perto(An_talas * self.fu / GAMA_A2, 289.0, 0.01, "talas")

    def test_5_bloco_de_cisalhamento_no_tirante(self):
        """R_d = 241 kN ≤ 238 kN → governa o escoamento; ≥ 180 kN."""
        dh = lig.furo_padrao(lig._diam('5/8"')[1])
        w = lig.largura_desconto_furo(dh)
        Agv = 2 * (3.0 + 5.0) * 0.8
        Anv = 2 * (8.0 - 1.5 * w) * 0.8
        Ant = (6.0 - w) * 0.8
        perto(Agv, 12.80, 0.01, "A_gv")
        perto(Anv, 8.14, 0.01, "A_nv")
        perto(Ant, 3.25, 0.01, "A_nt")
        v = lig.bloco_cisalhamento(Agv, Anv, Agv, Ant, self.fy, self.fu, 1.0, Sd=180.0)
        perto(v.Rd, 238.0, 0.01, "bloco de cisalhamento")
        assert v.ok

    def test_conclusao_governa_a_area_liquida(self):
        """Conclusão — governa a ruptura da seção líquida (192,5 kN, 94 %)."""
        dh = lig.furo_padrao(lig._diam('5/8"')[1])
        An = (12.0 - 2 * lig.largura_desconto_furo(dh)) * 0.8
        perto(180.0 / (An * self.fu / GAMA_A2), 0.94, 0.02, "utilização")


# ===========================================================================
# Capítulo 8 — Exemplo 8.3: T-stub e efeito alavanca
# ===========================================================================

class TestExemplo83:
    """Cap. 8, Exemplo 8.3 — pendural em T, 2 ø 3/4\" A325, T_Sd = 100 kN."""

    def test_1_resistencia_do_parafuso_a_tracao(self):
        perto(lig.tracao_parafuso('3/4"', "ASTM A325").Rd, 130.6, 0.01, "F_t,Rd")
        # com 5/8" a folga desapareceria
        perto(lig.tracao_parafuso('5/8"', "ASTM A325").Rd, 90.7, 0.01, "F_t,Rd 5/8\"")

    def test_2_espessura_minima_b_40mm(self):
        """b = 40 mm → b' = 30,5 mm → t_min = 1,83 cm → chapa de 19 mm."""
        _, d, _, _ = lig._diam('3/4"')
        t_min, b_linha = lig.t_stub_espessura_minima(50.0, 4.0, 8.0, 25.0, d)
        perto(b_linha, 3.05, 0.01, "b' = b − d/2")
        perto(t_min, 1.832, 0.01, "t_min")
        assert 1.83 <= t_min * 10 / 10 * 10 <= 19.0

    def test_3_aproximar_os_parafusos_da_alma(self):
        """b = 30 mm → b' = 20,5 mm → t_min = 1,50 cm → chapa de 16 mm."""
        _, d, _, _ = lig._diam('3/4"')
        t_min, b_linha = lig.t_stub_espessura_minima(50.0, 3.0, 8.0, 25.0, d)
        perto(b_linha, 2.05, 0.01, "b'")
        perto(t_min, 1.502, 0.01, "t_min com b = 30 mm")

    def test_alavanca_nula_com_chapa_espessa(self):
        """Com t ≥ t_c o modelo T-stub dá Q = 0 (chapa espessa, Figura 8.21b)."""
        _, d, _, _ = lig._diam('3/4"')
        dh = lig.furo_padrao(d)
        al = lig.forca_alavanca(50.0, 1.90, 4.0, 4.0, 8.0, 25.0, d, dh)
        assert al["Q"] == pytest.approx(0.0)
        assert al["alfa"] == pytest.approx(0.0)

    def test_alavanca_em_chapa_fina(self):
        """Com chapa de 9,5 mm a alavanca é inevitável e fica na faixa 30–60 %."""
        _, d, _, _ = lig._diam('3/4"')
        dh = lig.furo_padrao(d)
        al = lig.forca_alavanca(50.0, 0.95, 4.0, 4.0, 8.0, 25.0, d, dh)
        assert al["alfa"] == pytest.approx(1.0)
        razao = al["Q"] / 50.0
        assert 0.25 <= razao <= 0.60, f"Q/T = {razao:.2f} fora da faixa do manual"


# ===========================================================================
# Capítulo 9 — Tabela 9.5: resistência do filete por cm
# ===========================================================================

# perna mm: (garganta cm, E70, E60, A36, A572-50, A36+E70, A36+E60, A572+E70)
TABELA_9_5 = {
    3:  (0.212, 4.57, 3.91, 4.09, 5.65, 4.09, 3.91, 4.57),
    4:  (0.283, 6.10, 5.22, 5.45, 7.53, 5.45, 5.22, 6.10),
    5:  (0.353, 7.62, 6.52, 6.82, 9.41, 6.82, 6.52, 7.62),
    6:  (0.424, 9.14, 7.82, 8.18, 11.29, 8.18, 7.82, 9.14),
    8:  (0.566, 12.19, 10.43, 10.91, 15.05, 10.91, 10.43, 12.19),
    10: (0.707, 15.24, 13.04, 13.64, 18.82, 13.64, 13.04, 15.24),
    12: (0.848, 18.29, 15.65, 16.36, 22.58, 16.36, 15.65, 18.29),
}


@pytest.mark.parametrize("perna_mm,linha", sorted(TABELA_9_5.items()))
def test_tabela_9_5_filete_por_cm(perna_mm, linha):
    """Cap. 9, Tabela 9.5 — resistência do filete por cm, célula a célula."""
    a, e70, e60, a36, a572, a36e70, a36e60, a572e70 = linha
    b = perna_mm / 10.0
    perto(lig.garganta(b), a, 0.01, f"garganta b = {perna_mm} mm")

    s70, base36, adot = lig.resistencia_filete_cm(b, "E70XX", 25.0)
    perto(s70, e70, 0.01, f"metal da solda E70 b={perna_mm}")
    perto(base36, a36, 0.01, f"metal base A36 b={perna_mm}")
    perto(adot, a36e70, 0.01, f"adotada A36+E70 b={perna_mm}")

    s60, _, adot60 = lig.resistencia_filete_cm(b, "E60XX", 25.0)
    perto(s60, e60, 0.01, f"metal da solda E60 b={perna_mm}")
    perto(adot60, a36e60, 0.01, f"adotada A36+E60 b={perna_mm}")

    _, base50, adot50 = lig.resistencia_filete_cm(b, "E70XX", 34.5)
    perto(base50, a572, 0.01, f"metal base A572-50 b={perna_mm}")
    perto(adot50, a572e70, 0.01, f"adotada A572+E70 b={perna_mm}")


def test_regra_de_bolso_136_kN_por_mm_de_perna():
    """Cap. 9, regra de bolso — ≈ 1,36 kN/cm por mm de perna em A36 (metal base)."""
    for mm in (5, 6, 8):
        _, _, r = lig.resistencia_filete_cm(mm / 10.0, "E70XX", 25.0)
        perto(r / mm, 1.364, 0.01, f"kN/cm por mm de perna (b = {mm})")


def test_limites_geometricos_do_filete():
    """Cap. 9, Tabela 9.4 e item 9.5.2 — perna mínima, máxima e comprimento."""
    perto(mat.perna_minima(0.50) * 10, 3, 0.001, "t ≤ 6,35 mm")
    perto(mat.perna_minima(0.95) * 10, 5, 0.001, "6,35 < t ≤ 12,7")
    perto(mat.perna_minima(1.60) * 10, 6, 0.001, "12,7 < t ≤ 19")
    perto(mat.perna_minima(2.50) * 10, 8, 0.001, "t > 19")
    perto(mat.perna_maxima(0.79) * 10, 5.9, 0.01, "b ≤ t − 2 mm")
    perto(mat.perna_maxima(0.50) * 10, 5.0, 0.01, "b ≤ t para t < 6,35")

    # comprimento mínimo e redução de cordão longo
    v = lig.filete(0.6, 3.0, "E70XX", 25.0)
    assert "menor que o mínimo" in v.observacao
    Lef, beta = lig.comprimento_efetivo_filete(0.6 * 150, 0.6)
    perto(beta, 1.2 - 0.002 * 150, 0.001, "β de cordão longo")
    Lef2, _ = lig.comprimento_efetivo_filete(0.6 * 400, 0.6)
    perto(Lef2, 180 * 0.6, 0.001, "L_ef = 180·b")


# ===========================================================================
# Capítulo 9 — Exemplo 9.1: cantoneira tracionada com soldas balanceadas
# ===========================================================================

class TestExemplo91:
    """Cap. 9, Exemplo 9.1 — L 76×76×7,9, N_Sd = 150 kN, gusset 9,5 mm, E70/A36."""

    def test_1_escolha_da_perna(self):
        """b_min = 5 mm (chapa de 9,5) e b_max = 5,9 mm (borda de 7,9) → b = 5 mm."""
        perto(mat.perna_minima(0.95) * 10, 5.0, 0.001, "perna mínima")
        perto(mat.perna_maxima(0.79) * 10, 5.9, 0.01, "perna máxima")

    def test_2_resistencia_por_cm(self):
        """Metal da solda 7,62 kN/cm; metal base 6,82 kN/cm ← governa."""
        s, base, r = lig.resistencia_filete_cm(0.5, "E70XX", 25.0)
        perto(s, 7.62, 0.01, "metal da solda")
        perto(base, 6.82, 0.01, "metal base")
        perto(r, 6.82, 0.01, "adotada")

    def test_3_comprimento_total(self):
        """L_total = 150/6,82 = 22,0 cm."""
        _, _, r = lig.resistencia_filete_cm(0.5, "E70XX", 25.0)
        perto(150.0 / r, 22.0, 0.01, "comprimento total")

    def test_4_balanceamento_no_cg(self):
        """L₁ = 15,6 cm (talão) e L₂ = 6,4 cm (ponta da aba)."""
        _, _, r = lig.resistencia_filete_cm(0.5, "E70XX", 25.0)
        L = 150.0 / r
        ec, b = 2.2, 7.6
        perto(L * (b - ec) / b, 15.6, 0.01, "L₁ no talão")
        perto(L * ec / b, 6.4, 0.02, "L₂ na ponta")

    def test_5_verificacao_da_barra(self):
        """C_t = 0,86 → N_t,Rd = 293 kN; escoamento 261 kN."""
        Ag = 11.48
        Ct = 1 - 2.2 / 16.0
        perto(Ct, 0.8625, 0.01, "C_t = 1 − e_c/l_c")
        perto(Ct * Ag * 40.0 / GAMA_A2, 293.0, 0.01, "N_t,Rd ruptura")
        perto(Ag * 25.0 / GAMA_A1, 261.0, 0.01, "N_t,Rd escoamento")

    def test_6_gusset_whitmore(self):
        """Seção de Whitmore ≈ 26 cm × 0,95 cm → 561 kN."""
        r = lig.gusset_contraventamento(
            N_Sd=150.0, t_gusset=0.95, largura_ligacao=7.6,
            comprimento_ligacao=16.0, aco_gusset="ASTM A36",
            perna_solda=0.5, eletrodo="E70XX", comprimento_solda=16.0, n_cordoes=1,
            t_barra=0.79, aco_barra="ASTM A36")
        perto(r.dados["largura_whitmore"], 26.08, 0.01, "largura de Whitmore")
        v = [x for x in r.verificacoes if "Whitmore" in x.titulo][0]
        perto(v.Rd, 562.0, 0.01, "escoamento da seção de Whitmore")
        assert v.ok

    def test_resultado_final_capacidade_164_kN(self):
        """Resultado — 160 + 80 mm de filete de 5 mm: capacidade 164 kN."""
        v = lig.filete(0.5, 16.0, "E70XX", 25.0, F_Sd=150.0)
        v2 = lig.filete(0.5, 8.0, "E70XX", 25.0)
        perto(v.Rd + v2.Rd, 163.7, 0.01, "capacidade total adotada")
        assert v.Rd + v2.Rd >= 150.0


# ===========================================================================
# Capítulo 9 — Exemplo 9.2: mísula com dois filetes verticais
# ===========================================================================

class TestExemplo92:
    """Cap. 9, Exemplo 9.2 — chapa 12,5 mm, 2 filetes de 200 mm, V = 60 kN a e = 150 mm."""

    def test_1a3_metodo_elastico_fora_do_plano(self):
        """f_v = 1,50; f_m = 6,75; f_res = 6,91 kN/cm."""
        L, V, e = 20.0, 60.0, 15.0
        fv = V / (2 * L)
        W = 2 * L ** 2 / 6
        fm = V * e / W
        perto(fv, 1.50, 0.001, "f_v")
        perto(W, 133.33, 0.01, "W da linha de solda")
        perto(fm, 6.75, 0.01, "f_m")
        perto(math.hypot(fv, fm), 6.91, 0.01, "f_res")

    def test_grupo_solda_excentrico_reproduz_o_elastico(self):
        """O método elástico do módulo dá a mesma resultante de 6,91 kN/cm.

        Aqui os dois cordões estão no mesmo plano vertical (x = 0 e x = t da chapa),
        de modo que a excentricidade gera flexão fora do plano; modelamos os dois
        cordões separados de 1 cm apenas para o cálculo do cortante direto, e a
        parcela de momento é a do item 9.6.3 (f_m = M/W).
        """
        v = lig.grupo_solda_excentrico(
            [(0.0, -10.0, 0.0, 10.0)], P_y=30.0, ponto_aplicacao=(15.0, 0.0),
            perna=0.6, eletrodo="E70XX", fy_base=25.0)
        # um cordão isolado com metade da carga: f_v = 30/20 = 1,50 kN/cm
        # f_m = M/(L²/6) = 450/(400/6) = 6,75 kN/cm
        perto(v.Sd, 6.91, 0.01, "resultante pelo método elástico")
        perto(v.Rd, 8.18, 0.01, "filete de 6 mm em A36")
        assert v.ok

    def test_4_perna_necessaria(self):
        """b ≥ 0,45 cm pelo metal da solda e 0,51 cm pelo metal base → 6 mm."""
        perto(6.91 / 15.24, 0.4534, 0.01, "pelo metal da solda")
        perto(6.91 / 13.636, 0.5068, 0.01, "pelo metal base")
        _, _, r6 = lig.resistencia_filete_cm(0.6, "E70XX", 25.0)
        assert r6 >= 6.91

    def test_5_chapa_da_misula(self):
        """M_Rd = 2 841 kN·cm e V_Rd = 341 kN."""
        perto((1.25 * 20 ** 2 / 4) * 25.0 / GAMA_A1, 2841.0, 0.01, "M_Rd da chapa")
        perto(0.6 * 25.0 * (20 * 1.25) / GAMA_A1, 341.0, 0.01, "V_Rd da chapa")


# ===========================================================================
# Capítulo 9 — Exemplo 9.3: solda de composição
# ===========================================================================

class TestExemplo93:
    """Cap. 9, Exemplo 9.3 — VS 500 (mesas 250×12,5; alma 475×8), V_Sd = 300 kN."""

    I = 25 * 50 ** 3 / 12 - 24.2 * 47.5 ** 3 / 12
    Q = 25 * 1.25 * (25 - 0.625)

    def test_1_propriedades(self):
        perto(self.I, 44287.0, 0.01, "I da seção")
        perto(self.Q, 761.7, 0.01, "Q da mesa")

    def test_2_fluxo_de_cisalhamento(self):
        """q = 5,16 kN/cm total → 2,58 por filete."""
        v = lig.solda_composicao(300.0, self.Q, self.I, perna=0.5,
                                 eletrodo="E70XX", fy_base=25.0, n_filetes=2)
        perto(v.Sd, 2.58, 0.01, "q por filete")
        perto(300.0 * self.Q / self.I, 5.16, 0.01, "q total")

    def test_3_filete_continuo_de_5mm(self):
        """6,82 kN/cm ≫ 2,58 (utilização 38 %) — a perna mínima governa."""
        v = lig.solda_composicao(300.0, self.Q, self.I, perna=0.5, n_filetes=2)
        perto(v.Rd, 6.82, 0.01, "capacidade do filete de 5 mm")
        perto(v.razao, 0.378, 0.02, "utilização")
        assert v.ok
        perto(mat.perna_minima(1.25) * 10, 5.0, 0.001, "perna mínima pela mesa")
        perto(mat.perna_maxima(0.8) * 10, 6.0, 0.01, "perna máxima pela alma")

    def test_4_alternativa_intermitente(self):
        """50–150 não passa (2,27 < 2,58); 60–150 passa (2,73 ≥ 2,58)."""
        v50 = lig.solda_composicao(300.0, self.Q, self.I, perna=0.5, n_filetes=2,
                                   trecho=5.0, passo=15.0, t_alma=0.8)
        perto(v50.Rd, 2.27, 0.01, "50–150")
        assert not v50.ok
        v60 = lig.solda_composicao(300.0, self.Q, self.I, perna=0.5, n_filetes=2,
                                   trecho=6.0, passo=15.0, t_alma=0.8)
        perto(v60.Rd, 2.73, 0.01, "60–150")
        assert v60.ok
        assert "fadiga" in v60.observacao


# ===========================================================================
# Outras ligações típicas — coerência e memória de cálculo
# ===========================================================================

def test_chapa_simples_coerente():
    """Chapa simples: corte excêntrico > corte direto e todas as verificações somam."""
    r = lig.chapa_simples("W 360×51", V_Sd=120.0, n_parafusos=3, t_chapa=0.95,
                          a_excentricidade=6.0)
    assert r.dados["F_max_parafuso"] > 120.0 / 3.0
    # I_p de 3 parafusos a 7,6 cm: 2 × 7,6² = 115,52 cm²
    perto(r.dados["Ip"], 2 * 7.6 ** 2, 0.001, "I_p do grupo")
    assert r.ok, r.resumo()
    assert all(v.passos for v in r.verificacoes if not v.dispensada)


def test_chapa_de_topo_binario_e_alavanca():
    """Chapa de topo: binário T = M/(d − t_f) e o T-stub controla a espessura."""
    r = lig.chapa_de_topo("W 360×51", M_Sd=15000.0, V_Sd=120.0, diametro='7/8"',
                          parafuso="ASTM A325", n_por_linha=2, linhas_tracionadas=2,
                          t_chapa=2.24, gabarito=10.0, passo_linhas=9.0,
                          pilar="W 250×73", aco_pilar="ASTM A572 Gr.50")
    d, tf = 35.5, 1.16
    perto(r.dados["braco"], d - tf, 0.001, "braço do binário")
    perto(r.dados["T"], 15000.0 / (d - tf), 0.001, "tração na mesa")
    assert r.dados["T_por_parafuso"] == pytest.approx(r.dados["T"] / 4)
    assert "enrijecedor_necessario" in r.dados
    assert isinstance(r.dados["alavanca"]["Q"], float)


def test_emenda_viga_transmite_o_binario():
    """Emenda: T_mesa = M/(d − t_f) e o grupo de alma usa o método elástico."""
    r = lig.emenda_viga("W 360×51", M_Sd=20000.0, V_Sd=100.0, diametro='3/4"',
                        n_parafusos_mesa=8, n_parafusos_alma=3, colunas_alma=2)
    perto(r.dados["T_mesa"], 20000.0 / (35.5 - 1.16), 0.001, "T da mesa")
    assert r.dados["Ip_alma"] > 0
    assert r.dados["F_max_alma"] >= 100.0 / 6


def test_verificar_grupo_parafusos_metodo_elastico():
    """Grupo sob V com excentricidade: distribuição elástica e todos os ELU."""
    r = lig.verificar_grupo_parafusos(
        '3/4"', "ASTM A325", linhas=3, colunas=1, passo=7.6, gabarito=0.0,
        chapas=[{"nome": "alma", "t": 0.72, "fu": 40.0, "fy": 25.0, "borda": 3.5,
                 "n_borda": 1, "planos": 1}],
        V_Sd=120.0, excentricidade=6.0, planos=2)
    perto(r.dados["Ip"], 2 * 7.6 ** 2, 0.001, "I_p")
    perto(r.dados["M_total"], 120.0 * 6.0, 0.001, "momento total")
    fv = 120.0 / 3
    fm = (120.0 * 6.0) * 7.6 / (2 * 7.6 ** 2)
    perto(r.dados["F_max_parafuso"], math.hypot(fm, fv), 0.001, "força máxima")


def test_memoria_de_calculo_presente_em_todas_as_verificacoes():
    """GUIA, princípio 2 — toda verificação carrega passos com fórmula, conta e valor."""
    r = lig.dupla_cantoneira("W 360×51", 120.0)
    for v in r.verificacoes:
        if v.dispensada:
            continue
        assert v.passos, f"{v.titulo} sem memória de cálculo"
        assert v.norma, f"{v.titulo} sem citação de norma"
        for p in v.passos:
            assert p.texto


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
