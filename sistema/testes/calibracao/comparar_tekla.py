# -*- coding: utf-8 -*-
"""Calibração (08/10/2026): as peças do nosso modelo × as mesmas peças no Tekla (tekla_entrada.json × tekla_pecas.json).

    python testes/calibracao/comparar_tekla.py <pasta>

Por perfil: quantidade, comprimento total, área da seção, kg/m, peso total e área de pintura — o nosso (o mesmo cálculo da
lista de materiais e dos resumos: o kg/m do perfil e o perímetro da seção) e o do Tekla (o perfil paramétrico dele, com a
densidade do Steel_Undefined, 7.850 kg/m³). Grava `comparacao_tekla.json`.
"""
import collections
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, SISTEMA)


def comparar(pasta: str) -> dict:
    from nucleo.perfis_fabrica import perfil_de_fabrica
    from saida.resumos import _perimetro_m
    E = {p["id"]: p for p in json.load(open(os.path.join(pasta, "tekla_entrada.json"), encoding="utf-8"))["pecas"]}
    T = json.load(open(os.path.join(pasta, "tekla_pecas.json"), encoding="utf-8"))["pecas"]
    grupos = collections.defaultdict(list)
    for t in T:
        grupos[E[t["id"]]["perfil_nosso"]].append(t)
    out = {}
    for perfil, ts in sorted(grupos.items()):
        p = perfil_de_fabrica(perfil)
        L_nosso = sum(math.dist(E[t["id"]]["inicio"], E[t["id"]]["fim"]) for t in ts) / 1000.0
        L_tekla = sum(t["LENGTH"] for t in ts) / 1000.0
        per = _perimetro_m(perfil) or 0.0
        out[perfil] = {
            "perfil_tekla": ts[0]["perfil"], "pecas": len(ts),
            "comprimento_m": [round(L_nosso, 3), round(L_tekla, 3)],
            "area_secao_cm2": [round(p.A, 3), round(ts[0]["PROFILE.CROSS_SECTION_AREA"] / 100.0, 3)],
            "kg_m": [round(p.massa, 3), round(sum(t["WEIGHT"] for t in ts) / max(L_tekla, 1e-9), 3)],
            "peso_kg": [round(L_nosso * p.massa, 1), round(sum(t["WEIGHT"] for t in ts), 1)],
            "pintura_m2": [round(L_nosso * per, 2), round(sum(t["AREA"] for t in ts) / 1e6, 2)],
            "nome_resolvido": getattr(p, "nome", ""),
        }
    with open(os.path.join(pasta, "comparacao_tekla.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


def imprimir(out: dict) -> None:
    pct = lambda a, b: 100.0 * (b - a) / a if a else 0.0                   # noqa: E731
    print("%-20s %-18s %4s %16s %16s %14s %18s %18s" % ("perfil", "Tekla", "pç", "compr. (m) n/T", "A (cm²) n/T", "kg/m n/T", "peso (kg) n/T", "pintura (m²) n/T"))
    tot = [0, 0, 0, 0]
    for perfil, r in out.items():
        print("%-20s %-18s %4d %7.2f/%-7.2f %6.2f/%-6.2f(%+.1f%%) %5.2f/%-5.2f %7.1f/%-7.1f(%+.1f%%) %7.2f/%-7.2f(%+.1f%%)" % (
            perfil[:20], r["perfil_tekla"], r["pecas"], *r["comprimento_m"], *r["area_secao_cm2"], pct(*r["area_secao_cm2"]),
            *r["kg_m"], *r["peso_kg"], pct(*r["peso_kg"]), *r["pintura_m2"], pct(*r["pintura_m2"])))
        tot = [tot[0] + r["peso_kg"][0], tot[1] + r["peso_kg"][1], tot[2] + r["pintura_m2"][0], tot[3] + r["pintura_m2"][1]]
    print("TOTAL: peso %.1f / %.1f kg (%+.1f%%), pintura %.2f / %.2f m² (%+.1f%%)" % (tot[0], tot[1], pct(tot[0], tot[1]), tot[2], tot[3], pct(tot[2], tot[3])))


if __name__ == "__main__":
    imprimir(comparar(sys.argv[1]))
