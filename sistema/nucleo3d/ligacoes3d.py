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
    "chapa_simples": {"pede": "a viga apoiada e o pilar ou a viga em que ela chega", "barras": ("viga", "apoio")},
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


def _parafuso(centro, eixo, d, pega, classe, comprimento=None):
    from nucleo3d.lancamento import _parafuso_solido
    from nucleo.acessorios import comprimento_parafuso
    s = _parafuso_solido(centro, eixo, d, float(comprimento or comprimento_parafuso(pega, d)), classe)
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
    from nucleo3d.geometria import base_local
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
            # na cantoneira de abas iguais duas rotações dão a mesma peça; o detalhamento chama de "mesa" a aba do eixo v
            # da seção: sempre a mesma (o v para d2), senão a castanha do outro lado da viga, igual, saía com outra marca
            # (o furo na "mesa" numa, na "alma" na outra — 23/10)
            nota = _dot(base_local(a, rot)[1], d2)
            if melhor is None or nota > melhor[3] + 1e-6:
                melhor = (rot, x0, y0, nota)
    if melhor is not None:
        melhor = melhor[:3]
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


# ------------------------------------------------------------------ chapa simples (uma chapa na alma)

def _acima5(n):
    return math.ceil(n / 5.0 - 1e-9) * 5.0


def _chapa_simples(viga, apoio, p):
    """Uma chapa só, soldada dos dois lados na face do apoio (a alma da viga principal, a mesa ou a alma do pilar), com
    a alma da viga apoiada parafusada nela — o detalhe do projetista no heliponto v2 (23/10): chapa 8 × 90, 5 M16 a 45
    da face, borda 29 em cima e embaixo, o passo pela altura da chapa. A viga fica 10 mm antes da face; na viga apoiada
    em viga, a mesa que bate na mesa da principal sai recortada (cope, 10 mm de folga). A viga que chega inclinada em
    planta leva a chapa no plano da alma dela, soldada em ângulo na face (a V14 na V2 do heliponto)."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    from nucleo2d.detalhe.soldas import _perna
    pv = _perfil(viga.perfil)
    eixo_a = _norm(_sub(apoio.fim, apoio.inicio))
    ponta, no, outro = _ponta_perto(viga, apoio.inicio, eixo_a)
    dirv = _norm(_sub(outro, no))                          # da face para dentro da viga
    nf, F, parede, face = _face_do_apoio(apoio, no, dirv)
    cosf = _dot(dirv, nf)
    if cosf < 0.3:
        raise ErroDeDados("a viga chega muito inclinada na face do apoio")
    folga = float(p.get("folga") or 10.0)
    t = float(p.get("espessura") or 8.0)
    B = float(p.get("largura") or 90.0)
    gauge = float(p.get("gauge") or B / 2.0)              # o furo a partir da face
    n = int(p.get("n_parafusos") or 5)
    borda = float(p.get("borda") or 29.0)
    nome_par = str(p.get("parafuso") or "M16")
    classe = str(p.get("classe") or "ASTM A325")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    dv, tfv, twv, bfv = float(pv.d or 300), float(pv.tf or 10), float(pv.tw or 6), float(pv.bf or 150)
    _, vv, _ = _triedro(viga)                              # a altura da seção
    X = _add(no, _mul(dirv, _dot(_sub(F, no), nf) / cosf))   # o eixo da viga na face
    # recortes (cope): só na viga apoiada em viga, onde a mesa dela bate na mesa da principal
    recortes, cope = [], {"cima": 0.0, "baixo": 0.0}
    if abs(eixo_a[2]) < 0.7:
        pa = _perfil(apoio.perfil)
        da, tfa, twa, bfa = float(pa.d or 300), float(pa.tf or 10), float(pa.tw or 6), float(pa.bf or 150)
        qa = _add(apoio.inicio, _mul(eixo_a, _dot(_sub(X, apoio.inicio), eixo_a)))
        ha = _dot(_sub(qa, X), vv)                          # o eixo da principal na altura da apoiada
        sen = math.sqrt(max(0.0, 1.0 - cosf * cosf))
        comp = _acima5((_dot(_sub(F, no), nf) + bfa / 2.0 - twa / 2.0 + folga + bfv / 2.0 * sen) / cosf)
        if dv / 2.0 > ha + da / 2.0 - tfa - 0.5:
            cope["cima"] = _acima5(dv / 2.0 - (ha + da / 2.0 - tfa) + folga)
        if -dv / 2.0 < ha - da / 2.0 + tfa + 0.5:
            cope["baixo"] = _acima5((ha - da / 2.0 + tfa) + dv / 2.0 + folga)
        recortes = [{"ponta": ponta, "lado": lado, "comprimento": comp, "altura": h} for lado, h in cope.items() if h > 0]
    # a chapa: entre as mesas (ou os recortes), 10 mm de folga, de 10 em 10
    topo = dv / 2.0 - (cope["cima"] or tfv)
    pe = -dv / 2.0 + (cope["baixo"] or tfv)
    H = float(p.get("altura") or math.floor((topo - pe - 10.0) / 10.0) * 10.0)
    if H < 2 * borda + 30:
        raise ErroDeDados("a alma da viga %s não cabe uma chapa de ligação" % viga.perfil)
    pas = float(p.get("passo") or ((H - 2 * borda) / (n - 1) if n > 1 else 0.0))
    meio = (topo + pe) / 2.0
    nn = _norm(_cruz(dirv, vv))                            # a chapa fica deste lado da alma
    Xc = _add(_add(X, _mul(nn, twv / 2.0 + t / 2.0)), _mul(vv, meio))
    Xc = _sub(Xc, _mul(dirv, _dot(_sub(Xc, F), nf) / cosf))      # o meio da espessura encostado na face
    origem = _add(_sub(Xc, _mul(nn, t / 2.0)), _mul(vv, -H / 2.0))
    alturas = [H / 2.0 + (i - (n - 1) / 2.0) * pas for i in range(n)]
    chapa = _chapa("Chapa de ligação", origem, dirv, vv, B, H, t, [(gauge, h, fd) for h in alturas],
                   aco=str(p.get("aco") or "ASTM A36"))
    pars = [_parafuso(_add(_add(_add(Xc, _mul(dirv, gauge)), _mul(vv, h - H / 2.0)), _mul(nn, -twv / 2.0)), nn, d,
                      t + twv, classe, p.get("comprimento_parafuso")) for h in alturas]
    chave = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    antigos = [r for r in (getattr(viga, "recortes", None) or []) if r.get("ponta") != ponta]
    ajustes = {viga.id: {chave: copy.deepcopy(getattr(viga, chave) or []), rec: float(getattr(viga, rec) or 0.0),
                         "recortes": copy.deepcopy(getattr(viga, "recortes", None) or [])}}
    alterar = {viga.id: {chave: [{"normal": _r(nf, 6), "ponto": _r(_sub(_add(F, _mul(nf, folga)), no), 3)}], rec: 0.0,
                         "recortes": antigos + recortes}}
    soldas = [(apoio.id, chapa, {"tipo": "filete", "perna": _perna(parede, t), "lados": 2, "local": "fabrica"})]
    params = dict(p, viga=viga.perfil, espessura=t, largura=B, altura=H, n_parafusos=n, passo=round(pas, 1), borda=borda,
                  parafuso=nome_par, classe=classe, folga=folga, recorte_cima=cope["cima"], recorte_baixo=cope["baixo"])
    avisos = [] if cosf > 0.99 else ["viga inclinada em planta: a chapa vai soldada em ângulo na face do apoio"]
    return {"pecas": [chapa] + pars, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(apoio, [chapa])],
            "soldas": soldas, "parametros": params, "avisos": avisos}


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
    "chapa_simples": {
        "nome": "Ligação flexível com chapa simples", "categoria": "tesoura",
        "descricao": "Uma chapa soldada dos dois lados na face do apoio (alma da viga principal, mesa ou alma do pilar) e "
                     "a alma da viga parafusada nela; a viga 10 mm antes da face, recortada onde a mesa bate na principal.",
        "parametros": [{"chave": "espessura", "rotulo": "Espessura da chapa", "unidade": "mm", "padrao": 8},
                       {"chave": "largura", "rotulo": "Largura da chapa", "unidade": "mm", "padrao": 90},
                       {"chave": "altura", "rotulo": "Altura da chapa (vazio = a alma livre − 10)", "unidade": "mm", "padrao": ""},
                       {"chave": "n_parafusos", "rotulo": "Parafusos", "unidade": "", "padrao": 5},
                       {"chave": "borda", "rotulo": "Borda em cima e embaixo", "unidade": "mm", "padrao": 29},
                       {"chave": "parafuso", "rotulo": "Diâmetro", "unidade": "", "padrao": "M16"},
                       {"chave": "classe", "rotulo": "Classe", "unidade": "", "padrao": "ASTM A325"},
                       {"chave": "comprimento_parafuso", "rotulo": "Comprimento do parafuso (vazio = pela pega)",
                        "unidade": "mm", "padrao": ""}],
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


# ------------------------------------------------------------------ contravento × viga: as variantes por nó
#
# Pedido do usuário (23/10, o detalhamento de um terceiro): o projeto marca onde o X de contravento chega na viga mas não
# diz a ligação; "quero só clicar e mudar o tipo (castanha, duas chapas iguais à Sooro, cantoneira cortada…)". Cada
# variante é uma ligação POR NÓ: a viga e o(s) tirante(s) que chegam no mesmo ponto dela (o V do print, dois tirantes
# no mesmo ponto). Com dois, as pontas se afastam `separa` ao longo da viga, uma para o lado de onde cada tirante vem.
# Só a ponta do nó muda (o campo `inicio` ou `fim`): a outra ponta do tirante tem a ligação dela.

Z_ = (0.0, 0.0, 1.0)


def _ponta_no_apoio(tir, ap, limite=600.0):
    """a ponta do tirante que chega no eixo do apoio (em planta, até `limite`): {ponta, E, Q, w (o apoio), dist}"""
    wa = _norm(_sub(ap.fim, ap.inicio))
    wh = (wa[0], wa[1], 0.0)
    if math.sqrt(_dot(wh, wh)) < 1e-6:
        return None
    wh = _norm(wh)
    melhor = None
    for ponta, E, Q in (("inicio", tir.inicio, tir.fim), ("fim", tir.fim, tir.inicio)):
        r = _sub(E, ap.inicio)
        r = (r[0], r[1], 0.0)
        d = math.sqrt(max(0.0, _dot(r, r) - _dot(r, wh) ** 2))
        if d <= limite and (melhor is None or d < melhor["dist"]):
            melhor = {"ponta": ponta, "E": tuple(E), "Q": tuple(Q), "wa": wa, "wh": wh, "dist": d}
    return melhor


def _tirantes_do_no(tirantes, ap, p, separa_padrao=150.0):
    """as pontas no nó, cada uma com o ponto de chegada já afastado (`separa`, quando são dois) e o referencial dela:
    dh (em planta, de fora para o nó), lado (⟂ em planta), n (⟂ ao apoio, do lado do tirante para o eixo), o ponto no
    eixo do apoio, as faces de cima e de baixo dele ali"""
    pontas = []
    for t in tirantes:
        info = _ponta_no_apoio(t, ap)
        if info is None:
            raise ErroDeDados("o tirante %s não chega na viga %s (até 600 mm em planta)" % (t.nome or t.id, ap.nome or ap.id))
        info["tirante"] = t
        pontas.append(info)
    separa = float(p.get("separa") or separa_padrao) if len(pontas) > 1 else 0.0
    nb, _ = _eixo_secao_mais_perto(ap, Z_)
    lo_b, hi_b = _extremos(ap, nb)
    for info in pontas:
        wa, wh, E, Q = info["wa"], info["wh"], info["E"], info["Q"]
        de_fora = _norm((E[0] - Q[0], E[1] - Q[1], 0.0))
        lado_vem = -1.0 if _dot(de_fora, wh) > 0 else 1.0       # o tirante vem deste lado (ao longo da viga)
        P = _add(ap.inicio, _mul(wa, _dot(_sub(E, ap.inicio), wa)))   # a ponta levada ao eixo do apoio
        P = _add(P, _mul(wa, lado_vem * separa / 2.0))
        dh = _norm((P[0] - Q[0], P[1] - Q[1], 0.0))
        n = _sub(dh, _mul(wh, _dot(dh, wh)))
        if math.sqrt(_dot(n, n)) < 0.15:
            raise ErroDeDados("o tirante %s corre junto da viga: não chega nela" % (info["tirante"].nome or info["tirante"].id))
        n = _norm(n)
        z_cima = _add(P, _mul(nb, hi_b - _dot(P, nb)))[2]
        z_baixo = _add(P, _mul(nb, lo_b - _dot(P, nb)))[2]
        info.update(P=P, dh=dh, n=n, lado=_norm(_cruz(Z_, dh)), z_cima=z_cima, z_baixo=z_baixo,
                    borda=_extremos(ap, n)[0])            # a borda da mesa do lado de onde o tirante vem
    return pontas


def _face(info, p):
    """'cima' ou 'baixo': a pedida, ou a face da viga mais perto da altura em que o tirante chega"""
    f = str(p.get("face") or "").lower()
    if f in ("cima", "baixo"):
        return f
    return "cima" if abs(info["E"][2] - info["z_cima"]) <= abs(info["E"][2] - info["z_baixo"]) else "baixo"


def _ponta_alterada(info, ponto):
    t = info["tirante"]
    return ({t.id: {info["ponta"]: tuple(round(float(c), 2) for c in ponto)}},
            {t.id: {info["ponta"]: tuple(getattr(t, info["ponta"]))}})


def _juntar(dst, src):
    for bid, campos in src.items():
        dst.setdefault(bid, {}).update(campos)


def _castanha_contravento(barras, p):
    """A castanha (a CA1 do Hangar, folha CASTANHAS DOS CONTRAVENTOS): a cantoneira deitada na mesa da viga, ao longo do
    tirante, presa por um parafuso na mesa a 30 mm da borda; na ponta de fora dela a cantoneira pequena em pé, furada —
    o tirante passa nela a 25 mm da mesa e sobra `passa` para as porcas. Na mesa de cima a aba sobe; na de baixo, desce."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    from nucleo3d.de_planta_estrutura import _furo_marcador
    *tirantes, ap = barras
    pa = _perfil(ap.perfil)
    tf = float(pa.tf or pa.tw or 8.0)
    perfil = str(p.get("cantoneira") or "L 50X50X4.75")
    Lc = float(p.get("comprimento") or 150.0)
    perfil_a = str(p.get("aba") or perfil)
    La = float(p.get("comprimento_aba") or 50.0)
    nome_par = str(p.get("parafuso") or '1/2"')
    d = d_parafuso_mm(nome_par)
    fd = float(p.get("furo") or furo_mm(nome_par))         # sem cota: d + 1,5 (FAB-02; o Ø14 do Hangar era cotado)
    classe = str(p.get("classe") or "ASTM A307")
    borda = float(p.get("borda") or 30.0)
    h_furo = float(p.get("altura_furo") or 25.0)
    passa = float(p.get("passa") or 40.0)
    pl = _perfil(perfil)
    tL, aba_L = float(pl.tw or pl.tf or 4.76), float(pl.bf or 50.8)
    pecas, alterar, ajustes, conjuntos, soldas_entre, soldas = [], {}, {}, [], [], []
    faces = []
    for info in _tirantes_do_no(tirantes, ap, p, 250.0):
        face = _face(info, p)
        faces.append(face)
        sz = 1.0 if face == "cima" else -1.0
        zf = info["z_cima"] if face == "cima" else info["z_baixo"]
        dh, lado, n, P = info["dh"], info["lado"], info["n"], info["P"]
        Ph = (P[0], P[1], zf)
        # o parafuso na linha do tirante, a `borda` da borda da mesa do lado dele
        alvo = info["borda"] + borda
        Bp = _add(Ph, _mul(dh, (alvo - _dot(Ph, n)) / _dot(dh, n)))
        Bp = (Bp[0], Bp[1], zf)
        S0 = _add(Bp, _mul(dh, 25.0))
        S1 = _sub(S0, _mul(dh, Lc))
        M = _mul(_add(S0, S1), 0.5)
        cast = _cantoneira_no_canto(perfil, _mul(dh, -1.0), _sub(M, _mul(lado, aba_L / 2.0)), lado, _mul(Z_, sz), Lc)
        cast.nome, cast.papel = "Castanha", "castanha"
        cast.atributos = {"tipo_ifc": "IfcMember", "elemento": "Castanha"}
        aba = _cantoneira_no_canto(perfil_a, lado, S1, _mul(dh, -1.0), _mul(Z_, sz), La)
        aba.nome, aba.papel = "Castanha (aba)", "castanha"
        aba.atributos = {"tipo_ifc": "IfcMember", "elemento": "Castanha (aba)"}
        H = _add(_add(S1, _mul(Z_, sz * h_furo)), _mul(dh, passa))      # a ponta do tirante: passa a aba
        furos = [_furo_marcador(Bp, _mul(Z_, sz), fd, tL + 1.0, cast.id),
                 _furo_marcador(Bp, _mul(Z_, -sz), fd, tf + 1.0, ap.id),
                 _furo_marcador(_add(S1, _mul(Z_, sz * h_furo)), _mul(dh, -1.0), fd, tL + 1.0, aba.id)]
        par = _parafuso(_add(Bp, _mul(Z_, sz * (tL - tf) / 2.0)), _mul(Z_, sz), d, tL + tf, classe)
        pecas += [cast, aba, par] + furos
        conjuntos.append((cast, [aba]))
        soldas_entre.append((cast, aba, {"tipo": "filete", "perna": 4.0, "lados": 1, "local": "fabrica", "forma": "contorno"}))
        a, b = _ponta_alterada(info, H)
        _juntar(alterar, a)
        _juntar(ajustes, b)
    params = dict(p, cantoneira=perfil, comprimento=Lc, aba=perfil_a, comprimento_aba=La, parafuso=nome_par, furo=fd,
                  classe=classe, borda=borda, altura_furo=h_furo, passa=passa, face="/".join(sorted(set(faces))))
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": conjuntos, "soldas": soldas,
            "soldas_entre": soldas_entre, "parametros": params, "avisos": []}


