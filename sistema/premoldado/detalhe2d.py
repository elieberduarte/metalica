# -*- coding: utf-8 -*-
"""O detalhamento 2D dos pilares pré-moldados (fôrma e armação) como um Desenho do CAD (nucleo2d.desenho:
mm no modelo, a escala só no que é de papel).

Para cada tipo de pilar, lado a lado:

* a fôrma em duas vistas — no plano do pórtico (largura h, com o consolo da ponte rolante para dentro do
  galpão) e no comprimento (largura b, com os consolos das vigas longitudinais) — com os níveis (base do
  pilar, boca do cálice, consolos, topo) e as cotas;
* a armação na vista do pórtico: as barras longitudinais (N1), os estribos (N2) no espaçamento, o
  cintamento do topo (N3, NBR 9062 6.2.3) e o corte A-A com as barras, o estribo e os suplementares (N4,
  NBR 6118 18.2.4);
* o quadro de ferros por pilar e o resumo por bitola (massa nominal da NBR 7480, sem perdas).

Os consolos entram na fôrma; a armação deles (tirante, costura, estribos) sai na memória de cálculo e o
desenho dela fica para o detalhe do consolo.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from nucleo.base import fmt
from nucleo2d.desenho import Cota, Desenho, Hachura, Linha, Polilinha, Texto, Circulo

from .concreto import BITOLAS, cobrimento
from .galpao import SUFIXO, ProjetoGalpaoPM, PilarDimensionado

ESCALA = 25.0                                  # 1:25
PAPEL = ESCALA                                 # 1 mm de papel em mm de modelo
TXT = 2.5                                      # altura dos textos (mm de papel)


def _ret(x0, y0, x1, y1, camada="CORTE", **atr) -> Polilinha:
    return Polilinha(camada=camada, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=atr)


def _texto(des: Desenho, x, y, s, altura=TXT, alin="esquerda", vert="base", camada="TEXTO", angulo=0.0):
    des.add(Texto(camada=camada, posicao=(x, y), texto=s, altura=altura, alinhamento=alin, vertical=vert, angulo=angulo))


def _cota(des: Desenho, p1, p2, modo, desloc, texto=None):
    des.add(Cota(modo=modo, p1=p1, p2=p2, deslocamento=desloc, texto=texto))


def _nivel(des: Desenho, x, z, rotulo):
    """a marca de nível: um traço horizontal com o valor em metros"""
    des.add(Linha(camada="AUXILIAR", a=(x, z), b=(x + 14 * PAPEL, z)))
    _texto(des, x + 15 * PAPEL, z, "%s %s" % (rotulo, ("+%s" % fmt(z / 1000.0, 2)) if z > 0.5 else ("±0,00" if abs(z) <= 0.5 else fmt(z / 1000.0, 2))),
           vert="meio")


# ------------------------------------------------------------------ as posições de aço

def _suplementares(n: int, comprimento: float, fi_t: float) -> int:
    """as barras intermediárias de uma face (n barras com os cantos, igualmente espaçadas em `comprimento`
    cm) que o estribo não protege (NBR 6118, 18.2.4): as que ficam a mais de 20φt do canto e as que passam
    de duas nesse trecho"""
    if n <= 2:
        return 0
    zona = 20.0 * fi_t / 10.0
    passo = comprimento / (n - 1)
    protegidas = 0
    for canto in (0, n - 1):
        perto = [k for k in range(1, n - 1) if abs(k - canto) * passo <= zona + 1e-9
                 and abs(k - canto) <= abs(k - (n - 1 - canto))]
        protegidas += min(len(perto), 2)
    return (n - 2) - protegidas


def posicoes(p: ProjetoGalpaoPM, pil: PilarDimensionado) -> List[dict]:
    """o quadro de ferros de um pilar: N, ø, quantidade, comprimento unitário (cm)"""
    d = p.dados
    c = cobrimento(d.caa, "pilar", pre_fabricado=True)
    arm = pil.armadura
    fi_t, s_t = pil.estribos
    L = pil.comprimento_total * 100.0
    out = [{"N": 1, "fi": arm.bitola, "qtd": arm.n_total, "comp": L - 2 * c, "desc": "longitudinal, reta"}]
    gancho = 2 * max(5 * fi_t / 10.0, 5.0)
    per = 2 * (pil.b - 2 * c - fi_t / 10.0) + 2 * (pil.h - 2 * c - fi_t / 10.0) + gancho
    n_est = math.floor((L - 2 * c) / s_t) + 1
    out.append({"N": 2, "fi": fi_t, "qtd": n_est, "comp": per, "desc": "estribo %s × %s, ganchos a 135° (9.4.6.1)" % (
        fmt(pil.b - 2 * c, 0), fmt(pil.h - 2 * c, 0))})
    cint = next((r for r in p.icamento if r.elemento.startswith("Cintamento") and r.dados.get("tipo_pilar") == pil.tipo), None)
    if cint is not None:
        fc = cint.dados["bitola"]
        per_c = 2 * (pil.b - 2 * c - fc / 10.0) + 2 * (pil.h - 2 * c - fc / 10.0) + 2 * max(5 * fc / 10.0, 5.0)
        out.append({"N": 3, "fi": fc, "qtd": int(cint.dados["estribos"]), "comp": per_c,
                    "desc": "cintamento do topo, em %s cm (NBR 9062, 6.2.3)" % fmt(cint.dados["h1"], 0)})
    # suplementares: nas faces com n_h barras (comprimento b − 2c) atravessando h, e nas com n_b + 2 barras
    k_h = _suplementares(arm.n_h, pil.b - 2 * c, fi_t)
    k_b = _suplementares(arm.n_b + 2, pil.h - 2 * c, fi_t)
    N = 4
    for k, vao_ in ((k_h, pil.h), (k_b, pil.b)):
        if k:
            out.append({"N": N, "fi": fi_t, "qtd": k * n_est, "comp": vao_ - 2 * c + gancho,
                        "desc": "estribo suplementar reto (18.2.4), %d por nível" % k})
            N += 1
    return out


def resumo_aco(pos: List[dict], multiplicador: int = 1) -> List[Tuple[float, float, float]]:
    """(ø, comprimento total m, massa kg) por bitola"""
    tot: Dict[float, float] = {}
    for q in pos:
        tot[q["fi"]] = tot.get(q["fi"], 0.0) + q["qtd"] * q["comp"] / 100.0 * multiplicador
    return [(fi, m, m * BITOLAS[fi][1]) for fi, m in sorted(tot.items())]


# ------------------------------------------------------------------ as vistas

def _forma_portico(des, p, pil, x0, z_base, H, Lemb):
    """a fôrma no plano do pórtico: largura h, o consolo da ponte rolante para dentro (à direita)"""
    d = p.dados
    h = pil.h * 10
    des.add(_ret(x0, z_base, x0 + h, H, peca="P-%s" % SUFIXO[pil.tipo]))
    xr = x0 + h
    if d.ponte_rolante and pil.tipo != "oitão":
        Hr = d.pr_altura * 1000
        hc = d.consolo_pr_altura * 10
        comp = (d.pr_excentricidade - pil.h / 2 + 20.0) * 10
        des.add(Polilinha(camada="CORTE", vertices=[(x0 + h, Hr - hc), (x0 + h + comp, Hr - hc), (x0 + h + comp, Hr), (x0 + h, Hr)], fechada=False))
        _cota(des, (x0 + h, Hr), (x0 + h + comp, Hr), "h", 8, None)
        _cota(des, (x0 + h + comp, Hr - hc), (x0 + h + comp, Hr), "v", -8, None)
        _nivel(des, x0 + h + comp + 20 * PAPEL, Hr, "consolo da ponte")
        xr = x0 + h + comp
    # boca do cálice e a hachura do trecho embutido
    des.add(Linha(camada="AUXILIAR", a=(x0 - 10 * PAPEL, 0.0), b=(x0 + h + 10 * PAPEL, 0.0)))
    des.add(Hachura(contornos=[[(x0, z_base), (x0 + h, z_base), (x0 + h, 0.0), (x0, 0.0)]], padrao="concreto", espacamento=4.0))
    _cota(des, (x0, H), (x0 + h, H), "h", 10)
    _cota(des, (x0, z_base), (x0, H), "v", 14)
    _cota(des, (x0, z_base), (x0, 0.0), "v", 7)
    _nivel(des, x0 - 45 * PAPEL, H, "topo")
    _nivel(des, x0 - 45 * PAPEL, 0.0, "boca do cálice")
    _nivel(des, x0 - 45 * PAPEL, z_base, "base do pilar")
    _texto(des, x0 + h / 2, z_base - 14 * PAPEL, "FÔRMA — PLANO DO PÓRTICO", 3.5, "centro")
    _texto(des, x0 + h / 2, z_base - 20 * PAPEL, "embutimento no cálice %s cm" % fmt(Lemb / 10, 0), TXT, "centro")
    return xr


def _forma_comprimento(des, p, pil, x0, z_base, H):
    """a fôrma no comprimento: largura b, os consolos das vigas longitudinais nos dois lados (um no canto)"""
    d = p.dados
    b = pil.b * 10
    des.add(_ret(x0, z_base, x0 + b, H))
    vl = next((v for v in p.vigas if v.funcao not in ("viga de cobertura", "terça")), None)
    if vl is not None and pil.tipo != "oitão":
        hv = vl.secao.h * 10
        z1 = H - hv - 10.0
        hc = d.consolo_altura * 10
        comp = 2 * d.consolo_a * 10
        lados = [1] if pil.tipo.startswith("canto") else [1, -1]
        for lado in lados:
            xa = x0 + b if lado > 0 else x0
            xb = xa + lado * comp
            des.add(Polilinha(camada="CORTE", vertices=[(xa, z1 - hc), (xb, z1 - hc), (xb, z1), (xa, z1)], fechada=False))
        _cota(des, (x0 + b, z1 - hc), (x0 + b, z1), "v", -(comp / PAPEL + 8))
        _cota(des, (x0 + b, z1), (x0 + b + comp, z1), "h", 6)
        _nivel(des, x0 + b + comp + 10 * PAPEL, z1, "apoio da %s" % vl.funcao)
    des.add(Linha(camada="AUXILIAR", a=(x0 - 10 * PAPEL, 0.0), b=(x0 + b + 10 * PAPEL, 0.0)))
    _cota(des, (x0, H), (x0 + b, H), "h", 10)
    _texto(des, x0 + b / 2, z_base - 14 * PAPEL, "FÔRMA — COMPRIMENTO", 3.5, "centro")


def _armacao(des, p, pil, x0, z_base, H, pos):
    """a armação na vista do pórtico: N1 nas posições das barras vistas de frente, N2 no espaçamento, N3 no topo"""
    d = p.dados
    c = cobrimento(d.caa, "pilar", pre_fabricado=True) * 10
    arm = pil.armadura
    fi_t, s_t = pil.estribos
    h = pil.h * 10
    des.add(_ret(x0, z_base, x0 + h, H, camada="VISTA-FINA"))
    cb = c + fi_t + arm.bitola / 2
    xs = [cb, h - cb] + [cb + k * (h - 2 * cb) / (arm.n_b + 1) for k in range(1, arm.n_b + 1)]
    for x in sorted(xs):
        des.add(Linha(camada="VISTA", a=(x0 + x, z_base + c), b=(x0 + x, H - c), atributos={"posicao": "N1"}))
    n_est = next(q for q in pos if q["N"] == 2)["qtd"]
    for k in range(n_est):
        z = z_base + c + k * s_t * 10
        if z > H - c + 1:
            break
        des.add(Linha(camada="FURO", a=(x0 + c, z), b=(x0 + h - c, z), atributos={"posicao": "N2"}))
    n3 = next((q for q in pos if q["N"] == 3), None)
    if n3:
        cint = next(r for r in p.icamento if r.elemento.startswith("Cintamento") and r.dados.get("tipo_pilar") == pil.tipo)
        h1 = cint.dados["h1"] * 10
        for k in range(n3["qtd"]):
            z = H - c - (k + 0.5) * (2.0 / 3.0 * h1) / n3["qtd"]
            des.add(Linha(camada="SOLDA", a=(x0 + c, z), b=(x0 + h - c, z), atributos={"posicao": "N3"}))
        _texto(des, x0 + h + 6 * PAPEL, H - h1 / 3, "N3 — %d ø%s (cintamento)" % (n3["qtd"], fmt(n3["fi"], 1)), vert="meio")
    q1 = pos[0]
    _texto(des, x0 + h + 6 * PAPEL, (z_base + H) / 2, "N1 — %d ø%s  c = %s" % (q1["qtd"], fmt(q1["fi"], 1), fmt(q1["comp"], 0)), vert="meio")
    _texto(des, x0 + h + 6 * PAPEL, (z_base + H) / 2 - 8 * PAPEL, "N2 — ø%s c/ %s" % (fmt(fi_t, 1), fmt(s_t, 1)), vert="meio")
    # o corte A-A na meia altura
    za = (z_base + H) / 2 + 20 * PAPEL
    des.add(Linha(camada="EIXO", a=(x0 - 8 * PAPEL, za), b=(x0 + h + 3 * PAPEL, za)))
    _texto(des, x0 - 9 * PAPEL, za, "A", 3.5, "direita", "meio")
    _texto(des, x0 + h / 2, z_base - 14 * PAPEL, "ARMAÇÃO", 3.5, "centro")


def _corte(des, p, pil, x0, y0, pos):
    """o corte A-A: h na horizontal, b na vertical, as barras, o estribo e os suplementares"""
    d = p.dados
    c = cobrimento(d.caa, "pilar", pre_fabricado=True) * 10
    arm = pil.armadura
    fi_t = pil.estribos[0]
    h, b = pil.h * 10, pil.b * 10
    des.add(_ret(x0, y0, x0 + h, y0 + b))
    des.add(Polilinha(camada="FURO", vertices=[(x0 + c + fi_t / 2, y0 + c + fi_t / 2), (x0 + h - c - fi_t / 2, y0 + c + fi_t / 2),
                                               (x0 + h - c - fi_t / 2, y0 + b - c - fi_t / 2), (x0 + c + fi_t / 2, y0 + b - c - fi_t / 2)], fechada=True))
    cb = c + fi_t + arm.bitola / 2
    r = arm.bitola / 2
    pts = []
    for x in (cb, h - cb):
        for i in range(arm.n_h):
            pts.append((x, cb + i * (b - 2 * cb) / max(arm.n_h - 1, 1)))
    for y in (cb, b - cb):
        for i in range(1, arm.n_b + 1):
            pts.append((cb + i * (h - 2 * cb) / (arm.n_b + 1), y))
    for x, y in pts:
        des.add(Circulo(camada="CORTE", centro=(x0 + x, y0 + y), raio=r))
        des.add(Hachura(contornos=[[(x0 + x + r * math.cos(t * math.pi / 8), y0 + y + r * math.sin(t * math.pi / 8)) for t in range(16)]], padrao="solido"))
    for q in pos:
        if q["N"] >= 4:
            _texto(des, x0, y0 - 12 * PAPEL, "N%d — suplementares (%s)" % (q["N"], q["desc"]), TXT)
    _cota(des, (x0, y0 + b), (x0 + h, y0 + b), "h", 8)
    _cota(des, (x0, y0), (x0, y0 + b), "v", 8)
    _texto(des, x0 + h / 2, y0 - 6 * PAPEL, "CORTE A-A", 3.5, "centro")


def _quadro(des, x0, y0, pil, pos, titulo):
    """o quadro de ferros (por pilar) e o resumo por bitola (do tipo inteiro)"""
    col = [0, 12, 26, 40, 62, 84]
    lin = 6.0 * PAPEL
    cab = ["N", "ø (mm)", "Qtd.", "Comp. (cm)", "Total (m)"]
    _texto(des, x0, y0 + 2 * PAPEL, titulo, 3.5)
    y = y0 - lin
    for k, t in enumerate(cab):
        _texto(des, x0 + col[k] * PAPEL, y, t, TXT)
    des.add(Linha(camada="VISTA-FINA", a=(x0, y - 2 * PAPEL), b=(x0 + col[-1] * PAPEL, y - 2 * PAPEL)))
    for q in pos:
        y -= lin
        for k, t in enumerate(["N%d" % q["N"], fmt(q["fi"], 1), str(q["qtd"]), fmt(q["comp"], 0), fmt(q["qtd"] * q["comp"] / 100.0, 2)]):
            _texto(des, x0 + col[k] * PAPEL, y, t, TXT)
    y -= 1.6 * lin
    _texto(des, x0, y, "Resumo — %d pilar%s" % (pil.quantidade, "es" if pil.quantidade > 1 else ""), 3.0)
    tot_kg = 0.0
    for fi, m, kg in resumo_aco(pos, pil.quantidade):
        y -= lin
        _texto(des, x0, y, "ø%s: %s m — %s kg" % (fmt(fi, 1), fmt(m, 1), fmt(kg, 1)), TXT)
        tot_kg += kg
    y -= lin
    _texto(des, x0, y, "Total: %s kg (massa nominal, sem perdas)" % fmt(tot_kg, 1), TXT)
    return tot_kg


def desenho(p: ProjetoGalpaoPM, nome: str = "Pilares pré-moldados") -> Desenho:
    d = p.dados
    des = Desenho(nome=nome, escala=ESCALA)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "detalhamento dos pilares (fôrma e armação)"})
    x0 = 0.0
    total = 0.0
    celulas = []                                  # uma célula por tipo de pilar: cada um cabe numa prancha
    for pil in p.pilares:
        x_ini = x0
        H = d.altura_tipo(pil.tipo) * 1000.0
        Lemb = (pil.comprimento_total - d.altura_tipo(pil.tipo)) * 1000.0
        z_base = -Lemb
        pos = posicoes(p, pil)
        marca = "P-%s" % SUFIXO[pil.tipo]
        _texto(des, x0, H + 30 * PAPEL, "%s — pilar %s %s × %s cm (%d un.), C%s, %s" % (
            marca, pil.tipo, fmt(pil.b, 0), fmt(pil.h, 0), pil.quantidade, fmt(d.fck, 0), d.aco), 5.0)
        _texto(des, x0, H + 22 * PAPEL, "cobrimento %s cm; comprimento %s m" % (
            fmt(cobrimento(d.caa, "pilar", True), 1), fmt(pil.comprimento_total, 2)), TXT)
        xa = x0 + 60 * PAPEL
        xr = _forma_portico(des, p, pil, xa, z_base, H, Lemb)
        xb = xr + 70 * PAPEL
        _forma_comprimento(des, p, pil, xb, z_base, H)
        vl = next((v for v in p.vigas if v.funcao != "viga de cobertura"), None)
        xc = xb + pil.b * 10 + (2 * d.consolo_a * 10 if vl else 0) + 90 * PAPEL
        _armacao(des, p, pil, xc, z_base, H, pos)
        xd = xc + pil.h * 10 + 70 * PAPEL
        _corte(des, p, pil, xd, (z_base + H) / 2, pos)
        total += _quadro(des, xd, (z_base + H) / 2 - 30 * PAPEL, pil, pos, "QUADRO DE FERROS — %s (por pilar)" % marca)
        x0 = xd + 110 * PAPEL
        celulas.append([x_ini - 5 * PAPEL, z_base - 80 * PAPEL, x0 - 20 * PAPEL, H + 40 * PAPEL])
    if len(celulas) > 1:
        des.metadados["celulas"] = celulas
    _texto(des, 0.0, -(max(q.comprimento_total for q in p.pilares) - d.altura_pilar) * 1000 - 40 * PAPEL,
           "Aço dos pilares: %s kg (os consolos e o cálice detalhados à parte)" % fmt(total, 0), 3.5)
    return des


# ------------------------------------------------------------------ a planta de locação dos pilares

ESCALA_PLANTA = 100.0


def planta_locacao(p: ProjetoGalpaoPM, nome: str = "Locação dos pilares") -> Desenho:
    """a planta de locação: os eixos (balões e cotas), cada pilar na posição real com a marca, a seção e o nível
    do topo, o cálice e a fundação em linha oculta, os pilares de oitão; o quadro dos pilares"""
    d = p.dados
    des = Desenho(nome=nome, escala=ESCALA_PLANTA)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "planta de locação dos pilares"})
    K = ESCALA_PLANTA
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v * 1000.0)
    ys = [0.0, d.vao * 1000.0]
    por_tipo = {q.tipo: q for q in p.pilares}
    cal = {}
    for r in p.calices:
        if r.dados.get("direcao") == "x":
            cal[r.dados.get("tipo_pilar") or next(t for t in ("canto", "oitão", "intermediário") if t in r.elemento)] = r
    fund = {r.dados.get("tipo_pilar"): r for r in p.fundacoes if "ah" in r.dados}
    folga = 25 * K
    # eixos
    for i, x in enumerate(xs):
        des.add(Linha(camada="EIXO", a=(x, ys[0] - folga), b=(x, ys[-1] + folga)))
        for y, s in ((ys[0] - folga, -1), (ys[-1] + folga, 1)):
            des.add(Circulo(camada="EIXO", centro=(x, y + s * 5 * K), raio=4 * K))
            _texto(des, x, y + s * 5 * K, str(i + 1), 3.5, "centro", "meio")
    for j, y in enumerate(ys):
        des.add(Linha(camada="EIXO", a=(xs[0] - folga, y), b=(xs[-1] + folga, y)))
        for x, s in ((xs[0] - folga, -1), (xs[-1] + folga, 1)):
            des.add(Circulo(camada="EIXO", centro=(x + s * 5 * K, y), raio=4 * K))
            _texto(des, x + s * 5 * K, y, "AB"[j], 3.5, "centro", "meio")
    for a, b in zip(xs, xs[1:]):
        _cota(des, (a, ys[0] - folga), (b, ys[0] - folga), "h", -14)
    _cota(des, (xs[0], ys[0] - folga), (xs[-1], ys[0] - folga), "h", -24)
    _cota(des, (xs[0] - folga, ys[0]), (xs[0] - folga, ys[-1]), "v", 14)
    # os pilares
    posicoes = [(i, x, y, ("canto" if i in (0, len(xs) - 1) else "intermediário") + (" B" if j == 1 and d.filas_diferentes else ""))
                for i, x in enumerate(xs) for j, y in enumerate(ys)]
    posicoes += [(int(e) - 1, xs[int(e) - 1], yy * 1000.0, "oitão") for e, yy in (d.pilares_oitao or []) if 1 <= int(e) <= len(xs)]
    for i, x, y, tipo in posicoes:
        pil = por_tipo.get(tipo)
        if pil is None:
            continue
        b, h = pil.b * 10, pil.h * 10
        if tipo in fund:
            dd = fund[tipo].dados
            ab, ah = dd["ab"] * 10, dd["ah"] * 10
            des.add(Polilinha(camada="OCULTA", vertices=[(x - ab / 2, y - ah / 2), (x + ab / 2, y - ah / 2), (x + ab / 2, y + ah / 2), (x - ab / 2, y + ah / 2)],
                              fechada=True, atributos={"peca": "%s-%s" % ("SP" if dd["tipo"] == "sapata" else "BL", SUFIXO[tipo])}))
            if dd["tipo"] == "estacas":
                for (ph, pb) in dd["estacas"]:
                    des.add(Circulo(camada="OCULTA", centro=(x + pb * 10, y + ph * 10), raio=dd["estaca_diametro"] * 5))
        if tipo in cal:
            eb, eh = cal[tipo].dados["externo"]
            des.add(Polilinha(camada="VISTA-FINA", vertices=[(x - eb * 5, y - eh * 5), (x + eb * 5, y - eh * 5), (x + eb * 5, y + eh * 5), (x - eb * 5, y + eh * 5)],
                              fechada=True, atributos={"peca": "CL-%s" % SUFIXO[tipo]}))
        des.add(_ret(x - b / 2, y - h / 2, x + b / 2, y + h / 2, peca="P-%s" % SUFIXO[tipo], eixo="%d" % (i + 1)))
        des.add(Hachura(contornos=[[(x - b / 2, y - h / 2), (x + b / 2, y - h / 2), (x + b / 2, y + h / 2), (x - b / 2, y + h / 2)]], padrao="solido"))
        _texto(des, x + b / 2 + 2 * K, y + h / 2 + 1 * K, "P-%s" % SUFIXO[tipo], 2.5)
        _texto(des, x + b / 2 + 2 * K, y + h / 2 - 3 * K, "%s×%s" % (fmt(pil.b, 0), fmt(pil.h, 0)), 2.0)
    # cotas de posição dos pilares de oitão (à fila A)
    for e, yy in (d.pilares_oitao or []):
        k = int(e) - 1
        if 0 <= k < len(xs):
            _cota(des, (xs[k], ys[0]), (xs[k], yy * 1000.0), "v", 12 if k == 0 else -12)
    # o quadro
    x0, y0 = xs[0], ys[-1] + folga + 22 * K
    _texto(des, x0, y0 + 6 * K, "LOCAÇÃO DOS PILARES — %s (topo dos pilares +%s m%s; boca do cálice ±0,00)" % (
        d.nome, fmt(d.altura_pilar, 2), " na fila A e +%s m na fila B" % fmt(d.altura_b, 2) if d.filas_diferentes else ""), 4.0)
    lin = 5 * K
    y = y0
    cols = [0, 14, 30, 38, 58, 80]
    for k, t in enumerate(["Marca", "Seção (cm)", "Qtd.", "Comprimento (m)", "Cálice (cm)", "Fundação"]):
        _texto(des, x0 + cols[k] * K, y, t, 2.5)
    for pil in p.pilares:
        y -= lin
        c = cal.get(pil.tipo)
        f = fund.get(pil.tipo)
        vals = ["P-%s" % SUFIXO[pil.tipo], "%s × %s" % (fmt(pil.b, 0), fmt(pil.h, 0)), str(pil.quantidade), fmt(pil.comprimento_total, 2),
                "%s × %s, emb. %s" % (fmt(c.dados["externo"][0], 0), fmt(c.dados["externo"][1], 0), fmt(c.dados["Lemb_adotado"], 0)) if c else "—",
                f.perfil if f else "—"]
        for k, t in enumerate(vals):
            _texto(des, x0 + cols[k] * K, y, t, 2.5)
    return des
