# -*- coding: utf-8 -*-
"""Planta de cargas da fundação (09/10/2026, o BRAMAIS: "pode criar a apresentação de uma planta de cargas").

Sai do último resultado da análise estrutural (`analise_estrutural.json` do projeto): em cada apoio (o pé dos pilares e das
colunas), as forças que a estrutura entrega ao bloco — as reações com o sinal trocado —, por ação e sem coeficientes
(característicos), em tf e tf·m, e a envoltória das combinações últimas. A planta mostra os eixos do projeto (a malha do
IFC, quando há) e, em cada pilar, o nome e a carga vertical; a tabela traz tudo.

Convenção: N > 0 comprime o bloco; H e M em valor absoluto por direção (x, y da planta), com o caso de vento que os dá.
"""
import html
import math
import os
import re
from typing import Dict, List, Optional, Tuple

TF = 9.80665                 # kN por tf


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""), quote=True)


def _n(x, c=1) -> str:
    s = ("%." + str(c) + "f") % float(x)
    i, _, d = s.partition(".")
    neg = i.startswith("-")
    i = i.lstrip("-")
    g = []
    while len(i) > 3:
        g.insert(0, i[-3:])
        i = i[:-3]
    g.insert(0, i)
    return ("−" if neg else "") + ".".join(g) + ("," + d if d else "")


# ------------------------------------------------------------------ a malha de eixos do IFC

def eixos_do_ifc(caminho: str) -> List[dict]:
    """[{nome, tipo: 'x' | 'y', pos (mm)}] da primeira IfcGrid do arquivo (o nível mais baixo): os eixos retos paralelos a
    x ou a y. Vazio quando não há malha."""
    try:
        t = open(caminho, encoding="latin-1").read()
    except OSError:
        return []
    L = {int(m.group(1)): m.group(2) for m in re.finditer(r"#(\d+)=\s*(.*?);\s*$", t, re.M)}
    grids = [v for v in L.values() if v.startswith("IFCGRID(")]
    if not grids:
        return []

    def nivel(g):
        m = re.search(r"'([+-]?\d+(?:\.\d+)?)m'", g)
        return float(m.group(1)) if m else 0.0
    g = min(grids, key=nivel)
    listas = re.findall(r"\(([^()]*#[^()]*)\)", g)
    saida = []
    for lst in listas[:2]:
        for ref in re.findall(r"#(\d+)", lst):
            ax = L.get(int(ref), "")
            m = re.match(r"IFCGRIDAXIS\('([^']*)',#(\d+)", ax)
            if not m:
                continue
            curva = L.get(int(m.group(2)), "")
            pts = [L.get(int(r), "") for r in re.findall(r"#(\d+)", curva)]
            xy = []
            for p in pts:
                c = re.match(r"IFCCARTESIANPOINT\(\(([^)]*)\)\)", p)
                if c:
                    xy.append([float(v) for v in c.group(1).split(",")[:2]])
            if len(xy) < 2:
                continue
            (x0, y0), (x1, y1) = xy[0], xy[-1]
            if abs(x1 - x0) < 1.0:
                saida.append({"nome": m.group(1), "tipo": "x", "pos": x0, "de": min(y0, y1), "ate": max(y0, y1)})
            elif abs(y1 - y0) < 1.0:
                saida.append({"nome": m.group(1), "tipo": "y", "pos": y0, "de": min(x0, x1), "ate": max(x0, x1)})
    return saida


# ------------------------------------------------------------------ os apoios e as cargas

def _nome_do_pilar(ent, contagem: Dict[str, int]) -> str:
    """P + o número de controle do Tekla; a coluna metálica, CM1, CM2…; o resto, pela marca"""
    at = getattr(ent, "atributos", None) or {}
    pr = at.get("propriedades") or {}
    for grupo in pr.values():
        if isinstance(grupo, dict) and grupo.get("Control number") not in (None, ""):
            return "P%s" % grupo["Control number"]
    nome = str(getattr(ent, "nome", "") or "")
    if "COLUNA" in nome.upper() or getattr(ent, "tipo", "") == "barra":
        contagem["CM"] = contagem.get("CM", 0) + 1
        return "CM%d" % contagem["CM"]
    contagem["P"] = contagem.get("P", 0) + 1
    return "P%d" % (900 + contagem["P"])