def _duas_chapas_contravento(barras, p):
    """As duas chapas da Sooro (o CV da ME-Sooro no IFC: L 2½"×¼", chapas 80×80×8, barra roscada 5/8"): a chapa deitada
    soldada na mesa da viga (uma só para o nó, 270 × 120 com dois tirantes); em cada tirante, um toco de cantoneira
    parafusado nela e outro soldado no tirante, cada um com uma chapa 80×80 na ponta, e a barra roscada entre as duas
    chapas — as porcas esticam o X. Medidas ao longo do tirante, do nó para fora."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm, DIAMETROS_BARRA
    from nucleo3d.modelo import Barra
    from nucleo3d import geometria as geo
    *tirantes, ap = barras
    perfil = str(p.get("cantoneira") or "L 2 1/2'' X 1/4''")
    Lt = float(p.get("comprimento_toco") or 150.0)
    B80, t80 = float(p.get("chapa") or 80.0), float(p.get("chapa_t") or 8.0)
    vao = float(p.get("vao") or 100.0)                      # entre as duas chapas 80×80 (as porcas)
    tb, Bb = float(p.get("base_t") or 6.35), float(p.get("base_largura") or 120.0)
    rosca = str(p.get("rosca") or '5/8"')
    dr = DIAMETROS_BARRA[rosca]
    sobra = float(p.get("sobra_rosca") or 40.0)
    nome_par = str(p.get("parafuso") or "M16")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A307")
    pl = _perfil(perfil)
    tL, abaL = float(pl.tw or pl.tf or 6.35), float(pl.bf or 63.5)
    pontas = _tirantes_do_no(tirantes, ap, p, 200.0)
    face = _face(pontas[0], p)
    sz = 1.0 if face == "cima" else -1.0
    zf = pontas[0]["z_cima"] if face == "cima" else pontas[0]["z_baixo"]
    z0 = zf + sz * tb                                      # a face da chapa deitada, onde os tocos deitam
    pecas, alterar, ajustes, conjuntos, soldas_entre, soldas_tirante = [], {}, {}, [], [], []
    furos_base, tocos_parafusados = [], []
    perfil_r = "FE RED %s" % rosca.replace('"', "''")
    geo.registrar_perfil(geo.barra_redonda(dr, perfil_r))
    for info in pontas:
        dh, lado, P = info["dh"], info["lado"], info["P"]
        t = info["tirante"]
        r_t = float(_perfil(t.perfil).d or 12.7) / 2.0
        fora = _mul(dh, -1.0)
        Ph = (P[0], P[1], z0)
        zr = sz * B80 / 2.0                                 # o eixo da barra roscada: no meio da chapa 80×80
        def em(s, lat=0.0, z=0.0):
            return _add(_add(_add(Ph, _mul(fora, s)), _mul(lado, lat)), _mul(Z_, z))
        # toco 1 (o da viga): de s = -25 a Lt-25, a aba em pé encostada na barra roscada (a mais grossa)
        heel = -(tL + max(r_t, dr / 2.0) + 0.5)
        s1a, s1b = -25.0, Lt - 25.0
        toco1 = _cantoneira_no_canto(perfil, fora, em((s1a + s1b) / 2.0, heel), lado, _mul(Z_, sz), Lt)
        toco1.nome, toco1.papel = "Toco da castanha", "castanha"
        toco1.atributos = {"tipo_ifc": "IfcMember", "elemento": "Castanha"}
        s_par = 10.0
        lat_par = heel + abaL / 2.0
        Bp = em(s_par, lat_par)
        par = _parafuso(_add(Bp, _mul(Z_, sz * (tL - tb) / 2.0)), _mul(Z_, sz), d, tL + tb, classe)
        furos_base.append(Bp)
        # as duas chapas 80×80 e o toco 2 (o do tirante)
        ex = lado
        ey = _mul(Z_, sz)
        ch1 = _chapa("Chapa 80×80", _add(em(s1b, -B80 / 2.0), (0.0, 0.0, 0.0)), ex, ey, B80, B80, t80,
                     [(B80 / 2.0, B80 / 2.0, round(dr + 1.5, 1))])
        # a chapa cresce para fora (eixo x × eixo y = −fora quando sz=1): a origem na face de dentro dela
        nrm = _cruz(ex, ey)
        if _dot(nrm, fora) < 0:
            ch1.origem = tuple(_add(ch1.origem, _mul(fora, t80)))
        s2 = s1b + t80 + vao
        ch2 = _chapa("Chapa 80×80", em(s2, -B80 / 2.0), ex, ey, B80, B80, t80, [(B80 / 2.0, B80 / 2.0, round(dr + 1.5, 1))])
        if _dot(nrm, fora) < 0:
            ch2.origem = tuple(_add(ch2.origem, _mul(fora, t80)))
        s2b = s2 + t80
        toco2 = _cantoneira_no_canto(perfil, fora, em(s2b + Lt / 2.0, heel), lado, _mul(Z_, sz), Lt)
        toco2.nome, toco2.papel = "Toco do tirante", "castanha"
        toco2.atributos = {"tipo_ifc": "IfcMember", "elemento": "Castanha"}
        barra_r = Barra(nome="Barra roscada", inicio=em(s1b - sobra, 0.0, zr), fim=em(s2b + sobra, 0.0, zr), perfil=perfil_r,
                        papel="barra_roscada", camada="Chapas", material="Aço",
                        atributos={"tipo_ifc": "IfcMember", "elemento": "Barra roscada"})
        # o tirante: encostado na aba em pé do toco 2, até depois da sobra da barra roscada
        H = em(s2b + sobra + 5.0, 0.0, zr)
        pecas += [toco1, par, ch1, ch2, toco2, barra_r]
        # o toco 2 e a chapa dele soldados no tirante, na fábrica: saem no conjunto do tirante
        conjuntos += [(toco1, [ch1]), (t, [toco2, ch2])]
        for x, y in ((toco1, ch1), (toco2, ch2)):
            soldas_entre.append((x, y, {"tipo": "filete", "perna": 5.0, "lados": 1, "local": "fabrica", "forma": "contorno"}))
        soldas_tirante.append((t.id, toco2, {"tipo": "filete", "perna": 5.0, "lados": 2, "local": "fabrica", "forma": "sobreposição"}))
        tocos_parafusados.append(toco1)
        a, b = _ponta_alterada(info, H)
        _juntar(alterar, a)
        _juntar(ajustes, b)
    # a chapa deitada: no eixo da viga, do primeiro ao último parafuso + a borda (mín. 150)
    wa = pontas[0]["wa"]
    c_ = _mul(_add(furos_base[0], furos_base[-1]), 0.5)
    q = _add(ap.inicio, _mul(wa, _dot(_sub(c_, ap.inicio), wa)))
    q = (q[0], q[1], zf)
    us = [_dot(_sub(f, q), wa) for f in furos_base]
    # borda de 25 (≥ 22 do furo de M16): a chapa de 270 da Sooro com os dois tocos afastados 200
    Lb = max(float(p.get("base_comprimento") or 0.0), 150.0, _acima(max(us) - min(us) + 2 * 25.0))
    if len(pontas) > 1:
        Lb = max(Lb, 270.0)
    eyb = _norm(_cruz(Z_, wa))
    exb = wa if _dot(_cruz(wa, eyb), Z_) * sz > 0 else _mul(wa, -1.0)
    ob = _add(_add(q, _mul(exb, -Lb / 2.0)), _mul(eyb, -Bb / 2.0))
    if sz < 0:
        ob = _sub(ob, _mul(Z_, tb))
    furos_loc = []
    for f in furos_base:
        r = _sub(f, ob)
        furos_loc.append((_dot(r, exb), _dot(r, eyb), fd))
    base = _chapa("Chapa da castanha", ob, exb, eyb, Lb, Bb, tb, furos_loc)
    from nucleo2d.detalhe.soldas import _perna
    pecas.insert(0, base)
    params = dict(p, cantoneira=perfil, comprimento_toco=Lt, chapa=B80, chapa_t=t80, vao=vao, base_t=tb,
                  base_largura=Bb, base_comprimento=Lb, rosca=rosca, sobra_rosca=sobra, parafuso=nome_par, classe=classe,
                  face=face)
    soldas = [(ap.id, base, {"tipo": "filete", "perna": _perna(float(_perfil(ap.perfil).tf or 8.0), tb), "lados": 1,
                             "local": "fabrica", "forma": "contorno"})] + soldas_tirante
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(ap, [base])] + conjuntos,
            "soldas": soldas, "soldas_entre": soldas_entre, "parametros": params, "avisos": []}


def _cantoneira_contravento(barras, p):
    """A cantoneira cortada em pé (a SC1 da portaria, banco de detalhes) no nó: a mesma colocação do
    `_suporte_contravento`, uma por tirante, as pontas afastadas `separa` quando são dois."""
    from nucleo3d.modelo import Barra
    *tirantes, ap = barras
    pecas, alterar, ajustes, conjuntos, soldas = [], {}, {}, [], []
    params = dict(p)
    for info in _tirantes_do_no(tirantes, ap, p):
        t = info["tirante"]
        # o tirante com a ponta já no ponto afastado (na altura dela): o SC1 acha a colocação a partir daí
        alvo = (info["P"][0], info["P"][1], info["E"][2])
        tmp = Barra(id=t.id, nome=t.nome, inicio=t.inicio, fim=t.fim, perfil=t.perfil, papel=t.papel)
        setattr(tmp, info["ponta"], alvo)
        g = _suporte_contravento(tmp, [ap], p)
        pecas += g["pecas"]
        conjuntos += g["conjuntos"]
        soldas += g["soldas"]
        params.update(g["parametros"])
        novo = g["alterar"][t.id][info["ponta"]]
        a, b = _ponta_alterada(info, novo)
        _juntar(alterar, a)
        _juntar(ajustes, b)
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": conjuntos, "soldas": soldas,
            "parametros": params, "avisos": []}


def _chapa_de_no_contravento(barras, p, esticador=False):
    """A chapa de nó (a "Windbrace connection" da Tekla, para 1 a 3 tirantes no mesmo ponto): chapa deitada soldada na
    mesa da viga, saindo para o lado dos tirantes; cada tirante com uma lingueta (chapa) soldada na ponta, parafusada na
    chapa de nó. Com `esticador`, entre a ponta do tirante e a lingueta vai um esticador (tensor comercial) e um toco de
    barra roscada soldado na lingueta."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm, DIAMETROS_BARRA
    from nucleo3d.modelo import Barra
    from nucleo3d import geometria as geo
    from nucleo2d.detalhe.soldas import _perna
    *tirantes, ap = barras
    tg = float(p.get("t") or 8.0)
    tl, Bl, Ll = float(p.get("lingueta_t") or 8.0), float(p.get("lingueta_largura") or 60.0), float(p.get("lingueta_comprimento") or 110.0)
    fora_mesa = float(p.get("fora_da_mesa") or 45.0)          # o parafuso além da borda da mesa
    borda = float(p.get("borda") or 35.0)
    nome_par = str(p.get("parafuso") or "M16")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A325")
    solda_l = float(p.get("solda_tirante") or 60.0)           # o tirante deitado e soldado na lingueta
    L_est = float(p.get("esticador_comprimento") or 150.0)
    pecas, alterar, ajustes, conjuntos, soldas, soldas_entre = [], {}, {}, [], [], []
    pontas = _tirantes_do_no(tirantes, ap, p, 0.0)
    face = _face(pontas[0], p)
    sz = 1.0 if face == "cima" else -1.0
    zf = pontas[0]["z_cima"] if face == "cima" else pontas[0]["z_baixo"]
    zg = zf + sz * tg                                         # a face da chapa de nó onde as linguetas deitam
    pts_casco, furos_mundo = [], []
    wa = pontas[0]["wa"]
    for info in pontas:
        dh, lado, n, P = info["dh"], info["lado"], info["n"], info["P"]
        t = info["tirante"]
        r_t = float(_perfil(t.perfil).d or 12.7) / 2.0
        fora = _mul(dh, -1.0)
        Ph = (P[0], P[1], zg)
        # o parafuso: na linha do tirante, `fora_mesa` além da borda da mesa (do lado de onde o tirante vem)
        alvo = info["borda"] - fora_mesa
        s_b = max(40.0, (_dot(Ph, n) - alvo) / _dot(dh, n))

        def em(s, lat=0.0, z=0.0, _Ph=Ph, _fora=fora, _lado=lado):
            return _add(_add(_add(_Ph, _mul(_fora, s)), _mul(_lado, lat)), _mul(Z_, z))
        B = em(s_b)
        furos_mundo.append(B)
        # o casco da chapa de nó: a volta do parafuso e o trecho da mesa até o eixo da viga
        for k in range(12):
            ang = 2 * math.pi * k / 12
            pts_casco.append(_add(B, _add(_mul(fora, math.cos(ang) * borda), _mul(lado, math.sin(ang) * borda))))
        # a lingueta: deitada na chapa de nó, ao longo do tirante, o furo a 35 da ponta de dentro
        s0 = s_b - 35.0
        ex, ey = fora, lado
        if _dot(_cruz(ex, ey), Z_) * sz < 0:
            ey = _mul(lado, -1.0)
        o = _add(em(s0, 0.0), _mul(ey, -Bl / 2.0))
        if sz < 0:
            o = _sub(o, _mul(Z_, tl))
        lg = _chapa("Lingueta", o, ex, ey, Ll, Bl, tl, [(35.0, Bl / 2.0, fd)], aco=str(p.get("aco") or "ASTM A36"))
        par = _parafuso(_add(B, _mul(Z_, sz * (tl - tg) / 2.0)), _mul(Z_, sz), d, tl + tg, classe)
        pecas += [lg, par]
        z_t = sz * (tl + r_t)                                 # o eixo do tirante deitado na lingueta
        if esticador:
            # o toco de barra roscada soldado na lingueta, o esticador e a ponta do tirante (roscada) dentro dele
            dr = DIAMETROS_BARRA.get(str(p.get("rosca") or '1/2"'), 12.7)
            nome_r = "FE RED %s" % str(p.get("rosca") or '1/2"').replace('"', "''")
            geo.registrar_perfil(geo.barra_redonda(dr, nome_r))
            s_tc0, s_tc1 = s_b + 20.0, s_b + 20.0 + solda_l + 60.0
            toco = Barra(nome="Ponta roscada", inicio=em(s_tc0, 0.0, z_t), fim=em(s_tc1, 0.0, z_t), perfil=nome_r,
                         papel="barra_roscada", camada="Chapas", material="Aço",
                         atributos={"tipo_ifc": "IfcMember", "elemento": "Barra roscada"})
            # o toco e a ponta do tirante encostam nas faces do corpo (a rosca que entra nele é do item comprado: no
            # modelo, nada atravessa — GER-02)
            corpo = Barra(nome="Esticador", inicio=em(s_tc1, 0.0, z_t), fim=em(s_tc1 + L_est, 0.0, z_t),
                          perfil=nome_r, papel="esticador", camada="Parafusos", material="Aço",
                          atributos={"tipo_ifc": "IfcDiscreteAccessory", "elemento": "Esticador",
                                     "comprado": {"item": "Esticador (tensor) %s" % str(p.get("rosca") or '1/2"'), "qtd": 1}})
            pecas += [toco, corpo]
            conjuntos.append((toco, [lg]))
            soldas_entre.append((toco, lg, {"tipo": "filete", "perna": 4.0, "lados": 2, "local": "fabrica", "forma": "sobreposição"}))
            H = em(s_tc1 + L_est, 0.0, z_t)
        else:
            conjuntos.append((t, [lg]))
            soldas.append((t.id, lg, {"tipo": "filete", "perna": 4.0, "lados": 2, "local": "fabrica", "forma": "sobreposição"}))
            H = em(s_b + 20.0, 0.0, z_t)                      # o tirante começa depois da cabeça do parafuso
        a_, b_ = _ponta_alterada(info, H)
        _juntar(alterar, a_)
        _juntar(ajustes, b_)
    # a chapa de nó: o casco dos parafusos e da faixa da mesa entre eles, no plano da mesa
    q = _add(ap.inicio, _mul(wa, _dot(_sub(_mul(_add(furos_mundo[0], furos_mundo[-1]), 0.5), ap.inicio), wa)))
    ny = pontas[0]["n"]
    us = [_dot(_sub(f, q), wa) for f in furos_mundo]
    for u_ in (min(us) - borda, max(us) + borda):
        pts_casco.append(_add(q, _mul(wa, u_)))
    exg = wa
    eyg = _mul(ny, -1.0)                                      # da viga para o lado dos tirantes
    if _dot(_cruz(exg, eyg), Z_) * sz < 0:
        exg = _mul(wa, -1.0)
    org = (q[0], q[1], zf if sz > 0 else zf - tg)
    loc = [(_dot(_sub(c, org), exg), _dot(_sub(c, org), eyg)) for c in pts_casco]
    casco = _casco2(loc)
    x0, y0 = min(c[0] for c in casco), min(c[1] for c in casco)
    cont = [(round(x - x0, 1), round(y - y0, 1)) for x, y in casco]
    o_g = _add(_add(org, _mul(exg, x0)), _mul(eyg, y0))
    furos = [{"x": round(_dot(_sub(f, org), exg) - x0, 2), "y": round(_dot(_sub(f, org), eyg) - y0, 2), "diametro": round(fd, 2)}
             for f in furos_mundo]
    from nucleo3d.modelo import Chapa
    gus = Chapa(nome="Chapa de nó", origem=tuple(o_g), eixo_x=tuple(exg), eixo_y=tuple(eyg), contorno=cont, espessura=tg,
                centrada=False, furos=furos, camada="Chapas", material="Aço", aco=str(p.get("aco") or "ASTM A36"),
                atributos={"tipo_ifc": "IfcPlate"})
    pecas.insert(0, gus)
    conjuntos.insert(0, (ap, [gus]))
    soldas.append((ap.id, gus, {"tipo": "filete", "perna": _perna(float(_perfil(ap.perfil).tf or 8.0), tg), "lados": 1,
                                "local": "fabrica", "forma": "contorno"}))
    params = dict(p, t=tg, lingueta_t=tl, lingueta_largura=Bl, lingueta_comprimento=Ll, fora_da_mesa=fora_mesa, borda=borda,
                  parafuso=nome_par, classe=classe, face=face)
    if esticador:
        params.update(esticador_comprimento=L_est, rosca=str(p.get("rosca") or '1/2"'))
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": conjuntos, "soldas": soldas,
            "soldas_entre": soldas_entre, "parametros": params, "avisos": []}


