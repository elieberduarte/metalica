"""Modelo analítico: o esqueleto de nós e barras que o cálculo de esforços usa.

O modelo físico põe cada perfil no lugar dele — a terça meia altura acima do banzo, a viga
meia altura abaixo do nó, a cantoneira dupla em duas barras, uma de cada lado do plano da
treliça. Para ver a estrutura (e para calcular), cada peça é o eixo que liga um nó a outro:

1. o perfil duplo (a cantoneira dupla, a viga 2Ue) vira uma barra só, no meio dos dois — o
   "duplo" fica anotado para o detalhamento;
2. as pontas a menos de `TOL_NO` mm umas das outras viram o mesmo nó;
3. a ponta que não chegou em nada desce/sobe até a peça em que ela apoia (a terça no banzo de
   cima ou na viga, a viga no pilar, a corrente na terça, o pilar no banzo…), a até
   `TOL_APOIO` mm — é a excentricidade física, que volta no detalhamento; a peça de apoio ganha
   um nó ali;
4. a terça que passa por cima de outras treliças ganha um nó em cada uma (a viga, em cada banzo que cruza);
5. o que sobrar sem ligar é ponta solta: um erro de verdade do modelo.

`analitico(doc)` devolve {nos, barras, soltas, resumo}; cada barra lembra as ids das peças de
onde saiu, para o editor selecionar e pintar.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Tuple

TOL_NO = 60.0           # pontas mais perto que isso são o mesmo nó
TOL_DUPLO = 200.0       # as duas barras do perfil duplo: pontas a até isso uma da outra
TOL_APOIO = 450.0       # a peça desce/sobe até a de apoio a até isso (meia altura dos dois perfis)
TOL_CRUZA = 250.0       # a terça sobre o banzo que ela cruza: diferença de altura aceita
TOL_LADO = 200.0        # a treliça deitada presa pela lateral no banzo de outra: afastamento aceito

# em que cada papel apoia a ponta dele
APOIA_EM = {
    # a terça que chega na lateral da transição (mais alta que o telhado) encosta na alma dela
    "terça": ("banzo", "viga", "apoio_terca", "montante", "diagonal"),
    # o perfil ao lado da treliça que recebe as terças (o U da TRANSIÇÃO 1 do Posto CB): preso nela
    "apoio_terca": ("montante", "banzo", "diagonal", "pilar", "viga"),
    "corrente": ("terça",),
    "viga": ("pilar", "viga", "banzo"),
    "contraventamento": ("banzo", "pilar", "viga", "montante", "diagonal", "terça"),
    "pilar": ("banzo", "viga"),
    "banzo": ("pilar", "banzo", "viga", "montante"),
    # a alma da mão-francesa (PM6) termina na face do pilar, a meia seção do eixo
    "montante": ("banzo", "diagonal", "montante", "pilar", "viga"),
    "diagonal": ("banzo", "diagonal", "montante", "pilar", "viga"),
}
ALMA = ("montante", "diagonal")
TOL_ALMA = 120.0        # alma que chega no meio de outra barra de alma (o painel subdividido): bem perto

Ponto = Tuple[float, float, float]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _proj(p, a, b) -> Tuple[float, float, Ponto]:
    """distância de p ao segmento ab, o parâmetro t (0..1) e o ponto"""
    d = _sub(b, a)
    L2 = _dot(d, d)
    t = 0.0 if L2 <= 1e-9 else min(max(_dot(_sub(p, a), d) / L2, 0.0), 1.0)
    q = (a[0] + d[0] * t, a[1] + d[1] * t, a[2] + d[2] * t)
    return math.dist(p, q), t, q


def _entre_segmentos(a, b, c, d) -> Tuple[float, float, float, Ponto]:
    """a menor distância entre os segmentos ab e cd, os parâmetros t (em ab) e u (em cd) dos
    pontos mais próximos, e o ponto de cd"""
    u_ = _sub(b, a)
    v_ = _sub(d, c)
    w_ = _sub(a, c)
    A, B, C = _dot(u_, u_), _dot(u_, v_), _dot(v_, v_)
    D, E = _dot(u_, w_), _dot(v_, w_)
    den = A * C - B * B
    t = 0.0 if den < 1e-9 else min(max((B * E - C * D) / den, 0.0), 1.0)
    u = 0.0 if C < 1e-9 else min(max((B * t + E) / C, 0.0), 1.0)
    t = 0.0 if A < 1e-9 else min(max((B * u - D) / A, 0.0), 1.0)
    p = (a[0] + u_[0] * t, a[1] + u_[1] * t, a[2] + u_[2] * t)
    q = (c[0] + v_[0] * u, c[1] + v_[1] * u, c[2] + v_[2] * u)
    return math.dist(p, q), t, u, q


def _origem(ent) -> dict:
    return (getattr(ent, "atributos", None) or {}).get("origem") or {}


def _linhas_do(doc) -> List[dict]:
    """as peças como linhas: a barra do início ao fim; a calandrada pelos centros dos anéis"""
    out = []
    for ent in doc.entidades.values():
        o = _origem(ent)
        if ent.tipo == "barra":
            out.append({"a": tuple(ent.inicio), "b": tuple(ent.fim), "papel": ent.papel or "barra",
                        "peca": o.get("peca"), "grupo": o.get("peca") or o.get("planta") or ent.id,
                        "perfil": ent.perfil, "ids": [ent.id], "duplo": False,
                        "deitada": "deitada" in str(o.get("sentido") or "")})
        elif ent.tipo == "solido" and (ent.atributos or {}).get("calandrada") and ent.faces:
            v = ent.vertices
            k = len(ent.faces[0])
            if k < 3 or len(v) % k or len(v) // k < 2:
                continue
            c = [tuple(sum(v[j][m] for j in range(i, i + k)) / k for m in range(3)) for i in range(0, len(v), k)]
            for a, b in zip(c, c[1:]):
                out.append({"a": a, "b": b, "papel": "banzo", "peca": o.get("peca"),
                            "grupo": o.get("peca") or ent.id, "perfil": ent.nome, "ids": [ent.id], "duplo": False,
                            "curva": True})
        elif ent.tipo == "solido" and ent.vertices:
            # peça importada (IFC): a linha pela direção em que ela é mais comprida; a chapa não
            # é barra. Sem o papel dela, a ponta não vira alarme de peça solta
            from nucleo3d.apoios import _eixo_do_solido, _papel_do_solido
            papel = _papel_do_solido(ent)
            if papel == "chapa":
                continue
            (a, b), = _eixo_do_solido([tuple(p) for p in ent.vertices])[0][:1]
            if math.dist(a, b) < 50.0:
                continue
            out.append({"a": a, "b": b, "papel": papel, "peca": o.get("peca"), "grupo": o.get("peca") or ent.id,
                        "perfil": ent.nome, "ids": [ent.id], "duplo": False, "importada": True})
    return out


def _juntar_duplos(linhas: List[dict]) -> Tuple[List[dict], int]:
    """o perfil duplo (duas barras paralelas lado a lado, da mesma peça e do mesmo papel) vira
    uma barra só, no meio das duas"""
    grupos = collections.defaultdict(list)
    for i, ln in enumerate(linhas):
        if not ln.get("curva"):
            grupos[(ln["grupo"], ln["papel"], ln["perfil"])].append(i)
    fora = set()
    novas = []
    for idx in grupos.values():
        if len(idx) < 2:
            continue
        for x in range(len(idx)):
            i = idx[x]
            if i in fora:
                continue
            a1, b1 = linhas[i]["a"], linhas[i]["b"]
            for y in range(x + 1, len(idx)):
                j = idx[y]
                if j in fora:
                    continue
                a2, b2 = linhas[j]["a"], linhas[j]["b"]
                if math.dist(a1, a2) < TOL_DUPLO and math.dist(b1, b2) < TOL_DUPLO:
                    pa, pb = a2, b2
                elif math.dist(a1, b2) < TOL_DUPLO and math.dist(b1, a2) < TOL_DUPLO:
                    pa, pb = b2, a2
                else:
                    continue
                if max(math.dist(a1, pa), math.dist(b1, pb)) < 1.0:
                    continue                                 # a mesma barra repetida, não o par
                fora.update((i, j))
                ln = dict(linhas[i])
                ln["a"] = tuple((a1[m] + pa[m]) / 2 for m in range(3))
                ln["b"] = tuple((b1[m] + pb[m]) / 2 for m in range(3))
                ln["ids"] = linhas[i]["ids"] + linhas[j]["ids"]
                ln["duplo"] = True
                novas.append(ln)
                break
    return [ln for i, ln in enumerate(linhas) if i not in fora] + novas, len(novas)


class _Grade:
    def __init__(self, cel: float):
        self.cel = cel
        self.c = collections.defaultdict(list)

    def chave(self, p):
        return (int(math.floor(p[0] / self.cel)), int(math.floor(p[1] / self.cel)), int(math.floor(p[2] / self.cel)))

    def por(self, p, item):
        self.c[self.chave(p)].append(item)

    def perto(self, p, r=1):
        cx, cy, cz = self.chave(p)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    yield from self.c.get((cx + dx, cy + dy, cz + dz), ())


def analitico(doc, base: Optional[float] = None) -> dict:
    linhas, duplos = _juntar_duplos(_linhas_do(doc))
    if base is None:
        zs = [ln[k][2] for ln in linhas if ln["papel"] == "pilar" for k in ("a", "b")]
        base = min(zs) if zs else 0.0

    # --- 2. as pontas perto umas das outras viram o mesmo nó (união das pontas próximas)
    pts: List[Ponto] = []
    for ln in linhas:
        pts += [ln["a"], ln["b"]]
    pai = list(range(len(pts)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    g = _Grade(TOL_NO)
    for i, p in enumerate(pts):
        for j in g.perto(p):
            if math.dist(p, pts[j]) <= TOL_NO:
                ri, rj = raiz(i), raiz(j)
                if ri != rj:
                    pai[ri] = rj
        g.por(p, i)
    grupo_no: Dict[int, int] = {}
    nos: List[List[float]] = []
    soma = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    for i, p in enumerate(pts):
        s = soma[raiz(i)]
        s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3] += 1
    for r, s in soma.items():
        grupo_no[r] = len(nos)
        nos.append([s[0] / s[3], s[1] / s[3], s[2] / s[3]])
    for k, ln in enumerate(linhas):
        ln["na"] = grupo_no[raiz(2 * k)]
        ln["nb"] = grupo_no[raiz(2 * k + 1)]

    def grau():
        gr = collections.Counter()
        for ln in linhas:
            gr[ln["na"]] += 1
            gr[ln["nb"]] += 1
        return gr

    # índice das linhas por onde passam (para achar o apoio)
    gl = _Grade(1000.0)
    for k, ln in enumerate(linhas):
        a, b = nos[ln["na"]], nos[ln["nb"]]
        n = int(math.dist(a, b) // 500.0) + 1
        vistos = set()
        for j in range(n + 1):
            p = tuple(a[m] + (b[m] - a[m]) * j / n for m in range(3))
            ch = gl.chave(p)
            if ch not in vistos:
                vistos.add(ch)
                gl.c[ch].append(k)

    cortes = collections.defaultdict(list)       # linha -> [(t, nó)] onde ganha um nó
    # os nós por lugar: o nó novo no meio de uma linha é o que já existe ali, se houver (o topo do
    # pilar em que a TRELIÇA 10 do Posto CB desceu ficava a 4 mm do nó das TRELIÇAS 9 e 13, sem
    # ligar as duas)
    gn = _Grade(2 * TOL_NO)
    for i_n, p_n in enumerate(nos):
        gn.por(p_n, i_n)

    def no_em(k, q, t):
        """o nó na linha k no ponto q: a ponta dela, se perto; o nó que já existe ali (a linha é
        cortada nele); senão um nó novo que a corta ali"""
        ln = linhas[k]
        a, b = nos[ln["na"]], nos[ln["nb"]]
        if math.dist(q, a) <= 2 * TOL_NO:
            return ln["na"]
        if math.dist(q, b) <= 2 * TOL_NO:
            return ln["nb"]
        for t2, n2 in cortes[k]:
            if math.dist(nos[n2], q) <= 2 * TOL_NO:
                return n2
        perto = min((n2 for n2 in gn.perto(q) if math.dist(nos[n2], q) <= 2 * TOL_NO),
                    key=lambda n2: math.dist(nos[n2], q), default=None)
        if perto is not None:
            cortes[k].append((t, perto))
            return perto
        nos.append([q[0], q[1], q[2]])
        gn.por(q, len(nos) - 1)
        cortes[k].append((t, len(nos) - 1))
        return len(nos) - 1

    # --- 2b. a alma no banzo da própria treliça: o banzo desenhado de ponta a ponta numa barra só
    # ganha um nó em cada montante e diagonal que chega nele (sem isso a alma ficava presa só nas
    # pontas do banzo e a treliça não trabalhava — o pilar do meio da TESOURA 2 do Posto CB, sob o
    # banzo contínuo, não recebia quase nada)
    na_alma = 0
    for k, ln in enumerate(linhas):
        if ln["papel"] not in ALMA:
            continue
        for lado in ("na", "nb"):
            n = ln[lado]
            p = nos[n]
            for j in set(gl.perto(p)):
                lj = linhas[j]
                if lj["papel"] != "banzo" or lj["grupo"] != ln["grupo"] or n in (lj["na"], lj["nb"]):
                    continue
                dd, t, _q = _proj(p, nos[lj["na"]], nos[lj["nb"]])
                if dd <= 2 * TOL_NO and 0.0 < t < 1.0 and all(n2 != n for _t2, n2 in cortes[j]):
                    cortes[j].append((t, n))
                    na_alma += 1

    # --- 2c. a treliça deitada presa pela lateral: o banzo dela que corre colado e paralelo ao
    # banzo de outra treliça, no mesmo nível, liga nele em cada nó (a passarela do Posto CB, a
    # TRELIÇA 1 deitada, corre 24 m a 11 cm do banzo de baixo da TRANSIÇÃO 16 e ficava solta)
    ao_lado = 0
    for k, ln in enumerate(linhas):
        if not ln.get("deitada") or ln["papel"] != "banzo":
            continue
        a, b = nos[ln["na"]], nos[ln["nb"]]
        dk = _sub(b, a)
        Lk = math.sqrt(_dot(dk, dk))
        if Lk < 1.0:
            continue
        nos_k = {ln["na"], ln["nb"]} | {n2 for _t2, n2 in cortes[k]}     # as pontas e os nós da alma (2b)
        for n in nos_k:
            p = nos[n]
            for j in set(gl.perto(p)):
                lj = linhas[j]
                if lj["papel"] != "banzo" or lj["grupo"] == ln["grupo"] or lj.get("deitada"):
                    continue
                c, e = nos[lj["na"]], nos[lj["nb"]]
                dj = _sub(e, c)
                Lj = math.sqrt(_dot(dj, dj))
                if Lj < 1.0 or abs(_dot(dk, dj)) < 0.996 * Lk * Lj:
                    continue                               # não é paralelo
                dd, t, q = _proj(p, c, e)
                if dd <= TOL_LADO and abs(q[2] - p[2]) <= TOL_NO and 0.0 < t < 1.0                         and all(n2 != n for _t2, n2 in cortes[j]) and n not in (lj["na"], lj["nb"]):
                    cortes[j].append((t, n))
                    ao_lado += 1

    # --- 2d. o perfil de apoio das terças corre ao lado da treliça e é fixado em cada montante
    # dela: onde passa a até TOL_LADO de um montante da própria peça, os dois ganham um nó comum
    # (o U da TRANSIÇÃO 1 do Posto CB ficava preso só nas pontas, e as terças nele cediam)
    no_montante = 0
    for k, ln in enumerate(linhas):
        if ln["papel"] != "apoio_terca":
            continue
        a, b = nos[ln["na"]], nos[ln["nb"]]
        cand = set()
        n_p = int(math.dist(a, b) // 500.0) + 1
        for s_ in range(n_p + 1):
            cand.update(gl.perto(tuple(a[m] + (b[m] - a[m]) * s_ / n_p for m in range(3))))
        for j in cand:
            lj = linhas[j]
            if lj["papel"] != "montante" or lj["grupo"] != ln["grupo"]:
                continue
            dd, t, u, q = _entre_segmentos(a, b, nos[lj["na"]], nos[lj["nb"]])
            if dd > TOL_LADO or not (0.0 < t < 1.0) or not (0.0 <= u <= 1.0):
                continue
            nj = no_em(j, q, u)
            if all(n2 != nj for _t2, n2 in cortes[k]) and nj not in (ln["na"], ln["nb"]):
                cortes[k].append((t, nj))
                no_montante += 1

    # --- 3. a ponta solta desce/sobe até a peça em que apoia
    gr = grau()
    # a ponta da treliça: o fim do banzo, onde só chegam barras da própria peça (o montante de
    # ponta) — ela também desce até o apoio (o pilar, a viga, a outra treliça), levando junto
    # as barras dela que chegam ali
    no_linhas = collections.defaultdict(list)
    for k, ln in enumerate(linhas):
        no_linhas[ln["na"]].append(k)
        no_linhas[ln["nb"]].append(k)

    def fim_de_trelica(k, n):
        ls = [i for i in no_linhas[n] if n in (linhas[i]["na"], linhas[i]["nb"])]
        return linhas[k]["papel"] == "banzo" and linhas[k]["peca"] and len(ls) > 1 \
            and all(linhas[i]["grupo"] == linhas[k]["grupo"] for i in ls) \
            and sum(1 for i in ls if linhas[i]["papel"] == "banzo") == 1
    ligadas = 0
    for k, ln in enumerate(linhas):
        alvo = APOIA_EM.get(ln["papel"])
        if not alvo:
            continue
        for lado in ("na", "nb"):
            n = ln[lado]
            # a ponta está apoiada se chega nela uma peça em que ela apoia; a corrente presa na
            # ponta da terça não a apoia (é a terça que apoia a corrente)
            outras = [i for i in no_linhas[n] if i != k and n in (linhas[i]["na"], linhas[i]["nb"])]
            ponta_trelica = bool(outras) and fim_de_trelica(k, n)
            if any(linhas[i]["papel"] in alvo for i in outras) and not ponta_trelica:
                continue
            p = nos[n]
            if p[2] <= base + 50.0 and ln["papel"] in ("pilar", "viga"):
                continue                                   # o pé do pilar (e da escada) é a base
            melhor = None
            for j in set(gl.perto(p)):
                if j == k or linhas[j]["papel"] not in alvo or linhas[j]["grupo"] == ln["grupo"] and (
                        ln["papel"] in ("terça", "viga") or ponta_trelica):
                    continue
                d, t, q = _proj(p, nos[linhas[j]["na"]], nos[linhas[j]["nb"]])
                # alma de outra peça: só bem perto (senão liga treliças vizinhas); da mesma
                # peça (o painel subdividido, a mão-francesa treliçada), a tolerância normal
                alma_de_outra = linhas[j]["papel"] in ALMA and linhas[j]["grupo"] != ln["grupo"]
                tol = TOL_ALMA if alma_de_outra and ln["papel"] != "terça" else TOL_APOIO
                # o banzo (onde a terça senta) vale mais que a alma ao lado: a alma só se for bem mais perto
                if ln["papel"] == "terça" and linhas[j]["papel"] in ALMA:
                    d = d + TOL_APOIO / 2.0
                if d <= tol and (melhor is None or d < melhor[0]):
                    melhor = (d, j, t, q)
            if melhor:
                _d, j, t, q = melhor
                novo = no_em(j, q, t)
                if novo == n:
                    continue
                # o nó inteiro vai junto: as barras da própria treliça na ponta dela, a corrente
                # presa na ponta da terça
                for i in [k] + outras:
                    for ld in ("na", "nb"):
                        if linhas[i][ld] == n:
                            linhas[i][ld] = novo
                            no_linhas[novo].append(i)
                            gr[novo] += 1
                            gr[n] -= 1
                ligadas += 1

    # --- 4. a terça que passa sobre as treliças ganha um nó em cada banzo que ela cruza; a viga
    # também, no banzo que ela cruza (a VM do piso da caixa d'água deitada sobre as treliças)
    for k, ln in enumerate(linhas):
        if ln["papel"] not in ("terça", "viga"):
            continue
        a, b = nos[ln["na"]], nos[ln["nb"]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1.0:
            continue
        cand = set()
        n = int(L // 500.0) + 1
        for s in range(n + 1):
            cand.update(gl.perto(tuple(a[m] + (b[m] - a[m]) * s / n for m in range(3))))
        for j in cand:
            lj = linhas[j]
            if lj["papel"] not in (("banzo", "viga") if ln["papel"] == "terça" else ("banzo",)):
                continue
            c, e = nos[lj["na"]], nos[lj["nb"]]
            ex, ey = e[0] - c[0], e[1] - c[1]
            den = dx * ey - dy * ex
            if abs(den) <= 1e-3 * L * max(math.hypot(ex, ey), 1.0):
                continue                                   # paralelas (ou banzo vertical): não cruzam
            t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
            u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
            if not (0.02 < t < 0.98 and 0.0 <= u <= 1.0):
                continue
            zt = a[2] + (b[2] - a[2]) * t
            q = (c[0] + ex * u, c[1] + ey * u, c[2] + (e[2] - c[2]) * u)
            if abs(zt - q[2]) > TOL_CRUZA:
                continue
            nj = no_em(j, q, u)
            cortes[k].append((t, nj))

    # --- corta as linhas nos nós que ganharam
    barras = []
    for k, ln in enumerate(linhas):
        seq = [(0.0, ln["na"])] + sorted(cortes.get(k, [])) + [(1.0, ln["nb"])]
        for (t0, n0), (t1, n1) in zip(seq, seq[1:]):
            if n0 == n1:
                continue
            barras.append({"a": n0, "b": n1, "papel": ln["papel"], "peca": ln["peca"], "perfil": ln["perfil"],
                           "ids": ln["ids"], "duplo": ln["duplo"], "importada": bool(ln.get("importada")),
                           "deitada": bool(ln.get("deitada"))})

    # --- 5. o que sobrou sem ligar
    gr = collections.Counter()
    for br in barras:
        gr[br["a"]] += 1
        gr[br["b"]] += 1
    soltas = []
    for br in barras:
        for lado in ("a", "b"):
            n = br[lado]
            if gr[n] != 1:
                continue
            if br["papel"] in ("pilar", "viga") and nos[n][2] <= base + 50.0:
                continue
            if br["importada"] or br["papel"] in ("solido", "barra"):
                continue                                   # peça importada ou sem papel: não se sabe onde apoia
            soltas.append({"no": n, "ponto": [round(c) for c in nos[n]], "papel": br["papel"], "peca": br["peca"],
                           "ids": br["ids"]})
    usados = sorted({br["a"] for br in barras} | {br["b"] for br in barras})
    renum = {n: i for i, n in enumerate(usados)}
    for br in barras:
        br["a"], br["b"] = renum[br["a"]], renum[br["b"]]
    for s in soltas:
        s["no"] = renum[s["no"]]
    return {
        "nos": [[round(c, 1) for c in nos[n]] for n in usados],
        "barras": barras,
        "soltas": soltas,
        "resumo": {"nos": len(usados), "barras": len(barras), "duplos_juntados": duplos,
                   "pontas_levadas_ao_apoio": ligadas, "alma_no_banzo": na_alma, "deitada_ao_lado": ao_lado, "apoio_no_montante": no_montante,
                   "soltas": len(soltas),
                   "soltas_por_papel": dict(collections.Counter(s["papel"] for s in soltas))},
    }
