# -*- coding: utf-8 -*-
"""As placas de base como o projetista as detalha (22/10/2026, Posto CB: 82 placas CH1–CH8 da LOC_01, nenhuma no modelo).

A locação desenha cada placa no lugar dela (o contorno na camada de chapa, com o nome "CH1" ao lado); o detalhe
"DET. DO CH1-21X" desenha a mesma placa em tamanho real — a vista de cima com os furos, a espessura ("CHAPA # 3/8\""),
o chumbador ("2 Ø 5/8\"") e, na vista lateral, o comprimento dele. Daqui saem a placa (posição e giro pela locação;
medidas, furos e espessura pelo detalhe) e um chumbador em cada furo. O pilar que nasce na placa começa em cima dela
(o recorte da ponta de baixo, como a placa de base de `ligacoes3d`).

O que o detalhe não diz fica `a_conferir` na peça e vira aviso: a placa da locação com medida diferente da do detalhe
(o texto CH2 sobre o bloco da CH1), o furo desenhado menor que o chumbador, o comprimento do chumbador sem cota."""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

#: o título do detalhe: "DET. DO CH1-21X", "DET. DA C1 - 4X"
_TITULO = re.compile(r"^\s*DET\.?\s*D[AO]\s+(CH\s*\d+[A-Z]?)\s*-\s*(\d+)\s*X", re.I)
#: o título do detalhe da nervura: "NERVURA 1 - 48X"; o nome dela na vista de cima da placa: "NERVURA 1"
_TITULO_NERVURA = re.compile(r"^\s*(NERVURA\s*\d+)\s*-\s*(\d+)\s*X", re.I)
_NOME_NERVURA = re.compile(r"^\s*(NERVURA\s*\d+)\s*$", re.I)
#: o nome da placa na locação
_NOME = re.compile(r"^\s*(CH\s*\d+[A-Z]?)\s*$", re.I)
_ESPESSURA = re.compile(r"CHAPA\s*#\s*([\d/,.]+)\s*(\"|MM)?", re.I)
_CHUMBADOR = re.compile(r"^\s*(\d+)\s*[ØϕΦ]\s*([\d/]+)\s*\"?\s*$")
#: polegadas em fração → mm (a chapa e a barra redonda)
_POL = {"3/16": 4.76, "1/4": 6.35, "5/16": 7.94, "3/8": 9.53, "1/2": 12.7, "5/8": 15.88, "3/4": 19.05, "7/8": 22.23,
        "1": 25.4, "1.1/4": 31.75, "1.1/2": 38.1}
#: mm: a placa da locação e a do detalhe são a mesma com essa diferença nas medidas
TOL_MEDIDA = 15.0
#: mm: a projeção do chumbador acima da placa, além da espessura (2 porcas + arruela, como a placa de ligacoes3d)
PROJECAO_EXTRA = 40.0


def _nome(t: str) -> str:
    return re.sub(r"\s+", "", t).upper()


def _caixa(vs) -> Tuple[float, float, float, float]:
    xs, ys = [v[0] for v in vs], [v[1] for v in vs]
    return min(xs), min(ys), max(xs), max(ys)


def _espessura(txt: str) -> Optional[float]:
    m = _ESPESSURA.search(txt or "")
    if not m:
        return None
    v = m.group(1).replace(",", ".")
    if "/" in v or (m.group(2) or "").startswith('"'):
        return _POL.get(v)
    try:
        return float(v)
    except ValueError:
        return None