def levantar(analise: dict, doc=None) -> List[dict]:
    """Os apoios com o nome, a posição (mm), a seção desenhada e as cargas por ação e as envoltórias, em tf / tf·m"""
    nos = analise["nos"]
    casos = list(analise["casos"])
    barras = analise["barras"]
    env = {e["chave"]: e for e in analise.get("reacoes_envoltoria") or []}
    # o pilar de cada apoio: a barra de pilar que começa no nó
    pilar_do_no = {}
    for b in barras:
        if b["papel"] == "pilar":
            pilar_do_no.setdefault(b["a"], b)
            pilar_do_no.setdefault(b["b"], b)
    ordem = sorted(analise["apoios"], key=lambda ap: (round(nos[ap["no"]][1] / 500), nos[ap["no"]][0]))
    # o nome: as colunas metálicas numeradas pela posição
    contagem: Dict[str, int] = {}
    saida = []
    grupos = {"G": ("PP", "CP"), "Qp": ("SCP",), "Qc": ("SC",)}
    for ap in ordem:
        no = ap["no"]
        b = pilar_do_no.get(no)
        ent = doc.entidades.get(b["ids"][0]) if (doc is not None and b and b.get("ids")) else None
        nome = _nome_do_pilar(ent, contagem) if ent is not None else "A%d" % (len(saida) + 1)
        R = analise["reacoes_casos"].get(str(no)) or []
        por = {c: R[k] for k, c in enumerate(casos) if k < len(R)}
        soma = lambda cs, k: sum(por[c][k] for c in cs if c in por)
        item = {"nome": nome, "id": (b or {}).get("ids", [None])[0], "x": nos[no][0], "y": nos[no][1], "z": nos[no][2], "tipo": ap["tipo"],
                "aco": bool(b and not b.get("concreto")), "perfil": (b or {}).get("perfil", ""),
                "secao": (b or {}).get("secao")}
        for g, cs in grupos.items():
            item[g] = {"N": soma(cs, 2) / TF, "Hx": soma(cs, 0) / TF, "Hy": soma(cs, 1) / TF,
                       "Mx": soma(cs, 3) / TF, "My": soma(cs, 4) / TF}
        ventos = [c for c in casos if c.startswith("V")]
        if ventos:
            ns = [(por[c][2] / TF, c) for c in ventos if c in por]
            item["W"] = {"Nmax": max(ns), "Nmin": min(ns),
                         "Hx": max(((abs(por[c][0]) / TF, c) for c in ventos if c in por)),
                         "Hy": max(((abs(por[c][1]) / TF, c) for c in ventos if c in por)),
                         "Mx": max(((abs(por[c][3]) / TF, c) for c in ventos if c in por)),
                         "My": max(((abs(por[c][4]) / TF, c) for c in ventos if c in por))}
        e = env.get(ap["chave"]) or {}
        item["ELU"] = {k: (float(e[k][0]) / TF, str(e[k][1]).strip(" ·")) for k in ("Fz_max", "Fz_min", "H_max", "M_max") if e.get(k)}
        saida.append(item)
    return saida


# ------------------------------------------------------------------ o desenho

