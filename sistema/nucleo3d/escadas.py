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
5. as alturas: do chão ao piso de cima (o nível da planta que ela serve), com os espelhos iguais —
   os pisantes de cada lance pelo comprimento dele e o passo, um espelho a mais que pisantes em
   cada lance; o patamar pela cota do corte que confirma essa conta (a ESCADA 1 do Posto CB a
   1.700, 10 espelhos; a 2 a 1.421, 9 espelhos);
6. os pisantes: a chapa xadrez dobrada de cada degrau, entre as longarinas, na altura dele.

`ler(ents, textos, referencia, pes_esc, altura, avisos)` devolve as escadas: lances e patamar com as
pontas em mm, já no lugar da planta estrutural.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

Ponto2 = Tuple[float, float]
TITULO = re.compile(r"(?i)^\s*PLANTA\s+BAIXA\s+DA\s+ESCADA\s*(.*)$")
ABA_DEGRAU = 40.0            # mm: a aba do pisante dobrado, para baixo na frente e atrás (os cortes do Posto CB)
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


def cotas_dos_cortes(textos, regs, altura: float) -> List[float]:
    """as cotas verticais dos cortes das escadas (em volta das plantas) que podem ser a altura de um
    patamar: entre 30% e 70% da altura da escada"""
    x0 = min(r[0] for r in regs) - 3000.0
    x1 = max(r[2] for r in regs) + 3000.0
    y0 = min(r[1] for r in regs) - 16000.0
    y1 = max(r[3] for r in regs) + 16000.0
    return sorted({float(t["texto"]) for t in textos if re.fullmatch(r"\d{3,5}", str(t.get("texto") or "").strip())
                   and "cota" in str(t.get("camada") or "").lower() and x0 <= t["posicao"][0] <= x1
                   and y0 <= t["posicao"][1] <= y1 and 0.3 * altura < float(t["texto"]) < 0.7 * altura})