LOCAIS["chapa_de_no_contravento"] = {
    "nome": "Contravento: chapa de nó (1 a 3 tirantes)", "categoria": "contraventamento",
    "descricao": "Chapa deitada soldada na mesa da viga, saindo para o lado dos tirantes; cada tirante com uma lingueta "
                 "soldada na ponta, parafusada (M16) na chapa de nó.",
    "parametros": [{"chave": "t", "rotulo": "Chapa de nó: espessura", "unidade": "mm", "padrao": 8},
                   {"chave": "lingueta_comprimento", "rotulo": "Lingueta: comprimento", "unidade": "mm", "padrao": 110},
                   {"chave": "lingueta_largura", "rotulo": "Lingueta: largura", "unidade": "mm", "padrao": 60},
                   {"chave": "lingueta_t", "rotulo": "Lingueta: espessura", "unidade": "mm", "padrao": 8},
                   {"chave": "fora_da_mesa", "rotulo": "Parafuso além da borda da mesa", "unidade": "mm", "padrao": 45},
                   {"chave": "parafuso", "rotulo": "Parafuso", "unidade": "", "padrao": "M16"}],
    "esforcos": [],
}
LOCAIS["esticador_contravento"] = {
    "nome": "Contravento: chapa de nó com esticador", "categoria": "contraventamento",
    "descricao": "A chapa de nó com um esticador (tensor comercial) na ponta do tirante: lingueta parafusada na chapa de "
                 "nó, toco de barra roscada soldado nela, o esticador e a ponta roscada do tirante.",
    "parametros": LOCAIS["chapa_de_no_contravento"]["parametros"] + [
        {"chave": "esticador_comprimento", "rotulo": "Esticador: comprimento do corpo", "unidade": "mm", "padrao": 150},
        {"chave": "rosca", "rotulo": "Rosca", "unidade": "", "padrao": '1/2"'}],
    "esforcos": [],
}


