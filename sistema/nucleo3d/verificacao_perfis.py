# -*- coding: utf-8 -*-
"""Verificação dos perfis da estrutura inteira, com os esforços do esqueleto (nucleo3d/esforcos.py).

Cada barra do esqueleto (o trecho de uma peça entre dois nós) é verificada em todas as
combinações últimas, pelo perfil dela: U e Ue formados a frio pela NBR 14762 (MRD, interação
N–M linear do item 9.8.2.4), laminados, cantoneiras e tubos pela NBR 8800 (interação do item
5.5.1.2), barra redonda só à tração. As resistências vêm das rotinas de `nucleo/verificar.py`
— as mesmas da tesoura importada e do galpão —, calculadas uma vez por perfil e comprimentos de
flambagem; a razão de cada combinação sai delas.

Os esforços: a força normal e o momento em torno do eixo forte (o plano vertical da barra) das
duas pontas, do cálculo; mais o momento da barra biapoiada com a carga dela, porque as cargas
entram nos nós (metade em cada ponta). A alma das treliças (montantes e diagonais), as correntes
e os contraventos só com a força normal (rótula nas pontas, como o projeto de treliça).

Comprimentos de flambagem (K = 1): no plano, o trecho entre nós; fora do plano, no banzo, a
distância entre os nós travados — onde chega uma peça fora do plano da treliça (terça,
corrente, contravento, viga, outra treliça) ou um pilar. As outras barras, o trecho entre nós.
"""
from __future__ import annotations

import collections
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

SO_NORMAL = {"montante", "diagonal", "corrente", "contraventamento"}
E_ACO_KN_CM2 = 20000.0             # E = 200 GPa
LIMITE_TRACIONADA = 300.0          # NBR 8800 5.2.8: L/r da tracionada (a redonda rosqueada é dispensada)


def _plano_das_pecas(nos: np.ndarray, barras: List[dict]) -> Dict[str, np.ndarray]:
    """a normal do plano de cada treliça (peça com banzo): a direção de menor espalhamento dos nós dela"""
    pts = collections.defaultdict(set)
    for b in barras:
        if b.get("peca") and b["papel"] in ("banzo", "montante", "diagonal"):
            pts[b["peca"]].update((b["a"], b["b"]))
    out = {}
    for peca, ns in pts.items():
        if len(ns) < 3:
            continue
        P = nos[sorted(ns)]
        P = P - P.mean(axis=0)
        _w, v = np.linalg.eigh(P.T @ P)
        out[peca] = v[:, 0]
    return out


def _fora_do_plano(nos, barras, usadas, planos) -> Dict[int, float]:
    """Ly (m) de cada trecho de banzo: a soma dos trechos colineares da mesma peça até o nó travado
    de cada lado"""
    por_no = collections.defaultdict(list)
    for e in usadas:
        b = barras[e]
        por_no[b["a"]].append(e)
        por_no[b["b"]].append(e)

    def direcao(e):
        b = barras[e]
        v = nos[b["b"]] - nos[b["a"]]
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-9 else v

    def travado(no, peca, normal):
        for e in por_no[no]:
            b = barras[e]
            if b.get("peca") == peca and b["papel"] in ("banzo", "montante", "diagonal"):
                continue
            if b["papel"] == "pilar" or abs(float(direcao(e) @ normal)) > 0.5:
                return True
        return len(por_no[no]) == 1                       # a ponta da peça: o apoio dela

    Ly = {}
    for e in usadas:
        b = barras[e]
        if b["papel"] != "banzo" or not b.get("peca") or b["peca"] not in planos:
            continue
        normal = planos[b["peca"]]
        u = direcao(e)
        total = float(np.linalg.norm(nos[b["b"]] - nos[b["a"]]))
        for ponta in (b["a"], b["b"]):
            no, atual, passos = ponta, e, 0
            while not travado(no, b["peca"], normal) and passos < 60:
                seg = [f for f in por_no[no] if f != atual and barras[f]["papel"] == "banzo"
                       and barras[f].get("peca") == b["peca"] and abs(float(direcao(f) @ u)) > 0.9]
                if not seg:
                    break
                atual = seg[0]
                bf = barras[atual]
                total += float(np.linalg.norm(nos[bf["b"]] - nos[bf["a"]]))
                no = bf["b"] if bf["a"] == no else bf["a"]
                passos += 1
        Ly[e] = total
    return Ly


