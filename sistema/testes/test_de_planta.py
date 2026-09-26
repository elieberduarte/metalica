# -*- coding: utf-8 -*-
"""Montagem pela planta (nucleo3d/de_planta.py): um projeto recebido pequeno, desenhado
como o do posto — planta estrutural com os nomes nas treliças, elevações com título
"- kX", nota dos perfis e marcas ST, locação dos pilares e planta das terças — vira o
modelo com as quantidades que o próprio desenho pede."""
import math

import pytest

from nucleo2d import reconhecer
from nucleo3d import de_planta

L_TES = 9000.0          # tesoura: 9 m, 1300 de altura numa ponta e 900 na outra
R_PAINEL = 5000.0       # painel curvo: meia volta de raio 5 m
DX_LOC, DY_TER = -100000.0, -60000.0
S_TERCAS = [600.0, 2100.0, 3900.0, 5200.0, 7400.0, 8600.0]   # passo irregular


def linha(a, b, camada="metalica3"):
    return {"tipo": "linha", "camada": camada, "a": [a[0], a[1]], "b": [b[0], b[1]]}


def texto(p, t, altura=2.5, angulo=0.0, camada="REG60-100"):
    return {"tipo": "texto", "camada": camada, "posicao": [p[0], p[1]], "texto": t, "altura": altura,
            "angulo": angulo, "alinhamento": "esquerda", "vertical": "base"}


def ret(x0, y0, x1, y1, camada):
    return {"tipo": "polilinha", "camada": camada, "vertices": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "fechada": True}


def baloes(dx, dy):
    out = []
    for nome, x in (("1", 0.0), ("2", 4500.0), ("3", 9000.0)):
        out += [{"tipo": "circulo", "camada": "Eixo", "centro": [x + dx, 10500.0 + dy], "raio": 250.0},
                texto((x + dx - 80, 10500.0 + dy - 100), nome, camada="Eixo")]
    for nome, y in (("A", 0.0), ("B", 6000.0)):
        out += [{"tipo": "circulo", "camada": "Eixo", "centro": [-3000.0 + dx, y + dy], "raio": 250.0},
                texto((-3000.0 + dx - 80, y + dy - 100), nome, camada="Eixo")]
    return out


def planta():
    ents = []
    for y in (0.0, 6000.0):                    # duas tesouras ao longo de x
        ents += [linha((0.0, y - 50.0), (L_TES, y - 50.0)), linha((0.0, y + 50.0), (L_TES, y + 50.0)),
                 texto((3500.0, y + 150.0), "TESOURA 1")]
    # o painel curvo, da ponta de uma tesoura à outra
    for r in (R_PAINEL - 50.0, R_PAINEL + 50.0):
        ents.append({"tipo": "arco", "camada": "metalica3", "centro": [L_TES, 3000.0], "raio": r,
                     "inicio": 270.0, "fim": 90.0})
    ents.append(texto((L_TES + R_PAINEL + 300.0, 3000.0), "PAINEL 1", angulo=90.0))
    # a viga que liga as pontas das tesouras, do lado reto
    ents += [linha((-100.0, -50.0), (-100.0, 6050.0), "metalica4"), linha((100.0, -50.0), (100.0, 6050.0), "metalica4"),
             texto((-250.0, 1500.0), "VM-2Ue200X70X20X2,65", angulo=90.0)]
    ents.append(texto((2000.0, -4000.0), "PLANTA NO NÍVEL 6,00m", altura=5.0))
    return ents


def locacao():
    ents = []
    for x, y in ((0.0, 0.0), (L_TES, 0.0), (0.0, 6000.0), (L_TES, 6000.0)):
        ents.append(ret(x + DX_LOC - 175, y - 145, x + DX_LOC + 175, y + 145, "Chapas"))
        ents.append(texto((x + DX_LOC + 279, y + 516), "PM1(250X70X25X3,0)"))
    ents.append(texto((2000.0 + DX_LOC, -4000.0), "LOCAÇÃO / CARGAS", altura=5.0))
    return ents


def plantas_das_tercas():
    ents = []
    for s in S_TERCAS:
        # a obra tem a ponta alta da tesoura em x = 9000: a terça que na elevação fica a
        # s da ponta esquerda (a alta) está em x = 9000 − s na planta
        x = L_TES - s
        ents.append(linha((x, -300.0 + DY_TER), (x, 6300.0 + DY_TER), "1-Terça Eixo"))
        ents.append(texto((x + 60.0, 3000.0 + DY_TER), "TC1", angulo=90.0, camada="1-Terça"))
    ents.append(texto((2000.0, -4000.0 + DY_TER), "PLANTA NO NÍVEL DAS TERÇAS", altura=5.0))
    ents.append(texto((-20000.0, -20000.0), "TC1-U100X40X2,65 - 12X"))
    return ents


