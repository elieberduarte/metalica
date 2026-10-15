# -*- coding: utf-8 -*-
"""As ligações da biblioteca (nucleo/acessorios.py, a tela /ligacoes) aplicadas no modelo 3D, nas peças escolhidas.

F13 da análise de 14/10/2026 (Projeto/ANALISES/Editor-3D): a biblioteca calcula 23 ligações pela NBR, mas só desenha e
verifica — não punha nada no 3D, e o usuário tinha de montar chapa, furo e parafuso à mão. Aqui cada tipo sabe onde
as peças dele ficam a partir das barras escolhidas (o pé do pilar, a ponta da viga e a face da mesa do pilar, o topo
do pilar sob o banzo), com as mesmas medidas e a mesma furação da biblioteca.

Decisão do usuário (14/10): a ligação aplicada continua paramétrica. Toda peça gerada leva `atributos.ligacao` =
{id, tipo, parametros, pecas (as barras ligadas), ajustes (os campos das barras antes da ligação)}: o editor refaz a
ligação quando uma barra dela muda, edita os parâmetros e apaga a ligação inteira, devolvendo as barras como eram.

`aplicar` não altera o documento recebido: devolve as entidades novas (com marca, conjunto e solda definidos), as
alterações das barras e as entidades da versão anterior da ligação a remover, para o editor aplicar com desfazer.
"""
import collections
import copy
import dataclasses
import math
import re
from typing import Dict, List, Optional, Sequence

from nucleo.base import ErroDeDados

#: os tipos da biblioteca que sabem se pôr no 3D, com o que cada um pede
TIPOS_3D = {
    "placa_base_rotulada": {"pede": "um pilar (ou vários)", "barras": ("pilar",)},
    "placa_base_engastada": {"pede": "um pilar (ou vários)", "barras": ("pilar",)},
    "chapa_topo_joelho": {"pede": "uma viga e o pilar em que ela chega", "barras": ("viga", "pilar")},
    "tesoura_topo_pilar": {"pede": "um pilar e a viga ou o banzo que apoia no topo dele", "barras": ("pilar", "viga")},
    "suporte_terca_cadeirinha": {"pede": "as terças e os banzos (ou vigas) em que elas apoiam — uma cadeirinha em "
                                         "cada cruzamento", "barras": ("terca", "apoio")},
    "ligacao_flexivel": {"pede": "a viga apoiada e o pilar ou a viga em que ela chega", "barras": ("viga", "apoio")},
    "emenda_banzo": {"pede": "as duas metades do banzo, na mesma reta", "barras": ("barra", "barra")},
    "gusset_contravento": {"pede": "a diagonal do contravento e o pilar ou a viga em que ela chega", "barras": ("viga", "apoio")},
    "chumbador_gancho": {"pede": "a placa (chapa) com os furos — um chumbador em J em cada furo", "barras": ("chapa",)},
    "chumbador_placa": {"pede": "a placa (chapa) com os furos — um chumbador com placa de ancoragem em cada furo",
                        "barras": ("chapa",)},
    "presilhas": {"pede": "as duas barras do perfil duplo (cantoneiras ou U costas com costas)", "barras": ("barra", "barra")},
    "suporte_contravento": {"pede": "o tirante e o(s) banzo(s) ou viga(s) em que ele chega", "barras": ("tirante", "apoio")},
}


# ------------------------------------------------------------------ vetores

def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cruz(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    if n < 1e-9:
        raise ErroDeDados("direção degenerada")
    return (a[0] / n, a[1] / n, a[2] / n)


def _r(p, casas=3):
    return [round(float(x), casas) for x in p]


def _acima(n, m=10.0):
    return math.ceil(n / m) * m


# ------------------------------------------------------------------ peças

def _perfil(nome):
    from nucleo3d.geometria import resolver_perfil
    try:
        return resolver_perfil(nome)
    except Exception as exc:                              # noqa: BLE001
        raise ErroDeDados("perfil %s fora do catálogo: %s" % (nome, exc))


def _triedro(b):
    from nucleo3d.geometria import base_local
    return base_local(b.direcao, b.rotacao or 0.0)


def _parafuso(centro, eixo, d, pega, classe):
    from nucleo3d.lancamento import _parafuso_solido
    from nucleo.acessorios import comprimento_parafuso
    s = _parafuso_solido(centro, eixo, d, comprimento_parafuso(pega, d), classe)
    s.atributos["parafuso"].update(ponto=_r(centro, 2), eixo=_r(eixo, 6), pega=round(pega, 1))
    s.atributos["criado_no_editor"] = True
    return s


def _chapa(nome, origem, ex, ey, B, H, t, furos, aco="ASTM A36"):
    from nucleo3d.modelo import Chapa
    return Chapa(nome=nome, origem=tuple(origem), eixo_x=tuple(ex), eixo_y=tuple(ey),
                 contorno=[(0.0, 0.0), (B, 0.0), (B, H), (0.0, H)], espessura=t, centrada=False,
                 furos=[{"x": round(x, 2), "y": round(y, 2), "diametro": round(fd, 2)} for x, y, fd in furos],
                 camada="Chapas", material="Aço", aco=aco, atributos={"tipo_ifc": "IfcPlate"})


def _ponta_de_baixo(b):
    """('inicio'|'fim', ponto de baixo, ponto de cima)"""
    return ("inicio", b.inicio, b.fim) if b.inicio[2] <= b.fim[2] else ("fim", b.fim, b.inicio)


def _ponta_perto(b, ponto, eixo):
    """a ponta da barra mais perto da reta (ponto, eixo): ('inicio'|'fim', nó, o outro nó)"""
    def dist(p):
        q = _sub(p, ponto)
        return math.sqrt(max(0.0, _dot(q, q) - _dot(q, eixo) ** 2))
    return ("inicio", b.inicio, b.fim) if dist(b.inicio) <= dist(b.fim) else ("fim", b.fim, b.inicio)


# ------------------------------------------------------------------ os tipos

def _base(pilar, p, engastada):
    """Placa de base no pé do pilar, com os chumbadores; o pilar fica mais curto pela espessura (o nível do pé é o
    de baixo da placa)."""
    from nucleo.acessorios import DIAMETROS_BARRA
    from nucleo3d.modelo import Barra
    from nucleo3d import geometria as geo
    pf = _perfil(pilar.perfil)
    d, bf = float(pf.d or 250), float(pf.bf or 150)
    ponta, pe, topo = _ponta_de_baixo(pilar)
    up = _norm(_sub(topo, pe))
    if up[2] < 0.7:
        raise ErroDeDados("a placa de base vai no pé de um pilar em pé — a barra %s está deitada" % (pilar.nome or pilar.id))
    u, v, _ = _triedro(pilar)
    ex, ey = u, v
    if _dot(_cruz(ex, ey), up) < 0:
        ex = _mul(u, -1.0)
    # medidas: as dadas, ou pela seção (as folgas da biblioteca: 300 × 450 numa W 250)
    folga_B, folga_L = (100.0, 100.0) if engastada else (120.0, 110.0)
    B = float(p.get("B") or _acima(bf + 150.0))
    L = float(p.get("L") or _acima(d + 190.0))
    gB = float(p.get("gab_B") or B - folga_B)
    gL = float(p.get("gab_L") or L - folga_L)
    t = float(p.get("t") or (31.75 if engastada else 25.4))
    nome_ch = str(p.get("chumbador") or ('1"' if engastada else '3/4"'))
    dch = DIAMETROS_BARRA[nome_ch]
    fd = round(dch + 6.0)
    furos = [(B / 2 + sx * gB / 2, L / 2 + sy * gL / 2, fd) for sx in (-1, 1) for sy in ((-1, 1) if engastada else (0,))]
    origem = _add(pe, _add(_mul(ex, -B / 2), _mul(ey, -L / 2)))
    placa = _chapa("Placa de base", origem, ex, ey, B, L, t, furos, aco=str(p.get("aco") or "ASTM A36"))
    # o pilar começa em cima da placa
    campo = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ajustes = {pilar.id: {campo: float(getattr(pilar, campo) or 0.0)}}
    alterar = {pilar.id: {campo: float(getattr(pilar, campo) or 0.0) + t}}
    # chumbadores: do alto da projeção para baixo, em cada furo
    Lc = float(p.get("comprimento_chumbador") or (900.0 if engastada else 600.0))
    proj = max(120.0, t + 1.5 * dch + 40.0)
    perfil_ch = "FE RED %s" % nome_ch.replace('"', "''")
    geo.registrar_perfil(geo.barra_redonda(dch, perfil_ch))
    chumb = []
    for x, y, _ in furos:
        c = _add(origem, _add(_mul(ex, x), _mul(ey, y)))
        chumb.append(Barra(nome="Chumbador", inicio=_add(c, _mul(up, proj)), fim=_add(c, _mul(up, proj - Lc)),
                           perfil=perfil_ch, papel="chumbador", camada="Referência", material="Aço",
                           atributos={"tipo_ifc": "IfcMember", "elemento": "Chumbador", "projecao_mm": round(proj)}))
    tf = float(pf.tf or 10.0)
    from nucleo2d.detalhe.soldas import _perna
    soldas = [(pilar.id, placa, {"tipo": "filete", "perna": _perna(tf, t), "lados": 1, "local": "fabrica",
                                 "forma": "contorno"})]
    params = dict(p, pilar=pilar.perfil, B=B, L=L, t=t, gab_B=gB, gab_L=gL, chumbador=nome_ch, comprimento_chumbador=Lc)
    return {"pecas": [placa] + chumb, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(pilar, [placa])],
            "soldas": soldas, "parametros": params, "avisos": []}


