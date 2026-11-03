# -*- coding: utf-8 -*-
"""Vigas e terças protendidas por pré-tração (cordoalhas retas aderentes, na pista da fábrica) —
NBR 6118 e NBR 9062.

* as cordoalhas (NBR 7483 — fora da pasta Normas: as áreas nominais e fpyk = 0,9·fptk ficam como dado a
  conferir com o fornecedor), Ep = 200 GPa (8.4.4) e o diagrama bilinear da Figura 8.6;
* a tensão inicial σpi ≤ 0,74·fptk (9.6.1.2.1 a);
* as perdas: iniciais (relaxação até a liberação, 9.6.3.4.5 com a Tabela 8.3; acomodação na pista, dado
  do fabricante — 9.6.3.2), imediatas (encurtamento elástico na seção homogeneizada com o módulo na data
  da protensão, 9.6.3.3.1) e progressivas pelo processo simplificado de 9.6.3.4.2 (fluência e retração da
  Tabela 8.1, relaxação com χ = −ln(1 − ψ), ψ∞ = 2,5·ψ1000);
* a transferência gradual ao longo de ℓbpt (9.4.5.2, fbpd de 9.3.2.2 na idade da liberação);
* o ato da protensão pela verificação simplificada de 17.2.4.3.2 (γp = 1,1; compressão ≤ 0,7·fckj; tração
  ≤ 1,2·fctm,j, com a armadura passiva para a resultante da tração com Δσ ≤ 250 MPa);
* o serviço (17.2.4.4 e Tabela 13.4): nível 2 (CAA I e II) ou 3 (CAA III e IV); ELS-F com a tração ≤ α·fctk,inf
  (17.3.1 e 3.2.2), ELS-D sem tração, compressões ≤ 0,45·fck (quase permanente) e 0,6·fck (frequente); com a
  sucção do vento a borda de cima;
* o ELU de flexão com o pré-alongamento (17.2.4.2.1, γp = 0,9) em todas as seções, o momento mínimo
  (17.3.5.2.1) e a ductilidade (14.6.4.3); o cisalhamento com Vc da flexo-compressão (17.4.2.2, M0 com γp 0,9);
* a flecha e a contraflecha (17.3.2.1.3: Ecs·Ic sem fissuras, a parcela permanente × (1 + φ)) com os limites
  da NBR 9062, Tabela 8;
* a estabilidade lateral (NBR 9062, 6.1.6), o apoio e o elastômero como nas vigas armadas.

Unidades: cm, kN, kN·cm; tensões em kN/cm² (as saídas em MPa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from nucleo.base import ErroDeDados, Resultado, Verificacao, fmt

from . import nbr6118 as N6118
from . import nbr9062 as N9062
from . import vigas as VG
from .concreto import Concreto

EP = 20000.0                    # kN/cm² (200 GPa, 8.4.4)
EPS_UK = 35.0                   # ‰ (NBR 7483: alongamento mínimo após ruptura — a conferir)
DMAX = 1.9                      # cm (brita 1)

#: cordoalhas de 7 fios (NBR 7483 — áreas nominais, a conferir com o catálogo do fornecedor)
CORDOALHAS: Dict[str, dict] = {
    "CP190 RB 9,5": {"fi": 9.5, "area": 0.555, "fptk": 190.0},
    "CP190 RB 12,7": {"fi": 12.7, "area": 1.014, "fptk": 190.0},
    "CP190 RB 15,2": {"fi": 15.2, "area": 1.435, "fptk": 190.0},
    "CP210 RB 12,7": {"fi": 12.7, "area": 1.014, "fptk": 210.0},
}

#: ψ1000 (%) das cordoalhas RB — NBR 6118, Tabela 8.3
PSI1000_RB = ((0.5, 0.0), (0.6, 1.3), (0.7, 2.5), (0.8, 3.5))

#: φ(t∞, t0) — NBR 6118, Tabela 8.1: classe → umidade → {t0 (dias): (2Ac/u = 20 cm, 60 cm)}
FLUENCIA = {
    "C20-C45": {40: {5: (4.6, 3.8), 30: (3.4, 3.0), 60: (2.9, 2.7)}, 55: {5: (3.9, 3.3), 30: (2.9, 2.6), 60: (2.5, 2.3)},
                75: {5: (2.8, 2.4), 30: (2.2, 2.0), 60: (1.9, 1.8)}, 90: {5: (2.0, 1.9), 30: (1.6, 1.5), 60: (1.4, 1.4)}},
    "C50-C90": {40: {5: (2.7, 2.4), 30: (2.0, 1.8), 60: (1.7, 1.6)}, 55: {5: (2.4, 2.1), 30: (1.7, 1.6), 60: (1.5, 1.4)},
                75: {5: (1.9, 1.8), 30: (1.4, 1.3), 60: (1.2, 1.2)}, 90: {5: (1.6, 1.5), 30: (1.1, 1.1), 60: (1.0, 1.0)}},
}

#: cobrimento nominal do concreto protendido, viga (mm) — NBR 6118, Tabela 7.2; o pré-fabricado com Δc = 5 mm
#: (7.4.7.4) e nunca menos de 25 mm (NBR 9062, 9.2.1.1.2)
COBRIMENTO_PROTENDIDO = {"I": 30, "II": 35, "III": 45, "IV": 55}


def cobrimento_protendido(caa: str, pre_fabricado: bool = True) -> float:
    c = COBRIMENTO_PROTENDIDO[caa] - (5 if pre_fabricado else 0)
    return max(c, 25) / 10.0


def fluencia(fck: float, umidade: float, t0: float, esp: float) -> float:
    tab = FLUENCIA["C20-C45" if fck <= 45 else "C50-C90"]
    us = sorted(tab)
    vals = []
    for u in us:
        ts = sorted(tab[u])
        v20 = float(np.interp(t0, ts, [tab[u][t][0] for t in ts]))
        v60 = float(np.interp(t0, ts, [tab[u][t][1] for t in ts]))
        vals.append(float(np.interp(esp, [20.0, 60.0], [v20, v60])))
    return float(np.interp(umidade, us, vals))


def psi1000(sigma_fptk: float) -> float:
    """% (Tabela 8.3, cordoalhas RB, interpolação linear; abaixo de 0,5·fptk não há relaxação)"""
    return float(np.interp(sigma_fptk, [p[0] for p in PSI1000_RB], [p[1] for p in PSI1000_RB]))


def sigma_p(eps_mil: float, fptk: float) -> float:
    """tensão de cálculo (kN/cm²) na cordoalha para a deformação total (‰): diagrama bilinear da Figura 8.6
    com fpyk = 0,9·fptk e γs = 1,15"""
    fpyd = 0.9 * fptk / 1.15
    fptd = fptk / 1.15
    eyd = fpyd / EP * 1000.0
    if eps_mil <= eyd:
        return EP * eps_mil / 1000.0
    return min(fpyd + (fptd - fpyd) * (eps_mil - eyd) / (EPS_UK - eyd), fptd)


@dataclass
class Protensao:
    cordoalha: str = "CP190 RB 12,7"
    n: int = 4
    sigma_pi: float = 0.74                     # σpi/fptk (≤ 0,74)
    fcj: float = 25.0                          # MPa na liberação (≥ 21, NBR 9062 9.2.5.3)
    t_liberacao: float = 1.0                   # dias entre o estiramento e a liberação
    t0: float = 5.0                            # dias: idade para a fluência e a retração (Tabela 8.1 começa em 5)
    acomodacao: float = 0.0                    # mm de acomodação da ancoragem na pista (fabricante)
    pista: float = 100.0                       # m de pista
    gradual: bool = True                       # liberação gradual (9.4.5.2)

    @property
    def dados_cord(self) -> dict:
        if self.cordoalha not in CORDOALHAS:
            raise ErroDeDados("cordoalha desconhecida: %s (use %s)" % (self.cordoalha, ", ".join(CORDOALHAS)))
        return CORDOALHAS[self.cordoalha]

    @property
    def Ap(self) -> float:
        return self.n * self.dados_cord["area"]


def arranjo(n: int, fi_mm: float, b: float, c: float, max_camadas: int = 4) -> Optional[Tuple[List[Tuple[int, float]], float]]:
    """as cordoalhas em camadas na largura b (espaçamento livre ≥ 3φ e 1,2·dmáx, Tabela 18.2): ([(n_k, y_k)], y do
    centroide), y a partir da face de baixo"""
    fi = fi_mm / 10.0
    livre = max(3 * fi, 1.2 * DMAX)
    por = int((b - 2 * c - fi) // (fi + livre)) + 1
    if por < 1:
        return None
    camadas, resto, k = [], n, 0
    while resto > 0:
        if k >= max_camadas:
            return None
        nk = min(por, resto)
        camadas.append((nk, c + fi / 2 + k * (fi + livre)))
        resto -= nk
        k += 1
    yg = sum(nk * y for nk, y in camadas) / n
    return camadas, yg


def _homog(sec: VG.SecaoViga, Ap: float, yp: float, alfa: float) -> Tuple[float, float, float]:
    """(A, yc, I) da seção homogeneizada (as cordoalhas com αp − 1)"""
    A = sec.A + (alfa - 1.0) * Ap
    yc = (sec.A * sec.yc + (alfa - 1.0) * Ap * yp) / A
    I = sec.I + sec.A * (sec.yc - yc) ** 2 + (alfa - 1.0) * Ap * (yp - yc) ** 2
    return A, yc, I


def _tensoes(P: float, M: float, A: float, yc: float, I: float, h: float, yp: float) -> Tuple[float, float]:
    """(σ em cima, σ embaixo), compressão positiva: a força P no cabo (a yp da base) e o momento M (positivo
    tracionando embaixo)"""
    e = yc - yp
    s_top = P / A - P * e * (h - yc) / I + M * (h - yc) / I
    s_bot = P / A + P * e * yc / I - M * yc / I
    return s_top, s_bot


@dataclass
class VigaProtendida(VG.VigaDimensionada):
    protensao: Optional[Protensao] = None
    perdas: Dict[str, float] = field(default_factory=dict)

    def texto_armadura(self) -> str:
        a = self.armadura
        if not a or not self.protensao:
            return super().texto_armadura()
        return "%d cordoalhas %s (σpi = %s·fptk) + %d ø%s (sup.) + estribos ø%s c/ %s" % (
            self.protensao.n, self.protensao.cordoalha, fmt(self.protensao.sigma_pi, 2), a["n_sup"], fmt(a["fi_sup"], 1),
            fmt(a["fi_est"], 1), fmt(a["s_est"], 1))


def verificar(caso: VG.CasoViga, secao_em: Callable[[float], VG.SecaoViga], meio: VG.MeioViga, prot: Protensao) -> VigaProtendida:
    """todas as verificações da viga protendida com `prot.n` cordoalhas"""
    conc, aco = meio.conc, meio.aco
    cd = prot.dados_cord
    fptk = cd["fptk"]
    fi = cd["fi"]
    L = caso.vao * 100.0
    xs = np.linspace(0.0, L, VG.N_SECOES)
    secs = [secao_em(x) for x in xs]
    s_ap, s_meio = secs[0], max(secs, key=lambda s: s.h)
    c = cobrimento_protendido(meio.caa, True)
    r = Resultado("%s %s (protendida)" % (caso.funcao.capitalize(), caso.marca),
                  perfil=s_meio.texto() if s_meio is s_ap else "%s (apoio %s cm, meio %s cm)" % (s_meio.texto(), fmt(s_ap.h, 0), fmt(s_meio.h, 0)),
                  material=conc.nome)
    arr = arranjo(prot.n, fi, s_ap.b_inf, c + VG.ESTRIBO)
    if arr is None:
        v = Verificacao("Cordoalhas — arranjo na mesa de baixo", norma="NBR 6118, Tabela 18.2", Sd=prot.n, Rd=0.0, unidade="")
        v.indeterminada = True
        v.observacao = "as %d cordoalhas não cabem na largura de %s cm" % (prot.n, fmt(s_ap.b_inf, 0))
        r.add(v)
        return VigaProtendida(caso.marca, caso.funcao, s_meio, s_ap, caso.vao, caso.comprimento, resultado=r, protensao=prot,
                              quantidade=caso.quantidade)
    camadas, yp = arr
    Ap = prot.Ap
    # ---- as cargas
    gpp = VG._gama_pp()
    w_pp = np.array([s.peso for s in secs]) / 100.0
    _, _, Vpp, Mpp = VG.estatica(xs, w_pp)
    RApp = float(Vpp[0])
    _, _, Vg, Mg = VG.estatica(xs, np.full_like(xs, caso.g / 100.0))
    _, _, Vq, Mq = VG.estatica(xs, np.full_like(xs, caso.q / 100.0))
    _, _, Vw, Mw = VG.estatica(xs, np.full_like(xs, caso.succao / 100.0))
    psi0, psi1, psi2 = caso.psi_q
    from nucleo import cargas as _cargas
    psi1_w = _cargas.PSI["vento"][1]
    Md = gpp * Mpp + 1.4 * Mg + 1.5 * Mq
    Vd0 = float(gpp * Vpp[0] + 1.4 * Vg[0] + 1.5 * Vq[0])
    # ---- materiais nas idades
    cj = Concreto(prot.fcj, conc.agregado, gama_c=1.2)            # 17.2.4.3.1 b: γc = 1,2 no ato
    alfa_j = EP / cj.Ecs
    alfa_28 = EP / conc.Ecs
    alfa_ci = EP / conc.Eci
    # ---- perdas (seção do meio: as progressivas aí e as imediatas seção a seção)
    spi = prot.sigma_pi * fptk
    rel0 = psi1000(prot.sigma_pi) / 100.0 * (max(prot.t_liberacao, 1e-3) / 41.67) ** 0.15
    d_rel0 = rel0 * spi
    d_anc = EP * prot.acomodacao / 10.0 / (prot.pista * 100.0) if prot.acomodacao > 0 else 0.0
    spa = spi - d_rel0 - d_anc
    i_m = int(np.argmax([s.h for s in secs]))
    sm = secs[i_m]
    Ah, ych, Ih = _homog(sm, Ap, yp, alfa_j)
    e_h = ych - yp
    scp = spa * Ap / Ah + spa * Ap * e_h ** 2 / Ih - Mpp[i_m] * e_h / Ih
    sp0 = spa - alfa_j * scp
    P0 = sp0 * Ap
    # progressivas (9.6.3.4.2) no meio
    e_c = sm.yc - yp
    sc_p0g = P0 / sm.A + P0 * e_c ** 2 / sm.I - Mpp[i_m] * e_c / sm.I
    esp_fic = 2 * sm.A / sm.perimetro
    phi = fluencia(conc.fck_MPa, meio.umidade, prot.t0, esp_fic)
    ecs = -VG.retracao(meio.umidade, prot.t0, esp_fic) / 1000.0
    psi_inf = 2.5 * psi1000(sp0 / fptk) / 100.0
    chi = -math.log(1.0 - psi_inf)
    chi_c = 1.0 + 0.5 * phi
    chi_p = 1.0 + chi
    eta = 1.0 + e_c ** 2 * sm.A / sm.I
    rho = Ap / sm.A
    d_prog = (ecs * EP - alfa_ci * sc_p0g * phi - sp0 * chi) / (chi_p + chi_c * alfa_ci * eta * rho)
    spinf = sp0 + d_prog
    Pinf = spinf * Ap
    perdas = {"sigma_pi": spi, "relaxacao_inicial": d_rel0, "ancoragem": d_anc, "sigma_pa": spa, "encurtamento": spa - sp0,
              "sigma_p0": sp0, "progressivas": -d_prog, "sigma_pinf": spinf, "phi": phi, "ecs": ecs, "psi_inf": psi_inf,
              "P0": P0, "Pinf": Pinf, "perda_total": (spi - spinf) / spi}
    r.carga("Tensão na saída do macaco", "σ<sub>pi</sub> ≤ 0,74·f<sub>ptk</sub>", "%s × %s" % (fmt(prot.sigma_pi, 2), fmt(fptk * 10, 0)),
             fmt(spi * 10, 0, "MPa"), "NBR 6118, 9.6.1.2.1 a")
    r.carga("Relaxação até a liberação (%s dia)" % fmt(prot.t_liberacao, 1), "ψ = ψ<sub>1000</sub>·(t/41,67)<sup>0,15</sup>",
             "ψ<sub>1000</sub> = %s %%" % fmt(psi1000(prot.sigma_pi), 2), fmt(d_rel0 * 10, 1, "MPa"), "NBR 6118, 9.6.3.4.5 e Tabela 8.3")
    if d_anc:
        r.carga("Acomodação da ancoragem na pista", "E<sub>p</sub>·δ/L", "δ = %s mm, L = %s m" % (fmt(prot.acomodacao, 1), fmt(prot.pista, 0)),
                 fmt(d_anc * 10, 1, "MPa"), "NBR 6118, 9.6.3.2 b")
    r.carga("Encurtamento elástico na liberação (seção homogeneizada, E<sub>cs</sub> a f<sub>cj</sub> = %s MPa)" % fmt(prot.fcj, 0),
             "Δσ = α<sub>p</sub>·σ<sub>cp</sub>", "α<sub>p</sub> = %s; σ<sub>cp</sub> = %s MPa" % (fmt(alfa_j, 2), fmt(scp * 10, 2)),
             fmt((spa - sp0) * 10, 1, "MPa"), "NBR 6118, 9.6.3.3.1")
    r.carga("Progressivas (fluência, retração, relaxação)", "Δσ<sub>p</sub> = [ε<sub>cs</sub>E<sub>p</sub> − α<sub>p</sub>σ<sub>c,p0g</sub>φ − σ<sub>p0</sub>χ]/(χ<sub>p</sub> + χ<sub>c</sub>α<sub>p</sub>ηρ<sub>p</sub>)",
             "φ = %s; ε<sub>cs</sub> = %s ‰; ψ<sub>∞</sub> = %s %%; t<sub>0</sub> = %s dias" % (fmt(phi, 2), fmt(ecs * 1000, 3), fmt(psi_inf * 100, 2), fmt(prot.t0, 0)),
             fmt(-d_prog * 10, 1, "MPa"), "NBR 6118, 9.6.3.4.2 e Tabela 8.1")
    r.carga("Tensão final", "σ<sub>p∞</sub>", "perda total %s %%" % fmt(perdas["perda_total"] * 100, 1), fmt(spinf * 10, 0, "MPa"), "")
    if prot.sigma_pi > 0.74 + 1e-9:
        vx = Verificacao("Protensão — tensão inicial", norma="NBR 6118, 9.6.1.2.1 a", Sd=spi * 10, Rd=0.74 * fptk * 10, unidade="MPa")
        vx.passo("Pré-tração", "σ<sub>pi</sub> ≤ 0,74·f<sub>ptk</sub>", "", fmt(spi * 10, 0, "MPa"), "")
        r.add(vx)
    # ---- transferência
    fctd_j = cj.fctk_inf / 1.4
    fbpd = 1.2 * 1.0 * fctd_j
    fpyd = 0.9 * fptk / 1.15
    lbp = 7.0 * fi / 10.0 / 36.0 * fpyd / fbpd
    lbpt = 0.5 * lbp * spi / fpyd * (1.0 if prot.gradual else 1.25)
    fator = np.minimum(xs / max(lbpt, 1e-6), 1.0)
    fator = np.minimum(fator, np.minimum((L - xs) / max(lbpt, 1e-6), 1.0))
    # ---- ato da protensão (17.2.4.3.2)
    gp_ato = 1.1
    pior_c, pior_t = (0.0, 0), (1e9, 0)
    for i, s in enumerate(secs):
        A_, yc_, I_ = _homog(s, Ap, yp, alfa_j)
        st, sb = _tensoes(gp_ato * P0 * fator[i], Mpp[i], A_, yc_, I_, s.h, yp)
        if max(st, sb) > pior_c[0]:
            pior_c = (max(st, sb), i)
        if min(st, sb) < pior_t[0]:
            pior_t = (min(st, sb), i)
    lim_c = 0.7 * prot.fcj / 10.0
    lim_t = 1.2 * cj.fctm
    va = Verificacao("Ato da protensão — compressão", norma="NBR 6118, 17.2.4.3.2 a", Sd=pior_c[0] * 10, Rd=lim_c * 10, unidade="MPa")
    va.passo("Liberação com γ<sub>p</sub> = 1,1 e o peso próprio (γ<sub>f</sub> = 1,0), transferência em ℓ<sub>bpt</sub> = %s cm" % fmt(lbpt, 0),
             "σ ≤ 0,7·f<sub>ckj</sub>", "x = %s m; f<sub>ckj</sub> = %s MPa" % (fmt(xs[pior_c[1]] / 100, 2), fmt(prot.fcj, 0)),
             fmt(pior_c[0] * 10, 2, "MPa"), "NBR 6118, 9.4.5.2 e 17.2.4.3.2")
    r.add(va)
    vt = Verificacao("Ato da protensão — tração", norma="NBR 6118, 17.2.4.3.2 b", Sd=max(-pior_t[0], 0.0) * 10, Rd=lim_t * 10, unidade="MPa")
    vt.passo("Tração máxima", "σ<sub>t</sub> ≤ 1,2·f<sub>ctm,j</sub>", "x = %s m" % fmt(xs[pior_t[1]] / 100, 2), fmt(-pior_t[0] * 10, 2, "MPa"), "")
    As_ato = 0.0
    if pior_t[0] < 0:
        i = pior_t[1]
        s = secs[i]
        A_, yc_, I_ = _homog(s, Ap, yp, alfa_j)
        st, sb = _tensoes(gp_ato * P0 * fator[i], Mpp[i], A_, yc_, I_, s.h, yp)
        # a resultante da tração (triângulo na borda de cima): a altura tracionada e a largura da mesa
        ht = s.h * (-st) / (sb - st) if sb > st else 0.0
        Ft = 0.5 * (-st) * ht * s.b_sup
        As_ato = Ft / 25.0
        vt.passo("Armadura passiva para a resultante da tração", "A<sub>s</sub> = F<sub>t</sub>/250 MPa", "F<sub>t</sub> = %s kN" % fmt(Ft, 1),
                 fmt(As_ato, 2, "cm²"), "NBR 6118, 17.2.4.3.2 c")
    r.add(vt)
    # ---- serviço (t∞)
    nivel = 3 if meio.caa in ("III", "IV") else 2
    combF = ("rara", Mpp + Mg + Mq) if nivel == 3 else ("frequente", Mpp + Mg + psi1 * Mq)
    combD = ("frequente", Mpp + Mg + psi1 * Mq) if nivel == 3 else ("quase permanente", Mpp + Mg + psi2 * Mq)
    alfa_f = s_meio.alfa_forma
    fctf = alfa_f * conc.fctk_inf
    tens = {}
    for nome, M in (("F", combF[1]), ("D", combD[1]), ("qp", Mpp + Mg + psi2 * Mq), ("fr", Mpp + Mg + psi1 * Mq),
                    ("vento", Mpp + Mg - psi1_w * Mw)):
        piores = [1e9, 1e9, -1e9, -1e9]           # min topo, min base, max topo, max base
        for i, s in enumerate(secs):
            A_, yc_, I_ = _homog(s, Ap, yp, alfa_28)
            st, sb = _tensoes(Pinf * fator[i], M[i], A_, yc_, I_, s.h, yp)
            piores = [min(piores[0], st), min(piores[1], sb), max(piores[2], st), max(piores[3], sb)]
        tens[nome] = piores
    vF = Verificacao("ELS-F — formação de fissuras (combinação %s)" % combF[0], norma="NBR 6118, Tabela 13.4 e 17.3.4",
                     Sd=max(-tens["F"][1], -tens["vento"][0], 0.0) * 10, Rd=fctf * 10, unidade="MPa")
    vF.passo("Protensão nível %d (pré-tração, CAA %s)" % (nivel, meio.caa), "tração na borda ≤ f<sub>ct,f</sub> = α·f<sub>ctk,inf</sub>",
             "α = %s (%s)" % (fmt(alfa_f, 1), s_meio.tipo), fmt(fctf * 10, 2, "MPa"), "NBR 6118, 3.2.2 e 17.3.1")
    vF.passo("Borda de baixo (após todas as perdas)", "", "", fmt(-tens["F"][1] * 10, 2, "MPa (tração +)"), "")
    if caso.succao:
        vF.passo("Borda de cima com a sucção do vento (ψ<sub>1</sub> = %s)" % fmt(psi1_w, 1), "", "", fmt(-tens["vento"][0] * 10, 2, "MPa (tração +)"), "")
    r.add(vF)
    t_D = max(-tens["D"][1], 0.0) * 10                       # MPa de tração
    vD = Verificacao("ELS-D — descompressão (combinação %s)" % combD[0], norma="NBR 6118, Tabela 13.4 e 17.2.4.4.2",
                     Sd=t_D, Rd=0.01, unidade="MPa")
    vD.passo("Sem tração na borda de baixo (tolerância numérica 0,01 MPa)", "σ ≥ 0", "", fmt(tens["D"][1] * 10, 2, "MPa (compressão +)"),
             "NBR 6118, 3.2.5")
    r.add(vD)
    comp_qp = max(tens["qp"][2], tens["qp"][3])
    comp_fr = max(tens["fr"][2], tens["fr"][3])
    vC = Verificacao("ELS — compressão no concreto", norma="NBR 6118, 17.2.4.4.1", Sd=max(comp_qp / 0.45, comp_fr / 0.6) * 10,
                     Rd=conc.fck_MPa, unidade="MPa")
    vC.passo("Quase permanente ≤ 0,45·f<sub>ck</sub>", "", "", fmt(comp_qp * 10, 2, "MPa"), "")
    vC.passo("Frequente ≤ 0,6·f<sub>ck</sub>", "", "", fmt(comp_fr * 10, 2, "MPa"), "")
    vC.passo("Comparação", "máx(σ<sub>qp</sub>/0,45; σ<sub>fr</sub>/0,6) ≤ f<sub>ck</sub>", "", fmt(vC.Sd, 2, "MPa"), "")
    r.add(vC)
    # ---- ELU flexão com o pré-alongamento (γp = 0,9)
    eps_pre = 0.9 * spinf / EP * 1000.0                    # ‰
    pior_u = None
    for i, s in enumerate(secs):
        if Md[i] <= 0:
            continue
        dp = s.h - yp
        lo, hi = 1e-3, dp
        for _ in range(60):
            x = (lo + hi) / 2
            y = min(conc.lam * x, s.h)
            C = conc.sigma_cd * s.bloco(y)[0]
            de = min(conc.eps_cu * (dp - x) / x, 10.0)
            T = Ap * sigma_p(eps_pre + de, fptk)
            if C > T:
                hi = x
            else:
                lo = x
        x = (lo + hi) / 2
        y = min(conc.lam * x, s.h)
        de = min(conc.eps_cu * (dp - x) / x, 10.0)
        T = Ap * sigma_p(eps_pre + de, fptk)
        MRd = T * (dp - s.bloco(y)[1])
        raz = Md[i] / MRd
        if pior_u is None or raz > pior_u[0]:
            pior_u = (raz, i, MRd, x / dp, T / Ap)
    raz, i, MRd, xd, sgp = pior_u
    vu = Verificacao("ELU — flexão com a armadura ativa (x = %s m)" % fmt(xs[i] / 100, 2), norma="NBR 6118, 17.2.4.2", Sd=float(Md[i]), Rd=MRd,
                     unidade="kN·cm")
    vu.passo("Pré-alongamento", "ε<sub>p,pré</sub> = γ<sub>p</sub>·σ<sub>p∞</sub>/E<sub>p</sub>, γ<sub>p</sub> = 0,9", "", fmt(eps_pre, 2, "‰"), "NBR 6118, 17.2.4.2.1")
    vu.passo("Equilíbrio (retângulo de tensões e diagrama bilinear do aço)", "σ<sub>cd</sub>·A<sub>c</sub>(λx) = A<sub>p</sub>·σ<sub>pd</sub>",
             "x/d<sub>p</sub> = %s" % fmt(xd, 3), "σ<sub>pd</sub> = %s MPa" % fmt(sgp * 10, 0), "NBR 6118, 8.4.5 e 17.2.2")
    vu.passo("Momento resistente", "M<sub>Rd</sub>", "", fmt(MRd / 100, 1, "kN·m"), "")
    if xd > conc.xi_lim:
        vu.observacao = "x/d = %s > %s: a seção perde a ductilidade (14.6.4.3) — aumente a mesa de cima" % (fmt(xd, 2), fmt(conc.xi_lim, 2))
        vu.Rd = min(vu.Rd, vu.Sd * 0.999)
    r.add(vu)
    s0 = s_meio
    Mmin = 0.8 * s0.I / s0.yc * conc.fctk_sup
    vm = Verificacao("ELU — momento mínimo", norma="NBR 6118, 17.3.5.2.1", Sd=Mmin, Rd=MRd, unidade="kN·cm")
    vm.passo("M<sub>d,mín</sub> = 0,8·W<sub>0</sub>·f<sub>ctk,sup</sub>", "", "", fmt(Mmin / 100, 1, "kN·m"), "")
    r.add(vm)
    # ---- cisalhamento com a flexo-compressão
    dp0 = s_ap.h - yp
    k_d = min(dp0 / max(lbpt, 1e-6), 1.0)
    W_inf = s_ap.I / s_ap.yc
    M0 = 0.9 * Pinf * k_d * (W_inf / s_ap.A + (s_ap.yc - yp))
    vs, ds = N6118.cisalhamento(s_ap.bw, dp0, Vd0, conc, aco, flexo_compressao=True, M0_Msd=M0 / max(float(Md.max()), 1e-9))
    fi_e, s_e = N6118.estribos(ds["asw"], ds["s_max"], ramos=2 * s_ap.almas)
    for v in vs:
        v.titulo += " (apoio)"
        r.add(v)
    vs[-1].passo("V<sub>c</sub> com a protensão", "V<sub>c</sub> = V<sub>c0</sub>(1 + M<sub>0</sub>/M<sub>Sd,máx</sub>) ≤ 2V<sub>c0</sub>",
                 "M<sub>0</sub> = 0,9·P<sub>∞</sub>·(W<sub>inf</sub>/A + e) = %s kN·m" % fmt(M0 / 100, 1), fmt(ds["Vc"], 1, "kN"), "NBR 6118, 17.4.2.2")
    vs[-1].passo("Estribos", "", "%d ramos" % (2 * s_ap.almas), "ø%s c/ %s cm" % (fmt(fi_e, 1), fmt(s_e, 1)), "")
    # ---- flecha e contraflecha (Ecs·Ic, sem fissuras)
    EI = np.array([conc.Ecs * _homog(s, Ap, yp, alfa_28)[2] for s in secs])
    MP0 = -np.array([P0 * fator[i] * (secs[i].yc - yp) for i in range(len(secs))])
    MPinf = MP0 * Pinf / P0
    f_pp, _ = VG._integral_unitaria(xs, Mpp, EI)
    f_g, _ = VG._integral_unitaria(xs, Mg, EI)
    f_q, _ = VG._integral_unitaria(xs, Mq, EI)
    f_P0, _ = VG._integral_unitaria(xs, MP0, EI)
    f_Pinf, _ = VG._integral_unitaria(xs, MPinf, EI)
    f_ini = f_pp + f_P0                                       # na liberação (para cima negativa)
    f_long = (f_pp + f_g + psi2 * f_q + f_Pinf) * (1 + phi) + (psi1 - psi2) * f_q * 0.0
    lim_cf = L / 150.0
    vcf = Verificacao("Contraflecha (inicial e diferida)", norma="NBR 9062, Tabela 8", Sd=max(-f_ini, -f_long, 0.0), Rd=lim_cf, unidade="cm")
    vcf.passo("Na liberação", "f = f<sub>pp</sub> + f<sub>P0</sub> (E<sub>cs</sub>·I<sub>c</sub>)", "", fmt(-f_ini, 2, "cm para cima"), "NBR 6118, 17.3.2.1.3")
    vcf.passo("Diferida (quase permanente com P<sub>∞</sub>, × (1 + φ))", "", "φ = %s" % fmt(phi, 2), fmt(-f_long, 2, "cm para cima"), "")
    vcf.passo("Limite", "L/150", "", fmt(lim_cf, 2, "cm"), "NBR 9062, Tabela 8")
    r.add(vcf)
    lim_f = L / caso.limite_flecha
    vfl = Verificacao("Flecha positiva diferida", norma="NBR 9062, %s" % caso.tabela_flecha.replace("NBR 9062, ", ""),
                      Sd=max(f_long, 0.0), Rd=lim_f, unidade="cm")
    vfl.passo("Quase permanente, diferida", "", "", fmt(f_long, 2, "cm (para baixo +)"), "")
    r.add(vfl)
    # ---- estabilidade lateral
    bf = s_meio.b_compressao
    comp = caso.comprimento * 100.0
    Lst = max(L, comp * (1 - 2 * caso.alcas))
    ve1 = Verificacao("Estabilidade lateral — L/b<sub>f</sub>", norma="NBR 9062, 6.1.6", Sd=Lst / bf, Rd=50.0, unidade="")
    r.add(ve1)
    ve2 = Verificacao("Estabilidade lateral — L·h/b<sub>f</sub>²", norma="NBR 9062, 6.1.6", Sd=Lst * s_meio.h / bf ** 2, Rd=500.0, unidade="")
    r.add(ve2)
    # ---- armadura passiva de cima, apoio e elastômero
    n_sup, fi_sup = N9062._barras(max(As_ato, 2 * VG.BITOLAS[8.0][0]), (8.0, 10.0, 12.5, 16.0), n_min=2)
    apoio = VG._apoio(caso, s_ap, dp0, Vd0, conc, aco, meio)
    elast = VG._elastomero(caso, s_ap, float(Vpp[0] + Vg[0]), float(Vq[0]), float(Vw[0]), Vd0, L, xs, Mpp + Mg + MPinf, Mq, EI, meio, aco)
    vol = float(np.trapezoid([s.A / 1e4 for s in secs], xs / 100.0)) * comp / L
    kg_cord = prot.n * cd["area"] * 0.785 * (comp / 100.0)          # 7850 kg/m³ × área (cm²) × m
    kg_pass = n_sup * VG.BITOLAS[fi_sup][1] * (comp / 100.0 + 0.3)
    per_e = 2 * (s_meio.h - 2 * c) / 100.0 * s_ap.almas + 0.3
    kg_est = math.ceil(comp / s_e) * per_e * VG.BITOLAS[fi_e][1]
    arm = {"n_inf": 0, "fi_inf": 0.0, "camadas": len(camadas), "As_inf": 0.0, "n_sup": n_sup, "fi_sup": fi_sup,
           "As_sup": n_sup * VG.BITOLAS[fi_sup][0], "fi_est": fi_e, "s_est": s_e, "ramos": 2 * s_ap.almas, "d": s_meio.h - yp,
           "d_apoio": dp0, "cordoalhas": prot.n, "cordoalha": prot.cordoalha, "yp": yp, "camadas_cord": camadas, "Ap": Ap,
           "kg_cordoalha": kg_cord}
    r.dados.update({"lbpt": lbpt, "nivel": nivel, "P0": P0, "Pinf": Pinf, "f_ini": f_ini, "f_long": f_long,
                    "perda_total": perdas["perda_total"]})
    r.hipotese("cordoalha", "Cordoalha %s: área %s cm², f<sub>ptk</sub> = %s MPa, f<sub>pyk</sub> = 0,9·f<sub>ptk</sub>, ε<sub>uk</sub> = 3,5 %% "
               "(NBR 7483, fora da pasta Normas — conferir com o fornecedor)." % (prot.cordoalha, fmt(cd["area"], 3), fmt(fptk * 10, 0)), "usuario")
    r.hipotese("liberacao", "Liberação %s com f<sub>cj</sub> = %s MPa (≥ 21, NBR 9062 9.2.5.3); fluência e retração com t<sub>0</sub> = %s dias "
               "(a menor idade da Tabela 8.1 — com cura térmica, conferir a idade fictícia)." % (
                   "gradual" if prot.gradual else "brusca", fmt(prot.fcj, 0), fmt(prot.t0, 0)), "rotina")
    if not prot.acomodacao:
        r.hipotese("pista", "Sem perda por acomodação da ancoragem na pista: informe o valor do fabricante das ancoragens (9.6.3.2 b).", "usuario")
    v = VigaProtendida(caso.marca, caso.funcao, s_meio, s_ap, caso.vao, caso.comprimento, arm, r, apoio, elast,
                       {"pp": RApp, "g": float(Vg[0]), "q": float(Vq[0]), "w": float(Vw[0]), "Fd": Vd0}, caso.quantidade, vol,
                       kg_cord + kg_pass + kg_est, protensao=prot, perdas=perdas)
    return v


def dimensionar(caso: VG.CasoViga, candidatos: Sequence[Tuple[VG.CasoViga, Callable[[float], VG.SecaoViga]]], meio: VG.MeioViga,
                base: Protensao, n_max: int = 24) -> VigaProtendida:
    """a seção mais leve e, nela, o menor número de cordoalhas que passa em tudo"""
    ordem = sorted(candidatos, key=lambda c: c[1](c[0].vao * 50.0).A)
    alternativas, ultima = [], None
    for caso_c, secao_em in ordem:
        achou = None
        for n in range(2, n_max + 1):
            v = verificar(caso_c, secao_em, meio, replace(base, n=n))
            ultima = v
            if v.resultado.indeterminada and any("arranjo" in x.titulo for x in v.resultado.verificacoes):
                break
            if v.ok:
                achou = v
                break
        alternativas.append({"secao": ultima.secao.texto(), "ok": bool(achou), "cordoalhas": (achou or ultima).protensao.n,
                             "razao": round((achou or ultima).resultado.razao, 3)})
        if achou:
            achou.alternativas = alternativas
            return achou
    ultima.alternativas = alternativas
    return ultima