def detalhes(ents: Sequence[dict]) -> Dict[str, dict]:
    """{"CH1": {qtd, B, H, t, furos: [(x, y, d)], abertos: [(x, y, w, h)], nervuras, chumbador: {bitola, d, L, n}}}
    — as medidas no canto de baixo da vista de cima (x ao longo de B)."""
    titulos = [(e, _TITULO.match(str(e.get("texto") or ""))) for e in ents if e.get("tipo") == "texto"]
    titulos = [(e, m) for e, m in titulos if m]
    if not titulos:
        return {}
    rets = []
    for e in ents:
        if e.get("tipo") == "polilinha" and e.get("fechada") and len(e.get("vertices") or []) >= 4:
            x0, y0, x1, y1 = _caixa(e["vertices"])
            rets.append((x0, y0, x1, y1))
    circ = [(e["centro"][0], e["centro"][1], 2.0 * float(e["raio"])) for e in ents if e.get("tipo") == "circulo"]
    textos = [e for e in ents if e.get("tipo") == "texto"]
    vistas = []                                          # (nome, qtd, a caixa da vista de cima)
    for t, m in titulos:
        tx, ty = t["posicao"][0], t["posicao"][1]
        # a vista de cima: o retângulo grande logo acima do título, no começo da coluna dele
        cand = [r for r in rets if -250.0 <= r[0] - tx <= 300.0 and 250.0 <= r[1] - ty <= 1600.0
                and r[2] - r[0] >= 100.0 and r[3] - r[1] >= 100.0]
        if cand:
            vistas.append((_nome(m.group(1)), int(m.group(2)), max(cand, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))))

    def dist_caixa(p, r):
        return math.hypot(max(r[0] - p[0], 0.0, p[0] - r[2]), max(r[1] - p[1], 0.0, p[1] - r[3]))

    def da_vista(e, k, alcance=1200.0):
        """o texto é do detalhe k: a vista de cima dele é a mais perto (os detalhes ficam lado a lado na folha)"""
        p = e["posicao"]
        ds = [dist_caixa(p, v[2]) for v in vistas]
        return ds[k] <= alcance and ds[k] <= min(ds) + 1e-6
    cotas = [e for e in textos if re.match(r"^\s*\d{3,4}\s*$", str(e.get("texto") or ""))]
    out: Dict[str, dict] = {}
    for k, (nome, qtd, (x0, y0, x1, y1)) in enumerate(vistas):
        B, H = x1 - x0, y1 - y0
        furos = [(round(cx - x0, 1), round(cy - y0, 1), round(d, 1)) for cx, cy, d in circ
                 if x0 < cx < x1 and y0 < cy < y1]
        dentro = [r for r in rets if r != (x0, y0, x1, y1) and r[0] > x0 - 1 and r[2] < x1 + 1 and r[1] > y0 - 1 and r[3] < y1 + 1]
        abertos = [(round((r[0] + r[2]) / 2 - x0, 1), round((r[1] + r[3]) / 2 - y0, 1), round(r[2] - r[0], 1), round(r[3] - r[1], 1))
                   for r in dentro if min(r[2] - r[0], r[3] - r[1]) >= 40.0]
        nerv = [(r[0] - x0, r[1] - y0, r[2] - x0, r[3] - y0) for r in dentro if min(r[2] - r[0], r[3] - r[1]) < 20.0]
        meus = [e for e in textos if da_vista(e, k)]
        n_nerv = [_nome(_NOME_NERVURA.match(str(e["texto"])).group(1)) for e in meus if _NOME_NERVURA.match(str(e["texto"]))]
        esp = sorted((dist_caixa(e["posicao"], (x0, y0, x1, y1)), _espessura(e["texto"])) for e in meus if _espessura(e["texto"]))
        ch = [(_CHUMBADOR.match(str(e["texto"])), e) for e in meus]
        ch = [(mm, e) for mm, e in ch if mm]
        bitola = (ch[0][0].group(2) + '"') if ch else None
        # o comprimento do chumbador: a cota da vista lateral logo ao lado do texto dele ("2 Ø 5/8\"" e o 400 da CH1, o
        # 500 da CH7 à esquerda, o da CH5 com a vista lateral ao lado da de cima)
        Ls = sorted((min(math.dist(c["posicao"][:2], e["posicao"][:2]) for _mm, e in ch), float(c["texto"])) for c in cotas
                    if ch and 150.0 <= float(c["texto"]) <= 1500.0)
        L = Ls[0][1] if Ls and Ls[0][0] <= 250.0 else None
        out[nome] = {
            "qtd": qtd, "B": round(B, 1), "H": round(H, 1), "t": esp[0][1] if esp else None,
            "furos": furos, "abertos": abertos, "nervuras": nerv, "nervura": n_nerv[0] if n_nerv else None,
            "chumbador": {"bitola": bitola, "d": _POL.get(bitola.rstrip('"')) if bitola else None,
                          "L": L, "n": sum(int(mm.group(1)) for mm, _e in ch) or None},
        }
    return out


