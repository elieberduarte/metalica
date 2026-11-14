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
from versao import VERSAO                                     # noqa: E402

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
    # a cota que muda vira mm inteiro, o meio para o MAIOR (DET-03; o round() do Python dava 6554 — revisão de 14/11, achado 5)
    assert r["alteracoes"] == ["viga T.C.1: movida 300 mm, topo 6454.5 → 6555"]
    assert des.entidades[e.id].a == pytest.approx((300.0, 0.0)) and des.entidades[e.id].atributos["nivel_topo"] == 6555
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


# ------------------------------------------------------------------ o carimbo da montagem (no 3D) e o que já veio (na planta)
def _pequena_com_a_volta_feita(giro=0.0):
    """a tesoura pequena com aleta na Montagem, o CV1 movido 150 mm no 3D e a volta feita: (planta, 3D, ids)"""
    real, ids = _planta_pequena("aleta", 5000.0)
    des = _na_montagem(real, giro)
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    cv1 = next(b for b in doc.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == ids[0])
    _andar(cv1, (0.0, 150.0, 0.0))
    modelo_antes = json.dumps(doc.dict(), sort_keys=True)
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga CV1: movida 150 mm"] and r["modelo_mudou"] == []
    assert json.dumps(doc.dict(), sort_keys=True) == modelo_antes              # a volta não mexe no modelo
    return des, doc, ids


def _cv(doc, eid):
    return next(b for b in doc.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == eid)


