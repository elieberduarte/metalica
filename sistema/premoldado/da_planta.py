# -*- coding: utf-8 -*-
"""Os dados do galpão pré-moldado tirados da planta de lançamento (CAD, menu Estrutura).

O ciclo convencional: o arquitetônico recebe os elementos em planta (pilares, vigas, fundações, consolos,
com os níveis), e o cálculo parte do que foi lançado. Aqui a planta vira `DadosGalpaoPM`:

* os pilares de concreto em duas linhas paralelas ao X (a mais perto de Y = 0 é a fila A, a outra a B):
  as posições em X dão os pórticos e os vãos entre eles; o nível do topo de cada fila dá a altura dos
  pilares (a partir da boca do cálice, o nível "Boca do cálice" do projeto ou ±0,00); filas com topos
  diferentes viram `altura_pilar_b` e cobertura de uma água;
* os pilares entre as filas, num pórtico da ponta, são os pilares de oitão;
* as seções lançadas nos pilares são as candidatas (o programa verifica o que o projetista desenhou;
  o que não passa vira erro, não troca de seção sozinho);
* as vigas ao longo das filas (de pilar a pilar) são as vigas longitudinais: U → calha; retangular →
  travamento; as que cruzam de A a B são a viga de cobertura em concreto;
* os consolos dão a altura e o balanço (`consolo_a` = comprimento − meio do apoio);
* as fundações dão o tipo (sapata ou bloco sobre estacas).

O que não encaixa nessa leitura fica em `avisos`, e os demais dados (cargas, vento, materiais, solo)
vêm do `base` (os dados já gravados no projeto)."""
from __future__ import annotations

import dataclasses
import math
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados, fmt
from nucleo2d.desenho import Desenho
from nucleo3d.de_planta_estrutura import elementos, _nivel

from .galpao import DadosGalpaoPM

#: mm: pilares a menos disso de uma linha estão nela; pórticos a menos disso são o mesmo
TOL_LINHA = 500.0
TOL_PORTICO = 300.0


def _agrupar(vals: List[float], gap: float) -> List[List[float]]:
    gr: List[List[float]] = []
    for v in sorted(vals):
        if gr and v - gr[-1][-1] <= gap:
            gr[-1].append(v)
        else:
            gr.append([v])
    return gr


def _media(vs: List[float]) -> float:
    return sum(vs) / len(vs)


