# -*- coding: utf-8 -*-
"""A conferência do 3D: o que o olho acharia no modelo montado, achado pela conta (12/10/2026).

Nasceu da rodada do Posto CB em que o usuário pediu "renderizar e enxergar" o modelo: os erros que apareceram nas fotos
— a terça correndo dentro do painel, o painel curvo entrando no reto, os banzos de duas treliças no mesmo lugar, os
montantes e presilhas em dobro, a tesoura de ponta-cabeça que fazia a telha subir e descer — saíram de quatro contas,
que agora rodam sozinhas no fim de toda montagem pela planta:

* peças repetidas: duas barras com as mesmas pontas (a linha dobrada na elevação, duas peças no mesmo eixo);
* pontas soltas: a ponta de barra longe de qualquer outra peça (a terça em balanço, a treliça que não chega);
* choques: barras de peças diferentes que se atravessam por dentro (longe das pontas das duas) — fora os cruzamentos
  normais (os X do contraventamento, a corrente e o contravento passando pela terça, a viga no pilar);
* a telha ao lado ("o que comanda no final é a telha"): uma telha de teste lançada só na conta, sem entrar no modelo
  — o degrau entre chapas vizinhas e a dobra na caída (a terça fora da reta das vizinhas), acima de 20 mm.

Devolve os apontamentos (tipo, texto, ponto no modelo, ids) e as contagens; quem chama decide como mostrar.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Sequence

#: os papéis que cruzam as outras peças por projeto (o X do contraventamento, a corrente entre terças)
CRUZAM_POR_PROJETO = {"contraventamento", "corrente", "esticador", "agulha", "tirante"}
#: as famílias de peça que se cruzam nos nós (a viga no pilar, a viga na viga)
NOS_NORMAIS = {frozenset(("pilar", "viga")), frozenset(("viga",)), frozenset(("pilar",))}


def _peca(e) -> str:
    o = (e.atributos or {}).get("origem") or {}
    return str(o.get("peca") or o.get("planta") or o.get("sigla") or e.id)


def _nome(e) -> str:
    """o nome da peça para o texto: "TESOURA 8" (sem o número do conjunto), a sigla da terça, o papel"""
    o = (e.atributos or {}).get("origem") or {}
    n = str(o.get("peca") or o.get("planta") or "").split("#")[0].strip()
    if n:
        return n
    if o.get("sigla"):
        return "terça %s" % o["sigla"]
    return str(e.papel or e.nome or "barra")


def _dist_seg(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    L2 = sum(v * v for v in ab) or 1e-9
    t = max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / L2))
    return math.dist(p, [a[i] + ab[i] * t for i in range(3)])


def _seg_seg(p1, q1, p2, q2):
    """(distância, s em 0..1 na primeira, t na segunda, o ponto da primeira) entre dois segmentos"""
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    r = [p1[i] - p2[i] for i in range(3)]
    a = sum(x * x for x in d1)
    e = sum(x * x for x in d2)
    f = sum(d2[i] * r[i] for i in range(3))
    c = sum(d1[i] * r[i] for i in range(3))
    b = sum(d1[i] * d2[i] for i in range(3))
    den = a * e - b * b
    s = max(0.0, min(1.0, (b * f - c * e) / den)) if den > 1e-6 else 0.0
    t = (b * s + f) / e if e > 1e-9 else 0.0
    if t < 0.0:
        t, s = 0.0, max(0.0, min(1.0, -c / a)) if a > 1e-9 else 0.0
    elif t > 1.0:
        t, s = 1.0, max(0.0, min(1.0, (b - c) / a)) if a > 1e-9 else 0.0
    c1 = [p1[i] + d1[i] * s for i in range(3)]
    c2 = [p2[i] + d2[i] * t for i in range(3)]
    return math.dist(c1, c2), s, t, c1


def _grade(barras, cel: float):
    g: Dict[tuple, list] = collections.defaultdict(list)
    for k, e in enumerate(barras):
        a, b = e.inicio, e.fim
        for gx in range(int(min(a[0], b[0]) // cel), int(max(a[0], b[0]) // cel) + 1):
            for gy in range(int(min(a[1], b[1]) // cel), int(max(a[1], b[1]) // cel) + 1):
                g[(gx, gy)].append(k)
    return g


def repetidas(barras, tol: float = 15.0) -> List[dict]:
    """duas barras com as duas pontas no mesmo lugar (até `tol` mm), qualquer perfil"""
    g = _grade(barras, 2000.0)
    vistos, out = set(), []
    for k, e in enumerate(barras):
        a, b = e.inicio, e.fim
        for j in g[(int(a[0] // 2000.0), int(a[1] // 2000.0))]:
            if j <= k or (k, j) in vistos:
                continue
            f = barras[j]
            if (math.dist(a, f.inicio) <= tol and math.dist(b, f.fim) <= tol) or (math.dist(a, f.fim) <= tol and math.dist(b, f.inicio) <= tol):
                vistos.add((k, j))
                m = [(a[i] + b[i]) / 2 for i in range(3)]
                out.append({"tipo": "repetida", "ids": [e.id, f.id], "ponto": [round(v) for v in m],
                            "texto": "%s e %s no mesmo lugar (%s / %s)" % (_nome(e), _nome(f), e.perfil, f.perfil)})
    return out


def pontas_soltas(barras, solidos=(), tol: float = 250.0, tol_solido: float = 150.0) -> List[dict]:
    """a ponta de barra (acima da base) a mais de `tol` de qualquer outra barra e de `tol_solido` dos vértices de um
    sólido (o banzo curvo calandrado é um sólido: o montante encosta nele)"""
    g = _grade(barras, 2000.0)
    zmin = min((min(e.inicio[2], e.fim[2]) for e in barras), default=0.0)
    gs: Dict[tuple, list] = collections.defaultdict(list)
    for s in solidos:
        for v in s.vertices or ():
            gs[(int(v[0] // 2000.0), int(v[1] // 2000.0))].append(v)
    out = []
    for k, e in enumerate(barras):
        for qi, p in enumerate((e.inicio, e.fim)):
            if p[2] <= zmin + 5.0:
                continue                                     # no chão (a base do pilar)
            cel = (int(p[0] // 2000.0), int(p[1] // 2000.0))
            viz = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in g.get((cel[0] + dx, cel[1] + dy), ())]
            if any(j != k and _dist_seg(p, barras[j].inicio, barras[j].fim) <= tol for j in viz):
                continue
            vs = [v for dx in (-1, 0, 1) for dy in (-1, 0, 1) for v in gs.get((cel[0] + dx, cel[1] + dy), ())]
            if any(math.dist(p, v) <= tol_solido for v in vs):
                continue
            balanco = e.papel in ("terça", "terca")
            out.append({"tipo": "ponta_solta", "ids": [e.id], "ponto": [round(v) for v in p],
                        "texto": ("%s em balanço: a ponta não chega em apoio nenhum" % _nome(e)) if balanco else
                                 ("%s (%s): a ponta não encosta em peça nenhuma" % (_nome(e), e.papel or "barra"))})
    return out


def choques(barras, tol: float = 40.0, longe_da_ponta: float = 150.0) -> List[dict]:
    """barras de peças diferentes que se atravessam por dentro: os eixos a menos de `tol` mm, longe das pontas das duas.
    Um apontamento por par de peças (com quantos cruzamentos)"""
    g = _grade(barras, 3000.0)
    vistos = set()
    por_par: Dict[tuple, dict] = {}
    for ks in g.values():
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                k1, k2 = ks[i], ks[j]
                if (k1, k2) in vistos:
                    continue
                vistos.add((k1, k2))
                e1, e2 = barras[k1], barras[k2]
                p1, p2 = _peca(e1), _peca(e2)
                if p1 == p2 or e1.papel in CRUZAM_POR_PROJETO or e2.papel in CRUZAM_POR_PROJETO:
                    continue
                if frozenset((e1.papel, e2.papel)) in NOS_NORMAIS or "pilar" in (e1.papel, e2.papel):
                    continue                                 # no pilar é o nó (a ligação), não o choque
                L1, L2 = math.dist(e1.inicio, e1.fim), math.dist(e2.inicio, e2.fim)
                if L1 < 200.0 or L2 < 200.0:
                    continue
                d, s, t, c = _seg_seg(e1.inicio, e1.fim, e2.inicio, e2.fim)
                if d >= tol or not (longe_da_ponta < s * L1 < L1 - longe_da_ponta and longe_da_ponta < t * L2 < L2 - longe_da_ponta):
                    continue
                par = tuple(sorted((p1.split("#")[0], p2.split("#")[0])))
                if par not in por_par:
                    por_par[par] = {"tipo": "choque", "ids": [e1.id, e2.id], "ponto": [round(v) for v in c], "n": 0,
                                    "texto": "%s (%s) atravessa %s (%s)" % (_nome(e1), e1.papel, _nome(e2), e2.papel)}
                por_par[par]["n"] += 1
    out = list(por_par.values())
    for a in out:
        if a["n"] > 1:
            a["texto"] += " — %d cruzamentos" % a["n"]
    return out


def telha_ao_lado(doc, limite: float = 20.0) -> List[dict]:
    """a telha de teste lançada só na conta (nada entra no modelo): o degrau entre chapas vizinhas e a dobra na caída"""
    from nucleo3d import telhas_cobertura as tc
    tercas = [b for b in doc.barras if b.papel in ("terça", "terca")]
    if len(tercas) < 2:
        return []
    an = tc._analise(tercas, doc.barras)
    chapas = tc._chapas(an["panos"], dict(tc.TELHA_PADRAO))
    g = _grade(tercas, 2000.0)
    out = []
    for a in tc.conferir_ao_lado(chapas, limite):
        if a["tipo"] == "degrau":
            txt = "telha: degrau de %d mm entre chapas vizinhas (as terças das duas faixas não estão na mesma altura)" % abs(a["mm"])
        else:
            txt = "telha: dobra de %d mm na caída (a terça %s da reta das vizinhas)" % (abs(a["mm"]), "acima" if a["mm"] > 0 else "abaixo")
        # as terças do ponto (para a tela selecionar e enquadrar) e a altura delas ali
        P = (a["ponto"][0], a["ponto"][1])
        cel = (int(P[0] // 2000.0), int(P[1] // 2000.0))
        perto = []
        for k in {j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in g.get((cel[0] + dx, cel[1] + dy), ())}:
            b = tercas[k]
            d = _dist_seg((P[0], P[1], 0.0), (b.inicio[0], b.inicio[1], 0.0), (b.fim[0], b.fim[1], 0.0))
            if d <= 400.0:
                perto.append((d, b))
        perto.sort(key=lambda x: x[0])
        z = sum((b.inicio[2] + b.fim[2]) / 2 for _d, b in perto[:2]) / len(perto[:2]) if perto else 0.0
        out.append({"tipo": a["tipo"], "mm": a["mm"], "ids": [b.id for _d, b in perto[:3]], "ponto": [P[0], P[1], round(z)],
                    "texto": txt})
    return out


REGRA_EM_TEXTO = {"T2": "banzo em U com a boca para o miolo", "T3": "peça em pé em U com a boca para o meio do vão",
                  "T4": "diagonal em U com a boca para cima", "T5": "cantoneira com a aba do mesmo lado das outras"}


def posicao_na_trelica(barras) -> List[dict]:
    """as peças da treliça fora das regras de posição (nucleo3d/regras_trelica — usuário, 16/10: "perfis de canto com a
    boca virada para o lado errado"): o U de boca para fora, a cantoneira do outro lado do plano"""
    from nucleo3d import regras_trelica
    out = []
    for v in regras_trelica.conferir(barras):
        out.append({"tipo": "posicao", "ids": [v["id"]], "ponto": v["ponto"],
                    "texto": "%s (%s, %s) girada %.0f° da regra %s: %s" % (
                        v["nome"] or v["perfil"], v["perfil"], v["papel"], v["erro_graus"], v["regra"],
                        REGRA_EM_TEXTO.get(v["regra"], ""))})
    return out


def conferir(doc, telha: bool = True, soltas: bool = True) -> dict:
    """as quatro contas no modelo; devolve {apontamentos: [...] (do mais grave para o menos), contagens}. Sem `soltas`,
    as pontas soltas ficam de fora (a tela Verificar apoios já as diz pelas regras dela)"""
    barras = list(doc.barras)
    rep = repetidas(barras)
    soltas = pontas_soltas(barras, list(doc.solidos)) if soltas else []
    ch = choques(barras)
    tl = telha_ao_lado(doc) if telha else []
    pos = posicao_na_trelica(barras)
    ordem = {"repetida": 0, "choque": 1, "posicao": 2, "degrau": 3, "dobra": 4, "ponta_solta": 5}
    aps = sorted(rep + ch + pos + tl + soltas, key=lambda a: (ordem.get(a["tipo"], 9), -abs(a.get("mm") or 0)))
    return {"apontamentos": aps,
            "contagens": {"repetidas": len(rep), "choques": len(ch), "pontas_soltas": len(soltas),
                          "fora_da_posicao": len(pos),
                          "tercas_em_balanco": sum(1 for a in soltas if "balanço" in a["texto"]),
                          "telha_degraus": sum(1 for a in tl if a["tipo"] == "degrau"),
                          "telha_dobras": sum(1 for a in tl if a["tipo"] == "dobra"),
                          "telha_acima_de_5cm": sum(1 for a in tl if abs(a["mm"]) >= 50)}}


def avisos(conf: dict, desl: Sequence[float] = (0.0, 0.0), telha_min: float = 50.0) -> List[str]:
    """os apontamentos em texto de aviso, com o ponto em mm do DESENHO (o modelo − `desl`), como os outros avisos da
    montagem (a montagem troca o ponto pelos eixos). A telha abaixo de `telha_min` fica só na contagem"""
    c = conf["contagens"]
    out = ["Conferência do 3D: %d peça(s) repetida(s), %d choque(s) entre peças, %d peça(s) da treliça fora da posição "
           "da regra, %d ponta(s) solta(s) (%d terça(s) em balanço), telha ao lado: %d degrau(s) e %d dobra(s) acima de "
           "20 mm (%d acima de 5 cm)."
           % (c["repetidas"], c["choques"], c.get("fora_da_posicao", 0), c["pontas_soltas"], c["tercas_em_balanco"],
              c["telha_degraus"], c["telha_dobras"], c["telha_acima_de_5cm"])]
    for a in conf["apontamentos"]:
        if a["tipo"] in ("degrau", "dobra") and abs(a.get("mm") or 0) < telha_min:
            continue
        x, y = a["ponto"][0] - desl[0], a["ponto"][1] - desl[1]
        out.append("Conferência do 3D em (%.0f; %.0f): %s." % (x, y, a["texto"]))
    return out
