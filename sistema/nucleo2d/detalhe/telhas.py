# -*- coding: utf-8 -*-
"""Telhas multi-dobra (calandradas em facetas) do modelo importado.

O TecnoMETAL modela a telha que dobra do telhado para a parede (o beiral arredondado)
como várias peças: o trecho reto da cobertura, uma fileira de facetas curtas (110 mm)
girando alguns graus cada uma e o trecho reto da parede, todas com a mesma marca de
conjunto. Na fábrica e na compra é **uma telha só**: a multi-dobra, pedida pelo perfil —
os dois trechos retos (entre os pontos de tangência), o raio e o ângulo da dobra — e pelo
comprimento desenvolvido, externo e interno (o raio externo é o interno mais a altura da
onda). Aqui essas peças são reconhecidas por instância do conjunto e medidas no plano do
perfil (perpendicular à largura da telha).

`multidobras(pecas)` devolve as telhas multi-dobra do modelo e as posições que elas
consomem (as facetas e os trechos retos não saem mais como telhas recortadas).
"""
import collections
import math
from typing import Dict, List, Optional, Sequence

from saida.detalhamento import _autovetores, _eh_telha, RHO_ACO, _ordem_natural
from nucleo2d.detalhe.base import _marcas, _dot, _sub, _norm, _cruz, arredondar_telha

#: Peça mais curta que isto (mm) na fileira é faceta da dobra; a reta é bem mais longa.
FACETA_MAX = 400.0

#: Cobrimento da multi-dobra (regra da fábrica): ela passa 150 mm além da primeira terça,
#: e a telha seguinte começa 150 mm antes dela — transpasse de 300 mm + a largura da terça.
COBRIMENTO_TERCA = 150.0

#: Saia (regra da fábrica): a telha de fachada e a reta da parede da multi-dobra descem 150 mm
#: abaixo da última longarina.
SAIA_TELHA = 150.0


def _medidas(e):
    """Centro, eixos principais e extensões (maior → menor) da malha."""
    c, pca = _autovetores(e.vertices)
    ext = []
    for ax in pca:
        t = [_dot(_sub(p, c), ax) for p in e.vertices]
        ext.append(max(t) - min(t))
    return c, [tuple(a) for a in pca], ext


def _posicao(e) -> str:
    return str(_marcas(e).get("posicao") or e.nome or e.id)


