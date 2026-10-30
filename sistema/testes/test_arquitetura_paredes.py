# -*- coding: utf-8 -*-
"""Módulo de arquitetura — paredes (ARQ-01 a ARQ-04, aprovadas em 30/10/2026; exemplos em
Projeto/ANALISES/Arquitetura/Prova-fase-1-arquitetura-2026-10-30.pdf). As áreas e os volumes esperados foram contados à
mão nos casos da prova: L, T e X de 20 com 15 e a J1/P1."""
import math

import pytest

from arquitetura.paredes import Esquadria, Parede, TIPOS, montar, solido_da_parede


def _areas(m, pid, funcao=None):
    return sum(p.area for p in m.da_parede(pid) if funcao is None or p.funcao == funcao)


def _uniao(pecas):
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    return unary_union([Polygon(p.poligono) for p in pecas])


def _sem_sobreposicao(pecas):
    """a soma das áreas é a área da união: nenhuma peça entra na outra"""
    u = _uniao(pecas)
    assert abs(sum(p.area for p in pecas) - u.area) < 1.0


# ------------------------------------------------------------------ ARQ-01

def test_tipos_padrao_da_dezn():
    assert TIPOS["EXT20"].espessura == 200 and TIPOS["EXT20"].nucleo() == (70, -70)
    assert TIPOS["INT15"].espessura == 150 and TIPOS["INT15"].nucleo() == (45, -45)
    assert TIPOS["EXT20"].acabamento(1) == TIPOS["EXT20"].acabamento(-1) == 30


def test_parede_solta_tem_as_tres_camadas_retas():
    m = montar([Parede("p", (0, 0), (1000, 0), "EXT20")])
    assert _areas(m, "p", "nucleo") == pytest.approx(140_000)
    assert _areas(m, "p", "acabamento") == pytest.approx(60_000)


# ------------------------------------------------------------------ ARQ-02 — L, T, X

@pytest.mark.parametrize("sentido", [1, -1])
def test_l_meia_esquadria_camada_por_camada(sentido):
    """L de duas externas de 1,00 m pelo eixo: o canto de fora em (−100, −100); cada camada vai até a bissetriz y = x.
    Conta à mão (parede ao longo de x): núcleo 1000 × 140; reboco de dentro ∫(1000 − y) dy de 70 a 100 = 27 450;
    reboco de fora = 32 550."""
    a = Parede("a", (0, 0), (1000, 0), "EXT20") if sentido > 0 else Parede("a", (1000, 0), (0, 0), "EXT20")
    b = Parede("b", (0, 0), (0, 1000), "EXT20")
    m = montar([a, b])
    for pid in ("a", "b"):
        assert _areas(m, pid, "nucleo") == pytest.approx(140_000)
        rebocos = sorted(p.area for p in m.da_parede(pid) if p.funcao == "acabamento")
        assert rebocos == pytest.approx([27_450, 32_550])
    _sem_sobreposicao(m.pecas)
    # o núcleo é contínuo: a união dos núcleos das duas paredes é uma peça só
    nucleos = _uniao([p for p in m.pecas if p.funcao == "nucleo"])
    assert nucleos.geom_type == "Polygon"
    # e o contorno de fora fecha no canto (−100, −100)
    tudo = _uniao(m.pecas)
    assert tudo.geom_type == "Polygon"
    assert min(x for x, _ in tudo.exterior.coords) == pytest.approx(-100)
    assert min(y for _, y in tudo.exterior.coords) == pytest.approx(-100)


