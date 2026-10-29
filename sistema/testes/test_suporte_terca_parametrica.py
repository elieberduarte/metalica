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
