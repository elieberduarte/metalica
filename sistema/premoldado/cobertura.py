# -*- coding: utf-8 -*-
"""A cobertura de outra obra (a metálica, calculada no programa) dentro do 3D do galpão pré-moldado, para
conferir o encaixe, e os níveis do galpão no 3D.

O alinhamento é pelos eixos das duas obras: o eixo numerado "1" da obra da cobertura cai no eixo 1 do galpão
(X = 0, os numerados ao longo de X) e as duas linhas de apoio das tesouras (os nós apoiados do cálculo da
cobertura) caem nas filas A (Y = 0) e B; o z fica o da obra da cobertura, com o ±0,00 dela na boca do cálice.
A conferência compara cada apoio das tesouras com o pilar mais perto: a distância em planta e o desnível
até o topo do pilar.
"""
from __future__ import annotations

import copy
import json
import math
import os
from typing import Dict, List, Optional, Tuple

from nucleo.base import ErroDeDados, fmt
from nucleo3d import eixos as _eixos
from nucleo3d.geometria import girar, mover
from nucleo3d.modelo import Camada, Documento, Grupo

CAMADA_COBERTURA = "Cobertura (obra %s)"
#: o que não ajuda a conferir o encaixe e pesa no 3D
CAMADAS_FORA = {"Parafusos"}


_CACHE: Dict[tuple, list] = {}


