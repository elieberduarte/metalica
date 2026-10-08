# -*- coding: utf-8 -*-
"""Calibração da análise estrutural (08/10/2026): o modelo de cálculo de um projeto, como o nosso motor o monta, num
JSON que outros programas leem — o OpenSees (opensees_resolver.py) e o Tekla (tekla/*.ps1).

    python testes/calibracao/exportar_modelo.py <projeto> [pasta de saída]

Só lê o projeto (o modelo 3D e os parâmetros da análise gravados nele). Sai `modelo.json` com:

* nós (m), barras (pontas, comprimento, perfil, seção A/Iy/Iz/J, eixos locais, rótulas por grau), apoios e os graus que o
  nosso motor prende por não terem rigidez (nó só de barras rotuladas);
* os casos de carga (distribuídas por barra no global, forças nos nós) e as combinações da NBR 8800;
* os nossos resultados de 1ª ordem por caso (deslocamentos, reações, forças nas pontas das barras nos eixos locais) e, nas
  ELU, os da 2ª ordem (4.10.7) — o que os outros programas vão conferir.
"""
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
RAIZ = os.path.dirname(SISTEMA)
sys.path.insert(0, SISTEMA)

import numpy as np                                                     # noqa: E402

SAIDA_PADRAO = os.path.join(RAIZ, "Projeto", "ANALISES", "Analise-estrutural", "Calibracao-Tekla-OpenSees")


def _lst(a, casas=9):
    return np.round(np.asarray(a, float), casas).tolist()


def _nocionais(M: dict, sol: dict, combs: dict, so2: dict) -> dict:
    """{análise de 2ª ordem: {nó: [Fx, Fy, 0]}}: as forças nocionais que a nossa 2ª ordem somou (0,3 % da carga gravitacional
    de cálculo de cada nó, NBR 8800:2024 4.10.7.1.1) — a mesma conta de segunda_ordem.analisar, para o outro programa
    receber as mesmas cargas"""
    from nucleo3d import analise_estrutural as AE
    from nucleo3d import segunda_ordem as SO
    ctx = sol["_ctx"]
    lt, ndof = ctx["lote"], ctx["ndof"]
    apoiados = sorted({int(ap["no"]) for ap in M["apoios"]})
    ke = ctx["k"] * SO.FATOR_RIGIDEZ
    out = {}
    for nome, r in so2.items():
        d = (r.get("nocional") or {}).get("dir") or [0.0, 0.0]
        if not any(d):
            continue
        fat = AE.fatores_da(combs[r["base"]], sol["casos"])
        f0 = np.einsum("ncj,c->nj", ctx["f0"], fat)[:, None, :]
        _kc, f0c, _rec = AE._condensar_lote(lt, ke, f0)
        F0 = ctx["Fn"] @ fat - AE._somar_nos_graus(lt, ndof, AE._forcas_para_global(lt, f0c))[:, 0]
        grav = np.clip(-F0[2::6], 0.0, None)
        grav[apoiados] = 0.0
        out[nome] = {str(n): [round(SO.NOCIONAL * g * d[0], 9), round(SO.NOCIONAL * g * d[1], 9), 0.0]
                     for n, g in enumerate(grav) if g > 0}
    return out