def _cantoneira_dupla(p, aco: str, Lx_cm: float, Ly_cm: float) -> dict:
    """2L costas com costas (alma da treliça, com presilhas): a compressão do par pela NBR 8800
    (5.3.3, flambagem por flexão; Q da cantoneira), com o r de uma no plano da treliça e o do par
    fora dele (as duas encostadas, sem chapa entre elas). A flexo-torção do T não entra."""
    from nucleo import materiais as mat, nbr8800
    a = mat.aco(aco)
    b = float(p.bf or p.d or 25.4) / 10.0                        # mm → cm
    t = float(p.tf or p.tw or 3.18) / 10.0
    xb = (b * b + b * t - t * t) / (2.0 * (2.0 * b - t))          # centro da cantoneira de abas iguais até a costa
    A2 = 2.0 * p.A
    r_in = p.rx or p.ry
    r_out = math.sqrt((p.ry or r_in) ** 2 + xb ** 2)
    lam = max(Lx_cm / r_in, Ly_cm / r_out)
    try:
        Q = float(nbr8800.fator_Q(p, a)[0])
    except Exception:
        Q = 1.0
    Ne = math.pi ** 2 * E_ACO_KN_CM2 * A2 / lam ** 2
    lam0 = math.sqrt(Q * A2 * a.fy / Ne)
    chi = nbr8800.fator_chi(lam0)
    return {"Nc": chi * Q * A2 * a.fy / 1.10, "Nt": 2.0 * (A2 / 2.0) * a.fy / 1.10, "M": None,
            "esb_c": (lam, 200.0), "norma": "NBR 8800 (2L)"}


class _Resistencias:
    """as resistências de um perfil com os comprimentos de flambagem (cache por chave)"""

    def __init__(self):
        self.cache = {}
        self.perfis = {}

    def perfil(self, nome):
        if nome not in self.perfis:
            from nucleo3d.calculo_ifc import _perfil_de
            self.perfis[nome] = _perfil_de(nome or "", "", {}, {})
        return self.perfis[nome]

    def de(self, nome: str, aco: str, Lx_cm: float, Ly_cm: float) -> Optional[dict]:
        chave = (nome, aco, round(Lx_cm / 5.0), round(Ly_cm / 5.0))
        if chave in self.cache:
            return self.cache[chave]
        from nucleo import perfis_fabrica, verificar
        p = self.perfil(nome)
        r = None
        if p is not None and p.A > 0:
            tipo = perfis_fabrica.tipo_de_verificacao(p)

            def menor(res, unidade):
                vs = [v.Rd for v in res.verificacoes if not v.dispensada and v.unidade == unidade and v.Rd > 0]
                return min(vs) if vs else None

            def esb(res, palavra):
                vs = [(v.Sd, v.Rd) for v in res.verificacoes if "sbeltez" in v.titulo and palavra in v.titulo and v.Rd]
                return vs[0] if vs else None
            rc = verificar.verificar_membro(p, aco, 1.0, 0.0, 0.0, Lx_cm, Ly_cm, 1, "")
            rt = verificar.verificar_membro(p, aco, 0.0, 1.0, 0.0, Lx_cm, Ly_cm, 1, "")
            rm = verificar.verificar_membro(p, aco, 0.0, 0.0, 1.0, Lx_cm, Ly_cm, 1, "")
            r = {"tipo": tipo, "Nc": None if tipo == "redonda" else menor(rc, "kN"), "Nt": menor(rt, "kN"),
                 "M": None if tipo == "redonda" else menor(rm, "kN·cm"),
                 "esb_c": esb(rc, "comprimida"), "esb_t": esb(rt, "tracionada"),
                 "norma": "NBR 14762" if tipo == "frio" else "NBR 8800"}
        self.cache[chave] = r
        return r


