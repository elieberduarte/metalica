# -*- coding: utf-8 -*-
"""Concreto armado pela ABNT NBR 6118:2023 — seções retangulares de vigas e pilares.

* `SecaoRetangular` com as camadas de armadura e o equilíbrio por compatibilidade de
  deformações (17.2.2): diagrama parábola-retângulo do concreto (8.2.10.1), aço elastoplástico
  (8.3.6), domínios da Figura 17.1;
* `flexao_simples` — a armadura de uma viga (retângulo equivalente, ductilidade x/d de 14.6.4.3,
  armadura mínima de 17.3.5.2.1);
* `cisalhamento` — modelo de cálculo I (17.4.2.2), armadura mínima (17.4.1.1.1) e espaçamentos
  (18.3.3.2);
* `flexo_compressao` — o momento resistente da seção para uma força normal (ELU);
* `momento_curvatura` — o diagrama M, N, 1/r com a tensão de pico 1,10·fcd (15.3);
* `pilar` — o pilar isolado com os efeitos locais de 2ª ordem: momento mínimo (11.3.3.4.3),
  dispensa (15.8.2), pilar-padrão com curvatura aproximada (λ ≤ 90, 15.8.3.3.2) ou acoplado a
  diagramas M, N, 1/r (λ ≤ 140, 15.8.3.3.4), com a fluência para λ > 90 (15.8.4);
  a flexão oblíqua pela aproximação de 17.2.5.2 (α = 1,2).

Unidades: cm, kN, kN·cm; deformações em ‰; tensões em kN/cm².
Convenção: compressão positiva no concreto; na seção, y medido do centro para a face comprimida.
"""
from __future__ import annotations

import math

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from nucleo.base import ErroDeDados, Passo, Resultado, Verificacao, fmt

from .concreto import BITOLAS, AcoArmadura, Concreto, escolher_barras

N_FATIAS = 60                 # fatias do concreto na integração da seção
ESTRIBO_MIN = 5.0             # mm


# ------------------------------------------------------------------ a seção e o equilíbrio

@dataclass
class Camada:
    y: float                  # cm, do centro da seção (positivo para a face "de cima")
    As: float                 # cm²


@dataclass
class SecaoRetangular:
    """b (cm) paralela à linha neutra, h (cm) na direção da flexão; as camadas de armadura."""
    b: float
    h: float
    camadas: List[Camada] = field(default_factory=list)

    @property
    def Ac(self) -> float:
        return self.b * self.h

    @property
    def Ic(self) -> float:
        return self.b * self.h ** 3 / 12.0

    @property
    def As(self) -> float:
        return sum(c.As for c in self.camadas)

    @staticmethod
    def simetrica(b: float, h: float, As_face: float, d_linha: float, As_lateral: float = 0.0, n_lat: int = 0) -> "SecaoRetangular":
        """armadura simétrica: As_face em cada face (a d' da borda) e, se houver, barras laterais
        igualmente espaçadas entre elas (n_lat de cada lado, com As_lateral cada camada)"""
        cam = [Camada(h / 2 - d_linha, As_face), Camada(-(h / 2 - d_linha), As_face)]
        for i in range(1, n_lat + 1):
            y = (h / 2 - d_linha) - i * (h - 2 * d_linha) / (n_lat + 1)
            cam.append(Camada(y, As_lateral))
        return SecaoRetangular(b, h, cam)


def _sigma_c(eps: float, conc: Concreto, pico: float) -> float:
    """parábola-retângulo (8.2.10.1): eps em ‰, compressão positiva; `pico` a tensão máxima"""
    if eps <= 0.0:
        return 0.0
    e2, n = conc.eps_c2, conc.n_parabola
    if eps >= e2:
        return pico
    return pico * (1.0 - (1.0 - eps / e2) ** n)


def _sigma_s(eps: float, aco: AcoArmadura) -> float:
    """elastoplástico perfeito (8.3.6): eps em ‰ (+ compressão)"""
    s = aco.Es * eps / 1000.0
    return max(-aco.fyd, min(aco.fyd, s))


