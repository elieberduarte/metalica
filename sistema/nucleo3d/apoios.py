# -*- coding: utf-8 -*-
"""Regras de apoio do modelo 3D: o que toda estrutura precisa cumprir, conferido peça por peça.

* nenhuma peça voando: seguindo o que encosta no quê, desde a base dos pilares, toda peça
  tem de chegar ao chão;
* a treliça termina apoiada: em cima de um pilar, em outra treliça ou numa viga;
* a terça apoia nas pontas (não passa do último apoio) e cruza a treliça num nó (onde chega
  um montante ou uma diagonal), não no meio do banzo;
* o pilar tem o que carregar em cima; a viga apoia nas duas pontas.

Serve a qualquer modelo (montado pela planta, lançado, importado). A treliça é reconhecida
pela marca `atributos.origem.peca` (a montagem pela planta grava); sem ela, a regra da ponta
de treliça fica de fora e as outras valem.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Tuple

__all__ = ["verificar", "TOL_ENCOSTO"]

Ponto = Tuple[float, float, float]

TOL_ENCOSTO = 250.0      # mm: duas peças a menos disso se tocam (eixo a eixo, com meia seção)
BALANCO_MAX = 300.0      # mm: terça além do último apoio
FORA_DO_NO = 200.0       # mm: cruzamento da terça até o nó mais perto do banzo (o par da cumeeira fica a ~150)
ALMA = ("montante", "diagonal")
ACESSORIOS = ("terça", "corrente", "contraventamento")


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _dist_seg_seg(p1, q1, p2, q2) -> Tuple[float, float, float]:
    """(distância, t no primeiro, u no segundo) entre os segmentos p1–q1 e p2–q2"""
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if a <= 1e-9 and e <= 1e-9:
        return math.dist(p1, p2), 0.0, 0.0
    if a <= 1e-9:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = _dot(d1, r)
        if e <= 1e-9:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = _dot(d1, d2)
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > 1e-9 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    c1 = (p1[0] + d1[0] * s, p1[1] + d1[1] * s, p1[2] + d1[2] * s)
    c2 = (p2[0] + d2[0] * t, p2[1] + d2[1] * t, p2[2] + d2[2] * t)
    return math.dist(c1, c2), s, t


def _dist_pt_seg(p, a, b) -> Tuple[float, float]:
    d = _sub(b, a)
    L2 = _dot(d, d)
    t = 0.0 if L2 <= 1e-9 else min(max(_dot(_sub(p, a), d) / L2, 0.0), 1.0)
    q = (a[0] + d[0] * t, a[1] + d[1] * t, a[2] + d[2] * t)
    return math.dist(p, q), t


class _Elem:
    __slots__ = ("id", "papel", "camada", "peca", "segs", "nome", "ent", "raio")

    def __init__(self, ent, segs, papel, peca):
        self.id = ent.id
        self.ent = ent
        self.papel = papel
        self.camada = getattr(ent, "camada", "")
        self.peca = peca
        self.segs = segs
        self.raio = 0.0                 # meia seção do sólido (a barra usa a tolerância)
        orig = (getattr(ent, "atributos", None) or {}).get("origem") or {}
        self.nome = orig.get("planta") or orig.get("locacao") or orig.get("sigla") or getattr(ent, "nome", "")


def _eixo_do_solido(v: List[Ponto]) -> Tuple[list, float]:
    """o sólido importado (perfil extrudado, chapa) como cápsula: o segmento pela direção em
    que ele é mais comprido, passando pelo centro, e o raio que cobre a seção"""
    n = len(v)
    c = tuple(sum(p[j] for p in v) / n for j in range(3))
    # direção principal: a mais comprida entre os pares de vértices extremos (sem álgebra
    # linear: o ponto mais longe do centro e o mais longe dele)
    a = max(v, key=lambda p: math.dist(p, c))
    b = max(v, key=lambda p: math.dist(p, a))
    L = math.dist(a, b)
    if L < 1e-6:
        return [(c, c)], 0.0
    u = tuple((b[j] - a[j]) / L for j in range(3))
    ts = [_dot(_sub(p, c), u) for p in v]
    t0, t1 = min(ts), max(ts)
    p0 = tuple(c[j] + u[j] * t0 for j in range(3))
    p1 = tuple(c[j] + u[j] * t1 for j in range(3))
    raio = max(_dist_pt_seg(p, p0, p1)[0] for p in v)
    return [(p0, p1)], min(raio, 400.0)


def _papel_do_solido(s) -> str:
    nome = (getattr(s, "nome", "") or "").upper()
    t = ((getattr(s, "atributos", None) or {}).get("tipo_ifc") or "").lower()
    if "column" in t:
        return "pilar"
    if "plate" in t or nome.startswith("CH"):
        return "chapa"
    return "solido"


def _elementos(doc) -> List[_Elem]:
    out = []
    for b in doc.barras:
        orig = (b.atributos or {}).get("origem") or {}
        out.append(_Elem(b, [(tuple(b.inicio), tuple(b.fim))], b.papel, orig.get("peca")))
    for s in doc.solidos:
        orig = (s.atributos or {}).get("origem") or {}
        v = [tuple(p) for p in s.vertices]
        if not v:
            continue
        k = len(s.faces[0]) if s.faces and (s.atributos or {}).get("calandrada") else 0
        if k and len(v) % k == 0 and len(v) // k >= 2:
            # peça varrida: a linha pelos centros dos anéis
            cs = []
            for i in range(0, len(v), k):
                anel = v[i:i + k]
                cs.append(tuple(sum(p[j] for p in anel) / k for j in range(3)))
            segs = list(zip(cs, cs[1:]))
        else:
            segs, raio = _eixo_do_solido(v)
        e = _Elem(s, segs, "banzo" if orig.get("peca") else _papel_do_solido(s), orig.get("peca"))
        e.raio = raio if not k else 0.0
        out.append(e)
    return out


def _vizinhos(els: List[_Elem], tol: float) -> Dict[int, Dict[int, float]]:
    """pares de elementos que se tocam (distância entre eixos < tol): {i: {j: dist}}"""
    cel = max(tol * 2.0, 600.0, 2.0 * max((e.raio for e in els), default=0.0) + tol)
    grade: Dict[tuple, set] = collections.defaultdict(set)
    for i, e in enumerate(els):
        for a, b in e.segs:
            L = math.dist(a, b)
            n = max(1, int(L / (cel / 2.0)))
            if e.raio > cel / 2.0:
                n = max(n, 2)
            for k in range(n + 1):
                p = tuple(a[j] + (b[j] - a[j]) * k / n for j in range(3))
                grade[(int(p[0] // cel), int(p[1] // cel), int(p[2] // cel))].add(i)
    viz: Dict[int, Dict[int, float]] = collections.defaultdict(dict)
    vistos = set()
    for ch, lst in grade.items():
        cand = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    cand |= grade.get((ch[0] + dx, ch[1] + dy, ch[2] + dz), set())
        for i in lst:
            for j in cand:
                if j <= i or (i, j) in vistos:
                    continue
                vistos.add((i, j))
                d = min(_dist_seg_seg(a, b, c, e)[0] for a, b in els[i].segs for c, e in els[j].segs)
                d -= els[i].raio + els[j].raio
                if d < tol:
                    viz[i][j] = d
                    viz[j][i] = d
    return viz


def _m(mm: float) -> str:
    """metros com vírgula (3,96 m)"""
    return ("%.2f m" % (mm / 1000.0)).replace(".", ",")


def _achado(regra, texto, ponto, ids, peca="", **extra) -> dict:
    d = {"regra": regra, "texto": texto, "ponto": [round(c) for c in ponto], "ids": list(ids), "peca": peca}
    d.update(extra)
    return d


def verificar(doc, tol: float = TOL_ENCOSTO) -> dict:
    """confere as regras de apoio. Devolve {resumo, achados} — cada achado com a regra, o
    texto em linguagem de obra, o ponto (x, y, z) e as ids das peças."""
    els = _elementos(doc)
    viz = _vizinhos(els, tol)
    achados: List[dict] = []
    if not els:
        return {"resumo": {}, "achados": []}
    zs = [p[2] for e in els for s in e.segs for p in s]
    pil = [i for i, e in enumerate(els) if e.papel == "pilar"]
    z_base = min((min(p[2] for s in els[i].segs for p in s) for i in pil), default=min(zs))

    # ------------------------------------------------------------- peças voando
    pai = list(range(len(els)))

    def acha(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i, js in viz.items():
        for j in js:
            ra, rb = acha(i), acha(j)
            if ra != rb:
                pai[rb] = ra
    no_chao = {acha(i) for i, e in enumerate(els) if min(p[2] for s in e.segs for p in s) <= z_base + 100.0}
    grupos: Dict[int, List[int]] = collections.defaultdict(list)
    for i in range(len(els)):
        grupos[acha(i)].append(i)
    soltos = 0
    for raiz, lst in grupos.items():
        if raiz in no_chao:
            continue
        soltos += len(lst)
        pts = [p for i in lst for s in els[i].segs for p in s]
        meio = tuple(sum(p[j] for p in pts) / len(pts) for j in range(3))
        nomes = collections.Counter(els[i].nome or els[i].papel for i in lst)
        achados.append(_achado("voando", "%d peça(s) sem ligação até a base: %s" % (
            len(lst), ", ".join("%s (%d)" % kv for kv in nomes.most_common(3))), meio,
            [els[i].id for i in lst], peca=nomes.most_common(1)[0][0]))

    # ------------------------------------------------------------- ponta de treliça
    por_peca: Dict[str, List[int]] = collections.defaultdict(list)
    for i, e in enumerate(els):
        if e.peca:
            por_peca[e.peca].append(i)
    pontas_ok = pontas_total = 0
    for peca, lst in por_peca.items():
        pts = [(p, i) for i in lst for s in els[i].segs for p in s]
        xy = [p[:2] for p, _i in pts]
        # eixo da treliça: as duas pontas mais distantes em planta (o caminho pode ser curvo)
        a = max(xy, key=lambda q: math.dist(q, xy[0]))
        b = max(xy, key=lambda q: math.dist(q, a))
        for ponta in (a, b):
            perto = [(p, i) for p, i in pts if math.dist(p[:2], ponta) < 200.0]
            ids_ponta = {i for _p, i in perto}
            apoiada = False
            for i in ids_ponta:
                for j in viz.get(i, {}):
                    ej = els[j]
                    if ej.peca == peca or ej.papel in ACESSORIOS:
                        continue
                    apoiada = True
                    break
                if apoiada:
                    break
            pontas_total += 1
            if apoiada:
                pontas_ok += 1
                continue
            baixo = min(perto, key=lambda pi: pi[0][2])[0] if perto else (ponta[0], ponta[1], 0.0)
            achados.append(_achado("ponta_sem_apoio", "%s: ponta sem pilar, treliça ou viga embaixo" % (
                els[lst[0]].nome or peca), baixo, [els[i].id for i in lst], peca=els[lst[0]].nome or peca))

    # ------------------------------------------------------------- terças
    tercas_ok = 0
    tercas = [i for i, e in enumerate(els) if e.papel == "terça"]
    for i in tercas:
        e = els[i]
        a, b = e.segs[0]
        L = math.dist(a, b)
        # (s ao longo da terça, j do apoio): um cruzamento por treliça, medido no banzo (a
        # terça encosta também em montantes e diagonais da mesma treliça)
        por_apoio: Dict[object, Tuple[float, float, int]] = {}
        faixas = []                    # (s0, s1): trecho da terça que corre em cima de um apoio
        u = tuple((b[k] - a[k]) / L for k in range(3)) if L > 0 else (1.0, 0.0, 0.0)
        for j in viz.get(i, {}):
            ej = els[j]
            if ej.papel in ACESSORIOS or ej.papel == "pilar":
                continue
            best = min((_dist_seg_seg(a, b, c, d) for c, d in ej.segs), key=lambda r: r[0])
            chave = ej.peca or j
            nota = best[0] + (0.0 if ej.papel in ("banzo", "viga", "solido") else 1000.0)
            if chave not in por_apoio or nota < por_apoio[chave][0]:
                por_apoio[chave] = (nota, best[1] * L, j)
            # o apoio paralelo (a terça deitada ao longo da transição) apoia o trecho todo
            for c, d in ej.segs:
                Ld = math.dist(c, d)
                if Ld < 1.0 or _dist_seg_seg(a, b, c, d)[0] >= tol:
                    continue
                if abs(_dot(u, _sub(d, c))) / Ld > 0.95:
                    sc, sd = _dot(_sub(c, a), u), _dot(_sub(d, a), u)
                    faixas.append((max(0.0, min(sc, sd)), min(L, max(sc, sd))))
        cruz = [(s, j) for _n, s, j in por_apoio.values()]
        if not cruz:
            achados.append(_achado("terca_sem_apoio", "terça %s sem nenhum apoio" % (e.nome or ""), a, [e.id], peca=e.nome))
            continue
        s0 = min([c[0] for c in cruz] + [f[0] for f in faixas])
        s1 = max([c[0] for c in cruz] + [f[1] for f in faixas])
        ok = True
        for s_b, p in ((s0, a), (L - s1, b)):
            if s_b > BALANCO_MAX:
                ok = False
                achados.append(_achado("terca_em_balanco", "terça %s passa %s do último apoio" % (
                    e.nome or "", _m(s_b)), p, [e.id], peca=e.nome, balanco_mm=round(s_b)))
        # nós: onde a alma da treliça encontra o banzo de cima
        for s, j in cruz:
            ej = els[j]
            if not ej.peca:
                continue
            p = tuple(a[k] + (b[k] - a[k]) * s / L for k in range(3))
            # só vale para a terça que senta em cima: a que encosta do lado (painel,
            # transição que sobe acima do telhado) não tem nó do banzo onde cair
            topo = max((q[2] for k in por_peca.get(ej.peca, []) if els[k].papel == "banzo" for sg in els[k].segs
                        for q in sg if math.dist(q[:2], p[:2]) < 600.0), default=None)
            if topo is not None and p[2] < topo - 50.0:
                continue
            nos = [q for k in por_peca.get(ej.peca, []) if els[k].papel in ALMA for sg in els[k].segs for q in sg
                   if abs(q[2] - p[2]) < 400.0]
            dmin = min((math.dist(q[:2], p[:2]) for q in nos), default=None)
            if dmin is None or dmin > FORA_DO_NO:
                ok = False
                achados.append(_achado("terca_fora_do_no", "terça %s cruza %s a %s do nó" % (
                    e.nome or "", ej.nome or ej.peca, _m(dmin) if dmin is not None else "longe"),
                    p, [e.id, ej.id], peca=ej.nome or ej.peca, dist_mm=round(dmin) if dmin is not None else None))
        tercas_ok += ok

    # ------------------------------------------------------------- pilares e vigas
    for i in pil:
        e = els[i]
        a, b = e.segs[0]
        topo = a if a[2] > b[2] else b
        carrega = False
        for j in viz.get(i, {}):
            ej = els[j]
            if ej.papel in ("pilar",) or ej.papel in ("corrente", "contraventamento"):
                continue
            if min(_dist_pt_seg(topo, c, d)[0] for c, d in ej.segs) < tol + 150.0:
                carrega = True
                break
        if not carrega:
            achados.append(_achado("pilar_sem_carga", "pilar %s sem peça em cima" % (e.nome or ""), topo, [e.id],
                                   peca=e.nome))
    for i, e in enumerate(els):
        if e.papel != "viga":
            continue
        a, b = e.segs[0]
        for p in (a, b):
            apoiada = False
            for j in viz.get(i, {}):
                ej = els[j]
                if ej.papel in ACESSORIOS:
                    continue
                if ej.papel == "viga" and ej.nome == e.nome and all(
                        _dist_pt_seg(q, *e.segs[0])[0] < 300.0 for q in ej.segs[0]):
                    continue            # o outro perfil da mesma viga dupla
                if min(_dist_pt_seg(p, c, d)[0] for c, d in ej.segs) < tol + 150.0:
                    apoiada = True
                    break
            if not apoiada:
                achados.append(_achado("viga_sem_apoio", "viga %s com a ponta sem apoio" % (e.nome or ""), p, [e.id],
                                       peca=e.nome))

    cont = collections.Counter(a["regra"] for a in achados)
    resumo = {"pecas": len(els), "soltas": soltos, "pontas_trelica": pontas_total, "pontas_apoiadas": pontas_ok,
              "tercas": len(tercas), "tercas_ok": tercas_ok, "pilares": len(pil), "por_regra": dict(cont)}
    return {"resumo": resumo, "achados": achados}