def _analisar_instancia(inst, barras: Sequence = ()) -> Optional[dict]:
    """Perfil de uma instância (lista de sólidos) ou None se não é multi-dobra."""
    if len(inst) < 4:
        return None
    med = [(e,) + _medidas(e) for e in inst]
    # largura da telha: o eixo com a maior extensão comum a todas as peças (1031 na TP40)
    e0, c0, eixos0, ext0 = max(med, key=lambda m: m[3][0])
    largura_eixo = None
    for i, ax in enumerate(eixos0):
        if all(any(abs(_dot(ax, a)) > 0.95 and abs(x - ext0[i]) < 0.15 * ext0[i] + 5 for a, x in zip(m[2], m[3])) for m in med):
            if ext0[i] > 300 and (largura_eixo is None or ext0[i] > largura_eixo[1]):
                largura_eixo = (ax, ext0[i])
    if largura_eixo is None:
        return None
    w = _norm(largura_eixo[0])
    z = (0.0, 0.0, 1.0)
    bz = _sub(z, tuple(v * _dot(z, w) for v in w))
    b = _norm(bz) if _dot(bz, bz) > 1e-6 else _norm(_cruz(w, (1.0, 0.0, 0.0)))
    a = _norm(_cruz(b, w))
    segs = []
    altura_onda = []
    for e, c, eixos, ext in med:
        # comprimento: o maior eixo que não é a largura; espessura (altura da onda): o menor
        outros = [(ax, x) for ax, x in zip(eixos, ext) if abs(_dot(ax, w)) < 0.9]
        if len(outros) < 2:
            return None
        (ax_l, comp), (_, alt) = sorted(outros, key=lambda t: -t[1])[:2]
        altura_onda.append(alt)
        c2 = (_dot(c, a), _dot(c, b))
        d2 = (_dot(ax_l, a), _dot(ax_l, b))
        n = math.hypot(*d2) or 1.0
        d2 = (d2[0] / n, d2[1] / n)
        segs.append({"e": e, "c": c2, "d": d2, "L": comp})
    # encadeia: começa pela peça com a ponta mais longe de todas as outras
    def pontas(s):
        return [(s["c"][0] - s["d"][0] * s["L"] / 2, s["c"][1] - s["d"][1] * s["L"] / 2),
                (s["c"][0] + s["d"][0] * s["L"] / 2, s["c"][1] + s["d"][1] * s["L"] / 2)]
    for s in segs:
        s["p"] = pontas(s)

    def dist_ponta(p, outros):
        return min(math.dist(p, q) for o in outros for q in o["p"]) if outros else 0.0
    inicio, ponta_livre = None, None
    for s in segs:
        outros = [o for o in segs if o is not s]
        for k in (0, 1):
            d = dist_ponta(s["p"][k], outros)
            if inicio is None or d > ponta_livre[0]:
                inicio, ponta_livre = s, (d, k)
    cadeia = [inicio]
    if ponta_livre[1] == 1:           # a ponta livre vira o começo: inverte a peça
        inicio["d"] = (-inicio["d"][0], -inicio["d"][1]); inicio["p"] = inicio["p"][::-1]
    restantes = [s for s in segs if s is not inicio]
    while restantes:
        fim = cadeia[-1]["p"][1]
        prox, k, dm = None, 0, float("inf")
        for s in restantes:
            for kk in (0, 1):
                d = math.dist(fim, s["p"][kk])
                if d < dm:
                    prox, k, dm = s, kk, d
        if dm > 150.0:                # a fileira não é contínua
            return None
        if k == 1:
            prox["d"] = (-prox["d"][0], -prox["d"][1]); prox["p"] = prox["p"][::-1]
        cadeia.append(prox)
        restantes.remove(prox)
    reta1, reta2, meio = cadeia[0], cadeia[-1], cadeia[1:-1]
    if len(meio) < 3 or any(s["L"] > FACETA_MAX for s in meio) or min(reta1["L"], reta2["L"]) < 1.5 * max(s["L"] for s in meio):
        return None
    ang = lambda d: math.atan2(d[1], d[0])      # noqa: E731
    theta = ang(reta2["d"]) - ang(reta1["d"])
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    if abs(theta) < math.radians(10):
        return None
    arco = sum(s["L"] for s in meio)
    R = arco / abs(theta)
    # tangência: interseção das retas, recuada de R·tan(θ/2)
    p1, d1 = reta1["p"][0], reta1["d"]
    p2, d2 = reta2["p"][1], reta2["d"]
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-9:
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    I = (p1[0] + d1[0] * t, p1[1] + d1[1] * t)
    T = R * math.tan(abs(theta) / 2)
    L1 = math.dist(p1, I) - T
    L2 = math.dist(p2, I) - T
    if L1 <= 0 or L2 <= 0:
        return None
    # cobrimento: a reta da cobertura (a mais deitada) termina 150 mm depois da primeira
    # terça; o que sobra do modelo vira a telha complementar, que começa 150 mm antes dela
    cobrimento = None
    saia = None
    desenv_modelo = L1 + L2
    if barras:
        cob = 1 if abs(d1[1]) <= abs(d2[1]) else 2
        ponta, Lc = (p1, L1) if cob == 1 else (p2, L2)
        Tt = (I[0] - d1[0] * T, I[1] - d1[1] * T) if cob == 1 else (I[0] + d2[0] * T, I[1] + d2[1] * T)
        n_ = math.dist(ponta, Tt) or 1.0
        dirc = ((ponta[0] - Tt[0]) / n_, (ponta[1] - Tt[1]) / n_)
        nrm = (-dirc[1], dirc[0])
        wc = sum(_dot(m[1], w) for m in med) / len(med)
        melhor = None
        for e, c, eixos, ext in barras:
            if abs(_dot(eixos[0], w)) < 0.95 or abs(_dot(c, w) - wc) > ext[0] / 2:
                continue
            pts = [(_dot(q, a), _dot(q, b)) for q in e.vertices]
            ss = [(q[0] - Tt[0]) * dirc[0] + (q[1] - Tt[1]) * dirc[1] for q in pts]
            dd = [abs((q[0] - Tt[0]) * nrm[0] + (q[1] - Tt[1]) * nrm[1]) for q in pts]
            if min(ss) < 0 or max(ss) > Lc or min(dd) > 300.0:
                continue
            if melhor is None or min(ss) < melhor[0]:
                melhor = (min(ss), max(ss), str(_marcas(e).get("perfil") or e.nome or ""))
        if melhor and melhor[1] + COBRIMENTO_TERCA < Lc - 100.0:
            novo = melhor[1] + COBRIMENTO_TERCA
            cobrimento = {"terca": melhor[2], "terca_ini": round(melhor[0], 1), "terca_fim": round(melhor[1], 1),
                          "reta_modelo": round(Lc, 1), "transpasse": round(melhor[1] - melhor[0] + 2 * COBRIMENTO_TERCA, 1),
                          "resto": round(Lc - (melhor[0] - COBRIMENTO_TERCA), 1), "reta": "cobertura",
                          "reta_nova": round(novo, 1)}
            novo_p = (Tt[0] + dirc[0] * novo, Tt[1] + dirc[1] * novo)
            if cob == 1:
                L1, p1 = novo, novo_p
            else:
                L2, p2 = novo, novo_p
        # saia: a reta da parede desce 150 mm abaixo da última longarina
        par = 2 if cob == 1 else 1
        ponta_p, Lp = (p2, L2) if par == 2 else (p1, L1)
        Tp = (I[0] + d2[0] * T, I[1] + d2[1] * T) if par == 2 else (I[0] - d1[0] * T, I[1] - d1[1] * T)
        n_ = math.dist(ponta_p, Tp) or 1.0
        dirp = ((ponta_p[0] - Tp[0]) / n_, (ponta_p[1] - Tp[1]) / n_)
        nrp = (-dirp[1], dirp[0])
        ultimo = None
        for e, c, eixos, ext in barras:
            if abs(_dot(eixos[0], w)) < 0.95 or abs(_dot(c, w) - wc) > ext[0] / 2:
                continue
            pts = [(_dot(q, a), _dot(q, b)) for q in e.vertices]
            ss = [(q[0] - Tp[0]) * dirp[0] + (q[1] - Tp[1]) * dirp[1] for q in pts]
            dd = [abs((q[0] - Tp[0]) * nrp[0] + (q[1] - Tp[1]) * nrp[1]) for q in pts]
            if min(ss) < 0 or min(ss) > Lp + 2000.0 or min(dd) > 300.0:
                continue
            if ultimo is None or max(ss) > ultimo[0]:
                ultimo = (max(ss), str(_marcas(e).get("perfil") or e.nome or ""))
        if ultimo:
            novo = ultimo[0] + SAIA_TELHA
            saia = {"longarina": ultimo[1], "reta_modelo": round(Lp, 1), "reta_nova": round(novo, 1)}
            novo_p = (Tp[0] + dirp[0] * novo, Tp[1] + dirp[1] * novo)
            if par == 2:
                L2, p2 = novo, novo_p
            else:
                L1, p1 = novo, novo_p
    # retas arredondadas para cima (regra da fábrica: sobra nas pontas livres)
    t1_ = (I[0] - d1[0] * T, I[1] - d1[1] * T)
    t2_ = (I[0] + d2[0] * T, I[1] + d2[1] * T)
    L1, L2 = arredondar_telha(L1), arredondar_telha(L2)
    p1 = (t1_[0] - d1[0] * L1, t1_[1] - d1[1] * L1)
    p2 = (t2_[0] + d2[0] * L2, t2_[1] + d2[1] * L2)
    if cobrimento:
        cobrimento["resto"] = arredondar_telha(cobrimento["resto"])
    apoios = _apoios_no_perfil(barras, med, w, a, b, p1, t1_, t2_, p2, R, 1 if theta > 0 else -1, d1) if barras else []
    h = sorted(altura_onda)[len(altura_onda) // 2]
    R_int, R_ext = R - h / 2, R + h / 2
    peso = sum(_volume(e) for e in inst) * RHO_ACO
    arco_mid = R * abs(theta)
    peso_mm = peso / max(desenv_modelo + arco_mid, 1.0)      # kg por mm de telha desenvolvida
    peso = peso_mm * (L1 + L2 + arco_mid)
    if cobrimento:
        cobrimento["peso"] = round(peso_mm * cobrimento["resto"], 3)
    e_longa = reta2["e"] if reta2["L"] >= reta1["L"] else reta1["e"]
    m0 = _marcas(e_longa)
    from nucleo2d.detalhe.base import _material
    return {"reta1": round(L1, 1), "reta2": round(L2, 1), "raio": round(R, 1), "raio_int": round(R_int, 1),
            "raio_ext": round(R_ext, 1), "angulo": round(math.degrees(abs(theta)), 2), "altura_onda": round(h, 1),
            "largura": round(largura_eixo[1]), "arco_ext": round(R_ext * abs(theta), 1), "arco_int": round(R_int * abs(theta), 1),
            "desenv_ext": round(L1 + L2 + R_ext * abs(theta), 1), "desenv_int": round(L1 + L2 + R_int * abs(theta), 1),
            "corda": round(math.dist(p1, p2), 1), "peso": round(peso, 3),
            "perfil": str(m0.get("perfil") or e_longa.nome or "TELHA"), "material": _material(e_longa),
            # o perfil no plano: pontas livres, tangências, centro do arco (para o desenho)
            "p1": p1, "p2": p2, "d1": d1, "d2": d2, "I": I, "T": T, "sentido": 1 if theta > 0 else -1,
            "cobrimento": cobrimento, "saia": saia, "eixos_perfil": (a, b, w),
            # como o raio sai do modelo: o arco das facetas (linha média) dividido pelo ângulo
            "facetas": len(meio), "arco_modelo": round(arco, 1), "apoios": apoios}


def _secao_2d(e, w, a, b):
    """Seção de uma barra paralela a `w`, no plano (a, b): a face da ponta (normal ao
    longo de w) — o C da terça de verdade, não o casco. Sem face de ponta, o casco."""
    P = e.vertices
    melhores, wmax = [], None
    for f in e.faces:
        if len(f) < 3:
            continue
        s = [0.0, 0.0, 0.0]
        for i in range(1, len(f) - 1):
            c_ = _cruz(_sub(P[f[i]], P[f[0]]), _sub(P[f[i + 1]], P[f[0]]))
            s = [s[0] + c_[0], s[1] + c_[1], s[2] + c_[2]]
        n = _norm(tuple(s))
        if abs(_dot(n, w)) < 0.99:
            continue
        wf = sum(_dot(P[i], w) for i in f) / len(f)
        if wmax is None or wf > wmax + 1.0:
            melhores, wmax = [f], wf
        elif abs(wf - wmax) <= 1.0:
            melhores.append(f)
    if melhores:
        return [[(_dot(P[i], a), _dot(P[i], b)) for i in f] for f in melhores]
    return [_casco2d([(_dot(q, a), _dot(q, b)) for q in P])]


def _apoios_no_perfil(barras, med, w, a, b, p1, t1, t2, p2, R, s, d1) -> List[dict]:
    """As terças e longarinas debaixo da multi-dobra (na faixa da largura dela e a menos
    de 250 mm do perfil), com a seção no plano do perfil e a posição ao longo de cada reta
    — para conferir fixação e espaçamento no desenho."""
    wc = sum(_dot(m[1], w) for m in med) / len(med)
    n1 = (-d1[1] * s, d1[0] * s)
    centro = (t1[0] + n1[0] * R, t1[1] + n1[1] * R)
    a0 = math.atan2(t1[1] - centro[1], t1[0] - centro[0])
    da = (math.atan2(t2[1] - centro[1], t2[0] - centro[0]) - a0 + math.pi) % (2 * math.pi) - math.pi
    arco_pts = [(centro[0] + R * math.cos(a0 + da * i / 24), centro[1] + R * math.sin(a0 + da * i / 24)) for i in range(25)]

    def dist_seg(q, u, v):
        ux, uy = v[0] - u[0], v[1] - u[1]
        L2 = ux * ux + uy * uy or 1.0
        k = max(0.0, min(1.0, ((q[0] - u[0]) * ux + (q[1] - u[1]) * uy) / L2))
        return math.dist(q, (u[0] + ux * k, u[1] + uy * k)), k
    fora = []
    for e, c, eixos, ext in barras:
        if abs(_dot(eixos[0], w)) < 0.95 or abs(_dot(c, w) - wc) > ext[0] / 2:
            continue
        cc = (_dot(c, a), _dot(c, b))
        d_r1, k1 = dist_seg(cc, p1, t1)
        d_r2, k2 = dist_seg(cc, t2, p2)
        d_arco = min(dist_seg(cc, arco_pts[i], arco_pts[i + 1])[0] for i in range(len(arco_pts) - 1))
        dmin = min(d_r1, d_r2, d_arco)
        if dmin > 250.0:
            continue
        onde = "reta1" if dmin == d_r1 else ("reta2" if dmin == d_r2 else "arco")
        # posição ao longo da reta, medida da ponta livre (p1 na reta 1, p2 na reta 2)
        if onde == "reta1":
            pos = math.dist(p1, t1) * k1
        elif onde == "reta2":
            pos = math.dist(t2, p2) * (1.0 - k2)
        else:
            pos = None
        fora.append({"secao": _secao_2d(e, w, a, b), "centro": cc, "onde": onde, "posicao": pos,
                     "perfil": str(_marcas(e).get("perfil") or e.nome or "")})
    return fora


def _volume(e) -> float:
    v = 0.0
    P = e.vertices
    for f in e.faces:
        for i in range(1, len(f) - 1):
            a, b_, c = P[f[0]], P[f[i]], P[f[i + 1]]
            v += (a[0] * (b_[1] * c[2] - b_[2] * c[1]) - a[1] * (b_[0] * c[2] - b_[2] * c[0])
                  + a[2] * (b_[0] * c[1] - b_[1] * c[0])) / 6.0
    return abs(v)


def _perfil_da_face(md: dict, lado: float):
    """Pontos do perfil numa face da telha: `lado` = +1 externa (longe do centro da
    dobra), −1 interna. Devolve (reta1 (a, b), arco [pontos], reta2 (a, b), centro, raio)."""
    p1, p2, d1, d2, I, T = md["p1"], md["p2"], md["d1"], md["d2"], md["I"], md["T"]
    s = md["sentido"]
    n1 = (-d1[1] * s, d1[0] * s)                 # normal da reta 1 para o lado do centro
    n2 = (-d2[1] * s, d2[0] * s)
    R = md["raio"]
    t1 = (I[0] - d1[0] * T, I[1] - d1[1] * T)
    t2 = (I[0] + d2[0] * T, I[1] + d2[1] * T)
    centro = (t1[0] + n1[0] * R, t1[1] + n1[1] * R)
    h = md["altura_onda"] / 2.0 * lado
    off = lambda p, n: (p[0] - n[0] * h, p[1] - n[1] * h)      # noqa: E731
    r = R + h
    a0 = math.atan2(t1[1] - centro[1], t1[0] - centro[0])
    a1 = math.atan2(t2[1] - centro[1], t2[0] - centro[0])
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    arco = [(centro[0] + r * math.cos(a0 + da * i / 24), centro[1] + r * math.sin(a0 + da * i / 24)) for i in range(25)]
    return (off(p1, n1), off(t1, n1)), arco, (off(t2, n2), off(p2, n2)), centro, r


def desenho_da_multidobra(md: dict, desenho, dx: float, dy: float, nome: str = ""):
    """Célula da telha multi-dobra: o perfil longitudinal duas vezes — medidas externas e
    medidas internas —, cada um com as retas entre tangências, o raio, o ângulo, o arco e
    a corda, e o comprimento desenvolvido no título do painel (como a fábrica pede)."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.desenho import Cota
    esc = desenho.escala
    atr = {"conjunto": md["conjunto"], "detalhe": "multidobra"}
    if nome:
        atr["nome"] = nome
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    todos = [q for lado in (1.0, -1.0) for parte in _perfil_da_face(md, lado)[:3] for q in parte]
    x0 = min(q[0] for q in todos)
    y0 = min(q[1] for q in todos)
    alt = max(q[1] for q in todos) - y0
    painel_y = 0.0
    fmt = lambda v: "%d" % round(v)          # noqa: E731  (a fábrica trabalha no milímetro inteiro)
    for lado, titulo, arco_v, desenv, raio_v in ((-1.0, "MEDIDAS INTERNAS", md["arco_int"], md["desenv_int"], md["raio_int"]),
                                                 (1.0, "MEDIDAS EXTERNAS", md["arco_ext"], md["desenv_ext"], md["raio_ext"])):
        r1, arco, r2, centro, r = _perfil_da_face(md, lado)
        T = lambda q: (q[0] - x0, q[1] - y0 + painel_y)        # noqa: E731
        p.polilinha([T(r1[0]), T(r1[1])] + [T(q) for q in arco[1:-1]] + [T(r2[0]), T(r2[1])], camada="ACO")
        for (a_, b_), desl in ((r1, 12.0), (r2, 12.0), ((r1[0], r2[1]), 30.0)):
            pa, pb = T(a_), T(b_)
            # do lado de fora da dobra (longe do centro do arco), para não cruzar o perfil
            ux, uy = pb[0] - pa[0], pb[1] - pa[1]
            meio_seg = ((pa[0] + pb[0]) / 2 - T(centro)[0], (pa[1] + pb[1]) / 2 - T(centro)[1])
            sinal = 1.0 if (-uy * meio_seg[0] + ux * meio_seg[1]) > 0 else -1.0
            desenho.add(Cota(modo="alinhada", p1=p._p(*pa), p2=p._p(*pb), deslocamento=desl * sinal,
                             texto=str(int(round(math.dist(pa, pb)))), atributos=dict(atr)))
            p._p(pa[0] - uy / (math.hypot(ux, uy) or 1) * desl * sinal * esc, pa[1] + ux / (math.hypot(ux, uy) or 1) * desl * sinal * esc)
        # as terças/longarinas debaixo da telha (só para conferir fixação e espaçamento)
        for ap in md.get("apoios") or []:
            for poli in ap["secao"]:
                p.polilinha([T(q) for q in poli], fechada=True, camada="TERCAS")
        if lado > 0:
            _cotas_dos_apoios(md, p, T, r1, r2, T(centro), atr)
        meio = arco[len(arco) // 2]
        cx, cy = T(centro)
        mx, my = T(meio)
        p.linha(cx, cy, mx, my, "VISTA-FINA")
        p.texto((cx + mx) / 2, (cy + my) / 2, "R%s" % fmt(raio_v), 2.2 * esc)
        p.texto(mx, my + 3.0 * esc, "arco %s · %s°" % (fmt(arco_v), ("%.1f" % md["angulo"]).replace(".", ",")), 2.2 * esc)
        # o título acima das cotas externas (reta a 12, apoios a 21, corda a 30)
        p.texto(0, painel_y + alt + 36.0 * esc, "%s  %s mm" % (titulo, fmt(desenv)), 3.0 * esc)
        painel_y += alt + 70.0 * esc
    comp = ", ".join("%s x%d" % (k, q) for k, q in sorted(md["composicao"].items(), key=lambda kv: _ordem_natural(kv[0])))
    linhas = ["TELHA MULTI-DOBRA",
              "%s – %02dx  (%s)" % (nome or md["conjunto"], md["instancias"], md["conjunto"]),
              "%s  %s  largura 1050 mm (útil 980)" % (md["perfil"], md["material"]),
              "retas %s + %s mm · raio int. %s / ext. %s · %s°" % (fmt(md["reta1"]), fmt(md["reta2"]), fmt(md["raio_int"]),
                                                               fmt(md["raio_ext"]), ("%.1f" % md["angulo"]).replace(".", ",")),
              "desenvolvida: ext. %s mm · int. %s mm   %s kg/pç  total %s kg" % (
                  fmt(md["desenv_ext"]), fmt(md["desenv_int"]), ("%.2f" % md["peso"]).replace(".", ","),
                  ("%.1f" % (md["peso"] * md["instancias"])).replace(".", ",")),
              "no modelo: %s (facetas de %s)" % (comp, md["conjunto"])]
    if md.get("arco_modelo"):
        linhas.insert(4, "raio = arco / ângulo: as %d facetas do modelo somam %s mm na linha média; %s / %s rad (%s°) = R%s; int./ext. = R ∓ meia onda (%s)" % (
            md["facetas"], fmt(md["arco_modelo"]), fmt(md["arco_modelo"]),
            ("%.4f" % math.radians(md["angulo"])).replace(".", ","), ("%.1f" % md["angulo"]).replace(".", ","),
            fmt(md["raio"]), fmt(md["altura_onda"] / 2)))
    if md.get("apoios"):
        linhas.append("apoios (azul): " + ", ".join(sorted({ap["perfil"] for ap in md["apoios"]})) + " — só para conferir fixação e espaçamento")
    if md.get("saia"):
        linhas.insert(5, "saia: a reta da parede desce %d mm abaixo da última longarina (%s); no modelo tinha %s" % (
            SAIA_TELHA, md["saia"]["longarina"], fmt(md["saia"]["reta_modelo"])))
    cb = md.get("cobrimento")
    if cb:
        linhas.insert(5, "cobrimento: passa %d mm da 1ª terça (%s); a telha seguinte começa %d mm antes — transpasse %s mm" % (
            COBRIMENTO_TERCA, cb["terca"], COBRIMENTO_TERCA, fmt(cb["transpasse"])))
        linhas.insert(6, "telha complementar %s-C: %02dx  L = %s mm (a reta do modelo tinha %s)" % (
            nome or md["conjunto"], md["instancias"], fmt(cb["resto"]), fmt(cb["reta_modelo"])))
    y = painel_y + 4.0 * esc
    for i, txt in enumerate(reversed(linhas)):
        altura = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, altura * esc)
        y += (altura + 1.2) * esc
    return p.extremos


def _cotas_dos_apoios(md, p, T, r1, r2, centro, atr):
    """Cadeia de cotas em cada reta: da ponta livre ao centro de cada apoio e entre apoios,
    do lado de fora da dobra (entre a cota da reta e a da corda)."""
    from nucleo2d.desenho import Cota
    for reta, (u, v) in (("reta1", r1), ("reta2", r2)):
        # ponta livre → tangência (reta 1: r1[0] → r1[1]; reta 2: r2[1] → r2[0])
        ini, fim = (u, v) if reta == "reta1" else (v, u)
        pa, pb = T(ini), T(fim)
        L = math.dist(pa, pb)
        if L < 1.0:
            continue
        dx_, dy_ = (pb[0] - pa[0]) / L, (pb[1] - pa[1]) / L
        pos = sorted(ap["posicao"] for ap in md.get("apoios") or [] if ap["onde"] == reta and ap["posicao"] is not None)
        if not pos:
            continue
        marcas = [0.0] + [q for q in pos if 0.5 < q < L - 0.5]
        meio_seg = ((pa[0] + pb[0]) / 2 - centro[0], (pa[1] + pb[1]) / 2 - centro[1])
        sinal = 1.0 if (-dy_ * meio_seg[0] + dx_ * meio_seg[1]) > 0 else -1.0
        esc = p.d.escala
        h = 2.5 * esc
        nx, ny = -dy_, dx_                          # a normal que a Cota alinhada usa
        off = 21.0 * sinal * esc
        n = len(marcas) - 1
        for i, (q0, q1) in enumerate(zip(marcas, marcas[1:])):
            a_ = (pa[0] + dx_ * q0, pa[1] + dy_ * q0)
            b_ = (pa[0] + dx_ * q1, pa[1] + dy_ * q1)
            txt = str(int(round(q1 - q0)))
            # número que não cabe entre as chamadas: sai pela ponta ou um degrau para fora
            onde = p._texto_fora(q1 - q0, len(txt), i, n)
            tw = 0.62 * h * len(txt)
            pos = None
            if onde == "antes":
                q = q0 - tw / 2 - 1.5 * esc
            elif onde == "depois":
                q = q1 + tw / 2 + 1.5 * esc
            elif onde == "fora":
                q = (q0 + q1) / 2
            if onde:
                extra = off + sinal * (0.55 * h + (1.9 * h if onde == "fora" else 0.0))
                pos = p._p(pa[0] + dx_ * q + nx * extra, pa[1] + dy_ * q + ny * extra)
            p.d.add(Cota(modo="alinhada", p1=p._p(*a_), p2=p._p(*b_), deslocamento=21.0 * sinal,
                         texto=txt, texto_pos=pos, atributos=dict(atr)))


def multidobras(pecas: Sequence) -> Dict[str, object]:
    """{"telhas": [ {conjunto, instancias, composicao, perfil…} ], "posicoes": {marcas de
    posição consumidas}}. Uma posição só é consumida quando todas as peças dela estão em
    telhas multi-dobra reconhecidas."""
    from nucleo2d.detalhe.conjuntos import _instancias_do_conjunto
    por_conj: Dict[str, list] = collections.defaultdict(list)
    todas_por_pos = collections.Counter()
    for e in pecas:
        m = _marcas(e)
        if not _eh_telha(str(m.get("perfil") or e.nome or "")):
            continue
        todas_por_pos[_posicao(e)] += 1
        conj = str(m.get("conjunto") or "")
        if conj:
            por_conj[conj].append(e)
    telhas, usadas = [], collections.Counter()
    barras = []
    if any(len(v) >= 4 for v in por_conj.values()):
        for e in pecas:
            m = _marcas(e)
            if _eh_telha(str(m.get("perfil") or e.nome or "")) or len(e.vertices or []) < 8:
                continue
            if "PLATE" in str(m.get("perfil") or e.nome or "").upper():
                continue
            c, eixos, ext = _medidas(e)
            if ext[0] > 1000.0 and ext[1] < 400.0:
                barras.append((e, c, eixos, ext))
    for conj, lista in sorted(por_conj.items(), key=lambda kv: _ordem_natural(kv[0])):
        if len(lista) < 4:
            continue
        total = collections.Counter(_posicao(e) for e in lista)
        g = 0
        for q in total.values():
            g = math.gcd(g, q)
        unidade = collections.Counter({k: q // max(g, 1) for k, q in total.items()})
        if sum(unidade.values()) < 4:
            continue
        insts = [i for i in _instancias_do_conjunto(lista, unidade)
                 if collections.Counter(_posicao(e) for e in i) == unidade]
        if not insts:
            continue
        perfil = _analisar_instancia(insts[0], barras)
        if perfil is None:
            continue
        perfil.update(conjunto=conj, instancias=len(insts), composicao=dict(unidade),
                      ids=[e.id for i in insts for e in i])
        telhas.append(perfil)
        for i in insts:
            for e in i:
                usadas[_posicao(e)] += 1
    consumidas = {p for p, n in usadas.items() if n >= todas_por_pos.get(p, 0)}
    # a cumeeira (duas pernas curtas, uma em cada água) é uma peça só
    try:
        cm = cumeeiras([e for e in pecas if e.id not in {i for t in telhas for i in t.get("ids", [])}])
    except Exception:                                 # noqa: BLE001 — sem cumeeira, o resto segue
        cm = {"cumeeiras": [], "posicoes": set()}
    return {"telhas": telhas, "posicoes": consumidas | cm["posicoes"], "cumeeiras": cm["cumeeiras"]}


# ============================================================ cumeeira
#: Perna de cumeeira mais comprida que isto (mm) não é cumeeira: é telha que se apoia.
PERNA_MAX_CUMEEIRA = 600.0


def _perna(e, w):
    """Perna (peça curta de telha) no plano perpendicular à largura `w`: centro, direção,
    comprimento, espessura (altura da onda)."""
    c, eixos, ext = _medidas(e)
    outros = [(ax, x) for ax, x in zip(eixos, ext) if abs(_dot(ax, w)) < 0.9]
    if len(outros) < 2:
        return None
    (ax_l, comp), (_, alt) = sorted(outros, key=lambda t: -t[1])[:2]
    return c, ax_l, comp, alt


def cumeeiras(pecas: Sequence) -> Dict[str, object]:
    """Cumeeiras do modelo: o TecnoMETAL modela cada uma como duas telhas curtas (uma em cada
    água) que se encontram na cumeeira; na fábrica é uma peça só, dobrada no meio. Por
    conjunto de telhas, as peças são pareadas pela ponta que se encontra (até 60 mm) com
    as pernas formando uma dobra entre 90° e 178°. {"cumeeiras": [...], "posicoes": {...}}."""
    por_conj: Dict[str, list] = collections.defaultdict(list)
    todas_por_pos = collections.Counter()
    for e in pecas:
        m = _marcas(e)
        if not _eh_telha(str(m.get("perfil") or e.nome or "")):
            continue
        todas_por_pos[_posicao(e)] += 1
        conj = str(m.get("conjunto") or "")
        if conj:
            por_conj[conj].append(e)
    saida, usadas = [], collections.Counter()
    for conj, lista in sorted(por_conj.items(), key=lambda kv: _ordem_natural(kv[0])):
        if len(lista) < 2:
            continue
        # a largura (TP40: 1031): o maior eixo, comum às peças
        c0, eixos0, ext0 = _medidas(lista[0])
        w = _norm(eixos0[0])
        if ext0[0] < 300:
            continue
        z = (0.0, 0.0, 1.0)
        bz = _sub(z, tuple(v * _dot(z, w) for v in w))
        if _dot(bz, bz) < 1e-6:
            continue
        b = _norm(bz)
        a = _norm(_cruz(b, w))
        pernas = []
        for e in lista:
            pr = _perna(e, w)
            if pr is None or pr[2] > PERNA_MAX_CUMEEIRA:
                pernas = []
                break
            c, ax, L, alt = pr
            c2 = (_dot(c, a), _dot(c, b))
            d2 = (_dot(ax, a), _dot(ax, b))
            n = math.hypot(*d2) or 1.0
            d2 = (d2[0] / n, d2[1] / n)
            pontas = [(c2[0] - d2[0] * L / 2, c2[1] - d2[1] * L / 2), (c2[0] + d2[0] * L / 2, c2[1] + d2[1] * L / 2)]
            pernas.append({"e": e, "p": pontas, "L": L, "alt": alt, "w": _dot(c, w)})
        if len(pernas) < 2:
            continue
        # pares: mesma faixa da largura, pontas que se encontram, dobra de verdade
        pares, livres = [], set(range(len(pernas)))
        cands = []
        for i in range(len(pernas)):
            for j in range(i + 1, len(pernas)):
                A, B = pernas[i], pernas[j]
                if abs(A["w"] - B["w"]) > 50.0:
                    continue
                for ka in (0, 1):
                    for kb in (0, 1):
                        gap = math.dist(A["p"][ka], B["p"][kb])
                        if gap <= 60.0:
                            cands.append((gap, i, j, ka, kb))
        cands.sort()
        for gap, i, j, ka, kb in cands:
            if i not in livres or j not in livres:
                continue
            A, B = pernas[i], pernas[j]
            topo = ((A["p"][ka][0] + B["p"][kb][0]) / 2, (A["p"][ka][1] + B["p"][kb][1]) / 2)
            da = _sub((*A["p"][1 - ka], 0.0), (*A["p"][ka], 0.0))[:2]
            db = _sub((*B["p"][1 - kb], 0.0), (*B["p"][kb], 0.0))[:2]
            na, nb = math.hypot(*da) or 1.0, math.hypot(*db) or 1.0
            cosang = (da[0] * db[0] + da[1] * db[1]) / (na * nb)
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            if not (90.0 <= ang <= 178.0):
                continue
            livres -= {i, j}
            pares.append((A, B, topo, (da[0] / na, da[1] / na), (db[0] / nb, db[1] / nb), ang))
        if not pares or len(pares) * 2 < 0.8 * len(pernas):
            continue
        A, B, topo, da, db, ang = pares[0]
        L1, L2 = arredondar_telha(A["L"]), arredondar_telha(B["L"])
        # a perna 1 é a da esquerda no desenho
        if da[0] > db[0]:
            L1, L2, da, db = L2, L1, db, da
        peso_m = sum(_volume(p["e"]) for p in (A, B)) * RHO_ACO
        peso = peso_m * (L1 + L2) / max(A["L"] + B["L"], 1.0)
        from nucleo2d.detalhe.base import _material
        m0 = _marcas(A["e"])
        comp = collections.Counter(_posicao(p["e"]) for par in pares for p in par[:2])
        g = 0
        for q in comp.values():
            g = math.gcd(g, q)
        saida.append({"tipo": "cumeeira", "conjunto": conj, "instancias": len(pares),
                      "composicao": {k: q // len(pares) if q % len(pares) == 0 else q for k, q in comp.items()},
                      "ids": [p["e"].id for par in pares for p in par[:2]],
                      "perna1": L1, "perna2": L2, "angulo": round(ang, 1), "desenv": L1 + L2,
                      "desenv_ext": L1 + L2, "altura_onda": round(sorted((A["alt"], B["alt"]))[0], 1),
                      "perfil": str(m0.get("perfil") or A["e"].nome or "TELHA"), "material": _material(A["e"]),
                      "peso": round(peso, 3), "topo": (0.0, 0.0), "d1": da, "d2": db})
        for par in pares:
            for p in par[:2]:
                usadas[_posicao(p["e"])] += 1
    consumidas = {p for p, n in usadas.items() if n >= todas_por_pos.get(p, 0)}
    return {"cumeeiras": saida, "posicoes": consumidas}


def desenho_da_cumeeira(cm: dict, desenho, dx: float, dy: float, nome: str = ""):
    """Célula da cumeeira: o perfil das duas pernas dobrado na cumeeira, cada perna cotada, o
    ângulo da dobra e o desenvolvido (o comprimento da chapa cortada da bobina)."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.desenho import Cota
    esc = desenho.escala
    atr = {"conjunto": cm["conjunto"], "detalhe": "cumeeira"}
    if nome:
        atr["nome"] = nome
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    d1, d2 = cm["d1"], cm["d2"]
    q1 = (d1[0] * cm["perna1"], d1[1] * cm["perna1"])
    q2 = (d2[0] * cm["perna2"], d2[1] * cm["perna2"])
    xs = [0.0, q1[0], q2[0]]
    ys = [0.0, q1[1], q2[1]]
    x0, y0 = min(xs), min(ys)
    T = lambda q: (q[0] - x0, q[1] - y0)          # noqa: E731
    topo, a1, a2 = T((0.0, 0.0)), T(q1), T(q2)
    p.polilinha([a1, topo, a2], camada="ACO")
    for pa, pb in ((a1, topo), (topo, a2)):
        # cota por fora da dobra (do lado de cima, longe do ângulo)
        ux, uy = pb[0] - pa[0], pb[1] - pa[1]
        sinal = 1.0 if ux >= 0 else -1.0
        desenho.add(Cota(modo="alinhada", p1=p._p(*pa), p2=p._p(*pb), deslocamento=10.0 * sinal,
                         texto=str(int(round(math.dist(pa, pb)))), atributos=dict(atr)))
    p.texto(topo[0], topo[1] - 5.0 * esc, "dobra %s°" % ("%.1f" % cm["angulo"]).replace(".", ","), 2.2 * esc, alinhamento="centro")
    alt = max(a1[1], a2[1], topo[1])
    comp = ", ".join("%s x%d" % (k, q) for k, q in sorted(cm["composicao"].items(), key=lambda kv: _ordem_natural(kv[0])))
    linhas = ["CUMEEIRA",
              "%s – %02dx  (%s)" % (nome or cm["conjunto"], cm["instancias"], cm["conjunto"]),
              "%s  %s  largura 1050 mm (útil 980)" % (cm["perfil"], cm["material"]),
              "pernas %d + %d mm · dobra %s° · desenvolvida %d mm   %s kg/pç  total %s kg" % (
                  cm["perna1"], cm["perna2"], ("%.1f" % cm["angulo"]).replace(".", ","), cm["desenv"],
                  ("%.2f" % cm["peso"]).replace(".", ","), ("%.1f" % (cm["peso"] * cm["instancias"])).replace(".", ",")),
              "uma peça só, dobrada na cumeeira; no modelo: %s" % comp]
    y = alt + 18.0 * esc
    for i, txt in enumerate(reversed(linhas)):
        altura = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, altura * esc)
        y += (altura + 1.2) * esc
    return p.extremos


