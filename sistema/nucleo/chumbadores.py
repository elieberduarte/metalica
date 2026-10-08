# -*- coding: utf-8 -*-
"""Chumbadores pós-instalados do catálogo (dados/fornecedores/chumbadores.json): a resistência por chumbador que a
ancoragem da análise estrutural compara com o que a estrutura aplica no pilar de concreto.

Critério do usuário (08/10/2026): "por enquanto vamos adotar a mais conservadora". Então:

* a resistência é a carga **permissível** do fabricante (Hardbolt: já dividida por C.S. 4,0), usada direto contra os
  esforços das combinações últimas (que já trazem os coeficientes de ponderação) — sem converter para resistência
  de cálculo;
* o f_ck cai para a coluna de baixo da tabela (20, 30, 40 MPa), sem interpolar; abaixo de 20 não há valor, acima de
  40 vale o de 40 e o fabricante não recomenda;
* espaçamento e borda: o fator da maior distância da tabela que não passa da informada (sem interpolar); abaixo do
  mínimo não há valor; os fatores de espaçamento e de borda se multiplicam; sem as distâncias, a tabela vale só se
  S ≥ Scr e C ≥ Ccr (fica dito no resultado);
* a interação de tração e corte é a linear (soma ≤ 1,0), não a do catálogo (≤ 1,2) — essa fica na tela da análise.
"""
import json
import os
from typing import Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO = os.path.join(BASE, "dados", "fornecedores", "chumbadores.json")
KGF_KN = 9.80665 / 1000.0

_dados = None


def dados() -> dict:
    global _dados
    if _dados is None:
        try:
            with open(ARQUIVO, encoding="utf-8") as f:
                _dados = json.load(f)
        except (OSError, ValueError):
            _dados = {}
    return _dados


def opcoes() -> dict:
    """O que a tela precisa para escolher: por diâmetro, os embutimentos da tabela de cargas e as distâncias crítica e mínima."""
    hb = dados().get("hardbolt") or {}
    F = hb.get("fatores") or {}
    por_d = {}
    for c in (hb.get("cargas") or {}).get("valores") or []:
        d = c["diametro"]
        o = por_d.setdefault(d, {"diametro": d, "embutimentos": [], "Scr": c["Scr_tracao"], "Ccr": c["Ccr_tracao"],
                                 "Scr_corte": c["Scr_corte"], "Ccr_corte": c["Ccr_corte"],
                                 "Smin": (F.get("espacamento_tracao_Fn") or {}).get("Smin", {}).get(d),
                                 "Cmin": (F.get("borda_tracao_Fn") or {}).get("Cmin", {}).get(d)})
        o["embutimentos"].append(c["embutimento"])
    return {"fabricante": hb.get("fabricante") or "", "produto": "Hardbolt", "fck": [20, 30, 40],
            "coeficiente": (hb.get("cargas") or {}).get("coeficiente_seguranca"), "diametros": list(por_d.values())}


def _fator(tabela: dict, d: str, dist: Optional[float], critica_rot: str):
    """(fator, texto, erro): a maior distância da tabela ≤ a informada; None → considera ≥ a crítica."""
    crit = (tabela.get("Scr") or tabela.get("Ccr") or {}).get(d)
    if dist is None:
        return 1.0, "%s ≥ %s mm (considerado)" % (critica_rot, crit), None
    linhas = [(l["distancia_mm"], l["fatores"][d]) for l in tabela.get("linhas") or [] if d in l["fatores"]]
    if not linhas:
        return None, "", "sem tabela para %s" % d
    if dist < linhas[0][0]:
        return None, "", "%s = %g mm abaixo do mínimo da tabela (%g mm)" % (critica_rot[0], dist, linhas[0][0])
    dist_t, f = max((x for x in linhas if x[0] <= dist), key=lambda x: x[0])
    return f, "%s = %g mm → fator %.2f (linha de %g mm)" % (critica_rot[0], dist, f, dist_t), None


def resistencia(diametro: str, embutimento: float, fck: Optional[float], S: Optional[float] = None,
                C: Optional[float] = None) -> dict:
    """{T_kN, V_kN, fck_tabela, fatores, detalhe[], avisos[], erro}: a tração e o corte por chumbador."""
    hb = dados().get("hardbolt") or {}
    linha = next((c for c in (hb.get("cargas") or {}).get("valores") or []
                  if c["diametro"] == diametro and abs(c["embutimento"] - float(embutimento)) < 0.5), None)
    if not linha:
        return {"erro": "Hardbolt %s com embutimento %s mm não está na tabela de cargas" % (diametro, embutimento)}
    avisos = []
    fck = float(fck) if fck else None
    if fck is None:
        fck_t = 20
        avisos.append("sem o f_ck do pilar: usada a coluna de 20 MPa (a menor)")
    elif fck < 20:
        return {"erro": "f_ck %g MPa abaixo de 20 MPa: o catálogo não dá carga (e não recomenda concreto de baixa resistência)" % fck}
    else:
        fck_t = max(x for x in (20, 30, 40) if x <= fck)
        if fck > 40:
            avisos.append("f_ck acima de 40 MPa: o fabricante não recomenda o Hardbolt (usado o valor de 40 MPa)")
        elif fck != fck_t:
            avisos.append("f_ck %g MPa: usada a coluna de %d MPa, sem interpolar" % (fck, fck_t))
    p = linha["permissivel_kgf"][str(fck_t)]
    F = hb.get("fatores") or {}
    partes, erro = {}, None
    for chave, tab, rot in (("Fn_espacamento", "espacamento_tracao_Fn", "S"), ("Fv_espacamento", "espacamento_corte_Fv", "S"),
                            ("Fn_borda", "borda_tracao_Fn", "C"), ("Fv_borda", "borda_corte_Fv", "C")):
        dist = S if rot == "S" else C
        f, txt, e = _fator(F.get(tab) or {}, diametro, dist, "Scr" if rot == "S" else "Ccr")
        if e:
            erro = e
            break
        partes[chave] = (f, txt)
    if erro:
        return {"erro": erro}
    fn = partes["Fn_espacamento"][0] * partes["Fn_borda"][0]
    fv = partes["Fv_espacamento"][0] * partes["Fv_borda"][0]
    T, V = p["tracao"] * KGF_KN * fn, p["corte"] * KGF_KN * fv
    detalhe = ["Hardbolt %s, embutimento %g mm, f_ck %d MPa: permissível %d kgf à tração e %d kgf ao corte (C.S. %g do fabricante)"
               % (diametro, linha["embutimento"], fck_t, p["tracao"], p["corte"], (hb.get("cargas") or {}).get("coeficiente_seguranca") or 4),
               "tração: espaçamento %s; borda %s → × %.2f" % (partes["Fn_espacamento"][1], partes["Fn_borda"][1], fn),
               "corte: espaçamento %s; borda %s → × %.2f" % (partes["Fv_espacamento"][1], partes["Fv_borda"][1], fv),
               "critério conservador: a carga permissível contra os esforços de cálculo, interação linear (≤ 1,0)"]
    if S is None or C is None:
        avisos.append("sem %s: a tabela vale para um chumbador longe dos outros e da borda (S ≥ Scr, C ≥ Ccr)"
                      % " e ".join(x for x, v in (("o espaçamento", S), ("a distância à borda", C)) if v is None))
    return {"T_kN": round(T, 2), "V_kN": round(V, 2), "fck_tabela": fck_t, "Fn": round(fn, 3), "Fv": round(fv, 3),
            "detalhe": detalhe, "avisos": avisos, "erro": None}