def _apoios_do_calculo(pasta: str) -> List[Tuple[float, float, float]]:
    """os nós apoiados das tesouras no cálculo da obra (a reserva quando não há chumbadores)"""
    caminho = os.path.join(pasta, "calculo.json")
    if not os.path.exists(caminho):
        return []
    try:
        c = json.load(open(caminho, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    nos = ((c.get("resultado") or {}).get("portico") or {}).get("nos") or []
    return [tuple(n["p"]) for n in nos if n.get("apoiado") and len(n.get("p") or []) == 3]


def _apoios_dos_chumbadores(pasta: str) -> List[Tuple[float, float, float]]:
    """os apoios pelos chumbadores (os tipos do detalhamento, como a identificação de eixos da Metálica): o
    centro de cada grupo em planta e o nível do topo do concreto — a face de baixo da chapa de base deitada
    sobre o chumbador (sem chapa, o topo do chumbador)"""
    try:
        nomes = json.load(open(os.path.join(pasta, "detalhamento", "nomes.json"), encoding="utf-8"))
        bruto = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    tipos = nomes.get("tipos") or {}
    doc = Documento.de_dict(bruto)
    chumb = [e for e in doc.entidades.values()
             if tipos.get(str(_eixos._marcas(e).get("posicao") or "")) == "chumbador" and _eixos._em_pe(e)]
    if not chumb:
        return []
    chapas = []
    for e in doc.entidades.values():
        vs = _eixos._vertices(e)
        if len(vs) < 4 or e in chumb:
            continue
        zs = [v[2] for v in vs]
        if max(zs) - min(zs) <= 40.0:
            xs, ys = [v[0] for v in vs], [v[1] for v in vs]
            chapas.append((min(xs), max(xs), min(ys), max(ys), min(zs)))
    grupos: List[List[tuple]] = []
    for e in chumb:
        vs = _eixos._vertices(e)
        c = _eixos._centroide(vs)
        item = (c[0], c[1], min(v[2] for v in vs), max(v[2] for v in vs))
        for gr in grupos:
            if math.hypot(gr[0][0] - item[0], gr[0][1] - item[1]) < 400.0:
                gr.append(item)
                break
        else:
            grupos.append([item])
    out = []
    for gr in grupos:
        x = sum(i[0] for i in gr) / len(gr)
        y = sum(i[1] for i in gr) / len(gr)
        z0, z1 = min(i[2] for i in gr), max(i[3] for i in gr)
        sob = [k[4] for k in chapas if k[0] - 5 <= x <= k[1] + 5 and k[2] - 5 <= y <= k[3] + 5 and z0 <= k[4] <= z1 + 300.0]
        out.append((x, y, min(sob) if sob else z1))
    return out


def _apoios(g, slug: str) -> Tuple[List[Tuple[float, float, float]], str]:
    pasta = g.pasta(slug)
    mod = os.path.join(pasta, "modelo.json")
    chave = (slug, os.path.getmtime(mod) if os.path.exists(mod) else 0.0)
    if chave not in _CACHE:
        ap = _apoios_dos_chumbadores(pasta)
        _CACHE[chave] = [ap, "os chumbadores da cobertura (topo do concreto na chapa de base)"] if ap else [
            _apoios_do_calculo(pasta), "os apoios das tesouras no cálculo da cobertura"]
    return _CACHE[chave][0], _CACHE[chave][1]


def alinhamento(g, slug: str) -> dict:
    """a rotação e as translações que levam a obra `slug` ao sistema do galpão, e os apoios já nele"""
    p = g.ler(slug)
    ex = _eixos.de_dict(p.get("eixos"))
    if not ex or not ex["numeros"]:
        raise ErroDeDados("a obra da cobertura (%s) não tem eixos gravados: grave os eixos nela primeiro" % slug)
    gx, gy = ex["eixo_g"]
    px, py = ex["perp_g"]
    pos1 = next((n["pos"] for n in ex["numeros"] if n["nome"] == "1"), ex["numeros"][0]["pos"])
    apoios, fonte = _apoios(g, slug)
    perps = [x * px + y * py for x, y, _z in apoios]
    if perps:
        p0 = min(perps)
    else:
        p0 = min(n["pos"] for n in ex["letras"]) if ex["letras"] else 0.0
        fonte = "o primeiro eixo com letra (a obra da cobertura não tem cálculo gravado)"
    ang = math.degrees(math.atan2(gy, gx))
    ap = [((x * gx + y * gy) - pos1, (x * px + y * py) - p0, z) for x, y, z in apoios]
    return {"obra": slug, "nome": p.get("nome") or slug, "rotacao_graus": -ang, "translacao": (-pos1, -p0, 0.0),
            "apoios": ap, "fonte": fonte, "vao_apoios": (max(perps) - min(perps)) if perps else None}


def trazer(g, slug: str, doc: Documento) -> dict:
    """acrescenta ao `doc` as peças da obra `slug` alinhadas ao galpão (sem os parafusos); devolve o alinhamento"""
    info = alinhamento(g, slug)
    bruto = g.abrir_modelo(slug)
    if not bruto:
        raise ErroDeDados("a obra da cobertura (%s) não tem modelo 3D" % slug)
    cob = Documento.de_dict(bruto)
    camada = CAMADA_COBERTURA % info["nome"]
    doc.camadas[camada] = Camada(nome=camada, cor="#6e8fb8")
    # a cobertura inteira num grupo (o clique no 3D pega ela toda; Alt+clique, uma peça): os grupos que
    # ela já tinha continuam dentro
    grupo = Grupo(nome="Cobertura — %s" % info["nome"], camada=camada, origem=(0.0, 0.0, 0.0))
    trazidos = {e.id for e in cob.entidades.values() if e.camada not in CAMADAS_FORA}
    n = 0
    for e in list(cob.entidades.values()):
        if e.camada in CAMADAS_FORA:
            continue
        if e.tipo == "grupo":
            novo = copy.deepcopy(e)
            novo.filhos = [f for f in novo.filhos if f in trazidos]
            novo.camada = camada
            if not novo.grupo or novo.grupo not in trazidos:
                novo.grupo = grupo.id
                grupo.filhos.append(novo.id)
            doc.add(novo)
            continue
        # girar e mover devolvem uma cópia (nucleo3d não altera a peça no lugar)
        novo = mover(girar(e, (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), info["rotacao_graus"]), info["translacao"])
        novo.atributos = dict(novo.atributos or {}, camada_original=e.camada, obra_cobertura=slug)
        novo.camada = camada
        if not novo.grupo or novo.grupo not in trazidos:
            novo.grupo = grupo.id
            grupo.filhos.append(novo.id)
        doc.add(novo)
        n += 1
    doc.add(grupo)
    info.update({"pecas": n, "camada": camada, "grupo": grupo.id})
    doc.metadados["cobertura"] = {k: v for k, v in info.items() if k != "apoios"}
    return info


def pilares_em_planta(p) -> List[Tuple[str, float, float]]:
    d = p.dados
    xs = [0.0]
    for v in d.vaos_longitudinais:
        xs.append(xs[-1] + v * 1000.0)
    out = [("%d/%s" % (i + 1, l), x, y, z * 1000.0) for i, x in enumerate(xs)
           for l, y, z in (("A", 0.0, d.altura_pilar), ("B", d.vao * 1000.0, d.altura_b))]
    for (eixo, y) in getattr(d, "pilares_oitao", []) or []:
        k = int(eixo) - 1
        if 0 <= k < len(xs):
            out.append(("%d/oitão %s" % (k + 1, fmt(y, 2)), xs[k], y * 1000.0, d.altura_oitao(float(y)) * 1000.0))
    return out


def _agrupar(vals: List[float], gap: float = 500.0) -> List[List[float]]:
    gr: List[List[float]] = []
    for v in sorted(vals):
        if gr and v - gr[-1][-1] <= gap:
            gr[-1].append(v)
        else:
            gr.append([v])
    return gr


def geometria(info: dict) -> dict:
    """o galpão que a cobertura pede: as duas linhas extremas de apoios são as filas A e B (o vão), os apoios
    delas dão os pórticos (os vãos entre eles), o topo do concreto dá a altura dos pilares, e os apoios entre
    as filas, num pórtico da ponta, são pilares de oitão"""
    ap = info["apoios"]
    if len(ap) < 4:
        raise ErroDeDados("a cobertura tem só %d apoios: não dá para tirar o galpão dela" % len(ap))
    linhas = _agrupar([a[1] for a in ap])
    y0, y1 = sum(linhas[0]) / len(linhas[0]), sum(linhas[-1]) / len(linhas[-1])
    principais = [a for a in ap if abs(a[1] - y0) <= 500 or abs(a[1] - y1) <= 500]
    porticos = [sum(g_) / len(g_) for g_ in _agrupar([a[0] for a in principais])]
    x0 = porticos[0]
    vaos = [round((b - a) / 1000.0, 3) for a, b in zip(porticos, porticos[1:])]
    avisos = []
    z_fila = {}
    for nome, yl, fila in (("A", y0, [a for a in principais if abs(a[1] - y0) <= 500]),
                           ("B", y1, [a for a in principais if abs(a[1] - y1) <= 500])):
        fora = max(abs(a[1] - yl) for a in fila)
        if fora > 20:
            avisos.append("fila %s: os apoios variam até %s cm em relação à linha média — os pilares ficam na linha" % (nome, fmt(fora / 10, 0)))
        zf = sorted(a[2] for a in fila)
        z_fila[nome] = zf[len(zf) // 2]
        if zf[-1] - zf[0] > 20:
            avisos.append("fila %s: os apoios estão em alturas diferentes (%s a %s m): adotado %s m" % (
                nome, fmt(zf[0] / 1000, 3), fmt(zf[-1] / 1000, 3), fmt(z_fila[nome] / 1000, 3)))
    z = z_fila["A"]
    zb = z_fila["B"] if abs(z_fila["B"] - z) > 20 else 0.0
    if zb:
        avisos.append("as filas apoiam em alturas diferentes (A %s m, B %s m): cobertura de uma água, inclinação %s° pelas alturas" % (
            fmt(z / 1000, 3), fmt(zb / 1000, 3), fmt(math.degrees(math.atan2(abs(zb - z), y1 - y0)), 2)))
    oitao = []
    for a in ap:
        if a in principais:
            continue
        k = min(range(len(porticos)), key=lambda i: abs(porticos[i] - a[0]))
        if k not in (0, len(porticos) - 1) or abs(porticos[k] - a[0]) > 500:
            avisos.append("apoio em (%s; %s) m fora das filas e dos oitões: fica de fora" % (fmt((a[0] - x0) / 1000, 2), fmt((a[1] - y0) / 1000, 2)))
            continue
        oitao.append((k + 1, round((a[1] - y0) / 1000.0, 3)))
    return {"vao": round((y1 - y0) / 1000.0, 3), "vaos_longitudinais": vaos, "altura_pilar": round(z / 1000.0, 3),
            "altura_pilar_b": round(zb / 1000.0, 3), "cobertura": "uma água" if zb else "duas águas",
            "pilares_oitao": sorted(oitao), "avisos": avisos, "deslocamento_x": x0, "fonte": info.get("fonte")}


def conferir(info: dict, pilares: List[tuple], topo_mm: float, vao_mm: float) -> List[str]:
    """os apontamentos do encaixe: o vão entre as linhas de apoio contra o do galpão; cada apoio contra o pilar
    mais perto (distância em planta e o desnível até o topo). `pilares`: (marca, x, y[, topo_mm de cada um]);
    com o topo de cada pilar, o desnível é conferido pilar a pilar; sem ele, contra `topo_mm`"""
    out = []
    por_pilar = bool(pilares) and len(pilares[0]) > 3 and len({round(q[3]) for q in pilares}) > 1
    linhas = _agrupar([a[1] for a in info["apoios"]])
    vao_c = (sum(linhas[-1]) / len(linhas[-1]) - sum(linhas[0]) / len(linhas[0])) if len(linhas) > 1 else info.get("vao_apoios")
    if vao_c is not None and abs(vao_c - vao_mm) > 20:
        out.append("o vão entre os apoios das tesouras (%s m) difere do vão do galpão (%s m)" % (fmt(vao_c / 1000, 3), fmt(vao_mm / 1000, 3)))
    zs = sorted({round(z) for _x, _y, z in info["apoios"]})
    if zs:
        grupos = []
        for z in zs:
            if not grupos or z - grupos[-1][-1] > 150:
                grupos.append([z])
            else:
                grupos[-1].append(z)
        niveis = [sum(g_) / len(g_) for g_ in grupos]
        if len(niveis) > 1 and not por_pilar:
            out.append("a cobertura se apoia em %d níveis (%s m): o galpão tem os pilares todos com o topo a %s m"
                       % (len(niveis), " e ".join(fmt(z / 1000, 2) for z in niveis), fmt(topo_mm / 1000, 2)))
        if not por_pilar:
            for z in niveis:
                dz = topo_mm - z
                if abs(dz) > 50:
                    out.append("apoio da cobertura a %s m: o topo dos pilares (%s m) fica %s m %s" % (
                        fmt(z / 1000, 2), fmt(topo_mm / 1000, 2), fmt(abs(dz) / 1000, 2), "acima — o pilar atravessaria a cobertura"
                        if dz > 0 else "abaixo — falta apoio"))
    longe = []
    desnivel = []
    for x, y, z in info["apoios"]:
        q = min(pilares, key=lambda q_: math.hypot(q_[1] - x, q_[2] - y))
        nome, px_, py_ = q[0], q[1], q[2]
        d = math.hypot(px_ - x, py_ - y)
        if d > 150:
            longe.append((d, nome, x, y))
        elif por_pilar and abs(q[3] - z) > 50:
            desnivel.append((q[3] - z, nome, z))
    for dz, nome, z in sorted(desnivel, key=lambda t: -abs(t[0]))[:6]:
        out.append("apoio da cobertura a %s m no pilar %s: o topo dele (%s m) fica %s m %s" % (
            fmt(z / 1000, 2), nome, fmt((z + dz) / 1000, 2), fmt(abs(dz) / 1000, 2),
            "acima — o pilar atravessaria a cobertura" if dz > 0 else "abaixo — falta apoio"))
    if len(desnivel) > 6:
        out.append("… e mais %d apoios com desnível" % (len(desnivel) - 6))
    if longe:
        pior = max(longe)
        out.append("%d apoio(s) das tesouras a mais de 15 cm do eixo de um pilar (o pior: %s cm do pilar %s)"
                   % (len(longe), fmt(pior[0] / 10, 0), pior[1]))
    return out


def niveis(p, info: Optional[dict] = None) -> List[Dict[str, float]]:
    """os níveis do galpão (mm) para o 3D: boca do cálice, base dos pilares, fundo da fundação, consolos, topo
    dos pilares, apoios da cobertura trazida"""
    d = p.dados
    out = [{"nome": "Boca do cálice", "z": 0.0}]
    if d.filas_diferentes:
        out += [{"nome": "Topo dos pilares — fila A", "z": d.altura_pilar * 1000.0}, {"nome": "Topo dos pilares — fila B", "z": d.altura_b * 1000.0}]
    else:
        out.append({"nome": "Topo dos pilares", "z": d.altura_pilar * 1000.0})
    if p.pilares:
        lemb = max(q.comprimento_total - d.altura_tipo(q.tipo) for q in p.pilares)
        out.append({"nome": "Base dos pilares", "z": -lemb * 1000.0})
        if p.fundacoes:
            hf = max(r.dados.get("hf", 0.0) for r in p.fundacoes)
            out.append({"nome": "Fundo da fundação", "z": -lemb * 1000.0 - hf * 10.0})
    if d.ponte_rolante:
        out.append({"nome": "Consolo da ponte rolante", "z": d.pr_altura * 1000.0})
    vl = next((v for v in p.vigas if v.funcao not in ("viga de cobertura", "terça")), None)
    if vl is not None:
        if d.filas_diferentes:
            out += [{"nome": "Apoio das vigas — fila A", "z": d.altura_pilar * 1000.0 - vl.secao.h * 10 - 10.0},
                    {"nome": "Apoio das vigas — fila B", "z": d.altura_b * 1000.0 - vl.secao.h * 10 - 10.0}]
        else:
            out.append({"nome": "Apoio das vigas", "z": d.altura_pilar * 1000.0 - vl.secao.h * 10 - 10.0})
    if info:
        zs = sorted({round(z) for _x, _y, z in info["apoios"]})
        vistos = []
        for z in zs:
            if not vistos or z - vistos[-1] > 150:
                vistos.append(z)
        for k, z in enumerate(vistos):
            out.append({"nome": "Apoio da cobertura" + (" %d" % (k + 1) if len(vistos) > 1 else ""), "z": float(z)})
    return sorted(out, key=lambda n: n["z"])
