# -*- coding: utf-8 -*-
"""Testes do módulo de perfis formados a frio (NBR 14762:2010).

Referências usadas:
    manual, cap. 3, item 3.5 e Tabela 3.9  — perfis Ue e suas dimensões
    manual, cap. 7, item 7.11 e Tabela 7.9 — perfis formados a frio, capacidade
                                             indicativa de terças
    manual, cap. 16, Passo 3 (item 16.3)   — terça Ue 200×75×20×2,65, vão 5 m,
                                             com todos os números

Rode com `python -m pytest testes/test_nbr14762.py -q` ou direto:
`python testes/test_nbr14762.py`.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import materiais as mat                       # noqa: E402
from nucleo import nbr14762 as cf                         # noqa: E402
from nucleo.base import ErroDeDados                       # noqa: E402
from nucleo.perfis import banco                           # noqa: E402

CF26 = mat.aco("CF-26 (NBR 6650)")           # fy = 26 kN/cm², como no cap. 16
PERFIL_CAP16 = "Ue 200×75×20×2,65"


def _dif(calc, ref):
    return abs(calc / ref - 1.0)


# =============================================================================
# 1. Propriedades de seção contra o catálogo (dados/perfis.json)
# =============================================================================

# Divergências acima de 5 % entre o método linear e `dados/perfis.json`.
# Em todas elas a ÁREA bate (≤ 2,5 %), o que mostra que a linha média está certa:
# o que diverge são os momentos de inércia tabelados, arredondados a 2–3 algarismos
# e, em dois casos, incoerentes com o próprio manual.
EXCECOES = {
    ("Ue 100×50×17×2,00", "Iy"): (
        0.08, "catálogo arredonda Iy a 15 cm⁴ (2 algarismos); r_y tabelado 1,8 cm "
              "dá Iy = 1,8²×4,5 = 14,6 — a própria tabela é incoerente em ±4 %"),
    ("Ue 127×50×17×2,00", "Iy"): (
        0.09, "idem: Iy tabelado a 2 algarismos (16 cm⁴) para uma seção de mesa "
              "estreita, onde o valor é muito sensível ao raio de dobra adotado"),
    ("Ue 200×75×20×2,65", "Iy"): (
        0.07, "catálogo traz Iy = 76 cm⁴; o cap. 16 do manual usa esse mesmo valor. "
              "Com r = 1,0·t o método linear dá 71,8 cm⁴ (−5,5 %); com canto vivo "
              "daria 73,8 cm⁴. Conservador para a sucção (reduz M_e)"),
    ("Ue 300×85×25×3,00", "Ix"): (
        0.09, "perfis.json traz Ix = 1 830 cm⁴, mas a Tabela 3.9 do próprio manual "
              "traz 1 950 cm⁴ para o mesmo perfil — o valor calculado (1 953) "
              "concorda com a Tabela 3.9; o registro do JSON é que está baixo"),
    ("Ue 300×85×25×3,00", "Wx"): (0.09, "consequência direta do Ix acima"),
    ("Ue 300×100×25×3,75", "Ix"): (
        0.09, "A tabelada (19,9 cm²) confere em 1 %, mas Ix tabelado (2 450 cm⁴) é "
              "8 % menor que o da linha média; a Tabela 3.9 não lista esta "
              "espessura para conferir. Provável arredondamento da fonte"),
    ("Ue 300×100×25×3,75", "Wx"): (0.09, "consequência direta do Ix acima"),
}


def _ue_do_catalogo():
    return [p for p in banco().lista("Ue") if p.nome.strip().upper().startswith("UE")]


def test_propriedades_ue_contra_catalogo():
    """Método linear × tabela do catálogo, tolerância 5 %.

    O catálogo considera os raios de concordância e arredonda; aqui o raio interno
    adotado é 1,0·t (NBR 6355 / manual, item 3.5.2). As divergências acima de 5 %
    estão listadas em EXCECOES, com a explicação de cada uma.
    """
    fora = []
    for p in _ue_do_catalogo():
        s = cf.secao_do_perfil(p)
        for prop in ("A", "Ix", "Wx", "Iy"):
            ref = p.dados.get(prop)
            if not ref:
                continue
            d = _dif(getattr(s, prop), ref)
            tol, _motivo = EXCECOES.get((p.nome, prop), (0.05, ""))
            if d > tol:
                fora.append(f"{p.nome} {prop}: catálogo {ref}, calculado "
                            f"{getattr(s, prop):.2f} ({d * 100:.1f} %)")
        # a massa depende só do comprimento desenvolvido: bate sempre
        assert _dif(s.massa, p.massa) < 0.03, p.nome
    assert not fora, "propriedades fora da tolerância:\n" + "\n".join(fora)


def test_area_sempre_dentro_de_3_por_cento():
    """A área é a prova de que a geometria da linha média está certa: ela não
    depende de arredondamento de inércia nem da posição do centroide."""
    for p in _ue_do_catalogo():
        s = cf.secao_do_perfil(p)
        assert _dif(s.A, p.dados["A"]) < 0.03, f"{p.nome}: A = {s.A:.2f}"


def test_propriedades_de_torcao_cap16():
    """Cap. 16, Passo 3 — J, C_w, r_y e W_x adotados para o Ue 200×75×20×2,65.

    O manual adota J = 0,24 cm⁴, C_w ≈ 5 500 cm⁶, r_y = 2,74 cm e W_x = 62 cm³
    ("propriedades de catálogo").
    """
    s = cf.secao_do_perfil(PERFIL_CAP16)
    assert _dif(s.J, 0.24) < 0.05, s.J
    assert _dif(s.Cw, 5500.0) < 0.05, s.Cw
    assert _dif(s.ry, 2.74) < 0.05, s.ry
    assert _dif(s.Wx, 62.0) < 0.05, s.Wx
    # W_y ≈ 14 cm³ na borda das mesas (cap. 16)
    assert _dif(s.Wy, 14.0) < 0.05, s.Wy
    # o centro de torção fica fora da seção, do lado oposto às mesas
    assert s.xs < 0 < s.x0


# =============================================================================
# 2. Cargas críticas elásticas
# =============================================================================

def test_momento_critico_cap16():
    """Cap. 16, Passo 3: M_e ≈ 2 150 kN·cm para L_b = L_t = 250 cm, C_b = 1."""
    s = cf.secao_do_perfil(PERFIL_CAP16)
    Me = cf.forca_critica_global(s, KyLy=250.0, KtLt=250.0, esforco="flexao", Cb=1.0)
    assert _dif(Me, 2150.0) < 0.05, Me


def test_chi_flt_cap16():
    """Cap. 16: χ_FLT = 0,88 com correntes (L_b = 2,5 m) e ≈ 0,38 sem correntes."""
    s = cf.secao_do_perfil(PERFIL_CAP16)
    My = s.Wx * CF26.fy
    v = cf.flexao_mrd(s, CF26, 0.0, Lb=250.0, Lt=250.0, Cb=1.0)
    chi_com = v.Rd * 1.10 / My
    assert abs(chi_com - 0.88) < 0.05, chi_com
    v0 = cf.flexao_mrd(s, CF26, 0.0, Lb=500.0, Lt=500.0, Cb=1.0)
    chi_sem = v0.Rd * 1.10 / My
    assert abs(chi_sem - 0.38) < 0.05, chi_sem
    assert chi_sem < chi_com


def test_cargas_criticas_coerentes():
    """Ordem de grandeza e coerência física das cargas críticas."""
    s = cf.secao_do_perfil(PERFIL_CAP16)
    sig_l = cf.tensoes_criticas_locais(s, "flexao")
    # a alma (b/t ≈ 71) é o elemento crítico na flexão
    assert sig_l["alma"] < sig_l["mesa"] < sig_l["enrijecedor"]
    # flambagem local na flexão pura é bem acima de f_y: seção totalmente efetiva,
    # como o cap. 16 afirma ("alma h/t = 75 < limite; mesa b/t = 28 < limite")
    assert sig_l["alma"] > CF26.fy

    s_dist_flex = cf.forca_critica_distorcional(s, "flexao") / s.Wx
    s_dist_comp = cf.forca_critica_distorcional(s, "compressao") / s.A
    # distorcional na compressão é sempre mais severa que na flexão
    assert s_dist_comp < s_dist_flex
    # faixa esperada para terça Ue de 2 a 3 mm: 25 a 60 kN/cm² na flexão
    assert 25.0 < s_dist_flex < 60.0, s_dist_flex
    # uma mola externa (telha) só pode aumentar a carga crítica
    com_mola = cf.forca_critica_distorcional(s, "flexao", k_mola=5.0)
    assert com_mola > cf.forca_critica_distorcional(s, "flexao")


def test_distorcional_cai_com_chapa_mais_fina():
    """Mesma geometria, chapa mais fina: σ_dist cai (varia com t³ na rigidez)."""
    grosso = cf.propriedades_ue(200, 75, 20, 3.00)
    fino = cf.propriedades_ue(200, 75, 20, 2.00)
    assert (cf.forca_critica_distorcional(grosso, "flexao") / grosso.Wx
            > cf.forca_critica_distorcional(fino, "flexao") / fino.Wx)


def test_compressao_mrd_devolve_o_menor_modo():
    s = cf.secao_do_perfil(PERFIL_CAP16)
    v = cf.compressao_mrd(s, CF26, 20.0, KxLx=200.0, KyLy=200.0)
    Ny = s.A * CF26.fy
    assert 0 < v.Rd < Ny / 1.10             # algum modo reduziu a resistência
    assert "governa" in v.observacao or "Modo" in v.observacao
    # com barra mais curta a resistência não pode diminuir
    v_curto = cf.compressao_mrd(s, CF26, 20.0, KxLx=100.0, KyLy=100.0)
    assert v_curto.Rd >= v.Rd


# =============================================================================
# 3. Cap. 16, Passo 3 — a terça completa
# =============================================================================

def _terca_cap16(espacamento=1.60, n_correntes=1, vao=5.0):
    """Reproduz as cargas do Passo 3 do cap. 16 para um espaçamento qualquer.

    g = 0,05 kN/m² (telha) × s + 0,077 kN/m (peso próprio da terça)
    q = 0,25 kN/m² (sobrecarga) × s
    vento de sucção: 1,08 kN/m² × s
    C1 (gravidade): 1,4·g + 1,5·q      C2 (sucção): 1,0·g − 1,4·w
    """
    g = 0.05 * espacamento + 0.077
    q = 0.25 * espacamento
    w = 1.08 * espacamento
    wd_grav = 1.4 * g + 1.5 * q
    wd_suc = 1.4 * w - 1.0 * g
    return cf.terca(PERFIL_CAP16, CF26, vao=vao,
                    carga_gravidade=wd_grav, carga_succao=wd_suc,
                    n_correntes=n_correntes, inclinacao=5.71,
                    carga_servico_gravidade=g + q, carga_servico_succao=w,
                    comprimento_apoio=10.0)


def test_cap16_cargas_conferem():
    """As cargas do Passo 3: w_d = 0,82 kN/m na gravidade e 2,26 kN/m na sucção."""
    g = 0.05 * 1.60 + 0.077
    q = 0.25 * 1.60
    w = 1.08 * 1.60
    assert abs(g - 0.157) < 0.002
    assert abs(1.4 * g + 1.5 * q - 0.82) < 0.01
    assert abs(1.4 * w - 1.0 * g - 2.26) < 0.02


def test_cap16_terca_succao_razao_064():
    """Cap. 16, Passo 3, combinação C2 (sucção): razão relatada ≈ 0,64.

    O manual chega a 7,07/11,0 = 0,64 usando propriedades de catálogo e adotando
    χ_FLT = 0,75 "na mão" (o cálculo dele dá 0,88 com L_b = L_t = 2,5 m, e ele
    reduz porque as correntes travam o deslocamento lateral mas não o giro).
    Este módulo faz essa mesma consideração de forma explícita: L_y = 2,5 m
    (correntes) e L_t = 5,0 m (não há travamento à torção), com C_b do trecho.
    """
    r = _terca_cap16(espacamento=1.60)
    v = [x for x in r.verificacoes if "sucção" in x.titulo and "Flexão" in x.titulo][0]
    assert _dif(v.Sd, 707.0) < 0.02, v.Sd           # M_d = 7,07 kN·m
    assert _dif(v.razao, 0.64) < 0.05, (v.razao, v.Rd)
    assert v.ok


def test_cap16_terca_succao_espacamento_157():
    """Mesma terça com espaçamento 1,57 m — a razão cai ~2 % e continua ≈ 0,64."""
    r = _terca_cap16(espacamento=1.57)
    v = [x for x in r.verificacoes if "sucção" in x.titulo and "Flexão" in x.titulo][0]
    assert _dif(v.razao, 0.64) < 0.05, v.razao


def test_cap16_terca_gravidade():
    """C1: M_d = 2,56 kN·m e a razão fica em torno de 0,2 (o manual relata 0,19)."""
    r = _terca_cap16()
    v = [x for x in r.verificacoes
         if "gravitacional" in x.titulo and "Flexão" in x.titulo][0]
    assert _dif(v.Sd, 256.0) < 0.03, v.Sd
    # o manual usa M_Rd = 14,7 kN·m (sem distorcional); aqui a distorcional reduz
    # ~11 %, então a razão sai um pouco maior — e a folga continua enorme
    assert 0.15 < v.razao < 0.25, v.razao
    obl = [x for x in r.verificacoes if "oblíqua" in x.titulo][0]
    assert obl.razao < 0.30 and obl.ok


def test_cap16_cortante_esmagamento_e_flecha():
    """Cortante, esmagamento da alma e flecha do Passo 3."""
    r = _terca_cap16()
    vc = [x for x in r.verificacoes if "cortante" in x.titulo.lower()
          and "Interação" not in x.titulo][0]
    assert _dif(vc.Sd, 5.65) < 0.05, vc.Sd                  # V_d = 5,7 kN
    # o manual estima V_Rd ≈ 75 kN pelo escoamento puro; aqui entra a flambagem
    # da alma (h/t ≈ 71), que reduz para ~66 kN — a favor da segurança
    assert 55.0 < vc.Rd < 80.0, vc.Rd
    assert vc.razao < 0.12

    ve = [x for x in r.verificacoes if "Esmagamento" in x.titulo][0]
    assert ve.ok and 0.1 < ve.razao < 0.8      # é uma verificação que "aparece"

    fg = [x for x in r.verificacoes if x.titulo.startswith("Flecha — gravidade")][0]
    assert _dif(fg.Sd, 0.37) < 0.08, fg.Sd     # δ = 0,37 cm no manual
    assert _dif(fg.Rd, 500.0 / 180.0) < 1e-6   # L/180 = 2,78 cm
    assert fg.ok

    fs = [x for x in r.verificacoes if x.titulo.startswith("Flecha — sucção")][0]
    assert _dif(fs.Rd, 500.0 / 120.0) < 1e-6   # L/120 = 4,17 cm
    assert fs.ok

    assert r.ok
    assert "sucção" in r.critica.titulo        # é a sucção que dimensiona a terça


def test_cap16_sem_correntes_reprova():
    """Cap. 16: "sem correntes (L_b = 5 m) ... a terça não passaria"."""
    r = _terca_cap16(n_correntes=0)
    v = [x for x in r.verificacoes if "sucção" in x.titulo and "Flexão" in x.titulo][0]
    assert not v.ok, v.razao
    assert not r.ok


def test_cap16_longarina():
    """Cap. 16, Passo 3, longarinas: mesmo perfil, vão 5 m, espaçamento 1,9 m,
    vento de canto 1,13 kN/m² → w_d = 3,0 kN/m e M_d = 9,4 kN·m, "justo"."""
    wd = 1.4 * 1.13 * 1.9
    assert abs(wd - 3.0) < 0.02
    r = cf.terca(PERFIL_CAP16, CF26, vao=5.0, carga_gravidade=0.0,
                 carga_succao=wd, n_correntes=1, elemento="Longarina")
    v = [x for x in r.verificacoes if "sucção" in x.titulo and "Flexão" in x.titulo][0]
    assert _dif(v.Sd, 940.0) < 0.02, v.Sd
    # o manual acha 9,4/11,0 = 0,85 ("justo nos cantos"); aqui a razão fica na
    # mesma faixa, entre 0,75 e 0,95
    assert 0.75 < v.razao < 0.95, v.razao


# =============================================================================
# 4. Tabela 7.9 do cap. 7 (declarada orientativa pelo próprio manual)
# =============================================================================

TABELA_79 = {   # perfil -> q_d (kN/m) nos vãos 5, 6, 7 e 8 m
    "Ue 150×60×20×2,00": [2.0, 1.2, 0.7, 0.5],
    "Ue 200×75×20×2,00": [3.4, 2.3, 1.6, 1.1],
    "Ue 200×75×20×2,65": [4.5, 3.1, 2.2, 1.4],
    "Ue 250×85×25×2,65": [6.3, 4.3, 3.2, 2.4],
    "Ue 300×85×25×3,00": [8.8, 6.1, 4.5, 3.4],
}
VAOS = (5, 6, 7, 8)


def test_tabela_7_9_ordem_de_grandeza():
    """Tabela 7.9 — capacidade indicativa de terças Ue sob carga gravitacional.

    O manual calculou a tabela com M_Rd = 0,95·W_x·f_y/1,10 e flecha L/180, com as
    propriedades da Tabela 17.3, e avisa que "os valores são orientativos". Este
    módulo calcula M_Rd pelo MRD, o que **inclui a flambagem distorcional** — que
    a fórmula do manual ignora. O resultado é sistematicamente menor nas células
    governadas pelo momento, e praticamente igual nas governadas pela flecha.

    Aqui se confere a ordem de grandeza (±20 %), o sinal da divergência e o
    acordo estreito nas células de flecha; as diferenças são relatadas, não
    "ajustadas".
    """
    tabela = {l["perfil"]: l for l in cf.tabela_capacidade(CF26, VAOS, n_correntes=2)}
    relato = []
    for nome, refs in TABELA_79.items():
        linha = tabela[nome]
        for vao, ref in zip(VAOS, refs):
            cel = linha["q"][vao]
            d = cel["qd"] / ref - 1.0
            relato.append(f"{nome} L={vao} m: manual {ref:.1f}, módulo "
                          f"{cel['qd']:.2f} kN/m ({d * 100:+.0f} %, governa "
                          f"{cel['governa']})")
            assert abs(d) < 0.20, relato[-1]
            if cel["governa"] == "flecha":
                # a flecha é a mesma conta nos dois; só muda I_x calculado × tabelado
                assert abs(d) < 0.06, relato[-1]
            else:
                # nas células de momento o módulo é sempre mais conservador
                assert d <= 0.01, relato[-1]
    print("\n".join(relato))


def test_tabela_7_9_flecha_manda_a_partir_de_7m():
    """Cap. 7: "a partir de 7 m a flecha já manda nos perfis mais leves"."""
    tabela = {l["perfil"]: l for l in cf.tabela_capacidade(CF26, VAOS, n_correntes=2)}
    assert tabela["Ue 150×60×20×2,00"]["q"][7]["governa"] == "flecha"
    assert tabela["Ue 200×75×20×2,00"]["q"][8]["governa"] == "flecha"
    # nos perfis pesados o momento continua mandando
    assert tabela["Ue 300×85×25×3,00"]["q"][8]["governa"] == "momento"


# =============================================================================
# 5. Monotonicidade
# =============================================================================

def test_mais_correntes_aumenta_capacidade_na_succao():
    s = cf.secao_do_perfil(PERFIL_CAP16)
    razoes = []
    for n in (0, 1, 2, 3):
        r = cf.terca(s, CF26, vao=7.0, carga_gravidade=0.5, carga_succao=1.6,
                     n_correntes=n)
        v = [x for x in r.verificacoes if "sucção" in x.titulo
             and "Flexão" in x.titulo][0]
        razoes.append(v.razao)
    assert razoes == sorted(razoes, reverse=True), razoes
    assert razoes[0] > razoes[-1] * 1.3         # o ganho é grande, não marginal


def test_perfil_mais_espesso_resiste_mais():
    """Mesma geometria externa, chapa mais grossa: mais capacidade em tudo."""
    fino = cf.secao_do_perfil("Ue 200×75×20×2,00")
    grosso = cf.secao_do_perfil("Ue 200×75×20×2,65")
    for lb, lt in ((0.0, 0.0), (250.0, 500.0)):
        a = cf.flexao_mrd(fino, CF26, 0.0, lb, lt)
        b = cf.flexao_mrd(grosso, CF26, 0.0, lb, lt)
        assert b.Rd > a.Rd, (lb, a.Rd, b.Rd)
    assert (cf.cisalhamento(grosso, CF26).Rd > cf.cisalhamento(fino, CF26).Rd)
    assert (cf.esmagamento_alma(grosso, CF26, N_apoio=10.0).Rd
            > cf.esmagamento_alma(fino, CF26, N_apoio=10.0).Rd)


def test_perfil_mais_alto_resiste_mais_a_flexao():
    baixo = cf.secao_do_perfil("Ue 150×60×20×2,65")
    alto = cf.secao_do_perfil("Ue 250×85×25×2,65")
    assert (cf.flexao_mrd(alto, CF26, 0.0, 0.0).Rd
            > cf.flexao_mrd(baixo, CF26, 0.0, 0.0).Rd)


def test_vao_maior_reprova_mais():
    s = cf.secao_do_perfil(PERFIL_CAP16)
    anterior = 0.0
    for vao in (4.0, 5.0, 6.0, 7.0):
        r = cf.terca(s, CF26, vao=vao, carga_gravidade=0.8, carga_succao=2.2,
                     n_correntes=1)
        assert r.razao > anterior
        anterior = r.razao


# =============================================================================
# 6. Caso de reprovação
# =============================================================================

def test_terca_esbelta_vao_grande_sem_correntes_reprova():
    """Ue 150×60×20×2,00 com 8 m de vão e sem correntes: tem de reprovar, e o
    modo governante na sucção tem de ser distorcional ou FLT (global) — não
    escoamento, não cortante."""
    s = cf.secao_do_perfil("Ue 150×60×20×2,00")
    r = cf.terca(s, CF26, vao=8.0, carga_gravidade=0.6, carga_succao=1.5,
                 n_correntes=0)
    assert not r.ok
    v = [x for x in r.verificacoes if "sucção" in x.titulo and "Flexão" in x.titulo][0]
    assert not v.ok, v.razao
    assert ("global" in v.observacao or "distorcional" in v.observacao), v.observacao


def test_reprovacao_por_distorcional_em_chapa_fina():
    """Perfil muito esbelto com a mesa comprimida travada: quem sobra para
    governar é a distorcional."""
    s = cf.propriedades_ue(300, 100, 15, 1.20)          # enrijecedor curto, chapa fina
    v = cf.flexao_mrd(s, CF26, 0.0, Lb=0.0)             # sem FLT
    assert "distorcional" in v.observacao or "local" in v.observacao, v.observacao
    assert v.Rd < s.Wx * CF26.fy / 1.10 * 0.8


# =============================================================================
# 7. Método da Seção Efetiva (MSE)
# =============================================================================

def test_largura_efetiva_winter():
    """b_ef = b para λ_p ≤ 0,673 e cai pela curva de Winter acima disso."""
    t = 0.2
    # chapa pouco esbelta: totalmente efetiva
    assert cf.largura_efetiva(2.0, t, 26.0) == 2.0
    # chapa muito esbelta: reduz
    b = 20.0
    bef = cf.largura_efetiva(b, t, 26.0)
    assert bef < b
    # monotonicidade: quanto maior a tensão, menor a largura efetiva
    assert cf.largura_efetiva(b, t, 34.5) < bef
    # e quanto maior k, maior a largura efetiva
    assert cf.largura_efetiva(b, t, 26.0, k=23.9) > bef
    # conferência numérica da fórmula de Winter
    sigma_cr = 4.0 * math.pi ** 2 * 20000.0 / (12 * (1 - 0.3 ** 2)) / (b / t) ** 2
    lam = math.sqrt(26.0 / sigma_cr)
    assert abs(bef - b * (1 - 0.22 / lam) / lam) < 1e-9


def test_secao_efetiva_cap16_quase_integral():
    """Cap. 16: "para esta espessura a seção é totalmente efetiva ... W_ef = W_x"."""
    s = cf.secao_do_perfil(PERFIL_CAP16)
    ef = cf.secao_efetiva(s, CF26, "flexao")
    assert ef["Wef"] / s.Wx > 0.95, ef["Wef"]
    assert ef["Aef"] / s.A > 0.95
    assert 0.0 < ef["RI"] <= 1.0
    assert 0.43 <= ef["k_mesa"] <= 4.0
    # na compressão centrada a seção já não é integral (alma b/t ≈ 71 com k = 4)
    efc = cf.secao_efetiva(s, CF26, "compressao")
    assert efc["Aef"] < s.A


def test_mse_e_mrd_dao_resultados_proximos():
    """Os dois caminhos da norma têm de conversar: o MSE (item 9.7) sem a
    distorcional e o MRD (item 9.8) não podem divergir mais que ~20 %."""
    s = cf.secao_do_perfil(PERFIL_CAP16)
    mse = cf.flexao_mse(s, CF26, 0.0, Lb=250.0, Lt=500.0, Cb=1.30)
    mrd = cf.flexao_mrd(s, CF26, 0.0, Lb=250.0, Lt=500.0, Cb=1.30)
    assert _dif(mse.Rd, mrd.Rd) < 0.20, (mse.Rd, mrd.Rd)


def test_secao_efetiva_chapa_fina_reduz_bastante():
    s = cf.propriedades_ue(300, 100, 25, 1.20)
    ef = cf.secao_efetiva(s, CF26, "flexao")
    assert ef["Wef"] < 0.85 * s.Wx, ef["Wef"] / s.Wx


# =============================================================================
# 8. Dimensionamento automático
# =============================================================================

def test_dimensionar_terca_ordena_por_peso_e_aprova():
    ops = cf.dimensionar_terca(CF26, vao=5.0, carga_gravidade=0.82,
                               carga_succao=2.26, inclinacao=5.71)
    assert ops, "nenhum perfil atendeu"
    massas = [o.dados["massa_kg_m"] for o in ops]
    assert massas == sorted(massas)
    for o in ops:
        assert o.ok and o.razao <= 1.0001
        assert o.dados["razoes"]                      # razão de cada verificação
        assert "Lb_cm" in o.dados and "secao" in o.dados
    # o perfil do cap. 16 tem de estar entre as opções aprovadas
    assert any(o.perfil == PERFIL_CAP16 for o in ops)


def test_dimensionar_terca_carga_absurda_nao_acha_nada():
    ops = cf.dimensionar_terca(CF26, vao=12.0, carga_gravidade=20.0,
                               carga_succao=20.0)
    assert ops == []


def test_dimensionar_terca_usa_correntes_quando_precisa():
    """Sob sucção forte num vão grande, a solução econômica usa correntes."""
    ops = cf.dimensionar_terca(CF26, vao=7.5, carga_gravidade=0.6,
                               carga_succao=2.2, correntes=(0, 1, 2, 3))
    assert ops
    assert ops[0].dados["n_correntes"] >= 1, ops[0].dados["n_correntes"]


# =============================================================================
# 9. Falha explícita em entrada inconsistente
# =============================================================================

def _espera_erro(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ErroDeDados:
        return True
    raise AssertionError(f"{fn.__name__} deveria ter levantado ErroDeDados")


def test_entrada_inconsistente_levanta_erro_de_dados():
    _espera_erro(cf.propriedades_ue, -200, 75, 20, 2.65)      # altura negativa
    _espera_erro(cf.propriedades_ue, 200, 75, 20, 0.1)        # t fora da NBR 6355
    _espera_erro(cf.propriedades_ue, 200, 8, 20, 2.65)        # mesa menor que a dobra
    _espera_erro(cf.propriedades_ue, 200, 75, 3, 2.65)        # enrijecedor menor que a dobra
    _espera_erro(cf.secao_do_perfil, "W 360×51")              # não é Ue
    _espera_erro(cf.tensoes_criticas_locais,
                 cf.propriedades_ue(200, 75, 20, 2.65), "torcao")
    _espera_erro(cf.terca, PERFIL_CAP16, CF26, -1.0, 1.0, 1.0, 1)
    _espera_erro(cf.terca, PERFIL_CAP16, CF26, 5.0, -1.0, 1.0, 1)
    _espera_erro(cf.esmagamento_alma, cf.secao_do_perfil(PERFIL_CAP16), CF26,
                 5.0, 10.0, "meio-do-vao")


def test_memoria_de_calculo_existe_em_toda_verificacao():
    """Princípio 2 do guia: a memória é parte do resultado."""
    r = _terca_cap16()
    for v in r.verificacoes:
        assert v.passos, f"{v.titulo} sem memória de cálculo"
        for p in v.passos:
            assert p.texto
        assert v.norma.startswith("NBR 14762")


def test_esmagamento_depende_do_comprimento_de_apoio():
    s = cf.secao_do_perfil(PERFIL_CAP16)
    curto = cf.esmagamento_alma(s, CF26, 5.0, N_apoio=4.0)
    longo = cf.esmagamento_alma(s, CF26, 5.0, N_apoio=15.0)
    assert longo.Rd > curto.Rd
    interior = cf.esmagamento_alma(s, CF26, 5.0, N_apoio=10.0, posicao="interior")
    extremo = cf.esmagamento_alma(s, CF26, 5.0, N_apoio=10.0, posicao="extremidade")
    assert interior.Rd > extremo.Rd          # apoio interior é bem mais resistente


def test_cb_trecho():
    """C_b = 1,0 em momento uniforme e ≈ 1,14 em viga biapoiada sob carga
    uniforme (trecho único)."""
    assert abs(cf.cb_trecho(1, 1, 1, 1) - 1.0) < 1e-9
    segs = cf.segmentos_viga_uniforme(0)
    assert len(segs) == 1
    assert abs(segs[0][1] - 1.136) < 0.01
    # com uma corrente no meio do vão, o trecho crítico tem C_b ≈ 1,30
    segs1 = cf.segmentos_viga_uniforme(1)
    assert len(segs1) == 2
    assert abs(segs1[0][1] - 1.30) < 0.02


if __name__ == "__main__":
    import traceback
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = 0
    for nome, fn in testes:
        try:
            fn()
            print(f"ok   {nome}")
        except Exception:
            falhas += 1
            print(f"FALHA {nome}")
            traceback.print_exc()
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