# ============================================================ paginação
def faces_de_telhas(pecas: Sequence, md: Optional[dict] = None, nome_de=None, saias: Optional[dict] = None) -> List[dict]:
    """As telhas do modelo agrupadas por face (água da cobertura, fachada), cada uma com as
    chapas na posição de montagem: [{"normal", "u", "v", "chapas": [{"contorno": [(x, y)],
    "comprimento", "nome", "centro"}]}]. A telha multi-dobra entra como uma chapa só, na face
    do seu trecho reto mais longo, com o comprimento desenvolvido externo."""
    nome_de = nome_de or (lambda marca: marca)
    md = md or {"telhas": []}
    em_md = {}
    for t in md.get("telhas", []):
        for i in t.get("ids", []):
            em_md[i] = t
    de_cumeeira = {i for cm in md.get("cumeeiras", []) for i in cm.get("ids", [])}
    feitas_md = set()
    chapas = []
    for e in pecas:
        m = _marcas(e)
        if not _eh_telha(str(m.get("perfil") or e.nome or "")) or e.id in de_cumeeira:
            continue
        c, eixos, ext = _medidas(e)
        t = em_md.get(e.id)
        if t is not None:
            # só o trecho reto mais longo de cada multi-dobra representa a telha
            if ext[0] < 0.5 * max(t["reta1"], t["reta2"], (t.get("cobrimento") or {}).get("reta_modelo", 0.0)):
                continue

        # normal da chapa: o eixo de menor extensão (altura da onda); para cima ou para fora
        n = _norm(eixos[2])
        if n[2] < -1e-6 or (abs(n[2]) < 1e-6 and (n[0] + n[1]) < 0):
            n = (-n[0], -n[1], -n[2])
        # comprimento: o maior eixo; largura o do meio (a onda corre no comprimento)
        chapas.append({"e": e, "c": c, "n": n, "u": _direcao_da_onda(e, n), "ext": ext, "multidobra": t,
                       "nome": (t["nome"] if t is not None and t.get("nome") else nome_de(_posicao(e)))})
    # centros das facetas das multi-dobra (para saber de que lado fica a curva)
    facetas = []
    for e in pecas:
        if e.id in em_md:
            c, eixos, ext = _medidas(e)
            if ext[0] < FACETA_MAX and max(ext[1], ext[2]) > 300:
                facetas.append(c)
    faces: List[dict] = []
    for ch in chapas:
        for f in faces:
            if abs(_dot(f["normal"], ch["n"])) > 0.985 and abs(_dot(f["normal"], _sub(ch["c"], f["ponto"]))) < 400.0:
                f["itens"].append(ch)
                break
        else:
            faces.append({"normal": ch["n"], "ponto": ch["c"], "itens": [ch]})
    saida = []
    for f in faces:
        n = f["normal"]
        # u: a direção das ondas (comprimento) mais comum na face; v completa o plano
        # a direção das ondas é a mesma em toda a face: a das chapas em que ela é clara
        claras = [ch for ch in f["itens"] if ch["u"][1]] or f["itens"]
        u = max(claras, key=lambda ch: ch["ext"][0])["u"][0]
        u = _norm(_sub(u, tuple(x * _dot(u, n) for x in n)))
        if _dot(u, (0.0, 0.0, 1.0)) < 0 or (abs(u[2]) < 1e-6 and u[0] + u[1] < 0):
            u = (-u[0], -u[1], -u[2])
        v = _norm(_cruz(n, u))
        lista = []
        for ch in f["itens"]:
            pts = [(_dot(p, v), _dot(p, u)) for p in ch["e"].vertices]
            contorno = _casco2d(pts)
            ys = [q[1] for q in pts]
            xs = [q[0] for q in pts]
            # comprimento: ao longo da onda da própria chapa quando ela é clara (numa face
            # plana cabem chapas com a onda em direções diferentes), senão a da face
            uu = ch["u"][0] if ch["u"][1] else u
            proj = [_dot(p, uu) for p in ch["e"].vertices]
            comp = ch["multidobra"]["desenv_ext"] if ch["multidobra"] else max(proj) - min(proj)
            corte = list(contorno)              # o corte do modelo, na posição real
            desce = (saias or {}).get(ch["e"].id, 0.0)
            if desce and not ch["multidobra"]:
                # a saia: a ponta de baixo desce (a face da fachada tem u para cima)
                comp += desce
                y_min = min(ys)
                contorno = [(q[0], q[1] - desce) if q[1] <= y_min + 1.0 else q for q in contorno]
                corte = list(contorno)
                ys = ys + [y_min - desce]
            if not ch["multidobra"]:
                # a sobra da fábrica: a chapa sobe até o comprimento arredondado
                comp_r = arredondar_telha(comp)
                if comp_r > comp:
                    ys = ys + [min(ys) + (max(ys) - min(ys)) * comp_r / max(comp, 1.0)]
                comp = comp_r
            cb = ch["multidobra"].get("cobrimento") if ch["multidobra"] else None
            if cb:
                # a multi-dobra termina 150 mm depois da 1ª terça; a complementar começa 150
                # antes dela e vai até o fim da reta do modelo. A ponta da curva é a ponta da
                # peça mais perto das facetas.
                y0_, y1_ = min(ys), max(ys)
                uf = min((_dot(fc, u) for fc in facetas), key=lambda q: min(abs(q - y0_), abs(q - y1_)), default=y0_)
                de_baixo = abs(uf - y0_) <= abs(uf - y1_)
                yt, sg = (y0_, 1.0) if de_baixo else (y1_, -1.0)
                x0_, x1_ = min(xs), max(xs)
                ret = lambda a_, b_: [(x0_, min(a_, b_)), (x1_, min(a_, b_)), (x1_, max(a_, b_)), (x0_, max(a_, b_))]   # noqa: E731
                ym = yt + sg * cb["reta_nova"]
                yc = yt + sg * (cb["terca_ini"] - COBRIMENTO_TERCA)
                yf = y1_ if de_baixo else y0_
                lista.append({"contorno": ret(yt, ym), "comprimento": comp, "nome": ch["nome"],
                              "x": (x0_ + x1_) / 2, "y0": min(yt, ym), "y1": max(yt, ym), "multidobra": True})
                lista.append({"contorno": ret(yc, yf), "comprimento": cb["resto"], "nome": ch["nome"] + "-C",
                              "x": (x0_ + x1_) / 2 + 1e-3, "y0": min(yc, yf), "y1": max(yc, yf), "multidobra": False})
                continue
            lista.append({"contorno": contorno, "corte": corte, "comprimento": comp, "nome": ch["nome"], "saia": desce,
                          "x": (min(xs) + max(xs)) / 2, "y0": min(ys), "y1": max(ys),
                          "multidobra": bool(ch["multidobra"]), "alinhada": abs(_dot(uu, u)) > 0.9})
        inclinacao = math.degrees(math.acos(max(-1.0, min(1.0, abs(n[2])))))
        saida.append({"normal": n, "chapas": lista, "inclinacao": inclinacao,
                      "tipo": "cobertura" if inclinacao < 45 else "fachada"})
    saida.sort(key=lambda f: (f["tipo"] != "cobertura", -len(f["chapas"])))
    return saida


