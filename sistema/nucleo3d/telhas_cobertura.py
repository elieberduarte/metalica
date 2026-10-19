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
import re
from typing import Dict, List, Optional, Tuple

from nucleo3d.geometria import base_local, secao
from nucleo3d.modelo import Solido, origem_de

TELHA_PADRAO = {"nome": "TP40 0,5 mm (Isoeste Metálica)", "modelo": "TP40", "largura_util": 1020.0, "altura_onda": 40.0,
                "comprimento_max": 12000.0, "massa_m2": 4.62}
ESPESSURA_DESENHO = 6.0          # mm: o pano no 3D (a chapa tem 0,5 mm; 6 mm para aparecer)
# a calha em todo encontro das águas baixas (17/10, o usuário: "as telhas devem ter um afastamento entre si e a calha
# ficará centralizada deixando os cobrimentos necessários para a água não infiltrar para dentro da cobertura")
AFASTAMENTO_CALHA = 150.0        # mm entre as pontas das telhas das duas águas, no vale
COBRIMENTO_CALHA = 100.0         # mm de telha por cima da calha, de cada lado (a calha do vale: 150 + 2 × 100 = 350)
AFASTAMENTO_PAREDE = 100.0       # mm da ponta da telha até a face da parede em que a água desce (a calha encostada nela)
FUNDO_CALHA = 150.0              # mm de fundo da calha, abaixo da ponta das telhas


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
    o = origem_de(b)
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
    # para a borda contra a parede diagonal: todo banzo conta (a TRELIÇA 6 do Posto, 0,5 m acima da telha, é a borda do
    # telhado ao lado da TRANSIÇÃO 16 — a telha não passa dela)
    paredes_todas = [b for b in barras if b.papel == "banzo"]
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
            o = origem_de(b)
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
            por_cima = set()                             # os pares que passam por cima de uma transição baixa (a da calha)
            degraus = []                                 # (a terça de baixo, lado, até onde): o degrau para o telhado de cima
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
                            por_cima.add((id(q["b"]), id(r["b"])))
                    if dt <= vao_max and dz <= 0.3 * dt and barr is None:
                        cadeia[-1].append(r)
                        continue
                    if barr is not None and dt <= 2 * vao_max:
                        paredes.append((q, r, barr["t"]))
                    elif barr is None and dz > 0.3 * dt and dt <= 1600.0:
                        # o degrau para o telhado de cima (a cobertura da caixa d'água, 4 m acima das TC3/TC4 do Posto): a
                        # telha de baixo segue até ficar sob a borda do de cima (50 mm antes) — sem a faixa aberta entre os dois
                        baixa, lado_b = (q, +1) if z_em(q, sm) < z_em(r, sm) else (r, -1)
                        degraus.append((baixa, lado_b, dt - 50.0))
                    if dt <= 2 * vao_max:
                        k = (id(q["b"]), id(r["b"]))
                        o_b = origem_de(barr["b"]) if barr is not None else {}
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
            no_vale = set()                              # as terças da calha de duas terças (o V numa terça é outro caso)
            for seq in cadeia:
                zs_ = [z_em(r, sm) for r in seq]
                ts_ = [r["t"] for r in seq]
                inc_ = [(zs_[i + 1] - zs_[i]) / (ts_[i + 1] - ts_[i]) for i in range(len(seq) - 1)]
                if inc_:
                    fim_de[id(seq[0]["b"])] = inc_[0]
                    fim_de[id(seq[-1]["b"])] = inc_[-1]

                def desce_ate(j, inc_=inc_):
                    """a água desce no vão j até o vale, sem subir no vão de antes (a terça baixa no meio de uma água — o
                    par da cumeeira de x 42,07 do Posto, 85 mm abaixo — não é vale: é apontamento)"""
                    return inc_[j] < -0.005 and (j == 0 or inc_[j - 1] < 0.005)

                def sobe_de(j, inc_=inc_):
                    return inc_[j] > 0.005 and (j == len(inc_) - 1 or inc_[j + 1] > -0.005)
                for i, (q, r) in enumerate(zip(seq, seq[1:])):
                    # o vale estreito entre duas águas (a de antes desce até q, a de depois sobe a partir de r, até 1 m uma da
                    # outra): é a calha, não telha — as calhas de x 10,06, 21,37 e 33,96 do Posto. Qualquer inclinação entre as
                    # duas (17/10: a terça do fundo 0,1 m abaixo da vizinha a 0,45 m — a linha x 10,06 — ficava sem calha)
                    no_fundo = 0 < i and i + 1 < len(inc_) and desce_ate(i - 1) and sobe_de(i + 1)
                    vale = no_fundo and ts_[i + 1] - ts_[i] <= 1000.0
                    # o par de terças da cumeeira (as duas águas sobem até elas, até 0,5 m uma da outra): a cumeeira cobre o
                    # meio (a peça de funilaria), não a telha — o par a 0,35 m das cumeeiras de x 27,6 e 41,9 do Posto
                    cume = (0 < i and i + 1 < len(inc_) and inc_[i - 1] > 0.005 and inc_[i + 1] < -0.005
                            and ts_[i + 1] - ts_[i] <= 500.0)
                    if vale:
                        abrir(("calha", id(q["b"]), id(r["b"])), {"q": q, "r": r, "calha": True})
                        no_vale.update((id(q["b"]), id(r["b"])))
                        # as telhas das duas águas entram na calha até ficarem a AFASTAMENTO_CALHA uma da outra
                        bal = (ts_[i + 1] - ts_[i] - AFASTAMENTO_CALHA) / 2.0
                        if bal > 20.0:
                            for ter, lado, m_ in ((q, +1, inc_[i - 1]), (r, -1, inc_[i + 1])):
                                abrir(("beiral", id(ter["b"]), lado, round(bal / 10), round(m_ * 1000)),
                                      {"q": ter, "r": ter, "beiral": True, "lado": lado, "L": bal, "m": m_})
                    elif cume:
                        abrir(("cumeeira", id(q["b"]), id(r["b"])), {"q": q, "r": r, "cumeeira": True})
                    else:
                        abrir((id(q["b"]), id(r["b"])), {"q": q, "r": r})
            # o vale em V numa terça (as duas águas descem até ela — a linha de x 10,06 do Posto): a calha ao longo dela
            for seq in cadeia:
                zs_ = [z_em(r, sm) for r in seq]
                ts_ = [r["t"] for r in seq]
                inc_ = [(zs_[i + 1] - zs_[i]) / (ts_[i + 1] - ts_[i]) for i in range(len(seq) - 1)]
                for k_ in range(1, len(seq) - 1):
                    if (inc_[k_ - 1] < -0.005 and (k_ == 1 or inc_[k_ - 2] < 0.005) and inc_[k_] > 0.005
                            and (k_ == len(inc_) - 1 or inc_[k_ + 1] > -0.005) and id(seq[k_]["b"]) not in no_vale):
                        abrir(("calhaV", id(seq[k_]["b"])), {"q": seq[k_], "r": seq[k_], "calha": True, "eixo": True})
            for ter, lado, L in degraus:
                if L > 50.0:
                    m = fim_de.get(id(ter["b"]), 0.0)
                    abrir(("beiral", id(ter["b"]), lado, round(L / 10), round(m * 1000)),
                          {"q": ter, "r": ter, "beiral": True, "lado": lado, "L": L, "m": m})
            # o beiral até a face da parede: da última terça de cada lado até 100 mm da barreira, na inclinação da água
            for q, r, fr in paredes:
                t_c = q["t"] + (r["t"] - q["t"]) * fr
                for ter, lado in ((q, +1), (r, -1)):
                    L = (t_c - 100.0 - ter["t"]) if lado > 0 else (ter["t"] - (t_c + 100.0))
                    if not (-300.0 < L <= 1600.0):
                        continue
                    m = fim_de.get(id(ter["b"]), 0.0)
                    # a água que desce até a parede (o frontão das TRANSIÇÕES 2/3 do Posto na linha da calha): a telha para a
                    # AFASTAMENTO_PAREDE da face e a calha fica encostada nela, por baixo da ponta da telha
                    desce = m * lado < -0.005
                    Lt = L - AFASTAMENTO_PAREDE if desce else L
                    if Lt > 50.0:
                        abrir(("beiral", id(ter["b"]), lado, round(Lt / 10), round(m * 1000)),
                              {"q": ter, "r": ter, "beiral": True, "lado": lado, "L": Lt, "m": m})
                    if desce and L > 0.0:
                        abrir(("calhaP", id(ter["b"]), lado, round(L / 10)),
                              {"q": ter, "r": ter, "calha": True, "parede": True, "lado": lado, "L": L, "Lt": max(0.0, Lt), "m": m})
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
        # a borda escalonada (a borda diagonal do Posto, do eixo 13/D ao K): onde uma das duas terças do pano acaba antes
        # e nenhum outro pano continua do lado dela, o triângulo da ponta da mais curta até a ponta da mais longa — a
        # linha da borda passa pelas pontas das terças
        deste = [p for p in panos if "cantos" not in p and not p.get("calha") and not p.get("cumeeira") and not p.get("beiral")]
        cobre_lado: Dict[tuple, list] = collections.defaultdict(list)
        for p in deste:
            cobre_lado[(id(p["q"]["b"]), +1)].append((p["s0"], p["s1"]))
            cobre_lado[(id(p["r"]["b"]), -1)].append((p["s0"], p["s1"]))

        def coberto(ter, lado, a_, b_):
            return any(x0 < b_ - 1 and x1 > a_ + 1 for x0, x1 in cobre_lado.get((id(ter["b"]), lado), ()))
        # a linha de terça inteira: os pedaços na mesma linha, emendados no apoio (a linha x 30,13 do Posto, partida na
        # tesoura de y 11,45, 17/10) — a ponta da borda é a da LINHA; com a do pedaço, o triângulo não saía e a telha
        # parava em degraus de até 1,3 m da TRANSIÇÃO 16
        linhas: Dict[int, list] = {}
        por_t = sorted(reg, key=lambda r_: r_["t"])
        i0 = 0
        while i0 < len(por_t):
            i1 = i0
            while i1 + 1 < len(por_t) and por_t[i1 + 1]["t"] - por_t[i1]["t"] < 30.0:
                i1 += 1
            mesmas = sorted(por_t[i0:i1 + 1], key=lambda r_: r_["s0"])
            cad = [mesmas[0]]
            for r_ in mesmas[1:]:
                if r_["s0"] <= max(x["s1"] for x in cad) + 60.0:
                    cad.append(r_)
                else:
                    for x in cad:
                        linhas[id(x)] = cad
                    cad = [r_]
            for x in cad:
                linhas[id(x)] = cad
            i0 = i1 + 1
        triangulos = []
        for p in deste:
            q, r = p["q"], p["r"]
            for ponta in ("s1", "s0"):
                s_p = p[ponta]
                for longa, curta, lado in ((r, q, -1), (q, r, +1)):
                    cad = linhas.get(id(longa)) or [longa]
                    s_l = max(x["s1"] for x in cad) if ponta == "s1" else min(x["s0"] for x in cad)
                    alem = (s_l - s_p) if ponta == "s1" else (s_p - s_l)
                    s_c = curta[ponta]
                    if not (100.0 < alem <= 3000.0) or abs(s_c - s_p) > 5.0:
                        continue                         # a curta tem de acabar ali, e a longa seguir até 3 m
                    a_, b_ = (s_p, s_l) if ponta == "s1" else (s_l, s_p)
                    if any(coberto(x, lado, a_, b_) for x in cad):
                        continue
                    E0, E1 = ponto(curta, s_p), _pt_linha(cad, s_l, d, n)
                    triangulos.append({"q": curta, "r": longa, "s0": a_, "s1": b_, "borda": True, "d": d, "n": n, "sp": s_p, "sl": s_l,
                                       "linha": cad, "E": (E0, s_p, E1, s_l),
                                       "cantos": [E0, _pt_linha(cad, s_p, d, n), E1],
                                       "area": alem * abs(longa["t"] - curta["t"]) / 2.0})
        panos += triangulos
        # os cantos dos panos deste grupo (no topo das duas terças)
        for p in panos:
            if "cantos" in p:
                continue
            q, r = p["q"], p["r"]
            p["d"], p["n"] = d, n
            meia = AFASTAMENTO_CALHA / 2.0 + COBRIMENTO_CALHA
            if p.get("eixo"):
                # a calha do V numa terça: centrada nela, as telhas param a AFASTAMENTO_CALHA / 2 de cada lado (_chapas)
                def lado_(s_, k_):
                    a_ = ponto(q, s_)
                    return (a_[0] + n[0] * meia * k_, a_[1] + n[1] * meia * k_, a_[2])
                p["cantos"] = [lado_(p["s0"], -1), lado_(p["s1"], -1), lado_(p["s1"], 1), lado_(p["s0"], 1)]
                continue
            if p.get("parede"):
                # a calha da parede: da face até COBRIMENTO_CALHA por baixo da ponta da telha, na altura da ponta
                L, Lt, m, lado = p["L"], p.get("Lt", p["L"]), p["m"], p["lado"]

                def ate(s_, x_):
                    a_ = ponto(q, s_)
                    return (a_[0] + n[0] * x_ * lado, a_[1] + n[1] * x_ * lado, a_[2] + m * Lt * lado)
                x0 = Lt - COBRIMENTO_CALHA
                p["cantos"] = [ate(p["s0"], x0), ate(p["s1"], x0), ate(p["s1"], L), ate(p["s0"], L)]
                continue
            if p.get("calha"):
                # a calha entre as duas terças do vale: centrada no vão, AFASTAMENTO_CALHA + 2 × COBRIMENTO_CALHA de largura
                tc_ = (q["t"] + r["t"]) / 2.0
                dt_ = (r["t"] - q["t"]) or 1.0

                def no_vao(s_, t_):
                    f = (t_ - q["t"]) / dt_
                    A_, B_ = ponto(q, s_), ponto(r, s_)
                    return tuple(A_[j] + (B_[j] - A_[j]) * f for j in range(3))
                p["cantos"] = [no_vao(p["s0"], tc_ - meia), no_vao(p["s1"], tc_ - meia), no_vao(p["s1"], tc_ + meia),
                               no_vao(p["s0"], tc_ + meia)]
                continue
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
        panos += _ate_a_parede_diagonal(reg, panos, d, n, ponto, z_em, paredes_todas, vao_max)
    calhas = [p for p in panos if p.get("calha")]
    cumeeiras = [p for p in panos if p.get("cumeeira")]
    panos = [p for p in panos if not p.get("calha") and not p.get("cumeeira")]
    return {"panos": panos, "calhas": calhas, "cumeeiras": cumeeiras, "fora": fora, "aguas": aguas, "vaos_grandes": vaos_grandes, "amostras": dict(amostras), "direcao": direcao,
            "sem_telha": [dict(v, comp=round(v["comp"])) for v in sem_telha.values()]}