def _chapa_topo(viga, pilar, p):
    """Chapa de topo soldada na ponta da viga, parafusada na face do pilar (mesa ou alma, a que está de frente para a
    viga). A viga é cortada na face de fora da chapa (corte no ângulo: a viga inclinada também)."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    pv, pp = _perfil(viga.perfil), _perfil(pilar.perfil)
    dv, bfv, tfv = float(pv.d or 300), float(pv.bf or 150), float(pv.tf or 10)
    dp, twp, tfp = float(pp.d or 300), float(pp.tw or 6), float(pp.tf or 10)
    _, pe, topo = _ponta_de_baixo(pilar)
    eixo_p = _norm(_sub(topo, pe))
    ponta, no, outro = _ponta_perto(viga, pe, eixo_p)
    dirv = _norm(_sub(outro, no))                          # da ligação para dentro da viga
    horiz = _sub(dirv, _mul(eixo_p, _dot(dirv, eixo_p)))
    if math.sqrt(_dot(horiz, horiz)) < 0.2:
        raise ErroDeDados("a viga corre ao longo do pilar: não há face para a chapa de topo")
    horiz = _norm(horiz)
    up_, vp_, _ = _triedro(pilar)
    if abs(_dot(horiz, vp_)) >= abs(_dot(horiz, up_)):
        nf, dist, face, parede = (vp_ if _dot(horiz, vp_) > 0 else _mul(vp_, -1.0)), dp / 2.0, "mesa", tfp
    else:
        nf, dist, face, parede = (up_ if _dot(horiz, up_) > 0 else _mul(up_, -1.0)), twp / 2.0, "alma", twp
    t = float(p.get("t") or 25.4)
    q = _add(pe, _mul(eixo_p, _dot(_sub(no, pe), eixo_p)))   # o nó da viga levado ao eixo do pilar
    F = _add(q, _mul(nf, dist))                              # a face do pilar
    fora = _add(F, _mul(nf, t))                              # a face de fora da chapa
    cos_ = _dot(dirv, nf)
    if cos_ < 0.3:
        raise ErroDeDados("a viga chega muito inclinada na face do pilar (%.0f°)" % math.degrees(math.acos(max(-1, min(1, cos_)))))
    s = _dot(_sub(fora, no), nf) / cos_
    X = _add(no, _mul(dirv, s))                               # o eixo da viga na face de fora da chapa
    ex = _norm(_cruz(eixo_p, nf))
    ey = _cruz(nf, ex)
    gab = float(p.get("gabarito") or 100.0)
    B = float(p.get("B") or max(bfv + 30.0, gab + 100.0))
    H = float(p.get("H") or _acima(dv / cos_ + 2 * 70.0, 5.0))
    nome_par = str(p.get("parafuso") or '3/4"')
    d = d_parafuso_mm(nome_par)
    fd = furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    ys = [H - 35.0, H - 105.0, 35.0, 105.0]
    furos = [(B / 2 + sx * gab / 2, y, fd) for y in ys for sx in (-1, 1)]
    avisos = []
    if face == "mesa" and gab + fd + 2 * 20.0 > float(pp.bf or 0):
        avisos.append("o gabarito %g não cabe na mesa do pilar (%g mm)" % (gab, float(pp.bf or 0)))
    if face == "alma" and H > dp - 2 * float(pp.tf or 0):
        avisos.append("a chapa (%g) não cabe entre as mesas do pilar (%g): confira" % (H, dp - 2 * float(pp.tf or 0)))
    origem = _add(_sub(X, _mul(nf, t)), _add(_mul(ex, -B / 2), _mul(ey, -H / 2)))
    chapa = _chapa("Chapa de topo", origem, ex, ey, B, H, t, furos, aco=str(p.get("aco") or "ASTM A36"))
    pars = []
    for x, y, _ in furos:
        h = _add(origem, _add(_mul(ex, x), _mul(ey, y)))      # na face do pilar
        pega = t + parede
        pars.append(_parafuso(_add(h, _mul(nf, (t - parede) / 2.0)), nf, d, pega, classe))
    # a viga cortada na face de fora da chapa (a normal para dentro da viga)
    chave = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ajustes = {viga.id: {chave: copy.deepcopy(getattr(viga, chave) or []), rec: float(getattr(viga, rec) or 0.0)}}
    alterar = {viga.id: {chave: [{"normal": _r(nf, 6), "ponto": _r(_sub(fora, no), 3)}], rec: 0.0}}
    from nucleo2d.detalhe.soldas import _perna
    soldas = [(viga.id, chapa, {"tipo": "filete", "perna": _perna(tfv, t), "lados": 1, "local": "fabrica",
                                "forma": "contorno"})]
    params = dict(p, viga=viga.perfil, t=t, gabarito=gab, B=B, H=H, parafuso=nome_par, classe=classe)
    return {"pecas": [chapa] + pars, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(viga, [chapa])],
            "soldas": soldas, "parametros": params, "avisos": avisos}


def _topo_pilar(pilar, viga, p):
    """Duas chapas horizontais aparafusadas no topo do pilar: a de baixo soldada no pilar, a de cima na viga (o banzo
    inferior da tesoura apoiada). O topo do pilar vai até a chapa de baixo (corte, que encurta ou estica)."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    pv, pp = _perfil(viga.perfil), _perfil(pilar.perfil)
    dv = float(pv.d or 200)
    ponta_b, pe, topo = _ponta_de_baixo(pilar)
    eixo_p = _norm(_sub(topo, pe))
    if eixo_p[2] < 0.7:
        raise ErroDeDados("o topo de pilar pede um pilar em pé")
    uv, vv, wv = _triedro(viga)
    if abs(_dot(wv, (0, 0, 1))) > 0.5:
        raise ErroDeDados("a viga/banzo que apoia no topo do pilar precisa estar deitada")
    # o ponto do eixo da viga sobre o pilar e a face de baixo dela
    a = viga.inicio
    t_ = _dot(_sub(topo, a), wv)
    Pv = _add(a, _mul(wv, t_))
    baixo = vv if vv[2] < 0 else _mul(vv, -1.0)
    face = _add(Pv, _mul(baixo, dv / 2.0))
    face = (topo[0], topo[1], face[2])                   # no eixo do pilar, na altura da face de baixo da viga
    t = float(p.get("t") or 12.7)
    B, L = float(p.get("B") or 200.0), float(p.get("L") or 300.0)
    gB, gL = float(p.get("gab_B") or 120.0), float(p.get("gab_L") or 200.0)
    nome_par = str(p.get("parafuso") or "M16")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    n = int(p.get("n_parafusos") or 4)
    hor = _norm((wv[0], wv[1], 0.0))
    ex = _norm(_cruz((0.0, 0.0, 1.0), hor))                 # ⟂ à viga (largura B)
    ey = hor                                                # ao longo da viga (comprimento L)
    if _dot(_cruz(ex, ey), (0, 0, 1)) < 0:
        ex = _mul(ex, -1.0)
    furos = [(B / 2 + sx * gB / 2, L / 2 + sy * gL / 2, fd) for sx in (-1, 1) for sy in ((-1, 1) if n == 4 else (0,))]
    z_ch6 = face[2] - t
    z_ch5 = face[2] - 2 * t
    o6 = (face[0], face[1], z_ch6)
    o5 = (face[0], face[1], z_ch5)
    desl = _add(_mul(ex, -B / 2), _mul(ey, -L / 2))
    ch5 = _chapa("Chapa do topo do pilar", _add(o5, desl), ex, ey, B, L, t, furos, aco=str(p.get("aco") or "ASTM A36"))
    ch6 = _chapa("Chapa de apoio da viga", _add(o6, desl), ex, ey, B, L, t, furos, aco=str(p.get("aco") or "ASTM A36"))
    pars = []
    for x, y, _ in furos:
        h = _add(_add(o5, desl), _add(_mul(ex, x), _mul(ey, y)))
        pars.append(_parafuso(_add(h, (0.0, 0.0, t)), (0.0, 0.0, 1.0), d, 2 * t, classe))
    # o pilar até a chapa de baixo
    chave = "cortes_fim" if ponta_b == "inicio" else "cortes_inicio"
    rec = "recorte_fim" if ponta_b == "inicio" else "recorte_inicio"
    no = topo
    ajustes = {pilar.id: {chave: copy.deepcopy(getattr(pilar, chave) or []), rec: float(getattr(pilar, rec) or 0.0)}}
    alterar = {pilar.id: {chave: [{"normal": [0.0, 0.0, -1.0], "ponto": _r(_sub(o5, no), 3)}], rec: 0.0}}
    from nucleo2d.detalhe.soldas import _perna
    tfp = float(pp.tf or 10)
    soldas = [(pilar.id, ch5, {"tipo": "filete", "perna": _perna(tfp, t), "lados": 1, "local": "fabrica", "forma": "contorno"}),
              (viga.id, ch6, {"tipo": "filete", "perna": _perna(float(pv.tf or 6), t), "lados": 2, "local": "fabrica", "forma": "T"})]
    params = dict(p, t=t, B=B, L=L, gab_B=gB, gab_L=gL, parafuso=nome_par, classe=classe, n_parafusos=n)
    return {"pecas": [ch5, ch6] + pars, "alterar": alterar, "ajustes": ajustes,
            "conjuntos": [(pilar, [ch5]), (viga, [ch6])], "soldas": soldas, "parametros": params, "avisos": []}


# ------------------------------------------------------------------ apoio comum: a malha da barra

def _malha(b):
    from nucleo3d.geometria import malha_barra
    v, _f = malha_barra(b)
    return v


def _extremos(b, n):
    """(mín, máx) da malha da barra ao longo de n"""
    pr = [_dot(q, n) for q in _malha(b)]
    return min(pr), max(pr)


def _lado_da_alma(b, n):
    """-1 ou +1: o lado (ao longo de n) em que a seção tem a face mais alta — a alma do U, do Ue, do C — e a
    coordenada dessa face; para o I (as duas iguais) devolve 0 e o centro"""
    from nucleo3d.geometria import malha_barra, area_face
    vs, fs = malha_barra(b)
    pr = [_dot(q, n) for q in vs]
    lo, hi = min(pr), max(pr)

    def area(alvo):
        # a área das faces deitadas no plano do extremo: a alma é uma face cheia; do lado aberto do Ue só as tiras
        # dos enrijecedores (a altura total das duas seria igual à da alma)
        return sum(area_face([vs[i] for i in f]) for f in fs if len(f) >= 3 and all(abs(pr[i] - alvo) < 1.0 for i in f))
    a_lo, a_hi = area(lo), area(hi)
    if abs(a_lo - a_hi) <= 0.05 * max(a_lo, a_hi, 1.0):
        return 0, (lo + hi) / 2.0
    return (-1, lo) if a_lo > a_hi else (1, hi)