def test_t_interna_chega_na_externa():
    """T: externa de −600 a 600 no eixo x; interna de (0, 0) a (0, 900).
    - O núcleo da interna (90) vai da face do núcleo da externa (y = 70) até 900: 90 × 830.
    - O reboco da interna para na face da externa (y = 100): 2 × 30 × 800.
    - O reboco da externa do lado de cima perde a faixa do núcleo que chega: (1200 − 90) × 30."""
    m = montar([Parede("ext", (-600, 0), (600, 0), "EXT20"), Parede("int", (0, 0), (0, 900), "INT15")])
    assert _areas(m, "int", "nucleo") == pytest.approx(90 * 830)
    assert _areas(m, "int", "acabamento") == pytest.approx(2 * 30 * 800)
    assert _areas(m, "ext", "nucleo") == pytest.approx(1200 * 140)
    rebocos = sorted(p.area for p in m.da_parede("ext") if p.funcao == "acabamento")
    assert sum(rebocos) == pytest.approx((1200 - 90) * 30 + 1200 * 30)
    assert len(rebocos) == 3                        # o de cima partido em dois
    _sem_sobreposicao(m.pecas)
    assert _uniao([p for p in m.pecas if p.funcao == "nucleo"]).geom_type == "Polygon"
    assert _uniao(m.pecas).geom_type == "Polygon"


def test_x_a_mais_grossa_passa():
    """X: a externa passa; a interna vira duas T. Núcleo da interna: 2 × 90 × 530; reboco da externa: os dois lados
    partidos."""
    m = montar([Parede("int", (0, -600), (0, 600), "INT15"), Parede("ext", (-600, 0), (600, 0), "EXT20")])
    assert _areas(m, "int", "nucleo") == pytest.approx(2 * 90 * 530)
    assert _areas(m, "ext", "nucleo") == pytest.approx(1200 * 140)
    assert len([p for p in m.da_parede("ext") if p.funcao == "acabamento"]) == 4
    _sem_sobreposicao(m.pecas)
    assert _uniao([p for p in m.pecas if p.funcao == "nucleo"]).geom_type == "Polygon"


def test_x_de_espessuras_iguais_passa_a_primeira():
    m = montar([Parede("a", (-600, 0), (600, 0), "INT15"), Parede("b", (0, -600), (0, 600), "INT15")])
    assert _areas(m, "a", "nucleo") == pytest.approx(1200 * 90)
    assert _areas(m, "b", "nucleo") == pytest.approx(2 * 90 * (600 - 45))


def test_l_em_angulo_qualquer_fecha_sem_sobrepor():
    """a mesma regra num canto de 60°, para não depender de parede no eixo x/y"""
    a = math.radians(60)
    m = montar([Parede("a", (0, 0), (1500, 0), "EXT20"),
                Parede("b", (0, 0), (1500 * math.cos(a), 1500 * math.sin(a)), "INT15")])
    _sem_sobreposicao(m.pecas)
    assert _uniao([p for p in m.pecas if p.funcao == "nucleo"]).geom_type == "Polygon"
    assert _uniao(m.pecas).geom_type == "Polygon"


def test_tres_pontas_no_mesmo_ponto():
    """duas em linha seguem como uma; a terceira chega em T"""
    m = montar([Parede("a", (-800, 0), (0, 0), "EXT20"), Parede("b", (0, 0), (800, 0), "EXT20"),
                Parede("c", (0, 0), (0, 700), "INT15")])
    assert _areas(m, "c", "nucleo") == pytest.approx(90 * (700 - 70))
    _sem_sobreposicao(m.pecas)
    assert _uniao(m.pecas).geom_type == "Polygon"


