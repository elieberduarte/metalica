# -*- coding: utf-8 -*-
"""As plantas de saída do galpão pré-moldado (rodada R4 do ciclo arquitetônico → lançamento → 3D → pranchas).

Do mesmo projeto calculado (premoldado.galpao) e no mesmo arranjo do 3D (premoldado.modelo3d: os pórticos ao
longo de X, as filas A e B no vão, Y; a boca do cálice no ±0,00), cada vista é um Desenho do CAD (mm no
modelo, a escala só no papel), pronto para o jogo de pranchas (nucleo2d.pranchas):

* **planta de fôrmas da cobertura** (1:100) — os pilares cortados logo abaixo do topo, as vigas longitudinais
  e a de cobertura em vista com a marca, os consolos debaixo das vigas (ocultos), o topo de cada fila;
* **planta de cálices e fundações** (1:100) — o colarinho visto de cima com o vazio e o pilar cortado, a
  sapata ou o bloco e as estacas, as marcas e o quadro das fundações com os níveis;
* **corte transversal** (1:50) num pórtico — fundação, cálice e pilar cortados, a viga longitudinal em
  seção no topo de cada fila, a viga de cobertura (ou a linha da cobertura metálica), os níveis e as cotas;
* **corte longitudinal** (1:100) de cada fila — pilares, cálices, fundações, consolos e vigas entre as
  faces, com os níveis.

O que é desenho da obra (o piso, o terreno) não entra: o programa não tem esses dados.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from nucleo.base import fmt
from nucleo2d.desenho import Circulo, Cota, Desenho, Hachura, Linha, Polilinha, Texto

from .galpao import ProjetoGalpaoPM, SUFIXO
from .locacao import eixos_do_galpao, posicoes_dos_pilares

TXT = 2.5


# ------------------------------------------------------------------ utilidades

def _texto(des: Desenho, k: float, x, y, s, altura=TXT, alin="esquerda", vert="base", camada="TEXTO", **atr):
    des.add(Texto(camada=camada, posicao=(x, y), texto=s, altura=altura, alinhamento=alin, vertical=vert, atributos=atr))


def _ret(x0, y0, x1, y1, camada, **atr) -> Polilinha:
    return Polilinha(camada=camada, vertices=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fechada=True, atributos=atr)


def _hachura(des: Desenho, contornos, **atr):
    des.add(Hachura(contornos=contornos, padrao="concreto", espacamento=2.0, atributos=atr))


def _bolinha(des: Desenho, k: float, x, y, nome):
    r = 4.0 * k
    des.add(Circulo(camada="EIXO", centro=(x, y), raio=r, atributos={"eixo": nome}))
    _texto(des, k, x, y, nome, 3.5, "centro", "meio", camada="EIXO", eixo=nome)


def _nivel(des: Desenho, k: float, x, z, rotulo, lado=1.0):
    """a marca de nível: o triângulo, o traço e o valor (m) com o nome"""
    t = 2.5 * k
    des.add(Polilinha(camada="VISTA", vertices=[(x, z), (x - t / 2, z + t), (x + t / 2, z + t)], fechada=True))
    des.add(Linha(camada="VISTA-FINA", a=(x - lado * 2 * t, z), b=(x + lado * 8 * t, z)))
    val = ("+%s" % fmt(z / 1000.0, 2)) if z > 0.5 else ("±0,00" if abs(z) <= 0.5 else fmt(z / 1000.0, 2))
    _texto(des, k, x + lado * 1.2 * t, z + 1.3 * t, "%s %s" % (val, rotulo), 2.2, "esquerda" if lado > 0 else "direita")


def _titulo(des: Desenho, k: float, x, y, titulo: str, escala: float, notas: List[str]):
    _texto(des, k, x, y, titulo, 5.0)
    _texto(des, k, x, y - 7 * k, "ESC. 1:%d  ·  cotas em mm  ·  níveis em m (boca do cálice ±0,00)" % escala, TXT)
    for i, n in enumerate(notas):
        _texto(des, k, x, y - (12 + 5 * i) * k, n, TXT)


class _Galpao:
    """o que as vistas usam do projeto calculado, no arranjo do 3D (mm)"""

    def __init__(self, p: ProjetoGalpaoPM):
        self.p = p
        d = self.d = p.dados
        self.xs, self.ys = eixos_do_galpao(p)
        self.pos = posicoes_dos_pilares(p)
        self.por_tipo = {q.tipo: q for q in p.pilares}
        self.calice: Dict[str, dict] = {}
        for r in p.calices:
            if r.dados.get("direcao") == "x" and "externo" in r.dados:
                t = r.dados.get("tipo_pilar") or next((t_ for t_ in ("canto", "oitão", "intermediário") if t_ in r.elemento), "intermediário")
                self.calice[t] = r.dados
        self.fundacao: Dict[str, dict] = {r.dados["tipo_pilar"]: r.dados for r in p.fundacoes if "ah" in r.dados and r.dados.get("tipo_pilar")}
        self.long = next((v for v in p.vigas if v.funcao not in ("viga de cobertura", "terça")), None)
        self.cob = next((v for v in p.vigas if v.funcao == "viga de cobertura"), None)
        self.tercas = next((v for v in p.vigas if v.funcao == "terça"), None)
        self.marcas_long = {l["comprimento_m"]: l["marca"] for l in p.lista if l["marca"].startswith(("VC", "VT"))}

    def tipo_de(self, i: int, j: int) -> str:
        return ("canto" if i in (0, len(self.xs) - 1) else "intermediário") + (" B" if j == 1 and self.d.filas_diferentes else "")

    def topo(self, q: dict) -> float:
        """mm: o topo do pilar da posição"""
        if q["fila"] is None:
            return self.d.altura_oitao(q["y"] / 1000.0) * 1000.0
        return self.d.altura_tipo(q["tipo"]) * 1000.0

    def lemb(self, tipo: str) -> float:
        pil = self.por_tipo[tipo]
        return (pil.comprimento_total - self.d.altura_tipo(tipo)) * 1000.0

    def z_apoio(self, j: int) -> Optional[float]:
        """a face de cima do consolo (o apoio da viga longitudinal) na fila j"""
        if self.long is None:
            return None
        H = (self.d.altura_pilar if j == 0 else self.d.altura_b) * 1000.0
        return H - self.long.secao.h * 10 - 10.0

    def trechos_long(self, j: int):
        """as vigas longitudinais da fila j: (k, x0, x1, marca)"""
        d = self.d
        out = []
        if self.long is None:
            return out
        b_max = max(q.b for q in self.p.pilares) / 100.0
        for k in range(len(self.xs) - 1):
            pa, pb = self.por_tipo.get(self.tipo_de(k, j)), self.por_tipo.get(self.tipo_de(k + 1, j))
            if pa is None or pb is None:
                continue
            x0 = self.xs[k] + pa.b * 5 + 10.0
            x1 = self.xs[k + 1] - pb.b * 5 - 10.0
            comp = math.floor((d.vaos_longitudinais[k] - b_max - 0.02) * 100.0 + 1e-6) / 100.0
            out.append((k, x0, x1, self.marcas_long.get(comp, self.long.marca)))
        return out

    def notas_fundacao(self) -> str:
        d = self.d
        return {"sapata": "fundação: sapata moldada no local sob o cálice", "estacas": "fundação: bloco sobre estacas (comprimento pela sondagem)",
                }.get(d.fundacao, "fundação: só o cálice (o fundo dele apoiado no terreno)")


def _eixos_e_cotas(des: Desenho, k: float, g: _Galpao, meia_x: float, meia_y: float):
    """os eixos com as bolinhas, a cadeia entre eixos (embaixo e em cima) e o vão dos dois lados; devolve a
    caixa (x_ini, x_fim, y_ini, y_fim) e o y da cadeia de baixo"""
    xs, ys = g.xs, g.ys
    av = 22.0 * k
    x_ini, x_fim = xs[0] - meia_x - av, xs[-1] + meia_x + av
    y_ini, y_fim = ys[0] - meia_y - av, ys[-1] + meia_y + av
    rb = 4.0 * k
    for i, x in enumerate(xs):
        des.add(Linha(camada="EIXO", a=(x, y_ini), b=(x, y_fim), atributos={"eixo": str(i + 1)}))
        _bolinha(des, k, x, y_ini - rb, str(i + 1))
        _bolinha(des, k, x, y_fim + rb, str(i + 1))
    for j, y in enumerate(ys):
        nome = "AB"[j]
        des.add(Linha(camada="EIXO", a=(x_ini, y), b=(x_fim, y), atributos={"eixo": nome}))
        _bolinha(des, k, x_ini - rb, y, nome)
        _bolinha(des, k, x_fim + rb, y, nome)
    y_cad = y_ini - 2 * rb - 6 * k
    for a, b in zip(xs, xs[1:]):
        des.add(Cota(modo="h", p1=(a, y_cad), p2=(b, y_cad), deslocamento=0.0))
    if len(xs) > 2:
        des.add(Cota(modo="h", p1=(xs[0], y_cad), p2=(xs[-1], y_cad), deslocamento=-8.0))
    x_cad = x_ini - 2 * rb - 6 * k
    des.add(Cota(modo="v", p1=(x_cad, ys[0]), p2=(x_cad, ys[-1]), deslocamento=0.0))
    x_cad2 = x_fim + 2 * rb + 6 * k
    des.add(Cota(modo="v", p1=(x_cad2, ys[0]), p2=(x_cad2, ys[-1]), deslocamento=0.0))
    return x_ini, x_fim, y_ini, y_fim, y_cad


def _pilar_cortado(des: Desenho, g: _Galpao, q: dict):
    pil = g.por_tipo[q["tipo"]]
    x, y = q["x"], q["y"]
    b2, h2 = pil.b * 5, pil.h * 5
    atr = {"peca": "P-%s" % SUFIXO[q["tipo"]], "eixo": q["eixo"], "pre_moldado": True}
    o = (g.d.origem_planta or {}).get(q["eixo"])
    if o:
        atr["origem_2d"] = o["id"]
    des.add(_ret(x - b2, y - h2, x + b2, y + h2, "CORTE", **atr))
    _hachura(des, [[(x - b2, y - h2), (x + b2, y - h2), (x + b2, y + h2), (x - b2, y + h2)]], **atr)
    return b2, h2


# ------------------------------------------------------------------ planta de fôrmas da cobertura

def planta_formas(p: ProjetoGalpaoPM, nome: str = "Fôrmas da cobertura") -> Desenho:
    ESC = 100.0
    k = ESC
    g = _Galpao(p)
    d = g.d
    des = Desenho(nome=nome, escala=ESC)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "planta de fôrmas da cobertura"})
    meia_x = max((q.b * 5 for q in p.pilares), default=0.0)
    meia_y = max((q.h * 5 for q in p.pilares), default=0.0)
    if g.long is not None:
        meia_y = max(meia_y, g.long.secao.b_max * 5)
    x_ini, x_fim, y_ini, y_fim, y_cad = _eixos_e_cotas(des, k, g, meia_x, meia_y)
    # os pilares cortados logo abaixo do topo
    for q in g.pos:
        b2, h2 = _pilar_cortado(des, g, q)
        if q["fila"] is None:
            lado = 1.0 if q["i"] == 0 else -1.0
            _texto(des, k, q["x"] + lado * (b2 + 3 * k), q["y"], "P-%s  topo +%s" % (SUFIXO[q["tipo"]], fmt(g.topo(q) / 1000.0, 2)), 2.2,
                   "esquerda" if lado > 0 else "direita", "meio", peca="P-%s" % SUFIXO[q["tipo"]], eixo=q["eixo"])
    # as vigas longitudinais (vista, sobre os consolos) e os consolos debaixo delas
    if g.long is not None:
        w2 = g.long.secao.b_max * 5
        comp_c = 2 * d.consolo_a * 10
        for j, y in enumerate(g.ys):
            for (kk, x0, x1, marca) in g.trechos_long(j):
                des.add(_ret(x0, y - w2, x1, y + w2, "VISTA", peca=marca, vao="%d-%d" % (kk + 1, kk + 2), fila="AB"[j]))
                dentro = 1.0 if j == 0 else -1.0
                _texto(des, k, (x0 + x1) / 2, y + dentro * (w2 + 2.5 * k), marca, 2.5, "centro", "base" if dentro > 0 else "topo", peca=marca)
            for i, x in enumerate(g.xs):
                pil = g.por_tipo.get(g.tipo_de(i, j))
                if pil is None:
                    continue
                for lado in ([1] if i < len(g.xs) - 1 else []) + ([-1] if i > 0 else []):
                    xa = x + lado * pil.b * 5
                    xb = xa + lado * comp_c
                    des.add(_ret(min(xa, xb), y - pil.h * 5, max(xa, xb), y + pil.h * 5, "OCULTA", peca="consolo", eixo="%d/%s" % (i + 1, "AB"[j])))
    # a viga de cobertura em cada pórtico (de face externa a face externa dos pilares) e as terças
    if g.cob is not None:
        bf2 = g.cob.secao.b_max * 5
        h_pil = max(q.h for q in p.pilares) * 10
        for i, x in enumerate(g.xs):
            des.add(_ret(x - bf2, g.ys[0] - h_pil / 2, x + bf2, g.ys[-1] + h_pil / 2, "VISTA", peca=g.cob.marca, eixo=str(i + 1)))
            _texto(des, k, x + bf2 + 1.5 * k, (g.ys[0] + g.ys[-1]) / 2, g.cob.marca, 2.5, "esquerda", "meio", peca=g.cob.marca)
        if g.tercas is not None and p.cargas_vigas.get("tercas_linhas", 0) >= 2:
            linhas = p.cargas_vigas["tercas_linhas"]
            L = g.ys[-1] - g.ys[0]
            passo = (L / 2) / ((linhas - 1) / 2)
            tw2 = g.tercas.secao.b_max * 5
            for kk in range(linhas):
                y = g.ys[0] + kk * passo
                for a, b in zip(g.xs, g.xs[1:]):
                    des.add(_ret(a + bf2, y - tw2, b - bf2, y + tw2, "VISTA-FINA", peca=g.tercas.marca))
            _texto(des, k, (g.xs[0] + g.xs[1]) / 2, g.ys[0] + passo + tw2 + 1.5 * k, "%s (%d linhas)" % (g.tercas.marca, linhas), 2.2, "centro", peca=g.tercas.marca)
    # o topo de cada fila, do lado de fora
    for j, y in enumerate(g.ys):
        fora = -1.0 if j == 0 else 1.0
        H = (d.altura_pilar if j == 0 else d.altura_b) * 1000.0
        _texto(des, k, (g.xs[0] + g.xs[-1]) / 2, y + fora * (meia_y + 9 * k), "FILA %s — TOPO DOS PILARES +%s%s" % (
            "AB"[j], fmt(H / 1000.0, 2), ("  ·  APOIO DAS VIGAS +%s" % fmt(g.z_apoio(j) / 1000.0, 2)) if g.long is not None else ""),
            2.5, "centro", "topo" if fora < 0 else "base")
    notas = ["pilares cortados logo abaixo do topo (hachurados); vigas em vista; tracejado: consolos debaixo das vigas"]
    if d.uma_agua:
        notas.append("cobertura de uma água: inclinação %s° (%s%%) da fila %s para a fila %s" % (
            fmt(d.inclinacao_efetiva, 2), fmt(100 * math.tan(math.radians(d.inclinacao_efetiva)), 1),
            "B" if d.altura_b > d.altura_pilar else "A", "A" if d.altura_b > d.altura_pilar else "B"))
    elif not d.viga_cobertura:
        notas.append("cobertura metálica (projeto próprio) apoiada no topo dos pilares")
    _titulo(des, k, x_ini, y_cad - 22 * k, "PLANTA DE FÔRMAS — COBERTURA", ESC, notas)
    return des


# ------------------------------------------------------------------ planta de cálices e fundações

def planta_fundacoes(p: ProjetoGalpaoPM, nome: str = "Cálices e fundações") -> Desenho:
    ESC = 100.0
    k = ESC
    g = _Galpao(p)
    d = g.d
    des = Desenho(nome=nome, escala=ESC)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "planta de cálices e fundações"})
    meia_x = meia_y = 0.0
    for t, pil in g.por_tipo.items():
        meia_x, meia_y = max(meia_x, pil.b * 5), max(meia_y, pil.h * 5)
        for ab in ([g.calice[t]["externo"]] if t in g.calice else []) + ([(g.fundacao[t]["ab"], g.fundacao[t]["ah"])] if t in g.fundacao else []):
            meia_x, meia_y = max(meia_x, ab[0] * 5), max(meia_y, ab[1] * 5)
    x_ini, x_fim, y_ini, y_fim, y_cad = _eixos_e_cotas(des, k, g, meia_x, meia_y)
    cotado = set()
    for q in g.pos:
        t, x, y = q["tipo"], q["x"], q["y"]
        suf = SUFIXO[t]
        _pilar_cortado(des, g, q)
        c = g.calice.get(t)
        if c is not None:
            eb, eh = c["externo"][0] * 5, c["externo"][1] * 5
            ib, ih = c["interno"][0] * 5, c["interno"][1] * 5
            des.add(_ret(x - eb, y - eh, x + eb, y + eh, "VISTA", peca="CL-%s" % suf, eixo=q["eixo"]))
            des.add(_ret(x - ib, y - ih, x + ib, y + ih, "VISTA-FINA", peca="CL-%s" % suf, eixo=q["eixo"]))
        f = g.fundacao.get(t)
        if f is not None:
            fb, fh = f["ab"] * 5, f["ah"] * 5
            pref = "SP" if f["tipo"] == "sapata" else "BL"
            des.add(_ret(x - fb, y - fh, x + fb, y + fh, "VISTA", peca="%s-%s" % (pref, suf), eixo=q["eixo"]))
            for (ph, pb) in f.get("estacas") or []:
                des.add(Circulo(camada="OCULTA", centro=(x + pb * 10, y + ph * 10), raio=f["estaca_diametro"] * 5,
                                atributos={"peca": "EST-%s" % suf, "eixo": q["eixo"]}))
        # a marca para dentro do galpão
        rot = "CL-%s%s" % (suf, (" + %s-%s" % ("SP" if f["tipo"] == "sapata" else "BL", suf)) if f is not None else "")
        if q["fila"] is not None:
            dentro = 1.0 if q["fila"] == 0 else -1.0
            _texto(des, k, x, y + dentro * (meia_y + 3 * k), rot, 2.2, "centro", "base" if dentro > 0 else "topo", eixo=q["eixo"])
        else:
            lado = 1.0 if q["i"] == 0 else -1.0
            _texto(des, k, x + lado * (meia_x + 3 * k), y, rot, 2.2, "esquerda" if lado > 0 else "direita", "meio", eixo=q["eixo"])
        # as medidas de um de cada tipo: a fundação (ou o cálice) centrada no eixo
        if t not in cotado:
            cotado.add(t)
            ob, oh = (f["ab"] * 5, f["ah"] * 5) if f is not None else ((c["externo"][0] * 5, c["externo"][1] * 5) if c else (0, 0))
            if ob:
                dentro = 1.0 if q["fila"] in (0, None) else -1.0
                des.add(Cota(modo="h", p1=(x - ob, y + dentro * oh), p2=(x + ob, y + dentro * oh), deslocamento=dentro * 4.0))
                lado = 1.0 if q["i"] < len(g.xs) - 1 else -1.0
                # na cota vertical o deslocamento positivo vai para −x: para fora da fundação é −lado
                des.add(Cota(modo="v", p1=(x + lado * ob, y - oh), p2=(x + lado * ob, y + oh), deslocamento=-lado * 5.0))
    # o quadro das fundações
    linhas = [["MARCA", "CÁLICE ext. × int. (cm)", "EMBUT. (cm)", "FUNDAÇÃO (cm)", "FUNDO (m)", "QTD."]]
    for t, pil in g.por_tipo.items():
        c, f = g.calice.get(t), g.fundacao.get(t)
        if c is None:
            continue
        Lc = c["Lemb_adotado"] * 10
        if f is not None:
            fund = ("sapata %s × %s × %s" % (fmt(f["ab"], 0), fmt(f["ah"], 0), fmt(f["hf"], 0)) if f["tipo"] == "sapata" else
                    "bloco %s × %s × %s, %d estacas ø%s" % (fmt(f["ab"], 0), fmt(f["ah"], 0), fmt(f["hf"], 0), f["n_estacas"], fmt(f["estaca_diametro"], 0)))
            fundo = -(Lc + f["hf"] * 10)
        else:
            fund = "fundo do cálice %s cm" % fmt(c["fundo"], 0)
            fundo = -(Lc + c["fundo"] * 10)
        linhas.append(["CL-%s" % SUFIXO[t], "%s × %s / %s × %s" % (fmt(c["externo"][0], 0), fmt(c["externo"][1], 0), fmt(c["interno"][0], 0), fmt(c["interno"][1], 0)),
                       fmt(c["Lemb_adotado"], 0), fund, fmt(fundo / 1000.0, 2), str(pil.quantidade)])
    y_tit = y_cad - 22 * k
    _titulo(des, k, x_ini, y_tit, "PLANTA DE CÁLICES E FUNDAÇÕES", ESC,
            ["vista de cima na boca do cálice (±0,00): pilar cortado, colarinho e vazio do cálice; a fundação embaixo",
             g.notas_fundacao() + "  ·  tracejado: estacas"])
    _quadro(des, k, x_ini, y_tit - 30 * k, linhas)
    return des


def _quadro(des: Desenho, k: float, x0: float, y0: float, linhas: List[List[str]]) -> float:
    """uma tabela simples (textos e linhas); devolve o x da borda direita"""
    alt = 6.0 * k
    larg = [max(len(l[c]) for l in linhas) * 1.9 * k + 4 * k for c in range(len(linhas[0]))]
    x1 = x0 + sum(larg)
    for i, l in enumerate(linhas):
        y = y0 - i * alt
        des.add(Linha(camada="VISTA-FINA", a=(x0, y), b=(x1, y)))
        xc = x0
        for c, s in enumerate(l):
            _texto(des, k, xc + 2 * k, y - alt / 2, s, 2.2 if i else 2.3, "esquerda", "meio")
            xc += larg[c]
    y_fim = y0 - len(linhas) * alt
    des.add(Linha(camada="VISTA-FINA", a=(x0, y_fim), b=(x1, y_fim)))
    xc = x0
    for w in [0.0] + larg:
        xc += w
        des.add(Linha(camada="VISTA-FINA", a=(xc, y0), b=(xc, y_fim)))
    return x1


# ------------------------------------------------------------------ cortes

def _fundacao_em_elevacao(des: Desenho, g: _Galpao, tipo: str, u: float, largura_calice: float, largura_fund: float, eixo: str,
                          cortado: bool = True):
    """o cálice (paredes cortadas, o vazio) e a fundação embaixo, centrados em u (a coordenada horizontal do corte)"""
    c = g.calice.get(tipo)
    if c is None:
        return 0.0
    Lc = c["Lemb_adotado"] * 10
    e2 = largura_calice / 2
    i2 = (c["interno"][1] if largura_calice == c["externo"][1] * 10 else c["interno"][0]) * 5
    cam = "CORTE" if cortado else "VISTA"
    des.add(_ret(u - e2, -Lc, u + e2, 0.0, cam, peca="CL-%s" % SUFIXO[tipo], eixo=eixo))
    if cortado:
        _hachura(des, [[(u - e2, -Lc), (u - i2, -Lc), (u - i2, 0.0), (u - e2, 0.0)]], peca="CL-%s" % SUFIXO[tipo])
        _hachura(des, [[(u + i2, -Lc), (u + e2, -Lc), (u + e2, 0.0), (u + i2, 0.0)]], peca="CL-%s" % SUFIXO[tipo])
        des.add(Linha(camada="CORTE", a=(u - i2, -Lc), b=(u - i2, 0.0)))
        des.add(Linha(camada="CORTE", a=(u + i2, -Lc), b=(u + i2, 0.0)))
    f = g.fundacao.get(tipo)
    if f is not None:
        hf = f["hf"] * 10
        f2 = largura_fund / 2
        des.add(_ret(u - f2, -Lc - hf, u + f2, -Lc, cam, peca="%s-%s" % ("SP" if f["tipo"] == "sapata" else "BL", SUFIXO[tipo]), eixo=eixo))
        if cortado:
            _hachura(des, [[(u - f2, -Lc - hf), (u + f2, -Lc - hf), (u + f2, -Lc), (u - f2, -Lc)]])
        if f["tipo"] != "sapata":
            usados = set()
            for (ph, pb) in f.get("estacas") or []:
                off = (ph if largura_fund == f["ah"] * 10 else pb) * 10
                if round(off) in usados:
                    continue
                usados.add(round(off))
                r = f["estaca_diametro"] * 5
                des.add(Linha(camada="VISTA", a=(u + off - r, -Lc - hf), b=(u + off - r, -Lc - hf - 1500.0)))
                des.add(Linha(camada="VISTA", a=(u + off + r, -Lc - hf), b=(u + off + r, -Lc - hf - 1500.0)))
                des.add(Linha(camada="VISTA-FINA", a=(u + off - 1.4 * r, -Lc - hf - 1450.0), b=(u + off + 1.4 * r, -Lc - hf - 1550.0)))
        return -Lc - hf
    fundo = c["fundo"] * 10
    des.add(_ret(u - e2, -Lc - fundo, u + e2, -Lc, cam, peca="CL-%s" % SUFIXO[tipo], eixo=eixo))
    if cortado:
        _hachura(des, [[(u - e2, -Lc - fundo), (u + e2, -Lc - fundo), (u + e2, -Lc), (u - e2, -Lc)]])
    return -Lc - fundo


def corte_transversal(p: ProjetoGalpaoPM, nome: str = "Corte transversal") -> Desenho:
    """o corte num pórtico intermediário (no 2, ou no 1 se só houver dois), olhando para os de número maior"""
    ESC = 50.0
    k = ESC
    g = _Galpao(p)
    d = g.d
    i = 1 if len(g.xs) > 2 else 0
    des = Desenho(nome=nome, escala=ESC)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "corte transversal"})
    ys = g.ys
    fundos, topos = [], []
    for j, y in enumerate(ys):
        t = g.tipo_de(i, j)
        pil = g.por_tipo.get(t)
        if pil is None:
            continue
        eixo = "%d/%s" % (i + 1, "AB"[j])
        H = d.altura_tipo(t) * 1000.0
        Le = g.lemb(t)
        h2 = pil.h * 5
        des.add(_ret(y - h2, -Le, y + h2, H, "CORTE", peca="P-%s" % SUFIXO[t], eixo=eixo))
        _hachura(des, [[(y - h2, -Le), (y + h2, -Le), (y + h2, H), (y - h2, H)]], peca="P-%s" % SUFIXO[t])
        c = g.calice.get(t)
        f = g.fundacao.get(t)
        fundos.append(_fundacao_em_elevacao(des, g, t, y, c["externo"][1] * 10 if c else 0.0, f["ah"] * 10 if f else 0.0, eixo))
        topos.append((j, y, H, pil))
        # a viga longitudinal em seção sobre o consolo (o consolo fica atrás, em vista: é o pilar mais largo)
        if g.long is not None:
            za = g.z_apoio(j)
            cont = [(y + cx * 10, za + 10.0 + cy * 10) for cx, cy in g.long.secao.contorno()]
            des.add(Polilinha(camada="CORTE", vertices=cont, fechada=True, atributos={"peca": g.long.marca}))
            _hachura(des, [cont], peca=g.long.marca)
            des.add(_ret(y - h2, za - d.consolo_altura * 10, y + h2, za, "VISTA", peca="consolo"))
            des.add(_ret(y - pil.h * 4, za, y + pil.h * 4, za + 10.0, "VISTA-FINA", peca="elastômero"))
    # a cobertura: a viga de cobertura em vista ou a linha da cobertura metálica
    if len(topos) == 2:
        (_, ya, HA, pa), (_, yb, HB, pb) = topos
        y0, y1 = ya - pa.h * 5, yb + pb.h * 5
        if g.cob is not None:
            h0 = g.cob.secao_apoio.h * 10
            hm = g.cob.secao.h * 10
            if d.uma_agua:
                cont = [(y0, HA), (y1, HB), (y1, HB + h0), (y0, HA + h0)]
            else:
                ym = (ya + yb) / 2
                cont = [(y0, HA), (y1, HB), (y1, HB + h0), (ym, HA + hm), (y0, HA + h0)]
            des.add(Polilinha(camada="VISTA", vertices=cont, fechada=True, atributos={"peca": g.cob.marca}))
            _texto(des, k, (ya + yb) / 2, max(HA, HB) + h0 + 3 * k, g.cob.marca, 2.5, "centro", peca=g.cob.marca)
        else:
            if d.uma_agua:
                pts = [(ya, HA), (yb, HB)]
            else:
                pts = [(ya, HA), ((ya + yb) / 2, d.altura_cumeeira * 1000.0), (yb, HB)]
            des.add(Polilinha(camada="OCULTA", vertices=pts, atributos={"cobertura": "metálica"}))
            xm = (pts[0][0] + pts[-1][0]) / 2
            _texto(des, k, xm, (pts[0][1] + pts[-1][1]) / 2 + (0 if d.uma_agua else (d.altura_cumeeira * 1000.0 - HA) / 2) + 3 * k,
                   "cobertura metálica (projeto próprio)", 2.2, "centro")
    # níveis à esquerda e à direita, cotas
    x_esq = ys[0] - 40 * k
    x_dir = ys[-1] + 40 * k
    _nivel(des, k, x_esq, 0.0, "boca do cálice", -1.0)
    _nivel(des, k, x_dir, 0.0, "boca do cálice", 1.0)
    for j, y, H, _pil in topos:
        _nivel(des, k, x_esq if j == 0 else x_dir, H, "topo fila %s" % "AB"[j], -1.0 if j == 0 else 1.0)
        if g.long is not None:
            _nivel(des, k, x_esq if j == 0 else x_dir, g.z_apoio(j), "apoio das vigas", -1.0 if j == 0 else 1.0)
    if fundos:
        z_f = min(fundos)
        _nivel(des, k, x_esq, z_f, "fundo da fundação", -1.0)
        des.add(Linha(camada="VISTA-FINA", a=(x_esq, 0.0), b=(x_dir, 0.0), atributos={"nivel": "boca do cálice"}))
    y_cota = min(fundos or [0.0]) - 25 * k
    des.add(Cota(modo="h", p1=(ys[0], y_cota), p2=(ys[-1], y_cota), deslocamento=0.0))
    for j, y, H, _pil in topos:
        xc = y + (-1 if j == 0 else 1) * 25 * k
        des.add(Cota(modo="v", p1=(xc, 0.0), p2=(xc, H), deslocamento=0.0))
        des.add(Cota(modo="v", p1=(xc, -g.lemb(g.tipo_de(i, j))), p2=(xc, 0.0), deslocamento=0.0))
    for j, y in enumerate(ys):
        _bolinha(des, k, y, y_cota - 14 * k, "AB"[j])
        des.add(Linha(camada="EIXO", a=(y, y_cota - 10 * k), b=(y, max((t[2] for t in topos), default=0.0) + 10 * k)))
    _titulo(des, k, x_esq, y_cota - 30 * k, "CORTE TRANSVERSAL — PÓRTICO %d" % (i + 1), ESC,
            ["pilares, cálices e fundação cortados; a viga longitudinal em seção sobre o consolo e o elastômero",
             g.notas_fundacao()])
    return des


def corte_longitudinal(p: ProjetoGalpaoPM, fila: int = 0, nome: Optional[str] = None) -> Desenho:
    """a elevação de uma fila (olhando de fora do galpão): pilares, cálices, fundações, consolos e vigas"""
    ESC = 100.0
    k = ESC
    g = _Galpao(p)
    d = g.d
    des = Desenho(nome=nome or "Corte longitudinal — fila %s" % "AB"[fila], escala=ESC)
    des.metadados.update({"origem": "premoldado", "obra": d.nome, "gerado": "corte longitudinal fila %s" % "AB"[fila]})
    xs = g.xs
    fundos = []
    H = (d.altura_pilar if fila == 0 else d.altura_b) * 1000.0
    for i, x in enumerate(xs):
        t = g.tipo_de(i, fila)
        pil = g.por_tipo.get(t)
        if pil is None:
            continue
        eixo = "%d/%s" % (i + 1, "AB"[fila])
        Le = g.lemb(t)
        b2 = pil.b * 5
        des.add(_ret(x - b2, -Le, x + b2, H, "CORTE", peca="P-%s" % SUFIXO[t], eixo=eixo))
        _hachura(des, [[(x - b2, -Le), (x + b2, -Le), (x + b2, H), (x - b2, H)]], peca="P-%s" % SUFIXO[t])
        c = g.calice.get(t)
        f = g.fundacao.get(t)
        fundos.append(_fundacao_em_elevacao(des, g, t, x, c["externo"][0] * 10 if c else 0.0, f["ab"] * 10 if f else 0.0, eixo))
        _texto(des, k, x, H + 3 * k, "P-%s" % SUFIXO[t], 2.5, "centro", peca="P-%s" % SUFIXO[t], eixo=eixo)
        if g.long is not None:
            za = g.z_apoio(fila)
            comp_c = 2 * d.consolo_a * 10
            for lado in ([1] if i < len(xs) - 1 else []) + ([-1] if i > 0 else []):
                xa = x + lado * b2
                xb = xa + lado * comp_c
                des.add(_ret(min(xa, xb), za - d.consolo_altura * 10, max(xa, xb), za, "VISTA", peca="consolo", eixo=eixo))
    if g.long is not None:
        za = g.z_apoio(fila)
        hv = g.long.secao.h * 10
        for (kk, x0, x1, marca) in g.trechos_long(fila):
            des.add(_ret(x0, za + 10.0, x1, za + 10.0 + hv, "VISTA", peca=marca, vao="%d-%d" % (kk + 1, kk + 2)))
            _texto(des, k, (x0 + x1) / 2, za + 10.0 + hv / 2, marca, 2.5, "centro", "meio", peca=marca)
    x_esq = xs[0] - 30 * k
    _nivel(des, k, x_esq, 0.0, "boca do cálice", -1.0)
    _nivel(des, k, x_esq, H, "topo", -1.0)
    if g.long is not None:
        _nivel(des, k, x_esq, g.z_apoio(fila), "apoio das vigas", -1.0)
    if fundos:
        _nivel(des, k, x_esq, min(fundos), "fundo da fundação", -1.0)
    des.add(Linha(camada="VISTA-FINA", a=(x_esq, 0.0), b=(xs[-1] + 20 * k, 0.0), atributos={"nivel": "boca do cálice"}))
    y_cota = min(fundos or [0.0]) - 20 * k
    for a, b in zip(xs, xs[1:]):
        des.add(Cota(modo="h", p1=(a, y_cota), p2=(b, y_cota), deslocamento=0.0))
    if len(xs) > 2:
        des.add(Cota(modo="h", p1=(xs[0], y_cota), p2=(xs[-1], y_cota), deslocamento=-8.0))
    for i, x in enumerate(xs):
        _bolinha(des, k, x, y_cota - 20 * k, str(i + 1))
        des.add(Linha(camada="EIXO", a=(x, y_cota - 16 * k), b=(x, H + 8 * k)))
    _titulo(des, k, x_esq, y_cota - 34 * k, "CORTE LONGITUDINAL — FILA %s (vista de fora)" % "AB"[fila], ESC,
            ["pilares, cálices e fundações cortados no eixo da fila; consolos e vigas em vista", g.notas_fundacao()])
    return des


def conflitos(p: ProjetoGalpaoPM) -> List[str]:
    """as fundações (ou os cálices, sem fundação) que se sobrepõem em planta — o lugar dos pilares vem do projeto
    (a cobertura, a planta lançada): o programa não muda, aponta"""
    g = _Galpao(p)
    caixas = []
    for q in g.pos:
        t = q["tipo"]
        f, c = g.fundacao.get(t), g.calice.get(t)
        if f is not None:
            b2, h2, nome = f["ab"] * 5, f["ah"] * 5, "%s-%s" % ("SP" if f["tipo"] == "sapata" else "BL", SUFIXO[t])
        elif c is not None:
            b2, h2, nome = c["externo"][0] * 5, c["externo"][1] * 5, "CL-%s" % SUFIXO[t]
        else:
            continue
        caixas.append((q["x"] - b2, q["y"] - h2, q["x"] + b2, q["y"] + h2, "%s (%s)" % (nome, q["eixo"])))
    out = []
    for i, a in enumerate(caixas):
        for b in caixas[i + 1:]:
            dx = min(a[2], b[2]) - max(a[0], b[0])
            dy = min(a[3], b[3]) - max(a[1], b[1])
            if dx > 1.0 and dy > 1.0:
                out.append("as fundações %s e %s se sobrepõem em planta (%s × %s cm): juntar numa fundação só ou rever o "
                           "lugar dos pilares — o programa não muda o que veio do projeto" % (a[4], b[4], fmt(dx / 10, 0), fmt(dy / 10, 0)))
    return out


def desenhos(p: ProjetoGalpaoPM) -> List[Tuple[str, Desenho]]:
    """(slug, desenho) de todas as plantas de saída, na ordem das pranchas"""
    d = p.dados
    out = [("formas-da-cobertura", planta_formas(p)), ("calices-e-fundacoes", planta_fundacoes(p)),
           ("corte-transversal", corte_transversal(p)), ("corte-longitudinal-fila-a", corte_longitudinal(p, 0))]
    if d.filas_diferentes:
        out.append(("corte-longitudinal-fila-b", corte_longitudinal(p, 1)))
    return out
