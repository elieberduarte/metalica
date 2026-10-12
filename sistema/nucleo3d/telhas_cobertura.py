# -*- coding: utf-8 -*-
"""As telhas da cobertura lançadas em cima das terças do 3D, para ver as caídas e achar a terça fora do lugar.

Pedido do usuário (12/10/2026, Posto CB): "lançar as telhas na cobertura, use uma TP 40 padrão só para testar — quero ver
como ficam as caídas, se não tem nenhuma terça fora do lugar".

Como sai:
- As terças são agrupadas pela direção em planta. Em cada grupo, a cobertura é cortada em faixas ao longo das terças
  (entre as pontas delas): em cada faixa, as terças que a cobrem inteira, em ordem na direção da caída, e cada par vizinho
  (até `vao_max` uma da outra, com até 30 % de inclinação entre elas — senão é outro telhado, outro nível) recebe um pano
  de telha assentado no TOPO das duas (a altura do topo pela seção e o giro de cada terça). As faixas seguidas com o
  mesmo par viram um pano só.
- A conferência, em cada faixa, pela sequência de terças da água:
  · terça fora do plano: a terça que sai mais de `tol_plano` da reta das vizinhas, numa água reta (a inclinação antes
    e depois dela igual) — a telha dobra em cima dela;
  · as águas (trechos com a mesma inclinação): a caída em %, o comprimento da telha (inclinado) e se passa do
    comprimento máximo da telha (precisa de emenda).
O pano é um Sólido fino (camada Telhas) — a telha trapezoidal é desenhada como a superfície em cima das terças.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Tuple

from nucleo3d.geometria import base_local, secao
from nucleo3d.modelo import Solido

TELHA_PADRAO = {"nome": "TP40 0,5 mm (Isoeste Metálica)", "modelo": "TP40", "largura_util": 1020.0, "altura_onda": 40.0,
                "comprimento_max": 12000.0, "massa_m2": 4.62}
ESPESSURA_DESENHO = 6.0          # mm: o pano no 3D (a chapa tem 0,5 mm; 6 mm para aparecer)


def _perfil(nome):
    from nucleo3d.de_planta import _perfil as p
    return p(nome)


def _topo_da_terca(b) -> float:
    """quanto o topo da seção fica acima do eixo da terça (pelo perfil e pelo giro)"""
    d = [b.fim[i] - b.inicio[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in d)) or 1.0
    d = tuple(x / L for x in d)
    p = _perfil(b.perfil)
    if p is None:
        return 50.0
    u, v, _w = base_local(d, b.rotacao or 0.0)
    return max(u[2] * x + v[2] * y for x, y in secao(p))


def lancar(doc, telha: Optional[dict] = None, vao_max: float = 2500.0, tol_plano: float = 10.0,
           camada: str = "Telhas") -> dict:
    """Lança os panos de telha em cima das terças de `doc` (tira os panos lançados antes por aqui). Devolve o resumo,
    as águas e os apontamentos."""
    telha = dict(TELHA_PADRAO, **(telha or {}))
    # tira os panos de uma rodada anterior
    velhos = [e.id for e in doc.solidos if (e.atributos or {}).get("telha_lancada")]
    for i in velhos:
        doc.remover(i)
    tercas = [b for b in doc.barras if b.papel in ("terça", "terca")]
    # as barreiras: a transição e o painel (a calha, a testeira) — a telha termina na face deles, não passa por cima; o
    # pano entre as terças dos dois lados (a calha de x 21,37 do Posto, a TRANSIÇÃO 3) não é telha
    barreiras = []
    for b in doc.barras:
        o = (b.atributos or {}).get("origem") or {}
        nome = str(o.get("planta") or o.get("peca") or "").upper()
        if b.papel == "banzo" and (nome.startswith("PAINEL") or nome.startswith("TRANSI")):
            barreiras.append(((b.inicio[0], b.inicio[1]), (b.fim[0], b.fim[1])))
    CEL = 3000.0
    grade_b: Dict[tuple, list] = collections.defaultdict(list)
    for k, (a, c) in enumerate(barreiras):
        for gx in range(int(min(a[0], c[0]) // CEL), int(max(a[0], c[0]) // CEL) + 1):
            for gy in range(int(min(a[1], c[1]) // CEL), int(max(a[1], c[1]) // CEL) + 1):
                grade_b[(gx, gy)].append(k)

    def atravessa(p, q) -> bool:
        """o pano de p a q (planta) cruza a linha de uma barreira por dentro (a terça em cima dela não conta: ela é a ponta)"""
        vistos = set()
        for gx in range(int(min(p[0], q[0]) // CEL), int(max(p[0], q[0]) // CEL) + 1):
            for gy in range(int(min(p[1], q[1]) // CEL), int(max(p[1], q[1]) // CEL) + 1):
                for k in grade_b.get((gx, gy), ()):
                    if k in vistos:
                        continue
                    vistos.add(k)
                    a, c = barreiras[k]
                    r = (q[0] - p[0], q[1] - p[1]); s_ = (c[0] - a[0], c[1] - a[1])
                    den = r[0] * s_[1] - r[1] * s_[0]
                    if abs(den) < 1e-9:
                        continue
                    t = ((a[0] - p[0]) * s_[1] - (a[1] - p[1]) * s_[0]) / den
                    u = ((a[0] - p[0]) * r[1] - (a[1] - p[1]) * r[0]) / den
                    if 0.03 < t < 0.97 and -0.001 <= u <= 1.001:
                        return True
        return False
    # por direção em planta (a terça em qualquer sentido: o ângulo módulo 180°)
    grupos: Dict[int, list] = collections.defaultdict(list)
    for b in tercas:
        dx, dy = b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1]
        if math.hypot(dx, dy) < 300:
            continue
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        grupos[int(round(ang)) % 180].append(b)
    panos: List[dict] = []
    fora: Dict[str, dict] = {}
    aguas: Dict[tuple, dict] = {}
    vaos_grandes: Dict[tuple, dict] = {}
    for ang, lst in grupos.items():
        d = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        n = (-d[1], d[0])
        reg = []
        for b in lst:
            sa = b.inicio[0] * d[0] + b.inicio[1] * d[1]
            sb = b.fim[0] * d[0] + b.fim[1] * d[1]
            t = ((b.inicio[0] + b.fim[0]) / 2) * n[0] + ((b.inicio[1] + b.fim[1]) / 2) * n[1]
            top = _topo_da_terca(b)
            za, zb = b.inicio[2] + top, b.fim[2] + top
            if sb < sa:
                sa, sb, za, zb = sb, sa, zb, za
            o = (b.atributos or {}).get("origem") or {}
            reg.append({"b": b, "s0": sa, "s1": sb, "t": t, "z0": za, "z1": zb, "sigla": o.get("sigla") or (b.atributos or {}).get("sigla") or ""})

        def z_em(r, s):
            return r["z0"] if r["s1"] - r["s0"] < 1 else r["z0"] + (r["z1"] - r["z0"]) * (s - r["s0"]) / (r["s1"] - r["s0"])

        def ponto(r, s):
            return (d[0] * s + n[0] * r["t"], d[1] * s + n[1] * r["t"], z_em(r, s))

        estacoes = sorted({round(v, 0) for r in reg for v in (r["s0"], r["s1"])})
        abertos: Dict[tuple, dict] = {}            # par de terças → pano em aberto (s inicial, s final)
        for sa, sb in zip(estacoes, estacoes[1:]):
            if sb - sa < 50:
                continue
            sm = (sa + sb) / 2
            cobre = sorted((r for r in reg if r["s0"] <= sa + 5 and r["s1"] >= sb - 5), key=lambda r: r["t"])
            # a sequência de terças da água, em ordem na caída: pares vizinhos ligados
            cadeia: List[List[dict]] = []
            for r in cobre:
                if cadeia and cadeia[-1]:
                    q = cadeia[-1][-1]
                    dt = r["t"] - q["t"]
                    dz = abs(z_em(r, sm) - z_em(q, sm))
                    if dt < 30:                                  # a terça dupla (o par da cumeeira) : a mais alta fica
                        if z_em(r, sm) > z_em(q, sm):
                            cadeia[-1][-1] = r
                        continue
                    if dt <= vao_max and dz <= 0.3 * dt and not atravessa(ponto(q, sm)[:2], ponto(r, sm)[:2]):
                        cadeia[-1].append(r)
                        continue
                    if dt > vao_max and dz <= 0.3 * dt and dt <= 2 * vao_max and not atravessa(ponto(q, sm)[:2], ponto(r, sm)[:2]):
                        k = (id(q["b"]), id(r["b"]))
                        g = vaos_grandes.setdefault(k, {"de": q["sigla"], "para": r["sigla"], "vao": round(dt), "ponto": ponto(q, sm), "comp": 0.0})
                        g["comp"] += sb - sa
                cadeia.append([r])
            pares_aqui = set()
            for seq in cadeia:
                for q, r in zip(seq, seq[1:]):
                    k = (id(q["b"]), id(r["b"]))
                    pares_aqui.add(k)
                    if k in abertos and abs(abertos[k]["s1"] - sa) < 1:
                        abertos[k]["s1"] = sb
                    else:
                        if k in abertos:
                            panos.append(abertos.pop(k))
                        abertos[k] = {"q": q, "r": r, "s0": sa, "s1": sb}
                # a conferência da sequência: os trechos retos da água (3 ou mais terças com a mesma inclinação, até 0,5 %)
                # são o plano da telha; a terça fora deles é conferida pela reta do trecho vizinho de cada lado (até 2 terças
                # de distância) — fora das duas retas mais que `tol_plano`, a telha dobra em cima dela. Pega a terça junto
                # da calha (fora da água ao lado) e a do meio da água (fora das duas)
                zs = [z_em(r, sm) for r in seq]
                ts = [r["t"] for r in seq]
                incl = [(zs[i + 1] - zs[i]) / (ts[i + 1] - ts[i]) for i in range(len(seq) - 1)]
                trechos = []
                a0 = 0
                while a0 < len(incl):
                    b0 = a0
                    while b0 + 1 < len(incl) and abs(incl[b0 + 1] - incl[a0]) <= 0.005:
                        b0 += 1
                    if b0 - a0 >= 1:                               # 2 inclinações iguais = 3 terças
                        trechos.append((a0, b0 + 1, sum(incl[a0:b0 + 1]) / (b0 - a0 + 1)))
                    a0 = b0 + 1 if b0 > a0 else a0 + 1
                no_plano = {k for a_, b_, _ in trechos for k in range(a_, b_ + 1)}
                for k in range(len(seq)):
                    if k in no_plano:
                        continue
                    devs = []
                    for a_, b_, m_ in trechos:
                        if 0 < k - b_ <= 2:                        # o trecho acaba antes dela
                            devs.append(zs[k] - (zs[b_] + m_ * (ts[k] - ts[b_])))
                        elif 0 < a_ - k <= 2:                      # o trecho começa depois dela
                            devs.append(zs[k] - (zs[a_] - m_ * (ts[a_] - ts[k])))
                    if not devs or min(abs(d_) for d_ in devs) <= tol_plano:
                        continue
                    dev = min(devs, key=abs)
                    r = seq[k]
                    f = fora.get(r["b"].id)
                    if not f or abs(dev) > abs(f["desvio"]):
                        fora[r["b"].id] = {"sigla": r["sigla"], "desvio": round(dev), "ponto": [round(c) for c in ponto(r, sm)], "id": r["b"].id}
                # as águas: trechos seguidos com a mesma inclinação (até 0,5 % de diferença)
                i0 = 0
                for i in range(1, len(incl) + 1):
                    if i == len(incl) or abs(incl[i] - incl[i0]) > 0.005 or (incl[i] > 0) != (incl[i0] > 0):
                        a_, b_ = seq[i0], seq[i]
                        hor = b_["t"] - a_["t"]
                        if hor > 0:
                            dz = z_em(b_, sm) - z_em(a_, sm)
                            k = (ang, round(a_["t"] / 100), round(b_["t"] / 100), round(dz / 10))
                            ag = aguas.setdefault(k, {"de": a_["sigla"], "ate": b_["sigla"], "caida_pct": round(abs(dz) / hor * 100, 1),
                                                      "comprimento": round(math.hypot(hor, dz)), "largura": 0.0, "ponto": [round(c) for c in ponto(a_, sm)],
                                                      "tercas": i - i0 + 1})
                            ag["largura"] += sb - sa
                        i0 = i
            for k in [k for k in abertos if k not in pares_aqui]:
                panos.append(abertos.pop(k))
        panos += list(abertos.values())
        # os sólidos dos panos
        for p in panos:
            if p.get("_feito"):
                continue
            p["_feito"] = True
            q, r = p["q"], p["r"]
            c = [ponto(q, p["s0"]), ponto(q, p["s1"]), ponto(r, p["s1"]), ponto(r, p["s0"])]
            e = ESPESSURA_DESENHO
            vs = c + [(x, y, z + e) for x, y, z in c]
            fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
            s = Solido(nome=telha["nome"], camada=camada, vertices=vs, faces=fs)
            s.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": telha["modelo"],
                           "entre": [q["sigla"], r["sigla"]]}
            doc.add(s)
            p["area"] = (p["s1"] - p["s0"]) * math.dist(ponto(q, (p["s0"] + p["s1"]) / 2), ponto(r, (p["s0"] + p["s1"]) / 2))
    feitos = [p for p in panos if p.get("_feito")]
    area = sum(p.get("area", 0.0) for p in feitos) / 1e6
    lista_aguas = sorted(aguas.values(), key=lambda a: (a["caida_pct"], -a["comprimento"]))
    for a in lista_aguas:
        a["largura"] = round(a["largura"])
        a["emenda"] = a["comprimento"] > telha["comprimento_max"]
    return {
        "telha": telha["nome"], "panos": len(feitos), "area_m2": round(area, 1), "peso_kg": round(area * telha["massa_m2"], 1),
        "tercas": len(tercas), "aguas": lista_aguas,
        "caida_min": min((a["caida_pct"] for a in lista_aguas), default=None),
        "caida_max": max((a["caida_pct"] for a in lista_aguas), default=None),
        "fora_do_plano": sorted(fora.values(), key=lambda f: -abs(f["desvio"])),
        "vaos_grandes": [dict(v, comp=round(v["comp"]), ponto=[round(c) for c in v["ponto"]]) for v in vaos_grandes.values() if v["comp"] > 300],
    }
