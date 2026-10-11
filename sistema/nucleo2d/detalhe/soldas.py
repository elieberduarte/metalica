# -*- coding: utf-8 -*-
"""As soldas de fábrica de um conjunto: chapa × perfil (auditoria D3, 2º passo — 11/10/2026).

Nos conjuntos (a tesoura, a viga com as chapas dela) a chapa que encosta num perfil sem parafuso que atravesse os dois é
soldada na fábrica: a chapa de nó com as cantoneiras, o suporte de terça no banzo, a chapa deitada na mesa. Dois tipos:

* **T** — a borda da chapa sobre um plano do perfil (a chapa perpendicular a ele): o cordão vai ao longo do encontro,
  um filete de cada lado da chapa;
* **sobreposição** — a chapa deitada no perfil (ou o perfil deitado na chapa de nó): os cordões seguem as arestas de cada
  peça que caem dentro da outra (a borda de cima sobre a face de baixo).

A malha do IFC vem triangulada: o trabalho é por plano (as faces coplanares do perfil juntas) e pelas arestas de contorno
dele. A perna é a mínima da NBR 8800:2024 (Tabela 11) pela parte menos espessa, limitada pela chapa fina (6.2.6.2.2).
Decisão do usuário (11/10): no desenho do conjunto vai uma nota geral e um símbolo "TÍP." por tipo; os metros, na lista.
"""
import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo2d.detalhe.base import _caixa, _cruz, _dot, _marcas, _norm, _sub

TOL_PLANO = 1.5          # mm: o vértice da chapa está no plano do perfil
MENOR_CORDAO = 15.0      # mm: encontro mais curto que isto não é cordão (o canto que só encosta)


def _tocam(a, b, folga: float) -> bool:
    return all(a[i][0] - folga <= b[i][1] and b[i][0] - folga <= a[i][1] for i in range(3))


def _normal(vs) -> Optional[Tuple[float, float, float]]:
    n = (0.0, 0.0, 0.0)
    for i in range(len(vs)):                             # Newell: vale para o polígono não convexo
        a, b = vs[i], vs[(i + 1) % len(vs)]
        n = (n[0] + (a[1] - b[1]) * (a[2] + b[2]), n[1] + (a[2] - b[2]) * (a[0] + b[0]), n[2] + (a[0] - b[0]) * (a[1] + b[1]))
    L = math.sqrt(_dot(n, n))
    return None if L < 1e-9 else (n[0] / L, n[1] / L, n[2] / L)


def planos(e) -> List[dict]:
    """os planos da malha: {n, d (= n·p), faces, arestas de contorno (pares de índices), área}"""
    grupos: List[dict] = []
    for f in e.faces:
        if len(f) < 3:
            continue
        vs = [e.vertices[i] for i in f]
        n = _normal(vs)
        if n is None:
            continue
        d = _dot(n, vs[0])
        g = next((g for g in grupos if _dot(g["n"], n) > 0.999 and abs(g["d"] - d) < 0.5), None)
        if g is None:
            g = {"n": n, "d": d, "faces": []}
            grupos.append(g)
        g["faces"].append(list(f))
    for g in grupos:
        conta = collections.Counter()
        for f in g["faces"]:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                conta[(min(a, b), max(a, b))] += 1
        g["contorno"] = [k for k, n in conta.items() if n == 1]      # a aresta de uma face só é a borda do plano
    return grupos


def _base_do_plano(n):
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_cruz(n, a))
    return e1, _norm(_cruz(n, e1))


def _dentro(pt, arestas2d) -> bool:
    """o ponto 2D dentro da região limitada pelas arestas (raio para a direita; vale para várias voltas e furos)"""
    x, y = pt
    dentro = False
    for (x1, y1), (x2, y2) in arestas2d:
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xc > x:
                dentro = not dentro
    return dentro


def _na_borda(pt, arestas2d, tol=1.0) -> bool:
    x, y = pt
    for (x1, y1), (x2, y2) in arestas2d:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= tol:
            return True
    return False


def _espessura(e, n) -> float:
    ws = [_dot(q, n) for q in e.vertices]
    return max(ws) - min(ws)


def _perna(t_a: float, t_b: float) -> float:
    from nucleo import materiais as _mat
    t = min(x for x in (t_a, t_b) if x > 0) if (t_a > 0 or t_b > 0) else 3.0
    perna = _mat.perna_minima(t / 10.0) * 10.0
    return round(min(perna, t), 1)


def _espessura_do_perfil(barra, n_face) -> float:
    """a espessura da parede do perfil (a menor entre mesa e alma, pelo catálogo); 0 sem o perfil no catálogo"""
    melhor = None
    try:
        from nucleo3d.geometria import resolver_perfil
        p = resolver_perfil(str(_marcas(barra).get("perfil") or barra.nome or ""))
        ts = [float(getattr(p, k, 0.0) or 0.0) for k in ("tf", "tw", "t")]
        ts = [t for t in ts if t > 0]
        if ts:
            melhor = min(ts)
    except Exception:                                   # noqa: BLE001
        melhor = None
    return melhor or 0.0