# ------------------------------------------------------------------ agulhamento: a corrente entre as terças
#
# Pedido do usuário (23/10, depois da pesquisa): a família do agulhamento, com variantes que se trocam. A ligação é por
# corrente (a barra de terça a terça): as duas pontas dela, nas almas das terças em que chega.

def _pontas_da_corrente(corr, tercas):
    """cada ponta da corrente com a terça em que ela chega: [(ponta, terça, w (de dentro para a terça), plano da alma
    mais perto (coordenada ao longo de w), espessura da alma)]"""
    w = _norm(_sub(corr.fim, corr.inicio))
    fora = []
    for ponta, E, sinal in (("inicio", corr.inicio, -1.0), ("fim", corr.fim, 1.0)):
        wp = _mul(w, sinal)                                   # para fora da corrente, rumo à terça
        melhor = None
        for t in tercas:
            wt = _norm(_sub(t.fim, t.inicio))
            if abs(_dot(wt, w)) > 0.5:
                continue
            r = _sub(E, t.inicio)
            r = _sub(r, _mul(wt, _dot(r, wt)))
            dist = math.sqrt(_dot(r, r))
            if dist < 400.0 and (melhor is None or dist < melhor[0]):
                melhor = (dist, t)
        if melhor is None:
            raise ErroDeDados("a ponta (%s) da corrente %s não chega numa terça selecionada" % (ponta, corr.nome or corr.id))
        t = melhor[1]
        lado, f = _lado_da_alma(t, wp)
        if lado == 0:
            raise ErroDeDados("a terça %s não tem alma de um lado só (perfil %s)" % (t.nome or t.id, t.perfil))
        tw = float(_perfil(t.perfil).tw or 2.25)
        alma_ext = f                                          # a face de fora da alma (do lado da alma)
        alma_int = f - lado * tw
        fora.append({"ponta": ponta, "E": E, "terca": t, "wp": wp, "lado": lado, "f_ext": alma_ext, "f_int": alma_int, "tw": tw})
    return w, fora


def _agulhamento_roscado(barras, p):
    """A corrente de barra roscada: atravessa a alma das duas terças, com arruela e porca dos dois lados de cada alma
    (`sobra` além da face de fora); o furo na alma no eixo da corrente."""
    from nucleo.acessorios import DIAMETROS_BARRA
    from nucleo3d.de_planta_estrutura import _furo_marcador
    from nucleo3d import geometria as geo
    corr, *tercas = barras
    nome_b = str(p.get("barra") or '3/8"')
    d = DIAMETROS_BARRA[nome_b]
    fd = float(p.get("furo") or round(d + 1.5, 1))
    sobra = float(p.get("sobra") or 30.0)
    perfil = "FE RED %s" % nome_b.replace('"', "''")
    geo.registrar_perfil(geo.barra_redonda(d, perfil))
    w, pontas = _pontas_da_corrente(corr, tercas)
    pecas, novo = [], {}
    for pt in pontas:
        wp, E = pt["wp"], pt["E"]
        faces = [pt["f_ext"], pt["f_int"]]
        proj_E = _dot(E, wp)
        # `f_ext`/`f_int` vêm medidos ao longo de wp (o _lado_da_alma recebe wp): a face mais longe de E é a de fora
        f_fora = max(faces, key=lambda v_: v_ - proj_E)
        f_dentro = min(faces, key=lambda v_: v_ - proj_E)
        ponta_nova = _add(E, _mul(wp, (f_fora - proj_E) + sobra))
        novo[pt["ponta"]] = ponta_nova
        furo_ponto = _add(E, _mul(wp, f_dentro - proj_E - 0.5))
        pecas.append(_furo_marcador(furo_ponto, wp, fd, pt["tw"] + 1.0, pt["terca"].id))
    ajustes = {corr.id: {"inicio": tuple(corr.inicio), "fim": tuple(corr.fim), "perfil": corr.perfil}}
    alterar = {corr.id: {"inicio": tuple(round(c, 2) for c in novo["inicio"]), "fim": tuple(round(c, 2) for c in novo["fim"]),
                         "perfil": perfil}}
    params = dict(p, barra=nome_b, furo=fd, sobra=sobra,
                  porcas="2 porcas + 2 arruelas em cada terça (uma de cada lado da alma)")
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": [], "soldas": [], "parametros": params,
            "avisos": []}


