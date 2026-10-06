# -*- coding: utf-8 -*-
"""O perfil que o IFC do Revit traz ("Família:Tipo:ID") cruzado com o catálogo, o tubo fora dele no similar,
o rótulo da chapa e a área do tubo na fatia (Bella Casa, 06/10)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo import catalogo as cat          # noqa: E402
from saida import detalhamento as det       # noqa: E402
from saida.resumos import rotulo_chapa      # noqa: E402


def test_nome_do_revit_vira_o_tipo():
    assert cat.nome_do_ifc("Vigas W Gerdau:W200X22.5:6474310") == "W200X22.5"
    assert cat.nome_do_ifc("CRV - Cortes retangulares vazados (sem emenda):RHS 127x76.2x6.35:6474177") == "RHS 127x76.2x6.35"
    assert cat.nome_do_ifc("U150X50X2.25") == "U150X50X2.25"


def test_do_ifc_acha_o_catalogo_e_o_similar():
    assert cat.do_ifc("Vigas W Gerdau:W200X15:1")["catalogo"] == "W 200×15,0"
    r = cat.do_ifc("X:RHS 127x76.2x6.35:1")
    assert r["catalogo"] == "TR 127×76×6,3" and r["fonte"] == "catálogo"
    for nome, esperado in (("SHS 225x225x6.4", "TQ 220×220×7,1"), ("SHS 110x110x3.2", "TQ 110×110×3,35"),
                           ("RHS 127x63.5x3.2", "TR 130×70×3,0")):
        r = cat.do_ifc("X:%s:1" % nome)
        assert r["fonte"] == "similar" and r["catalogo"] == esperado, (nome, r["catalogo"])
        # a geometria continua a do projeto: a seção e a área são as do IFC
        assert r["secao"][0] == float(nome.split()[1].split("x")[0])
    r = cat.do_ifc("X:CHS 406.4x12.5:1")
    assert r["fonte"] == "calculado" and not r["catalogo"] and abs(r["kg_m"] - 121.43) < 0.05


def test_rotulo_da_chapa():
    assert rotulo_chapa(3.0) == '#11 - 3,00mm - 1/8"'
    assert rotulo_chapa(19.1) == '19,10mm - 3/4"'
    assert rotulo_chapa(5.6) == "5,60mm"


def test_area_do_tubo_desconta_o_vazio():
    fora = [(0, 0), (127, 0), (127, 76.2), (0, 76.2)]
    t = 6.35
    dentro = [(t, t), (127 - t, t), (127 - t, 76.2 - t), (t, 76.2 - t)]
    area, cx, cy = det._area_e_centro([fora, dentro])
    assert abs(area - (127 * 76.2 - (127 - 2 * t) * (76.2 - 2 * t))) < 0.01
    assert abs(cx - 63.5) < 0.01 and abs(cy - 38.1) < 0.01
    assert det._externos([fora, dentro]) == 1


def test_trecho_reto_com_meia_esquadria_nao_e_curva():
    """Tubo 127×76 com as duas pontas a 30° (um trapézio, como o segmento da curva): reto, com o comprimento de
    ponta a ponta."""
    h, b, L, ang = 127.0, 76.0, 600.0, math.radians(30)
    d = h * math.tan(ang)
    sec = [(0, 0), (0, h), (b, h), (b, 0)]           # (z, y)
    v = [(y * math.tan(ang), y, z) for z, y in sec]                  # ponta da esquerda
    v += [(L + d - y * math.tan(ang), y, z) for z, y in sec]         # ponta da direita, inclinada para o outro lado
    f = [[0, 1, 2, 3][::-1], [4, 5, 6, 7]] + [[i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i] for i in range(4)]
    pos = det.Posicao(marca="B.1", tipo_ifc="IfcBeam", perfil="X:RHS 127x76x5:1", vertices=v, faces=f)
    det.analisar(pos)
    assert pos.classe == "barra", (pos.classe, pos.observacoes)
    assert abs(pos.comprimento - (L + d)) < 2, pos.comprimento


def test_chapa_vai_para_a_comercial():
    from saida.resumos import chapa_comercial, _chapas_por_rotulo
    assert chapa_comercial(3.0) == 3.0 and chapa_comercial(19.1) == 19.05
    assert chapa_comercial(10.3) == 12.7 and chapa_comercial(5.6) == 6.3      # nunca mais fina que o projeto
    g = _chapas_por_rotulo([{"espessura": 10.0, "material": "A36", "peso": 78.5, "pecas": 2, "area_m2": 1.0},
                            {"espessura": 11.2, "material": "A36", "peso": 87.9, "pecas": 1, "area_m2": 1.0}])
    assert len(g) == 1 and g[0]["polegada"] == '1/2"' and g[0]["modelo"] == '10,00mm, 11,20mm (≈7/16")'
    from saida.resumos import fracao_polegada
    assert fracao_polegada(5.6) == '7/32"' and fracao_polegada(8.9) == "" and fracao_polegada(25.4) == '1"'
    assert abs(g[0]["kg_compra"] - 2.0 * 12.7 * 7.85) < 0.01 and abs(g[0]["kg"] - 166.4) < 0.01


def test_parecidos_e_troca_na_lista():
    r = cat.parecidos("X:SHS 225x225x6.4:1")
    assert r["automatico"] == "TQ 220×220×7,1" and r["itens"][0]["atende"]
    assert all(not x["atende"] for x in r["itens"] if x["nome"].startswith("TQ 220×220×6,4"))
    from saida.lista_producao import trocar_na_lista
    lista = {"perfis": [{"perfil": "SHS 225x225x6.4", "material": "A36", "comprimento_m": 2.0, "peso": 86.2, "kg_m": 43.1}],
             "posicoes": [{"perfil": "X:SHS 225x225x6.4:1", "material": "A36", "classe": "Barra", "categoria": "BARRAS",
                           "comprimento": 1000, "quantidade": 2, "peso": 43.1, "peso_total": 86.2}],
             "totais": {"peso": 86.2, "categorias": [{"categoria": "BARRAS", "peso": 86.2, "pct": 100.0}]}}
    trocar_na_lista(lista, {"SHS 225x225x6.4": "TQ 240×240×6,4"})
    g = lista["perfis"][0]
    assert g["catalogo"] == "TQ 240×240×6,4" and g["fonte_kg_m"] == "escolhido" and abs(g["peso"] - 92.2) < 0.01
    assert abs(lista["totais"]["peso"] - 92.2) < 0.01
    trocar_na_lista(lista, {})                                                   # volta ao automático (o similar)
    assert lista["perfis"][0]["catalogo"] == "TQ 220×220×7,1" and abs(lista["perfis"][0]["peso"] - 93.2) < 0.01


def test_forma_no_fim_do_nome():
    """"250x250x10SHS" (a Passarela Mirante do Revit): a forma vem depois das medidas."""
    r = cat.do_ifc("Pilar:250x250x10SHS:1")
    assert r and r["catalogo"].startswith("TQ 250×250×10") and r["secao"] == (250.0, 250.0)
    assert cat.do_ifc("X:406.4x12.5CHS:1")["fonte"] == "calculado"
