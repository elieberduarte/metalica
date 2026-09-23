# -*- coding: utf-8 -*-
"""Quadros do detalhamento: moldura pela extensão real e unidade do conjunto pela maioria."""
import collections

from nucleo2d.desenho import Desenho, Cota, Texto, Linha
from nucleo2d import detalhar as D


def test_unidade_pela_maioria_tolera_uma_peca_a_menos():
    # 8 tesouras de 4 P13, mas uma veio com 1: o mdc cai para 1
    total = collections.Counter({"P10": 80, "P11": 64, "P12": 64, "P13": 29, "P4": 56, "P1": 8})
    n, unidade = D._unidade_pela_maioria(total)
    assert n == 8
    assert unidade == collections.Counter({"P10": 10, "P11": 8, "P12": 8, "P13": 4, "P4": 7, "P1": 1})


def test_unidade_pela_maioria_nao_inventa_instancias():
    assert D._unidade_pela_maioria(collections.Counter({"P1": 1, "P2": 3, "P3": 1})) is None
    assert D._unidade_pela_maioria(collections.Counter({"P1": 2, "P2": 2})) is None     # poucas posições


def test_extremos_da_cota_incluem_a_linha_deslocada():
    c = Cota(modo="h", p1=(0.0, 0.0), p2=(1000.0, 0.0), deslocamento=-10.0)
    ys = [p[1] for p in D._extremos_de(c, 50.0)]
    assert min(ys) < -500.0 + 1e-6          # 10 mm de papel × 1:50, e o número abaixo


def test_extremos_do_texto_tem_largura():
    t = Texto(posicao=(0.0, 0.0), texto="TESOURA", altura=3.5)
    xs = [p[0] for p in D._extremos_de(t, 50.0)]
    assert max(xs) > 3.5 * 50.0 * 3


def test_moldura_do_quadro_cerca_as_cotas():
    d = Desenho(nome="t", escala=50.0)

    def celula(dd, x, y):
        dd.add(Linha(camada="ACO", a=(x, y), b=(x + 2000.0, y)))
        dd.add(Cota(modo="h", p1=(x, y), p2=(x + 2000.0, y), deslocamento=-15.0))
        return (x, y - 15.0 * 50.0 - 200.0, x + 2000.0, y + 100.0)
    D._quadros_por_tipo(d, [("tesoura", celula)])
    quadro = next(e for e in d.entidades.values() if (e.atributos or {}).get("quadro") == "TESOURAS")
    fundo = min(v[1] for v in quadro.vertices)
    cota = next(e for e in d.entidades.values() if isinstance(e, Cota))
    assert fundo < cota.p1[1] - 15.0 * 50.0
