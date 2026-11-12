# -*- coding: utf-8 -*-
"""Explodir com critério: o sólido que chega do SketchUp com tudo dentro vira as peças da obra (usuário, 12/11, pelo GESTÃO:
"explodir os elementos — não todos peçinha por peçinha, mas com um critério: o que está junto por um motivo fica junto.
Tesouras: não precisa explodir as partes da tesoura, ela pode ser UM elemento"; aprovado na amostra
Projeto/BRIEFINGS/imagens/explodir-criterio/amostra-1-explodir-com-criterio.png: "pode seguir, preciso explodir o galpão viena").

O IFC que o SketchUp exporta de um modelo vindo de DWG chega como UM objeto (o Galpão Viena: um IfcBuildingElementProxy com
64 malhas pela cor, 1.903 pedaços soltos dentro) e sem os grupos. O critério sai da geometria:

  1. cada pedaço de malha ligado (faces que dividem vértices) é uma peça; nunca é cortado — a não ser os dois perfis I
     iguais lado a lado numa malha só (a viga mestra dupla), que viram dois, como na importação do .skp (ifc/skp.py);
  2. TRELIÇA: barras longas PARALELAS (os banzos) ligadas por 3 ou mais peças leves (diagonais, montantes) = UM elemento —
     um grupo do editor com os banzos, a alma e as presilhas (as chapinhas que só encostam nos banzos) dentro; cada peça
     de dentro continua com o perfil dela, para a lista de materiais;
  3. o resto: cada pedaço uma peça, com o perfil lido na seção (I soldado "PS h×b×tw×tf" ou o W do catálogo, U, barra
     redonda, chapa "PLATE c×l×t"); o que não se lê fica "Seção b×h (a confirmar)".

Medidas em mm. A rota é POST /api/explodir-criterio (app.py); o editor aplica numa entrada só do desfazer
(web/editor3d/modulos/explodir.js, explodirComCriterio)."""
import collections
import math
from typing import Dict, List, Optional

import numpy as np

#: limites das famílias (mm)
ALMA_L_MAX = 3500.0          # diagonal/montante: mais curta que isto…
ALMA_SECAO_MAX = 170.0       # …e com a seção até isto
PRESILHA_SECAO_MAX = 70.0    # chapinha (presilha): seção até isto e…
PRESILHA_L_MAX = 1200.0      # …mais curta que isto
BANZO_L_MIN = 3500.0         # banzo: barra longa
BANZO_DIST = (50.0, 3000.0)  # distância entre dois banzos da mesma treliça
ALMA_MIN = 3                 # peças de alma ligando o par de banzos
TOQUE = 3.0                  # folga do contato

CAMADAS = {"Treliças": "#c0392b", "Pilares": "#34495e", "Vigas": "#2e86c1", "Contraventos": "#27ae60",
           "Chapas": "#e67e22", "A confirmar": "#8e44ad"}
PREFIXO = {"Pilares": "P", "Vigas": "V", "Contraventos": "CV", "Chapas": "CH", "A confirmar": "X"}


# ------------------------------------------------------------------ pedaços

