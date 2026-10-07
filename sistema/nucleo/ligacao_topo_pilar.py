# -*- coding: utf-8 -*-
"""Ligação da viga apoiada no topo do pilar por duas chapas parafusadas — a solução de partida da Cobertura Kaefer
(07/10/2026): uma chapa soldada no topo do pilar, outra soldada na mesa inferior da viga, unidas por parafusos
verticais. Pela ABNT NBR 8800:2024 (com a Errata 1:2025):

* **parafusos** (6.3.3): tração F_t,Rd = A_be·f_ub/γ_a2 com A_be = 0,75·A_b (6.3.3.1, 6.3.2.2); cisalhamento
  F_v,Rd = 0,45·A_b·f_ub/γ_a2 com a rosca no plano de corte (6.3.3.2-a); tração e cisalhamento combinados
  (F_t/F_t,Rd)² + (F_v/F_v,Rd)² ≤ 1 (6.3.3.4); pressão de contato 1,2·ℓ_f·t·f_u/γ_a2 ≤ 2,4·d_b·t·f_u/γ_a2 (6.3.3.3-a,
  deformação no furo limitada);
* **chapas** pelo efeito de alavanca (6.3.5): placa flexível (6.3.5.4), t ≥ √(4(b − 0,5d_b)F_t,0,Sd·γ_a1/(p·f_u(1 + δα))),
  com p, δ, α e β de 6.3.5.2 (a ≤ 1,25b; β < 0 → trocar o parafuso); a placa rígida (6.3.5.3, α = 0) é informada;
* **solda de filete** do pilar na chapa (6.2.5, Tabela 9): 0,6·A_w·f_w/γ_w2, o filete corrido no contorno do pilar;
* **alma da viga** sob a compressão que o pilar entrega: escoamento local (5.7.3) e enrugamento (5.7.4), com ℓ_n o
  comprimento de contato ao longo da viga e a regra da distância à extremidade; se não passa, enrijecedores (5.7.9).

A força em cada parafuso sai do grupo elástico em torno do centro dos parafusos (N, M nos dois eixos, V e torção) —
a favor da segurança: o pivô real na borda comprimida da chapa daria braço maior e menos tração. A análise global
considera a ligação viga–pilar rígida; chapas parafusadas no topo são semirrígidas (depende das espessuras): é
apontado.

Unidades: mm, N, MPa internamente; a interface recebe kN e kN·m.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

GAMA_A1, GAMA_A2, GAMA_W2 = 1.10, 1.35, 1.35
E_ACO = 200000.0
FW_E70 = 485.0                                  # eletrodo E70XX (AWS A5.1, compatível com A36/A572, Tabela 8)
CHAPAS_MM = [9.5, 12.5, 16.0, 19.0, 22.4, 25.0, 31.5, 37.5, 44.5, 50.0]
# diâmetro nominal (mm), furo-padrão (mm, Tabela 14) e borda mínima cortada a maçarico (mm, Tabela 14 do sistema)
PARAFUSOS = {'5/8"': (15.875, 17.5, 28.0), '3/4"': (19.05, 20.6, 32.0), '7/8"': (22.225, 23.8, 38.0), '1"': (25.4, 28.6, 44.0)}
FILETES_MM = [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]


def perna_minima(t_mais_fina: float) -> float:
    """dimensão mínima do filete pela espessura da parte mais fina (Tabela 10 da NBR 8800)"""
    return 3.0 if t_mais_fina <= 6.35 else 5.0 if t_mais_fina <= 12.5 else 6.0 if t_mais_fina <= 19.0 else 8.0


def grupo(n: int, gx: float, gy: float) -> List[tuple]:
    """os parafusos em planta (mm, centro na origem; x na altura da seção do pilar, y na largura): 4 nos cantos de um
    retângulo gx×gy; 8 no contorno (cantos + meios)"""
    hx, hy = gx / 2, gy / 2
    pts = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    if n == 8:
        pts += [(0.0, -hy), (hx, 0.0), (0.0, hy), (-hx, 0.0)]
    return pts


def forcas_nos_parafusos(pts, N: float, Mx: float, My: float, V: float, T: float) -> tuple:
    """(maior tração, maior cortante) por parafuso, N: N > 0 compressão; Mx em torno de x (tração em +y), My em torno de y
    (tração em +x), em N·mm; V, T (torção) em N e N·mm"""
    n = len(pts)
    sx = sum(x * x for x, y in pts) or 1.0
    sy = sum(y * y for x, y in pts) or 1.0
    sr = sx + sy
    ft = max(-N / n + abs(Mx) * y / sy + abs(My) * x / sx for x, y in pts)
    fv = max(math.hypot(V / n + abs(T) * abs(y) / sr, abs(T) * abs(x) / sr) for x, y in pts)
    return max(ft, 0.0), fv


def alavanca(Ft0: float, Ft_rd: float, b: float, a: float, e_ext: float, e_int: float, db: float, df: float,
             fu: float, t: float) -> dict:
    """NBR 8800:2024, 6.3.5: a espessura da placa flexível (6.3.5.4) e da rígida (6.3.5.3) para a tração F_t,0,Sd sem
    alavanca, mm"""
    a = min(a, 1.25 * b)
    p = min(e_ext, 1.75 * b) + min(0.5 * e_int, 1.75 * b)
    delta = 1.0 - df / p
    bl = b - 0.5 * db
    if Ft0 <= 0:
        return {"p": p, "delta": delta, "beta": None, "alfa": 0.0, "t_rigida": 0.0, "t_flexivel": 0.0, "ok_parafuso": True}
    beta = ((a + 0.5 * db) / bl) * (Ft_rd / Ft0 - 1.0) if bl > 0 else -1.0
    if beta >= 1.0:
        alfa = 1.0
    elif beta > 0:
        alfa = min(1.0, beta / (delta * (1 - beta)))
    else:
        alfa = 0.0
    t_rig = math.sqrt(max(4 * bl * Ft0 * GAMA_A1 / (p * fu), 0.0))
    t_flex = math.sqrt(max(4 * bl * Ft0 * GAMA_A1 / (p * fu * (1 + delta * alfa)), 0.0))
    return {"p": p, "delta": delta, "beta": beta, "alfa": alfa, "t_rigida": t_rig, "t_flexivel": t_flex,
            "ok_parafuso": beta >= 0, "ok_chapa": t >= t_flex - 1e-6}


def _solda_pilar(pilar: dict, N: float, Mx: float, My: float, V: float, T: float) -> float:
    # Mx: o momento no eixo forte do pilar (o vetor na largura, tração variando ao longo da altura d); My: no eixo fraco
    """a maior força por comprimento no filete corrido no contorno do pilar (N/mm): tubo circular, tubo retangular ou I"""
    d, bf, tw, tf = pilar["d"], pilar.get("bf") or 0.0, pilar.get("tw") or 0.0, pilar.get("tf") or 0.0
    Nt = max(-N, 0.0)                                 # a tração (a compressão passa por contato da chapa no pilar)
    if pilar.get("tipo") == "tubo" and not bf:
        L = math.pi * d
        S = math.pi * d * d / 4
        fn = Nt / L + math.hypot(Mx, My) / S
        fv = 2 * V / L + abs(T) / (math.pi * d * d / 2)
    elif pilar.get("tipo") == "tubo":
        L = 2 * (d + bf)
        Ix = bf * d * d / 2 + d ** 3 / 6
        Iy = d * bf * bf / 2 + bf ** 3 / 6
        fn = Nt / L + abs(Mx) / (Ix / (d / 2)) + abs(My) / (Iy / (bf / 2))
        fv = V / (2 * min(d, bf)) + abs(T) / (2 * d * bf)
    else:
        hw = d - 2 * tf
        L = 2 * bf + 2 * (bf - tw) + 2 * hw
        Ix = 2 * bf * (d / 2) ** 2 + 2 * (bf - tw) * (d / 2 - tf) ** 2 + 2 * hw ** 3 / 12
        Iy = 4 * bf ** 3 / 12
        fn = Nt / L + abs(Mx) / (Ix / (d / 2)) + abs(My) / (Iy / (bf / 2))
        fv = V / (2 * hw) + abs(T) / (2 * bf * d)
    return math.hypot(fn, fv)


def alma_da_viga(viga: dict, C: float, ln: float, na_extremidade: bool, fy: float) -> dict:
    """NBR 8800:2024, 5.7.3 (escoamento local) e 5.7.4 (enrugamento) da alma da viga sob a força C (N) aplicada na mesa
    em ℓ_n (mm). na_extremidade: a força a menos de d (5.7.3) e de d/2 (5.7.4) da ponta da viga"""
    d, tw, tf = viga["d"], viga["tw"], viga["tf"]
    k = tf + viga.get("r", tw)
    Fy = 1.10 * ((2.5 if na_extremidade else 5.0) * k + ln) * fy * tw / GAMA_A1
    raiz = math.sqrt(E_ACO * fy * tf / tw)
    if not na_extremidade:
        Fe = 0.66 * tw * tw / GAMA_A1 * (1 + 3 * (ln / d) * (tw / tf) ** 1.5) * raiz
    elif ln / d <= 0.2:
        Fe = 0.33 * tw * tw / GAMA_A1 * (1 + 3 * (ln / d) * (tw / tf) ** 1.5) * raiz
    else:
        Fe = 0.33 * tw * tw / GAMA_A1 * (1 + (4 * ln / d - 0.2) * (tw / tf) ** 1.5) * raiz
    return {"k": k, "F_esc": Fy / 1e3, "F_enr": Fe / 1e3, "C": C / 1e3, "uso": C / min(Fy, Fe) if C > 0 else 0.0,
            "governa": "escoamento local da alma (5.7.3)" if Fy <= Fe else "enrugamento da alma (5.7.4)"}


def verificar(pilar: dict, viga: dict, combs: Sequence[dict], diametro: str, n: int, t_pilar: float, t_viga: float,
              viga_continua: bool = False, fub: float = 825.0, fy: float = 250.0, fu: float = 400.0,
              fy_viga: float = 345.0, viga_ao_longo: str = "x", fy_pilar: float = 345.0) -> dict:
    """a ligação com uma geometria em todas as combinações (N > 0 compressão; Mz no eixo forte do pilar e My no fraco,
    kN·m; V e T, concomitantes). viga_ao_longo: a viga corre na direção x (a altura da seção do pilar) ou y (a largura)"""
    db, df, emin = PARAFUSOS[diametro]
    Ab = math.pi * db * db / 4
    Ft_rd = 0.75 * Ab * fub / GAMA_A2
    Fv_rd = 0.45 * Ab * fub / GAMA_A2
    dx, dy = pilar["d"], (pilar.get("bf") or pilar["d"])
    perna0 = perna_minima(min(pilar.get("tw") or pilar.get("tf") or 6.0, t_pilar))
    c = max(35.0, 1.5 * db + perna0)                  # da face do pilar ao eixo do parafuso (chave e solda)
    gx, gy = dx + 2 * c, dy + 2 * c
    e = emin
    Bx, By = gx + 2 * e, gy + 2 * e
    pts = grupo(n, gx, gy)
    e_int = min(gx, gy) if n == 4 else min(gx, gy) / 2
    # o lado da viga: os parafusos fora da mesa (chapa soldada sob a mesa, em balanço da borda da mesa) ou através dela
    g_tr = gy if viga_ao_longo == "x" else gx                 # a distância entre as linhas de parafusos, de través
    B_long = Bx if viga_ao_longo == "x" else By               # o comprimento de contato ao longo da viga
    fora = g_tr / 2 - viga["bf"] / 2 >= 0.5 * df + 5.0
    b_viga = (g_tr / 2 - viga["bf"] / 2) if fora else (g_tr / 2 - viga["tw"] / 2)
    t_viga_ef = t_viga if fora else t_viga + viga["tf"]
    falhas, linhas = [], []
    pior = {"ft": 0.0, "fv": 0.0, "int": 0.0, "tp": 0.0, "tv": 0.0, "solda": 0.0, "alma": 0.0, "contato": 0.0}
    gov = {}
    for cb in combs:
        N, Mf, Mw, V, T = cb["N"] * 1e3, cb["Mz"] * 1e6, cb["My"] * 1e6, cb["V"] * 1e3, cb.get("T", 0.0) * 1e6
        # na chapa: o momento forte (vetor na largura y) traciona variando em x; o fraco (vetor em x) varia em y
        Mx, My = Mw, Mf
        Ft0, Fv = forcas_nos_parafusos(pts, N, Mx, My, V, T)
        rv = Fv / Fv_rd
        Ft_rd_red = Ft_rd * math.sqrt(max(1 - rv * rv, 0.0))     # o que sobra para a tração (6.3.3.4)
        ip = (Ft0 / Ft_rd) ** 2 + rv ** 2
        lp = alavanca(Ft0, Ft_rd_red, c, e, e, e_int, db, df, fu, t_pilar)
        lv = alavanca(Ft0, Ft_rd_red, b_viga, e, e, e_int, db, df, fu, t_viga_ef)
        # pressão de contato no furo (a chapa mais fina; ℓ_f até a borda)
        tmin = min(t_pilar, t_viga_ef)
        lf = e - df / 2
        Fc_rd = min(1.2 * lf * tmin * fu, 2.4 * db * tmin * fu) / GAMA_A2
        # solda do pilar na chapa
        fw = _solda_pilar(pilar, N, Mf, Mw, V, T)
        # a compressão que chega na alma da viga: N + a tração dos parafusos (equilíbrio da chapa); com momento o
        # contato fica de um lado da chapa (ℓ_n = B/2)
        Ft_tot = sum(max(-N / n + abs(Mx) * y / (sum(q * q for _p, q in pts) or 1) + abs(My) * x / (sum(p_ * p_ for p_, _q in pts) or 1), 0.0)
                     for x, y in pts)
        C = max(N, 0.0) + Ft_tot
        ln = B_long / 2 if (abs(Mx) + abs(My)) > 1e-6 else B_long
        av = alma_da_viga(viga, C, ln, not viga_continua, fy_viga)
        r = {"comb": cb.get("comb"), "sit": cb.get("sit"), "Ft0": Ft0 / 1e3, "Fv": Fv / 1e3, "interacao": ip,
             "t_pilar_min": lp["t_flexivel"], "t_viga_min": lv["t_flexivel"], "beta": lp["beta"], "solda_N_mm": fw,
             "contato": Fv / Fc_rd, "alma": av}
        linhas.append(r)
        for k_, v_ in (("ft", Ft0 / Ft_rd), ("fv", rv), ("int", ip), ("tp", lp["t_flexivel"]), ("tv", lv["t_flexivel"]),
                       ("solda", fw), ("alma", av["uso"]), ("contato", Fv / Fc_rd)):
            if v_ > pior[k_]:
                pior[k_] = v_
                gov[k_] = r
        if not lp["ok_parafuso"]:
            falhas.append("%s: F_t,0,Sd %.1f kN > F_t,Rd %.1f kN (β < 0, 6.3.5.2): trocar o parafuso" % (cb.get("comb"), Ft0 / 1e3, Ft_rd_red / 1e3))
    # o filete: a menor perna que resiste à maior força por comprimento (0,6·f_w·0,707a/γ_w2, Tabela 9)
    t_base = min(pilar.get("tw") or pilar.get("tf") or 99.0, pilar.get("tf") or 99.0) if pilar.get("tipo") != "tubo" else (pilar.get("tw") or pilar.get("tf"))
    perna = next((a for a in FILETES_MM if a >= perna0 and 0.6 * FW_E70 * 0.707 * a / GAMA_W2 >= pior["solda"]), None)
    if perna is None:
        falhas.append("o filete pilar–chapa precisa de mais que %.0f mm (%.0f N/mm): solda de penetração ou chapa de reforço" % (FILETES_MM[-1], pior["solda"]))
    elif t_base and pior["solda"] > 0.6 * fy_pilar * t_base / GAMA_A1 + 1e-6:
        # o metal-base junto ao filete (6.5): o escoamento por cisalhamento da parede/alma do pilar, por comprimento
        falhas.append("o metal-base do pilar não leva a força do filete (%.0f N/mm > 0,6·fy·t/γa1 = %.0f N/mm, 6.5): "
                      "parede/alma de %.1f mm fina demais — chapa de reforço ou pilar mais espesso"
                      % (pior["solda"], 0.6 * fy_pilar * t_base / GAMA_A1, t_base))
    for k_, rot in (("ft", "tração no parafuso"), ("fv", "cisalhamento no parafuso"), ("int", "tração + cisalhamento (6.3.3.4)"),
                    ("contato", "pressão de contato no furo")):
        if pior[k_] > 1.0 + 1e-9:
            falhas.append("%s: %.0f%% (%s)" % (rot, pior[k_] * 100, gov[k_]["comb"]))
    if pior["tp"] > t_pilar + 1e-6:
        falhas.append("chapa do pilar: t_mín %.1f mm > %.1f mm (alavanca, 6.3.5.4)" % (pior["tp"], t_pilar))
    if pior["tv"] > t_viga_ef + 1e-6:
        falhas.append("chapa da viga: t_mín %.1f mm > %.1f mm (alavanca, 6.3.5.4)" % (pior["tv"], t_viga_ef))
    enrijecedor = pior["alma"] > 1.0 + 1e-9
    peso = Bx * By * (t_pilar + t_viga) * 7.85e-6
    return {"ok": not falhas, "falhas": falhas, "diametro": diametro, "n": n, "db": db, "furo": df, "gx": gx, "gy": gy, "c": c,
            "e": e, "Bx": Bx, "By": By, "t_pilar": t_pilar, "t_viga": t_viga, "viga_ao_longo": viga_ao_longo, "parafusos_fora_da_mesa": fora, "b_viga": b_viga,
            "perna_solda": perna, "Ft_Rd": Ft_rd / 1e3, "Fv_Rd": Fv_rd / 1e3, "pior": pior,
            "governa": {k_: (v_.get("comb"), v_.get("sit")) for k_, v_ in gov.items()},
            "alma": gov.get("alma", {}).get("alma"), "enrijecedor_na_viga": enrijecedor,
            "peso_chapas_kg": peso, "combinacoes": linhas}


def ponta_de_viga(viga: dict, combs: Sequence[dict], diametro: str, n: int, t_chapa: float, Lp: float, g_tr: float,
                  fub: float = 825.0, fy: float = 250.0, fu: float = 400.0, fy_viga: float = 345.0) -> dict:
    """a ponta da viga emendada sobre o pilar: a chapa soldada sob a mesa inferior (comprimento Lp ao longo da viga, as
    linhas de parafusos a g_tr de través) parafusada na chapa do topo do pilar. Cada combinação: N > 0 comprimindo os
    parafusos, Mz o momento forte da viga (binário ao longo dela), My o de través (torção da viga), T a torção do grupo,
    V horizontal (kN, kN·m). Os mesmos critérios de `verificar`; a solda é a da mesa inferior na chapa (dois cordões ao
    longo da viga + o de través na ponta) e a alma da viga é verificada na extremidade"""
    db, df, emin = PARAFUSOS[diametro]
    Ab = math.pi * db * db / 4
    Ft_rd = 0.75 * Ab * fub / GAMA_A2
    Fv_rd = 0.45 * Ab * fub / GAMA_A2
    e = emin
    gl = Lp - 2 * e                                    # entre as linhas de parafusos ao longo da viga
    pts = [(-gl / 2, -g_tr / 2), (gl / 2, -g_tr / 2), (gl / 2, g_tr / 2), (-gl / 2, g_tr / 2)]
    if n == 6:
        pts += [(0.0, -g_tr / 2), (0.0, g_tr / 2)]
    fora = g_tr / 2 - viga["bf"] / 2 >= 0.5 * df + 5.0
    b = (g_tr / 2 - viga["bf"] / 2) if fora else (g_tr / 2 - viga["tw"] / 2)
    t_ef = t_chapa if fora else t_chapa + viga["tf"]
    e_int = gl if n == 4 else gl / 2
    pior = {"ft": 0.0, "fv": 0.0, "int": 0.0, "t": 0.0, "solda": 0.0, "alma": 0.0, "contato": 0.0}
    gov, falhas = {}, []
    bf = viga["bf"]
    Lw = 2 * Lp + bf
    Iw = 2 * Lp ** 3 / 12 + bf * (Lp / 2) ** 2           # a linha de solda em torno do eixo de través (por mm de garganta)
    for cb in combs:
        N, Mf, Mt, V, T = cb["N"] * 1e3, cb["Mz"] * 1e6, cb["My"] * 1e6, cb["V"] * 1e3, cb.get("T", 0.0) * 1e6
        Ft0, Fv = forcas_nos_parafusos(pts, N, Mt, Mf, V, T)
        rv = Fv / Fv_rd
        Ft_rd_red = Ft_rd * math.sqrt(max(1 - rv * rv, 0.0))
        ip = (Ft0 / Ft_rd) ** 2 + rv ** 2
        lv = alavanca(Ft0, Ft_rd_red, b, e, e, e_int, db, df, fu, t_ef)
        Fc_rd = min(1.2 * (e - df / 2) * t_ef * fu, 2.4 * db * t_ef * fu) / GAMA_A2
        fw = math.hypot(max(-N, 0.0) / Lw + abs(Mf) / (Iw / (Lp / 2)) + abs(Mt) / (bf * Lp), V / Lw + abs(T) / (Lp * bf))
        sx = sum(x * x for x, _y in pts) or 1.0
        Ft_tot = sum(max(-N / len(pts) + abs(Mf) * x / sx, 0.0) for x, _y in pts)
        C = max(N, 0.0) + Ft_tot
        av = alma_da_viga(viga, C, Lp / 2, True, fy_viga)
        r = {"comb": cb.get("comb"), "sit": cb.get("sit"), "Ft0": Ft0 / 1e3, "Fv": Fv / 1e3, "alma": av}
        for k_, v_ in (("ft", Ft0 / Ft_rd), ("fv", rv), ("int", ip), ("t", lv["t_flexivel"]), ("solda", fw),
                       ("alma", av["uso"]), ("contato", Fv / Fc_rd)):
            if v_ > pior[k_]:
                pior[k_] = v_
                gov[k_] = r
        if not lv["ok_parafuso"]:
            falhas.append("%s: F_t,0,Sd %.1f kN > F_t,Rd %.1f kN (β < 0): trocar o parafuso" % (cb.get("comb"), Ft0 / 1e3, Ft_rd_red / 1e3))
    perna = next((a for a in FILETES_MM if a >= perna_minima(min(viga["tf"], t_chapa)) and 0.6 * FW_E70 * 0.707 * a / GAMA_W2 >= pior["solda"]), None)
    if perna is None:
        falhas.append("o filete mesa–chapa precisa de mais que %.0f mm" % FILETES_MM[-1])
    for k_, rot in (("ft", "tração no parafuso"), ("fv", "cisalhamento no parafuso"), ("int", "tração + cisalhamento"), ("contato", "pressão de contato")):
        if pior[k_] > 1.0 + 1e-9:
            falhas.append("%s: %.0f%% (%s)" % (rot, pior[k_] * 100, gov[k_]["comb"]))
    if pior["t"] > t_ef + 1e-6:
        falhas.append("chapa da viga: t_mín %.1f mm > %.1f mm (alavanca)" % (pior["t"], t_ef))
    return {"ok": not falhas, "falhas": falhas, "diametro": diametro, "n": n, "Lp": Lp, "g_tr": g_tr, "gl": gl, "e": e,
            "t_chapa": t_chapa, "perna_solda": perna, "pior": pior, "governa": {k_: (v_.get("comb"), v_.get("sit")) for k_, v_ in gov.items()},
            "alma": gov.get("alma", {}).get("alma"), "enrijecedor_na_viga": pior["alma"] > 1.0 + 1e-9, "parafusos_fora_da_mesa": fora,
            "peso_chapa_kg": Lp * (g_tr + 2 * e) * t_chapa * 7.85e-6}


def dimensionar_ponta(viga: dict, combs: Sequence[dict], g_tr: float, **kw) -> dict:
    """a ponta de viga mais leve que passa: diâmetro, 4 ou 6 parafusos, comprimento da chapa (150 a 400 mm) e espessura"""
    melhor, menos_ruim = None, None
    for diam in PARAFUSOS:
        for n in (4, 6):
            for Lp in (150.0, 200.0, 250.0, 300.0, 400.0):
                if Lp - 2 * PARAFUSOS[diam][2] < (2 if n == 6 else 1) * 3 * PARAFUSOS[diam][0]:
                    continue
                base = ponta_de_viga(viga, combs, diam, n, CHAPAS_MM[-1], Lp, g_tr, **kw)
                if not base["ok"]:
                    if menos_ruim is None or len(base["falhas"]) < len(menos_ruim["falhas"]):
                        menos_ruim = base
                    continue
                t = next((x for x in CHAPAS_MM if x >= max(base["pior"]["t"] - (0.0 if base["parafusos_fora_da_mesa"] else viga["tf"]), 9.5) - 1e-6), None)
                cand = ponta_de_viga(viga, combs, diam, n, t or CHAPAS_MM[-1], Lp, g_tr, **kw)
                custo = cand["peso_chapa_kg"] + n * (cand_db := PARAFUSOS[diam][0]) ** 2 / 19.05 ** 2 * 0.6
                cand["custo"] = custo
                if cand["ok"] and (melhor is None or custo < melhor["custo"]):
                    melhor = cand
    return melhor or menos_ruim


def dimensionar(pilar: dict, viga: dict, combs: Sequence[dict], viga_continua: bool = False, **kw) -> dict:
    """a ligação mais leve que passa: os diâmetros de 5/8" a 1", 4 ou 8 parafusos e as chapas comerciais; o enrijecedor
    da alma da viga é apontado à parte (não impede a solução)"""
    melhor, menos_ruim = None, None
    for diam in PARAFUSOS:
        for n in (4, 8):
            base = verificar(pilar, viga, combs, diam, n, CHAPAS_MM[-1], CHAPAS_MM[-1], viga_continua, **kw)
            if any("parafuso" in f or "6.3.3.4" in f or "contato" in f for f in base["falhas"]):
                cand = base
            else:
                tp = next((t for t in CHAPAS_MM if t >= base["pior"]["tp"] - 1e-6), None)
                tv_ef = base["pior"]["tv"] - (0.0 if base["parafusos_fora_da_mesa"] else viga["tf"])
                tv = next((t for t in CHAPAS_MM if t >= max(tv_ef, 9.5) - 1e-6), None)
                cand = verificar(pilar, viga, combs, diam, n, tp or CHAPAS_MM[-1], tv or CHAPAS_MM[-1], viga_continua, **kw)
            custo = cand["peso_chapas_kg"] + n * (cand["db"] / 19.05) ** 2 * 0.6
            cand["custo"] = custo
            if cand["ok"] and (melhor is None or custo < melhor["custo"]):
                melhor = cand
            elif not cand["ok"] and (menos_ruim is None or len(cand["falhas"]) < len(menos_ruim["falhas"])):
                menos_ruim = cand
    return melhor or menos_ruim


__all__ = ["verificar", "dimensionar", "forcas_nos_parafusos", "alavanca", "alma_da_viga"]
