# -*- coding: utf-8 -*-
"""As placas de base pela locação e pelos detalhes "DET. DO CHn" (nucleo3d/bases_locacao.py; Posto CB, 22/10/2026: as 82
placas CH1–CH8 da LOC_01 e os 352 chumbadores, que o modelo não tinha)."""
import math

from nucleo3d import bases_locacao as BL
from nucleo3d.modelo import Barra, Documento


def _ret(x0, y0, w, h, camada="1-Metalica2"):
    return {"tipo": "polilinha", "fechada": True, "camada": camada,
            "vertices": [[x0, y0, 0], [x0 + w, y0, 0], [x0 + w, y0 + h, 0], [x0, y0 + h, 0]]}


def _txt(t, x, y, camada="REG60-100"):
    return {"tipo": "texto", "texto": t, "posicao": [x, y, 0], "camada": camada}


def _circ(x, y, r):
    return {"tipo": "circulo", "centro": [x, y, 0], "raio": r, "camada": "1-Metalica2"}


def _desenho():
    """dois detalhes como os da LOC_01 do Posto (vista de cima em tamanho real acima do título, a vista lateral com o
    chumbador e a cota do comprimento ao lado) e a locação: a CH1 desenhada girada com o texto "CH2" ao lado (o PIL-09 do
    Posto) e a CH5 só nomeada ao lado do pilar"""
    e = [_txt("DET. DO CH1-21X", 0, 0), _ret(120, 800, 400, 290)]
    e += [_circ(120 + x, 800 + y, 10.5) for x in (35, 365) for y in (35, 255)]
    e += [_txt('CHAPA # 3/8"', 220, 1130), _txt('2 Ø 5/8"', 150, 290), _txt('2 Ø 5/8"', 470, 290),
          _txt("400", 580, 350, "1-Cota"), _txt("400", 320, 620, "1-Cota")]
    e += [_txt("DET. DO CH5-3X", 3000, 0), _ret(3036, 367, 550, 550), _ret(3186, 517, 250, 250)]
    e += [_circ(3036 + x, 367 + y, 9) for x, y in ((35, 35), (275, 35), (515, 35), (35, 275), (515, 275), (35, 515), (275, 515), (515, 515))]
    e += [_txt('CHAPA # 5/8"', 3230, 935), _txt('3 Ø 3/4"', 3993, 460), _txt("500", 3904, 520, "1-Cota"),
          _txt("150", 3903, 845, "1-Cota")]
    # duas nervuras na vista de cima da CH5 (de pé, da face do pilar à borda) e o detalhe delas: 70 × 150, chanfro de 15
    e += [_ret(3036 + 5, 367 + 272, 70, 6.35, "1-Metalica1"), _ret(3036 + 475, 367 + 272, 70, 6.35, "1-Metalica1"),
          _txt("NERVURA 1", 3679, 953)]
    e += [_txt("NERVURA 1 - 6X", 6000, 0), _txt('CHAPA # 1/4"', 6151, 92),
          {"tipo": "polilinha", "fechada": True, "camada": "1-Metalica2",
           "vertices": [[6188, 233, 0], [6188, 368, 0], [6203, 368, 0], [6258, 233, 0], [6258, 218, 0], [6203, 218, 0]]}]
    # a locação: a CH1 em pé (290 ao longo de x), o texto que diz outra placa ao lado; a CH5 só pelo nome
    e += [_ret(10000 - 145, 10000 - 200, 290, 400, "Chapas"), _txt("CH2", 10000, 10350)]
    e += [_txt("CH5", 20400, 10300)]
    return e


def _pilares(doc):
    for x, y in ((10000.0, 9949.0), (10000.0, 10051.0), (20000.0 - 134.0, 10000.0), (20000.0 + 134.0, 10000.0)):
        b = Barra(nome="pilar", inicio=(x, y, 0.0), fim=(x, y, 6000.0), perfil="Ue 250×70×25×3,00", papel="pilar")
        b.atributos = {"origem": {"caixao": True}}
        doc.add(b)


def test_detalhes_como_o_projetista_desenha():
    d = BL.detalhes(_desenho())
    assert d["CH1"]["qtd"] == 21 and (d["CH1"]["B"], d["CH1"]["H"], d["CH1"]["t"]) == (400.0, 290.0, 9.53)
    assert len(d["CH1"]["furos"]) == 4 and d["CH1"]["chumbador"] == {"bitola": '5/8"', "d": 15.88, "L": 400.0, "n": 4}
    # a CH5: a vista lateral AO LADO da de cima, o furo do meio, o comprimento pela cota junto do texto do chumbador
    assert d["CH5"]["abertos"] == [(275.0, 275.0, 250.0, 250.0)] and len(d["CH5"]["furos"]) == 8
    assert d["CH5"]["chumbador"]["bitola"] == '3/4"' and d["CH5"]["chumbador"]["L"] == 500.0


