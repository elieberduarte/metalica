# -*- coding: utf-8 -*-
"""Os suportes de terça como o projetista os detalha (23/10/2026, Posto CB: "SUPORTE DE TERÇA ST1 - 400X" e "ST2 - 72X";
decisão do usuário: os do projeto, no lugar do L 3" padrão).

O detalhe desenha, em tamanho real, a vista frontal (a chapa 150 × 90, com os furos oblongos 12,7 × 25 em arcos) e a
vista lateral (a chapa #3,0 e a nervura atrás dela, 70 × 85 com o chanfro da solda). No 3D, cada terça que apoia num
banzo ganha o suporte ali: a chapa em pé, encostada nas costas da alma da terça (parafusada por ela), soldada no topo do
banzo, e a nervura do outro lado. O suporte é o do detalhe cuja altura casa com a da terça (a chapa 10 mm mais baixa
que a alma: 90 na U 100, 120 na U 127). A terça erguida acima do banzo (a da calha, no plano da água) leva a chapa
mais alta, até o banzo — `a_conferir`."""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence

_TITULO = re.compile(r"(?i)^\s*SUPORTE\s+DE\s+TER[ÇC]A\s+(ST\s*\d+[A-Z]?)\s*-\s*(\d+)\s*X")
_ESPESSURA = re.compile(r"(?i)CHAPAS?\s*#\s*([\d,.]+)\s*mm")
#: mm: a folga entre a terça e o banzo que ainda é o apoio dela (acima disso, a terça erguida ao plano da água)
FOLGA_APOIO = 15.0


