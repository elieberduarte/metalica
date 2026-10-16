# -*- coding: utf-8 -*-
"""As ferramentas de modelagem estrutural do editor 3D (14/10/2026): terças por espaçamento, treliça entre banzos,
contraventamento em X, pilares nos eixos e viga entre pilares — a geometria que devolvem, sem mexer no documento."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.base import ErroDeDados  # noqa: E402
from nucleo3d.modelo import Barra, Documento  # noqa: E402
from nucleo3d.geometria import malha_barra  # noqa: E402
from nucleo3d import modelagem  # noqa: E402


def _doc(*ents):
    d = Documento()
    for e in ents:
        d.add(e)
    return d


def _barras(r):
    return [Barra(**{k: v for k, v in e.items() if k != "tipo"}) for e in r["novas"]]


# ------------------------------------------------------------------ terças

def _duas_tesouras(caimento=0.10):
    """dois banzos de cima (W 150) de uma água, 6 m de vão em planta, a 5 m um do outro"""
    z1 = 6000 * caimento
    t1 = Barra(nome="T1", inicio=(0, 0, 5000), fim=(6000, 0, 5000 + z1), perfil="W 150×13", papel="banzo")
    t2 = Barra(nome="T2", inicio=(0, 5000, 5000), fim=(6000, 5000, 5000 + z1), perfil="W 150×13", papel="banzo")
    return _doc(t1, t2), t1, t2


def test_tercas_igualmente_espacadas_sem_passar_do_pedido():
    doc, t1, t2 = _duas_tesouras()
    n0 = len(doc.entidades)
    r = modelagem.tercas(doc, [t1.id, t2.id], {"espacamento": 1500, "beiral": 200, "cumeeira": 250})
    assert len(doc.entidades) == n0                       # não mexe no documento
    L = math.dist(t1.inicio, t1.fim)
    util = L - 450
    n = math.ceil(util / 1500)
    assert r["resumo"]["linhas"] == n + 1
    assert r["resumo"]["passo"] <= 1500
    bs = _barras(r)
    assert len(bs) == n + 1                               # um vão: uma terça por linha
    for b in bs:
        assert b.papel == "terça"
        assert abs(b.inicio[1] - 0) < 1 and abs(b.fim[1] - 5000) < 1   # de apoio a apoio


def test_terca_senta_no_topo_do_apoio():
    doc, t1, t2 = _duas_tesouras(caimento=0.0)
    r = modelagem.tercas(doc, [t1.id, t2.id], {"espacamento": 2000, "perfil": "Ue 150×60×20×2,25"})
    b = _barras(r)[0]
    vs, _ = malha_barra(b)
    vt, _ = malha_barra(t1)
    assert abs(min(q[2] for q in vs) - max(q[2] for q in vt)) < 0.5     # a base da terça no topo da mesa
    # o eixo forte em pé (a altura da seção na vertical)
    assert max(q[2] for q in vs) - min(q[2] for q in vs) == pytest.approx(150, abs=0.5)


def test_tercas_em_tres_apoios_por_vao_ou_continua():
    doc, t1, t2 = _duas_tesouras()
    t3 = Barra(nome="T3", inicio=(0, 10000, 5000), fim=(6000, 10000, 5600), perfil="W 150×13", papel="banzo")
    doc.add(t3)
    r = modelagem.tercas(doc, [t3.id, t1.id, t2.id], {"espacamento": 3000})
    linhas = r["resumo"]["linhas"]
    assert len(r["novas"]) == 2 * linhas
    r = modelagem.tercas(doc, [t1.id, t2.id, t3.id], {"espacamento": 3000, "continua": "sim", "balanco": 300})
    bs = _barras(r)
    assert len(bs) == linhas
    assert min(b.inicio[1] for b in bs) == pytest.approx(-300, abs=1)
    assert max(b.fim[1] for b in bs) == pytest.approx(10300, abs=1)


def test_tercas_recusa_apoio_em_pe_e_um_so():
    doc, t1, t2 = _duas_tesouras()
    with pytest.raises(ErroDeDados):
        modelagem.tercas(doc, [t1.id], {})
    p = Barra(inicio=(0, 8000, 0), fim=(0, 8000, 5000), perfil="W 150×13", papel="pilar")
    doc.add(p)
    with pytest.raises(ErroDeDados):
        modelagem.tercas(doc, [t1.id, p.id], {})


# ------------------------------------------------------------------ treliça

def _banzos(peca=None):
    at = {"origem": {"peca": peca}} if peca else {}
    sup = Barra(nome="BS", inicio=(0, 0, 1000), fim=(6000, 0, 1000), perfil="U 100×40×2,65", papel="banzo",
                atributos=dict(at))
    inf = Barra(nome="BI", inicio=(0, 0, 0), fim=(6000, 0, 0), perfil="U 100×40×2,65", papel="banzo",
                atributos=dict(at))
    return _doc(sup, inf), sup, inf


@pytest.mark.parametrize("tipo", ["pratt", "howe"])
def test_trelica_pratt_e_howe_montantes_e_diagonais(tipo):
    doc, sup, inf = _banzos()
    r = modelagem.trelica(doc, [sup.id, inf.id], {"tipo": tipo, "passo": 1000})
    n = r["resumo"]["paineis"]
    assert n == 6
    bs = _barras(r)
    assert sum(b.papel == "montante" for b in bs) == n + 1
    assert sum(b.papel == "diagonal" for b in bs) == n
    # os banzos entram no bloco da treliça
    assert set(r["alterar"]) == {sup.id, inf.id}
    assert all(c["atributos"]["origem"]["peca"] == "TRELIÇA" for c in r["alterar"].values())
    # Pratt: a primeira diagonal desce do banzo de cima para o meio
    d0 = min((b for b in bs if b.papel == "diagonal"), key=lambda b: min(b.inicio[0], b.fim[0]))
    alto, baixo = (d0.inicio, d0.fim) if d0.inicio[2] > d0.fim[2] else (d0.fim, d0.inicio)
    if tipo == "pratt":
        assert alto[0] < baixo[0]
    else:
        assert alto[0] > baixo[0]


def test_trelica_warren_e_bloco_existente_dos_banzos():
    doc, sup, inf = _banzos(peca="TESOURA 1#1")
    r = modelagem.trelica(doc, [sup.id, inf.id], {"tipo": "warren", "paineis": 6})
    bs = _barras(r)
    assert all(b.papel == "diagonal" for b in bs) and len(bs) == 6
    assert all(b.atributos["origem"]["peca"] == "TESOURA 1#1" for b in bs)
    # os banzos já são do bloco: só o giro muda (a boca do U para o miolo, regras_trelica T2 — 16/10)
    assert all(set(c) == {"rotacao"} for c in r["alterar"].values())


def test_trelica_encaixa_as_almas_nas_faces_dos_banzos():
    doc, sup, inf = _banzos()
    r = modelagem.trelica(doc, [sup.id, inf.id], {"tipo": "pratt", "passo": 1500})
    assert not r["avisos"], r["avisos"]
    bs = _barras(r)
    # os banzos com o giro da regra (regras_trelica T2, 16/10: a boca do U para o miolo — as abas viradas para dentro)
    for bz in (sup, inf):
        bz.rotacao = r["alterar"].get(bz.id, {}).get("rotacao", bz.rotacao)
    face_sup = min(q[2] for q in malha_barra(sup)[0])
    face_inf = max(q[2] for q in malha_barra(inf)[0])
    assert face_sup < 1000 - 20 and face_inf > 20                     # as abas do U descem/sobem para o miolo
    # as almas não atravessam os banzos: a malha fica entre a face de baixo do de cima e a de cima do de baixo
    for b in bs:
        vs, _ = malha_barra(b)
        assert max(q[2] for q in vs) <= face_sup + 1.0, (b.papel, max(q[2] for q in vs))
        assert min(q[2] for q in vs) >= face_inf - 1.0


# ------------------------------------------------------------------ contravento

def test_contravento_x_entre_dois_pilares_em_dois_paineis():
    a = Barra(inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 150×13", papel="pilar")
    b = Barra(inicio=(5000, 0, 6000), fim=(5000, 0, 0), perfil="W 150×13", papel="pilar")   # ao contrário
    doc = _doc(a, b)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 2, "margem": 300})
    bs = _barras(r)
    assert len(bs) == 4
    zs = sorted({round(q[2]) for x in bs for q in (x.inicio, x.fim)})
    assert zs == [300, 3000, 5700]
    # as duas de cada painel se cruzam no meio do painel
    for k in range(2):
        d1, d2 = bs[2 * k], bs[2 * k + 1]
        m1 = [(u + v) / 2 for u, v in zip(d1.inicio, d1.fim)]
        m2 = [(u + v) / 2 for u, v in zip(d2.inicio, d2.fim)]
        assert math.dist(m1, m2) < 1


def test_contravento_recusa_barras_nao_paralelas():
    a = Barra(inicio=(0, 0, 0), fim=(0, 0, 6000))
    b = Barra(inicio=(0, 0, 0), fim=(5000, 0, 0))
    doc = _doc(a, b)
    with pytest.raises(ErroDeDados):
        modelagem.contravento_x(doc, [a.id, b.id], {})


# ------------------------------------------------------------------ pilares e vigas

EIXOS = [
    {"nome": "A", "a": (0, -1000), "b": (0, 11000)},
    {"nome": "B", "a": (8000, -1000), "b": (8000, 11000)},
    {"nome": "1", "a": (-1000, 0), "b": (9000, 0)},
    {"nome": "2", "a": (-1000, 10000), "b": (9000, 10000)},
]


def test_cruzamentos_e_pilares_nos_eixos_com_a_alma_no_portico():
    cs = modelagem._cruzamentos(EIXOS)
    assert [c["nome"] for c in cs] == ["A-1", "A-2", "B-1", "B-2"]
    r = modelagem.pilares_nos_eixos(EIXOS, ["A-1", "B-2"], {"perfil": "W 250×32,7", "base": 0, "topo": 7000})
    bs = _barras(r)
    assert [(b.inicio[0], b.inicio[1]) for b in bs] == [(0, 0), (8000, 10000)]
    assert all(b.fim[2] == 7000 and b.papel == "pilar" for b in bs)
    # a alma no plano do eixo numerado (o pórtico, ao longo de x): a altura d da seção em x
    vs, _ = malha_barra(bs[0])
    dx = max(q[0] for q in vs) - min(q[0] for q in vs)
    dy = max(q[1] for q in vs) - min(q[1] for q in vs)
    assert dx == pytest.approx(258, abs=1) and dy < dx
    # todos, quando nenhum é escolhido
    assert len(modelagem.pilares_nos_eixos(EIXOS, [], {})["novas"]) == 4


def test_viga_entre_pilares_com_o_topo_no_nivel():
    r = modelagem.pilares_nos_eixos(EIXOS, ["A-1", "B-1"], {"topo": 6000})
    doc = _doc(*_barras(r))
    ids = list(doc.entidades)
    rv = modelagem.viga_entre_pilares(doc, ids, {"perfil": "W 310×38,7", "nivel": 6000})
    v = _barras(rv)
    assert len(v) == 1
    vs, _ = malha_barra(v[0])
    assert max(q[2] for q in vs) == pytest.approx(6000, abs=0.5)
    assert {v[0].inicio[0], v[0].fim[0]} == {0, 8000}
    assert not rv["avisos"]
    rv = modelagem.viga_entre_pilares(doc, ids, {"nivel": 6500})
    assert rv["avisos"]


# ------------------------------------------------------------------ longarinas

def _parede():
    """3 pilares W 250 na linha y = 0 (a parede), alma ao longo de x, e uma tesoura do lado de dentro (y > 0)"""
    ps = [Barra(nome="P%d" % i, inicio=(x, 0, 0), fim=(x, 0, 7000), perfil="W 250×32,7", papel="pilar", rotacao=0)
          for i, x in enumerate((0, 6000, 12000))]
    t = Barra(nome="T", inicio=(0, 0, 7000), fim=(0, 20000, 7000), perfil="W 150×13", papel="banzo")
    return _doc(*ps, t), ps


def test_longarinas_na_face_de_fora_com_a_boca_para_baixo():
    doc, ps = _parede()
    r = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 1000, "ultima": 6500, "espacamento": 1900})
    bs = _barras(r)
    n = math.ceil(5500 / 1900)
    assert r["resumo"]["linhas"] == n + 1
    assert len(bs) == 2 * (n + 1)                          # dois vãos por fiada
    zs = sorted({b.inicio[2] for b in bs})
    assert zs[0] == pytest.approx(1000) and zs[-1] == pytest.approx(6500)
    face = min(min(q[1] for q in malha_barra(p)[0]) for p in ps)     # o lado de fora é y < 0 (a tesoura está em y > 0)
    for b in bs:
        vs, _ = malha_barra(b)
        # encostada na face de fora do pilar, toda do lado de fora
        assert max(q[1] for q in vs) == pytest.approx(face, abs=0.5)
        # a alma na horizontal: a altura da seção (150) ao longo de y, as abas (60) na vertical
        assert max(q[1] for q in vs) - min(q[1] for q in vs) == pytest.approx(150, abs=0.5)
        assert max(q[2] for q in vs) - min(q[2] for q in vs) == pytest.approx(60, abs=0.5)
        # a boca para baixo: a alma em cima, perto do eixo (o centro de gravidade do Ue), e as abas descendo
        zc = b.inicio[2]
        assert max(q[2] for q in vs) - zc < zc - min(q[2] for q in vs)


def test_longarinas_continuas_e_do_lado_de_dentro():
    doc, ps = _parede()
    r = modelagem.longarinas(doc, [p.id for p in ps], {"continua": "sim", "lado": "dentro", "balanco": 200})
    bs = _barras(r)
    assert len(bs) == r["resumo"]["linhas"]
    assert all(b.inicio[1] > 0 for b in bs)
    assert min(min(b.inicio[0], b.fim[0]) for b in bs) == pytest.approx(-200)
    # sem primeira/última: da base + espaçamento ao topo − 300
    assert min(b.inicio[2] for b in bs) == pytest.approx(1900)
    assert max(b.inicio[2] for b in bs) == pytest.approx(6700)


def test_longarinas_recusa_pilares_fora_de_linha():
    doc, ps = _parede()
    q = Barra(inicio=(3000, 2000, 0), fim=(3000, 2000, 7000), perfil="W 250×32,7", papel="pilar")
    doc.add(q)
    with pytest.raises(ErroDeDados):
        modelagem.longarinas(doc, [ps[0].id, ps[1].id, q.id], {})


# ------------------------------------------------------------------ correntes

def _cobertura():
    """3 tesouras (banzos em x = 0, 6000, 12000) e 4 linhas de terças contínuas de 0 a 12000 em cima delas"""
    ts = [Barra(nome="T%d" % i, inicio=(x, 0, 5000), fim=(x, 8000, 5800), perfil="W 150×13", papel="banzo")
          for i, x in enumerate((0, 6000, 12000))]
    ls = [Barra(nome="L%d" % k, inicio=(0, y, 5000 + y / 10 + 150), fim=(12000, y, 5000 + y / 10 + 150),
                perfil="Ue 150×60×20×2,25", papel="terça") for k, y in enumerate((500, 2500, 4500, 6500))]
    return _doc(*ts, *ls), ts, ls


def test_correntes_no_meio_de_cada_vao_pelos_apoios():
    doc, ts, ls = _cobertura()
    r = modelagem.correntes(doc, [b.id for b in ls], {"linhas": 1})
    bs = _barras(r)
    assert r["resumo"]["vaos"] == 2                        # as tesouras partem as terças contínuas em 2 vãos
    assert len(bs) == 2 * 3                               # 3 ligações entre 4 linhas, por vão
    assert sorted({round(b.inicio[0]) for b in bs}) == [3000, 9000]
    for b in bs:
        assert b.papel == "corrente" and b.inicio[0] == b.fim[0]
        # de centro a centro: as pontas no eixo das terças
        assert any(abs(b.inicio[1] - l.inicio[1]) < 0.5 and abs(b.inicio[2] - l.inicio[2]) < 0.5 for l in ls)


def test_correntes_nos_tercos_e_terças_por_vao():
    doc, ts, _ls = _cobertura()
    ls = [Barra(inicio=(x0, y, 5200), fim=(x0 + 6000, y, 5200), perfil="Ue 150×60×20×2,25", papel="terça")
          for y in (500, 2500) for x0 in (0, 6000)]
    for b in ls:
        doc.add(b)
    r = modelagem.correntes(doc, [b.id for b in ls], {"linhas": 2})
    bs = _barras(r)
    assert sorted(round(b.inicio[0]) for b in bs) == [2000, 4000, 8000, 10000]


def test_correntes_pede_duas_linhas():
    doc, ts, ls = _cobertura()
    with pytest.raises(ErroDeDados):
        modelagem.correntes(doc, [ls[0].id], {})


# ------------------------------------------------------------------ mão-francesa

def _portico_com_tercas():
    """uma viga de cobertura W 310 em x = 6000 (ao longo de y, plana) e duas terças Ue 150 em cima dela, ao longo de x"""
    v = Barra(nome="V", inicio=(6000, 0, 6000), fim=(6000, 10000, 6000), perfil="W 310×38,7", papel="viga")
    zt = 6000 + 155 + 75                                   # a terça sentada na mesa de cima
    ts = [Barra(nome="T%d" % k, inicio=(0, y, zt), fim=(12000, y, zt), perfil="Ue 150×60×20×2,25", papel="terça",
                rotacao=0) for k, y in enumerate((2000, 5000))]
    return _doc(v, *ts), v, ts


def _colisoes(doc, novas):
    """as colisões da conferência (a mesma do Conferir antes de detalhar) com as peças novas no modelo"""
    from nucleo3d.conferencia_producao import colisoes
    from nucleo3d.producao import _proxy
    d2 = Documento.de_dict(doc.dict())
    for b in novas:
        d2.add(b)
    return colisoes([_proxy(e) for e in d2.entidades.values()])["achados"]


def test_mao_francesa_a_45_graus_sem_atravessar_terca_nem_apoio():
    doc, v, ts = _portico_com_tercas()
    r = modelagem.mao_francesa(doc, [t.id for t in ts], {})           # só as terças: o apoio é achado por baixo
    bs = _barras(r)
    assert r["resumo"]["apoios"] == 2 and len(bs) == 4                 # dois lados em cada terça
    for b in bs:
        alto, baixo = (b.inicio, b.fim) if b.inicio[2] > b.fim[2] else (b.fim, b.inicio)
        assert b.papel == "mão-francesa"
        # embaixo: 30 mm acima da face de baixo da viga, além da ponta da mesa (bf/2 + 30), onde vai a orelha
        assert abs(baixo[0] - 6000) == pytest.approx(165 / 2 + 30, abs=0.5)
        assert baixo[2] == pytest.approx(6000 - 155 + 30, abs=0.5)
        # em cima: 30 mm acima da face de baixo da terça
        assert alto[2] == pytest.approx(6230 - 75 + 30, abs=0.5)
        # 45°: o que anda na horizontal é o que desce
        assert abs(alto[0] - baixo[0]) == pytest.approx(alto[2] - baixo[2], abs=0.5)
        # encostada na face de trás da alma da terça (fora dela, ao lado do plano da terça)
        assert 0 < abs(alto[1] - round(alto[1], -3)) < 60
    # a conferência não acha colisão nenhuma: nem com a terça, nem com a viga, nem entre as duas de um apoio
    assert _colisoes(doc, bs) == []


def test_mao_francesa_um_lado_angulo_e_apoio_escolhido():
    doc, v, ts = _portico_com_tercas()
    outra = Barra(inicio=(9000, 0, 6000), fim=(9000, 10000, 6000), perfil="W 310×38,7", papel="viga")
    doc.add(outra)
    r = modelagem.mao_francesa(doc, [ts[0].id, outra.id], {"lados": "um", "angulo": 60})
    bs = _barras(r)
    assert len(bs) == 1
    b = bs[0]
    alto, baixo = (b.inicio, b.fim) if b.inicio[2] > b.fim[2] else (b.fim, b.inicio)
    assert abs(baixo[0] - 9000) == pytest.approx(165 / 2 + 30, abs=0.5)
    assert (alto[2] - baixo[2]) / abs(alto[0] - baixo[0]) == pytest.approx(math.tan(math.radians(60)), rel=1e-3)


def test_viga_entre_pilares_para_na_face_dos_pilares():
    r = modelagem.pilares_nos_eixos(EIXOS, ["A-1", "B-1"], {"topo": 6000, "perfil": "W 250×32,7"})
    doc = _doc(*_barras(r))
    rv = modelagem.viga_entre_pilares(doc, list(doc.entidades), {"perfil": "W 310×38,7", "nivel": 6000})
    v = _barras(rv)[0]
    # o pilar com a alma no pórtico (x): a face a d/2 = 129 do eixo
    assert v.recorte_inicio == pytest.approx(129, abs=0.5) and v.recorte_fim == pytest.approx(129, abs=0.5)
    assert _colisoes(doc, [v]) == []


def test_mao_francesa_sem_terca_ou_sem_apoio():
    doc, v, ts = _portico_com_tercas()
    with pytest.raises(ErroDeDados):
        modelagem.mao_francesa(doc, [v.id], {})
    longe = Barra(inicio=(0, 9000, 9000), fim=(12000, 9000, 9000), perfil="Ue 150×60×20×2,25", papel="terça")
    doc.add(longe)
    with pytest.raises(ErroDeDados):
        modelagem.mao_francesa(doc, [longe.id], {})


def _duas_aguas():
    """duas águas de 10 % (cumeeira em y = 5000): 3 linhas de terças de cada lado, um vão de 6 m entre duas tesouras"""
    def z(y):
        return 5000 + 0.1 * min(y, 10000 - y) + 150
    ts = [Barra(nome="T%d" % i, inicio=(x, 0, 5000), fim=(x, 5000, 5500), perfil="W 150×13", papel="banzo")
          for i, x in enumerate((0, 6000))]
    ts += [Barra(nome="U%d" % i, inicio=(x, 5000, 5500), fim=(x, 10000, 5000), perfil="W 150×13", papel="banzo")
           for i, x in enumerate((0, 6000))]
    ls = [Barra(inicio=(0, y, z(y)), fim=(6000, y, z(y)), perfil="Ue 150×60×20×2,25", papel="terça")
          for y in (500, 2500, 4500, 5500, 7500, 9500)]
    return _doc(*ts, *ls), ls, z


def test_correntes_fecham_em_v_na_cumeeira():
    doc, ls, z = _duas_aguas()
    r = modelagem.correntes(doc, [b.id for b in ls], {"linhas": 1})
    bs = _barras(r)
    v = [b for b in bs if b.atributos.get("cumeeira")]
    assert len(v) == 2 and len(bs) == 4 + 2                # 2 + 2 correntes e o V no lugar da reta do meio
    # as duas pernas do V vão ao mesmo ponto: na cumeeira (y 5000), no plano dos centros das terças, 6 % adiante
    c = v[0].fim
    assert v[1].fim == c
    assert c[1] == pytest.approx(5000, abs=0.5)
    assert c[2] == pytest.approx(z(5000), abs=0.5)
    assert c[0] == pytest.approx(3000 + 0.06 * 6000, abs=0.5)
    assert {round(b.inicio[1]) for b in v} == {4500, 5500}


def test_correntes_reta_na_cumeeira_e_uma_agua_sem_v():
    doc, ls, z = _duas_aguas()
    r = modelagem.correntes(doc, [b.id for b in ls], {"cumeeira": "reta"})
    assert len(r["novas"]) == 5 and not any(b["atributos"].get("cumeeira") for b in r["novas"])
    r = modelagem.correntes(doc, [b.id for b in ls[:3]], {})
    assert len(r["novas"]) == 2 and not any(b["atributos"].get("cumeeira") for b in r["novas"])


# ------------------------------------------------------------------ longarinas no oitão, contravento com SC1

def test_longarinas_no_oitao_so_entre_os_pilares_que_passam_da_fiada():
    # o oitão: pilares de 6, 8, 10, 8 e 6 m (a água sobe até o meio)
    ps = [Barra(inicio=(0, y, 0), fim=(0, y, h), perfil="W 250×32,7", papel="pilar")
          for y, h in ((0, 6000), (5000, 8000), (10000, 10000), (15000, 8000), (20000, 6000))]
    t = Barra(inicio=(0, 0, 6000), fim=(30000, 0, 6000), perfil="W 150×13", papel="viga")
    doc = _doc(*ps, t)
    r = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 1500, "espacamento": 1900, "topo": "nao"})
    bs = _barras(r)
    # as fiadas de 1,50 a 9,70 m (o pilar mais alto − 300); na de 6,42 m só os dois vãos do meio (pilares de 8 e 10 m)
    assert r["resumo"]["linhas"] == 6
    assert max(b.inicio[2] for b in bs) == pytest.approx(6420)
    assert sorted(sorted((round(b.inicio[1]), round(b.fim[1]))) for b in bs if round(b.inicio[2]) == 6420) == [[5000, 10000], [10000, 15000]]
    for b in bs:
        z = b.inicio[2]
        ys = sorted((b.inicio[1], b.fim[1]))
        # nenhum trecho apoiado num pilar que não passa da fiada + 300
        for y in ys:
            h = dict(((0, 6000), (5000, 8000), (10000, 10000), (15000, 8000), (20000, 6000)))[round(y)]
            assert h >= z + 300 - 1e-6, (y, z)
    # abaixo de 5,7 m, as 4 peças; acima de 7,7 m, nenhuma (só o pilar do meio passa)
    assert sum(1 for b in bs if b.inicio[2] < 5700) % 4 == 0
    assert not any(b.inicio[2] > 7700 for b in bs)
    assert any("oitão" in a for a in r["avisos"])
    # contínua: o maior trecho seguido dos que passam
    r = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 6500, "ultima": 6500, "continua": "sim", "topo": "nao"})
    b = _barras(r)[0]
    assert sorted((round(b.inicio[1]), round(b.fim[1]))) == [5000, 15000]


def test_contravento_de_cobertura_ja_nos_suportes_sc1():
    a = Barra(nome="BA", inicio=(0, 0, 6000), fim=(0, 12000, 6000), perfil="W 250×32,7", papel="banzo")
    b = Barra(nome="BB", inicio=(6000, 0, 6000), fim=(6000, 12000, 6000), perfil="W 250×32,7", papel="banzo")
    doc = _doc(a, b)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 1, "perfil": "FE RED 5/8''", "suporte": "sc1"})
    assert r["resumo"]["suportes"] == 4                   # 2 tirantes × 2 pontas
    scs = [e for e in r["novas"] if e.get("papel") == "suporte"]
    tir = [e for e in r["novas"] if e.get("papel") == "contraventamento"]
    assert len(tir) == 2 and all(e["atributos"].get("ligacao", {}).get("tipo") == "suporte_contravento" for e in scs)
    # a L em pé no topo do banzo (W 250: topo em 6000 + 129)
    assert all(abs(min(e["inicio"][2], e["fim"][2]) - (6000 + 129)) < 1.0 for e in scs)
    # o tirante esticado de furo a furo (já não vai de eixo a eixo)
    assert all(t["inicio"][2] > 6000 + 100 for t in tir)
    # as marcas e a solda gravadas nos banzos vão em "alterar"
    assert set(r["alterar"]) <= {a.id, b.id} and r["alterar"]
    assert not r["avisos"]


def test_contravento_sc1_avisa_no_com_dois_tirantes_e_recusa_pilares():
    a = Barra(inicio=(0, 0, 6000), fim=(0, 12000, 6000), perfil="W 250×32,7", papel="banzo")
    b = Barra(inicio=(6000, 0, 6000), fim=(6000, 12000, 6000), perfil="W 250×32,7", papel="banzo")
    doc = _doc(a, b)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 2, "perfil": "FE RED 5/8''", "suporte": "sc1"})
    assert r["resumo"]["suportes"] == 8
    assert r["avisos"] and "2 nó" in r["avisos"][0]
    p1 = Barra(inicio=(0, 0, 0), fim=(0, 0, 6000), perfil="W 250×32,7", papel="pilar")
    p2 = Barra(inicio=(6000, 0, 0), fim=(6000, 0, 6000), perfil="W 250×32,7", papel="pilar")
    doc = _doc(p1, p2)
    with pytest.raises(ErroDeDados):
        modelagem.contravento_x(doc, [p1.id, p2.id], {"suporte": "sc1"})


def test_terca_de_oitao_inclinada_pelo_topo_dos_pilares():
    alturas = ((0, 6000), (5000, 8000), (10000, 10000), (15000, 8000), (20000, 6000))
    ps = [Barra(inicio=(0, y, 0), fim=(0, y, h), perfil="W 250×32,7", papel="pilar") for y, h in alturas]
    t = Barra(inicio=(0, 0, 6000), fim=(30000, 0, 6000), perfil="W 150×13", papel="viga")
    doc = _doc(*ps, t)
    r = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 1500})       # oitão: a terça do topo por padrão
    topo = [b for b in _barras(r) if b.atributos.get("topo")]
    assert r["resumo"]["topo"] == 4 and len(topo) == 4
    h = dict(alturas)
    for b in topo:
        assert b.nome == "Terça de oitão"
        y0, y1 = sorted((b.inicio[1], b.fim[1]))
        # de pilar a pilar, na inclinação da água (2 m em 5 m)
        assert (round(y0), round(y1)) in ((0, 5000), (5000, 10000), (10000, 15000), (15000, 20000))
        assert abs(b.fim[2] - b.inicio[2]) == pytest.approx(2000, abs=0.5)
        # a borda de cima rente ao topo dos pilares: na ponta alta, o topo da malha é o topo do pilar
        vs, _ = malha_barra(b)
        assert max(q[2] for q in vs) == pytest.approx(max(h[round(y0)], h[round(y1)]), abs=0.5)
        # no plano das longarinas (a mesma distância da parede)
        assert b.inicio[0] == pytest.approx(min(x.inicio[0] for x in _barras(r) if not x.atributos.get("topo")), abs=0.5)
    # abaixo do topo, e desligada: as fiadas avisam do oitão
    r2 = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 1500, "abaixo_topo": 100})
    t2 = [b for b in _barras(r2) if b.atributos.get("topo")][0]
    assert max(q[2] for q in malha_barra(t2)[0]) == pytest.approx(
        max(h[round(t2.inicio[1])], h[round(t2.fim[1])]) - 100, abs=0.5)
    r3 = modelagem.longarinas(doc, [p.id for p in ps], {"primeira": 1500, "topo": "nao"})
    assert r3["resumo"]["topo"] == 0 and any("oitão" in a for a in r3["avisos"])


def test_parede_lateral_nao_ganha_terca_de_topo_sem_pedir():
    doc, ps = _parede()
    r = modelagem.longarinas(doc, [p.id for p in ps], {})
    assert r["resumo"]["topo"] == 0
    r = modelagem.longarinas(doc, [p.id for p in ps], {"topo": "sim"})
    assert r["resumo"]["topo"] == 2 and all(b.nome == "Longarina de topo" for b in _barras(r) if b.atributos.get("topo"))


def test_tirante_no_furo_do_sc1_nao_e_colisao_e_o_x_para_na_ponta_util():
    from nucleo3d.conferencia_producao import conferir
    a = Barra(nome="BA", inicio=(0, 0, 6000), fim=(0, 12000, 6000), perfil="W 250×32,7", papel="viga",
              recorte_inicio=129, recorte_fim=129)
    b = Barra(nome="BB", inicio=(6000, 0, 6000), fim=(6000, 12000, 6000), perfil="W 250×32,7", papel="viga",
              recorte_inicio=129, recorte_fim=129)
    doc = _doc(a, b)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 1, "perfil": "FE RED 5/8''", "suporte": "sc1"})
    tir = [e for e in r["novas"] if e.get("papel") == "contraventamento"]
    # o X começa e acaba nas pontas úteis das vigas (129 da ponta do eixo), não no eixo do pilar: os suportes ficam lá
    assert len(tir) == 2
    ys = sorted(round(e["inicio"][1]) for e in r["novas"] if e.get("papel") == "suporte")
    assert ys[0] >= 129 - 30 and ys[-1] <= 12000 - 129 + 30, ys
    d2 = Documento.de_dict(doc.dict())
    for e in r["novas"]:
        d2.entidades[e["id"]] = Documento.de_dict({"entidades": [e]}).entidades[e["id"]]
    achados = [x for x in conferir(d2, quais=("colisao",))["achados"] if x["regra"].startswith("colisao")]
    assert achados == [], achados


def test_marcador_de_furo_do_sc1_nao_vira_peca_fora_do_aco_no_detalhamento():
    from nucleo2d.detalhar import levantar
    a = Barra(nome="BA", inicio=(0, 0, 6000), fim=(0, 12000, 6000), perfil="W 250×32,7", papel="viga")
    b = Barra(nome="BB", inicio=(6000, 0, 6000), fim=(6000, 12000, 6000), perfil="W 250×32,7", papel="viga")
    doc = _doc(a, b)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 1, "perfil": "FE RED 5/8''", "suporte": "sc1"})
    d2 = Documento.de_dict(dict(doc.dict(), entidades=doc.dict()["entidades"] + r["novas"]))
    assert any((e.atributos or {}).get("furo") for e in d2.entidades.values())
    lev = levantar(d2)
    assert not any("não são de aço" in str(x) for x in (lev.get("avisos") or [])), lev.get("avisos")


def test_tercas_juntam_os_trechos_do_banzo_partido_nos_nos():
    """o banzo de cima partido em trechos (um por painel, como vem do IFC): selecionados os trechos das duas tesouras,
    as terças saem iguais às do banzo inteiro"""
    doc_i, t1, t2 = _duas_tesouras()
    r_inteiro = modelagem.tercas(doc_i, [t1.id, t2.id], {"espacamento": 1500})
    trechos = []
    for y in (0, 5000):
        for k in range(4):
            x0, x1 = 1500 * k, 1500 * (k + 1)
            trechos.append(Barra(inicio=(x0, y, 5000 + 0.1 * x0), fim=(x1, y, 5000 + 0.1 * x1), perfil="W 150×13", papel="banzo"))
    doc = _doc(*trechos)
    r = modelagem.tercas(doc, [b.id for b in trechos], {"espacamento": 1500})
    assert r["resumo"] == r_inteiro["resumo"]
    a = sorted(tuple(round(c) for c in b["inicio"]) for b in r["novas"])
    b_ = sorted(tuple(round(c) for c in b["inicio"]) for b in r_inteiro["novas"])
    assert a == b_


def test_conferencia_aceita_a_corrente_na_alma_da_terca_e_o_no_das_correntes():
    from nucleo3d.conferencia_producao import conferir
    doc, ls, z = _duas_aguas()
    # a terça girada com a alma de pé no eixo (a corrente entra na alma, não no vazio do U)
    for t in ls:
        t.rotacao = 90.0
    r = modelagem.correntes(doc, [b.id for b in ls], {"linhas": 1})
    d2 = Documento.de_dict(dict(doc.dict(), entidades=doc.dict()["entidades"] + r["novas"]))
    achados = [x for x in conferir(d2, quais=("colisao",))["achados"] if x["regra"].startswith("colisao")]
    nomes = [{d2.entidades[i].papel for i in x["ids"]} for x in achados]
    assert not any("corrente" in n for n in nomes), nomes


def test_mao_francesa_nao_pega_montante_diagonal_nem_forro_da_trelica():
    # a terça sobre a treliça: logo abaixo, o banzo de cima (sem altura); mais abaixo, montante, diagonal e forro
    bs = Barra(inicio=(3000, 0, 5000), fim=(3000, 8000, 5000), perfil="U 100×40×2,65", papel="banzo")
    bi = Barra(inicio=(3000, 0, 4000), fim=(3000, 8000, 4000), perfil="U 100×40×2,65", papel="banzo")
    dg = Barra(inicio=(3000, 1000, 4000), fim=(3000, 3000, 5000), perfil="U 100×40×2,65", papel="diagonal")
    fo = Barra(inicio=(0, 2000, 4300), fim=(6000, 2000, 4300), perfil="U 100×40×2,65", papel="forro")
    t = Barra(inicio=(0, 2000, 5050 + 75), fim=(6000, 2000, 5050 + 75), perfil="Ue 150×60×20×2,25", papel="terça")
    doc = _doc(bs, bi, dg, fo, t)
    with pytest.raises(ErroDeDados):
        modelagem.mao_francesa(doc, [t.id], {})
    # escolhido o banzo de baixo à mão, sai
    r = modelagem.mao_francesa(doc, [t.id, bi.id], {})
    assert len(r["novas"]) == 2


def test_correntes_so_param_nas_vigas_e_banzos_e_pulam_as_que_ja_existem():
    doc, ts, ls = _cobertura()
    # uma diagonal e um forro cruzando por baixo das terças no meio do vão: não partem o vão
    doc.add(Barra(inicio=(3000, 0, 5000), fim=(3100, 8000, 5500), perfil="L 2'' X 3/16''", papel="diagonal"))
    doc.add(Barra(inicio=(4000, 0, 5100), fim=(4000, 8000, 5100), perfil="L 2'' X 3/16''", papel="forro"))
    r = modelagem.correntes(doc, [b.id for b in ls], {"linhas": 1})
    assert r["resumo"]["vaos"] == 2 and len(r["novas"]) == 6
    # lançadas uma vez, a segunda não repete
    d2 = Documento.de_dict(dict(doc.dict(), entidades=doc.dict()["entidades"] + r["novas"]))
    with pytest.raises(ErroDeDados):
        modelagem.correntes(d2, [b.id for b in ls], {"linhas": 1})
    # nos terços também não: o par já tem corrente naquele vão
    with pytest.raises(ErroDeDados):
        modelagem.correntes(d2, [b.id for b in ls], {"linhas": 2})
    # uma terça a mais (de fora do par que já tem): só o par novo ganha corrente
    nova = Barra(inicio=(0, 8500, 5000 + 850 + 150), fim=(12000, 8500, 5000 + 850 + 150), perfil="Ue 150×60×20×2,25", papel="terça")
    d2.add(nova)
    r3 = modelagem.correntes(d2, [b.id for b in ls] + [nova.id], {"linhas": 1})
    assert len(r3["novas"]) == 2 and r3["avisos"]


def test_trelica_e_contravento_sc1_nao_mudam_o_documento_recebido():
    import json
    def foto(d):
        return json.dumps(d.dict(), sort_keys=True, default=str)
    doc, sup, inf = _banzos(peca="TESOURA 1#1")
    # uma alma que já estava no bloco: o encaixe mexe nela na cópia, não no recebido
    doc.add(Barra(inicio=(0, 0, 0), fim=(0, 0, 1000), perfil="U 100×40×2,65", papel="montante",
                  atributos={"origem": {"peca": "TESOURA 1#1"}}))
    antes = foto(doc)
    modelagem.trelica(doc, [sup.id, inf.id], {"tipo": "pratt", "passo": 1500})
    assert foto(doc) == antes
    a = Barra(inicio=(0, 0, 6000), fim=(0, 12000, 6000), perfil="W 250×32,7", papel="viga")
    b = Barra(inicio=(6000, 0, 6000), fim=(6000, 12000, 6000), perfil="W 250×32,7", papel="viga")
    doc = _doc(a, b)
    antes = foto(doc)
    r = modelagem.contravento_x(doc, [a.id, b.id], {"paineis": 2, "perfil": "FE RED 5/8''", "suporte": "sc1"})
    assert foto(doc) == antes and r["resumo"]["suportes"] == 8
