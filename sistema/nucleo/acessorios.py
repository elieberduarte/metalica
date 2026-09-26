# -*- coding: utf-8 -*-
"""Biblioteca de ligações e acessórios de uma estrutura metálica.

Cada tipo junta o que o projetista e a fábrica precisam dele:

    parâmetros  as medidas que definem a peça (padrões tirados das obras da Sooro, onde há)
    peças       o que se fabrica e se compra: chapas com furos, barras, parafusos, porcas,
                com quantidade e peso (7 850 kg/m³)
    desenho     vistas em SVG com cotas, furos e solda (classes de estilo, a tela dá a cor)
    verificação a conta pela NBR 8800 com as rotinas de `nucleo.ligacoes` e `nucleo.bases`
                (grupo de parafusos, esmagamento, solda de filete, chumbadores, placa de base,
                chapa de topo, gusset), dado o esforço de cálculo

    from nucleo import acessorios
    acessorios.lista()                                   # os tipos, por categoria
    acessorios.montar("suporte_terca_cadeirinha", {"t": 4.75}, {"R_Sd": 6.0})

Unidades: parâmetros em mm (como a fábrica fala) e esforços em kN (e kN·m); as rotinas de
verificação recebem cm, como o resto do núcleo. `exemplos_das_obras` lê a lista de
materiais dos projetos detalhados e diz, peça a peça, a que tipo cada acessório corresponde.
"""
from __future__ import annotations

import html as _html
import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt, nao_verificada

RHO = 7.85e-6          # kg/mm³
FOLGA_FURO = 1.5       # mm: furo padrão = d + 1,5 mm (NBR 8800, Tabela 12)

CATEGORIAS = [
    ("tercas", "Terças e longarinas"),
    ("correntes", "Correntes e agulhamentos"),
    ("contraventamento", "Contraventamento"),
    ("apoios", "Apoios e bases"),
    ("tesoura", "Tesoura e pórtico"),
    ("fechamento", "Fechamento e telha"),
    ("fixadores", "Parafusos e chumbadores"),
]


@dataclass
class Param:
    chave: str
    rotulo: str
    unidade: str = "mm"
    padrao: object = None
    opcoes: Optional[List] = None
    dica: str = ""

    def dict(self):
        return {"chave": self.chave, "rotulo": self.rotulo, "unidade": self.unidade, "padrao": self.padrao,
                "opcoes": self.opcoes, "dica": self.dica}


@dataclass
class Tipo:
    id: str
    nome: str
    categoria: str
    descricao: str
    parametros: List[Param]
    esforcos: List[Param]
    gerar: Callable
    verificar: Optional[Callable] = None
    origem: str = ""                       # "obras Sooro", "galpão", "NBR 8800"…
    uso: str = ""                          # onde e quando se usa

    def dict(self):
        return {"id": self.id, "nome": self.nome, "categoria": self.categoria, "descricao": self.descricao,
                "parametros": [p.dict() for p in self.parametros], "esforcos": [p.dict() for p in self.esforcos],
                "verifica": self.verificar is not None, "origem": self.origem, "uso": self.uso}


REGISTRO: Dict[str, Tipo] = {}


def _registrar(t: Tipo) -> Tipo:
    REGISTRO[t.id] = t
    return t


# =====================================================================================
# peças
# =====================================================================================

PARAFUSOS = ["M12", "M16", "M20", "M22", "M24", '1/2"', '5/8"', '3/4"', '7/8"', '1"']
CLASSES = ["ASTM A307", "ASTM A325", "ISO 4.6", "ISO 8.8"]
ACOS_CHAPA = ["ASTM A36", "CIVIL 300", "ASTM A572 Gr.50"]
BITOLAS_CHAPA = [3.0, 3.75, 4.75, 6.35, 8.0, 9.5, 12.7, 16.0, 19.0, 22.4, 25.4, 31.75, 37.5, 50.8]
DIAMETROS_BARRA = {'3/8"': 9.525, '1/2"': 12.7, '5/8"': 15.875, '3/4"': 19.05, '7/8"': 22.225, '1"': 25.4,
                   "Ø10": 10.0, "Ø12,5": 12.5, "Ø16": 16.0, "Ø20": 20.0, "Ø25": 25.0}


def d_parafuso_mm(nome: str) -> float:
    from nucleo import materiais as mat
    if nome in mat.DIAMETROS:
        return mat.DIAMETROS[nome][0] * 10.0
    if nome in DIAMETROS_BARRA:
        return DIAMETROS_BARRA[nome]
    raise ErroDeDados("diâmetro desconhecido: %s" % nome)


def furo_mm(nome: str) -> float:
    return round(d_parafuso_mm(nome) + FOLGA_FURO, 1)


def _num(v, padrao=0.0) -> float:
    if v is None or v == "":
        return float(padrao)
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "."))


def peca_chapa(descricao: str, L: float, B: float, t: float, qtd: int = 1, furos: Sequence[float] = (),
               oblongos: Sequence[Tuple[float, float]] = (), aco: str = "ASTM A36", nota: str = "") -> dict:
    """Chapa retangular L × B × t com furos (diâmetros) e oblongos (largura, comprimento)."""
    area = L * B - sum(math.pi * d * d / 4.0 for d in furos) \
        - sum(w * (c - w) + math.pi * w * w / 4.0 for w, c in oblongos)
    peso = area * t * RHO
    fs = []
    if furos:
        from collections import Counter
        fs += ["%d× Ø%s" % (n, fmt(d, 1).replace(",0", "")) for d, n in Counter(furos).items()]
    if oblongos:
        from collections import Counter
        fs += ["%d× oblongo %s×%s" % (n, fmt(w, 0), fmt(c, 0)) for (w, c), n in Counter(oblongos).items()]
    return {"item": "chapa", "descricao": descricao, "medida": "%s × %s × %s" % (fmt(L, 0), fmt(B, 0), fmt(t, 2)),
            "furos": ", ".join(fs), "qtd": int(qtd), "material": aco, "peso_unit": round(peso, 3),
            "peso": round(peso * qtd, 3), "nota": nota}


def peca_barra(descricao: str, perfil: str, L: float, qtd: int = 1, aco: str = "ASTM A36", nota: str = "") -> dict:
    massa = massa_perfil(perfil)
    peso = massa * L / 1000.0
    return {"item": "barra", "descricao": descricao, "medida": "%s L = %s" % (perfil, fmt(L, 0)), "furos": "",
            "qtd": int(qtd), "material": aco, "peso_unit": round(peso, 3), "peso": round(peso * qtd, 3), "nota": nota}


def peca_redonda(descricao: str, d: float, L: float, qtd: int = 1, aco: str = "ASTM A36", nota: str = "") -> dict:
    peso = math.pi * d * d / 4.0 * L * RHO
    return {"item": "barra", "descricao": descricao, "medida": "Ø %s L = %s" % (fmt(d, 1).replace(",0", ""), fmt(L, 0)),
            "furos": "", "qtd": int(qtd), "material": aco, "peso_unit": round(peso, 3), "peso": round(peso * qtd, 3),
            "nota": nota}


def peca_fixador(item: str, descricao: str, qtd: int, nota: str = "") -> dict:
    return {"item": item, "descricao": descricao, "medida": "", "furos": "", "qtd": int(qtd), "material": "",
            "peso_unit": 0.0, "peso": 0.0, "nota": nota}


def massa_perfil(nome: str) -> float:
    from nucleo import perfis_fabrica as pf, catalogo
    p = pf.perfil_de_fabrica(nome) or catalogo.perfil_de(nome)
    if p is None:
        raise ErroDeDados("perfil desconhecido: %s" % nome)
    return float(p.massa or 0.0)


def comprimento_parafuso(pega: float, d: float) -> int:
    """Comprimento comercial (mm) que atravessa a pega com porca e arruela."""
    alvo = pega + 0.8 * d + 3.0 + 2.0 * max(2.0, d / 8.0)
    for c in (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100, 110, 120, 130, 140, 150):
        if c >= alvo:
            return c
    return int(math.ceil(alvo / 10.0) * 10)


# =====================================================================================
# desenho SVG
# =====================================================================================

class Svg:
    """Desenho técnico simples em SVG: milímetro, Y para cima, várias vistas lado a lado.
    As classes (aco, furo, eixo, cota, solda, oculta, concreto, rot) recebem a cor da tela."""

    def __init__(self):
        self.els: List[str] = []
        self.xs: List[float] = []
        self.ys: List[float] = []
        self.dx = 0.0
        self.dy = 0.0
        self.h = 12.0                   # altura do texto (mm do desenho), definida por vista

    def origem(self, dx: float, dy: float, h: Optional[float] = None):
        self.dx, self.dy = dx, dy
        if h:
            self.h = h

    def _p(self, x, y):
        X, Y = x + self.dx, y + self.dy
        self.xs.append(X)
        self.ys.append(Y)
        return X, -Y

    def poli(self, pts, cls="aco", fechada=True):
        q = [self._p(x, y) for x, y in pts]
        d = " ".join("%.2f,%.2f" % p for p in q)
        self.els.append('<%s class="%s" points="%s"/>' % ("polygon" if fechada else "polyline", cls, d))

    def ret(self, x, y, w, h, cls="aco"):
        self.poli([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], cls)

    def linha(self, x1, y1, x2, y2, cls="eixo"):
        a, b = self._p(x1, y1), self._p(x2, y2)
        self.els.append('<line class="%s" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (cls, a[0], a[1], b[0], b[1]))

    def circ(self, x, y, r, cls="furo"):
        c = self._p(x, y)
        self._p(x - r, y - r); self._p(x + r, y + r)
        self.els.append('<circle class="%s" cx="%.2f" cy="%.2f" r="%.2f"/>' % (cls, c[0], c[1], r))

    def oblongo(self, x, y, larg, comp, horizontal=True, cls="furo"):
        """Furo oblongo centrado em (x, y): `comp` na direção horizontal (ou vertical)."""
        r = larg / 2.0
        s = (comp - larg) / 2.0
        if horizontal:
            a, b = (x - s, y), (x + s, y)
        else:
            a, b = (x, y - s), (x, y + s)
        pa, pb = self._p(*a), self._p(*b)
        self._p(x - comp / 2, y - comp / 2); self._p(x + comp / 2, y + comp / 2)
        if horizontal:
            d = "M%.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 1 %.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 1 %.2f,%.2f Z" % (
                pa[0], pa[1] - r, pb[0], pb[1] - r, r, r, pb[0], pb[1] + r, pa[0], pa[1] + r, r, r, pa[0], pa[1] - r)
        else:
            d = "M%.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 1 %.2f,%.2f L%.2f,%.2f A%.2f,%.2f 0 0 1 %.2f,%.2f Z" % (
                pa[0] - r, pa[1], pb[0] - r, pb[1], r, r, pb[0] + r, pb[1], pa[0] + r, pa[1], r, r, pa[0] - r, pa[1])
        self.els.append('<path class="%s" d="%s"/>' % (cls, d))

    def texto(self, x, y, t, cls="rot", anc="start", h=None, ang=0.0):
        hh = h or self.h
        # a caixa do texto entra na moldura do desenho (sem isso o título da vista da direita
        # e os rótulos saíam cortados); largura média de 0,6·h por letra
        w = 0.6 * hh * len(str(t))
        x0 = x - (w / 2 if anc == "middle" else (w if anc == "end" else 0.0))
        if not ang:
            self._p(x0, y); self._p(x0 + w, y + hh)
        p = self._p(x, y)
        tr = ' transform="rotate(%.1f %.2f %.2f)"' % (-ang, p[0], p[1]) if ang else ""
        self.els.append('<text class="%s" x="%.2f" y="%.2f" font-size="%.2f" text-anchor="%s"%s>%s</text>'
                        % (cls, p[0], p[1], hh, anc, tr, _html.escape(str(t))))

    def cota(self, x1, y1, x2, y2, desl: float, texto: Optional[str] = None):
        """Cota alinhada entre (x1,y1) e (x2,y2), com a linha de cota a `desl` (mm do
        desenho; positivo à esquerda do sentido 1→2) e o número no meio."""
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-6:
            return
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        nx, ny = -uy, ux
        a = (x1 + nx * desl, y1 + ny * desl)
        b = (x2 + nx * desl, y2 + ny * desl)
        ext = self.h * 0.3 * (1 if desl >= 0 else -1)
        self.linha(x1 + nx * self.h * 0.2 * (1 if desl >= 0 else -1), y1 + ny * self.h * 0.2 * (1 if desl >= 0 else -1),
                   a[0] + nx * ext, a[1] + ny * ext, "cota")
        self.linha(x2 + nx * self.h * 0.2 * (1 if desl >= 0 else -1), y2 + ny * self.h * 0.2 * (1 if desl >= 0 else -1),
                   b[0] + nx * ext, b[1] + ny * ext, "cota")
        self.linha(a[0], a[1], b[0], b[1], "cota")
        s = self.h * 0.45
        for (px, py), sg in ((a, 1), (b, -1)):
            self.poli([(px, py), (px + sg * ux * s * 1.6 + nx * s * 0.35, py + sg * uy * s * 1.6 + ny * s * 0.35),
                       (px + sg * ux * s * 1.6 - nx * s * 0.35, py + sg * uy * s * 1.6 - ny * s * 0.35)], "seta")
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90.001 or ang < -89.999:
            ang += 180.0
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        lado = self.h * 0.25
        self.texto(mx + nx * lado * (1 if desl >= 0 else -1) * (1 if -89.999 <= math.degrees(math.atan2(uy, ux)) <= 90.001 else -1),
                   my + ny * lado * (1 if desl >= 0 else -1) * (1 if -89.999 <= math.degrees(math.atan2(uy, ux)) <= 90.001 else -1),
                   texto if texto is not None else fmt(L, 0), "cotatx", "middle", ang=ang)

    def solda(self, x1, y1, x2, y2, perna=4.0):
        """Filete representado por triângulos pequenos ao longo do cordão."""
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-6:
            return
        n = max(2, int(L / max(perna * 2.5, 6.0)))
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        nx, ny = -uy, ux
        for i in range(n):
            px, py = x1 + ux * (i + 0.5) * L / n, y1 + uy * (i + 0.5) * L / n
            self.poli([(px - ux * perna / 2, py - uy * perna / 2), (px + ux * perna / 2, py + uy * perna / 2),
                       (px + nx * perna * 0.8, py + ny * perna * 0.8)], "solda")

    def titulo(self, x, y, t):
        self.texto(x, y, t, "tit", "start", h=self.h * 1.15)

    def render(self) -> str:
        if not self.xs:
            return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
        x0, x1 = min(self.xs), max(self.xs)
        y0, y1 = -max(self.ys), -min(self.ys)
        m = max(x1 - x0, y1 - y0) * 0.04 + self.h
        vb = (x0 - m, y0 - m, (x1 - x0) + 2 * m, (y1 - y0) + 2 * m)
        return ('<svg xmlns="http://www.w3.org/2000/svg" class="ligacao" viewBox="%.1f %.1f %.1f %.1f" '
                'preserveAspectRatio="xMidYMid meet">%s</svg>' % (vb[0], vb[1], vb[2], vb[3], "".join(self.els)))


# =====================================================================================
# tipos
# =====================================================================================

def _grupo(r: Resultado, diametro: str, classe: str, linhas: int, colunas: int, passo: float, gab: float,
           chapas: List[dict], V: float = 0.0, N: float = 0.0, M: float = 0.0, exc: float = 0.0, planos: int = 1,
           furo: str = "padrão", elemento: str = "Parafusos"):
    from nucleo import ligacoes as lig
    try:
        g = lig.verificar_grupo_parafusos(diametro, classe, linhas, colunas, passo / 10.0, gab / 10.0, chapas,
                                          V_Sd=V, N_Sd=N, M_Sd=M, excentricidade=exc / 10.0, planos=planos,
                                          furo=furo, elemento=elemento)
        for v in g.verificacoes:
            v.titulo = "%s — %s" % (elemento, v.titulo) if not v.titulo.startswith(elemento) else v.titulo
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada("%s: %s" % (elemento, exc_)))