def _cruzamento(a, b):
    """os pontos mais próximos entre os eixos de a e de b: (pa, ta, pb, tb), t em fração do comprimento"""
    d1, d2 = _sub(a.fim, a.inicio), _sub(b.fim, b.inicio)
    r = _sub(a.inicio, b.inicio)
    A, B, C = _dot(d1, d1), _dot(d1, d2), _dot(d2, d2)
    D, E = _dot(d1, r), _dot(d2, r)
    den = A * C - B * B
    if abs(den) < 1e-9:
        raise ErroDeDados("as barras são paralelas: não se cruzam")
    ta = (B * E - C * D) / den
    tb = (A * E - B * D) / den
    return _add(a.inicio, _mul(d1, ta)), ta, _add(b.inicio, _mul(d2, tb)), tb


def _eixo_secao_mais_perto(b, direcao):
    """o eixo da seção (±u, ±v) mais perto de `direcao`: (vetor, 'u'|'v')"""
    u, v, _ = _triedro(b)
    cands = [(u, "u"), (_mul(u, -1.0), "u"), (v, "v"), (_mul(v, -1.0), "v")]
    return max(cands, key=lambda c: _dot(c[0], direcao))


# ------------------------------------------------------------------ suporte de terça (cadeirinha)

def _cadeirinha(terca, banzo, p):
    """A cadeirinha no cruzamento da terça com o banzo: a base deitada soldada no topo do banzo e a chapa em pé
    soldada nela, encostada por fora na alma da terça, com os oblongos na furação da máquina (50 × 60 até a terça de
    200 mm, 100 × 60 acima). Peças do conjunto do banzo (a tesoura)."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    pt_, pb_ = _perfil(terca.perfil), _perfil(banzo.perfil)
    Pt, ta, Pb, tb = _cruzamento(terca, banzo)
    if not (-0.02 <= ta <= 1.02 and -0.02 <= tb <= 1.02):
        raise ErroDeDados("a terça %s não passa sobre o banzo %s" % (terca.nome or terca.id, banzo.nome or banzo.id))
    sobe = _sub(Pt, Pb)
    wb = _norm(_sub(banzo.fim, banzo.inicio))
    sobe = _sub(sobe, _mul(wb, _dot(sobe, wb)))
    if math.sqrt(_dot(sobe, sobe)) < 1.0:
        sobe = (0.0, 0.0, 1.0)
    nb, _ = _eixo_secao_mais_perto(banzo, _norm(sobe))
    _lo, topo = _extremos(banzo, nb)
    T0 = _add(Pb, _mul(nb, topo - _dot(Pb, nb)))            # o topo do banzo no cruzamento
    wt = _norm(_sub(terca.fim, terca.inicio))
    ex7 = _norm(_sub(wt, _mul(nb, _dot(wt, nb))))           # ao longo da terça, no plano do topo
    s = _cruz(nb, ex7)                                      # atravessado (ao longo do banzo)
    lado, f = _lado_da_alma(terca, s)
    if lado == 0:
        raise ErroDeDados("a terça %s não tem alma de um lado só (perfil %s): a cadeirinha é para U, Ue ou C"
                          % (terca.nome or terca.id, terca.perfil))
    t = float(p.get("t") or 4.75)
    B = float(p.get("largura") or 150.0)
    bl, bb, bt = float(p.get("base_l") or 153.0), float(p.get("base_b") or 44.0), float(p.get("base_t") or 3.0)
    dt = float(pt_.d or 150)
    gv = float(p.get("gab_v") or (100.0 if dt > 200.0 else 50.0))
    gh = float(p.get("gab_h") or 60.0)
    borda = float(p.get("borda_topo") or 30.0)
    n = int(p.get("n_parafusos") or 4)
    nome_par = str(p.get("parafuso") or "M12")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A307")
    oblongo = p.get("oblongo", "horizontal")
    # a altura do centro da alma da terça acima da base: os furos centrados nela
    yc = _dot(_sub(Pt, T0), nb) - bt
    ys = [yc + gv / 2.0, yc - gv / 2.0] if n >= 4 else [yc]
    H = float(p.get("altura") or 0.0)
    H = max(H, _acima(max(ys) + borda, 5.0))
    avisos = []
    if min(ys) < 15.0:
        avisos.append("a terça está baixa demais para a cadeirinha (furo a %.0f mm da base)" % min(ys))
    xs = [B / 2.0 - gh / 2.0, B / 2.0 + gh / 2.0] if n >= 2 else [B / 2.0]
    centro_s = f + lado * t / 2.0                            # o plano médio da chapa em pé, por fora da alma
    desl_s = centro_s - _dot(T0, s)
    base_ch = _add(T0, _mul(s, desl_s))
    o7 = _add(_add(base_ch, _mul(nb, bt)), _mul(ex7, -B / 2.0))
    from nucleo3d.modelo import Chapa
    if oblongo in ("horizontal", "vertical"):
        comp = fd + 12.0
        furos = [{"x": round(x, 2), "y": round(y, 2), "largura": comp if oblongo == "horizontal" else fd,
                  "altura": fd if oblongo == "horizontal" else comp} for y in ys for x in xs]
    else:
        furos = [{"x": round(x, 2), "y": round(y, 2), "diametro": fd} for y in ys for x in xs]
    aco = str(p.get("aco") or "ASTM A36")
    ch7 = Chapa(nome="Suporte de terça (chapa)", origem=o7, eixo_x=ex7, eixo_y=nb,
                contorno=[(0.0, 0.0), (B, 0.0), (B, H), (0.0, H)], espessura=t, centrada=True, furos=furos,
                camada="Chapas", material="Aço", aco=aco, atributos={"tipo_ifc": "IfcPlate"})
    o8 = _add(_add(base_ch, _mul(ex7, -bl / 2.0)), _mul(s, -bb / 2.0))
    ch8 = _chapa("Suporte de terça (base)", o8, ex7, s, bl, bb, bt, [], aco=aco)
    pars = []
    twt = float(pt_.tw or 2.25)
    s_meio = f + lado * (t - twt) / 2.0                      # o meio da pega: chapa por fora + alma
    for y in ys:
        for x in xs:
            h = _add(o7, _add(_mul(ex7, x), _mul(nb, y)))
            c = _add(h, _mul(s, s_meio - _dot(h, s)))
            pars.append(_parafuso(c, s, d, t + twt, classe))
    from nucleo2d.detalhe.soldas import _perna
    tfb = float(pb_.tf or pb_.tw or 3.0)
    soldas = [(banzo.id, ch8, {"tipo": "filete", "perna": _perna(tfb, bt), "lados": 1, "local": "fabrica", "forma": "sobreposição"})]
    params = dict(p, largura=B, altura=H, t=t, base_l=bl, base_b=bb, base_t=bt, gab_v=gv, gab_h=gh,
                  n_parafusos=n, parafuso=nome_par, classe=classe, oblongo=oblongo, t_terca=twt)
    return {"pecas": [ch7, ch8] + pars, "alterar": {}, "ajustes": {}, "conjuntos": [(banzo, [ch7, ch8])],
            "soldas": soldas, "soldas_entre": [(ch7, ch8, {"tipo": "filete", "perna": _perna(t, bt), "lados": 2,
                                                          "local": "fabrica", "forma": "T"})],
            "parametros": params, "avisos": avisos}


# ------------------------------------------------------------------ ligação flexível (duas cantoneiras)

def _face_do_apoio(apoio, no, dirv):
    """a face do apoio (pilar ou viga) que olha para a ponta da viga: (normal para a viga, ponto da face no eixo
    do nó, espessura da parede, 'mesa'|'alma')"""
    pa = _perfil(apoio.perfil)
    wa = _norm(_sub(apoio.fim, apoio.inicio))
    horiz = _sub(dirv, _mul(wa, _dot(dirv, wa)))
    if math.sqrt(_dot(horiz, horiz)) < 0.2:
        raise ErroDeDados("a viga corre ao longo do apoio: não há face para ligar")
    nf, eixo = _eixo_secao_mais_perto(apoio, _norm(horiz))
    q = _add(apoio.inicio, _mul(wa, _dot(_sub(no, apoio.inicio), wa)))
    if eixo == "v":
        return nf, _add(q, _mul(nf, float(pa.d or 200) / 2.0)), float(pa.tf or 8), "mesa"
    return nf, _add(q, _mul(nf, float(pa.tw or 6) / 2.0)), float(pa.tw or 6), "alma"


def _cantoneira_no_canto(perfil, a, heel, d1, d2, comp):
    """a Barra de cantoneira de eixo `a`, comprimento `comp` centrada no `heel`, com as abas para d1 e para d2 (a
    rotação achada pela malha, como no suporte da Montagem)"""
    from nucleo3d.modelo import Barra
    melhor = None
    for rot in (0.0, 90.0, 180.0, 270.0):
        b = Barra(inicio=(0.0, 0.0, 0.0), fim=_mul(a, comp), perfil=perfil, rotacao=rot)
        pts = [(_dot(q, d1), _dot(q, d2)) for q in _malha(b)]
        x0, y0 = min(p_[0] for p_ in pts), min(p_[1] for p_ in pts)
        x1, y1 = max(p_[0] for p_ in pts), max(p_[1] for p_ in pts)
        tol = 1.0
        canto_cheio = any(abs(p_[0] - x0) < tol and abs(p_[1] - y0) < tol for p_ in pts)
        canto_vazio = not any(abs(p_[0] - x1) < tol and abs(p_[1] - y1) < tol for p_ in pts)
        if canto_cheio and canto_vazio:
            melhor = (rot, x0, y0)
            break
    if melhor is None:
        raise ErroDeDados("não consegui virar a cantoneira %s no canto da ligação" % perfil)
    rot, x0, y0 = melhor
    base = _add(_add(heel, _mul(d1, -x0)), _mul(d2, -y0))
    return Barra(nome="Cantoneira de ligação", inicio=_add(base, _mul(a, -comp / 2.0)), fim=_add(base, _mul(a, comp / 2.0)),
                 perfil=perfil, rotacao=rot, papel="suporte", camada="Chapas", material="Aço",
                 atributos={"tipo_ifc": "IfcMember"})


def _flexivel(viga, apoio, p):
    """Duas cantoneiras abraçando a alma da viga, parafusadas na alma dela e na face do apoio (a mesa do pilar ou a
    alma da viga principal); a viga fica 10 mm antes da face."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    pv = _perfil(viga.perfil)
    eixo_a = _norm(_sub(apoio.fim, apoio.inicio))
    ponta, no, outro = _ponta_perto(viga, apoio.inicio, eixo_a)
    dirv = _norm(_sub(outro, no))
    nf, F, parede, face = _face_do_apoio(apoio, no, dirv)
    if _dot(dirv, nf) < 0.3:
        raise ErroDeDados("a viga chega muito inclinada na face do apoio")
    folga = float(p.get("folga") or 10.0)
    perfil_l = str(p.get("cantoneira") or "L 3'' X 5/16''")
    pl = _perfil(perfil_l)
    t_l = float(pl.tf or pl.tw or 7.94)
    n = int(p.get("n_parafusos") or 3)
    pas = float(p.get("passo") or 76.0)
    Hc = (n - 1) * pas + 70.0
    nome_par = str(p.get("parafuso") or '3/4"')
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    uv, vv, _ = _triedro(viga)
    s = _norm(_sub(uv, _mul(nf, _dot(uv, nf))))             # atravessado à alma da viga
    a = _norm(_cruz(nf, s))                                  # ao longo das cantoneiras (a "altura")
    # o eixo da viga na face do apoio
    X = _add(no, _mul(dirv, _dot(_sub(F, no), nf) / _dot(dirv, nf)))
    twv = float(pv.tw or 6.0)
    avisos = []
    if Hc > float(pv.d or 0) - 2 * float(pv.tf or 0):
        avisos.append("as cantoneiras (%g mm) passam da altura livre da alma da viga" % Hc)
    if abs(eixo_a[2]) < 0.7:
        avisos.append("viga apoiada em viga: as mesas da viga apoiada pedem recorte (cope) para não bater na mesa da principal")
    pecas, pars = [], []
    gauge = 45.0
    for lado in (1.0, -1.0):
        sd = _mul(s, lado)
        heel = _add(X, _mul(sd, twv / 2.0))
        pecas.append(_cantoneira_no_canto(perfil_l, a, heel, sd, nf, Hc))
    alturas = [(i - (n - 1) / 2.0) * pas for i in range(n)]
    for h in alturas:
        # na alma da viga: atravessa as duas cantoneiras e a alma
        c = _add(_add(X, _mul(nf, gauge)), _mul(a, h))
        pars.append(_parafuso(c, s, d, 2 * t_l + twv, classe))
        for lado in (1.0, -1.0):
            c2 = _add(_add(X, _mul(s, lado * (twv / 2.0 + gauge))), _mul(a, h))
            c2 = _add(c2, _mul(nf, (t_l - parede) / 2.0))
            pars.append(_parafuso(c2, nf, d, t_l + parede, classe))
    chave = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ajustes = {viga.id: {chave: copy.deepcopy(getattr(viga, chave) or []), rec: float(getattr(viga, rec) or 0.0)}}
    alterar = {viga.id: {chave: [{"normal": _r(nf, 6), "ponto": _r(_sub(_add(F, _mul(nf, folga)), no), 3)}], rec: 0.0}}
    params = dict(p, viga=viga.perfil, cantoneira=perfil_l, n_parafusos=n, passo=pas, parafuso=nome_par, classe=classe,
                  folga=folga)
    return {"pecas": pecas + pars, "alterar": alterar, "ajustes": ajustes, "conjuntos": [], "soldas": [],
            "parametros": params, "avisos": avisos}