def verificar(doc, r: dict, aco_padrao: str = "ASTM A36") -> dict:
    """a razão (solicitante ÷ resistente) de cada barra do esqueleto na pior combinação, e o
    resumo por papel e por peça. `r` é o resultado de `esforcos.calcular` (com os campos internos)"""
    esq = r["esqueleto"]
    barras = esq["barras"]
    nos = np.array(esq["nos"], dtype=float) / 1000.0
    usadas = list(r["_usadas"])
    L = np.asarray(r["_L"], dtype=float)
    d = np.asarray(r["_d"], dtype=float)
    casos = list(r["_casos"])
    m0 = r["_m0"]
    combs = r["combinacoes"]
    n = len(usadas)
    FL = {c: np.array([r["esforcos"][e][c] for e in usadas], dtype=float) for c in casos}
    cperp = np.sqrt(np.clip(1.0 - (d[:, 2] / L) ** 2, 0.0, 1.0))
    planos = _plano_das_pecas(nos, barras)
    Ly = _fora_do_plano(nos, barras, usadas, planos)
    aco_de = {}
    ents = doc.entidades if hasattr(doc, "entidades") else {}
    for e in usadas:
        for i_d in barras[e]["ids"]:
            ent = ents.get(i_d) if hasattr(ents, "get") else None
            if ent is not None and getattr(ent, "aco", None):
                aco_de[e] = ent.aco
                break

    # os esforços de cálculo de cada combinação: N (+ tração) e o maior momento no eixo forte (kN·m)
    N = np.zeros((len(combs), n))
    M0v = np.zeros((len(combs), n))                     # o momento de vão simples (a carga da própria barra)
    Mp = np.zeros((len(combs), n))                      # o maior momento positivo (traciona embaixo)
    Mn = np.zeros((len(combs), n))                      # o maior negativo, em módulo
    for k, cb in enumerate(combs):
        f = cb["fatores"]
        soma = sum(fa * FL[c] for c, fa in f.items() if c in FL)
        mv = sum(fa * np.asarray(m0[c]) for c, fa in f.items() if c in m0) * cperp
        N[k] = soma[:, 6]
        M0v[k] = mv
        # o momento interno (positivo tracionando embaixo): f4 na ponta 1, −f10 na ponta 2, e a
        # parábola da carga da barra por cima da reta entre os dois; o maior em módulo ao longo dela
        ma, mb = soma[:, 4], -soma[:, 10]
        xi = np.where(np.abs(mv) > 1e-9, 0.5 + (mb - ma) / np.where(np.abs(mv) > 1e-9, 8.0 * mv, 1.0), 0.5)
        xi = np.clip(xi, 0.0, 1.0)
        m_pico = ma * (1 - xi) + mb * xi + 4.0 * mv * xi * (1 - xi)
        Mp[k] = np.clip(np.maximum.reduce([ma, mb, m_pico]), 0.0, None)
        Mn[k] = np.clip(-np.minimum.reduce([ma, mb, m_pico]), 0.0, None)

    # o banzo entre dois nós da alma (ou de apoio): o momento das pontas é o secundário do nó rígido,
    # que o projeto de treliça (nós rotulados) desconsidera — fica só o da carga da própria barra; o
    # trecho com um nó onde só chega carga (a terça fora do nó da alma) leva a flexão local, que é real
    no_de_alma = collections.defaultdict(set)            # peça → nós onde chega alma dela ou pilar
    for e in usadas:
        b = barras[e]
        if b["papel"] in ("montante", "diagonal") and b.get("peca"):
            no_de_alma[b["peca"]].update((b["a"], b["b"]))
    nos_pilar = {n for e in usadas if barras[e]["papel"] == "pilar" for n in (barras[e]["a"], barras[e]["b"])}
    res = _Resistencias()
    saida = []
    for i, e in enumerate(usadas):
        b = barras[e]
        papel = b["papel"]
        nome = b.get("perfil") or ""
        aco = aco_de.get(e, aco_padrao)
        n_p = 2 if b.get("duplo") else 1
        Lx_cm = L[i] * 100.0                            # no plano (o trecho entre nós)
        Ly_cm = Ly.get(e, L[i]) * 100.0                 # fora do plano (entre os travamentos)
        item = {"barra": e, "papel": papel, "perfil": nome, "peca": b.get("peca"), "ids": b["ids"], "n": n_p,
                "Lx_m": round(Lx_cm / 100.0, 2), "Ly_m": round(Ly_cm / 100.0, 2)}
        p = res.perfil(nome)
        banzo_deitado_u = papel == "banzo" and p is not None and p.tipo in ("U", "Ue")
        if banzo_deitado_u:
            # o banzo em U com as abas para dentro da treliça: no plano dela flamba em torno do eixo
            # fraco (o trecho entre nós), fora do plano em torno do forte (entre os travamentos)
            R = res.de(nome, aco, Ly_cm, Lx_cm)
        else:
            R = res.de(nome, aco, Lx_cm, Ly_cm)
        if R is None:
            item.update({"razao": None, "motivo": "perfil fora do catálogo"})
            saida.append(item)
            continue
        R = dict(R)
        if p is not None and p.tipo == "L" and n_p == 2:
            R.update(_cantoneira_dupla(p, aco, Lx_cm, Ly_cm))
            n_calc = 1                                  # a resistência já é do par
        else:
            n_calc = n_p
        Nk = N[:, i] / n_calc
        comp = np.clip(-Nk, 0.0, None)
        trac = np.clip(Nk, 0.0, None)
        razoes = np.zeros(len(combs))
        tipo = np.array(["—"] * len(combs), dtype=object)
        mrd_txt = None
        if papel in SO_NORMAL or R["tipo"] == "redonda":
            rm = np.zeros(len(combs))
        elif banzo_deitado_u and not b.get("deitada"):
            # o momento no plano vertical, no banzo em U deitado, é em torno do eixo fraco: conferência
            # elástica W_y·f_y/γ (a NBR 14762 não traz o MRD nesse eixo para o U)
            from nucleo import materiais as mat
            MRd = (p.Wy or 0.0) * mat.aco(aco).fy / 1.10
            alma_ = no_de_alma.get(b.get("peca"), set()) | nos_pilar
            if b["a"] in alma_ and b["b"] in alma_:
                M_ = np.abs(M0v[:, i]) / n_calc * 100.0       # entre nós da alma: só a carga da barra
                item["momento"] = "só o do vão (nós da alma rotulados)"
            else:
                M_ = np.maximum(Mp[:, i], Mn[:, i]) / n_calc * 100.0
                item["momento"] = "carga fora do nó da alma"
            rm = M_ / MRd if MRd > 0 else np.zeros(len(combs))
            mrd_txt = MRd
        elif banzo_deitado_u:
            # a treliça deitada (passarela): o momento vertical é no eixo forte, destravado entre os travamentos
            Rm = res.de(nome, aco, Ly_cm, Ly_cm)
            M_ = np.maximum(Mp[:, i], Mn[:, i]) / n_calc * 100.0
            rm = M_ / Rm["M"] if Rm and Rm["M"] else np.zeros(len(combs))
            mrd_txt = Rm["M"] if Rm else None
        elif papel == "terça" and R["M"]:
            # a terça: o momento positivo (gravidade) comprime a mesa de cima, travada pela telha; o
            # negativo (sucção) a de baixo, livre entre as correntes (o trecho entre nós)
            Rt = res.de(nome, aco, Lx_cm, 10.0)
            MRd_trav = Rt["M"] if Rt and Rt["M"] else R["M"]
            rm = np.maximum(Mp[:, i] / n_calc * 100.0 / MRd_trav, Mn[:, i] / n_calc * 100.0 / R["M"])
            mrd_txt = R["M"]
        else:
            M_ = np.maximum(Mp[:, i], Mn[:, i]) / n_calc * 100.0
            rm = M_ / R["M"] if R["M"] else np.zeros(len(combs))
            mrd_txt = R["M"]
        if R["tipo"] == "redonda":
            # a barra redonda (corrente, agulha, contravento) só trabalha tracionada: a compressão do
            # modelo elástico ela não pega (afrouxa)
            razoes = trac / R["Nt"] if R["Nt"] else razoes
            tipo[:] = "tração"
        else:
            rc = comp / R["Nc"] if R["Nc"] else np.where(comp > 0, np.inf, 0.0)
            rt = trac / R["Nt"] if R["Nt"] else np.zeros(len(combs))
            rn = np.maximum(rc, rt)
            if R["tipo"] == "frio":
                inter = rn + rm
            else:
                inter = np.where(rn >= 0.2, rn + 8.0 / 9.0 * rm, rn / 2.0 + rm)
            razoes = inter
            tipo = np.where(rm > 0.05 * np.maximum(rn, 1e-9), np.where(rn > 0.05 * rm, "interação N–M", "flexão"),
                            np.where(rc >= rt, "compressão", "tração")).astype(object)
        k = int(np.argmax(razoes)) if len(razoes) else 0
        rz = float(razoes[k]) if len(razoes) else 0.0
        # o limite de esbeltez da barra comprimida (KL/r ≤ 200) fica à parte da resistência: aparece
        # também na barra que quase não trabalha (a compressão de 1 kN que o modelo dá ao banzo de baixo)
        if R["tipo"] != "redonda" and comp.max() > 1e-6 and R["esb_c"]:
            item["esbeltez"] = round(R["esb_c"][0], 1)
            item["esbeltez_excede"] = R["esb_c"][0] > R["esb_c"][1] + 1e-6
        M_max = float(np.max(np.maximum(Mp[:, i], Mn[:, i]))) if papel not in SO_NORMAL else 0.0
        if item.get("momento", "").startswith("só o do vão"):
            M_max = float(np.max(np.abs(M0v[:, i])))
        item.update({"razao": round(rz, 3) if math.isfinite(rz) else 99.0, "combinacao": combs[k]["nome"],
                     "verificacao": str(tipo[k]), "norma": R["norma"],
                     "Nc_kN": round(float(comp.max()) * n_calc, 2), "Nt_kN": round(float(trac.max()) * n_calc, 2),
                     "M_kNm": round(M_max, 3),
                     "NcRd_kN": None if R["Nc"] is None else round(R["Nc"] * n_calc, 2),
                     "NtRd_kN": None if R["Nt"] is None else round(R["Nt"] * n_calc, 2),
                     "MRd_kNm": None if not mrd_txt else round(mrd_txt / 100.0 * n_calc, 3)})
        saida.append(item)

    # o resumo: por papel e por peça (a pior barra de cada uma)
    por_papel = collections.defaultdict(lambda: {"barras": 0, "passam": 0, "nao_passam": 0, "sem_perfil": 0, "pior": 0.0,
                                                 "esbeltez_excede": 0})
    por_peca: Dict[str, dict] = {}
    for it in saida:
        pp = por_papel[it["papel"]]
        pp["barras"] += 1
        if it["razao"] is None:
            pp["sem_perfil"] += 1
            continue
        pp["passam" if it["razao"] <= 1.0 else "nao_passam"] += 1
        pp["esbeltez_excede"] += 1 if it.get("esbeltez_excede") else 0
        pp["pior"] = max(pp["pior"], it["razao"])
        chave = it["peca"] or "%s %s" % (it["papel"], it["perfil"])
        if chave not in por_peca or it["razao"] > por_peca[chave]["razao"]:
            por_peca[chave] = it
    piores = sorted((it for it in saida if it["razao"] is not None), key=lambda it: -it["razao"])
    return {"barras": saida,
            "por_papel": {k: dict(v, pior=round(v["pior"], 3)) for k, v in sorted(por_papel.items())},
            "pecas": sorted(({"peca": k, **{c: v[c] for c in ("papel", "perfil", "razao", "combinacao", "verificacao",
                                                                 "Lx_m", "Ly_m", "Nc_kN", "Nt_kN", "M_kNm")}}
                             for k, v in por_peca.items()), key=lambda x: -x["razao"]),
            "piores": piores[:40],
            "resumo": {"barras": len(saida), "passam": sum(1 for it in saida if it["razao"] is not None and it["razao"] <= 1.0),
                       "nao_passam": sum(1 for it in saida if it["razao"] is not None and it["razao"] > 1.0),
                       "sem_perfil": sum(1 for it in saida if it["razao"] is None),
                       "esbeltez_excede": sum(1 for it in saida if it.get("esbeltez_excede")),
                       "combinacoes": len(combs)}}


