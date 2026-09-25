# -*- coding: utf-8 -*-
"""Cantos redondos: a barra calandrada do modelo (o joelho da tesoura, que o TecnoMETAL
exporta como um arco facetado) vira peças retas no próprio 3D — o canto quinado que a
fábrica monta —, para o detalhamento e os desenhos saírem do canto certo sem correção à mão.

Como a peça chega: uma malha de **anéis** (a seção do perfil, 8 vértices num U) ligados por
quadriláteros, com uma tampa em cada ponta — 27 anéis num joelho de 77°, um a cada 3°. Os
centroides dos anéis dão o eixo da peça; onde o eixo gira a passos iguais é o arco (centro,
raio e ângulo por ajuste de círculo), onde não gira é trecho reto.

Como se quebra: o arco de ângulo θ vira N retas **tangentes** (circunscritas, não a corda por
dentro): os trechos retos vizinhos se prolongam até a primeira e a última tangente, e as
tangentes se cruzam nos nós. É o que `nucleo2d.detalhe.conjuntos._chanfrar_cantos` já
desenha no 2D com N = 1 (a diagonal tangente no meio do arco); aqui a geometria vai para o
modelo, em todas as instâncias da posição. O desvio de cada opção — quanto o nó sai do arco,
R·(1/cos(θ/2N) − 1) — é o que a análise mostra para o usuário escolher N.

A malha nova reaproveita a seção do próprio anel (não o catálogo): as tampas ficam, e cada
nó recebe a seção no plano bissetor dos dois trechos, esticada em 1/cos(φ/2) na direção
do plano do arco (meia-esquadria), para as faces de fora e de dentro continuarem contínuas.
A peça continua `barra_conformada` no detalhamento, com `atributos.quebras` = {n, nos,
raio, angulo}: a elevação ganha os nós de chanfro (linha de emenda) neles.
"""
import collections
import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Documento, Solido

Ponto = Tuple[float, float, float]