def _direcao_da_onda(e, normal):
    """Direção em que a onda da telha corre (o comprimento de compra): a direção do plano
    da chapa que as faces da malha menos apontam — as faces inclinadas da onda têm normal
    na largura, nenhuma no comprimento. O maior eixo da malha não serve: numa telha curta
    (258 mm) o maior eixo é a largura."""
    import numpy as np
    P = e.vertices
    M = np.zeros((3, 3))
    for f in e.faces:
        if len(f) < 3:
            continue
        s = np.zeros(3)
        a = np.array(P[f[0]])
        for i in range(1, len(f) - 1):
            s += np.cross(np.array(P[f[i]]) - a, np.array(P[f[i + 1]]) - a)
        area = np.linalg.norm(s)
        if area < 1e-9:
            continue
        n = s / area
        M += (area / 2.0) * np.outer(n, n)
    # no plano da chapa (tira a normal), o autovetor de menor peso
    nrm = np.array(normal)
    Pp = np.eye(3) - np.outer(nrm, nrm)
    Mp = Pp @ M @ Pp + 1e9 * np.outer(nrm, nrm)
    w, V = np.linalg.eigh(Mp)
    ordem = np.argsort(w)
    u = V[:, int(ordem[0])]
    u = u / (np.linalg.norm(u) or 1.0)
    # clareza: a outra direção do plano precisa pesar bem mais (a onda existe na malha)
    clara = bool(w[ordem[1]] > 1e-9 and w[ordem[0]] < 0.3 * w[ordem[1]])
    return (float(u[0]), float(u[1]), float(u[2])), clara