def test_casa_piloto_superior_fecha_sem_sobrepor():
    """as paredes do pavimento superior da sugestão de planta da casa (prova, pág. 5): nada se sobrepõe e as uniões
    fecham (uma peça só)"""
    e = 100
    ps = [Parede("f", (200, 600 + e), (13800, 600 + e), "EXT20"),
          Parede("e", (200, 600 + e), (200, 11000 - e), "EXT20"), Parede("d", (13800, 600 + e), (13800, 11000 - e), "EXT20"),
          Parede("t", (200, 11000 - e), (13800, 11000 - e), "EXT20"),
          Parede("i1", (200, 5400), (13800, 5400), "INT15"), Parede("i2", (200, 8000), (13800, 8000), "INT15"),
          Parede("v1", (4600, 600 + e), (4600, 8000), "INT15"), Parede("v2", (9400, 600 + e), (9400, 8000), "INT15"),
          Parede("v3", (2400, 5400), (2400, 8000), "INT15"), Parede("v4", (2800, 8000), (2800, 11000 - e), "INT15"),
          Parede("v5", (7000, 5400), (7000, 8000), "INT15"), Parede("v6", (11000, 5400), (11000, 8000), "INT15")]
    m = montar(ps)
    _sem_sobreposicao(m.pecas)
    assert _uniao(m.pecas).geom_type == "Polygon"
    assert _uniao([p for p in m.pecas if p.funcao == "nucleo"]).geom_type == "Polygon"


# ------------------------------------------------------------------ ARQ-03 / ARQ-04

def test_janela_j1_abre_o_osso_e_o_requadro_fecha_o_acabado():
    """J1 150 × 120, peitoril 110, numa externa de 3,00 × 3,00: o osso tem 1,56 × 1,26 com peitoril 1,07; o volume que
    sai da parede é o do vão acabado na espessura inteira (1500 × 1200 × 200)."""
    w = Parede("w", (0, 0), (3000, 0), "EXT20", 0, 3000)
    j = Esquadria("j1", "w", "janela", u=750, largura=1500, altura=1200, peitoril=1100, codigo="J1")
    m = montar([w], [j])
    total = sum(p.volume for p in m.pecas)
    assert total == pytest.approx(3000 * 200 * 3000 - 1500 * 1200 * 200)
    nucleo = sum(p.volume for p in m.pecas if p.funcao == "nucleo")
    assert nucleo == pytest.approx(3000 * 140 * 3000 - 1560 * 1260 * 140)
    peitoril = [p for p in m.pecas if p.funcao == "peitoril"]
    assert len(peitoril) == 1 and (peitoril[0].z0, peitoril[0].z1) == (1070, 1100)
    req = [p for p in m.pecas if p.funcao == "requadro"]
    assert len(req) == 3 and max(p.z1 for p in req) == 2330


def test_porta_p1_pela_folha_com_osso_de_folga():
    """P1 90 × 210 numa interna: o osso é 1,00 × 2,15 em todas as camadas (o batente cobre)"""
    w = Parede("w", (0, 0), (3000, 0), "INT15", 0, 3000)
    m = montar([w], [Esquadria("p1", "w", "porta", u=1050, largura=900, altura=2100, codigo="P1")])
    total = sum(p.volume for p in m.pecas)
    assert total == pytest.approx(3000 * 150 * 3000 - 1000 * 2150 * 150)
    assert not [p for p in m.pecas if p.funcao in ("requadro", "peitoril")]


def test_janela_em_parede_partida_pela_x():
    """a esquadria fica na parede original, mesmo quando a X parte a parede em duas"""
    w = Parede("w", (0, 0), (4000, 0), "INT15", 0, 3000)
    x = Parede("x", (2000, -1000), (2000, 1000), "EXT20", 0, 3000)
    j = Esquadria("j", "w", "janela", u=400, largura=1000, altura=1000, peitoril=1000)
    m = montar([w, x], [j])
    vol = sum(p.volume for p in m.da_parede("w"))
    assert vol == pytest.approx(2 * 1930 * 90 * 3000 + 2 * 1900 * 60 * 3000 - 1000 * 1000 * 150)


def test_solido_da_parede_fecha_as_cascas():
    m = montar([Parede("w", (0, 0), (3000, 0), "EXT20")],
               [Esquadria("j", "w", "janela", u=750, largura=1500, altura=1200, peitoril=1100)])
    s = solido_da_parede(m.da_parede("w"), "Parede w")
    assert s.tipo == "solido" and s.camada == "ARQ — Paredes"
    assert len(s.faces) == 6 * len(m.da_parede("w"))
