"""As bases dos pilares com as reações da análise — etapa 5 do plano da análise estrutural (07/10/2026).

Para cada base (o pé de cada pilar), cada combinação última de cada situação (a cobertura retrátil calcula aberta e
retraída) dá a reação concomitante — N, os momentos e o cortante da MESMA combinação, já com a 2ª ordem. A reação vai
para os eixos do pilar: o momento em torno do eixo de maior inércia (o vetor na direção ez da seção, a largura) é o
que a ABNT NBR 8800:2024, 6.7, cobre; o do eixo fraco fica apontado (6.7.1.3: "são previstos apenas os casos de
momento fletor atuante em torno do eixo de maior momento de inércia do perfil").

A base sai de `nucleo.base_pilar.dimensionar` (a mais leve que passa em todas as combinações). Pilar tubular não é da
6.7 (ABNT NBR 16239): fica com as reações e o apontamento.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np


def _perfil_mm(nome: str) -> Optional[dict]:
    from nucleo3d.calculo_ifc import _perfil_de
    p = _perfil_de(nome or "", "", {}, {})
    if p is None:
        return None
    r = {"nome": p.nome, "tipo": p.tipo, "d": float(p.d or 0), "bf": float(p.bf or 0), "tw": float(p.tw or 0), "tf": float(p.tf or 0)}
    dados = getattr(p, "dados", {}) or {}
    if dados.get("h") and dados.get("d_linha"):
        r["r"] = (float(dados["h"]) - float(dados["d_linha"])) / 2          # o raio de concordância mesa–alma (laminado)
    return r


def ligacoes_no_topo(sits: Dict[str, dict], par: dict) -> List[dict]:
    """a ligação da viga apoiada no topo de cada pilar por duas chapas parafusadas (nucleo/ligacao_topo_pilar.py), com
    os esforços concomitantes de todas as combinações últimas das situações"""
    from nucleo import ligacao_topo_pilar as LT
    por: Dict[str, dict] = {}
    for nome, r in sits.items():
        for tp in r.get("topos_pilares") or []:
            e = por.setdefault(tp["pilar_chave"], dict(tp, combinacoes=[], pontas=[]))
            e["combinacoes"] += [dict(c, sit=nome) for c in tp["combinacoes"]]
            for k, pv in enumerate(tp.get("pontas_viga") or []):
                if k >= len(e["pontas"]):
                    e["pontas"].append({"viga": pv["viga"], "combinacoes": []})
                e["pontas"][k]["combinacoes"] += [dict(c, sit=nome) for c in pv["combinacoes"]]
    saida, cache = [], {}
    for k, e in sorted(por.items(), key=lambda kv: tuple(int(v) for v in kv[0].split(","))):
        pil, vig = _perfil_mm(e["pilar"]), _perfil_mm(e["viga"])
        item = {"chave": k, "pilar": e["pilar"], "viga": e["viga"], "viga_continua": e["viga_continua"],
                "viga_ao_longo": e["viga_ao_longo"], "xyz": e["xyz"]}
        if pil is None or vig is None or vig["tipo"] not in ("I", "H", "W"):
            item.update(ok=None, aviso="perfis fora do método (viga I/H sobre pilar)")
            saida.append(item)
            continue
        combs = e["combinacoes"]
        chave = (e["pilar"], e["viga"], e["viga_continua"], e["viga_ao_longo"], tuple((c["N"], c["Mz"], c["My"], c["V"], c["T"]) for c in combs))
        if chave not in cache:
            cache[chave] = LT.dimensionar(pil, vig, combs, viga_continua=e["viga_continua"], viga_ao_longo=e["viga_ao_longo"])
        lg = cache[chave]
        env = {"N_max": max(combs, key=lambda c: c["N"]), "N_min": min(combs, key=lambda c: c["N"]),
               "M_max": max(combs, key=lambda c: math.hypot(c["Mz"], c["My"])), "V_max": max(combs, key=lambda c: c["V"])}
        item.update(ok=bool(lg and lg["ok"]), envoltoria=env,
                    ligacao={kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in (lg or {}).items() if kk != "combinacoes"})
        # a viga emendada sobre o pilar: cada ponta transmite o momento dela pela chapa do topo — verificada à parte
        if e.get("pontas") and lg:
            g_tr = lg["gy"] if e["viga_ao_longo"] == "x" else lg["gx"]
            pts_ = []
            for pv in e["pontas"]:
                cs = pv["combinacoes"]
                ck = (pv["viga"], g_tr, tuple((c["N"], c["Mz"], c["My"], c["V"], c["T"]) for c in cs))
                if ck not in cache:
                    cache[ck] = LT.dimensionar_ponta(vig, cs, g_tr)
                pp = cache[ck]
                pts_.append({"viga": pv["viga"], "ok": bool(pp and pp["ok"]),
                             "M_max": max((abs(c["Mz"]) for c in cs), default=0.0), "V_max": max((abs(c["N"]) for c in cs), default=0.0),
                             "ligacao": {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in (pp or {}).items()}})
            item["pontas_viga"] = pts_
            item["ok"] = item["ok"] and all(p_["ok"] for p_ in pts_)
            # as chapas das pontas apoiam lado a lado na do topo: ela precisa ter, ao longo da viga, a soma delas
            soma = sum(float(p_["ligacao"].get("Lp") or 0.0) for p_ in pts_)
            b_long = lg["Bx"] if e["viga_ao_longo"] == "x" else lg["By"]
            item["chapa_topo_ao_longo_mm"] = round(max(soma, b_long), 0)
            mx = ("%.1f" % max(p_["M_max"] for p_ in pts_)).replace(".", ",")
            item["aviso"] = ("a viga chega ao pilar em duas peças: o momento de uma peça para a outra (até %s kN·m na ponta) "
                             "passa pelas chapas — cada ponta tem a sua ligação; tornar a viga contínua sobre o pilar (emenda "
                             "fora dele, perto do momento nulo) deixa a ligação só com o que o pilar recebe" % mx)
        saida.append(item)
    return saida


def reacoes_por_base(sits: Dict[str, dict]) -> Dict[str, dict]:
    """{chave da base: {perfil, tipo do apoio, ey, ez, combinações [{sit, comb, N, M_forte, M_fraco, V, Mz (torção)}]}}"""
    out: Dict[str, dict] = {}
    for nome, r in sits.items():
        barras = r["barras"]
        elu = [c for c, cb in r["combinacoes"].items() if cb["tipo"] == "ELU"]
        for ap in r["apoios"]:
            no = int(ap["no"])
            pil = next((b for b in barras if b.get("papel") == "pilar" and no in (b["a"], b["b"])), None)
            if pil is None:
                continue
            e = out.setdefault(ap["chave"], {"chave": ap["chave"], "apoio": ap["tipo"], "perfil": pil["perfil"],
                                             "ey": pil["ey"], "ez": pil["ez"], "combinacoes": []})
            ey, ez = np.array(pil["ey"], float), np.array(pil["ez"], float)
            for c in elu:
                rr = r["por_comb"][c]["reacoes"].get(str(no))
                if rr is None:
                    continue
                F, Mv = np.array(rr[:3], float), np.array(rr[3:6], float)
                e["combinacoes"].append({"sit": nome, "comb": c, "N": round(float(F[2]), 2),
                                         "M": round(abs(float(Mv @ ez)), 3), "M_fraco": round(abs(float(Mv @ ey)), 3),
                                         "V": round(float(math.hypot(F[0], F[1])), 2), "T": round(float(Mv[2]), 3)})
    return out


def dimensionar_bases(sits: Dict[str, dict], par: dict) -> List[dict]:
    """cada base: as reações concomitantes e a base pela NBR 8800:2024, 6.7 (ou o motivo de não ter)"""
    from nucleo import base_pilar as BP, materiais as mat
    fck = float(par.get("base_fck_mpa") or 25.0)
    aco = par.get("base_aco_placa") or "ASTM A36"
    fy = mat.aco(aco).fy * 10.0 if aco in mat.ACOS else 250.0
    saida = []
    cache: Dict[tuple, dict] = {}
    for k, e in sorted(reacoes_por_base(sits).items(), key=lambda kv: tuple(int(v) for v in kv[0].split(","))):
        item = {"chave": k, "apoio": e["apoio"], "perfil": e["perfil"], "combinacoes": e["combinacoes"], "avisos": [],
                "fck": fck, "aco_placa": aco}
        combs = e["combinacoes"]
        item["envoltoria"] = {
            "N_max": max(combs, key=lambda c: c["N"]), "N_min": min(combs, key=lambda c: c["N"]),
            "M_max": max(combs, key=lambda c: c["M"]), "V_max": max(combs, key=lambda c: c["V"]),
            "M_fraco_max": max(combs, key=lambda c: c["M_fraco"])} if combs else {}
        p = _perfil_mm(e["perfil"])
        if p is None:
            item.update(ok=False, metodo=None, avisos=["perfil do pilar fora do catálogo"])
            saida.append(item)
            continue
        tubo = p["tipo"] == "tubo"
        if not tubo and (p["tipo"] not in ("I", "H", "W") or not p["bf"]):
            item.update(ok=None, metodo=None)
            item["avisos"].append("pilar %s: perfil sem método de base no sistema (a NBR 8800:2024, 6.7, é para I/H; a NBR "
                                  "16239, 8, para tubos)" % e["perfil"])
            saida.append(item)
            continue
        if tubo and max(p["d"], p["bf"]) > 510:
            item["avisos"].append("pilar %s com mais de 510 mm: fora da NBR 16239, 8.1.1" % e["perfil"])
        if e["apoio"] != "engastada":
            combs = [dict(c, M=0.0) for c in combs]
        chave = (e["perfil"], tuple((c["N"], c["M"], c["V"]) for c in combs), fck, fy)
        if chave not in cache:
            # I/H: tipo 2 (chumbadores internos) só sem momento; com momento, tipo 1. Tubo: retangular tipo 1;
            # circular tipo 2 (placa retangular) ou 3 (placa circular)
            if tubo:
                tipos = (2, 3) if not p["bf"] else (1,)
            else:
                tipos = (2, 1) if all(c["M"] < 1e-6 for c in combs) else (1,)
            cache[chave] = BP.dimensionar(p, combs, fck, fy, tipos=tipos)
        b = cache[chave]
        item.update(ok=bool(b.get("ok")), metodo=b.get("norma") or "NBR 8800:2024, 6.7", base=_resumo(b))
        # o detalhe pensado para a obra (07/10): chumbador em J concretado com a armadura do bloco e abas de reforço
        g_ = b.get("geometria") or {}
        if g_.get("db") and b.get("tabela"):
            Ft_max = max((r.get("Ft") or 0.0) for r in (b.get("combinacoes") or [{}]))
            item["chumbador_j"] = {kk: (round(v, 2) if isinstance(v, float) else v)
                                   for kk, v in BP.chumbador_j(Ft_max, g_["db"], fck, float(b["tabela"]["h1"])).items()}
            item["chumbador_j"]["Ft_kN"] = round(Ft_max, 2)
        if not tubo and g_.get("tipo") == 1 and any(c["M"] > 1e-6 for c in combs):
            ab = BP.com_abas(p, combs, g_, fck, fy)
            item["com_abas"] = {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in ab.items()}
        mf = max((c["M_fraco"] for c in combs), default=0.0)
        mF = max((c["M"] for c in combs), default=0.0)
        if e["apoio"] == "engastada" and mf > max(1.0, 0.10 * mF) and not (tubo and not p["bf"]):
            cf = max(combs, key=lambda c: c["M_fraco"])
            item["avisos"].append(("momento no eixo fraco do pilar até %.1f kN·m (%s · %s) — a 6.7 só prevê o momento em "
                                   "torno do eixo de maior inércia (6.7.1.3): a base precisa de outro método (enrijecedores, "
                                   "verificação em flexão oblíqua) ou de contraventamento nessa direção") % (mf, cf["sit"], cf["comb"]))
        if not b.get("ok"):
            item["avisos"].append("a base não fecha pela %s com chumbadores até ø 2\" e chapa até %.0f mm: %s" %
                                  (item["metodo"], BP.CHAPAS_MM[-1], "; ".join((b.get("falhas") or [])[:3])))
        saida.append(item)
    return saida


def _resumo(b: dict) -> dict:
    """o que a tela e o memorial precisam da base (sem as linhas de todas as combinações, só as que governam)"""
    g = b.get("geometria") or {}
    linhas = b.get("combinacoes") or []
    criticas = sorted(linhas, key=lambda r: -(r.get("tp_min") or 0))[:3] + sorted(linhas, key=lambda r: -(r.get("Ft") or 0))[:2]
    vistos, crit = set(), []
    for r in criticas:
        k = (r.get("sit"), r.get("comb"))
        if k not in vistos:
            vistos.add(k)
            crit.append({kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in r.items()})
    return {"ok": b.get("ok"), "falhas": b.get("falhas"), "norma": b.get("norma"), "ld": g.get("ld"),
            "tipo": g.get("tipo"), "nb": g.get("nb"), "diametro": g.get("diametro"),
            "db": g.get("db"), "lx": g.get("lx"), "ly": g.get("ly"), "a": g.get("a"), "a1": g.get("a1"), "a2": g.get("a2"),
            "tp": b.get("tp"), "tp_min": round(b.get("tp_min") or 0, 2), "dispositivo": b.get("dispositivo"),
            "placa_cisalhamento": b.get("placa_cisalhamento"), "bloco": b.get("bloco"), "tabela": b.get("tabela"),
            "governa_tp": b.get("governa_tp"), "governa_ft": b.get("governa_ft") or None, "peso_kg": b.get("peso_kg"),
            "criticas": crit,
            "casos": sorted({r.get("caso") for r in linhas if r.get("caso")})}


__all__ = ["reacoes_por_base", "dimensionar_bases"]
