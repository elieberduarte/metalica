# -*- coding: utf-8 -*-
"""Os painéis solares em cima da telha.

Pedido do usuário (21/10/2026, Posto V2): o executivo com "suportes, chapas, telhas, painéis solares". O projetista dá a
PAGINAÇÃO DOS PAINÉIS SOLARES (folha 12: "350 PAINÉIS SOLARES - PLACAS 1200 X 2450mm"), os retângulos das placas em
planta. Cada placa assenta no plano da telha debaixo dela: a altura de cada canto pela chapa de telha lançada (a crista
das ondas) mais a do trilho; a placa é plana (o plano pelos cantos, erguido até nenhum canto ficar abaixo do trilho).

Apontamentos (o que não encaixa vai para o projetista):
- a placa com parte fora da telha (passando da cobertura, em cima da abertura);
- a placa em cima de duas águas (a cumeeira ou o vale debaixo dela: a placa não fica plana na telha);
- a placa em cima da calha ou da cumeeira (a peça debaixo da placa, sem acesso para limpar/trocar);
- duas placas uma em cima da outra.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from nucleo3d.modelo import Camada, Solido

CAMADA = "Painéis solares"
COR = "#1e3a8a"
#: mm da crista da telha à face de baixo da placa: o grampo na onda e o trilho de alumínio (perfil de ~40 mm)
ALTURA_TRILHO = 60.0
#: mm: a placa com a moldura
ESPESSURA = 35.0
#: a diferença de inclinação (m/m) entre as chapas debaixo da placa que é outra água
OUTRA_AGUA = 0.02
#: fração da área da placa fora da telha que vira apontamento
FORA_MAX = 0.02


def _planos_das_telhas(doc):
    """[(polígono em planta, a, b, c)] de cada chapa de telha lançada: o plano z = a·x + b·y + c pela crista das ondas.
    A telha cai no sentido perpendicular à terça debaixo dela (a mais perto): o plano é ajustado só nesse sentido — o
    plano livre pelos vértices, na chapa estreita (140 mm de largura no Posto V2), pegava a onda como caída de lado (7 %)."""
    from shapely.geometry import LineString, MultiPoint
    from shapely.strtree import STRtree
    import numpy as np
    tercas = [b for b in doc.barras if b.papel in ("terça", "terca") and math.dist(b.inicio[:2], b.fim[:2]) > 1.0]
    arv_t = STRtree([LineString([b.inicio[:2], b.fim[:2]]) for b in tercas]) if tercas else None
    out = []
    for s in doc.solidos:
        at = s.atributos or {}
        if not at.get("telha_lancada") or at.get("fechamento") or at.get("revestimento") or s.camada != "Telhas":
            continue
        P = np.asarray([v[:3] for v in s.vertices], dtype=float)
        if len(P) < 3:
            continue
        pg = MultiPoint([tuple(v[:2]) for v in P]).convex_hull
        if pg.area <= 1.0:
            continue
        x0, y0 = P[:, 0].mean(), P[:, 1].mean()
        if arv_t is not None:
            t = tercas[int(arv_t.nearest(pg.centroid))]
            L = math.dist(t.inicio[:2], t.fim[:2])
            n = (-(t.fim[1] - t.inicio[1]) / L, (t.fim[0] - t.inicio[0]) / L)
            u = (P[:, 0] - x0) * n[0] + (P[:, 1] - y0) * n[1]
            if np.ptp(u) > 1.0:
                inc, c0 = np.polyfit(u, P[:, 2], 1)
                a, b = inc * n[0], inc * n[1]
            else:
                a = b = 0.0
                c0 = float(P[:, 2].mean())
        else:
            M = np.c_[P[:, 0] - x0, P[:, 1] - y0, np.ones(len(P))]
            (a, b, c0), *_r = np.linalg.lstsq(M, P[:, 2], rcond=None)
        c = float(c0 - a * x0 - b * y0)
        c += float((P[:, 2] - (a * P[:, 0] + b * P[:, 1] + c)).max())
        out.append((pg, float(a), float(b), c))
    return out


def lancar(doc, placas: Sequence[Sequence[Tuple[float, float]]], altura: float = ALTURA_TRILHO,
           espessura: float = ESPESSURA, largura: float = 1200.0, comprimento: float = 2450.0,
           camada: str = CAMADA) -> dict:
    """Lança as placas (cada uma os 4 cantos em planta, mm do modelo) em cima das telhas de `doc` (tira as lançadas antes
    por aqui). Devolve o resumo e os apontamentos."""
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree
    for i in [e.id for e in doc.solidos if (e.atributos or {}).get("painel_solar_lancado")]:
        doc.remover(i)
    if camada not in doc.camadas:
        doc.camadas[camada] = Camada(nome=camada, cor=COR)
    planos = _planos_das_telhas(doc)
    arv = STRtree([p[0] for p in planos]) if planos else None
    pecas = []
    for s in doc.solidos:
        if s.camada in ("Calhas", "Cumeeiras") and s.vertices:
            from shapely.geometry import MultiPoint
            pg = MultiPoint([v[:2] for v in s.vertices]).convex_hull
            if pg.area > 1.0:
                pecas.append((pg, "calha" if s.camada == "Calhas" else "cumeeira"))
    arv_pecas = STRtree([p[0] for p in pecas]) if pecas else None
    telhado = None
    if planos:
        from shapely.ops import unary_union
        telhado = unary_union([p[0] for p in planos]).buffer(5.0)

    def plano_em(x, y):
        """o plano de telha mais alto que cobre (x, y) (até 5 mm da borda da chapa)"""
        if arv is None:
            return None
        pt = Point(x, y)
        melhor = None
        for i in arv.query(pt.buffer(5.0)):
            pg, a, b, c = planos[i]
            if pg.distance(pt) > 5.0:
                continue
            z = a * x + b * y + c
            if melhor is None or z > melhor[0]:
                melhor = (z, a, b)
        return melhor

    apont: List[dict] = []
    feitas: List[Tuple[object, int]] = []
    area = 0.0
    for k, cantos in enumerate(placas, start=1):
        cs = [(float(p[0]), float(p[1])) for p in cantos][:4]
        if len(cs) < 4:
            continue
        pg = Polygon(cs)
        if not pg.is_valid or pg.area < 1.0:
            continue
        if pg.exterior.is_ccw is False:
            cs = cs[::-1]
            pg = Polygon(cs)
        cx, cy = pg.centroid.x, pg.centroid.y
        amostras = cs + [(cx, cy)] + [((cs[i][0] + cs[(i + 1) % 4][0]) / 2, (cs[i][1] + cs[(i + 1) % 4][1]) / 2) for i in range(4)]
        achados = [(x, y, plano_em(x, y)) for x, y in amostras]
        com = [(x, y, p_) for x, y, p_ in achados if p_ is not None]
        if not com:
            apont.append({"tipo": "fora", "placa": k, "ponto": [round(cx), round(cy)], "fora_pct": 100})
            continue
        fora = pg.difference(telhado).area / pg.area if telhado is not None else 1.0
        if fora > FORA_MAX:
            apont.append({"tipo": "fora", "placa": k, "ponto": [round(cx), round(cy)], "fora_pct": round(100 * fora)})
        incl = [(p_[1], p_[2]) for _x, _y, p_ in com]
        if max(abs(a1 - a2) + abs(b1 - b2) for a1, b1 in incl for a2, b2 in incl) > OUTRA_AGUA:
            apont.append({"tipo": "duas_aguas", "placa": k, "ponto": [round(cx), round(cy)]})
        if arv_pecas is not None:
            for i in arv_pecas.query(pg):
                if pecas[i][0].intersection(pg).area > 0.01 * pg.area:
                    apont.append({"tipo": "sobre_" + pecas[i][1], "placa": k, "ponto": [round(cx), round(cy)]})
                    break
        # o plano da placa pelos pontos achados (mínimos quadrados), erguido até nenhum ficar abaixo do trilho
        import numpy as np
        X = np.asarray([[x - cx, y - cy, 1.0] for x, y, _p in com])
        Z = np.asarray([p_[0] + altura for _x, _y, p_ in com])
        if len(com) >= 3 and np.linalg.matrix_rank(X) == 3:
            (a, b, c), *_r = np.linalg.lstsq(X, Z, rcond=None)
        else:
            a, b, c = com[0][2][1], com[0][2][2], 0.0
            c = float(max(Z - (a * X[:, 0] + b * X[:, 1])))
        c += float(max(0.0, (Z - (a * X[:, 0] + b * X[:, 1] + c)).max()))
        base = [(x, y, a * (x - cx) + b * (y - cy) + c) for x, y in cs]
        vs = base + [(x, y, z + espessura) for x, y, z in base]
        fs = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        so = Solido(nome="Painel solar %d×%d mm" % (round(largura), round(comprimento)), camada=camada, vertices=vs, faces=fs)
        so.atributos = {"tipo_ifc": "IfcSolarDevice", "painel_solar_lancado": True, "placa": k,
                        "largura": round(largura), "comprimento": round(comprimento),
                        "altura_trilho": round(altura), "inclinacao_pct": round(100.0 * math.hypot(a, b), 1)}
        doc.add(so)
        area += pg.area
        for pg2, k2 in feitas:
            if pg2.intersection(pg).area > 0.01 * pg.area:
                apont.append({"tipo": "sobreposta", "placa": k, "outra": k2, "ponto": [round(cx), round(cy)]})
        feitas.append((pg, k))
    return {"placas": len(feitas), "area_m2": round(area / 1e6, 1), "apontamentos": apont,
            "por_tipo": {t: sum(1 for a_ in apont if a_["tipo"] == t) for t in sorted({a_["tipo"] for a_ in apont})}}
