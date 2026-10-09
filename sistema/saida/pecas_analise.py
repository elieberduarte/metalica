# -*- coding: utf-8 -*-
"""PDF das peças marcadas na análise estrutural (09/10/2026, o BRAMAIS: "nesse mapa já gerar o pdf com as cargas dos
pilares que indiquei" — as 4 colunas metálicas do oitão).

Para cada peça (o pilar inteiro, ainda que partido em trechos pelos nós das vigas; a viga inteira): os esforços nas duas
pontas — base e topo no pilar — por caso de carga, sem coeficientes, e a envoltória das combinações últimas (a normal
máxima e mínima, o maior momento e o maior cortante ao longo da peça, com a combinação de cada um), em tf e tf·m.

Os esforços saem do resultado gravado (`analise_estrutural.json`): as forças da ponta a de cada barra por caso (`pontas`,
eixos locais) e a carga distribuída local (`w_local`); nas combinações últimas com a 2ª ordem, as `pontas2`.
Convenção: N > 0 tração (compressão negativa), como na tela da análise.
"""
import html
import math
import os
from typing import Dict, List, Optional

TF = 9.80665
ESTACOES = 11


def _esc(t) -> str:
    return html.escape(str(t if t is not None else ""), quote=True)


def _n(x, c=2) -> str:
    s = ("%." + str(c) + "f") % float(x)
    i, _, d = s.partition(".")
    neg = i.startswith("-") and float(x) != 0
    i = i.lstrip("-")
    return ("−" if neg else "") + i + ("," + d if d else "")


def esforcos(f_a, w, x):
    """N, Vy, Vz, T, My, Mz na seção x da barra (a mesma conta da tela, esforcosEm)"""
    Fx, Fy, Fz, Mx, My, Mz = f_a[:6]
    wx, wy, wz = w[:3]
    return [-(Fx + wx * x), -(Fy + wy * x), -(Fz + wz * x), -Mx,
            -(My + x * Fz + wz * x * x / 2.0), -(Mz - x * Fy - wy * x * x / 2.0)]


def _forcas_comb(an: dict, i: int, comb: str):
    """(f_a, w) da barra i na combinação: a soma dos casos pelos fatores; com a 2ª ordem gravada, as pontas dela"""
    casos = list(an["casos"])
    fat = (an["combinacoes"][comb].get("fatores") or {})
    w = [0.0, 0.0, 0.0]
    f = [0.0] * 6
    for c, nome in enumerate(casos):
        a = float(fat.get(nome) or 0.0)
        if not a:
            continue
        for k in range(3):
            w[k] += a * an["w_local"][i][c][k]
        for k in range(6):
            f[k] += a * an["pontas"][i][c][k]
    p2 = (an.get("pontas2") or {}).get(comb)
    if p2 is not None:
        f = list(p2[i][:6])
    return f, w


def pecas(an: dict, ids: List[str]) -> List[dict]:
    """As peças pedidas (pelos ids das entidades do 3D) com as barras em ordem e as pontas"""
    nos = an["nos"]
    saida = []
    for pid in ids:
        bs = [i for i, b in enumerate(an["barras"]) if (b.get("ids") or [None])[0] == pid]
        if not bs:
            continue
        b0 = an["barras"][bs[0]]
        pilar = b0["papel"] == "pilar"
        # a cadeia: no pilar, de baixo para cima; na viga, pela ordem dos nós
        if pilar:
            bs.sort(key=lambda i: min(nos[an["barras"][i]["a"]][2], nos[an["barras"][i]["b"]][2]))
        else:
            ref = nos[b0["a"]]
            bs.sort(key=lambda i: math.dist(ref, nos[an["barras"][i]["a"]]) + math.dist(ref, nos[an["barras"][i]["b"]]))
        saida.append({"id": pid, "barras": bs, "pilar": pilar, "nome": b0.get("marca") or b0.get("perfil"),
                      "perfil": b0.get("perfil"), "L": sum(an["barras"][i]["L"] for i in bs)})
    return saida


def _ponta(an, pc, qual):
    """(barra, x) da ponta da peça: 'ini' (base do pilar / começo da viga) ou 'fim'"""
    nos = an["nos"]
    i = pc["barras"][0] if qual == "ini" else pc["barras"][-1]
    b = an["barras"][i]
    za, zb = nos[b["a"]][2], nos[b["b"]][2]
    if pc["pilar"]:
        baixo_a = za <= zb
        x = (0.0 if baixo_a else b["L"]) if qual == "ini" else (b["L"] if baixo_a else 0.0)
    else:
        x = 0.0 if qual == "ini" else b["L"]
    return i, x


def _dist_desde_inicio(an, pc, i, x):
    """a distância da seção x da barra i desde o começo dela no sentido da peça (de baixo para cima no pilar)"""
    if not pc["pilar"]:
        return x
    b = an["barras"][i]
    return x if an["nos"][b["a"]][2] <= an["nos"][b["b"]][2] else b["L"] - x


