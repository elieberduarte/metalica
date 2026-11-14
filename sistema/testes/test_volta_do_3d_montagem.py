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


def _sem_carimbo(doc):
    """o modelo como era gravado antes de 14/11/2026: as barras sem o carimbo da montagem"""
    for p3 in doc.entidades.values():
        if DPE.GERADA in (p3.atributos or {}):
            p3.atributos = {k: v for k, v in p3.atributos.items() if k != DPE.GERADA}
    return doc


@pytest.fixture(params=["modelo de agora", "modelo de antes"])
def hangar(hangar_bruto, request):
    """(a Montagem, os níveis, o 3D que a montagem fez dela) — cópias novas a cada teste. "modelo de agora": as barras
    com o carimbo da montagem; "modelo de antes": sem ele (o projeto gravado antes de 14/11), pela régua da montagem"""
    des, niveis, modelo = hangar_bruto
    doc = Documento.de_dict(copy.deepcopy(modelo))
    assert sum(1 for p3 in doc.entidades.values() if DPE.GERADA in (p3.atributos or {})) >= 56 + 32
    return Desenho.de_dict(copy.deepcopy(des)), niveis, (_sem_carimbo(doc) if request.param == "modelo de antes" else doc)


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


def test_hangar_o_que_veio_e_foi_desfeito_na_planta_nao_volta_sozinho(hangar):
    """a mudança veio do 3D e o usuário a desfez na planta, com o 3D ainda sem acompanhar: a volta seguinte não a traz
    de novo — a barra já está carimbada onde está, e a planta mexida depois é que vale (o 3D a segue na sincronia)"""
    des, niveis, doc = hangar
    cv, eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    antes = copy.deepcopy(des.entidades[eid])
    _andar(cv, (0.0, 200.0, 0.0))
    assert len(DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"]) == 1
    des.entidades[eid].a, des.entidades[eid].b = antes.a, antes.b          # o usuário desfez na planta
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == []
    assert des.entidades[eid].a == antes.a and des.entidades[eid].b == antes.b


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


# ------------------------------------------------------------------ as terças que a montagem estende (Hangar V12)
def _planta_com_tercas_na_tesoura_da_ponta():
    """três tesouras e duas terças com o suporte do projeto: nas tesouras da ponta (o oitão) a montagem leva a terça
    até a face de fora da tesoura (usuário, 22/10) — no Hangar V12 de verdade a volta antiga dava 28 terças "movidas" """
    st = {"marca": "ST1", "perfil": "L 127×50×3,75 (FF)", "comprimento": 150.0, "folga": 10.0,
          "furos": [{"ao_longo": a, "altura": h, "d": 14.0} for a in (-30.0, 30.0) for h in (38.5, 88.5)]}
    des = Desenho(nome="planta", escala=1.0)
    barras = [[0, 0, 6000, 0, "banzo_inf"], [0, 600, 6000, 600, "banzo_sup"], [0, 0, 0, 600, "extremidade"],
              [6000, 0, 6000, 600, "extremidade"], [3000, 0, 3000, 600, "montante"], [0, 600, 3000, 0, "diagonal"],
              [3000, 0, 6000, 600, "diagonal"]]
    for x in (0.0, 5000.0, 10000.0):
        des.add(Linha(camada="E", a=(x, 0.0), b=(x, 6000.0), atributos={
            "elemento": "trelica", "material": "aco", "marca": "T",
            "perfis": {"banzo_sup": "U 127×50×3,00 (FF)", "banzo_inf": "U 127×50×3,00 (FF)", "diagonal": "L 25×3 (FF)"},
            "nivel_base": 5000, "desenho": {"barras": barras, "vao": 6000, "altura": 600}}))
    ids = []
    for x0, x1 in ((0.0, 5000.0), (5000.0, 10000.0)):
        e = Linha(camada="E", a=(x0, 3000.0), b=(x1, 3000.0), atributos={
            "elemento": "viga", "material": "aco", "papel": "terça", "marca": "TC", "secao": {"perfil": "U 127×50×2,25 (FF)"},
            "nivel_topo": 5000 + 600 + 63.5 + 1.5, "alinhamento": "base", "suporte": st})
        des.add(e)
        ids.append(e.id)
    return des, ids


def test_terca_estendida_ate_a_face_da_tesoura_da_ponta_nao_volta_como_mudanca():
    des, ids = _planta_com_tercas_na_tesoura_da_ponta()
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    tc = {b.atributos["origem_2d"]: b for b in doc.entidades.values() if isinstance(b, Barra) and b.papel == "terça"}
    assert all(b.comprimento > 5010.0 for b in tc.values())     # a montagem estendeu as duas: é o caso
    antes = _texto(des)
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == [], r["alteracoes"]
    assert _texto(des) == antes
    _andar(tc[ids[0]], (0.0, 200.0, 0.0))                       # a terça andou 200 mm ao longo da tesoura
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga TC: movida 200 mm"]
    assert des.entidades[ids[0]].a == pytest.approx((0.0, 3200.0)) and des.entidades[ids[0]].b == pytest.approx((5000.0, 3200.0))
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == []


# ------------------------------------------------------------------ o carimbo da montagem na barra do 3D
def _pequena_com_a_volta_feita(giro=0.0):
    """a tesoura pequena com aleta na Montagem, o CV1 movido 150 mm no 3D e a volta feita: (planta, 3D, ids)"""
    real, ids = _planta_pequena("aleta", 5000.0)
    des = _na_montagem(real, giro)
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    cv1 = next(b for b in doc.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == ids[0])
    _andar(cv1, (0.0, 150.0, 0.0))
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga CV1: movida 150 mm"] and r["modelo_mudou"] == [cv1.id]
    return des, doc, ids


def _cv(doc, eid):
    return next(b for b in doc.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == eid)


def test_a_montagem_carimba_a_barra_de_cada_viga_de_aco_e_so_ela():
    real, ids = _planta_pequena("aleta", 5000.0)
    doc, _av = DPE.modelo_da_planta(real, [])
    com = [p3 for p3 in doc.entidades.values() if DPE.GERADA in (p3.atributos or {})]
    assert sorted(p3.atributos["origem_2d"] for p3 in com) == sorted(ids)      # os dois contraventos; a tesoura e as aletas não
    for b in com:
        assert b.atributos[DPE.GERADA] == [list(b.inicio), list(b.fim)]         # depois do alongamento: onde a montagem a deixou
    assert DPE.GERADA not in json.dumps(real.dict(), ensure_ascii=False)       # a planta não guarda nada


def test_projeto_antigo_sem_o_carimbo_a_primeira_volta_funciona_e_carimba(hangar_bruto):
    """o modelo gravado antes de 14/11 não tem o carimbo em peça nenhuma: a 1ª volta traz a mudança pela régua da
    montagem, só a barra que mudou ganha o carimbo, e a planta não ganha atributo nenhum"""
    bruto, niveis, modelo = hangar_bruto
    des, doc = Desenho.de_dict(copy.deepcopy(bruto)), _sem_carimbo(Documento.de_dict(copy.deepcopy(modelo)))
    assert DPE.GERADA not in json.dumps(doc.dict(), ensure_ascii=False)
    cv, eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    chaves_antes = {k: set(e.atributos) for k, e in des.entidades.items()}
    _andar(cv, (0.0, 200.0, 0.0))
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == ["viga CV5: movida 200 mm"] and r["modelo_mudou"] == [cv.id]
    assert [p3.id for p3 in doc.entidades.values() if DPE.GERADA in (p3.atributos or {})] == [cv.id]
    assert {k: set(e.atributos) for k, e in des.entidades.items()} == chaves_antes
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == []


def test_o_carimbo_sobrevive_a_gravar_e_reabrir_o_modelo(tmp_path):
    """pelo gerente de projetos (o que a rota grava) e pelo documento do editor 3D (abrir, mover a barra e gravar)"""
    import shutil
    import subprocess
    from projetos import Projetos
    des, doc, ids = _pequena_com_a_volta_feita()
    cv1 = _cv(doc, ids[0])
    carimbo = json.loads(json.dumps(cv1.atributos[DPE.GERADA]))
    assert carimbo == [list(cv1.inicio), list(cv1.fim)]                         # atualizado na volta: onde a barra está
    g = Projetos(str(tmp_path))
    s = g.criar("Volta", tipo="desenho")["slug"]
    g.salvar_modelo(s, doc.dict(), marco=True)
    aberto = g.abrir_modelo(s)
    doc2 = Documento.de_dict(copy.deepcopy(aberto))
    assert _cv(doc2, ids[0]).atributos[DPE.GERADA] == carimbo
    assert DPE.montagem_do_modelo(des, doc2, [])["alteracoes"] == []           # reaberto, o que já veio não vem de novo
    node = shutil.which("node")
    if not node:
        pytest.skip("sem o Node: o documento do editor 3D não roda aqui")
    js = "file:///" + os.path.abspath(os.path.join(os.path.dirname(AQUI), "web", "editor3d", "nucleo", "documento.js")).replace("\\", "/")
    # no editor: abrir, mover a barra 80 mm em y (as pontas mudam, os atributos ficam) e gravar
    roteiro = ("import { Documento } from %s;\n"
               "let t = ''; process.stdin.on('data', d => t += d); process.stdin.on('end', () => {\n"
               "  const { modelo, id } = JSON.parse(t); const doc = Documento.deJSON(modelo); const e = doc.entidades.get(id);\n"
               "  e.inicio = [e.inicio[0], e.inicio[1] + 80, e.inicio[2]]; e.fim = [e.fim[0], e.fim[1] + 80, e.fim[2]];\n"
               "  process.stdout.write(doc.paraTexto());\n"
               "});\n" % json.dumps(js.replace(" ", "%20")))
    r = subprocess.run([node, "--input-type=module", "-e", roteiro], input=json.dumps({"modelo": aberto, "id": cv1.id}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    doc3 = Documento.de_dict(json.loads(r.stdout))
    assert _cv(doc3, ids[0]).atributos[DPE.GERADA] == carimbo                  # o carimbo ficou; a barra andou
    assert DPE.montagem_do_modelo(des, doc3, [])["alteracoes"] == ["viga CV1: movida 80 mm"]


def test_o_carimbo_nao_sai_do_modelo(tmp_path):
    """é da peça do 3D, só para a volta: não vai para a planta, para o IFC exportado, para a lista de materiais nem
    para o DXF do desenho"""
    from ifc import exportar as ifc_exportar
    des, doc, ids = _pequena_com_a_volta_feita()
    assert DPE.GERADA in _cv(doc, ids[0]).atributos
    assert "gerada" not in _texto(des)                                          # a planta (e o que sai dela)
    assert "gerada" not in des.para_dxf().dxf().lower()
    caminho = os.path.join(str(tmp_path), "volta.ifc")
    ifc_exportar.exportar(doc, caminho)
    with open(caminho, encoding="utf-8", errors="replace") as f:
        assert "gerada" not in f.read().lower()
    assert "gerada" not in json.dumps(doc.estatisticas(), ensure_ascii=False, default=str).lower()


def test_a_planta_nao_guarda_nada_apagar_redesenhar_copiar_e_mover_a_linha():
    """o que já veio mora na barra do 3D, não na linha: a linha apagada não deixa nada; a redesenhada e a copiada
    seguem a vida delas; e a linha movida na planta depois da volta não é desfeita pela volta seguinte"""
    des, doc, ids = _pequena_com_a_volta_feita()
    antiga = des.entidades[ids[0]]
    assert set(antiga.atributos) == {"elemento", "material", "papel", "marca", "secao", "nivel_topo", "alinhamento", "quadro"}
    # apagada: a peça do 3D fica sem elemento (a volta não quebra; a sincronia do CAD a tira)
    des_a = copy.deepcopy(des)
    del des_a.entidades[ids[0]]
    assert DPE.montagem_do_modelo(des_a, copy.deepcopy(doc), [])["alteracoes"] == []
    # redesenhada no mesmo lugar: elemento novo, 3D refeito, a volta mede pela barra nova
    des_r = copy.deepcopy(des)
    del des_r.entidades[ids[0]]
    nova = Linha(camada=antiga.camada, a=antiga.a, b=antiga.b, atributos=dict(antiga.atributos))
    des_r.add(nova)
    doc_r, _av = DPE.modelo_da_planta(copy.deepcopy(des_r), [])
    assert DPE.montagem_do_modelo(des_r, doc_r, [])["alteracoes"] == []
    _andar(_cv(doc_r, nova.id), (0.0, 120.0, 0.0))
    assert DPE.montagem_do_modelo(des_r, doc_r, [])["alteracoes"] == ["viga CV1: movida 120 mm"]
    # copiada 20 mm de papel adiante (Copiar do CAD leva os atributos)
    des_c = copy.deepcopy(des)
    copia = copy.deepcopy(antiga)
    copia.id = "copia-do-cv1"
    copia.a, copia.b = (antiga.a[0], antiga.a[1] + 20.0), (antiga.b[0], antiga.b[1] + 20.0)
    copia.atributos = dict(antiga.atributos, marca="CV9")
    des_c.entidades[copia.id] = copia
    doc_c, _av = DPE.modelo_da_planta(copy.deepcopy(des_c), [])
    assert DPE.montagem_do_modelo(des_c, doc_c, [])["alteracoes"] == []
    _andar(_cv(doc_c, copia.id), (0.0, 100.0, 0.0))
    assert DPE.montagem_do_modelo(des_c, doc_c, [])["alteracoes"] == ["viga CV9: movida 100 mm"]
    # movida na planta depois da volta, com o 3D ainda sem acompanhar: a volta não a leva de volta
    des_m = copy.deepcopy(des)
    e = des_m.entidades[ids[0]]
    e.a, e.b = (e.a[0], e.a[1] + 4.0), (e.b[0], e.b[1] + 4.0)                   # 4 mm de papel = 200 mm
    depois = _texto(des_m)
    assert DPE.montagem_do_modelo(des_m, doc, [])["alteracoes"] == [] and _texto(des_m) == depois


def test_a_planta_mexida_sem_o_3d_acompanhar_nao_e_desfeita_pela_volta(hangar_bruto):
    """a planta e o 3D fora de dia (a sincronia que não chegou, ou a que refez o 3D pela planta antiga no meio do
    clique — 14/11): com o carimbo, a volta só traz o que o usuário mexeu no 3D; a linha que ele mexeu na planta fica"""
    bruto, niveis, modelo = hangar_bruto
    des, doc = Desenho.de_dict(copy.deepcopy(bruto)), Documento.de_dict(copy.deepcopy(modelo))
    _cv5, eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    e = des.entidades[eid]
    e.a, e.b = (e.a[0], e.a[1] + 4.0), (e.b[0], e.b[1] + 4.0)                   # 300 mm na planta; o 3D é o de antes
    tb, _ = _barra_de(doc, des, "terça", "T.C.1")
    _andar(tb, tuple(300.0 * c for c in tb.direcao))
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == ["viga T.C.1: movida 300 mm"]
    assert des.entidades[eid].a == pytest.approx(e.a) and des.entidades[eid].b == pytest.approx(e.b)
