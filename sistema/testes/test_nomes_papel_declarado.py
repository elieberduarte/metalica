# -*- coding: utf-8 -*-
"""O tipo de produção pelo papel que a barra declara no modelo (Kaefer, 19/10): no resumo da obra os chumbadores Ø20 da
base gerada por script saíam como "Contraventamentos" (o chumbamento não se fechava pela geometria) e as travessas da
lona (2U 127, papel longarina) como "Terças" de cobertura; o reforço Ue em pé do pilar redondo caía em Terças."""
from nucleo3d.modelo import Barra, Chapa, Documento
from nucleo2d.detalhar import levantar
from nucleo2d.detalhe.nomes import nomear
from saida import dossie


def _modelo(com_base=True):
    doc = Documento(nome="quadra")
    # dois pilares, a base de um com 4 chumbadores e uma travessa da lona a +4,00 entre eles
    for x in (0.0, 6000.0):
        doc.add(Barra(nome="P", inicio=(x, 0.0, 0.0), fim=(x, 0.0, 8000.0), perfil="W 460×52,0", papel="pilar"))
    if com_base:
        doc.add(Chapa(nome="CH base", origem=(0.0, 0.0, -16.0), contorno=[(-325, -225), (325, -225), (325, 225), (-325, 225)],
                      espessura=16.0, centrada=False,
                      furos=[{"x": fx, "y": fy, "diametro": 21.5} for fx in (-265, 265) for fy in (-165, 165)]))
    for fx in (-265.0, 265.0):
        for fy in (-165.0, 165.0):
            doc.add(Barra(nome="CB", inicio=(fx, fy, 65.0), fim=(fx, fy, -852.0), perfil="Barra redonda ø 20 mm",
                          papel="chumbador", atributos={"marca": "CB1", "elemento": "Chumbador"}))
    doc.add(Barra(nome="CV1", inicio=(0.0, 0.0, 0.0), fim=(6000.0, 0.0, 4000.0), perfil="Barra redonda ø 8 mm",
                  papel="contraventamento"))
    # o reforço do pilar redondo: Ue em pé, 3 m (sem papel) — não é terça
    doc.add(Barra(nome="RF1", inicio=(6000.0, 140.0, 0.0), fim=(6000.0, 140.0, 3000.0), perfil="Ue 150×60×20×2,00", papel=""))
    doc.add(Barra(nome="TR1", inicio=(225.0, 38.1, 4000.0), fim=(5775.0, 38.1, 4000.0), perfil="U 127×50×2,00 (FF)",
                  papel="longarina", camada="Travessas da lona"))
    return doc


def test_chumbador_e_longarina_pelo_papel_declarado():
    _conferir(_modelo())
    _conferir(_modelo(com_base=False))                   # sem a placa, o chumbamento não fecha pela geometria


def _conferir(doc):
    lev = levantar(doc)
    tipos = nomear(lev["posicoes"], lev["camadas"], lev["pecas"], [])["tipos"]
    por_perfil = {}
    for p in lev["posicoes"]:
        por_perfil.setdefault(p.perfil, set()).add(tipos.get(p.marca))
    assert por_perfil["Barra redonda ø 20 mm"] == {"chumbador"}
    assert por_perfil["U 127×50×2,00 (FF)"] <= {"terca_lateral", "terca_oitao"}
    assert por_perfil["Barra redonda ø 8 mm"] == {"contraventamento"}
    em_pe = [p for p in lev["posicoes"] if p.perfil == "Ue 150×60×20×2,00"]
    assert em_pe and all(lev["categorias"][p.marca] == "BARRAS" for p in em_pe)      # peça em pé não é terça
    # e no resumo da obra: o chumbador fora das barras da estrutura, a travessa nas longarinas de fechamento
    assert "chumbador" in dossie._FORA
    assert dossie._PAPEL_DO_TIPO["terca_lateral"] == "longarinas" == dossie._PAPEL_DO_TIPO["terca_oitao"]