# ------------------------------------------------------------------ emenda de banzo (talas)

def _emenda_banzo(a, b, p):
    """Duas talas, uma de cada lado da alma, na junta de duas barras na mesma reta (a tesoura que sai em duas
    metades); parafusos dos dois lados da junta."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    wa = _norm(_sub(a.fim, a.inicio))
    if abs(abs(_dot(wa, _norm(_sub(b.fim, b.inicio)))) - 1.0) > 1e-3:
        raise ErroDeDados("a emenda pede duas barras na mesma reta")
    pontas = sorted(((math.dist(pa, pb), pa, pb) for pa in (a.inicio, a.fim) for pb in (b.inicio, b.fim)), key=lambda t_: t_[0])
    gap, pa, pb = pontas[0]
    if gap > 100.0:
        raise ErroDeDados("as duas barras estão %.0f mm afastadas: a emenda é na junta delas" % gap)
    J = _mul(_add(pa, pb), 0.5)
    pf = _perfil(a.perfil)
    u, v, _ = _triedro(a)
    lado, f = _lado_da_alma(a, u)
    tw = float(pf.tw or 3.0)
    centro_alma = (_dot(J, u)) if lado == 0 else f - lado * tw / 2.0
    t = float(p.get("t") or 6.35)
    Lc = float(p.get("comprimento_tala") or 400.0)
    B = float(p.get("largura_tala") or 120.0)
    livre = float(pf.d or 150) - 2 * float(pf.tf or 3) - 10.0
    avisos = []
    if B > livre:
        avisos.append("tala de %g mm reduzida para %g (altura livre da alma)" % (B, livre))
        B = max(40.0, livre)
    n = int(p.get("n_por_lado") or 3)
    pas = float(p.get("passo") or 60.0)
    nome_par = str(p.get("parafuso") or "M16")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    xs = [Lc / 2.0 + sx * (40.0 + i * pas) for sx in (-1, 1) for i in range(n)]
    if max(xs) + 25.0 > Lc:
        Lc = _acima(max(xs) + 30.0, 10.0)
        xs = [Lc / 2.0 + sx * (40.0 + i * pas) for sx in (-1, 1) for i in range(n)]
    furos = [(x, B / 2.0, fd) for x in xs]
    aco = str(p.get("aco") or "ASTM A36")
    talas = []
    Ju = _add(J, _mul(u, centro_alma - _dot(J, u)))
    for sx in (1.0, -1.0):
        c = _add(Ju, _mul(u, sx * (tw / 2.0)))
        ex, ey = wa, v
        # a tala cresce para fora da alma: normal ex × ey = ±u
        if _dot(_cruz(ex, ey), _mul(u, sx)) < 0:
            ey = _mul(v, -1.0)
        o = _add(_add(c, _mul(ex, -Lc / 2.0)), _mul(ey, -B / 2.0))
        talas.append(_chapa("Tala de emenda", o, ex, ey, Lc, B, t, furos, aco=aco))
    pars = []
    for x in xs:
        c = _add(_add(Ju, _mul(wa, x - Lc / 2.0)), (0.0, 0.0, 0.0))
        pars.append(_parafuso(c, u, d, 2 * t + tw, classe))
    params = dict(p, comprimento_tala=Lc, largura_tala=B, t=t, n_por_lado=n, passo=pas, parafuso=nome_par,
                  classe=classe, t_banzo=tw)
    return {"pecas": talas + pars, "alterar": {}, "ajustes": {}, "conjuntos": [], "soldas": [],
            "parametros": params, "avisos": avisos}


# ------------------------------------------------------------------ gusset de contravento

def _casco2(pts):
    from nucleo3d.producao import _casco
    return _casco(pts)


def _gusset(diag, apoio, p):
    """A chapa de nó do contravento: no plano da diagonal com o apoio, soldada na face do apoio que olha para a
    diagonal, encostada na face plana da diagonal (a aba da cantoneira); parafusos na linha do meio dessa face; a
    diagonal aparada antes da face do apoio."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    pa = _perfil(apoio.perfil)
    wa = _norm(_sub(apoio.fim, apoio.inicio))
    ponta, no, outro = _ponta_perto(diag, apoio.inicio, wa)
    wd = _norm(_sub(outro, no))                           # da ligação para dentro da diagonal
    nplano = _cruz(wa, wd)
    if math.sqrt(_dot(nplano, nplano)) < 0.2:
        raise ErroDeDados("a diagonal corre junto do apoio: não há plano para a chapa de nó")
    nplano = _norm(nplano)
    nf, F, parede, face = _face_do_apoio(apoio, no, wd)
    if _dot(wd, nf) < 0.15:
        raise ErroDeDados("a diagonal não sai da face do apoio")
    t = float(p.get("t") or 8.0)
    n = int(p.get("n_parafusos") or 2)
    pas = float(p.get("passo") or 55.0)
    nome_par = str(p.get("parafuso") or "M16")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    folga = float(p.get("folga") or 20.0)
    # a face plana da diagonal ao longo da normal do plano (a aba da cantoneira): a chapa encosta nela
    lado, f = _lado_da_alma(diag, nplano)
    if lado == 0:
        lado, f = 1, _extremos(diag, nplano)[0]            # seção simétrica: a chapa encosta numa das faces (fica de lado)
        lado_chapa = -1.0
    else:
        lado_chapa = float(lado)
    # o plano médio da chapa: a face da diagonal mais meia espessura para fora
    s_meio = f + lado_chapa * t / 2.0
    # a linha dos parafusos: o meio da faixa da face da diagonal (a aba), no plano da chapa
    from nucleo3d.geometria import malha_barra
    vs, _ = malha_barra(diag)
    perp = _norm(_cruz(nplano, wd))
    na_face = [q for q in vs if abs(_dot(q, nplano) - f) < 1.0]
    if na_face:
        lo_p, hi_p = min(_dot(q, perp) for q in na_face), max(_dot(q, perp) for q in na_face)
        desl_p = (lo_p + hi_p) / 2.0 - _dot(no, perp)
        larg_aba = hi_p - lo_p
    else:
        desl_p, larg_aba = 0.0, float(p.get("largura_barra") or 60.0)
    # o ponto onde a linha dos parafusos sai da face do apoio (mais a folga): o primeiro parafuso a 40 + borda
    base_linha = _add(_add(no, _mul(perp, desl_p)), _mul(nplano, s_meio - _dot(no, nplano)))
    s_face = _dot(_sub(F, base_linha), nf) / _dot(wd, nf)
    corte = _add(base_linha, _mul(wd, s_face + folga / _dot(wd, nf)))      # a ponta da diagonal (aparada)
    borda = max(30.0, 1.75 * d)
    bolts = [_add(corte, _mul(wd, borda + 10.0 + i * pas)) for i in range(n)]
    # o contorno: o casco da linha de solda na face e da região dos parafusos com as bordas
    ex = wa
    ey = _norm(_sub(nf, _mul(nplano, _dot(nf, nplano))))
    if _dot(_cruz(ex, ey), _mul(nplano, lado_chapa)) < 0:
        ex = _mul(ex, -1.0)
    o_ch = _add(F, _mul(nplano, s_meio - _dot(F, nplano)))
    def loc(q):
        r = _sub(q, o_ch)
        return (_dot(r, ex), _dot(r, ey))
    pts = []
    for q in bolts:
        x, y = loc(q)
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
            pts.append((x + ax * borda, y + ay * borda))
    xs_b = [loc(q)[0] for q in bolts] + [loc(corte)[0]]
    pts += [(min(xs_b) - borda, 0.0), (max(xs_b) + borda, 0.0)]
    casco = _casco2(pts)
    casco = [(x, max(0.0, y)) for x, y in casco]
    x0, y0 = min(q[0] for q in casco), min(q[1] for q in casco)
    cont = [(round(x - x0, 1), round(y - y0, 1)) for x, y in casco]
    origem = _add(_add(o_ch, _mul(ex, x0)), _mul(ey, y0))
    furos = []
    for q in bolts:
        x, y = loc(q)
        furos.append({"x": round(x - x0, 2), "y": round(y - y0, 2), "diametro": round(fd, 2)})
    from nucleo3d.modelo import Chapa
    ch = Chapa(nome="Chapa de nó (gusset)", origem=tuple(origem), eixo_x=tuple(ex), eixo_y=tuple(ey), contorno=cont,
               espessura=t, centrada=True, furos=furos, camada="Chapas", material="Aço",
               aco=str(p.get("aco") or "ASTM A36"), atributos={"tipo_ifc": "IfcPlate"})
    t_aba = float(_perfil(diag.perfil).tw or _perfil(diag.perfil).tf or 6.35)
    pars = []
    for q in bolts:
        # o meio da pega: chapa + aba, a partir do plano entre as duas
        c = _add(q, _mul(nplano, -lado_chapa * t_aba / 2.0))
        pars.append(_parafuso(c, nplano, d, t + t_aba, classe))
    chave = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ajustes = {diag.id: {chave: copy.deepcopy(getattr(diag, chave) or []), rec: float(getattr(diag, rec) or 0.0)}}
    alterar = {diag.id: {chave: [{"normal": _r(nf, 6), "ponto": _r(_sub(_add(F, _mul(nf, folga)), no), 3)}], rec: 0.0}}
    from nucleo2d.detalhe.soldas import _perna
    soldas = [(apoio.id, ch, {"tipo": "filete", "perna": _perna(parede, t), "lados": 2, "local": "fabrica", "forma": "T"})]
    ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(_dot(wd, wa))))))
    bb = [q[0] for q in cont], [q[1] for q in cont]
    params = dict(p, comprimento=round(max(bb[0]) - min(bb[0])), altura=round(max(bb[1]) - min(bb[1])), t=t, n_parafusos=n,
                  passo=pas, parafuso=nome_par, classe=classe, angulo=round(ang, 1), largura_barra=round(larg_aba, 1),
                  folga=folga)
    avisos = []
    if face == "alma":
        avisos.append("a chapa de nó vai na alma do apoio (entre as mesas): confira o acesso para a solda")
    return {"pecas": [ch] + pars, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(apoio, [ch])],
            "soldas": soldas, "parametros": params, "avisos": avisos}