def cordoes_chapa_perfil(chapa, barra) -> List[dict]:
    """os cordões entre a chapa e o perfil que se tocam (T ou sobreposição); [] se só encostam"""
    from saida.detalhamento import _autovetores
    _, pca = _autovetores(chapa.vertices)
    n_p = _norm(tuple(pca[2]))
    t_p = _espessura(chapa, n_p)
    fora = []
    planos_c = None
    for g in planos(barra):
        n_f, d_f = g["n"], g["d"]
        perto = [q for q in chapa.vertices if abs(_dot(n_f, q) - d_f) <= TOL_PLANO]
        if len(perto) < 2:
            continue
        e1, e2 = _base_do_plano(n_f)
        borda_b = [((_dot(barra.vertices[a], e1), _dot(barra.vertices[a], e2)), (_dot(barra.vertices[b], e1), _dot(barra.vertices[b], e2)))
                   for a, b in g["contorno"]]
        c_perto = tuple(sum(q[j] for q in perto) / len(perto) for j in range(3))
        c2 = (_dot(c_perto, e1), _dot(c_perto, e2))
        cos = abs(_dot(n_f, n_p))
        t_b = _espessura_do_perfil(barra, n_f)
        if cos < 0.3:
            if not (_dentro(c2, borda_b) or _na_borda(c2, borda_b)):
                continue                                  # a borda da chapa no prolongamento do plano, fora da face
            # T: a borda da chapa no plano do perfil
            d = _norm(_cruz(n_f, n_p))
            s_c = [_dot(q, d) for q in perto]
            s_b = [_dot(barra.vertices[i], d) for f in g["faces"] for i in f]
            lo, hi = max(min(s_c), min(s_b)), min(max(s_c), max(s_b))
            if hi - lo < MENOR_CORDAO:
                continue
            s_m = _dot(c_perto, d)
            fora.append({"tipo": "T", "lados": 2, "comprimento": round(hi - lo, 1), "perna": _perna(t_p, t_b),
                         "p0": tuple(c_perto[j] + d[j] * (lo - s_m) for j in range(3)),
                         "p1": tuple(c_perto[j] + d[j] * (hi - s_m) for j in range(3))})
        elif cos > 0.95:
            # sobreposição: as arestas de cada uma que caem dentro da outra
            if planos_c is None:
                planos_c = planos(chapa)
            gc = next((h for h in planos_c if _dot(h["n"], n_f) < -0.95 and abs(-h["d"] - d_f) <= TOL_PLANO), None)
            if gc is None:
                continue
            borda_c = [((_dot(chapa.vertices[a], e1), _dot(chapa.vertices[a], e2)), (_dot(chapa.vertices[b], e1), _dot(chapa.vertices[b], e2)))
                       for a, b in gc["contorno"]]
            segs = []
            for (a2, b2), outra, (ia, ib), ent in [(s, borda_b, k, chapa) for s, k in zip(borda_c, gc["contorno"])] + \
                                                  [(s, borda_c, k, barra) for s, k in zip(borda_b, g["contorno"])]:
                meio = ((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2)
                if _dentro(meio, outra) and not _na_borda(meio, outra):
                    segs.append((ent.vertices[ia], ent.vertices[ib], math.dist(a2, b2)))
            total = sum(s[2] for s in segs)
            if total < MENOR_CORDAO:
                continue
            maior = max(segs, key=lambda s: s[2])
            fora.append({"tipo": "sobreposição", "lados": 1, "comprimento": round(total, 1), "perna": _perna(t_p, t_b),
                         "p0": maior[0], "p1": maior[1]})
    # um plano só por tipo: as faces do mesmo encontro (frente e verso da chapa) não contam duas vezes
    unicos = {}
    for c in fora:
        k = (c["tipo"], round(c["comprimento"]))
        unicos.setdefault(k, c)
    return list(unicos.values())


def soldas_do_conjunto(instancia: Sequence, fixadores: Sequence = ()) -> List[dict]:
    """os cordões de fábrica chapa × perfil de uma instância do conjunto (sem parafuso que passe pelos dois)"""
    from nucleo2d.detalhe.montagens import _eh_chapa
    chapas = [e for e in instancia if getattr(e, "vertices", None) and _eh_chapa(e)]
    barras = [e for e in instancia if getattr(e, "vertices", None) and not _eh_chapa(e)]
    cx_fix = [_caixa(f) for f in fixadores or ()]
    fora = []
    for ch in chapas:
        cxc = _caixa(ch)
        for b in barras:
            cxb = _caixa(b)
            if not _tocam(cxc, cxb, 1.0):
                continue
            if any(_tocam(cf, cxc, 0.5) and _tocam(cf, cxb, 0.5) for cf in cx_fix):
                continue                                  # aparafusada
            for c in cordoes_chapa_perfil(ch, b):
                c.update(chapa=ch.id, perfil=b.id)
                fora.append(c)
    return fora


def resumo(cordoes: Sequence[dict]) -> dict:
    """{metros (com os dois lados do T), pernas, por tipo}"""
    m = sum(c["comprimento"] * c["lados"] for c in cordoes) / 1000.0
    return {"m": round(m, 3), "pernas": sorted({c["perna"] for c in cordoes}),
            "tipos": collections.Counter(c["tipo"] for c in cordoes)}