def _ate_a_parede_diagonal(reg, panos, d, n, ponto, z_em, banzos, vao_max) -> List[dict]:
    """A borda contra a parede em diagonal (a TRANSIÇÃO 16 do Posto, 17/10/2026 — o usuário marcou a borda dela no 3D):
    a última terça antes da parede, sem outra terça do lado dela, fica sem telha até a face — o beiral entre duas terças
    (as `paredes` de _analise) precisa de uma terça do outro lado. Aqui, o lado da terça que nenhum pano cobre e que bate
    numa parede (o banzo de treliça que sobe acima da telha) a até 1,6 m, em diagonal, ganha o triângulo (ou o trapézio)
    da terça até 100 mm da face, na inclinação da água, em chapas recortadas. A parede mais perto paralela à terça fica
    de fora (é o beiral comum, ou a borda do telhado — a TRELIÇA 6 do Posto); a parede curva (sólido) também."""
    ALCANCE, FOLGA, PASSO = 1700.0, 100.0, 100.0
    CEL = 3000.0
    barreiras = [((b.inicio[0], b.inicio[1]), (b.fim[0], b.fim[1])) for b in banzos]
    grade_b: Dict[tuple, list] = collections.defaultdict(list)
    for k, (a, c) in enumerate(barreiras):
        for gx in range(int(min(a[0], c[0]) // CEL), int(max(a[0], c[0]) // CEL) + 1):
            for gy in range(int(min(a[1], c[1]) // CEL), int(max(a[1], c[1]) // CEL) + 1):
                grade_b[(gx, gy)].append(k)
    polis = []
    grade_p: Dict[tuple, list] = collections.defaultdict(list)
    for p in panos:
        if p.get("d") != d or "cantos" not in p:
            continue
        poli = [v[:2] for v in p["cantos"]]
        k = len(polis)
        polis.append(poli)
        xs, ys = [v[0] for v in poli], [v[1] for v in poli]
        for gx in range(int(min(xs) // 2000.0), int(max(xs) // 2000.0) + 1):
            for gy in range(int(min(ys) // 2000.0), int(max(ys) // 2000.0) + 1):
                grade_p[(gx, gy)].append(k)

    def coberto(P):
        return any(_dentro_poli(P, polis[k]) for k in grade_p.get((int(P[0] // 2000.0), int(P[1] // 2000.0)), ()))

    def parede(P, lado, z_telha):
        """a distância de P até a parede, andando para o lado (n·lado), e se ela corre em diagonal à terça"""
        v = (n[0] * lado * ALCANCE, n[1] * lado * ALCANCE)
        Q = (P[0] + v[0], P[1] + v[1])
        melhor = None
        vistos = set()
        for gx in range(int(min(P[0], Q[0]) // CEL), int(max(P[0], Q[0]) // CEL) + 1):
            for gy in range(int(min(P[1], Q[1]) // CEL), int(max(P[1], Q[1]) // CEL) + 1):
                for k in grade_b.get((gx, gy), ()):
                    if k in vistos:
                        continue
                    vistos.add(k)
                    a, c = barreiras[k]
                    s_ = (c[0] - a[0], c[1] - a[1])
                    den = v[0] * s_[1] - v[1] * s_[0]
                    if abs(den) < 1e-9:
                        continue
                    t = ((a[0] - P[0]) * s_[1] - (a[1] - P[1]) * s_[0]) / den
                    u = ((a[0] - P[0]) * v[1] - (a[1] - P[1]) * v[0]) / den
                    if not (0.0 <= t <= 1.0 and -0.001 <= u <= 1.001):
                        continue
                    bb = banzos[k]
                    topo = bb.inicio[2] + (bb.fim[2] - bb.inicio[2]) * max(0.0, min(1.0, u)) + _ext_z(bb)[1]
                    if topo < z_telha - 30.0:
                        continue                         # o banzo baixo: a telha passa por cima
                    Ls = math.hypot(*s_) or 1.0
                    diagonal = abs(s_[0] * d[0] + s_[1] * d[1]) / Ls < math.cos(math.radians(10.0))
                    if melhor is None or t * ALCANCE < melhor[0]:
                        melhor = (t * ALCANCE, diagonal)
        return melhor

    def inclinacao(r, lado, s_):
        """a inclinação da água chegando em r pelo outro lado (dz por dt), para seguir até a parede"""
        viz = [x for x in reg if x is not r and x["s0"] <= s_ <= x["s1"] and 0.0 < (r["t"] - x["t"]) * lado <= vao_max]
        if not viz:
            return 0.0
        x = min(viz, key=lambda x: abs(r["t"] - x["t"]))
        return (z_em(r, s_) - z_em(x, s_)) / (r["t"] - x["t"])

    novos = []
    for r in reg:
        L_ter = r["s1"] - r["s0"]
        if L_ter < 300.0:
            continue
        ss = [r["s0"] + 1.0] + [r["s0"] + PASSO * k for k in range(1, int(L_ter // PASSO))] + [r["s1"] - 1.0]
        for lado in (+1, -1):
            livres = []
            for s_ in ss:
                P = ponto(r, s_)
                if coberto((P[0] + n[0] * lado * 150.0, P[1] + n[1] * lado * 150.0)):
                    livres.append(None)
                    continue
                pa = parede(P[:2], lado, P[2])
                livres.append((s_, pa[0]) if pa is not None and pa[1] else None)
            # os trechos seguidos de terça descoberta com a parede diagonal perto
            k = 0
            while k < len(livres):
                if livres[k] is None:
                    k += 1
                    continue
                j = k
                while j + 1 < len(livres) and livres[j + 1] is not None:
                    j += 1
                sa, La = livres[k]
                sb, Lb = livres[j]
                k = j + 1
                # (a ponta fina do triângulo da borda escalonada, ao lado da terça, não conta: até 300 mm)
                if sb - sa < 300.0 or max(La, Lb) - FOLGA < 200.0 or min(La, Lb) > ALCANCE - 100.0 or abs(La - Lb) < 100.0:
                    continue
                m = inclinacao(r, lado, (sa + sb) / 2)

                def face(s_, L_):
                    P = ponto(r, s_)
                    x_ = max(0.0, L_ - FOLGA)
                    return (P[0] + n[0] * lado * x_, P[1] + n[1] * lado * x_, P[2] + m * lado * x_)
                Fa, Fb = face(sa, La), face(sb, Lb)
                Ma, Mb = ponto(r, sa), ponto(r, sb)
                larg = (max(0.0, La - FOLGA) + max(0.0, Lb - FOLGA)) / 2.0
                novos.append({"q": r, "r": r, "s0": sa, "s1": sb, "borda": True, "parede_diagonal": True, "d": d, "n": n,
                              "linha": [r], "E": (Fa, sa, Fb, sb), "cantos": [Ma, Mb, Fb, Fa],
                              "area": (sb - sa) * larg * math.sqrt(1.0 + m * m)})
    return novos


# ---------------------------------------------------------------------------------------------- as chapas de telha
def _pt_linha(linha, s_, d, n):
    """o ponto em s_ na linha de terça (os pedaços emendados): no pedaço que passa por s_ (ou no mais perto)"""
    ter = min(linha, key=lambda r: 0.0 if r["s0"] - 1.0 <= s_ <= r["s1"] + 1.0 else min(abs(s_ - r["s0"]), abs(s_ - r["s1"])))
    return _pt(ter, s_, d, n)


def _z_na_terca(ter, s_):
    return ter["z0"] if ter["s1"] - ter["s0"] < 1 else ter["z0"] + (ter["z1"] - ter["z0"]) * (s_ - ter["s0"]) / (ter["s1"] - ter["s0"])


def _pt(ter, s_, d, n):
    return (d[0] * s_ + n[0] * ter["t"], d[1] * s_ + n[1] * ter["t"], _z_na_terca(ter, s_))


def _perfil_tp(a_, b_, origem, telha):
    """o perfil trapezoidal atravessado (ao longo das terças) entre a_ e b_: [(s, altura)] — as ondas no passo da telha
    (TP 40: 4 por 1.020 mm, 40 mm), contadas da origem da água para as chapas vizinhas casarem"""
    passo = float(telha.get("passo_onda") or 255.0)
    h = float(telha.get("altura_onda") or 40.0)
    base, crista = 0.33 * passo, 0.12 * passo           # a base e a crista da onda (85 e 30 mm na TP 40)
    pts = [(a_, 0.0)]
    k = math.floor((a_ - origem) / passo)
    while True:
        s_on = origem + k * passo + (passo - base) / 2.0     # o começo da onda neste passo
        for s_, z_ in ((s_on, 0.0), (s_on + (base - crista) / 2, h), (s_on + (base + crista) / 2, h), (s_on + base, 0.0)):
            if a_ < s_ < b_:
                pts.append((s_, z_))
        if s_on > b_:
            break
        k += 1
    pts.append((b_, 0.0))
    return pts


def _partir(secoes, comp_max: float):
    """a sequência de seções de uma chapa partida onde a água muda (a cumeeira, o vale, a mudança de caída de mais de 4 %)
    e, na água mais comprida que a telha, em partes iguais numa terça (a emenda)"""
    def meio(sec):
        A, B = sec
        return ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2, (A[2] + B[2]) / 2)

    def incl(i):
        P, Q = meio(secoes[i]), meio(secoes[i + 1])
        h = math.hypot(Q[0] - P[0], Q[1] - P[1]) or 1.0
        return (Q[2] - P[2]) / h
    cortes = [0]
    for i in range(1, len(secoes) - 1):
        a_, b_ = incl(i - 1), incl(i)
        if (a_ > 0.005 and b_ < -0.005) or (a_ < -0.005 and b_ > 0.005) or abs(a_ - b_) > 0.04:
            cortes.append(i)
    cortes.append(len(secoes) - 1)
    partes = []
    for i0, i1 in zip(cortes, cortes[1:]):
        pedaco = secoes[i0:i1 + 1]
        dist = [0.0]
        for P, Q in zip(pedaco, pedaco[1:]):
            dist.append(dist[-1] + math.dist(meio(P), meio(Q)))
        n_ = max(1, int(math.ceil(dist[-1] / comp_max))) if comp_max > 0 else 1
        if n_ == 1 or len(pedaco) <= 2:
            partes.append(pedaco)
            continue
        # a emenda na terça mais perto de cada divisão igual
        idx = [0]
        for k in range(1, n_):
            alvo = dist[-1] * k / n_
            j = min(range(1, len(pedaco) - 1), key=lambda j: abs(dist[j] - alvo))
            if j > idx[-1]:
                idx.append(j)
        idx.append(len(pedaco) - 1)
        partes += [pedaco[a_:b_ + 1] for a_, b_ in zip(idx, idx[1:])]
    return [pt_ for pt_ in partes if len(pt_) >= 2]


def _chapas(panos, telha, vales=()):
    """As chapas de telha no sentido da caída: a cobertura de cada direção cortada em faixas da largura útil da telha
    (ao longo das terças, contadas do começo da água) e, em cada faixa, os panos seguidos (a terça de cima de um é a de
    baixo do outro) viram UMA chapa, da primeira à última terça (com o beiral) — as emendas correm na caída, como na
    obra. `vales`: as calhas do V numa terça — a chapa que acaba nela para a AFASTAMENTO_CALHA / 2 do eixo. Devolve
    [{secoes: [(A, B)] (as bordas da chapa em cada terça), a, b, origem, d, n}]."""
    W = float(telha.get("largura_util") or 1020.0)
    em_v: Dict[int, list] = collections.defaultdict(list)
    for c in vales:
        if c.get("eixo"):
            em_v[id(c["q"]["b"])].append((c["s0"], c["s1"]))

    def recua(parte, k_ponta, k_viz):
        """a seção da ponta recuada AFASTAMENTO_CALHA / 2 na direção da seção vizinha (a telha não chega no eixo do V)"""
        (A, B), (C, D) = parte[k_ponta], parte[k_viz]
        dist = math.hypot((C[0] + D[0] - A[0] - B[0]) / 2.0, (C[1] + D[1] - A[1] - B[1]) / 2.0) or 1.0
        f = min(0.5, AFASTAMENTO_CALHA / 2.0 / dist)
        parte[k_ponta] = (tuple(A[j] + (C[j] - A[j]) * f for j in range(3)), tuple(B[j] + (D[j] - B[j]) * f for j in range(3)))
    por_dir: Dict[tuple, list] = collections.defaultdict(list)
    for p in panos:
        if p.get("borda") or p.get("calha") or p.get("cumeeira") or "d" not in p:
            continue
        por_dir[(round(p["d"][0], 6), round(p["d"][1], 6))].append(p)
    chapas = []
    for _k, lst in por_dir.items():
        d, n = lst[0]["d"], lst[0]["n"]
        origem = min(p["s0"] for p in lst)
        fim = max(p["s1"] for p in lst)
        k = 0
        while origem + k * W < fim - 1:
            a, b = origem + k * W, origem + (k + 1) * W
            k += 1
            pedacos: Dict[tuple, list] = collections.defaultdict(list)   # (a', b') → [pano]
            for p in lst:
                a2, b2 = max(a, p["s0"]), min(b, p["s1"])
                if b2 - a2 >= 30.0:
                    pedacos[(round(a2), round(b2))].append(p)
            for (a2, b2), ps in pedacos.items():
                # as ligações: terça de baixo → pano (pela ordem na caída, t crescente); o beiral é uma ponta
                comuns = [p for p in ps if not p.get("beiral")]
                beirais = [p for p in ps if p.get("beiral")]
                de = {id(p["q"]["b"]): p for p in comuns}
                chega = {id(p["r"]["b"]) for p in comuns}
                for ini in [p for p in comuns if id(p["q"]["b"]) not in chega]:
                    seq_t = [ini["q"]]
                    p_ = ini
                    while p_ is not None and len(seq_t) < 200:
                        seq_t.append(p_["r"])
                        p_ = de.get(id(p_["r"]["b"]))
                    secoes = [(_pt(t_, a2, d, n), _pt(t_, b2, d, n)) for t_ in seq_t]
                    terca_da = {id(sec): t_ for sec, t_ in zip(secoes, seq_t)}
                    # o beiral nas pontas (até a face da parede)
                    for bb in beirais:
                        ext = lambda P, bb=bb: (P[0] + n[0] * bb["L"] * bb["lado"], P[1] + n[1] * bb["L"] * bb["lado"], P[2] + bb["m"] * bb["L"] * bb["lado"])
                        if bb["q"] is seq_t[-1] and bb["lado"] > 0:
                            secoes.append((ext(secoes[-1][0]), ext(secoes[-1][1])))
                        elif bb["q"] is seq_t[0] and bb["lado"] < 0:
                            secoes.insert(0, (ext(secoes[0][0]), ext(secoes[0][1])))
                    # uma chapa por água (a cumeeira e o vale separam), até o comprimento da telha (12 m na TP 40)
                    for parte in _partir(secoes, float(telha.get("comprimento_max") or 12000.0)):
                        parte = list(parte)
                        for k_ponta, k_viz in ((0, 1), (len(parte) - 1, len(parte) - 2)):
                            t_ = terca_da.get(id(parte[k_ponta]))
                            if t_ is not None and any(x0 < b2 - 1 and x1 > a2 + 1 for x0, x1 in em_v.get(id(t_["b"]), ())):
                                recua(parte, k_ponta, k_viz)
                        chapas.append({"secoes": parte, "a": a2, "b": b2, "origem": origem, "d": d, "n": n})
                # o beiral sozinho (a água de uma terça só até a parede)
                usados = {id(x) for x in comuns}
                for bb in beirais:
                    if any(bb["q"] is p["q"] or bb["q"] is p["r"] for p in comuns):
                        continue
                    t_ = bb["q"]
                    P0, P1 = _pt(t_, a2, d, n), _pt(t_, b2, d, n)
                    ext = lambda P, bb=bb: (P[0] + n[0] * bb["L"] * bb["lado"], P[1] + n[1] * bb["L"] * bb["lado"], P[2] + bb["m"] * bb["L"] * bb["lado"])
                    sec = [(P0, P1), (ext(P0), ext(P1))]
                    chapas.append({"secoes": sec if bb["lado"] > 0 else sec[::-1], "a": a2, "b": b2, "origem": origem, "d": d, "n": n})
    # a borda escalonada: a chapa recortada na diagonal — da terça longa até a linha da borda (da ponta da curta à da
    # longa), nas mesmas faixas e ondas da água (são as telhas que vão precisar de recorte)
    for p in panos:
        if not p.get("borda") or ("sp" not in p and "E" not in p):
            continue
        d, n = p["d"], p["n"]
        linha = p.get("linha") or [p["r"]]
        # a linha da borda: da ponta da curta à da longa (a borda escalonada) ou a face da parede diagonal
        E0, sp, E1, sl = p.get("E") or (_pt(p["q"], p["sp"], d, n), p["sp"], _pt(p["r"], p["sl"], d, n), p["sl"])
        orig = min((q["s0"] for q in panos if q.get("d") == d and not q.get("borda")), default=min(sp, sl))

        def borda_em(s_):
            f = (s_ - sp) / ((sl - sp) or 1.0)
            return (E0[0] + (E1[0] - E0[0]) * f, E0[1] + (E1[1] - E0[1]) * f, E0[2] + (E1[2] - E0[2]) * f)
        lo, hi = min(sp, sl), max(sp, sl)
        k0 = math.floor((lo - orig) / W)
        while orig + k0 * W < hi - 1:
            a2, b2 = max(lo, orig + k0 * W), min(hi, orig + (k0 + 1) * W)
            k0 += 1
            if b2 - a2 < 30.0:
                continue
            chapas.append({"secoes": [(_pt_linha(linha, a2, d, n), _pt_linha(linha, b2, d, n)), (borda_em(a2), borda_em(b2))],
                           "a": a2, "b": b2, "origem": orig, "d": d, "n": n, "recorte": True})
    return chapas


def _dentro_poli(pt, poli) -> bool:
    x, y = pt
    dentro = False
    j = len(poli) - 1
    for i in range(len(poli)):
        xi, yi = poli[i]
        xj, yj = poli[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            dentro = not dentro
        j = i
    return dentro


def _fechamentos(doc, panos, telha, camada):
    """Os fechamentos laterais (12/10/2026, "lançar as telhas dos fechamentos laterais ... vai ficar mais claro como
    ficaram as telhas que precisam de recortes"): em cada painel (a testeira), a TP 40 em pé na face de FORA — o lado sem
    telhado —, do banzo de baixo ao de cima, em chapas da largura útil ao longo do painel (o curvo, trecho a trecho), com
    as ondas na vertical. Devolve (sólidos, metros, m²)."""
    from nucleo3d import apoios as _ap
    polis = [[v[:2] for v in p["cantos"]] for p in panos]
    CEL = 3000.0
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for k, pl in enumerate(polis):
        xs, ys = [v[0] for v in pl], [v[1] for v in pl]
        for gx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for gy in range(int(min(ys) // CEL), int(max(ys) // CEL) + 1):
                grade[(gx, gy)].append(k)

    def coberto(pt):
        return any(_dentro_poli(pt, polis[k]) for k in grade.get((int(pt[0] // CEL), int(pt[1] // CEL)), ()))
    paineis: Dict[str, list] = collections.defaultdict(list)
    # toda treliça do perímetro (o painel da testeira, a transição e a treliça da borda — a borda diagonal do Posto são as
    # TRANSIÇÕES 14–16 e a TRELIÇA 3): a que tem telhado de um lado e nada do outro
    for e in _ap._elementos(doc):
        nome_ = str(e.peca or "").upper()
        # (e a tesoura da borda — a TESOURA 6 do Posto, em y 53,40, entre a curva do PAINEL 8 e o PAINEL 15)
        # (e as treliças com os nomes da regra 7 das tesouras — P.n platibanda/fechamento, VT.n, VL.n: o Mercado, 19/10, não
        # ganhava fechamento nenhum; a tesoura T.n/MT.n no perímetro fica de fora — no Mercado ela encosta no fechamento ou na
        # parede de concreto; o teste de perímetro abaixo é que separa a do perímetro da do meio)
        if e.papel == "banzo" and (nome_.startswith(("PAINEL", "TRANSI", "TRELI", "TESOURA"))
                                   or re.match(r"^(P|VT|VL)\.\d", nome_)):
            paineis[e.peca].append(e)
    W = float(telha.get("largura_util") or 1020.0)
    solidos, ml, area = [], 0.0, 0.0
    for peca, lst in paineis.items():
        segs = [sg for e in lst for sg in e.segs]
        zmin = min(min(a[2], b[2]) for a, b in segs)
        cima = [(a, b) for a, b in segs if min(a[2], b[2]) > zmin + 300.0]

        def tem_acima(a, b, f=0.5):
            # outro banzo da mesma peça passa por cima deste ali (a linha do telhado por dentro do PAINEL 15, da TESOURA 6):
            # só o mais alto — conferido chapa a chapa (o de cima pode cobrir só parte do de baixo)
            mx, my, mz = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
            for c, d_ in cima:
                if (c, d_) == (a, b):
                    continue
                Lc = math.hypot(d_[0] - c[0], d_[1] - c[1])
                if Lc < 1:
                    continue
                t_ = ((mx - c[0]) * (d_[0] - c[0]) + (my - c[1]) * (d_[1] - c[1])) / (Lc * Lc)
                if -0.01 <= t_ <= 1.01 and math.hypot(c[0] + (d_[0] - c[0]) * t_ - mx, c[1] + (d_[1] - c[1]) * t_ - my) < 150.0                         and c[2] + (d_[2] - c[2]) * t_ > mz + 100.0:
                    return True
            return False
        cima_todos = list(cima)
        cum = 0.0
        for A, B in cima:
            L = math.hypot(B[0] - A[0], B[1] - A[1])
            if L < 30.0:
                continue
            u = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
            nh = (-u[1], u[0])
            # o lado do telhado: coberto até 1,5 m da face (o PAINEL 21 do Posto fica a mais de 0,4 m da telha); o de fora:
            # nada até 0,9 m
            def lado_coberto(M, k_):
                return any(coberto((M[0] + nh[0] * x_ * k_, M[1] + nh[1] * x_ * k_)) for x_ in (400.0, 900.0, 1500.0))

            def lado_livre(M, k_):
                # o telhado pode passar do painel em beiral até 0,9 m (o PAINEL 15 do Posto)
                return not any(coberto((M[0] + nh[0] * x_ * k_, M[1] + nh[1] * x_ * k_)) for x_ in (900.0, 1500.0))
            # em três pontos ao longo do trecho, por maioria (o meio do PAINEL 15 cai no vão da cumeeira, sem telha)
            votos = [0, 0]
            for f_ in (0.2, 0.5, 0.8):
                M = (A[0] + (B[0] - A[0]) * f_, A[1] + (B[1] - A[1]) * f_)
                votos[0] += lado_coberto(M, +1) and lado_livre(M, -1)
                votos[1] += lado_coberto(M, -1) and lado_livre(M, +1)
            mais, menos = votos[0] >= 2 and votos[0] > votos[1], votos[1] >= 2 and votos[1] > votos[0]
            if mais == menos:
                cum += L
                continue                                 # telhado dos dois lados, ou de nenhum: não é perímetro
            fora_ = (-nh[0], -nh[1]) if mais else nh
            zb = zmin - 60.0

            def zt(s_):
                return A[2] + (B[2] - A[2]) * s_ / L + 60.0
            # o fechamento é duplo: a telha nas duas faces do painel (110 mm do eixo, as ondas para fora de cada face)
            for face in (fora_, (-fora_[0], -fora_[1])):
                def P(s_, z_, face=face):
                    return (A[0] + u[0] * s_ + face[0] * 110.0, A[1] + u[1] * s_ + face[1] * 110.0, z_)
                a_ = 0.0
                while a_ < L - 1.0:
                    b_ = min(L, a_ + W)
                    if tem_acima(A, B, (a_ + b_) / 2.0 / L):
                        a_ = b_
                        continue
                    ch = {"secoes": [(P(a_, zb), P(b_, zb)), (P(a_, zt(a_)), P(b_, zt(b_)))],
                          "a": cum + a_, "b": cum + b_, "origem": 0.0, "d": u, "n": nh}
                    so = _solido_da_chapa(ch, telha, camada, normal=(face[0], face[1], 0.0))
                    so.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "fechamento": True, "telha": telha["modelo"],
                                    "painel": peca.split("#")[0], "face": "fora" if face is fora_ else "dentro"}
                    solidos.append(so)
                    area += (b_ - a_) * ((zt(a_) + zt(b_)) / 2 - zb)
                    if face is fora_:
                        ml += b_ - a_                    # o perímetro com fechamento (uma face)
                    a_ = b_
            cum += L
    return solidos, ml, area


def _revestimentos(doc, panos, telha, camada):
    """O revestimento da treliça que sobe acima da telha no MEIO do telhado (17/10/2026 — o usuário marcou no 3D do Posto a
    TRANSIÇÃO 1 e as tesouras de cima das TRANSIÇÕES 2/3/5/6 atravessando a telha): o corte BB do projeto manda "REVESTIR
    TRANSIÇÃO 2/3 COM TELHA OU RUFO", com "RUFO C/TELHA" onde a telha encosta e "RUFO MOLDURA" no topo da TRANSIÇÃO 1
    (+7,60). Na treliça com telhado dos DOIS lados cujo banzo de cima passa mais de 100 mm acima da telha: a TP em pé nas
    duas faces, da telha de cada lado até o topo, e o rufo moldura (chapa galvanizada #26, corte 400) em cima. A treliça
    do perímetro (telhado de um lado só) é o fechamento (_fechamentos). Devolve (sólidos, metros de rufo, m²)."""
    tris = []
    CEL = 2000.0
    grade: Dict[tuple, list] = collections.defaultdict(list)
    for p in panos:
        c = p.get("cantos") or []
        for i in range(1, len(c) - 1):
            k = len(tris)
            tris.append((c[0], c[i], c[i + 1]))
            xs, ys = (c[0][0], c[i][0], c[i + 1][0]), (c[0][1], c[i][1], c[i + 1][1])
            for gx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
                for gy in range(int(min(ys) // CEL), int(max(ys) // CEL) + 1):
                    grade[(gx, gy)].append(k)

    def z_telha(x, y):
        zs = []
        for k in grade.get((int(x // CEL), int(y // CEL)), ()):
            a, b, c = tris[k]
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
            l3 = 1.0 - l1 - l2
            if min(l1, l2, l3) >= -1e-6:
                zs.append(l1 * a[2] + l2 * b[2] + l3 * c[2])
        return max(zs) if zs else None

    def telha_ao_lado(M, nh, k_):
        for x_ in (300.0, 600.0, 1000.0):
            z_ = z_telha(M[0] + nh[0] * x_ * k_, M[1] + nh[1] * x_ * k_)
            if z_ is not None:
                return z_
        return None
    pecas: Dict[str, list] = collections.defaultdict(list)
    for b in doc.barras:
        if b.papel == "banzo" and b.camada == "Treliças" and origem_de(b).get("peca"):
            pecas[origem_de(b)["peca"]].append(b)
    W = float(telha.get("largura_util") or 1020.0)
    solidos, ml_rufo, area = [], 0.0, 0.0
    for peca, lst in pecas.items():
        # todos os banzos: o de baixo fica sob a telha (e sai pela altura); o de cima da tesoura de cima começa a 0,30 m
        # do banzo reto dela
        cima = lst
        for b in cima:
            A, B = b.inicio, b.fim
            L = math.hypot(B[0] - A[0], B[1] - A[1])
            if L < 300.0:
                continue
            u = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
            nh = (-u[1], u[0])
            topo = _ext_z(b)[1] + 6.0

            def zt(s_):
                return A[2] + (B[2] - A[2]) * s_ / L + topo
            # só o banzo mais alto ali (o de baixo de uma treliça de duas alturas fica por dentro)
            def por_baixo(s_):
                mx, my, mz = A[0] + u[0] * s_, A[1] + u[1] * s_, zt(s_)
                for c in cima:
                    if c is b:
                        continue
                    Lc = math.hypot(c.fim[0] - c.inicio[0], c.fim[1] - c.inicio[1])
                    if Lc < 1:
                        continue
                    t_ = ((mx - c.inicio[0]) * (c.fim[0] - c.inicio[0]) + (my - c.inicio[1]) * (c.fim[1] - c.inicio[1])) / (Lc * Lc)
                    if -0.01 <= t_ <= 1.01 and math.hypot(c.inicio[0] + (c.fim[0] - c.inicio[0]) * t_ - mx,
                                                          c.inicio[1] + (c.fim[1] - c.inicio[1]) * t_ - my) < 150.0 \
                            and c.inicio[2] + (c.fim[2] - c.inicio[2]) * t_ + _ext_z(c)[1] + 6.0 > mz + 5.0:
                        return True                       # o outro banzo com o topo mais alto ali (o par do caixão)
                return False
            rufo = []                                     # os trechos com revestimento (para o rufo do topo)
            a_ = 0.0
            while a_ < L - 1.0:
                b_ = min(L, a_ + W)
                sm = (a_ + b_) / 2.0
                M = (A[0] + u[0] * sm, A[1] + u[1] * sm)
                lados = [telha_ao_lado(M, nh, k_) for k_ in (+1, -1)]
                if None in lados or por_baixo(sm) or zt(sm) - max(lados) < 100.0:
                    a_ = b_
                    continue
                for k_, face in ((+1, nh), (-1, (-nh[0], -nh[1]))):
                    def P(s_, z_, face=face):
                        return (A[0] + u[0] * s_ + face[0] * 110.0, A[1] + u[1] * s_ + face[1] * 110.0, z_)
                    za = telha_ao_lado((A[0] + u[0] * a_, A[1] + u[1] * a_), nh, k_) or lados[0 if k_ > 0 else 1]
                    zb = telha_ao_lado((A[0] + u[0] * b_, A[1] + u[1] * b_), nh, k_) or lados[0 if k_ > 0 else 1]
                    if zt(a_) - za < 30.0 and zt(b_) - zb < 30.0:
                        continue
                    ch = {"secoes": [(P(a_, min(za, zt(a_))), P(b_, min(zb, zt(b_)))), (P(a_, zt(a_)), P(b_, zt(b_)))],
                          "a": a_, "b": b_, "origem": 0.0, "d": u, "n": nh}
                    so = _solido_da_chapa(ch, telha, camada, normal=(face[0], face[1], 0.0))
                    so.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "fechamento": True, "revestimento": True,
                                    "telha": telha["modelo"], "painel": peca.split("#")[0]}
                    solidos.append(so)
                    area += (b_ - a_) * max(0.0, (zt(a_) - za + zt(b_) - zb) / 2.0)
                if rufo and abs(rufo[-1][1] - a_) < 1.0:
                    rufo[-1][1] = b_
                else:
                    rufo.append([a_, b_])
                a_ = b_
            # o rufo moldura no topo: a chapa por cima do banzo e as abas descendo 100 mm por fora do revestimento
            for r0, r1 in rufo:
                vs, fs = [], []
                for off0, off1, dz0, dz1 in ((-130.0, 130.0, 0.0, 6.0), (-136.0, -130.0, -100.0, 6.0), (130.0, 136.0, -100.0, 6.0)):
                    o = len(vs)
                    for s_ in (r0, r1):
                        for off, dz in ((off0, dz0), (off1, dz0), (off1, dz1), (off0, dz1)):
                            vs.append((A[0] + u[0] * s_ + nh[0] * off, A[1] + u[1] * s_ + nh[1] * off, zt(s_) + dz))
                    fs += [[o, o + 1, o + 2, o + 3], [o + 7, o + 6, o + 5, o + 4], [o, o + 4, o + 5, o + 1],
                           [o + 1, o + 5, o + 6, o + 2], [o + 2, o + 6, o + 7, o + 3], [o + 3, o + 7, o + 4, o]]
                so = Solido(nome="Rufo moldura (ch. galv. #26, corte 400)", camada="Rufos", vertices=vs, faces=fs)
                so.atributos = {"tipo_ifc": "IfcCovering", "rufo_lancado": True, "rufo": "moldura", "painel": peca.split("#")[0],
                                "comprimento": round(r1 - r0)}
                solidos.append(so)
                ml_rufo += r1 - r0
    return solidos, ml_rufo, area


def _solido_da_chapa(ch, telha, camada, espessura=ESPESSURA_DESENHO, normal=(0.0, 0.0, 1.0)):
    """o sólido da chapa: o perfil trapezoidal (as ondas no sentido da caída) em cada terça, ligado de uma à outra; a
    onda cresce para `normal` (para cima no telhado, para fora no fechamento)"""
    perfil = _perfil_tp(ch["a"], ch["b"], ch["origem"], telha)
    np_ = len(perfil)
    vs, fs = [], []
    for A, B in ch["secoes"]:
        L = (ch["b"] - ch["a"]) or 1.0
        for s_, h in perfil:
            f = (s_ - ch["a"]) / L
            hh = h + espessura
            vs.append((A[0] + (B[0] - A[0]) * f + normal[0] * hh, A[1] + (B[1] - A[1]) * f + normal[1] * hh,
                       A[2] + (B[2] - A[2]) * f + normal[2] * hh))
        vs.append((A[0], A[1], A[2]))                     # o fundo, nas duas bordas
        vs.append((B[0], B[1], B[2]))
    m = np_ + 2
    for j in range(len(ch["secoes"]) - 1):
        o, o2 = j * m, (j + 1) * m
        for i in range(np_ - 1):
            fs.append([o + i, o2 + i, o2 + i + 1, o + i + 1])          # a face de cima, onda por onda
        fs.append([o + np_, o + np_ + 1, o2 + np_ + 1, o2 + np_])        # o fundo
        fs.append([o + np_, o2 + np_, o2, o])                            # as bordas da chapa
        fs.append([o + np_ - 1, o2 + np_ - 1, o2 + np_ + 1, o + np_ + 1])
    s = Solido(nome=telha["nome"], camada=camada, vertices=vs, faces=fs)
    return s


def lancar(doc, telha: Optional[dict] = None, vao_max: float = 2500.0, tol_plano: float = 10.0,
           camada: str = "Telhas") -> dict:
    """Lança os panos de telha em cima das terças de `doc` (tira os panos lançados antes por aqui). Devolve o resumo,
    as águas e os apontamentos."""
    telha = dict(TELHA_PADRAO, **(telha or {}))
    # tira os panos de uma rodada anterior
    for i in [e.id for e in doc.solidos if (e.atributos or {}).get("telha_lancada") or (e.atributos or {}).get("calha_lancada")
              or (e.atributos or {}).get("rufo_lancado")]:
        doc.remover(i)
    tercas = [b for b in doc.barras if b.papel in ("terça", "terca")]
    an = _analise(tercas, doc.barras, vao_max, tol_plano)
    feitos = an["panos"]
    chapas = _chapas(feitos, telha, an["calhas"])
    for ch in chapas:
        so = _solido_da_chapa(ch, telha, camada)
        so.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": telha["modelo"],
                        **({"recorte": True} if ch.get("recorte") else {}),
                        "comprimento": round(sum(math.dist(((a1[0] + b1[0]) / 2, (a1[1] + b1[1]) / 2, a1[2]), ((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2, a2[2]))
                                                 for (a1, b1), (a2, b2) in zip(ch["secoes"], ch["secoes"][1:])))}
        doc.add(so)
    # a calha e a cumeeira contam como telhado (o pedaço de tesoura na linha da calha não é borda)
    fech, fech_ml, fech_area = _fechamentos(doc, feitos + an["calhas"] + an["cumeeiras"], telha, camada)
    for so in fech:
        doc.add(so)
    # e a treliça que sobe acima da telha no meio do telhado: revestida e com rufo no topo (o corte BB do Posto)
    rev, rufo_ml, rev_area = _revestimentos(doc, feitos + an["calhas"] + an["cumeeiras"], telha, camada)
    for so in rev:
        doc.add(so)
    for p in []:                                         # o triângulo da borda virou chapa recortada (_chapas)
        c = p["cantos"]
        e = ESPESSURA_DESENHO
        k = len(c)
        vs = c + [(x, y, z + e) for x, y, z in c]
        fs = [list(range(k - 1, -1, -1)), list(range(k, 2 * k))] + [[i, (i + 1) % k, k + (i + 1) % k, k + i] for i in range(k)]
        s = Solido(nome=telha["nome"], camada=camada, vertices=vs, faces=fs)
        s.atributos = {"tipo_ifc": "IfcCovering", "telha_lancada": True, "telha": telha["modelo"],
                       "entre": [p["q"]["sigla"], p["r"]["sigla"]], **({"beiral": True} if p.get("beiral") else {})}
        doc.add(s)
    # a calha: a caixa entre as duas terças do vale, logo abaixo da telha (200 mm de fundo)
    ml_calha = 0.0
    for c in an["calhas"]:
        cs = c["cantos"]
        # a calha do vale em V e a da parede ficam no nível da telha (a telha entra nela); a entre duas terças, abaixo
        # por baixo da ponta das telhas, que entram nela COBRIMENTO_CALHA (17/10: a do V e a da parede ficavam 50 mm por
        # cima da telha)
        topo = min(v[2] for v in cs) - 15.0
        de = [(x, y, topo) for x, y, _z in cs]
        vs = [(x, y, topo - FUNDO_CALHA) for x, y, _z in cs] + de
        fs = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        so = Solido(nome="Calha", camada="Calhas", vertices=vs, faces=fs)
        so.atributos = {"tipo_ifc": "IfcPipeSegment", "calha_lancada": True, "entre": [c["q"]["sigla"], c["r"]["sigla"]]}
        doc.add(so)
        ml_calha += c["s1"] - c["s0"]
    for for_ in [e.id for e in doc.solidos if (e.atributos or {}).get("cumeeira_lancada")]:
        doc.remover(for_)
    ml_cume = 0.0
    for c in an["cumeeiras"]:
        q_, r_ = c["q"], c["r"]
        d_, n_ = c["d"], c["n"]
        dt_ = r_["t"] - q_["t"]
        cs = []
        for s_ in (c["s0"], c["s1"]):
            A = _pt(q_, s_, d_, n_)
            B = _pt(r_, s_, d_, n_)
            meio_ = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2, max(A[2], B[2]) + 60.0)
            fora_a = (A[0] - n_[0] * 100.0, A[1] - n_[1] * 100.0, A[2] + 40.0)
            fora_b = (B[0] + n_[0] * 100.0, B[1] + n_[1] * 100.0, B[2] + 40.0)
            cs.append((fora_a, meio_, fora_b))
        (a0, m0, b0), (a1, m1, b1) = cs
        vs = [a0, m0, b0, a1, m1, b1] + [(x, y, z + ESPESSURA_DESENHO) for x, y, z in (a0, m0, b0, a1, m1, b1)]
        fs = [[0, 3, 4, 1], [1, 4, 5, 2], [6, 7, 10, 9], [7, 8, 11, 10], [0, 1, 7, 6], [1, 2, 8, 7], [3, 9, 10, 4], [4, 10, 11, 5],
              [0, 6, 9, 3], [2, 5, 11, 8]]
        so = Solido(nome="Cumeeira", camada="Cumeeiras", vertices=vs, faces=fs)
        so.atributos = {"tipo_ifc": "IfcCovering", "cumeeira_lancada": True, "entre": [q_["sigla"], r_["sigla"]], "abas_mm": round(dt_ + 200)}
        doc.add(so)
        ml_cume += c["s1"] - c["s0"]
    fora, aguas, vaos_grandes = an["fora"], an["aguas"], an["vaos_grandes"]
    area = sum(p.get("area", 0.0) for p in feitos) / 1e6
    lista_aguas = sorted(aguas.values(), key=lambda a: (a["caida_pct"], -a["comprimento"]))
    for a in lista_aguas:
        a["largura"] = round(a["largura"])
        a["emenda"] = a["comprimento"] > telha["comprimento_max"]
    return {
        "telha": telha["nome"], "panos": len(feitos), "chapas": len(chapas), "area_m2": round(area, 1), "peso_kg": round(area * telha["massa_m2"], 1),
        "beirais": sum(1 for p in feitos if p.get("beiral")), "bordas": sum(1 for p in feitos if p.get("borda")),
        "recortes": sum(1 for c in chapas if c.get("recorte")),
        "calhas": len(an["calhas"]), "calha_ml": round(ml_calha / 1000.0, 1),
        "calhas_vale": sum(1 for c in an["calhas"] if c.get("eixo")), "calhas_parede": sum(1 for c in an["calhas"] if c.get("parede")),
        "fechamentos": len(fech), "fechamento_ml": round(fech_ml / 1000.0, 1), "fechamento_m2": round(fech_area / 1e6, 1),
        "revestimentos": sum(1 for so in rev if (so.atributos or {}).get("revestimento")), "revestimento_m2": round(rev_area / 1e6, 1),
        "rufo_ml": round(rufo_ml / 1000.0, 1),
        "cumeeiras": len(an["cumeeiras"]), "cumeeira_ml": round(ml_cume / 1000.0, 1),
        "tercas": len(tercas), "aguas": lista_aguas,
        "caida_min": min((a["caida_pct"] for a in lista_aguas), default=None),
        "caida_max": max((a["caida_pct"] for a in lista_aguas), default=None),
        "fora_do_plano": sorted(fora.values(), key=lambda f: -abs(f["desvio"])),
        "vaos_grandes": [dict(v, comp=round(v["comp"]), ponto=[round(c) for c in v["ponto"]]) for v in vaos_grandes.values() if v["comp"] > 300],
        "ao_lado": conferir_ao_lado(chapas),
    }


def conferir_ao_lado(chapas, limite: float = 20.0) -> List[dict]:
    """A telha ao lado (12/10, o usuário: "precisa existir alguma verificação da telha ao lado, para seguir um
    alinhamento … o que comanda no final é a telha, toda a estrutura é feita para acomodá-las"): cada chapa com a da
    faixa do lado — a borda comum na mesma altura — e a caída dela reta — a terça do meio na reta das vizinhas. Devolve
    os pontos que não encaixam ({tipo: degrau|dobra, mm, ponto}), do maior para o menor, um por lugar (2 m)."""
    def borda(ch, lado):
        n = ch["n"]
        return sorted(((Q[0] * n[0] + Q[1] * n[1], Q[2], Q[0], Q[1]) for Q in (s[lado] for s in ch["secoes"])))

    def z_em(bd, t):
        for (t0, z0, *_r0), (t1, z1, *_r1) in zip(bd, bd[1:]):
            if t0 - 1.0 <= t <= t1 + 1.0:
                return z0 + (z1 - z0) * (t - t0) / ((t1 - t0) or 1.0)
        return None
    achados = []
    por_dir: Dict[tuple, list] = collections.defaultdict(list)
    for ch in chapas:
        if not ch.get("recorte"):
            por_dir[(round(ch["d"][0], 4), round(ch["d"][1], 4))].append(ch)
    for lst in por_dir.values():
        pela_a: Dict[int, list] = collections.defaultdict(list)
        for ch in lst:
            pela_a[round(ch["a"])].append(ch)
        for ch in lst:
            bd1 = borda(ch, 1)
            for viz in pela_a.get(round(ch["b"]), []):
                bd2 = borda(viz, 0)
                t_lo, t_hi = max(bd1[0][0], bd2[0][0]), min(bd1[-1][0], bd2[-1][0])
                if t_hi - t_lo < 200.0:
                    continue
                pior = None
                for i in range(11):
                    t = t_lo + (t_hi - t_lo) * i / 10.0
                    z1, z2 = z_em(bd1, t), z_em(bd2, t)
                    if z1 is None or z2 is None or (pior is not None and abs(z1 - z2) <= abs(pior[0])):
                        continue
                    f = (t - bd1[0][0]) / ((bd1[-1][0] - bd1[0][0]) or 1.0)
                    pior = (z1 - z2, bd1[0][2] + (bd1[-1][2] - bd1[0][2]) * f, bd1[0][3] + (bd1[-1][3] - bd1[0][3]) * f)
                if pior and abs(pior[0]) > limite:
                    achados.append({"tipo": "degrau", "mm": round(pior[0]), "ponto": [round(pior[1]), round(pior[2])]})
        # a caída de cada faixa inteira (as chapas da faixa emendadas: a terça erguida parte a chapa ali): a terça do meio
        # fora da reta das vizinhas é dobra — menos na cumeeira e no vale (a caída troca de sentido, é de propósito)
        def chave(P):
            return (round(P[0] / 5.0), round(P[1] / 5.0))
        for a_faixa, da_faixa in pela_a.items():
            comeca = {chave(((c["secoes"][0][0][0] + c["secoes"][0][1][0]) / 2, (c["secoes"][0][0][1] + c["secoes"][0][1][1]) / 2)): c
                      for c in da_faixa}
            termina = {chave(((c["secoes"][-1][0][0] + c["secoes"][-1][1][0]) / 2, (c["secoes"][-1][0][1] + c["secoes"][-1][1][1]) / 2))
                       for c in da_faixa}
            for ch in da_faixa:
                m0 = chave(((ch["secoes"][0][0][0] + ch["secoes"][0][1][0]) / 2, (ch["secoes"][0][0][1] + ch["secoes"][0][1][1]) / 2))
                if m0 in termina:
                    continue                                  # não é o começo da fila
                secoes, c_ = list(ch["secoes"]), ch
                for _k in range(50):
                    fim = secoes[-1]
                    prox = comeca.get(chave(((fim[0][0] + fim[1][0]) / 2, (fim[0][1] + fim[1][1]) / 2)))
                    if prox is None or prox is c_:
                        break
                    secoes += prox["secoes"][1:]
                    c_ = prox
                meio = [((A[0] + B[0]) / 2, (A[1] + B[1]) / 2, (A[2] + B[2]) / 2) for A, B in secoes]
                for P0, P1, P2 in zip(meio, meio[1:], meio[2:]):
                    h01, h02 = math.hypot(P1[0] - P0[0], P1[1] - P0[1]), math.hypot(P2[0] - P0[0], P2[1] - P0[1]) or 1.0
                    i1, i2 = (P1[2] - P0[2]) / (h01 or 1.0), (P2[2] - P1[2]) / ((h02 - h01) or 1.0)
                    # a cumeeira e o vale: as duas águas com caída de verdade (a terça erguida faz um "cume" com um lado
                    # quase plano — esse é dobra)
                    if i1 * i2 < 0.0 and abs(i1) > 0.02 and abs(i2) > 0.02:
                        continue
                    dz = P1[2] - (P0[2] + (P2[2] - P0[2]) * h01 / h02)
                    if abs(dz) > limite:
                        achados.append({"tipo": "dobra", "mm": round(dz), "ponto": [round(P1[0]), round(P1[1])]})
    um_por_lugar: Dict[tuple, dict] = {}
    for a in sorted(achados, key=lambda a: -abs(a["mm"])):
        um_por_lugar.setdefault((a["tipo"], round(a["ponto"][0] / 2000.0), round(a["ponto"][1] / 2000.0)), a)
    return list(um_por_lugar.values())


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
                o = origem_de(a)
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


def _choca_ao_subir(b, sobe, barras, tol: float = 40.0, longe_da_ponta: float = 150.0) -> bool:
    """a terça b, erguida `sobe` mm, passaria por dentro de uma peça que ela não atravessava (o choque da conferência do
    3D: os eixos a menos de `tol`, longe das pontas das duas)"""
    from nucleo3d.conferencia_3d import _seg_seg
    P = (b.inicio[0], b.inicio[1], b.inicio[2] + sobe)
    Q = (b.fim[0], b.fim[1], b.fim[2] + sobe)
    L = math.dist(P, Q)
    x0, x1 = min(P[0], Q[0]) - 300.0, max(P[0], Q[0]) + 300.0
    y0, y1 = min(P[1], Q[1]) - 300.0, max(P[1], Q[1]) + 300.0
    for a in barras:
        if a is b or a.tipo != "barra" or a.papel in ("terça", "terca", "corrente", "esticador", "agulha", "tirante",
                                                       "contraventamento", "apoio_terca"):
            continue
        if max(a.inicio[0], a.fim[0]) < x0 or min(a.inicio[0], a.fim[0]) > x1 or \
           max(a.inicio[1], a.fim[1]) < y0 or min(a.inicio[1], a.fim[1]) > y1:
            continue
        La = math.dist(a.inicio, a.fim)
        if La < 200.0:
            continue
        def choca(p, q):
            d_, s, t, _c = _seg_seg(p, q, a.inicio, a.fim)
            return d_ < tol and longe_da_ponta < s * L < L - longe_da_ponta and longe_da_ponta < t * La < La - longe_da_ponta
        if choca(P, Q) and not choca(b.inicio, b.fim):
            return True
    return False


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
        pc = origem_de(a).get("peca")
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
        o = origem_de(b)
        return o.get("sigla") or (b.atributos or {}).get("sigla") or ""

    # A. a terça da calha
    subir = []
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
        subir.append((b, sobe_i, sobe_f, sobre, lo_b))
    por_dir: Dict[tuple, list] = collections.defaultdict(list)
    for c in tercas:
        if c.id in an["direcao"]:
            por_dir[an["direcao"][c.id]].append(c)
    # a linha de terça não muda de altura na emenda (17/10, o degrau de 133 mm na telha do Posto em x 34,06, junto da
    # TRANSIÇÃO 16): o pedaço da ponta da linha da calha subia 0,11 m sozinho e o resto da linha, sentado na transição
    # 0,16 m abaixo das duas águas (fora de qualquer água — sem amostras), ficava embaixo. Os pedaços emendados (a mesma
    # linha, as pontas juntas na mesma altura) andam com o pedaço mais comprido que sobe, na altura da ponta dele que fica
    # do lado deles — menos o que já está no plano da água e o que entraria noutra peça
    mov = {b.id: (b, si, sf, so, lo) for b, si, sf, so, lo in subir}
    for b, si, sf, so, lo in sorted(subir, key=lambda x: -math.dist(x[0].inicio[:2], x[0].fim[:2])):
        if mov.get(b.id, (None,))[0] is not b or mov[b.id][1:3] != (si, sf):
            continue                                         # já andou com um pedaço mais comprido
        d_ = an["direcao"].get(b.id)
        if d_ is None:
            continue
        n_ = (-d_[1], d_[0])
        tb = b.inicio[0] * n_[0] + b.inicio[1] * n_[1]
        fila = [(b, si, sf)]
        vistos_l = {b.id}
        while fila:
            a, ai, af = fila.pop()
            for c in por_dir[d_]:
                if c.id in vistos_l or abs(c.inicio[0] * n_[0] + c.inicio[1] * n_[1] - tb) > 30.0:
                    continue
                junta = None
                for P, sP in ((a.inicio, ai), (a.fim, af)):
                    for k_q, Q in enumerate((c.inicio, c.fim)):
                        if math.dist(P[:2], Q[:2]) <= 60.0 and abs(P[2] - Q[2]) <= 20.0:
                            junta, ponta_c = sP, k_q
                if junta is None:
                    continue
                if c.id not in mov and any(x == 0.0 for _s, x, _b in an["amostras"].get(c.id, ())):
                    continue                                 # o pedaço que já está no plano da água fica
                if c.id not in mov and _choca_ao_subir(c, junta, barras):
                    continue                                 # e o que entraria noutra peça (a tesoura de cima da TRANSIÇÃO 3)
                vistos_l.add(c.id)
                if c.id in mov and abs(mov[c.id][1 + ponta_c] - junta) <= 20.0:
                    fila.append(mov[c.id][:3])               # a subida dele já casa na emenda (a terça torta nivelada)
                    continue
                lo_c, _hi = _ext_z(c)
                so_c = mov[c.id][3] if c.id in mov else [p for p in _apoios_da_terca(c, apoios, grade, CEL)
                                                           if abs(c.inicio[2] + (c.fim[2] - c.inicio[2]) * p[0] + lo_c - p[1]) <= 20.0]
                mov[c.id] = (c, junta, junta, so_c, lo_c)
                fila.append((c, junta, junta))
    for b, sobe_i, sobe_f, sobre, lo_b in mov.values():
        b.inicio = (b.inicio[0], b.inicio[1], b.inicio[2] + sobe_i)
        b.fim = (b.fim[0], b.fim[1], b.fim[2] + sobe_f)
        maior = max(maior, sobe_i, sobe_f)
        calha.append({"sigla": sigla(b), "mm": round(max(sobe_i, sobe_f)), "sobre": sorted({p[2] for p in sobre}), "ponto": [round(c) for c in b.inicio]})
        bx, by = b.fim[0] - b.inicio[0], b.fim[1] - b.inicio[1]
        for t, za, nome, _barr, _cr, _pc in sobre:
            zf = b.inicio[2] + (b.fim[2] - b.inicio[2]) * t + lo_b
            if zf - za > folga_suporte:
                x, y = b.inicio[0] + bx * t, b.inicio[1] + by * t
                # as terças das duas águas (e a emenda) chegam no mesmo apoio do vale: um suporte só ali (12/10, o 3D
                # mostrou 2 a 4 L 3" no mesmo ponto da linha de x 10,06)
                ja = [k for k, (p0, _p1, _n) in enumerate(suportes) if math.hypot(x - p0[0], y - p0[1]) < 60.0 and abs(za - p0[2]) < 60.0]
                if ja:
                    p0, p1, n0 = suportes[ja[0]]
                    suportes[ja[0]] = (p0, (p1[0], p1[1], max(p1[2], zf)), n0)
                    continue
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