def _filete(r: Resultado, perna: float, comp: float, F: float, n: int, t_base: float, nome: str, fy: float = 25.0):
    from nucleo import ligacoes as lig
    try:
        r.add(lig.filete(perna / 10.0, comp / 10.0, F_Sd=F, n_cordoes=n, t_base=t_base / 10.0, fy_base=fy, nome=nome))
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada("%s: %s" % (nome, exc_)))


def tipo_furo(parafuso: str, comprimento_oblongo: float = 0.0) -> str:
    """Nome do furo na NBR 8800 (Tabela 11) para o oblongo de `comprimento_oblongo` mm."""
    if not comprimento_oblongo:
        return "padrão"
    d = d_parafuso_mm(parafuso)
    return "oblongo curto" if comprimento_oblongo <= d + (6.0 if d <= 24 else 10.0) + 0.5 else "oblongo longo"


def _aco(nome: str):
    from nucleo import materiais as mat
    return mat.aco(nome)


def _chapa_lig(nome, t, aco, borda, n_borda=1):
    a = _aco(aco)
    return {"nome": nome, "t": t / 10.0, "fu": a.fu, "fy": a.fy, "borda": borda / 10.0, "n_borda": n_borda}


# ------------------------------------------------------------------ terças

def _g_cadeirinha(p):
    B, H, t = _num(p["largura"]), _num(p["altura"]), _num(p["t"])
    bl, bb, bt = _num(p["base_l"]), _num(p["base_b"]), _num(p["base_t"])
    gv, gh = _num(p["gab_v"]), _num(p["gab_h"])
    d = d_parafuso_mm(p["parafuso"])
    w, c = furo_mm(p["parafuso"]), furo_mm(p["parafuso"]) + 12.0
    n = int(p["n_parafusos"])
    ys = [H - _num(p["borda_topo"]) - i * gv for i in range(2 if n >= 4 else 1)] if n > 1 else [H - _num(p["borda_topo"])]
    xs = [B / 2 - gh / 2, B / 2 + gh / 2] if n >= 2 else [B / 2]
    furos = [(x, y) for y in ys for x in xs][:n]
    s = Svg()
    s.origem(0, 0, h=max(B, H) * 0.075)
    s.titulo(0, H + s.h * 4.2, "VISTA FRONTAL")
    s.ret(-(bl - B) / 2, -bt, bl, bt, "aco2")                     # base (vista de topo não: corte)
    s.ret(0, 0, B, H)
    for x, y in furos:
        s.oblongo(x, y, w, c, horizontal=p["oblongo"] == "horizontal")
    s.solda(0, 0, B, 0, perna=_num(p["perna"]))
    s.cota(0, 0, B, 0, -s.h * 2.6)
    s.cota(B, 0, B, H, -s.h * 2.0)
    if len(xs) == 2:
        s.cota(xs[0], H, xs[1], H, s.h * 1.6)
    if len(ys) == 2:
        s.cota(0, ys[1], 0, ys[0], s.h * 1.6)
    s.cota(0, ys[0], 0, H, s.h * 1.6 if len(ys) < 2 else s.h * 3.4)
    # lateral: o L da cadeirinha (base deitada, chapa em pé) sobre o banzo
    ox = B + max(bl, 120) * 0.9 + s.h * 6
    s.origem(ox, 0)
    s.titulo(0, H + s.h * 4.2, "VISTA LATERAL")
    s.ret(-bb / 2, -bt, bb, bt, "aco2")
    s.ret(-t / 2, 0, t, H)
    s.ret(-bb / 2 - 20, -bt - 60, bb + 40, 60, "oculta")          # banzo da tesoura
    s.texto(bb / 2 + 26, -bt - 40, "banzo", "rot")
    s.solda(-t / 2, 0, -t / 2 - 1, 0, perna=_num(p["perna"]))
    s.cota(-bb / 2, -bt, bb / 2, -bt, -s.h * 5.2)
    pecas = [peca_chapa("Chapa do suporte (em pé)", B, H, t, 1, oblongos=[(w, c)] * n, aco=p["aco"]),
             peca_chapa("Base do suporte (soldada no banzo)", bl, bb, bt, 1, aco=p["aco"]),
             peca_fixador("parafuso", "Parafuso %s × %d %s com porca e arruela" % (
                 p["parafuso"], comprimento_parafuso(t + _num(p["t_terca"]), d), p["classe"]), n)]
    notas = ["Furação da fábrica: %s mm na vertical × %s mm na horizontal (terça abaixo de 200 mm: 50×60; a partir de 200: 100×60)."
             % (fmt(gv, 0), fmt(gh, 0)), "Solda de filete da chapa em pé na base, dos dois lados; a base vai soldada no banzo."]
    return pecas, s.render(), notas


def _v_cadeirinha(p, e):
    r = Resultado("Suporte de terça (cadeirinha)")
    n = int(p["n_parafusos"])
    linhas, colunas = (2, 2) if n >= 4 else (1, n)
    R = _num(e.get("R_Sd"))
    H = _num(e.get("H_Sd"))
    chapas = [_chapa_lig("chapa do suporte", _num(p["t"]), p["aco"], _num(p["borda_topo"])),
              _chapa_lig("alma da terça", _num(p["t_terca"]), "CIVIL 300", 25.0)]
    _grupo(r, p["parafuso"], p["classe"], linhas, colunas, _num(p["gab_v"]), _num(p["gab_h"]), chapas,
           V=R, N=H, furo=tipo_furo(p["parafuso"], furo_mm(p["parafuso"]) + 12.0) if p.get("oblongo") else "padrão",
           elemento="Parafusos da terça")
    _filete(r, _num(p["perna"]), _num(p["largura"]), math.hypot(R, H), 2, _num(p["t"]), "Solda da chapa na base")
    _filete(r, _num(p["perna"]), _num(p["base_l"]), math.hypot(R, H), 2, _num(p["base_t"]), "Solda da base no banzo")
    return r


_registrar(Tipo(
    "suporte_terca_cadeirinha", "Suporte de terça (cadeirinha)", "tercas",
    "Chapa em pé com os furos da terça, soldada numa base deitada que vai soldada no banzo superior da "
    "tesoura. É o suporte que a Sooro usa em toda a cobertura (chapa 150×145×5 com 4 oblongos 13×25 e base 153×44×3).",
    [Param("largura", "Largura da chapa", "mm", 150), Param("altura", "Altura da chapa", "mm", 145),
     Param("t", "Espessura da chapa", "mm", 4.75, BITOLAS_CHAPA),
     Param("base_l", "Comprimento da base", "mm", 153), Param("base_b", "Largura da base", "mm", 44),
     Param("base_t", "Espessura da base", "mm", 3.0, BITOLAS_CHAPA),
     Param("n_parafusos", "Parafusos", "", 4, [2, 4]), Param("parafuso", "Diâmetro", "", "M12", PARAFUSOS),
     Param("classe", "Classe do parafuso", "", "ASTM A307", CLASSES),
     Param("gab_v", "Gabarito vertical", "mm", 50, None, "fábrica: 50 mm (terça < 200 mm) ou 100 mm"),
     Param("gab_h", "Gabarito horizontal", "mm", 60), Param("borda_topo", "Furo à borda de cima", "mm", 30),
     Param("oblongo", "Oblongo", "", "horizontal", ["horizontal", "vertical", ""], "furo alongado para a montagem"),
     Param("t_terca", "Espessura da terça", "mm", 2.25), Param("perna", "Perna da solda", "mm", 4),
     Param("aco", "Aço das chapas", "", "ASTM A36", ACOS_CHAPA)],
    [Param("R_Sd", "Reação da terça (normal ao telhado)", "kN", 6.0),
     Param("H_Sd", "Componente no plano do telhado", "kN", 0.6)],
    _g_cadeirinha, _v_cadeirinha, "obras Sooro (CH1, CH2)", "Toda terça sobre tesoura; uma por cruzamento terça × tesoura."))


