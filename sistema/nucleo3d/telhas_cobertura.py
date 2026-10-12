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


def _e_barreira(b) -> bool:
    o = (b.atributos or {}).get("origem") or {}
    nome = str(o.get("planta") or o.get("peca") or "").upper()
    return b.papel == "banzo" and (nome.startswith("PAINEL") or nome.startswith("TRANSI"))


def _analise(tercas, barras, vao_max: float = 2500.0, tol_plano: float = 10.0) -> dict:
    """A cobertura pelas terças: os panos (os cantos no topo das terças vizinhas), a terça fora do plano da água, as
    águas, os vãos grandes e, por terça, as amostras do desvio ao plano ao longo dela ({id: [(s, desvio, borda)]}, com a
    direção da terça em planta) — o que o lançamento das telhas e o alinhamento das terças usam."""
    # as barreiras: a transição e o painel (a calha, a testeira) — a telha termina na face deles, não passa por cima; o
    # pano entre as terças dos dois lados (a calha de x 21,37 do Posto, a TRANSIÇÃO 3) não é telha
    barreiras = []
    barreiras_b = []
    for b in barras:
        if _e_barreira(b):
            barreiras.append(((b.inicio[0], b.inicio[1]), (b.fim[0], b.fim[1])))
            barreiras_b.append(b)
    CEL = 3000.0
    grade_b: Dict[tuple, list] = collections.defaultdict(list)
    for k, (a, c) in enumerate(barreiras):
        for gx in range(int(min(a[0], c[0]) // CEL), int(max(a[0], c[0]) // CEL) + 1):
            for gy in range(int(min(a[1], c[1]) // CEL), int(max(a[1], c[1]) // CEL) + 1):
                grade_b[(gx, gy)].append(k)

    def atravessa(p, q):
        """o pano de p a q (planta) cruza a linha de uma barreira por dentro (a terça em cima dela não conta: ela é a ponta):
        {b, topo (a altura do topo da barreira mais alta ali), t (a fração de p a q)}, ou None"""
        vistos = set()
        melhor = None
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
                        bb = barreiras_b[k]
                        topo = bb.inicio[2] + (bb.fim[2] - bb.inicio[2]) * max(0.0, min(1.0, u)) + _ext_z(bb)[1]
                        if melhor is None or topo > melhor["topo"]:
                            melhor = {"b": bb, "topo": topo, "t": t}
        return melhor
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
    amostras: Dict[str, list] = collections.defaultdict(list)
    direcao: Dict[str, tuple] = {}
    sem_telha: Dict[tuple, dict] = {}            # o par de terças vizinhas sem telha entre elas, e por quê
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
            direcao[b.id] = d

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
            paredes = []                                 # (q, r, fração do cruzamento): a barreira que sobe entre as duas
            for r in cobre:
                if cadeia and cadeia[-1]:
                    q = cadeia[-1][-1]
                    dt = r["t"] - q["t"]
                    dz = abs(z_em(r, sm) - z_em(q, sm))
                    if dt < 30:                                  # a terça dupla (o par da cumeeira) : a mais alta fica
                        if z_em(r, sm) > z_em(q, sm):
                            cadeia[-1][-1] = r
                        continue
                    barr = atravessa(ponto(q, sm)[:2], ponto(r, sm)[:2])
                    if barr is not None:
                        # a transição por baixo da linha da telha (a TRANSIÇÃO 10 e a 13 do Posto, no meio da água; a da
                        # calha): a telha passa por cima — só a que sobe acima dela (o painel da testeira, a transição alta)
                        # corta, e aí a telha vai até a face dela (o beiral)
                        zt = z_em(q, sm) + (z_em(r, sm) - z_em(q, sm)) * barr["t"]
                        if barr["topo"] <= zt - 30.0:
                            barr = None
                    if dt <= vao_max and dz <= 0.3 * dt and barr is None:
                        cadeia[-1].append(r)
                        continue
                    if barr is not None and dt <= 2 * vao_max:
                        paredes.append((q, r, barr["t"]))
                    if dt <= 2 * vao_max:
                        k = (id(q["b"]), id(r["b"]))
                        o_b = ((barr["b"].atributos or {}).get("origem") or {}) if barr is not None else {}
                        motivo = ("parede" if barr is not None else "vao" if dt > vao_max else "inclinacao")
                        g = sem_telha.setdefault(k, {"de": q["sigla"], "para": r["sigla"], "motivo": motivo, "vao": round(dt),
                                                     "dz": round(z_em(r, sm) - z_em(q, sm)), "comp": 0.0,
                                                     "barreira": o_b.get("planta") or o_b.get("peca") or "",
                                                     "barreira_topo": round(barr["topo"]) if barr is not None else None,
                                                     "z": (round(z_em(q, sm)), round(z_em(r, sm))),
                                                     "ponto": [round(c) for c in ponto(q, sm)], "ponto2": [round(c) for c in ponto(r, sm)]})
                        g["comp"] += sb - sa
                    if dt > vao_max and dz <= 0.3 * dt and dt <= 2 * vao_max and not atravessa(ponto(q, sm)[:2], ponto(r, sm)[:2]):
                        k = (id(q["b"]), id(r["b"]))
                        g = vaos_grandes.setdefault(k, {"de": q["sigla"], "para": r["sigla"], "vao": round(dt), "ponto": ponto(q, sm), "comp": 0.0})
                        g["comp"] += sb - sa
                cadeia.append([r])
            pares_aqui = set()

            def abrir(k, rec):
                pares_aqui.add(k)
                if k in abertos and abs(abertos[k]["s1"] - sa) < 1:
                    abertos[k]["s1"] = sb
                else:
                    if k in abertos:
                        panos.append(abertos.pop(k))
                    abertos[k] = dict(rec, s0=sa, s1=sb)
            fim_de = {}                                  # a terça → a inclinação da água dela na ponta (para o beiral)
            for seq in cadeia:
                zs_ = [z_em(r, sm) for r in seq]
                ts_ = [r["t"] for r in seq]
                inc_ = [(zs_[i + 1] - zs_[i]) / (ts_[i + 1] - ts_[i]) for i in range(len(seq) - 1)]
                if inc_:
                    fim_de[id(seq[0]["b"])] = inc_[0]
                    fim_de[id(seq[-1]["b"])] = inc_[-1]
                for i, (q, r) in enumerate(zip(seq, seq[1:])):
                    # o vale estreito entre duas águas (a de antes desce até q, a de depois sobe a partir de r, e o pano
                    # entre as duas quase plano, até 1 m): é a calha, não telha — a calha de x 10,06, 21,37 e 33,96 do Posto
                    vale = (0 < i and i + 1 < len(inc_) and inc_[i - 1] < -0.005 and inc_[i + 1] > 0.005
                            and ts_[i + 1] - ts_[i] <= 1000.0 and abs(inc_[i]) <= 0.03)
                    if vale:
                        abrir(("calha", id(q["b"]), id(r["b"])), {"q": q, "r": r, "calha": True})
                    else:
                        abrir((id(q["b"]), id(r["b"])), {"q": q, "r": r})
            # o beiral até a face da parede: da última terça de cada lado até 100 mm da barreira, na inclinação da água
            for q, r, fr in paredes:
                t_c = q["t"] + (r["t"] - q["t"]) * fr
                for ter, lado in ((q, +1), (r, -1)):
                    L = (t_c - 100.0 - ter["t"]) if lado > 0 else (ter["t"] - (t_c + 100.0))
                    if not (50.0 < L <= 1600.0):
                        continue
                    m = fim_de.get(id(ter["b"]), 0.0)
                    abrir(("beiral", id(ter["b"]), lado, round(L / 10), round(m * 1000)),
                          {"q": ter, "r": ter, "beiral": True, "lado": lado, "L": L, "m": m})
            for seq in cadeia:
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
                        amostras[seq[k]["b"].id].append((sm, 0.0, False))
                        continue
                    devs = []
                    desce_antes = sobe_depois = False
                    for a_, b_, m_ in trechos:
                        # a reta do trecho só vale para a terça que continua na mesma água (a inclinação até ela no mesmo
                        # sentido): a da água da esquerda, estendida por cima da calha, apontava a primeira terça da
                        # água da direita 0,12 m "acima" (x 11,27 do Posto)
                        if 0 < k - b_ <= 2:                        # o trecho acaba antes dela
                            if (zs[k] - zs[b_]) * m_ >= 0 or abs(m_) < 0.005:
                                devs.append(zs[k] - (zs[b_] + m_ * (ts[k] - ts[b_])))
                            desce_antes = desce_antes or m_ < -0.005
                        elif 0 < a_ - k <= 2:                      # o trecho começa depois dela
                            if (zs[a_] - zs[k]) * m_ >= 0 or abs(m_) < 0.005:
                                devs.append(zs[k] - (zs[a_] - m_ * (ts[a_] - ts[k])))
                            sobe_depois = sobe_depois or m_ > 0.005
                    # a borda da água: a ponta da sequência (a transição, o painel) ou o vale entre duas águas (a calha)
                    borda = k in (0, len(seq) - 1) or (desce_antes and sobe_depois)
                    if not devs or min(abs(d_) for d_ in devs) <= tol_plano:
                        continue
                    dev = min(devs, key=abs)
                    r = seq[k]
                    amostras[r["b"].id].append((sm, dev, borda))
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
        # os cantos dos panos deste grupo (no topo das duas terças)
        for p in panos:
            if "cantos" in p:
                continue
            q, r = p["q"], p["r"]
            if p.get("beiral"):
                # da terça para fora, na inclinação da água (lado +1: t crescente)
                L, m, lado = p["L"], p["m"], p["lado"]

                def fora_(s_):
                    a_ = ponto(q, s_)
                    return (a_[0] + n[0] * L * lado, a_[1] + n[1] * L * lado, a_[2] + m * L * lado)
                p["cantos"] = [ponto(q, p["s0"]), ponto(q, p["s1"]), fora_(p["s1"]), fora_(p["s0"])]
                p["area"] = (p["s1"] - p["s0"]) * math.hypot(L, m * L)
                continue
            p["cantos"] = [ponto(q, p["s0"]), ponto(q, p["s1"]), ponto(r, p["s1"]), ponto(r, p["s0"])]
            p["area"] = (p["s1"] - p["s0"]) * math.dist(ponto(q, (p["s0"] + p["s1"]) / 2), ponto(r, (p["s0"] + p["s1"]) / 2))
    calhas = [p for p in panos if p.get("calha")]
    panos = [p for p in panos if not p.get("calha")]
    return {"panos": panos, "calhas": calhas, "fora": fora, "aguas": aguas, "vaos_grandes": vaos_grandes, "amostras": dict(amostras), "direcao": direcao,
            "sem_telha": [dict(v, comp=round(v["comp"])) for v in sem_telha.values()]}


def lancar(doc, telha: Optional[dict] = None, vao_max: float = 2500.0, tol_plano: float = 10.0,
           camada: str = "Telhas") -> dict:
    """Lança os panos de telha em cima das terças de `doc` (tira os panos lançados antes por aqui). Devolve o resumo,
    as águas e os apontamentos."""
    telha = dict(TELHA_PADRAO, **(telha or {}))
    # tira os panos de uma rodada anterior
    for i in [e.id for e in doc.solidos if (e.atributos or {}).get("telha_lancada") or (e.atributos or {}).get("calha_lancada")]:
        doc.remover(i)
    tercas = [b for b in doc.barras if b.papel in ("terça", "terca")]
    an = _analise(tercas, doc.barras, vao_max, tol_plano)
    feitos = an["panos"]
    for p in feitos:
        c = p["cantos"]
        e = ESPESSURA_DESENHO
        vs = c + [(x, y, z + e) for x, y, z in c]
        fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        s = Solido(nome=telha["nome"], camada=camada, vertices=vs, faces=fs)
        s.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": telha["modelo"],
                       "entre": [p["q"]["sigla"], p["r"]["sigla"]], **({"beiral": True} if p.get("beiral") else {})}
        doc.add(s)
    # a calha: a caixa entre as duas terças do vale, logo abaixo da telha (200 mm de fundo)
    ml_calha = 0.0
    for c in an["calhas"]:
        cs = c["cantos"]
        topo = min(v[2] for v in cs) - 20.0
        de = [(x, y, topo) for x, y, _z in cs]
        vs = [(x, y, topo - 200.0) for x, y, _z in cs] + de
        fs = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        so = Solido(nome="Calha", camada="Calhas", vertices=vs, faces=fs)
        so.atributos = {"tipo_ifc": "IfcPipeSegment", "calha_lancada": True, "entre": [c["q"]["sigla"], c["r"]["sigla"]]}
        doc.add(so)
        ml_calha += c["s1"] - c["s0"]
    fora, aguas, vaos_grandes = an["fora"], an["aguas"], an["vaos_grandes"]
    area = sum(p.get("area", 0.0) for p in feitos) / 1e6
    lista_aguas = sorted(aguas.values(), key=lambda a: (a["caida_pct"], -a["comprimento"]))
    for a in lista_aguas:
        a["largura"] = round(a["largura"])
        a["emenda"] = a["comprimento"] > telha["comprimento_max"]
    return {
        "telha": telha["nome"], "panos": len(feitos), "area_m2": round(area, 1), "peso_kg": round(area * telha["massa_m2"], 1),
        "beirais": sum(1 for p in feitos if p.get("beiral")), "calhas": len(an["calhas"]), "calha_ml": round(ml_calha / 1000.0, 1),
        "tercas": len(tercas), "aguas": lista_aguas,
        "caida_min": min((a["caida_pct"] for a in lista_aguas), default=None),
        "caida_max": max((a["caida_pct"] for a in lista_aguas), default=None),
        "fora_do_plano": sorted(fora.values(), key=lambda f: -abs(f["desvio"])),
        "vaos_grandes": [dict(v, comp=round(v["comp"]), ponto=[round(c) for c in v["ponto"]]) for v in vaos_grandes.values() if v["comp"] > 300],
    }


# ---------------------------------------------------------------------------------------------- as terças no plano
SUPORTE_PADRAO = 'L 3"×1/4"'      # o suporte de terça (a cantoneira do calço) onde a terça sobe para o plano da água


def _ext_z(b) -> Tuple[float, float]:
    """(fundo, topo) da seção em relação ao eixo da barra, pelo perfil e pelo giro"""
    d = [b.fim[i] - b.inicio[i] for i in range(3)]
    L = math.sqrt(sum(x * x for x in d)) or 1.0
    d = tuple(x / L for x in d)
    p = _perfil(b.perfil)
    if p is None:
        return -50.0, 50.0
    u, v, _w = base_local(d, b.rotacao or 0.0)
    zs = [u[2] * x + v[2] * y for x, y in secao(p)]
    return min(zs), max(zs)


def _apoios_da_terca(b, apoios, grade, CEL):
    """os pontos de apoio da terça b: (t ao longo dela, topo do apoio, nome, é barreira, cruza, peça) — o banzo/viga/U de apoio
    que ela cruza em planta, e o que corre junto por baixo dela (até 150 mm em planta), nas pontas e a cada 1,5 m"""
    bx, by = b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1]
    Lb = math.hypot(bx, by)
    if Lb < 1:
        return []
    ub = (bx / Lb, by / Lb)
    pontos = []
    vistos = set()
    for gx in range(int(min(b.inicio[0], b.fim[0]) // CEL) - 1, int(max(b.inicio[0], b.fim[0]) // CEL) + 2):
        for gy in range(int(min(b.inicio[1], b.fim[1]) // CEL) - 1, int(max(b.inicio[1], b.fim[1]) // CEL) + 2):
            for k in grade.get((gx, gy), ()):
                if k in vistos:
                    continue
                vistos.add(k)
                a = apoios[k]
                ax, ay = a.fim[0] - a.inicio[0], a.fim[1] - a.inicio[1]
                La = math.hypot(ax, ay)
                if La < 1:
                    continue
                _lo_a, hi_a = _ext_z(a)
                o = (a.atributos or {}).get("origem") or {}
                nome = str(o.get("planta") or o.get("peca") or a.papel)
                barr = _e_barreira(a)
                den = bx * ay - by * ax
                if abs(den) / (Lb * La) > 0.1:
                    t = ((a.inicio[0] - b.inicio[0]) * ay - (a.inicio[1] - b.inicio[1]) * ax) / den
                    u = ((a.inicio[0] - b.inicio[0]) * by - (a.inicio[1] - b.inicio[1]) * bx) / den
                    if -0.01 <= t <= 1.01 and -0.01 <= u <= 1.01:
                        pontos.append((max(0.0, min(1.0, t)), a.inicio[2] + (a.fim[2] - a.inicio[2]) * u + hi_a, nome, barr, True, o.get("peca")))
                    continue
                dist = abs((a.inicio[0] - b.inicio[0]) * ub[1] - (a.inicio[1] - b.inicio[1]) * ub[0])
                if dist > 150.0:
                    continue
                sa = ((a.inicio[0] - b.inicio[0]) * ub[0] + (a.inicio[1] - b.inicio[1]) * ub[1]) / Lb
                sb = ((a.fim[0] - b.inicio[0]) * ub[0] + (a.fim[1] - b.inicio[1]) * ub[1]) / Lb
                t0, t1 = max(0.0, min(sa, sb)), min(1.0, max(sa, sb))
                if (t1 - t0) * Lb < 50:
                    continue
                inset = min(100.0 / Lb, (t1 - t0) / 2)
                m = max(1, int(math.ceil((t1 - t0 - 2 * inset) * Lb / 1500.0)))
                for i in range(m + 1):
                    t = t0 + inset + (t1 - t0 - 2 * inset) * i / m
                    ua = (t - sa) / (sb - sa) if abs(sb - sa) > 1e-9 else 0.0
                    pontos.append((t, a.inicio[2] + (a.fim[2] - a.inicio[2]) * ua + hi_a, nome, barr, False, o.get("peca")))
    return pontos


def alinhar_tercas(tercas, barras, tol: float = 10.0, maximo: float = 300.0, vao_max: float = 2500.0,
                   folga_suporte: float = 15.0) -> dict:
    """As terças fora do lugar, corrigidas onde a correção é clara (12/10/2026, "pode corrigir seguindo bom senso de
    projeto" — a telha TP 40 de teste mostrou as dobras):
      A. a terça da BORDA da água (a última antes da calha ou da transição) ABAIXO do plano dela (toda ela, pelo trecho
         reto de 3+ terças ao lado): SOBE até o plano (até
         'maximo'), e o suporte de terça (SUPORTE_PADRAO) com a altura da folga vai em cada apoio em que ela estava
         sentada — a ponta da tesoura que desce junto da calha, o banzo da transição por baixo dela (nas pontas e a cada
         1,5 m). No Posto, as das calhas de x 10,06 · 21,67 · 34,06 · 49,72, ~0,10 m abaixo.
      B. a terça TORTA: a altura muda ao longo dela (mais de 30 mm) com as vizinhas da mesma água niveladas — fica
         nivelada na altura do apoio dela (o banzo que ela cruza; com mais de um, não é este caso) e, se encostar num
         apoio mais alto, senta nele. No Posto, TC22 e TC27 (subiam 0,22 e 0,42 m a partir da TESOURA 3B), TC52, TC48.
    O resto (a água que não fecha num plano — as tesouras em alturas diferentes) fica como está, para a conferência.
    Muda inicio/fim das terças; devolve {calha, tortas, suportes: [(p0, p1, apoio)], maior_mm}."""
    an = _analise(tercas, barras, vao_max, tol)
    apoios = [a for a in barras if a.papel in ("banzo", "viga", "apoio_terca") and a.tipo == "barra"]
    CEL = 3000.0
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for k, a in enumerate(apoios):
        for gx in range(int(min(a.inicio[0], a.fim[0]) // CEL), int(max(a.inicio[0], a.fim[0]) // CEL) + 1):
            for gy in range(int(min(a.inicio[1], a.fim[1]) // CEL), int(max(a.inicio[1], a.fim[1]) // CEL) + 1):
                grade[(gx, gy)].append(k)
    calha, tortas, suportes = [], [], []
    maior = 0.0
    por_id = {b.id: b for b in tercas}
    # as pontas de cada peça (tesoura, treliça) em planta: a terça da calha senta na ponta das tesouras, onde o banzo
    # desce; a do meio da água senta na tesoura que passa
    pontas_peca: Dict[str, list] = collections.defaultdict(list)
    for a in apoios:
        pc = ((a.atributos or {}).get("origem") or {}).get("peca")
        if pc:
            pontas_peca[pc] += [(a.inicio[0], a.inicio[1]), (a.fim[0], a.fim[1])]
    extremos = {}
    for pc, pts_ in pontas_peca.items():
        (x0, y0), (x1, y1) = max(((p, q) for p in pts_[:40] for q in pts_[:40]), key=lambda pq: math.dist(*pq))
        L = math.dist((x0, y0), (x1, y1))
        if L > 1:
            u_ = ((x1 - x0) / L, (y1 - y0) / L)
            ss_ = [(x - x0) * u_[0] + (y - y0) * u_[1] for x, y in pts_]
            extremos[pc] = ((x0, y0), u_, min(ss_), max(ss_))

    def na_ponta(b, p) -> bool:
        if not p[4]:
            return True                                      # o que corre por baixo dela: a transição, a COMP da calha
        ext = extremos.get(p[5]) if p[4] else None
        if not ext:
            return False
        (x0, y0), u_, smin, smax = ext
        x = b.inicio[0] + (b.fim[0] - b.inicio[0]) * p[0]
        y = b.inicio[1] + (b.fim[1] - b.inicio[1]) * p[0]
        s_ = (x - x0) * u_[0] + (y - y0) * u_[1]
        return min(abs(s_ - smin), abs(s_ - smax)) <= 400.0

    def sigla(b):
        o = (b.atributos or {}).get("origem") or {}
        return o.get("sigla") or (b.atributos or {}).get("sigla") or ""

    # A. a terça da calha
    for bid, am in an["amostras"].items():
        b = por_id.get(bid)
        if b is None:
            continue
        devs = [x for _, x, _b in am if x != 0.0]
        if not devs or max(devs) >= -tol or min(devs) < -maximo:
            continue                                         # só a que está toda abaixo do plano
        lo_b, _hi = _ext_z(b)
        pts = _apoios_da_terca(b, apoios, grade, CEL)
        # os apoios em que ela está sentada (a barreira só por baixo dela)
        sobre = [p for p in pts if abs(b.inicio[2] + (b.fim[2] - b.inicio[2]) * p[0] + lo_b - p[1]) <= 20.0]
        if not sobre:
            continue
        # a da borda da água (a calha): na ponta da sequência / no vale, ou sentada só na ponta das tesouras ou numa
        # transição por baixo; a do meio da água, sentada na tesoura que passa, é apontamento
        if not (all(borda for _, x, borda in am if x != 0.0) or all(na_ponta(b, p) for p in sobre)):
            continue
        # a subida em cada ponta, pela reta do desvio ao longo dela (a TC9 da calha de x 10,06: −0,10 m numa ponta, 0 na outra)
        d = an["direcao"][b.id]
        ss = [s_ for s_, _x, _b in am]
        ds = [x for _s, x, _b in am]
        if max(ss) - min(ss) < 200:
            a0, a1 = sum(ds) / len(ds), 0.0
        else:
            ms, md = sum(ss) / len(ss), sum(ds) / len(ds)
            a1 = sum((s_ - ms) * (x - md) for s_, x in zip(ss, ds)) / sum((s_ - ms) ** 2 for s_ in ss)
            a0 = md - a1 * ms
        si = b.inicio[0] * d[0] + b.inicio[1] * d[1]
        sf = b.fim[0] * d[0] + b.fim[1] * d[1]
        sobe_i = min(maximo, max(0.0, -(a0 + a1 * si)))
        sobe_f = min(maximo, max(0.0, -(a0 + a1 * sf)))
        if max(sobe_i, sobe_f) <= tol / 2:
            continue
        b.inicio = (b.inicio[0], b.inicio[1], b.inicio[2] + sobe_i)
        b.fim = (b.fim[0], b.fim[1], b.fim[2] + sobe_f)
        maior = max(maior, sobe_i, sobe_f)
        calha.append({"sigla": sigla(b), "mm": round(max(sobe_i, sobe_f)), "sobre": sorted({p[2] for p in sobre}), "ponto": [round(c) for c in b.inicio]})
        bx, by = b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1]
        for t, za, nome, _barr, _cr, _pc in sobre:
            zf = b.inicio[2] + (b.fim[2] - b.inicio[2]) * t + lo_b
            if zf - za > folga_suporte:
                x, y = b.inicio[0] + bx * t, b.inicio[1] + by * t
                suportes.append(((x, y, za), (x, y, zf), nome))

    # B. a terça torta, com as vizinhas niveladas
    for d in set(an["direcao"].values()):
        n = (-d[1], d[0])
        grupo = [b for b in tercas if an["direcao"].get(b.id) == d]
        for b in grupo:
            dz = b.fim[2] - b.inicio[2]
            if abs(dz) <= 30.0 or abs(dz) > 2 * maximo:
                continue
            tb = ((b.inicio[0] + b.fim[0]) / 2) * n[0] + ((b.inicio[1] + b.fim[1]) / 2) * n[1]
            sa = sorted((b.inicio[0] * d[0] + b.inicio[1] * d[1], b.fim[0] * d[0] + b.fim[1] * d[1]))
            viz = []
            for c in grupo:
                if c is b:
                    continue
                tc = ((c.inicio[0] + c.fim[0]) / 2) * n[0] + ((c.inicio[1] + c.fim[1]) / 2) * n[1]
                sc = sorted((c.inicio[0] * d[0] + c.inicio[1] * d[1], c.fim[0] * d[0] + c.fim[1] * d[1]))
                if 100.0 < abs(tc - tb) <= 2000.0 and min(sa[1], sc[1]) - max(sa[0], sc[0]) > 500.0:
                    viz.append((tc - tb, abs(c.fim[2] - c.inicio[2])))
            # vizinhas dos dois lados, todas niveladas
            if not (any(v[0] < 0 for v in viz) and any(v[0] > 0 for v in viz)) or any(v[1] > 10.0 for v in viz):
                continue
            lo_b, _hi = _ext_z(b)
            pts = [p for p in _apoios_da_terca(b, apoios, grade, CEL) if p[4] and not p[3]]
            assentados = [p for p in pts if abs(b.inicio[2] + dz * p[0] + lo_b - p[1]) <= 20.0]
            if len(assentados) != 1:
                continue                                     # sem apoio claro, ou mais de um (a inclinação é dos apoios)
            t0 = assentados[0][0]
            z_ap = b.inicio[2] + dz * t0
            antes = (b.inicio[2], b.fim[2])
            b.inicio = (b.inicio[0], b.inicio[1], z_ap)
            b.fim = (b.fim[0], b.fim[1], z_ap)
            # encostou num apoio mais alto: senta nele
            menor = min((z_ap + lo_b - za for _t, za, _n, _b, _c, _p in pts if -300.0 < z_ap + lo_b - za < 400.0), default=0.0)
            if menor < -5.0:
                b.inicio = (b.inicio[0], b.inicio[1], b.inicio[2] - menor)
                b.fim = (b.fim[0], b.fim[1], b.fim[2] - menor)
            mm = max(abs(b.inicio[2] - antes[0]), abs(b.fim[2] - antes[1]))
            maior = max(maior, mm)
            tortas.append({"sigla": sigla(b), "mm": round(mm), "apoio": assentados[0][2], "ponto": [round(c) for c in b.inicio]})
    return {"calha": calha, "tortas": tortas, "suportes": suportes, "maior_mm": round(maior)}
