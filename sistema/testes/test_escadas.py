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
    # o 1º lance: longarinas (linha dupla a 40 mm) em y 1000 e 0, de x 3800 (pé) a 0 (o patamar
    # até 1100): 9 pisantes de 300
    for y in (1000.0, 0.0):
        ents += [_linha((3800.0, y), (0.0, y)), _linha((3800.0, y + 40.0), (0.0, y + 40.0))]
    # o 2º lance: em x 0 e 1060, de y 1040 a −2400
    for x in (0.0, 1060.0):
        ents += [_linha((x, 1040.0), (x, -2400.0)), _linha((x + 40.0, 1040.0), (x + 40.0, -2400.0))]
    # os degraus: 1 a 9 no 1º lance, 10 no patamar, 11 a 18 no 2º e 19 a chegada
    for k in range(1, 10):
        textos.append(_texto(3800.0 - 150.0 - 300.0 * (k - 1), 500.0, str(k)))
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
    # os pisantes: 9 no 1º lance (espelho 1700/10) e 8 no 2º (1470/9), numerados como o desenho,
    # de 300 entre as faces de dentro das longarinas, em chapa dobrada com as abas para baixo
    ps = {p["k"]: p for p in e["pisantes"]}
    assert sorted(ps) == list(range(1, 10)) + list(range(11, 19))
    assert ps[1]["origem"][2] == pytest.approx(170.0) and ps[9]["origem"][2] == pytest.approx(1530.0)
    assert ps[11]["origem"][2] == pytest.approx(1700.0 + 1470.0 / 9) and ps[18]["origem"][2] == pytest.approx(3170.0 - 1470.0 / 9)
    assert ps[1]["piso"] == pytest.approx(300.0, abs=5) and ps[1]["largura"] == pytest.approx(960.0, abs=5)
    assert ps[1]["aba"] == escadas.ABA_DEGRAU



def test_pe_no_meio_das_pontas_da_longarina():
    """a ESCADA 1 do Posto V2: a face de fora da longarina vai mais longe que a de dentro no pé (293.032 × 292.832) e a
    placa CH8 fica no meio; com a ponta da linha mais comprida a escada saía 100 mm deslocada e o patamar não apoiava
    nos PM5 (22/10/2026). Aqui a face de cima da longarina de y 1000 vai até x 4000 (a outra até 3800)"""
    ents, textos = _planta()
    for e in ents:
        if e["a"] == (3800.0, 1040.0):
            e["a"] = (4000.0, 1040.0)
    referencia = {"E": [(100.0, 33000.0)], "F": [(100.0, 32000.0)]}
    baloes = {"E": (-1500.0, 1000.0), "F": (-1500.0, 0.0)}
    # as placas no meio das pontas de cada longarina: 3900 e 3800 do desenho + 900
    pes = [(4800.0, 33020.0), (4700.0, 32020.0)]
    r = escadas.ler(ents, textos, referencia, pes, 3170.0, [], baloes_de=lambda reg: baloes)
    assert len(r) == 1
    xs2 = sorted({round(p[0]) for seg in r[0]["lances"] for p in seg if p[2] > 1800.0})
    assert xs2 and all(min(abs(x - 920.0), abs(x - 1980.0)) <= 5 for x in xs2), xs2

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