# ------------------------------------------------------------------ chumbadores nos furos de uma chapa

def _chumbadores(ch, p, tipo):
    """Um chumbador em cada furo da chapa (a placa de base desenhada à mão): em J (o gancho fica gravado na barra, como
    no lançamento) ou com a placa de ancoragem embaixo; para baixo na placa deitada, para trás na placa em pé."""
    from nucleo.acessorios import DIAMETROS_BARRA
    from nucleo3d.modelo import Barra, Chapa
    from nucleo3d import geometria as geo
    if not (ch.furos or []):
        raise ErroDeDados("a chapa %s não tem furos para os chumbadores" % (ch.nome or ch.id))
    ex, ey = _norm(tuple(ch.eixo_x)), _norm(tuple(ch.eixo_y))
    nrm = _norm(_cruz(ex, ey))
    t = float(ch.espessura or 0.0)
    o = tuple(ch.origem)
    baixo_face = o if not ch.centrada else _sub(o, _mul(nrm, t / 2.0))
    if abs(nrm[2]) > 0.7:
        cima = (0.0, 0.0, 1.0)
        avisos = []
    else:
        cima = nrm                                         # a placa em pé: o chumbador entra para trás dela
        avisos = ["placa em pé: os chumbadores entram pelo lado de trás dela — confira o lado do concreto"]
    # a face de baixo (a que encosta no concreto/graute)
    faces = [baixo_face, _add(baixo_face, _mul(nrm, t))]
    pe = min(faces, key=lambda q: _dot(q, cima))
    nome = str(p.get("diametro") or '3/4"')
    d = DIAMETROS_BARRA[nome]
    L = float(p.get("comprimento") or 996.0)
    proj = float(p.get("projecao") or 120.0)
    perfil = "FE RED %s" % nome.replace('"', "''")
    geo.registrar_perfil(geo.barra_redonda(d, perfil))
    pecas = []
    for f in ch.furos:
        diam = float(f.get("diametro") or min(float(f.get("largura") or 0), float(f.get("altura") or 0)) or 0)
        if diam and diam < d + 1.0:
            avisos.append("furo Ø%g menor que o chumbador Ø%g" % (diam, d))
        c = _add(_add(o, _mul(ex, float(f.get("x", 0)))), _mul(ey, float(f.get("y", 0))))
        c = _add(c, _mul(nrm, _dot(_sub(pe, c), nrm)))   # no plano da face de baixo
        topo = _add(c, _mul(cima, proj))
        fundo = _add(topo, _mul(cima, -L))
        at = {"tipo_ifc": "IfcMember", "elemento": "Chumbador", "projecao_mm": round(proj)}
        if tipo == "chumbador_gancho":
            at["gancho_mm"] = float(p.get("gancho") or 150.0)
        pecas.append(Barra(nome="Chumbador", inicio=tuple(topo), fim=tuple(fundo), perfil=perfil, papel="chumbador",
                           camada="Referência", material="Aço", atributos=at))
        if tipo == "chumbador_placa":
            a, ta = float(p.get("placa") or 70.0), float(p.get("placa_t") or 9.5)
            pecas.append(Chapa(nome="Placa de ancoragem", origem=tuple(_add(_add(fundo, _mul(ex, -a / 2)), _mul(ey, -a / 2))),
                               eixo_x=tuple(ex), eixo_y=tuple(ey), contorno=[(0, 0), (a, 0), (a, a), (0, a)], espessura=ta,
                               centrada=False, furos=[{"x": a / 2, "y": a / 2, "diametro": round(d + 2)}], camada="Referência",
                               material="Aço", atributos={"tipo_ifc": "IfcPlate"}))
    params = dict(p, diametro=nome, comprimento=L, projecao=proj)
    return {"pecas": pecas, "alterar": {}, "ajustes": {}, "conjuntos": [], "soldas": [], "parametros": params,
            "avisos": sorted(set(avisos))}


# ------------------------------------------------------------------ perfil duplo: as presilhas

#: tipos que não estão na biblioteca da tela /ligacoes (sem verificação de lá): os parâmetros ficam aqui
LOCAIS = {
    "presilhas": {
        "nome": "Presilhas do perfil duplo", "categoria": "tesoura",
        "descricao": "As chapas de ligação no vão entre as duas cantoneiras (ou U) costas com costas, soldadas nas duas: "
                     "a quantidade mínima da NBR 8800:2024 (5.3.6.1), igualmente espaçadas.",
        "parametros": [{"chave": "n", "rotulo": "Quantidade (vazio = a da norma)", "unidade": "", "padrao": ""},
                       {"chave": "comprimento", "rotulo": "Comprimento da presilha (ao longo da barra)", "unidade": "mm",
                        "padrao": 60}],
        "esforcos": [],
    },
}