def esforcos_da_deformacao(sec: SecaoRetangular, eps_topo: float, eps_base: float, conc: Concreto, aco: AcoArmadura,
                           pico: Optional[float] = None) -> Tuple[float, float]:
    """(N, M) resistentes para a distribuição linear de deformações (‰) da face de cima à de baixo:
    N em kN (+ compressão), M em kN·cm (+ comprime a face de cima), em relação ao centro"""
    if pico is None:
        pico = conc.alfa_c * conc.eta_c * conc.fcd              # 0,85·ηc·fcd
    h, b = sec.h, sec.b
    y, ya, As = _malha(sec)
    e2, n = conc.eps_c2, conc.n_parabola

    def sig_c(eps):
        e = np.clip(eps, 0.0, e2)
        return np.where(eps <= 0.0, 0.0, pico * (1.0 - (1.0 - e / e2) ** n))
    eps = eps_base + (eps_topo - eps_base) * (y + h / 2) / h
    f = sig_c(eps) * (b * h / N_FATIAS)
    N = float(f.sum())
    M = float((f * y).sum())
    if len(ya):
        eps_s = eps_base + (eps_topo - eps_base) * (ya + h / 2) / h
        s = np.clip(aco.Es * eps_s / 1000.0, -aco.fyd, aco.fyd)
        fs = (s - sig_c(eps_s)) * As                         # o concreto deslocado pela barra comprimida
        N += float(fs.sum())
        M += float((fs * ya).sum())
    return N, M


_MALHAS: Dict[tuple, tuple] = {}


def _NM_vetor(sec: SecaoRetangular, et: np.ndarray, eb: np.ndarray, conc: Concreto, aco: AcoArmadura, pico: float):
    """(N, M) para vários estados de deformação de uma vez (arrays de εtopo e εbase, ‰)"""
    h, b = sec.h, sec.b
    y, ya, As = _malha(sec)
    e2, n = conc.eps_c2, conc.n_parabola
    t = (y + h / 2) / h                                   # (fatias,)
    eps = eb[:, None] + (et - eb)[:, None] * t[None, :]
    e = np.minimum(np.maximum(eps, 0.0), e2)
    s = pico * (1.0 - (1.0 - e / e2) ** n)
    f = s * (b * h / N_FATIAS)
    N = f.sum(axis=1)
    M = (f * y).sum(axis=1)
    if len(ya):
        ta = (ya + h / 2) / h
        es = eb[:, None] + (et - eb)[:, None] * ta[None, :]
        ss = np.minimum(np.maximum(aco.Es * es / 1000.0, -aco.fyd), aco.fyd)
        ec = np.minimum(np.maximum(es, 0.0), e2)
        sc = pico * (1.0 - (1.0 - ec / e2) ** n)
        fs = (ss - sc) * As
        N = N + fs.sum(axis=1)
        M = M + (fs * ya).sum(axis=1)
    return N, M


def _malha(sec: SecaoRetangular):
    """as fatias do concreto e as camadas da armadura em arrays (guardadas na própria seção)"""
    m = sec.__dict__.get("_malha")
    if m is None:
        dy = sec.h / N_FATIAS
        y = sec.h / 2 - (np.arange(N_FATIAS) + 0.5) * dy
        m = (y, np.array([c.y for c in sec.camadas]), np.array([c.As for c in sec.camadas]))
        sec.__dict__["_malha"] = m
    return m


def _deformacao_ultima(sec: SecaoRetangular, x: float, conc: Concreto, aco: AcoArmadura) -> Tuple[float, float]:
    """(eps_topo, eps_base) da ruína (domínios da Figura 17.1) para a linha neutra a x da face de
    cima: domínios 1-2 pelo aço a 10 ‰, 3-4a pelo concreto a εcu, 5 pelo ponto C (εc2 a (1 − εc2/εcu)·h)"""
    h = sec.h
    d = h / 2 - min(c.y for c in sec.camadas) if sec.camadas else 0.9 * h
    ecu, ec2 = conc.eps_cu, conc.eps_c2
    x23 = ecu / (ecu + 10.0) * d
    if x <= x23:                                   # domínio 2 (e 1 com x ≤ 0): aço a 10 ‰
        k = 10.0 / (d - x) if d - x > 1e-9 else 1e9
        topo = k * x
        base = -k * (h - x)
        return topo, base
    if x <= h:                                     # domínios 3, 4, 4a
        k = ecu / x
        return ecu, ecu - k * h
    # domínio 5: gira em C (εc2 a (1 − εc2/εcu)·h da face mais comprimida)
    hc = (1.0 - ec2 / ecu) * h
    k = ec2 / (x - hc)
    return ec2 + k * hc, ec2 - k * (h - hc)


def momento_resistente(sec: SecaoRetangular, Nd: float, conc: Concreto, aco: AcoArmadura) -> Tuple[float, float]:
    """(MRd, x): o momento resistente de cálculo para a força normal Nd (+ compressão), flexão
    reta com a face de cima comprimida — a linha neutra que equilibra Nd, por bisseção"""
    def N_de(x):
        et, eb = _deformacao_ultima(sec, x, conc, aco)
        return esforcos_da_deformacao(sec, et, eb, conc, aco)
    lo, hi = -2.0 * sec.h, 50.0 * sec.h
    Nlo, Nhi = N_de(lo)[0], N_de(hi)[0]
    if Nd <= Nlo:
        return 0.0, lo
    if Nd >= Nhi:
        return 0.0, hi                              # compressão acima da resistência da seção
    for _ in range(45):
        m = (lo + hi) / 2
        if N_de(m)[0] < Nd:
            lo = m
        else:
            hi = m
    x = (lo + hi) / 2
    return N_de(x)[1], x


