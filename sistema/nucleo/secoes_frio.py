# -*- coding: utf-8 -*-
"""Propriedades de perfis formados a frio que não são U nem Ue: **Z enrijecido a 90°**
(Ze / Z90), **Z enrijecido a 45°** (Z45) e **cartola** (Cr).

Mesmo método de `nbr14762.propriedades_ue` (NBR 14762, Anexo A): a parede é trocada pela
linha média de espessura t, com os cantos arredondados (raio interno r = t, raio da linha
média r + t/2); área, centroide e inércias por integração da polilinha; centro de torção e
Cw pela coordenada setorial (Vlasov); J = Σ L·t³/3. O Z é simétrico em relação a um ponto:
o centro de torção é o centroide, e os eixos principais saem de Ix, Iy e Ixy (I1, I2 e o
ângulo α). Dimensões de entrada em mm (externas, como na designação NBR 6355); saída em cm.
"""
import math
from typing import List, Sequence, Tuple

from .base import ErroDeDados
from . import nbr14762

RHO = 7850.0     # kg/m³

Ponto = Tuple[float, float]


def _arredondar(pts: Sequence[Ponto], rm: float, n: int = 6) -> List[Ponto]:
    """Troca cada vértice interno da polilinha (cantos vivos na linha média) por um arco de
    raio `rm` tangente aos dois trechos."""
    fora = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, v, b = pts[i - 1], pts[i], pts[i + 1]
        u1 = (v[0] - a[0], v[1] - a[1])
        u2 = (b[0] - v[0], b[1] - v[1])
        l1, l2 = math.hypot(*u1), math.hypot(*u2)
        u1 = (u1[0] / l1, u1[1] / l1)
        u2 = (u2[0] / l2, u2[1] / l2)
        cruz = u1[0] * u2[1] - u1[1] * u2[0]
        ang = math.atan2(cruz, u1[0] * u2[0] + u1[1] * u2[1])     # giro com sinal
        if abs(ang) < 1e-6:
            fora.append(v)
            continue
        tg = rm * math.tan(abs(ang) / 2)
        tg = min(tg, 0.49 * l1, 0.49 * l2)
        r_ = tg / math.tan(abs(ang) / 2)
        p1 = (v[0] - u1[0] * tg, v[1] - u1[1] * tg)
        s = 1.0 if ang > 0 else -1.0
        c = (p1[0] - u1[1] * r_ * s, p1[1] + u1[0] * r_ * s)          # centro à esquerda (giro +) ou direita
        a0 = math.atan2(p1[1] - c[1], p1[0] - c[0])
        for k in range(n + 1):
            t = a0 + ang * k / n
            fora.append((c[0] + r_ * math.cos(t), c[1] + r_ * math.sin(t)))
    fora.append(pts[-1])
    return fora


def _linha_ze(h, b, d, t):
    """Z 90°: mesa de cima para +x com enrijecedor para baixo; de baixo para −x com
    enrijecedor para cima. Linha média com a alma em x = 0."""
    ym = (h - t) / 2.0
    xm = b - t              # da linha média da alma à linha média do enrijecedor
    dm = d - t / 2.0
    return [(-xm, -ym + dm), (-xm, -ym), (0.0, -ym), (0.0, ym), (xm, ym), (xm, ym - dm)]


def _linha_z45(h, b, d, t):
    """Z com enrijecedor a 45°: a aba dobra 45° para fora e para baixo (em cima) — o giro na dobra é de 45°, não de 135°."""
    ym = (h - t) / 2.0
    xm = b - t / 2.0 - t / 2.0 * math.tan(math.radians(22.5))
    dm = d - t / 2.0 * math.tan(math.radians(22.5))
    c = math.sqrt(0.5)
    return [(-xm - dm * c, -ym + dm * c), (-xm, -ym), (0.0, -ym), (0.0, ym), (xm, ym), (xm + dm * c, ym - dm * c)]


def _linha_cr(h, b, d, t):
    """Cartola (chapéu): mesa de cima de largura externa b, almas de altura h e abas de
    apoio D para fora, embaixo."""
    xa = b / 2.0 - t / 2.0
    xo = xa + d - t / 2.0
    ym = h - t
    return [(-xo, 0.0), (-xa, 0.0), (-xa, ym), (xa, ym), (xa, 0.0), (xo, 0.0)]


LINHAS = {"Ze": _linha_ze, "Z45": _linha_z45, "Cr": _linha_cr}


def propriedades(familia: str, h: float, b: float, d: float, t: float, r: float = None) -> dict:
    """Propriedades (cm) de um Ze, Z45 ou Cr. Chaves: A, massa, xc, yc, Ix, Iy, Ixy, I1, I2,
    alfa (graus), Wx, Wy, rx, ry, rmin, J, Cw, x0, y0, r0."""
    if familia not in LINHAS:
        raise ErroDeDados("família %s sem cálculo de seção" % familia)
    if min(h, b, d, t) <= 0:
        raise ErroDeDados("dimensões do perfil devem ser positivas")
    r = t if r is None else r
    pts = LINHAS[familia](h, b, d, t)
    rm = r + t / 2.0
    pts = _arredondar([(x / 10.0, y / 10.0) for x, y in pts], rm / 10.0)
    tc = t / 10.0
    p = nbr14762._props_linha(pts, tc)
    Ix, Iy, Ixy = p["Ix"], p["Iy"], p.get("Ixy", 0.0)
    if familia in ("Ze", "Z45"):
        # simetria em relação a um ponto: centro de torção no centroide; Cw com polo nele
        p["xs"], p["ys"], p["x0"], p["y0"] = p["xc"], p["yc"], 0.0, 0.0
        om = [0.0]
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            om.append(om[-1] + (x1 - p["xc"]) * (y2 - y1) - (y1 - p["yc"]) * (x2 - x1))
        S = S2 = 0.0
        for i in range(len(pts) - 1):
            li = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            S += li * (om[i] + om[i + 1]) / 2.0
            S2 += li * (om[i] ** 2 + om[i] * om[i + 1] + om[i + 1] ** 2) / 3.0
        p["Cw"] = S2 * tc - (S * tc) ** 2 / p["A"]
    med = (Ix + Iy) / 2.0
    raio = math.sqrt(((Ix - Iy) / 2.0) ** 2 + Ixy ** 2)
    I1, I2 = med + raio, med - raio
    alfa = 0.5 * math.degrees(math.atan2(-2 * Ixy, Ix - Iy))
    xs_ = [q[0] for q in pts]
    ys_ = [q[1] for q in pts]
    c_x = max(max(ys_) - p["yc"], p["yc"] - min(ys_)) + tc / 2
    c_y = max(max(xs_) - p["xc"], p["xc"] - min(xs_)) + tc / 2
    A = p["A"]
    x0, y0 = p.get("x0", 0.0), p.get("y0", 0.0)
    return {"A": A, "massa": A * RHO * 1e-4, "xc": p["xc"], "yc": p["yc"],
            "Ix": Ix, "Iy": Iy, "Ixy": Ixy, "I1": I1, "I2": I2, "alfa": alfa,
            "Wx": Ix / c_x, "Wy": Iy / c_y, "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A),
            "rmin": math.sqrt(max(I2, 1e-12) / A), "J": p["J"], "Cw": p["Cw"], "x0": x0, "y0": y0,
            "r0": math.sqrt((Ix + Iy) / A + x0 ** 2 + y0 ** 2)}