def _g_chapa_simples_terca(p):
    L, B, t = _num(p["comprimento"]), _num(p["altura"]), _num(p["t"])
    n = int(p["n_parafusos"])
    g = _num(p["gabarito"])
    d = d_parafuso_mm(p["parafuso"])
    fd = furo_mm(p["parafuso"])
    xs = [L / 2 + (i - (n - 1) / 2) * g for i in range(n)]
    y = B - _num(p["borda_topo"])
    s = Svg(); s.origem(0, 0, h=max(L, B) * 0.06)
    s.titulo(0, B + s.h * 4.2, "VISTA FRONTAL")
    s.ret(0, 0, L, B)
    for x in xs:
        s.circ(x, y, fd / 2)
    s.solda(0, 0, L, 0, perna=_num(p["perna"]))
    s.cota(0, 0, L, 0, -s.h * 2.4)
    s.cota(L, 0, L, B, -s.h * 2.0)
    if n > 1:
        s.cota(xs[0], B, xs[-1], B, s.h * 1.6)
    s.cota(0, y, 0, B, s.h * 1.8)
    pecas = [peca_chapa("Chapa do suporte", L, B, t, 1, furos=[fd] * n, aco=p["aco"]),
             peca_fixador("parafuso", "Parafuso %s × %d %s com porca e arruela" % (
                 p["parafuso"], comprimento_parafuso(t + _num(p["t_terca"]), d), p["classe"]), n)]
    return pecas, s.render(), ["Chapa soldada de topo no banzo (ou no console), a terça parafusada pela alma."]


def _v_chapa_simples_terca(p, e):
    r = Resultado("Suporte de terça em chapa")
    n = int(p["n_parafusos"])
    chapas = [_chapa_lig("chapa do suporte", _num(p["t"]), p["aco"], _num(p["borda_topo"])),
              _chapa_lig("alma da terça", _num(p["t_terca"]), "CIVIL 300", 25.0)]
    _grupo(r, p["parafuso"], p["classe"], 1, n, 50.0, _num(p["gabarito"]), chapas, V=_num(e.get("R_Sd")),
           N=_num(e.get("H_Sd")), elemento="Parafusos da terça")
    _filete(r, _num(p["perna"]), _num(p["comprimento"]), math.hypot(_num(e.get("R_Sd")), _num(e.get("H_Sd"))), 2,
            _num(p["t"]), "Solda da chapa no apoio")
    return r


_registrar(Tipo(
    "suporte_terca_chapa", "Suporte de terça em chapa simples", "tercas",
    "Chapa em pé soldada de topo, com a terça parafusada pela alma. Na Sooro: 270×120×6,3 com 2 furos Ø17 (M16) "
    "nos beirais e 220×130×9,5 com 4 furos Ø17 nas terças W.",
    [Param("comprimento", "Comprimento", "mm", 270), Param("altura", "Altura", "mm", 120),
     Param("t", "Espessura", "mm", 6.35, BITOLAS_CHAPA), Param("n_parafusos", "Parafusos", "", 2, [1, 2, 3, 4]),
     Param("parafuso", "Diâmetro", "", "M16", PARAFUSOS), Param("classe", "Classe", "", "ASTM A307", CLASSES),
     Param("gabarito", "Passo entre furos", "mm", 100), Param("borda_topo", "Furo à borda de cima", "mm", 40),
     Param("t_terca", "Espessura da alma da terça", "mm", 4.3), Param("perna", "Perna da solda", "mm", 5),
     Param("aco", "Aço", "", "ASTM A36", ACOS_CHAPA)],
    [Param("R_Sd", "Reação da terça", "kN", 8.0), Param("H_Sd", "Componente no plano do telhado", "kN", 1.0)],
    _g_chapa_simples_terca, _v_chapa_simples_terca, "obras Sooro (CH3, CH4)", "Terça de beiral, terça de perfil W, apoio em console."))


def _g_suporte_cantoneira(p):
    perfil = p["cantoneira"]
    L = _num(p["comprimento"])
    aba = _aba_cantoneira(perfil)
    n = int(p["n_parafusos"]); g = _num(p["gabarito"])
    fd = furo_mm(p["parafuso"])
    s = Svg(); s.origem(0, 0, h=max(L, aba) * 0.07)
    s.titulo(0, aba + s.h * 4.2, "VISTA FRONTAL (aba com furos)")
    s.ret(0, 0, L, aba)
    xs = [L / 2 + (i - (n - 1) / 2) * g for i in range(n)]
    for x in xs:
        s.circ(x, aba / 2 + 5, fd / 2)
    s.solda(0, 0, L, 0)
    s.cota(0, 0, L, 0, -s.h * 2.4)
    s.cota(L, 0, L, aba, -s.h * 2)
    if n > 1:
        s.cota(xs[0], aba, xs[-1], aba, s.h * 1.6)
    pecas = [peca_barra("Cantoneira do suporte", perfil, L, 1),
             peca_fixador("parafuso", "Parafuso %s %s com porca e arruela" % (p["parafuso"], p["classe"]), n)]
    return pecas, s.render(), ["Uma aba soldada no banzo (ou no pilar, para longarina); a outra recebe a alma da terça."]


def _aba_cantoneira(perfil: str) -> float:
    from nucleo import perfis_fabrica as pf, catalogo
    q = pf.perfil_de_fabrica(perfil) or catalogo.perfil_de(perfil)
    return float(getattr(q, "b", None) or getattr(q, "bf", None) or getattr(q, "d", 0) or 63.5)


def _v_suporte_cantoneira(p, e):
    r = Resultado("Suporte de terça em cantoneira")
    from nucleo import perfis_fabrica as pf, catalogo
    q = pf.perfil_de_fabrica(p["cantoneira"]) or catalogo.perfil_de(p["cantoneira"])
    t = float(getattr(q, "t", 0) or getattr(q, "tw", 0) or 6.35) if q else 6.35
    chapas = [_chapa_lig("aba da cantoneira", t if t > 1 else t * 10, "ASTM A36", 25.0),
              _chapa_lig("alma da terça", _num(p["t_terca"]), "CIVIL 300", 25.0)]
    _grupo(r, p["parafuso"], p["classe"], 1, int(p["n_parafusos"]), 50.0, _num(p["gabarito"]), chapas,
           V=_num(e.get("R_Sd")), elemento="Parafusos da terça")
    _filete(r, _num(p["perna"]), _num(p["comprimento"]), _num(e.get("R_Sd")), 2, t if t > 1 else t * 10, "Solda da cantoneira")
    return r


_registrar(Tipo(
    "suporte_terca_cantoneira", "Suporte de terça (ou longarina) em cantoneira", "tercas",
    "Pedaço de cantoneira soldado no banzo (terça) ou no pilar (longarina), com a terça parafusada pela alma. "
    "Mais rápido de fabricar que a cadeirinha quando a reação é pequena.",
    [Param("cantoneira", "Cantoneira", "", "L 2 1/2'' X 1/4''", ["L 2 1/2'' X 1/4''", "L 2'' X 3/16''", "L 3'' X 1/4''"]),
     Param("comprimento", "Comprimento", "mm", 150), Param("n_parafusos", "Parafusos", "", 2, [1, 2]),
     Param("parafuso", "Diâmetro", "", "M12", PARAFUSOS), Param("classe", "Classe", "", "ASTM A307", CLASSES),
     Param("gabarito", "Passo", "mm", 60), Param("t_terca", "Espessura da alma da terça", "mm", 2.25),
     Param("perna", "Perna da solda", "mm", 4)],
    [Param("R_Sd", "Reação da terça", "kN", 4.0)],
    _g_suporte_cantoneira, _v_suporte_cantoneira, "galpão / obras Sooro (CH16, CH17 nos contraventos)",
    "Terças leves, longarinas de fechamento no pilar."))


def _g_emenda_terca(p):
    t = _num(p["transpasse"]); h = _num(p["altura_terca"])
    n = int(p["n_parafusos"]); gv = _num(p["gab_v"])
    fd = furo_mm(p["parafuso"])
    s = Svg(); s.origem(0, 0, h=max(t * 2.2, h) * 0.05)
    s.titulo(-t, h / 2 + s.h * 2.4, "VISTA LATERAL (sobre o apoio)")
    s.ret(-t, -h / 2, 2 * t + 300, h, "oculta")
    s.ret(-t - 300, -h / 2 + 2, 2 * t + 300, h - 4)
    s.linha(0, -h / 2 - 40, 0, h / 2 + 40, "eixo")
    for x in (-t / 2, t / 2):
        for y in ((-gv / 2, gv / 2) if n >= 4 else (0.0,)):
            s.circ(x, y, fd / 2)
    s.cota(-t, -h / 2, t, -h / 2, -s.h * 2.4, fmt(2 * t, 0))
    s.texto(0, -h / 2 - s.h * 5, "eixo da tesoura", "rot", "middle")
    pecas = [peca_fixador("parafuso", "Parafuso %s %s com porca e arruela" % (p["parafuso"], p["classe"]), n)]
    return pecas, s.render(), ["Transpasse das duas terças sobre o apoio: a terça fica contínua (momento negativo no apoio) — calcule como contínua ou como biapoiada, não misture."]


def _v_emenda_terca(p, e):
    r = Resultado("Emenda de terça por transpasse")
    n = int(p["n_parafusos"])
    chapas = [_chapa_lig("alma da terça", _num(p["t_terca"]), "CIVIL 300", 30.0)]
    _grupo(r, p["parafuso"], p["classe"], 2 if n >= 4 else 1, 2, _num(p["gab_v"]), _num(p["transpasse"]), chapas,
           V=_num(e.get("V_Sd")), M=_num(e.get("M_Sd")) * 100.0, elemento="Parafusos do transpasse")
    return r


_registrar(Tipo(
    "emenda_terca", "Emenda de terça por transpasse", "tercas",
    "As duas terças se sobrepõem sobre o apoio e são parafusadas pela alma. Dá continuidade e reduz o momento no vão.",
    [Param("transpasse", "Meio transpasse (de cada lado do apoio)", "mm", 300), Param("altura_terca", "Altura da terça", "mm", 150),
     Param("n_parafusos", "Parafusos", "", 4, [2, 4]), Param("parafuso", "Diâmetro", "", "M12", PARAFUSOS),
     Param("classe", "Classe", "", "ASTM A307", CLASSES), Param("gab_v", "Gabarito vertical", "mm", 50),
     Param("t_terca", "Espessura da alma", "mm", 2.25)],
    [Param("V_Sd", "Cortante no apoio", "kN", 6.0), Param("M_Sd", "Momento no apoio", "kN·m", 3.0)],
    _g_emenda_terca, _v_emenda_terca, "prática de fábrica", "Terças contínuas sobre as tesouras."))


# ------------------------------------------------------------------ correntes

def _g_agulhamento(p):
    L = _num(p["comprimento"]); perfil = p["cantoneira"]
    B, H, t = _num(p["chapa_l"]), _num(p["chapa_b"]), _num(p["chapa_t"])
    w, c = furo_mm(p["parafuso"]), furo_mm(p["parafuso"]) + 12.0
    g = _num(p["gabarito"])
    s = Svg(); s.origem(0, 0, h=max(L, 300) * 0.04)
    s.titulo(0, H + s.h * 4.2, "AGULHAMENTO (vista de cima)")
    s.ret(0, H / 2 - 16, L, 32)
    for x0 in (-B + 20, L - 20):
        s.ret(x0, 0, B, H, "aco2")
        for x in (x0 + B / 2 - g / 2, x0 + B / 2 + g / 2):
            s.oblongo(x, H / 2, w, c, horizontal=True)
    s.cota(0, 0, L, 0, -s.h * 2.4)
    s.cota(-B + 20, H, 20, H, s.h * 1.6)
    pecas = [peca_barra("Agulha (cantoneira)", perfil, L, 1),
             peca_chapa("Chapinha de ponta", B, H, t, 2, oblongos=[(w, c)] * 2, aco="ASTM A36"),
             peca_fixador("parafuso", "Parafuso %s × %d %s" % (p["parafuso"], comprimento_parafuso(t + 2.25, d_parafuso_mm(p["parafuso"])), p["classe"]), 4)]
    notas = ["A agulha trava a mesa inferior da terça (e passa a carga da água para a cumeeira). Na Sooro: L1.1/4\"×1/8\" com chapinhas 130×50×3."]
    try:
        from nucleo import perfis_fabrica as pf, catalogo
        q = pf.perfil_de_fabrica(perfil) or catalogo.perfil_de(perfil)
        rmin = getattr(q, "rmin", None) or min(x for x in (getattr(q, "ry", None), getattr(q, "rx", None)) if x)
        if L / 10.0 / rmin > 200:
            notas.append("Com %s mm, a %s passa do limite de esbeltez L/r = 200 da barra comprimida (NBR 8800, item 5.3.4): "
                         "só vale como tirante (a linha do outro lado da terça é a que comprime), ou use cantoneira maior." % (fmt(L, 0), perfil))
    except Exception:                                   # noqa: BLE001
        pass
    return pecas, s.render(), notas