def normal_resistente_maxima(sec: SecaoRetangular, conc: Concreto, aco: AcoArmadura) -> float:
    et, eb = conc.eps_c2, conc.eps_c2
    return esforcos_da_deformacao(sec, et, eb, conc, aco)[0]


def momento_curvatura(sec: SecaoRetangular, Nd: float, curvatura: float, conc: Concreto, aco: AcoArmadura) -> Optional[float]:
    """o momento (kN·cm) para a curvatura 1/r (1/cm) e a força normal Nd, com a tensão de pico
    1,10·fcd (15.3): a deformação no centro que equilibra Nd, por bisseção. None se não há equilíbrio"""
    pico = 1.10 * conc.fcd
    h = sec.h
    k = curvatura * 1000.0                          # ‰ por cm

    def N_de(e0):
        return esforcos_da_deformacao(sec, e0 + k * h / 2, e0 - k * h / 2, conc, aco, pico)
    lo, hi = -30.0, 10.0
    if N_de(hi)[0] < Nd or N_de(lo)[0] > Nd:
        return None
    for _ in range(40):
        m = (lo + hi) / 2
        if N_de(m)[0] < Nd:
            lo = m
        else:
            hi = m
    e0 = (lo + hi) / 2
    # o limite: a deformação do concreto não passa de εcu
    if e0 + k * h / 2 > conc.eps_cu + 1e-6:
        return None
    return N_de(e0)[1]


_DIAGRAMAS: Dict[tuple, Tuple[np.ndarray, np.ndarray]] = {}


def diagrama_mnr(sec: SecaoRetangular, Nd: float, conc: Concreto, aco: AcoArmadura, n: int = 48) -> Tuple[np.ndarray, np.ndarray]:
    """o diagrama M, N, 1/r para a força normal Nd: (curvaturas 1/cm, momentos kN·cm), da origem
    até a ruína do concreto (εcu) — calculado uma vez e interpolado depois (cache)"""
    chave = (sec.b, sec.h, tuple((round(c.y, 3), round(c.As, 4)) for c in sec.camadas), round(Nd, 2), conc.fck_MPa,
             conc.gama_c, aco.nome, aco.gama_s)
    if chave in _DIAGRAMAS:
        return _DIAGRAMAS[chave]
    pico = 1.10 * conc.fcd
    h = sec.h
    # a curvatura última: o concreto da face comprimida em εcu com Nd em equilíbrio (N cai com k)
    def N_ult(k):
        return _NM_vetor(sec, np.array([conc.eps_cu]), np.array([conc.eps_cu - k * 1000.0 * h]), conc, aco, pico)[0][0]
    lo, hi = 0.0, 1e-6
    while N_ult(hi) > Nd and hi < 1.0:
        lo, hi = hi, hi * 2.0
    for _ in range(40):
        m = (lo + hi) / 2
        if N_ult(m) > Nd:
            lo = m
        else:
            hi = m
    ku = lo
    ks = np.array([0.0] + [ku * (i / n) ** 1.5 for i in range(1, n + 1)])
    # para cada curvatura, a deformação no centro que equilibra Nd (bisseção vetorizada)
    kk = ks * 1000.0
    a = np.full(len(ks), -30.0)
    b_ = np.full(len(ks), 10.0)
    for _ in range(45):
        m = (a + b_) / 2
        Nm = _NM_vetor(sec, m + kk * h / 2, m - kk * h / 2, conc, aco, pico)[0]
        baixo = Nm < Nd
        a = np.where(baixo, m, a)
        b_ = np.where(baixo, b_, m)
    e0 = (a + b_) / 2
    Ms = _NM_vetor(sec, e0 + kk * h / 2, e0 - kk * h / 2, conc, aco, pico)[1]
    res = (ks, np.where(np.isfinite(Ms), Ms, 0.0))
    if len(_DIAGRAMAS) > 3000:
        _DIAGRAMAS.clear()
    _DIAGRAMAS[chave] = res
    return res


def curvatura_para_momento(sec: SecaoRetangular, Nd: float, Md: float, conc: Concreto, aco: AcoArmadura) -> Optional[float]:
    """a curvatura (1/cm) em que o diagrama M, N, 1/r chega a Md (interpolado no ramo crescente);
    None se Md passa do pico"""
    ks, Ms = diagrama_mnr(sec, Nd, conc, aco)
    i_pico = int(np.argmax(Ms))
    if Md > Ms[i_pico]:
        return None
    return float(np.interp(Md, Ms[: i_pico + 1], ks[: i_pico + 1]))