def hipoteses() -> List[str]:
    return [
        "Cada barra do esqueleto (o trecho entre dois nós) verificada em todas as combinações últimas; a razão é a da pior.",
        "U e Ue formados a frio pela NBR 14762:2010 (MRD; interação N/NRd + M/MRd ≤ 1, item 9.8.2.4); laminados, "
        "cantoneiras e tubos pela NBR 8800:2024 (interação do item 5.5.1.2); barra redonda só à tração.",
        "Momento no eixo forte: o das pontas do cálculo mais o da barra biapoiada com a carga dela (as cargas entram nos nós). "
        "O momento no eixo fraco não entra nesta verificação.",
        "Alma das treliças, correntes e contraventos só com a força normal (rótula nas pontas).",
        "O limite de esbeltez da barra comprimida (KL/r ≤ 200; NBR 14762 9.7.4, NBR 8800 5.3.4) listado à parte da "
        "resistência, com a compressão que a barra leva.",
        "K = 1. No plano, o trecho entre nós; fora do plano, no banzo, a distância entre os nós travados (onde chega peça "
        "fora do plano da treliça, ou pilar); nas outras barras, o trecho entre nós. Sem efeitos de 2ª ordem.",
        "Banzo em U com as abas para dentro da treliça: no plano dela flamba e flete em torno do eixo fraco (flexão pela "
        "conferência elástica W·fy/γ), fora do plano em torno do forte; na treliça deitada, a flexão vertical é no eixo forte.",
        "Banzo entre dois nós da alma (ou de apoio): nós rotulados, como o projeto de treliça — o momento de continuidade do "
        "nó rígido não entra, só o da carga da própria barra; o trecho com carga fora do nó da alma (a terça) leva a flexão toda.",
        "Terça: o momento positivo (gravidade) com a mesa de cima travada pela telha; o negativo (sucção) com a de baixo livre "
        "entre as correntes.",
        "Alma em 2L (costas com costas, com presilhas): a compressão do par (NBR 8800, flexão; r de uma no plano, do par fora "
        "dele, sem chapa entre as duas; sem a flexo-torção). Outro perfil duplo (2U): o esforço dividido pelos dois.",
    ]


