# -*- coding: utf-8 -*-
"""A mesma peça posta girada no modelo é a mesma marca (FERRAMENTA · LIGAÇÕES, 23/10: "peça igual girada 180° em
planta sai com outra marca" — a castanha da viga de cima e a da de baixo saíam P3 e P5, com o furo numa aba e na outra).
A assinatura (nucleo2d/detalhe/base.py) guarda dos furos só quantos e de que tamanho; o lugar deles é `_furos_iguais`,
que aceita os giros que levam a peça sobre ela mesma — pela seção: em volta do comprimento, de ponta-cabeça e, na
cantoneira de abas iguais, pela diagonal. O espelho não: a outra mão é outra marca."""
import collections
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from saida.detalhamento import Posicao, Furo
from nucleo2d.detalhe.base import _furos_iguais, _simetrias_da_secao, fundir_posicoes_iguais


def _cantoneira(furos, abas=(50.8, 50.8), L=50.0):
    """L com o canto em (v 0, w −a/2): a aba em pé na alma (frente), a deitada na mesa (topo)"""
    a, b = abas
    t = 4.75
    secao = [[(0.0, -b / 2), (0.0, b / 2), (t, b / 2), (t, -b / 2 + t), (a, -b / 2 + t), (a, -b / 2)]]
    return Posicao(marca="X", tipo_ifc="", perfil="L %gX%gX4.75" % (a, b), classe="barra", L=L, H=a, T=b, comprimento=L,
                   quantidade=1, secao=secao, furos=furos)


def _perfil_u(furos, L=1000.0):
    """U 100 × 50: alma em w = −25, mesas em v = 0 e v = 100 (simétrico só em v → H − v)"""
    secao = [[(0.0, -25.0), (0.0, 25.0), (5.0, 25.0), (5.0, -20.0), (95.0, -20.0), (95.0, 25.0), (100.0, 25.0), (100.0, -25.0)]]
    return Posicao(marca="U", tipo_ifc="", perfil="U 100X50", classe="barra", L=L, H=100.0, T=50.0, comprimento=L,
                   quantidade=1, secao=secao, furos=furos)


def test_o_caso_das_ligacoes_uma_marca_so():
    """o nó do contravento com castanha: as duas castanhas (aba) do V, uma virada em relação à outra"""
    from test_ligacoes_contravento import _numerado
    from nucleo2d.detalhar import levantar
    doc, *_ = _numerado("castanha_contravento")
    marcas = collections.defaultdict(set)
    for e in doc.entidades.values():
        m = (e.atributos or {}).get("marcas") or {}
        if m.get("posicao"):
            marcas[e.nome].add(m["posicao"])
    assert len(marcas["Castanha (aba)"]) == 1, marcas["Castanha (aba)"]
    lev = levantar(doc, regra_tercas=False)
    abas = [p for p in lev["posicoes"] if p.perfil.startswith("L 50") and p.L < 60]
    assert len(abas) == 1 and abas[0].quantidade == 2, [(p.marca, p.quantidade) for p in abas]


def test_cantoneira_de_abas_iguais_pela_diagonal():
    a = _cantoneira([Furo("redondo", 25.0, 26.0, 14.2, vista="frente")])      # o furo na aba em pé (a 26 do canto)
    b = _cantoneira([Furo("redondo", 25.0, 0.0, 14.2, vista="topo")])         # na deitada (w 0 = 25,4 do canto)
    assert "d0" in _simetrias_da_secao(a)
    assert _furos_iguais(a, b) and _furos_iguais(b, a)
    c = _cantoneira([Furo("redondo", 25.0, 40.0, 14.2, vista="topo")])        # noutro lugar da aba: outra peça
    assert not _furos_iguais(a, c)


def test_cantoneira_de_abas_desiguais_nao_vira():
    a = _cantoneira([Furo("redondo", 25.0, 26.0, 14.2, vista="frente")], abas=(50.8, 30.0))
    b = _cantoneira([Furo("redondo", 25.0, -15.0 + 26.0, 14.2, vista="topo")], abas=(50.8, 30.0))
    assert "d0" not in _simetrias_da_secao(a) and not _furos_iguais(a, b)


def test_u_girado_junta_e_a_outra_mao_nao():
    a = _perfil_u([Furo("redondo", 100.0, 30.0, 18.0, vista="frente")])
    girado = _perfil_u([Furo("redondo", 900.0, 70.0, 18.0, vista="frente")])   # de ponta-cabeça: as pontas e v trocam
    mao = _perfil_u([Furo("redondo", 900.0, 30.0, 18.0, vista="frente")])      # o espelho
    assert _simetrias_da_secao(a) == ["w"]
    assert _furos_iguais(a, girado) and not _furos_iguais(a, mao)


def test_fundir_junta_as_giradas():
    a = _cantoneira([Furo("redondo", 25.0, 26.0, 14.2, vista="frente")]); a.marca = "P3"
    b = _cantoneira([Furo("redondo", 25.0, 0.0, 14.2, vista="topo")]); b.marca = "P5"
    c = _cantoneira([Furo("redondo", 10.0, 0.0, 14.2, vista="topo")]); c.marca = "P7"
    out = fundir_posicoes_iguais([a, b, c], {})
    assert sorted((p.marca, p.quantidade) for p in out) == [("P3 / P5", 2), ("P7", 1)]


def test_chapa_girada_180_junta():
    cont = [(0.0, 0.0), (300.0, 0.0), (300.0, 200.0), (0.0, 200.0)]
    a = Posicao(marca="C1", tipo_ifc="", perfil="CH 8", classe="chapa", L=300.0, H=200.0, T=8.0, comprimento=300.0, quantidade=1,
                contorno=cont, furos=[Furo("redondo", 40.0, 40.0, 18.0)])
    b = Posicao(marca="C2", tipo_ifc="", perfil="CH 8", classe="chapa", L=300.0, H=200.0, T=8.0, comprimento=300.0, quantidade=1,
                contorno=cont, furos=[Furo("redondo", 260.0, 160.0, 18.0)])
    assert _furos_iguais(a, b)
