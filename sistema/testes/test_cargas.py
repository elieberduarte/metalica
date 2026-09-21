# -*- coding: utf-8 -*-
"""Testes do módulo `nucleo.cargas` contra os exemplos resolvidos do manual.

Fontes conferidas:
    Capítulo 5  — Ações, segurança e combinações (Tabelas 5.1 a 5.12;
                  Exemplo 5.1 — vento no galpão; Exemplo 5.2 — terça)
    Capítulo 16 — Exemplo completo do galpão 20 × 40 m (Tabelas 16.1 a 16.3)

Tolerância padrão de 1 % contra o manual, com piso absoluto de 0,005 (o manual
publica as pressões arredondadas em duas casas: ±0,005 é o próprio arredondamento).

Divergências encontradas no manual estão marcadas com DIVERGÊNCIA e explicadas
no teste correspondente — os valores não foram "ajustados" para passar.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados                                  # noqa: E402
from nucleo import cargas as cg                                      # noqa: E402


# ---------------------------------------------------------------------------
# auxiliares
# ---------------------------------------------------------------------------

def perto(obtido, esperado, tol=0.01, abs_min=0.006, o_que=""):
    """Compara com 1 % de tolerância e um piso absoluto.

    O piso de 0,006 é o arredondamento do próprio manual: ele publica as pressões
    com duas casas (±0,005) e as calcula com o q já arredondado (0,88 em vez de
    0,8834; 0,94 em vez de 0,9419), o que desloca mais 0,4 % cada valor.
    """
    limite = max(tol * abs(esperado), abs_min)
    assert abs(obtido - esperado) <= limite, (
        f"{o_que}: obtido {obtido:.4f}, manual {esperado:.4f} "
        f"(diferença {abs(obtido - esperado):.4f} > {limite:.4f})")


def vento_exemplo_5_1():
    """Galpão do Exemplo 5.1: b = 20 m, a = 60 m, h = 7 m, θ = 10°, V0 = 40 m/s."""
    return cg.pressoes_galpao(b=20.0, a=60.0, h=7.0, theta_graus=10.0,
                              V0=40.0, categoria="II", classe="B", z=7.0,
                              S1=1.0, grupo=2, aberturas="duas faces opostas")


def vento_cap16():
    """Galpão do Capítulo 16: b = 20 m, a = 40 m, h = 6 m, θ = 5,71°, S2 a 10 m."""
    return cg.pressoes_galpao(b=20.0, a=40.0, h=6.0, theta_graus=5.71,
                              V0=40.0, categoria="II", classe="B", S2=0.98,
                              S1=1.0, grupo=2, aberturas="duas faces opostas")


# ===========================================================================
# 1. Ações permanentes e variáveis (NBR 6120:2019)
# ===========================================================================

def test_tabela_de_pesos_e_sobrecargas():
    """Tabelas 5.1 e 5.2 do manual, consultadas por nome."""
    assert cg.peso("telha metálica simples").valor == 0.05
    assert cg.peso("sanduíche").valor == 0.15                  # alias sem acento também
    assert cg.peso("SANDUICHE").valor == 0.15
    assert cg.peso("fibrocimento").faixa == (0.18, 0.25)
    assert cg.peso("alvenaria cerâmica 14 cm").valor == 2.00
    assert cg.peso("revestimento de piso").valor == 1.00

    assert cg.sobrecarga("cobertura sem acesso").valor == 0.25
    assert cg.sobrecarga("residencial").valor == 1.50
    assert cg.sobrecarga("escritório").valor == 2.50
    assert cg.sobrecarga("loja").valor == 4.00
    assert cg.sobrecarga("depósito").valor == 7.50
    assert cg.sobrecarga("garagem").valor == 3.00
    assert cg.sobrecarga("escada com acesso ao público").valor == 3.00
    assert cg.sobrecarga("mezanino industrial").valor == 5.00
    # ψ da Tabela 2 da NBR 8800 associado ao uso
    assert cg.psi(cg.sobrecarga("cobertura sem acesso").psi) == (0.8, 0.7, 0.6)
    assert cg.psi(cg.sobrecarga("escritório").psi) == (0.7, 0.6, 0.4)

    perto(cg.peso_laje_steel_deck(12.0), 2.55, o_que="laje steel deck 12 cm")
    perto(cg.peso_laje_steel_deck(15.0), 3.10, o_que="laje steel deck 15 cm")
    perto(cg.peso_laje_macica(12.0), 3.00, o_que="laje maciça 12 cm")

    try:
        cg.peso("telha de palha")
    except ErroDeDados as e:
        assert "desconhecido" in str(e)
    else:
        raise AssertionError("esperava ErroDeDados para elemento inexistente")


def test_peso_proprio_cobertura_cap16():
    """Manual, item 16.2.1: telha 0,05 + terças 0,05 + acessórios 0,05 = 0,15 kN/m²."""
    c = cg.peso_proprio_cobertura("telha metálica simples")
    perto(c.total, 0.15, o_que="peso próprio da cobertura (16.2.1)")
    assert len(c.itens) == 3, "a composição deve ficar discriminada no memorial"
    assert abs(sum(i.valor for i in c.itens) - c.total) < 1e-12
    assert all(i.fonte for i in c.itens), "cada parcela cita a sua fonte"
    assert "0,15" in c.texto()
    assert len(c.passos()) == 4                       # 3 parcelas + total

    # com forro e instalações a composição cresce, e continua discriminada
    d = cg.peso_proprio_cobertura("sanduíche", com_forro=True, instalacoes=0.10)
    perto(d.total, 0.15 + 0.05 + 0.05 + 0.20 + 0.10, o_que="cobertura com forro")

    # Exemplo 5.2: telha de 0,08 kN/m² informada pelo fabricante
    e = cg.peso_proprio_cobertura("telha metálica simples", valor_telha=0.08,
                                  com_tercas=False, com_acessorios=False)
    perto(e.total, 0.08, o_que="telha do Exemplo 5.2")


def test_area_de_influencia():
    """Manual, item 5.2.3: kN/m² × largura da faixa = kN/m."""
    perto(cg.por_metro(0.08, 1.60), 0.128, o_que="telha por metro de terça")
    perto(cg.por_metro(0.25, 1.60), 0.40, o_que="sobrecarga por metro de terça")
    perto(cg.carga_de_parede("alvenaria cerâmica 14 cm", 3.0), 6.0, o_que="parede sobre viga")


# ===========================================================================
# 2. Vento — NBR 6123
# ===========================================================================

def test_velocidade_basica():
    """Tabela 5.4 do manual (leitura do mapa de isopletas)."""
    assert cg.velocidade_basica("Porto Alegre") == 46
    assert cg.velocidade_basica("porto alegre") == 46
    assert cg.velocidade_basica("Belo Horizonte") == 32
    assert cg.velocidade_basica("Recife") == 30
    assert cg.velocidade_basica("Brasília") == 35
    assert cg.velocidade_basica(40) == 40.0            # V0 informado direto
    for entrada in ("Hogwarts", 15.0):
        try:
            cg.velocidade_basica(entrada)
        except ErroDeDados:
            pass
        else:
            raise AssertionError(f"esperava ErroDeDados para {entrada!r}")


def test_fator_s1():
    """NBR 6123, item 5.2 (manual, item 5.4.2)."""
    assert cg.fator_s1("plano") == 1.0
    assert cg.fator_s1("vale") == 0.9
    # manual: morro de 30 m com θ = 10°, ponto junto ao topo → S1 ≈ 1,3
    perto(cg.fator_s1("morro", theta_graus=10.0, z=0.0, d=30.0), 1.307,
          o_que="S1 na crista de morro de 10°")
    # θ ≤ 3° não acelera o vento; o acréscimo se anula para z ≥ 2,5·d
    assert cg.fator_s1("talude", theta_graus=2.0, z=0.0, d=30.0) == 1.0
    assert cg.fator_s1("talude", theta_graus=10.0, z=80.0, d=30.0) == 1.0
    # θ ≥ 45°: S1 = 1 + (2,5 − z/d)·0,31
    perto(cg.fator_s1("morro", theta_graus=45.0, z=0.0, d=20.0), 1.775, o_que="S1 com θ = 45°")
    try:
        cg.fator_s1("montanha russa")
    except ErroDeDados:
        pass
    else:
        raise AssertionError("esperava ErroDeDados para relevo desconhecido")


def test_fator_s2_tabela_5_5():
    """Tabela 5.5 do manual: S2 = b·Fr·(z/10)^p para as categorias II, III e IV."""
    esperado = {
        # z  : (II-A, II-B, III-A, III-B, IV-A, IV-B)
        5:  (0.94, 0.92, 0.88, 0.86, 0.79, 0.76),
        10: (1.00, 0.98, 0.94, 0.92, 0.86, 0.83),
        15: (1.04, 1.02, 0.98, 0.96, 0.90, 0.88),
        20: (1.06, 1.04, 1.01, 0.99, 0.93, 0.91),
        30: (1.10, 1.08, 1.05, 1.03, 0.98, 0.96),
    }
    casos = [("II", "A"), ("II", "B"), ("III", "A"), ("III", "B"), ("IV", "A"), ("IV", "B")]
    for z, linha in esperado.items():
        for (cat, cl), valor in zip(casos, linha):
            obtido = cg.fator_s2(cat, cl, z)
            assert round(obtido, 2) == valor, (
                f"S2 cat {cat} classe {cl} z = {z} m: obtido {obtido:.4f} "
                f"(arredondado {round(obtido, 2)}), manual {valor}")
            perto(obtido, valor, o_que=f"S2 {cat}-{cl} z={z}")

    # abaixo de 5 m a norma mantém o valor de 5 m (a favor da segurança)
    assert cg.fator_s2("II", "B", 3.0) == cg.fator_s2("II", "B", 5.0)
    # categoria informada como número e classe pela maior dimensão
    perto(cg.fator_s2(2, "B", 10.0), 0.98, o_que="S2 com categoria numérica")
    assert cg.classe_por_dimensao(15.0) == "A"
    assert cg.classe_por_dimensao(40.0) == "B"
    assert cg.classe_por_dimensao(60.0) == "C"
    for entrada in (("VI", "B", 10.0), ("II", "D", 10.0), ("II", "B", 400.0)):
        try:
            cg.fator_s2(*entrada)
        except ErroDeDados:
            pass
        else:
            raise AssertionError(f"esperava ErroDeDados para {entrada}")


def test_fator_s3_e_pressao_dinamica():
    """Tabela 5.6 do manual e q = 0,613·Vk² (NBR 6123, item 4.2)."""
    assert cg.fator_s3(1) == 1.10
    assert cg.fator_s3(2) == 1.00
    assert cg.fator_s3(3) == 0.95
    assert cg.fator_s3(4) == 0.88
    assert cg.fator_s3(5) == 0.83
    # regras de bolso do capítulo 5: 40 m/s ≈ 1 kN/m²; 30 ≈ 0,55; 45 ≈ 1,25
    perto(cg.pressao_dinamica(40.0), 0.981, o_que="q para Vk = 40 m/s")
    perto(cg.pressao_dinamica(30.0), 0.552, o_que="q para Vk = 30 m/s")
    perto(cg.pressao_dinamica(45.0), 1.241, o_que="q para Vk = 45 m/s")


def test_coeficiente_pressao_interna():
    """Tabela 5.8 do manual (NBR 6123, item 6.2)."""
    casos = cg.coeficiente_pressao_interna("duas faces opostas")
    assert [c.valor for c in casos] == [0.2, -0.3]
    assert [c.valor for c in cg.coeficiente_pressao_interna("quatro faces permeáveis")] == [-0.3, 0.0]
    assert [c.valor for c in cg.coeficiente_pressao_interna("estanque")] == [-0.2, 0.0]
    # abertura dominante a barlavento: 1 / 1,5 / 2 / 3 / ≥ 6 → +0,1 / +0,3 / +0,5 / +0,6 / +0,8
    for razao, valor in ((1.0, 0.1), (1.5, 0.3), (2.0, 0.5), (3.0, 0.6), (6.0, 0.8), (10.0, 0.8)):
        obtido = cg.coeficiente_pressao_interna("abertura dominante a barlavento",
                                                razao_areas=razao)[0].valor
        perto(obtido, valor, abs_min=1e-9, o_que=f"Cpi com razão {razao}")
    # interpolação entre os pontos tabelados
    perto(cg.coeficiente_pressao_interna("abertura dominante a barlavento",
                                         razao_areas=2.5)[0].valor, 0.55,
          abs_min=1e-9, o_que="Cpi interpolado (razão 2,5)")
    # abertura dominante a sotavento: Cpi = Ce da face onde está a abertura
    perto(cg.coeficiente_pressao_interna("abertura dominante a sotavento",
                                         ce_face=-0.3)[0].valor, -0.3,
          abs_min=1e-9, o_que="Cpi de abertura a sotavento")
    try:
        cg.coeficiente_pressao_interna("abertura dominante a barlavento")
    except ErroDeDados:
        pass
    else:
        raise AssertionError("abertura dominante sem razão de áreas deve falhar explicitamente")


def test_exemplo_5_1_fatores_e_pressao_dinamica():
    """Exemplo 5.1, passos 1 a 3: S2 = 0,949; Vk ≈ 38 m/s; q = 0,88 kN/m²."""
    v = vento_exemplo_5_1()
    assert v.S1 == 1.0 and v.S3 == 1.0
    perto(v.S2, 0.949, o_que="S2 do Exemplo 5.1")
    perto(v.Vk, 37.96, o_que="Vk do Exemplo 5.1")
    perto(v.q, 0.883, o_que="q do Exemplo 5.1")         # manual: 883 N/m² = 0,88 kN/m²
    assert v.coeficientes.h_b == 0.35 and v.coeficientes.a_b == 3.0
    assert len(v.passos) >= 8 and all(p.norma for p in v.passos)


def test_exemplo_5_1_pressoes_por_face():
    """Exemplo 5.1, Tabela 5.9: pressões efetivas (Ce − Cpi)·q nos dois sentidos.

    A linha da parede de sotavento a 0° é tratada no teste da divergência abaixo.
    """
    v = vento_exemplo_5_1()
    T, L = "transversal", "longitudinal"               # 0° e 90° na notação do cap. 5
    esperado = [
        # (superfície, direção, Ce, p com Cpi=+0,2, p com Cpi=−0,3)
        ("parede lateral barlavento", T, +0.7, +0.44, +0.88),
        ("oitão zona 1", T, -0.9, -0.97, -0.53),
        ("oitão zona 2", T, -0.5, -0.62, -0.18),
        ("telhado barlavento", T, -1.2, -1.23, -0.79),
        ("telhado sotavento", T, -0.4, -0.53, -0.09),
        ("oitão barlavento", L, +0.7, +0.44, +0.88),
        ("oitão sotavento", L, -0.3, -0.44, 0.00),
        ("parede lateral zona 1", L, -0.8, -0.88, -0.44),
        ("parede lateral zona 2", L, -0.4, -0.53, -0.09),
        ("telhado zona 1", L, -0.8, -0.88, -0.44),
        ("telhado zona 2", L, -0.6, -0.70, -0.26),
    ]
    for sup, dire, ce, p_mais, p_menos in esperado:
        c = v.coeficientes.busca(sup, dire)
        perto(c.Ce, ce, abs_min=1e-9, o_que=f"Ce de {sup} ({dire})")
        perto(v.pressao(sup, dire, +0.2), p_mais, o_que=f"p de {sup} ({dire}) com Cpi = +0,2")
        perto(v.pressao(sup, dire, -0.3), p_menos, o_que=f"p de {sup} ({dire}) com Cpi = −0,3")

    # Passo 7 do exemplo: a maior sucção da estrutura é 1,23 kN/m² na água de barlavento
    critica = v.critica()
    assert critica.superficie == "telhado barlavento"
    perto(critica.p, -1.23, o_que="maior sucção do Exemplo 5.1")
    # e é dez vezes o peso próprio da cobertura (0,13 kN/m² no exemplo)
    assert abs(critica.p) > 8 * 0.13


def test_exemplo_5_1_divergencia_parede_de_sotavento():
    """DIVERGÊNCIA — parede lateral de sotavento com vento perpendicular à cumeeira.

    Cap. 5 (Tabelas 5.7 e 5.9 e Figura 5.8) adota Ce = −0,3 para a parede maior de
    sotavento, o que dá p = −0,44 / 0,00 kN/m².
    Cap. 16 (Tabela 16.2, mesmo galpão baixo, h/b ≤ 1/2 e a/b na faixa 2–4) adota
    Ce = −0,5 para a mesma face, e a Tabela 16.2 é internamente consistente com a
    Tabela 4 da NBR 6123: para o vento na face maior a edificação é "rasa"
    (profundidade b menor que a frente a) e a sucção de sotavento é maior; o valor
    −0,3 é o da face de sotavento na **outra** direção (oitão D, edificação
    "profunda"). O cap. 5 aparentemente repetiu −0,3 nas duas direções.

    Este módulo segue o cap. 16 / NBR 6123 (Ce = −0,5). A conta:
        Ce = −0,5 → (−0,5 − 0,2)·0,8834 = −0,618 kN/m²   (cap. 5 daria −0,44)
                    (−0,5 + 0,3)·0,8834 = −0,177 kN/m²   (cap. 5 daria  0,00)
    A escolha é a favor da segurança: a sucção de sotavento soma-se à pressão de
    barlavento na força horizontal total do pórtico.
    """
    v = vento_exemplo_5_1()
    c = v.coeficientes.busca("parede lateral sotavento", "transversal")
    assert c.Ce == -0.5
    perto(v.pressao("parede lateral sotavento", "transversal", +0.2), -0.618,
          o_que="parede de sotavento com Cpi = +0,2 (valor do cap. 16)")
    perto(v.pressao("parede lateral sotavento", "transversal", -0.3), -0.177,
          o_que="parede de sotavento com Cpi = −0,3 (valor do cap. 16)")
    # o valor do cap. 5 (−0,44) fica 30 % abaixo — fora de qualquer tolerância
    assert abs(-0.618 - (-0.44)) / 0.618 > 0.25


def test_exemplo_5_1_abertura_dominante():
    """Exemplo 5.1, passos 5 e 7: portão do oitão aberto → Cpi = +0,5.

    Manual: telhado a 90° com Cpi = +0,5 → −1,14 (EG) e −0,97 (FH); com o
    coeficiente local de borda (Ce = −1,2) chega a −1,50 kN/m².
    """
    v = cg.pressoes_galpao(b=20.0, a=60.0, h=7.0, theta_graus=10.0, V0=40.0,
                           categoria="II", classe="B", z=7.0,
                           aberturas="abertura dominante a barlavento", razao_areas=2.0)
    assert [c.valor for c in v.casos_cpi] == [0.5]
    perto(v.pressao("telhado zona 1", "longitudinal", 0.5), -1.14,
          o_que="telhado EG com portão aberto")
    perto(v.pressao("telhado zona 2", "longitudinal", 0.5), -0.97,
          o_que="telhado FH com portão aberto")
    perto(cg.pressao_efetiva(-1.2, 0.5, v.q), -1.50,
          o_que="borda do telhado (Ce local −1,2) com portão aberto")


def test_cap16_vento():
    """Capítulo 16, item 16.2.2 e Tabela 16.2: q = 0,94 kN/m² e pressões do pórtico."""
    v = vento_cap16()
    perto(v.S2, 0.98, o_que="S2 adotado no cap. 16 (valor a 10 m)")
    perto(v.Vk, 39.2, o_que="Vk do cap. 16")
    perto(v.q, 0.942, o_que="q do cap. 16")            # manual: 942 N/m² = 0,94 kN/m²
    # o S2 calculado no topo real (7 m) confere com o 0,95 citado no texto
    perto(cg.fator_s2("II", "B", 7.0), 0.95, o_que="S2 a 7 m (cap. 16)")

    T, L = "transversal", "longitudinal"
    # Tabela 16.2 — Ce adotados (θ = 5,71°, h/b = 0,3, a/b = 2)
    perto(v.coeficientes.busca("parede lateral barlavento", T).Ce, +0.7, abs_min=1e-9,
          o_que="Ce parede barlavento")
    perto(v.coeficientes.busca("parede lateral sotavento", T).Ce, -0.5, abs_min=1e-9,
          o_que="Ce parede sotavento")
    perto(v.coeficientes.busca("oitão zona 1", T).Ce, -0.9, abs_min=1e-9, o_que="Ce C1/D1")
    perto(v.coeficientes.busca("oitão zona 2", T).Ce, -0.5, abs_min=1e-9, o_que="Ce C2/D2")
    perto(v.coeficientes.busca("telhado barlavento", T).Ce, -0.95, o_que="Ce EF interpolado")
    perto(v.coeficientes.busca("telhado sotavento", T).Ce, -0.4, abs_min=1e-9, o_que="Ce GH")
    perto(v.coeficientes.busca("parede lateral zona 1", L).Ce, -0.8, abs_min=1e-9, o_que="Ce A1/B1")
    perto(v.coeficientes.busca("parede lateral zona 2", L).Ce, -0.4, abs_min=1e-9, o_que="Ce A2/B2")
    perto(v.coeficientes.busca("oitão barlavento", L).Ce, +0.7, abs_min=1e-9, o_que="Ce C")
    perto(v.coeficientes.busca("oitão sotavento", L).Ce, -0.3, abs_min=1e-9, o_que="Ce D")
    perto(v.coeficientes.busca("telhado zona 1", L).Ce, -0.8, abs_min=1e-9, o_que="Ce EG")
    # DIVERGÊNCIA de critério (não de valor tabelado): a Tabela 16.2 adota FH = −0,4,
    # que é o valor de θ = 5° da Tabela 5, sem interpolar — embora interpole a água de
    # barlavento (EF) no mesmo ângulo. Interpolando FH entre θ = 5° (−0,4) e θ = 10°
    # (−0,6), como este módulo faz em todas as zonas, vem −0,4 + (0,71/5)·(−0,2) = −0,43.
    # Adotamos o valor interpolado, coerente com o EF do próprio cap. 16 e a favor da
    # segurança (sucção 7 % maior). A face só entra no vento longitudinal, que no cap. 16
    # não governa o pórtico — nenhuma pressão publicada na Tabela 16.2 é afetada.
    perto(v.coeficientes.busca("telhado zona 2", L).Ce, -0.428, o_que="Ce FH interpolado")

    # Tabela 16.2 — pressões efetivas (kN/m²)
    esperado = [
        ("parede lateral barlavento", T, +0.47, +0.94),
        ("parede lateral sotavento", T, -0.66, -0.19),
        ("telhado barlavento", T, -1.08, -0.61),
        ("telhado sotavento", T, -0.56, -0.09),
        ("oitão barlavento", L, +0.47, +0.94),
        ("oitão sotavento", L, -0.47, 0.00),
    ]
    for sup, dire, p_mais, p_menos in esperado:
        perto(v.pressao(sup, dire, +0.2), p_mais, o_que=f"{sup} ({dire}) com Cpi = +0,2")
        perto(v.pressao(sup, dire, -0.3), p_menos, o_que=f"{sup} ({dire}) com Cpi = −0,3")

    # cantos das paredes (faixa ≈ 0,2·b), Ce = −1,0 → −1,13 e −0,66
    perto(v.pressao("canto de parede", T, +0.2), -1.13, o_que="canto de parede com Cpi = +0,2")
    perto(v.pressao("canto de parede", T, -0.3), -0.66, o_que="canto de parede com Cpi = −0,3")

    # Figura 16.4: a força horizontal total no pórtico é a mesma nos dois casos de Cpi
    h_mais = v.pressao("parede lateral barlavento", T, +0.2) - v.pressao(
        "parede lateral sotavento", T, +0.2)
    h_menos = v.pressao("parede lateral barlavento", T, -0.3) - v.pressao(
        "parede lateral sotavento", T, -0.3)
    perto(h_mais, 1.13, o_que="força horizontal com Cpi = +0,2")
    perto(h_menos, 1.13, o_que="força horizontal com Cpi = −0,3")
    perto(h_mais, h_menos, o_que="a força horizontal total independe do Cpi")


def test_cap16_cargas_por_portico():
    """Capítulo 16, item 16.2.3: cargas características por pórtico (faixa de 5 m)."""
    v = vento_cap16()
    # g_k = 0,15 × 5 + 0,33 = 1,08 kN/m ; q_k = 0,25 × 5 = 1,25 kN/m
    g = cg.por_metro(cg.peso_proprio_cobertura("telha metálica simples").total, 5.0) + 0.33
    perto(g, 1.08, o_que="g_k por pórtico")
    perto(cg.por_metro(cg.sobrecarga("cobertura sem acesso").valor, 5.0), 1.25,
          o_que="q_k por pórtico")
    # vento na água de barlavento: 1,08 kN/m² × 5 m = 5,40 kN/m (Tabela 16.3)
    perto(cg.por_metro(abs(v.pressao("telhado barlavento", "transversal", 0.2)), 5.0), 5.40,
          o_que="vento EF por pórtico")
    perto(cg.por_metro(abs(v.pressao("telhado sotavento", "transversal", 0.2)), 5.0), 2.82,
          o_que="vento GH por pórtico")
    perto(cg.por_metro(abs(v.pressao("parede lateral barlavento", "transversal", 0.2)), 5.0),
          2.35, o_que="vento na parede de barlavento por pórtico")
    perto(cg.por_metro(abs(v.pressao("parede lateral sotavento", "transversal", 0.2)), 5.0),
          3.29, o_que="vento na parede de sotavento por pórtico")
    # o item 16.10 usa (0,7 + 0,3)·q = 0,94 kN/m² no oitão para o portal de vento
    perto(v.pressao("oitão barlavento", "longitudinal", -0.3), 0.94, o_que="vento no oitão")


def test_limites_dos_coeficientes():
    """Falha explícita nos casos que as Tabelas 4 e 5 não cobrem."""
    for args in (dict(b=20, a=60, h=40, theta_graus=10),      # h/b = 2 > 3/2
                 dict(b=20, a=60, h=7, theta_graus=75),       # θ > 60°
                 dict(b=60, a=20, h=7, theta_graus=10)):      # a < b
        try:
            cg.coeficientes_pressao_galpao(**args)
        except ErroDeDados:
            pass
        else:
            raise AssertionError(f"esperava ErroDeDados para {args}")
    # a faixa intermediária de h/b é aceita, mas avisa que não foi validada
    c = cg.coeficientes_pressao_galpao(b=20, a=40, h=14, theta_graus=10)
    assert any("h/b entre 1/2 e 3/2" in o for o in c.observacoes)
    # a/b > 4 usa a coluna 2–4, com aviso de extrapolação
    c = cg.coeficientes_pressao_galpao(b=20, a=120, h=7, theta_graus=10)
    assert any("extrapolação" in o for o in c.observacoes)
    # coeficientes locais existem, mas ficam fora da lista estrutural
    assert all(not x.local for x in c.estruturais())
    assert any(x.local and x.Ce == -2.0 for x in c.coeficientes)


# ===========================================================================
# 3. Combinações — NBR 8681 e NBR 8800
# ===========================================================================

def test_tabelas_de_coeficientes():
    """Tabelas 5.10 e 5.11 do manual (NBR 8800, Tabelas 1 e 2)."""
    assert cg.gama_f("permanente", "metálica") == 1.25
    assert cg.gama_f("permanente", "metálica", favoravel=True) == 1.00
    assert cg.gama_f("permanente", "metálica", "construção") == 1.15
    assert cg.gama_f("permanente", "moldada no local") == 1.35
    assert cg.gama_f("permanente", "geral") == 1.50
    assert cg.gama_f("permanente", "indireta", favoravel=True) == 0.0
    assert cg.gama_f("vento") == 1.40
    assert cg.gama_f("vento", combinacao="especiais") == 1.20
    assert cg.gama_f("variavel", "sobrecarga") == 1.50
    assert cg.gama_f("variavel", "temperatura") == 1.20
    assert cg.psi("residencial") == (0.5, 0.4, 0.3)
    assert cg.psi("comercial") == (0.7, 0.6, 0.4)
    assert cg.psi("depósito") == (0.8, 0.7, 0.6)
    assert cg.psi("cobertura") == (0.8, 0.7, 0.6)
    assert cg.psi("vento") == (0.6, 0.3, 0.0)
    assert cg.psi("ponte rolante") == (1.0, 0.8, 0.5)


def acoes_da_terca():
    """Exemplo 5.2 — terça Ue 200, s = 1,60 m, vão 6,0 m, na água de barlavento."""
    return [
        cg.Acao("PP", "permanente", 0.21, subtipo="metálica"),       # telha 0,128 + terça 0,08
        cg.Acao("SC", "variavel", 0.40, subtipo="sobrecarga", psi="cobertura"),
        cg.Acao("Vento", "vento", -1.97),                            # −1,23 kN/m² × 1,60 m
    ]


def test_exemplo_5_2_combinacoes_da_terca():
    """Exemplo 5.2: gravitacional +3,8 kN·m contra sucção −11,5 kN·m."""
    combs = cg.combinacoes_ultimas(acoes_da_terca())
    assert len(combs) == 2, "uma combinação gravitacional e uma de sucção"
    grav, suc = combs[0], combs[1]

    # Combinação 1 — gravitacional, SC principal: 1,25×0,21 + 1,5×0,40 = 0,86 kN/m
    perto(grav.total, 0.86, o_que="combinação gravitacional (Exemplo 5.2)")
    assert grav.expressao == "1,25·PP + 1,5·SC"
    assert grav.principal == "SC"

    # Combinação 2 — sucção, vento principal e PP favorável: 1,0×0,21 − 1,4×1,97 = −2,55 kN/m
    perto(suc.total, -2.55, o_que="combinação de sucção (Exemplo 5.2)")
    assert suc.expressao == "1,0·PP + 1,4·Vento (sucção)"
    assert suc.titulo.startswith("C2: 1,0·PP + 1,4·Vento (sucção)")
    assert suc.principal == "Vento (sucção)"
    # a sobrecarga de manutenção alivia a sucção, logo não entra (manual, comb. 3)
    assert "SC" not in suc.expressao

    # Momentos da terça biapoiada, vão de 6 m, com a decomposição de cos 10°
    L, cos10 = 6.0, math.cos(math.radians(10.0))
    perto(grav.total * cos10 * L ** 2 / 8, 3.8, o_que="M gravitacional da terça")
    perto(suc.total * L ** 2 / 8, -11.5, o_que="M de sucção da terça")
    # a inversão de esforço: três vezes maior e de sinal contrário
    assert suc.total * grav.total < 0
    assert abs(suc.total) / abs(grav.total) > 2.9


def test_permanente_favoravel_usa_gama_1():
    """O ponto que mais causa erro em galpões: γ_g = 1,0 quando o PP alivia.

    Na combinação de levantamento o peso próprio segura a cobertura: ele é
    favorável e não pode ser majorado (NBR 8800, Tabela 1; manual, item 5.6.1).
    """
    combs = cg.combinacoes_ultimas(acoes_da_terca())
    grav, suc = combs[0], combs[1]

    parcela_pp_grav = [p for p in grav.parcelas if p.acao == "PP"][0]
    parcela_pp_suc = [p for p in suc.parcelas if p.acao == "PP"][0]
    assert parcela_pp_grav.gama == 1.25, "PP desfavorável na gravitacional"
    assert parcela_pp_grav.papel == "permanente desfavorável"
    assert parcela_pp_suc.gama == 1.00, "PP favorável na sucção → γ_g = 1,0"
    assert parcela_pp_suc.papel == "permanente favorável"

    # o resultado é sucção líquida: o vento levanta a cobertura
    assert suc.total < 0
    perto(suc.total, -2.55, o_que="sucção líquida com PP favorável")

    # majorar o PP (erro clássico) reduziria a sucção em ~5 %: o teste registra a conta
    errado = 1.25 * 0.21 - 1.4 * 1.97
    assert errado > suc.total                       # menos sucção = a favor da insegurança
    perto(errado, -2.495, o_que="conta errada com PP majorado")

    # e a envoltória aponta a combinação de sucção como a crítica
    maxima, minima = cg.envoltoria(combs)
    assert minima is suc and maxima is grav
    assert cg.critica(combs) is suc


def test_permanente_favoravel_sem_variavel_no_sentido():
    """Só peso próprio: o sentido negativo produz a combinação com γ_g = 1,0."""
    acoes = [cg.Acao("PP", "permanente", 1.08, subtipo="metálica")]
    combs = cg.combinacoes_ultimas(acoes)
    assert [round(c.total, 4) for c in combs] == [1.35, 1.08]
    assert combs[1].parcelas[0].gama == 1.0


def test_cap16_combinacoes_do_portico():
    """Capítulo 16, Tabela 16.3: C1 = 3,39; C2 com γ_g = 1,0; C3 com ψ0 = 0,7."""
    # o cap. 16 adota γ_g = 1,4 simplificadamente (telhas + estrutura) — Tabela 16.1
    g = cg.Acao("G", "permanente", 1.08, subtipo="industrializado com adições")
    q = cg.Acao("Q", "variavel", 1.25, subtipo="sobrecarga", psi="comercial")   # ψ0 = 0,7
    combs = cg.combinacoes_ultimas([g, q])
    perto(combs[0].total, 3.39, o_que="C1 = 1,4 G + 1,5 Q (cap. 16)")
    assert combs[0].expressao == "1,4·G + 1,5·Q"

    # C2 — sucção com Cpi = +0,2: vertical 1,0·G e vento normal ao telhado
    v = vento_cap16()
    w_ef = cg.por_metro(v.pressao("telhado barlavento", "transversal", 0.2), 5.0)
    c2 = cg.combinacoes_ultimas([g, q, cg.Acao("V", "vento", w_ef)], sentidos=("-",))[0]
    assert [p for p in c2.parcelas if p.acao == "G"][0].gama == 1.0
    perto([p for p in c2.parcelas if p.acao == "V (sucção)"][0].contribuicao, -7.57,
          o_que="1,4 × 5,40 = 7,57 kN/m (Tabela 16.3)")
    perto(c2.total, 1.08 - 7.57, o_que="C2 líquido na água de barlavento")

    # C3 — vento + gravidade com a sobrecarga reduzida por ψ0 = 0,7 (1,5 × 0,7 = 1,05)
    c3 = cg.combinacoes_ultimas([g, q], sentidos=("+",))[0]
    combs3 = cg.combinacoes_ultimas(
        [g, q, cg.Acao("V", "vento", 1.0)], sentidos=("+",))
    c3_vento = [c for c in combs3 if c.principal.startswith("V")][0]
    parcela_q = [p for p in c3_vento.parcelas if p.acao == "Q"][0]
    perto(parcela_q.coef, 1.05, abs_min=1e-9, o_que="1,5 × 0,7 = 1,05 (ψ0 da sobrecarga)")
    perto(parcela_q.contribuicao, 1.3125, o_que="1,05 × 1,25 kN/m")
    perto(c3.total + 0, 1.4 * 1.08 + 1.5 * 1.25, o_que="C1 conferida")


def test_combinacoes_tipicas_com_ponte_rolante():
    """Manual, item 5.7.1: ponte rolante entra com ψ0 = 1,0 nas combinações com vento."""
    acoes = [cg.Acao("PP", "permanente", 1.0, subtipo="metálica"),
             cg.Acao("PR", "variavel", 2.0, subtipo="ponte rolante"),
             cg.Acao("V", "vento", 1.5)]
    combs = cg.combinacoes_ultimas(acoes, sentidos=("+",))
    # ponte rolante principal: 1,25·PP + 1,5·PR + 1,4·0,6·V
    perto(combs[0].total, 1.25 * 1.0 + 1.5 * 2.0 + 1.4 * 0.6 * 1.5, o_que="PR principal")
    assert combs[0].expressao == "1,25·PP + 1,5·PR + 1,4·0,6·V"
    # vento principal: 1,25·PP + 1,4·V + 1,5·1,0·PR  (ψ0 = 1,0 para ponte rolante)
    parcela_pr = [p for p in combs[1].parcelas if p.acao == "PR"][0]
    assert parcela_pr.papel.startswith("variável secundária")
    assert parcela_pr.psi == 1.0, "ψ0 da ponte rolante é 1,0 (Tabela 2 da NBR 8800)"
    perto(combs[1].total, 1.25 * 1.0 + 1.4 * 1.5 + 1.5 * 1.0 * 2.0, o_que="vento principal")
    # combinações de construção usam os γ reduzidos da Tabela 1
    constr = cg.combinacoes_ultimas(acoes, tipo="construção", sentidos=("+",))
    assert constr[0].expressao == "1,15·PP + 1,3·PR + 1,2·0,6·V"


def test_combinacoes_servico():
    """Combinações de serviço do Exemplo 5.2 (ELS, γ_f = 1,0)."""
    combs = cg.combinacoes_servico(acoes_da_terca())
    por_nome = {(c.tipo, c.principal): c for c in combs}

    # manual: flecha gravitacional com PP + SC → q = 0,61 kN/m
    rara_grav = por_nome[("serviço rara", "SC")]
    perto(rara_grav.total, 0.61, o_que="combinação rara gravitacional (Exemplo 5.2)")
    # manual: flecha por sucção (combinação rara) → q = 1,97 − 0,21 = 1,76 kN/m
    rara_suc = por_nome[("serviço rara", "Vento (sucção)")]
    perto(rara_suc.total, -1.76, o_que="combinação rara de sucção (Exemplo 5.2)")
    assert rara_suc.expressao == "1,0·PP + 1,0·Vento (sucção)"

    # frequente com vento: ψ1 = 0,3 (usada no deslocamento horizontal, cap. 16)
    freq_suc = por_nome[("serviço frequente", "Vento (sucção)")]
    perto(freq_suc.total, 0.21 - 0.3 * 1.97, o_que="combinação frequente de sucção")
    assert "0,3·Vento (sucção)" in freq_suc.expressao
    # quase permanente: ψ2 = 0 para o vento e 0,6 para sobrecarga de cobertura
    qp = [c for c in combs if c.tipo == "serviço quase permanente"]
    perto(qp[0].total, 0.21 + 0.6 * 0.40, o_que="quase permanente (ψ2 = 0,6)")

    # cap. 16: deslocamento com vento integral × ψ1 = 0,3 → 0,3 × 6,2 = 1,86 cm, que o
    # manual arredonda para 1,9 cm ≤ H/300 = 2,0 cm
    perto(0.3 * 6.2, 1.9, tol=0.03, o_que="deslocamento horizontal com ψ1 = 0,3")


def test_memoria_de_calculo():
    """Cada combinação sabe se explicar — é isso que o memorial imprime."""
    suc = cg.combinacoes_ultimas(acoes_da_terca())[1]
    assert suc.titulo == "C2: 1,0·PP + 1,4·Vento (sucção)"
    passos = suc.passos("kN/m")
    assert len(passos) == len(suc.parcelas) + 1
    assert all(p.norma for p in passos)
    assert "1,4 × -1,970" in passos[1].conta or "1,4 × −1,970" in passos[1].conta
    assert "2,548 kN/m" in passos[-1].valor
    assert sum(p.contribuicao for p in suc.parcelas) == suc.total

    v = vento_exemplo_5_1()
    texto = " ".join(p.conta + p.valor for p in v.passos)
    assert "0,613" in texto and "m/s" in texto
    assert any("NBR 6123" in p.norma for p in v.passos)
    assert v.tabela() and all("p (kN/m²)" in linha for linha in v.tabela())


def test_erros_de_dados():
    """Entrada inconsistente falha explicitamente, em português (princípio 4)."""
    for chamada in (lambda: cg.Acao("X", "esquisita", 1.0),
                    lambda: cg.Acao("X", "permanente", 1.0, subtipo="madeira laminada"),
                    lambda: cg.combinacoes_ultimas([]),
                    lambda: cg.combinacoes_ultimas([cg.Acao("G", "permanente", 1.0)],
                                                   tipo="mágicas"),
                    lambda: cg.combinacoes_servico([cg.Acao("G", "permanente", 1.0)],
                                                   tipos=("eventual",)),
                    lambda: cg.por_metro(1.0, 0.0),
                    lambda: cg.pressao_dinamica(-3.0)):
        try:
            chamada()
        except ErroDeDados as e:
            assert str(e), "a mensagem de erro não pode ser vazia"
        else:
            raise AssertionError("esperava ErroDeDados")


def test_catalogo_para_a_interface():
    d = cg.listar()
    for chave in ("pesos", "sobrecargas", "cidades", "categorias_s2", "grupos_s3",
                  "gama_g", "gama_q", "psi", "aberturas"):
        assert d[chave], f"catálogo vazio: {chave}"
    assert d["gama_g"]["metálica"]["normais"] == 1.25
    assert d["psi"]["vento"]["psi0"] == 0.6


# ---------------------------------------------------------------------------
# execução direta: python testes/test_cargas.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    testes = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f)]
    falhas = 0
    for nome, func in testes:
        try:
            func()
            print(f"  ok   {nome}")
        except Exception as exc:                      # noqa: BLE001
            falhas += 1
            print(f"  FALHA {nome}: {exc}")
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