def _v_agulhamento(p, e):
    from nucleo import nbr8800, perfis_fabrica as pf, catalogo
    r = Resultado("Agulhamento (corrente rígida)")
    N = _num(e.get("N_Sd"))
    q = pf.perfil_de_fabrica(p["cantoneira"]) or catalogo.perfil_de(p["cantoneira"])
    try:
        c = nbr8800.compressao(q, "ASTM A36", _num(p["comprimento"]) / 10.0, N_Sd=N, cantoneira_simplificada=True,
                               elemento="Agulha comprimida")
        for v in c.verificacoes:
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada("compressão da agulha: %s" % exc_))
    chapas = [_chapa_lig("chapinha", _num(p["chapa_t"]), "ASTM A36", 20.0), _chapa_lig("alma da terça", 2.25, "CIVIL 300", 25.0)]
    _grupo(r, p["parafuso"], p["classe"], 1, 2, 50.0, _num(p["gabarito"]), chapas, V=N,
           furo=tipo_furo(p["parafuso"], furo_mm(p["parafuso"]) + 12.0), elemento="Parafusos de uma ponta")
    return r


_registrar(Tipo(
    "agulhamento_rigido", "Agulhamento (corrente rígida)", "correntes",
    "Cantoneira entre duas terças, com uma chapinha soldada em cada ponta e dois parafusos em furo oblongo. "
    "Trava a terça contra a flambagem lateral e leva a componente da carga paralela ao telhado.",
    [Param("comprimento", "Comprimento da agulha", "mm", 1538), Param("cantoneira", "Cantoneira", "", "L1.1/4''X1/8''",
                                                                         ["L1.1/4''X1/8''", "L1.1/2''X1/8''", "L 2'' X 1/8''"]),
     Param("chapa_l", "Chapinha: comprimento", "mm", 130), Param("chapa_b", "Chapinha: largura", "mm", 50),
     Param("chapa_t", "Chapinha: espessura", "mm", 3.0, BITOLAS_CHAPA), Param("parafuso", "Diâmetro", "", "M12", PARAFUSOS),
     Param("classe", "Classe", "", "ASTM A307", CLASSES), Param("gabarito", "Passo dos furos", "mm", 60)],
    [Param("N_Sd", "Força na agulha", "kN", 2.0)],
    _g_agulhamento, _v_agulhamento, "obras Sooro (A.C.)", "Entre terças, no meio (ou nos terços) do vão."))


def _g_agulha_diagonal(p):
    L = _num(p["comprimento"]); d = DIAMETROS_BARRA[p["barra"]]
    g = _num(p["gancho"])
    s = Svg(); s.origem(0, 0, h=max(L, 300) * 0.04)
    s.titulo(0, 150 + s.h * 2.2, "AGULHAMENTO DIAGONAL")
    s.linha(0, 0, L, 0, "barra")
    s.poli([(L, 0), (L + g * 0.4, 0), (L + g * 0.4, g * 0.3)], "barra", fechada=False)
    s.ret(-40, -20, 40, 40, "aco2")
    s.cota(0, 0, L, 0, -s.h * 2.4)
    pecas = [peca_redonda("Agulha diagonal", d, L, 1), peca_redonda("Gancho", d, g, 1),
             peca_barra("Chapinha em cantoneira", "L1.1/2''X1/8''", 40, 1)]
    return pecas, s.render(), ["Ferro redondo 3/8\" com gancho numa ponta e uma cantoneirinha soldada na outra; trabalha só à tração."]


def _v_agulha_diagonal(p, e):
    from nucleo import nbr8800
    from nucleo3d import geometria
    r = Resultado("Agulhamento diagonal")
    d = DIAMETROS_BARRA[p["barra"]]
    try:
        t = nbr8800.tracao(geometria.barra_redonda(d), "ASTM A36", N_Sd=_num(e.get("N_Sd")), L=_num(p["comprimento"]) / 10.0,
                           rosqueada=False, pretensionada=True, elemento="Agulha diagonal")
        for v in t.verificacoes:
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada(str(exc_)))
    _filete(r, 3.0, 40.0, _num(e.get("N_Sd")), 2, 3.0, "Solda da barra na cantoneirinha")
    return r


_registrar(Tipo(
    "agulhamento_diagonal", "Agulhamento diagonal (ferro com gancho)", "correntes",
    "Ferro redondo com gancho numa ponta e cantoneirinha soldada na outra, em diagonal entre as terças da "
    "cumeeira ou do beiral, para levar a componente paralela ao telhado.",
    [Param("comprimento", "Comprimento", "mm", 2184), Param("barra", "Barra", "", '3/8"', list(DIAMETROS_BARRA)),
     Param("gancho", "Gancho (desenvolvido)", "mm", 250)],
    [Param("N_Sd", "Tração", "kN", 3.0)],
    _g_agulha_diagonal, _v_agulha_diagonal, "obras Sooro (A.D., G.1)", "Linhas de agulhamento junto da cumeeira."))


def _g_corrente_roscada(p):
    L = _num(p["comprimento"]); d = DIAMETROS_BARRA[p["barra"]]
    r = _num(p["rosca"])
    s = Svg(); s.origem(0, 0, h=max(L, 300) * 0.04)
    s.titulo(0, 60 + s.h * 2.2, "CORRENTE ROSCADA")
    s.ret(0, -d / 2, L, d)
    for x0 in (0, L - r):
        s.ret(x0, -d / 2 - 2, r, d + 4, "rosca")
    for x in (r * 0.5, L - r * 0.5):
        s.ret(x - 8, -d, 16, 2 * d, "aco2")
    s.cota(0, -d, L, -d, -s.h * 2.4)
    s.cota(0, d, r, d, s.h * 1.6)
    pecas = [peca_redonda("Corrente (rosca nas pontas)", d, L, 1),
             peca_fixador("porca", "Porca %s" % p["barra"], 4), peca_fixador("arruela", "Arruela %s" % p["barra"], 4)]
    return pecas, s.render(), ["Atravessa a alma das terças; duas porcas de cada lado prendem a terça na posição."]


def _v_corrente_roscada(p, e):
    from nucleo import nbr8800
    from nucleo3d import geometria
    r = Resultado("Corrente roscada")
    try:
        t = nbr8800.tracao(geometria.barra_redonda(DIAMETROS_BARRA[p["barra"]]), "ASTM A36", N_Sd=_num(e.get("N_Sd")),
                           L=_num(p["comprimento"]) / 10.0, rosqueada=True, pretensionada=True, elemento="Corrente")
        for v in t.verificacoes:
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada(str(exc_)))
    return r


_registrar(Tipo(
    "corrente_roscada", "Corrente de barra redonda roscada", "correntes",
    "Barra redonda com rosca nas pontas que atravessa as terças, presa com porcas. É a corrente do galpão paramétrico.",
    [Param("comprimento", "Comprimento", "mm", 1600), Param("barra", "Barra", "", "Ø16", list(DIAMETROS_BARRA)),
     Param("rosca", "Rosca em cada ponta", "mm", 60)],
    [Param("N_Sd", "Tração", "kN", 4.0)],
    _g_corrente_roscada, _v_corrente_roscada, "galpão", "Correntes entre terças, fechando na cumeeira."))


# ------------------------------------------------------------------ contraventamento

def _g_contravento(p):
    L = _num(p["comprimento"]); d = DIAMETROS_BARRA[p["tirante"]]; dr = DIAMETROS_BARRA[p["rosca"]]
    lr = _num(p["barra_roscada"])
    cL, cB, ct = _num(p["castanha_l"]), _num(p["castanha_b"]), _num(p["castanha_t"])
    fd = furo_mm(p["parafuso"])
    fr = round(dr + 1.5, 1)
    s = Svg(); s.origem(0, 0, h=260 * 0.06)
    s.titulo(-60, 150, "PONTA DO TIRANTE")
    s.ret(-cL, -cB / 2, cL, cB, "aco2")                           # castanha
    s.circ(-cL + 30, 0, fd / 2)
    s.ret(0, -dr / 2, lr, dr, "rosca")                            # barra roscada
    s.ret(lr - 60, -d / 2, 260, d)                                 # tirante soldado
    for x in (18, 36):
        s.ret(x - 6, -40, 12, 80, "aco2")                          # chapas 80×80 e porcas
    s.solda(lr - 60, d / 2, lr, d / 2, perna=4)
    s.cota(-cL, -cB / 2, 0, -cB / 2, -s.h * 2.2)
    s.cota(0, -40, lr, -40, -s.h * 3.6)
    s.texto(-cL, cB / 2 + s.h * 0.8, "castanha %s×%s×%s" % (fmt(cL, 0), fmt(cB, 0), fmt(ct, 2)), "rot")
    s.texto(lr + 80, d / 2 + s.h * 0.8, "tirante %s" % p["tirante"], "rot")
    pecas = [peca_redonda("Tirante", d, L, 1), peca_redonda("Barra roscada (nas duas pontas)", dr, lr, 2),
             peca_chapa("Castanha (gusset)", cL, cB, ct, 2, furos=[fd], aco="ASTM A36"),
             peca_chapa("Chapa-arruela", 80, 80, 8, 4, furos=[fr], aco="ASTM A36"),
             peca_barra("Cantoneira de apoio da castanha", "L 2 1/2'' X 1/4''", 200, 2),
             peca_fixador("parafuso", "Parafuso %s %s (castanha na cantoneira)" % (p["parafuso"], p["classe"]), 2),
             peca_fixador("porca", "Porca %s (esticar e travar)" % p["rosca"], 8)]
    notas = ["Montagem da Sooro: o tirante liso vai soldado na barra roscada, que atravessa as chapas-arruela na castanha; as porcas esticam o X.",
             "Contravento só trabalha à tração: o X tem sempre uma diagonal ativa."]
    return pecas, s.render(), notas


def _v_contravento(p, e):
    from nucleo import nbr8800, ligacoes as lig
    from nucleo3d import geometria
    r = Resultado("Contraventamento em X (tirante)")
    N = _num(e.get("N_Sd"))
    d = DIAMETROS_BARRA[p["tirante"]]; dr = DIAMETROS_BARRA[p["rosca"]]
    try:
        for v in nbr8800.tracao(geometria.barra_redonda(d), "ASTM A36", N_Sd=N, L=_num(p["comprimento"]) / 10.0,
                                rosqueada=False, pretensionada=True, elemento="Tirante").verificacoes:
            r.add(v)
        for v in nbr8800.tracao(geometria.barra_redonda(dr), "ASTM A36", N_Sd=N, L=_num(p["barra_roscada"]) / 10.0,
                                rosqueada=True, pretensionada=True, elemento="Barra roscada").verificacoes:
            v.titulo = "Barra roscada — " + v.titulo
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada(str(exc_)))
    _filete(r, 5.0, 60.0, N, 2, dr, "Solda do tirante na barra roscada")
    try:
        r.add(lig.cisalhamento_parafuso(p["parafuso"], p["classe"], planos=1, Fv_Sd=N))
        a = _aco("ASTM A36")
        r.add(lig.esmagamento(p["parafuso"], _num(p["castanha_t"]) / 10.0, a.fu, distancia_borda=3.0, Fc_Sd=N,
                              nome_chapa="castanha"))
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada(str(exc_)))
    return r


_registrar(Tipo(
    "contravento_tirante", "Contraventamento em X com tirante e castanha", "contraventamento",
    "O conjunto de contravento da Sooro: tirante FE RED 1/2\" soldado em barra roscada 5/8\", que atravessa chapas-"
    "arruela 80×80×8 na castanha 200×76×6,3; a castanha parafusada (M16) numa cantoneira L 2½\"×¼\" soldada no banzo.",
    [Param("comprimento", "Comprimento do tirante", "mm", 5300), Param("tirante", "Tirante", "", '1/2"', list(DIAMETROS_BARRA)),
     Param("rosca", "Barra roscada", "", '5/8"', list(DIAMETROS_BARRA)), Param("barra_roscada", "Comprimento da barra roscada", "mm", 230),
     Param("castanha_l", "Castanha: comprimento", "mm", 200), Param("castanha_b", "Castanha: largura", "mm", 76),
     Param("castanha_t", "Castanha: espessura", "mm", 6.35, BITOLAS_CHAPA), Param("parafuso", "Parafuso da castanha", "", "M16", PARAFUSOS),
     Param("classe", "Classe", "", "ASTM A307", CLASSES)],
    [Param("N_Sd", "Tração no tirante", "kN", 15.0)],
    _g_contravento, _v_contravento, "obras Sooro (CV, CH castanha, BR1)", "X de cobertura e de parede nos vãos contraventados."))


