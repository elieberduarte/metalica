# -*- coding: utf-8 -*-
"""O suporte de terça no passo da máquina quando a terça é barra paramétrica (gerada pela planta) e o suporte é chapa do
gerador sem marca de posição (Posto CB V2, 29/10/2026: os 398 ST1/ST2 ficavam com o par a 40/60 mm do projeto, as 77
terças "fora do passo da máquina" travavam as pranchas, e o DXF de corte dos ST saía com os furos do projetista — a
decisão de 27/10 é o passo da fábrica, 50 mm na altura). ajustar_suportes_as_tercas só via a terça do IFC (Solido) e a
chapa com marca de posição."""
from nucleo3d.modelo import Barra, Chapa, Documento
from nucleo2d.detalhe.celulas import ajustar_suportes_as_tercas


def _terca_e_suporte():
    doc = Documento()
    t = Barra(nome="TC14", inicio=(0.0, 0.0, 1000.0), fim=(3000.0, 0.0, 1000.0), perfil="U 100×40×2,65", papel="terça")
    t.camada = "Terças"
    t.atributos = {"marcas": {"posicao": "P1512"}}
    doc.add(t)
    # o ST1 do detalhe do projeto: 150 × 90, dois pares a 40 na altura e 80 ao longo da terça, centrados nela
    st = Chapa(nome="Suporte de terça ST1", origem=(1425.0, 0.0, 955.0), eixo_x=(1.0, 0.0, 0.0), eixo_y=(0.0, 0.0, 1.0),
               contorno=[(0.0, 0.0), (150.0, 0.0), (150.0, 90.0), (0.0, 90.0)], espessura=3.0, centrada=True,
               furos=[{"x": x, "y": y, "largura": 25.0, "altura": 12.7} for x in (35.0, 115.0) for y in (25.0, 65.0)])
    doc.add(st)
    return doc, st


def test_suporte_do_gerador_vai_ao_passo_da_maquina_na_terca_parametrica():
    doc, st = _terca_e_suporte()
    r = ajustar_suportes_as_tercas(doc, {"P1512"}, {"Suporte de terça ST1"})
    assert r["chapas"] == 1, r
    ys = sorted({round(f["y"], 1) for f in st.furos})
    assert ys == [20.0, 70.0], st.furos                     # 50 na altura, centrados no eixo da terça (z 1000)
    assert sorted({f["x"] for f in st.furos}) == [35.0, 115.0]   # ao longo da terça, o da ligação


def test_sem_a_terca_marcada_nada_muda():
    doc, st = _terca_e_suporte()
    assert ajustar_suportes_as_tercas(doc, {"OUTRA"}, {"Suporte de terça ST1"})["chapas"] == 0
    assert sorted({f["y"] for f in st.furos}) == [25.0, 65.0]


def test_suporte_na_ponta_da_linha_de_tercas_fica_com_as_duas_colunas_iguais():
    """Posto V2, 29/10/2026: a terça acaba entre as duas colunas do ST1 (o suporte da ponta da linha) e só a coluna dentro
    dela ia ao passo da máquina — a chapa ia ao corte com uma coluna a 50 e a outra a 40 (37 suportes)."""
    doc, st = _terca_e_suporte()
    t = doc.barras[0]
    t.fim = (1500.0, 0.0, 1000.0)                           # a terça acaba no meio do suporte (as colunas em 1460 e 1540)
    assert ajustar_suportes_as_tercas(doc, {"P1512"}, {"Suporte de terça ST1"})["chapas"] == 1
    for x in (35.0, 115.0):
        assert sorted(round(f["y"], 1) for f in st.furos if f["x"] == x) == [20.0, 70.0], st.furos


def test_suporte_sob_terca_muito_inclinada_vai_ao_passo_da_maquina():
    """Posto V2, 30/10/2026: o ST1 em x 49,71 / y 40,29 (a CH9 da relação de corte de 29/10) foi ao corte com o par a 40 do
    projeto — a T.C.133 em cima dele sobe 22 % (180 mm em 0,80 m), os dois furos da coluna vertical ficavam 8,8 mm um do
    outro ao longo da terça e cada um virava uma coluna sozinha. Agora a coluna da chapa é uma coluna só: os dois furos a 50
    na altura da terça e na mesma abscissa dela (como a máquina fura a terça)."""
    doc, st = _terca_e_suporte()
    t = doc.barras[0]
    t.inicio, t.fim = (0.0, 0.0, 1000.0 - 1500.0 * 0.225), (3000.0, 0.0, 1000.0 + 1500.0 * 0.225)
    assert ajustar_suportes_as_tercas(doc, {"P1512"}, {"Suporte de terça ST1"})["chapas"] == 1
    import math
    L = (1.0, 0.0, 0.225)
    n = math.hypot(*L)
    L = tuple(v / n for v in L)
    h = (-L[2], 0.0, L[0])                                  # na face da chapa, perpendicular à terça
    for x0 in (35.0, 115.0):
        col = [f for f in st.furos if abs(f["x"] - x0) < 15.0]
        assert len(col) == 2, st.furos
        pts = [(1425.0 + f["x"], 0.0, 955.0 + f["y"]) for f in col]
        s = [sum(p[k] * L[k] for k in range(3)) for p in pts]
        a = sorted(sum(p[k] * h[k] for k in range(3)) for p in pts)
        assert abs(s[0] - s[1]) < 0.5, col                  # na mesma abscissa da terça
        assert abs((a[1] - a[0]) - 50.0) < 0.5, col          # o passo da máquina


def test_letra_da_variante_depois_do_z():
    from nucleo2d.detalhe.base import letra_da_variante
    assert [letra_da_variante(i) for i in (1, 25, 26, 27, 52)] == ["b", "z", "aa", "ab", "ba"]
