# -*- coding: utf-8 -*-
"""A volta do 3D para a planta não devolve o que a MONTAGEM fez (14/11/2026; achado do VERSÃO na conferência da 0.9.3).

No Hangar Almayer, "Trazer do 3D o que mudou" devolvia, além da terça que o usuário moveu, 32 alterações dos contraventos
CV1–CV8 que ninguém fez: "viga CV1: comprimento 6575 → 6658 mm, movida 41 mm, topo 6415.8 → 6384". A montagem alonga a
ponta do contravento que tem aleta até o comprimento de corte do projeto e a leva ao meio da altura do banzo (as castanhas
da V12 fazem o mesmo), e a volta tomava as pontas da barra do 3D como a linha nova da planta. A planta era gravada assim, e
na gravação seguinte do CAD as 32 aletas saíam do lugar. Reincidência da família de 20/10 (a terça que subia 63,5 mm).

A regra: nada mudou no 3D → nada muda na planta, com os ajustes da montagem. A volta compara o 3D gravado com o 3D que a
montagem gera da planta de agora, peça por peça; só a diferença vai para a planta, e o que já veio não vem de novo.
"""
import copy
import json
import math
import os
import sys

import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from nucleo2d.desenho import Desenho, Linha                   # noqa: E402
from nucleo3d import de_planta_estrutura as DPE               # noqa: E402
from nucleo3d.modelo import Barra, Chapa, Documento           # noqa: E402

#: a Montagem do verif_identificacao_ui logo depois de "Montar o modelo 3D": 56 terças, 32 contraventos com a aleta AC1
#: numa ponta só (as T2 dos eixos 3 e 5), as T2, as VC, as VT, os apoios — a forma em que o defeito apareceu
HANGAR = os.path.join(AQUI, "dados_cad", "hangar_montagem_identificada.json")
ROD = 'Barra redonda ø 1/2"'


# ------------------------------------------------------------------ o Hangar, como no verificador
@pytest.fixture(scope="module")
def hangar_bruto():
    with open(HANGAR, encoding="utf-8") as f:
        bruto = json.load(f)
    doc, _avisos = DPE.modelo_da_planta(Desenho.de_dict(copy.deepcopy(bruto["desenho"])), bruto["niveis"])
    return bruto["desenho"], bruto["niveis"], doc.dict()


@pytest.fixture
def hangar(hangar_bruto):
    """(a Montagem, os níveis, o 3D que a montagem fez dela) — cópias novas a cada teste"""
    des, niveis, modelo = hangar_bruto
    return Desenho.de_dict(copy.deepcopy(des)), niveis, Documento.de_dict(copy.deepcopy(modelo))


def _texto(des):
    return json.dumps(des.dict(), sort_keys=True, ensure_ascii=False)


def _barra_de(doc, des, papel, marca, plano=None):
    """a barra do 3D (e a linha dela na planta) de um elemento com esse papel e essa marca"""
    for e in des.entidades.values():
        a = e.atributos or {}
        if a.get("papel") == papel and a.get("marca") == marca and (plano is None or a.get("plano") == plano):
            b = next(x for x in doc.entidades.values() if isinstance(x, Barra) and (x.atributos or {}).get("origem_2d") == e.id)
            return b, e.id
    raise AssertionError("sem %s %s" % (papel, marca))


def _andar(barra, v):
    barra.inicio = tuple(barra.inicio[k] + v[k] for k in range(3))
    barra.fim = tuple(barra.fim[k] + v[k] for k in range(3))


def _real(des, eid):
    return DPE.planta_real(des).entidades[eid]


def test_hangar_tem_os_ajustes_da_montagem(hangar):
    """a forma do defeito: os 32 contraventos saem da montagem mais compridos que a linha da planta (a ponta com aleta)"""
    des, _niveis, doc = hangar
    real = DPE.planta_real(des)
    cvs = [b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "contraventamento"]
    assert len(cvs) == 32
    assert sum(1 for c in doc.entidades.values() if isinstance(c, Chapa) and (c.atributos or {}).get("papel_chapa") == "aleta") == 32
    for b in cvs:
        e = real.entidades[b.atributos["origem_2d"]]
        cresceu = math.dist(b.inicio[:2], b.fim[:2]) - math.dist(e.a, e.b)
        assert 70.0 < cresceu < 90.0, (b.atributos.get("marca"), cresceu)