# ------------------------------------------------------------------ flexão simples (vigas)

def flexao_simples(bw: float, h: float, d: float, Md: float, conc: Concreto, aco: AcoArmadura,
                   d_linha: float = 4.0, elemento: str = "viga") -> Tuple[Verificacao, Dict[str, float]]:
    """a armadura de tração (e a de compressão, se preciso) para o momento Md (kN·cm) na seção
    retangular bw × h com altura útil d (retângulo equivalente, 17.2.2 e): x/d ≤ ξlim (14.6.4.3);
    a armadura mínima pelo momento mínimo 0,8·W0·fctk,sup (17.3.5.2.1), com 0,15 % no mínimo"""
    sc = conc.sigma_cd
    lam = conc.lam
    v = Verificacao("Flexão simples — armadura longitudinal", norma="NBR 6118, 17.2.2 e 17.3.5.2", Sd=abs(Md),
                    unidade="kN·cm")
    Md = abs(Md)
    xlim = conc.xi_lim * d
    Mlim = sc * bw * lam * xlim * (d - lam * xlim / 2)
    As2 = 0.0
    if Md <= Mlim:
        # λx da equação do 2º grau: Md = σ·bw·λx·(d − λx/2)
        disc = d * d - 2.0 * Md / (sc * bw)
        y = d - math.sqrt(max(disc, 0.0))
        x = y / lam
        As1 = Md / (aco.fyd * (d - y / 2)) if Md > 0 else 0.0
        v.passo("Altura do retângulo de tensões", "λx = d − √(d² − 2M<sub>d</sub>/(α<sub>c</sub>η<sub>c</sub>f<sub>cd</sub>·b<sub>w</sub>))",
                "%s − √(%s² − 2×%s/(%s×%s))" % (fmt(d, 1), fmt(d, 1), fmt(Md, 0), fmt(sc, 3), fmt(bw, 1)), fmt(y, 2, "cm"), "NBR 6118, 17.2.2")
    else:
        # armadura dupla: o excesso sobre Mlim vai para a armadura de compressão
        x = xlim
        y = lam * x
        eps_s2 = conc.eps_cu * (x - d_linha) / x
        sig_s2 = _sigma_s(eps_s2, aco)
        As2 = (Md - Mlim) / (sig_s2 * (d - d_linha))
        As1 = Mlim / (aco.fyd * (d - y / 2)) + (Md - Mlim) / (aco.fyd * (d - d_linha))
        v.passo("Armadura dupla: o momento passa do limite de ductilidade", "M<sub>lim</sub> = σ<sub>cd</sub>·b<sub>w</sub>·λx<sub>lim</sub>·(d − λx<sub>lim</sub>/2)",
                "", fmt(Mlim / 100, 2, "kN·m"), "NBR 6118, 14.6.4.3")
    W0 = bw * h * h / 6.0
    Mmin = 0.8 * W0 * conc.fctk_sup
    As_min_M = Mmin / (aco.fyd * 0.9 * d)
    As_min = max(As_min_M, 0.0015 * bw * h)
    v.passo("Armadura de tração", "A<sub>s</sub> = M<sub>d</sub>/(f<sub>yd</sub>·(d − λx/2))", "", fmt(As1, 2, "cm²"), "NBR 6118, 17.2.2")
    v.passo("Armadura mínima", "M<sub>d,mín</sub> = 0,8·W<sub>0</sub>·f<sub>ctk,sup</sub>; ρ<sub>mín</sub> = 0,15 %",
            "0,8 × %s × %s" % (fmt(W0, 0), fmt(conc.fctk_sup, 3)), fmt(As_min, 2, "cm²"), "NBR 6118, 17.3.5.2.1")
    As = max(As1, As_min)
    v.Rd = Md if Md > 0 else 1.0
    v.Sd = abs(Md)
    As_max = 0.04 * bw * h
    if As + As2 > As_max:
        v.Rd = Md * As_max / (As + As2)
        v.observacao = "a armadura passa de 4 % da seção (17.3.5.2.4): aumente a seção"
    dados = {"As": As, "As_comp": As2, "x": x, "x_d": x / d, "As_min": As_min, "Mlim": Mlim}
    return v, dados


# ------------------------------------------------------------------ cisalhamento (modelo I)