def exportar(slug: str, pasta: str) -> str:
    os.environ.setdefault("METALICA_DADOS", os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica"))
    import app
    from nucleo3d import analise_estrutural as AE
    proj = app._gerente().ler(slug)
    par = dict(AE.PARAMETROS_PADRAO, **(proj.get("analise_parametros") or {}))
    doc = app._documento3d_do_projeto(slug)
    M = AE.montar(doc, par)
    casos, info, av_c = AE.cargas(M)
    combs = AE.combinacoes(list(casos))
    sol = AE.resolver(M, casos)
    so2, nocionais = {}, {}
    if M["par"].get("segunda_ordem", True) and not sol["instavel"]:
        from nucleo3d import segunda_ordem as SO
        so2 = SO.analisar(M, sol, combs)
        nocionais = _nocionais(M, sol, combs, so2)
    nos, barras = M["nos"], M["barras"]
    ndof = 6 * len(nos)
    fixos_apoio = set()
    for ap in M["apoios"]:
        fixos_apoio.update(range(6 * ap["no"], 6 * ap["no"] + (6 if ap["tipo"] == "engastada" else 3)))
    livres = set(int(d) for d in sol["_ctx"]["livres"])
    presos = sorted(d for d in range(ndof) if d not in livres and d not in fixos_apoio)
    nomes = sol["casos"]
    out = {
        "projeto": proj.get("nome") or slug, "slug": slug, "gerado": datetime.datetime.now().isoformat(timespec="seconds"),
        "unidades": "m, kN, kN·m; E = %.0f kN/m², G = %.0f kN/m²" % (AE.E_ACO, AE.G_ACO), "E": AE.E_ACO, "G": AE.G_ACO,
        "parametros": {k: v for k, v in M["par"].items() if isinstance(v, (str, int, float, bool)) or v is None},
        "avisos": list(M["avisos"]) + list(av_c), "resumo_esqueleto": M.get("resumo_esqueleto"),
        "nos": _lst(nos, 6),
        "barras": [{"a": br["a"], "b": br["b"], "L": round(br["L"], 6), "perfil": br["perfil"], "papel": br["papel"],
                    "papel_trelica": br.get("papel_trelica"), "elemento": br.get("elemento"), "grupo": br.get("grupo"),
                    "marca": br.get("marca"), "ids": br.get("ids") or [], "aco": br.get("aco") or "", "duplo": br.get("duplo"),
                    "rot": br.get("rot", 0.0), "hipotese": bool(br.get("hipotese")),
                    "sec": {k: br["sec"][k] for k in ("A", "Iy", "Iz", "J", "Wz", "Wy", "kg_m")},
                    "R": _lst(br["R"], 9), "soltos": sorted(int(s) for s in br["soltos"])} for br in barras],
        "apoios": [{k: v for k, v in ap.items()} for ap in M["apoios"]],
        "graus_presos": presos,
        "casos": {c: {"descricao": casos[c].get("descricao", ""),
                      "dist": {str(i): _lst(w, 9) for i, w in casos[c]["dist"].items()},
                      "nodal": {str(i): _lst(F, 9) for i, F in casos[c]["nodal"].items()},
                      "nos": {str(n): _lst(F, 9) for n, F in (casos[c].get("nos") or {}).items()}} for c in nomes},
        "combinacoes": {c: {"tipo": cb["tipo"], "fatores": cb["fatores"], "descricao": cb.get("descricao", "")} for c, cb in combs.items()},
        "nossos": {
            "instavel": sol["instavel"],
            "casos": {c: {"U": _lst(sol["U"][:, k].reshape(-1, 6), 9),
                          "reacoes": {str(no): _lst(r[:, k], 6) for no, r in sol["reacoes"].items()},
                          "pontas": _lst(sol["pontas"][:, k, :], 6)} for k, c in enumerate(nomes)},
            # "pontas_nos": as forças das pontas que equilibram os nós (as que o OpenSees devolve); "pontas": as dos diagramas
            "segunda_ordem": {c: {"base": r["base"], "imperfeicao": r["imperfeicao"], "iteracoes": r["iteracoes"],
                                  "razao": r.get("razao"), "nocionais": nocionais.get(c, {}),
                                  "U": _lst(np.asarray(r["U"]).reshape(-1, 6), 9),
                                  "reacoes": {str(no): _lst(v, 6) for no, v in (r.get("reacoes") or {}).items()},
                                  "pontas_nos": _lst(r["pontas_nos"], 6)} for c, r in so2.items() if r.get("pontas") is not None},
        },
    }
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, "modelo.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    slug = sys.argv[1]
    pasta = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAIDA_PADRAO, slug)
    c = exportar(slug, pasta)
    d = json.load(open(c, encoding="utf-8"))
    print("%s: %d nós, %d barras, %d apoios, %d graus presos, casos %s, %d combinações -> %s" % (
        d["projeto"], len(d["nos"]), len(d["barras"]), len(d["apoios"]), len(d["graus_presos"]), ", ".join(d["casos"]),
        len(d["combinacoes"]), c))