def _agulhamento_cantoneira(barras, p):
    """O agulhamento rígido da Sooro (A.C.): a cantoneira entre as terças com uma chapinha soldada em cada ponta,
    encostada na alma da terça e parafusada nela (2 parafusos, oblongo horizontal na chapinha)."""
    from nucleo.acessorios import d_parafuso_mm, furo_mm
    corr, *tercas = barras
    perfil = str(p.get("cantoneira") or "L1.1/4''X1/8''")
    Bc, Hc, tc = float(p.get("chapa_l") or 130.0), float(p.get("chapa_b") or 50.0), float(p.get("chapa_t") or 3.0)
    gab = float(p.get("gabarito") or 60.0)
    nome_par = str(p.get("parafuso") or "M12")
    d, fd = d_parafuso_mm(nome_par), furo_mm(nome_par)
    classe = str(p.get("classe") or "ASTM A307")
    comp_obl = float(p.get("oblongo") or 25.0)
    pl = _perfil(perfil)
    aba = float(pl.bf or 31.75)
    w, pontas = _pontas_da_corrente(corr, tercas)
    pecas, chapinhas, extremos = [], [], {}
    for pt in pontas:
        wp, E = pt["wp"], pt["E"]
        proj_E = _dot(E, wp)
        faces = [pt["f_ext"], pt["f_int"]]
        f_dentro = min(faces, key=lambda v_: v_ - proj_E)        # a face da alma do lado da corrente
        face = _add(E, _mul(wp, f_dentro - proj_E))
        wt = _norm(_sub(pt["terca"].fim, pt["terca"].inicio))
        ex = wt
        ey = Z_
        # a chapinha encostada na alma, do lado da corrente: cresce para dentro (−wp)
        if _dot(_cruz(ex, ey), _mul(wp, -1.0)) < 0:
            ex = _mul(wt, -1.0)
        o = _add(_add(face, _mul(ex, -Bc / 2.0)), _mul(ey, -Hc / 2.0))
        furos = [{"x": round(Bc / 2.0 + sx * gab / 2.0, 2), "y": round(Hc / 2.0, 2), "largura": comp_obl, "altura": fd}
                 for sx in (-1, 1)]
        from nucleo3d.modelo import Chapa
        ch = Chapa(nome="Chapinha do agulhamento", origem=tuple(o), eixo_x=tuple(ex), eixo_y=tuple(ey),
                   contorno=[(0.0, 0.0), (Bc, 0.0), (Bc, Hc), (0.0, Hc)], espessura=tc, centrada=False, furos=furos,
                   camada="Chapas", material="Aço", aco=str(p.get("aco") or "ASTM A36"), atributos={"tipo_ifc": "IfcPlate"})
        chapinhas.append(ch)
        pecas.append(ch)
        for sx in (-1, 1):
            c = _add(face, _mul(ex, sx * gab / 2.0))
            pecas.append(_parafuso(_add(c, _mul(wp, (pt["tw"] - tc) / 2.0)), wp, d, tc + pt["tw"], classe))
        extremos[pt["ponta"]] = _sub(face, _mul(wp, tc))         # a ponta da cantoneira na face da chapinha
    # a cantoneira: de chapinha a chapinha, as abas para cima e para o lado, centrada na chapinha
    a_ = _norm(_sub(extremos["fim"], extremos["inicio"]))
    lado = _norm(_cruz(Z_, a_))
    meio = _mul(_add(extremos["inicio"], extremos["fim"]), 0.5)
    comp = math.dist(extremos["inicio"], extremos["fim"])
    heel = _sub(_sub(meio, _mul(lado, aba / 2.0)), _mul(Z_, aba / 2.0))
    ag = _cantoneira_no_canto(perfil, a_, heel, lado, Z_, comp)
    ag.nome, ag.papel = "Agulha", "corrente"
    ag.atributos = {"tipo_ifc": "IfcMember", "elemento": "Agulhamento"}
    # a corrente que estava ali vira a cantoneira (a barra do modelo passa a ser a agulha, com o perfil e as pontas dela)
    ajustes = {corr.id: {"inicio": tuple(corr.inicio), "fim": tuple(corr.fim), "perfil": corr.perfil,
                         "rotacao": float(corr.rotacao or 0.0)}}
    alterar = {corr.id: {"inicio": tuple(round(c, 2) for c in ag.inicio), "fim": tuple(round(c, 2) for c in ag.fim),
                         "perfil": ag.perfil, "rotacao": ag.rotacao}}
    soldas = [(corr.id, ch, {"tipo": "filete", "perna": 3.0, "lados": 1, "local": "fabrica", "forma": "contorno"})
              for ch in chapinhas]
    params = dict(p, cantoneira=perfil, chapa_l=Bc, chapa_b=Hc, chapa_t=tc, gabarito=gab, parafuso=nome_par, classe=classe,
                  oblongo=comp_obl)
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(corr, chapinhas)], "soldas": soldas,
            "parametros": params, "avisos": []}


LOCAIS["agulhamento_roscado"] = {
    "nome": "Agulhamento: barra roscada com porcas", "categoria": "correntes",
    "descricao": "A corrente de barra redonda roscada atravessa a alma das duas terças, com arruela e porca dos dois lados "
                 "de cada alma.",
    "parametros": [{"chave": "barra", "rotulo": "Barra", "unidade": "", "padrao": '3/8"'},
                   {"chave": "sobra", "rotulo": "Sobra além da alma (porca + arruela)", "unidade": "mm", "padrao": 30}],
    "esforcos": [],
}
LOCAIS["agulhamento_cantoneira"] = {
    "nome": "Agulhamento: cantoneira com chapinhas (Sooro)", "categoria": "correntes",
    "descricao": "O agulhamento rígido da Sooro: L 1¼\"×⅛\" entre as terças, chapinha 130×50×3 soldada em cada ponta, "
                 "parafusada na alma da terça com 2 M12 em oblongo.",
    "parametros": [{"chave": "cantoneira", "rotulo": "Cantoneira", "unidade": "", "padrao": "L1.1/4''X1/8''"},
                   {"chave": "chapa_l", "rotulo": "Chapinha: comprimento", "unidade": "mm", "padrao": 130},
                   {"chave": "chapa_b", "rotulo": "Chapinha: altura", "unidade": "mm", "padrao": 50},
                   {"chave": "chapa_t", "rotulo": "Chapinha: espessura", "unidade": "mm", "padrao": 3},
                   {"chave": "gabarito", "rotulo": "Passo dos furos", "unidade": "mm", "padrao": 60},
                   {"chave": "parafuso", "rotulo": "Parafuso", "unidade": "", "padrao": "M12"}],
    "esforcos": [],
}
for _t in ("agulhamento_roscado", "agulhamento_cantoneira"):
    TIPOS_3D[_t] = {"pede": "a corrente (de terça a terça) e as terças em que ela chega", "barras": ("corrente", "tercas")}


LOCAIS["castanha_contravento"] = {
    "nome": "Contravento: castanha (cantoneira deitada + aba furada)", "categoria": "contraventamento",
    "descricao": "A CA1 do Hangar: L50 de 150 deitada na mesa da viga ao longo do tirante, um parafuso 1/2\" na mesa a 30 "
                 "mm da borda; na ponta, L50 de 50 em pé furada (d + 1,5) — o tirante passa nela a 25 mm da mesa.",
    "parametros": [{"chave": "cantoneira", "rotulo": "Castanha (perfil)", "unidade": "", "padrao": "L 50X50X4.75"},
                   {"chave": "comprimento", "rotulo": "Comprimento da castanha", "unidade": "mm", "padrao": 150},
                   {"chave": "comprimento_aba", "rotulo": "Comprimento da aba furada", "unidade": "mm", "padrao": 50},
                   {"chave": "parafuso", "rotulo": "Parafuso na mesa", "unidade": "", "padrao": '1/2"'},
                   {"chave": "furo", "rotulo": "Furo (vazio = d + 1,5)", "unidade": "mm", "padrao": ""},
                   {"chave": "separa", "rotulo": "Dois tirantes no nó: afastar", "unidade": "mm", "padrao": 250},
                   {"chave": "face", "rotulo": "Mesa (vazio = a mais perto do tirante)", "unidade": "", "padrao": "",
                    "opcoes": ["", "cima", "baixo"]}],
    "esforcos": [],
}
LOCAIS["duas_chapas_contravento"] = {
    "nome": "Contravento: duas chapas (Sooro)", "categoria": "contraventamento",
    "descricao": "O CV da Sooro: chapa deitada soldada na mesa (270×120×6,35 no nó de dois tirantes); em cada tirante um "
                 "toco de L 2½\"×¼\" parafusado (M16) nela e outro soldado no tirante, cada um com uma chapa 80×80×8, e a "
                 "barra roscada 5/8\" entre as duas chapas — as porcas esticam o X.",
    "parametros": [{"chave": "cantoneira", "rotulo": "Tocos (perfil)", "unidade": "", "padrao": "L 2 1/2'' X 1/4''"},
                   {"chave": "comprimento_toco", "rotulo": "Comprimento de cada toco", "unidade": "mm", "padrao": 150},
                   {"chave": "chapa_t", "rotulo": "Chapas 80×80: espessura", "unidade": "mm", "padrao": 8},
                   {"chave": "vao", "rotulo": "Vão entre as duas chapas", "unidade": "mm", "padrao": 100},
                   {"chave": "rosca", "rotulo": "Barra roscada", "unidade": "", "padrao": '5/8"'},
                   {"chave": "parafuso", "rotulo": "Parafuso do toco", "unidade": "", "padrao": "M16"},
                   {"chave": "separa", "rotulo": "Dois tirantes no nó: afastar", "unidade": "mm", "padrao": 200}],
    "esforcos": [],
}
LOCAIS["cantoneira_contravento"] = {
    "nome": "Contravento: cantoneira cortada em pé (SC1)", "categoria": "contraventamento",
    "descricao": LOCAIS["suporte_contravento"]["descricao"],
    "parametros": LOCAIS["suporte_contravento"]["parametros"] + [
        {"chave": "separa", "rotulo": "Dois tirantes no nó: afastar", "unidade": "mm", "padrao": 150}],
    "esforcos": [],
}
for _t in ("castanha_contravento", "duas_chapas_contravento", "cantoneira_contravento", "chapa_de_no_contravento",
           "esticador_contravento"):
    TIPOS_3D[_t] = {"pede": "a viga e o(s) tirante(s) que chegam nela — uma ligação por nó", "barras": ("tirantes", "apoio")}