def nervuras(ents: Sequence[dict]) -> Dict[str, dict]:
    """{"NERVURA1": {qtd, t, contorno: [(x, y)]}} — o contorno com x a partir da face do pilar (o lado mais alto) e y a
    partir da placa: a NERVURA 1-48X do Posto, 70 × 150 com o chanfro de 15 da solda"""
    polis = [[(v[0], v[1]) for v in e["vertices"]] for e in ents
             if e.get("tipo") == "polilinha" and e.get("fechada") and 5 <= len(e.get("vertices") or []) <= 12]
    textos = [e for e in ents if e.get("tipo") == "texto"]
    out: Dict[str, dict] = {}
    for t in textos:
        m = _TITULO_NERVURA.match(str(t.get("texto") or ""))
        if not m:
            continue
        tx, ty = t["posicao"][0], t["posicao"][1]
        cand = [vs for vs in polis if min(v[0] for v in vs) >= tx - 50.0 and 100.0 <= min(v[1] for v in vs) - ty <= 600.0
                and max(v[0] for v in vs) - min(v[0] for v in vs) <= 400.0]
        if not cand:
            continue
        vs = min(cand, key=lambda q: math.dist((min(v[0] for v in q), min(v[1] for v in q)), (tx, ty)))
        x0, y0, x1, y1 = _caixa(vs)
        # a face do pilar: o lado (esquerdo ou direito) onde a nervura é mais alta
        alto_esq = max(v[1] for v in vs if v[0] - x0 < 1.0)
        alto_dir = max(v[1] for v in vs if x1 - v[0] < 1.0)
        if alto_esq >= alto_dir:
            cont = [(round(v[0] - x0, 1), round(v[1] - y0, 1)) for v in vs]
        else:
            cont = [(round(x1 - v[0], 1), round(v[1] - y0, 1)) for v in reversed(vs)]
        esp = sorted((min(math.dist(e["posicao"][:2], v) for v in vs), _espessura(e["texto"])) for e in textos
                     if _espessura(e["texto"]) and abs(e["posicao"][0] - tx) < 800.0 and abs(e["posicao"][1] - ty) < 800.0)
        out[_nome(m.group(1))] = {"qtd": int(m.group(2)), "t": esp[0][1] if esp else None, "contorno": cont,
                                  "largura": round(x1 - x0, 1), "altura": round(y1 - y0, 1)}
    return out


def placas(ents: Sequence[dict], folga: Tuple[float, float, float, float]) -> List[dict]:
    """as placas desenhadas na locação (o contorno na camada de chapa, dentro de `folga`), com o nome CHn mais perto"""
    nomes = [((e["posicao"][0], e["posicao"][1]), _nome(_NOME.match(str(e["texto"])).group(1))) for e in ents
             if e.get("tipo") == "texto" and _NOME.match(str(e.get("texto") or ""))]
    out = []
    for e in ents:
        if not (e.get("tipo") == "polilinha" and e.get("fechada") and re.search(r"(?i)chapa", e.get("camada", ""))):
            continue
        vs = [(v[0], v[1]) for v in e["vertices"]]
        x0, y0, x1, y1 = _caixa(vs)
        if not (folga[0] <= x0 and x1 <= folga[2] and folga[1] <= y0 and y1 <= folga[3]):
            continue
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        if len(vs) > 4 and math.dist(vs[0], vs[-1]) < 1.0:
            vs = vs[:-1]
        if len(vs) != 4:
            continue
        lados = [math.dist(vs[i], vs[(i + 1) % 4]) for i in range(4)]
        if not (120.0 <= min(lados) and max(lados) <= 1000.0):
            continue
        perto = sorted((math.dist(c, p), n) for p, n in nomes)
        out.append({"vertices": vs, "centro": c, "rotulo": perto[0][1] if perto and perto[0][0] < 600.0 else None,
                    "id": e.get("id")})
    return out


def rotulos(ents: Sequence[dict], folga: Tuple[float, float, float, float]) -> List[tuple]:
    """os nomes CHn escritos na locação (dentro de `folga`): [((x, y), "CH5")]"""
    return [((e["posicao"][0], e["posicao"][1]), _nome(_NOME.match(str(e["texto"])).group(1))) for e in ents
            if e.get("tipo") == "texto" and _NOME.match(str(e.get("texto") or ""))
            and folga[0] <= e["posicao"][0] <= folga[2] and folga[1] <= e["posicao"][1] <= folga[3]]


