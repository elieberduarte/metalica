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
from nucleo2d.detalhe.base import _marcas, _dot, _sub, _norm, _cruz

#: Peça mais curta que isto (mm) na fileira é faceta da dobra; a reta é bem mais longa.
FACETA_MAX = 400.0


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


def _analisar_instancia(inst) -> Optional[dict]:
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
    h = sorted(altura_onda)[len(altura_onda) // 2]
    R_int, R_ext = R - h / 2, R + h / 2
    peso = sum(_volume(e) for e in inst) * RHO_ACO
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
            "p1": p1, "p2": p2, "d1": d1, "d2": d2, "I": I, "T": T, "sentido": 1 if theta > 0 else -1}


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
        meio = arco[len(arco) // 2]
        cx, cy = T(centro)
        mx, my = T(meio)
        p.linha(cx, cy, mx, my, "VISTA-FINA")
        p.texto((cx + mx) / 2, (cy + my) / 2, "R%s" % fmt(raio_v), 2.2 * esc)
        p.texto(mx, my + 3.0 * esc, "arco %s · %s°" % (fmt(arco_v), ("%.1f" % md["angulo"]).replace(".", ",")), 2.2 * esc)
        p.texto(0, painel_y + alt + 22.0 * esc, "%s  %s mm" % (titulo, fmt(desenv)), 3.0 * esc)
        painel_y += alt + 60.0 * esc
    comp = ", ".join("%s x%d" % (k, q) for k, q in sorted(md["composicao"].items(), key=lambda kv: _ordem_natural(kv[0])))
    linhas = ["TELHA MULTI-DOBRA",
              "%s – %02dx  (%s)" % (nome or md["conjunto"], md["instancias"], md["conjunto"]),
              "%s  %s  largura de compra 980 mm" % (md["perfil"], md["material"]),
              "retas %s + %s mm · raio int. %s / ext. %s · %s°" % (fmt(md["reta1"]), fmt(md["reta2"]), fmt(md["raio_int"]),
                                                               fmt(md["raio_ext"]), ("%.1f" % md["angulo"]).replace(".", ",")),
              "desenvolvida: ext. %s mm · int. %s mm   %s kg/pç  total %s kg" % (
                  fmt(md["desenv_ext"]), fmt(md["desenv_int"]), ("%.2f" % md["peso"]).replace(".", ","),
                  ("%.1f" % (md["peso"] * md["instancias"])).replace(".", ",")),
              "no modelo: %s (facetas de %s)" % (comp, md["conjunto"])]
    y = painel_y + 4.0 * esc
    for i, txt in enumerate(reversed(linhas)):
        altura = 3.5 if i == len(linhas) - 1 else 2.5
        p.texto(0, y, txt, altura * esc)
        y += (altura + 1.2) * esc
    return p.extremos


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
        perfil = _analisar_instancia(insts[0])
        if perfil is None:
            continue
        perfil.update(conjunto=conj, instancias=len(insts), composicao=dict(unidade),
                      ids=[e.id for i in insts for e in i])
        telhas.append(perfil)
        for i in insts:
            for e in i:
                usadas[_posicao(e)] += 1
    consumidas = {p for p, n in usadas.items() if n >= todas_por_pos.get(p, 0)}
    return {"telhas": telhas, "posicoes": consumidas}


# ============================================================ paginação
def faces_de_telhas(pecas: Sequence, md: Optional[dict] = None, nome_de=None) -> List[dict]:
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
    feitas_md = set()
    chapas = []
    for e in pecas:
        m = _marcas(e)
        if not _eh_telha(str(m.get("perfil") or e.nome or "")):
            continue
        c, eixos, ext = _medidas(e)
        t = em_md.get(e.id)
        if t is not None:
            # só o trecho reto mais longo de cada multi-dobra representa a telha
            if ext[0] < 0.5 * max(t["reta1"], t["reta2"]):
                continue

        # normal da chapa: o eixo de menor extensão (altura da onda); para cima ou para fora
        n = _norm(eixos[2])
        if n[2] < -1e-6 or (abs(n[2]) < 1e-6 and (n[0] + n[1]) < 0):
            n = (-n[0], -n[1], -n[2])
        # comprimento: o maior eixo; largura o do meio (a onda corre no comprimento)
        chapas.append({"e": e, "c": c, "n": n, "u": _direcao_da_onda(e, n), "ext": ext, "multidobra": t,
                       "nome": (t["nome"] if t is not None and t.get("nome") else nome_de(_posicao(e)))})
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
            lista.append({"contorno": contorno, "comprimento": comp, "nome": ch["nome"],
                          "x": (min(xs) + max(xs)) / 2, "y0": min(ys), "y1": max(ys),
                          "multidobra": bool(ch["multidobra"])})
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
    for ch in sorted(chapas, key=lambda c: c["x"]):
        p.polilinha([T(q) for q in ch["contorno"]], fechada=True, camada="ACO")
        xm = ch["x"] - x0
        a, b = (xm, ch["y0"] - y0), (xm, ch["y1"] - y0)
        texto = "%d" % round(ch["comprimento"])
        desenho.add(Cota(modo="v", p1=p._p(*a), p2=p._p(*b), deslocamento=0.0, texto=texto, altura=1.8,
                         atributos=dict(atr, chapa=ch["nome"])))
        p.texto(xm, ch["y0"] - y0 - 4.0 * esc, ch["nome"], 1.8 * esc, angulo=90.0, alinhamento="direita")
    alt = max(q[1] for ch in chapas for q in ch["contorno"]) - y0
    cont = collections.Counter(ch["nome"] for ch in chapas)
    resumo = " · ".join("%s %dx" % (k, q) for k, q in sorted(cont.items(), key=lambda kv: _ordem_natural(kv[0])))
    titulo = "FACE %d – %s%s – %d chapas" % (indice, face["tipo"].upper(),
                                            (" (%.0f°)" % face["inclinacao"]) if face["tipo"] == "cobertura" else "",
                                            len(chapas))
    p.texto(0, alt + 6.0 * esc, titulo, 3.5 * esc)
    p.texto(0, alt + 2.0 * esc, resumo[:220], 2.0 * esc)
    return p.extremos