# ------------------------------------------------------------------ ligações soldadas de prédio (viga × pilar, viga × viga)
#
# Hora Certa · Edifício Administrativo (29/10, casos A–C aprovados pelo usuário): as típicas da 902 (AKMX, EN 1993-1-8,
# "ligações soldadas") — a viga soldada direto na face do apoio, com a cantoneira 80×80×8 de apoio provisório de
# montagem embaixo; os enrijecedores do pilar na altura das mesas da viga; a placa de topo no pilar que termina; a placa
# de transição (com mísulas) no pilar que nasce sobre a viga ou troca de perfil. As típicas não têm medida ("# ≥ e"):
# as medidas abaixo são as aprovadas.

def _placa(nome, centro, ex, ey, contorno, t, aco="ASTM A36"):
    """chapa de contorno qualquer (mm, no plano ex × ey a partir de `centro`), espessura centrada no plano"""
    from nucleo3d.modelo import Chapa
    return Chapa(nome=nome, origem=tuple(centro), eixo_x=tuple(ex), eixo_y=tuple(ey),
                 contorno=[(round(x, 2), round(y, 2)) for x, y in contorno], espessura=t, centrada=True, furos=[],
                 camada="Chapas", material="Aço", aco=aco, atributos={"tipo_ifc": "IfcPlate"})


def _viga_soldada(viga, apoio, p):
    """A viga soldada na face do apoio (a mesa ou a alma do pilar, a alma da viga principal), cortada na face; embaixo,
    a cantoneira de apoio provisório de montagem (L 80×80×8 × 200, soldada no apoio na fábrica), quando cabe: na viga
    sobre viga, só se o fundo da apoiada fica acima da mesa de baixo da principal (902: "apoio indireto … de altura
    diferente"; na de mesma altura, só a solda). Na viga sobre viga de mesma altura, as mesas que batem saem recortadas."""
    from nucleo2d.detalhe.soldas import _perna
    pv = _perfil(viga.perfil)
    eixo_a = _norm(_sub(apoio.fim, apoio.inicio))
    ponta, no, outro = _ponta_perto(viga, apoio.inicio, eixo_a)
    dirv = _norm(_sub(outro, no))
    nf, F, parede, face = _face_do_apoio(apoio, no, dirv)
    cosf = _dot(dirv, nf)
    if cosf < 0.3:
        raise ErroDeDados("a viga chega muito inclinada na face do apoio")
    folga = float(p.get("folga") or 0.0)
    perfil_l = str(p.get("cantoneira") or "L 80×80×8")
    comp_l = float(p.get("comprimento_cantoneira") or 200.0)
    dv, tfv, twv, bfv = float(pv.d or 300), float(pv.tf or 10), float(pv.tw or 6), float(pv.bf or 150)
    _, vv, _ = _triedro(viga)
    if vv[2] < 0:
        vv = _mul(vv, -1.0)
    X = _add(no, _mul(dirv, _dot(_sub(F, no), nf) / cosf))       # o eixo da viga na face
    em_viga = abs(eixo_a[2]) < 0.7
    recortes, cope = [], {"cima": 0.0, "baixo": 0.0}
    poe_cantoneira = True
    if em_viga:
        pa = _perfil(apoio.perfil)
        da, tfa, twa, bfa = float(pa.d or 300), float(pa.tf or 10), float(pa.tw or 6), float(pa.bf or 150)
        qa = _add(apoio.inicio, _mul(eixo_a, _dot(_sub(X, apoio.inicio), eixo_a)))
        ha = _dot(_sub(qa, X), vv)                                # o eixo da principal na altura da apoiada
        sen = math.sqrt(max(0.0, 1.0 - cosf * cosf))
        comp = _acima5((_dot(_sub(F, no), nf) + bfa / 2.0 - twa / 2.0 + 10.0 + bfv / 2.0 * sen) / cosf)
        if dv / 2.0 > ha + da / 2.0 - tfa - 0.5:
            cope["cima"] = _acima5(dv / 2.0 - (ha + da / 2.0 - tfa) + 10.0)
        if -dv / 2.0 < ha - da / 2.0 + tfa + 0.5:
            cope["baixo"] = _acima5((ha - da / 2.0 + tfa) + dv / 2.0 + 10.0)
        recortes = [{"ponta": ponta, "lado": lado, "comprimento": comp, "altura": h} for lado, h in cope.items() if h > 0]
        # a cantoneira cabe entre o fundo da apoiada e a mesa de baixo da principal (a aba de 80 + 10)
        livre = (-dv / 2.0) - (ha - da / 2.0 + tfa)
        poe_cantoneira = livre >= float(_perfil(perfil_l).d or 80.0) + 10.0
    pecas, conjuntos, soldas = [], [], []
    if poe_cantoneira:
        a = _norm(_cruz(nf, vv))                                   # ao longo da face, deitada
        heel = _add(X, _mul(vv, -dv / 2.0))                        # na face, no fundo da viga
        L = _cantoneira_no_canto(perfil_l, a, heel, nf, _mul(vv, -1.0), comp_l)
        L.nome = "Cantoneira de apoio de montagem"
        pecas.append(L)
        conjuntos.append((apoio, [L]))
        tl = float(_perfil(perfil_l).tf or 8.0)
        soldas.append((apoio.id, L, {"tipo": "filete", "perna": _perna(parede, tl), "lados": 1, "local": "fabrica"}))
    chave = "cortes_inicio" if ponta == "inicio" else "cortes_fim"
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    antigos = [r for r in (getattr(viga, "recortes", None) or []) if r.get("ponta") != ponta]
    ajustes = {viga.id: {chave: copy.deepcopy(getattr(viga, chave) or []), rec: float(getattr(viga, rec) or 0.0),
                         "recortes": copy.deepcopy(getattr(viga, "recortes", None) or [])}}
    alterar = {viga.id: {chave: [{"normal": _r(nf, 6), "ponto": _r(_sub(_add(F, _mul(nf, folga)), no), 3)}], rec: 0.0,
                         "recortes": antigos + recortes}}
    # a viga na face: penetração total, na obra (902: "os cordões de solda serão contínuos e de penetração completa";
    # "ligações a realizar na obra")
    soldas_entre = [(apoio, viga, {"tipo": "penetracao", "perna": _perna(parede, tfv), "lados": 1, "local": "obra",
                                   "forma": "contorno"})]
    params = dict(p, viga=viga.perfil, face=face, cantoneira=perfil_l if poe_cantoneira else "",
                  comprimento_cantoneira=comp_l, folga=folga, recorte_cima=cope["cima"], recorte_baixo=cope["baixo"])
    avisos = [] if poe_cantoneira else ["viga sobre viga de mesma altura: sem cantoneira de montagem (902), só a solda"]
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": conjuntos, "soldas": soldas,
            "soldas_entre": soldas_entre, "parametros": params, "avisos": avisos}


def _enrijecedores_pilar(pilar, vigas, p):
    """Os enrijecedores do pilar na altura das mesas das vigas que chegam pela mesa dele: um de cada lado da alma, entre
    as mesas, espessura ≥ a da mesa da viga (12,5 até 12,5; 16 acima). No pilar que termina (`topo_livre`), a mesa de
    cima fica com a placa de topo (902: "placa de topo # ≥ e" + "enrijecedor # ≥ e1")."""
    from nucleo2d.detalhe.soldas import _perna
    pp = _perfil(pilar.perfil)
    dp, bfp, tfp, twp = float(pp.d or 300), float(pp.bf or 200), float(pp.tf or 10), float(pp.tw or 6)
    _, pe, topo = _ponta_de_baixo(pilar)
    up_, vp_, wp_ = _triedro(pilar)                               # u: largura da mesa; v: a altura (a alma)
    livre = bool(p.get("topo_livre"))
    niveis = []
    for v in vigas:
        pv = _perfil(v.perfil)
        dv, tfv = float(pv.d or 300), float(pv.tf or 10)
        dirv = _norm(_sub(v.fim, v.inicio))
        if abs(_dot(dirv, vp_)) < 0.7:
            continue                                               # chega pela alma: sem enrijecedor
        z = (v.inicio[2] + v.fim[2]) / 2.0
        t = 12.5 if tfv <= 12.5 else 16.0
        for zz, cima in ((z - dv / 2.0 + tfv / 2.0, False), (z + dv / 2.0 - tfv / 2.0, True)):
            if cima and livre and abs(topo[2] - (z + dv / 2.0)) < 50.0:
                continue
            if not (pe[2] + 20.0 < zz < topo[2] - 1.0):
                continue
            achou = next((n for n in niveis if abs(n[0] - zz) < 40.0), None)
            if achou:
                achou[1] = max(achou[1], t)
            else:
                niveis.append([zz, t])
    if not niveis:
        raise ErroDeDados("nenhuma viga chega pela mesa do pilar %s" % (pilar.nome or pilar.id))
    ch = float(p.get("chanfro") or 15.0)
    Bv = dp - 2.0 * tfp                                           # entre as mesas
    Bu = (bfp - twp) / 2.0                                        # da alma à borda da mesa
    pecas, soldas = [], []
    for zz, t in sorted(niveis):
        c = (pe[0], pe[1], zz)
        for lado in (1.0, -1.0):
            eu = _mul(up_, lado)
            o = _add(_add(c, _mul(eu, twp / 2.0)), _mul(vp_, -Bv / 2.0))
            # chanfro nos cantos junto da alma (a concordância do perfil)
            cont = [(ch, 0.0), (Bv - ch, 0.0), (Bv, ch), (Bv, Bu), (0.0, Bu), (0.0, ch)]
            e = _placa("Enrijecedor do pilar", o, vp_, eu, cont, t, aco=str(p.get("aco") or "ASTM A36"))
            pecas.append(e)
            soldas.append((pilar.id, e, {"tipo": "filete", "perna": _perna(min(tfp, twp), t), "lados": 2, "local": "fabrica",
                                         "forma": "contorno"}))
    params = dict(p, pilar=pilar.perfil, niveis=[round(n[0], 1) for n in sorted(niveis)], chanfro=ch)
    return {"pecas": pecas, "alterar": {}, "ajustes": {}, "conjuntos": [(pilar, pecas)], "soldas": soldas,
            "parametros": params, "avisos": []}