def cisalhamento(bw: float, d: float, Vd: float, conc: Concreto, aco: AcoArmadura,
                 flexo_compressao: bool = False, M0_Msd: float = 0.0) -> Tuple[List[Verificacao], Dict[str, float]]:
    """modelo de cálculo I (17.4.2.2), estribos a 90°: VRd2, Vc, Asw/s (cm²/m) com o mínimo de
    17.4.1.1.1 e os espaçamentos de 18.3.3.2"""
    fck = conc.fck_MPa
    av2 = 1.0 - fck / 250.0
    VRd2 = 0.27 * av2 * conc.fcd * bw * d
    v2 = Verificacao("Cisalhamento — compressão diagonal do concreto", norma="NBR 6118, 17.4.2.2 a)", Sd=abs(Vd), Rd=VRd2)
    v2.passo("Força resistente da biela", "V<sub>Rd2</sub> = 0,27·α<sub>v2</sub>·f<sub>cd</sub>·b<sub>w</sub>·d, α<sub>v2</sub> = 1 − f<sub>ck</sub>/250",
             "0,27 × %s × %s × %s × %s" % (fmt(av2, 3), fmt(conc.fcd, 3), fmt(bw, 1), fmt(d, 1)), fmt(VRd2, 1, "kN"), "NBR 6118, 17.4.2.2")
    Vc0 = 0.6 * conc.fctd * bw * d
    Vc = min(Vc0 * (1 + M0_Msd), 2 * Vc0) if flexo_compressao else Vc0
    fywd = min(aco.fyd, 43.5)
    Vsw = max(abs(Vd) - Vc, 0.0)
    asw = Vsw / (0.9 * d * fywd) * 100.0                     # cm²/m
    rho_min = 0.2 * conc.fctm / aco.fyk
    asw_min = rho_min * bw * 100.0
    asw_ad = max(asw, asw_min)
    v3 = Verificacao("Cisalhamento — armadura transversal", norma="NBR 6118, 17.4.2.2 b)", Sd=abs(Vd), Rd=Vc + asw_ad / 100.0 * 0.9 * d * fywd)
    v3.passo("Parcela do concreto", "V<sub>c0</sub> = 0,6·f<sub>ctd</sub>·b<sub>w</sub>·d", "0,6 × %s × %s × %s" % (fmt(conc.fctd, 4), fmt(bw, 1), fmt(d, 1)),
             fmt(Vc0, 1, "kN"), "NBR 6118, 17.4.2.2")
    v3.passo("Estribos (a 90°)", "A<sub>sw</sub>/s = (V<sub>Sd</sub> − V<sub>c</sub>)/(0,9·d·f<sub>ywd</sub>)", "", fmt(asw, 2, "cm²/m"), "NBR 6118, 17.4.2.2")
    v3.passo("Taxa mínima", "ρ<sub>sw,mín</sub> = 0,2·f<sub>ct,m</sub>/f<sub>ywk</sub>", "", fmt(asw_min, 2, "cm²/m"), "NBR 6118, 17.4.1.1.1")
    s_max = min(0.6 * d, 30.0) if abs(Vd) <= 0.67 * VRd2 else min(0.3 * d, 20.0)
    return [v2, v3], {"asw": asw_ad, "s_max": s_max, "VRd2": VRd2, "Vc": Vc}


def estribos(asw_cm2_m: float, s_max: float, ramos: int = 2, bitolas=(5.0, 6.3, 8.0, 10.0)) -> Tuple[float, float]:
    """(bitola mm, espaçamento cm) dos estribos: o menor diâmetro que dá espaçamento de pelo menos
    10 cm (de 2,5 em 2,5 cm, até o máximo da norma); sem isso, o que der o maior espaçamento ≥ 7,5 cm"""
    opcoes = []
    for fi in bitolas:
        a = ramos * BITOLAS[fi][0]
        s = min(s_max, a / max(asw_cm2_m, 1e-9) * 100.0)
        s = math.floor(s / 2.5) * 2.5
        opcoes.append((fi, s))
        if s >= 10.0:
            return fi, s
    fi, s = max(opcoes, key=lambda o: o[1])
    return fi, max(s, 7.5)


# ------------------------------------------------------------------ pilares

@dataclass
class ArmaduraPilar:
    """barras longitudinais distribuídas nas quatro faces de um pilar retangular b × h (cm)"""
    n_h: int                  # barras em cada face paralela a b (as faces que a flexão em h comprime/traciona), com os cantos
    n_b: int                  # barras em cada face paralela a h, sem os cantos
    bitola: float             # mm

    @property
    def n_total(self) -> int:
        return 2 * self.n_h + 2 * self.n_b

    @property
    def As(self) -> float:
        return self.n_total * BITOLAS[self.bitola][0]

    def texto(self) -> str:
        return "%d ø %s" % (self.n_total, fmt(self.bitola, 1).replace(",0", ""))

    def secao(self, b: float, h: float, d_linha: float) -> SecaoRetangular:
        """a seção para a flexão em h (a face de cima e a de baixo com n_h barras, as laterais com n_b)"""
        a = BITOLAS[self.bitola][0]
        return SecaoRetangular.simetrica(b, h, self.n_h * a, d_linha, 2 * a, self.n_b)

    def girada(self) -> "ArmaduraPilar":
        """as mesmas barras vistas na outra direção (a flexão em b)"""
        return ArmaduraPilar(self.n_b + 2, max(self.n_h - 2, 0), self.bitola)


