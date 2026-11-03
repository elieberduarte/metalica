# -*- coding: utf-8 -*-
"""A planta de locação dos pilares do galpão pré-moldado, como um Desenho do CAD (nucleo2d.desenho: mm no
modelo, a escala só no que é de papel).

O mesmo arranjo do modelo 3D (premoldado.modelo3d): os pórticos numerados ao longo de X (eixos 1, 2, …) e as
duas filas de pilares A e B no vão (Y); cada pilar centrado no cruzamento dos eixos, b na direção do
comprimento e h na direção do vão. Na planta:

* os eixos com as bolinhas nas duas pontas, a cadeia de cotas entre eixos com a total e o vão A–B;
* cada pilar em corte (hachurado) com a marca (P-C no canto, P-I no meio) e o eixo dele ("1/A");
* o contorno do cálice e, quando há, o da sapata ou do bloco, tracejados;
* a seção de um pilar de cada tipo cotada, com a distância da face ao eixo (é o que a obra marca no gabarito);
* o quadro dos pilares: marca, seção, quantidade, comprimento da peça, cálice, fundação e os eixos.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from nucleo.base import fmt
from nucleo2d.desenho import Circulo, Cota, Desenho, Hachura, Linha, Polilinha, Texto

from .galpao import ProjetoGalpaoPM, SUFIXO, tipos_de_pilar

ESCALA = 100.0                                 # 1:100
PAPEL = ESCALA                                 # 1 mm de papel em mm de modelo
TXT = 2.5                                      # altura dos textos (mm de papel)
RAIO_BOLINHA = 4.0                             # mm de papel
AVANCO_EIXO = 22.0                             # quanto o eixo passa do último pilar (mm de papel)


def _texto(des: Desenho, x, y, s, altura=TXT, alin="esquerda", vert="base", camada="TEXTO", **atr):
    des.add(Texto(camada=camada, posicao=(x, y), texto=s, altura=altura, alinhamento=alin, vertical=vert, atributos=atr))


def _ret(x0, y0, x1, y1, camada, **atr) -> Polilinha:
    return Polilinha(camada=camada, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=atr)


def _bolinha(des: Desenho, x, y, nome):
    des.add(Circulo(camada="EIXO", centro=(x, y), raio=RAIO_BOLINHA * PAPEL, atributos={"eixo": nome}))
    _texto(des, x, y, nome, 3.5, "centro", "meio", camada="EIXO", eixo=nome)


def eixos_do_galpao(p: ProjetoGalpaoPM):
    """(xs, ys) dos eixos em mm: os pórticos ao longo de X e as filas A e B no vão"""
    d = p.dados
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v * 1000.0)
    return xs, [0.0, d.vao * 1000.0]


def _contornos_de_baixo(p: ProjetoGalpaoPM) -> Dict[str, dict]:
    """por tipo de pilar: o cálice (externo b × h, cm) e a fundação (ab × ah, cm, e o tipo), como o 3D os põe"""
    fora: Dict[str, dict] = {}
    for r in p.calices:
        if r.dados.get("direcao") == "x" and "externo" in r.dados:
            t = r.dados.get("tipo_pilar") or next((t_ for t_ in ("canto", "oitão", "intermediário") if t_ in r.elemento), "intermediário")
            fora.setdefault(t, {})["calice"] = tuple(r.dados["externo"])
    for r in p.fundacoes:
        dd = r.dados
        if "ah" in dd and dd.get("tipo_pilar"):
            fora.setdefault(dd["tipo_pilar"], {})["fundacao"] = (dd["ab"], dd["ah"], dd.get("tipo", "sapata"))
    return fora


def desenho(p: ProjetoGalpaoPM, nome: str = "Locação dos pilares") -> Desenho:
    d = p.dados
    des = Desenho(nome=nome, escala=ESCALA)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "planta de locação dos pilares"})
    xs, ys = eixos_do_galpao(p)
    por_tipo = {q.tipo: q for q in p.pilares}
    de_baixo = _contornos_de_baixo(p)
    marca_de = lambda t: "P-%s" % SUFIXO.get(t, "I")                                 # noqa: E731
    pos = posicoes_dos_pilares(p)

    # o que passa do eixo para fora (a sapata é o maior): os eixos e as cotas ficam além disso
    meia_x = meia_y = 0.0
    for t, pil in por_tipo.items():
        meia_x, meia_y = max(meia_x, pil.b * 5), max(meia_y, pil.h * 5)
        cb = de_baixo.get(t, {})
        for chave in ("calice", "fundacao"):
            if chave in cb:
                meia_x, meia_y = max(meia_x, cb[chave][0] * 5), max(meia_y, cb[chave][1] * 5)
    av = AVANCO_EIXO * PAPEL
    x_ini, x_fim = xs[0] - meia_x - av, xs[-1] + meia_x + av
    y_ini, y_fim = ys[0] - meia_y - av, ys[-1] + meia_y + av

    # os eixos, com as bolinhas nas duas pontas
    rb = RAIO_BOLINHA * PAPEL
    for i, x in enumerate(xs):
        des.add(Linha(camada="EIXO", a=(x, y_ini), b=(x, y_fim), atributos={"eixo": str(i + 1)}))
        _bolinha(des, x, y_ini - rb, str(i + 1))
        _bolinha(des, x, y_fim + rb, str(i + 1))
    for j, y in enumerate(ys):
        nome_e = "AB"[j]
        des.add(Linha(camada="EIXO", a=(x_ini, y), b=(x_fim, y), atributos={"eixo": nome_e}))
        _bolinha(des, x_ini - rb, y, nome_e)
        _bolinha(des, x_fim + rb, y, nome_e)

    # os pilares em corte, o cálice e a fundação tracejados, a marca e o eixo de cada um
    for q in pos:
        t, x, y, eixo = q["tipo"], q["x"], q["y"], q["eixo"]
        pil = por_tipo[t]
        b2, h2 = pil.b * 5, pil.h * 5
        atr = {"peca": marca_de(t), "eixo": eixo, "pre_moldado": True}
        o = (getattr(d, "origem_planta", None) or {}).get(eixo)
        if o:
            atr["origem_2d"] = o["id"]                  # o elemento da planta de lançamento (R5)
        des.add(_ret(x - b2, y - h2, x + b2, y + h2, "CORTE", **atr))
        des.add(Hachura(contornos=[[(x - b2, y - h2), (x + b2, y - h2), (x + b2, y + h2), (x - b2, y + h2)]],
                        padrao="concreto", espacamento=2.0, atributos=dict(atr)))
        cb = de_baixo.get(t, {})
        if "calice" in cb:
            cx2, cy2 = cb["calice"][0] * 5, cb["calice"][1] * 5
            des.add(_ret(x - cx2, y - cy2, x + cx2, y + cy2, "OCULTA", peca="CL-%s" % SUFIXO.get(t, "I"), eixo=eixo))
        if "fundacao" in cb:
            fx2, fy2 = cb["fundacao"][0] * 5, cb["fundacao"][1] * 5
            pref = "SP" if cb["fundacao"][2] == "sapata" else "BL"
            des.add(_ret(x - fx2, y - fy2, x + fx2, y + fy2, "OCULTA", peca="%s-%s" % (pref, SUFIXO.get(t, "I")), eixo=eixo))
        if q["fila"] is not None:
            # a marca do lado de dentro do galpão (fora ficam as cotas)
            dentro = 1.0 if q["fila"] == 0 else -1.0
            yt = y + dentro * (max(h2, meia_y) + 4 * PAPEL)
            _texto(des, x, yt, marca_de(t), 3.0, "centro", "base" if dentro > 0 else "topo", peca=marca_de(t), eixo=eixo)
            _texto(des, x, yt + dentro * 4.5 * PAPEL, eixo, 2.0, "centro", "base" if dentro > 0 else "topo", eixo=eixo)
        else:
            # o pilar de oitão: a marca para dentro do galpão, ao lado dele
            lado = 1.0 if q["i"] == 0 else -1.0
            xt = x + lado * (max(b2, meia_x) + 4 * PAPEL)
            _texto(des, xt, y + 1.0 * PAPEL, marca_de(t), 3.0, "esquerda" if lado > 0 else "direita", peca=marca_de(t), eixo=eixo)
            _texto(des, xt, y - 1.0 * PAPEL, eixo, 2.0, "esquerda" if lado > 0 else "direita", "topo", eixo=eixo)

    # as cotas: a cadeia entre eixos (embaixo e em cima) com a total, e o vão A–B dos dois lados
    y_cad = y_ini - 2 * rb - 6 * PAPEL
    for k in range(len(xs) - 1):
        des.add(Cota(modo="h", p1=(xs[k], y_cad), p2=(xs[k + 1], y_cad), deslocamento=0.0))
    if len(xs) > 2:
        des.add(Cota(modo="h", p1=(xs[0], y_cad), p2=(xs[-1], y_cad), deslocamento=-8.0))
    y_cad2 = y_fim + 2 * rb + 6 * PAPEL
    for k in range(len(xs) - 1):
        des.add(Cota(modo="h", p1=(xs[k], y_cad2), p2=(xs[k + 1], y_cad2), deslocamento=0.0))
    x_cad = x_ini - 2 * rb - 6 * PAPEL
    des.add(Cota(modo="v", p1=(x_cad, ys[0]), p2=(x_cad, ys[-1]), deslocamento=0.0))
    x_cad2 = x_fim + 2 * rb + 6 * PAPEL
    des.add(Cota(modo="v", p1=(x_cad2, ys[0]), p2=(x_cad2, ys[-1]), deslocamento=0.0))
    # os pilares de oitão: a cadeia da fila A até a B passando por eles, do lado de fora do oitão
    for i_o, x_c in ((0, x_cad), (len(xs) - 1, x_cad2)):
        yy = sorted({q["y"] for q in pos if q["fila"] is None and q["i"] == i_o})
        if not yy:
            continue
        cad = [ys[0]] + yy + [ys[-1]]
        lado = -1.0 if i_o == 0 else 1.0
        for a_, b_ in zip(cad, cad[1:]):
            des.add(Cota(modo="v", p1=(x_c, a_), p2=(x_c, b_), deslocamento=-lado * 8.0))

    # o título e as notas, embaixo
    y_tit = y_cad - 22 * PAPEL
    _texto(des, x_ini, y_tit, "PLANTA DE LOCAÇÃO DOS PILARES", 5.0)
    _texto(des, x_ini, y_tit - 7 * PAPEL, "ESC. 1:%d  ·  cotas em mm  ·  eixos no centro dos pilares  ·  b na direção do "
           "comprimento, h na direção do vão" % ESCALA, TXT)
    _texto(des, x_ini, y_tit - 12 * PAPEL, "tracejado: cálice%s  ·  boca do cálice no nível ±0,00" % (
        " e %s" % ("sapata" if d.fundacao == "sapata" else "bloco sobre estacas") if d.fundacao in ("sapata", "estacas") else ""), TXT)

    # o quadro dos pilares embaixo do título e, à direita dele, o detalhe de locação de cada tipo
    linhas = _linhas_do_quadro(p, pos, marca_de, de_baixo)
    x_q1 = _quadro(des, x_ini, y_tit - 22 * PAPEL, linhas)
    x_det = max(x_q1 + 20 * PAPEL, x_ini + 250 * PAPEL)
    for t in tipos_de_pilar(d) + ["oitão"]:
        pil = por_tipo.get(t)
        if pil is not None:
            x_det = _detalhe(des, x_det, y_tit + 2 * PAPEL, pil, de_baixo.get(t, {}), marca_de(t)) + 25 * PAPEL
    return des


#: O detalhe de locação ampliado: 1:25 dentro da planta de 1:100.
AMPLIACAO = 4.0


def _detalhe(des: Desenho, x0: float, y_topo: float, pil, cb: dict, marca: str) -> float:
    """o pilar, o cálice e a fundação de um tipo, em 1:25, com as distâncias das faces aos eixos (o que a obra
    marca no gabarito); devolve a borda direita do detalhe"""
    k = AMPLIACAO
    b2, h2 = pil.b * 5, pil.h * 5
    partes = [("pilar", b2, h2, "CORTE")]
    if "calice" in cb:
        partes.append(("cálice", cb["calice"][0] * 5, cb["calice"][1] * 5, "OCULTA"))
    if "fundacao" in cb:
        partes.append((cb["fundacao"][2] if cb["fundacao"][2] == "sapata" else "bloco", cb["fundacao"][0] * 5, cb["fundacao"][1] * 5, "OCULTA"))
    mx = max(a for _n, a, _b, _c in partes) * k
    my = max(b_ for _n, _a, b_, _c in partes) * k
    cx = x0 + mx + 14 * PAPEL
    cy = y_topo - (6.0 * len(partes) + 12.0) * PAPEL - my          # as fileiras de cota de cima abaixo do título
    _texto(des, x0, y_topo, "LOCAÇÃO %s — ESC. 1:%d" % (marca, round(ESCALA / k)), 3.5)
    ext = 10 * PAPEL
    des.add(Linha(camada="EIXO", a=(cx - mx - ext, cy), b=(cx + mx + ext, cy)))
    des.add(Linha(camada="EIXO", a=(cx, cy - my - ext), b=(cx, cy + my + ext)))
    for nome, a, b_, cam in partes:
        des.add(_ret(cx - a * k, cy - b_ * k, cx + a * k, cy + b_ * k, cam, peca=marca))
        if nome == "pilar":
            des.add(Hachura(contornos=[[(cx - a * k, cy - b_ * k), (cx + a * k, cy - b_ * k), (cx + a * k, cy + b_ * k),
                                        (cx - a * k, cy + b_ * k)]], padrao="concreto", espacamento=2.0))
    # as cotas das faces ao eixo: em cima (na direção do comprimento) e à direita (na do vão), uma fileira por peça
    for n_, (nome, a, b_, _c) in enumerate(partes):
        d_ = 4.0 + 6.0 * n_
        for xa, xb in ((cx - a * k, cx), (cx, cx + a * k)):
            des.add(Cota(modo="h", p1=(xa, cy + my), p2=(xb, cy + my), deslocamento=d_, texto="%d" % round(a)))
        for ya, yb in ((cy - b_ * k, cy), (cy, cy + b_ * k)):
            des.add(Cota(modo="v", p1=(cx + mx, ya), p2=(cx + mx, yb), deslocamento=-d_, texto="%d" % round(b_)))
    y_leg = cy - my - ext - 6 * PAPEL
    for n_, (nome, a, b_, _c) in enumerate(partes):
        _texto(des, x0, y_leg - n_ * 4.5 * PAPEL, "%s %s × %s cm%s" % (nome, fmt(a / 5, 0), fmt(b_ / 5, 0),
                                                                          " (tracejado)" if n_ else " (hachurado)"), TXT)
    return cx + mx + (6.0 * len(partes) + 12) * PAPEL


def posicoes_dos_pilares(p: ProjetoGalpaoPM) -> List[dict]:
    """cada pilar no lugar dele, como o 3D (premoldado.modelo3d) os põe: {"tipo", "i" (pórtico, 0…), "fila" (0 = A,
    1 = B, None no oitão), "x", "y" (mm), "eixo" ("1/A", "1/oitão 4,14")}"""
    d = p.dados
    xs, ys = eixos_do_galpao(p)
    por_tipo = {q.tipo: q for q in p.pilares}
    tipo_de = lambda i, j: ("canto" if i in (0, len(xs) - 1) else "intermediário") + (" B" if j == 1 and d.filas_diferentes else "")   # noqa: E731
    fora = [{"tipo": tipo_de(i, j), "i": i, "fila": j, "x": x, "y": y, "eixo": "%d/%s" % (i + 1, "AB"[j])}
            for i, x in enumerate(xs) for j, y in enumerate(ys) if tipo_de(i, j) in por_tipo]
    if "oitão" in por_tipo:
        for e, yy in (getattr(d, "pilares_oitao", None) or []):
            i = int(e) - 1
            if 0 <= i < len(xs):
                fora.append({"tipo": "oitão", "i": i, "fila": None, "x": xs[i], "y": float(yy) * 1000.0,
                             "eixo": "%d/oitão %s" % (i + 1, fmt(float(yy), 2))})
    return fora


def _linhas_do_quadro(p: ProjetoGalpaoPM, pos: List[dict], marca_de, de_baixo) -> List[List[str]]:
    fora = []
    for pil in p.pilares:
        meus = [q for q in pos if q["tipo"] == pil.tipo]
        if not meus:
            continue
        eixos = ", ".join(q["eixo"] for q in meus)
        cb = de_baixo.get(pil.tipo, {})
        cal = ("%s × %s" % (fmt(cb["calice"][0], 0), fmt(cb["calice"][1], 0))) if "calice" in cb else "—"
        fund = "—"
        if "fundacao" in cb:
            fund = "%s %s × %s" % ("sapata" if cb["fundacao"][2] == "sapata" else "bloco", fmt(cb["fundacao"][0], 0), fmt(cb["fundacao"][1], 0))
        fora.append([marca_de(pil.tipo), pil.tipo, "%s × %s" % (fmt(pil.b, 0), fmt(pil.h, 0)), str(len(meus)),
                     fmt(pil.comprimento_total, 2), cal, fund, eixos])
    return fora


def _quadro(des: Desenho, x0: float, y0: float, linhas: List[List[str]]) -> float:
    """o quadro dos pilares; devolve a borda direita dele"""
    cab = ["Marca", "Tipo", "b × h (cm)", "Qtd.", "Comp. (m)", "Cálice (cm)", "Fundação (cm)", "Eixos"]
    col = [0, 18, 48, 72, 86, 108, 134, 172]
    larg_eixos = max([len(ln[-1]) for ln in linhas] + [5]) * 0.62 * TXT
    lin = 5.0 * PAPEL
    _texto(des, x0, y0 + 2 * PAPEL, "QUADRO DOS PILARES", 3.5)
    y = y0 - lin
    for k, t in enumerate(cab):
        _texto(des, x0 + col[k] * PAPEL, y, t, TXT)
    x1 = x0 + (col[-1] + larg_eixos) * PAPEL
    des.add(Linha(camada="VISTA-FINA", a=(x0, y - 1.5 * PAPEL), b=(x1, y - 1.5 * PAPEL)))
    for ln in linhas:
        y -= lin
        for k, t in enumerate(ln):
            _texto(des, x0 + col[k] * PAPEL, y, t, TXT)
    y -= lin
    total = sum(int(ln[3]) for ln in linhas)
    _texto(des, x0, y, "Total: %d pilares; comprimento da peça com o trecho embutido no cálice" % total, TXT)
    return x1