def test_pisante_e_uma_chapa_dobrada_so():
    """Posto CB, 29/10/2026 (relação de corte das chapas): o pisante era o piso e duas abas de 40 como três chapas planas,
    e o corte recebia o piso 302 × 1120 e duas tiras 40 × 1120 por degrau no lugar da chapa xadrez dobrada do
    "DEGRAU 2 - 17X" (300 + abas de 40, # 2,65). Agora é uma peça só: o levantamento a vê dobrada, com o
    desenvolvimento pela linha média, e o DXF de corte leva a planificada."""
    from nucleo2d.detalhar import levantar
    from nucleo3d.modelo import Documento
    from saida import corte_chapas
    pd = {"k": 1, "origem": (1000.0, 2000.0, 170.0), "u": (0.0, 1.0), "n": (-1.0, 0.0), "piso": 300.0, "largura": 1119.0,
          "aba": escadas.ABA_DEGRAU, "espessura": 2.65}
    doc = Documento()
    so = escadas.pisante_dobrado(pd)
    so.nome = "Pisante 1 (escada 1)"
    doc.add(so)
    # o topo do piso na altura do degrau, as abas 40 para baixo, entre as longarinas (x 1000 → -119)
    zs = [v[2] for v in so.vertices]
    assert max(zs) == pytest.approx(170.0) and min(zs) == pytest.approx(130.0)
    assert {round(v[0], 1) for v in so.vertices} == {1000.0, -119.0}
    lev = levantar(doc, regra_tercas=False)
    ps = [p for p in lev["posicoes"] if p.quantidade]
    assert len(ps) == 1 and ps[0].classe == "chapa_dobrada", [(p.classe, p.observacoes) for p in ps]
    larg, desenv = ps[0].desenvolvimento
    assert larg == pytest.approx(1119.0, abs=1) and desenv == pytest.approx(300.0 + 2 * 40.0 - 2 * 2.65, abs=1)
    assert ps[0].espessura == pytest.approx(2.65, abs=0.01)
    assert ps[0].peso == pytest.approx(1119.0 * desenv * 2.65 * 7.85e-6, rel=0.02)
    cortes = corte_chapas.chapas_para_corte(lev["posicoes"])
    assert cortes == ps
    d = corte_chapas.desenho_de_corte(ps[0])
    pl = [o for o in d.entidades.values() if type(o).__name__ == "Polilinha"]
    assert len(pl) == 1 and sorted({round(v[0]) for v in pl[0].vertices}) == [0, round(desenv)]


def test_juntar_pisantes_do_modelo_ja_montado():
    """O V2 do Posto montado antes de 29/10/2026: o pisante em três chapas (piso + duas abas, como o gerador fazia) vira
    a chapa dobrada no mesmo lugar."""
    from nucleo3d.modelo import Chapa, Documento
    doc = Documento()
    o_, u, n, g, w, ab, e_, zt = (1000.0, 2000.0), (0.0, 1.0), (-1.0, 0.0), 300.0, 1119.0, 40.0, 2.65, 170.0
    org = {"origem": {"escada": "ESCADA 1", "pisante": 1, "piso": "chapa xadrez dobrada"}}
    partes = [((o_[0], o_[1], zt - e_), (u[0], u[1], 0.0), (n[0], n[1], 0.0), g, w, False)]
    for s_ in (e_ / 2.0, g - e_ / 2.0):
        partes.append(((o_[0] + u[0] * s_, o_[1] + u[1] * s_, zt - ab), (n[0], n[1], 0.0), (0.0, 0.0, 1.0), w, ab, True))
    for org_, ex_, ey_, lx, ly, cen in partes:
        ch = Chapa(nome="Pisante 1 (escada 1)", origem=org_, eixo_x=ex_, eixo_y=ey_,
                   contorno=[(0.0, 0.0), (lx, 0.0), (lx, ly), (0.0, ly)], espessura=e_, centrada=cen)
        ch.camada = "Escadas"
        ch.atributos = dict(org)
        doc.add(ch)
    assert escadas.juntar_pisantes(doc) == 1
    assert not doc.chapas and len(doc.solidos) == 1
    so = doc.solidos[0]
    assert so.nome == "Pisante 1 (escada 1)" and so.atributos["origem"]["pisante"] == 1
    assert max(v[2] for v in so.vertices) == pytest.approx(zt) and min(v[2] for v in so.vertices) == pytest.approx(zt - ab)
    assert {round(v[0], 1) for v in so.vertices} == {1000.0, -119.0}
    assert escadas.juntar_pisantes(doc) == 0