def placas_sem_contorno(placas_l: Sequence[dict], rots: Sequence[tuple], dets: Dict[str, dict], doc, mover) -> List[dict]:
    """a placa que a locação só nomeia (o "CH5" ao lado do PM6 do Posto, sem o contorno): a do detalhe, centrada no pilar
    mais perto do nome (o caixão pelo meio dos dois Ue), com o lado B na direção do par — só os detalhes que nenhum
    contorno da locação tem"""
    desenhadas = set()
    for pl in placas_l:
        vs = pl["vertices"]
        lados = sorted(math.dist(vs[i], vs[(i + 1) % 4]) for i in range(4))
        for k, d_ in dets.items():
            if abs(max(d_["B"], d_["H"]) - lados[3]) <= TOL_MEDIDA and abs(min(d_["B"], d_["H"]) - lados[0]) <= TOL_MEDIDA:
                desenhadas.add(k)
    pes = []
    for b in doc.barras:
        if b.papel == "pilar":
            pe = b.inicio if b.inicio[2] <= b.fim[2] else b.fim
            pes.append((pe[0], pe[1]))
    out = []
    for p, nome in rots:
        d = dets.get(nome)
        if d is None or nome in desenhadas or not d.get("furos"):
            continue
        q = mover(p)
        perto = sorted(pes, key=lambda c: math.dist(c, q))
        if not perto or math.dist(perto[0], q) > 1500.0:
            continue
        grupo = [c for c in perto if math.dist(c, perto[0]) < 600.0]
        cx, cy = sum(c[0] for c in grupo) / len(grupo), sum(c[1] for c in grupo) / len(grupo)
        if any(math.dist((cx, cy), mover(o["centro"])) < 300.0 for o in out):
            continue                                     # o mesmo pilar nomeado duas vezes
        u = (1.0, 0.0)
        if len(grupo) >= 2 and math.dist(grupo[0], grupo[1]) > 1.0:
            a_, b_ = grupo[0], grupo[1]
            L_ = math.dist(a_, b_)
            u = ((b_[0] - a_[0]) / L_, (b_[1] - a_[1]) / L_)
        v = (-u[1], u[0])
        B, H = d["B"], d["H"]
        c0 = (cx - u[0] * B / 2 - v[0] * H / 2, cy - u[1] * B / 2 - v[1] * H / 2)
        vs = [c0, (c0[0] + u[0] * B, c0[1] + u[1] * B), (c0[0] + u[0] * B + v[0] * H, c0[1] + u[1] * B + v[1] * H),
              (c0[0] + v[0] * H, c0[1] + v[1] * H)]
        out.append({"vertices": vs, "centro": (cx, cy), "rotulo": nome, "id": None, "ja_na_planta": True,
                    "a_conferir": "a locação só escreve %s ao lado do pilar (sem o contorno): a placa do detalhe centrada nele" % nome})
    return out


def _quadro(vs, B: float, H: float):
    """o canto, o eixo de B e o de H da placa da locação (a medida B do detalhe no lado que mais se parece com ela);
    devolve (canto, u, v, medida ao longo de u, medida ao longo de v)"""
    a, b, c = vs[0], vs[1], vs[2]
    l1, l2 = math.dist(a, b), math.dist(b, c)
    u = ((b[0] - a[0]) / l1, (b[1] - a[1]) / l1)
    v = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
    if abs(l1 - H) + abs(l2 - B) < abs(l1 - B) + abs(l2 - H):
        # o lado de B é o segundo: começa em b, B ao longo de v, H ao longo de -u
        canto, u, v, l1, l2 = b, v, (-u[0], -u[1]), l2, l1
    else:
        canto = a
    if u[0] * v[1] - u[1] * v[0] < 0:                  # a normal para cima
        canto = (canto[0] + v[0] * l2, canto[1] + v[1] * l2)
        v = (-v[0], -v[1])
    return canto, u, v, l1, l2