def test_placas_e_chumbadores_no_modelo():
    ents = _desenho()
    doc = Documento()
    _pilares(doc)
    postas, chapas, avisos = [], [], []

    def barra(p0, p1, perfil, papel, camada, conjunto=None, rot=0.0, origem=None):
        b = Barra(nome=perfil, inicio=tuple(p0), fim=tuple(p1), perfil=perfil, papel=papel, camada=camada)
        b.atributos = {"origem": dict(origem or {})}
        doc.add(b)
        postas.append(b)
        return b
    dets = BL.detalhes(ents)
    folga = (5000.0, 5000.0, 30000.0, 30000.0)
    pl = BL.placas(ents, folga)
    assert len(pl) == 1                                  # os retângulos dos detalhes não são placas da locação
    pl += BL.placas_sem_contorno(pl, BL.rotulos(ents, folga), dets, doc, lambda p: p)
    r = BL.lancar(doc, pl, dets, lambda p: p, 0.0, "ASTM A36", barra, chapas, avisos, BL.nervuras(ents))
    assert r["placas"] == 2 and r["chumbadores"] == 12 and r["nervuras"] == 2, r
    ch1 = next(c for c in chapas if c.nome.endswith("CH1"))
    # a medida manda no nome; o texto "CH2" ao lado vira pergunta
    assert "diz CH2" in ch1.atributos["origem"]["a_conferir"]
    # o lado de 400 ao longo de y, como a locação desenha
    assert abs(abs(ch1.eixo_x[1]) - 1.0) < 1e-6 and ch1.contorno[2] == (400.0, 290.0)
    # os chumbadores de 5/8" × 400, de pé, nos furos (dentro da placa) e acima dela o bastante para as porcas
    c1 = [b for b in postas if b.atributos["origem"]["placa"] == "CH1"]
    assert len(c1) == 4 and all(abs(math.dist(b.inicio, b.fim) - 400.0) < 0.1 for b in c1)
    assert all(abs(b.inicio[0] - 10000.0) <= 110.0 + 0.1 and abs(b.inicio[1] - 10000.0) <= 165.0 + 0.1 for b in c1)
    assert all(b.inicio[2] > 9.53 + 15.88 for b in c1)
    # o pilar nasce em cima da placa
    assert all(abs(b.recorte_inicio - 9.53) < 1e-6 for b in doc.barras if b.papel == "pilar" and b.inicio[0] == 10000.0)
    # a CH5 centrada no caixão do pilar (o meio dos dois Ue), o furo desenhado menor que o chumbador abre para d + 1,5
    ch5 = next(c for c in chapas if c.nome.endswith("CH5"))
    cx = ch5.origem[0] + ch5.eixo_x[0] * 275.0 + ch5.eixo_y[0] * 275.0
    cy = ch5.origem[1] + ch5.eixo_x[1] * 275.0 + ch5.eixo_y[1] * 275.0
    assert math.dist((cx, cy), (20000.0, 10000.0)) < 0.5
    assert {f.get("diametro") for f in ch5.furos if f.get("diametro")} == {20.6}
    assert "só escreve CH5" in ch5.atributos["origem"]["a_conferir"]
    assert len([b for b in postas if b.atributos["origem"]["placa"] == "CH5"]) == 8
    # as nervuras: de pé em cima da placa, a ponta alta na face do pilar (a 75 mm da borda), para fora
    nv = [c for c in chapas if c.nome.startswith("Nervura")]
    assert len(nv) == 2 and all(abs(c.origem[2] - 15.88) < 1e-6 and c.eixo_y == (0.0, 0.0, 1.0) for c in nv)
    assert all(max(q[1] for q in c.contorno) == 150.0 and abs(c.espessura - 6.35) < 1e-6 for c in nv)
    assert sorted(round(math.dist(c.origem[:2], (20000.0, 10000.0))) for c in nv) == [200, 200]
    assert "a_conferir" not in nv[0].atributos["origem"]          # 6X para 3 placas: as 2 desenhadas em cada