def _placa_topo_pilar(pilar, p):
    """A placa de topo do pilar que termina (902): o tamanho do pilar + `sobra`, espessura `t`; o pilar fica mais curto
    pela espessura (o topo da placa no topo do aço)."""
    from nucleo2d.detalhe.soldas import _perna
    pp = _perfil(pilar.perfil)
    dp, bfp, tfp = float(pp.d or 300), float(pp.bf or 200), float(pp.tf or 10)
    ponta_b, pe, topo = _ponta_de_baixo(pilar)
    if _norm(_sub(topo, pe))[2] < 0.7:
        raise ErroDeDados("a placa de topo pede um pilar em pé")
    up_, vp_, _ = _triedro(pilar)
    t = float(p.get("t") or 12.5)
    sobra = float(p.get("sobra") or 50.0)
    B, H = bfp + sobra, dp + sobra
    c = (topo[0], topo[1], topo[2] - t / 2.0)
    o = _add(_add(c, _mul(up_, -B / 2.0)), _mul(vp_, -H / 2.0))
    placa = _placa("Placa de topo do pilar", o, up_, vp_, [(0, 0), (B, 0), (B, H), (0, H)], t, aco=str(p.get("aco") or "ASTM A36"))
    chave = "cortes_fim" if ponta_b == "inicio" else "cortes_inicio"
    rec = "recorte_fim" if ponta_b == "inicio" else "recorte_inicio"
    ajustes = {pilar.id: {chave: copy.deepcopy(getattr(pilar, chave) or []), rec: float(getattr(pilar, rec) or 0.0)}}
    alterar = {pilar.id: {rec: float(getattr(pilar, rec) or 0.0) + t}}
    soldas = [(pilar.id, placa, {"tipo": "filete", "perna": _perna(tfp, t), "lados": 1, "local": "fabrica", "forma": "contorno"})]
    params = dict(p, pilar=pilar.perfil, t=t, sobra=sobra, B=B, H=H)
    return {"pecas": [placa], "alterar": alterar, "ajustes": ajustes, "conjuntos": [(pilar, [placa])], "soldas": soldas,
            "parametros": params, "avisos": []}


def _placa_transicao(pilar, apoio, p):
    """O pilar que nasce sobre a viga (902: "placa de transição # ≥ 12 mm" + "mísula ≥ 150 mm, # ≥ 10 mm") ou sobre o
    trecho de baixo de outro perfil (a troca W610 → W530): a placa no pé do pilar, do tamanho do maior + `sobra`, e — sobre
    viga — as 2 mísulas nas faces das mesas, no plano da alma. O pilar começa em cima da placa."""
    from nucleo2d.detalhe.soldas import _perna
    pp, pa = _perfil(pilar.perfil), _perfil(apoio.perfil)
    ponta, pe, topo = _ponta_de_baixo(pilar)
    if _norm(_sub(topo, pe))[2] < 0.7:
        raise ErroDeDados("a placa de transição pede o pilar de cima em pé")
    up_, vp_, _ = _triedro(pilar)
    sobre_viga = abs(_norm(_sub(apoio.fim, apoio.inicio))[2]) < 0.7
    t = float(p.get("t") or 16.0)
    sobra = float(p.get("sobra") or (100.0 if sobre_viga else 50.0))
    m, tm = float(p.get("misula") or 150.0), float(p.get("t_misula") or 10.0)
    dmax = max(float(pp.d or 0), 0.0 if sobre_viga else float(pa.d or 0))
    bmax = max(float(pp.bf or 0), 0.0 if sobre_viga else float(pa.bf or 0))
    # sobre viga, a placa vai até a ponta das mísulas (a mísula de m × m nas faces das mesas)
    B, H = bmax + sobra, dmax + (2.0 * m if sobre_viga else sobra)
    c = (pe[0], pe[1], pe[2] + t / 2.0)
    o = _add(_add(c, _mul(up_, -B / 2.0)), _mul(vp_, -H / 2.0))
    aco = str(p.get("aco") or "ASTM A36")
    placa = _placa("Placa de transição", o, up_, vp_, [(0, 0), (B, 0), (B, H), (0, H)], t, aco=aco)
    pecas = [placa]
    soldas = [(pilar.id, placa, {"tipo": "filete", "perna": _perna(float(pp.tf or 10), t), "lados": 1, "local": "fabrica",
                                 "forma": "contorno"})]
    soldas_entre = [(apoio, placa, {"tipo": "filete", "perna": _perna(float(pa.tf or 10), t), "lados": 1, "local": "obra",
                                    "forma": "contorno"})]
    if sobre_viga:
        for lado in (1.0, -1.0):
            ev = _mul(vp_, lado)
            o2 = (pe[0] + ev[0] * float(pp.d or 300) / 2.0, pe[1] + ev[1] * float(pp.d or 300) / 2.0, pe[2] + t)
            mi = _placa("Mísula da transição", o2, ev, (0.0, 0.0, 1.0), [(0, 0), (m, 0), (0, m)], tm, aco=aco)
            pecas.append(mi)
            soldas.append((pilar.id, mi, {"tipo": "filete", "perna": _perna(float(pp.tf or 10), tm), "lados": 2,
                                          "local": "fabrica", "forma": "T"}))
            soldas_entre.append((placa, mi, {"tipo": "filete", "perna": _perna(t, tm), "lados": 2, "local": "fabrica",
                                             "forma": "T"}))
    rec = "recorte_inicio" if ponta == "inicio" else "recorte_fim"
    ajustes = {pilar.id: {rec: float(getattr(pilar, rec) or 0.0)}}
    alterar = {pilar.id: {rec: float(getattr(pilar, rec) or 0.0) + t}}
    params = dict(p, pilar=pilar.perfil, apoio=apoio.perfil, t=t, sobra=sobra, B=B, H=H, sobre_viga=sobre_viga)
    return {"pecas": pecas, "alterar": alterar, "ajustes": ajustes, "conjuntos": [(pilar, pecas)], "soldas": soldas,
            "soldas_entre": soldas_entre, "parametros": params, "avisos": []}


LOCAIS["viga_soldada_cantoneira"] = {
    "nome": "Viga soldada no apoio, com cantoneira de montagem", "categoria": "viga",
    "descricao": "A viga soldada direto na face do apoio (mesa ou alma do pilar, alma da viga principal), penetração total "
                 "na obra; embaixo, a cantoneira 80×80×8 de apoio provisório de montagem, soldada no apoio na fábrica "
                 "(na viga sobre viga de mesma altura, só a solda, com as mesas recortadas).",
    "parametros": [{"chave": "cantoneira", "rotulo": "Cantoneira de montagem", "unidade": "", "padrao": "L 80×80×8"},
                   {"chave": "comprimento_cantoneira", "rotulo": "Comprimento da cantoneira", "unidade": "mm", "padrao": 200},
                   {"chave": "folga", "rotulo": "Folga da viga à face", "unidade": "mm", "padrao": 0}],
    "esforcos": [],
}
LOCAIS["enrijecedores_pilar"] = {
    "nome": "Enrijecedores do pilar na altura das mesas da viga", "categoria": "pilar",
    "descricao": "Um enrijecedor de cada lado da alma do pilar, entre as mesas, na altura de cada mesa das vigas que chegam "
                 "pela mesa dele (12,5 mm; 16 mm se a mesa da viga passa de 12,5). No pilar que termina, a mesa de cima "
                 "fica com a placa de topo.",
    "parametros": [{"chave": "topo_livre", "rotulo": "O pilar termina aqui (placa de topo)", "unidade": "", "padrao": ""},
                   {"chave": "chanfro", "rotulo": "Chanfro junto da alma", "unidade": "mm", "padrao": 15}],
    "esforcos": [],
}
LOCAIS["placa_topo_pilar"] = {
    "nome": "Placa de topo do pilar", "categoria": "pilar",
    "descricao": "A placa no topo do pilar que termina, do tamanho do pilar + 50; o pilar fica mais curto pela espessura.",
    "parametros": [{"chave": "t", "rotulo": "Espessura", "unidade": "mm", "padrao": 12.5},
                   {"chave": "sobra", "rotulo": "Sobra além do pilar", "unidade": "mm", "padrao": 50}],
    "esforcos": [],
}
LOCAIS["placa_transicao_pilar"] = {
    "nome": "Placa de transição no pé do pilar", "categoria": "pilar",
    "descricao": "O pilar que nasce sobre a viga (placa + 2 mísulas nas faces das mesas) ou sobre o trecho de baixo de "
                 "outro perfil (só a placa, do tamanho do maior).",
    "parametros": [{"chave": "t", "rotulo": "Espessura da placa", "unidade": "mm", "padrao": 16},
                   {"chave": "sobra", "rotulo": "Sobra além do pilar (vazio: 100 sobre viga, 50 sobre pilar)", "unidade": "mm",
                    "padrao": ""},
                   {"chave": "misula", "rotulo": "Mísula (altura)", "unidade": "mm", "padrao": 150},
                   {"chave": "t_misula", "rotulo": "Mísula: espessura", "unidade": "mm", "padrao": 10}],
    "esforcos": [],
}
TIPOS_3D["viga_soldada_cantoneira"] = {"pede": "a viga apoiada e o pilar ou a viga em que ela chega", "barras": ("viga", "apoio")}
TIPOS_3D["enrijecedores_pilar"] = {"pede": "o pilar e as vigas que chegam pela mesa dele", "barras": ("pilar", "vigas")}
TIPOS_3D["placa_topo_pilar"] = {"pede": "um pilar (ou vários)", "barras": ("pilar",)}
TIPOS_3D["placa_transicao_pilar"] = {"pede": "o pilar de cima e a viga (ou o trecho de pilar) em que ele nasce",
                                     "barras": ("pilar", "viga")}

#: as famílias: os tipos de uma família ligam as mesmas barras e se trocam um pelo outro
FAMILIAS = {
    "contravento": {"nome": "Contravento × viga", "tipos": ["castanha_contravento", "duas_chapas_contravento",
                                                            "cantoneira_contravento", "chapa_de_no_contravento",
                                                            "esticador_contravento"]},
    "agulhamento": {"nome": "Agulhamento entre terças", "tipos": ["agulhamento_roscado", "agulhamento_cantoneira"]},
}


def familia_de(tipo: str) -> Optional[str]:
    return next((f for f, v in FAMILIAS.items() if tipo in v["tipos"]), None)


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
    if pede == ("tirantes", "apoio"):
        return _nos_de_contravento(barras, TIPOS_3D[tipo]["pede"])
    if pede == ("corrente", "tercas"):
        tercas = [b for b in barras if str(b.papel).lower() in ("terça", "terca", "longarina")]
        corr = [b for b in barras if b not in tercas]
        if not corr or len(tercas) < 2:
            raise ErroDeDados("selecione %s" % TIPOS_3D[tipo]["pede"])
        grupos = []
        for c in corr:
            _w, pts = _pontas_da_corrente(c, tercas)
            grupos.append([c] + list({id(pt["terca"]): pt["terca"] for pt in pts}.values()))
        return grupos
    if pede == ("pilar", "vigas"):
        pil = [b for b in barras if abs(b.direcao[2]) > 0.7]
        if len(pil) != 1 or len(barras) < 2:
            raise ErroDeDados("selecione %s (um pilar só)" % TIPOS_3D[tipo]["pede"])
        return [pil + [b for b in barras if b is not pil[0]]]
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