def test_hangar_sem_mexer_no_3d_a_volta_nao_devolve_nada_e_a_planta_fica_igual(hangar):
    des, niveis, doc = hangar
    antes = _texto(des)
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == [], r["alteracoes"][:4]
    assert r["sem_peca"] == []
    assert _texto(des) == antes                                # byte a byte: nem a ida e volta ao papel mexe nas outras


def test_hangar_a_terca_movida_volta_so_ela(hangar):
    des, niveis, doc = hangar
    tb, eid = _barra_de(doc, des, "terça", "T.C.1")
    antes = copy.deepcopy(des.entidades)
    d = tb.direcao
    _andar(tb, tuple(300.0 * c for c in d))
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == ["viga T.C.1: movida 300 mm"]
    mudou = [k for k, e in des.entidades.items() if repr(e) != repr(antes[k])]
    assert mudou == [eid]                                       # na planta, só a linha da terça
    esc = 75.0
    assert math.dist(des.entidades[eid].a, antes[eid].a) * esc == pytest.approx(300.0, abs=0.5)
    assert des.entidades[eid].atributos["nivel_topo"] == antes[eid].atributos["nivel_topo"]


@pytest.mark.parametrize("marca, plano", [("CV5", "inf"), ("CV1", "sup")])
def test_hangar_o_contravento_movido_anda_o_que_andou_sem_o_alongamento(hangar, marca, plano):
    """o contravento andou 200 mm ao longo da tesoura no 3D: a linha da planta anda 200 mm, com o comprimento de antes
    (o alongamento da ponta com aleta é da montagem, não vai para a planta)"""
    des, niveis, doc = hangar
    cv, eid = _barra_de(doc, des, "contraventamento", marca, plano)
    antes = copy.deepcopy(_real(des, eid))
    _andar(cv, (0.0, 200.0, 0.0))                               # as tesouras correm em y
    guardado = (cv.inicio, cv.fim)
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == ["viga %s: movida 200 mm" % marca]
    depois = _real(des, eid)
    assert depois.a == pytest.approx((antes.a[0], antes.a[1] + 200.0), abs=0.01)
    assert depois.b == pytest.approx((antes.b[0], antes.b[1] + 200.0), abs=0.01)
    assert depois.atributos["nivel_topo"] == antes.atributos["nivel_topo"]
    assert depois.atributos.get("nivel_fim") == antes.atributos.get("nivel_fim")
    # o 3D refeito da planta nova põe o contravento onde o usuário o deixou (em planta)
    novo, _ = DPE.modelo_da_planta(copy.deepcopy(des), niveis)
    b2 = next(x for x in novo.entidades.values() if isinstance(x, Barra) and (x.atributos or {}).get("origem_2d") == eid)
    # (2 mm: no banzo de cima, inclinado, a montagem repõe a cota da ponta no furo da aleta e o alongamento acompanha)
    assert math.dist(b2.inicio[:2], guardado[0][:2]) < 2.0 and math.dist(b2.fim[:2], guardado[1][:2]) < 2.0


def _mexer(caso, doc, des):
    if caso == "terça":
        tb, _ = _barra_de(doc, des, "terça", "T.C.1")
        _andar(tb, tuple(300.0 * c for c in tb.direcao))
    elif caso == "contravento de baixo":
        _andar(_barra_de(doc, des, "contraventamento", "CV5", "inf")[0], (0.0, 200.0, 0.0))
    elif caso == "contravento de cima":                         # o banzo de cima é inclinado: a montagem repõe a cota da ponta
        _andar(_barra_de(doc, des, "contraventamento", "CV1", "sup")[0], (0.0, 200.0, 0.0))
    elif caso == "ponta esticada":                              # a ponta que a montagem alonga, puxada mais 50 mm
        cv, _ = _barra_de(doc, des, "contraventamento", "CV6", "inf")
        d = cv.direcao
        cv.inicio = tuple(cv.inicio[k] - 50.0 * d[k] for k in range(3))
        cv.fim = tuple(cv.fim[k] + 50.0 * d[k] for k in range(3))
    elif caso == "contravento subiu":
        _andar(_barra_de(doc, des, "contraventamento", "CV7", "inf")[0], (0.0, 0.0, 40.0))