def _pecas_de_linha(ents, reg) -> List[dict]:
    """as linhas e polilinhas de peça (fora das camadas de anotação) da região, como segmentos
    {a, b}: a polilinha fechada estreita (o U desenhado em planta) vira o segmento do lado maior"""
    out = []
    for e in ents:
        if ANOTACAO.search(str(e.get("camada") or "")):
            continue
        if e["tipo"] == "linha" and _dentro(e["a"], reg) and _dentro(e["b"], reg):
            out.append({"a": tuple(e["a"][:2]), "b": tuple(e["b"][:2])})
        elif e["tipo"] == "polilinha" and len(e.get("vertices") or ()) >= 4 and all(_dentro(v, reg) for v in e["vertices"]):
            xs = [v[0] for v in e["vertices"]]
            ys = [v[1] for v in e["vertices"]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if max(w, h) < 400.0 or min(w, h) > 120.0:
                continue                                   # a seção do pilar, o pé: não é barra
            cy, cx = (min(ys) + max(ys)) / 2.0, (min(xs) + max(xs)) / 2.0
            out.append({"a": (min(xs), cy), "b": (max(xs), cy)} if w >= h else {"a": (cx, min(ys)), "b": (cx, max(ys))})
    return out


def _dist_seg(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else min(max(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2, 0.0), 1.0)
    return math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dy * t)


def ler(ents, textos, referencia: Dict[str, List[Ponto2]], pes_esc: Sequence[Ponto2], altura: float,
        avisos: List[str], baloes_de=None) -> List[dict]:
    """as escadas desenhadas em planta baixa, no lugar da planta estrutural: [{nome, perfil,
    perfil_patamar, lances: [(p0, p1)], patamar: [(p0, p1)], degraus, altura, alinhada_por}]
    (pontos (x, y, z) em mm)"""
    out = []
    todas = regioes(textos)
    cotas_p = cotas_dos_cortes(textos, [r for _t, r in todas], altura) if todas else []
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
        # os pisantes de cada lance: o comprimento dele pelo passo (os números dos degraus nem sempre
        # ficam no meio da faixa, e o da ponta pode cair no patamar); a escada com um espelho a mais
        # que pisantes em cada lance (do chão ou do patamar ao pisante 1, do último ao patamar ou ao
        # piso de cima)
        ss_n = sorted(((q[0] - partes[0]["l"]["base"][0]) * partes[0]["l"]["u"][0]
                       + (q[1] - partes[0]["l"]["base"][1]) * partes[0]["l"]["u"][1], k) for k, q in numeros
                      if partes[0]["kmin"] <= k <= partes[0]["kmax"])
        passos = sorted(abs(b_[0] - a_[0]) / max(abs(b_[1] - a_[1]), 1) for a_, b_ in zip(ss_n, ss_n[1:]))
        g_esc = passos[len(passos) // 2] if passos else 300.0
        for p in partes:
            p["n"] = max(1, int(round((p["s1"] - p["s0"]) / g_esc)))
        z_pat = None
        patamar_por = None
        if len(partes) > 1:
            n1, n2 = partes[0]["n"], sum(p["n"] for p in partes[1:])
            z_est = altura * (n1 + 1) / float(n1 + n2 + 2)
            # a cota do corte que confirma o patamar (a mais perto da estimativa, dentro de meio espelho)
            tol_p = max(60.0, 0.5 * altura / float(n1 + n2 + 2))
            perto_c = [c for c in cotas_p if abs(c - z_est) <= tol_p]
            if perto_c:
                z_pat, patamar_por = min(perto_c, key=lambda c: abs(c - z_est)), "cortes"
            else:
                z_pat, patamar_por = z_est, "degraus"
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
        # o que a planta desenha além das longarinas e dos degraus: os perfis do patamar (no nível
        # dele) e, na chegada, a travessa entre as longarinas e a ligação com o piso de cima (a
        # ESCADA 1 do Posto CB continua a longarina de fora até a face do pilar do eixo 1/G)
        ultimo = partes[-1]
        lu = ultimo["l"]
        lbu = lu["base"][0] * lu["n"][0] + lu["base"][1] * lu["n"][1]
        s_topo = ultimo["s1"] if ultimo["sobe"] else ultimo["s0"]
        topo = [(lu["base"][0] + lu["u"][0] * s_topo + lu["n"][0] * (lat - lbu),
                 lu["base"][1] + lu["u"][1] * s_topo + lu["n"][1] * (lat - lbu)) for lat in lu["lats"]]
        eixos_long = [e_ for l in lances for e_ in l["eixos"]]

        def da_longarina(sg):
            (ux, uy), _L = _unit(sg["a"], sg["b"])
            for e_ in eixos_long:
                if abs(ux * e_["u"][1] - uy * e_["u"][0]) < 0.02 and \
                        abs(sg["a"][0] * e_["n"][0] + sg["a"][1] * e_["n"][1] - e_["lat"]) < 60.0:
                    s_ = [(p[0] - e_["base"][0]) * e_["u"][0] + (p[1] - e_["base"][1]) * e_["u"][1] for p in (sg["a"], sg["b"])]
                    if min(s_) >= e_["s0"] - 60.0 and max(s_) <= e_["s1"] + 60.0:
                        return True
            return False

        def degrau(sg):
            for p in partes:
                l = p["l"]
                (ux, uy), _L = _unit(sg["a"], sg["b"])
                if abs(ux * l["u"][0] + uy * l["u"][1]) > 0.05:
                    continue                               # não é transversal ao lance
                s_ = sum((q[0] - l["base"][0]) * l["u"][0] + (q[1] - l["base"][1]) * l["u"][1] for q in (sg["a"], sg["b"])) / 2
                if p["s0"] + 100.0 < s_ < p["s1"] - 100.0:
                    return True
            return False
        sobra = [sg for sg in _pecas_de_linha(ents, reg) if math.dist(sg["a"], sg["b"]) >= 400.0
                 and not da_longarina(sg) and not degrau(sg)]
        # as duas linhas do mesmo perfil viram uma (o eixo)
        pares = _eixos_das_longarinas([{"a": sg["a"], "b": sg["b"]} for sg in sobra])
        juntas = [({"a": (e_["base"][0] + e_["u"][0] * e_["s0"], e_["base"][1] + e_["u"][1] * e_["s0"]),
                    "b": (e_["base"][0] + e_["u"][0] * e_["s1"], e_["base"][1] + e_["u"][1] * e_["s1"])}) for e_ in pares]
        usadas_p = set()
        for e_ in pares:
            for i_s, sg in enumerate(sobra):
                (ux, uy), _L = _unit(sg["a"], sg["b"])
                if abs(ux * e_["u"][1] - uy * e_["u"][0]) < 0.02 and \
                        abs(sg["a"][0] * e_["n"][0] + sg["a"][1] * e_["n"][1] - e_["lat"]) < 60.0:
                    usadas_p.add(i_s)
        vigas = []
        vistos = []
        for sg in juntas + [sg for i_s, sg in enumerate(sobra) if i_s not in usadas_p]:
            meio = ((sg["a"][0] + sg["b"][0]) / 2, (sg["a"][1] + sg["b"][1]) / 2)
            if any(math.dist(meio, m) < 80.0 for m in vistos):
                continue
            vistos.append(meio)
            if patamar and z_pat is not None and all(_dentro(q, (patamar[0] - 120, patamar[1] - 120, patamar[2] + 120,
                                                                 patamar[3] + 120)) for q in (sg["a"], sg["b"])):
                vigas.append((mover(sg["a"], z_pat), mover(sg["b"], z_pat)))
            elif min(_dist_seg(q, sg["a"], sg["b"]) for q in topo) < 150.0:
                vigas.append((mover(sg["a"], altura), mover(sg["b"], altura)))
        # o piso do patamar (a chapa xadrez dos cortes)
        pisos = []
        if patamar and z_pat is not None:
            esp = 3.0
            for x in textos:
                m = re.search(r"(?i)CHAPA\s+XADREZ\D*(\d+[.,]\d+)", str(x.get("texto") or ""))
                if m:
                    esp = float(m.group(1).replace(",", "."))
                    break
            pisos.append({"canto": mover((patamar[0], patamar[1]), z_pat), "lx": patamar[2] - patamar[0],
                          "ly": patamar[3] - patamar[1], "espessura": esp})
        # os pisantes: a chapa xadrez dobrada de cada degrau (o piso entre as faces de dentro das
        # longarinas, as abas para baixo na frente e atrás, sem espelho), os espelhos iguais do chão
        # ao patamar e do patamar ao piso de cima
        esp_d = pisos[0]["espessura"] if pisos else 3.0
        m_b = re.search(r"(?i)X\s*(\d+)", p_long or "")
        bf_long = float(m_b.group(1)) if m_b else 40.0
        pisantes = []
        for i_p, p in enumerate(partes):
            l = p["l"]
            lb = l["base"][0] * l["n"][0] + l["base"][1] * l["n"][1]
            ux, uy = l["u"]
            nx, ny = -uy, ux                                   # u × n para cima: a espessura sobe
            z0 = 0.0 if i_p == 0 else z_pat
            z1 = z_pat if (i_p == 0 and z_pat is not None) else altura
            n_p = p["n"]
            g = (p["s1"] - p["s0"]) / n_p
            faces = []
            for lat in l["lats"]:
                q = (l["base"][0] + l["n"][0] * (lat - lb), l["base"][1] + l["n"][1] * (lat - lb))
                faces.append(q[0] * nx + q[1] * ny)
            if len(faces) < 2:
                continue
            c0, c1 = min(faces) + bf_long / 2.0, max(faces) - bf_long / 2.0
            b_n = l["base"][0] * nx + l["base"][1] * ny
            # a numeração do desenho: o primeiro lance do 1; os seguintes terminam no penúltimo número
            # (o último é a chegada no piso de cima)
            k_ini = 1 if i_p == 0 else N - sum(q["n"] for q in partes[i_p:])
            for i in range(1, n_p + 1):
                s_a = (p["s0"] + (i - 1) * g) if p["sobe"] else (p["s1"] - i * g)
                o_ = (l["base"][0] + ux * s_a + nx * (c0 - b_n), l["base"][1] + uy * s_a + ny * (c0 - b_n))
                pisantes.append({"k": k_ini + i - 1, "origem": mover(o_, z0 + (z1 - z0) * i / float(n_p + 1)),
                                 "u": (ux, uy), "n": (nx, ny), "piso": g, "largura": c1 - c0, "aba": ABA_DEGRAU,
                                 "espessura": esp_d})
        out.append({"nome": nome, "perfil": p_long, "perfil_patamar": p_pat, "lances": segs, "patamar": pat_segs,
                    "vigas": vigas, "pisos": pisos, "pisantes": pisantes,
                    "degraus": N, "altura": altura, "patamar_z": z_pat, "alinhada_por": por,
                    "patamar_por": patamar_por})
    # a planta que não escreve o perfil da longarina: o das outras escadas
    perfis = [e["perfil"] for e in out if e["perfil"]]
    for e in out:
        if not e["perfil"] and perfis:
            e["perfil"] = perfis[0]
    return out
