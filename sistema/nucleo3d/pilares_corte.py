# -*- coding: utf-8 -*-
"""Pilares com corte próprio no projeto recebido ("PM6 - 3X", "PM8 - 1X").

A locação diz onde cada pilar fica e com que perfil; o corte diz a forma dele quando não é
um pilar reto simples: o PM6 do Posto CB é um pilar em árvore (2Ue 400×200 de 6 m com uma
copa treliçada em cruz de 4,11 m em cima e quatro mãos-francesas MF1), o PM8 é um perfil
duplo inclinado a 51° que segura a passarela. Sem ler o corte, o modelo punha um pilar reto
e o Verificar apoios reclamava de "pilar sem peça em cima".

Leitura (só o que o desenho mostra; o que precisou de escolha fica em `a_conferir`):
- o corte é o título "PMn - kX" com as vistas rotuladas acima dele (VISTA LATERAL, VISTA
  SUPERIOR, VISTA FRONTAL); o desenho de cada vista é o aglomerado de linhas estruturais
  logo acima do rótulo;
- na vista lateral, as linhas compridas e paralelas são o pilar: dão a inclinação e o
  comprimento. Reto, o que fica acima do topo é a copa (banzos horizontais, montantes e
  diagonais) e o que liga o pilar à copa por baixo são as mãos-francesas;
- na vista superior, os braços da copa (0°/90°, compridos) dizem a cruz: quanto sai para
  cada lado;
- a nota "BANZO …" / "DIAG/MONT …" do corte dá os perfis da copa.

Montagem: o pilar reto continua o da montagem normal (a copa e as mãos-francesas entram
por cima dele); o inclinado substitui o pilar reto — sai da placa de base da locação, no
sentido do lado comprido da placa, para o lado em que há estrutura no nível de chegada.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

Ponto2 = Tuple[float, float]

_RX_TITULO = re.compile(r"^\s*(PM\s*\d+[A-Z]?)\s*-\s*(\d+)\s*X\s*$", re.I)
_RX_VISTA = re.compile(r"^\s*VISTA\s+(LATERAL|SUPERIOR|FRONTAL)\s*$", re.I)
_RX_ESTRUTURAL = re.compile(r"(?i)metalica|chapa")
_RX_FORA = re.compile(r"(?i)cota|eixo|texto|hachura")
GAP = 450.0            # mm: linhas a menos disso uma da outra são o mesmo desenho
PILAR_MIN = 2500.0     # mm: a linha do pilar é comprida


def _pts(e) -> List[Ponto2]:
    if e.get("tipo") == "linha":
        return [tuple(e["a"][:2]), tuple(e["b"][:2])]
    if e.get("tipo") == "polilinha":
        v = [tuple(p[:2]) for p in e.get("vertices") or []]
        return v + ([v[0]] if e.get("fechada") and len(v) > 2 else [])
    if e.get("tipo") == "arco":
        c, r = e["centro"], float(e["raio"])
        # o desenho guarda os ângulos do arco em "inicio"/"fim" (graus)
        a0 = math.radians(float(e.get("inicio", e.get("ini", 0.0))))
        a1 = math.radians(float(e.get("fim", 360.0)))
        if a1 <= a0:
            a1 += 2 * math.pi
        n = max(4, int((a1 - a0) / math.radians(10)))
        return [(c[0] + r * math.cos(a0 + (a1 - a0) * k / n), c[1] + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    return []


def _segs(e) -> List[Tuple[Ponto2, Ponto2]]:
    p = _pts(e)
    return list(zip(p, p[1:]))


def _caixa(pts) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _toca(a, b, gap) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def _aglomerado(ents, desde: Ponto2, alcance=(9000.0, 15000.0)) -> List[dict]:
    """as entidades estruturais ligadas por proximidade ao desenho que fica logo acima do
    ponto `desde` (o rótulo da vista), dentro de `alcance` (dx, dy). Grade de células: cada
    entidade marca as células que a caixa dela (com a folga GAP) cobre, e o aglomerado é a
    varredura das células a partir da entidade mais perto do rótulo — o custo é o número de
    entidades, não o quadrado dele (a folha dos cortes é densa)."""
    cand = []
    for e in ents:
        cam = str(e.get("camada") or "")
        if not _RX_ESTRUTURAL.search(cam) or _RX_FORA.search(cam):
            continue
        pts = _pts(e)
        if len(pts) < 2:
            continue
        cx = _caixa(pts)
        if cx[2] < desde[0] - alcance[0] or cx[0] > desde[0] + alcance[0] or cx[3] < desde[1] - 300.0 or cx[1] > desde[1] + alcance[1]:
            continue
        cand.append((e, cx))
    if not cand:
        return []
    CEL = GAP
    celulas: Dict[Tuple[int, int], List[int]] = {}
    chaves = []
    for k, (_e, cx) in enumerate(cand):
        ks = []
        for ix in range(int(math.floor((cx[0] - GAP / 2) / CEL)), int(math.floor((cx[2] + GAP / 2) / CEL)) + 1):
            for iy in range(int(math.floor((cx[1] - GAP / 2) / CEL)), int(math.floor((cx[3] + GAP / 2) / CEL)) + 1):
                celulas.setdefault((ix, iy), []).append(k)
                ks.append((ix, iy))
        chaves.append(ks)
    inicio = min(range(len(cand)), key=lambda i: (max(0.0, cand[i][1][1] - desde[1]) + abs((cand[i][1][0] + cand[i][1][2]) / 2 - desde[0]) * 0.3))
    dentro = {inicio}
    fila = [inicio]
    while fila:
        k = fila.pop()
        for ch in chaves[k]:
            for k2 in celulas.get(ch, ()):
                if k2 not in dentro and _toca(cand[k][1], cand[k2][1], GAP):
                    dentro.add(k2)
                    fila.append(k2)
    return [cand[i][0] for i in sorted(dentro)]


def ler_cortes_de_pilar(ents, textos) -> Dict[str, dict]:
    """{"PM6": {"qtd", "titulo", "vistas": {"lateral": [ents], "superior": [...], "frontal": [...]},
    "notas": [texto], "ids": {ids}}} — os cortes de pilar do desenho"""
    out: Dict[str, dict] = {}
    rotulos = [t for t in textos if _RX_VISTA.match(str(t.get("texto") or ""))]
    for t in textos:
        m = _RX_TITULO.match(str(t.get("texto") or ""))
        if not m:
            continue
        nome = m.group(1).upper().replace(" ", "")
        tx, ty = t["posicao"][0], t["posicao"][1]
        vistas: Dict[str, List[dict]] = {}
        ids = {t.get("id")}
        for r in rotulos:
            tipo = _RX_VISTA.match(r["texto"]).group(1).lower()
            rx, ry = r["posicao"][0], r["posicao"][1]
            if not (tx - 12000.0 <= rx <= tx + 12000.0 and ty - 400.0 <= ry <= ty + 16000.0):
                continue
            # o rótulo desta vista é o mais perto do título entre os do mesmo tipo
            d = math.hypot(rx - tx, ry - ty)
            if tipo in vistas and vistas[tipo][0] <= d:
                continue
            vistas[tipo] = (d, r)
        blocos = {}
        for tipo, (_d, r) in vistas.items():
            ents_v = _aglomerado(ents, (r["posicao"][0], r["posicao"][1]))
            blocos[tipo] = ents_v
            ids |= {e.get("id") for e in ents_v} | {r.get("id")}
        # as notas de perfil perto do corte (acima do título, até a altura das vistas)
        notas = [n for n in textos if tx - 8000.0 <= n["posicao"][0] <= tx + 9000.0 and ty - 400.0 <= n["posicao"][1] <= ty + 16000.0
                 and re.search(r"(?i)banzo|diag|mont|Ue|\d+x\d+x", str(n.get("texto") or ""))]
        ids |= {n.get("id") for n in notas}
        out[nome] = {"qtd": int(m.group(2)), "titulo": t, "vistas": blocos, "notas": [str(n["texto"]) for n in notas],
                     "ids": {i for i in ids if i}}
    return out


def _pilar_na_vista(ents_v) -> Optional[dict]:
    """as linhas compridas e paralelas da vista: {"ang" (graus, da horizontal), "L", "base",
    "topo", "largura"} — o eixo do pilar como a vista o desenha"""
    longas = []
    for e in ents_v:
        for a, b in _segs(e):
            L = math.dist(a, b)
            if L >= PILAR_MIN:
                longas.append((L, a, b, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0))
    if not longas:
        return None
    longas.sort(reverse=True)
    L0, _a, _b, ang0 = longas[0]
    grupo = [x for x in longas if min(abs(x[3] - ang0), 180.0 - abs(x[3] - ang0)) < 2.0 and x[0] >= 0.6 * L0]
    # a linha de cada borda, orientada de baixo para cima
    bordas = []
    for L, a, b, ang in grupo:
        if a[1] > b[1]:
            a, b = b, a
        bordas.append((a, b))
    base = (sum(p[0][0] for p in bordas) / len(bordas), sum(p[0][1] for p in bordas) / len(bordas))
    topo = (sum(p[1][0] for p in bordas) / len(bordas), sum(p[1][1] for p in bordas) / len(bordas))
    ang = math.degrees(math.atan2(topo[1] - base[1], topo[0] - base[0]))
    u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    n = (-u[1], u[0])
    offs = [(p[0][0] - base[0]) * n[0] + (p[0][1] - base[1]) * n[1] for p in bordas]
    return {"ang": ang, "L": math.dist(base, topo), "base": base, "topo": topo, "largura": (max(offs) - min(offs)) if len(offs) > 1 else 0.0,
            "n_bordas": len(bordas)}


def _copa_na_vista(ents_v, pilar: dict) -> Optional[dict]:
    """no pilar reto, o que fica em cima dele: os banzos da copa (horizontais compridos, na
    faixa logo acima do topo — uma altura só, ou duas quando há treliça), a alma entre eles e
    as mãos-francesas por baixo, como o corte as desenha. Posições relativas ao eixo do pilar
    (s) e ao topo dele (dz)."""
    if abs(pilar["ang"] - 90.0) > 5.0:
        return None
    x0, ytopo = pilar["topo"]
    meia = pilar["largura"] / 2.0
    segs = [(a, b) for e in ents_v for a, b in _segs(e) if math.dist(a, b) >= 60.0]
    # o banzo da copa passa por cima do pilar: a horizontal de um desenho vizinho não passa
    horiz = [(a, b) for a, b in segs if abs(a[1] - b[1]) < 20.0 and math.dist(a, b) >= 800.0
             and ytopo - 150.0 <= (a[1] + b[1]) / 2 <= ytopo + 2500.0
             and min(a[0], b[0]) - 300.0 <= x0 <= max(a[0], b[0]) + 300.0]
    if not horiz:
        return None
    niveis = sorted({round((a[1] + b[1]) / 2.0 / 20.0) * 20.0 for a, b in horiz})
    z_baixo = niveis[0]
    z_cima = max([n for n in niveis if n - z_baixo <= 2000.0], default=z_baixo)
    if z_cima - z_baixo < 300.0:
        z_cima = z_baixo                                  # uma viga: as duas linhas do perfil
    banzos = [(a, b) for a, b in horiz if z_baixo - 60.0 <= (a[1] + b[1]) / 2 <= z_cima + 60.0]
    esq = min(min(a[0], b[0]) for a, b in banzos) - x0
    dir_ = max(max(a[0], b[0]) for a, b in banzos) - x0
    alcance = max(abs(esq), abs(dir_)) + 60.0
    membros = []
    if z_cima > z_baixo:
        for a, b in segs:
            if abs(a[1] - b[1]) < 20.0:
                continue
            if min(a[1], b[1]) < z_baixo - 60.0 or max(a[1], b[1]) > z_cima + 60.0 or max(abs(a[0] - x0), abs(b[0] - x0)) > alcance:
                continue
            s0, s1 = a[0] - x0, b[0] - x0
            h0, h1 = a[1] - z_baixo, b[1] - z_baixo
            papel = "montante" if abs(s1 - s0) < 0.1 * abs(h1 - h0) + 1.0 else "diagonal"
            membros.append((s0, h0, s1, h1, papel))
    # a mão-francesa: o que fica entre o pilar e a copa, fora do pilar, abaixo do banzo de baixo
    maos = {-1: [], 1: []}
    for a, b in segs:
        if max(a[1], b[1]) > z_baixo + 60.0 or min(a[1], b[1]) < ytopo - 4000.0:
            continue
        if max(abs(a[0] - x0), abs(b[0] - x0)) <= meia + 40.0 or max(abs(a[0] - x0), abs(b[0] - x0)) > alcance:
            continue
        if abs(a[1] - b[1]) < 20.0 and min(a[1], b[1]) >= z_baixo - 60.0:
            continue                                       # é o próprio banzo
        lado = 1 if (a[0] + b[0]) / 2 > x0 else -1
        maos[lado].append((a[0] - x0, a[1] - ytopo, b[0] - x0, b[1] - ytopo))
    # a cantoneira dupla é desenhada como duas linhas paralelas: vira uma só, no meio; e só
    # fica o que se encadeia pelas pontas até o pilar ou até a ponta do braço — uma linha do
    # desenho vizinho que o aglomerado trouxe não chega a nenhum dos dois
    maos = {lado: _encadeados(_juntar_paralelas(v), meia, abs(esq) if lado < 0 else abs(dir_)) for lado, v in maos.items()}
    return {"altura": z_cima - z_baixo, "z_baixo": z_baixo - ytopo, "esq": esq, "dir": dir_, "membros": membros,
            "maos": maos, "n_maos": sum(1 for v in maos.values() if v)}


def _encadeados(segs, meia, s_fim, tol=70.0):
    """os segmentos ligados, ponta com ponta, aos que encostam no pilar (|s| ≤ meia + tol) ou
    na ponta do braço (|s| ≥ s_fim − 150)"""
    segs = list(segs)
    if not segs:
        return segs

    def raiz_ok(x0, y0, x1, y1):
        return min(abs(x0), abs(x1)) <= meia + tol or max(abs(x0), abs(x1)) >= s_fim - 150.0
    dentro = {i for i, sg in enumerate(segs) if raiz_ok(*sg)}
    mudou = True
    while mudou:
        mudou = False
        for i, (x0, y0, x1, y1) in enumerate(segs):
            if i in dentro:
                continue
            for j in dentro:
                a0, b0, a1, b1 = segs[j]
                if min(math.hypot(x0 - a0, y0 - b0), math.hypot(x0 - a1, y0 - b1), math.hypot(x1 - a0, y1 - b0), math.hypot(x1 - a1, y1 - b1)) <= tol:
                    dentro.add(i)
                    mudou = True
                    break
    return [sg for i, sg in enumerate(segs) if i in dentro]


def _juntar_paralelas(segs, dist_max=90.0):
    """pares de segmentos paralelos, perto e sobrepostos (as duas linhas de um perfil) viram
    um segmento só, no meio dos dois"""
    segs = list(segs)
    fora = set()
    out = []
    for i, (x0, y0, x1, y1) in enumerate(segs):
        if i in fora:
            continue
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        par = None
        for j in range(i + 1, len(segs)):
            if j in fora:
                continue
            a0, b0, a1, b1 = segs[j]
            L2 = math.hypot(a1 - a0, b1 - b0)
            if L2 < 1e-6 or abs(ux * (a1 - a0) + uy * (b1 - b0)) / L2 < 0.995:
                continue
            d = abs(-(a0 - x0) * uy + (b0 - y0) * ux)
            if d > dist_max or d < 5.0:
                continue
            t0 = (a0 - x0) * ux + (b0 - y0) * uy
            t1 = (a1 - x0) * ux + (b1 - y0) * uy
            if min(max(t0, t1), L) - max(min(t0, t1), 0.0) < 0.5 * min(L, L2):
                continue
            par = j
            break
        if par is None:
            out.append((x0, y0, x1, y1))
            continue
        a0, b0, a1, b1 = segs[par]
        if (a1 - a0) * ux + (b1 - b0) * uy < 0:
            a0, b0, a1, b1 = a1, b1, a0, b0
        fora.add(par)
        out.append(((x0 + a0) / 2, (y0 + b0) / 2, (x1 + a1) / 2, (y1 + b1) / 2))
    return out


def _bracos_na_superior(ents_v) -> Optional[dict]:
    """na vista superior, os braços da copa: quanto sai em cada direção a partir do centro"""
    longas = []
    for e in ents_v:
        for a, b in _segs(e):
            L = math.dist(a, b)
            if L < 800.0:
                continue
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
            if ang < 3.0 or ang > 177.0:
                longas.append(("x", a, b))
            elif abs(ang - 90.0) < 3.0:
                longas.append(("y", a, b))
    if not longas:
        return None
    pts = [p for _d, a, b in longas for p in (a, b)]
    cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
    cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2
    bx = [p[0] - cx for d, a, b in longas if d == "x" for p in (a, b)]
    by = [p[1] - cy for d, a, b in longas if d == "y" for p in (a, b)]
    return {"x": (min(bx) if bx else 0.0, max(bx) if bx else 0.0), "y": (min(by) if by else 0.0, max(by) if by else 0.0)}


def _perfis_das_notas(notas: Sequence[str]) -> dict:
    from nucleo2d.reconhecer import perfil_do_texto
    out = {}
    for n in notas:
        s = re.split(r"(?i)\bPRES", n)[0]         # "…3 PRES. L 1.1/2…": a presilha não é a barra
        if re.search(r"(?i)^\s*banzo", s):
            out["banzo"] = perfil_do_texto(s)
        elif re.search(r"(?i)diag|mont", s):
            # só o trecho do perfil ("2L 2"X1/8""): o resto da nota confunde o leitor
            m = re.search(r"(\d?\s*L\s*[\d\.\/½¼¾]+\"?\s*X\s*[\d\/\.]+\"?)", s)
            out["alma"] = perfil_do_texto(m.group(1)) if m else perfil_do_texto(s)
        elif re.search(r"(?i)^\s*\d?\s*Ue", s):
            out["pilar"] = perfil_do_texto(s)
    return out


def interpretar(corte: dict) -> dict:
    """o corte lido → {"tipo": "reto"|"inclinado", "ang", "L", "copa", "bracos", "perfis", "avisos"}"""
    vistas = corte["vistas"]
    lateral = vistas.get("lateral") or []
    pilar = _pilar_na_vista(lateral)
    r = {"tipo": None, "perfis": _perfis_das_notas(corte["notas"]), "avisos": [], "pilar": pilar}
    if not pilar:
        r["avisos"].append("não achei o pilar na vista lateral")
        return r
    if abs(pilar["ang"] - 90.0) <= 5.0:
        r["tipo"] = "reto"
        r["copa"] = _copa_na_vista(lateral, pilar)
        r["bracos"] = _bracos_na_superior(vistas.get("superior") or [])
    else:
        r["tipo"] = "inclinado"
        frontal = vistas.get("frontal") or []
        pf = _pilar_na_vista(frontal) if frontal else None
        r["afastamento"] = pf["largura"] if pf else None
    return r


def _u(a, b):
    L = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L


def sentido_da_placa(ents_loc, mover, ponto: Ponto2, raio=900.0) -> Optional[Ponto2]:
    """o lado comprido da placa de base desenhada em volta do ponto (camada Chapas), como
    vetor unitário — o plano em que o pilar inclinado inclina"""
    melhor = None
    for e in ents_loc:
        if not re.search(r"(?i)chapa", str(e.get("camada") or "")) or e.get("tipo") not in ("polilinha", "linha"):
            continue
        pts = [mover(p) for p in _pts(e)]
        if not pts or min(math.dist(p, ponto) for p in pts) > raio:
            continue
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if melhor is None or L > melhor[0]:
                melhor = (L, _u(a, b)[0])
    return melhor[1] if melhor else None


def montar(cortes: Dict[str, dict], locados: Sequence[dict], barra, nivel: float, base: float,
           perto_da_estrutura, ents_loc, mover_loc, avisos: List[str]) -> dict:
    """monta os pilares que têm corte: a copa e as mãos-francesas por cima do pilar reto (que a
    montagem normal já fez) e o pilar inclinado inteiro. `perto_da_estrutura(p)` diz a distância
    em planta do ponto à estrutura montada (para escolher o lado da inclinação).
    Devolve {"inclinados": {nomes dos locados que não devem virar pilar reto}, "n": peças}"""
    from nucleo3d.de_planta import _perfil
    inclinados = set()
    n = 0
    lidos = {}
    for nome, corte in cortes.items():
        lidos[nome] = interpretar(corte)
    for pl in locados:
        nome = re.sub(r"\(.*$", "", str(pl.get("nome") or "")).upper().replace(" ", "")
        if nome not in lidos:
            continue
        lido = lidos[nome]
        x, y = pl["x"], pl["y"]
        perfil_pl = pl["perfil"]
        pa = _perfil(perfil_pl)
        if lido["tipo"] == "inclinado":
            u = sentido_da_placa(ents_loc, mover_loc, (x, y))
            if u is None:
                avisos.append("%s em (%.0f; %.0f): o corte mostra o pilar inclinado a %.0f°, mas não achei a placa de base "
                              "na locação para saber o sentido; ficou reto." % (nome, x, y, lido["pilar"]["ang"]))
                continue
            inclinados.add(pl["nome"])
            ang = lido["pilar"]["ang"]
            L = lido["pilar"]["L"]
            # o lado: o que leva o topo (no nível de chegada) para perto da estrutura
            run = (nivel - base) / math.tan(math.radians(ang)) if abs(ang) > 1e-6 else 0.0
            cands = []
            for s in (1.0, -1.0):
                topo = (x + u[0] * run * s, y + u[1] * run * s)
                cands.append((perto_da_estrutura(topo), s))
            d_perto, s = min(cands)
            ux, uy = u[0] * s, u[1] * s
            dz = L * math.sin(math.radians(ang))
            dxy = L * math.cos(math.radians(ang))
            mult = int((lido["perfis"].get("pilar") or {}).get("mult") or 1)
            af = (float(pa.bf or 125.0) if pa else 125.0) / 2 + 3.0 if mult > 1 else 0.0
            nx, ny = -uy, ux
            orig = {"locacao": pl["nome"], "corte": "%s - %dX" % (nome, corte["qtd"]),
                    "a_conferir": "pilar inclinado a %.1f°, %.2f m, no sentido do lado comprido da placa de base; o lado "
                                  "foi o que leva o topo para a estrutura mais perto (%.1f m)" % (ang, L / 1000.0, d_perto / 1000.0)}
            for sinal in ((1.0, -1.0) if mult > 1 else (0.0,)):
                p0 = (x + nx * af * sinal, y + ny * af * sinal, base)
                p1 = (x + ux * dxy + nx * af * sinal, y + uy * dxy + ny * af * sinal, base + dz)
                if barra(p0, p1, perfil_pl, "pilar", "Pilares", None, 0.0, orig):
                    n += 1
            avisos.append("%s: montado inclinado a %.1f° pelo corte (%.2f m, chega ao nível %.2f m aos %.2f m e segue até "
                          "%.2f m); sentido escolhido pela estrutura mais perto do topo — confira." % (
                              nome, ang, L / 1000.0, nivel / 1000.0, (nivel - base) / math.sin(math.radians(ang)) / 1000.0, (base + dz) / 1000.0))
            continue
        if lido["tipo"] != "reto" or not lido.get("copa"):
            if lido["tipo"] == "reto":
                avisos.append("%s: o corte mostra pilar reto sem copa; nada a acrescentar." % nome)
            continue
        copa = lido["copa"]
        bracos = lido.get("bracos") or {"x": (copa["esq"], copa["dir"]), "y": (0.0, 0.0)}
        p_banzo = (lido["perfis"].get("banzo") or {}).get("perfil") or perfil_pl
        p_alma = (lido["perfis"].get("alma") or {}).get("perfil") or p_banzo
        topo_pilar = base + lido["pilar"]["L"]
        z0 = topo_pilar + copa["z_baixo"]                          # o banzo (de baixo) da copa
        z1 = z0 + copa["altura"]
        rot = math.radians(float(pl.get("rot") or 0.0))
        conj = "%s copa#%d" % (nome, int(abs(x) + abs(y)) % 100000)
        orig = {"locacao": pl["nome"], "corte": "%s - %dX" % (nome, corte["qtd"]), "peca": conj}
        if abs(z1 - nivel) > 150.0:
            orig["a_conferir"] = "copa em %.2f m; a estrutura sobre o pilar está no nível %.2f m" % (z1 / 1000, nivel / 1000)
        meia = (lido["pilar"]["largura"] or (float(pa.d or 400.0) if pa else 400.0)) / 2.0

        def P(dx, dy, z):
            return (x + dx * math.cos(rot) - dy * math.sin(rot), y + dx * math.sin(rot) + dy * math.cos(rot), z)
        # o corte mostra os dois lados; o lado direito é o gabarito de cada braço (o esquerdo
        # espelhado, se o direito não tiver desenho)
        alma = [(abs(s0), h0, abs(s1), h1, papel) for s0, h0, s1, h1, papel in copa["membros"] if (s0 + s1) / 2 > 0] or \
               [(abs(s0), h0, abs(s1), h1, papel) for s0, h0, s1, h1, papel in copa["membros"] if (s0 + s1) / 2 < 0]
        mao = copa["maos"].get(1) or copa["maos"].get(-1) or []
        bracos_lista = []
        for d, (neg, pos) in (((1.0, 0.0), bracos["x"]), ((0.0, 1.0), bracos["y"])):
            for s_fim, sinal in ((abs(neg), -1.0), (abs(pos), 1.0)):
                if s_fim >= 500.0:
                    bracos_lista.append((d[0] * sinal, d[1] * sinal, s_fim))
        for ex, ey, s_fim in bracos_lista:
            niveis = ((z0, 90.0), (z1, 270.0)) if copa["altura"] > 0 else ((z0, 270.0),)
            for z, r_ in niveis:
                if barra(P(ex * meia, ey * meia, z), P(ex * s_fim, ey * s_fim, z), p_banzo, "banzo", "Treliças", conj, r_, orig):
                    n += 1
            for a0, h0, a1, h1, papel in alma:
                if max(a0, a1) > s_fim + 60.0 or min(a0, a1) < meia - 60.0:
                    continue
                if barra(P(ex * a0, ey * a0, z0 + h0), P(ex * a1, ey * a1, z0 + h1), p_alma, papel, "Treliças", conj, 0.0, orig):
                    n += 1
            orig_mf = dict(orig, mao_francesa="MF1")
            for s0, dz0, s1, dz1 in mao:
                a0, a1 = min(abs(s0), s_fim), min(abs(s1), s_fim)
                papel = "montante" if abs(a1 - a0) < 0.1 * abs(dz1 - dz0) + 1.0 else "diagonal"
                if barra(P(ex * a0, ey * a0, topo_pilar + dz0), P(ex * a1, ey * a1, topo_pilar + dz1), p_alma, papel, "Treliças", conj, 0.0, orig_mf):
                    n += 1
        maior = max(abs(v) for par in bracos.values() for v in par) / 1000.0
        avisos.append("%s: copa em cruz pelo corte (braços de %.2f m em %.2f m%s) com mão-francesa MF1 de %d peças em cada braço; %s" % (
            nome, maior, z1 / 1000.0, ", treliça de %.2f m" % (copa["altura"] / 1000.0) if copa["altura"] > 0 else "", len(mao),
            ("a estrutura sobre o pilar está em %.2f m — confira o nível da base do %s." % (nivel / 1000.0, nome))
            if abs(z1 - nivel) > 150.0 else "no nível da estrutura."))
    return {"inclinados": inclinados, "n": n, "lidos": lidos}