def _svg_planta(pilares: List[dict], eixos: List[dict], largura=400.0, altura_max=240.0) -> str:
    xs = [p["x"] for p in pilares] + [e["pos"] for e in eixos if e["tipo"] == "x"]
    ys = [p["y"] for p in pilares] + [e["pos"] for e in eixos if e["tipo"] == "y"]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mg = (18.0, 26.0)                                    # margem para as bolhas e as cotas (mm de papel)
    k = min((largura - 2 * mg[1]) / max(x1 - x0, 1.0), (altura_max - 2 * mg[0] - 10) / max(y1 - y0, 1.0))
    W = (x1 - x0) * k + 2 * mg[1]
    H = (y1 - y0) * k + 2 * mg[0] + 10
    X = lambda x: mg[1] + (x - x0) * k
    Y = lambda y: mg[0] + 6 + (y1 - y) * k
    p = []
    ex = sorted([e for e in eixos if e["tipo"] == "x"], key=lambda e: e["pos"])
    ey = sorted([e for e in eixos if e["tipo"] == "y"], key=lambda e: e["pos"])
    for e in ex:
        x = X(e["pos"])
        p.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" class="eixo"/>' % (x, Y(y1) - 6, x, Y(y0) + 6))
        for yb in (Y(y1) - 10, Y(y0) + 10):
            p.append('<circle cx="%.2f" cy="%.2f" r="3.6" class="bolha"/><text x="%.2f" y="%.2f" class="tb">%s</text>' % (x, yb, x, yb + 1.3, _esc(e["nome"])))
    for e in ey:
        y = Y(e["pos"])
        p.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" class="eixo"/>' % (X(x0) - 6, y, X(x1) + 6, y))
        for xb in (X(x0) - 10, X(x1) + 10):
            p.append('<circle cx="%.2f" cy="%.2f" r="3.6" class="bolha"/><text x="%.2f" y="%.2f" class="tb">%s</text>' % (xb, y, xb, y + 1.3, _esc(e["nome"])))
    # cotas entre eixos (em cima e à esquerda)
    for a, b in zip(ex, ex[1:]):
        xa, xb = X(a["pos"]), X(b["pos"])
        yc = Y(y1) - 16
        p.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" class="cota"/>' % (xa, yc, xb, yc))
        p.append('<text x="%.2f" y="%.2f" class="tc">%s</text>' % ((xa + xb) / 2, yc - 0.8, _n((b["pos"] - a["pos"]) / 1000.0, 2)))
    for a, b in zip(ey, ey[1:]):
        ya, yb = Y(a["pos"]), Y(b["pos"])
        xc = X(x0) - 16
        p.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" class="cota"/>' % (xc, ya, xc, yb))
        cx, cy = xc - 0.8, (ya + yb) / 2
        p.append('<text x="%.2f" y="%.2f" class="tc" transform="rotate(-90 %.2f %.2f)">%s</text>' % (cx, cy, cx, cy, _n(abs(b["pos"] - a["pos"]) / 1000.0, 2)))
    # os pilares
    for pl in pilares:
        x, y = X(pl["x"]), Y(pl["y"])
        s = 2.4 if not pl["aco"] else 1.8
        p.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" class="%s"/>' % (x - s / 2, y - s / 2, s, s, "pa" if pl["aco"] else "pc"))
        Nk = pl["G"]["N"] + pl["Qp"]["N"] + pl["Qc"]["N"]
        # a última fila com o texto à esquerda do pilar (à direita ele encostava nas bolhas dos eixos)
        dir_ = pl["x"] > x1 - 0.04 * (x1 - x0)
        tx, anc = (x - 1.8, ' text-anchor="end"') if dir_ else (x + 1.8, "")
        p.append('<text x="%.2f" y="%.2f" class="tn"%s>%s</text>' % (tx, y - 2.4, anc, _esc(pl["nome"])))
        p.append('<text x="%.2f" y="%.2f" class="tv"%s>%s tf</text>' % (tx, y + 0.6, anc, _n(Nk, 1)))
        if pl.get("W"):
            hm = max(pl["W"]["Hx"][0], pl["W"]["Hy"][0])
            mm = max(pl["W"]["Mx"][0], pl["W"]["My"][0])
            p.append('<text x="%.2f" y="%.2f" class="tw"%s>H %s · M %s</text>' % (tx, y + 3.2, anc, _n(hm, 1), _n(mm, 1)))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%.1fmm" height="%.1fmm" viewBox="0 0 %.2f %.2f" '
            'font-family="Segoe UI, Arial, sans-serif">%s</svg>' % (W, H, W, H, "".join(p)))