def elevacao_tesoura(x0, y0):
    """TESOURA 1 - 2X: alta à esquerda (1300), baixa à direita (900)"""
    def topo(x):
        return 1300.0 + (900.0 - 1300.0) * x / L_TES
    ents = [linha((x0, y0), (x0 + L_TES, y0), "metalica3"), linha((x0, y0 + 40), (x0 + L_TES, y0 + 40), "metalica3"),
            linha((x0, y0 + topo(0)), (x0 + L_TES, y0 + topo(L_TES))),
            linha((x0, y0 + topo(0) + 40), (x0 + L_TES, y0 + topo(L_TES) + 40))]
    xs = [0.0, 1500.0, 3000.0, 4500.0, 6000.0, 7500.0, L_TES]
    for i, x in enumerate(xs):
        ents.append(linha((x0 + x, y0 + 40), (x0 + x, y0 + topo(x)), "metalica2"))
        if i + 1 < len(xs):
            ents.append(linha((x0 + x, y0 + 40), (x0 + xs[i + 1], y0 + topo(xs[i + 1])), "metalica2"))
    for s in S_TERCAS:                    # marca ST2 com a chamada até o apoio
        tx, ty = x0 + s - 420.0, y0 + topo(s) + 250.0
        ents.append(texto((tx, ty), "ST2", camada="metalica2"))
        ents.append(linha((tx + 10.0, ty - 20.0), (tx + 360.0, ty - 20.0), "1-Metalica2"))
        ents.append(linha((tx + 360.0, ty - 20.0), (x0 + s, y0 + topo(s) + 45.0), "1-Metalica2"))
    ents += [texto((x0, y0 - 300.0), "BANZO U100X40X2,25"),
             texto((x0, y0 - 450.0), 'DIAGONAIS E MONTANTES 2L 1"X1/8"  3 PRELILHAS L 1"X1/8"'),
             texto((x0, y0 - 700.0), "TESOURA 1 - 2X", altura=3.5)]
    return ents


def elevacao_painel(x0, y0):
    L = math.pi * R_PAINEL
    ents = [linha((x0, y0), (x0 + L, y0)), linha((x0, y0 + 40), (x0 + L, y0 + 40)),
            linha((x0, y0 + 1560), (x0 + L, y0 + 1560)), linha((x0, y0 + 1600), (x0 + L, y0 + 1600))]
    n = 10
    for i in range(n + 1):
        x = L * i / n
        ents.append(linha((x0 + x, y0 + 40), (x0 + x, y0 + 1560), "metalica2"))
    ents += [texto((x0, y0 - 300.0), "BANZO U100X40X2,25"),
             texto((x0, y0 - 450.0), 'DIAGONAIS E MONTANTES 2L 1"X1/8"'),
             texto((x0, y0 - 700.0), "PAINEL 1 - 1X", altura=3.5)]
    return ents


@pytest.fixture(scope="module")
def resultado():
    ents = planta() + locacao() + plantas_das_tercas() + baloes(0, 0) + baloes(DX_LOC, 0) + baloes(0, DY_TER)
    ents += elevacao_tesoura(0.0, -120000.0) + elevacao_painel(20000.0, -120000.0)
    return de_planta.montar(ents, {"nivel": 6000.0})


def test_le_os_perfis_da_nota_da_elevacao():
    r = reconhecer.perfil_do_texto('DIAGONAIS E MONTANTES 2L 1"X1/8"  3 PRELILHAS L 1"X1/8"')
    assert r["mult"] == 2 and r["perfil"] == 'L 1"×1/8"'
    p = reconhecer.perfil_do_texto("PM3(200X70X20X2,65)")
    assert p["perfil"] == "Ue 200×70×20×2,65" and p["papel"] == "pilar"


def test_quantidades_conferem_com_o_titulo(resultado):
    conf = {c["peca"]: c for c in resultado["conferencia"]}
    assert conf["TESOURA 1"]["modelo"] == 2 and conf["TESOURA 1"]["ok"]
    z = resultado["resumo"]
    assert z["pilares"] == 4
    assert z["vigas"] == 1
    assert z["tercas"] == len(S_TERCAS)
    assert z["projeto"]["tercas"] == 12


def test_painel_curvo_sai_calandrado(resultado):
    doc = resultado["doc"]
    cal = [e for e in doc.solidos if (e.atributos or {}).get("calandrada")]
    assert len(cal) == 2                                   # banzo de baixo e de cima
    assert abs(cal[0].atributos["calandrada"]["raio"] - R_PAINEL) < 1.0
    assert cal[0].atributos["marcas"]["perfil"] == "U 100×40×2,25 (FF)"


def test_sentido_da_tesoura_pelas_marcas_de_terca(resultado):
    """as marcas ST caem nos cruzamentos das terças só no sentido invertido: a ponta alta
    (1300) vai para x = 9000, onde a planta das terças diz que ela está"""
    doc = resultado["doc"]
    assert resultado["resumo"]["orientacao"]["pelas_marcas"] >= 2
    banzos = [b for b in doc.barras if b.papel == "banzo" and max(b.inicio[2], b.fim[2]) > 6500.0]
    assert banzos
    b = max(banzos, key=lambda b: b.comprimento)
    alto, baixo = (b.inicio, b.fim) if b.inicio[2] > b.fim[2] else (b.fim, b.inicio)
    assert alto[0] > baixo[0]
    assert abs(alto[2] - 6000.0 - 1300.0) < 30.0


def test_terca_senta_no_banzo_superior(resultado):
    doc = resultado["doc"]
    tercas = [b for b in doc.barras if b.papel == "terça"]
    assert tercas
    t = min(tercas, key=lambda b: abs(b.inicio[0] - (L_TES - S_TERCAS[0])))
    # banzo superior a 1300 − (1300 − 900) · s / L acima do nível, + meio banzo + meia terça
    s = S_TERCAS[0]
    esperado = 6000.0 + 1300.0 + (900.0 - 1300.0) * s / L_TES + 20.0 + 50.0
    assert abs(t.inicio[2] - esperado) < 40.0


def test_pilares_no_lugar_da_planta(resultado):
    doc = resultado["doc"]
    pil = sorted((round(b.inicio[0]), round(b.inicio[1])) for b in doc.barras if b.papel == "pilar")
    assert pil == [(0, 0), (0, 6000), (9000, 0), (9000, 6000)]
    assert all(b.fim[2] == 6000.0 for b in doc.barras if b.papel == "pilar")