def test_chapa_do_pe_do_pilar_inclinado():
    """a C1 do PM8 do Posto (DET. DA C1 - 4X: base 700, lado em pé 465, a hipotenusa na face de trás da perna a 50,9°, o
    topo perpendicular a ela com a altura da perna): uma em cada face do caixão, assentada na placa, e a perna começa no
    topo dela (decisão do usuário, 23/10/2026: segue a perna do 3D)"""
    ents = [{"tipo": "texto", "texto": "DET. DA C1 - 4X", "posicao": [0, 0, 0]},
            {"tipo": "texto", "texto": '# 3/16"', "posicao": [385, 487, 0]},
            {"tipo": "polilinha", "fechada": False,
             "vertices": [[709, 305, 0], [9, 305, 0], [515, 927, 0], [709, 770, 0], [709, 305, 0]]}]
    det = BL.detalhes_do_pe(ents)
    assert det == {"C1": {"qtd": 4, "base": 700.0, "altura": 465.0, "t": 4.76, "angulo": 50.9}}, det
    doc = Documento()
    th = math.radians(50.9)
    for lado in (1.0, -1.0):                                   # o caixão 2Ue 250×125: os dois Ue a ±85,5 do meio
        b = Barra(nome="p", inicio=(0.0, 85.5 * lado, 0.0), fim=(8000.0 / math.tan(th), 85.5 * lado, 8000.0),
                  perfil="Ue 250×125×25×4,75", papel="pilar")
        b.atributos = {"origem": {"caixao": True, "locacao": "PM8"}}
        b.recorte_inicio = 15.88                               # na placa CH7
        doc.add(b)
    chapas, avisos = [], []
    assert BL.chapas_do_pe(doc, det, "ASTM A36", chapas, avisos) == 2
    assert {round(c.origem[1], 1) for c in chapas} == {122.6, -122.6}                  # nas faces do caixão
    assert all(abs(c.origem[2] - 15.88) < 1e-6 and c.eixo_x == (1.0, 0.0, 0.0) for c in chapas)
    A, B, C, D = chapas[0].contorno
    assert abs(B[0] - A[0] - 700.0) < 0.1 and abs(C[1] - 465.0) < 0.1
    assert abs(math.dist(C, D) - 250.0) < 1.5                                          # o topo: a altura da perna
    # a perna começa no topo da chapa
    p = doc.barras[0]
    L = math.dist(p.inicio, p.fim)
    assert abs(p.inicio[2] + (p.fim[2] - p.inicio[2]) * p.recorte_inicio / L - (15.88 + (C[1] + D[1]) / 2)) < 1.0


def _lancar_so(ents, folga=(5000.0, 5000.0, 30000.0, 30000.0)):
    doc = Documento()
    _pilares(doc)
    chapas, avisos = [], []

    def barra(p0, p1, perfil, papel, camada, conjunto=None, rot=0.0, origem=None):
        b = Barra(nome=perfil, inicio=tuple(p0), fim=tuple(p1), perfil=perfil, papel=papel, camada=camada)
        b.atributos = {"origem": dict(origem or {})}
        doc.add(b)
        return b
    dets = BL.detalhes(ents)
    pl = BL.placas(ents, folga)
    pl += BL.placas_sem_contorno(pl, BL.rotulos(ents, folga), dets, doc, lambda p: p)
    BL.lancar(doc, pl, dets, lambda p: p, 0.0, "ASTM A36", barra, chapas, avisos, BL.nervuras(ents))
    return doc, chapas


def test_placa_na_medida_do_detalhe_e_nao_da_locacao():
    """Posto CB, 29/10/2026 (relação de corte das chapas): a CH6 da locação desenhada 400 × 390 ia ao corte com 390 e os
    furos a 30 mm da borda; o DET. DO CH6-1X é 400 × 400, furos a 35. A chapa sai na medida do detalhe, no meio do
    contorno da locação."""
    e = [_txt("DET. DO CH6-1X", 0, 0), _ret(120, 800, 400, 400)]
    e += [_circ(120 + x, 800 + y, 10.5) for x in (35, 365) for y in (35, 365)]
    e += [_txt('CHAPA # 3/8"', 220, 1240), _txt('2 Ø 5/8"', 150, 290), _txt("400", 320, 620, "1-Cota")]
    e += [_ret(10000 - 200, 10000 - 195, 400, 390, "Chapas"), _txt("CH6", 10000, 10300)]
    doc, chapas = _lancar_so(e)
    ch6 = next(c for c in chapas if c.nome.endswith("CH6"))
    xs, ys = [q[0] for q in ch6.contorno], [q[1] for q in ch6.contorno]
    assert (max(xs) - min(xs), max(ys) - min(ys)) == (400.0, 400.0), ch6.contorno
    assert sorted({(f["x"], f["y"]) for f in ch6.furos}) == [(35.0, 35.0), (35.0, 365.0), (365.0, 35.0), (365.0, 365.0)]
    meio = (ch6.origem[0] + ch6.eixo_x[0] * 200.0 + ch6.eixo_y[0] * 200.0,
            ch6.origem[1] + ch6.eixo_x[1] * 200.0 + ch6.eixo_y[1] * 200.0)
    assert math.dist(meio, (10000.0, 10000.0)) < 0.5