@pytest.mark.parametrize("caso", ["terça", "contravento de baixo", "contravento de cima", "ponta esticada", "contravento subiu"])
def test_hangar_duas_voltas_seguidas_a_segunda_nao_devolve_nada(hangar, caso):
    """a família de 20/10 (a terça subia 63,5 mm a cada ida e volta): o que já veio do 3D não vem de novo — nem quando
    a montagem não acompanha o que o usuário fez (a ponta que ela repõe no furo da aleta)"""
    des, niveis, doc = hangar
    _mexer(caso, doc, des)
    r1 = DPE.montagem_do_modelo(des, doc, niveis)
    assert len(r1["alteracoes"]) == 1, r1["alteracoes"]
    # a 2ª volta na planta gravada e aberta de novo (o que a rota faz entre um clique e outro)
    des = Desenho.de_dict(json.loads(json.dumps(des.dict())))
    depois_da_1a = _texto(des)
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == [], r["alteracoes"]
    assert _texto(des) == depois_da_1a
    # o 3D refeito da planta nova (a gravação seguinte do CAD) também não tem o que trazer
    novo, _ = DPE.modelo_da_planta(copy.deepcopy(des), niveis)
    assert DPE.montagem_do_modelo(des, novo, niveis)["alteracoes"] == []


def test_hangar_o_que_veio_e_foi_desfeito_na_planta_volta_a_vir(hangar):
    """o "já veio" vale para aquela planta: a linha levada de volta no CAD e o mesmo 3D → a volta traz de novo"""
    des, niveis, doc = hangar
    cv, eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    antes = copy.deepcopy(des.entidades[eid])
    _andar(cv, (0.0, 200.0, 0.0))
    assert len(DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"]) == 1
    des.entidades[eid].a, des.entidades[eid].b = antes.a, antes.b          # o usuário desfez na planta
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == ["viga CV5: movida 200 mm"]


# ------------------------------------------------------------------ outra forma: tesoura pequena, cota e giro diferentes
BARRAS = [[0, 0, 6000, 0, "banzo_inf"], [0, 600, 3000, 900, "banzo_sup"], [3000, 900, 6000, 600, "banzo_sup"],
          [0, 0, 0, 600, "extremidade"], [6000, 0, 6000, 600, "extremidade"], [3000, 0, 3000, 900, "montante"],
          [0, 600, 3000, 0, "diagonal"], [3000, 0, 6000, 600, "diagonal"]]
ALETA = {"marca": "AC1", "espessura": 6.3, "largura": 140.0, "altura": 119.0, "furos": [{"x": 30.0, "y": 59.5, "d": 15.0}]}
CASTANHA = {"marca": "CA1", "quantidade": 64, "peca": {"perfil": "L 2\"×3/16\"", "comprimento": 150.0},
            "aba": {"perfil": "L 2\"×3/16\"", "comprimento": 50.0}, "furo": 14.0,
            "parafuso": {"texto": '1/2"', "diametro": 12.7, "quantidade": 64}, "banzos": ["inf"]}


def _planta_pequena(ligacao, base):
    """uma tesoura de 6 m com o banzo de baixo em `base` e dois contraventos chegando nela: com a aleta (V5) ou com a
    castanha (V12) numa ponta, e o comprimento de corte do projeto maior que a linha"""
    des = Desenho(nome="planta", escala=1.0)
    aletas = ({"aleta": ALETA} if ligacao == "aleta" else {"castanha": CASTANHA})
    aletas["contraventos"] = {"CV1": {"comprimento": 4140.0}, "CV2": {"comprimento": 4140.0}}
    des.add(Linha(camada="E", a=(0.0, 0.0), b=(0.0, 6000.0), atributos={
        "elemento": "trelica", "material": "aco", "marca": "T1",
        "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "diagonal": "L 32×3 (FF)", "montante": "L 32×3 (FF)"},
        "nivel_base": base, "desenho": {"barras": BARRAS, "vao": 6000, "altura": 900}, "aletas": aletas}))
    ids = []
    for marca, x0, y0 in (("CV1", 130.0, 1000.0), ("CV2", 141.3, 5000.0)):
        e = Linha(camada="E", a=(x0, y0), b=(x0 + 2900.0, y0 + 2900.0 * (1 if y0 < 3000 else -1)), atributos={
            "elemento": "viga", "material": "aco", "papel": "contraventamento", "marca": marca,
            "secao": {"perfil": ROD}, "nivel_topo": base + 80.0, "alinhamento": "eixo"})
        des.add(e)
        ids.append(e.id)
    return des, ids


def _na_montagem(real, giro, escala=50.0):
    """a mesma planta dentro do quadro da Implantação de uma Montagem (mm de papel), com o giro do quadro"""
    q = {"id": "qi", "tipo": "implantacao", "escala": escala, "x": 0.0, "y": 0.0, "w": 420, "h": 297,
         "mapa": {"X0": -500.0, "Y0": 7000.0, "ox": 8.0, "oy": -270.0, "giro": giro}}
    f, _s = DPE._mapa_inverso_do_quadro(q)
    des = Desenho(nome="Montagem", escala=1.0)
    des.metadados = {"montagem": {"versao": 1, "original": "planta-de-lançamento", "quadros": [q]}}
    for e in real.entidades.values():
        n = copy.deepcopy(e)
        n.a, n.b = f(e.a), f(e.b)
        n.atributos = dict(e.atributos, quadro="qi")
        des.entidades[n.id] = n
    return des


@pytest.mark.parametrize("ligacao", ["aleta", "castanha"])
@pytest.mark.parametrize("base, giro", [(5000.0, None), (0.0, 0.0), (12500.0, 90.0)])
def test_tesoura_pequena_com_aleta_ou_castanha_a_volta_sem_mexer_nao_devolve_nada(ligacao, base, giro):
    """a aleta (V5) e a castanha (V12), com o piso no zero e longe dele, na planta solta e na Montagem girada"""
    real, ids = _planta_pequena(ligacao, base)
    des = real if giro is None else _na_montagem(real, giro)
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    cvs = {b.atributos["marca"]: b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "contraventamento"}
    assert abs(cvs["CV1"].comprimento - 4140.0) < 0.5           # a montagem alongou: é o caso
    antes = _texto(des)
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == [], r["alteracoes"]
    assert _texto(des) == antes
    # o contravento andou 150 mm ao longo da tesoura (y): só isso volta, e uma vez só
    _andar(cvs["CV1"], (0.0, 150.0, 0.0))
    a0 = DPE.planta_real(des).entidades[ids[0]]
    a0 = (a0.a, a0.b)
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga CV1: movida 150 mm"]
    e1 = DPE.planta_real(des).entidades[ids[0]]
    assert e1.a == pytest.approx((a0[0][0], a0[0][1] + 150.0), abs=0.01) and e1.b == pytest.approx((a0[1][0], a0[1][1] + 150.0), abs=0.01)
    assert e1.atributos["nivel_topo"] == base + 80.0
    assert DPE.montagem_do_modelo(des, doc, [])["alteracoes"] == []


def test_sem_ajuste_da_montagem_a_volta_continua_como_era():
    """a viga de aço que a montagem não ajusta: movida e levantada no 3D, a planta acompanha (a cota também)"""
    des = Desenho(nome="planta", escala=100.0)
    e = Linha(camada="ESTRUTURA", a=(0.0, 0.0), b=(5460.0, 0.0), atributos={
        "elemento": "viga", "material": "aco", "papel": "terça", "marca": "T.C.1",
        "secao": {"perfil": "U 127×50×2,25 (FF)", "aco": "ASTM A36"}, "nivel_topo": 6454.5, "alinhamento": "base"})
    des.add(e)
    doc, _ = DPE.modelo_da_planta(copy.deepcopy(des), [])
    b = next(x for x in doc.entidades.values() if isinstance(x, Barra))
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == []
    _andar(b, (300.0, 0.0, 100.0))
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga T.C.1: movida 300 mm, topo 6454.5 → 6554"]         # a cota que muda vira mm inteiro
    assert des.entidades[e.id].a == pytest.approx((300.0, 0.0)) and des.entidades[e.id].atributos["nivel_topo"] == 6554
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == []


def test_a_peca_que_a_montagem_nao_refaz_segue_pela_conta_de_sempre():
    """o 3D com uma peça ligada a um elemento que a montagem de agora recusa (o pilar sem altura): a volta não quebra e
    acerta a planta pelo 3D, como sempre"""
    from nucleo2d.desenho import Polilinha
    des = Desenho(nome="planta", escala=100.0)
    p = Polilinha(camada="ESTRUTURA", fechada=True, vertices=[(0, 0), (300, 0), (300, 400), (0, 400)], atributos={
        "elemento": "pilar", "material": "concreto", "marca": "P1", "nivel_base": 0, "nivel_topo": 5000,
        "secao": {"tipo": "retangular", "b": 30, "h": 40}})
    des.add(p)
    doc, _ = DPE.modelo_da_planta(copy.deepcopy(des), [])
    des.entidades[p.id].atributos["nivel_topo"] = -100          # agora a montagem recusa: "o topo não está acima da base"
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["pilar P1: topo -100 → 5000"]