CSS = """
@page { size: A3 landscape; margin: 10mm 12mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1d232b; font-size: 8.4pt; margin: 0; }
h1 { font-size: 15pt; margin: 0 0 1mm; } .sub { color: #5b6573; font-size: 8.6pt; margin: 0 0 3mm; }
.eixo { stroke: #c0392b; stroke-width: 0.15; stroke-dasharray: 3 0.8 0.6 0.8; }
.bolha { fill: #fff; stroke: #c0392b; stroke-width: 0.3; } .tb { font-size: 3.2px; fill: #c0392b; text-anchor: middle; font-weight: 700; }
.cota { stroke: #2b8a3e; stroke-width: 0.15; } .tc { font-size: 2.4px; fill: #1d232b; text-anchor: middle; }
.pc { fill: #868e96; stroke: #343a40; stroke-width: 0.15; } .pa { fill: #2f9e44; stroke: #1b5e20; stroke-width: 0.15; }
.tn { font-size: 2.6px; font-weight: 700; fill: #1d232b; } .tv { font-size: 2.5px; fill: #1f4e9c; font-weight: 700; }
.tw { font-size: 2.0px; fill: #5b6573; }
.legenda { font-size: 8pt; color: #5b6573; margin: 2mm 0; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin-top: 2mm; }
th { font-size: 7pt; color: #5b6573; text-align: right; border-bottom: 1.2px solid #2a3a52; padding: 1.2mm 1.4mm; vertical-align: bottom; }
th.l, td.l { text-align: left; } td { text-align: right; padding: 0.8mm 1.4mm; border-bottom: 1px solid #e3e7ec; white-space: nowrap; }
tr.grupo th { text-align: center; border-bottom: 1px solid #c9d0d9; color: #2a3a52; }
td.n { font-weight: 700; color: #1f4e9c; } .quebra { break-before: page; } tr { break-inside: avoid; }
.nota { color: #5b6573; font-size: 7.6pt; margin: 2mm 0; }
"""


def html_planta(pilares: List[dict], eixos: List[dict], projeto: dict, analise: dict) -> str:
    par = analise.get("parametros") or {}
    svg = _svg_planta(pilares, eixos)
    linhas = []
    for pl in pilares:
        G, Qp, Qc, W, E = pl["G"], pl["Qp"], pl["Qc"], pl.get("W") or {}, pl.get("ELU") or {}
        def w(k, i=0):
            v = W.get(k)
            return _n(v[0], 1) if v else "—"
        linhas.append("<tr><td class=l><b>%s</b></td><td class=l>%s</td><td class=l>%s</td>"
                      "<td class=n>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                      "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                          _esc(pl["nome"]), _esc("%s; %s" % (_n(pl["x"] / 1000, 2), _n(pl["y"] / 1000, 2))),
                          _esc(("aço " + pl["perfil"]) if pl["aco"] else pl["tipo"]),
                          _n(G["N"], 1), _n(Qp["N"], 1), _n(Qc["N"], 1),
                          w("Nmax"), w("Nmin"), w("Hx"), w("Hy"), w("Mx"), w("My"),
                          _n(E["Fz_max"][0], 1) if "Fz_max" in E else "—", _n(E["Fz_min"][0], 1) if "Fz_min" in E else "—",
                          _n(E["H_max"][0], 1) if "H_max" in E else "—", _n(E["M_max"][0], 1) if "M_max" in E else "—"))
    tabela = ("<table><thead><tr class=grupo><th colspan=3></th><th colspan=3>Característicos (sem coeficientes)</th>"
              "<th colspan=6>Vento (o pior dos casos)</th><th colspan=4>Envoltória de cálculo (ELU)</th></tr>"
              "<tr><th class=l>Pilar</th><th class=l>x; y (m)</th><th class=l>Base</th><th>N perm.<br>G (tf)</th><th>N sobrec.<br>piso (tf)</th>"
              "<th>N sobrec.<br>cobert. (tf)</th><th>N máx<br>(tf)</th><th>N mín<br>(tf)</th><th>H<sub>x</sub><br>(tf)</th><th>H<sub>y</sub><br>(tf)</th>"
              "<th>M<sub>x</sub><br>(tf·m)</th><th>M<sub>y</sub><br>(tf·m)</th><th>N máx<br>(tf)</th><th>N mín<br>(tf)</th><th>H máx<br>(tf)</th>"
              "<th>M máx<br>(tf·m)</th></tr></thead><tbody>%s</tbody></table>" % "".join(linhas))
    vi = (analise.get("info") or {}).get("vento") or {}
    premissas = ("Permanentes: peso próprio (25 kN/m³) + lajes, revestimento %s kN/m² e cobertura %s kN/m²; sobrecargas: piso %s kN/m², "
                 "cobertura %s kN/m²; vento: V0 %s m/s, categoria %s, q = %s kN/m²." % (
                     _n(par.get("piso_revestimento") or 0, 2), _n(par.get("telha") or 0, 3), _n(par.get("piso_sobrecarga") or 0, 2),
                     _n(par.get("sobrecarga") or 0, 2), _n(par.get("v0") or 0, 0), par.get("categoria") or "—",
                     _n(vi.get("q_kN_m2") or 0, 3)))
    cab = ("<h1>Planta de cargas da fundação — %s</h1><p class=sub>%s · análise de %s · forças da estrutura no topo do bloco "
           "(as reações com o sinal trocado), em tf e tf·m · N &gt; 0 comprime</p>" % (
               _esc(projeto.get("nome") or ""), _esc(projeto.get("local") or ""), _esc(analise.get("calculado_em") or "")))
    legenda = ("<p class=legenda>Em cada pilar: o nome, a carga vertical característica total (permanente + sobrecargas) e, embaixo, "
               "o maior esforço horizontal e o maior momento do vento (característicos). Cinza: pilar de concreto (base engastada); "
               "verde: coluna metálica. Eixos do projeto pela malha do IFC.</p>")
    notas = ("<p class=nota>%s Os valores característicos por ação servem para o projetista da fundação montar as combinações dele; "
             "a envoltória de cálculo é a das combinações últimas da análise (NBR 8681), com a 2ª ordem. Os momentos M<sub>x</sub> e "
             "M<sub>y</sub> são em torno dos eixos x e y da planta.</p>" % _esc(premissas))
    return ("<!doctype html><html lang=pt-BR><meta charset=utf-8><title>Planta de cargas - %s</title><style>%s</style><body>"
            "%s%s%s<div class=quebra></div><h1>Cargas por pilar</h1>%s%s</body></html>" % (
                _esc(projeto.get("nome") or ""), CSS, cab, svg, legenda, tabela, notas))