def verificar_cenarios(doc, r: dict) -> dict:
    """a verificação em três cenários de combinação — só as gravitacionais, com o vento de cpi
    negativo e com todos (o cpi +0,8 levanta a cobertura muito mais) —, para separar o que é da
    estrutura do que é da hipótese do vento; as peças com a pior razão de cada cenário"""
    import re
    fortes = set()
    for c in ((r.get("vento") or {}).get("casos") or []):
        m = re.search(r"cpi\s*([+-]?\d+(?:[.,]\d+)?)", c.get("descricao") or "")
        if m and float(m.group(1).replace(",", ".")) > 0:
            fortes.add(c["caso"])
    todos = r["combinacoes"]
    cenarios = [("gravidade", "só as cargas gravitacionais", [c for c in todos if not re.search(r"\bV\d", c["nome"])]),
                ("vento_leve", "com o vento de cpi negativo", [c for c in todos if not any(re.search(r"\b%s\b" % v, c["nome"]) for v in fortes)]),
                ("todas", "todas as combinações (com o vento de cpi +0,8)", todos)]
    saida = {"cenarios": [], "hipoteses": hipoteses()}
    por_peca: Dict[str, dict] = {}
    for chave, desc, combs in cenarios:
        if not combs:
            continue
        rr = dict(r)
        rr["combinacoes"] = combs
        v = verificar(doc, rr)
        saida["cenarios"].append({"chave": chave, "descricao": desc, "combinacoes": len(combs),
                                  "resumo": v["resumo"], "por_papel": v["por_papel"]})
        for it in v["barras"]:
            if it["razao"] is None:
                continue
            k = it["peca"] or "%s %s" % (it["papel"], it["perfil"])
            p = por_peca.setdefault(k, {"peca": k, "papel": it["papel"], "perfil": it["perfil"], "ids": [], "razoes": {}})
            if it["razao"] > p["razoes"].get(chave, -1.0):
                p["razoes"][chave] = it["razao"]
                if chave == "todas" or not p.get("verificacao"):
                    p.update({c: it[c] for c in ("verificacao", "combinacao", "Lx_m", "Ly_m", "Nc_kN", "Nt_kN", "M_kNm",
                                                  "NcRd_kN", "NtRd_kN", "MRd_kNm", "norma")})
                    p["ids"] = it["ids"]
            p.setdefault("todos_ids", set()).update(it["ids"])
    pecas = []
    for p in por_peca.values():
        p["todos_ids"] = sorted(p.get("todos_ids") or [])
        p["razao"] = max(p["razoes"].values()) if p["razoes"] else 0.0
        pecas.append(p)
    saida["pecas"] = sorted(pecas, key=lambda p: -p["razao"])
    return saida
