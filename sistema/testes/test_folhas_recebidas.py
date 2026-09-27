# -*- coding: utf-8 -*-
"""As folhas do projeto recebido (nucleo2d/folhas_recebidas.py): número e título de cada folha,
carimbo e considerações de cálculo lidos do espaço do papel do DXF — como no Posto CB."""
from nucleo2d import folhas_recebidas as F
from nucleo3d import esforcos


def _texto(x, y, t, h=2.5, papel=True):
    return "0\nTEXT\n8\nCARIMBO\n%s10\n%s\n20\n%s\n40\n%s\n1\n%s\n" % ("67\n1\n" if papel else "", x, y, h, t)


def _moldura(x0, y0, w, h):
    pts = "".join("10\n%s\n20\n%s\n" % p for p in ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)))
    return "0\nLWPOLYLINE\n8\nFOLHA\n67\n1\n90\n4\n70\n1\n%s" % pts


def _folha(x0, numero, titulo):
    """uma folha A0 com o carimbo no canto de baixo à direita (as posições do carimbo do Posto)"""
    fx, fy = x0 + 1150, 40
    s = _moldura(x0, 0, 1189, 841)
    for dx, dy, t in ((5, 11, "FOLHA"), (0, 0, numero), (-83, -5, titulo), (-125, 5, "PROJETO ESTRUTURAL METÁLICO"),
                      (3, 47, "DESENHO"), (2, 43, "ITAMAR"), (4, 39, "ESCALA"), (1, 35, "INDICADA"),
                      (6, 31, "DATA"), (2, 27, "21/07/26"), (4, 23, "REVISÃO"), (6, 19, "R02"),
                      (-137, 44, "CLIENTE:"), (-127, 44, "CONSTRUTORA ROSA DOS VENTOS"),
                      (-137, 34, "OBRA:"), (-127, 34, "POSTO DE COMBUSTIVEL EM ESTRUTURA METÁLICA"),
                      (-137, 25, "LOCAL:"), (-126, 26, "AV. AMÉRICO BELAY"), (-126, 22, "MARINGÁ PR"),
                      (-36, 56, "ITAMAR FÉLIX DA SILVA"), (-33, 54, "ENG. CIVIL-CREA PR 71.683/D"),
                      (-31, -19, "MET_PE_PHD_POSTO.dxf")):
        s += _texto(fx + dx, fy + dy, t)
    # as considerações de cálculo, acima do carimbo
    cx, cy = fx - 143, fy + 142
    for dx, dy, t in ((0, 0, "CONSIDERAÇÕES DE CÁLCULO"), (1.7, -4.0, "1- PESO DAS TELHAS"), (69.4, -4.0, "5,00 KGF/M2"),
                      (1.7, -6.8, "2- PESO DO FORRO E INSTALAÇÕES"), (68.5, -6.8, "15,00 KGF/M2"),
                      (1.7, -9.7, "3- SOBRECARGA DE UTILIZAÇÃO"), (68.5, -9.7, "25,00 KGF/M2"),
                      (1.7, -12.6, "4- SOBRECARGA DE VENTO"), (68.6, -12.6, "45,00 M/S"),
                      (1.7, -22.1, "5- RESERVA PARA SOBRECARGA DE PAINÉIS SOLARES"), (68.5, -24.4, "17,00 KGF/M2"),
                      (1.9, 7.7, "7- NBR -  6120 (ABNT)  AÇÕES PARA O CÁLCULO DE ESTRUTURAS DE EDIFICAÇÕES / 2019"),
                      (1.9, 12, "PERFIS DOBRADOS:  AÇO ASTM A36;")):
        s += _texto(cx + dx, cy + dy, t)
    return s


def _dxf():
    corpo = _folha(0, "01/03", "LOCAÇÃO") + _folha(1300, "02/03", "PLANTA NO NÍVEL 6,00") + _folha(2600, "03/03", "CORTES")
    corpo += _texto(50, 50, "TEXTO DO MODELO", papel=False)
    return "0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n%s0\nENDSEC\n0\nEOF\n" % corpo


def test_folhas_carimbo_e_consideracoes_de_calculo():
    d = F.ler(_dxf())
    assert [(f["numero"], f["titulo"], f["formato"]) for f in d["folhas"]] == [
        ("01/03", "LOCAÇÃO", "A0"), ("02/03", "PLANTA NO NÍVEL 6,00", "A0"), ("03/03", "CORTES", "A0")]
    c = d["carimbo"]
    assert c["cliente"] == "CONSTRUTORA ROSA DOS VENTOS"
    assert c["obra"] == "POSTO DE COMBUSTIVEL EM ESTRUTURA METÁLICA"
    assert c["local"] == "AV. AMÉRICO BELAY — MARINGÁ PR"
    assert (c["revisao"], c["data"], c["responsavel"]) == ("R02", "21/07/26", "ITAMAR FÉLIX DA SILVA")
    assert {k: (v["valor"], v["unidade"]) for k, v in d["cargas"].items()} == {
        "telha": (5.0, "KGF/M2"), "forro": (15.0, "KGF/M2"), "sobrecarga": (25.0, "KGF/M2"),
        "vento": (45.0, "M/S"), "paineis": (17.0, "KGF/M2")}
    assert any("6120" in n for n in d["normas"]) and "PERFIS DOBRADOS:  AÇO ASTM A36;" in d["materiais"]


def test_cargas_do_projetista_no_calculo():
    projeto = {"projeto_recebido": dict(F.ler(_dxf()), arquivo="posto.dxf")}
    c = esforcos.cargas_do_projeto(projeto)
    assert c["telha"] == 0.049 and c["forro"] == 0.1471 and c["paineis"] == 0.1667 and c["sobrecarga"] == 0.2452
    assert c["v0"] == 45.0 and "projetista" in c["fonte"]
    assert esforcos.cargas_do_projeto({})["fonte"] == "padrão do programa"