def eixos_do_projeto(pasta_projeto: str) -> List[dict]:
    """Os eixos do primeiro IFC da origem do projeto (vazio sem IFC)"""
    origem = os.path.join(pasta_projeto, "origem")
    if os.path.isdir(origem):
        for f in sorted(os.listdir(origem)):
            if f.lower().endswith(".ifc"):
                return eixos_do_ifc(os.path.join(origem, f))
    return []


def eixos_do_ponto(eixos: List[dict], x: float, y: float, tol: float = 600.0) -> str:
    """"B/7": os eixos que passam pelo ponto (até `tol` mm); fora deles, os mais próximos com "≈" """
    nomes = []
    for tipo, v in (("x", x), ("y", y)):
        es = [e for e in eixos if e["tipo"] == tipo]
        if not es:
            continue
        e = min(es, key=lambda e: abs(e["pos"] - v))
        nomes.append(("" if abs(e["pos"] - v) <= tol else "≈") + str(e["nome"]))
    return "/".join(nomes)


def gerar(pasta_projeto: str, analise: dict, doc, projeto: dict) -> Dict[str, str]:
    """Grava analise/planta-de-cargas.html e .pdf no projeto; devolve os caminhos"""
    from saida.printpdf import navegador
    import subprocess
    pilares = levantar(analise, doc)
    eixos = eixos_do_projeto(pasta_projeto)
    pasta = os.path.join(pasta_projeto, "analise")
    os.makedirs(pasta, exist_ok=True)
    h = os.path.join(pasta, "planta-de-cargas.html")
    with open(h, "w", encoding="utf-8") as f:
        f.write(html_planta(pilares, eixos, projeto, analise))
    pdf = os.path.join(pasta, "planta-de-cargas.pdf")
    subprocess.run([navegador(), "--headless=new", "--no-pdf-header-footer", "--print-to-pdf=" + pdf,
                    "file:///" + h.replace("\\", "/")], capture_output=True, timeout=300)
    return {"html": h, "pdf": pdf, "pilares": len(pilares), "eixos": len(eixos)}