def _presilhas(a, b, p):
    """As presilhas entre as duas barras paralelas do perfil duplo: chapas no vão entre as faces que se olham, com a
    espessura do vão, soldadas nas duas, igualmente espaçadas no trecho em que as duas correm juntas; tudo num conjunto."""
    wa = _norm(_sub(a.fim, a.inicio))
    if abs(_dot(wa, _norm(_sub(b.fim, b.inicio)))) < 0.999:
        raise ErroDeDados("as presilhas pedem as duas barras do perfil duplo, paralelas")
    La = math.dist(a.inicio, a.fim)
    sb = sorted(_dot(_sub(q, a.inicio), wa) for q in (b.inicio, b.fim))
    s0, s1 = max(0.0, sb[0]), min(La, sb[1])
    if s1 - s0 < 200.0:
        raise ErroDeDados("as duas barras quase não correm juntas")
    r = _sub(b.inicio, a.inicio)
    gd = _sub(r, _mul(wa, _dot(r, wa)))
    if math.sqrt(_dot(gd, gd)) < 1.0:
        raise ErroDeDados("as duas barras estão no mesmo eixo")
    gd = _norm(gd)
    fa = _extremos(a, gd)[1]
    fb = _extremos(b, gd)[0]
    vao = fb - fa
    if vao < 3.0:
        raise ErroDeDados("as duas barras estão encostadas (vão de %.1f mm): não há onde pôr a presilha" % vao)
    ey = _norm(_cruz(gd, wa))
    va = [q for q in _malha(a) if abs(_dot(q, gd) - fa) < 1.0]
    vb = [q for q in _malha(b) if abs(_dot(q, gd) - fb) < 1.0]
    if not va or not vb:
        raise ErroDeDados("não achei as faces que se olham no perfil duplo")
    lo = max(min(_dot(q, ey) for q in va), min(_dot(q, ey) for q in vb))
    hi = min(max(_dot(q, ey) for q in va), max(_dot(q, ey) for q in vb))
    if hi - lo < 15.0:
        raise ErroDeDados("as faces que se olham não se cobrem: confira o perfil duplo")
    from nucleo3d.de_planta import _presilhas_pela_norma
    n = int(p.get("n") or 0) or _presilhas_pela_norma(a.perfil)
    Lp = float(p.get("comprimento") or 60.0)
    pecas = []
    ex = wa
    eyp = ey if _dot(_cruz(ex, ey), gd) > 0 else _mul(ey, -1.0)
    for k in range(1, n + 1):
        s = s0 + (s1 - s0) * k / (n + 1.0)
        base = _add(a.inicio, _mul(wa, s))
        base = _add(base, _mul(gd, fa - _dot(base, gd)))                 # na face da barra a
        y0 = lo if eyp is ey else -hi
        o = _add(_add(base, _mul(ex, -Lp / 2.0)), _mul(eyp, y0 - _dot(base, eyp)))
        pecas.append(_chapa("Presilha", o, ex, eyp, Lp, hi - lo, round(vao, 2), []))
    from nucleo2d.detalhe.soldas import _perna
    soldas = []
    for ch in pecas:
        for barra in (a, b):
            soldas.append((barra.id, ch, {"tipo": "filete", "perna": _perna(vao, float(_perfil(barra.perfil).tw or 3)),
                                          "lados": 2, "local": "fabrica", "forma": "contorno"}))
    params = dict(p, n=n, comprimento=Lp, vao=round(vao, 2))
    return {"pecas": pecas, "alterar": {}, "ajustes": {}, "conjuntos": [(a, pecas + [b])], "soldas": soldas,
            "parametros": params, "avisos": []}


# ------------------------------------------------------------------ contravento: o tirante nos suportes (SC1)

LOCAIS["suporte_contravento"] = {
    "nome": "Contravento: tirante nos suportes SC1", "categoria": "contraventamento",
    "descricao": "O detalhe validado na portaria (30/09, banco de detalhes): em cada ponta do tirante uma cantoneira em "
                 "pé no topo do banzo, centrada nele e girada no ângulo do tirante, com o furo a 45 mm do pé; o "
                 "tirante reto entre os furos, passando 40 mm de cada um (porca e rosca).",
    "parametros": [{"chave": "variante", "rotulo": "Suporte (banco de detalhes)", "unidade": "", "padrao": "SC1",
                    "opcoes": ["SC1"]}],
    "esforcos": [],
}


def _suporte_contravento(tirante, apoios, p):
    """O tirante entre os suportes da variante (SC1): o mesmo desenho da montagem pelos quadros
    (de_quadros._contravento_com_sc) — a L em pé no topo do banzo, a aba do furo em esquadro com o tirante, o meio
    da L no eixo do banzo; o tirante esticado de furo a furo mais `passa`. Ponta sem banzo perto fica como está."""
    import numpy as np
    from nucleo import banco_detalhes
    from nucleo2d.reconhecer import perfil_do_texto
    from nucleo3d.modelo import Barra
    from nucleo3d import geometria as G
    var = banco_detalhes.variante(str(p.get("variante") or "SC1")) or banco_detalhes.variante("SC1")
    col = var.get("colocacao") or {}
    r = perfil_do_texto(col.get("peca") or "")
    perfil = r["perfil"] if r else "L 2'' X 3/16''"
    alt, fz = float(col.get("altura") or 90.0), float(col.get("furo_z") or 45.0)
    passa, fd = float(col.get("passa") or 40.0), float(col.get("furo_d") or 16.0)
    pf = _perfil(perfil)
    t_, aba = float(pf.tw or pf.tf or 4.76), float(pf.bf or pf.d or 50.8)
    borda = aba / 2.0
    cache = {}

    def secao(rot):
        rk = round(rot % 360.0, 2)
        if rk not in cache:
            cache[rk] = np.array(G.malha_barra(Barra(inicio=(0, 0, 0), fim=(0, 0, 100), perfil=perfil, rotacao=rk))[0])
        return rk, cache[rk]

    def pose(H, u_out):
        uh = np.array((u_out[0], u_out[1], 0.0))
        uh /= np.linalg.norm(uh)
        nh = np.array((-uh[1], uh[0], 0.0))

        def nota(rot):
            rk, v = secao(rot)
            pu, pn = v @ uh, v @ nh
            return (np.ptp(pu) + np.ptp(pn)) + 0.01 * (pu.max() - pn.min()), rk, pu.max(), pn.min()
        melhor = min((nota(x) for x in np.arange(0.0, 360.0, 0.5)), key=lambda x: x[0])
        melhor = min((nota(melhor[1] + dd) for dd in np.arange(-0.5, 0.51, 0.05)), key=lambda x: x[0])
        _s, rot, hi_u, lo_n = melhor
        eixo = H + uh * (-(hi_u - t_ / 2.0)) + nh * (-(lo_n + borda))
        return rot, eixo, secao(rot)[1] + eixo

    pontas = [np.array(tirante.inicio, float), np.array(tirante.fim, float)]
    Hs, ns, axs, apo = [], [], [], []
    for q in pontas:
        melhor = None
        for ap in apoios:
            wa = np.array(_norm(_sub(ap.fim, ap.inicio)))
            a0 = np.array(ap.inicio, float)
            # a distância em planta da ponta ao eixo do apoio
            wh = np.array((wa[0], wa[1], 0.0))
            if np.linalg.norm(wh) < 1e-6:
                continue
            wh /= np.linalg.norm(wh)
            r_ = (q - a0) * np.array((1, 1, 0))
            dist = float(np.linalg.norm(r_ - wh * (r_ @ wh)))
            if melhor is None or dist < melhor[0]:
                melhor = (dist, ap, wa, a0, wh)
        if melhor is None or melhor[0] > 600.0:
            Hs.append(None); ns.append(None); axs.append(None); apo.append(None)
            continue
        _d, ap, wa, a0, wh = melhor
        Pb = a0 + wa * float((q - a0) @ wa)
        nb, _ = _eixo_secao_mais_perto(ap, (0.0, 0.0, 1.0))
        topo = _extremos(ap, nb)[1]
        z_top = float((Pb + np.array(nb) * (topo - float(np.array(nb) @ Pb)))[2])     # o topo do banzo sobre o eixo
        Hs.append(np.array((Pb[0], Pb[1], z_top + fz)))
        ns.append(np.array((-wh[1], wh[0], 0.0)))
        axs.append(np.array((Pb[0], Pb[1], 0.0)))
        apo.append(ap)
    if not any(h is not None for h in Hs):
        raise ErroDeDados("nenhuma ponta do tirante chega a um banzo ou viga selecionado (até 600 mm em planta)")
    fixos = [h if h is not None else pontas[k] for k, h in enumerate(Hs)]
    for _it in range(4):
        u = (fixos[1] - fixos[0]) / np.linalg.norm(fixos[1] - fixos[0])
        for k, u_out in ((0, -u), (1, u)):
            if Hs[k] is None:
                continue
            _rot, _eixo, v = pose(fixos[k], u_out)
            meio = (v.min(axis=0) + v.max(axis=0)) / 2.0
            fixos[k] = fixos[k] + ns[k] * float((axs[k] - meio) @ ns[k])
    u = (fixos[1] - fixos[0]) / np.linalg.norm(fixos[1] - fixos[0])
    q0 = fixos[0] - u * passa if Hs[0] is not None else pontas[0]
    q1 = fixos[1] + u * passa if Hs[1] is not None else pontas[1]
    pecas, conjuntos, soldas = [], [], []
    from nucleo2d.detalhe.soldas import _perna
    for k, u_out in ((0, -u), (1, u)):
        if Hs[k] is None:
            continue
        rot, eixo, _v = pose(fixos[k], u_out)
        z0 = float(fixos[k][2]) - fz
        sc = Barra(nome=var.get("id") or "SC1", inicio=(float(eixo[0]), float(eixo[1]), z0),
                   fim=(float(eixo[0]), float(eixo[1]), z0 + alt), perfil=perfil, rotacao=round(float(rot), 2), papel="suporte",
                   camada="Suportes", material="Aço", atributos={"tipo_ifc": "IfcMember", "sigla": var.get("id"), "variante": var.get("id")})
        # o furo da L: o marcador que o detalhamento lê (o mesmo da ferramenta Furo), atravessando a aba
        H = fixos[k]
        face = H - u_out * (t_ / 2.0 + 0.5)
        lados = [face + (np.array((-u_out[1], u_out[0], 0.0)) * math.cos(a) + np.array((0, 0, 1.0)) * math.sin(a)) * (fd / 2.0)
                 for a in (2 * math.pi * j / 8 for j in range(8))]
        furo = G.prisma([tuple(float(c) for c in q) for q in lados], tuple(float(c) for c in u_out * (t_ + 1.0)),
                        nome="Furo Ø%g" % fd, camada="Furos", material="Cor #1f2430")
        furo.atributos = {"tipo_ifc": "IfcOpeningElement", "exportar": False,
                          "furo": {"d": fd, "ponto": [round(float(c), 2) for c in face], "eixo": [round(float(c), 6) for c in u_out],
                                   "profundidade": t_ + 1.0, "peca": sc.id}}
        pecas += [sc, furo]
        conjuntos.append((apo[k], [sc]))
        soldas.append((apo[k].id, sc, {"tipo": "filete", "perna": _perna(t_, float(_perfil(apo[k].perfil).tf or 4)),
                                       "lados": 2, "local": "fabrica", "forma": "T"}))
    ajustes = {tirante.id: {"inicio": tuple(tirante.inicio), "fim": tuple(tirante.fim)}}
    alterar = {tirante.id: {"inicio": tuple(round(float(c), 2) for c in q0), "fim": tuple(round(float(c), 2) for c in q1)}}
    params = dict(p, variante=var.get("id"))
    avisos = [] if all(h is not None for h in Hs) else ["uma das pontas do tirante não chega a um banzo selecionado: ficou como estava"]
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": conjuntos, "soldas": soldas,
            "parametros": params, "avisos": avisos}


