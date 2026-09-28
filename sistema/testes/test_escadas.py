# -*- coding: utf-8 -*-
"""Escadas do projeto recebido (nucleo3d/escadas.py): a planta baixa de uma escada em "L", como a
ESCADA 1 do Posto CB — o 1º lance em −x, o patamar, o 2º lance em −y —, posta no lugar pelos balões
das letras (y) e pelos pés da escada na locação (x), com o patamar pelas cotas do corte."""
import math

import pytest

from nucleo3d import escadas


def _linha(a, b, camada="metalica3"):
    return {"tipo": "linha", "camada": camada, "a": a, "b": b}


def _texto(x, y, t, h=4.0, camada="REG60-100"):
    return {"tipo": "texto", "posicao": [x, y], "texto": t, "altura": h, "camada": camada}


def _planta():
    ents, textos = [], []
    # o 1º lance: longarinas (linha dupla a 40 mm) em y 1000 e 0, de x 4000 (pé) a 1060 (patamar)
    for y in (1000.0, 0.0):
        ents += [_linha((4000.0, y), (0.0, y)), _linha((4000.0, y + 40.0), (0.0, y + 40.0))]
    # o 2º lance: em x 0 e 1060, de y 1040 a −2400
    for x in (0.0, 1060.0):
        ents += [_linha((x, 1040.0), (x, -2400.0)), _linha((x + 40.0, 1040.0), (x + 40.0, -2400.0))]
    # os degraus: 1 a 9 no 1º lance, 10 no patamar, 11 a 18 no 2º e 19 a chegada
    for k in range(1, 10):
        textos.append(_texto(4000.0 - 150.0 - 300.0 * (k - 1), 500.0, str(k)))
    textos.append(_texto(500.0, 500.0, "10"))
    for k in range(11, 20):
        textos.append(_texto(500.0, -150.0 - 300.0 * (k - 11), str(k)))
    textos += [_texto(2000.0, 1200.0, "Ue 200X40X20X3,04"), _texto(500.0, 900.0, "U100X40X2,25"),
               _texto(-500.0, -4000.0, "PLANTA BAIXA DA ESCADA 1", h=12.0),
               # o corte: 1.700 do chão ao patamar e 1.470 dele ao piso de cima
               _texto(6000.0, 800.0, "1700", h=5.0, camada="1-Cota"), _texto(6000.0, 2500.0, "1470", h=5.0, camada="1-Cota")]
    return ents, textos


def test_escada_em_L_no_lugar_com_o_patamar_do_corte():
    ents, textos = _planta()
    # a referência (a planta estrutural): o eixo E em y 33.000; na planta da escada, o balão E em y 1000
    referencia = {"E": [(100.0, 33000.0)], "F": [(100.0, 32000.0)]}
    baloes = {"E": (-1500.0, 1000.0), "F": (-1500.0, 0.0)}
    # os pés na locação: x 4716, nas linhas das longarinas
    pes = [(4716.0, 33020.0), (4716.0, 32020.0)]
    avisos = []
    r = escadas.ler(ents, textos, referencia, pes, 3170.0, avisos, baloes_de=lambda reg: baloes)
    assert len(r) == 1, avisos
    e = r[0]
    assert e["nome"] == "ESCADA 1" and e["perfil"] == "Ue 200X40X20X3,04" and e["perfil_patamar"] == "U100X40X2,25"
    assert e["patamar_z"] == pytest.approx(1700.0) and e["patamar_por"] == "cortes"
    assert "balões E, F" in e["alinhada_por"] and "pés" in e["alinhada_por"]
    pontos = [p for seg in e["lances"] for p in seg]
    # o pé (z 0) em x 4716 e o topo (z 3170) no fim do 2º lance
    assert any(p[2] == 0.0 and p[0] == pytest.approx(4736.0, abs=30) for p in pontos)
    assert any(p[2] == pytest.approx(3170.0) for p in pontos)
    assert len(e["patamar"]) == 4 and all(p[2] == pytest.approx(1700.0) for seg in e["patamar"] for p in seg)


def test_sem_como_por_no_lugar_fica_de_fora_com_aviso():
    ents, textos = _planta()
    avisos = []
    r = escadas.ler(ents, textos, {}, [], 3170.0, avisos, baloes_de=lambda reg: {})
    assert r == [] and any("não consegui pôr no lugar" in a for a in avisos)


def test_ligacao_ao_mezanino_vigas_do_patamar_e_o_piso():
    """as peças da planta que não são longarina nem degrau: a viga de chegada e a ligação dela ao
    mezanino (no alto, junto do fim do último lance), as vigas do patamar (na altura dele) e o piso
    de chapa xadrez do patamar"""
    ents, textos = _planta()
    # a chegada: U em linha dupla atravessando o fim do 2º lance; a ligação: dali até o pilar, em −y
    ents += [_linha((-20.0, -2400.0), (1120.0, -2400.0)), _linha((-20.0, -2440.0), (1120.0, -2440.0)),
             _linha((0.0, -2440.0), (0.0, -3500.0)), _linha((40.0, -2440.0), (40.0, -3500.0)),
             # uma viga do patamar, no meio dele
             _linha((40.0, 480.0), (1060.0, 480.0)), _linha((40.0, 520.0), (1060.0, 520.0))]
    textos.append(_texto(3000.0, -3000.0, "PISO EM CHAPA XADREZ 2,65 mm"))
    referencia = {"E": [(100.0, 33000.0)], "F": [(100.0, 32000.0)]}
    baloes = {"E": (-1500.0, 1000.0), "F": (-1500.0, 0.0)}
    pes = [(4716.0, 33020.0), (4716.0, 32020.0)]
    avisos = []
    e = escadas.ler(ents, textos, referencia, pes, 3170.0, avisos, baloes_de=lambda reg: baloes)[0]
    alturas = sorted(round(a[2]) for a, _b in e["vigas"])
    assert alturas.count(3170) == 2, e["vigas"]          # a chegada e a ligação
    assert alturas.count(1700) == 1, e["vigas"]          # a viga do patamar
    compr = sorted(round(math.dist(a[:2], b[:2])) for a, b in e["vigas"] if round(a[2]) == 3170)
    assert compr[0] == pytest.approx(1080, abs=50) and compr[1] == pytest.approx(1140, abs=50)
    assert len(e["pisos"]) == 1
    p = e["pisos"][0]
    assert p["espessura"] == pytest.approx(2.65) and p["canto"][2] == pytest.approx(1700.0)
    assert p["lx"] > 900 and p["ly"] > 900
