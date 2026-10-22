# -*- coding: utf-8 -*-
"""A peça lida do desenho posta pela seção real (MET-1 da verificação do SESI Chapecó, 22/10/2026): o eixo lido no meio do
contorno vai para o centroide; a corrente vai até a alma da terça."""
import pytest

from nucleo3d.encaixe_pela_secao import correntes_ate_a_alma, eixo_pelo_contorno, meio_do_contorno
from nucleo3d.geometria import base_local, secao, resolver_perfil
from nucleo3d.modelo import Barra

UE200 = "Ue 200×75×25×2,65"
UE150 = "Ue 150×60×20×2,25"


def _faixa(b, eixo):
    """a faixa que a seção ocupa no eixo global `eixo` (0 = x, 1 = y)"""
    d = tuple(b.fim[i] - b.inicio[i] for i in range(3))
    u, v, _ = base_local(d, b.rotacao)
    vals = [b.inicio[eixo] + x * u[eixo] + y * v[eixo] for x, y in secao(resolver_perfil(b.perfil))]
    return min(vals), max(vals)


def test_caixa_de_dois_ue_boca_a_boca_fecha_sem_se_atravessar():
    # a VM caixa do SESI: dois Ue 200×75 boca a boca, os eixos lidos no meio do contorno de cada um (a 75 mm)
    a = Barra(inicio=(0.0, -37.5, 3500.0), fim=(6000.0, -37.5, 3500.0), perfil=UE200, rotacao=0.0)     # boca para +y
    b = Barra(inicio=(0.0, 37.5, 3500.0), fim=(6000.0, 37.5, 3500.0), perfil=UE200, rotacao=180.0)     # boca para −y
    antes = _faixa(a, 1)[1] - _faixa(b, 1)[0]
    assert antes > 20, "sem a correção os dois Ue entram um no outro (%.1f mm)" % antes
    r = eixo_pelo_contorno([a, b])
    assert r["deslocadas"] == 2
    (a0, a1), (b0, b1) = _faixa(a, 1), _faixa(b, 1)
    assert a1 == pytest.approx(b0, abs=0.5), "os lábios se encostam"
    assert b1 - a0 == pytest.approx(150.0, abs=0.5), "a caixa fecha com 150 mm, como no Det. Típico VM"


def test_secao_simetrica_nao_se_move():
    w = Barra(inicio=(0.0, 0.0, 0.0), fim=(0.0, 0.0, 3000.0), perfil="W 200×35,9", rotacao=0.0)
    r = eixo_pelo_contorno([w])
    assert r["deslocadas"] == 0 and w.inicio == (0.0, 0.0, 0.0)
    assert meio_do_contorno("W 200×35,9") == pytest.approx((0.0, 0.0), abs=0.01)


def test_corrente_vai_ate_a_alma_pela_boca_e_pelas_costas():
    # terça Ue 150×60 ao longo de y, boca para +x (giro 180); correntes chegando dos dois lados, paradas a 40 mm do eixo
    t = Barra(inicio=(0.0, 0.0, 17000.0), fim=(0.0, 6000.0, 17000.0), perfil=UE150, rotacao=180.0)
    u = base_local((0.0, 6000.0, 0.0), 180.0)[0]
    assert u[0] == pytest.approx(1.0)
    xs = [q[0] for q in secao(resolver_perfil(UE150))]
    fora = min(xs)                                            # face de fora da alma (costas), a partir do centroide
    c_costas = Barra(inicio=(-1500.0, 3000.0, 17000.0), fim=(-40.0, 3000.0, 17000.0), perfil="L 50×3,00 (FF)")
    c_boca = Barra(inicio=(40.0, 3000.0, 17000.0), fim=(1500.0, 3000.0, 17000.0), perfil="L 50×3,00 (FF)")
    r = correntes_ate_a_alma([c_costas, c_boca], [t])
    assert r["pontas"] == 2
    assert c_costas.fim[0] == pytest.approx(fora, abs=0.5), "do lado das costas, na face de fora da alma"
    assert fora < c_boca.inicio[0] < fora + 4.0, "do lado da boca, na face de dentro da alma (a espessura dela)"
    assert c_boca.fim == (1500.0, 3000.0, 17000.0), "a outra ponta (longe de terça) fica"
