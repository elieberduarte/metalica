# -*- coding: utf-8 -*-
"""Calibração (08/10/2026): as barras do modelo 3D de um projeto como peças do Tekla (entrada do TeklaPonte.exe criar).

    python testes/calibracao/exportar_tekla.py <projeto> [pasta de saída]

Por barra: o perfil equivalente do Tekla (o paramétrico do ambiente blank_project: o Ue vira CC h-t-e-b, o U e a
cantoneira os paramétricos U h*b*t e L h*b*t, que são de canto laminado), a linha da barra (a nossa passa pelo centro de
gravidade da seção) e os eixos da seção (u = largura, v = altura, como no nosso 3D). A ponte põe a peça pelo centro da
caixa (MIDDLE/MIDDLE) e gira até o centro de gravidade do Tekla cair na nossa linha.
"""
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SISTEMA = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, SISTEMA)

from exportar_modelo import SAIDA_PADRAO  # noqa: E402

_NUM = r"(\d+(?:[.,]\d+)?)"


def _f(s):
    return float(s.replace(",", "."))


def perfil_tekla(nome: str) -> str:
    """o nome do perfil paramétrico do Tekla (ambiente blank_project) para o nosso nome"""
    s = nome.replace("×", "x").replace("X", "x")
    m = re.match(r"^Ue\s*%sx%sx%sx%s" % (_NUM, _NUM, _NUM, _NUM), s)
    if m:
        h, b, e, t = (_f(x) for x in m.groups())
        return "CC%g-%g-%g-%g" % (h, t, e, b)
    m = re.match(r"^U\s*%sx%sx%s" % (_NUM, _NUM, _NUM), s)
    if m:
        h, b, t = (_f(x) for x in m.groups())
        return "U%g*%g*%g" % (h, b, t)
    m = re.match(r"^L\s*%sx%s" % (_NUM, _NUM), s)
    if m:
        b, t = (_f(x) for x in m.groups())
        return "L%g*%g*%g" % (b, b, t)
    raise ValueError("perfil sem equivalente no Tekla: %s" % nome)


def exportar(slug: str, pasta: str) -> str:
    os.environ.setdefault("METALICA_DADOS", os.path.join(os.path.expanduser("~"), "OneDrive", "Documentos", "Metálica"))
    import app
    from nucleo3d import geometria as G
    doc = app._documento3d_do_projeto(slug)
    pecas, caixas = [], {}
    for e in doc.entidades.values():
        if type(e).__name__ != "Barra" or not getattr(e, "perfil", None):
            continue
        a, b = e.inicio, e.fim
        d = tuple(b[k] - a[k] for k in range(3))
        u, v, w = G.base_local(d, float(e.rotacao or 0.0))
        if e.perfil not in caixas:
            c = G.secao(e.perfil)
            xs, ys = [p[0] for p in c], [p[1] for p in c]
            caixas[e.perfil] = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        cu, cv = caixas[e.perfil]
        at = e.atributos or {}
        pecas.append({
            "id": e.id, "nome": (e.papel or at.get("elemento") or "barra").upper()[:20], "prefixo": (at.get("marca") or "P")[:10],
            "perfil_nosso": e.perfil, "perfil": perfil_tekla(e.perfil), "material": "Steel_Undefined",
            "inicio": [round(x, 3) for x in a], "fim": [round(x, 3) for x in b],
            "u": [round(x, 9) for x in u], "v": [round(x, 9) for x in v],
            # o centro da caixa da seção visto do centro de gravidade (mm, nos eixos u e v): no Tekla o centro de gravidade
            # fica a -c do centro da caixa
            "caixa_cg": [round(cu, 3), round(cv, 3)],
        })
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, "tekla_entrada.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"projeto": slug, "pecas": pecas}, f, ensure_ascii=False)
    return caminho


if __name__ == "__main__":
    slug = sys.argv[1]
    pasta = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SAIDA_PADRAO, slug)
    c = exportar(slug, pasta)
    d = json.load(open(c, encoding="utf-8"))
    from collections import Counter
    print("%d peças -> %s" % (len(d["pecas"]), c))
    for (a, b), n in Counter((p["perfil_nosso"], p["perfil"]) for p in d["pecas"]).items():
        print("  %3d  %-22s -> %s" % (n, a, b))