# ------------------------------------------------------------------ escolher as barras

def _barras_para(doc, tipo, ids):
    """As barras da seleção no papel que o tipo pede, na ordem dele."""
    from nucleo3d.modelo import Barra, Chapa
    pede = TIPOS_3D[tipo]["barras"]
    if pede == ("chapa",):
        chapas = [doc.entidades[i] for i in ids if isinstance(doc.entidades.get(i), Chapa)]
        if not chapas:
            raise ErroDeDados("selecione %s" % TIPOS_3D[tipo]["pede"])
        return [[c] for c in chapas]
    barras = [doc.entidades[i] for i in ids if isinstance(doc.entidades.get(i), Barra)]
    if len(pede) == 1:
        if not barras:
            raise ErroDeDados("selecione %s" % TIPOS_3D[tipo]["pede"])
        return [[b] for b in barras]
    if pede == ("terca", "apoio"):
        return _pares_terca_apoio(barras)
    if pede == ("tirante", "apoio"):
        redondo = lambda b: bool(re.search(r"RED|Ø|TIRANTE|REDOND", str(b.perfil), re.I))      # noqa: E731
        tir = [b for b in barras if str(b.papel).lower().startswith("contravent") or redondo(b)]
        if len(tir) != 1 or len(barras) < 2:
            raise ErroDeDados("selecione %s (um tirante só)" % TIPOS_3D[tipo]["pede"])
        return [[tir[0]] + [b for b in barras if b is not tir[0]]]
    if len(barras) != 2:
        raise ErroDeDados("selecione %s (duas barras)" % TIPOS_3D[tipo]["pede"])
    a, b = barras
    vertical = lambda x: abs(x.direcao[2]) > 0.7               # noqa: E731
    if pede == ("viga", "pilar"):
        if vertical(a) and not vertical(b):
            a, b = b, a
        elif vertical(a) == vertical(b):
            a, b = (a, b) if str(b.papel) == "pilar" else (b, a)
        return [[a, b]]
    if pede == ("pilar", "viga"):
        if vertical(b) and not vertical(a):
            a, b = b, a
        return [[a, b]]
    if pede == ("viga", "apoio"):
        # a apoiada é a que tem a ponta mais perto do eixo da outra
        def ponta_no_eixo(x, y):
            w = _norm(_sub(y.fim, y.inicio))
            def dist(q):
                r = _sub(q, y.inicio)
                return math.sqrt(max(0.0, _dot(r, r) - _dot(r, w) ** 2))
            return min(dist(x.inicio), dist(x.fim))
        if ponta_no_eixo(b, a) < ponta_no_eixo(a, b):
            a, b = b, a
        return [[a, b]]
    return [[a, b]]


def _pares_terca_apoio(barras):
    """cada cruzamento de uma terça (papel terça/longarina, ou a de cima) com um banzo/viga em que ela apoia"""
    tercas = [b for b in barras if str(b.papel).lower() in ("terça", "terca", "longarina")]
    apoios = [b for b in barras if b not in tercas]
    if not tercas and len(barras) == 2:
        a, b = barras
        za = (a.inicio[2] + a.fim[2]) / 2.0
        zb = (b.inicio[2] + b.fim[2]) / 2.0
        tercas, apoios = ([a], [b]) if za > zb else ([b], [a])
    pares = []
    for t in tercas:
        for ap in apoios:
            try:
                Pt, ta, Pb, tb = _cruzamento(t, ap)
            except ErroDeDados:
                continue
            if -0.02 <= ta <= 1.02 and -0.02 <= tb <= 1.02 and math.dist(Pt, Pb) < 1500.0:
                pares.append([t, ap])
    if not pares:
        raise ErroDeDados("nenhuma terça selecionada cruza um banzo ou viga selecionado")
    return pares


def _gerar(tipo, barras, p):
    if tipo in ("placa_base_rotulada", "placa_base_engastada"):
        return _base(barras[0], p, tipo == "placa_base_engastada")
    if tipo == "chapa_topo_joelho":
        return _chapa_topo(barras[0], barras[1], p)
    if tipo == "tesoura_topo_pilar":
        return _topo_pilar(barras[0], barras[1], p)
    if tipo == "suporte_terca_cadeirinha":
        return _cadeirinha(barras[0], barras[1], p)
    if tipo == "ligacao_flexivel":
        return _flexivel(barras[0], barras[1], p)
    if tipo == "emenda_banzo":
        return _emenda_banzo(barras[0], barras[1], p)
    if tipo == "gusset_contravento":
        return _gusset(barras[0], barras[1], p)
    if tipo in ("chumbador_gancho", "chumbador_placa"):
        return _chumbadores(barras[0], p, tipo)
    if tipo == "presilhas":
        return _presilhas(barras[0], barras[1], p)
    if tipo == "suporte_contravento":
        return _suporte_contravento(barras[0], barras[1:], p)
    raise ErroDeDados("a ligação %s ainda não sabe se pôr no 3D" % tipo)


def esforcos_da_analise(analise: Optional[dict], tipo: str, barras) -> Optional[dict]:
    """Os esforços de cálculo da ligação tirados da análise gravada do projeto (nucleo3d/analise_estrutural.py,
    <projeto>/analise_estrutural.json), nas combinações últimas com a 2ª ordem: a reação no pé do pilar (placa de base),
    a ponta da viga no pilar (chapa de topo, ligação flexível), o topo do pilar sob a viga. None quando a análise não tem
    a ligação (o tipo não é desses, a barra não está no unifilar): a verificação fica com os padrões da biblioteca."""
    if not analise or analise.get("instavel"):
        return None
    ab = analise.get("barras") or []
    nos = analise.get("nos") or []
    elu = [c for c, cb in (analise.get("combinacoes") or {}).items() if cb.get("tipo") == "ELU"]
    de = collections.defaultdict(list)
    for i, br in enumerate(ab):
        for eid in br.get("ids") or []:
            de[str(eid).split("#")[0]].append(i)

    def nos_da(b):
        return {n for i in de.get(b.id, []) for n in (ab[i]["a"], ab[i]["b"])}
    if tipo in ("placa_base_rotulada", "placa_base_engastada"):
        ns = [n for n in nos_da(barras[0]) if n < len(nos)]
        if not ns:
            return None
        pe = min(ns, key=lambda n: nos[n][2])
        rs = [(analise.get("por_comb") or {}).get(c, {}).get("reacoes", {}).get(str(pe)) for c in elu]
        rs = [r for r in rs if r]
        if not rs:
            return None
        e = {"N_Sd": round(max(r[2] for r in rs), 2), "H_Sd": round(max(math.hypot(r[0], r[1]) for r in rs), 2)}
        if tipo == "placa_base_engastada":
            e["M_Sd"] = round(max(math.hypot(r[3], r[4]) for r in rs), 2)
        else:
            e["N_min"] = round(min(r[2] for r in rs), 2)
        return e
    if tipo in ("chapa_topo_joelho", "ligacao_flexivel"):
        viga, apoio = barras[0], barras[1]
        ind_v, nos_a = set(de.get(viga.id, [])), nos_da(apoio)
        for lg in analise.get("ligacoes") or []:
            if lg.get("viga") in ind_v and lg.get("no") in nos_a:
                mx = lg.get("max") or {}
                v = lambda k: float((mx.get(k) or [0.0])[0])          # noqa: E731
                if tipo == "ligacao_flexivel":
                    return {"V_Sd": round(v("V"), 2)}
                return {"M_Sd": round(v("Mz"), 2), "V_Sd": round(v("V"), 2), "N_Sd": round(max(v("Nt"), v("Nc")), 2)}
        return None
    if tipo == "tesoura_topo_pilar":
        nos_p = nos_da(barras[0])
        for tp in analise.get("topos_pilares") or []:
            if tp.get("no") in nos_p:
                cs = tp.get("combinacoes") or []
                if not cs:
                    return None
                return {"R_Sd": round(max(c["N"] for c in cs), 2), "H_Sd": round(max(c["V"] for c in cs), 2),
                        "T_Sd": round(max(0.0, max(-c["N"] for c in cs)), 2)}
        return None
    return None


def tipos(doc=None, ids=()) -> List[dict]:
    """Os tipos que se põem no 3D, com os parâmetros da biblioteca (os padrões dela)."""
    from nucleo import acessorios as A
    fora = []
    for tid, info in TIPOS_3D.items():
        if tid in LOCAIS:
            d = dict(LOCAIS[tid], id=tid, verifica=False)
        else:
            d = A.REGISTRO[tid].dict()
        d["pede"] = info["pede"]
        fora.append(d)
    return fora


def assinatura(b) -> list:
    """o que, mudando na barra, pede a ligação refeita: as pontas, o perfil e a rotação (o editor compara igual); na
    chapa (os chumbadores), a origem, o eixo x (× 1000) e a espessura"""
    if getattr(b, "tipo", "") == "chapa":
        return [_r(b.origem, 1), _r(_mul(tuple(b.eixo_x), 1000.0), 1), "%g" % float(b.espessura or 0), 0.0]
    return [_r(b.inicio, 1), _r(b.fim, 1), str(b.perfil), round(float(b.rotacao or 0.0), 3)]


def _id_ligacao():
    import uuid
    return "L" + uuid.uuid4().hex[:10]


