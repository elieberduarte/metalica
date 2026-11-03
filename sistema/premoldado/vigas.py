# -*- coding: utf-8 -*-
"""Vigas pré-moldadas de concreto armado, biapoiadas (NBR 6118 e NBR 9062).

A seção é uma pilha de retângulos centrados, de baixo para cima (`SecaoViga`): retangular, T, I,
T invertido e U (viga-calha: o fundo e as duas paredes). A altura pode variar ao longo do vão (viga
de cobertura com o banzo de cima acompanhando a água): `dimensionar_viga` recebe a seção como
função da posição.

As verificações de cada viga:

* ELU flexão em todas as seções do vão (retângulo de tensões na seção composta, 17.2.2; ductilidade
  x/d ≤ ξlim, 14.6.4.3; mínima 17.3.5.2.1) e, havendo sucção do vento, o momento negativo;
* ELU cisalhamento no apoio (modelo I, 17.4.2.2), estribos com os ramos das almas;
* ELS-W abertura de fissuras na combinação frequente (17.3.3.2, limites da Tabela 13.4);
* ELS-DEF flecha na combinação quase permanente, rigidez equivalente de Branson (17.3.2.1.1) seção a
  seção e fluência pelo αf (17.3.2.1.2), limites da NBR 9062 (Tabelas 8 e 9);
* estabilidade lateral pelos critérios geométricos da NBR 9062 (6.1.6);
* içamento: carga dinâmica γf·βa·gk (5.3.2), momento negativo nas alças e a força nas alças (βa = 3);
* o apoio: sem recorte (7.5) ou dente Gerber (7.4, assemelhado a consolo), e o aparelho de
  elastômero (7.2.1.6) com a força horizontal da temperatura e da retração.

Unidades: cm, kN, kN·cm (entrada do vão e do comprimento em m).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados, Passo, Resultado, Verificacao, fmt

from . import nbr6118 as N6118
from . import nbr9062 as N9062
from .concreto import BITOLAS, AcoArmadura, Concreto

PESO_CONCRETO = 25.0          # kN/m³ (NBR 6118, 8.2.2)
PESO_AGUA = 10.0              # kN/m³
ALFA_TERMICO = 1e-5           # 1/°C (NBR 6118, 8.2.3)
DMAX_AGREGADO = 1.9           # cm (brita 1): espaçamento das barras (18.3.2.2)
ESTRIBO = 0.63                # cm (ø6,3) na conta da altura útil antes de escolher os estribos
ETA1 = 2.25                   # barra nervurada (9.3.2.1)
N_SECOES = 41                 # seções ao longo do vão

#: fator de forma do momento de fissuração (NBR 6118, 17.3.1)
ALFA_FORMA = {"retangular": 1.5, "T": 1.2, "I": 1.3, "T invertido": 1.3, "U": 1.3}

#: limite de wk (mm) por classe de agressividade, concreto armado, combinação frequente (Tabela 13.4)
WK_LIMITE = {"I": 0.4, "II": 0.3, "III": 0.3, "IV": 0.2}

#: ξ(t) da NBR 6118, Tabela 17.1 — a expressão vale até 70 meses
def xi_tempo(t_meses: float) -> float:
    if t_meses <= 0:
        return 0.0
    if t_meses > 70:
        return 2.0
    return 0.68 * (0.996 ** t_meses) * t_meses ** 0.32


#: εcs(t∞, t0) em ‰ (NBR 6118, Tabela 8.1): umidade (%) → {t0 (dias): (2Ac/u = 20 cm, 60 cm)}
RETRACAO = {40: {5: (0.53, 0.47), 30: (0.44, 0.45), 60: (0.39, 0.43)},
            55: {5: (0.48, 0.43), 30: (0.41, 0.41), 60: (0.36, 0.40)},
            75: {5: (0.36, 0.32), 30: (0.33, 0.31), 60: (0.30, 0.31)},
            90: {5: (0.18, 0.15), 30: (0.17, 0.15), 60: (0.17, 0.15)}}


def retracao(umidade: float, t0_dias: float, esp_ficticia: float) -> float:
    """εcs(t∞, t0) em ‰ pela Tabela 8.1, com interpolação linear (fora da tabela, o valor da borda)"""
    def interp(x, xs, ys):
        return float(np.interp(x, xs, ys))
    us = sorted(RETRACAO)
    por_u = []
    for u in us:
        ts = sorted(RETRACAO[u])
        v20 = interp(t0_dias, ts, [RETRACAO[u][t][0] for t in ts])
        v60 = interp(t0_dias, ts, [RETRACAO[u][t][1] for t in ts])
        por_u.append(interp(esp_ficticia, [20.0, 60.0], [v20, v60]))
    return interp(umidade, us, por_u)


# ------------------------------------------------------------------ a seção

@dataclass
class SecaoViga:
    """retângulos centrados empilhados de baixo para cima: (largura, altura) em cm. `almas` é o número
    de almas (2 na viga-calha); `parametros` guarda as medidas que definem a seção (para o desenho e a
    lista)."""
    tipo: str
    camadas: List[Tuple[float, float]]
    almas: int = 1
    parametros: Dict[str, float] = field(default_factory=dict)

    @property
    def h(self) -> float:
        return sum(c[1] for c in self.camadas)

    @property
    def A(self) -> float:
        return sum(b * t for b, t in self.camadas)

    @property
    def yc(self) -> float:
        """centroide, medido da face de baixo"""
        s, y0 = 0.0, 0.0
        for b, t in self.camadas:
            s += b * t * (y0 + t / 2)
            y0 += t
        return s / self.A

    @property
    def I(self) -> float:
        yc, s, y0 = self.yc, 0.0, 0.0
        for b, t in self.camadas:
            s += b * t ** 3 / 12.0 + b * t * (y0 + t / 2 - yc) ** 2
            y0 += t
        return s

    @property
    def bw(self) -> float:
        """a largura das almas somadas (cisalhamento)"""
        return min(b for b, _ in self.camadas)

    @property
    def b_inf(self) -> float:
        return self.camadas[0][0]

    @property
    def b_sup(self) -> float:
        return self.camadas[-1][0]

    @property
    def b_max(self) -> float:
        return max(b for b, _ in self.camadas)

    @property
    def b_compressao(self) -> float:
        """a menor largura da região comprimida (NBR 9062, 6.1.5) com o momento positivo: a mesa de
        cima; na viga-calha, a largura externa (as paredes ligadas pelo fundo) — ver hipótese"""
        if self.tipo == "U":
            return self.b_inf
        if self.tipo == "T invertido":
            return self.bw
        return self.b_sup

    @property
    def peso(self) -> float:
        """kN/m"""
        return PESO_CONCRETO * self.A / 1e4

    @property
    def perimetro(self) -> float:
        """o perímetro em contato com o ar (espessura fictícia, 8.2.11)"""
        if self.tipo == "U":
            B, t, tf = self.parametros["B"], self.parametros["t"], self.parametros["tf"]
            return 2 * self.h + B + 2 * t + 2 * (self.h - tf) + (B - 2 * t)
        bs = [b for b, _ in self.camadas]
        return 2 * self.h + bs[0] + bs[-1] + sum(abs(a - b) for a, b in zip(bs, bs[1:]))

    @property
    def alfa_forma(self) -> float:
        return ALFA_FORMA.get(self.tipo, 1.5)

    def texto(self) -> str:
        p = self.parametros
        if self.tipo == "retangular":
            return "%s × %s" % (fmt(p["b"], 0), fmt(p["h"], 0))
        if self.tipo == "U":
            return "U %s × %s (paredes %s, fundo %s)" % (fmt(p["B"], 0), fmt(p["h"], 0), fmt(p["t"], 0), fmt(p["tf"], 0))
        if self.tipo == "T":
            return "T %s × %s (mesa %s × %s, alma %s)" % (fmt(p["bf"], 0), fmt(p["h"], 0), fmt(p["bf"], 0), fmt(p["hf"], 0), fmt(p["bw"], 0))
        if self.tipo == "T invertido":
            return "T invertido %s × %s (aba %s × %s, alma %s)" % (fmt(p["bfi"], 0), fmt(p["h"], 0), fmt(p["bfi"], 0), fmt(p["hfi"], 0), fmt(p["bw"], 0))
        return "I %s (mesas %s × %s, alma %s)" % (fmt(p["h"], 0), fmt(p["bf"], 0), fmt(p["hf"], 0), fmt(p["bw"], 0))

    def invertida(self) -> "SecaoViga":
        """a mesma seção de cabeça para baixo (momento negativo: a face de baixo comprimida)"""
        return SecaoViga(self.tipo, list(reversed(self.camadas)), self.almas, dict(self.parametros))

    def contorno(self) -> List[Tuple[float, float]]:
        """o contorno fechado (cm; x centrado, y da face de baixo) — para o 3D e os desenhos"""
        if self.tipo == "U":
            B, t, tf, h = self.parametros["B"], self.parametros["t"], self.parametros["tf"], self.h
            return [(-B / 2, 0), (B / 2, 0), (B / 2, h), (B / 2 - t, h), (B / 2 - t, tf), (-B / 2 + t, tf),
                    (-B / 2 + t, h), (-B / 2, h)]
        dir_, esq, y0 = [], [], 0.0
        for b, t in self.camadas:
            dir_ += [(b / 2, y0), (b / 2, y0 + t)]
            esq += [(-b / 2, y0), (-b / 2, y0 + t)]
            y0 += t
        return dir_ + list(reversed(esq))

    # -- integrais do bloco comprimido (profundidade z medida da face de cima)
    def _faixas(self):
        """(z1, z2, b) de cima para baixo"""
        out, z = [], 0.0
        for b, t in reversed(self.camadas):
            out.append((z, z + t, b))
            z += t
        return out

    def bloco(self, y: float) -> Tuple[float, float]:
        """a área comprimida até a profundidade y (do topo) e a profundidade do seu centroide"""
        A = S = 0.0
        for z1, z2, b in self._faixas():
            if z1 >= y:
                break
            zz = min(z2, y)
            a = b * (zz - z1)
            A += a
            S += a * (z1 + zz) / 2
        return A, (S / A if A > 0 else 0.0)

    def momentos_comprimidos(self, x: float) -> Tuple[float, float]:
        """∫b(x − z)dz e ∫b(x − z)²dz do concreto acima da linha neutra (profundidade x)"""
        S1 = S2 = 0.0
        for z1, z2, b in self._faixas():
            if z1 >= x:
                break
            zz = min(z2, x)
            S1 += b * ((x - z1) ** 2 - (x - zz) ** 2) / 2.0
            S2 += b * ((x - z1) ** 3 - (x - zz) ** 3) / 3.0
        return S1, S2


def secao_retangular(b: float, h: float) -> SecaoViga:
    return SecaoViga("retangular", [(b, h)], 1, {"b": b, "h": h})


def secao_T(bf: float, hf: float, bw: float, h: float) -> SecaoViga:
    return SecaoViga("T", [(bw, h - hf), (bf, hf)], 1, {"bf": bf, "hf": hf, "bw": bw, "h": h})


def secao_I(bf: float, hf: float, bw: float, h: float) -> SecaoViga:
    """mesas iguais em cima e embaixo"""
    if h <= 2 * hf:
        raise ErroDeDados("seção I: a altura (%s cm) precisa passar das duas mesas (%s cm)" % (fmt(h, 0), fmt(2 * hf, 0)))
    return SecaoViga("I", [(bf, hf), (bw, h - 2 * hf), (bf, hf)], 1, {"bf": bf, "hf": hf, "bw": bw, "h": h})


def secao_T_invertido(bw: float, h: float, bfi: float, hfi: float) -> SecaoViga:
    return SecaoViga("T invertido", [(bfi, hfi), (bw, h - hfi)], 1, {"bw": bw, "h": h, "bfi": bfi, "hfi": hfi})


def secao_U(B: float, h: float, t: float, tf: float) -> SecaoViga:
    """viga-calha: largura externa B, altura h, paredes t, fundo tf"""
    if B <= 2 * t or h <= tf:
        raise ErroDeDados("seção U: as paredes (%s cm) ou o fundo (%s cm) não cabem em %s × %s" % (fmt(t, 0), fmt(tf, 0), fmt(B, 0), fmt(h, 0)))
    return SecaoViga("U", [(B, tf), (2 * t, h - tf)], 2, {"B": B, "h": h, "t": t, "tf": tf})


# ------------------------------------------------------------------ flexão e estádio II

def _y_do_bloco(sec: SecaoViga, C: float, sc: float) -> float:
    """a profundidade do retângulo de tensões que dá a força C (kN)"""
    lo, hi = 0.0, sec.h
    if sc * sec.bloco(hi)[0] <= C:
        return hi
    for _ in range(60):
        m = (lo + hi) / 2
        if sc * sec.bloco(m)[0] < C:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def momento_resistente(sec: SecaoViga, As: float, d: float, conc: Concreto, aco: AcoArmadura) -> Tuple[float, float]:
    """(MRd kN·cm, x cm) da seção com a armadura As a d do topo, aço escoando"""
    sc = conc.sigma_cd
    C = As * aco.fyd
    y = _y_do_bloco(sec, C, sc)
    _A, zc = sec.bloco(y)
    return C * (d - zc), y / conc.lam


def flexao(sec: SecaoViga, d: float, Md: float, conc: Concreto, aco: AcoArmadura, d_linha: float = 4.0,
           titulo: str = "Flexão — armadura longitudinal") -> Tuple[Verificacao, Dict[str, float]]:
    """a armadura de tração (e a de compressão, se preciso) para Md ≥ 0 (a face de cima comprimida)
    na seção composta: retângulo de tensões σcd até λx (17.2.2 e); ductilidade x/d ≤ ξlim (14.6.4.3);
    armadura mínima pelo momento mínimo 0,8·W0·fctk,sup, 0,15 % no mínimo (17.3.5.2.1)"""
    sc, lam = conc.sigma_cd, conc.lam
    Md = abs(Md)
    v = Verificacao(titulo, norma="NBR 6118, 17.2.2 e 17.3.5.2", unidade="kN·cm")
    xlim = conc.xi_lim * d
    Alim, zlim = sec.bloco(lam * xlim)
    Mlim = sc * Alim * (d - zlim)
    As2 = 0.0
    if Md <= Mlim:
        lo, hi = 0.0, lam * xlim
        for _ in range(60):
            m = (lo + hi) / 2
            A_, z_ = sec.bloco(m)
            if sc * A_ * (d - z_) < Md:
                lo = m
            else:
                hi = m
        y = (lo + hi) / 2
        A_, z_ = sec.bloco(y)
        As1 = sc * A_ / aco.fyd if Md > 0 else 0.0
        x = y / lam
        v.passo("Altura do retângulo de tensões", "M<sub>d</sub> = σ<sub>cd</sub>·A<sub>c</sub>(λx)·(d − z<sub>c</sub>)",
                "σ<sub>cd</sub> = %s kN/cm², d = %s cm" % (fmt(sc, 3), fmt(d, 1)), "λx = %s cm" % fmt(y, 2), "NBR 6118, 17.2.2")
    else:
        x = xlim
        eps_s2 = conc.eps_cu * (x - d_linha) / x
        sig_s2 = N6118._sigma_s(eps_s2, aco)
        As2 = (Md - Mlim) / (sig_s2 * (d - d_linha))
        As1 = sc * Alim / aco.fyd + (Md - Mlim) / (aco.fyd * (d - d_linha))
        v.passo("Armadura dupla: o momento passa do limite de ductilidade", "M<sub>lim</sub> com x = ξ<sub>lim</sub>·d",
                "ξ<sub>lim</sub> = %s" % fmt(conc.xi_lim, 2), fmt(Mlim / 100, 2, "kN·m"), "NBR 6118, 14.6.4.3")
    W0 = sec.I / sec.yc
    Mmin = 0.8 * W0 * conc.fctk_sup
    As_min = max(Mmin / (aco.fyd * 0.9 * d), 0.0015 * sec.A)
    v.passo("Armadura de tração", "A<sub>s</sub> = σ<sub>cd</sub>·A<sub>c</sub>(λx)/f<sub>yd</sub>", "", fmt(As1, 2, "cm²"), "NBR 6118, 17.2.2")
    v.passo("Armadura mínima", "M<sub>d,mín</sub> = 0,8·W<sub>0</sub>·f<sub>ctk,sup</sub>; ρ<sub>mín</sub> = 0,15 %",
            "0,8 × %s × %s" % (fmt(W0, 0), fmt(conc.fctk_sup, 3)), fmt(As_min, 2, "cm²"), "NBR 6118, 17.3.5.2.1")
    As = max(As1, As_min)
    v.Sd, v.Rd = Md, max(Md, 1e-9)
    if As + As2 > 0.04 * sec.A:
        v.Rd = Md * 0.04 * sec.A / (As + As2)
        v.observacao = "a armadura passa de 4 % da seção (17.3.5.2.4): aumente a seção"
    return v, {"As": As, "As_comp": As2, "x": x, "x_d": x / d, "As_min": As_min, "Mlim": Mlim}


def estadio2(sec: SecaoViga, As: float, d: float, As2: float, d2: float, alfa_e: float) -> Tuple[float, float]:
    """(x, III) da seção fissurada (o concreto tracionado desprezado), a face de cima comprimida"""
    def f(x):
        S1, _ = sec.momentos_comprimidos(x)
        return S1 + (alfa_e - 1.0) * As2 * (x - d2) - alfa_e * As * (d - x)
    lo, hi = 1e-6, d
    for _ in range(80):
        m = (lo + hi) / 2
        if f(m) < 0:
            lo = m
        else:
            hi = m
    x = (lo + hi) / 2
    _S1, S2 = sec.momentos_comprimidos(x)
    III = S2 + alfa_e * As * (d - x) ** 2 + (alfa_e - 1.0) * As2 * (x - d2) ** 2
    return x, III


# ------------------------------------------------------------------ a estática da viga biapoiada

def estatica(xs: np.ndarray, w: np.ndarray) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """viga biapoiada com a carga distribuída w(x) (kN/cm, para baixo positiva) nos pontos xs (cm):
    (RA, RB, V(x), M(x))"""
    L = xs[-1] - xs[0]
    W = float(np.trapezoid(w, xs))
    RB = float(np.trapezoid(w * (xs - xs[0]), xs)) / L
    RA = W - RB
    cum = np.concatenate([[0.0], np.cumsum((w[1:] + w[:-1]) / 2 * np.diff(xs))])
    V = RA - cum
    M = np.concatenate([[0.0], np.cumsum((V[1:] + V[:-1]) / 2 * np.diff(xs))])
    return RA, RB, V, M


def _integral_unitaria(xs: np.ndarray, M: np.ndarray, EI: np.ndarray) -> Tuple[float, float]:
    """(flecha no meio, rotação no apoio A) por trabalhos virtuais: ∫M·m/EI dx"""
    L = xs[-1] - xs[0]
    x = xs - xs[0]
    m_meio = np.where(x <= L / 2, x / 2, (L - x) / 2)
    m_rot = 1.0 - x / L
    return float(np.trapezoid(M * m_meio / EI, xs)), float(np.trapezoid(M * m_rot / EI, xs))


# ------------------------------------------------------------------ as barras

def _arranjo_inferior(As: float, b: float, c_lat: float, bitolas=(10.0, 12.5, 16.0, 20.0, 25.0), max_camadas: int = 3):
    """(n, ø mm, camadas, y do centroide acima da face de baixo contado da face do estribo) com a menor
    área que cobre As e cabe em até `max_camadas` camadas na largura b (espaçamento de 18.3.2.2)"""
    melhor = None
    for fi in bitolas:
        a = BITOLAS[fi][0]
        n = max(2, math.ceil(As / a - 1e-9))
        ah = max(2.0, fi / 10.0, 1.2 * DMAX_AGREGADO)
        av = max(2.0, fi / 10.0, 0.5 * DMAX_AGREGADO)
        por_camada = int((b - 2 * c_lat + ah) // (fi / 10.0 + ah))
        if por_camada < 2:
            continue
        camadas = math.ceil(n / por_camada)
        if camadas > max_camadas:
            continue
        # centroide: as camadas cheias de baixo para cima
        ys, resto = [], n
        for k in range(camadas):
            nk = min(por_camada, resto)
            ys.append((nk, fi / 20.0 + k * (fi / 10.0 + av)))
            resto -= nk
        yg = sum(nk * y for nk, y in ys) / n
        # cada camada a mais pesa como 5 % de área: prefere-se menos camadas com área parecida
        cand = (n * a * (1 + 0.05 * (camadas - 1)), camadas, n, fi, yg)
        if melhor is None or cand[:2] < melhor[:2]:
            melhor = cand
    if melhor is None:
        return None
    _A, camadas, n, fi, yg = melhor
    return n, fi, camadas, yg


# ------------------------------------------------------------------ a viga

@dataclass
class VigaDimensionada:
    marca: str
    funcao: str
    secao: SecaoViga                           # na seção mais alta (o meio do vão)
    secao_apoio: SecaoViga
    vao: float                                 # m, de cálculo
    comprimento: float                         # m, da peça
    armadura: Dict = field(default_factory=dict)
    resultado: Optional[Resultado] = None
    apoio: Optional[Resultado] = None
    elastomero: Optional[Resultado] = None
    reacoes: Dict[str, float] = field(default_factory=dict)   # kN por apoio (característicos)
    quantidade: int = 0
    volume: float = 0.0                        # m³
    aco_kg: float = 0.0
    alternativas: List[dict] = field(default_factory=list)

    @property
    def peso_kN(self) -> float:
        return self.volume * PESO_CONCRETO

    @property
    def ok(self) -> bool:
        return all(r is not None and r.ok for r in (self.resultado, self.apoio, self.elastomero))

    def texto_armadura(self) -> str:
        a = self.armadura
        if not a:
            return ""
        return "%d ø%s (inf.%s) + %d ø%s (sup.) + estribos ø%s c/ %s (%d ramos)" % (
            a["n_inf"], fmt(a["fi_inf"], 1), "" if a["camadas"] == 1 else ", %d camadas" % a["camadas"],
            a["n_sup"], fmt(a["fi_sup"], 1), fmt(a["fi_est"], 1), fmt(a["s_est"], 1), a["ramos"])


@dataclass
class CasoViga:
    """o que a viga recebe (kN/m, características; além do peso próprio) e como ela é"""
    marca: str
    funcao: str                                # "viga-calha", "viga de travamento", "viga de cobertura"
    vao: float                                 # m, de cálculo
    comprimento: float                         # m, da peça
    g: float = 0.0                             # permanente adicional
    q: float = 0.0                             # variável
    psi_q: Tuple[float, float, float] = (0.8, 0.7, 0.6)
    succao: float = 0.0                        # vento para cima (kN/m, positivo para cima)
    limite_flecha: float = 250.0               # L/…
    tabela_flecha: str = "NBR 9062, Tabela 9"
    extremidade: str = "sem recorte"           # ou "dente Gerber"
    dente_h: float = 0.5                       # fração da altura no apoio que fica no dente
    dente_c: float = 25.0                      # cm, comprimento do dente
    alcas: float = 0.10                        # distância das alças às pontas / comprimento
    quantidade: int = 1


@dataclass
class MeioViga:
    """o ambiente e os materiais da viga"""
    conc: Concreto
    aco: AcoArmadura
    c_nom: float                               # cobrimento (cm)
    caa: str = "II"
    pre_fabricado: bool = False
    umidade: float = 75.0
    idade_saque_dias: float = 3.0
    idade_montagem_dias: float = 30.0
    delta_T: float = 15.0                      # °C (11.4.2.1 a)
    shore: int = 60


def _gama_pp() -> float:
    from nucleo import cargas
    return cargas.GAMA_G["pré-moldada"][0]


def verificar_viga(caso: CasoViga, secao_em: Callable[[float], SecaoViga], meio: MeioViga) -> VigaDimensionada:
    """todas as verificações da viga com a seção dada (secao_em(x) com x em cm do apoio A)"""
    conc, aco = meio.conc, meio.aco
    L = caso.vao * 100.0
    xs = np.linspace(0.0, L, N_SECOES)
    secs = [secao_em(x) for x in xs]
    s_meio = max(secs, key=lambda s: s.h)
    s_apoio = secs[0]
    r = Resultado("%s %s" % (caso.funcao.capitalize(), caso.marca), perfil=s_meio.texto() if s_meio is s_apoio else
                  "%s (apoio %s cm, meio %s cm)" % (s_meio.texto(), fmt(s_apoio.h, 0), fmt(s_meio.h, 0)), material=conc.nome)
    gpp = _gama_pp()
    w_pp = np.array([s.peso for s in secs]) / 100.0              # kN/cm
    w_g = np.full_like(xs, caso.g / 100.0)
    w_q = np.full_like(xs, caso.q / 100.0)
    w_w = np.full_like(xs, caso.succao / 100.0)
    RApp, _, Vpp, Mpp = estatica(xs, w_pp)
    RAg, _, Vg, Mg = estatica(xs, w_g)
    RAq, _, Vq, Mq = estatica(xs, w_q)
    RAw, _, Vw, Mw = estatica(xs, w_w)
    psi0, psi1, psi2 = caso.psi_q
    Md = gpp * Mpp + 1.4 * Mg + 1.5 * Mq
    Vd0 = gpp * RApp + 1.4 * RAg + 1.5 * RAq
    Md_neg = np.minimum(1.0 * Mpp + 1.0 * Mg - 1.4 * Mw, 0.0)       # a sucção levantando a viga
    M_freq = Mpp + Mg + psi1 * Mq
    M_qp = Mpp + Mg + psi2 * Mq
    r.carga("Peso próprio (seção do meio)", "g<sub>pp</sub> = 25·A<sub>c</sub>", "25 × %s" % fmt(s_meio.A / 1e4, 4), fmt(s_meio.peso, 2, "kN/m"), "NBR 6118, 8.2.2")
    if caso.g:
        r.carga("Permanente adicional", "g", "", fmt(caso.g, 2, "kN/m"), "")
    if caso.q:
        r.carga("Variável", "q", "ψ<sub>1</sub> = %s, ψ<sub>2</sub> = %s" % (fmt(psi1, 1), fmt(psi2, 1)), fmt(caso.q, 2, "kN/m"), "NBR 8681")
    if caso.succao:
        r.carga("Vento (sucção, para cima)", "w", "", fmt(caso.succao, 2, "kN/m"), "NBR 6123")
    r.carga("Combinação última", "M<sub>d</sub> = %s·M<sub>pp</sub> + 1,4·M<sub>g</sub> + 1,5·M<sub>q</sub>" % fmt(gpp, 1), "",
            fmt(float(Md.max()) / 100, 2, "kN·m"), "NBR 8681 (pré-moldada: γ = %s)" % fmt(gpp, 1))

    c = meio.c_nom
    # ---- a armadura de baixo: altura útil com uma camada, depois com o arranjo escolhido
    yg = 1.0
    arr = None
    for _ in range(3):
        dist = c + ESTRIBO + yg
        As_req, pior = 0.0, None
        for i, s in enumerate(secs):
            if Md[i] <= 0:
                continue
            vf, df = flexao(s, s.h - dist, float(Md[i]), conc, aco, d_linha=c + ESTRIBO + 0.5)
            if pior is None or (df["As"], Md[i]) > (As_req, Md[pior[0]]):
                As_req, pior = df["As"], (i, vf, df)
        arr = _arranjo_inferior(As_req, s_apoio.b_inf, c + ESTRIBO)
        if arr is None:
            break
        if abs(arr[3] - yg) < 0.05:
            break
        yg = arr[3]
    if arr is None or pior is None:
        v = Verificacao("Flexão — armadura longitudinal", norma="NBR 6118, 17.2.2", Sd=float(Md.max()), Rd=0.0, unidade="kN·cm")
        v.indeterminada = True
        v.observacao = "a armadura não cabe na largura da seção em três camadas: aumente a seção"
        r.add(v)
        return VigaDimensionada(caso.marca, caso.funcao, s_meio, s_apoio, caso.vao, caso.comprimento, resultado=r,
                                quantidade=caso.quantidade)
    n_inf, fi_inf, camadas, yg = arr
    As_inf = n_inf * BITOLAS[fi_inf][0]
    dist = c + ESTRIBO + yg
    i_c, vf, df = pior
    s_c = secs[i_c]
    MRd, xr = momento_resistente(s_c, As_inf, s_c.h - dist, conc, aco)
    vf.Sd, vf.Rd = float(Md[i_c]), MRd
    vf.titulo = "Flexão — armadura de baixo (x = %s m)" % fmt(xs[i_c] / 100, 2)
    vf.passo("Adotado", "", "%d ø %s%s" % (n_inf, fmt(fi_inf, 1), "" if camadas == 1 else " em %d camadas" % camadas),
             "%s cm² → M<sub>Rd</sub> = %s kN·m" % (fmt(As_inf, 2), fmt(MRd / 100, 2)), "NBR 6118, 18.3.2.2")
    if df["As_comp"] > 0:
        vf.observacao = "armadura dupla: A's = %s cm² em cima" % fmt(df["As_comp"], 2)
    r.add(vf)

    # ---- a armadura de cima: porta-estribos, compressão, momento negativo do vento e do içamento
    d_sup = c + ESTRIBO + 0.5
    As_sup_req = max(df["As_comp"], 0.0)
    As_neg, i_neg = 0.0, None
    for i, s in enumerate(secs):
        if Md_neg[i] < 0:
            vn, dn = flexao(s.invertida(), s.h - d_sup, float(-Md_neg[i]), conc, aco, titulo="Flexão — momento negativo (sucção)")
            if dn["As"] > As_neg:
                As_neg, i_neg = dn["As"], (i, vn)
    # içamento (5.3.2): as alças a α·comprimento das pontas, carga γf·βa·gk
    comp = caso.comprimento * 100.0
    a_alca = caso.alcas * comp
    g_med = float(np.mean([s.peso for s in secs])) / 100.0
    g_eq = N9062.GAMA_F_DINAMICO * N9062.BETA_A_PILAR * g_med
    M_ic_neg = g_eq * a_alca ** 2 / 2.0
    M_ic_pos = g_eq * (comp - 2 * a_alca) ** 2 / 8.0 - M_ic_neg
    z_sup = 0.9 * (s_apoio.h - d_sup)
    As_ic = M_ic_neg / (aco.fyd * z_sup)
    As_sup_req = max(As_sup_req, As_neg, As_ic, 2 * BITOLAS[8.0][0])
    n_sup, fi_sup = N9062._barras(As_sup_req, (8.0, 10.0, 12.5, 16.0, 20.0), n_min=2)
    As_sup = n_sup * BITOLAS[fi_sup][0]
    if i_neg is not None:
        i, vn = i_neg
        s = secs[i]
        MRn, _x = momento_resistente(s.invertida(), As_sup, s.h - d_sup, conc, aco)
        vn.Sd, vn.Rd = float(-Md_neg[i]), MRn
        vn.passo("Combinação", "M<sub>d</sub> = 1,0·M<sub>pp</sub> + 1,0·M<sub>g</sub> − 1,4·M<sub>vento</sub>", "", fmt(vn.Sd / 100, 2, "kN·m"), "NBR 8681")
        vn.passo("Adotado em cima", "", "%d ø %s" % (n_sup, fmt(fi_sup, 1)), "M<sub>Rd</sub> = %s kN·m" % fmt(MRn / 100, 2), "")
        r.add(vn)

    # ---- cisalhamento no apoio
    d0 = s_apoio.h - dist
    vs, ds = N6118.cisalhamento(s_apoio.bw, d0, Vd0, conc, aco)
    ramos = 2 * s_apoio.almas
    fi_e, s_e = N6118.estribos(ds["asw"], ds["s_max"], ramos=ramos)
    for v in vs:
        v.titulo += " (apoio)"
        r.add(v)
    vs[-1].passo("Estribos", "", "%d ramos (%d alma%s)" % (ramos, s_apoio.almas, "s" if s_apoio.almas > 1 else ""),
                 "ø%s c/ %s cm" % (fmt(fi_e, 1), fmt(s_e, 1)), "NBR 6118, 18.3.3.2")

    # ---- ELS-W: abertura de fissuras (combinação frequente)
    Es = aco.Es
    fctm = conc.fctm
    pior_w = None
    for i, s in enumerate(secs):
        if M_freq[i] <= 0:
            continue
        d_i = s.h - dist
        x2, I2 = estadio2(s, As_inf, d_i, As_sup, d_sup, 15.0)
        sig = 15.0 * M_freq[i] * (d_i - x2) / I2                   # kN/cm²
        if pior_w is None or sig > pior_w[0]:
            pior_w = (sig, i, x2)
    wk_lim = WK_LIMITE.get(meio.caa, 0.3)
    vw = Verificacao("Abertura de fissuras (ELS-W, combinação frequente)", norma="NBR 6118, 17.3.3.2", unidade="mm", Rd=wk_lim)
    if pior_w is not None:
        sig, i, x2 = pior_w
        fi_cm = fi_inf / 10.0
        n_cam1 = n_inf if camadas == 1 else math.ceil(n_inf / camadas)
        larg = min(s_apoio.b_inf / n_cam1, 15.0 * fi_cm)
        alt = min(c + ESTRIBO + fi_cm / 2 + 7.5 * fi_cm, secs[i].h - x2)
        Acr = larg * alt
        rho_r = BITOLAS[fi_inf][0] / Acr
        sig_MPa, Es_MPa, fctm_MPa = sig * 10, Es * 10, fctm * 10
        w1 = fi_inf / (12.5 * ETA1) * sig_MPa / Es_MPa * 3 * sig_MPa / fctm_MPa
        w2 = fi_inf / (12.5 * ETA1) * sig_MPa / Es_MPa * (4 / rho_r + 45)
        vw.Sd = min(w1, w2)
        vw.passo("Tensão na armadura no estádio II (α<sub>e</sub> = 15), x = %s m" % fmt(xs[i] / 100, 2),
                 "σ<sub>s</sub> = α<sub>e</sub>·M<sub>freq</sub>·(d − x<sub>II</sub>)/I<sub>II</sub>",
                 "M = %s kN·m, x<sub>II</sub> = %s cm" % (fmt(M_freq[i] / 100, 2), fmt(x2, 1)), fmt(sig_MPa, 0, "MPa"), "NBR 6118, 17.3.3.2")
        vw.passo("Região de envolvimento", "A<sub>cr</sub> (7,5ø em volta da barra); ρ<sub>r</sub> = A<sub>s,barra</sub>/A<sub>cr</sub>",
                 "%s × %s cm" % (fmt(larg, 1), fmt(alt, 1)), "ρ<sub>r</sub> = %s" % fmt(rho_r, 4), "NBR 6118, Figura 17.4")
        vw.passo("Abertura característica (o menor valor)", "w<sub>k</sub> = ø/(12,5η<sub>1</sub>)·σ<sub>s</sub>/E<sub>s</sub>·min(3σ<sub>s</sub>/f<sub>ctm</sub>; 4/ρ<sub>r</sub> + 45)",
                 "%s ; %s" % (fmt(w1, 3), fmt(w2, 3)), fmt(vw.Sd, 3, "mm"), "NBR 6118, 17.3.3.2")
        vw.passo("Limite (CAA %s, concreto armado)" % meio.caa, "w<sub>k</sub> ≤ %s mm" % fmt(wk_lim, 1), "", "", "NBR 6118, Tabela 13.4")
    else:
        vw.dispensada = True
    r.add(vw)

    # ---- ELS-DEF: flecha (quase permanente, com a fluência)
    Ecs = conc.Ecs
    alfa_e = Es / Ecs
    Ma = float(M_qp.max())
    EI = np.empty_like(xs)
    for i, s in enumerate(secs):
        Ic = s.I
        Mr = s.alfa_forma * fctm * Ic / s.yc
        if Ma <= Mr:
            EI[i] = Ecs * Ic
        else:
            _x2, I2 = estadio2(s, As_inf, s.h - dist, As_sup, d_sup, alfa_e)
            k = (Mr / Ma) ** 3
            EI[i] = min(Ecs * (k * Ic + (1 - k) * I2), Ecs * Ic)
    f0, _ = _integral_unitaria(xs, M_qp, EI)
    # t0 ponderado (17.3.2.1.2): o peso próprio desde o saque, o resto desde a montagem
    P_pp = float(np.trapezoid(w_pp, xs))
    P_resto = float(np.trapezoid(w_g + psi2 * w_q, xs))
    t0 = (P_pp * meio.idade_saque_dias + P_resto * meio.idade_montagem_dias) / max(P_pp + P_resto, 1e-9) / 30.0
    dxi = 2.0 - xi_tempo(t0)
    i_m = int(np.argmax([s.h for s in secs]))
    rho_l = As_sup / (secs[i_m].b_sup * (secs[i_m].h - dist))
    af = dxi / (1 + 50 * rho_l)
    f_tot = f0 * (1 + af)
    f_lim = L / caso.limite_flecha
    vd = Verificacao("Flecha (ELS-DEF, quase permanente, com a fluência)", norma="NBR 6118, 17.3.2.1 e %s" % caso.tabela_flecha,
                     Sd=f_tot, Rd=f_lim, unidade="cm")
    Mr_m = secs[i_m].alfa_forma * fctm * secs[i_m].I / secs[i_m].yc
    vd.passo("Momento de fissuração (meio do vão)", "M<sub>r</sub> = α·f<sub>ct,m</sub>·I<sub>c</sub>/y<sub>t</sub>",
             "α = %s (%s)" % (fmt(secs[i_m].alfa_forma, 1), secs[i_m].tipo), fmt(Mr_m / 100, 2, "kN·m"), "NBR 6118, 17.3.1")
    vd.passo("Rigidez equivalente (seção a seção)", "(EI)<sub>eq</sub> = E<sub>cs</sub>{(M<sub>r</sub>/M<sub>a</sub>)³I<sub>c</sub> + [1 − (M<sub>r</sub>/M<sub>a</sub>)³]I<sub>II</sub>} ≤ E<sub>cs</sub>I<sub>c</sub>",
             "M<sub>a</sub> = %s kN·m; α<sub>e</sub> = %s" % (fmt(Ma / 100, 2), fmt(alfa_e, 2)), "", "NBR 6118, 17.3.2.1.1")
    vd.passo("Flecha imediata", "f<sub>0</sub> = ∫M·m/(EI)<sub>eq</sub>dx", "", fmt(f0, 2, "cm"), "")
    vd.passo("Fluência", "α<sub>f</sub> = Δξ/(1 + 50ρ'), Δξ = 2 − ξ(t<sub>0</sub>)",
             "t<sub>0</sub> = %s meses (ponderado); ρ' = %s" % (fmt(t0, 2), fmt(rho_l, 4)), fmt(af, 2), "NBR 6118, 17.3.2.1.2")
    vd.passo("Flecha total", "f = f<sub>0</sub>·(1 + α<sub>f</sub>) ≤ L/%s" % fmt(caso.limite_flecha, 0), "%s × (1 + %s)" % (fmt(f0, 2), fmt(af, 2)),
             fmt(f_tot, 2, "cm"), caso.tabela_flecha)
    r.add(vd)

    # ---- estabilidade lateral (NBR 9062, 6.1.6)
    bf = s_meio.b_compressao
    L_ic = comp - 2 * a_alca
    L_est = max(L, L_ic)
    h_max = s_meio.h
    ve1 = Verificacao("Estabilidade lateral — esbeltez L/b<sub>f</sub>", norma="NBR 9062, 6.1.6", Sd=L_est / bf, Rd=50.0, unidade="")
    ve1.passo("Fases", "içamento: L = %s cm entre as alças; montagem: L = %s cm entre os apoios" % (fmt(L_ic, 0), fmt(L, 0)), "", "", "NBR 9062, 6.1.2")
    ve1.passo("Menor largura comprimida", "b<sub>f</sub>", "", fmt(bf, 0, "cm"), "NBR 9062, 6.1.5")
    ve1.passo("L/b<sub>f</sub> ≤ 50", "", "%s / %s" % (fmt(L_est, 0), fmt(bf, 0)), fmt(L_est / bf, 1), "")
    r.add(ve1)
    ve2 = Verificacao("Estabilidade lateral — L·h/b<sub>f</sub>²", norma="NBR 9062, 6.1.6", Sd=L_est * h_max / bf ** 2, Rd=500.0, unidade="")
    ve2.passo("L·h/b<sub>f</sub>² ≤ 500", "", "%s × %s / %s²" % (fmt(L_est, 0), fmt(h_max, 0), fmt(bf, 0)), fmt(ve2.Sd, 0), "")
    r.add(ve2)
    if s_meio.tipo == "U":
        ve1.observacao = "viga-calha: b<sub>f</sub> = a largura externa (as paredes ligadas pelo fundo) — confira"

    # ---- içamento: o momento nas alças e a força nas alças
    MRd_ic = As_sup * aco.fyd * z_sup
    vi = Verificacao("Içamento — momento negativo nas alças", norma="NBR 9062, 5.3.2", Sd=M_ic_neg, Rd=MRd_ic, unidade="kN·cm")
    vi.passo("Carga dinâmica", "g<sub>eq,d</sub> = γ<sub>f</sub>·β<sub>a</sub>·g<sub>k</sub>",
             "1,30 × 1,3 × %s" % fmt(g_med * 100, 2), fmt(g_eq * 100, 2, "kN/m"), "NBR 9062, 5.3.2")
    vi.passo("Alças a %s cm das pontas" % fmt(a_alca, 0), "M<sup>−</sup> = g<sub>eq,d</sub>·a²/2; M<sup>+</sup> = g<sub>eq,d</sub>·ℓ²/8 − M<sup>−</sup>",
             "", "M<sup>−</sup> = %s; M<sup>+</sup> = %s kN·m" % (fmt(M_ic_neg / 100, 2), fmt(M_ic_pos / 100, 2)), "")
    vi.passo("Resistente (armadura de cima, z = 0,9d)", "M<sub>Rd</sub> = A<sub>s,sup</sub>·f<sub>yd</sub>·z", "%s × %s × %s" % (fmt(As_sup, 2), fmt(aco.fyd, 2), fmt(z_sup, 1)),
             fmt(MRd_ic / 100, 2, "kN·m"), "")
    r.add(vi)
    G_tot = float(np.trapezoid([s.peso / 100.0 for s in secs], xs)) * comp / L
    F_alca = N9062.GAMA_F_DINAMICO * 3.0 * G_tot / 2.0
    fy_a36 = 25.0
    fyd_a36 = fy_a36 / 1.10
    As_ramo = F_alca / math.sin(math.radians(45.0)) / 2.0 / fyd_a36
    fi_alca = next((f for f in (10.0, 12.5, 16.0, 20.0, 25.0) if BITOLAS[f][0] >= As_ramo), None)
    va = Verificacao("Alças de içamento (ASTM A36, dois ramos, cabo a 45°)", norma="NBR 9062, 5.3.2 e 5.3.3", Sd=As_ramo,
                     Rd=BITOLAS[fi_alca][0] if fi_alca else 0.0, unidade="cm²")
    va.passo("Força de cálculo por alça", "F<sub>d</sub> = γ<sub>f</sub>·β<sub>a</sub>·G/2, β<sub>a</sub> = 3", "1,30 × 3 × %s / 2" % fmt(G_tot, 1),
             fmt(F_alca, 1, "kN"), "NBR 9062, 5.3.2.2")
    va.passo("Área por ramo", "A = F<sub>d</sub>/(2·sen 45°·f<sub>y</sub>/γ<sub>a1</sub>)", "f<sub>y</sub> = 250 MPa, γ<sub>a1</sub> = 1,10",
             "%s cm² → ø%s" % (fmt(As_ramo, 2), fmt(fi_alca, 1) if fi_alca else "— (passa de ø25)"), "NBR 9062, 5.3.3.6")
    va.observacao = "CA-50/CA-60 são proibidos em alças (5.3.3.5); verificar a ancoragem e as tensões radiais no concreto (5.3.3.3 e 5.3.3.4)"
    if fi_alca is None:
        va.indeterminada = True
    r.add(va)

    # ---- apoio e elastômero
    Fd = Vd0
    apoio = _apoio(caso, s_apoio, d0, Fd, conc, aco, meio)
    Rg = RApp + RAg
    elast = _elastomero(caso, s_apoio, Rg, RAq, RAw, Fd, L, xs, Mpp + Mg, Mq, EI, meio, aco)

    # ---- quantidades
    vol = float(np.trapezoid([s.A / 1e4 for s in secs], xs / 100.0)) * comp / L
    kg_long = (n_inf * BITOLAS[fi_inf][1] + n_sup * BITOLAS[fi_sup][1]) * (comp / 100.0 + 0.3)
    perim_e = 2 * (s_meio.h - 2 * c) / 100.0 * s_apoio.almas + 2 * (max(s_apoio.bw / s_apoio.almas - 2 * c, 5.0)) / 100.0 + 0.2
    kg_est = math.ceil(comp / s_e) * perim_e * BITOLAS[fi_e][1]
    arm = {"n_inf": n_inf, "fi_inf": fi_inf, "camadas": camadas, "As_inf": As_inf, "n_sup": n_sup, "fi_sup": fi_sup,
           "As_sup": As_sup, "fi_est": fi_e, "s_est": s_e, "ramos": ramos, "d": s_meio.h - dist, "d_apoio": d0, "alca": fi_alca,
           "a_alca": a_alca}
    r.dados.update({"xs": xs.tolist(), "Md": Md.tolist(), "M_qp": M_qp.tolist(), "Vd": Vd0, "f": f_tot, "wk": vw.Sd,
                    "armadura": arm})
    r.hipotese("vao", "Viga biapoiada de %s m (vão de cálculo) e %s m de peça; carga distribuída uniforme%s."
               % (fmt(caso.vao, 2), fmt(caso.comprimento, 2), "; peso próprio com a altura variável" if s_meio is not s_apoio else ""), "rotina")
    r.hipotese("icamento", "Içamento por duas alças a %s%% do comprimento das pontas; resistência do concreto no saque a especificar "
               "(mínimo 15 MPa, NBR 9062, 8.2.2.2)." % fmt(caso.alcas * 100, 0), "norma")
    viga = VigaDimensionada(caso.marca, caso.funcao, s_meio, s_apoio, caso.vao, caso.comprimento, arm, r, apoio, elast,
                            {"pp": RApp, "g": RAg, "q": RAq, "w": RAw, "Fd": Fd}, caso.quantidade, vol, kg_long + kg_est)
    return viga


def _apoio(caso: CasoViga, s: SecaoViga, d0: float, Fd: float, conc: Concreto, aco: AcoArmadura, meio: MeioViga) -> Resultado:
    fyd = min(aco.fyd, 43.5)
    Hd = N9062.HD_FD["elastômero"] * Fd
    if caso.extremidade == "dente Gerber":
        h_d = round(caso.dente_h * s.h / 5.0) * 5.0
        a = caso.dente_c / 2.0
        b = s.b_max
        r = N9062.consolo(b, h_d, a, Fd, conc, aco, apoio="elastômero", pre_fabricado=meio.pre_fabricado,
                          elemento="Dente Gerber — %s %s" % (caso.funcao, caso.marca))
        r.perfil = "dente %s × %s cm, comprimento %s cm (bloco de extremidade maciço)" % (fmt(b, 0), fmt(h_d, 0), fmt(caso.dente_c, 0))
        gn = r.dados.get("gn", N9062.gama_n(meio.pre_fabricado, False))
        As_sus = gn * Fd / fyd
        n, fi = N9062._barras(As_sus / 2.0, (8.0, 10.0, 12.5, 16.0), n_min=2)      # estribos de 2 ramos
        vs = Verificacao("Dente Gerber — armadura de suspensão", norma="NBR 9062, 7.4.6", Sd=As_sus, Rd=2 * n * BITOLAS[fi][0], unidade="cm²")
        vs.passo("Toda a carga do dente, com f<sub>yd</sub> ≤ 435 MPa", "A<sub>s,susp</sub> = γ<sub>n</sub>·F<sub>d</sub>/f<sub>yd</sub>",
                 "%s × %s / %s" % (fmt(gn, 1), fmt(Fd, 1), fmt(fyd, 2)), fmt(As_sus, 2, "cm²"), "NBR 9062, 7.4.6.1")
        vs.passo("Estribos fechados junto ao dente, envolvendo a armadura da viga", "", "", "%d estribos ø%s" % (n, fmt(fi, 1)), "NBR 9062, 7.4.6.2")
        r.add(vs)
        lb, _p = N9062.ancoragem(r.dados["barras"][1], conc, aco, boa_aderencia=False)
        vh = Verificacao("Dente Gerber — estribos horizontais", norma="NBR 9062, 7.4.5.1", Sd=0.0, Rd=1.0, unidade="")
        vh.passo("Ancorados na face externa do dente e entrando 1,5·ℓ<sub>b</sub> na viga", "1,5·ℓ<sub>b</sub> (má aderência)",
                 "", fmt(1.5 * lb, 0, "cm"), "NBR 9062, 7.4.5.1")
        vh.passo("Início da ancoragem do tirante na viga", "(d<sub>viga</sub> − d) do primeiro estribo", "", fmt(d0 - r.dados["d"], 0, "cm"), "NBR 9062, 7.4.4.2")
        r.add(vh)
        r.dados["h_dente"] = h_d
        return r
    r = Resultado("Apoio sem recorte — %s %s" % (caso.funcao, caso.marca), perfil="b = %s cm" % fmt(s.b_inf, 0), material=conc.nome)
    Asd = (Fd / 1.2 + Hd) / fyd
    n, fi = N9062._barras(Asd, (10.0, 12.5, 16.0, 20.0), n_min=2)
    v = Verificacao("Apoio sem recorte — tirante", norma="NBR 9062, 7.5.1", Sd=Asd, Rd=n * BITOLAS[fi][0], unidade="cm²")
    v.passo("Força horizontal (elastômero)", "H<sub>d</sub> = 0,16·F<sub>d</sub>", "0,16 × %s" % fmt(Fd, 1), fmt(Hd, 1, "kN"), "NBR 9062, 7.3.9")
    v.passo("Armadura do tirante", "A<sub>sd</sub> = (F<sub>d</sub>/1,2 + H<sub>d</sub>)/f<sub>yd</sub>",
            "(%s/1,2 + %s) / %s" % (fmt(Fd, 1), fmt(Hd, 1), fmt(fyd, 2)), fmt(Asd, 2, "cm²"), "NBR 9062, 7.5.1")
    v.passo("Adotado", "barras horizontais com barra transversal soldada ou alça, 2·ℓ<sub>b</sub> para dentro", "", "%d ø%s" % (n, fmt(fi, 1)), "NBR 9062, Figura 24")
    r.add(v)
    Ash = Fd / (8.0 * fyd)
    nh, fih = N9062._barras(Ash, (6.3, 8.0, 10.0), n_min=2)
    vc = Verificacao("Apoio sem recorte — costura horizontal e vertical", norma="NBR 9062, 7.5.2", Sd=Ash, Rd=nh * BITOLAS[fih][0], unidade="cm²")
    vc.passo("Cada uma", "A<sub>sh</sub> = A<sub>sv</sub> = F<sub>d</sub>/(8·f<sub>yd</sub>)", "%s / (8 × %s)" % (fmt(Fd, 1), fmt(fyd, 2)),
             fmt(Ash, 2, "cm²") + " → %d ø%s" % (nh, fmt(fih, 1)), "NBR 9062, 7.5.2")
    r.add(vc)
    r.dados.update({"Asd": Asd, "barras": (n, fi), "costura": (nh, fih), "Hd": Hd})
    return r


def _elastomero(caso: CasoViga, s: SecaoViga, Rg: float, Rq: float, Rw: float, Fd: float, L: float, xs, Mg, Mq, EI,
                meio: MeioViga, aco_pino: AcoArmadura) -> Resultado:
    """o aparelho simples sob a ponta da viga: o menor (a na direção do vão, b na largura) que passa; a
    força horizontal da variação de temperatura (11.4.2.1) e da retração depois da montagem (Tabela 8.1)"""
    esp_fic = 2 * s.A / s.perimetro
    ecs = retracao(meio.umidade, meio.idade_montagem_dias, esp_fic) / 1000.0
    delta = (ALFA_TERMICO * meio.delta_T + ecs) * L / 2.0
    _f, th_g = _integral_unitaria(xs, Mg, EI)
    _f, th_q = _integral_unitaria(xs, Mq, EI)
    b_max = max(10.0, min(40.0, math.floor((s.b_inf - 5.0) / 5.0) * 5.0))
    G = N9062.SHORE_G[meio.shore]
    opcoes = sorted(((a_el, b_el, h_el) for h_el in (1.0, 1.5, 2.0) for a_el in (10.0, 12.0, 15.0, 20.0, 25.0)
                     for b_el in np.arange(10.0, b_max + 0.1, 5.0) if b_el >= a_el), key=lambda o: (o[2], o[0] * o[1]))
    escolhido, so_minima, ultimo = None, None, None
    for a_el, b_el, h_el in opcoes:
        Hk = G * a_el * b_el * delta / h_el
        ultimo = N9062.elastomero_simples(a_el, float(b_el), h_el, Rg, Rq, Hk, meio.shore, abs(th_g), abs(th_q),
                                          elemento="Elastômero — %s %s" % (caso.funcao, caso.marca))
        falhas = [v for v in ultimo.verificacoes if not v.ok]
        if not falhas:
            escolhido = (ultimo, Hk)
            break
        if so_minima is None and all("tensão mínima" in v.titulo for v in falhas):
            so_minima = (ultimo, Hk)
    pino = escolhido is None and so_minima is not None
    r, Hk = escolhido or so_minima or (ultimo, 0.0)
    fyd = min(aco_pino.fyd, 43.5)
    T = max(1.4 * Rw - 0.9 * Rg, 0.0)
    if pino:
        vmin = next(v for v in r.verificacoes if "tensão mínima" in v.titulo)
        vmin.dispensada = True
        vmin.observacao = ("a reação da viga é pequena para o aparelho não deslizar (7.2.1.6.22 a): o deslizamento fica "
                           "impedido pelo chumbador (pino) que atravessa o aparelho")
    if pino or T > 0:
        Hd = max(1.4 * Hk, N9062.HD_FD["elastômero"] * Fd)
        As_v = Hd / (0.6 * fyd)
        As_t = T / fyd
        fi = next((f for f in (16.0, 20.0, 25.0, 32.0) if BITOLAS[f][0] >= max(As_v + As_t, 1e-9)), None)
        vp = Verificacao("Chumbador (pino) no apoio — corte%s" % (" e tração" if T > 0 else ""), norma="NBR 9062, 7.2.1.6.22 e 7.3.9",
                         Sd=As_v + As_t, Rd=BITOLAS[fi][0] if fi else 0.0, unidade="cm²")
        if pino:
            vp.passo("Por que o pino", "N<sub>mín,k</sub>/A' ≥ 1 + a/b não é atingido nem no menor aparelho",
                     "R<sub>g</sub> = %s kN" % fmt(Rg, 1), "deslizamento impedido pelo pino", "NBR 9062, 7.2.1.6.22 a)")
        vp.passo("Força horizontal de cálculo", "H<sub>d</sub> = máx(1,4·H<sub>k</sub>; 0,16·F<sub>d</sub>)",
                 "máx(1,4 × %s; 0,16 × %s)" % (fmt(Hk, 1), fmt(Fd, 1)), fmt(Hd, 1, "kN"), "NBR 9062, 7.3.9")
        vp.passo("Corte no aço do pino", "A<sub>s</sub> ≥ H<sub>d</sub>/(0,6·f<sub>yd</sub>)", "%s / (0,6 × %s)" % (fmt(Hd, 1), fmt(fyd, 2)),
                 fmt(As_v, 2, "cm²"), "")
        if T > 0:
            vp.passo("Tração pela sucção do vento", "T<sub>d</sub> = 1,4·R<sub>w</sub> − 0,9·R<sub>g</sub>", "1,4 × %s − 0,9 × %s" % (fmt(Rw, 1), fmt(Rg, 1)),
                     fmt(T, 1, "kN") + " → %s cm²" % fmt(As_t, 2), "NBR 8681")
        vp.passo("Adotado", "um chumbador por apoio, grauteado no consolo", "", "ø%s CA-50" % fmt(fi, 1) if fi else "—", "")
        vp.observacao = ("modelo adotado pelo programa: o corte só no aço do pino (0,6·f<sub>yd</sub>); a NBR 9062 não traz a conta do pino "
                         "ao corte — confira o efeito pino no concreto e a ancoragem (ℓ<sub>b</sub>)")
        if fi is None:
            vp.indeterminada = True
        r.add(vp)
        r.dados["chumbador"] = fi
    r.carga("Deslocamento imposto na ponta", "δ = (α·ΔT + ε<sub>cs</sub>)·L/2",
            "(10⁻⁵ × %s + %s) × %s / 2" % (fmt(meio.delta_T, 0), fmt(ecs, 5), fmt(L, 0)), fmt(delta, 3, "cm"), "NBR 6118, 8.2.3, 11.4.2.1 e Tabela 8.1")
    r.carga("Retração depois da montagem", "ε<sub>cs</sub>(t<sub>∞</sub>, t<sub>0</sub>)",
            "U = %s %%, t<sub>0</sub> = %s dias, 2A<sub>c</sub>/u = %s cm" % (fmt(meio.umidade, 0), fmt(meio.idade_montagem_dias, 0), fmt(esp_fic, 1)),
            fmt(ecs * 1000, 3, "‰"), "NBR 6118, Tabela 8.1")
    r.carga("Rotação no apoio", "θ = ∫M·(1 − x/L)/(EI)<sub>eq</sub>dx", "", "θ<sub>g</sub> = %s; θ<sub>q</sub> = %s rad" % (fmt(abs(th_g), 4), fmt(abs(th_q), 4)), "")
    return r


def dimensionar_viga(caso: CasoViga, candidatos: Sequence[Tuple[str, Callable[[float], SecaoViga]]], meio: MeioViga) -> VigaDimensionada:
    """a seção mais leve dos candidatos (nome, seção em função de x) que passa em tudo; sem nenhuma,
    a mais pesada com o que não passa"""
    ordem = sorted(candidatos, key=lambda c: c[1](caso.vao * 50.0).A)
    alternativas, ultima = [], None
    for nome, secao_em in ordem:
        v = verificar_viga(caso, secao_em, meio)
        alternativas.append({"secao": v.secao.texto(), "ok": v.ok, "razao": round(v.resultado.razao, 3) if v.resultado else None})
        ultima = v
        if v.ok:
            break
    ultima.alternativas = alternativas
    return ultima
