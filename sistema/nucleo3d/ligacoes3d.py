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
import copy
import dataclasses
import math
from typing import Dict, List, Optional, Sequence

from nucleo.base import ErroDeDados

#: os tipos da biblioteca que sabem se pôr no 3D, com o que cada um pede
TIPOS_3D = {
    "placa_base_rotulada": {"pede": "um pilar (ou vários)", "barras": ("pilar",)},
    "placa_base_engastada": {"pede": "um pilar (ou vários)", "barras": ("pilar",)},
    "chapa_topo_joelho": {"pede": "uma viga e o pilar em que ela chega", "barras": ("viga", "pilar")},
    "tesoura_topo_pilar": {"pede": "um pilar e a viga ou o banzo que apoia no topo dele", "barras": ("pilar", "viga")},
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


# ------------------------------------------------------------------ escolher as barras

def _barras_para(doc, tipo, ids):
    """As barras da seleção no papel que o tipo pede, na ordem dele."""
    from nucleo3d.modelo import Barra
    barras = [doc.entidades[i] for i in ids if isinstance(doc.entidades.get(i), Barra)]
    pede = TIPOS_3D[tipo]["barras"]
    if len(pede) == 1:
        if not barras:
            raise ErroDeDados("selecione %s" % TIPOS_3D[tipo]["pede"])
        return [[b] for b in barras]
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
    return [[a, b]]


def _gerar(tipo, barras, p):
    if tipo in ("placa_base_rotulada", "placa_base_engastada"):
        return _base(barras[0], p, tipo == "placa_base_engastada")
    if tipo == "chapa_topo_joelho":
        return _chapa_topo(barras[0], barras[1], p)
    if tipo == "tesoura_topo_pilar":
        return _topo_pilar(barras[0], barras[1], p)
    raise ErroDeDados("a ligação %s ainda não sabe se pôr no 3D" % tipo)


def tipos(doc=None, ids=()) -> List[dict]:
    """Os tipos que se põem no 3D, com os parâmetros da biblioteca (os padrões dela)."""
    from nucleo import acessorios as A
    fora = []
    for tid, info in TIPOS_3D.items():
        t = A.REGISTRO[tid]
        d = t.dict()
        d["pede"] = info["pede"]
        fora.append(d)
    return fora


def assinatura(b) -> list:
    """o que, mudando na barra, pede a ligação refeita: as pontas, o perfil e a rotação (o editor compara igual)"""
    return [_r(b.inicio, 1), _r(b.fim, 1), str(b.perfil), round(float(b.rotacao or 0.0), 3)]


def _id_ligacao():
    import uuid
    return "L" + uuid.uuid4().hex[:10]


def aplicar(doc, tipo: str, ids: Sequence[str], parametros: Optional[dict] = None, ligacao: Optional[str] = None,
            esforcos: Optional[dict] = None) -> dict:
    """A ligação `tipo` nas barras `ids` (uma ligação por pilar, nas bases), ou `ligacao` (o id de uma aplicada) refeita
    com os parâmetros novos. Devolve {"novas": [entidades], "alterar": {id: {campo: valor}}, "remover": [ids],
    "ligacoes": [{id, tipo, verificacao, avisos}]}."""
    from nucleo3d.modelo import Documento
    from nucleo3d import producao
    from nucleo import acessorios as A
    if tipo not in TIPOS_3D:
        raise ErroDeDados("ligação desconhecida para o 3D: %s" % tipo)
    trabalho = Documento.de_dict(doc.dict())                # cópia: o recebido não muda
    remover: List[str] = []
    restaurar: Dict[str, dict] = {}
    base_parametros = dict(parametros or {})
    if ligacao:
        velhas = [e for e in trabalho.entidades.values() if ((e.atributos or {}).get("ligacao") or {}).get("id") == ligacao]
        if not velhas:
            raise ErroDeDados("a ligação %s não está mais no modelo" % ligacao)
        reg = velhas[0].atributos["ligacao"]
        ids = list(reg.get("pecas") or [])
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
        reg = {"id": lid, "tipo": tipo, "parametros": g["parametros"], "pecas": [b.id for b in barras],
               "ajustes": g["ajustes"], "geometria": {b.id: assinatura(b) for b in barras}}
        for e in g["pecas"]:
            e.atributos = dict(e.atributos or {}, ligacao=dict(reg, papel=e.nome))
            trabalho.add(e)
            novas.append(e)
        for bid, campos in g["alterar"].items():
            b = trabalho.entidades[bid]
            for k, v in campos.items():
                setattr(b, k, copy.deepcopy(v))
            alterar.setdefault(bid, {}).update(copy.deepcopy(campos))
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
                ch.atributos = dict(ch.atributos or {}, marcas=mc)
        soldas_pendentes += g["soldas"]
        verif = None
        try:
            parametros_lib = {k: v for k, v in g["parametros"].items() if k in {x.chave for x in A.REGISTRO[tipo].parametros}}
            r = A.montar(tipo, parametros_lib, esforcos or {})
            verif = r.get("verificacao")
        except Exception as exc:                          # noqa: BLE001 — a verificação não impede a ligação
            verif = {"erro": str(exc)}
        resultados.append({"id": lid, "tipo": tipo, "barras": [b.id for b in barras], "verificacao": verif,
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
            if x is b:
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