def tabela_da_peca(an: dict, pc: dict) -> dict:
    casos = list(an["casos"])
    out = {"casos": [], "env": {}}
    for c, nome in enumerate(casos):
        linha = {"caso": nome, "descricao": an["casos"][nome].get("descricao", "")}
        for qual in ("ini", "fim"):
            i, x = _ponta(an, pc, qual)
            linha[qual] = [v / TF for v in esforcos(an["pontas"][i][c], an["w_local"][i][c], x)]
        # o maior momento ao longo da peça e onde (a distância desde a base / o começo)
        mm, onde, s0 = 0.0, 0.0, 0.0
        for i in pc["barras"]:
            b = an["barras"][i]
            for k in range(ESTACOES):
                x = b["L"] * k / (ESTACOES - 1)
                e = esforcos(an["pontas"][i][c], an["w_local"][i][c], x)
                m = math.hypot(e[4], e[5]) / TF
                if m > mm + 1e-9:
                    mm, onde = m, s0 + _dist_desde_inicio(an, pc, i, x)
            s0 += b["L"]
        linha["M_vao"] = (mm, onde)
        out["casos"].append(linha)
    elu = [c for c, v in an["combinacoes"].items() if v.get("tipo") == "ELU"]
    best = {}
    for comb in elu:
        for i in pc["barras"]:
            f, w = _forcas_comb(an, i, comb)
            L = an["barras"][i]["L"]
            for k in range(ESTACOES):
                e = esforcos(f, w, L * k / (ESTACOES - 1))
                N, V, M = e[0] / TF, math.hypot(e[1], e[2]) / TF, math.hypot(e[4], e[5]) / TF
                for chave, val, maior in (("N_max", N, True), ("N_min", N, False), ("M_max", M, True), ("V_max", V, True)):
                    if chave not in best or (val > best[chave][0] if maior else val < best[chave][0]):
                        best[chave] = (val, comb, e)
    out["env"] = best
    return out


CSS = """
@page { size: A4; margin: 12mm 12mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1d232b; font-size: 8.4pt; margin: 0; }
h1 { font-size: 14pt; margin: 0 0 1mm; } h2 { font-size: 11pt; margin: 6mm 0 1mm; padding-bottom: 1mm; border-bottom: 1.2px solid #2a3a52; }
.sub { color: #5b6573; font-size: 8.4pt; margin: 0 0 2mm; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin: 1mm 0 2mm; }
th { font-size: 6.8pt; color: #5b6573; text-align: right; white-space: nowrap; border-bottom: 1.2px solid #2a3a52; padding: 1mm 1.2mm; vertical-align: bottom; }
th.l, td.l { text-align: left; } td { text-align: right; padding: 0.7mm 1.2mm; border-bottom: 1px solid #e3e7ec; white-space: nowrap; }
tr.grupo th { text-align: center; border-bottom: 1px solid #c9d0d9; color: #2a3a52; }
.peca { break-inside: avoid; } .env td.n { font-weight: 700; color: #1f4e9c; }
.nota { color: #5b6573; font-size: 7.4pt; } td.mv { font-weight: 600; border-left: 1px solid #c9d0d9; }
"""


def _ponto(an, i, x):
    b = an["barras"][i]
    pa, pb = an["nos"][b["a"]], an["nos"][b["b"]]
    t = x / b["L"] if b["L"] else 0.0
    return [pa[k] + (pb[k] - pa[k]) * t for k in range(3)]