def _eh_tirante(b):
    return str(b.papel).lower().startswith("contravent") or bool(re.search(r"RED|Ø|TIRANTE|REDOND", str(b.perfil), re.I))


def _nos_de_contravento(barras, pede):
    """os nós: cada viga selecionada com os tirantes que chegam nela no mesmo ponto (até 400 mm um do outro ao longo
    dela) — [tirante(s)…, viga] por nó"""
    tir = [b for b in barras if _eh_tirante(b)]
    vigas = [b for b in barras if b not in tir]
    if not tir or not vigas:
        raise ErroDeDados("selecione %s" % pede)
    nos = []
    for v in vigas:
        chegam = []
        for t in tir:
            info = _ponta_no_apoio(t, v)
            if info is not None:
                chegam.append((_dot(_sub(info["E"], v.inicio), info["wa"]), t))
        chegam.sort(key=lambda x: x[0])
        grupo, ultimo = [], None
        for s, t in chegam:
            if grupo and s - ultimo > 400.0:
                nos.append(grupo + [v])
                grupo = []
            grupo.append(t)
            ultimo = s
        if grupo:
            nos.append(grupo + [v])
    if not nos:
        raise ErroDeDados("nenhum tirante selecionado chega numa viga selecionada (até 600 mm em planta)")
    return nos


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
    if tipo == "chapa_simples":
        return _chapa_simples(barras[0], barras[1], p)
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
    if tipo == "castanha_contravento":
        return _castanha_contravento(barras, p)
    if tipo == "duas_chapas_contravento":
        return _duas_chapas_contravento(barras, p)
    if tipo == "cantoneira_contravento":
        return _cantoneira_contravento(barras, p)
    if tipo == "agulhamento_roscado":
        return _agulhamento_roscado(barras, p)
    if tipo == "agulhamento_cantoneira":
        return _agulhamento_cantoneira(barras, p)
    if tipo == "chapa_de_no_contravento":
        return _chapa_de_no_contravento(barras, p)
    if tipo == "esticador_contravento":
        return _chapa_de_no_contravento(barras, p, esticador=True)
    if tipo == "viga_soldada_cantoneira":
        return _viga_soldada(barras[0], barras[1], p)
    if tipo == "enrijecedores_pilar":
        return _enrijecedores_pilar(barras[0], barras[1:], p)
    if tipo == "placa_topo_pilar":
        return _placa_topo_pilar(barras[0], p)
    if tipo == "placa_transicao_pilar":
        return _placa_transicao(barras[0], barras[1], p)
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
        d["familia"] = familia_de(tid)
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


def _grupo(trabalho, tipo, barras, p, lid, novas, alterar, soldas_pendentes, esforcos=None, analise=None) -> dict:
    """uma ligação (um grupo de barras): as peças no documento de trabalho, as barras alteradas, os conjuntos e as soldas
    a definir depois da numeração; devolve o resultado (verificação, avisos, parâmetros)"""
    from nucleo import acessorios as A
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
            # um conjunto por barra: a ligação por nó tem dois tirantes (e o topo do pilar, o pilar e a viga) —
            # com a instância da ligação, os dois saíam num conjunto só na prancha (23/10)
            inst = "c%s-%s" % (lid[1:], barra.id[-6:])
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
    return {"id": lid, "tipo": tipo, "barras": [b.id for b in barras], "verificacao": verif, "esforcos": usados,
            "origem_esforcos": origem, "avisos": g["avisos"], "parametros": g["parametros"]}


def _numerar_e_soldar(trabalho, novas, ids_barras, alterar, soldas_pendentes, tudo=False, avisar=None):
    """as marcas (o numerar no documento de trabalho, uma vez) e as soldas pela posição da outra peça. `tudo`: a
    numeração vale para o modelo inteiro (o modelo que ainda não tinha marcas), não só para as peças da ligação"""
    from nucleo3d import producao
    # marcas: o numerar no documento de trabalho (as peças novas, as barras que entraram em conjunto)
    r = producao.numerar(trabalho, avisar=avisar)
    ids_novas = {e.id for e in novas}
    da_ligacao = ids_novas | set(ids_barras)
    for i, patch in r["mudancas"].items():
        if not tudo and i not in da_ligacao:
            continue                                      # o resto do modelo não é numerado por tabela
        e = trabalho.entidades[i]
        a = dict(e.atributos or {})
        for k, v in patch.items():
            if v is None:
                a.pop(k, None)
            else:
                a[k] = v
        e.atributos = a
        if i not in ids_novas:
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
            # a peça nova já sai com os atributos; a que já existia (as duas barras soldadas uma na outra, a viga na face
            # do pilar — 29/10) vai em `alterar`
            if x.id not in ids_novas and x.id in trabalho.entidades:
                alterar.setdefault(x.id, {})["atributos"] = a


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
    if isinstance(ligacao, (list, tuple)):
        return _varias(doc, tipo, list(ligacao), parametros, esforcos, analise)
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
        if reg.get("tipo") == tipo:
            base_parametros = dict(reg.get("parametros") or {}, **(parametros or {}))
        else:
            # trocar o tipo (a variante da mesma família): as mesmas barras, os parâmetros do tipo novo
            if familia_de(tipo) is None or familia_de(tipo) != familia_de(str(reg.get("tipo"))):
                raise ErroDeDados("a ligação %s não se troca por %s (outra família)" % (reg.get("tipo"), tipo))
            base_parametros = dict(parametros or {})
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
        resultados.append(_grupo(trabalho, tipo, barras, p, lid, novas, alterar, soldas_pendentes, esforcos, analise))
    _numerar_e_soldar(trabalho, novas, {b.id for g_ in grupos for b in g_}, alterar, soldas_pendentes)
    # as barras que voltaram ao de antes e não mudaram de novo (inclusive as soldas tiradas com as peças velhas)
    for bid, campos in restaurar.items():
        for k, v in campos.items():
            alterar.setdefault(bid, {}).setdefault(k, v)
        if "atributos" not in alterar[bid]:
            alterar[bid]["atributos"] = trabalho.entidades[bid].atributos
    return {"novas": [e.dict() for e in novas], "alterar": alterar, "remover": remover, "ligacoes": resultados}


def aplicar_lote(doc, pedidos: Sequence, avisar=None, numerar_tudo: bool = False) -> dict:
    """Muitas ligações de uma vez — [(tipo, ids, parametros)], de tipos diferentes — numeradas uma vez só no fim (29/10,
    Hora Certa · Edifício Administrativo: ~800 ligações soldadas; o `aplicar` uma a uma numera o modelo inteiro a cada
    ligação). A que não se põe (ErroDeDados) vai para `recusadas` e as outras seguem. Devolve o mesmo que o `aplicar`
    (novas, alterar, remover vazio, ligacoes) e as recusadas. `numerar_tudo`: as marcas do modelo inteiro também (o
    modelo que nunca foi numerado: uma passada só, em vez de numerar antes e de novo depois)."""
    avisar = avisar or (lambda *a: None)
    trabalho = _copia_de_trabalho(doc, [])
    novas, alterar, resultados, recusadas, soldas_pendentes = [], {}, [], [], []
    ids_barras = set()
    for k, (tipo, ids, parametros) in enumerate(pedidos):
        if tipo not in TIPOS_3D:
            raise ErroDeDados("ligação desconhecida para o 3D: %s" % tipo)
        if k % 100 == 0:
            avisar("ligações (%d de %d)" % (k, len(pedidos)))
        _copiar_em(trabalho, ids)
        p = {k_: v for k_, v in (parametros or {}).items() if v not in (None, "")}
        na_ordem = bool(p.pop("_na_ordem", False))
        try:
            # `_na_ordem`: quem pede já sabe qual é a apoiada e qual é o apoio (o _barras_para decide pelas retas
            # infinitas: no nó em que duas vigas terminam na ponta de uma terceira, a terceira virava a apoiada das duas)
            grupos = [[trabalho.entidades[i] for i in ids]] if na_ordem else _barras_para(trabalho, tipo, ids)
            for barras in grupos:
                resultados.append(_grupo(trabalho, tipo, barras, dict(p), _id_ligacao(), novas, alterar, soldas_pendentes))
                ids_barras |= {b.id for b in barras}
        except ErroDeDados as exc:
            recusadas.append({"tipo": tipo, "barras": list(ids), "erro": str(exc)})
    avisar("marcas e soldas das ligações…")
    _numerar_e_soldar(trabalho, novas, ids_barras, alterar, soldas_pendentes, tudo=numerar_tudo, avisar=avisar)
    return {"novas": [e.dict() for e in novas], "alterar": alterar, "remover": [], "ligacoes": resultados,
            "recusadas": recusadas}


def _varias(doc, tipo, lids, parametros, esforcos, analise) -> dict:
    """Trocar o tipo (ou refazer) de várias ligações numa resposta só — um desfazer no editor: cada uma refeita na
    cópia de trabalho com as anteriores já feitas, e a resposta é o que mudou do documento recebido para o fim."""
    from nucleo3d.modelo import Documento
    trabalho = _copia_de_trabalho(doc, [])
    removidas, novas, alterar, ligs = set(), [], {}, []
    for lid in dict.fromkeys(lids):
        r = aplicar(trabalho, tipo, [], parametros, ligacao=lid, esforcos=esforcos, analise=analise)
        for i in r["remover"]:
            removidas.add(i)
            trabalho.entidades.pop(i, None)
        for i, campos in r["alterar"].items():
            if i not in trabalho.entidades:
                continue
            _copiar_em(trabalho, [i])
            for k, v in campos.items():
                setattr(trabalho.entidades[i], k, copy.deepcopy(v))
            alterar.setdefault(i, {}).update(copy.deepcopy(campos))
        for e in Documento.de_dict({"entidades": r["novas"]}).entidades.values():
            trabalho.add(e)
            trabalho._copiadas.add(e.id)
            novas.append(e.id)
        ligs += r["ligacoes"]
    return {"novas": [trabalho.entidades[i].dict() for i in novas if i in trabalho.entidades],
            "alterar": {i: c for i, c in alterar.items() if i in doc.entidades and i not in removidas},
            "remover": [i for i in removidas if i in doc.entidades], "ligacoes": ligs}


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
