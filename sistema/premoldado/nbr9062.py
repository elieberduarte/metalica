# -*- coding: utf-8 -*-
"""Concreto pré-moldado pela ABNT NBR 9062:2017 — ligações e situações transitórias.

* `coeficientes` — γc e γs de pré-fabricado ou pré-moldado (8.1);
* `calice` — ligação do pilar com a fundação por cálice de interfaces lisas ou rugosas (7.7):
  embutimento (Tabela 15), pressões na parede do colarinho (Hsfd, Nbd — 7.7.3), compressão
  na parede (7.7.3.6), armaduras do colarinho pelo modelo da Figura 27, mínimos (7.7.5.7);
* `icamento_pilar` — o pilar no saque da fôrma, transporte e montagem (5.3.2): carga dinâmica
  γf·βa·gk com βa = 1,3 e γf = 1,30, e a tensão na armadura longitudinal ≤ 0,50·fyk;
* `ancoragem` — comprimento de ancoragem (NBR 6118, 9.4.2.4).

Unidades: cm, kN, kN·cm; tensões em kN/cm².
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados, Passo, Resultado, Verificacao, fmt

from .concreto import BITOLAS, AcoArmadura, Concreto

GAMA_N_COLARINHO = 1.2        # 7.7.1.2: pilares engastados e vigas articuladas
BETA_A_PILAR = 1.3            # 5.3.2: pilares no transporte e içamento
GAMA_F_DINAMICO = 1.30        # 5.3.2: g_eq,d ≥ γf·βa·gk


def coeficientes(pre_fabricado: bool) -> Tuple[float, float]:
    """(γc, γs) — 8.1: pré-fabricado (produção industrial com o controle de 12.1.2) pode adotar
    1,3 e 1,10; pré-moldado deve adotar 1,4 e 1,15"""
    return (1.3, 1.10) if pre_fabricado else (1.4, 1.15)


# ------------------------------------------------------------------ ancoragem (NBR 6118, 9.4.2)

def ancoragem(bitola_mm: float, conc: Concreto, aco: AcoArmadura, boa_aderencia: bool = True,
              gancho: bool = False, As_calc_ef: float = 1.0) -> Tuple[float, List[Passo]]:
    """(lb,nec em cm, passos): lb = (ø/4)·fyd/fbd, fbd = η1·η2·η3·fctd (η1 = 2,25 barra nervurada,
    η2 = 1,0 boa aderência ou 0,7, η3 = 1,0 até ø32); lb,nec = α·lb·As,calc/As,ef ≥ lb,mín"""
    fi = bitola_mm / 10.0
    eta2 = 1.0 if boa_aderencia else 0.7
    fbd = 2.25 * eta2 * 1.0 * conc.fctd
    lb = fi / 4.0 * aco.fyd / fbd
    alfa = 0.7 if gancho else 1.0
    lb_min = max(0.3 * lb, 10 * fi, 10.0)
    lb_nec = max(alfa * lb * As_calc_ef, lb_min)
    passos = [Passo("Resistência de aderência", "f<sub>bd</sub> = η<sub>1</sub>η<sub>2</sub>η<sub>3</sub>·f<sub>ctd</sub>",
                    "2,25 × %s × 1,0 × %s" % (fmt(eta2, 1), fmt(conc.fctd, 4)), fmt(fbd * 10, 2, "MPa"), "NBR 6118, 9.3.2.1"),
              Passo("Comprimento de ancoragem básico", "ℓ<sub>b</sub> = (ø/4)·f<sub>yd</sub>/f<sub>bd</sub>",
                    "(%s/4) × %s / %s" % (fmt(fi, 2), fmt(aco.fyd, 2), fmt(fbd, 4)), fmt(lb, 1, "cm"), "NBR 6118, 9.4.2.4"),
              Passo("Comprimento necessário", "ℓ<sub>b,nec</sub> = α·ℓ<sub>b</sub>·A<sub>s,calc</sub>/A<sub>s,ef</sub> ≥ ℓ<sub>b,mín</sub>",
                    "α = %s; A<sub>s,calc</sub>/A<sub>s,ef</sub> = %s" % (fmt(alfa, 1), fmt(As_calc_ef, 2)), fmt(lb_nec, 1, "cm"), "NBR 6118, 9.4.2.5")]
    return lb_nec, passos


# ------------------------------------------------------------------ cálice (7.7)

@dataclass
class GeometriaCalice:
    Lemb: float               # cm
    parede: float             # espessura das paredes do colarinho, cm
    folga: float              # entre o pilar e a parede (enchimento), cm
    fundo: float              # espessura abaixo da base do pilar, cm
    h2: float                 # trecho do embutimento dentro do bloco, abaixo do colarinho (≥ 0,1·Lemb), cm

    @property
    def h_colarinho(self) -> float:
        return self.Lemb - self.h2


def embutimento_tabela15(Md: float, Nd: float, h: float, interface: str) -> float:
    """Tabela 15 (7.7.2.1), interpolando Md/(Nd·h) entre 0,15 e 2"""
    x = Md / (max(Nd, 1e-6) * h)
    if interface == "chaves":
        a, b_ = 1.2, 1.6
    else:
        a, b_ = 1.5, 2.0
    if x <= 0.15:
        f = a
    elif x >= 2.0:
        f = b_
    else:
        f = a + (b_ - a) * (x - 0.15) / 1.85
    return f * h


def _hsfd_geral(Md, Nd, Vd, h, Lemb, mu, enb, a):
    """o equilíbrio do pilar embutido da Figura 26 (atritos μ nas pressões e na base): com enb = h/4
    e a = Lemb/10 reproduz a expressão de 7.7.3.1; com enb = 0 e a = Lemb/6 dá a de pequena
    excentricidade (7.7.3.3)"""
    K = a - mu * (h / 2 + enb)
    Hs = (Md - Nd * (enb + mu * K / (1 + mu * mu)) + Vd * (Lemb - K / (1 + mu * mu))) / (Lemb - 2 * a + mu * h)
    Nb = (Nd - mu * Vd) / (1 + mu * mu)
    return Hs, Nb


def calice(b: float, h: float, Nd: float, Md: float, Vd: float, conc: Concreto, aco: AcoArmadura,
           bitola_pilar: float, interface: str = "rugosa", parede: float = 20.0, folga: float = 5.0,
           direcao: str = "x", elemento: str = "Cálice") -> Resultado:
    """o cálice com colarinho para um pilar b × h (h no plano do momento Md), interfaces lisas ou
    rugosas: embutimento, pressões Hsfd/Nbd, compressão na parede, armaduras do colarinho (com γn)"""
    if interface not in ("lisa", "rugosa"):
        raise ErroDeDados("cálice: interface '%s' — este cálculo cobre lisa ou rugosa (7.7.3)" % interface)
    r = Resultado(elemento, perfil="colarinho %s cm, pilar %s × %s" % (fmt(parede, 0), fmt(b, 0), fmt(h, 0)), material=conc.nome)
    Md, Vd = abs(Md), abs(Vd)
    tracao = Nd < 0
    Lemb = embutimento_tabela15(Md, abs(Nd), h, interface)
    if tracao:
        Lemb = 2.0 * h
    lb, passos_lb = ancoragem(bitola_pilar, conc, aco, gancho=False)
    # a ancoragem da armadura do pilar começa a 0,5·Lemb do topo (7.7.5.4): cabe no resto do embutimento
    Lemb_anc = 2.0 * (lb + 5.0)
    Lemb = max(Lemb, 40.0)
    Lemb_ad = math.ceil(max(Lemb, Lemb_anc) / 5.0) * 5.0
    v_emb = Verificacao("Cálice — comprimento de embutimento", norma="NBR 9062, 7.7.2 (Tabela 15) e 7.7.5.4", Sd=max(Lemb, Lemb_anc),
                        Rd=Lemb_ad, unidade="cm")
    v_emb.passo("Excentricidade relativa", "M<sub>d</sub>/(N<sub>d</sub>·h)", "%s / (%s × %s)" % (fmt(Md, 0), fmt(abs(Nd), 1), fmt(h, 0)),
                fmt(Md / max(abs(Nd), 1e-6) / h, 2), "NBR 9062, Tabela 15")
    v_emb.passo("Embutimento mínimo (interface %s)" % interface, "L<sub>emb</sub> = 1,5h a 2,0h (interpolado) ≥ 40 cm", "",
                fmt(Lemb, 1, "cm"), "NBR 9062, 7.7.2.1 e 7.7.2.4")
    for p_ in passos_lb:
        v_emb.passos.append(p_)
    v_emb.passo("A ancoragem da armadura do pilar a partir de 0,5·L<sub>emb</sub>", "L<sub>emb</sub> ≥ 2·(ℓ<sub>b,nec</sub> + c)",
                "2 × (%s + 5)" % fmt(lb, 1), fmt(Lemb_anc, 1, "cm"), "NBR 9062, 7.7.5.4")
    r.add(v_emb)
    Lemb = Lemb_ad
    geo = GeometriaCalice(Lemb, max(parede, 15.0), folga, 20.0, max(0.1 * Lemb, 10.0))
    # pressões na parede frontal
    mu_g = 0.6 if interface == "rugosa" else 0.3
    mu_p = 0.3 if interface == "rugosa" else 0.0
    x = Md / max(abs(Nd), 1e-6) / h
    Hg, Nbg = _hsfd_geral(Md, Nd, Vd, h, Lemb, mu_g, h / 4.0, Lemb / 10.0)
    Hp, Nbp = _hsfd_geral(Md, Nd, Vd, h, Lemb, mu_p, 0.0, Lemb / 6.0)
    if x >= 2.0:
        Hs, Nb, como = Hg, Nbg, "grande excentricidade (M<sub>d</sub>/N<sub>d</sub>h ≥ 2)"
    elif x <= 0.15:
        Hs, Nb, como = Hp, Nbp, "pequena excentricidade (M<sub>d</sub>/N<sub>d</sub>h ≤ 0,15)"
    else:
        f = (x - 0.15) / 1.85
        Hs, Nb, como = Hp + (Hg - Hp) * f, Nbp + (Nbg - Nbp) * f, "excentricidade intermediária (interpolação, 7.7.3.4)"
    gn = GAMA_N_COLARINHO
    Hs_n = gn * Hs
    v_h = Verificacao("Cálice — compressão na parede frontal do colarinho", norma="NBR 9062, 7.7.3.6", unidade="kN/cm²")
    v_h.passo("Resultante da pressão do pilar na parede frontal — %s" % como,
              "H<sub>sfd</sub> = {M<sub>d</sub> − N<sub>d</sub>[e<sub>nb</sub> + μK/(1+μ²)] + V<sub>d</sub>[L<sub>emb</sub> − K/(1+μ²)]}/(L<sub>emb</sub> − 2a + μh), "
              "K = a − μ(h/2 + e<sub>nb</sub>)", "μ = %s (grande) / %s (pequena)" % (fmt(mu_g, 1), fmt(mu_p, 1)), fmt(Hs, 1, "kN"), "NBR 9062, 7.7.3.1 a 7.7.3.4")
    v_h.passo("Com o coeficiente de ajustamento do colarinho", "γ<sub>n</sub>·H<sub>sfd</sub>", "%s × %s" % (fmt(gn, 1), fmt(Hs, 1)), fmt(Hs_n, 1, "kN"), "NBR 9062, 7.7.1.2")
    sig = Hs_n / (0.2 * Lemb * b)
    v_h.Sd, v_h.Rd = sig, 0.4 * conc.fcd
    v_h.passo("Tensão na faixa 0,2·L<sub>emb</sub> × largura do pilar", "σ = γ<sub>n</sub>H<sub>sfd</sub>/(0,2·L<sub>emb</sub>·b) ≤ 0,4·f<sub>cd</sub>",
              "%s / (0,2 × %s × %s)" % (fmt(Hs_n, 1), fmt(Lemb, 0), fmt(b, 0)), fmt(sig * 10, 2, "MPa"), "NBR 9062, 7.7.3.6")
    r.add(v_h)
    # armaduras do colarinho (modelo da Figura 27)
    As_hp = Hs_n / (2.0 * aco.fyd)
    ext = h + 2 * folga + 2 * geo.parede                 # dimensão externa no plano do momento
    braco = ext - geo.parede                             # do tirante vertical (canto frontal) à biela na parede posterior
    Fvd = (Hs_n / 2.0) * (geo.h_colarinho - 0.1 * Lemb) / braco
    As_vp = max(Fvd, 0.0) / aco.fyd
    As_min = 0.25 * geo.parede
    # as barras: laços horizontais no topo (faixa de 0,2·Lemb) e barras verticais nos cantos da parede frontal
    n_h, fi_h = _barras(As_hp, (8.0, 10.0, 12.5), n_min=2)
    As_vert_total = max(4.0 * As_vp, As_min)
    n_v, fi_v = _barras(As_vert_total, (10.0, 12.5, 16.0), n_min=8)
    n_hs, fi_hs = _barras(As_min, (8.0, 10.0), n_min=4)
    v_ah = Verificacao("Cálice — armadura horizontal principal do colarinho (por parede longitudinal)", norma="NBR 9062, 7.7.3.5 (Figura 27)",
                       Sd=As_hp, Rd=n_h * BITOLAS[fi_h][0], unidade="cm²")
    v_ah.passo("Tirante no topo: cada parede longitudinal recebe metade da pressão da frontal", "A<sub>s,hp</sub> = γ<sub>n</sub>H<sub>sfd</sub>/(2·f<sub>yd</sub>)",
               "%s / (2 × %s)" % (fmt(Hs_n, 1), fmt(aco.fyd, 2)), fmt(As_hp, 2, "cm²"), "NBR 9062, 7.7.3.5")
    v_ah.passo("Adotado: laços horizontais no topo (faixa de 0,2·L<sub>emb</sub>)", "", "", "%d ø %s por ramo" % (n_h, fmt(fi_h, 1)), "")
    v_ah.observacao = "a norma dá o modelo (Figura 27), não a expressão: a leitura do tirante é do programa — confira"
    r.add(v_ah)
    v_av = Verificacao("Cálice — armadura vertical principal do colarinho (canto da parede frontal)", norma="NBR 9062, 7.7.3.5 (Figura 27 a)",
                       Sd=max(As_vp, 0.0), Rd=n_v * BITOLAS[fi_v][0] / 4.0, unidade="cm²")
    v_av.passo("Parede longitudinal como consolo: H<sub>sfd</sub>/2 no topo, biela até a base junto à parede posterior",
               "F<sub>vd</sub> = (γ<sub>n</sub>H<sub>sfd</sub>/2)·(h<sub>c</sub> − 0,1L<sub>emb</sub>)/(ℓ<sub>ext</sub> − e<sub>p</sub>)",
               "(%s/2) × (%s − %s) / %s" % (fmt(Hs_n, 1), fmt(geo.h_colarinho, 0), fmt(0.1 * Lemb, 1), fmt(braco, 0)), fmt(Fvd, 1, "kN"), "NBR 9062, Figura 27 a")
    v_av.passo("Armadura", "A<sub>s,vp</sub> = F<sub>vd</sub>/f<sub>yd</sub>", "", fmt(As_vp, 2, "cm²"), "")
    v_av.passo("Adotado: barras verticais (um quarto em cada canto)", "", "", "%d ø %s no total" % (n_v, fmt(fi_v, 1)), "")
    v_av.observacao = "braços do modelo adotados pelo programa (a norma não fixa) — confira"
    r.add(v_av)
    v_min = Verificacao("Cálice — armaduras mínimas do colarinho", norma="NBR 9062, 7.7.5.7", Sd=As_min,
                        Rd=min(n_v * BITOLAS[fi_v][0], n_hs * BITOLAS[fi_hs][0]), unidade="cm²")
    v_min.passo("Armadura vertical total e horizontal total", "≥ 0,25·e<sub>p</sub> (cm², e<sub>p</sub> em cm)", "0,25 × %s" % fmt(geo.parede, 0),
                fmt(As_min, 2, "cm²"), "NBR 9062, 7.7.5.7")
    r.add(v_min)
    v_min.passo("Adotado: horizontais secundárias", "", "", "%d ø %s distribuídas na altura" % (n_hs, fmt(fi_hs, 1)), "")
    r.dados.update({"barras": {"horizontal_principal": (n_h, fi_h), "vertical": (n_v, fi_v), "horizontal_secundaria": (n_hs, fi_hs)}})
    r.dados.update({"direcao": direcao, "Lemb": Lemb, "Hsfd": Hs, "Hsfd_gn": Hs_n, "Nbd": Nb, "As_hp": As_hp, "As_vp": As_vp,
                    "As_min": As_min, "parede": geo.parede, "folga": folga, "fundo": geo.fundo, "h_colarinho": geo.h_colarinho,
                    "interno": (b + 2 * folga, h + 2 * folga), "externo": (b + 2 * folga + 2 * geo.parede, ext)})
    r.hipotese("calice", "Cálice com colarinho, interface %s (μ = %s na grande excentricidade, %s na pequena), paredes de %s cm, "
               "folga de %s cm para o enchimento; γn = 1,2 no colarinho (pilares engastados, vigas articuladas)."
               % (interface, fmt(mu_g, 1), fmt(mu_p, 1), fmt(geo.parede, 0), fmt(folga, 0)), "norma")
    return r


def _barras(As: float, bitolas, n_min: int = 2) -> Tuple[int, float]:
    """(n, bitola) com a menor área que cobre As"""
    melhor = None
    for fi in bitolas:
        n = max(n_min, math.ceil(As / BITOLAS[fi][0] - 1e-9))
        if n % 2:
            n += 1
        cand = (n * BITOLAS[fi][0], n, fi)
        if melhor is None or cand < melhor:
            melhor = cand
    return melhor[1], melhor[2]


# ------------------------------------------------------------------ içamento e transporte (5.3.2)

def icamento_pilar(b: float, h: float, comprimento: float, As_face: float, d: float, conc: Concreto, aco: AcoArmadura,
                   fcj_MPa: Optional[float] = None, elemento: str = "Pilar — içamento") -> Resultado:
    """o pilar deitado, içado por dois pontos a 0,207·L das pontas (os momentos positivo e negativo
    iguais: M = 0,0214·q·L²), deitado na face mais larga (flexão na menor dimensão, h): a carga
    dinâmica γf·βa·gk (5.3.2), o momento resistente e a tensão na armadura ≤ 0,5·fyk"""
    r = Resultado(elemento, perfil="%s × %s cm, %s m" % (fmt(b, 0), fmt(h, 0), fmt(comprimento / 100, 2)), material=conc.nome)
    gk = 25.0 * b * h / 1e4 / 100.0                      # kN/cm
    L = comprimento
    Mk = 0.0214 * gk * L * L
    g_eq = GAMA_F_DINAMICO * BETA_A_PILAR
    Md = g_eq * Mk
    z = 0.9 * d
    MRd = As_face * aco.fyd * z
    v = Verificacao("Içamento — flexão do pilar deitado (dois pontos a 0,207·L)", norma="NBR 9062, 5.3.2", Sd=Md, Rd=MRd, unidade="kN·cm")
    v.passo("Carga dinâmica de manuseio", "g<sub>eq,d</sub> = γ<sub>f</sub>·β<sub>a</sub>·g<sub>k</sub>",
            "%s × %s × %s" % (fmt(GAMA_F_DINAMICO, 2), fmt(BETA_A_PILAR, 2), fmt(gk * 100, 2)), fmt(g_eq * gk * 100, 2, "kN/m"), "NBR 9062, 5.3.2")
    v.passo("Momento com os apoios a 0,207·L", "M = 0,0214·q·L²", "0,0214 × %s × %s²" % (fmt(g_eq * gk * 100, 2), fmt(L / 100, 2)),
            fmt(Md / 100, 2, "kN·m"), "")
    v.passo("Momento resistente (armadura de uma face, z = 0,9d)", "M<sub>Rd</sub> = A<sub>s</sub>·f<sub>yd</sub>·0,9d",
            "%s × %s × %s" % (fmt(As_face, 2), fmt(aco.fyd, 2), fmt(z, 1)), fmt(MRd / 100, 2, "kN·m"), "NBR 6118, 17.2.2")
    r.add(v)
    sig = BETA_A_PILAR * Mk / (As_face * z)
    vs = Verificacao("Içamento — tensão na armadura longitudinal", norma="NBR 9062, 5.3.2", Sd=sig, Rd=0.5 * aco.fyk, unidade="kN/cm²")
    vs.passo("Tensão com a carga dinâmica característica", "σ<sub>s</sub> = β<sub>a</sub>·M<sub>k</sub>/(A<sub>s</sub>·0,9d) ≤ 0,50·f<sub>yk</sub>",
             "%s × %s / (%s × %s)" % (fmt(BETA_A_PILAR, 1), fmt(Mk, 0), fmt(As_face, 2), fmt(z, 1)), fmt(sig * 10, 0, "MPa"), "NBR 9062, 5.3.2")
    r.add(vs)
    if fcj_MPa is not None:
        vc = Verificacao("Içamento — resistência do concreto no saque", norma="NBR 9062, 5.3.3", Sd=15.0, Rd=fcj_MPa, unidade="MPa")
        r.add(vc)
    r.dados.update({"Mk": Mk, "Md": Md, "pontos": 0.207 * L})
    r.hipotese("icamento", "Pilar içado deitado por dois pontos a 0,207·L das pontas (%s cm), carga dinâmica %s·gk "
               "(γf = 1,30 × βa = 1,3); alças e dispositivos de içamento com βa = 3 (5.3.2) — especificar no detalhamento."
               % (fmt(0.207 * L, 0), fmt(g_eq, 2)), "norma")
    return r


# ------------------------------------------------------------------ consolos (7.3)

#: 7.3.9: Hd/Fd na falta de cálculo rigoroso (sem impedimento ao movimento horizontal)
HD_FD = {"junta a seco": 0.8, "argamassa": 0.5, "elastômero": 0.16, "PTFE": 0.08, "chapas não soldadas": 0.25,
         "concreto sobre chapa": 0.4}


def gama_n(pre_fabricado: bool, permanente_preponderante: bool) -> float:
    """7.3.1.1: 1,0/1,1 (pré-fabricado) e 1,1/1,2 (pré-moldado)"""
    if pre_fabricado:
        return 1.0 if permanente_preponderante else 1.1
    return 1.1 if permanente_preponderante else 1.2


def consolo(b: float, h: float, a: float, Fd: float, conc: Concreto, aco: AcoArmadura, d: Optional[float] = None,
            apoio: str = "elastômero", Hd: Optional[float] = None, carga_direta: bool = True,
            pre_fabricado: bool = False, permanente_preponderante: bool = False, interface: str = "monolítico",
            bitola_tirante: float = 12.5, elemento: str = "Consolo") -> Resultado:
    """o consolo de concreto (7.3): b largura, h altura no engastamento, a distância da carga à face do
    suporte (cm); Fd a reação vertical de cálculo (kN, sem γn). Classificação por a/d (7.3.2.2), tirante
    (7.3.5), biela (7.3.4), costura (7.3.6), estribos (7.3.7), com γn (7.3.1.1) e Hd (7.3.9)"""
    r = Resultado(elemento, perfil="b = %s, h = %s, a = %s cm" % (fmt(b, 0), fmt(h, 0), fmt(a, 1)), material=conc.nome)
    gn = gama_n(pre_fabricado, permanente_preponderante)
    if d is None:
        d = h - (3.0 + bitola_tirante / 20.0)
    Fdn = gn * Fd
    if Hd is None:
        if apoio not in HD_FD:
            raise ErroDeDados("consolo: apoio '%s' — informe Hd (7.3.9 g exige estudo) ou use %s" % (apoio, ", ".join(HD_FD)))
        Hd = HD_FD[apoio] * Fd
    Hdn = gn * Hd
    fyd = min(aco.fyd, 43.5)
    ad = a / d
    v = Verificacao("Consolo — tirante", norma="NBR 9062, 7.3.5", unidade="cm²")
    v.passo("Coeficiente de ajustamento", "γ<sub>n</sub>", "pré-%s, carga %s" % ("fabricado" if pre_fabricado else "moldado",
            "permanente preponderante" if permanente_preponderante else "variável relevante"), fmt(gn, 1), "NBR 9062, 7.3.1.1")
    v.passo("Força horizontal", "H<sub>d</sub>", "%s × %s (%s)" % (fmt(HD_FD.get(apoio, Hd / max(Fd, 1e-9)), 2), fmt(Fd, 1), apoio),
            fmt(Hd, 1, "kN"), "NBR 9062, 7.3.9")
    v.passo("Classificação", "a/d", "%s / %s" % (fmt(a, 1), fmt(d, 1)), fmt(ad, 2), "NBR 9062, 7.3.2.2")
    if ad > 2.0:
        v.indeterminada = True
        v.observacao = "a/d > 2: calcular como viga (NBR 6118)"
        r.add(v)
        return r
    if ad > 1.0:
        tipo = "consolo (1 < a/d ≤ 2): viga em balanço pela NBR 6118"
        from .nbr6118 import flexao_simples
        vf, df = flexao_simples(b, h, d, Fdn * a + Hdn * (h - d), conc, aco)
        As_tir = df["As"] + Hdn / fyd
        Asv = df["As"]
    elif ad > 0.5:
        tipo = "consolo curto (0,5 < a/d ≤ 1): biela e tirante"
        Asv = (0.1 + ad) * Fdn / fyd
        As_tir = Asv + Hdn / fyd
        v.passo("Armadura do tirante para a carga vertical", "A<sub>sv</sub> = (0,1 + a/d)·F<sub>d</sub>/f<sub>yd</sub>",
                "(0,1 + %s) × %s / %s" % (fmt(ad, 3), fmt(Fdn, 1), fmt(fyd, 2)), fmt(Asv, 2, "cm²"), "NBR 9062, 7.3.5.3")
    else:
        tipo = "consolo muito curto (a/d ≤ 0,5): cisalhamento-atrito"
        mu = {"monolítico": 1.4, "rugosa": 1.0, "lisa": 0.6}.get(interface, 1.4)
        Asv = 0.8 * Fdn / (fyd * mu)
        As_tir = Asv + Hdn / fyd
        v.passo("Armadura do tirante para a carga vertical", "A<sub>sv</sub> = 0,8·F<sub>d</sub>/(f<sub>yd</sub>·μ)",
                "0,8 × %s / (%s × %s)" % (fmt(Fdn, 1), fmt(fyd, 2), fmt(mu, 1)), fmt(Asv, 2, "cm²"), "NBR 9062, 7.3.5.4")
    As_min = 0.04 * conc.fck / aco.fyk * b * d
    As_nec = max(As_tir, As_min)
    v.passo("Tirante", "A<sub>s,tir</sub> = A<sub>sv</sub> + H<sub>d</sub>/f<sub>yd</sub>", "%s + %s / %s" % (fmt(Asv, 2), fmt(Hdn, 1), fmt(fyd, 2)),
            fmt(As_tir, 2, "cm²"), "NBR 9062, 7.3.5")
    v.passo("Taxa mecânica mínima", "ω = ρ·f<sub>yk</sub>/f<sub>ck</sub> > 0,04 → A<sub>s,tir</sub> ≥ 0,04·(f<sub>ck</sub>/f<sub>yk</sub>)·b·d", "",
            fmt(As_min, 2, "cm²"), "NBR 9062, 7.3.5.2")
    n, fi = _barras(As_nec, (10.0, 12.5, 16.0, 20.0, 25.0), n_min=2)
    fi = min(fi, 25.0)
    v.Sd, v.Rd = As_nec, n * BITOLAS[fi][0]
    v.passo("Adotado", "", "", "%d ø %s (%s cm²)" % (n, fmt(fi, 1), fmt(v.Rd, 2)), "")
    r.add(v)
    # a biela / o cisalhamento
    if ad > 1.0:
        from .nbr6118 import cisalhamento
        vs, ds = cisalhamento(b, d, Fdn, conc, aco)
        for x in vs:
            r.add(x)
    elif ad > 0.5:
        th = math.atan(0.9 * d / a)
        Rcd = Fdn / math.sin(th)
        largura = 0.2 * d                                   # a zona comprimida junto ao suporte (modelo adotado)
        sig = Rcd / (b * largura * math.cos(th) + 1e-9) if math.cos(th) > 0 else float("inf")
        lim = conc.fcd if carga_direta else 0.85 * conc.fcd
        vb = Verificacao("Consolo — biela comprimida", norma="NBR 9062, 7.3.4.1", Sd=sig, Rd=lim, unidade="kN/cm²")
        vb.passo("Força na biela (modelo da Figura 18)", "R<sub>cd</sub> = F<sub>d</sub>/sen θ, tg θ = 0,9d/a",
                 "θ = %s°" % fmt(math.degrees(th), 1), fmt(Rcd, 1, "kN"), "NBR 9062, Figura 18")
        vb.passo("Tensão na biela (largura 0,2·d na face do suporte)", "σ = R<sub>cd</sub>/(b·0,2d·cos θ) ≤ f<sub>cd</sub> (carga direta)",
                 "", fmt(sig * 10, 2, "MPa"), "NBR 9062, 7.3.4.1")
        vb.observacao = "a norma não fixa a geometria da biela: largura 0,2·d adotada pelo programa — confira"
        r.add(vb)
    else:
        rho = v.Rd / (b * d)
        tw_u = min(3.0 + 0.9 * rho * fyd * 10.0, 0.27 * (1 - conc.fck_MPa / 250.0) * conc.fcd * 10.0, 8.0)
        tw_d = Fdn / (b * d) * 10.0
        vb = Verificacao("Consolo muito curto — cisalhamento no plano de ligação", norma="NBR 9062, 7.3.4.2", Sd=tw_d, Rd=tw_u, unidade="MPa")
        vb.passo("Resistente", "τ<sub>wu</sub> = 3,0 + 0,9·ρ·f<sub>yd</sub> ≤ 0,27(1 − f<sub>ck</sub>/250)f<sub>cd</sub> e ≤ 8 MPa", "",
                 fmt(tw_u, 2, "MPa"), "NBR 9062, 7.3.4.2")
        r.add(vb)
    # costura e estribos
    if ad <= 1.0:
        k = 0.4 if ad > 0.5 else 0.5
        cost = k * Asv / d * 100.0                          # cm²/m na faixa 2d/3
        cost_min = 0.15 * b
        vc = Verificacao("Consolo — armadura de costura", norma="NBR 9062, 7.3.6", Sd=max(cost, cost_min), Rd=max(cost, cost_min), unidade="cm²/m")
        vc.passo("Distribuída em 2d/3 junto ao tirante", "(A<sub>s</sub>/s)<sub>cost</sub> ≥ %s·A<sub>sv</sub>/d; mínimo 0,15·b" % fmt(k, 1),
                 "%s × %s / %s" % (fmt(k, 1), fmt(Asv, 2), fmt(d, 1)), fmt(max(cost, cost_min), 2, "cm²/m"), "NBR 9062, 7.3.6")
        r.add(vc)
        ve = Verificacao("Consolo — estribos verticais (construtivos)", norma="NBR 9062, 7.3.7.2", Sd=0.0015 * b * h, Rd=0.0015 * b * h, unidade="cm²")
        ve.passo("Taxa mínima", "0,15 %·b<sub>w</sub>·h", "", fmt(0.0015 * b * h, 2, "cm²"), "NBR 9062, 7.3.7.2")
        r.add(ve)
    if not carga_direta:
        vsus = Verificacao("Consolo — armadura de suspensão (carga indireta)", norma="NBR 9062, 7.3.8", Sd=Fdn / fyd, Rd=Fdn / fyd, unidade="cm²")
        r.add(vsus)
    r.dados.update({"tipo": tipo, "a_d": ad, "d": d, "gn": gn, "Hd": Hd, "As_tir": v.Rd, "barras": (n, fi)})
    r.hipotese("consolo", "%s; γn = %s; Hd = %s kN (%s)." % (tipo, fmt(gn, 1), fmt(Hd, 1), apoio), "norma")
    return r


# ------------------------------------------------------------------ aparelho de apoio de elastômero (7.2.1.6)

SHORE_G = {50: 0.08, 60: 0.10, 70: 0.12}              # kN/cm² (Tabela 11: 0,8 / 1,0 / 1,2 MPa)


def elastomero_simples(a: float, b: float, h: float, Ngk: float, Nqk: float, Hk: float, shore: int = 60,
                       rotacao_g: float = 0.0, rotacao_q: float = 0.0, elemento: str = "Aparelho de apoio") -> Resultado:
    """aparelho simples (uma camada), a × b em planta (a na direção do vão), espessura h (cm); cargas
    características (kN) e as rotações (rad). Tensão de contato, distorção, deslizamento, cisalhamento
    total e estabilidade (7.2.1.6)"""
    r = Resultado(elemento, perfil="%s × %s × %s cm, dureza Shore %d" % (fmt(a, 0), fmt(b, 0), fmt(h, 1), shore), material="elastômero")
    G = SHORE_G.get(shore)
    if G is None:
        raise ErroDeDados("dureza Shore A %s fora da Tabela 11 (use 50, 60 ou 70)" % shore)
    A = a * b
    Nk = Ngk + Nqk
    sk = Nk / A
    v = Verificacao("Elastômero — tensão de contato", norma="NBR 9062, 7.2.1.6.19", Sd=sk * 10, Rd=7.0, unidade="MPa")
    v.passo("Aparelho simples", "σ<sub>k</sub> = N<sub>k</sub>/(a·b) ≤ 7,0 MPa", "%s / (%s × %s)" % (fmt(Nk, 1), fmt(a, 0), fmt(b, 0)), fmt(sk * 10, 2, "MPa"), "")
    r.add(v)
    # distorção: a_h = H·h/(G·A) (permanente com G/2)
    ah = Hk * h / (G * A)
    vd = Verificacao("Elastômero — deformação por cisalhamento", norma="NBR 9062, 7.2.1.6.21", Sd=ah, Rd=0.5 * h, unidade="cm")
    vd.passo("Deslocamento horizontal", "a<sub>h</sub> = H·h/(G·a·b) ≤ h/2", "%s × %s / (%s × %s)" % (fmt(Hk, 1), fmt(h, 1), fmt(G * 10, 1), fmt(A, 0)),
             fmt(ah, 2, "cm"), "")
    r.add(vd)
    # deslizamento
    A1 = max((a - ah) * b, 1e-6)
    s_g = Ngk / A1 * 10.0
    s_t = Nk / A1 * 10.0
    s_m = max(s_g, s_t)
    mu = 0.1 + 0.6 / s_m if s_m > 0 else 0.1
    vs = Verificacao("Elastômero — deslizamento", norma="NBR 9062, 7.2.1.6.22", Sd=Hk, Rd=mu * Nk, unidade="kN")
    vs.passo("Coeficiente de atrito", "μ = 0,1 + 0,6/σ'<sub>mk</sub>", "σ'<sub>mk</sub> = %s MPa" % fmt(s_m, 2), fmt(mu, 3), "")
    r.add(vs)
    vmin = Verificacao("Elastômero — tensão mínima (não deslizar)", norma="NBR 9062, 7.2.1.6.22 a)", Sd=1.0 + a / b, Rd=s_g, unidade="MPa")
    vmin.passo("N<sub>mín,k</sub>/A' ≥ 1 + a/b", "", "", fmt(s_g, 2, "MPa"), "")
    r.add(vmin)
    # cisalhamento total
    S = A / (2.0 * (a + b) * h)
    tn = 1.5 / S * (Ngk + 1.5 * Nqk) / A
    th_ = Hk / A
    tt = G * a * a / (2.0 * h * h) * (rotacao_g + 1.5 * rotacao_q)
    tau = tn + th_ + tt
    vt = Verificacao("Elastômero — tensão de cisalhamento total", norma="NBR 9062, 7.2.1.6", Sd=tau, Rd=5.0 * G, unidade="kN/cm²")
    vt.passo("τ = τ<sub>n</sub> + τ<sub>h</sub> + τ<sub>θ</sub> ≤ 5G", "τ<sub>n</sub> = (1,5/S)(N<sub>g</sub> + 1,5N<sub>q</sub>)/(ab); S = ab/[2(a+b)h]",
             "S = %s" % fmt(S, 2), fmt(tau * 10, 2, "MPa"), "")
    r.add(vt)
    vest = Verificacao("Elastômero — estabilidade", norma="NBR 9062, 7.2.1.6", Sd=h, Rd=a / 5.0, unidade="cm")
    vest.passo("Verificação dispensada se h < a/5", "", "", "", "")
    r.add(vest)
    return r