def _mediana(vs: List[float]) -> float:
    vs = sorted(vs)
    return vs[len(vs) // 2]


def _centro(el: dict) -> Optional[Tuple[float, float]]:
    a = el["atributos"]
    c = a.get("centro")
    if c and len(c) >= 2:
        return float(c[0]), float(c[1])
    e = el["entidade"]
    pts = getattr(e, "vertices", None)
    if pts:
        return _media([float(p[0]) for p in pts]), _media([float(p[1]) for p in pts])
    return None


def _secao_cm(a: dict) -> Optional[Tuple[float, float]]:
    s = a.get("secao") or {}
    try:
        b, h = float(s.get("b") or 0), float(s.get("h") or 0)
    except (TypeError, ValueError):
        return None
    if b > 0 and h > 0:
        return b, h
    return None


def dados_da_planta(des: Desenho, niveis: Optional[List[dict]] = None, base: Optional[DadosGalpaoPM] = None) -> Tuple[DadosGalpaoPM, List[str]]:
    """os dados do galpão lidos da planta; `base` traz o resto (cargas, vento, materiais, solo)"""
    nv = {n["nome"]: float(n["z"]) for n in (niveis or []) if isinstance(n, dict) and n.get("nome")}
    z0 = nv.get("Boca do cálice", 0.0)
    els = elementos(des)
    avisos: List[str] = []
    pil = []
    for el in els:
        if el["elemento"] != "pilar":
            continue
        c = _centro(el)
        if c is None:
            avisos.append("pilar %s sem centro: fica de fora" % el["atributos"].get("marca", el["id"]))
            continue
        a = el["atributos"]
        if a.get("material", "concreto") != "concreto":
            avisos.append("pilar %s de aço: o pré-moldado só calcula pilares de concreto — fica de fora" % a.get("marca", el["id"]))
            continue
        pil.append({"id": el["id"], "marca": str(a.get("marca") or el["id"]), "x": c[0], "y": c[1], "topo": _nivel(a.get("nivel_topo"), nv, 0.0),
                    "base": _nivel(a.get("nivel_base"), nv, 0.0), "secao": _secao_cm(a), "rot": float(a.get("rotacao") or 0)})
    if len(pil) < 4:
        raise ErroDeDados("a planta tem %d pilar(es) de concreto: o galpão pede as duas filas (4 no mínimo)" % len(pil))
    linhas = _agrupar([q["y"] for q in pil], TOL_LINHA)
    if len(linhas) < 2:
        raise ErroDeDados("os pilares estão numa linha só: o galpão pede as filas A e B")
    yA, yB = _media(linhas[0]), _media(linhas[-1])
    fila = {}
    for q in pil:
        if abs(q["y"] - yA) <= TOL_LINHA:
            fila[q["marca"]] = 0
        elif abs(q["y"] - yB) <= TOL_LINHA:
            fila[q["marca"]] = 1
    nas_filas = [q for q in pil if q["marca"] in fila]
    porticos = [_media(g) for g in _agrupar([q["x"] for q in nas_filas], TOL_PORTICO)]
    if len(porticos) < 2:
        raise ErroDeDados("as filas têm um pórtico só: o galpão pede dois ou mais")
    x0 = porticos[0]
    for k, xp in enumerate(porticos):
        tem = {fila[q["marca"]] for q in nas_filas if abs(q["x"] - xp) <= TOL_PORTICO}
        if tem != {0, 1}:
            avisos.append("pórtico %d (x = %s m): falta o pilar da fila %s" % (k + 1, fmt((xp - x0) / 1000, 3), "B" if tem == {0} else "A"))
    for q in nas_filas:
        xp = min(porticos, key=lambda v: abs(v - q["x"]))
        if 20 < abs(q["x"] - xp) <= TOL_PORTICO:
            avisos.append("pilar %s a %s cm do eixo do pórtico: fica no eixo" % (q["marca"], fmt(abs(q["x"] - xp) / 10, 0)))
        if 20 < abs(q["y"] - (yA, yB)[fila[q["marca"]]]):
            avisos.append("pilar %s a %s cm da linha da fila %s: fica na linha" % (q["marca"], fmt(abs(q["y"] - (yA, yB)[fila[q["marca"]]]) / 10, 0), "AB"[fila[q["marca"]]]))
    vaos = [round((b - a) / 1000.0, 3) for a, b in zip(porticos, porticos[1:])]
    topoA = _mediana([q["topo"] for q in nas_filas if fila[q["marca"]] == 0])
    topoB = _mediana([q["topo"] for q in nas_filas if fila[q["marca"]] == 1])
    for j, topo in ((0, topoA), (1, topoB)):
        fora = [q for q in nas_filas if fila[q["marca"]] == j and abs(q["topo"] - topo) > 20]
        if fora:
            avisos.append("fila %s: %d pilar(es) com o topo fora do nível da fila (%s m): %s" % (
                "AB"[j], len(fora), fmt(topo / 1000, 2), ", ".join(q["marca"] for q in fora[:5])))
    altura = round((topoA - z0) / 1000.0, 3)
    altura_b = round((topoB - z0) / 1000.0, 3) if abs(topoB - topoA) > 20 else 0.0
    # os pilares de oitão: entre as filas, num pórtico das pontas
    oitao = []
    for q in pil:
        if q["marca"] in fila:
            continue
        k = min(range(len(porticos)), key=lambda i: abs(porticos[i] - q["x"]))
        if k in (0, len(porticos) - 1) and abs(porticos[k] - q["x"]) <= TOL_PORTICO and yA < q["y"] < yB:
            oitao.append((k + 1, round((q["y"] - yA) / 1000.0, 3)))
        else:
            avisos.append("pilar %s fora das filas e dos oitões (x = %s m, y = %s m): fica de fora" % (
                q["marca"], fmt((q["x"] - x0) / 1000, 2), fmt((q["y"] - yA) / 1000, 2)))
    # as seções: as lançadas (h na direção do vão, o Y; a rotação de 90° troca)
    secoes = []
    for q in pil:
        if q["secao"] is None:
            avisos.append("pilar %s sem seção retangular: entra com as seções candidatas do projeto" % q["marca"])
            continue
        b, h = q["secao"]
        if q["rot"] % 180 >= 45:
            b, h = h, b
        if (b, h) not in secoes:
            secoes.append((b, h))
    # as bases dos pilares: o comprimento embutido é do cálice (calculado), mas o nível lançado fica anotado
    bases = sorted({round(q["base"]) for q in pil})
    if len(bases) > 1:
        avisos.append("os pilares foram lançados com bases em %d níveis (%s): o embutimento no cálice é o calculado" % (
            len(bases), ", ".join(fmt(b / 1000, 2) for b in bases)))
    # as vigas
    long_sec, cob_sec, calha = [], [], False
    for el in els:
        if el["elemento"] == "tesoura":
            s = el["atributos"].get("secao") or {}
            sec = (float(s.get("bf") or 0), float(s.get("hf") or 0), float(s.get("bw") or 0), float(s.get("h") or 0))
            if all(sec) and sec not in cob_sec:
                cob_sec.append(sec)
            continue
        if el["elemento"] != "viga":
            continue
        a, e = el["atributos"], el["entidade"]
        pa, pb = getattr(e, "a", None), getattr(e, "b", None)
        if pa is None or pb is None:
            continue
        s = a.get("secao") or {}
        ao_longo = abs(pb[1] - pa[1]) <= TOL_LINHA and (abs(pa[1] - yA) <= TOL_LINHA or abs(pa[1] - yB) <= TOL_LINHA)
        cruza = abs(pb[0] - pa[0]) <= TOL_PORTICO and min(pa[1], pb[1]) <= yA + TOL_LINHA and max(pa[1], pb[1]) >= yB - TOL_LINHA
        if a.get("material", "concreto") != "concreto":
            avisos.append("viga %s de aço: não entra no cálculo do pré-moldado (a cobertura metálica é carga)" % a.get("marca", el["id"]))
            continue
        if ao_longo:
            if s.get("tipo") == "U":
                calha = True
                sec = (float(s.get("B") or 0), float(s.get("h") or 0), float(s.get("t") or 0), float(s.get("tf") or 0))
                if all(sec) and sec not in long_sec:
                    long_sec.append(sec)
            else:
                sec = (float(s.get("b") or s.get("bw") or 0), float(s.get("h") or 0))
                if all(sec) and sec not in long_sec:
                    long_sec.append(sec)
        elif cruza:
            sec = (float(s.get("bf") or s.get("b") or 0), float(s.get("hf") or 0), float(s.get("bw") or s.get("b") or 0), float(s.get("h") or 0))
            if all(sec) and sec not in cob_sec:
                cob_sec.append(sec)
            elif s.get("tipo") == "retangular" and s.get("b") and s.get("h"):
                avisos.append("viga de cobertura %s retangular: o cálculo usa a seção I candidata do projeto" % a.get("marca", el["id"]))
        else:
            avisos.append("viga %s nem ao longo das filas nem de A a B: fica de fora" % a.get("marca", el["id"]))
    # os consolos
    cons_h, cons_a = [], []
    for el in els:
        if el["elemento"] != "consolo":
            continue
        a, e = el["atributos"], el["entidade"]
        pts = getattr(e, "vertices", None) or []
        if len(pts) >= 4:
            c = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
            cons_a.append(c / 2.0)
        if a.get("altura"):
            cons_h.append(float(a["altura"]))
    # as fundações
    tipos = {str((el["atributos"].get("tipo") or "sapata")) for el in els if el["elemento"] == "fundacao"}
    d = dataclasses.replace(base) if base is not None else DadosGalpaoPM()
    d.vao = round((yB - yA) / 1000.0, 3)
    d.vaos_longitudinais = vaos
    d.altura_pilar = altura
    d.altura_pilar_b = altura_b
    d.cobertura = "uma água" if altura_b else d.cobertura
    d.pilares_oitao = sorted(oitao)
    # o elemento da planta de cada pilar do galpão, pelo eixo (o mesmo nome que o 3D e a locação usam)
    origem = {}
    for q in pil:
        if q["marca"] in fila:
            k = min(range(len(porticos)), key=lambda i: abs(porticos[i] - q["x"]))
            origem["%d/%s" % (k + 1, "AB"[fila[q["marca"]]])] = {"id": q["id"], "marca": q["marca"]}
        else:
            k = min(range(len(porticos)), key=lambda i: abs(porticos[i] - q["x"]))
            if k in (0, len(porticos) - 1) and yA < q["y"] < yB:
                origem["%d/oitão %s" % (k + 1, fmt(round((q["y"] - yA) / 1000.0, 3), 2))] = {"id": q["id"], "marca": q["marca"]}
    d.origem_planta = origem
    if secoes:
        d.secoes_pilar = sorted(secoes, key=lambda s_: (s_[0] * s_[1], s_[1]))
    if long_sec:
        d.vigas_longitudinais = "calha" if calha else "travamento"
        if calha:
            d.secoes_calha = long_sec
        else:
            d.secoes_travamento = long_sec
    elif base is None:
        d.vigas_longitudinais = "nenhuma"
    if cob_sec:
        d.viga_cobertura = True
        d.secoes_viga_cobertura = cob_sec
    if cons_h:
        d.consolo_altura = round(max(cons_h) / 10.0, 1)
    if cons_a:
        d.consolo_a = round(max(cons_a) / 10.0, 1)
    if tipos:
        d.fundacao = "estacas" if "bloco" in tipos else "sapata"
    if d.vigas_longitudinais != "nenhuma" and not cons_h:
        avisos.append("vigas longitudinais lançadas sem consolo na planta: o consolo fica com %s cm de altura e a = %s cm" % (
            fmt(d.consolo_altura, 0), fmt(d.consolo_a, 0)))
    d.validar()
    resumo = "%d pilares nas filas (%d pórticos), %d de oitão; topo A +%s m%s; seções %s" % (
        len(nas_filas), len(porticos), len(oitao), fmt(altura, 2), (", B +%s m (uma água)" % fmt(altura_b, 2)) if altura_b else "",
        ", ".join("%s×%s" % (fmt(b, 0), fmt(h, 0)) for b, h in d.secoes_pilar))
    return d, [resumo] + avisos


def deslocamento(des: Desenho) -> Tuple[float, float]:
    """(x, y) em mm do pilar 1/A na planta: o 3D do galpão nasce com o 1/A em (0, 0), e a planta pode
    ter os eixos noutro lugar"""
    pil = [_centro(el) for el in elementos(des) if el["elemento"] == "pilar"]
    pil = [c for c in pil if c is not None]
    if not pil:
        return 0.0, 0.0
    linhas = _agrupar([c[1] for c in pil], TOL_LINHA)
    yA = _media(linhas[0])
    return min(c[0] for c in pil), yA