#: Giro entre passos consecutivos do eixo (graus) a partir do qual o trecho é curvo.
GIRO_MINIMO = 0.5
#: Giro acima disto num passo só é uma quina (peça já quebrada, dobra), não arco facetado.
GIRO_MAXIMO = 12.0
#: Ângulo total (graus) abaixo do qual a curva não é um canto (transição suave, ondulação).
ANGULO_MINIMO = 10.0
#: Opções de quebra oferecidas.
OPCOES_N = (1, 2, 3, 4)
#: Perfil de barra redonda (ferro redondo, barra roscada, chumbador): dobra, não é canto.
import re
_RE_REDONDA = re.compile(r"FE\s*RED|FERRO\s*RED|ROSCAD|REDOND|CHUMB|^\s*[ØO]\s*\d|^\s*BR", re.I)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norma(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norma(a)
    return _mul(a, 1.0 / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def _centro(pts: Sequence[Ponto]) -> Ponto:
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


# ============================================================ anéis da malha
def aneis_da_malha(e: Solido) -> Optional[List[List[int]]]:
    """Os anéis de vértices da peça, em ordem de uma tampa à outra, ou None quando a malha
    não é uma extrusão por anéis (tampas ligadas só por quadriláteros)."""
    faces = [list(f) for f in e.faces or []]
    quads = [f for f in faces if len(f) == 4]
    tampas = [f for f in faces if len(f) != 4]
    if len(tampas) != 2 or len(tampas[0]) != len(tampas[1]) or len(tampas[0]) < 3:
        return None
    k = len(tampas[0])
    por_aresta: Dict[frozenset, list] = collections.defaultdict(list)
    for f in quads:
        for i in range(4):
            por_aresta[frozenset((f[i], f[(i + 1) % 4]))].append(f)
    anel = list(tampas[0])
    aneis = [anel]
    visitados = set(anel)
    alvo = set(tampas[1])
    for _ in range(len(e.vertices)):
        prox = []
        for i in range(k):
            a, b = anel[i], anel[(i + 1) % k]
            q = next((f for f in por_aresta.get(frozenset((a, b)), []) if not set(f) <= visitados), None)
            if q is None:
                return None
            ia = q.index(a)
            va = q[(ia - 1) % 4] if q[(ia + 1) % 4] == b else q[(ia + 1) % 4]
            prox.append(va)
        if len(set(prox)) != k:
            return None
        anel = prox
        aneis.append(anel)
        visitados |= set(anel)
        if set(anel) == alvo:
            return aneis
    return None


def _quad_de_anel_para_anel(e: Solido, aneis: List[List[int]]) -> bool:
    """Como a malha original enrola os quadriláteros: True quando o quad entre os anéis r
    e r+1 sai como [r_i, r_{i+1}, (r+1)_{i+1}, (r+1)_i]; False quando é o sentido oposto."""
    a0, a1 = aneis[0], aneis[1]
    padrao = (a0[0], a0[1], a1[1], a1[0])
    for f in e.faces:
        if len(f) == 4 and set(f) == set(padrao):
            i = f.index(a0[0])
            return f[(i + 1) % 4] == a0[1]
    return True


# ============================================================ arco
def _ajustar_circulo(pts: Sequence[Ponto], normal: Ponto):
    """Centro e raio do círculo pelos pontos (mínimos quadrados de Kåsa no plano)."""
    c0 = _centro(pts)
    u = _unit(_sub(pts[-1], pts[0]))
    u = _unit(_sub(u, _mul(normal, _dot(u, normal))))
    v = _unit(_cruz(normal, u))
    P = [(_dot(_sub(p, c0), u), _dot(_sub(p, c0), v)) for p in pts]
    # x² + y² + D x + E y + F = 0
    Sxx = sum(x * x for x, _ in P); Syy = sum(y * y for _, y in P); Sxy = sum(x * y for x, y in P)
    Sx = sum(x for x, _ in P); Sy = sum(y for _, y in P); n = len(P)
    Sxz = sum(x * (x * x + y * y) for x, y in P); Syz = sum(y * (x * x + y * y) for x, y in P)
    Sz = sum(x * x + y * y for x, y in P)
    A = [[Sxx, Sxy, Sx], [Sxy, Syy, Sy], [Sx, Sy, float(n)]]
    B = [-Sxz, -Syz, -Sz]
    # Cramer
    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det3(A)
    if abs(d) < 1e-9:
        return None
    sol = []
    for k in range(3):
        M = [row[:] for row in A]
        for r in range(3):
            M[r][k] = B[r]
        sol.append(det3(M) / d)
    D, E, F = sol
    cx, cy = -D / 2.0, -E / 2.0
    r2 = cx * cx + cy * cy - F
    if r2 <= 0:
        return None
    centro = _add(c0, _add(_mul(u, cx), _mul(v, cy)))
    return centro, math.sqrt(r2)


def analisar_peca(e: Solido) -> Optional[dict]:
    """Eixo, trechos e o arco principal de uma barra calandrada, ou None quando a malha não
    é por anéis ou não tem canto: {aneis, centros, arco: {i0, i1, centro, raio, angulo,
    normal, comprimento}, retos: [(i, j, comprimento)]}."""
    aneis = aneis_da_malha(e)
    if not aneis or len(aneis) < 4:
        return None
    cs = [_centro([e.vertices[i] for i in a]) for a in aneis]
    dirs = [_unit(_sub(cs[i + 1], cs[i])) for i in range(len(cs) - 1)]
    giros = []
    for i in range(len(dirs) - 1):
        c = max(-1.0, min(1.0, _dot(dirs[i], dirs[i + 1])))
        giros.append(math.degrees(math.acos(c)))
    # trechos por passo: o passo k (anel k → k+1) é curvo quando gira nas duas pontas; na
    # ponta da peça (um giro só) quando gira e é curto como o vizinho — o trecho reto
    # comprido que encosta no arco gira meio passo na junção e não é arco
    passos = [math.dist(cs[i], cs[i + 1]) for i in range(len(cs) - 1)]
    curvo = [False] * len(dirs)
    for k in range(len(dirs)):
        g_ini = giros[k - 1] if k >= 1 else None
        g_fim = giros[k] if k < len(giros) else None
        suave = lambda g: GIRO_MINIMO <= g <= GIRO_MAXIMO          # noqa: E731
        if g_ini is not None and g_fim is not None:
            curvo[k] = suave(g_ini) and suave(g_fim)
        else:
            g = g_fim if g_ini is None else g_ini
            vizinho = passos[k + 1] if g_ini is None else passos[k - 1]
            curvo[k] = g is not None and suave(g) and passos[k] <= 1.5 * vizinho
    trechos = []                                  # (curvo?, passo inicial, passo final inclusivo)
    for k, c in enumerate(curvo):
        if trechos and trechos[-1][0] == c:
            trechos[-1][2] = k
        else:
            trechos.append([c, k, k])
    arcos = [t for t in trechos if t[0] and t[2] - t[1] >= 2]
    if not arcos:
        return None
    # o maior arco pelo giro total
    def giro_total(t):
        # os passos i..j giram nas duas pontas: os giros de i-1 (antes do primeiro) a j (depois do último)
        return sum(giros[max(t[1] - 1, 0):t[2] + 1])
    arco = max(arcos, key=giro_total)
    i0, i1 = arco[1], arco[2] + 1                 # anéis: do começo ao fim do arco
    angulo = giro_total(arco)
    if angulo < ANGULO_MINIMO:
        return None
    pts = cs[i0:i1 + 1]
    normal = _unit(_cruz(dirs[i0], dirs[i1 - 1]))
    if _norma(normal) < 1e-9:
        return None
    ajuste = _ajustar_circulo(pts, normal)
    if not ajuste:
        return None
    centro, raio = ajuste
    # o ângulo pela geometria (entre os raios das duas pontas): a soma dos giros perde meio
    # passo na ponta em que o arco acaba na tampa da peça
    r0, r1 = _unit(_sub(cs[i0], centro)), _unit(_sub(cs[i1], centro))
    ang = math.atan2(_dot(_cruz(r0, r1), normal), _dot(r0, r1))
    if ang < 0:
        ang += 2 * math.pi
    if 0.5 * angulo <= math.degrees(ang) <= 1.5 * angulo + 5.0:
        angulo = math.degrees(ang)
    comprimento = sum(math.dist(cs[k], cs[k + 1]) for k in range(i0, i1))
    retos = [(t[1], t[2] + 1, sum(math.dist(cs[k], cs[k + 1]) for k in range(t[1], t[2] + 1))) for t in trechos if not t[0]]
    return {"aneis": aneis, "centros": cs, "dirs": dirs,
            "arco": {"i0": i0, "i1": i1, "centro": centro, "raio": raio, "angulo": angulo, "normal": normal, "comprimento": comprimento},
            "retos": retos}


def opcoes_de_quebra(raio: float, angulo: float, ns: Sequence[int] = OPCOES_N) -> List[dict]:
    """Para cada N: quanto o nó sai do arco (mm) e o comprimento de cada reta tangente."""
    th = math.radians(angulo)
    saida = []
    for n in ns:
        meio = th / (2.0 * n)
        # os nós do meio ficam a R/cos(θ/2N) do centro; os das pontas (onde a tangente do
        # trecho reto encontra a primeira reta) a R/cos(θ/4N) — com N = 1 só há esses
        desvio = raio * (1.0 / math.cos(meio if n > 1 else meio / 2.0) - 1.0)
        reta = 2.0 * raio * math.tan(meio) if n > 1 else 2.0 * raio * math.tan(meio / 2.0)
        saida.append({"n": n, "desvio": desvio, "reta": reta, "pontas": raio * math.tan(meio / 2.0)})
    return saida


# ============================================================ quebra
def _nos_da_quebra(arco: dict, n: int) -> List[Ponto]:
    """Os nós do polígono tangente ao arco: onde a tangente do começo encontra a primeira
    reta, os cruzamentos entre retas e onde a última encontra a tangente do fim."""
    C, R, normal = arco["centro"], arco["raio"], arco["normal"]
    th = math.radians(arco["angulo"])
    a0 = _unit(_sub(arco["p0"], C))                   # raio no começo do arco
    b0 = _unit(_cruz(normal, a0))                     # sentido de giro
    if _dot(b0, arco["t0"]) < 0:
        b0 = _mul(b0, -1.0)
    def raio_em(ang):
        return _add(_mul(a0, math.cos(ang)), _mul(b0, math.sin(ang)))
    nos = []
    angulos = [th / (4.0 * n)] + [th * k / n for k in range(1, n)] + [th - th / (4.0 * n)]
    for k, ang in enumerate(angulos):
        meio = th / (4.0 * n) if k in (0, len(angulos) - 1) else th / (2.0 * n)
        nos.append(_add(C, _mul(raio_em(ang), R / math.cos(meio))))
    return nos


def quebrar_peca(e: Solido, n: int) -> Optional[dict]:
    """Reconstrói a malha da peça com o arco trocado por `n` retas tangentes. Devolve
    {"n", "nos", "raio", "angulo", "pontas"} (também gravado em `e.atributos["quebras"]`,
    sem "pontas"), ou None quando a peça não tem canto reconhecível.

    Quando o arco termina na própria ponta da peça (o joelho que encosta no banzo sem
    trecho reto), a peça passa a terminar **no nó**, cortada em meia-esquadria — o nó fica
    R·tan(θ/4N) antes da ponta antiga, e é o banzo que vem até ele (`_estender_vizinha`).
    `pontas` diz, para cada lado do arco, se era ponta ("cap"), a ponta antiga `p`, a
    tangente `t` (saindo da peça), o nó `no` e a normal `m` do plano da meia-esquadria."""
    an = analisar_peca(e)
    if not an:
        return None
    aneis, cs, dirs, arco = an["aneis"], an["centros"], an["dirs"], an["arco"]
    i0, i1 = arco["i0"], arco["i1"]
    ultimo = len(aneis) - 1
    arco = dict(arco, p0=cs[i0], t0=dirs[i0], p1=cs[i1], t1=dirs[i1 - 1])
    nos = _nos_da_quebra(arco, n)
    normal = arco["normal"]
    b = normal
    # a seção no anel do começo do arco, no quadro (t, m, b): t tangente, b normal do arco,
    # m = b × t (no plano do arco, é a direção que a meia-esquadria estica)
    t = dirs[i0]
    m = _unit(_cruz(b, t))
    c0 = cs[i0]
    secao = [(_dot(_sub(e.vertices[i], c0), m), _dot(_sub(e.vertices[i], c0), b)) for i in aneis[i0]]
    # tangentes nas pontas do arco, pela geometria do círculo (a corda do primeiro passo
    # facetado gira meio passo em relação à tangente de verdade)
    C = arco["centro"]

    def tangente_em(p, sentido):
        radial = _unit(_sub(p, C))
        tg = _unit(_cruz(normal, radial))
        return tg if _dot(tg, sentido) >= 0 else _mul(tg, -1.0)
    t_ini = tangente_em(cs[i0], dirs[i0])                 # entra no arco
    t_fim = tangente_em(cs[i1], dirs[i1 - 1])             # sai do arco
    cap_ini, cap_fim = i0 == 0, i1 == ultimo
    # eixo novo: anéis antes do arco ficam, os do arco saem, os nós entram, anéis depois
    # ficam; sem anel antes/depois (o arco vai até a ponta), o nó da ponta vira a tampa
    pontos_eixo: List[Tuple[str, object]] = []
    if not cap_ini:
        pontos_eixo += [("anel", k) for k in range(0, i0 + 1)]
    pontos_eixo += [("no", q) for q in nos]
    if not cap_fim:
        pontos_eixo += [("anel", k) for k in range(i1, ultimo + 1)]
    centros_novos = [cs[v] if tp == "anel" else v for tp, v in pontos_eixo]
    # direções virtuais nas pontas (a tangente), para o nó da ponta ser cortado em meia-esquadria
    antes_do_primeiro = _sub(centros_novos[0], t_ini)
    depois_do_ultimo = _add(centros_novos[-1], t_fim)
    vertices: List[Ponto] = []
    novos_aneis: List[List[int]] = []
    pontas = {"inicio": {"cap": cap_ini, "p": cs[0], "t": _mul(t_ini, -1.0), "no": nos[0]},
              "fim": {"cap": cap_fim, "p": cs[ultimo], "t": t_fim, "no": nos[-1]}}
    for idx, (tipo, val) in enumerate(pontos_eixo):
        if tipo == "anel":
            base = len(vertices)
            vertices.extend(tuple(e.vertices[i]) for i in aneis[val])
            novos_aneis.append(list(range(base, base + len(aneis[val]))))
            continue
        # nó: seção no plano bissetor, esticada em 1/cos(φ/2) na direção m
        anterior = centros_novos[idx - 1] if idx > 0 else antes_do_primeiro
        seguinte = centros_novos[idx + 1] if idx + 1 < len(centros_novos) else depois_do_ultimo
        d_in = _unit(_sub(val, anterior))
        d_out = _unit(_sub(seguinte, val))
        bis = _unit(_add(d_in, d_out))
        cos_meio = max(0.2, _dot(bis, d_in))
        m_no = _unit(_cruz(b, bis))
        if idx == 0:
            pontas["inicio"]["m"] = bis
        if idx == len(pontos_eixo) - 1:
            pontas["fim"]["m"] = bis
        base = len(vertices)
        for x, y in secao:
            vertices.append(_add(val, _add(_mul(m_no, x / cos_meio), _mul(b, y))))
        novos_aneis.append(list(range(base, base + len(secao))))
    # faces: tampas como eram (mesma ordem de vértices, mapeada pela posição no anel),
    # quads entre anéis no mesmo sentido
    sentido = _quad_de_anel_para_anel(e, aneis)
    faces: List[List[int]] = []
    k = len(secao)
    tampa0 = [f for f in e.faces if len(f) != 4 and set(f) == set(aneis[0])][0]
    tampa1 = [f for f in e.faces if len(f) != 4 and set(f) == set(aneis[-1])][0]
    faces.append([novos_aneis[0][aneis[0].index(vi)] for vi in tampa0])
    faces.append([novos_aneis[-1][aneis[-1].index(vi)] for vi in tampa1])
    for r in range(len(novos_aneis) - 1):
        a, c = novos_aneis[r], novos_aneis[r + 1]
        for i in range(k):
            j = (i + 1) % k
            faces.append([a[i], a[j], c[j], c[i]] if sentido else [a[i], c[i], c[j], a[j]])
    e.vertices = vertices
    e.faces = faces
    e.arestas_vivas = []
    quebras = {"n": n, "nos": [[round(x, 2) for x in q] for q in nos], "raio": round(arco["raio"], 1),
               "angulo": round(arco["angulo"], 2)}
    e.atributos = dict(e.atributos or {}, quebras=quebras)
    return dict(quebras, pontas=pontas, arco=arco)


# ============================================================ vizinhas e diagonais
#: Ponta de outra barra a menos disto (mm) da ponta antiga do joelho é a barra que encosta.
TOLERANCIA_VIZINHA = 60.0
#: Metade da altura do perfil, para dizer que a ponta de uma diagonal está no arco.
ALTURA_CANTO = 150.0


def _pontas_da_barra(b: Solido):
    """(ponta A, ponta B, comprimento) de uma barra: centros das tampas quando a malha é por
    anéis; senão os extremos ao longo do maior espalhamento."""
    aneis = aneis_da_malha(b)
    if aneis:
        return _centro([b.vertices[i] for i in aneis[0]]), _centro([b.vertices[i] for i in aneis[-1]])
    vs = b.vertices
    if len(vs) < 4:
        return None
    c = _centro(vs)
    melhor, eixo = 0.0, (1.0, 0.0, 0.0)
    for d in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        ts = [_dot(_sub(v, c), d) for v in vs]
        if max(ts) - min(ts) > melhor:
            melhor, eixo = max(ts) - min(ts), d
    ts = [_dot(_sub(v, c), eixo) for v in vs]
    return _add(c, _mul(eixo, min(ts))), _add(c, _mul(eixo, max(ts)))


def _eh_barra(b: Solido) -> bool:
    """Barra (não chapa, não parafuso): caixa com a menor dimensão de 20 mm ou mais e a
    maior de 300 ou mais."""
    if not isinstance(b, Solido) or len(b.vertices) < 8:
        return False
    ext = [max(v[i] for v in b.vertices) - min(v[i] for v in b.vertices) for i in range(3)]
    return sorted(ext)[0] >= 20.0 and max(ext) >= 300.0


def _estender_vizinha(doc: Documento, e: Solido, ponta: dict) -> Optional[Solido]:
    """A barra que encostava na ponta antiga do joelho (o banzo) vem até o nó: os vértices
    dela no plano da ponta antiga andam ao longo do eixo até o plano da meia-esquadria."""
    if not ponta.get("cap") or "m" not in ponta:
        return None
    p, t, no, m = ponta["p"], ponta["t"], ponta["no"], ponta["m"]
    den = _dot(t, m)
    if abs(den) < 0.2:
        return None
    for b in doc.entidades.values():
        if b is e or not _eh_barra(b) or (b.atributos or {}).get("quebras"):
            continue
        pontas = _pontas_da_barra(b)
        if not pontas:
            continue
        a_, b_ = pontas
        perto = min((math.dist(a_, p), a_), (math.dist(b_, p), b_))
        if perto[0] > TOLERANCIA_VIZINHA:
            continue
        eixo_b = _unit(_sub(b_, a_) if perto[1] is a_ else _sub(a_, b_))     # da ponta encostada para dentro da barra
        if abs(_dot(eixo_b, t)) < 0.95:
            continue
        # os vértices no plano da ponta antiga (normal t) andam até o plano da meia-esquadria
        novos = []
        mudou = 0
        for v in b.vertices:
            if abs(_dot(_sub(v, p), t)) <= 3.0:
                s = _dot(_sub(no, v), m) / den
                novos.append(_add(v, _mul(t, s)))
                mudou += 1
            else:
                novos.append(tuple(v))
        if mudou >= 3:
            b.vertices = novos
            b.atributos = dict(b.atributos or {}, estendida_ate_no=[round(x, 2) for x in no])
            return b
    return None


def _diagonais_do_canto(doc: Documento, e: Solido, q: dict) -> List[Solido]:
    """A diagonal que apontava para o meio do arco sai; entra uma diagonal do nó de baixo
    (a outra ponta dela) até cada nó da quebra, com a seção da diagonal antiga levada pela
    transformação afim (mesma seção, comprimento novo). Devolve as barras novas."""
    arco = q["arco"]
    C, R, normal = arco["centro"], arco["raio"], arco["normal"]
    th = math.radians(arco["angulo"])
    a0 = _unit(_sub(arco["p0"], C))
    b0 = _unit(_cruz(normal, a0))
    if _dot(b0, arco["t0"]) < 0:
        b0 = _mul(b0, -1.0)
    conj = str(((e.atributos or {}).get("marcas") or {}).get("conjunto") or "")

    def no_arco(p) -> bool:
        rel = _sub(p, C)
        fora = abs(_dot(rel, normal))
        rr = math.sqrt(max(_dot(rel, rel) - fora * fora, 0.0))
        if fora > ALTURA_CANTO or abs(rr - R) > ALTURA_CANTO:
            return False
        ang = math.atan2(_dot(rel, b0), _dot(rel, a0))
        return -math.radians(5.0) <= ang <= th + math.radians(5.0)
    def radial(p) -> float:
        """Quanto a direção `d_` da barra aponta para o centro do arco em `p` (0 = tangente)."""
        rel = _sub(p, C)
        rel = _sub(rel, _mul(normal, _dot(rel, normal)))
        return _unit(rel)
    novas: List[Solido] = []
    for d in list(doc.entidades.values()):
        if d is e or not _eh_barra(d) or (d.atributos or {}).get("quebras") or (d.atributos or {}).get("estendida_ate_no"):
            continue
        if conj and str(((d.atributos or {}).get("marcas") or {}).get("conjunto") or "") != conj:
            continue
        pontas = _pontas_da_barra(d)
        if not pontas:
            continue
        A, B = pontas
        if no_arco(B) and not no_arco(A):
            pass
        elif no_arco(A) and not no_arco(B):
            A, B = B, A
        else:
            continue
        if math.dist(A, B) < 300.0:
            continue
        # o banzo e a perna encostam nas pontas do arco, tangentes a ele: não são diagonais
        if min(math.dist(B, arco["p0"]), math.dist(B, arco["p1"])) < 100.0:
            continue
        d_old = _unit(_sub(B, A))
        if abs(_dot(d_old, radial(B))) < 0.5:
            continue
        L_old = math.dist(A, B)
        marcas = dict(((d.atributos or {}).get("marcas") or {}))
        pos_old = str(marcas.get("posicao") or d.nome or "D")
        for k, no in enumerate(q["nos"]):
            d_new = _unit(_sub(no, A))
            L_new = math.dist(A, no)
            if L_new < 100.0:
                continue
            # rotação d_old → d_new (Rodrigues) e escala só no eixo
            eixo_r = _cruz(d_old, d_new)
            sen = _norma(eixo_r)
            cos = max(-1.0, min(1.0, _dot(d_old, d_new)))

            def rodar(v):
                if sen < 1e-9:
                    return v if cos > 0 else _mul(v, -1.0)
                kx = _mul(eixo_r, 1.0 / sen)
                return _add(_add(_mul(v, cos), _mul(_cruz(kx, v), sen)), _mul(kx, _dot(kx, v) * (1.0 - cos)))
            vs = []
            for v in d.vertices:
                rel = _sub(v, A)
                axial = _dot(rel, d_old)
                trans = _sub(rel, _mul(d_old, axial))
                vs.append(_add(A, _add(rodar(trans), _mul(d_new, axial * L_new / L_old))))
            nova = Solido(nome=d.nome, camada=d.camada, material=d.material, visivel=d.visivel,
                          vertices=vs, faces=[list(f) for f in d.faces], arestas_vivas=[],
                          atributos=dict(d.atributos or {}, marcas=dict(marcas, posicao="%s-Q%d" % (pos_old, k + 1)),
                                         diagonal_da_quebra={"de": pos_old, "no": k + 1}))
            doc.add(nova)
            novas.append(nova)
        doc.remover(d.id)
    return novas


# ============================================================ o modelo inteiro
def _marca(e: Solido) -> str:
    m = (e.atributos or {}).get("marcas") or {}
    return str(m.get("posicao") or e.nome or e.id)


def _nome(e: Solido) -> str:
    m = (e.atributos or {}).get("marcas") or {}
    return str(m.get("nome") or "")


def analisar_modelo(doc: Documento) -> List[dict]:
    """As posições com canto redondo no modelo, uma linha por posição (a primeira instância
    analisada; as outras contadas): marca, nome, perfil, instancias, raio, angulo,
    comprimento do arco, retos, e as opções de quebra."""
    por_marca: Dict[str, List[Solido]] = collections.OrderedDict()
    for e in doc.entidades.values():
        if not isinstance(e, Solido) or len(e.vertices) < 24 or (e.atributos or {}).get("quebras"):
            continue
        # barra redonda (tirante com gancho, chumbador) dobra, não tem canto a chanfrar
        perfil = str(((e.atributos or {}).get("marcas") or {}).get("perfil") or e.nome or "")
        if _RE_REDONDA.search(perfil):
            continue
        por_marca.setdefault(_marca(e), []).append(e)
    saida = []
    for marca, ents in por_marca.items():
        an = None
        for e in ents:
            an = analisar_peca(e)
            if an:
                break
        if not an:
            continue
        arco = an["arco"]
        m = (e.atributos or {}).get("marcas") or {}
        saida.append({
            "marca": marca, "nome": _nome(e), "perfil": str(m.get("perfil") or e.nome or ""),
            "conjunto": str(m.get("conjunto") or ""), "instancias": len(ents),
            "raio": arco["raio"], "angulo": arco["angulo"], "comprimento_arco": arco["comprimento"],
            "retos": [r[2] for r in an["retos"]], "lados": len(an["aneis"][0]),
            "opcoes": opcoes_de_quebra(arco["raio"], arco["angulo"]),
        })
    saida.sort(key=lambda r: -r["instancias"])
    return saida


def quebrar_modelo(doc: Documento, escolhas: Dict[str, int], diagonais: bool = True) -> dict:
    """Quebra o arco de todas as instâncias de cada marca em `escolhas` ({marca: n}): a
    malha do joelho, a barra que encostava na ponta (vem até o nó) e, com `diagonais`, a
    diagonal do canto refeita do nó de baixo até cada nó. Devolve {"pecas", "posicoes",
    "estendidas", "diagonais", "falhas"}."""
    saida = {"pecas": 0, "posicoes": [], "estendidas": 0, "diagonais": 0, "falhas": []}
    for marca, n in escolhas.items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if n < 1 or n > 12:
            continue
        feitas = 0
        for e in list(doc.entidades.values()):
            if not isinstance(e, Solido) or _marca(e) != marca or (e.atributos or {}).get("quebras"):
                continue
            q = quebrar_peca(e, n)
            if not q:
                saida["falhas"].append("%s: uma instância sem canto reconhecível ficou como estava" % marca)
                continue
            feitas += 1
            for lado in ("inicio", "fim"):
                if _estender_vizinha(doc, e, q["pontas"][lado]) is not None:
                    saida["estendidas"] += 1
            if diagonais:
                saida["diagonais"] += len(_diagonais_do_canto(doc, e, q))
        if feitas:
            saida["pecas"] += feitas
            saida["posicoes"].append(marca)
    return saida
