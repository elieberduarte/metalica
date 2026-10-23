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
    r = BL.lancar(doc, pl, dets, lambda p: p, 0.0, "ASTM A36", barra, chapas, avisos)
    assert r["placas"] == 2 and r["chumbadores"] == 12, r
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