def _g_esticador(p):
    L = _num(p["comprimento"]); d = DIAMETROS_BARRA[p["tirante"]]
    s = Svg(); s.origem(0, 0, h=max(L, 600) * 0.03)
    s.titulo(0, 120, "TIRANTE COM ESTICADOR")
    s.linha(0, 0, L / 2 - 80, 0, "barra"); s.linha(L / 2 + 80, 0, L, 0, "barra")
    s.ret(L / 2 - 80, -d * 1.2, 160, d * 2.4, "aco2")
    s.circ(-20, 0, 20, "aco"); s.circ(L + 20, 0, 20, "aco")
    s.cota(0, -d * 2, L, -d * 2, -s.h * 2)
    pecas = [peca_redonda("Tirante (rosca direita e esquerda)", d, L, 1),
             peca_fixador("esticador", "Esticador (tensor) %s" % p["tirante"], 1),
             peca_fixador("olhal", "Olhal ou garfo %s" % p["tirante"], 2)]
    return pecas, s.render(), ["Alternativa ao conjunto de castanha: o esticador no meio dá o aperto, os olhais nas pontas vão a um gusset."]


_registrar(Tipo(
    "contravento_esticador", "Tirante com esticador", "contraventamento",
    "Tirante em duas metades unidas por esticador (tensor), com olhal ou garfo nas pontas presos a um gusset.",
    [Param("comprimento", "Comprimento", "mm", 6000), Param("tirante", "Tirante", "", '5/8"', list(DIAMETROS_BARRA))],
    [Param("N_Sd", "Tração", "kN", 15.0)],
    _g_esticador, lambda p, e: _v_corrente_roscada({"barra": p["tirante"], "comprimento": p["comprimento"]}, e),
    "prática de mercado", "Contravento de parede e de cobertura com ajuste fino."))


def _g_gusset(p):
    L, B, t = _num(p["comprimento"]), _num(p["altura"]), _num(p["t"])
    n = int(p["n_parafusos"]); fd = furo_mm(p["parafuso"]); pas = _num(p["passo"])
    s = Svg(); s.origem(0, 0, h=max(L, B) * 0.06)
    s.titulo(0, B + s.h * 2.2, "CHAPA GUSSET")
    s.poli([(0, 0), (L, 0), (L, B * 0.45), (L * 0.35, B), (0, B)])
    ang = math.radians(float(p.get("angulo") or 40))
    cx, cy = L * 0.45, B * 0.45
    for i in range(n):
        s.circ(cx + math.cos(ang) * i * pas, cy + math.sin(ang) * i * pas, fd / 2)
    s.solda(0, 0, L, 0); s.solda(0, 0, 0, B)
    s.cota(0, 0, L, 0, -s.h * 2.2); s.cota(L, 0, L, B, -s.h * 2.2)
    pecas = [peca_chapa("Gusset", L, B, t, 1, furos=[fd] * n, aco=p["aco"]),
             peca_fixador("parafuso", "Parafuso %s %s" % (p["parafuso"], p["classe"]), n)]
    return pecas, s.render(), ["Verificação pela seção de Whitmore (30°), bloco de cisalhamento e solda."]


def _v_gusset(p, e):
    from nucleo import ligacoes as lig
    try:
        return lig.gusset_contraventamento(_num(e.get("N_Sd")), _num(p["t"]) / 10.0, _num(p["largura_barra"]) / 10.0,
                                           (int(p["n_parafusos"]) - 1) * _num(p["passo"]) / 10.0, aco_gusset=p["aco"],
                                           diametro=p["parafuso"], parafuso=p["classe"], n_parafusos=int(p["n_parafusos"]),
                                           passo=_num(p["passo"]) / 10.0, comprimento_solda=(_num(p["comprimento"]) + _num(p["altura"])) / 10.0)
    except Exception as exc_:                           # noqa: BLE001
        r = Resultado("Gusset"); r.add(nao_verificada(str(exc_))); return r


_registrar(Tipo(
    "gusset_contravento", "Chapa gusset de contravento", "contraventamento",
    "Chapa soldada no pilar ou na viga que recebe a diagonal (cantoneira ou tirante com olhal) parafusada.",
    [Param("comprimento", "Comprimento", "mm", 250), Param("altura", "Altura", "mm", 220),
     Param("t", "Espessura", "mm", 8.0, BITOLAS_CHAPA), Param("n_parafusos", "Parafusos", "", 2, [1, 2, 3, 4]),
     Param("parafuso", "Diâmetro", "", "M16", PARAFUSOS), Param("classe", "Classe", "", "ASTM A325", CLASSES),
     Param("passo", "Passo", "mm", 55), Param("angulo", "Ângulo da diagonal", "°", 40),
     Param("largura_barra", "Largura da barra na ligação", "mm", 60), Param("aco", "Aço", "", "ASTM A36", ACOS_CHAPA)],
    [Param("N_Sd", "Força na diagonal", "kN", 40.0)],
    _g_gusset, _v_gusset, "NBR 8800 / galpão", "Contravento vertical (parede) e de cobertura em cantoneira."))


# ------------------------------------------------------------------ apoios e bases

def _g_apoio_concreto(p):
    L, B, t = _num(p["comprimento"]), _num(p["largura"]), _num(p["t"])
    dch = DIAMETROS_BARRA[p["chumbador"]]
    fd = _num(p["furo"]) or round(dch + 2.0)
    g = _num(p["gabarito"]); n = int(p["n_chumbadores"])
    Lc, gc = _num(p["comprimento_chumbador"]), _num(p["gancho"])
    xs = [L / 2 - g / 2, L / 2 + g / 2] if n == 2 else [L / 2 - g / 2, L / 2 + g / 2] * 2
    ys = [B / 2] if n == 2 else [B / 2 - _num(p["gabarito_b"]) / 2, B / 2 + _num(p["gabarito_b"]) / 2]
    s = Svg(); s.origem(0, 0, h=max(L, B) * 0.055)
    s.titulo(0, B + s.h * 4.2, "PLANTA DA CHAPA DE APOIO")
    s.ret(0, 0, L, B)
    for x in sorted(set(xs)):
        for y in ys:
            s.circ(x, y, fd / 2)
    s.linha(L / 2, -20, L / 2, B + 20, "eixo")
    s.cota(0, 0, L, 0, -s.h * 2.2)
    s.cota(L, 0, L, B, -s.h * 2)
    s.cota(sorted(set(xs))[0], B, sorted(set(xs))[-1], B, s.h * 1.6)
    ox = L + s.h * 8
    s.origem(ox, 0)
    s.titulo(0, B + s.h * 2.2, "CHUMBADOR")
    s.linha(0, B, 0, B - Lc * 0.25, "barra")
    s.poli([(0, B - Lc * 0.25), (0, B - Lc * 0.25 - 1)], "barra", fechada=False)
    s.texto(10, B - Lc * 0.12, "L = %s (gancho %s)" % (fmt(Lc, 0), fmt(gc, 0)), "rot")
    pecas = [peca_chapa("Chapa de apoio", L, B, t, 1, furos=[fd] * (len(set(xs)) * len(ys)), aco=p["aco"]),
             peca_redonda("Chumbador com gancho", dch, Lc + gc, len(set(xs)) * len(ys)),
             peca_fixador("porca", "Porca %s" % p["chumbador"], 2 * len(set(xs)) * len(ys), "dupla: nivelar e travar"),
             peca_fixador("arruela", "Arruela %s" % p["chumbador"], len(set(xs)) * len(ys))]
    return pecas, s.render(), ["Chapa de apoio da tesoura sobre pilar de concreto (Sooro: 400×120×12,7 com 2 furos Ø21 e chumbadores FE RED 3/4\" de 1 m)."]


def _v_apoio_concreto(p, e):
    from nucleo import bases
    n = int(p["n_chumbadores"])
    r = Resultado("Apoio da tesoura em pilar de concreto")
    try:
        c = bases.chumbadores(_num(e.get("T_Sd")), _num(e.get("H_Sd")), N_Sd=_num(e.get("R_Sd")), diametro=p["chumbador"],
                              n=n, fck=_num(p["fck"]) / 10.0, h_ef=_num(p["comprimento_chumbador"]) / 10.0,
                              espacamento=_num(p["gabarito"]) / 10.0, com_chapa_de_ancoragem=False)
        for v in c.verificacoes:
            r.add(v)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada("chumbadores: %s" % exc_))
    # pressão de contato no concreto
    A = _num(p["comprimento"]) * _num(p["largura"]) / 100.0          # cm²
    fcd = _num(p["fck"]) / 10.0 / 1.4 * 0.85
    R = _num(e.get("R_Sd"))
    v = Verificacao("Pressão da chapa no concreto", norma="NBR 8800, item 6.6.1", Sd=R / A if A else 0.0, Rd=fcd, unidade="kN/cm²")
    v.passo("Tensão de contato", "σ = R<sub>Sd</sub>/A", "%s / %s" % (fmt(R, 1), fmt(A, 0)), fmt(R / A if A else 0, 3, "kN/cm²"))
    v.passo("Resistência do concreto", "0,85·f<sub>ck</sub>/γ<sub>c</sub>", "0,85 × %s / 1,4" % fmt(_num(p["fck"]) / 10.0, 1),
            fmt(fcd, 3, "kN/cm²"), "NBR 6118")
    r.add(v)
    return r


_registrar(Tipo(
    "apoio_tesoura_concreto", "Apoio da tesoura em pilar de concreto", "apoios",
    "Chapa grossa soldada no banzo inferior (ou no montante de apoio) com os furos dos chumbadores deixados no "
    "topo do pilar de concreto. É o apoio das coberturas da Sooro.",
    [Param("comprimento", "Comprimento da chapa", "mm", 400), Param("largura", "Largura", "mm", 120),
     Param("t", "Espessura", "mm", 12.7, BITOLAS_CHAPA), Param("n_chumbadores", "Chumbadores", "", 2, [2, 4]),
     Param("chumbador", "Chumbador", "", '3/4"', list(DIAMETROS_BARRA)), Param("furo", "Furo na chapa", "mm", 21),
     Param("gabarito", "Distância entre chumbadores", "mm", 300), Param("gabarito_b", "Distância na largura (4 chumbadores)", "mm", 60),
     Param("comprimento_chumbador", "Comprimento dentro do concreto", "mm", 876, None, "Sooro: 996 mm, 120 mm acima do concreto"),
     Param("gancho", "Gancho", "mm", 250),
     Param("fck", "f<sub>ck</sub> do pilar", "MPa", 25), Param("aco", "Aço da chapa", "", "ASTM A36", ACOS_CHAPA)],
    [Param("R_Sd", "Reação vertical (compressão)", "kN", 40.0), Param("H_Sd", "Força horizontal", "kN", 8.0),
     Param("T_Sd", "Arrancamento (sucção)", "kN", 12.0)],
    _g_apoio_concreto, _v_apoio_concreto, "obras Sooro (CH9, CH11, CH13, CB)", "Cobertura metálica sobre pilares de concreto."))