def _casco2d(pts):
    pts = sorted(set((round(p[0], 1), round(p[1], 1)) for p in pts))
    if len(pts) < 3:
        return pts

    def giro(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    baixo, cima = [], []
    for p in pts:
        while len(baixo) >= 2 and giro(baixo[-2], baixo[-1], p) <= 0:
            baixo.pop()
        baixo.append(p)
    for p in reversed(pts):
        while len(cima) >= 2 and giro(cima[-2], cima[-1], p) <= 0:
            cima.pop()
        cima.append(p)
    return baixo[:-1] + cima[:-1]


def desenho_da_paginacao(face: dict, desenho, dx: float, dy: float, indice: int = 1):
    """Uma face paginada: as chapas lado a lado como são montadas, cada uma com a marca e a
    cota do comprimento real (na chapa, ao longo da onda) — o "comprimentos reais" que a
    obra usa para distribuir as telhas."""
    from nucleo2d.detalhe.base import _Papel
    from nucleo2d.desenho import Cota
    esc = desenho.escala
    atr = {"detalhe": "paginacao", "face": indice}
    p = _Papel(desenho, atr, dx, dy, camada_peca="TELHAS")
    chapas = face["chapas"]
    x0 = min(q[0] for ch in chapas for q in ch["contorno"])
    y0 = min(q[1] for ch in chapas for q in ch["contorno"])
    T = lambda q: (q[0] - x0, q[1] - y0)        # noqa: E731
    from nucleo2d.detalhe.base import LARGURA_TOTAL_TELHA, LARGURA_COMPRA_TELHA
    ordenadas = sorted(chapas, key=lambda c: c["x"])
    cotada = False
    for n, ch in enumerate(ordenadas):
        # a chapa com a largura total de catálogo (1050, com os transpasses) em volta do
        # centro dela; o passo entre chapas é o do modelo (a largura útil)
        xs = [q[0] for q in ch["contorno"]]
        larg = max(xs) - min(xs)
        k = LARGURA_TOTAL_TELHA / larg if 600.0 < larg < 1200.0 and ch.get("alinhada", True) else 1.0
        contorno = [(ch["x"] + (q[0] - ch["x"]) * k, q[1]) for q in ch["contorno"]]
        # a telha inteira (como é comprada) em traço cheio; o corte que ela tem no modelo
        # (a empena inclinada, a curva do canto) tracejado — é feito na obra, medido depois
        # de instalada. O tracejado fica na posição real (sem a escala para 1050): assim a
        # linha da empena segue contínua de uma telha para a outra.
        xa, xb = min(q[0] for q in contorno), max(q[0] for q in contorno)
        ya, yb = ch["y0"], ch["y1"]
        retangulo = [(xa, ya), (xb, ya), (xb, yb), (xa, yb)]
        p.polilinha([T(q) for q in retangulo], fechada=True, camada="ACO")
        corte = ch.get("corte") or ch["contorno"]
        cxa, cxb = min(q[0] for q in corte), max(q[0] for q in corte)
        area_c = abs(sum(corte[i][0] * corte[(i + 1) % len(corte)][1] - corte[(i + 1) % len(corte)][0] * corte[i][1]
                         for i in range(len(corte)))) / 2.0 if len(corte) >= 3 else 0.0
        if area_c and area_c < 0.99 * (cxb - cxa) * (yb - ya):
            p.polilinha([T(q) for q in corte], fechada=True, camada="OCULTA")
        if k != 1.0 and not cotada:
            cotada = True
            xa = min(q[0] for q in contorno) - x0
            yb = ch["y0"] - y0
            desenho.add(Cota(modo="h", p1=p._p(xa, yb), p2=p._p(xa + LARGURA_COMPRA_TELHA, yb), deslocamento=-14.0,
                             texto="%d útil" % LARGURA_COMPRA_TELHA, atributos=dict(atr)))
            desenho.add(Cota(modo="h", p1=p._p(xa, yb), p2=p._p(xa + LARGURA_TOTAL_TELHA, yb), deslocamento=-22.0,
                             texto="%d total" % LARGURA_TOTAL_TELHA, atributos=dict(atr)))
            p._p(xa, yb - 26.0 * esc)
        xm = ch["x"] - x0
        a, b = (xm, ch["y0"] - y0), (xm, ch["y1"] - y0)
        texto = "%d" % round(ch["comprimento"])
        desenho.add(Cota(modo="v", p1=p._p(*a), p2=p._p(*b), deslocamento=0.0, texto=texto, altura=1.8,
                         atributos=dict(atr, chapa=ch["nome"])))
        p.texto(xm, ch["y0"] - y0 - 4.0 * esc, ch["nome"], 1.8 * esc, angulo=90.0, alinhamento="direita")
    # a linha da estrutura (a última longarina, de onde a saia é medida) atravessando a
    # face, com a cota da saia até a ponta de baixo das telhas: para conferir os 150 mm
    com_saia = [ch for ch in ordenadas if ch.get("saia")]
    if com_saia:
        from nucleo2d.detalhe.base import LARGURA_TOTAL_TELHA as _LT
        y_fundo = min(ch["y0"] for ch in com_saia) - y0
        y_ref = y_fundo + SAIA_TELHA
        xa_f = min(q[0] for ch in ordenadas for q in ch["contorno"]) - x0 - 0.1 * _LT
        xb_f = max(q[0] for ch in ordenadas for q in ch["contorno"]) - x0 + 0.3 * _LT
        p.linha(xa_f, y_ref, xb_f, y_ref, "EIXO")
        p.texto(xb_f, y_ref + 1.0 * esc, "ÚLTIMA LONGARINA — saia %d abaixo" % SAIA_TELHA, 1.8 * esc, alinhamento="direita")
        desenho.add(Cota(modo="v", p1=p._p(xb_f, y_fundo), p2=p._p(xb_f, y_ref), deslocamento=-4.0,
                         texto="%d" % SAIA_TELHA, altura=1.8, atributos=dict(atr)))
        p._p(xb_f + 14.0 * esc, y_fundo)
    alt = max(q[1] for ch in chapas for q in ch["contorno"]) - y0
    cont = collections.Counter(ch["nome"] for ch in chapas)
    resumo = " · ".join("%s %dx" % (k, q) for k, q in sorted(cont.items(), key=lambda kv: _ordem_natural(kv[0])))
    titulo = "FACE %d – %s%s – %d chapas" % (indice, face["tipo"].upper(),
                                            (" (%.0f°)" % face["inclinacao"]) if face["tipo"] == "cobertura" else "",
                                            len(chapas))
    p.texto(0, alt + 6.0 * esc, titulo, 3.5 * esc)
    p.texto(0, alt + 2.0 * esc, resumo[:220], 2.0 * esc)
    return p.extremos

def saias_de_fachada(pecas, ignorar=frozenset()) -> Dict[str, float]:
    """{id da telha: quanto a ponta de baixo desce (mm; negativo sobe)} das telhas de
    fachada (chapa em pé, onda na vertical), para a ponta de baixo ficar SAIA_TELHA abaixo
    da longarina mais baixa atrás dela — a regra da fábrica. Longarina: barra comprida,
    deitada, paralela à face e a menos de 400 mm do plano da telha, cobrindo a largura dela."""
    barras, telhas = [], []
    for e in pecas:
        m = _marcas(e)
        nome = str(m.get("perfil") or e.nome or "")
        if len(e.vertices or []) < 8:
            continue
        if _eh_telha(nome):
            if e.id not in ignorar:                   # as peças das multi-dobra têm regra própria
                telhas.append(e)
        elif "PLATE" not in nome.upper():
            c, eixos, ext = _medidas(e)
            if ext[0] > 1000.0 and ext[1] < 400.0 and abs(eixos[0][2]) < 0.2:
                barras.append((e, c, eixos, ext))
    fachada = []
    for e in telhas:
        c, eixos, ext = _medidas(e)
        n = _norm(eixos[2])
        if abs(n[2]) > 0.2:
            continue                                  # não é fachada
        u, clara = _direcao_da_onda(e, n)
        if clara and abs(u[2]) < 0.8:
            continue                                  # onda deitada: não é a telha da saia
        fachada.append((e, c, n))
    # a saia é "fora a fora": uma altura só por face, a da longarina mais baixa da face —
    # a telha do canto, onde a longarina já terminou, desce junto com as outras
    grupos = []
    for item in fachada:
        for g in grupos:
            if abs(_dot(g["n"], item[2])) > 0.985 and abs(_dot(g["n"], _sub(item[1], g["c"]))) < 400.0:
                g["itens"].append(item)
                break
        else:
            grupos.append({"n": item[2], "c": item[1], "itens": [item]})
    fora = {}
    for g in grupos:
        n = g["n"]
        h = _norm(_cruz((0.0, 0.0, 1.0), n))           # horizontal no plano da face
        hs = [_dot(q, h) for e, _, _ in g["itens"] for q in e.vertices]
        h0, h1 = min(hs), max(hs)
        z0f = min(q[2] for e, _, _ in g["itens"] for q in e.vertices)
        mais_baixa = None
        for b, cb, eb, xb in barras:
            if abs(_dot(eb[0], n)) > 0.2:
                continue
            if min(abs(_dot(_sub(cb, c), n)) for _, c, _ in g["itens"]) > 400.0:
                continue                              # longe do plano da face
            bh = [_dot(q, h) for q in b.vertices]
            if min(bh) > h1 - 50.0 or max(bh) < h0 + 50.0:
                continue                              # não passa atrás da face
            zb = min(q[2] for q in b.vertices)
            if zb > z0f + 1500.0:
                continue
            if mais_baixa is None or zb < mais_baixa:
                mais_baixa = zb
        if mais_baixa is None:
            continue
        for e, _, _ in g["itens"]:
            z0 = min(q[2] for q in e.vertices)
            delta = z0 - (mais_baixa - SAIA_TELHA)
            if abs(delta) > 0.5 and abs(delta) < 2000.0:
                fora[e.id] = round(delta, 1)
    return fora

def aplicar_saias(posicoes, pecas, md: Optional[dict] = None) -> Dict[str, float]:
    """Põe em cada posição de telha de fachada o `saia` (mm que a ponta de baixo desce para
    ficar SAIA_TELHA abaixo da última longarina): a compra, a célula e a lista usam o
    comprimento com a saia. Devolve {id da peça: desloc} para a paginação."""
    from nucleo2d.detalhe.base import marcas_de
    md = md if md is not None else multidobras(pecas)
    ignorar = {i for t in md.get("telhas", []) for i in t.get("ids", [])}
    por_peca = saias_de_fachada(pecas, ignorar)
    por_marca: Dict[str, float] = {}
    for e in pecas:
        v = por_peca.get(e.id)
        if v is None:
            continue
        m = _posicao(e)
        if m not in por_marca or abs(v) > abs(por_marca[m]):
            por_marca[m] = v
    for p in posicoes:
        if p.classe != "telha":
            continue
        vals = [por_marca[m] for m in marcas_de(p) if m in por_marca]
        if vals:
            p.saia = max(vals, key=abs)
            p.observacoes.append("saia: desce %d mm abaixo da última longarina (%+d mm no comprimento)" % (SAIA_TELHA, round(p.saia)))
    return por_peca