def lambda_1(e1_h: float, alfa_b: float) -> float:
    """15.8.2: λ1 = (25 + 12,5·e1/h)/αb, entre 35 e 90"""
    return min(max((25.0 + 12.5 * e1_h) / alfa_b, 35.0), 90.0)


def pilar_direcao(b: float, h: float, arm: ArmaduraPilar, d_linha: float, comprimento: float, le: float,
                  Nd: float, M1d_A: float, alfa_b: float, conc: Concreto, aco: AcoArmadura,
                  Nsg: float = 0.0, Msg: float = 0.0, phi: float = 2.0, direcao: str = "x") -> Tuple[Verificacao, dict]:
    """o pilar numa direção: h na direção da flexão. Devolve a verificação (Md,tot × MRd) e os dados"""
    sec = arm.secao(b, h, d_linha)
    i = h / math.sqrt(12.0)
    lam = le / i
    v = Verificacao("Pilar — flexo-compressão com 2ª ordem (direção %s, h = %s cm)" % (direcao, fmt(h, 0)),
                    norma="NBR 6118, 15.8", unidade="kN·cm")
    dados = {"lambda": lam, "le": le, "h": h, "b": b}
    v.passo("Índice de esbeltez", "λ = ℓ<sub>e</sub>·√12/h", "%s × 3,464 / %s" % (fmt(le, 0), fmt(h, 0)), fmt(lam, 1), "NBR 6118, 15.8.2")
    # momento mínimo de 1ª ordem
    M1min = Nd * (1.5 + 0.03 * h)
    v.passo("Momento mínimo de 1ª ordem", "M<sub>1d,mín</sub> = N<sub>d</sub>·(0,015 + 0,03·h)", "%s × (1,5 + 0,03 × %s)" % (fmt(Nd, 1), fmt(h, 0)),
            fmt(M1min / 100, 2, "kN·m"), "NBR 6118, 11.3.3.4.3")
    M1 = max(abs(M1d_A), M1min)
    # fluência (λ > 90)
    ecc = 0.0
    if lam > 90.0 and Nsg > 0:
        Ne = 10.0 * conc.Eci * sec.Ic / le ** 2
        theta1 = max(1.0 / (100.0 * math.sqrt(comprimento / 100.0)), 1.0 / 300.0)
        ea = theta1 * comprimento
        if Nsg >= Ne:
            v.indeterminada = True
            v.observacao = "força quase permanente acima da carga crítica de fluência (N<sub>e</sub>)"
            return v, dados
        ecc = (Msg / Nsg + ea) * (math.e ** (phi * Nsg / (Ne - Nsg)) - 1.0)
        v.passo("Excentricidade de fluência", "e<sub>cc</sub> = (M<sub>sg</sub>/N<sub>sg</sub> + e<sub>a</sub>)·(2,718<sup>φN<sub>sg</sub>/(N<sub>e</sub>−N<sub>sg</sub>)</sup> − 1), N<sub>e</sub> = 10E<sub>ci</sub>I<sub>c</sub>/ℓ<sub>e</sub>²",
                "φ = %s; N<sub>e</sub> = %s kN; e<sub>a</sub> = %s cm" % (fmt(phi, 1), fmt(Ne, 0), fmt(ea, 2)), fmt(ecc, 2, "cm"), "NBR 6118, 15.8.4")
        M1 = M1 + Nd * ecc
    e1_h = M1 / Nd / h if Nd > 0 else 0.0
    l1 = lambda_1(min(abs(M1d_A) / Nd / h, 1e3) if Nd > 0 else 0.0, alfa_b)
    dados.update({"lambda1": l1, "ecc": ecc, "M1": M1})
    MRd, x = momento_resistente(sec, Nd, conc, aco)
    if lam > 140.0:
        v.indeterminada = True
        v.observacao = "λ = %s > 140: exige o método geral (15.8.3.2) — aumente a seção" % fmt(lam, 0)
        v.Sd, v.Rd = M1, max(MRd, 1e-9)
        return v, dados
    if lam <= l1:
        Mtot = M1
        v.passo("Efeitos locais de 2ª ordem dispensados", "λ ≤ λ<sub>1</sub> = (25 + 12,5·e<sub>1</sub>/h)/α<sub>b</sub>", "%s ≤ %s" % (fmt(lam, 1), fmt(l1, 1)), "", "NBR 6118, 15.8.2")
    elif lam <= 90.0:
        nu = Nd / (sec.Ac * conc.fcd)
        inv_r = min(0.005 / (h * (nu + 0.5)), 0.005 / h)
        Mtot = max(alfa_b * M1 + Nd * le ** 2 / 10.0 * inv_r, M1)
        v.passo("Pilar-padrão com curvatura aproximada", "M<sub>d,tot</sub> = α<sub>b</sub>M<sub>1d,A</sub> + N<sub>d</sub>·ℓ<sub>e</sub>²/10·1/r; 1/r = 0,005/[h(ν + 0,5)] ≤ 0,005/h",
                "ν = %s; 1/r = %s /cm" % (fmt(nu, 3), fmt(inv_r, 7)), fmt(Mtot / 100, 2, "kN·m"), "NBR 6118, 15.8.3.3.2")
    else:
        # pilar-padrão acoplado ao diagrama M, N, 1/r: M = αb·M1 + Nd·ℓe²/10·1/r(M)
        M = alfa_b * M1
        ok = True
        for _ in range(60):
            k = curvatura_para_momento(sec, Nd, M, conc, aco)
            if k is None:
                ok = False
                break
            M_novo = alfa_b * M1 + Nd * le ** 2 / 10.0 * k
            if abs(M_novo - M) < 0.5:
                M = M_novo
                break
            M = M_novo
        if not ok:
            v.Sd, v.Rd = max(M, M1), max(MRd, 1e-9)
            v.observacao = "sem equilíbrio no diagrama M, N, 1/r: a seção não resiste ao efeito de 2ª ordem"
            v.Rd = min(v.Rd, 0.99 * v.Sd)
            v.passo("Pilar-padrão acoplado a M, N, 1/r", "M = α<sub>b</sub>M<sub>1</sub> + N<sub>d</sub>·ℓ<sub>e</sub>²/10·1/r(M)", "", "sem equilíbrio", "NBR 6118, 15.8.3.3.4")
            return v, dados
        Mtot = max(M, M1)
        v.passo("Pilar-padrão acoplado ao diagrama M, N, 1/r (tensão de pico 1,10·f<sub>cd</sub>)",
                "M<sub>d,tot</sub> = α<sub>b</sub>M<sub>1d,A</sub> + N<sub>d</sub>·ℓ<sub>e</sub>²/10·(1/r)", "1/r = %s /cm" % fmt(k, 7),
                fmt(Mtot / 100, 2, "kN·m"), "NBR 6118, 15.8.3.3.4 e 15.3")
    v.Sd, v.Rd = Mtot, max(MRd, 1e-9)
    v.passo("Momento resistente para N<sub>d</sub> (%s)" % arm.texto(), "M<sub>Rd</sub>(N<sub>d</sub>) — domínios da Figura 17.1",
            "N<sub>d</sub> = %s kN" % fmt(Nd, 1), fmt(MRd / 100, 2, "kN·m"), "NBR 6118, 17.2.2")
    dados.update({"Mtot": Mtot, "MRd": MRd})
    return v, dados