def _g_placa_base(p, engastada=False):
    B, L, t = _num(p["B"]), _num(p["L"]), _num(p["t"])
    perfil = p["pilar"]
    from nucleo import catalogo
    q = catalogo.perfil_de(perfil)
    d = float(getattr(q, "d", 0) or 250); bf = float(getattr(q, "bf", 0) or 150)
    tf = float(getattr(q, "tf", 0) or 10); tw = float(getattr(q, "tw", 0) or 6)
    n = 4 if engastada else 2
    gB, gL = _num(p["gab_B"]), _num(p["gab_L"])
    dch = DIAMETROS_BARRA[p["chumbador"]]; fd = round(dch + 6.0)
    furos = [(B / 2 + sx * gB / 2, L / 2 + sy * gL / 2) for sx in (-1, 1) for sy in ((-1, 1) if engastada else (0,))]
    s = Svg(); s.origem(0, 0, h=max(B, L) * 0.05)
    s.titulo(0, L + s.h * 4.2, "PLANTA DA PLACA DE BASE")
    s.ret(0, 0, B, L)
    cx, cy = B / 2, L / 2
    s.poli([(cx - bf / 2, cy + d / 2), (cx + bf / 2, cy + d / 2), (cx + bf / 2, cy + d / 2 - tf), (cx + tw / 2, cy + d / 2 - tf),
            (cx + tw / 2, cy - d / 2 + tf), (cx + bf / 2, cy - d / 2 + tf), (cx + bf / 2, cy - d / 2), (cx - bf / 2, cy - d / 2),
            (cx - bf / 2, cy - d / 2 + tf), (cx - tw / 2, cy - d / 2 + tf), (cx - tw / 2, cy + d / 2 - tf), (cx - bf / 2, cy + d / 2 - tf)],
           "oculta")
    for x, y in furos:
        s.circ(x, y, fd / 2)
    s.linha(cx, -20, cx, L + 20, "eixo"); s.linha(-20, cy, B + 20, cy, "eixo")
    s.cota(0, 0, B, 0, -s.h * 2.4); s.cota(B, 0, B, L, -s.h * 2.2)
    s.cota(furos[0][0], L, furos[-1][0], L, s.h * 1.6)
    if engastada:
        s.cota(0, furos[0][1], 0, furos[1][1], s.h * 1.8)
    pecas = [peca_chapa("Placa de base", B, L, t, 1, furos=[fd] * n, aco=p["aco"]),
             peca_redonda("Chumbador", dch, _num(p["comprimento_chumbador"]), n),
             peca_fixador("porca", "Porca %s" % p["chumbador"], 2 * n), peca_fixador("arruela", "Arruela de chapa %s" % p["chumbador"], n)]
    notas = ["Furo da placa com folga de 6 mm (montagem sobre chumbador concretado); arruela de chapa soldada em campo.",
             "Grout de 30 mm entre a placa e o topo do bloco."]
    return pecas, s.render(), notas


def _v_placa_base(p, e, engastada=False):
    from nucleo import bases, catalogo
    q = catalogo.perfil_de(p["pilar"])
    try:
        return bases.dimensionar_base(q, _num(e.get("N_Sd")), M_Sd=_num(e.get("M_Sd")) * 100.0, H_Sd=_num(e.get("H_Sd")),
                                      N_Sd_min=_num(e.get("N_min")) if e.get("N_min") not in (None, "") else None,
                                      fck=_num(p["fck"]) / 10.0, diametro_chumbador=p["chumbador"],
                                      n_chumbadores=4 if engastada else 2, B=_num(p["B"]) / 10.0, L=_num(p["L"]) / 10.0,
                                      pedestal=(_num(p["pedestal_B"]) / 10.0, _num(p["pedestal_L"]) / 10.0),
                                      h_ef=_num(p["comprimento_chumbador"]) / 10.0)
    except Exception as exc_:                           # noqa: BLE001
        r = Resultado("Placa de base"); r.add(nao_verificada(str(exc_))); return r


_PARAMS_BASE = [Param("pilar", "Pilar", "", "W 250×32,7"), Param("B", "Placa: largura (fora do plano)", "mm", 300),
                Param("L", "Placa: comprimento (no plano do pórtico)", "mm", 450), Param("t", "Espessura", "mm", 25.4, BITOLAS_CHAPA),
                Param("chumbador", "Chumbador", "", '3/4"', list(DIAMETROS_BARRA)), Param("gab_B", "Gabarito na largura", "mm", 180),
                Param("gab_L", "Gabarito no comprimento", "mm", 340), Param("comprimento_chumbador", "Comprimento do chumbador", "mm", 600),
                Param("fck", "f<sub>ck</sub> do bloco", "MPa", 25), Param("aco", "Aço da placa", "", "ASTM A36", ACOS_CHAPA),
                Param("pedestal_B", "Bloco: largura", "mm", 600), Param("pedestal_L", "Bloco: comprimento", "mm", 800)]

_registrar(Tipo(
    "placa_base_rotulada", "Placa de base rotulada (2 chumbadores)", "apoios",
    "Pilar sobre placa com dois chumbadores no eixo: transmite compressão, tração e cortante, mas não momento.",
    _PARAMS_BASE, [Param("N_Sd", "Compressão", "kN", 80.0), Param("H_Sd", "Cortante", "kN", 15.0),
                   Param("N_min", "Tração (sucção, negativo)", "kN", -20.0)],
    lambda p: _g_placa_base(p, False), lambda p, e: _v_placa_base(p, e, False), "galpão (CH3)",
    "Pórtico de alma cheia com base rotulada; pilar de tesoura rígida."))
_PARAMS_ENGASTADA = [Param(x.chave, x.rotulo, x.unidade, {"B": 300, "L": 500, "t": 31.75, "chumbador": '1"', "gab_B": 200,
                                                              "gab_L": 400, "comprimento_chumbador": 900, "pedestal_B": 750,
                                                              "pedestal_L": 1000}.get(x.chave, x.padrao),
                            x.opcoes, x.dica) for x in _PARAMS_BASE]
_registrar(Tipo(
    "placa_base_engastada", "Placa de base engastada (4 chumbadores)", "apoios",
    "Pilar sobre placa com quatro chumbadores afastados: transmite momento. É a base do pilar com tesoura apoiada.",
    _PARAMS_ENGASTADA, [Param("N_Sd", "Compressão", "kN", 80.0), Param("M_Sd", "Momento", "kN·m", 40.0),
                        Param("H_Sd", "Cortante", "kN", 20.0)],
    lambda p: _g_placa_base(p, True), lambda p, e: _v_placa_base(p, e, True), "galpão (CH3)",
    "Pilar engastado (tesoura apoiada, pórtico com base engastada)."))


def _g_chumbador(p, tipo="gancho"):
    d = DIAMETROS_BARRA[p["diametro"]]; L = _num(p["comprimento"]); r = _num(p["rosca"])
    s = Svg(); s.origem(0, 0, h=max(L, 300) * 0.05)
    s.titulo(-40, L + s.h * 2.4, "CHUMBADOR " + ("EM J" if tipo == "gancho" else "COM PLACA DE ANCORAGEM"))
    s.ret(-d / 2, 0, d, L)
    s.ret(-d / 2 - 2, L - r, d + 4, r, "rosca")
    if tipo == "gancho":
        g = _num(p["gancho"])
        s.ret(-d / 2, 0, g, d)
        s.cota(-d / 2, 0, g - d / 2, 0, -s.h * 2, fmt(g, 0))
    else:
        a = _num(p["placa"])
        s.ret(-a / 2, 0, a, _num(p["placa_t"]), "aco2")
    s.cota(-d / 2, 0, -d / 2, L, s.h * 2.2)
    s.cota(d / 2, L - r, d / 2, L, -s.h * 1.6)
    s.linha(-150, L - _num(p["projecao"]), 150, L - _num(p["projecao"]), "concreto")
    s.texto(160, L - _num(p["projecao"]), "topo do concreto", "rot")
    pecas = [peca_redonda("Chumbador", d, L + (_num(p.get("gancho")) if tipo == "gancho" else 0), 1),
             peca_fixador("porca", "Porca %s" % p["diametro"], 2 if tipo == "gancho" else 3),
             peca_fixador("arruela", "Arruela %s" % p["diametro"], 1)]
    if tipo != "gancho":
        pecas.insert(1, peca_chapa("Placa de ancoragem", _num(p["placa"]), _num(p["placa"]), _num(p["placa_t"]), 1,
                                   furos=[round(d + 2, 0)]))
    return pecas, s.render(), ["Comprimento de ancoragem pela aderência (NBR 6118) ou pelo cone de arrancamento a 35° (ACI 318)."]


def _v_chumbador(p, e, tipo="gancho"):
    from nucleo import bases
    try:
        return bases.chumbadores(_num(e.get("T_Sd")), _num(e.get("V_Sd")), diametro=p["diametro"], n=1, n_tracionados=1,
                                 fck=_num(p["fck"]) / 10.0, h_ef=(_num(p["comprimento"]) - _num(p["projecao"])) / 10.0,
                                 com_chapa_de_ancoragem=(tipo != "gancho"), elemento="Chumbador")
    except Exception as exc_:                           # noqa: BLE001
        r = Resultado("Chumbador"); r.add(nao_verificada(str(exc_))); return r


_P_CHUMB = [Param("diametro", "Diâmetro", "", '3/4"', list(DIAMETROS_BARRA)), Param("comprimento", "Comprimento total (reto)", "mm", 996),
            Param("projecao", "Parte acima do concreto", "mm", 120), Param("rosca", "Rosca", "mm", 100),
            Param("fck", "f<sub>ck</sub>", "MPa", 25)]
_registrar(Tipo(
    "chumbador_gancho", "Chumbador em J (com gancho)", "fixadores",
    "Barra redonda com rosca em cima e gancho embaixo, concretada no pilar ou no bloco. Na Sooro: FE RED 3/4\" com 996 mm (CB1).",
    _P_CHUMB + [Param("gancho", "Gancho", "mm", 150)],
    [Param("T_Sd", "Tração", "kN", 15.0), Param("V_Sd", "Cortante", "kN", 5.0)],
    lambda p: _g_chumbador(p, "gancho"), lambda p, e: _v_chumbador(p, e, "gancho"), "obras Sooro (CB1–CB4)",
    "Apoio de tesoura em pilar de concreto; base de pilar leve."))
_registrar(Tipo(
    "chumbador_placa", "Chumbador com placa de ancoragem", "fixadores",
    "Barra roscada com porca e placa quadrada na ponta de baixo: a ancoragem é pelo cone de concreto, mais curta que a do gancho.",
    _P_CHUMB + [Param("placa", "Placa de ancoragem (lado)", "mm", 70), Param("placa_t", "Espessura da placa", "mm", 9.5)],
    [Param("T_Sd", "Tração", "kN", 30.0), Param("V_Sd", "Cortante", "kN", 8.0)],
    lambda p: _g_chumbador(p, "placa"), lambda p, e: _v_chumbador(p, e, "placa"), "NBR 8800 / ACI 318",
    "Base engastada, tração alta."))


def _g_topo_pilar(p):
    B, L, t = _num(p["B"]), _num(p["L"]), _num(p["t"])
    n = int(p["n_parafusos"]); gB, gL = _num(p["gab_B"]), _num(p["gab_L"])
    fd = furo_mm(p["parafuso"])
    furos = [(B / 2 + sx * gB / 2, L / 2 + sy * gL / 2) for sx in (-1, 1) for sy in ((-1, 1) if n == 4 else (0,))]
    s = Svg(); s.origem(0, 0, h=max(B, L) * 0.055)
    s.titulo(0, L + s.h * 4.2, "CHAPA DE TOPO DO PILAR (planta)")
    s.ret(0, 0, B, L)
    for x, y in furos:
        s.circ(x, y, fd / 2)
    s.cota(0, 0, B, 0, -s.h * 2.4); s.cota(B, 0, B, L, -s.h * 2.2)
    s.cota(furos[0][0], L, furos[-1][0], L, s.h * 1.6)
    d = d_parafuso_mm(p["parafuso"])
    pecas = [peca_chapa("Chapa de topo do pilar", B, L, t, 1, furos=[fd] * n, aco=p["aco"]),
             peca_chapa("Chapa de apoio da tesoura (no banzo inferior)", B, L, t, 1, furos=[fd] * n, aco=p["aco"]),
             peca_fixador("parafuso", "Parafuso %s × %d %s" % (p["parafuso"], comprimento_parafuso(2 * t, d), p["classe"]), n)]
    return pecas, s.render(), ["A tesoura assenta no topo do pilar: uma chapa soldada no pilar, outra no apoio da tesoura, parafusadas entre si."]


