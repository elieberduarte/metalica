# -*- coding: utf-8 -*-
"""A passarela de manutenção pela planta dela (Posto CB, folha 14 "PLANTA DA PASSARELA", 23/10/2026; o jeito aprovado
pelo usuário: "é assim"; os pórticos "em balanço").

O que a planta desenha, em tamanho real: o piso (a hachura do contorno, a chapa expandida), as travessas U100 (os
retângulos finos de ~1.100 entre as longarinas), as seções dos pilaretes (40 × 100) com a chapa de apoio deles (100 ×
100, o CH9) e as vigas dos pórticos (os retângulos de ~1.200 que saem da estrutura ao lado). No 3D, com o nível do piso
que o corte dá (+7,60): o piso por cima de tudo; as longarinas U100 no contorno; as travessas; cada pilarete do CH9 até
a longarina, o CH9 em cima da telha (as terças embaixo + a altura da telha, com a borracha); o guarda-corpo nas bordas
soltas (as que não encostam na estrutura): montantes em tubo quadrado a no máximo 1,5 m e três tubos redondos; e cada
pórtico — a viga 2U em balanço saindo da estrutura e a mão-francesa por baixo (o detalhe "PORTICO 1": 1.200, 806, 700).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

PERFIL = "U 100×40×2,65 (FF)"
PERFIL_MONTANTE = "TQ 40×40×2,0"
PERFIL_TUBO = "TC 31,75×1,5"
ESPESSURA_PISO = 6.35                       # chapa expandida #1/4"
ESPESSURA_CH9 = 4.76                        # #3/16"
BORRACHA = 5.0                              # mm entre a telha e o CH9
ALTURA_TELHA = 40.0                         # TR40
GUARDA_CORPO = 1120.0
TUBOS = (504.0, 804.0, 1104.0)              # a altura de cada tubo acima do piso (504 + 300 + 300; 16 do topo)
MONTANTE_MAX = 1500.0
PORTICO = {"viga": 1200.0, "mao": 806.0, "horizontal": 700.0}


def _caixa(vs):
    xs, ys = [v[0] for v in vs], [v[1] for v in vs]
    return min(xs), min(ys), max(xs), max(ys)


def _ret(e) -> Optional[Tuple[float, float, float, float]]:
    vs = e.get("vertices") or []
    if e.get("tipo") != "polilinha" or not e.get("fechada") or len(vs) not in (4, 5):
        return None
    return _caixa(vs)


def ler(ents: Sequence[dict], caixa: Tuple[float, float, float, float]) -> Optional[dict]:
    """O que a planta da passarela (dentro de `caixa`) desenha: {piso: [(x, y)], travessas: [((x, y), (x, y))],
    pilaretes: [(x, y)], porticos: [((x, y), (x, y))]} em coordenadas do desenho"""
    x0, y0, x1, y1 = caixa

    def dentro(p):
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1
    # o piso: a hachura com mais chapas de pilarete (100 × 100) em volta — o bloco do título pega também os cortes, com
    # a hachura do terreno
    quadradas = []
    for e in ents:
        r = _ret(e)
        if r and 90.0 <= r[2] - r[0] <= 110.0 and 90.0 <= r[3] - r[1] <= 110.0 and dentro((r[0], r[1])):
            quadradas.append(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2))
    piso = None
    for e in ents:
        if e.get("tipo") != "hachura":
            continue
        for c in e.get("contornos") or []:
            if len(c) >= 4 and all(dentro(v) for v in c):
                a, b, c_, d = _caixa(c)
                nq = sum(1 for q in quadradas if a - 300 <= q[0] <= c_ + 300 and b - 300 <= q[1] <= d + 300)
                if nq and (piso is None or nq > piso[0]):
                    piso = (nq, [(v[0], v[1]) for v in c])
    if piso is None:
        return None
    contorno = piso[1]
    if len(contorno) > 3 and math.dist(contorno[0], contorno[-1]) < 1.0:
        contorno = contorno[:-1]
    pa, pb, pc, pd = _caixa(contorno)
    travessas, pilaretes, chapas, porticos = [], [], [], []
    for e in ents:
        r = _ret(e)
        if r is None or not (pa - 200 <= r[0] and r[2] <= pc + 200 and pb - 200 <= r[1] and r[3] <= pd + 200):
            continue
        w, h = r[2] - r[0], r[3] - r[1]
        fino, longo = min(w, h), max(w, h)
        meio = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        if 30.0 <= fino <= 50.0 and 900.0 <= longo <= 1150.0:
            # a travessa (U100 visto de cima: 40 de largura)
            if w > h:
                travessas.append(((r[0], meio[1]), (r[2], meio[1])))
            else:
                travessas.append(((meio[0], r[1]), (meio[0], r[3])))
        elif 30.0 <= fino <= 50.0 and 90.0 <= longo <= 110.0:
            pilaretes.append(meio)
        elif 90.0 <= fino <= 110.0 and 90.0 <= longo <= 110.0:
            chapas.append(meio)
        elif 60.0 <= fino <= 110.0 and 1150.0 <= longo <= 1350.0:
            if w > h:
                porticos.append(((r[0], meio[1]), (r[2], meio[1])))
            else:
                porticos.append(((meio[0], r[1]), (meio[0], r[3])))
    # o pilarete é o que tem o CH9 embaixo; um por chapa
    ps = []
    for c in chapas:
        if any(math.dist(c, q) < 60.0 for q in ps):
            continue
        if any(math.dist(c, p) < 80.0 for p in pilaretes):
            ps.append(c)
    # pórtico: um por linha (o retângulo desenhado duas vezes)
    pos = []
    for a, b in porticos:
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if not any(math.dist(m, ((q[0][0] + q[1][0]) / 2, (q[0][1] + q[1][1]) / 2)) < 150.0 for q in pos):
            pos.append((a, b))
    return {"piso": contorno, "travessas": travessas, "pilaretes": ps, "porticos": pos}


def _retangulos(cont: Sequence[Tuple[float, float]]) -> List[Tuple[float, float, float, float]]:
    """o contorno ortogonal do piso em retângulos (x0, y0, x1, y1): faixas entre os y dos vértices, juntadas na vertical
    quando o trecho em x é o mesmo — o piso em U do Posto saía uma chapa só do tamanho da caixa (9 × 57 m, 25,5 t na
    lista de materiais, que conta a chapa pelo retângulo de corte; 23/10/2026)"""
    ys = sorted({round(p[1], 1) for p in cont})
    n = len(cont)
    faixas = []
    for ya, yb in zip(ys, ys[1:]):
        ym = (ya + yb) / 2.0
        xs = []
        for i in range(n):
            (x1, y1), (x2, y2) = cont[i], cont[(i + 1) % n]
            if (y1 > ym) != (y2 > ym):
                xs.append(x1 + (ym - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            faixas.append([xs[k], ya, xs[k + 1], yb])
    # junta as faixas de cima com o mesmo trecho em x
    out: List[list] = []
    for f in sorted(faixas, key=lambda f: (round(f[0]), round(f[2]), f[1])):
        if out and abs(out[-1][0] - f[0]) < 1.0 and abs(out[-1][2] - f[2]) < 1.0 and abs(out[-1][3] - f[1]) < 1.0:
            out[-1][3] = f[3]
        else:
            out.append(list(f))
    return [tuple(r) for r in out]


def _no_segmento(p, a, b) -> Tuple[float, float]:
    ux, uy = b[0] - a[0], b[1] - a[1]
    L2 = ux * ux + uy * uy or 1.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / L2))
    return math.hypot(p[0] - a[0] - ux * t, p[1] - a[1] - uy * t), t


def _z_telha(p, tercas) -> Optional[float]:
    """o topo da telha em p: a reta pelas duas terças mais perto, uma de cada lado (o topo delas + a telha)"""
    from nucleo3d.de_planta import _perfil
    lados: Dict[int, tuple] = {}
    for t in tercas:
        d, f = _no_segmento(p, t.inicio, t.fim)
        if d > 2500.0 or f <= 0.0 or f >= 1.0:
            continue
        a, b = t.inicio, t.fim
        q = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f)
        ux, uy = b[0] - a[0], b[1] - a[1]
        lado = 1 if (p[0] - a[0]) * uy - (p[1] - a[1]) * ux > 0 else -1
        pf = _perfil(t.perfil)
        topo = q[2] + (float(pf.d) / 2.0 if pf is not None and pf.d else 50.0)
        if lado not in lados or d < lados[lado][0]:
            lados[lado] = (d, topo)
    if not lados:
        return None
    if len(lados) == 1:
        return list(lados.values())[0][1] + ALTURA_TELHA
    (d1, z1), (d2, z2) = lados[1], lados[-1]
    return z1 + (z2 - z1) * d1 / (d1 + d2) + ALTURA_TELHA


def lancar(doc, lido: dict, mover, nivel: float, estrutura: Sequence, tercas: Sequence, barra, aco: str,
           chapas_postas: list, avisos: List[str]) -> dict:
    """monta a passarela lida (`mover` leva o desenho à planta; `nivel` o topo do piso); `estrutura`: as barras em que
    a borda encosta (sem guarda-corpo ali) e de onde saem os pórticos"""
    from nucleo3d.modelo import Chapa
    from nucleo3d.de_planta import _perfil
    pu = _perfil(PERFIL)
    d_u = float(pu.d) if pu is not None else 100.0
    z_topo_u = nivel - ESPESSURA_PISO
    z_eixo_u = z_topo_u - d_u / 2.0
    o = {"locacao": "PASSARELA", "planta": "PLANTA DA PASSARELA"}
    cont = [mover(p) for p in lido["piso"]]
    n = {"longarinas": 0, "travessas": 0, "pilaretes": 0, "ch9": 0, "montantes": 0, "tubos": 0, "porticos": 0}
    # o piso (a chapa expandida), por cima das longarinas: um painel por retângulo do contorno
    n["paineis_piso"] = 0
    for x0_, y0_, x1_, y1_ in _retangulos(cont):
        piso = Chapa(nome="Piso da passarela (chapa expandida #1/4\")", origem=(x0_, y0_, z_topo_u), eixo_x=(1.0, 0.0, 0.0),
                     eixo_y=(0.0, 1.0, 0.0), contorno=[(0.0, 0.0), (x1_ - x0_, 0.0), (x1_ - x0_, y1_ - y0_), (0.0, y1_ - y0_)],
                     espessura=ESPESSURA_PISO, centrada=False, aco=aco)
        piso.camada = "Passarela"
        piso.atributos = {"tipo_ifc": "IfcPlate", "origem": dict(o, piso="chapa expandida #1/4\"",
                                                                 a_conferir="chapa expandida: o peso é o da tabela do fabricante "
                                                                            "(~11 kg/m²), não o da chapa cheia")}
        doc.add(piso)
        chapas_postas.append(piso)
        n["paineis_piso"] += 1
    # as bordas: a longarina em cada lado do contorno, 20 mm para dentro (a aba de 40); guarda-corpo onde a borda está solta
    area2 = sum(cont[i][0] * cont[(i + 1) % len(cont)][1] - cont[(i + 1) % len(cont)][0] * cont[i][1] for i in range(len(cont)))
    sentido = 1.0 if area2 > 0 else -1.0                   # o lado de dentro do contorno
    bordas_soltas = []
    for i in range(len(cont)):
        a, b = cont[i], cont[(i + 1) % len(cont)]
        L = math.dist(a, b)
        if L < 100.0:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy * sentido, ux * sentido                 # a normal para dentro
        a_i = (a[0] + nx * 20.0, a[1] + ny * 20.0)
        b_i = (b[0] + nx * 20.0, b[1] + ny * 20.0)
        if barra((a_i[0], a_i[1], z_eixo_u), (b_i[0], b_i[1], z_eixo_u), PERFIL, "viga", "Passarela", None, 0.0,
                 dict(o, peca="longarina")):
            n["longarinas"] += 1
        # encostada na estrutura (o painel): a borda a menos de 200 mm em planta de uma barra dela, ao longo
        meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        encostada = any(_no_segmento(meio, e.inicio, e.fim)[0] < 200.0 and abs(e.inicio[2] - nivel) < 2500.0 for e in estrutura)
        if not encostada:
            bordas_soltas.append((a_i, b_i, (nx, ny)))
    for a, b in lido["travessas"]:
        a, b = mover(a), mover(b)
        if barra((a[0], a[1], z_eixo_u), (b[0], b[1], z_eixo_u), PERFIL, "viga", "Passarela", None, 0.0, dict(o, peca="travessa")):
            n["travessas"] += 1
    # os pilaretes: do CH9 (em cima da telha, com a borracha) até o fundo da longarina
    sem_telha = 0
    for p in lido["pilaretes"]:
        q = mover(p)
        z_t = _z_telha(q, tercas)
        if z_t is None:
            sem_telha += 1
            continue
        z_ch = z_t + BORRACHA
        z_pe = z_ch + ESPESSURA_CH9
        z_cima = z_topo_u - d_u
        if z_cima - z_pe < 20.0:
            continue
        if barra((q[0], q[1], z_pe), (q[0], q[1], z_cima), PERFIL, "pilar", "Passarela", None, 0.0,
                 dict(o, peca="pilarete", a_conferir="pilarete pela telha (as terças + %.0f) e a borracha" % ALTURA_TELHA)):
            n["pilaretes"] += 1
        ch = Chapa(nome="CH9 (passarela)", origem=(q[0] - 50.0, q[1] - 50.0, z_ch), eixo_x=(1.0, 0.0, 0.0),
                   eixo_y=(0.0, 1.0, 0.0), contorno=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
                   espessura=ESPESSURA_CH9, centrada=False, aco=aco)
        ch.camada = "Passarela"
        ch.atributos = {"tipo_ifc": "IfcPlate", "origem": dict(o, locacao="CH9", placa="CH9")}
        doc.add(ch)
        chapas_postas.append(ch)
        n["ch9"] += 1
    # o guarda-corpo nas bordas soltas
    for a, b, (nx, ny) in bordas_soltas:
        L = math.dist(a, b)
        k = max(1, int(math.ceil(L / MONTANTE_MAX)))
        for j in range(k + 1):
            f = j / k
            q = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            if barra((q[0], q[1], nivel), (q[0], q[1], nivel + GUARDA_CORPO), PERFIL_MONTANTE, "montante", "Passarela",
                     None, 0.0, dict(o, peca="guarda-corpo")):
                n["montantes"] += 1
        for h in TUBOS:
            if barra((a[0], a[1], nivel + h), (b[0], b[1], nivel + h), PERFIL_TUBO, "corrimao", "Passarela", None, 0.0,
                     dict(o, peca="guarda-corpo", a_conferir="o projeto diz tubo Ø32×1,5: o 1¼\" do catálogo")):
                n["tubos"] += 1
    # os pórticos: a viga 2U em balanço saindo da estrutura (a ponta mais perto dela) e a mão-francesa por baixo
    for a, b in lido["porticos"]:
        a, b = mover(a), mover(b)

        def perto(p):
            return min((_no_segmento(p, e.inicio, e.fim)[0] for e in estrutura), default=1e9)
        if perto(a) > perto(b):
            a, b = b, a                                       # a: o lado da estrutura
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        z_v = z_eixo_u - d_u                                  # embaixo das travessas
        for s in (1.0, -1.0):                                 # 2U: um de cada lado da linha, costas com costas
            off = (-uy * 22.0 * s, ux * 22.0 * s)
            barra((a[0] + off[0], a[1] + off[1], z_v), (b[0] + off[0], b[1] + off[1], z_v), PERFIL, "viga", "Passarela",
                  None, 180.0 if s > 0 else 0.0, dict(o, peca="PÓRTICO 1 (viga)"))
            dz = math.sqrt(max(PORTICO["mao"] ** 2 - PORTICO["horizontal"] ** 2, 0.0))
            barra((a[0] + off[0], a[1] + off[1], z_v - dz),
                  (a[0] + ux * PORTICO["horizontal"] + off[0], a[1] + uy * PORTICO["horizontal"] + off[1], z_v), PERFIL,
                  "diagonal", "Passarela", None, 180.0 if s > 0 else 0.0, dict(o, peca="PÓRTICO 1 (mão-francesa)"))
        n["porticos"] += 1
    if sem_telha:
        avisos.append("Passarela: %d pilarete(s) sem terça embaixo (não dá para saber a altura da telha) — ficaram de fora."
                      % sem_telha)
    return n
