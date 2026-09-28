"""As escadas do projeto recebido, pela planta baixa de cada uma ("PLANTA BAIXA DA ESCADA 1").

A planta desenha, em tamanho real, as longarinas (linha dupla do perfil, "Ue 200X40X20X3,04"), o
patamar e os degraus numerados do primeiro ao último (o último é a chegada no piso de cima). Daqui:

1. a região da planta: acima do título, até o próximo título e até o meio do caminho para o título
   ao lado (as plantas e os cortes das escadas ficam encostados);
2. as longarinas: as linhas longas (fora das camadas de anotação), em pares a ~40 mm (as duas linhas do
   perfil) → o eixo de cada uma; dois eixos paralelos a 0,6–1,6 m são um lance;
3. o patamar é onde dois lances se cruzam; os degraus numerados dentro de cada lance dizem para
   que lado ele sobe;
4. o lugar no modelo: os balões da planta da escada com o mesmo nome dos balões já alinhados (a
   planta estrutural, a locação, as outras plantas) — a letra do eixo dá y, o número dá x; o que os
   balões não dão vem dos pés da escada na locação (as placas "ESC ..."), na linha das longarinas;
5. as alturas: do chão ao piso de cima (o nível da planta que ela serve), com o degrau de altura
   igual — o patamar na altura do degrau dele.

`ler(ents, textos, referencia, pes_esc, altura, avisos)` devolve as escadas: lances e patamar com as
pontas em mm, já no lugar da planta estrutural.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

Ponto2 = Tuple[float, float]
TITULO = re.compile(r"(?i)^\s*PLANTA\s+BAIXA\s+DA\s+ESCADA\s*(.*)$")
LINHA_MIN = 1500.0           # mm: longarina (as linhas curtas são degraus e cotas)
PAR_PERFIL = (15.0, 90.0)    # mm entre as duas linhas do perfil da longarina
LARGURA_LANCE = (600.0, 1600.0)
#: camadas que não são peça (a longarina vem em qualquer outra: "metalica3", "1-Tesoura Banzo"…)
ANOTACAO = re.compile(r"(?i)cota|eixo|alvenaria|linha fina|texto|hachur|vista|defpoints|carimbo|folha")


def _dentro(p, c) -> bool:
    return c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3]


def regioes(textos) -> List[Tuple[dict, Tuple[float, float, float, float]]]:
    """(título, região da planta) de cada escada"""
    tits = [t for t in textos if TITULO.match(str(t.get("texto") or ""))]
    grandes = [t for t in textos if float(t.get("altura") or 0) >= 8.0]
    out = []
    for t in tits:
        x, y = t["posicao"][0], t["posicao"][1]
        h = float(t.get("altura") or 10.0)
        vizinhos = [o["posicao"][0] for o in tits if o is not t and abs(o["posicao"][1] - y) < 3000 and o["posicao"][0] > x]
        x1 = min(vizinhos) - 1500.0 if vizinhos else x + 14000.0
        acima = [o["posicao"][1] for o in grandes if o is not t and float(o.get("altura") or 0) >= 0.8 * h
                 and x - 1500 <= o["posicao"][0] <= x1 and o["posicao"][1] > y + 1000]
        y1 = min(acima) - 300.0 if acima else y + 12000.0
        out.append((t, (x - 1500.0, y + 200.0, x1, y1)))
    return out


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return ((dx / L, dy / L), L) if L > 1e-9 else ((1.0, 0.0), 0.0)


def _eixos_das_longarinas(linhas) -> List[dict]:
    """as duas linhas de cada perfil → o eixo (no meio delas), com a extensão das duas"""
    eixos, usadas = [], set()
    for i, a in enumerate(linhas):
        if i in usadas:
            continue
        (ux, uy), La = _unit(a["a"], a["b"])
        n = (-uy, ux)
        melhor = None
        for j, b in enumerate(linhas):
            if j == i or j in usadas:
                continue
            (vx, vy), _ = _unit(b["a"], b["b"])
            if abs(ux * vy - uy * vx) > 0.02:
                continue
            d = (b["a"][0] - a["a"][0]) * n[0] + (b["a"][1] - a["a"][1]) * n[1]
            if PAR_PERFIL[0] <= abs(d) <= PAR_PERFIL[1] and (melhor is None or abs(d) < abs(melhor[0])):
                melhor = (d, j)
        if melhor is None:
            continue
        d, j = melhor
        usadas.update((i, j))
        b = linhas[j]
        s = [(p[0] - a["a"][0]) * ux + (p[1] - a["a"][1]) * uy for p in (a["a"], a["b"], b["a"], b["b"])]
        base = (a["a"][0] + n[0] * d / 2.0, a["a"][1] + n[1] * d / 2.0)
        eixos.append({"u": (ux, uy), "n": n, "base": base, "s0": min(s), "s1": max(s),
                      "lat": base[0] * n[0] + base[1] * n[1]})
    return eixos


def _lances(eixos) -> List[dict]:
    """dois eixos de longarina paralelos, a uma largura de lance, que se sobrepõem"""
    out, usados = [], set()
    for i, a in enumerate(eixos):
        for j, b in enumerate(eixos):
            if j <= i or i in usados or j in usados:
                continue
            if abs(a["u"][0] * b["u"][1] - a["u"][1] * b["u"][0]) > 0.02:
                continue
            larg = abs(a["lat"] - (b["base"][0] * a["n"][0] + b["base"][1] * a["n"][1]))
            if not (LARGURA_LANCE[0] <= larg <= LARGURA_LANCE[1]):
                continue
            ub = [(p[0] - a["base"][0]) * a["u"][0] + (p[1] - a["base"][1]) * a["u"][1] for p in
                  ((b["base"][0] + b["u"][0] * b["s0"], b["base"][1] + b["u"][1] * b["s0"]),
                   (b["base"][0] + b["u"][0] * b["s1"], b["base"][1] + b["u"][1] * b["s1"]))]
            if min(max(ub), a["s1"]) - max(min(ub), a["s0"]) < 500.0:
                continue
            usados.update((i, j))
            out.append({"eixos": (a, b), "u": a["u"], "n": a["n"], "base": a["base"],
                        "s0": min(a["s0"], min(ub)), "s1": max(a["s1"], max(ub)),
                        "lats": sorted((a["lat"], b["base"][0] * a["n"][0] + b["base"][1] * a["n"][1]))})
    return out


def _caixa(l) -> Tuple[float, float, float, float]:
    pts = []
    for s in (l["s0"], l["s1"]):
        for lat in l["lats"]:
            # o ponto de s ao longo e lat de lado: base + u·s + n·(lat − lat da base)
            lb = l["base"][0] * l["n"][0] + l["base"][1] * l["n"][1]
            pts.append((l["base"][0] + l["u"][0] * s + l["n"][0] * (lat - lb),
                        l["base"][1] + l["u"][1] * s + l["n"][1] * (lat - lb)))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _inter(c1, c2):
    c = (max(c1[0], c2[0]), max(c1[1], c2[1]), min(c1[2], c2[2]), min(c1[3], c2[3]))
    return c if c[2] > c[0] and c[3] > c[1] else None


def _alinhar(proprios: Dict[str, Ponto2], referencia: Dict[str, List[Ponto2]]) -> Tuple[Optional[float], Optional[float], List[str]]:
    """(dx, dy) pelos balões de mesmo nome: o balão numa coluna com outros (mesmo x) é de eixo
    horizontal e dá dy; numa fila (mesmo y), de eixo vertical e dá dx"""
    dxs, dys, usados = [], [], []
    for nome, p in proprios.items():
        refs = referencia.get(nome) or []
        if not refs:
            continue
        coluna = any(abs(q[0] - p[0]) < 300 for k, q in proprios.items() if k != nome)
        fila = any(abs(q[1] - p[1]) < 300 for k, q in proprios.items() if k != nome)
        if coluna and not fila:
            dys.append(sorted(r[1] for r in refs)[len(refs) // 2] - p[1])
            usados.append(nome)
        elif fila and not coluna:
            dxs.append(sorted(r[0] for r in refs)[len(refs) // 2] - p[0])
            usados.append(nome)
    med = lambda v: sorted(v)[len(v) // 2] if v else None      # noqa: E731
    return med(dxs), med(dys), usados


def patamar_dos_cortes(textos, regs, altura: float) -> Optional[float]:
    """a altura do patamar pelas cotas dos cortes das escadas (em volta das plantas): as duas cotas
    da mesma corrente vertical que somam a altura da escada (1.700 + 1.470 = 3.170) — o patamar é a
    de baixo, do chão até ele"""
    x0 = min(r[0] for r in regs) - 3000.0
    x1 = max(r[2] for r in regs) + 3000.0
    y0 = min(r[1] for r in regs) - 16000.0
    y1 = max(r[3] for r in regs) + 16000.0
    cotas = [(float(t["texto"]), t["posicao"]) for t in textos if re.fullmatch(r"\d{3,5}", str(t.get("texto") or "").strip())
             and "cota" in str(t.get("camada") or "").lower() and x0 <= t["posicao"][0] <= x1 and y0 <= t["posicao"][1] <= y1]
    votos: Dict[float, int] = {}
    for i, (a, pa) in enumerate(cotas):
        for b, pb in cotas[i + 1:]:
            # as duas cotas da mesma corrente vertical (mesmo x); a de baixo vai do chão ao patamar
            if abs(a + b - altura) <= 20.0 and abs(pa[0] - pb[0]) < 400.0 and 0.3 * altura < min(a, b) < 0.7 * altura:
                z = a if pa[1] < pb[1] else b
                votos[z] = votos.get(z, 0) + 1
    return max(votos, key=lambda k: votos[k]) if votos else None


def ler(ents, textos, referencia: Dict[str, List[Ponto2]], pes_esc: Sequence[Ponto2], altura: float,
        avisos: List[str], baloes_de=None) -> List[dict]:
    """as escadas desenhadas em planta baixa, no lugar da planta estrutural: [{nome, perfil,
    perfil_patamar, lances: [(p0, p1)], patamar: [(p0, p1)], degraus, altura, alinhada_por}]
    (pontos (x, y, z) em mm)"""
    out = []
    todas = regioes(textos)
    z_cortes = patamar_dos_cortes(textos, [r for _t, r in todas], altura) if todas else None
    for t, reg in todas:
        nome = "ESCADA " + (TITULO.match(t["texto"]).group(1).strip() or str(len(out) + 1))
        linhas = [e for e in ents if e["tipo"] == "linha" and not ANOTACAO.search(str(e.get("camada") or ""))
                  and _dentro(e["a"], reg) and _dentro(e["b"], reg) and math.dist(e["a"], e["b"]) >= LINHA_MIN]
        lances = _lances(_eixos_das_longarinas(linhas))
        if not lances:
            avisos.append("%s: não achei as longarinas na planta dela (linhas duplas das camadas de metálica)." % nome)
            continue
        numeros = [(int(x["texto"].strip()), x["posicao"]) for x in textos if _dentro(x["posicao"], reg)
                   and re.fullmatch(r"\d{1,2}", str(x.get("texto") or "").strip()) and float(x.get("altura") or 0) < 8.0
                   and "cota" not in str(x.get("camada") or "").lower()]
        if not numeros:
            avisos.append("%s: sem os degraus numerados na planta." % nome)
            continue
        N = max(k for k, _p in numeros)
        caixas = [_caixa(l) for l in lances]
        patamar = None
        if len(lances) >= 2:
            patamar = _inter(caixas[0], caixas[1])
        # os perfis escritos na planta: o da longarina (Ue) e o do patamar (U)
        nomes_p = [x["texto"].strip() for x in textos if _dentro(x["posicao"], reg) and re.match(r"(?i)^U", x["texto"].strip())]
        p_long = next((n for n in nomes_p if n.upper().startswith("UE")), None)
        p_pat = next((n for n in nomes_p if not n.upper().startswith("UE")), p_long)
        # o lugar: os balões da planta da escada
        proprios = baloes_de(reg) if baloes_de else {}
        dx, dy, usados = _alinhar(proprios, referencia)
        por = "balões %s" % ", ".join(usados) if usados else ""
        # os lances fora do patamar, com os degraus e o sentido de subida
        partes = []
        for l, cx in zip(lances, caixas):
            dentro = [(k, p) for k, p in numeros if _dentro(p, (cx[0] - 60, cx[1] - 60, cx[2] + 60, cx[3] + 60))
                      and not (patamar and _dentro(p, patamar))]
            if len(dentro) < 2:
                continue
            ss = [((p[0] - l["base"][0]) * l["u"][0] + (p[1] - l["base"][1]) * l["u"][1], k) for k, p in dentro]
            sobe = (max(ss, key=lambda z: z[1])[0] - min(ss, key=lambda z: z[1])[0]) > 0
            # a extensão do lance sem o patamar
            s0, s1 = l["s0"], l["s1"]
            if patamar:
                sp = [(x - l["base"][0]) * l["u"][0] + (y - l["base"][1]) * l["u"][1]
                      for x in (patamar[0], patamar[2]) for y in (patamar[1], patamar[3])]
                if min(sp) - s0 > s1 - max(sp):
                    s1 = min(s1, min(sp))
                else:
                    s0 = max(s0, max(sp))
            partes.append({"l": l, "s0": s0, "s1": s1, "sobe": sobe, "kmin": min(k for k, _ in dentro),
                           "kmax": max(k for k, _ in dentro)})
        if not partes:
            continue
        partes.sort(key=lambda p: p["kmin"])
        # o que os balões não deram: pelos pés da escada na locação, na linha das longarinas
        if dy is not None and dx is None and pes_esc:
            p0 = partes[0]
            l = p0["l"]
            s_pe = p0["s0"] if p0["sobe"] else p0["s1"]
            lb = l["base"][0] * l["n"][0] + l["base"][1] * l["n"][1]
            pes = [(l["base"][0] + l["u"][0] * s_pe + l["n"][0] * (lat - lb),
                    l["base"][1] + l["u"][1] * s_pe + l["n"][1] * (lat - lb) + dy) for lat in l["lats"]]
            cand = [(abs(q[1] - p[1]), q[0] - p[0]) for p in pes for q in pes_esc if abs(q[1] - p[1]) < 250.0]
            if cand:
                dx = sorted(c[1] for c in cand)[len(cand) // 2]
                por += (" e " if por else "") + "pés da escada na locação"
        if dx is None or dy is None:
            avisos.append("%s: não consegui pôr no lugar (balões em comum: %s); ficou de fora." % (nome, ", ".join(usados) or "nenhum"))
            continue

        def mover(p, z):
            return (p[0] + dx, p[1] + dy, z)
        z_pat = None
        if len(partes) > 1:
            z_pat = z_cortes if z_cortes is not None else altura * (partes[0]["kmax"] + 1) / float(N)
        segs = []
        for i_p, p in enumerate(partes):
            l = p["l"]
            lb = l["base"][0] * l["n"][0] + l["base"][1] * l["n"][1]
            z_baixo = 0.0 if i_p == 0 else (z_pat or 0.0)
            z_alto = z_pat if (i_p == 0 and z_pat is not None) else altura
            for lat in l["lats"]:
                def ponto(s):
                    return (l["base"][0] + l["u"][0] * s + l["n"][0] * (lat - lb),
                            l["base"][1] + l["u"][1] * s + l["n"][1] * (lat - lb))
                a_, b_ = (ponto(p["s0"]), ponto(p["s1"])) if p["sobe"] else (ponto(p["s1"]), ponto(p["s0"]))
                segs.append((mover(a_, z_baixo), mover(b_, z_alto)))
        pat_segs = []
        if patamar and z_pat is not None:
            c = patamar
            cantos = [(c[0], c[1]), (c[2], c[1]), (c[2], c[3]), (c[0], c[3])]
            pat_segs = [(mover(cantos[k], z_pat), mover(cantos[(k + 1) % 4], z_pat)) for k in range(4)]
        out.append({"nome": nome, "perfil": p_long, "perfil_patamar": p_pat, "lances": segs, "patamar": pat_segs,
                    "degraus": N, "altura": altura, "patamar_z": z_pat, "alinhada_por": por,
                    "patamar_por": "cortes" if z_cortes is not None else "degraus"})
    # a planta que não escreve o perfil da longarina: o das outras escadas
    perfis = [e["perfil"] for e in out if e["perfil"]]
    for e in out:
        if not e["perfil"] and perfis:
            e["perfil"] = perfis[0]
    return out