def _copia_de_trabalho(doc, ids):
    """A cópia em que a ligação trabalha: o dicionário das peças copiado, mas só as peças que a ligação altera (as
    escolhidas) copiadas a fundo — copiar o modelo inteiro (Documento.de_dict(doc.dict())) levava 3,6 s no Posto CB,
    17 mil peças, a cada ligação e a cada refazer."""
    from nucleo3d.modelo import Documento
    t = Documento(nome=doc.nome, unidade=doc.unidade, projeto=doc.projeto, metadados=copy.deepcopy(doc.metadados))
    t.camadas, t.materiais = copy.deepcopy(doc.camadas), copy.deepcopy(doc.materiais)     # poucas; o add cria camada
    t.entidades = dict(doc.entidades)
    t._copiadas = set()
    _copiar_em(t, ids)
    return t


def _copiar_em(trabalho, ids):
    """as peças `ids` da cópia de trabalho passam a ser cópias de verdade (antes de a ligação mexer nelas)"""
    feitas = getattr(trabalho, "_copiadas", None)
    if feitas is None:
        return                                           # documento de trabalho já copiado inteiro
    for i in ids or ():
        if i in trabalho.entidades and i not in feitas:
            trabalho.entidades[i] = copy.deepcopy(trabalho.entidades[i])
            feitas.add(i)


def aplicar(doc, tipo: str, ids: Sequence[str], parametros: Optional[dict] = None, ligacao: Optional[str] = None,
            esforcos: Optional[dict] = None, analise: Optional[dict] = None) -> dict:
    """A ligação `tipo` nas barras `ids` (uma ligação por pilar, nas bases), ou `ligacao` (o id de uma aplicada) refeita
    com os parâmetros novos. Devolve {"novas": [entidades], "alterar": {id: {campo: valor}}, "remover": [ids],
    "ligacoes": [{id, tipo, verificacao, avisos}]}."""
    from nucleo3d.modelo import Documento
    from nucleo3d import producao
    from nucleo import acessorios as A
    if tipo not in TIPOS_3D:
        raise ErroDeDados("ligação desconhecida para o 3D: %s" % tipo)
    trabalho = _copia_de_trabalho(doc, ids)                # o recebido não muda
    remover: List[str] = []
    restaurar: Dict[str, dict] = {}
    base_parametros = dict(parametros or {})
    if ligacao:
        velhas = [e for e in trabalho.entidades.values() if ((e.atributos or {}).get("ligacao") or {}).get("id") == ligacao]
        if not velhas:
            raise ErroDeDados("a ligação %s não está mais no modelo" % ligacao)
        reg = velhas[0].atributos["ligacao"]
        ids = list(reg.get("pecas") or [])
        _copiar_em(trabalho, ids)
        base_parametros = dict(reg.get("parametros") or {}, **(parametros or {}))
        _limpar_soldas(trabalho, velhas, ids)
        for e in velhas:
            remover.append(e.id)
            del trabalho.entidades[e.id]
        # as barras voltam como eram antes da ligação
        for bid, campos in (reg.get("ajustes") or {}).items():
            b = trabalho.entidades.get(bid)
            if b is None:
                continue
            for k, v in campos.items():
                setattr(b, k, copy.deepcopy(v))
            restaurar.setdefault(bid, {}).update(copy.deepcopy(campos))
    grupos = _barras_para(trabalho, tipo, ids)
    novas, alterar, resultados = [], {}, []
    soldas_pendentes = []
    for barras in grupos:
        lid = ligacao if (ligacao and len(grupos) == 1) else _id_ligacao()
        p = {k: v for k, v in base_parametros.items() if v not in (None, "")}
        g = _gerar(tipo, barras, p)
        for bid, campos in g["alterar"].items():
            b = trabalho.entidades[bid]
            for k, v in campos.items():
                setattr(b, k, copy.deepcopy(v))
            alterar.setdefault(bid, {}).update(copy.deepcopy(campos))
        # a geometria das barras DEPOIS da ligação (o tirante esticado até a castanha): é a que o editor compara
        reg = {"id": lid, "tipo": tipo, "parametros": g["parametros"], "pecas": [b.id for b in barras],
               "ajustes": g["ajustes"], "geometria": {b.id: assinatura(b) for b in barras}}
        for e in g["pecas"]:
            e.atributos = dict(e.atributos or {}, ligacao=dict(reg, papel=e.nome))
            trabalho.add(e)
            novas.append(e)
        # o conjunto: a chapa soldada entra no conjunto da barra
        for barra, chapas in g["conjuntos"]:
            mb = dict((barra.atributos or {}).get("marcas") or {})
            inst = mb.get("instancia")
            if not inst and not mb.get("conjunto"):
                inst = "c" + lid[1:]
                mb.update(instancia=inst, conjunto="")
                mb.setdefault("principal", True)
                barra.atributos = dict(barra.atributos or {}, marcas=mb)
                alterar.setdefault(barra.id, {})["atributos"] = barra.atributos
            for ch in chapas:
                mc = dict((ch.atributos or {}).get("marcas") or {})
                if inst:
                    mc.update(instancia=inst, conjunto="")
                else:
                    mc["conjunto"] = mb.get("conjunto")
                mc.pop("principal", None)
                ch.atributos = dict(ch.atributos or {}, marcas=mc)
                if ch.id in trabalho.entidades and not any(n_ is ch for n_ in g["pecas"]):
                    alterar.setdefault(ch.id, {})["atributos"] = ch.atributos     # a barra que já existia (a outra do par)
        soldas_pendentes += g["soldas"]
        soldas_pendentes += [(x.id, y, d) for x, y, d in g.get("soldas_entre", [])]
        verif = None
        try:
            if tipo in LOCAIS:
                raise LookupError("sem verificação na biblioteca")
            parametros_lib = {k: v for k, v in g["parametros"].items() if k in {x.chave for x in A.REGISTRO[tipo].parametros}}
            da_analise = esforcos_da_analise(analise, tipo, barras) if not esforcos else None
            origem = "informados" if esforcos else ("análise do projeto" if da_analise else "padrão da biblioteca")
            r = A.montar(tipo, parametros_lib, esforcos or da_analise or {})
            verif = r.get("verificacao")
            usados = r.get("esforcos")
        except Exception as exc:                          # noqa: BLE001 — a verificação não impede a ligação
            verif, usados, origem = {"erro": str(exc)}, None, "—"
        resultados.append({"id": lid, "tipo": tipo, "barras": [b.id for b in barras], "verificacao": verif,
                           "esforcos": usados, "origem_esforcos": origem,
                           "avisos": g["avisos"], "parametros": g["parametros"]})
    # marcas: o numerar no documento de trabalho (as peças novas, as barras que entraram em conjunto)
    r = producao.numerar(trabalho)
    da_ligacao = {e.id for e in novas} | {b for g_ in grupos for b in (x.id for x in g_)}
    for i, patch in r["mudancas"].items():
        if i not in da_ligacao:
            continue                                      # o resto do modelo não é numerado por tabela
        e = trabalho.entidades[i]
        a = dict(e.atributos or {})
        for k, v in patch.items():
            if v is None:
                a.pop(k, None)
            else:
                a[k] = v
        e.atributos = a
        if not any(n.id == i for n in novas):
            alterar.setdefault(i, {})["atributos"] = a
    # as soldas definidas (pela posição da outra peça, nas duas peças)
    for bid, chapa, d in soldas_pendentes:
        b = trabalho.entidades[bid]
        pb = ((b.atributos or {}).get("marcas") or {}).get("posicao")
        pc = ((chapa.atributos or {}).get("marcas") or {}).get("posicao")
        if not pb or not pc:
            continue
        dd = producao.normalizar_definicao(d)
        for x, outra in ((b, pc), (chapa, pb)):
            a = dict(x.atributos or {})
            a["soldas"] = dict(a.get("soldas") or {}, **{outra: dd})
            x.atributos = a
            if x is b and not any(n_ is b for n_ in novas):      # a peça nova já sai com os atributos
                alterar.setdefault(b.id, {})["atributos"] = a
    # as barras que voltaram ao de antes e não mudaram de novo (inclusive as soldas tiradas com as peças velhas)
    for bid, campos in restaurar.items():
        for k, v in campos.items():
            alterar.setdefault(bid, {}).setdefault(k, v)
        if "atributos" not in alterar[bid]:
            alterar[bid]["atributos"] = trabalho.entidades[bid].atributos
    return {"novas": [e.dict() for e in novas], "alterar": alterar, "remover": remover, "ligacoes": resultados}


def _limpar_soldas(doc, velhas, ids_barras):
    """Tira das barras da ligação as soldas definidas com as peças que saem (pela posição delas)."""
    posicoes = {((e.atributos or {}).get("marcas") or {}).get("posicao") for e in velhas} - {None, ""}
    if not posicoes:
        return
    for bid in ids_barras:
        b = doc.entidades.get(bid)
        s = (b.atributos or {}).get("soldas") if b is not None else None
        if not s or not (set(s) & posicoes):
            continue
        a = dict(b.atributos)
        a["soldas"] = {k: v for k, v in s.items() if k not in posicoes}
        if not a["soldas"]:
            del a["soldas"]
        b.atributos = a


def remover(doc, ligacao: str) -> dict:
    """Apaga a ligação inteira e devolve as barras como eram: {"remover": [ids], "alterar": {id: campos}}."""
    velhas = [e for e in doc.entidades.values() if ((e.atributos or {}).get("ligacao") or {}).get("id") == ligacao]
    if not velhas:
        raise ErroDeDados("a ligação %s não está mais no modelo" % ligacao)
    reg = velhas[0].atributos["ligacao"]
    ids = [bid for bid in (reg.get("pecas") or []) if bid in doc.entidades]
    _limpar_soldas(doc, velhas, ids)
    alterar = {bid: copy.deepcopy(c) for bid, c in (reg.get("ajustes") or {}).items() if bid in doc.entidades}
    for bid in ids:
        alterar.setdefault(bid, {})["atributos"] = doc.entidades[bid].atributos
    return {"remover": [e.id for e in velhas], "alterar": alterar}