def pedacos(faces: List[List[int]], n_vertices: int) -> List[List[int]]:
    """As faces agrupadas pelos pedaços ligados (faces que dividem um vértice)."""
    par = list(range(n_vertices))

    def raiz(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for f in faces:
        r = raiz(f[0])
        for j in f[1:]:
            rj = raiz(j)
            if rj != r:
                par[rj] = r
    grupos: Dict[int, List[int]] = collections.defaultdict(list)
    for i, f in enumerate(faces):
        if f:
            grupos[raiz(f[0])].append(i)
    return list(grupos.values())


def _quadro(X: np.ndarray) -> dict:
    """Eixo (a maior direção), as duas direções da seção e as medidas do pedaço."""
    c = X.mean(0)
    if len(X) >= 3:
        _u, _s, vt = np.linalg.svd(X - c, full_matrices=False)
        a = vt[0]
    else:
        a = np.array([1.0, 0.0, 0.0])
    if a[int(np.argmax(np.abs(a)))] < 0:
        a = -a
    if abs(a[2]) > 0.9:
        e1 = np.array([1.0, 0.0, 0.0])
        e1 = e1 - np.dot(e1, a) * a
    else:
        e1 = np.cross([0.0, 0.0, 1.0], a)
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    t, u, v = (X - c) @ a, (X - c) @ e1, (X - c) @ e2
    return {"c": c, "a": a, "e1": e1, "e2": e2, "L": float(np.ptp(t)), "b": float(np.ptp(u)), "h": float(np.ptp(v)),
            "lim": np.array([[t.min(), u.min(), v.min()], [t.max(), u.max(), v.max()]]),
            "mn": X.min(0), "mx": X.max(0)}


def _caixa(q: dict, folga: float):
    """A caixa orientada do pedaço: (centro, eixos 3×3, meias medidas) com a folga."""
    R = np.stack([q["a"], q["e1"], q["e2"]])
    meio = (q["lim"][0] + q["lim"][1]) / 2.0
    return q["c"] + meio @ R, R, (q["lim"][1] - q["lim"][0]) / 2.0 + folga / 2.0


def _toca(qa: dict, qb: dict, folga: float = TOQUE) -> bool:
    """As caixas orientadas dos dois pedaços se cruzam (com a folga): os 15 eixos separadores. Antes era "um vértice de um
    dentro da caixa do outro" — a presilha que passa do banzo em cima e embaixo não tem vértice nenhum dentro dele."""
    ca, A, ea = _caixa(qa, folga)
    cb, B, eb = _caixa(qb, folga)
    t = cb - ca
    eixos = [A[i] for i in range(3)] + [B[i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            x = np.cross(A[i], B[j])
            n = np.linalg.norm(x)
            if n > 1e-6:
                eixos.append(x / n)
    for L in eixos:
        ra = float(np.sum(ea * np.abs(A @ L)))
        rb = float(np.sum(eb * np.abs(B @ L)))
        if abs(float(t @ L)) > ra + rb:
            return False
    return True


# ------------------------------------------------------------------ seção

def _valores(x: np.ndarray, tol: float = 0.6) -> List[float]:
    s = sorted(float(v) for v in x)
    out: List[float] = []
    for v in s:
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _num(v: float) -> str:
    r = round(v, 2)
    if abs(r - round(r)) < 0.05:
        return "%d" % round(r)
    return ("%.2f" % r).rstrip("0").rstrip(".").replace(".", ",")


def _catalogo_w():
    try:
        from nucleo.perfis import banco
        return [p for p in banco().lista("I") if p.nome.upper().startswith(("W", "HP"))]
    except Exception:                                           # noqa: BLE001 — sem o catálogo, o PS pelas medidas
        return []


#: espessuras de chapa dobrada (mm): a lida pela área vai à mais perto (dentro de 8 %)
ESPESSURAS = (0.95, 1.25, 1.55, 1.95, 2.0, 2.25, 2.65, 3.0, 3.35, 3.75, 4.25, 4.75, 5.0, 6.3, 8.0)


def _espessura(t: float) -> float:
    perto = min(ESPESSURAS, key=lambda e: abs(e - t))
    return perto if abs(perto - t) <= 0.08 * perto else round(t, 2)


def _dobrado(V: List[float], b: float, h: float, area: float) -> Optional[str]:
    """U ou Ue dobrado de canto arredondado (muitos valores perto das pontas): a altura é a maior medida, a aba (o
    enrijecedor) é o valor que sobra no meio da altura, a espessura sai da área (área ÷ a linha média)."""
    alt, larg = max(b, h), min(b, h)
    if area <= 0:
        return None
    t = area / (alt + 2 * larg)
    d = 0.0
    for _ in range(3):
        meio = [x - V[0] for x in V if V[0] + 2 * t + 1 < x < V[-1] - 2 * t - 1]
        d = min(meio) if meio else 0.0
        lm = (alt - t) + 2 * (larg - t) + (2 * (d - t / 2) if d else 0.0)
        t = area / lm if lm > 0 else t
    if not (0.4 <= t <= 0.2 * larg):
        return None
    t = _espessura(t)
    if d:
        return "Ue %s×%s×%s×%s" % (_num(alt), _num(larg), _num(d), _num(t))
    return "U %s×%s×%s" % (_num(alt), _num(larg), _num(t))


def _redondo(d: float) -> str:
    """Ø em mm inteiro, o maior (regra 30/10: nunca meio mm; 15,88 = 5/8" → Ø16)."""
    return "Barra redonda Ø%d" % math.ceil(round(d, 1) - 0.05)


def ler_secao(X: np.ndarray, q: dict, area: Optional[float] = None) -> Optional[str]:
    """O perfil pela seção (os vértices projetados no plano da seção): I → W do catálogo ou "PS h×b×tw×tf"; U → "U h×b×t";
    o dobrado de canto arredondado → "U h×b×t" / "Ue h×b×d×t" (a espessura pela área); redondo → "Barra redonda Ø d";
    retângulo → "PLATE c×l×t" (chapa) ou "Barra chata l×t"; None quando não se lê."""
    Y = X - q["c"]
    u, v = Y @ q["e1"], Y @ q["e2"]
    b, h, L = q["b"], q["h"], q["L"]
    U, V = _valores(u), _valores(v)
    if abs(b - h) < 1.0 and b <= 120 and len(U) >= 5 and len(V) >= 5:
        return _redondo(max(b, h))
    if min(b, h) <= 25 and max(b, h) > 2500:
        return None                                    # a placa de 12,7 × 12.500 × 135.000 (a cobertura desenhada): a confirmar
    if len(U) == 2 and len(V) == 2:
        t, larg = min(b, h), max(b, h)
        if L < 12 * larg or larg >= 100:
            return "PLATE %sx%sx%s" % (_num(L), _num(larg), _num(t))
        return "Barra chata %s×%s" % (_num(larg), _num(t))
    # I: 4 valores numa direção (as mesas: 0, tf, h−tf, h) e 4 na outra (0, (b−tw)/2, (b+tw)/2, b)
    if len(U) == 4 and len(V) == 4:
        for alt, larg, A, B in ((h, b, V, U), (b, h, U, V)):
            tf = A[1] - A[0]
            tw = B[2] - B[1]
            if tf < 0.25 * alt and abs((B[1] - B[0]) - (B[3] - B[2])) < 1.0 and tw < 0.5 * larg and A[2] - A[1] > alt / 2:
                for w in _catalogo_w():
                    if abs(w.d - alt) <= 3 and abs(w.bf - larg) <= 3 and abs((w.tw or 0) - tw) <= 1.5 and abs((w.tf or 0) - tf) <= 1.5:
                        return w.nome
                return "PS %s×%s×%s×%s" % (_num(alt), _num(larg), _num(tw), _num(tf))
    # U: 3 valores na direção da largura (0, tw, b) e 4 na altura (0, tf, h−tf, h)
    for (A, B, alt, larg) in ((V, U, h, b), (U, V, b, h)):
        if len(A) == 4 and len(B) == 3:
            tf, tw = A[1] - A[0], min(B[1] - B[0], B[2] - B[1])
            if tf < 0.3 * alt:
                return "U %s×%s×%s" % (_num(alt), _num(larg), _num(max(tf, tw)))
    # dobrado de canto arredondado: muitos valores, só perto das pontas (e da aba)
    if area and (len(U) > 4 or len(V) > 4) and max(b, h) <= 400:
        return _dobrado(V if h >= b else U, b, h, area)
    return None


def _dois_perfis(X: np.ndarray, q: dict) -> Optional[int]:
    """Dois perfis I iguais lado a lado numa malha só (a viga mestra dupla do Galpão Viena: 2 PS 800×300 encostados): na
    largura, as duas metades iguais — 0, x1, x2, meio, meio+x1, meio+x2, fim (7 valores; 8 com folga entre eles); a outra
    direção com as 4 das mesas. A direção (1 = e1, 2 = e2) para cortar, ou None."""
    Y = X - q["c"]
    for k, eixo, outro in ((1, q["e1"], q["e2"]), (2, q["e2"], q["e1"])):
        W = [x - _valores(Y @ eixo)[0] for x in _valores(Y @ eixo)]
        if len(_valores(Y @ outro)) != 4 or len(W) not in (7, 8):
            continue
        a_ = W[:4] if len(W) == 8 else W[:4]
        b_ = W[4:] if len(W) == 8 else W[3:]
        larg = a_[3] - a_[0]
        if larg > 0 and all(abs((b_[i] - b_[0]) - (a_[i] - a_[0])) < 1.0 for i in range(4))                 and abs((a_[1] - a_[0]) - (a_[3] - a_[2])) < 1.0:
            return k
    return None


# ------------------------------------------------------------------ o critério

def explodir(vertices, faces, nome: str = "") -> dict:
    """{"pecas": [{nome, camada, vertices, faces, atributos}], "grupos": [{nome, membros (índices em pecas), atributos}],
    "resumo": {...}} — veja o cabeçalho do módulo."""
    V = np.asarray(vertices, dtype=float)
    F = [list(map(int, f)) for f in faces]
    if len(V) == 0 or not F:
        return {"pecas": [], "grupos": [], "resumo": {"pedacos": 0}}
    partes = []          # {faces, vidx, X, q}
    for fs in pedacos(F, len(V)):
        vidx = sorted({j for i in fs for j in F[i]})
        X = V[vidx]
        partes.append({"faces": fs, "vidx": vidx, "X": X, "q": _quadro(X)})

    # a viga dupla numa malha só: dois perfis
    novas = []
    for p in partes:
        q = p["q"]
        k = _dois_perfis(p["X"], q) if q["L"] >= BANZO_L_MIN and max(q["b"], q["h"]) > ALMA_SECAO_MAX else None
        if not k:
            novas.append(p)
            continue
        eixo = q["e1"] if k == 1 else q["e2"]
        pos = {j: float((V[j] - q["c"]) @ eixo) for j in p["vidx"]}
        lados = ([], [])
        for i in p["faces"]:
            lados[0 if sum(pos[j] for j in F[i]) / len(F[i]) < 0 else 1].append(i)
        if not (lados[0] and lados[1]):
            novas.append(p)
            continue
        for fs in lados:
            vidx = sorted({j for i in fs for j in F[i]})
            X = V[vidx]
            novas.append({"faces": fs, "vidx": vidx, "X": X, "q": _quadro(X), "dupla": True})
    partes = novas
    n = len(partes)
    Q = [p["q"] for p in partes]
    sec = [max(q["b"], q["h"]) for q in Q]
    presilha = [sec[i] <= PRESILHA_SECAO_MAX and Q[i]["L"] < PRESILHA_L_MAX for i in range(n)]
    alma = [Q[i]["L"] < ALMA_L_MAX and sec[i] <= ALMA_SECAO_MAX and not presilha[i] for i in range(n)]
    longa = [Q[i]["L"] >= BANZO_L_MIN and sec[i] > 20 for i in range(n)]
    mn = np.array([q["mn"] for q in Q])
    mx = np.array([q["mx"] for q in Q])

    def vizinhas(i, filtro):
        cand = np.where(np.all(mn <= Q[i]["mx"] + TOQUE, 1) & np.all(mx >= Q[i]["mn"] - TOQUE, 1))[0]
        return [int(j) for j in cand if j != i and filtro[j] and _toca(Q[i], Q[j])]

    toca_longa = {i: vizinhas(i, longa) for i in range(n) if alma[i] or presilha[i]}
    # pares de banzos: paralelos, a uma distância de treliça, ligados por ≥ ALMA_MIN peças de alma
    pares = collections.Counter()
    for i in range(n):
        if not alma[i]:
            continue
        L_ = toca_longa[i]
        for x in range(len(L_)):
            for y in range(x + 1, len(L_)):
                a, b = L_[x], L_[y]
                if abs(float(np.dot(Q[a]["a"], Q[b]["a"]))) < 0.99:
                    continue
                d = Q[b]["c"] - Q[a]["c"]
                perp = float(np.linalg.norm(d - np.dot(d, Q[a]["a"]) * Q[a]["a"]))
                if BANZO_DIST[0] < perp < BANZO_DIST[1]:
                    pares[(min(a, b), max(a, b))] += 1
    par: Dict[int, int] = {}

    def raiz(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for (a, b), k in pares.items():
        if k >= ALMA_MIN:
            par[raiz(a)] = raiz(b)
    banzos_de: Dict[int, set] = collections.defaultdict(set)
    for x in list(par):
        banzos_de[raiz(x)].add(x)
    trelicas = [{"banzos": g, "alma": set(), "pres": set()} for g in banzos_de.values()]
    tr_do_banzo = {k: i for i, t in enumerate(trelicas) for k in t["banzos"]}
    for i in range(n):
        if alma[i]:
            c = collections.Counter(tr_do_banzo[j] for j in toca_longa[i] if j in tr_do_banzo)
            if c:
                trelicas[c.most_common(1)[0][0]]["alma"].add(i)
    na_alma = {i: k for k, t in enumerate(trelicas) for i in t["alma"]}
    for i in range(n):                                  # montante da ponta (só toca a alma)
        if alma[i] and i not in na_alma:
            for j in vizinhas(i, alma):
                if j in na_alma:
                    trelicas[na_alma[j]]["alma"].add(i)
                    na_alma[i] = na_alma[j]
                    break
    for i in range(n):
        if presilha[i]:
            for j in toca_longa[i]:
                if j in tr_do_banzo:
                    trelicas[tr_do_banzo[j]]["pres"].add(i)
                    break
    trelicas = [t for t in trelicas if len(t["alma"]) >= ALMA_MIN]
    trelicas.sort(key=lambda t: tuple(np.round(np.mean([Q[k]["c"] for k in t["banzos"]], 0), -2)))
    da_trelica = {}
    for k, t in enumerate(trelicas):
        for i in t["banzos"] | t["alma"] | t["pres"]:
            da_trelica[i] = k

    # as peças
    pecas, assin, cont = [], {}, collections.Counter()
    resumo = collections.Counter()
    for i, p in enumerate(partes):
        q, X = Q[i], p["X"]
        try:
            from nucleo3d.geometria import volume_malha
            mapa0 = {j: k for k, j in enumerate(p["vidx"])}
            area = abs(volume_malha([tuple(x) for x in X], [[mapa0[j] for j in F[f]] for f in p["faces"]])) / max(q["L"], 1.0)
        except Exception:                                       # noqa: BLE001 — malha aberta: sem a área
            area = None
        perfil = ler_secao(X, q, area)
        if i in da_trelica:
            camada = "Treliças"
        elif perfil and perfil.startswith("Barra redonda"):
            camada = "Contraventos"
        elif perfil and perfil.startswith(("PLATE", "Barra chata")):
            camada = "Chapas"
        elif perfil and abs(q["a"][2]) > 0.9:
            camada = "Pilares"
        elif perfil:
            camada = "Vigas"
        else:
            camada = "A confirmar"
        perfil = perfil or "Seção %s×%s (a confirmar)" % (_num(min(q["b"], q["h"])), _num(max(q["b"], q["h"])))
        mapa = {j: k for k, j in enumerate(p["vidx"])}
        fs = [[mapa[j] for j in F[f]] for f in p["faces"]]
        if i in da_trelica:
            prefixo = "TR%d-" % (da_trelica[i] + 1)
        else:
            prefixo = PREFIXO[camada]
        k = (prefixo, perfil, round(q["L"]), len(p["vidx"]))
        if k not in assin:
            cont[prefixo] += 1
            assin[k] = "%s%d" % (prefixo, cont[prefixo])
        marcas = {"posicao": assin[k], "perfil": perfil, "conjunto": ("TR%d" % (da_trelica[i] + 1)) if i in da_trelica else assin[k]}
        atr = {"marcas": marcas, "tipo_ifc": "IfcMember" if camada in ("Treliças", "Contraventos") else
               "IfcColumn" if camada == "Pilares" else "IfcBeam" if camada == "Vigas" else
               "IfcPlate" if camada == "Chapas" else "IfcBuildingElementProxy",
               "explodido_de": {"nome": nome, "criterio": "explodir_com_criterio"}}
        if p.get("dupla"):
            atr["explodido_de"]["viga_dupla"] = True
        pecas.append({"nome": perfil, "camada": camada, "vertices": [[round(float(c), 3) for c in v] for v in X],
                      "faces": fs, "atributos": atr})
        resumo[camada] += 1
    grupos = []
    for k, t in enumerate(trelicas):
        membros = sorted(t["banzos"] | t["alma"] | t["pres"])
        L = max(Q[j]["L"] for j in t["banzos"])
        grupos.append({"nome": "TR%d · treliça %s m" % (k + 1, _num(L / 1000.0)), "membros": membros,
                       "atributos": {"treliça": {"banzos": len(t["banzos"]), "alma": len(t["alma"]),
                                                 "presilhas": len(t["pres"]), "comprimento": round(L)}}})
    return {"pecas": pecas, "grupos": grupos,
            "resumo": {"pedacos": n, "trelicas": len(trelicas),
                       "pecas_soltas": n - len(da_trelica), "por_camada": dict(resumo),
                       "vigas_duplas": sum(1 for p in partes if p.get("dupla")) // 2}}
