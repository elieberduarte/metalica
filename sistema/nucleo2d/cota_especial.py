"""As cotas angular, de raio, de diâmetro e ordenada (pedido do usuário, 23/10, na lista das ferramentas que faltam).

Espelho de web/cad/nucleo/cota_especial.js: a mesma conta dá o que se desenha — linhas, arcos, pontas e o número — na
tela, no PDF (desenho._cota_especial_dxf) e no DXF (dxf_cad). testes/test_cota_especial.py roda as duas e compara.

A entidade (desenho.CotaEspecial): modo (angular | raio | diametro | ordenada), centro (o vértice do ângulo, o centro do
círculo, a origem da ordenada), p1, p2, posicao (por onde passa o arco do ângulo / onde fica o número), eixo (x | y),
texto (vazio = a medida), altura, casas, escala, fator, terminador, folga."""
import math
from typing import Optional

RAD = math.pi / 180.0


def _n360(g: float) -> float:
    return ((g % 360.0) + 360.0) % 360.0


def _ang(a, b) -> float:
    return _n360(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))


def _pol(c, g, r):
    return (c[0] + r * math.cos(g * RAD), c[1] + r * math.sin(g * RAD))


def _dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def setor_angular(c):
    """(início, varredura) em graus: o setor de p1 a p2 (anti-horário) que contém a posição, ou o outro"""
    a1, a2, ap = _ang(c.centro, c.p1), _ang(c.centro, c.p2), _ang(c.centro, c.posicao)
    s12 = _n360(a2 - a1)
    return (a1, s12) if _n360(ap - a1) <= s12 else (a2, 360.0 - s12)


def _js_fixo(v: float, casas: int) -> str:
    """como o toFixed do JavaScript (meio para cima), com vírgula"""
    return ("%.*f" % (casas, v)).replace(".", ",")


def medida(c) -> str:
    """o número escrito (sem o texto posto à mão)"""
    from nucleo2d.desenho import formatar_mm
    e = float(getattr(c, "escala", None) or 1.0)
    casas = getattr(c, "casas", None)
    if c.modo == "angular":
        v = setor_angular(c)[1]
        if casas is not None and casas != "":
            s = _js_fixo(v, int(casas))
        elif abs(v - round(v)) < 0.05:
            s = "%d" % round(v)
        else:
            s = _js_fixo(v, 1)
        return s + "°"
    if c.modo == "raio":
        return "R" + formatar_mm(_dist(c.centro, c.p1) * e, casas)
    if c.modo == "diametro":
        return "Ø" + formatar_mm(2 * _dist(c.centro, c.p1) * e, casas)
    i = 1 if getattr(c, "eixo", "x") == "y" else 0
    return formatar_mm(abs(c.p1[i] - c.centro[i]) * e, casas)


def _legivel(g: float):
    g = _n360(g)
    if 90.0 < g <= 270.0:
        return g - 180.0, True
    return (g - 360.0 if g > 270.0 else g), False


