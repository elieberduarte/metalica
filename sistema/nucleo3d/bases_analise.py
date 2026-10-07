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
    return {"nome": p.nome, "tipo": p.tipo, "d": float(p.d or 0), "bf": float(p.bf or 0), "tw": float(p.tw or 0), "tf": float(p.tf or 0)}


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