def _node(roteiro, entrada):
    """roda um roteiro do editor no Node (os módulos de web/), com `entrada` em JSON pela entrada padrão"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("sem o Node: os módulos do editor não rodam aqui")
    web = "file:///" + os.path.abspath(os.path.join(os.path.dirname(AQUI), "web")).replace("\\", "/").replace(" ", "%20")
    r = subprocess.run([node, "--input-type=module", "-e", roteiro.replace("WEB", web)], input=json.dumps(entrada),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


LER = "let t = ''; process.stdin.on('data', d => t += d); process.stdin.on('end', () => {\n  const E = JSON.parse(t);\n"


def test_a_montagem_carimba_a_barra_de_cada_viga_de_aco_e_so_ela():
    real, ids = _planta_pequena("aleta", 5000.0)
    doc, _av = DPE.modelo_da_planta(real, [])
    com = [p3 for p3 in doc.entidades.values() if DPE.GERADA in (p3.atributos or {})]
    assert sorted(p3.atributos["origem_2d"] for p3 in com) == sorted(ids)      # os dois contraventos; a tesoura e as aletas não
    for b in com:
        assert b.atributos[DPE.GERADA] == {"peca": b.id, "pontas": [list(b.inicio), list(b.fim)],      # depois do alongamento: onde a montagem a deixou
                                           "versao": VERSAO}                                  # e qual versão montou (reforço A)
    assert doc.metadados["de_planta_estrutura"]["versao_montagem"] == VERSAO
    assert "gerada" not in _texto(real) and DPE.TRAZIDO not in _texto(real)    # a montagem não escreve na planta


def test_projeto_antigo_sem_carimbo_nem_guardado_a_primeira_volta_funciona(hangar_bruto):
    """o projeto gravado antes de 14/11: o modelo sem o carimbo em peça nenhuma e a planta sem o guardado. A 1ª volta
    traz a mudança pela régua da montagem, não grava o modelo, e só a linha que mudou passa a guardar o que veio"""
    bruto, niveis, modelo = hangar_bruto
    des, doc = Desenho.de_dict(copy.deepcopy(bruto)), _sem_carimbo(Documento.de_dict(copy.deepcopy(modelo)))
    assert DPE.GERADA not in json.dumps(doc.dict(), ensure_ascii=False) and DPE.TRAZIDO not in _texto(des)
    cv, eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    _andar(cv, (0.0, 200.0, 0.0))
    modelo_antes = json.dumps(doc.dict(), sort_keys=True)
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert r["alteracoes"] == ["viga CV5: movida 200 mm"] and r["modelo_mudou"] == []
    assert json.dumps(doc.dict(), sort_keys=True) == modelo_antes
    assert [k for k, e in des.entidades.items() if DPE.TRAZIDO in (e.atributos or {})] == [eid]
    assert des.entidades[eid].atributos[DPE.TRAZIDO]["peca"] == cv.id
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == []
    _andar(cv, (0.0, 0.0, 30.0))                                # mexida de novo no 3D: vem só o que mudou desde a última
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert len(r["alteracoes"]) == 1 and r["alteracoes"][0].startswith("viga CV5: topo 6063.5 → 6094") and "movida" not in r["alteracoes"][0]


def test_o_guardado_e_o_carimbo_sobrevivem_a_gravar_e_reabrir(tmp_path):
    """a planta pelo gerente de projetos (o que a rota grava) e pelo documento do CAD (abrir e gravar na tela); o
    modelo pelo gerente e pelo documento do editor 3D (abrir, mover a barra e gravar)"""
    from projetos import Projetos
    des, doc, ids = _pequena_com_a_volta_feita()
    cv1 = _cv(doc, ids[0])
    guardado = json.loads(json.dumps(des.entidades[ids[0]].atributos[DPE.TRAZIDO]))
    carimbo = json.loads(json.dumps(cv1.atributos[DPE.GERADA]))
    assert guardado == {"peca": cv1.id, "barra": [list(cv1.inicio), list(cv1.fim)]} and carimbo["pontas"] != guardado["barra"] and carimbo["peca"] == cv1.id
    g = Projetos(str(tmp_path))
    s = g.criar("Volta", tipo="desenho")["slug"]
    g.salvar_desenho(s, "montagem", des.dict())
    g.salvar_modelo(s, doc.dict(), marco=True)
    planta, modelo = g.abrir_desenho(s, "montagem"), g.abrir_modelo(s)
    des2, doc2 = Desenho.de_dict(copy.deepcopy(planta)), Documento.de_dict(copy.deepcopy(modelo))
    assert des2.entidades[ids[0]].atributos[DPE.TRAZIDO] == guardado and _cv(doc2, ids[0]).atributos[DPE.GERADA] == carimbo
    assert DPE.montagem_do_modelo(des2, doc2, [])["alteracoes"] == []          # reabertos, o que já veio não vem de novo
    # pela tela: o CAD abre e grava a planta; o editor 3D abre o modelo, move a barra 80 mm em y e grava
    sai = _node("import { Desenho2D } from 'WEB/cad/nucleo/desenho2d.js';\n"
                "import { Documento } from 'WEB/editor3d/nucleo/documento.js';\n" + LER +
                "  const doc = Documento.deJSON(E.modelo); const e = doc.entidades.get(E.id);\n"
                "  e.inicio = [e.inicio[0], e.inicio[1] + 80, e.inicio[2]]; e.fim = [e.fim[0], e.fim[1] + 80, e.fim[2]];\n"
                "  process.stdout.write(JSON.stringify({ planta: Desenho2D.deJSON(E.planta).paraJSON(), modelo: JSON.parse(doc.paraTexto()) }));\n"
                "});\n", {"planta": planta, "modelo": modelo, "id": cv1.id})
    des3, doc3 = Desenho.de_dict(sai["planta"]), Documento.de_dict(sai["modelo"])
    assert des3.entidades[ids[0]].atributos[DPE.TRAZIDO] == guardado and _cv(doc3, ids[0]).atributos[DPE.GERADA] == carimbo
    assert DPE.montagem_do_modelo(des3, doc3, [])["alteracoes"] == ["viga CV1: movida 80 mm"]      # só os 80 mm novos


def test_o_carimbo_e_o_guardado_nao_saem_para_as_saidas(tmp_path):
    """o carimbo é da peça do 3D e o guardado é da linha da planta, só para a volta: um não vai para a planta, o outro
    não vai para o 3D, e nenhum para o DXF do desenho, o IFC exportado ou as estatísticas"""
    from ifc import exportar as ifc_exportar
    des, doc, ids = _pequena_com_a_volta_feita()
    assert DPE.GERADA in _cv(doc, ids[0]).atributos and DPE.TRAZIDO in des.entidades[ids[0]].atributos
    assert "gerada" not in _texto(des)
    dxf = des.para_dxf().dxf().lower()
    assert "trazido" not in dxf and "gerada" not in dxf and "line" in dxf
    novo, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])                   # o 3D refeito da planta com o guardado
    assert "trazido" not in json.dumps(novo.dict(), ensure_ascii=False)
    caminho = os.path.join(str(tmp_path), "volta.ifc")
    ifc_exportar.exportar(doc, caminho)
    with open(caminho, encoding="utf-8", errors="replace") as f:
        ifc = f.read().lower()
    assert "gerada" not in ifc and "trazido" not in ifc
    assert "gerada" not in json.dumps(doc.estatisticas(), ensure_ascii=False, default=str).lower()


def test_apagar_redesenhar_copiar_e_mover_a_linha_na_planta():
    """o guardado mora na linha e vale para uma peça do 3D: a linha apagada o leva junto; a redesenhada e a copiada
    (Copiar do CAD leva os atributos) têm outra peça no 3D e não ficam presas nele; e a linha movida na planta depois
    da volta não é desfeita pela volta seguinte"""
    des, doc, ids = _pequena_com_a_volta_feita()
    antiga = des.entidades[ids[0]]
    # apagada: nada fica na planta (a peça do 3D fica sem elemento: a volta não quebra, a sincronia do CAD a tira)
    des_a = copy.deepcopy(des)
    del des_a.entidades[ids[0]]
    assert DPE.TRAZIDO not in _texto(des_a)
    assert DPE.montagem_do_modelo(des_a, copy.deepcopy(doc), [])["alteracoes"] == []
    # redesenhada no mesmo lugar, levando até o guardado da antiga: o 3D é refeito, a peça é outra
    des_r = copy.deepcopy(des)
    del des_r.entidades[ids[0]]
    nova = Linha(camada=antiga.camada, a=antiga.a, b=antiga.b, atributos=copy.deepcopy(antiga.atributos))
    des_r.add(nova)
    doc_r, _av = DPE.modelo_da_planta(copy.deepcopy(des_r), [])
    assert DPE.montagem_do_modelo(des_r, doc_r, [])["alteracoes"] == []
    _andar(_cv(doc_r, nova.id), (0.0, 120.0, 0.0))
    assert DPE.montagem_do_modelo(des_r, doc_r, [])["alteracoes"] == ["viga CV1: movida 120 mm"]
    # copiada 20 mm de papel adiante, com os atributos: sem o 3D refeito não tem peça; com ele, mede pela peça dela
    des_c = copy.deepcopy(des)
    copia = copy.deepcopy(antiga)
    copia.id = "copia-do-cv1"
    copia.a, copia.b = (antiga.a[0], antiga.a[1] + 20.0), (antiga.b[0], antiga.b[1] + 20.0)
    copia.atributos = dict(copy.deepcopy(antiga.atributos), marca="CV9")
    des_c.entidades[copia.id] = copia
    r = DPE.montagem_do_modelo(des_c, copy.deepcopy(doc), [])
    assert r["alteracoes"] == [] and r["sem_peca"] == ["CV9"]
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


def test_o_editor_aberto_que_grava_o_modelo_dele_depois_da_volta_nao_faz_a_mudanca_vir_de_novo():
    """a tela dividida: o editor 3D tem o modelo em memória e grava de novo depois da volta (com outra peça mexida). A
    volta não escreveu nada no modelo, então não há o que ele desfazer: o que já veio não vem de novo, o novo vem"""
    des, doc, ids = _pequena_com_a_volta_feita()                # o CV1 +150 já veio
    do_editor = Documento.de_dict(json.loads(json.dumps(doc.dict())))          # o modelo que o editor tinha, regravado
    _andar(_cv(do_editor, ids[1]), (0.0, -90.0, 0.0))                           # e o usuário mexeu no CV2
    assert DPE.montagem_do_modelo(des, do_editor, [])["alteracoes"] == ["viga CV2: movida 90 mm"]
    assert DPE.montagem_do_modelo(des, do_editor, [])["alteracoes"] == []


# ------------------------------------------------------------------ copiar, dividir e trocar o perfil no editor 3D
def _terca_solta(nivel_topo=6454.5, nivel_fim=None):
    """uma terça de 5,46 m que a montagem não ajusta: (planta, 3D, id) — para ver só o efeito da ferramenta do editor"""
    des = Desenho(nome="planta", escala=100.0)
    e = Linha(camada="ESTRUTURA", a=(0.0, 0.0), b=(5460.0, 0.0), atributos={
        "elemento": "viga", "material": "aco", "papel": "terça", "marca": "T.C.1",
        "secao": {"perfil": "U 127×50×2,25 (FF)", "aco": "ASTM A36"}, "nivel_topo": nivel_topo, "alinhamento": "base"})
    if nivel_fim is not None:
        e.atributos["nivel_fim"] = nivel_fim
    des.add(e)
    doc, _ = DPE.modelo_da_planta(copy.deepcopy(des), [])
    return des, doc, e.id


@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_barra_copiada_no_3d_nao_mexe_na_linha_da_planta(modelo):
    """Copiar do editor 3D (copiasTransformadas: clone com id novo) leva o `origem_2d` e o carimbo da original: a linha
    da planta continua sendo a da original — não anda até a cópia nem muda de tamanho. (Já era assim antes do carimbo:
    a volta sempre mediu pela primeira peça do elemento.)"""
    des, doc, eid = _terca_solta()
    if modelo == "de antes":
        _sem_carimbo(doc)
    sai = _node("import { Documento } from 'WEB/editor3d/nucleo/documento.js';\n"
                "import { copiasTransformadas } from 'WEB/editor3d/ferramentas/_comum.js';\n" + LER +
                "  const doc = Documento.deJSON(E.modelo); const e = doc.entidades.get(E.id);\n"
                "  for (const c of copiasTransformadas([e], p => [p[0] + 700, p[1] + 1500, p[2]], v => v)) doc.entidades.set(c.id, c);\n"
                "  process.stdout.write(doc.paraTexto());\n});\n", {"modelo": doc.dict(), "id": _cv(doc, eid).id})
    doc2 = Documento.de_dict(sai)
    barras = [b for b in doc2.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == eid]
    assert len(barras) == 2 and abs(barras[1].inicio[1] - barras[0].inicio[1] - 1500.0) < 0.01          # a cópia existe, 1,5 m ao lado
    antes = _texto(des)
    r = DPE.planta_do_modelo(des, doc2, [])
    assert r["alteracoes"] == [] and _texto(des) == antes
    _andar(barras[0], (0.0, 250.0, 0.0))                        # a original movida: a linha anda com ela
    assert DPE.planta_do_modelo(des, doc2, [])["alteracoes"] == ["viga T.C.1: movida 250 mm"]
    assert des.entidades[eid].a == pytest.approx((0.0, 250.0))


@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_barra_dividida_no_3d_nao_encurta_a_linha_da_planta(modelo):
    """Dividir do editor 3D: o 1º pedaço fica com o id (encurtado), os outros são cópias, todos com `emenda_de`. A
    barra conta inteira: a linha da planta não muda. (Antes de 14/11 a volta media pelo 1º pedaço e encurtava a linha
    da planta até ele — "comprimento 5460 → 2000 mm, movida 1730 mm".)"""
    des, doc, eid = _terca_solta()
    if modelo == "de antes":
        _sem_carimbo(doc)
    sai = _node("import { Documento } from 'WEB/editor3d/nucleo/documento.js';\n"
                "import { clonarEntidade } from 'WEB/editor3d/ferramentas/_comum.js';\n"
                "import { pedacosDaBarra } from 'WEB/editor3d/ferramentas/dividir.js';\n" + LER +
                "  const doc = Documento.deJSON(E.modelo); const b = doc.entidades.get(E.id);\n"
                "  const pedacos = pedacosDaBarra(b, [2000]); const novas = [];\n"       # como FerramentaDividir.dividir
                "  const atr = (extra) => ({ ...(b.atributos || {}), ...extra });\n"
                "  let primeiro = null;\n"
                "  pedacos.forEach((p, i) => {\n"
                "    const campos = { inicio: p.inicio, fim: p.fim, cortes_inicio: p.cortes_inicio, cortes_fim: p.cortes_fim,\n"
                "                     recorte_inicio: p.recorte_inicio, recorte_fim: p.recorte_fim, atributos: atr({ emenda_de: b.id }) };\n"
                "    if (i === 0) { primeiro = campos; return; }\n"
                "    const c = clonarEntidade(b, 'b'); Object.assign(c, campos); novas.push(c);\n"
                "  });\n"
                "  Object.assign(b, primeiro); for (const c of novas) doc.entidades.set(c.id, c);\n"
                "  process.stdout.write(doc.paraTexto());\n});\n", {"modelo": doc.dict(), "id": _cv(doc, eid).id})
    doc2 = Documento.de_dict(sai)
    barras = [b for b in doc2.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == eid]
    assert sorted(round(b.comprimento) for b in barras) == [2000, 3460]         # dividida em 2,00 + 3,46 m
    antes = _texto(des)
    r = DPE.planta_do_modelo(des, doc2, [])
    assert r["alteracoes"] == [] and _texto(des) == antes
    for b in barras:                                            # os dois pedaços movidos juntos: a linha anda inteira
        _andar(b, (0.0, 250.0, 0.0))
    assert DPE.planta_do_modelo(des, doc2, [])["alteracoes"] == ["viga T.C.1: movida 250 mm"]
    assert des.entidades[eid].a == pytest.approx((0.0, 250.0)) and des.entidades[eid].b == pytest.approx((5460.0, 250.0))


def test_o_perfil_trocado_no_3d_nao_vira_mudanca_de_posicao():
    """trocar o perfil da barra no editor 3D (o mesmo objeto, outro `perfil`): a volta não acusa nada — ela traz
    posição, comprimento e cota; o perfil da planta continua o da planta (já era assim)"""
    des, doc, eid = _terca_solta()
    _cv(doc, eid).perfil = "U 150×50×3,00 (FF)"
    antes = _texto(des)
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == [] and _texto(des) == antes


# ------------------------------------------------------------------ o carimbo não muda o que sai do modelo
def _saidas_do_modelo(app, raiz, modelo):
    """Detalhar + Montar pranchas + lista de materiais do `modelo` num projeto novo em `raiz`: os desenhos e a lista sem
    o que muda a cada geração (ids, o nome sorteado das folhas, datas e horas)"""
    import re
    app.PROJETOS = raiz
    os.makedirs(raiz, exist_ok=True)
    g = app._gerente()
    s = g.criar("Obra", tipo="ifc")["slug"]
    g.salvar_modelo(s, modelo)
    nomes = sorted(d["nome"] for d in app.detalhar_projeto(s, {})["desenhos"])
    pr = app.montar_pranchas_projeto(s, {"desenhos": [n for n in nomes if n.startswith("detalhamento-")], "formato": "A1", "titulo": "Pranchas"})
    lista = app.lista_de_materiais(s, recalcular=True)
    fora = ("id", "geracao", "gerado", "alterado", "quando", "data")      # "gerado": a hora da lista, com o minuto

    def limpo(x):
        if isinstance(x, dict):
            return {k: limpo(v) for k, v in sorted(x.items()) if k not in fora}
        return [limpo(v) for v in x] if isinstance(x, list) else x

    def texto(x):
        return re.sub(r"folha-[0-9a-f]{6,}", "folha-X", json.dumps(limpo(x), sort_keys=True, ensure_ascii=False))
    saidas = {n: texto(g.abrir_desenho(s, n)) for n in nomes + [pr["desenho"]]}
    saidas["lista de materiais"] = texto(lista)
    return saidas, len(pr.get("pranchas") or [])


def test_detalhar_pranchas_e_lista_sao_os_mesmos_com_e_sem_o_carimbo(tmp_path, monkeypatch):
    """de ponta a ponta: o modelo da tesoura pequena (12 peças) detalhado, montado em pranchas e levantado na lista com
    o carimbo da montagem nas barras e sem ele — os mesmos 7 desenhos, as mesmas 4 folhas, a mesma lista; e o carimbo
    não aparece em nenhum deles. (A mesma geração duas vezes dá o mesmo: a comparação vale.)"""
    import app
    monkeypatch.setattr(app, "PROJETOS", str(tmp_path))
    real, _ids = _planta_pequena("aleta", 5000.0)
    doc, _av = DPE.modelo_da_planta(real, [])
    com = doc.dict()
    sem = _sem_carimbo(Documento.de_dict(copy.deepcopy(com))).dict()
    assert json.dumps(com).count(DPE.GERADA) == 2 and DPE.GERADA not in json.dumps(sem)
    s_com, folhas_com = _saidas_do_modelo(app, os.path.join(str(tmp_path), "com"), com)
    s_sem, folhas_sem = _saidas_do_modelo(app, os.path.join(str(tmp_path), "sem"), sem)
    s_de_novo, _n = _saidas_do_modelo(app, os.path.join(str(tmp_path), "de_novo"), com)
    assert len(s_com) >= 7 and folhas_com == folhas_sem and folhas_com >= 1
    assert sorted(s_com) == sorted(s_sem)
    for nome in s_com:
        assert s_com[nome] == s_de_novo[nome], nome             # a geração repete
        assert s_com[nome] == s_sem[nome], nome                 # e o carimbo não muda nada
        assert "gerada" not in s_com[nome], nome


# ------------------------------------------------------------------ os achados da revisão independente (14/11)
@pytest.mark.parametrize("nivel_fim", [None, 6454.0, 6700.0])
@pytest.mark.parametrize("caso, sobe_a, sobe_b", [("só a ponta a", 100.0, 0.0), ("só a ponta b", 0.0, 100.0),
                                                   ("as duas, diferente", 100.0, 40.0), ("as duas, igual", 70.0, 70.0),
                                                   ("uma sobe e a outra desce", 60.0, -30.0)])
def test_a_ponta_levantada_no_3d_leva_so_ela_na_planta(caso, sobe_a, sobe_b, nivel_fim):
    """achado 1: com a terça sem `nivel_fim`, só a ponta `inicio` levantada 100 mm no 3D dava "topo 6454 → 6554" e a
    ponta b ia junto (o 3D refeito punha as duas em cima). Cada ponta leva a cota dela: o 3D refeito da planta fica
    como o usuário deixou"""
    des, doc, eid = _terca_solta(nivel_topo=6454.0, nivel_fim=nivel_fim)
    b = _cv(doc, eid)
    za, zb = b.inicio[2], b.fim[2]
    b.inicio = (b.inicio[0], b.inicio[1], za + sobe_a)
    b.fim = (b.fim[0], b.fim[1], zb + sobe_b)
    r = DPE.planta_do_modelo(des, doc, [])
    assert len(r["alteracoes"]) == 1 and "movida" not in r["alteracoes"][0] and "comprimento" not in r["alteracoes"][0]
    at = des.entidades[eid].atributos
    assert at["nivel_topo"] == 6454.0 + sobe_a
    fim_esperado = (nivel_fim if nivel_fim is not None else 6454.0) + sobe_b
    if nivel_fim is None and sobe_a == sobe_b:
        assert "nivel_fim" not in at                             # as duas juntas: a ponta b segue a cota da barra
    else:
        assert at["nivel_fim"] == fim_esperado
    # o 3D refeito da planta nova: as duas pontas onde o usuário as deixou
    novo, _ = DPE.modelo_da_planta(copy.deepcopy(des), [])
    b2 = _cv(novo, eid)
    assert b2.inicio[2] == pytest.approx(za + sobe_a, abs=0.01) and b2.fim[2] == pytest.approx(zb + sobe_b, abs=0.01)
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == []
    if caso == "só a ponta a" and nivel_fim is None:
        assert r["alteracoes"] == ["viga T.C.1: topo 6454.0 → 6554, a outra ponta fica em 6454"]


def _dividir_no_editor(modelo, bid, corte):
    """Dividir do editor 3D na barra `bid`, a `corte` mm do começo dela — o que FerramentaDividir.dividir faz: o 1º
    pedaço fica com o id, os outros são cópias (clonarEntidade), todos com `emenda_de` = o id da barra dividida.
    Devolve (o modelo, os ids dos pedaços)"""
    sai = _node("import { Documento } from 'WEB/editor3d/nucleo/documento.js';\n"
                "import { clonarEntidade } from 'WEB/editor3d/ferramentas/_comum.js';\n"
                "import { pedacosDaBarra } from 'WEB/editor3d/ferramentas/dividir.js';\n" + LER +
                "  const doc = Documento.deJSON(E.modelo); const b = doc.entidades.get(E.id);\n"
                "  const pedacos = pedacosDaBarra(b, [E.corte]); const novas = []; let primeiro = null;\n"
                "  const atr = (extra) => ({ ...(b.atributos || {}), ...extra });\n"
                "  pedacos.forEach((p, i) => {\n"
                "    const campos = { inicio: p.inicio, fim: p.fim, cortes_inicio: p.cortes_inicio, cortes_fim: p.cortes_fim,\n"
                "                     recorte_inicio: p.recorte_inicio, recorte_fim: p.recorte_fim, atributos: atr({ emenda_de: b.id }) };\n"
                "    if (i === 0) { primeiro = campos; return; }\n"
                "    const c = clonarEntidade(b, 'b'); Object.assign(c, campos); novas.push(c);\n"
                "  });\n"
                "  Object.assign(b, primeiro); for (const c of novas) doc.entidades.set(c.id, c);\n"
                "  process.stdout.write(JSON.stringify({ modelo: JSON.parse(doc.paraTexto()), ids: [b.id, ...novas.map(c => c.id)] }));\n});\n",
                {"modelo": modelo, "id": bid, "corte": corte})
    return sai["modelo"], sai["ids"]


FORA_DA_RETA = "viga T.C.1: barra dividida com pedaço fora da reta: a planta não foi alterada"


@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_barra_dividida_com_um_pedaco_fora_da_reta_nao_altera_a_planta_e_a_volta_diz(modelo):
    """achado 2a: a terça dividida em duas e só o 2º pedaço levantado 10 mm — o pedaço saía da reta, era tratado como
    cópia e a linha da planta encurtava até o 1º ("comprimento 5460 → 2000 mm, movida 1730 mm"). A linha da planta
    nunca encurta por causa de divisão: quando os pedaços não formam mais uma barra reta só, a volta não altera a
    linha e diz isso"""
    des, doc, eid = _terca_solta()
    if modelo == "de antes":
        _sem_carimbo(doc)
    m, ids = _dividir_no_editor(doc.dict(), _cv(doc, eid).id, 2000)
    doc2 = Documento.de_dict(m)
    _andar(doc2.entidades[ids[1]], (0.0, 0.0, 10.0))
    antes = _texto(des)
    for _vez in (1, 2):
        r = DPE.planta_do_modelo(des, doc2, [])
        assert r["alteracoes"] == [FORA_DA_RETA] and r["mudados"] == [] and _texto(des) == antes
    # e pelo lado: o 2º pedaço 300 mm para o lado também não encurta a linha
    _andar(doc2.entidades[ids[1]], (0.0, 300.0, -10.0))
    assert DPE.planta_do_modelo(des, doc2, [])["alteracoes"] == [FORA_DA_RETA] and _texto(des) == antes
    # o pedaço de volta ao lugar: a barra é uma só de novo e nada mudou
    _andar(doc2.entidades[ids[1]], (0.0, -300.0, 0.0))
    assert DPE.planta_do_modelo(des, doc2, [])["alteracoes"] == [] and _texto(des) == antes


@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_barra_dividida_duas_vezes_conta_inteira(modelo):
    """achado 2b: dividir de novo o 2º pedaço — o dividir.js grava `emenda_de` com o id do pedaço que está sendo
    dividido, os pedaços novos saíam da conta e a linha encurtava (5460 → 2000). Todos os pedaços do elemento contam"""
    des, doc, eid = _terca_solta()
    if modelo == "de antes":
        _sem_carimbo(doc)
    m, ids = _dividir_no_editor(doc.dict(), _cv(doc, eid).id, 2000)
    m, ids2 = _dividir_no_editor(m, ids[1], 1500)                 # o 2º pedaço (3,46 m) em 1,50 + 1,96
    doc2 = Documento.de_dict(m)
    barras = [b for b in doc2.entidades.values() if isinstance(b, Barra) and b.atributos.get("origem_2d") == eid]
    assert sorted(round(b.comprimento) for b in barras) == [1500, 1960, 2000]
    assert {b.atributos["emenda_de"] for b in barras} == {ids[0], ids[1]}       # a cadeia: o 3º aponta para o 2º
    antes = _texto(des)
    r = DPE.planta_do_modelo(des, doc2, [])
    assert r["alteracoes"] == [] and _texto(des) == antes
    for b in barras:
        _andar(b, (0.0, 250.0, 0.0))
    assert DPE.planta_do_modelo(des, doc2, [])["alteracoes"] == ["viga T.C.1: movida 250 mm"]
    assert des.entidades[eid].a == pytest.approx((0.0, 250.0)) and des.entidades[eid].b == pytest.approx((5460.0, 250.0))


def test_a_barra_dividida_com_pedaco_copiado_apagado_ou_faltando_no_meio():
    """os outros jeitos de a divisão deixar de ser uma barra só: a cópia de um pedaço posta ao lado não conta (a barra
    está inteira na reta); o pedaço do meio apagado deixa um vão — a volta não altera e diz; o último pedaço apagado é
    a barra que o usuário encurtou no 3D (não tem pedaço fora da reta): a linha acompanha"""
    des, doc, eid = _terca_solta()
    m, ids = _dividir_no_editor(doc.dict(), _cv(doc, eid).id, 2000)
    m, ids2 = _dividir_no_editor(m, ids[1], 1500)
    antes = _texto(des)
    # a cópia do 2º pedaço 800 mm ao lado
    d1 = Documento.de_dict(copy.deepcopy(m))
    c = copy.deepcopy(d1.entidades[ids[1]])
    c.id = "copia-do-pedaco"
    _andar(c, (0.0, 800.0, 0.0))
    d1.entidades[c.id] = c
    assert DPE.planta_do_modelo(des, d1, [])["alteracoes"] == [] and _texto(des) == antes
    # o pedaço do meio apagado
    d2 = Documento.de_dict(copy.deepcopy(m))
    del d2.entidades[ids[1]]
    assert DPE.planta_do_modelo(des, d2, [])["alteracoes"] == [FORA_DA_RETA] and _texto(des) == antes
    # o último pedaço apagado: a barra ficou com 3,50 m
    d3 = Documento.de_dict(copy.deepcopy(m))
    del d3.entidades[ids2[1]]
    # (o GESTÃO N.10, 14/11: a linha acompanha, mas a mensagem diz com as palavras o que aconteceu)
    assert DPE.planta_do_modelo(des, d3, [])["alteracoes"] == [
        "viga T.C.1: encurtada no 3D (barra dividida, o pedaço da ponta apagado), comprimento 5460 → 3500 mm, movida 980 mm"]
    assert des.entidades[eid].a == pytest.approx((0.0, 0.0)) and des.entidades[eid].b == pytest.approx((3500.0, 0.0))
    assert DPE.planta_do_modelo(des, d3, [])["alteracoes"] == []



@pytest.mark.parametrize("onde", ["no mesmo lugar", "80 mm ao lado"])
def test_a_mudanca_ja_trazida_nao_soma_de_novo_na_barra_copiada_com_a_original_apagada(onde):
    """achado 3: a volta trouxe o CV1 +150; antes de a sincronia refazer o 3D, a barra ganha outro id com os mesmos
    atributos (copiar e apagar a original). O guardado da planta aponta para o id antigo e deixa de valer; a volta media
    pelo carimbo copiado e trazia os +150 de novo (300 no total). O carimbo vale só na peça para a qual a montagem o fez:
    a cópia mede-se pela régua da montagem"""
    des, doc, ids = _pequena_com_a_volta_feita()                # o CV1 +150 já veio
    a0 = _real(des, ids[0]).a                                 # em mm reais (a Montagem é o papel, em escala)
    cv1 = _cv(doc, ids[0])
    c = copy.deepcopy(cv1)
    c.id = "copia-do-cv1"
    del doc.entidades[cv1.id]
    if onde == "80 mm ao lado":
        _andar(c, (0.0, 80.0, 0.0))
    doc.entidades[c.id] = c
    r = DPE.montagem_do_modelo(des, doc, [])
    if onde == "no mesmo lugar":
        assert r["alteracoes"] == [] and _real(des, ids[0]).a == pytest.approx(a0)
    else:
        assert r["alteracoes"] == ["viga CV1: movida 80 mm"]
        assert _real(des, ids[0]).a == pytest.approx((a0[0], a0[1] + 80.0), abs=0.01)
    assert DPE.montagem_do_modelo(des, doc, [])["alteracoes"] == []


def _girar(b, graus):
    """gira a barra em planta em torno do meio dela, sem mudar o comprimento"""
    mx, my = (b.inicio[0] + b.fim[0]) / 2, (b.inicio[1] + b.fim[1]) / 2
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))

    def g(p):
        x, y = p[0] - mx, p[1] - my
        return (mx + x * c - y * s, my + x * s + y * c, p[2])
    b.inicio, b.fim = g(b.inicio), g(b.fim)


def test_a_barra_girada_no_3d_em_torno_do_meio_vai_para_a_planta_e_diz():
    """achado 4: a barra girada 5° em torno do meio, sem mudar o comprimento — a volta mexia a linha na memória sem
    entrada nenhuma (alteracoes = [], mudados = []): na Montagem nunca chegava ao papel, e na planta só era gravada se
    outra peça mudasse junto. Agora diz "girada 5,0°" e entra nos mudados"""
    des, doc, eid = _terca_solta()
    _girar(_cv(doc, eid), 5.0)
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga T.C.1: girada 5,0°"] and r["mudados"] == [eid]
    e = des.entidades[eid]
    ang = math.degrees(math.atan2(e.b[1] - e.a[1], e.b[0] - e.a[0]))
    assert ang == pytest.approx(5.0, abs=0.01) and math.dist(e.a, e.b) == pytest.approx(5460.0, abs=0.01)
    assert DPE.planta_do_modelo(des, doc, [])["alteracoes"] == []


def test_a_barra_girada_no_3d_chega_ao_papel_da_montagem():
    """o mesmo na Montagem: o CV1 girado 5° em torno do meio chega ao papel (pelo mapa inverso do quadro)"""
    real, ids = _planta_pequena("aleta", 5000.0)
    des = _na_montagem(real, 0.0)
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    a0 = _real(des, ids[0])
    ang0 = math.degrees(math.atan2(a0.b[1] - a0.a[1], a0.b[0] - a0.a[0]))
    _girar(_cv(doc, ids[0]), 5.0)
    r = DPE.montagem_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga CV1: girada 5,0°"] and r["mudados"] == [ids[0]]
    e = _real(des, ids[0])
    assert math.degrees(math.atan2(e.b[1] - e.a[1], e.b[0] - e.a[0])) == pytest.approx(ang0 + 5.0, abs=0.05)
    assert DPE.montagem_do_modelo(des, doc, [])["alteracoes"] == []


def test_a_ponta_ajustada_de_lado_pouco_mais_que_1_mm_nao_e_calada():
    """a ponta b 1,5 mm de lado: nem comprimento, nem movida, nem giro passam da tolerância — mas a linha mudava calada"""
    des, doc, eid = _terca_solta()
    b = _cv(doc, eid)
    b.fim = (b.fim[0], b.fim[1] + 1.5, b.fim[2])
    r = DPE.planta_do_modelo(des, doc, [])
    assert r["alteracoes"] == ["viga T.C.1: ponta ajustada 2 mm"] and r["mudados"] == [eid]


@pytest.mark.parametrize("modelo", ["de agora", "pela conta de sempre"])
def test_a_cota_que_vem_do_3d_e_mm_inteiro_o_meio_para_o_maior(modelo):
    """achado 5 (reincidência da DET-03, "mm inteiro; na dúvida, o MAIOR"): o round() do Python leva o meio para o par —
    6554,5 → 6554 e 6800,5 → 6800. As três cotas da volta (o topo, a outra ponta e a da conta sem referência) sobem o
    meio, como o formatar_cota das pranchas e o numeroDaCota do CAD"""
    if modelo == "de agora":
        des, doc, eid = _terca_solta(nivel_topo=6454.5, nivel_fim=6700.5)
        _andar(_cv(doc, eid), (0.0, 0.0, 100.0))
        r = DPE.planta_do_modelo(des, doc, [])
        assert r["alteracoes"] == ["viga T.C.1: topo 6454.5 → 6555, topo da outra ponta 6700.5 → 6801"]
        at = des.entidades[eid].atributos
        assert (at["nivel_topo"], at["nivel_fim"]) == (6555, 6801)
    else:
        # sem carimbo e sem a régua da montagem: a cota pela barra (o elemento que a montagem de agora não refaz)
        des, doc, eid = _terca_solta(nivel_topo=6454.5)
        _sem_carimbo(doc)
        _andar(_cv(doc, eid), (0.0, 0.0, 100.0))
        r = DPE._volta_do_3d(des, doc, [], 1.0, None)
        assert r["alteracoes"] == ["viga T.C.1: topo 6454.5 → 6555"] and des.entidades[eid].atributos["nivel_topo"] == 6555


# ------------------------------------------------------------------ o modelo gravado por uma versão anterior (reforço A)
def _hangar_da_versao(hangar_bruto, versao):
    """a Montagem de hoje e o 3D que a montagem da `versao` publicada fez dela (dados_cad/hangar_gerado_<versao>.json,
    feito por dados_cad/gerar_hangar_de_versao_antiga.py: só as peças com origem_2d fora das tesouras, sem carimbo)"""
    bruto, niveis, _modelo = hangar_bruto
    with open(os.path.join(AQUI, "dados_cad", "hangar_gerado_%s.json" % versao), encoding="utf-8") as f:
        antigo = json.load(f)
    doc = Documento.de_dict(antigo["modelo"])
    assert DPE.GERADA not in json.dumps(antigo["modelo"], ensure_ascii=False) and len(doc.entidades) == 275
    return Desenho.de_dict(copy.deepcopy(bruto)), niveis, doc


@pytest.mark.parametrize("versao", ["v0_9_2", "v0_9_0"])
def test_modelo_de_versao_anterior_sem_mexer_a_volta_nao_devolve_nada(hangar_bruto, versao):
    des, niveis, doc = _hangar_da_versao(hangar_bruto, versao)
    antes = _texto(des)
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == [] and _texto(des) == antes


def test_modelo_da_v092_um_contravento_movido_volta_so_ele(hangar_bruto):
    """a v0.9.2 monta o Hangar igual à de hoje (0 de 275 elementos diferem): a régua vale"""
    des, niveis, doc = _hangar_da_versao(hangar_bruto, "v0_9_2")
    cv, _eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    _andar(cv, (0.0, 200.0, 0.0))
    assert DPE.montagem_do_modelo(des, doc, niveis)["alteracoes"] == ["viga CV5: movida 200 mm"]


def test_modelo_da_v090_um_contravento_movido_nao_traz_os_outros_31(hangar_bruto):
    """a 0.9.0 (21/10) não alongava a ponta do contravento até o furo da aleta: as barras dela não são as da régua de
    hoje. 1 CV movido 200 mm dava 32 alterações (CV1–CV8 ×4, "comprimento 6575 → 6493 mm, movida 231 mm…"). Vale só
    "viga CV5: movida 200 mm", ou nada na planta com um aviso — nunca as 32 caladas"""
    des, niveis, doc = _hangar_da_versao(hangar_bruto, "v0_9_0")
    cv, _eid = _barra_de(doc, des, "contraventamento", "CV5", "inf")
    _andar(cv, (0.0, 200.0, 0.0))
    antes = _texto(des)
    r = DPE.montagem_do_modelo(des, doc, niveis)
    so_ele = r["alteracoes"] == ["viga CV5: movida 200 mm"]
    recusa = _texto(des) == antes and len(r["alteracoes"]) == 1 and "versão" in r["alteracoes"][0]
    assert so_ele or recusa, r["alteracoes"][:4]


def test_varias_tercas_mexidas_de_verdade_no_modelo_sem_carimbo_voltam_todas(hangar):
    """o caso que NÃO pode ser barrado: 10 terças movidas de verdade no 3D (com e sem o carimbo — o modelo gravado
    pela montagem de hoje antes de 14/11): as 10 voltam, cada uma com o que andou, e só elas"""
    des, niveis, doc = hangar
    tercas = []
    for e in des.entidades.values():
        a = e.atributos or {}
        if a.get("papel") == "terça" and len(tercas) < 10:
            b = next((x for x in doc.entidades.values() if isinstance(x, Barra) and (x.atributos or {}).get("origem_2d") == e.id), None)
            if b is not None:
                tercas.append((a.get("marca"), b))
    assert len(tercas) == 10
    for _m, b in tercas:
        _andar(b, tuple(150.0 * c for c in b.direcao))
    r = DPE.montagem_do_modelo(des, doc, niveis)
    assert sorted(r["alteracoes"]) == sorted("viga %s: movida 150 mm" % m for m, _b in tercas)


@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_ponta_estendida_pela_montagem_e_encurtada_no_3d_vale_a_regua(modelo):
    """o contraexemplo do GESTÃO N.10 (14/11) ao "vence a referência com menos deslocamento": a montagem de hoje estende
    a terça até a face de fora da tesoura do oitão; o usuário encurta no 3D essa ponta em 60 % do que a montagem
    estendeu (o ajuste fino de verdade). Pela régua (onde a montagem a pôs) a ponta andou −0,6·L; pela linha da planta,
    +0,4·L — o menor deslocamento escolheria a linha, a planta ganharia +0,4·L e a próxima montagem estenderia de novo:
    o 3D ficaria mais comprido do que o usuário deixou. Vale a régua: a linha da planta encurta 0,6·L na ponta dela"""
    des, ids = _planta_com_tercas_na_tesoura_da_ponta()
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    if modelo == "de antes":
        _sem_carimbo(doc)
    tc = _cv(doc, ids[0])
    estendida = -tc.inicio[0]                                   # a terça vai de x = 0 a 5000 na planta; no 3D, além do 0
    assert estendida > 10.0 and abs(tc.fim[0] - 5000.0) < estendida, (tc.inicio, tc.fim)
    s = round(0.6 * estendida, 1)
    tc.inicio = (tc.inicio[0] + s, tc.inicio[1], tc.inicio[2])  # a ponta do oitão encurtada no 3D
    r = DPE.planta_do_modelo(des, doc, [])
    assert len(r["alteracoes"]) == 1 and r["alteracoes"][0].startswith("viga TC: comprimento 5000 → %d mm" % round(5000 - s))
    e = des.entidades[ids[0]]
    assert e.a == pytest.approx((s, 3000.0), abs=0.01) and e.b == pytest.approx((5000.0, 3000.0), abs=0.01)


@pytest.mark.xfail(strict=True, reason="LIMITE do 'puxar até' (14/11, BUGS N.4 → GESTÃO N.10 → usuário, 4º caso do "
                   "'é assim?' do Trazer do 3D): a montagem leva a ponta da terça até a face da tesoura do oitão (−63,5) só "
                   "com a ponta da linha a até 1 mm do cruzamento; o usuário encurta no 3D até −25,4, a volta soma o delta "
                   "à linha (+38,1), a linha sai do cruzamento e o 3D refeito fica em +38,1 — 63,5 mm mais curto, calado. "
                   "Vale hoje com carimbo e na 0.9.2/0.9.3 pela régua. Saída recomendada (B): a ponta da linha onde está a "
                   "do 3D quando a montagem a tinha puxado. Quando a decisão entrar, este teste passa e o xfail sai")
@pytest.mark.parametrize("modelo", ["de agora", "de antes"])
def test_a_ponta_estendida_e_encurtada_no_3d_o_3d_refeito_fica_onde_o_usuario_deixou(modelo):
    """a mesma ponta encurtada no 3D, pelo que importa ao usuário: o 3D refeito da planta depois da volta tem a ponta
    onde ele a deixou. A extensão até a face da tesoura do oitão só acontece com a ponta da linha no cruzamento com a
    tesoura (±1 mm, _suportes_das_tercas): a linha que a volta tira de lá deixa de ser estendida — então a referência
    que "devolve" o ajuste depende da regra de montagem da peça, e este teste diz qual vale aqui (14/11, para o GESTÃO)"""
    des, ids = _planta_com_tercas_na_tesoura_da_ponta()
    doc, _av = DPE.modelo_da_planta(copy.deepcopy(des), [])
    if modelo == "de antes":
        _sem_carimbo(doc)
    tc = _cv(doc, ids[0])
    estendida = -tc.inicio[0]
    s = round(0.6 * estendida, 1)
    tc.inicio = (tc.inicio[0] + s, tc.inicio[1], tc.inicio[2])
    DPE.planta_do_modelo(des, doc, [])
    novo, _ = DPE.modelo_da_planta(copy.deepcopy(des), [])
    assert _cv(novo, ids[0]).inicio[0] == pytest.approx(tc.inicio[0], abs=0.5), (_cv(novo, ids[0]).inicio, tc.inicio)