def _v_topo_pilar(p, e):
    r = Resultado("Tesoura apoiada no topo do pilar")
    n = int(p["n_parafusos"])
    chapas = [_chapa_lig("chapa de topo", _num(p["t"]), p["aco"], 35.0), _chapa_lig("chapa da tesoura", _num(p["t"]), p["aco"], 35.0)]
    _grupo(r, p["parafuso"], p["classe"], 2 if n == 4 else 1, 2, _num(p["gab_L"]), _num(p["gab_B"]), chapas,
           V=_num(e.get("H_Sd")), N=_num(e.get("T_Sd")), elemento="Parafusos do apoio")
    _filete(r, _num(p["perna"]), 2 * (_num(p["B"]) + _num(p["L"])) * 0.6, math.hypot(_num(e.get("H_Sd")), _num(e.get("T_Sd"))),
            1, _num(p["t"]), "Solda do pilar na chapa de topo")
    return r


_registrar(Tipo(
    "tesoura_topo_pilar", "Tesoura apoiada no topo do pilar metálico", "apoios",
    "Chapa soldada no topo do pilar e chapa soldada sob o apoio da tesoura, parafusadas. É o apoio da tesoura do lançamento.",
    [Param("B", "Largura", "mm", 200), Param("L", "Comprimento", "mm", 300), Param("t", "Espessura", "mm", 12.7, BITOLAS_CHAPA),
     Param("n_parafusos", "Parafusos", "", 4, [2, 4]), Param("parafuso", "Diâmetro", "", "M16", PARAFUSOS),
     Param("classe", "Classe", "", "ASTM A325", CLASSES), Param("gab_B", "Gabarito na largura", "mm", 120),
     Param("gab_L", "Gabarito no comprimento", "mm", 200), Param("perna", "Perna da solda", "mm", 6),
     Param("aco", "Aço", "", "ASTM A36", ACOS_CHAPA)],
    [Param("R_Sd", "Reação vertical", "kN", 40.0), Param("H_Sd", "Força horizontal", "kN", 10.0),
     Param("T_Sd", "Arrancamento (sucção)", "kN", 15.0)],
    _g_topo_pilar, _v_topo_pilar, "lançamento", "Tesoura apoiada em pilar W."))


def _g_console(p):
    perfil = p["perfil"]; L = _num(p["balanco"])
    from nucleo import catalogo
    q = catalogo.perfil_de(perfil) or catalogo.perfil_de(perfil.replace("X", "×"))
    d = float(getattr(q, "d", 0) or 150)
    s = Svg(); s.origem(0, 0, h=max(L, d) * 0.06)
    s.titulo(0, d + s.h * 2.4, "CONSOLE (elevação)")
    s.ret(-40, -d, 40, 3 * d, "oculta")
    s.ret(0, 0, L, d)
    s.ret(-12, -20, 12, d + 40, "aco2")
    s.solda(0, 0, 0, d, perna=6)
    s.cota(0, 0, L, 0, -s.h * 2.2)
    s.cota(L, 0, L, d, -s.h * 2)
    s.texto(L * 0.4, d + s.h * 0.7, "P", "rot")
    pecas = [peca_barra("Console", perfil, L, 1), peca_chapa("Chapa de topo do console", 150, d + 40, 12.7, 1)]
    return pecas, s.render(), ["Na Sooro: dispositivos DP com W150×13 em balanço para apoiar tesouras e terças de beiral."]


def _v_console(p, e):
    from nucleo import nbr8800, catalogo
    q = catalogo.perfil_de(p["perfil"])
    P = _num(e.get("P_Sd")); a = _num(p["excentricidade"])
    r = Resultado("Console")
    try:
        v = nbr8800.verificar_viga(q, "ASTM A572 Gr.50", L=_num(p["balanco"]) / 10.0, M_Sd=P * a / 10.0, V_Sd=P,
                                   Lb=_num(p["balanco"]) / 10.0, limite="L/150", caso="balanco_concentrada",
                                   elemento="Console")
        for x in v.verificacoes:
            r.add(x)
    except Exception as exc_:                           # noqa: BLE001
        r.add(nao_verificada(str(exc_)))
    _filete(r, 6.0, 2 * float(getattr(q, "d", 150) or 150), P, 2, 6.0, "Solda do console")
    return r


_registrar(Tipo(
    "console", "Console em perfil W", "apoios",
    "Pedaço de perfil W soldado em balanço no pilar (ou numa chapa) para apoiar uma tesoura, uma viga ou uma terça de beiral.",
    [Param("perfil", "Perfil", "", "W 150×13,0"), Param("balanco", "Balanço", "mm", 400), Param("excentricidade", "Carga a (do apoio)", "mm", 300)],
    [Param("P_Sd", "Carga no console", "kN", 30.0)],
    _g_console, _v_console, "obras Sooro (DP.2 a DP.7)", "Apoio de tesoura em pilar existente, marquise, beiral."))


# ------------------------------------------------------------------ tesoura e pórtico

def _g_no_soldado(p):
    h = _num(p["altura_banzo"]); th = math.radians(_num(p["angulo"]))
    lc = h / math.sin(th)
    s = Svg(); s.origem(0, 0, h=max(lc, h) * 0.07)
    s.titulo(0, h + lc * math.sin(th) + s.h * 2.4, "NÓ SOLDADO (diagonal no banzo)")
    s.ret(-lc, 0, 3 * lc, h, "aco2")
    w = _num(p["largura_diagonal"])
    x0 = 0
    s.poli([(x0, h), (x0 + w / math.sin(th), h), (x0 + w / math.sin(th) + lc * math.cos(th), h + lc * math.sin(th)),
            (x0 + lc * math.cos(th), h + lc * math.sin(th))])
    s.solda(x0, h, x0 + w / math.sin(th), h, perna=_num(p["perna"]))
    s.cota(-lc, 0, -lc, h, s.h * 2)
    pecas = [peca_fixador("solda", "Filete %s mm, 2 cordões de %s mm" % (fmt(_num(p["perna"]), 0), fmt(lc, 0)), 1)]
    return pecas, s.render(), ["Treliça leve da Sooro: a diagonal U é soldada direto na alma do banzo Ue, sem chapa de nó. Contato = altura do banzo / sen θ."]


def _v_no_soldado(p, e):
    r = Resultado("Nó soldado da tesoura")
    lc = _num(p["altura_banzo"]) / math.sin(math.radians(_num(p["angulo"])))
    _filete(r, _num(p["perna"]), lc, _num(e.get("N_Sd")), 2, _num(p["t_diagonal"]), "Solda da diagonal no banzo")
    return r


_registrar(Tipo(
    "no_soldado", "Nó de tesoura soldado (sem chapa de nó)", "tesoura",
    "Diagonal ou montante soldado direto no banzo, dois cordões de filete ao longo do contato.",
    [Param("altura_banzo", "Altura do banzo", "mm", 100), Param("angulo", "Ângulo da diagonal", "°", 45),
     Param("largura_diagonal", "Aba da diagonal", "mm", 40), Param("perna", "Perna da solda", "mm", 3),
     Param("t_diagonal", "Espessura da diagonal", "mm", 2.25)],
    [Param("N_Sd", "Força na diagonal", "kN", 20.0)],
    _g_no_soldado, _v_no_soldado, "obras Sooro (tesouras)", "Treliças de perfis formados a frio."))


def _g_emenda_banzo(p):
    Lc = _num(p["comprimento_tala"]); B = _num(p["largura_tala"]); t = _num(p["t"])
    n = int(p["n_por_lado"]); pas = _num(p["passo"]); fd = furo_mm(p["parafuso"])
    s = Svg(); s.origem(0, 0, h=max(Lc, B) * 0.06)
    s.titulo(0, B + s.h * 4.2, "EMENDA DE BANZO (tala)")
    s.ret(0, 0, Lc, B)
    s.linha(Lc / 2, -20, Lc / 2, B + 20, "eixo")
    for lado in (-1, 1):
        for i in range(n):
            s.circ(Lc / 2 + lado * (40 + i * pas), B / 2, fd / 2)
    s.cota(0, 0, Lc, 0, -s.h * 2.4); s.cota(Lc, 0, Lc, B, -s.h * 2)
    pecas = [peca_chapa("Tala de emenda", Lc, B, t, 2, furos=[fd] * (2 * n), aco=p["aco"]),
             peca_fixador("parafuso", "Parafuso %s %s" % (p["parafuso"], p["classe"]), 2 * n)]
    return pecas, s.render(), ["Emenda de campo do banzo (tesoura em duas metades): duas talas, uma de cada lado da alma."]


def _v_emenda_banzo(p, e):
    r = Resultado("Emenda de banzo")
    chapas = [_chapa_lig("tala", _num(p["t"]), p["aco"], 30.0, 1), _chapa_lig("alma do banzo", _num(p["t_banzo"]), "CIVIL 300", 40.0, 1)]
    _grupo(r, p["parafuso"], p["classe"], int(p["n_por_lado"]), 1, _num(p["passo"]), 50.0, chapas, N=_num(e.get("N_Sd")),
           planos=2, elemento="Parafusos de um lado da emenda")
    return r


_registrar(Tipo(
    "emenda_banzo", "Emenda de banzo com talas", "tesoura",
    "Tesoura grande demais para o transporte sai em duas metades; o banzo é emendado na obra com duas talas parafusadas.",
    [Param("comprimento_tala", "Comprimento da tala", "mm", 400), Param("largura_tala", "Largura", "mm", 120),
     Param("t", "Espessura", "mm", 6.35, BITOLAS_CHAPA), Param("n_por_lado", "Parafusos de cada lado", "", 3, [2, 3, 4]),
     Param("passo", "Passo", "mm", 60), Param("parafuso", "Diâmetro", "", "M16", PARAFUSOS),
     Param("classe", "Classe", "", "ASTM A325", CLASSES), Param("t_banzo", "Espessura do banzo", "mm", 3.0),
     Param("aco", "Aço", "", "ASTM A36", ACOS_CHAPA)],
    [Param("N_Sd", "Força no banzo", "kN", 80.0)],
    _g_emenda_banzo, _v_emenda_banzo, "prática de fábrica", "Tesouras acima de ~12 m (transporte)."))


def _g_chapa_topo(p):
    from nucleo import catalogo
    q = catalogo.perfil_de(p["viga"])
    d = float(getattr(q, "d", 0) or 300); bf = float(getattr(q, "bf", 0) or 150)
    B = max(bf + 30, _num(p["gabarito"]) + 100); H = d + 2 * 70
    fd = furo_mm(p["parafuso"])
    ys = [H - 35, H - 105, 35, 105]
    s = Svg(); s.origem(0, 0, h=max(B, H) * 0.045)
    s.titulo(0, H + s.h * 4.2, "CHAPA DE TOPO (joelho)")
    s.ret(0, 0, B, H)
    for y in ys:
        for x in (B / 2 - _num(p["gabarito"]) / 2, B / 2 + _num(p["gabarito"]) / 2):
            s.circ(x, y, fd / 2)
    s.ret(B / 2 - bf / 2, 70, bf, d, "oculta")
    s.cota(0, 0, B, 0, -s.h * 2.4); s.cota(B, 0, B, H, -s.h * 2)
    pecas = [peca_chapa("Chapa de topo", B, H, _num(p["t"]), 1, furos=[fd] * 8),
             peca_fixador("parafuso", "Parafuso %s %s protendido" % (p["parafuso"], p["classe"]), 8)]
    return pecas, s.render(), ["Joelho do pórtico de alma cheia: chapa soldada na viga (com mísula), parafusada na mesa do pilar."]


def _v_chapa_topo(p, e):
    from nucleo import ligacoes as lig, catalogo
    try:
        return lig.chapa_de_topo(catalogo.perfil_de(p["viga"]), _num(e.get("M_Sd")) * 100.0, V_Sd=_num(e.get("V_Sd")),
                                 N_Sd=_num(e.get("N_Sd")), diametro=p["parafuso"], parafuso=p["classe"], t_chapa=_num(p["t"]) / 10.0,
                                 gabarito=_num(p["gabarito"]) / 10.0)
    except Exception as exc_:                           # noqa: BLE001
        r = Resultado("Chapa de topo"); r.add(nao_verificada(str(exc_))); return r


