# -*- coding: utf-8 -*-
"""Calibração (08/10/2026): o nosso motor × o OpenSees no mesmo modelo (modelo.json × opensees.json).

    python testes/calibracao/comparar.py <pasta com modelo.json e opensees.json>

Por caso de carga: o maior deslocamento de cada um, as reações somadas e por apoio, e as forças nas pontas das barras
(N, cortantes, torção, momentos) — a diferença de cada grandeza sobre o maior valor dela no caso (assim a barra quase
descarregada não vira "100 %" de diferença). Grava `comparacao.json` ao lado e imprime o resumo.
"""
import json
import os
import sys

import numpy as np

NOMES_PONTA = ["N", "Vy", "Vz", "T", "My", "Mz"]


def comparar(pasta: str) -> dict:
    M = json.load(open(os.path.join(pasta, "modelo.json"), encoding="utf-8"))
    O = json.load(open(os.path.join(pasta, "opensees.json"), encoding="utf-8"))
    out = {"casos": _bloco(M["nossos"]["casos"], O["casos"], "pontas")}
    so = M["nossos"].get("segunda_ordem") or {}
    if O.get("segunda_ordem"):
        out["segunda_ordem"] = _bloco(so, O["segunda_ordem"], "pontas_nos")
    if O.get("segunda_ordem_dividida"):
        out["segunda_ordem_dividida"] = _bloco(so, O["segunda_ordem_dividida"], "pontas_nos")
    with open(os.path.join(pasta, "comparacao.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def _bloco(nossos: dict, deles: dict, chave_pontas: str) -> dict:
    res = {}
    for caso, o in deles.items():
        n = nossos.get(caso)
        if n is None:
            continue
        if "erro" in o:
            res[caso] = {"erro": o["erro"]}
            continue
        Un, Uo = np.array(n["U"]), np.array(o["U"])
        tn, to = np.linalg.norm(Un[:, :3], axis=1), np.linalg.norm(Uo[:, :3], axis=1)
        i_max = int(np.argmax(tn))
        dU = float(np.max(np.linalg.norm(Un[:, :3] - Uo[:, :3], axis=1)))
        Rn = {k: np.array(v) for k, v in n["reacoes"].items()}
        Ro = {k: np.array(v) for k, v in o["reacoes"].items()}
        soma_n = sum(Rn.values())
        soma_o = sum(Ro.values())
        escala_R = max(float(np.max(np.abs(np.stack(list(Rn.values()))[:, :3]))), 1e-9)
        dR = max(float(np.max(np.abs(Rn[k][:3] - Ro[k][:3]))) for k in Rn)
        Pn, Po = np.array(n[chave_pontas]), np.array(o["pontas"])      # (barras, 12) local
        por_grandeza = {}
        for j, nome in enumerate(NOMES_PONTA):
            a = np.concatenate([Pn[:, j], Pn[:, j + 6]])
            b = np.concatenate([Po[:, j], Po[:, j + 6]])
            esc = max(float(np.max(np.abs(a))), 1e-9)
            dif = np.abs(a - b)
            k = int(np.argmax(dif))
            por_grandeza[nome] = {"max": round(esc, 4), "dif_max": round(float(dif[k]), 5), "dif_pct": round(100 * float(dif[k]) / esc, 4),
                                  "barra": int(k % len(Pn)), "nosso": round(float(a[k]), 4), "opensees": round(float(b[k]), 4)}
        res[caso] = {
            "desloc_max_mm": [round(1000 * float(tn[i_max]), 3), round(1000 * float(to[i_max]), 3)], "no_desloc_max": i_max,
            "desloc_dif_max_mm": round(1000 * dU, 4), "desloc_dif_pct": round(100 * dU / max(float(tn.max()), 1e-12), 4),
            "reacao_soma_nosso": np.round(soma_n[:3], 3).tolist(), "reacao_soma_opensees": np.round(soma_o[:3], 3).tolist(),
            "reacao_dif_max_kN": round(dR, 4), "reacao_dif_pct": round(100 * dR / escala_R, 4),
            "pontas": por_grandeza,
        }
    return res


def imprimir(out: dict) -> None:
    for bloco, titulo in (("casos", "1ª ORDEM, POR CASO"), ("segunda_ordem", "2ª ORDEM (OpenSees: uma barra por elemento)"),
                          ("segunda_ordem_dividida", "2ª ORDEM (OpenSees: cada barra em 4 trechos, a referência)")):
        if out.get(bloco):
            print("\n== " + titulo)
            _imprimir_bloco(out[bloco])


def _imprimir_bloco(blo: dict) -> None:
    print("%-18s %18s %9s %22s %9s %s" % ("caso", "desl. máx (mm) n/o", "dif %", "ΣRz (kN) nosso/OS", "reação %", "pontas: maior dif % (N Vy Vz T My Mz)"))
    for caso, r in blo.items():
        if "erro" in r:
            print(caso, r["erro"])
            continue
        p = r["pontas"]
        print("%-18s %8.2f / %-8.2f %8.3f %10.2f / %-10.2f %8.3f   %s" % (
            caso, r["desloc_max_mm"][0], r["desloc_max_mm"][1], r["desloc_dif_pct"], r["reacao_soma_nosso"][2],
            r["reacao_soma_opensees"][2], r["reacao_dif_pct"], "  ".join("%.3f" % p[k]["dif_pct"] for k in NOMES_PONTA)))


if __name__ == "__main__":
    imprimir(comparar(sys.argv[1]))