def pilar(b: float, h: float, arm: ArmaduraPilar, d_linha: float, comprimento: float, le_x: float, le_y: float,
          Nd: float, Mx: float, My: float, alfa_bx: float, alfa_by: float, conc: Concreto, aco: AcoArmadura,
          Nsg: float = 0.0, Msgx: float = 0.0, Msgy: float = 0.0, phi: float = 2.0, elemento: str = "pilar") -> Resultado:
    """o pilar retangular b × h: flexão em h (direção x, momento Mx) e em b (direção y, My), cada uma
    com a sua 2ª ordem; a flexão oblíqua pela aproximação (Mx/MRx)^1,2 + (My/MRy)^1,2 ≤ 1 (17.2.5.2)"""
    r = Resultado(elemento, perfil="%s × %s cm" % (fmt(b, 0), fmt(h, 0)), material="%s, %s, %s" % (conc.nome, aco.nome, arm.texto()))
    vx, dx = pilar_direcao(b, h, arm, d_linha, comprimento, le_x, Nd, Mx, alfa_bx, conc, aco, Nsg, Msgx, phi, "x")
    vy, dy = pilar_direcao(h, b, arm.girada(), d_linha, comprimento, le_y, Nd, My, alfa_by, conc, aco, Nsg, Msgy, phi, "y")
    r.add(vx)
    r.add(vy)
    # compressão centrada (a seção aguenta Nd?)
    NRd = normal_resistente_maxima(arm.secao(b, h, d_linha), conc, aco)
    vn = Verificacao("Pilar — compressão", norma="NBR 6118, 17.2.2", Sd=Nd, Rd=NRd)
    r.add(vn)
    # a oblíqua: a direção com o momento principal e a outra com o mínimo
    if not (vx.indeterminada or vy.indeterminada) and vx.Rd > 0 and vy.Rd > 0:
        for (Ma, Ra, Mb, Rb, t) in ((vx.Sd, vx.Rd, Nd * (1.5 + 0.03 * b), vy.Rd, "x"), (Nd * (1.5 + 0.03 * h), vx.Rd, vy.Sd, vy.Rd, "y")):
            s = (Ma / Ra) ** 1.2 + (Mb / Rb) ** 1.2
            vo = Verificacao("Pilar — flexão composta oblíqua (principal em %s, mínimo na outra)" % t, norma="NBR 6118, 17.2.5.2",
                             Sd=s, Rd=1.0, unidade="—")
            vo.passo("Aproximação da envoltória", "(M<sub>Rd,x</sub>/M<sub>Rd,xx</sub>)<sup>α</sup> + (M<sub>Rd,y</sub>/M<sub>Rd,yy</sub>)<sup>α</sup> ≤ 1, α = 1,2",
                     "(%s/%s)<sup>1,2</sup> + (%s/%s)<sup>1,2</sup>" % (fmt(Ma / 100, 1), fmt(Ra / 100, 1), fmt(Mb / 100, 1), fmt(Rb / 100, 1)), fmt(s, 3), "NBR 6118, 17.2.5.2")
            r.add(vo)
    # armadura mínima e máxima (17.3.5.3)
    As_min = max(0.15 * Nd / aco.fyd, 0.004 * b * h)
    As_max = 0.04 * b * h
    va = Verificacao("Pilar — armadura longitudinal mínima", norma="NBR 6118, 17.3.5.3.1", Sd=As_min, Rd=arm.As, unidade="cm²")
    va.passo("Armadura mínima", "A<sub>s,mín</sub> = 0,15·N<sub>d</sub>/f<sub>yd</sub> ≥ 0,4 %·A<sub>c</sub>", "", fmt(As_min, 2, "cm²"), "NBR 6118, 17.3.5.3.1")
    r.add(va)
    vm = Verificacao("Pilar — armadura longitudinal máxima (fora das emendas)", norma="NBR 6118, 17.3.5.3.2", Sd=arm.As, Rd=As_max, unidade="cm²")
    r.add(vm)
    r.dados.update({"x": dx, "y": dy, "As": arm.As, "armadura": arm.texto(), "NRd": NRd})
    r.hipotese("pilar_2a_ordem", "Efeitos locais de 2ª ordem pelo pilar-padrão (curvatura aproximada até λ = 90, acoplado a "
               "diagramas M, N, 1/r até λ = 140), com a fluência para λ > 90 (φ = %s)." % fmt(phi, 1), "norma")
    return r