_registrar(Tipo(
    "chapa_topo_joelho", "Chapa de topo (joelho do pórtico)", "tesoura",
    "Ligação rígida viga–pilar do pórtico de alma cheia: chapa soldada na ponta da viga, parafusos de alta resistência na mesa do pilar.",
    [Param("viga", "Viga", "", "W 410×46,1"), Param("t", "Espessura da chapa", "mm", 25.4, BITOLAS_CHAPA),
     Param("parafuso", "Diâmetro", "", '3/4"', PARAFUSOS), Param("classe", "Classe", "", "ASTM A325", CLASSES),
     Param("gabarito", "Gabarito", "mm", 100)],
    [Param("M_Sd", "Momento", "kN·m", 90.0), Param("V_Sd", "Cortante", "kN", 60.0), Param("N_Sd", "Normal", "kN", 20.0)],
    _g_chapa_topo, _v_chapa_topo, "galpão (CH1, CH2)", "Joelho e cumeeira do pórtico de alma cheia."))


def _g_flexivel(p):
    from nucleo import catalogo
    q = catalogo.perfil_de(p["viga"])
    d = float(getattr(q, "d", 0) or 300)
    n = int(p["n_parafusos"]); pas = _num(p["passo"]); fd = furo_mm(p["parafuso"])
    Hc = (n - 1) * pas + 2 * 35
    s = Svg(); s.origem(0, 0, h=max(Hc, 150) * 0.07)
    s.titulo(0, Hc + s.h * 2.2, "LIGAÇÃO FLEXÍVEL (cantoneiras)")
    s.ret(0, 0, 90, Hc, "aco2")
    for i in range(n):
        s.circ(45, 35 + i * pas, fd / 2)
    s.cota(90, 0, 90, Hc, -s.h * 2)
    pecas = [peca_barra("Cantoneira de ligação", "L 3'' X 5/16''", Hc, 2),
             peca_fixador("parafuso", "Parafuso %s %s" % (p["parafuso"], p["classe"]), 2 * n)]
    return pecas, s.render(), ["Viga apoiada (sem momento) em pilar ou em outra viga; duas cantoneiras na alma."]


def _v_flexivel(p, e):
    from nucleo import ligacoes as lig, catalogo
    try:
        return lig.dupla_cantoneira(catalogo.perfil_de(p["viga"]), _num(e.get("V_Sd")), n_parafusos=int(p["n_parafusos"]),
                                    diametro=p["parafuso"], parafuso=p["classe"], passo=_num(p["passo"]) / 10.0)
    except Exception as exc_:                           # noqa: BLE001
        r = Resultado("Ligação flexível"); r.add(nao_verificada(str(exc_))); return r


_registrar(Tipo(
    "ligacao_flexivel", "Ligação flexível com duas cantoneiras", "tesoura",
    "Viga de mezanino, viga de fechamento ou viga secundária apoiada em pilar ou viga, só com cortante.",
    [Param("viga", "Viga", "", "W 250×17,9"), Param("n_parafusos", "Parafusos por aba", "", 3, [2, 3, 4, 5]),
     Param("passo", "Passo", "mm", 76), Param("parafuso", "Diâmetro", "", '3/4"', PARAFUSOS), Param("classe", "Classe", "", "ASTM A325", CLASSES)],
    [Param("V_Sd", "Cortante", "kN", 60.0)],
    _g_flexivel, _v_flexivel, "NBR 8800 / galpão", "Vigas secundárias, mezaninos, vigas de fechamento."))


# ------------------------------------------------------------------ fechamento

def _g_telha(p):
    area = _num(p["area"]); d = _num(p["densidade"])
    n = int(math.ceil(area * d))
    s = Svg(); s.origem(0, 0, h=40)
    s.titulo(0, 360, "FIXAÇÃO DA TELHA NA TERÇA")
    pts = []
    for i in range(6):
        x = i * 250
        pts += [(x, 0), (x + 40, 0), (x + 80, 120), (x + 170, 120), (x + 210, 0)]
    s.poli(pts, "aco", fechada=False)
    for i in range(6):
        s.linha(i * 250 + 125, 140, i * 250 + 125, 60, "barra")
    s.ret(-50, -150, 1600, 150, "oculta")
    s.texto(0, -200, "terça", "rot")
    pecas = [peca_fixador("parafuso", "Autobrocante 12-14 × 1\" com arruela de vedação", n, "%s por m² de cobertura" % fmt(d, 1))]
    return pecas, s.render(), ["Fixação na crista da onda, em todas as terças; nas bordas e na cumeeira, em todas as ondas."]


_registrar(Tipo(
    "fixacao_telha", "Fixação da telha na terça", "fechamento",
    "Parafuso autobrocante com arruela de vedação atravessando a crista da telha até a mesa da terça.",
    [Param("area", "Área de cobertura", "m²", 450), Param("densidade", "Parafusos por m²", "", 2.2)],
    [], _g_telha, None, "prática de montagem", "Toda telha metálica."))


def _g_parafusos(p):
    from nucleo import ligacoes as lig
    linhas = []
    for dnome in ("M12", "M16", "M20", "M24", '1/2"', '5/8"', '3/4"', '7/8"', '1"'):
        for classe in ("ASTM A307", "ASTM A325"):
            try:
                v = lig.cisalhamento_parafuso(dnome, classe, planos=1, rosca_no_plano=True, Fv_Sd=0.0)
                t = lig.tracao_parafuso(dnome, classe, Ft_Sd=0.0)
                linhas.append((dnome, classe, v.Rd, t.Rd))
            except Exception:                           # noqa: BLE001
                continue
    s = Svg(); s.origem(0, 0, h=14)
    y = 0
    s.texto(0, 30, "Diâmetro", "tit"); s.texto(160, 30, "Classe", "tit"); s.texto(400, 30, "Cisalhamento (kN)", "tit")
    s.texto(650, 30, "Tração (kN)", "tit")
    for dnome, classe, v, t in linhas:
        y -= 24
        s.texto(0, y, dnome, "rot"); s.texto(160, y, classe, "rot")
        s.texto(520, y, fmt(v, 1), "rot", "end"); s.texto(740, y, fmt(t, 1), "rot", "end")
    pecas = []
    return pecas, s.render(), ["Resistências de cálculo por parafuso (NBR 8800, item 6.3.3): cisalhamento com a rosca no plano de corte, um plano; tração."]


_registrar(Tipo(
    "tabela_parafusos", "Parafusos: resistências de cálculo", "fixadores",
    "Tabela de consulta rápida: quanto um parafuso aguenta ao cisalhamento e à tração, por diâmetro e classe.",
    [], [], _g_parafusos, None, "NBR 8800, item 6.3.3", "Pré-dimensionamento de qualquer ligação parafusada."))


# =====================================================================================
# montagem da resposta
# =====================================================================================

def lista() -> List[dict]:
    """Os tipos, na ordem das categorias."""
    ordem = {c: i for i, (c, _n) in enumerate(CATEGORIAS)}
    return [t.dict() for t in sorted(REGISTRO.values(), key=lambda t: (ordem.get(t.categoria, 99), t.nome))]


def _parametros(t: Tipo, dados: Optional[dict]) -> dict:
    p = {x.chave: x.padrao for x in t.parametros}
    for k, v in (dados or {}).items():
        if k in p and v not in (None, ""):
            p[k] = v
    return p


def montar(tipo: str, parametros: Optional[dict] = None, esforcos: Optional[dict] = None) -> dict:
    """Peças, desenho e (com esforços) a verificação de um tipo."""
    from nucleo.verificar import serializar_resultado
    t = REGISTRO.get(tipo)
    if t is None:
        raise ErroDeDados("ligação desconhecida: %s" % tipo)
    p = _parametros(t, parametros)
    try:
        pecas, svg, notas = t.gerar(p)
    except ErroDeDados:
        raise
    except Exception as exc_:                           # noqa: BLE001
        raise ErroDeDados("não consegui montar %s com esses parâmetros: %s" % (t.nome, exc_))
    saida = {"tipo": t.dict(), "parametros": p, "pecas": pecas, "svg": svg, "notas": notas,
             "peso_kg": round(sum(x["peso"] for x in pecas), 2), "verificacao": None}
    if t.verificar is not None and t.esforcos:
        e = {x.chave: x.padrao for x in t.esforcos}
        e.update({k: v for k, v in (esforcos or {}).items() if v not in (None, "")})
        try:
            r = t.verificar(p, e)
        except Exception as exc_:                       # noqa: BLE001
            r = Resultado(t.nome)
            r.add(nao_verificada(str(exc_)))
        saida["verificacao"] = serializar_resultado(r)
        saida["esforcos"] = e
    return saida


# =====================================================================================
# exemplos das obras
# =====================================================================================

def classificar_peca(tipo_prod: str, perfil: str, furos: str, parafusos: str, conjunto_tipo: str = "") -> Optional[str]:
    """A que tipo da biblioteca uma peça de uma obra corresponde (None: não é acessório)."""
    s = (perfil or "").upper()
    if tipo_prod == "suporte_terca":
        if "OBL" in (furos or "").upper() and ("4X" in (furos or "").upper().replace(" ", "") or "4×" in (furos or "")):
            return "suporte_terca_cadeirinha"
        if not furos:
            return "suporte_terca_cadeirinha"          # a base soldada no banzo
        return "suporte_terca_chapa"
    if tipo_prod in ("suporte_agulhamento",) or conjunto_tipo in ("agulhamento", "agulhamento_lateral"):
        return "agulhamento_rigido"
    if tipo_prod in ("agulhamento", "agulhamento_lateral") and s.startswith("L"):
        return "agulhamento_rigido"
    if tipo_prod in ("gancho", "agulhamento_diagonal") or conjunto_tipo == "agulhamento_diagonal":
        return "agulhamento_diagonal"
    if tipo_prod in ("castanha", "barra_roscada", "contraventamento", "suporte_contraventamento") or conjunto_tipo == "contraventamento":
        return "contravento_tirante"
    if tipo_prod == "chumbador":
        return "chumbador_gancho"
    if tipo_prod in ("chapa", "parte") and "CHUMBADOR" in (parafusos or "").upper():
        return "apoio_tesoura_concreto"
    if conjunto_tipo == "conjunto" and re.match(r"^W\s*1\d\d", s):
        return "console"
    return None


def exemplos_das_obras(pasta_dados: str, limite_por_tipo: int = 60) -> Dict[str, List[dict]]:
    """Peças de ligação das obras detalhadas na pasta de dados, por tipo da biblioteca:
    {tipo: [{obra, nome, perfil, medida, furos, parafusos, qtd, peso}]}. Lê a lista de
    materiais e os nomes do detalhamento de cada projeto; não refaz nada."""
    saida: Dict[str, List[dict]] = {}
    if not os.path.isdir(pasta_dados):
        return saida
    for s in sorted(os.listdir(pasta_dados)):
        d = os.path.join(pasta_dados, s, "detalhamento")
        lm, nm = os.path.join(d, "lista-de-materiais.json"), os.path.join(d, "nomes.json")
        if not (os.path.exists(lm) and os.path.exists(nm)):
            continue
        try:
            L = json.load(open(lm, encoding="utf-8"))
            N = json.load(open(nm, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        obra = (L.get("projeto") or {}).get("nome") or s
        tipos = N.get("tipos") or {}
        tconj = N.get("tipos_conjuntos") or {}
        conj_de = {}
        for c in L.get("conjuntos") or []:
            for m in (c.get("composicao") or {}):
                conj_de.setdefault(m, tconj.get(c["marca"], ""))
        for p in L.get("posicoes") or []:
            marca = str(p.get("marca") or "").split(" / ")[0]
            t = classificar_peca(tipos.get(marca, ""), p.get("perfil", ""), p.get("furos", ""), p.get("parafusos", ""),
                                 conj_de.get(marca, ""))
            if not t:
                continue
            lista_t = saida.setdefault(t, [])
            if len(lista_t) >= limite_por_tipo:
                continue
            medida = ("%s × %s × %s" % (p.get("comprimento"), p.get("largura"), p.get("espessura"))
                      if p.get("classe") == "Chapa" else "L = %s" % p.get("comprimento"))
            lista_t.append({"obra": obra, "projeto": s, "nome": p.get("nome") or marca, "marca": marca,
                            "perfil": p.get("perfil", ""), "medida": medida, "furos": p.get("furos", ""),
                            "parafusos": p.get("parafusos", ""), "qtd": p.get("quantidade", 0),
                            "peso": p.get("peso", 0.0), "tipo_producao": tipos.get(marca, "")})
    return saida