def lancar(doc, placas_l: Sequence[dict], dets: Dict[str, dict], mover, base: float, aco: str, barra,
           chapas_postas: list, avisos: List[str], nervs: Optional[Dict[str, dict]] = None) -> dict:
    """põe as placas e os chumbadores no modelo e encurta o pé dos pilares que nascem nelas; `mover` leva o ponto da
    locação para a planta, `barra` é a do montar (o chumbador entra nas marcas e no deslocamento junto com as outras)"""
    from nucleo3d.modelo import Chapa
    from nucleo3d import geometria as geo
    pilares = [b for b in doc.barras if b.papel == "pilar"]
    n_placas = n_chumb = n_nerv = 0
    sem_detalhe = set()
    for pl in placas_l:
        vs = list(pl["vertices"]) if pl.get("ja_na_planta") else [mover(p) for p in pl["vertices"]]
        lados = sorted(math.dist(vs[i], vs[(i + 1) % 4]) for i in range(4))
        conferir = [pl["a_conferir"]] if pl.get("a_conferir") else []
        # o nome pela medida (as dos detalhes do Posto são todas diferentes); o texto ao lado que diz outra coisa vira
        # pergunta (o CH2 escrito sobre o bloco da CH1 e da CH3, 22/10/2026) — a medida desenhada manda
        pela_medida = [k for k, d_ in dets.items() if abs(max(d_["B"], d_["H"]) - lados[3]) <= TOL_MEDIDA
                       and abs(min(d_["B"], d_["H"]) - lados[0]) <= TOL_MEDIDA]
        rot = pl.get("rotulo")
        nome = pela_medida[0] if len(pela_medida) == 1 else rot
        if rot and nome and rot != nome:
            conferir.append("o texto ao lado diz %s, mas a placa desenhada tem a medida da %s" % (rot, nome))
        d = dets.get(nome or "")
        if d is None:
            sem_detalhe.add(nome or "sem nome")
            B, H, t, furos, abertos = lados[3], lados[0], None, [], []
        else:
            B, H, t, furos, abertos = d["B"], d["H"], d["t"], d["furos"], d["abertos"]
            if abs(max(B, H) - lados[3]) > TOL_MEDIDA or abs(min(B, H) - lados[0]) > TOL_MEDIDA:
                conferir.append("a locação desenha %.0f × %.0f e o detalhe da %s, %.0f × %.0f" % (lados[3], lados[0], nome, B, H))
        if not t:
            t = 9.53
            conferir.append("espessura sem texto no detalhe: 3/8\" até confirmar")
        canto, u, v, Lu, Lv = _quadro(vs, B, H)
        # a placa da locação maior ou menor que a do detalhe: os furos do detalhe no meio dela
        dx, dy = (Lu - B) / 2.0, (Lv - H) / 2.0
        ch_d = (d or {}).get("chumbador") or {}
        dch = ch_d.get("d")
        fur = []
        for x, y, fd in furos:
            if dch and fd < dch + 1.5:
                conferir.append("furo Ø%g desenhado menor que o chumbador Ø%g: Ø%g (folga de 1,5)" % (fd, dch, round(dch + 1.5, 1)))
                fd = round(dch + 1.5, 1)
            fur.append({"x": round(x + dx, 1), "y": round(y + dy, 1), "diametro": fd})
        for x, y, w, h in abertos:
            fur.append({"x": round(x + dx, 1), "y": round(y + dy, 1), "largura": w, "altura": h})
            conferir.append("abertura %.0f × %.0f no meio da placa (no 3D como furo oblongo)" % (w, h))
        org = {"locacao": nome or "placa sem nome", "placa": nome, "detalhe": "DET. DO %s" % nome if d else None}
        if conferir:
            org["a_conferir"] = "; ".join(dict.fromkeys(conferir))
        ch = Chapa(nome="Placa de base %s" % (nome or ""), origem=(canto[0], canto[1], base),
                   eixo_x=(u[0], u[1], 0.0), eixo_y=(v[0], v[1], 0.0),
                   contorno=[(0.0, 0.0), (Lu, 0.0), (Lu, Lv), (0.0, Lv)], espessura=t, centrada=False,
                   furos=fur, aco=aco)
        ch.camada = "Chapas"
        ch.atributos = {"tipo_ifc": "IfcPlate", "origem": org}
        doc.add(ch)
        chapas_postas.append(ch)
        n_placas += 1
        # as nervuras desenhadas na vista de cima (os retângulos finos): de pé na placa, da face do pilar para fora
        nv = (nervs or {}).get((d or {}).get("nervura") or "") if d else None
        if d and d.get("nervuras") and nv:
            por_placa = nv["qtd"] / float(d["qtd"] or 1)
            o_nv = {"locacao": "%s da %s" % (d["nervura"].replace("NERVURA", "NERVURA "), nome), "placa": nome}
            if abs(por_placa - len(d["nervuras"])) > 0.01:
                o_nv["a_conferir"] = ("o detalhe %s-%dX dá %g por placa e a vista de cima da %s desenha %d: modeladas as "
                                      "desenhadas" % (d["nervura"].replace("NERVURA", "NERVURA "), nv["qtd"], por_placa, nome,
                                                      len(d["nervuras"])))
            for rx0, ry0, rx1, ry1 in d["nervuras"]:
                ao_x = rx1 - rx0 >= ry1 - ry0
                meio = ((rx0 + rx1) / 2 + dx, (ry0 + ry1) / 2 + dy)
                if ao_x:
                    pa, pb = (rx0 + dx, meio[1]), (rx1 + dx, meio[1])
                else:
                    pa, pb = (meio[0], ry0 + dy), (meio[0], ry1 + dy)
                # a ponta de dentro (mais perto do meio da placa) encosta no pilar
                cen = (Lu / 2.0, Lv / 2.0)
                if math.dist(pa, cen) > math.dist(pb, cen):
                    pa, pb = pb, pa
                A = (canto[0] + u[0] * pa[0] + v[0] * pa[1], canto[1] + u[1] * pa[0] + v[1] * pa[1])
                Bp = (canto[0] + u[0] * pb[0] + v[0] * pb[1], canto[1] + u[1] * pb[0] + v[1] * pb[1])
                Ln = math.dist(A, Bp) or 1.0
                ex = ((Bp[0] - A[0]) / Ln, (Bp[1] - A[1]) / Ln, 0.0)
                nchapa = Chapa(nome="%s (%s)" % (d["nervura"].replace("NERVURA", "Nervura "), nome), origem=(A[0], A[1], base + t),
                               eixo_x=ex, eixo_y=(0.0, 0.0, 1.0), contorno=[tuple(q) for q in nv["contorno"]],
                               espessura=nv["t"] or 6.35, centrada=True, aco=aco)
                nchapa.camada = "Chapas"
                nchapa.atributos = {"tipo_ifc": "IfcPlate", "origem": dict(o_nv)}
                doc.add(nchapa)
                chapas_postas.append(nchapa)
                n_nerv += 1
        # o pilar que nasce na placa começa em cima dela
        poly = vs
        for b in pilares:
            pe, ponta = (b.inicio, "recorte_inicio") if b.inicio[2] <= b.fim[2] else (b.fim, "recorte_fim")
            if abs(pe[2] - base) < 1.0 and _dentro_poligono((pe[0], pe[1]), poly):
                setattr(b, ponta, float(getattr(b, ponta) or 0.0) + t)
        # um chumbador em cada furo redondo, do alto da projeção para baixo
        if dch and ch_d.get("bitola"):
            L = float(ch_d.get("L") or 0.0)
            o_ch = {"locacao": "chumbador da %s" % (nome or "placa"), "placa": nome}
            if not L:
                L = 400.0
                o_ch["a_conferir"] = "comprimento do chumbador sem cota no detalhe: 400 até confirmar"
            perfil = "FE RED %s" % ch_d["bitola"].replace('"', "''")
            geo.registrar_perfil(geo.barra_redonda(dch, perfil))
            proj = t + 1.5 * dch + PROJECAO_EXTRA
            for f in fur:
                if not f.get("diametro"):
                    continue
                cx = canto[0] + u[0] * f["x"] + v[0] * f["y"]
                cy = canto[1] + u[1] * f["x"] + v[1] * f["y"]
                if barra((cx, cy, base + proj), (cx, cy, base + proj - L), perfil, "chumbador", "Chumbadores", None, 0.0, o_ch):
                    n_chumb += 1
    if sem_detalhe:
        avisos.append("placas de base sem detalhe (só o contorno da locação, sem furos nem chumbadores): %s"
                      % ", ".join(sorted(sem_detalhe)))
    return {"placas": n_placas, "chumbadores": n_chumb, "nervuras": n_nerv, "detalhes": sorted(dets)}


def _dentro_poligono(p, poly) -> bool:
    x, y = p
    dentro = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dentro = not dentro
    return dentro