def armar_pilar(b: float, h: float, d_linha: float, verificar: Callable[[ArmaduraPilar], Resultado],
                bitolas=(12.5, 16.0, 20.0, 25.0)) -> Tuple[Optional[ArmaduraPilar], Optional[Resultado]]:
    """a armadura mais leve que passa: barras nos cantos e nas faces com espaçamento ≤ 40 cm e
    ≤ 2b (18.4.2.2), ø ≥ 10 mm e ≤ b/8 (18.4.2.1)"""
    candidatos = []
    for fi in bitolas:
        if fi / 10.0 > min(b, h) / 8.0:
            continue
        n_h_min = max(2, math.ceil((b - 2 * d_linha) / 40.0) + 1)
        n_b_min = max(0, math.ceil((h - 2 * d_linha) / 40.0) - 1)
        for n_h in range(n_h_min, n_h_min + 4):
            for n_b in range(n_b_min, n_b_min + 4):
                candidatos.append(ArmaduraPilar(n_h, n_b, fi))
    candidatos.sort(key=lambda a: (a.As, a.n_total))
    ultimo = None
    for arm in candidatos:
        if arm.As > 0.04 * b * h:
            break
        r = verificar(arm)
        ultimo = (arm, r)
        if r.ok:
            return arm, r
    return (ultimo[0], ultimo[1]) if ultimo else (None, None)


def estribos_pilar(arm: ArmaduraPilar) -> Tuple[float, float]:
    """18.4.3: ø ≥ 5 mm e ≥ ø/4; s ≤ 20 cm, ≤ menor dimensão, ≤ 12ø (CA-50)"""
    fi_t = max(ESTRIBO_MIN, arm.bitola / 4.0)
    fi_t = next(f for f in (5.0, 6.3, 8.0, 10.0) if f >= fi_t)
    return fi_t, min(20.0, 12.0 * arm.bitola / 10.0)
