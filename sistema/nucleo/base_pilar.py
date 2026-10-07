# -*- coding: utf-8 -*-
"""Base de pilar I ou H pela ABNT NBR 8800:2024, Subseção 6.7 (com a Errata 1:2025).

O método da norma (6.7.2) — transcrito das páginas 100 a 109 da norma:

* a geometria sai da Tabela 18 pelo diâmetro do chumbador: ℓx = d + 4·a₁, ℓy = (0,5·n_b − 1)·a₂ + 2·a₁ ≥ b_f + 25 mm;
  base tipo 1 (chumbadores externos às mesas, 4 ≤ n_b ≤ 8) ou tipo 2 (internos, n_b = 4, só os casos C1, C2, T1, T2);
* com a excentricidade e = M_Sd/N_Sd, os casos da Figura 22 (compressão: C1 sem momento, C2 pequena excentricidade
  sem tração nos chumbadores, C3 grande excentricidade com tração) e da Figura 23 (tração: T1, T2 sem pressão de
  contato, T3 com pressão de contato);
* a espessura mínima da placa t_p,min, o diâmetro mínimo do chumbador d_b,min (casos com tração) e a força cortante
  resistente V_Rd por atrito (μ = 0,45); quando V_Sd > V_Rd (e sempre em T1 e T2), um dispositivo: arruelas especiais
  soldadas à placa (6.7.2.5) ou placa de cisalhamento (6.7.2.4);
* σ_c,Rd pela 6.6.5: 0,85·f_ck/γ_c·√(A₂/A₁) ≤ 1,7·f_ck/γ_c, com A₂ a maior área do bloco homotética à placa.

O que a norma garante pelas disposições construtivas da Tabela 18 (chumbadores ASTM A36 com porca hexagonal pesada,
embutimento h₁ com arruela e porca na ponta, armadura mínima do bloco, f_ck ≥ f_ck,mín, argamassa de assentamento com o
dobro do f_ck do bloco): o arrancamento do chumbador e o esmagamento na porca de ancoragem não se verificam à parte
(6.7.1.5). Momento só em torno do eixo de maior inércia do perfil (6.7.1.3); base de pilar tubular é da ABNT NBR 16239.

Unidades internas: N e mm (MPa = N/mm²); a interface recebe kN e kN·m.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

GAMA_A1, GAMA_A2, GAMA_C = 1.10, 1.35, 1.40
E_ACO = 200000.0
MU = 0.45                                 # atrito placa–argamassa expansiva (6.7.2.2-a)
FY_CHUMBADOR, FU_CHUMBADOR = 250.0, 400.0  # ASTM A36 (6.7.1.5-c)
FY_ARRUELA = 345.0                         # arruelas especiais (Tabela 18, nota a)

# Tabela 18 (com a Errata 1:2025): d_b pol → mm, a1, a2, a3, h1, h2, r1, r2, d_f, arruela (t, lado), e_n,
# f_ck,mín (MPa), N_b,mín, armadura mínima do bloco (S, φ) — mm
TABELA_18 = {
    '3/4"':   dict(db=19, a1=40, a2=80, a3=120, h1=450, h2=150, r1=175, r2=50, df=33, ta=6.3, arruela=50, en=40, fck_min=20, Nb_min=900, S=125, phi=10.0),
    '7/8"':   dict(db=22, a1=45, a2=90, a3=140, h1=465, h2=200, r1=225, r2=50, df=40, ta=6.3, arruela=65, en=50, fck_min=20, Nb_min=900, S=100, phi=10.0),
    '1"':     dict(db=25, a1=50, a2=100, a3=160, h1=465, h2=200, r1=225, r2=50, df=45, ta=8.0, arruela=75, en=60, fck_min=25, Nb_min=900, S=125, phi=12.5),
    '1.1/4"': dict(db=32, a1=65, a2=130, a3=190, h1=525, h2=225, r1=250, r2=60, df=50, ta=9.5, arruela=75, en=60, fck_min=25, Nb_min=1100, S=100, phi=12.5),
    '1.1/2"': dict(db=38, a1=80, a2=160, a3=230, h1=610, h2=250, r1=275, r2=70, df=60, ta=9.5, arruela=90, en=70, fck_min=25, Nb_min=1300, S=150, phi=16.0),
    '1.3/4"': dict(db=44, a1=90, a2=180, a3=270, h1=700, h2=300, r1=325, r2=70, df=70, ta=12.5, arruela=100, en=80, fck_min=25, Nb_min=1600, S=125, phi=16.0),
    '2"':     dict(db=50, a1=100, a2=200, a3=300, h1=850, h2=350, r1=375, r2=100, df=80, ta=16.0, arruela=125, en=90, fck_min=30, Nb_min=1800, S=100, phi=16.0),
}
DIAMETROS = list(TABELA_18)

# Tabela 23 da ABNT NBR 16239:2013 (bases de pilares tubulares): as mesmas dimensões da Tabela 18; mudam o f_ck,mín e a
# armadura mínima do bloco
TABELA_23 = {k: dict(v, **o) for (k, v), o in zip(TABELA_18.items(), (
    dict(fck_min=20, S=100, phi=10.0), dict(fck_min=20, S=100, phi=10.0), dict(fck_min=20, S=125, phi=12.5),
    dict(fck_min=20, S=125, phi=12.5), dict(fck_min=25, S=150, phi=16.0), dict(fck_min=25, S=150, phi=16.0),
    dict(fck_min=30, S=150, phi=16.0)))}


def geometria_tubo(perfil: dict, tipo: int, nb: int, diametro: str) -> dict:
    """a base de pilar tubular pela ABNT NBR 16239:2013, 8.2.1 e Figura 14: tipo 1 (tubo retangular, placa retangular),
    tipo 2 (tubo circular, placa retangular), tipo 3 (tubo circular, placa circular, n_b >= 8): mm"""
    T = TABELA_23[diametro]
    d, b = float(perfil["d"]), float(perfil.get("bf") or 0.0)
    circular = not b
    a1, a2 = float(T["a1"]), float(T["a2"])
    db = float(T["db"])
    if tipo == 3:
        ld = d + 4 * a1
        lx = ly = 0.90 * ld
        m = n = (0.90 * ld - 0.80 * d) / 2
        meq = (ld - 0.80 * d) / 2
        ly_eq = min(nb * (db + meq - a1), 0.90 * ld)
        nb_eq = min(2.0 / 3.0 * nb, 8.0)
        a = d / 2 + a1
    else:
        h, bb = (d, d) if circular else (d, b)
        lx = h + 4 * a1
        ly = max((0.5 * nb - 1) * a2 + 2 * a1, bb + 25.0)
        k = 0.80 if circular else 0.95
        m, n = (lx - k * h) / 2, (ly - k * bb) / 2
        meq, nb_eq = m, float(nb)
        ly_eq = min(nb * (db + m - a1), ly)
        a = h / 2 + a1
        ld = None
    return {"tipo": tipo, "nb": nb, "diametro": diametro, "db": db, "lx": lx, "ly": ly, "ld": ld, "a": a, "a1": a1, "a2": a2,
            "l0": None, "m": m, "n": n, "n0": 0.0, "m_eq": meq, "ly_eq": ly_eq, "nb_eq": nb_eq, "d": d, "bf": b or d, "tw": 0.0,
            "tab": T, "norma": "NBR 16239:2013, 8", "circular": circular}

# chapas grossas comerciais (mm) para a placa de base e a placa de cisalhamento
CHAPAS_MM = [12.5, 16.0, 19.0, 22.4, 25.0, 31.5, 37.5, 44.5, 50.0, 57.0, 63.0, 76.0]


def chapa_comercial(t_min: float) -> Optional[float]:
    for t in CHAPAS_MM:
        if t >= t_min - 1e-6:
            return t
    return None


def geometria(perfil: dict, tipo: int, nb: int, diametro: str, a1_tipo2: Optional[float] = None) -> dict:
    """a placa e os chumbadores pela Tabela 18 e pela Figura 21 (com a errata): mm"""
    T = TABELA_18[diametro]
    d, bf, tw = float(perfil["d"]), float(perfil["bf"]), float(perfil.get("tw") or 0.0)
    a1, a2 = float(T["a1"]), float(T["a2"])
    if tipo == 1:
        lx = d + 4 * a1
        ly = max((0.5 * nb - 1) * a2 + 2 * a1, bf + 25.0)
        a = d / 2 + a1                                   # a linha de chumbadores mais externa ao eixo da placa
        l0 = None
    else:
        nb = 4
        a1x = a1_tipo2 if a1_tipo2 is not None else a1   # na direção ℓx: entre 10 mm e o da tabela (nota f)
        lx = d + 4 * a1x
        ly = max(a2 + 2 * a1, bf + 25.0)
        a = a2 / 2
        l0 = min((0.5 * nb - 1) * a2 + 1.75 * (a2 - tw), d)
    return {"tipo": tipo, "nb": nb, "diametro": diametro, "db": float(T["db"]), "lx": lx, "ly": ly, "a": a, "a1": a1, "a2": a2,
            "l0": l0, "m": (lx - 0.95 * d) / 2, "n": (ly - 0.80 * bf) / 2, "n0": math.sqrt(d * bf) / 4, "d": d, "bf": bf, "tw": tw,
            "tab": T}


def sigma_c_rd(fck: float, A1: float, A2: float) -> float:
    """6.6.5: MPa"""
    return min(0.85 * fck / GAMA_C * math.sqrt(max(A2 / A1, 1.0)), 1.7 * fck / GAMA_C)


def bloco(g: dict) -> dict:
    """as dimensões mínimas do bloco (Tabela 18, nota e, com a errata): mm"""
    T = g["tab"]
    Nb = max(T["Nb_min"], g["lx"] + 2 * T["en"], g["lx"] + 2 * (T["a3"] - T["a1"]))
    Bb = max(g["ly"] + 2 * T["en"], g["ly"] + 2 * (T["a3"] - T["a1"]))
    return {"Nb": Nb, "Bb": Bb, "Ab": max(T["h1"] + 100.0, Nb), "S": T["S"], "phi": T["phi"]}


def caso(g: dict, N_kN: float, M_kNm: float, V_kN: float, fck: float, fy_placa: float, Bb: Optional[float] = None,
         Nb: Optional[float] = None) -> dict:
    """uma combinação (N > 0 compressão, kN; M em torno do eixo de maior inércia, kN·m; V, kN): o caso da norma, t_p,min,
    a força de tração por chumbador, d_b,min e V_Rd por atrito"""
    N, M, V = N_kN * 1e3, abs(M_kNm) * 1e6, abs(V_kN) * 1e3
    lx, ly, a, m, n, n0, nb = g["lx"], g["ly"], g["a"], g["m"], g["n"], g["n0"], g["nb"]
    d, bf, a1 = g["d"], g["bf"], g["a1"]
    blk = bloco(g)
    A1 = lx * ly
    Nbk, Bbk = (Nb or blk["Nb"]), (Bb or blk["Bb"])
    A2 = A1 * min(Nbk / lx, Bbk / ly) ** 2
    sRd = sigma_c_rd(fck, A1, A2)
    tau = min(0.2 * fck / GAMA_C, 4.0)
    fyd = fy_placa / GAMA_A1
    fubd = FU_CHUMBADOR / GAMA_A2
    r = {"N": N_kN, "M": abs(M_kNm), "V": abs(V_kN), "sigma_c_Rd": sRd, "Ft": 0.0, "Ft_lados": 0, "db_min": 0.0, "erro": None}
    if g.get("norma", "").startswith("NBR 16239"):
        return _caso_tubo(g, r, N, M, sRd, tau, fyd, fubd)
    lam_n0 = None
    if N > 0:
        X = 4 * d * bf / (d + bf) ** 2 * N / (A1 * sRd)
        r["X"] = X
        if X > 1.0:
            r["erro"] = "X = %.2f > 1,0: a placa não resiste à compressão (refazer a ligação, 6.7.2.1)" % X
            return r
        lam = min(2 * math.sqrt(X) / (1 + math.sqrt(1 - X)), 1.0)
        lam_n0 = lam * n0
    e = M / N if abs(N) > 1e-9 else (math.inf if M > 0 else 0.0)
    r["e"] = e if math.isfinite(e) else None
    p_de = lambda lc: math.sqrt(max(lc * (2 * m - lc), 0.0))             # noqa: E731

    def lmax(lc, com_lambda=True):
        if lc is None or lc >= m:
            return max(m, n, lam_n0 or 0.0) if com_lambda else max(m, n)
        return max(p_de(lc), n)
    if N > 0:
        lim = 0.5 * (lx - N / (sRd * ly))
        if M <= 1e-9:
            r["caso"] = "C1"
            sSd = N / A1
            r["sigma_c_Sd"] = sSd
            r["tp_min"] = max(m, n, lam_n0) * math.sqrt(2 * sSd / fyd)
            r["V_Rd"] = min(MU * sSd * A1 / GAMA_A2, tau * A1) / 1e3
        elif e <= lim:
            r["caso"] = "C2"
            lc = lx - 2 * e
            sSd = N / (lc * ly)
            r.update(lc=lc, sigma_c_Sd=sSd)
            r["tp_min"] = lmax(lc) * math.sqrt(2 * sSd / fyd)
            r["V_Rd"] = min(MU * sSd * lc * ly / GAMA_A2, tau * A1) / 1e3
        else:
            if g["tipo"] == 2:
                r["caso"] = "C3"
                r["erro"] = "grande excentricidade (C3): a base tipo 2 não cobre — use chumbadores externos (tipo 1)"
                return r
            r["caso"] = "C3"
            k = lx / 2 + a
            rad = k * k - 2 * N * (e + a) / (sRd * ly)
            if rad < 0:
                r["erro"] = "(ℓx/2 + a)² < 2N(e + a)/(σc,Rd·ℓy): alterar a ligação (6.7.2.2-c)"
                return r
            lc = k - math.sqrt(rad)
            Ft = 2 * (sRd * lc * ly - N) / nb
            r.update(lc=lc, sigma_c_Sd=sRd, Ft=Ft / 1e3, Ft_lados=1)
            tp1 = lmax(lc) * math.sqrt(2 * sRd / fyd)
            tp2 = math.sqrt(2 * nb * Ft * (m - a1) / (ly * fyd)) if m > a1 else 0.0
            r.update(tp_min=max(tp1, tp2), tp1=tp1, tp2=tp2)
            r["db_min"] = math.sqrt(4 * Ft / (0.75 * math.pi * fubd))
            r["V_Rd"] = min(MU * sRd * lc * ly / GAMA_A2, tau * A1) / 1e3
    else:
        T_ = -N                                                           # a tração (positiva)
        e = M / T_ if T_ > 1e-9 else math.inf
        r["e"] = e if math.isfinite(e) else None
        if M <= 1e-9 or e <= a:
            r["caso"] = "T1" if M <= 1e-9 else "T2"
            Ft = T_ / nb + (M / (a * nb) if M > 1e-9 else 0.0)
            r.update(Ft=Ft / 1e3, Ft_lados=2 if M <= 1e-9 else 1)
            if g["tipo"] == 1:
                r["tp_min"] = math.sqrt(2 * nb * Ft * (m - a1) / (ly * fyd)) if m > a1 else 0.0
            else:
                r["tp_min"] = math.sqrt(nb * Ft * (g["a2"] - g["tw"]) / (g["l0"] * fyd))
            r["db_min"] = math.sqrt(4 * Ft / (0.75 * math.pi * fubd))
            r["V_Rd"] = 0.0                                               # 6.7.2.3: só o dispositivo
        else:
            if g["tipo"] == 2:
                r["caso"] = "T3"
                r["erro"] = "grande excentricidade (T3): a base tipo 2 não cobre — use chumbadores externos (tipo 1)"
                return r
            r["caso"] = "T3"
            k = lx / 2 + a
            rad = k * k - 2 * T_ * (e - a) / (sRd * ly)
            if rad < 0:
                r["erro"] = "(ℓx/2 + a)² < 2N(e − a)/(σc,Rd·ℓy): alterar a ligação (6.7.2.2-f)"
                return r
            lc = k - math.sqrt(rad)
            Ft = 2 * (sRd * lc * ly + T_) / nb
            r.update(lc=lc, sigma_c_Sd=sRd, Ft=Ft / 1e3, Ft_lados=1)
            tp1 = lmax(lc, com_lambda=False) * math.sqrt(2 * sRd / fyd)
            tp2 = math.sqrt(2 * nb * Ft * (m - a1) / (ly * fyd)) if m > a1 else 0.0
            r.update(tp_min=max(tp1, tp2), tp1=tp1, tp2=tp2)
            r["db_min"] = math.sqrt(4 * Ft / (0.75 * math.pi * fubd))
            r["V_Rd"] = min(MU * sRd * lc * ly / GAMA_A2, tau * A1) / 1e3
    return r


def _caso_tubo(g: dict, r: dict, N: float, M: float, sRd: float, tau: float, fyd: float, fubd: float) -> dict:
    """os casos da ABNT NBR 16239:2013, 8.2.2 (pilar tubular) — as diferenças para a 6.7 da NBR 8800: l_max = max(m, n);
    V_Rd = mu*sigma*l*l_y (sem gama_a2); a condição de C3/T3 com 2,25*N(e + a) (tipos 1 e 2) ou 3,125 (tipo 3); F_t com
    n_b,eq; t_p,min2 com m_eq e l_y,eq. No T3 a norma imprime d_b,min sem o 0,75 do C3 — usado o 0,75 (a favor da
    segurança)"""
    lx, ly, a, m, n, nb = g["lx"], g["ly"], g["a"], g["m"], g["n"], g["nb"]
    meq, lyeq, nbeq, a1 = g["m_eq"], g["ly_eq"], g["nb_eq"], g["a1"]
    A1 = lx * ly
    kc = 3.125 if g["tipo"] == 3 else 2.25

    def p_de(lc):
        return math.sqrt(max(lc * (2 * m - lc), 0.0))

    def lmax(lc):
        return max(m, n) if (lc is None or lc >= m) else max(p_de(lc), n)

    def tp2(Ft):
        return math.sqrt(2 * nbeq * Ft * (meq - a1) / (lyeq * fyd)) if meq > a1 else 0.0

    def db_de(Ft):
        return math.sqrt(4 * Ft / (0.75 * math.pi * fubd))
    if N > 0:
        e = M / N
        r["e"] = e
        if M <= 1e-9:
            r["caso"] = "C1"
            s = N / A1
            r.update(sigma_c_Sd=s, tp_min=max(m, n) * math.sqrt(2 * s / fyd), V_Rd=min(MU * N, tau * A1) / 1e3)
        elif e <= 0.5 * (lx - N / (sRd * ly)):
            r["caso"] = "C2"
            lc = lx - 2 * e
            s = N / (lc * ly)
            r.update(lc=lc, sigma_c_Sd=s, tp_min=lmax(lc) * math.sqrt(2 * s / fyd), V_Rd=min(MU * s * lc * ly, tau * A1) / 1e3)
        else:
            r["caso"] = "C3"
            k = lx / 2 + a
            if k * k < kc * N * (e + a) / (sRd * ly):
                r["erro"] = "(lx/2 + a)² < %.3g·N(e + a)/(σc,Rd·ℓy): alterar a ligação (NBR 16239, 8.2.2-c)" % kc
                return r
            lc = k - math.sqrt(k * k - 2 * N * (e + a) / (sRd * ly))
            Ft = 2 * (sRd * lc * ly - N) / nbeq
            r.update(lc=lc, sigma_c_Sd=sRd, Ft=Ft / 1e3, Ft_lados=1, tp1=lmax(lc) * math.sqrt(2 * sRd / fyd), tp2=tp2(Ft))
            r.update(tp_min=max(r["tp1"], r["tp2"]), db_min=db_de(Ft), V_Rd=min(MU * sRd * lc * ly, tau * A1) / 1e3)
    else:
        T_ = -N
        e = M / T_ if T_ > 1e-9 else math.inf
        r["e"] = e if math.isfinite(e) else None
        if M <= 1e-9 or e <= a:
            r["caso"] = "T1" if M <= 1e-9 else "T2"
            Ft = T_ / nb + (M / (a * nbeq) if M > 1e-9 else 0.0)
            r.update(Ft=Ft / 1e3, Ft_lados=2 if M <= 1e-9 else 1, db_min=db_de(Ft), V_Rd=0.0)
            r["tp_min"] = math.sqrt(2 * nb * Ft * (meq - a1) / (lyeq * fyd)) if meq > a1 else 0.0
        else:
            r["caso"] = "T3"
            k = lx / 2 + a
            if k * k < kc * T_ * (e + a) / (sRd * ly):
                r["erro"] = "(lx/2 + a)² < %.3g·N(e + a)/(σc,Rd·ℓy): alterar a ligação (NBR 16239, 8.2.2-f)" % kc
                return r
            lc = k - math.sqrt(k * k - 2 * T_ * (e - a) / (sRd * ly))
            Ft = 2 * (sRd * lc * ly + T_) / nbeq
            r.update(lc=lc, sigma_c_Sd=sRd, Ft=Ft / 1e3, Ft_lados=1, tp1=lmax(lc) * math.sqrt(2 * sRd / fyd), tp2=tp2(Ft))
            r.update(tp_min=max(r["tp1"], r["tp2"]), db_min=db_de(Ft), V_Rd=min(MU * sRd * lc * ly, tau * A1) / 1e3)
    return r


def v_rd_arruelas(g: dict, tp: float, Ft_kN: float, lados: int, sRd: float, fy_placa: float) -> float:
    """6.7.2.5: as arruelas especiais soldadas à placa — a soma dos V_Rd,i (kN); F_t,Sd,i nos chumbadores tracionados
    (um lado ou os dois), zero nos outros. F_v,Rd,i = 0,4·A_b·f_ub/γ_a2 (rosca no plano de corte, 6.3.3.2)"""
    T = g["tab"]
    db, ta, nb = g["db"], T["ta"], g["nb"]
    Ab = math.pi * db * db / 4
    Fv = 0.4 * Ab * FU_CHUMBADOR / GAMA_A2
    alfa = 1.45 * (tp + 0.5 * ta) / db * FU_CHUMBADOR / fy_placa * GAMA_A1 / GAMA_A2
    teto = 5 * db * db * sRd

    def um(Ft):
        q = 0.533 * Ft
        rad = (1 + alfa ** 2) * Fv ** 2 - q * q
        if rad <= 0:
            return 0.0
        return min((math.sqrt(rad) - alfa * q) / (1 + alfa ** 2), teto)
    total = int(round(g.get("nb_eq") or nb))                         # NBR 16239, 8.2.5: a soma vai até n_b,eq
    tracionados = total if lados == 2 else (total // 2 if lados == 1 else 0)
    return (tracionados * um(Ft_kN * 1e3) + (total - tracionados) * um(0.0)) / 1e3


def placa_de_cisalhamento(V_kN: float, fck: float, fy_placa: float, en: float, bh: float, tp: float) -> dict:
    """6.7.2.4: a altura b_v para a força cortante (σ_c,Rd com A₂/A₁ = 4), a espessura t_pv,min e o momento na solda"""
    s = sigma_c_rd(fck, 1.0, 4.0)
    V = abs(V_kN) * 1e3
    bv = en + max(V / (s * bh), 50.0)
    bv = math.ceil(bv / 10.0) * 10.0
    tpv = math.sqrt(2 * V * (bv + en) / (bh * fy_placa / GAMA_A1))
    t = chapa_comercial(tpv)
    return {"bh": bh, "bv": bv, "tpv_min": tpv, "tpv": t, "V_Rd": s * (bv - en) * bh / 1e3,
            "M_solda_kNm": 0.5 * s * bh * (bv * bv - en * en) / 1e6, "ok": t is not None and t <= tp + 1e-6}


def verificar(perfil: dict, combs: Sequence[dict], tipo: int, nb: int, diametro: str, fck: float = 25.0,
              fy_placa: float = 250.0) -> dict:
    """a base com uma geometria nas combinações (cada uma com N, M, V concomitantes): a espessura (a maior t_p,min,
    arredondada para a chapa comercial), os chumbadores (d_b ≥ d_b,mín) e a força cortante (atrito, senão arruelas
    soldadas, senão placa de cisalhamento)"""
    tubo = (perfil.get("tipo") == "tubo")
    g = geometria_tubo(perfil, tipo, nb, diametro) if tubo else geometria(perfil, tipo, nb, diametro)
    T = g["tab"]
    linhas, falhas = [], []
    if fck < T["fck_min"]:
        falhas.append("f_ck do bloco %.0f MPa < f_ck,mín %d MPa da Tabela 18 para ø %s" % (fck, T["fck_min"], diametro))
    tp_min = 0.0
    for c in combs:
        r = caso(g, c["N"], c["M"], c["V"], fck, fy_placa)
        r.update({k: c[k] for k in ("comb", "sit") if k in c})
        linhas.append(r)
        if r["erro"]:
            falhas.append("%s (%s): %s" % (c.get("comb", ""), r.get("caso", ""), r["erro"]))
            continue
        tp_min = max(tp_min, r["tp_min"])
        if r["db_min"] > g["db"] + 1e-9:
            falhas.append("%s (%s): d_b,mín %.1f mm > %.0f mm" % (c.get("comb", ""), r["caso"], r["db_min"], g["db"]))
    fatais = [f for f in falhas if "alterar" in f or "não resiste" in f or "não cobre" in f]
    tp = chapa_comercial(max(tp_min, 12.5)) if not fatais else None
    if tp is None and not fatais:
        falhas.append("t_p,mín %.1f mm acima da maior chapa comercial (%.0f mm)" % (tp_min, CHAPAS_MM[-1]))
    # a força cortante: atrito; senão arruelas soldadas; senão placa de cisalhamento
    disp = "atrito"
    pc = None
    if tp is not None:
        precisa = [r for r in linhas if not r["erro"] and r["V"] > r["V_Rd"] + 1e-9]
        if precisa:
            disp = "arruelas soldadas"
            for r in precisa:
                r["V_Rd_arruelas"] = v_rd_arruelas(g, tp, r["Ft"], r["Ft_lados"], r["sigma_c_Rd"], fy_placa)
            if any(r["V"] > r["V_Rd_arruelas"] + 1e-9 for r in precisa):
                disp = "placa de cisalhamento"
                Vmax = max(r["V"] for r in precisa)
                largura = g["bf"] * (0.5 if tubo and g.get("circular") else 1.0)
                pc = placa_de_cisalhamento(Vmax, fck, fy_placa, T["en"], min(largura, g["ly"] - 2 * T["a1"]), tp)
                if not pc["ok"]:
                    falhas.append("placa de cisalhamento: t_pv,mín %.1f mm maior que a placa de base (%.1f mm)" % (pc["tpv_min"], tp))
    uso_tp = (tp_min / tp) if tp else None
    gov_tp = max((r for r in linhas if not r["erro"]), key=lambda r: r["tp_min"], default=None)
    gov_ft = max((r for r in linhas if not r["erro"]), key=lambda r: r["Ft"], default=None)
    return {"ok": not falhas and tp is not None, "falhas": falhas, "geometria": {k: v for k, v in g.items() if k != "tab"},
            "norma": g.get("norma") or "NBR 8800:2024, 6.7",
            "tabela": dict(T), "bloco": bloco(g), "tp": tp, "tp_min": tp_min, "uso_tp": uso_tp, "dispositivo": disp,
            "placa_cisalhamento": pc, "combinacoes": linhas,
            "governa_tp": gov_tp and {"comb": gov_tp.get("comb"), "sit": gov_tp.get("sit"), "caso": gov_tp["caso"]},
            "governa_ft": gov_ft and gov_ft["Ft"] > 0 and {"comb": gov_ft.get("comb"), "sit": gov_ft.get("sit"), "caso": gov_ft["caso"],
                                                         "Ft": gov_ft["Ft"], "db_min": gov_ft["db_min"]},
            "peso_placa_kg": ((g["ld"] ** 2 * math.pi / 4 if g.get("ld") else g["lx"] * g["ly"]) * tp * 7.85e-6) if tp else None}


def dimensionar(perfil: dict, combs: Sequence[dict], fck: float = 25.0, fy_placa: float = 250.0,
                tipos: Sequence[int] = (1,)) -> dict:
    """a base mais leve que passa: percorre os tipos, os diâmetros (do menor) e o número de chumbadores (4, 6, 8) e fica
    com a de menor peso (placa + chumbadores) entre as que passam; sem nenhuma, devolve a de menor espessura necessária
    (com as falhas) — para dizer o que falta"""
    melhor, menos_ruim = None, None
    tubo = perfil.get("tipo") == "tubo"
    for tipo in tipos:
        for diam in DIAMETROS:
            for nb in ((4, 6, 8) if (tipo == 1 or (tubo and tipo == 2)) else ((8,) if tubo else (4,))):
                r = verificar(perfil, combs, tipo, nb, diam, fck, fy_placa)
                g = r["geometria"]
                peso = (r["peso_placa_kg"] or 0.0) + nb * math.pi * g["db"] ** 2 / 4 * (r["tabela"]["h1"] + 300) * 7.85e-6
                r["peso_kg"] = round(peso, 1)
                if r["ok"]:
                    if melhor is None or peso < melhor["peso_kg"]:
                        melhor = r
                else:
                    crit = (len([f for f in r["falhas"] if "alterar" in f or "não resiste" in f]), r["tp_min"] or 1e9)
                    if menos_ruim is None or crit < menos_ruim[0]:
                        menos_ruim = (crit, r)
    return melhor or (menos_ruim[1] if menos_ruim else {"ok": False, "falhas": ["sem geometria"]})


# ------------------------------------------------------------------ o chumbador em J (barra roscada dobrada)

def chumbador_j(Ft_kN: float, db: float, fck: float, h_disponivel: float, fy: float = FY_CHUMBADOR) -> dict:
    """a ancoragem por aderência do chumbador em J — barra redonda roscada de aço ASTM A36 dobrada na ponta,
    concretada junto com a armadura do bloco — pela ABNT NBR 6118:2023 (a Emenda 1:2026 não muda estes itens):

    * f_bd = η1·η2·η3·f_ctd (9.3.2.1), f_ctd = f_ctk,inf/γ_c, f_ctk,inf = 0,7·0,3·f_ck^(2/3) (8.2.5); η1 = 1,0 (barra
      lisa, Tabela 8.2 — a barra roscada não tem nervuras), η2 = 1,0 (vertical, boa aderência, 9.3.1-a), η3 = 1,0
      (φ < 32 mm) ou (132 − φ)/100;
    * ℓ_b = (φ/4)·(f_yd/f_bd) ≥ 25φ (9.4.2.4), f_yd = f_y/1,15;
    * ℓ_b,nec = α·ℓ_b·A_s,calc/A_s,ef ≥ ℓ_b,mín = máx(0,3ℓ_b; 10φ; 100 mm) (9.4.2.5), α = 0,7 com gancho e cobrimento
      ≥ 3φ no plano normal ao gancho; A_s,calc/A_s,ef = F_t,Sd/(A_s·f_yd);
    * barra lisa: gancho obrigatório (9.4.2.1-a) e semicircular (9.4.2.3) — o J — com ponta reta ≥ 2φ e pino de
      dobramento ≥ 4φ (φ < 20) ou 5φ (Tabela 9.1, CA-25).

    Isto substitui a dispensa da 6.7.1.5 da NBR 8800 (que vale só para o chumbador reto com porca e arruela de
    ancoragem da Tabela 18). A força chega ao bloco pela aderência: a armadura do bloco (suspensão e a transversal de
    9.4.2.6, 25% da força) é do projeto de fundações. mm, kN, MPa."""
    fctd = 0.7 * 0.3 * fck ** (2.0 / 3.0) / GAMA_C
    eta3 = 1.0 if db < 32 else (132 - db) / 100
    fbd = 1.0 * 1.0 * eta3 * fctd
    fyd = fy / 1.15
    lb = max(db / 4 * fyd / fbd, 25 * db)
    As = math.pi * db * db / 4
    razao = min(Ft_kN * 1e3 / (As * fyd), 1.0) if Ft_kN > 0 else 0.0
    lb_min = max(0.3 * lb, 10 * db, 100.0)
    lb_nec = max(0.7 * lb * razao, lb_min)
    return {"fctd": fctd, "fbd": fbd, "fyd": fyd, "lb": lb, "razao_As": razao, "lb_min": lb_min, "lb_nec": lb_nec,
            "h_disponivel": h_disponivel, "ok": lb_nec <= h_disponivel + 1e-6, "ponta_reta_min": 2 * db,
            "pino_dobramento_min": (4 if db < 20 else 5) * db, "F_aco_ok": Ft_kN * 1e3 <= 0.75 * As * FU_CHUMBADOR / GAMA_A2 + 1e-6}


# ------------------------------------------------------------------ a base com abas de reforço (enrijecedores)

def com_abas(perfil: dict, combs: Sequence[dict], geo: dict, fck: float = 25.0, fy_placa: float = 250.0) -> dict:
    """a base de pilar I com chumbadores externos (tipo 1) e duas abas de reforço triangulares, uma de cada lado, no
    plano da alma, da face da mesa até a borda da placa na direção do momento — MÉTODO RACIONAL: a NBR 8800:2024, 6.7,
    é para placa sem enrijecedor; aqui os próprios casos da 6.7 (C1–C3, T1–T3, com ℓ_c, σ e F_t de cada combinação)
    são refeitos com o braço reduzido pelo apoio novo que a aba dá à placa:

    * lado comprimido: o balanço m vira m_c = mín(m; (ℓ_y − t_aba)/2) — a faixa entre a mesa e a aba vence o menor vão;
    * lado tracionado: o braço do chumbador (m − a₁) vira mín(m − a₁; y_b − t_aba/2), y_b a distância de través do
      chumbador à alma (a aba);
    * aba: a parte da força do lado que vai para ela — a tração dos chumbadores do lado (toda, a favor da segurança) ou
      metade da pressão na faixa além da face da mesa — em balanço da mesa: flexão (Z = t·h²/4), cortante
      (0,6·f_y·t·h/γ_a1) e a borda livre λ = L_livre/t ≤ 0,56·√(E/f_y) (o limite de chapa comprimida em balanço da
      Tabela F.1, a favor da segurança);
    * solda da aba no pilar: dois filetes de altura h sob V e M (0,6·f_w·0,707a/γ_w2).
    Usa a geometria e os chumbadores da base sem aba (`geo`); mm, kN, MPa."""
    g0 = geometria(perfil, 1, geo["nb"], geo["diametro"])
    nb, a1, lx, ly, m, n, d = g0["nb"], g0["a1"], g0["lx"], g0["ly"], g0["m"], g0["n"], g0["d"]
    y_b = ((0.5 * nb - 1) * g0["a2"]) / 2
    fyd = fy_placa / GAMA_A1
    lam_lim = 0.56 * math.sqrt(E_ACO / fy_placa)
    melhor = None
    for tg in (9.5, 12.5, 16.0, 19.0, 22.4, 25.0, 31.5):
        m_c = min(m, (ly - tg) / 2)
        b_t = min(m - a1, y_b - tg / 2) if y_b > tg / 2 else (m - a1)
        g_c = dict(g0, m=m_c)
        g_t = dict(g0, m=a1 + max(b_t, 1.0))
        tp_min, F, gov = 0.0, 0.0, None
        for c in combs:
            rc = caso(g_c, c["N"], c["M"], c["V"], fck, fy_placa)
            rt = caso(g_t, c["N"], c["M"], c["V"], fck, fy_placa)
            if rc["erro"] or rt["erro"]:
                continue
            if rc["caso"] in ("C1", "C2"):
                t_ = rc["tp_min"]
            elif rc["caso"] in ("T1", "T2"):
                t_ = rt["tp_min"]
            else:                                          # C3, T3: a parte comprimida com m_c e a tracionada com b_t
                t_ = max(rc.get("tp1", 0.0), rt.get("tp2", 0.0))
            if t_ > tp_min:
                tp_min, gov = t_, (c.get("comb"), c.get("sit"), rc["caso"])
            T_lado = rc["Ft"] * 1e3 * nb / 2
            s = rc.get("sigma_c_Sd") or 0.0
            lc = rc.get("lc") or (lx if rc["caso"] == "C1" else 0.0)
            C_aba = 0.5 * s * ly * min(lc, (lx - d) / 2)
            F = max(F, T_lado, C_aba)
        tp = chapa_comercial(max(tp_min, 12.5))
        hg = max(150.0, math.ceil(1.2 * m / 10) * 10)
        L_livre = math.hypot(hg, m)
        M = F * max(a1, m / 2)
        u_flex = M / (tg * hg * hg / 4 * fyd)
        u_cort = F / (0.6 * fy_placa * tg * hg / GAMA_A1)
        u_borda = (L_livre / tg) / lam_lim
        fw = math.hypot(F / (2 * hg), M / (2 * hg * hg / 6))
        perna = next((a for a in (5.0, 6.0, 8.0, 10.0, 12.0) if 0.6 * 485.0 * 0.707 * a / 1.35 >= fw), None)
        ok = tp is not None and max(u_flex, u_cort, u_borda) <= 1.0 and perna is not None
        r = {"tg": tg, "hg": hg, "Lg": m, "tp": tp, "tp_min": tp_min, "governa": gov, "u_flexao": u_flex, "u_cortante": u_cort,
             "u_borda": u_borda, "perna_solda": perna, "F_aba_kN": F / 1e3, "ok": ok}
        if ok:
            melhor = r
            break
        if melhor is None or max(u_flex, u_cort, u_borda) < max(melhor["u_flexao"], melhor["u_cortante"], melhor["u_borda"]):
            melhor = r
    peso = (lx * ly * (melhor["tp"] or 0.0) + 2 * 0.5 * melhor["hg"] * melhor["Lg"] * melhor["tg"] * 2) * 7.85e-6
    return dict(melhor, peso_kg=peso, metodo="racional (fora da 6.7: placa com enrijecedores)", nb=nb, diametro=geo["diametro"],
                lx=lx, ly=ly, falhas=[] if melhor["ok"] else ["a aba não fecha até 31,5 mm com altura %.0f mm: força de %.0f kN — "
                                                              "aba mais alta ou duas por lado" % (melhor["hg"], melhor["F_aba_kN"])])


def com_abas_nas_pontas(perfil: dict, combs: Sequence[dict], geo: dict, fck: float = 25.0, fy_placa: float = 250.0) -> dict:
    """a base de pilar I com DUAS abas por lado (quatro no total), alinhadas com as pontas das mesas, da face da mesa até
    a borda da placa na direção do momento — MÉTODO RACIONAL (a 6.7 é para placa sem enrijecedor), como `com_abas`:

    * os chumbadores ficam por fora das abas (de través, a y_b = b_f/2 + t_aba/2 + folga da arruela e do filete); com
      6 chumbadores, o do meio fica entre as abas, na linha da alma; a placa alarga o que for preciso (ℓ_y);
    * lado comprimido: entre as abas a placa vence o vão b_f − t_aba apoiada na mesa e nas duas abas (balanço
      equivalente mín(m; (b_f − t_aba)/2)); por fora delas, balanço até a borda (n' = ℓ_y/2 − b_f/2 − t_aba/2);
    * lado tracionado: o braço do chumbador é o menor entre (m − a₁) e a distância de través até a face da aba;
    * cada aba recebe metade da força do lado (a tração dos chumbadores do lado ou metade da pressão na faixa além da
      mesa) — flexão, cortante, borda livre e solda, como em `com_abas`. mm, kN, MPa"""
    g0 = geometria(perfil, 1, geo["nb"], geo["diametro"])
    nb, a1, lx, m, d, bf = g0["nb"], g0["a1"], g0["lx"], g0["m"], g0["d"], g0["bf"]
    T18 = g0["tab"]
    fyd = fy_placa / GAMA_A1
    lam_lim = 0.56 * math.sqrt(E_ACO / fy_placa)
    melhor = None
    for tg in (9.5, 12.5, 16.0, 19.0, 22.4, 25.0):
        folga = max(T18["arruela"] / 2 + 8.0 + 10.0, 1.5 * g0["db"])     # meia arruela + filete da aba + jogo de chave
        y_b = bf / 2 + tg / 2 + folga
        ly = max(g0["ly"], 2 * (y_b + a1))
        n_ext = ly / 2 - bf / 2 - tg / 2
        m_c = max(min(m, (bf - tg) / 2), 1.0)
        b_t = max(min(m - a1, folga), 1.0)
        g_c = dict(g0, ly=ly, m=m_c, n=n_ext)
        g_t = dict(g0, ly=ly, m=a1 + b_t, n=n_ext)
        tp_min, F, gov, falhas = 0.0, 0.0, None, []
        for c in combs:
            rc = caso(g_c, c["N"], c["M"], c["V"], fck, fy_placa)
            rt = caso(g_t, c["N"], c["M"], c["V"], fck, fy_placa)
            if rc["erro"] or rt["erro"]:
                falhas.append(rc["erro"] or rt["erro"])
                continue
            if rc["caso"] in ("C1", "C2"):
                t_ = rc["tp_min"]
            elif rc["caso"] in ("T1", "T2"):
                t_ = rt["tp_min"]
            else:
                t_ = max(rc.get("tp1", 0.0), rt.get("tp2", 0.0))
            if t_ > tp_min:
                tp_min, gov = t_, (c.get("comb"), c.get("sit"), rc["caso"])
            T_lado = rc["Ft"] * 1e3 * nb / 2
            s = rc.get("sigma_c_Sd") or 0.0
            lc = rc.get("lc") or (lx if rc["caso"] == "C1" else 0.0)
            C_faixa = s * ly * min(lc, (lx - d) / 2)
            F = max(F, T_lado / 2, C_faixa / 4)                 # duas abas por lado; metade da faixa vai para as abas
        tp = chapa_comercial(max(tp_min, 12.5))
        hg = max(150.0, math.ceil(1.2 * m / 10) * 10)
        M = F * max(a1, m / 2)
        u_flex = M / (tg * hg * hg / 4 * fyd)
        u_cort = F / (0.6 * fy_placa * tg * hg / GAMA_A1)
        u_borda = (math.hypot(hg, m) / tg) / lam_lim
        fw = math.hypot(F / (2 * hg), M / (2 * hg * hg / 6))
        perna = next((x for x in (5.0, 6.0, 8.0, 10.0, 12.0) if 0.6 * 485.0 * 0.707 * x / 1.35 >= fw), None)
        ok = tp is not None and max(u_flex, u_cort, u_borda) <= 1.0 and perna is not None and not falhas
        r = {"tg": tg, "hg": hg, "Lg": m, "tp": tp, "tp_min": tp_min, "governa": gov, "ly": ly, "y_b": y_b,
             "u_flexao": u_flex, "u_cortante": u_cort, "u_borda": u_borda, "perna_solda": perna, "F_aba_kN": F / 1e3,
             "ok": ok, "falhas": sorted(set(falhas))[:2]}
        if ok:
            melhor = r
            break
        if melhor is None or max(u_flex, u_cort, u_borda) < max(melhor["u_flexao"], melhor["u_cortante"], melhor["u_borda"]):
            melhor = r
    peso = (lx * melhor["ly"] * (melhor["tp"] or 0.0) + 4 * 0.5 * melhor["hg"] * melhor["Lg"] * melhor["tg"]) * 7.85e-6
    if not melhor["ok"] and not melhor["falhas"]:
        melhor["falhas"] = ["as abas não fecham até 25 mm com altura %.0f mm (força de %.0f kN por aba)" % (melhor["hg"], melhor["F_aba_kN"])]
    return dict(melhor, peso_kg=peso, metodo="racional (fora da 6.7: placa com quatro enrijecedores nas pontas das mesas)",
                nb=nb, diametro=geo["diametro"], lx=lx)


# ------------------------------------------------------------------ a especificação do chumbador em J

# porca hexagonal pesada (ASME B18.2.6, rosca UNC): altura ≈ diâmetro nominal; chave (distância entre faces), mm
PORCA_PESADA = {'3/4"': (19.1, 31.8), '7/8"': (22.2, 36.5), '1"': (25.4, 41.3), '1.1/4"': (31.8, 50.8), '1.1/2"': (38.1, 60.3),
                '1.3/4"': (44.5, 69.9), '2"': (50.8, 79.4)}
FIOS_UNC = {'3/4"': 10, '7/8"': 9, '1"': 8, '1.1/4"': 7, '1.1/2"': 6, '1.3/4"': 5, '2"': 4.5}


def especificar_chumbador_j(perfil: dict, combs: Sequence[dict], fck_opcoes: Sequence[float] = (25.0, 30.0, 35.0),
                            fy_placa: float = 250.0, t_grout: Optional[float] = None) -> dict:
    """as opções de chumbador em J para a base — barra redonda de aço ASTM A36 rosqueada na ponta de cima e dobrada
    em gancho semicircular na de baixo, concretada junto com a armadura do bloco. Para cada diâmetro e número de
    chumbadores (a geometria e a placa da 6.7, Tabela 18) e cada f_ck do bloco: a força por chumbador (a pior das
    combinações), o comprimento de ancoragem pela NBR 6118:2023 (9.4.2, com gancho), o comprimento total da barra, a
    rosca, as porcas e as arruelas — e o bloco que isso pede. A recomendada é a de menor peso de aço (barras + placa)
    com o bloco até 1,5 m de altura. mm, kN"""
    opcoes = []
    for diam in DIAMETROS:
        for nb in (4, 6, 8):
            for fck in fck_opcoes:
                r = verificar(perfil, combs, 1, nb, diam, fck, fy_placa)
                if r["tp"] is None or any("alterar" in f or "não resiste" in f for f in r["falhas"]):
                    continue
                if any("d_b,mín" in f for f in r["falhas"]):
                    continue
                g, T18 = r["geometria"], r["tabela"]
                db = g["db"]
                Ft = max((x.get("Ft") or 0.0) for x in r["combinacoes"])
                j = chumbador_j(Ft, db, fck, 1e9)
                D = j["pino_dobramento_min"]
                gancho = math.pi * (D + db) / 2 + j["ponta_reta_min"]          # o arco do J e a ponta reta
                porca_h, chave = PORCA_PESADA[diam]
                en = t_grout if t_grout is not None else float(T18["en"])
                acima = en + r["tp"] + T18["ta"] + porca_h + 3 * 25.4 / FIOS_UNC[diam] + 10.0     # 3 fios além da porca
                rosca = acima + porca_h + T18["ta"] + 30.0                                     # inclui a porca de nivelamento
                embut = j["lb_nec"]
                total = acima + embut + gancho
                bloco_h = embut + D / 2 + db + 50.0                                            # cobrimento de 50 mm sob o gancho
                peso = nb * math.pi * db * db / 4 * total * 7.85e-6 + (r["peso_placa_kg"] or 0.0)
                opcoes.append({"diametro": diam, "db": db, "nb": nb, "fck": fck, "Ft_kN": round(Ft, 1), "tp": r["tp"],
                               "lx": g["lx"], "ly": g["ly"], "fbd": round(j["fbd"], 3), "lb_nec": round(embut, 0),
                               "pino": D, "ponta_reta": j["ponta_reta_min"], "gancho": round(gancho, 0),
                               "projecao": round(acima, 0), "rosca": round(rosca, 0), "comprimento": round(total, 0),
                               "bloco_altura_min": round(max(bloco_h, B_ALTURA_MIN(r)), 0), "peso_kg": round(peso, 1),
                               "porca": "hexagonal pesada ASME B18.2.6 UNC %s, aço ASTM A36 (o mesmo da barra), chave %.0f mm, altura %.0f mm" % (diam, chave, porca_h),
                               "arruela": ("especial %s × %s × %s mm, fy 345 MPa, furo %.1f mm (d_b + 1,5)"
                                           % (T18["arruela"], T18["arruela"], T18["ta"], db + 1.5)).replace(".", ","),
                               "furo_placa": T18["df"], "dispositivo": r["dispositivo"], "ok_bloco": bloco_h <= 1500.0})
    validas = [o for o in opcoes if o["ok_bloco"]]
    rec = min(validas, key=lambda o: (o["peso_kg"], o["bloco_altura_min"])) if validas else None
    curto = min(opcoes, key=lambda o: o["comprimento"]) if opcoes else None
    return {"recomendada": rec, "mais_curta": curto, "opcoes": sorted(opcoes, key=lambda o: o["peso_kg"])[:12]}


def B_ALTURA_MIN(r: dict) -> float:
    """a altura mínima do bloco pela nota e da Tabela 18 (A_b), para comparar com a que a ancoragem pede"""
    return float((r.get("bloco") or {}).get("Ab") or 0.0)


__all__ = ["TABELA_18", "geometria", "caso", "verificar", "dimensionar", "sigma_c_rd", "bloco", "chumbador_j", "com_abas",
           "com_abas_nas_pontas", "especificar_chumbador_j"]