def primitivas(c, k: float = 1.0, estilo: Optional[dict] = None) -> dict:
    """{linhas: [(a, b)], arcos: [{centro, raio, inicio, fim}], pontas: [{p, ang, tam, tipo}], textos: [{pos, txt, h, ang,
    alinhamento}]}, em mm do desenho; `k` é a escala do desenho (mm de papel → mm)"""
    from nucleo2d.desenho import folga_da_cota
    f = float(getattr(c, "fator", None) or 1.0)
    h = float(getattr(c, "altura", None) or 2.5) * k * f
    seta, ext = 2.5 * k * f, 2.0 * k * f
    fol = folga_da_cota(c, estilo) * k * f
    termo = getattr(c, "terminador", None) or (estilo or {}).get("terminador") or "traco"
    txt = str(c.texto) if c.texto not in (None, "") else medida(c)
    larg = max(h, len(txt) * h * 0.62)
    out = {"linhas": [], "arcos": [], "pontas": [], "textos": []}
    C = c.centro
    if c.modo == "angular":
        ini, varre = setor_angular(c)
        fim = ini + varre
        r = max(_dist(C, c.posicao), 3 * seta)
        for p in (c.p1, c.p2):
            g, d = _ang(C, p), _dist(C, p)
            if d < r - 1e-9:
                out["linhas"].append((_pol(C, g, d + fol), _pol(C, g, r + ext)))
        out["arcos"].append({"centro": tuple(C), "raio": r, "inicio": _n360(ini), "fim": _n360(fim)})
        out["pontas"] += [{"p": _pol(C, ini, r), "ang": ini - 90.0, "tam": seta, "tipo": termo},
                          {"p": _pol(C, fim, r), "ang": fim + 90.0, "tam": seta, "tipo": termo}]
        meio = ini + varre / 2.0
        g, virou = _legivel(meio - 90.0)
        out["textos"].append({"pos": _pol(C, meio, r + fol + (h if virou else 0.0)), "txt": txt, "h": h, "ang": g, "alinhamento": "centro"})
        return out
    if c.modo in ("raio", "diametro"):
        R, u, dP = _dist(C, c.p1), _ang(C, c.posicao), _dist(C, c.posicao)
        P1, P2 = _pol(C, u, R), _pol(C, u + 180.0, R)
        ponta = "seta" if termo == "traco" else termo
        ini = tuple(C) if c.modo == "raio" else P2
        if dP > R + 1e-9:
            d_ = 1.0 if c.posicao[0] >= C[0] else -1.0
            out["linhas"] += [(P1 if c.modo == "raio" else P2, tuple(c.posicao)),
                              (tuple(c.posicao), (c.posicao[0] + d_ * (larg + 2 * fol), c.posicao[1]))]
            out["pontas"].append({"p": P1, "ang": u + 180.0, "tam": seta, "tipo": ponta})
            if c.modo == "diametro":
                out["pontas"].append({"p": P2, "ang": u, "tam": seta, "tipo": ponta})
            out["textos"].append({"pos": (c.posicao[0] + d_ * (fol + larg / 2.0), c.posicao[1] + fol), "txt": txt, "h": h, "ang": 0.0,
                                  "alinhamento": "centro"})
        else:
            out["linhas"].append((ini, P1))
            out["pontas"].append({"p": P1, "ang": u, "tam": seta, "tipo": ponta})
            if c.modo == "diametro":
                out["pontas"].append({"p": P2, "ang": u + 180.0, "tam": seta, "tipo": ponta})
            m = ((ini[0] + P1[0]) / 2.0, (ini[1] + P1[1]) / 2.0)
            g, _v = _legivel(u)
            out["textos"].append({"pos": _pol(m, g + 90.0, fol), "txt": txt, "h": h, "ang": g, "alinhamento": "centro"})
        return out
    F, P = c.p1, c.posicao
    vert = getattr(c, "eixo", "x") != "y"
    a, b = (1, 0) if vert else (0, 1)
    s = 1.0 if (P[a] - F[a]) >= 0 else -1.0
    J = 2 * seta

    def q(va, vb):
        return (vb, va) if vert else (va, vb)
    inicio = q(F[a] + s * fol, F[b])
    if abs(P[b] - F[b]) < 1e-6 or abs(P[a] - F[a]) < 3 * J:
        out["linhas"].append((inicio, q(P[a], F[b])))
    else:
        out["linhas"] += [(inicio, q(P[a] - s * 2 * J, F[b])), (q(P[a] - s * 2 * J, F[b]), q(P[a] - s * J, P[b])),
                          (q(P[a] - s * J, P[b]), q(P[a], P[b]))]
    lado = F[b] if abs(P[b] - F[b]) < 1e-6 else P[b]
    if vert:
        out["textos"].append({"pos": (lado + h / 2.0, P[a] + s * fol), "txt": txt, "h": h, "ang": 90.0,
                              "alinhamento": "esquerda" if s > 0 else "direita"})
    else:
        out["textos"].append({"pos": (P[a] + s * fol, lado - h / 2.0), "txt": txt, "h": h, "ang": 0.0,
                              "alinhamento": "esquerda" if s > 0 else "direita"})
    return out


def pontos(c, k: float = 1.0, estilo: Optional[dict] = None):
    """os pontos que dão a caixa da cota"""
    pr = primitivas(c, k, estilo)
    pts = []
    for a, b in pr["linhas"]:
        pts += [a, b]
    for ar in pr["arcos"]:
        v = _n360(ar["fim"] - ar["inicio"]) or 360.0
        pts += [_pol(ar["centro"], ar["inicio"] + v * i / 12.0, ar["raio"]) for i in range(13)]
    for t in pr["textos"]:
        w = max(t["h"], len(str(t["txt"])) * t["h"] * 0.65)
        x = -w / 2 if t["alinhamento"] == "centro" else (-w if t["alinhamento"] == "direita" else 0.0)
        ca, sa = math.cos(t["ang"] * RAD), math.sin(t["ang"] * RAD)
        pts += [(t["pos"][0] + u * ca - v_ * sa, t["pos"][1] + u * sa + v_ * ca) for u, v_ in ((x, 0), (x + w, 0), (x + w, t["h"]), (x, t["h"]))]
    return pts
