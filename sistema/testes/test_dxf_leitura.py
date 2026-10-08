# -*- coding: utf-8 -*-
"""Leitura do DXF fiel ao AutoCAD (o executivo do Vicente Residence, 08/10: carimbo com balões no lugar dos cantos,
títulos dos desenhos sumidos, hachuras, splines e multileaders de fora, roscas espelhadas)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo2d import dxf_ler as L  # noqa: E402


def _dxf(entidades, blocos="", tabelas=""):
    return ("0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
            "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS\n"
            "0\nLAYER\n2\nPH\n70\n0\n62\n8\n6\nPHANTOM\n0\nLAYER\n2\nDS\n70\n0\n62\n1\n6\nDASHDOT\n0\nENDTAB\n%s0\nENDSEC\n"
            "0\nSECTION\n2\nBLOCKS\n%s0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n%s0\nENDSEC\n0\nEOF\n") % (tabelas, blocos, entidades)


def _ents(texto, tipo=None):
    des, resumo = L.para_desenho(texto, escala=1.0)
    ents = list(des.entidades.values())
    return [e for e in ents if tipo is None or e.tipo == tipo], resumo, des


def test_bulge_so_no_vertice_que_tem_arco():
    # retângulo 100 x 50 com só o canto de cima à direita arredondado (o 42 aparece só depois do 2º vértice)
    lw = ("0\nLWPOLYLINE\n8\n0\n90\n4\n70\n1\n10\n0\n20\n0\n10\n90\n20\n0\n42\n0.414213562\n10\n100\n20\n10\n10\n0\n20\n50\n")
    (p,), _, _ = _ents(_dxf(lw), "polilinha")
    xs, ys = [v[0] for v in p.vertices], [v[1] for v in p.vertices]
    # o arco de 90° fica no canto (90,0)-(100,10): nada sai da caixa 0..100 x 0..50
    assert min(xs) >= -1e-6 and max(xs) <= 100 + 1e-6 and min(ys) >= -1e-6 and max(ys) <= 50 + 1e-6
    # o lado de baixo continua reto até x = 90 e a diagonal de (100,10) a (0,50) também (sem arco)
    assert (0.0, 0.0) in p.vertices and (90.0, 0.0) in p.vertices and (100.0, 10.0) in p.vertices
    meio = [v for v in p.vertices if 90 < v[0] < 100]
    assert meio and all(v[1] < 10 for v in meio)


def test_titulo_sublinhado_do_mtext_nao_some():
    assert L.mtext_linhas(r"{\LCORTE A-A\P\H0.5x;\l\C1;ESC.: 1:50}", 200) == [("CORTE A-A", 1.0, None), ("ESC.: 1:50", 0.5, 1)]
    assert [l for l, _, _ in L.mtext_linhas(r"\pxql;{\fArial|b0|i0|c0|p34;VIGA SUPORTE ^JPAVIMENTO TIPO     }")] == \
        ["VIGA SUPORTE", "PAVIMENTO TIPO"]
    assert L.mtext_limpo(r"PARAF. %%c\S1/2;\U+0022 A325\~X") == 'PARAF. Ø1/2" A325 X'
    assert L.mtext_limpo(r"\H2.5;ALTURA ABSOLUTA") == "ALTURA ABSOLUTA"


def test_mtext_vira_uma_linha_por_paragrafo_com_altura_e_cor():
    mt = "0\nMTEXT\n8\n0\n10\n0\n20\n0\n40\n200\n41\n2000\n71\n1\n1\n{\\LCORTE A-A\\P\\H0.5x;\\l\\C1;ESC.: 1:50}\n"
    ts, _, _ = _ents(_dxf(mt), "texto")
    ts.sort(key=lambda t: -t.posicao[1])
    assert [t.texto for t in ts] == ["CORTE A-A", "ESC.: 1:50"]
    assert ts[0].altura == 200 and ts[1].altura == 100
    assert ts[1].atributos.get("cor") == L.CORES_ACI[1] and not ts[0].atributos.get("cor")
    assert math.isclose(ts[0].posicao[1] - ts[1].posicao[1], 5 / 3 * 200, abs_tol=1e-2)


def test_paragrafo_a_esquerda_encosta_na_borda_da_caixa():
    # inserção no centro de cima (71 = 2), largura 1000: o parágrafo \pxql; começa em x = −500
    mt = "0\nMTEXT\n8\n0\n10\n0\n20\n0\n40\n50\n41\n1000\n71\n2\n1\n\\pxql;VIGA\n"
    (t,), _, _ = _ents(_dxf(mt), "texto")
    assert t.alinhamento == "esquerda" and math.isclose(t.posicao[0], -500.0)


def test_hachura_solida_e_de_linhas():
    solida = ("0\nHATCH\n8\nPH\n10\n0\n20\n0\n30\n0\n210\n0\n220\n0\n230\n1\n2\nSOLID\n70\n1\n71\n0\n91\n2\n"
              "92\n3\n72\n0\n73\n1\n93\n3\n10\n0\n20\n0\n10\n10\n20\n0\n10\n0\n20\n10\n97\n0\n"
              "92\n3\n72\n0\n73\n1\n93\n3\n10\n10\n20\n0\n10\n10\n20\n10\n10\n0\n20\n10\n97\n0\n75\n0\n76\n1\n98\n0\n")
    linhas = ("0\nHATCH\n8\nDS\n10\n0\n20\n0\n30\n0\n210\n0\n220\n0\n230\n1\n2\nANSI31\n70\n0\n71\n0\n91\n1\n92\n1\n93\n4\n"
              "72\n1\n10\n0\n20\n0\n11\n20\n21\n0\n72\n1\n10\n20\n20\n0\n11\n20\n21\n40\n"
              "72\n1\n10\n20\n20\n40\n11\n0\n21\n40\n72\n1\n10\n0\n20\n40\n11\n0\n21\n0\n97\n0\n"
              "75\n1\n76\n1\n52\n0\n41\n0.684\n77\n0\n78\n1\n53\n45\n43\n0\n44\n0\n45\n-1.5\n46\n1.5\n79\n0\n98\n0\n")
    hs, resumo, _ = _ents(_dxf(solida + linhas), "hachura")
    assert not [k for k in resumo["por_tipo"] if k.startswith("ignorado")]
    s, l = sorted(hs, key=lambda h: h.padrao != "solido")
    assert s.padrao == "solido" and len(s.contornos) == 2 and all(len(c) == 3 for c in s.contornos)
    assert l.padrao == "aco" and math.isclose(l.angulo, 45.0) and math.isclose(l.espacamento, 3.175 * 0.684, rel_tol=1e-3)
    assert sorted(l.contornos[0]) == sorted([(0.0, 0.0), (20.0, 0.0), (20.0, 40.0), (0.0, 40.0)])


def test_hachura_com_arco_horario_no_contorno():
    # meio disco: diâmetro de (−10,0) a (10,0) e o arco por baixo, descrito no sentido horário (73 = 0)
    h = ("0\nHATCH\n8\n0\n2\nSOLID\n70\n1\n71\n0\n91\n1\n92\n1\n93\n2\n"
         "72\n1\n10\n-10\n20\n0\n11\n10\n21\n0\n72\n2\n10\n0\n20\n0\n40\n10\n50\n0\n51\n180\n73\n0\n97\n0\n75\n0\n76\n1\n98\n0\n")
    (hh,), _, _ = _ents(_dxf(h), "hachura")
    c = hh.contornos[0]
    assert min(y for _, y in c) < -9.9 and max(y for _, y in c) <= 1e-6       # o arco ficou embaixo
    # sem salto: cada ponto perto do seguinte (o arco começa onde a reta acaba)
    assert max(math.dist(c[i], c[(i + 1) % len(c)]) for i in range(len(c))) <= 20.0 + 1e-6


def test_elipse_com_a_normal_para_baixo():
    # meia elipse de cima (t de 0 a π) com a normal (0,0,−1): no AutoCAD ela fica embaixo
    el = "0\nELLIPSE\n8\n0\n10\n0\n20\n0\n11\n10\n21\n0\n210\n0\n220\n0\n230\n-1\n40\n0.5\n41\n0\n42\n3.14159265\n"
    (p,), _, _ = _ents(_dxf(el), "polilinha")
    assert min(y for _, y in p.vertices) < -4.9 and max(y for _, y in p.vertices) <= 1e-6


def test_arco_de_bloco_espelhado():
    bloco = ("0\nBLOCK\n8\n0\n2\nB\n70\n0\n10\n0\n20\n0\n30\n0\n"
             "0\nARC\n8\n0\n10\n0\n20\n0\n40\n10\n50\n0\n51\n90\n0\nENDBLK\n8\n0\n")
    ins = "0\nINSERT\n8\n0\n2\nB\n10\n100\n20\n0\n41\n-1\n42\n1\n50\n0\n"
    (a,), _, _ = _ents(_dxf(ins, bloco), "arco")
    # o quarto de círculo do 1º quadrante, espelhado em x, vai para o 2º: de 90° a 180°
    assert a.centro == (100.0, 0.0) and math.isclose(a.inicio, 90.0) and math.isclose(a.fim, 180.0)


def test_leader_com_seta_do_estilo_de_cota():
    est = "0\nTABLE\n2\nDIMSTYLE\n0\nDIMSTYLE\n2\nCOTA 1-50\n70\n0\n40\n50\n41\n2\n0\nENDTAB\n"
    ld = "0\nLEADER\n8\n0\n3\nCOTA 1-50\n71\n1\n76\n2\n10\n0\n20\n0\n10\n1000\n20\n0\n"
    ents, _, _ = _ents(_dxf(ld, tabelas=est))
    (seta,) = [e for e in ents if e.tipo == "hachura"]
    assert seta.padrao == "solido" and seta.contornos[0][0] == (0.0, 0.0)
    assert math.isclose(max(x for x, _ in seta.contornos[0]), 100.0)          # 2 × 50


def test_multileader_traz_texto_linha_e_seta():
    ml = ("0\nMULTILEADER\n8\n0\n100\nAcDbMLeader\n270\n2\n300\nCONTEXT_DATA{\n40\n1\n10\n100\n20\n100\n41\n50\n140\n50\n"
          "145\n10\n174\n1\n175\n1\n176\n2\n177\n0\n290\n1\n304\n%%c19mm\n11\n0\n21\n0\n31\n1\n12\n70\n22\n110\n171\n3\n"
          "302\nLEADER{\n290\n1\n291\n1\n10\n100\n20\n100\n11\n-1\n21\n0\n90\n0\n40\n25\n304\nLEADER_LINE{\n10\n300\n20\n0\n"
          "91\n0\n305\n}\n271\n0\n303\n}\n301\n}\n")
    ents, resumo, _ = _ents(_dxf(ml))
    assert not [k for k in resumo["por_tipo"] if k.startswith("ignorado")]
    (t,) = [e for e in ents if e.tipo == "texto"]
    assert t.texto == "Ø19mm" and t.altura == 50 and t.posicao == (70.0, 110.0) and t.alinhamento == "direita"
    linhas = sorted(tuple(e.vertices) if e.tipo == "polilinha" else (e.a, e.b) for e in ents if e.tipo in ("linha", "polilinha"))
    assert ((100.0, 100.0), (75.0, 100.0)) in linhas and ((300.0, 0.0), (100.0, 100.0)) in linhas
    (seta,) = [e for e in ents if e.tipo == "hachura"]
    assert seta.contornos[0][0] == (300.0, 0.0)


def test_spline_e_solid():
    sp = ("0\nSPLINE\n8\n0\n70\n8\n71\n3\n72\n8\n73\n4\n74\n0\n40\n0\n40\n0\n40\n0\n40\n0\n40\n1\n40\n1\n40\n1\n40\n1\n"
          "10\n0\n20\n0\n10\n10\n20\n10\n10\n20\n20\n10\n10\n30\n20\n0\n")
    so = "0\nSOLID\n8\n0\n10\n0\n20\n0\n11\n10\n21\n0\n12\n0\n22\n10\n13\n10\n23\n10\n"
    ents, _, _ = _ents(_dxf(sp + so))
    (p,) = [e for e in ents if e.tipo == "polilinha"]
    assert p.vertices[0] == (0.0, 0.0) and p.vertices[-1] == (30.0, 0.0)
    assert math.isclose(max(y for _, y in p.vertices), 7.5, abs_tol=0.05)    # Bézier cúbica: 3/4 da altura do controle
    (s,) = [e for e in ents if e.tipo == "hachura"]
    assert s.contornos[0] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]   # 1-2-4-3, sem cruzar


def test_tipo_de_linha_das_camadas_e_pontos_fora_do_aviso():
    pt = "0\nPOINT\n8\nPH\n10\n0\n20\n0\n0\nLINE\n8\nPH\n10\n0\n20\n0\n11\n1\n21\n0\n0\nLINE\n8\nDS\n10\n0\n20\n0\n11\n1\n21\n0\n"
    _, resumo, des = _ents(_dxf(pt))
    assert des.camadas["PH"].tipo_linha == "CENTER" and des.camadas["DS"].tipo_linha == "CENTER"
    assert L.tipo_de_linha("HIDDEN2") == "HIDDEN" and L.tipo_de_linha("DASHED") == "DASHED" and L.tipo_de_linha("Continuous") == "CONTINUOUS"
    assert not [k for k in resumo["por_tipo"] if k.startswith("ignorado")]