def detalhes(ents: Sequence[dict]) -> Dict[str, dict]:
    """{"ST1": {qtd, B, H, t, furos: [{x, y, largura, altura}], nervura: [(x, y)]}} — a vista frontal (o retângulo logo
    acima do título, à esquerda) e a nervura da vista lateral (o polígono à direita, da altura da chapa menos o recuo)"""
    tits = [(e, _TITULO.match(str(e.get("texto") or ""))) for e in ents if e.get("tipo") == "texto"]
    tits = [(e, m) for e, m in tits if m]
    if not tits:
        return {}
    polis = [e for e in ents if e.get("tipo") == "polilinha" and len(e.get("vertices") or []) >= 4]
    arcos = [e for e in ents if e.get("tipo") in ("arco", "circulo")]
    textos = [e for e in ents if e.get("tipo") == "texto"]
    out: Dict[str, dict] = {}
    for t, m in tits:
        tx, ty = t["posicao"][0], t["posicao"][1]
        frente = []
        for e in polis:
            if not e.get("fechada") or len(e["vertices"]) not in (4, 5):
                continue
            xs, ys = [v[0] for v in e["vertices"]], [v[1] for v in e["vertices"]]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if -50.0 <= min(xs) - tx <= 300.0 and 200.0 <= min(ys) - ty <= 700.0 and 80.0 <= w <= 400.0 and 50.0 <= h <= 300.0:
                frente.append((min(xs), min(ys), max(xs), max(ys)))
        if not frente:
            continue
        x0, y0, x1, y1 = max(frente, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        B, H = x1 - x0, y1 - y0
        # os oblongos: os dois arcos de cada um, na mesma altura, a menos de 30 mm um do outro
        cs = sorted((a["centro"][0], a["centro"][1], float(a.get("raio") or 0)) for a in arcos
                    if x0 < a["centro"][0] < x1 and y0 < a["centro"][1] < y1)
        furos, usados = [], set()
        for i, (ax, ay, ar) in enumerate(cs):
            if i in usados:
                continue
            par = next((j for j in range(i + 1, len(cs)) if j not in usados and abs(cs[j][1] - ay) < 1.0
                        and 0.5 < cs[j][0] - ax < 30.0 and abs(cs[j][2] - ar) < 0.5), None)
            if par is None:
                furos.append({"x": round(ax - x0, 1), "y": round(ay - y0, 1), "diametro": round(2 * ar, 1)})
                continue
            usados.update((i, par))
            bx = cs[par][0]
            furos.append({"x": round((ax + bx) / 2 - x0, 1), "y": round(ay - y0, 1),
                          "largura": round(bx - ax + 2 * ar, 1), "altura": round(2 * ar, 1)})
        # a nervura: o polígono da vista lateral (à direita), de 6 vértices, mais baixo que a chapa
        nerv = None
        for e in polis:
            vs = []
            for v in e["vertices"]:                     # sem o ponto repetido (o fechamento desenhado)
                if not vs or math.dist(vs[-1], (v[0], v[1])) > 0.5:
                    vs.append((v[0], v[1]))
            if len(vs) > 3 and math.dist(vs[0], vs[-1]) < 0.5:
                vs.pop()
            if len(vs) != 6:
                continue
            xs, ys = [v[0] for v in vs], [v[1] for v in vs]
            if not (300.0 <= min(xs) - x1 <= 900.0 and abs(min(ys) - y0) < 20.0 and max(xs) - min(xs) <= 150.0
                    and H - 30.0 <= max(ys) - min(ys) <= H):
                continue
            nx0, ny0, nx1 = min(xs), min(ys), max(xs)
            alto_esq = max(v[1] for v in vs if v[0] - nx0 < 1.0)
            alto_dir = max(v[1] for v in vs if nx1 - v[0] < 1.0)
            nerv = ([(round(v[0] - nx0, 1), round(v[1] - ny0, 1)) for v in vs] if alto_esq >= alto_dir
                    else [(round(nx1 - v[0], 1), round(v[1] - ny0, 1)) for v in reversed(vs)])
            break
        esp = [(math.dist((x0, y0), e["posicao"][:2]), _ESPESSURA.search(e["texto"])) for e in textos
               if abs(e["posicao"][0] - tx) < 600.0 and abs(e["posicao"][1] - ty) < 700.0 and _ESPESSURA.search(e["texto"])]
        t_mm = float(min(esp, key=lambda q: q[0])[1].group(1).replace(",", ".")) if esp else None
        out[re.sub(r"\s+", "", m.group(1)).upper()] = {"qtd": int(m.group(2)), "B": round(B, 1), "H": round(H, 1), "t": t_mm,
                                                        "furos": furos, "nervura": nerv}
    return out


def _cruzamento(a, b, c, d):
    """o ponto em planta onde a reta ab cruza o segmento cd, com o parâmetro em cada um, ou None"""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    q = (c[0] - a[0], c[1] - a[1])
    t = (q[0] * s[1] - q[1] * s[0]) / den
    u = (q[0] * r[1] - q[1] * r[0]) / den
    if not (-0.001 <= t <= 1.001 and -0.001 <= u <= 1.001):
        return None
    return t, u


def lancar(doc, tercas: Sequence, apoios: Sequence, dets: Dict[str, dict], aco: str, chapas_postas: list,
           avisos: List[str]) -> dict:
    """um suporte do detalhe em cada apoio de terça em banzo (o cruzamento em planta, com a terça logo acima dele)"""
    from nucleo3d.geometria import base_local, secao
    from nucleo3d.modelo import Chapa
    from nucleo3d.de_planta import _perfil
    if not dets:
        return {"suportes": 0}

    def z_de(e, t):
        return e.inicio[2] + (e.fim[2] - e.inicio[2]) * t

    def ext(e):
        """(u, v, zmin, zmax, xmin) da seção no mundo: o fundo e o topo da peça, e as costas da alma ao longo de u"""
        p = _perfil(e.perfil)
        d = tuple(e.fim[i] - e.inicio[i] for i in range(3))
        u, v, _w = base_local(d, e.rotacao or 0.0)
        if p is None:
            return u, v, -50.0, 50.0, -20.0, None
        sec = secao(p)
        zs = [u[2] * x + v[2] * y for x, y in sec]
        return u, v, min(zs), max(zs), min(x for x, _y in sec), p

    n = 0
    postos: List[tuple] = []                           # (x, y, z) de cada suporte: a emenda de duas terças leva um só
    por_nome: Dict[str, int] = {}
    erguidos = 0
    grade: Dict[tuple, list] = {}
    for b in apoios:
        (x0, y0), (x1, y1) = b.inicio[:2], b.fim[:2]
        for gx in range(int(min(x0, x1) // 3000), int(max(x0, x1) // 3000) + 1):
            for gy in range(int(min(y0, y1) // 3000), int(max(y0, y1) // 3000) + 1):
                grade.setdefault((gx, gy), []).append(b)
    for t in tercas:
        u, v, zb_t, zt_t, xmin_t, pt = ext(t)
        if pt is None or abs(u[2]) > 0.3:
            continue                                   # a terça de alma deitada não tem onde parafusar o suporte
        d_t = float(pt.d or 100.0)
        nome = min(dets, key=lambda k: abs(dets[k]["H"] - (d_t - 10.0)))
        dt = dets[nome]
        L_t = math.dist(t.inicio, t.fim)
        if L_t < 1.0:
            continue
        ex = tuple((t.fim[i] - t.inicio[i]) / L_t for i in range(3))
        exh = math.hypot(ex[0], ex[1]) or 1.0
        exh = (ex[0] / exh, ex[1] / exh, 0.0)
        cand = set()
        for gx in range(int(min(t.inicio[0], t.fim[0]) // 3000), int(max(t.inicio[0], t.fim[0]) // 3000) + 1):
            for gy in range(int(min(t.inicio[1], t.fim[1]) // 3000), int(max(t.inicio[1], t.fim[1]) // 3000) + 1):
                cand.update(id(b) for b in grade.get((gx, gy), []))
        # os cruzamentos com os apoios abaixo da terça; no mesmo ponto (o caixão de dois U, o par), o mais alto
        cruz = []
        for b in apoios:
            if id(b) not in cand or b is t:
                continue
            cr = _cruzamento(t.inicio, t.fim, b.inicio, b.fim)
            if cr is None:
                continue
            tt, ub = cr
            _ub, _vb, _zb, zt_b, _x, _p = ext(b)
            topo_b = z_de(b, ub) + zt_b
            folga = z_de(t, tt) + zb_t - topo_b
            if not (-FOLGA_APOIO <= folga <= 400.0):
                continue
            cruz.append(((t.inicio[0] + (t.fim[0] - t.inicio[0]) * tt, t.inicio[1] + (t.fim[1] - t.inicio[1]) * tt), topo_b, folga))
        vistos = []
        for p, topo_b, folga in sorted(cruz, key=lambda c_: c_[2]):
            if any(math.dist(p, q) < 100.0 for q in vistos):
                continue                                # o caixão (dois U) ou o par: um suporte só, no de cima
            vistos.append(p)
            if any(math.dist(p, q[:2]) < 250.0 and abs(topo_b - q[2]) < 50.0 for q in postos):
                continue                                # a outra terça da emenda: o mesmo suporte (dois furos de cada lado)
            postos.append((p[0], p[1], topo_b))
            erguida = folga > FOLGA_APOIO
            H = dt["H"] + (folga if erguida else 0.0)
            tch = dt["t"] or 3.0
            # a chapa encosta nas costas da alma da terça: do eixo dela, xmin ao longo de u, mais meia chapa
            off = xmin_t - tch / 2.0
            uh = (u[0], u[1], 0.0)
            centro = (p[0] + uh[0] * off, p[1] + uh[1] * off)
            org = (centro[0] - exh[0] * dt["B"] / 2.0, centro[1] - exh[1] * dt["B"] / 2.0, topo_b)
            o = {"locacao": nome, "suporte": nome, "terca": (getattr(t, "atributos", None) or {}).get("origem", {}).get("sigla")}
            if erguida:
                o["a_conferir"] = "a terça sobe %.0f mm acima do banzo (plano da água): %s mais alto (%.0f)" % (folga, nome, H)
                erguidos += 1
            ch = Chapa(nome="Suporte de terça %s" % nome, origem=org, eixo_x=exh, eixo_y=(0.0, 0.0, 1.0),
                       contorno=[(0.0, 0.0), (dt["B"], 0.0), (dt["B"], H), (0.0, H)], espessura=tch, centrada=True,
                       furos=[dict(f, y=f["y"] + (folga if erguida else 0.0)) for f in dt["furos"]], aco=aco)
            ch.camada = "Chapas"
            ch.atributos = {"tipo_ifc": "IfcPlate", "origem": o}
            doc.add(ch)
            chapas_postas.append(ch)
            if dt.get("nervura"):
                # a nervura no meio da chapa, do outro lado da terça
                fora = (-uh[0], -uh[1], 0.0)
                base_n = (centro[0] + fora[0] * tch / 2.0, centro[1] + fora[1] * tch / 2.0, topo_b)
                nv = Chapa(nome="Nervura do suporte %s" % nome, origem=base_n, eixo_x=fora, eixo_y=(0.0, 0.0, 1.0),
                           contorno=[tuple(q) for q in dt["nervura"]], espessura=tch, centrada=True, aco=aco)
                nv.camada = "Chapas"
                nv.atributos = {"tipo_ifc": "IfcPlate", "origem": dict(o, nervura=True)}
                doc.add(nv)
                chapas_postas.append(nv)
            n += 1
            por_nome[nome] = por_nome.get(nome, 0) + 1
    for k, q in sorted(por_nome.items()):
        if dets[k]["qtd"] and abs(q - dets[k]["qtd"]) > 0:
            avisos.append("Suportes de terça: %d %s no modelo e o detalhe diz %dX — confira." % (q, k, dets[k]["qtd"]))
    if erguidos:
        avisos.append("Suportes de terça: %d mais altos que o detalhe, onde a terça sobe ao plano da água." % erguidos)
    return {"suportes": n, "por_nome": por_nome, "erguidos": erguidos}