def test_abertura_da_placa_vai_ao_corte_quadrada():
    """Posto CB, 29/10/2026: a abertura 250 × 250 do meio da CH5 (hachurada no detalhe) ia ao 3D e ao DXF de corte como
    furo oblongo (um estádio de 250). Agora é recorte retangular: a malha abre o quadrado e o corte desenha o quadrado."""
    from nucleo2d.detalhar import levantar
    from saida import corte_chapas
    _doc, chapas = _lancar_so(_desenho())
    ch5 = next(c for c in chapas if c.nome.endswith("CH5"))
    ab = [f for f in ch5.furos if f.get("largura")]
    assert ab == [{"x": 275.0, "y": 275.0, "largura": 250.0, "altura": 250.0, "forma": "retangular"}]
    assert "oblongo" not in (ch5.atributos["origem"].get("a_conferir") or "")
    so = Documento()
    so.add(ch5)
    lev = levantar(so, regra_tercas=False)
    pos = next(p for p in lev["posicoes"] if p.classe == "chapa")
    rec = [f for f in pos.furos if f.tipo == "recorte"]
    assert len(rec) == 1 and not [f for f in pos.furos if f.tipo == "oblongo"], [(f.tipo, f.larg, f.alt) for f in pos.furos]
    xs, ys = [q[0] for q in rec[0].pontos], [q[1] for q in rec[0].pontos]
    assert abs(max(xs) - min(xs) - 250.0) < 0.6 and abs(max(ys) - min(ys) - 250.0) < 0.6 and len(rec[0].pontos) == 4
    d = corte_chapas.desenho_de_corte(pos)
    furo = [o for o in d.entidades.values() if getattr(o, "camada", "") == corte_chapas.CAMADA_FURO and type(o).__name__ == "Polilinha"]
    assert len(furo) == 1 and len(furo[0].vertices) == 4
    assert abs(ch5.area - (550.0 * 550.0 - 8 * math.pi * 10.3 ** 2 - 250.0 * 250.0)) < 1.0


def test_acertar_o_modelo_ja_montado():
    """O V2 do Posto montado antes de 29/10/2026 (sem remontar): a CH6 400 × 390 vai a 400 × 400 no mesmo lugar (os
    furos não se movem no mundo) e a abertura oblonga da CH5 vira retangular."""
    from nucleo3d.modelo import Chapa
    doc = Documento()
    ch6 = Chapa(nome="Placa de base CH6", origem=(1000.0, 2000.0, 0.0), eixo_x=(0.0, 1.0, 0.0), eixo_y=(-1.0, 0.0, 0.0),
                contorno=[(0.0, 0.0), (400.0, 0.0), (400.0, 390.0), (0.0, 390.0)], espessura=9.53, centrada=False,
                furos=[{"x": x, "y": y, "diametro": 21.0} for x in (35.0, 365.0) for y in (30.0, 360.0)])
    ch5 = Chapa(nome="Placa de base CH5", contorno=[(0.0, 0.0), (550.0, 0.0), (550.0, 550.0), (0.0, 550.0)],
                espessura=15.88, centrada=False, furos=[{"x": 275.0, "y": 275.0, "largura": 250.0, "altura": 250.0}])
    ch5.atributos = {"origem": {"a_conferir": "abertura 250 × 250 no meio da placa (no 3D como furo oblongo)"}}
    doc.add(ch6)
    doc.add(ch5)

    def mundo(c):
        return sorted((round(c.origem[0] + c.eixo_x[0] * f["x"] + c.eixo_y[0] * f["y"], 1),
                       round(c.origem[1] + c.eixo_x[1] * f["x"] + c.eixo_y[1] * f["y"], 1)) for f in c.furos)
    antes = mundo(ch6)
    dets = {"CH6": {"B": 400.0, "H": 400.0}, "CH5": {"B": 550.0, "H": 550.0}}
    assert BL.acertar_no_modelo(doc, dets) == {"placas": 1, "aberturas": 1}
    assert ch6.contorno[2] == (400.0, 400.0) and mundo(ch6) == antes
    assert sorted({(f["x"], f["y"]) for f in ch6.furos}) == [(35.0, 35.0), (35.0, 365.0), (365.0, 35.0), (365.0, 365.0)]
    assert ch5.furos[0]["forma"] == "retangular" and "a_conferir" not in ch5.atributos["origem"]
    assert BL.acertar_no_modelo(doc, dets) == {"placas": 0, "aberturas": 0}          # de novo: nada muda