def html_pecas(an: dict, ids: List[str], projeto: dict, nomes: Optional[Dict[str, str]] = None,
               eixos: Optional[List[dict]] = None) -> str:
    from saida.planta_cargas import eixos_do_ponto
    partes = []
    lista = pecas(an, ids)
    for pc in lista:
        pc["nome_final"] = (nomes or {}).get(pc["id"]) or pc["nome"]
    import re
    natural = lambda t: [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(t))]
    lista.sort(key=lambda pc: (not pc["pilar"], natural(pc["nome_final"])))
    for pc in lista:
        t = tabela_da_peca(an, pc)
        p0 = _ponto(an, *_ponta(an, pc, "ini"))
        p1 = _ponto(an, *_ponta(an, pc, "fim"))
        rot = ("base", "topo") if pc["pilar"] else ("início", "fim")
        nome = pc["nome_final"]
        if eixos:
            ex0, ex1 = eixos_do_ponto(eixos, p0[0], p0[1]), eixos_do_ponto(eixos, p1[0], p1[1])
            onde = "eixo " + ex0 if pc["pilar"] or ex0 == ex1 else "eixos %s → %s" % (ex0, ex1)
        else:
            onde = "x %s; y %s m" % (_n(p0[0] / 1000, 2), _n(p0[1] / 1000, 2))
        cotas = "%s %s → %s %s m" % (rot[0], _n(p0[2] / 1000, 2), rot[1], _n(p1[2] / 1000, 2)) if pc["pilar"] else             "nível %s m" % _n(p0[2] / 1000, 2)
        linhas = []
        for ln in t["casos"]:
            a, b = ln["ini"], ln["fim"]
            mv, xv = ln["M_vao"]
            linhas.append("<tr><td class=l><b>%s</b></td><td class=l>%s</td>%s%s<td class=mv>%s</td><td>%s</td></tr>" % (
                _esc(ln["caso"]), _esc(ln["descricao"][:70]),
                "".join("<td>%s</td>" % _n(v) for v in (a[0], a[1], a[2], a[4], a[5])),
                "".join("<td>%s</td>" % _n(v) for v in (b[0], b[1], b[2], b[4], b[5])),
                _n(mv) if mv >= 0.005 else "—", _n(xv, 2) if mv >= 0.005 else ""))
        env = t["env"]
        ln_env = []
        for chave, rotulo in (("N_max", "N máxima (+ tração)"), ("N_min", "N mínima (− compressão)"), ("M_max", "momento máximo"),
                              ("V_max", "cortante máximo")):
            if chave in env:
                v, comb, e = env[chave]
                ln_env.append("<tr><td class=l>%s</td><td class=n>%s %s</td><td class=l>%s</td><td>N %s · V<sub>y</sub> %s · V<sub>z</sub> %s · M<sub>y</sub> %s · M<sub>z</sub> %s</td></tr>"
                              % (rotulo, _n(v), "tf·m" if chave == "M_max" else "tf", _esc(comb),
                                 *(_n(x / TF) for x in (e[0], e[1], e[2], e[4], e[5]))))
        partes.append(
            "<section class=peca><h2>%s <span class=sub>· %s · %s · L = %s m · %s · %s</span></h2>"
            "<table><thead><tr class=grupo><th colspan=2></th><th colspan=5>%s</th><th colspan=5>%s</th><th colspan=2>ao longo</th></tr>"
            "<tr><th class=l>Caso</th><th class=l>Descrição</th>%s%s<th>M máx</th><th>a (m)</th></tr></thead><tbody>%s</tbody></table>"
            "<table class=env><thead><tr><th class=l>Envoltória de cálculo (ELU)</th><th>valor</th><th class=l>combinação</th>"
            "<th>esforços concomitantes na seção (tf, tf·m)</th></tr></thead><tbody>%s</tbody></table></section>" % (
                _esc(nome), "pilar" if pc["pilar"] else "viga", _esc(pc["perfil"]), _n(pc["L"], 2), _esc(onde), _esc(cotas),
                rot[0], rot[1],
                "".join("<th>%s</th>" % h for h in ("N", "V<sub>y</sub>", "V<sub>z</sub>", "M<sub>y</sub>", "M<sub>z</sub>")),
                "".join("<th>%s</th>" % h for h in ("N", "V<sub>y</sub>", "V<sub>z</sub>", "M<sub>y</sub>", "M<sub>z</sub>")),
                "".join(linhas), "".join(ln_env)))
    cab = ("<h1>Esforços nas peças — %s</h1><p class=sub>análise de %s · por caso de carga (característicos, sem coeficientes) e a "
           "envoltória das combinações últimas · tf e tf·m · N &gt; 0 tração · \"a\": a distância do M máx desde a base do pilar (o começo da viga) · V e M nos eixos locais "
           "da barra (y, z); o M máx e a envoltória somam os dois planos</p>" % (_esc(projeto.get("nome") or ""), _esc(an.get("calculado_em") or "")))
    return ("<!doctype html><html lang=pt-BR><meta charset=utf-8><title>Esforços nas peças - %s</title><style>%s</style><body>%s%s"
            "<p class=nota>Os casos de vento são os do prédio fechado (NBR 6123:2023), nas quatro direções e com os dois C<sub>pi</sub>; "
            "a envoltória já inclui a 2ª ordem das combinações últimas.</p></body></html>" % (
                _esc(projeto.get("nome") or ""), CSS, cab, "".join(partes)))


def nomes_dos_pilares(an: dict, doc) -> Dict[str, str]:
    """{id da peça: nome}: os mesmos da planta de cargas (P + o número do Tekla, CM1… nas colunas metálicas)"""
    from saida.planta_cargas import levantar
    return {p["id"]: p["nome"] for p in levantar(an, doc) if p.get("id")}


def gerar(pasta_projeto: str, an: dict, ids: List[str], doc, projeto: dict) -> Dict[str, str]:
    from saida.printpdf import navegador
    from saida.planta_cargas import eixos_do_projeto
    import subprocess
    pasta = os.path.join(pasta_projeto, "analise")
    os.makedirs(pasta, exist_ok=True)
    h = os.path.join(pasta, "esforcos-das-pecas.html")
    with open(h, "w", encoding="utf-8") as f:
        f.write(html_pecas(an, ids, projeto, nomes_dos_pilares(an, doc), eixos_do_projeto(pasta_projeto)))
    pdf = os.path.join(pasta, "esforcos-das-pecas.pdf")
    subprocess.run([navegador(), "--headless=new", "--no-pdf-header-footer", "--print-to-pdf=" + pdf,
                    "file:///" + h.replace("\\", "/")], capture_output=True, timeout=300)
    return {"html": h, "pdf": pdf, "pecas": len(pecas(an, ids))}
