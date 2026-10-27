# -*- coding: utf-8 -*-
"""As folhas do projetista no Original (usuário, 27/10, GER-04 — Posto CB: o Layout1 do DXF com as 15 pranchas R02, 64
janelas, carimbo e notas, não entrava no 2D; só o espaço do modelo): o espaço do papel desenhado como sai na impressão."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import dxf_ler as L  # noqa: E402
from nucleo2d import folhas_papel as FP  # noqa: E402


def _dxf(entidades):
    return ("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
            "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n"
            "0\nLAYER\n5\n10\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n"
            "0\nLAYER\n5\n11\n2\nDESLIGADA\n70\n0\n62\n-3\n6\nCONTINUOUS\n"
            "0\nLAYER\n5\n12\n2\nSO_NA_JANELA\n70\n0\n62\n4\n6\nCONTINUOUS\n"
            "0\nLAYER\n5\n13\n2\nDEFPOINTS\n70\n0\n62\n7\n6\nCONTINUOUS\n290\n0\n"
            "0\nENDTAB\n0\nENDSEC\n"
            "0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n%s0\nENDSEC\n0\nEOF\n") % entidades


def _janela(id_, cx, cy, w, h, vcx, vcy, alvo, altura_vista, giro=0.0, congeladas=()):
    s = "0\nVIEWPORT\n8\n0\n67\n1\n10\n%s\n20\n%s\n40\n%s\n41\n%s\n68\n1\n69\n%d\n12\n%s\n22\n%s\n17\n%s\n27\n%s\n45\n%s\n51\n%s\n" % (
        cx, cy, w, h, id_, vcx, vcy, alvo[0], alvo[1], altura_vista, giro)
    return s + "".join("341\n%s\n" % hd for hd in congeladas)


MODELO = ("0\nLINE\n8\n0\n10\n0\n20\n300\n11\n2000\n21\n300\n"          # passa da janela: cortada na borda
          "0\nCIRCLE\n8\n0\n10\n500\n20\n500\n40\n100\n"                  # inteiro dentro
          "0\nTEXT\n8\n0\n10\n5000\n20\n5000\n40\n50\n1\nLONGE\n"           # fora da janela: não aparece
          "0\nLINE\n8\nDESLIGADA\n10\n400\n20\n400\n11\n600\n21\n400\n"      # camada desligada: não sai na folha
          "0\nLINE\n8\nDEFPOINTS\n10\n400\n20\n450\n11\n600\n21\n450\n"      # camada que não plota
          "0\nLINE\n8\nSO_NA_JANELA\n10\n400\n20\n600\n11\n600\n21\n600\n")  # congelada só na janela 3
PAPEL = ("0\nLINE\n8\n0\n67\n1\n10\n0\n20\n0\n11\n420\n21\n0\n"
         "0\nTEXT\n8\n0\n67\n1\n10\n10\n20\n10\n40\n2.5\n1\nCARIMBO R02\n"
         + _janela(1, 210, 148, 420, 297, 0, 0, (0, 0), 297)                    # a janela da própria folha
         + _janela(2, 100, 100, 100, 100, 0, 0, (500, 500), 1000))              # 1:10, mostra x e y de 0 a 1000


def _folhas(texto, escala=1.0, desl=(0.0, 0.0)):
    des, r = FP.para_desenho(texto, escala=escala, deslocamento=desl)
    return list(des.entidades.values()), r, des


def test_janela_mostra_o_modelo_na_escala_cortado_na_borda():
    ents, r, _ = _folhas(_dxf(MODELO + PAPEL))
    assert [f["janelas"] for f in r["folhas"]] == [1]
    textos = {e.texto: e for e in ents if e.tipo == "texto"}
    # o papel entra como está (a folha começa no canto de baixo da caixa dela: x 0, y 0)
    assert "CARIMBO R02" in textos and textos["CARIMBO R02"].altura == pytest.approx(2.5)
    assert textos["CARIMBO R02"].posicao == pytest.approx((10.0, 10.0))
    # o círculo (500, 500) r 100 vai ao centro da janela, r 10
    (c,) = [e for e in ents if e.tipo == "circulo"]
    assert c.centro == pytest.approx((100.0, 100.0)) and c.raio == pytest.approx(10.0)
    # a linha y 300 de x 0 a 2000: no papel y 80, de x 50 a 250 — cortada na borda da janela (x 150)
    corte = [e for e in ents if e.tipo == "linha" and abs(e.a[1] - 80) < 1e-6]
    assert len(corte) == 1 and sorted([corte[0].a[0], corte[0].b[0]]) == pytest.approx([50.0, 150.0])
    # fora da janela, camada desligada e camada que não plota: nada
    assert "LONGE" not in textos
    assert not any(abs(e.a[1] - 90) < 1e-6 or abs(e.a[1] - 95) < 1e-6 for e in ents if e.tipo == "linha")
    # tudo marcado como da folha do projetista
    assert all(e.atributos.get("origem") == "dxf-papel" for e in ents)


def test_escala_do_desenho_e_deslocamento():
    """num desenho 1:50 a folha cresce 50× (a letra fica com a altura de papel) e começa no deslocamento"""
    ents, r, _ = _folhas(_dxf(MODELO + PAPEL), escala=50, desl=(1e6, -2e5))
    t = [e for e in ents if e.tipo == "texto" and e.texto == "CARIMBO R02"][0]
    assert t.posicao == pytest.approx((1e6 + 500.0, -2e5 + 500.0)) and t.altura == pytest.approx(2.5)
    (c,) = [e for e in ents if e.tipo == "circulo"]
    assert c.centro == pytest.approx((1e6 + 5000.0, -2e5 + 5000.0)) and c.raio == pytest.approx(500.0)
    assert r["folhas"][0]["caixa"][:2] == pytest.approx((1e6, -2e5))


def test_mapa_da_janela_leva_o_modelo_ao_desenho():
    """o resumo traz a conta modelo → desenho de cada janela (o vínculo 2D ↔ 3D vai às vistas da folha impressa, ADM
    27/10): o ponto do modelo cai onde a folha o desenhou"""
    ents, r, _ = _folhas(_dxf(MODELO + PAPEL), escala=50, desl=(1e6, -2e5))
    (m,) = r["folhas"][0]["mapas"]
    assert m["janela"] == 2 and m["modelo"] == pytest.approx((0.0, 0.0, 1000.0, 1000.0))
    a, b, c, d, tx, ty = m["transformacao"]
    (circ,) = [e for e in ents if e.tipo == "circulo"]
    assert (a * 500 + b * 500 + tx, c * 500 + d * 500 + ty) == pytest.approx(circ.centro)
    assert math.hypot(a, c) == pytest.approx(5.0)                 # 1:10 num desenho 1:50: o modelo × 5


def _com_plotagem(texto, janela_plot, tipo=4):
    """o DXF com o bloco *Paper_Space (registro 1DF) e o LAYOUT que aponta para ele, plotando por "Janela" (tipo 4)"""
    bloco = ("0\nBLOCK\n5\n1E1\n330\n1DF\n100\nAcDbEntity\n67\n1\n8\n0\n100\nAcDbBlockBegin\n2\n*Paper_Space\n70\n0\n"
             "10\n0\n20\n0\n0\nENDBLK\n5\n1E2\n330\n1DF\n8\n0\n")
    layout = ("0\nSECTION\n2\nOBJECTS\n0\nLAYOUT\n5\n1E0\n330\n1A\n100\nAcDbPlotSettings\n1\n\n48\n%s\n49\n%s\n140\n%s\n141\n%s\n"
              "74\n%d\n100\nAcDbLayout\n1\nLayout1\n330\n1DF\n0\nENDSEC\n") % (tuple(janela_plot) + (tipo,))
    return texto.replace("2\nBLOCKS\n", "2\nBLOCKS\n" + bloco).replace("0\nEOF\n", layout + "0\nEOF\n")


def test_folha_cortada_na_janela_de_plotagem():
    """ADM Hora Certa (27/10): o layout da 900 plota por "Janela" (a A0 de 156 a 1345 mm do papel); 340 mm de papel à
    esquerda, fora da impressão, entravam na folha. A folha é o retângulo impresso e o que passa dele é cortado"""
    texto = _com_plotagem(_dxf(MODELO + PAPEL), (100.0, -5.0, 420.0, 297.0))
    assert L.ler_dxf(texto)["layouts"]["1DF"] == {"nome": "Layout1", "tipo_plot": 4, "janela_plot": (100.0, -5.0, 420.0, 297.0)}
    ents, r, _ = _folhas(texto)
    textos = {e.texto for e in ents if e.tipo == "texto"}
    assert "CARIMBO R02" not in textos                               # x 10 no papel: fora do que foi impresso
    assert r["folhas"][0]["caixa"] == pytest.approx((0.0, 0.0, 320.0, 302.0))
    # a linha do papel y 0, de x 0 a 420: de 100 a 420 → no desenho de 0 a 320, y 5
    base = [e for e in ents if e.tipo == "linha" and abs(e.a[1] - 5.0) < 1e-6]
    assert len(base) == 1 and sorted([base[0].a[0], base[0].b[0]]) == pytest.approx([0.0, 320.0])
    # a linha do modelo y 300 na janela (papel x 50 a 150) só de 100 a 150: no desenho de 0 a 50, y 85
    corte = [e for e in ents if e.tipo == "linha" and abs(e.a[1] - 85.0) < 1e-6]
    assert len(corte) == 1 and sorted([corte[0].a[0], corte[0].b[0]]) == pytest.approx([0.0, 50.0])
    # plotagem por "Layout" (tipo 5) ou sem LAYOUT: a folha inteira, como antes
    ents5, r5, _ = _folhas(_com_plotagem(_dxf(MODELO + PAPEL), (100.0, -5.0, 420.0, 297.0), tipo=5))
    assert "CARIMBO R02" in {e.texto for e in ents5 if e.tipo == "texto"}


def test_camada_congelada_so_naquela_janela():
    papel = PAPEL + _janela(3, 300, 100, 100, 100, 0, 0, (500, 500), 1000, congeladas=("12",))
    ents, r, _ = _folhas(_dxf(MODELO + papel))
    # a linha y 600 da SO_NA_JANELA: na janela 2 (papel y 110), não na 3
    ys = [e for e in ents if e.tipo == "linha" and e.camada == "SO_NA_JANELA"]
    assert len(ys) == 1 and ys[0].atributos.get("janela") == 2


def test_giro_da_janela_como_a_ezdxf():
    ezdxf = pytest.importorskip("ezdxf")
    v = {"tipo": "VIEWPORT", "c": (300.0, 200.0), "w": 120.0, "h": 80.0, "id": 2, "status": 1,
         "centro_vista": (40.0, -25.0), "alvo": (1000.0, 2000.0), "altura_vista": 800.0, "giro": 270.0}
    doc = ezdxf.new()
    vp = doc.layout("Layout1").add_viewport(center=v["c"], size=(v["w"], v["h"]), view_center_point=v["centro_vista"],
                                            view_height=v["altura_vista"])
    vp.dxf.view_target_point = (*v["alvo"], 0)
    vp.dxf.view_twist_angle = v["giro"]
    M = vp.get_transformation_matrix()
    T = FP._janela_para_papel(v)
    for p in ((1000, 2000), (1500, 1700), (0, 0)):
        q = M.transform((p[0], p[1], 0))
        assert T.ap(p) == pytest.approx((q.x, q.y), abs=1e-6)
    # a caixa do modelo enquadrada volta exatamente ao retângulo da janela no papel
    x0, y0, x1, y1 = FP.janela_no_modelo(v)
    cantos = [T.ap(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    assert min(c[0] for c in cantos) == pytest.approx(240.0) and max(c[0] for c in cantos) == pytest.approx(360.0)
    assert min(c[1] for c in cantos) == pytest.approx(160.0) and max(c[1] for c in cantos) == pytest.approx(240.0)


def test_ole_entra_como_contorno_com_aviso_e_layout_vazio_nao_vira_folha():
    ole = "0\nOLE2FRAME\n8\n0\n67\n1\n10\n200\n20\n250\n11\n400\n21\n150\n"
    ents, r, _ = _folhas(_dxf(PAPEL + ole))
    oles = [e for e in ents if e.atributos.get("ole")]
    assert {e.tipo for e in oles} == {"polilinha", "texto"}
    so_folha = _dxf(_janela(1, 210, 148, 420, 297, 0, 0, (0, 0), 297))
    assert FP.para_desenho(so_folha)[1]["folhas"] == []


def test_recortar_polilinha_e_hachura():
    from nucleo2d.desenho import Polilinha, Hachura
    r = (0.0, 0.0, 10.0, 10.0)
    p = Polilinha(camada="X", vertices=[(-5, 5), (5, 5), (5, 15), (8, 15), (8, 5), (15, 5)], fechada=False)
    trechos = L.recortar(p, r)
    assert len(trechos) == 2                                    # sai por cima e volta: dois pedaços
    h = Hachura(camada="X", contornos=[[(-5, -5), (5, -5), (5, 5), (-5, 5)]], padrao="solido")
    (hc,) = L.recortar(h, r)
    xs = [q[0] for q in hc.contornos[0]]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(5.0)
