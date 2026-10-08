# -*- coding: utf-8 -*-
"""Calibração (08/10/2026): o modelo exportado pelo nosso motor (exportar_modelo.py) resolvido no OpenSees, um programa
de cálculo independente (código aberto, Universidade da Califórnia em Berkeley). Roda no Python 3.12 portátil da pasta
de ferramentas (o OpenSees para Windows só existe para o 3.12), sem numpy:

    %LOCALAPPDATA%\\Metalica-ferramentas\\python312\\python.exe opensees_resolver.py <modelo.json> [--segunda-ordem]

A mesma estrutura, peça por peça: barras de pórtico espacial (elasticBeamColumn) com a mesma seção (A, Iy, Iz, J), os
mesmos eixos locais (o vetor do plano xz = o eixo z local do nosso motor), as mesmas rótulas (-releasey/-releasez), os
mesmos apoios e os mesmos graus presos; as mesmas cargas (distribuídas na barra pelos eixos locais e forças nos nós).
Sai `opensees.json` ao lado do modelo: por caso, deslocamentos, reações e forças nas pontas das barras (eixos locais, a
força do nó sobre a barra — a convenção do nosso motor).

Com --segunda-ordem, as mesmas análises de 2ª ordem do nosso motor (cada combinação ELU, as gravitacionais em ·X e ·Y
com as mesmas forças nocionais), com a rigidez a 80 % (NBR 8800:2024, 4.10.7.1.2) e o P-Delta (geomTransf PDelta, Newton):
uma vez com uma barra por elemento (a comparação direta) e outra com cada barra dividida em 4 (a referência mais exata:
pega a curvatura dentro da barra, o P-δ).
"""
import json
import os
import sys

import openseespy.opensees as ops


def _mul(R, v):
    return [sum(R[i][j] * v[j] for j in range(3)) for i in range(3)]


def _liberacoes(soltos):
    """os graus soltos do nosso motor (4 ry, 5 rz na ponta a; 10, 11 na b): {"y": ponta a?, ponta b?, "z": …}"""
    rel = {"y": [False, False], "z": [False, False]}
    for s in soltos:
        eixo = {4: "y", 5: "z", 10: "y", 11: "z"}.get(s)
        if eixo is None:
            raise ValueError("grau solto %d sem equivalente no OpenSees" % s)
        rel[eixo][0 if s < 6 else 1] = True
    return rel


def _codigo(i_solto, j_solto):
    return (1 if i_solto else 0) | (2 if j_solto else 0)


def montar(M, fator_rigidez=1.0, pdelta=False, dividir=1):
    """monta o modelo; devolve, por barra, as etiquetas dos elementos (do primeiro trecho ao último)"""
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    nos = M["nos"]
    for i, (x, y, z) in enumerate(nos):
        ops.node(i + 1, x, y, z)
    fixos = {}
    for ap in M["apoios"]:
        n = ap["no"]
        fixos.setdefault(n, [0] * 6)
        for k in range(6 if ap["tipo"] == "engastada" else 3):
            fixos[n][k] = 1
    for d in M["graus_presos"]:
        n, k = divmod(d, 6)
        fixos.setdefault(n, [0] * 6)[k] = 1
    usados = {br["a"] for br in M["barras"]} | {br["b"] for br in M["barras"]}
    for n in range(len(nos)):
        if n not in usados:
            fixos[n] = [1] * 6                                     # nó solto (sem barra): preso, como no nosso motor
    for n, m in fixos.items():
        ops.fix(n + 1, *m)
    E, G = M["E"] * fator_rigidez, M["G"] * fator_rigidez
    proximo_no = len(nos) + 1
    elementos = []
    etiqueta = 1
    for i, br in enumerate(M["barras"]):
        t = i + 1
        ops.geomTransf("PDelta" if pdelta else "Linear", t, *br["R"][2])
        s = br["sec"]
        rel = _liberacoes(br["soltos"])
        pa, pb = nos[br["a"]], nos[br["b"]]
        cadeia = [br["a"] + 1]
        for k in range(1, dividir):                                 # nós intermediários (livres)
            f = k / dividir
            ops.node(proximo_no, *[pa[j] + f * (pb[j] - pa[j]) for j in range(3)])
            cadeia.append(proximo_no)
            proximo_no += 1
        cadeia.append(br["b"] + 1)
        tags = []
        for k in range(dividir):
            primeiro, ultimo = k == 0, k == dividir - 1
            args = ["elasticBeamColumn", etiqueta, cadeia[k], cadeia[k + 1], s["A"], E, G, s["J"], s["Iy"], s["Iz"], t]
            cy = _codigo(primeiro and rel["y"][0], ultimo and rel["y"][1])
            cz = _codigo(primeiro and rel["z"][0], ultimo and rel["z"][1])
            if cy:
                args += ["-releasey", cy]
            if cz:
                args += ["-releasez", cz]
            ops.element(*args)
            tags.append(etiqueta)
            etiqueta += 1
        elementos.append(tags)
    return elementos


def carregar(M, elementos, fatores, nocionais=None):
    """as cargas da soma de casos {caso: fator}, mais as forças nocionais {nó: [Fx, Fy, Fz]}"""
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    nodal = {}
    for caso, f in fatores.items():
        C = M["casos"].get(caso)
        if not C or not f:
            continue
        for i, wg in C["dist"].items():
            br = M["barras"][int(i)]
            wx, wy, wz = _mul(br["R"], [f * w for w in wg])
            for tag in elementos[int(i)]:
                ops.eleLoad("-ele", tag, "-type", "-beamUniform", wy, wz, wx)
        for i, F in C["nodal"].items():
            br = M["barras"][int(i)]
            for n in (br["a"], br["b"]):
                acc = nodal.setdefault(n, [0.0] * 6)
                for k in range(3):
                    acc[k] += f * F[k]
        for n, F in C["nos"].items():
            acc = nodal.setdefault(int(n), [0.0] * 6)
            for k in range(3):
                acc[k] += f * F[k]
    for n, F in (nocionais or {}).items():
        acc = nodal.setdefault(int(n), [0.0] * 6)
        for k in range(3):
            acc[k] += F[k]
    for n, F in nodal.items():
        ops.load(n + 1, *F)


def analisar(M, elementos, linear=True):
    ops.system("UmfPack")
    ops.numberer("RCM")
    ops.constraints("Plain")
    if linear:
        ops.integrator("LoadControl", 1.0)
        ops.algorithm("Linear")
        ops.analysis("Static")
        ok = ops.analyze(1)
    else:
        ops.test("NormDispIncr", 1e-10, 100)
        ops.algorithm("Newton")
        ops.integrator("LoadControl", 1.0)
        ops.analysis("Static")
        ok = ops.analyze(1)
    if ok != 0:
        return None
    ops.reactions()
    U = [ops.nodeDisp(n + 1) for n in range(len(M["nos"]))]
    reac = {str(ap["no"]): ops.nodeReaction(ap["no"] + 1) for ap in M["apoios"]}
    pontas = []
    for i, br in enumerate(M["barras"]):
        R = br["R"]
        gi = ops.eleResponse(elementos[i][0], "globalForce")       # a força do nó sobre a barra, no global
        gj = ops.eleResponse(elementos[i][-1], "globalForce")
        g = list(gi[:6]) + list(gj[6:12])
        pontas.append([v for b in range(4) for v in _mul(R, g[3 * b:3 * b + 3])])
    return {"U": U, "reacoes": reac, "pontas": pontas}


def main():
    caminho = sys.argv[1]
    segunda = "--segunda-ordem" in sys.argv
    with open(caminho, encoding="utf-8") as f:
        M = json.load(f)
    out = {"programa": "OpenSees (openseespy)", "casos": {}, "segunda_ordem": {}, "segunda_ordem_dividida": {}}
    for caso in M["casos"]:
        el = montar(M)
        carregar(M, el, {caso: 1.0})
        r = analisar(M, el)
        out["casos"][caso] = r if r is not None else {"erro": "não convergiu / singular"}
        print("caso %-6s %s" % (caso, "ok" if r is not None else "FALHOU"), flush=True)
    if segunda:
        for nome, r2 in (M.get("nossos") or {}).get("segunda_ordem", {}).items():
            fat = M["combinacoes"][r2["base"]]["fatores"]
            for chave, dividir in (("segunda_ordem", 1), ("segunda_ordem_dividida", 4)):
                el = montar(M, fator_rigidez=0.8, pdelta=True, dividir=dividir)
                carregar(M, el, fat, r2.get("nocionais"))
                r = analisar(M, el, linear=False)
                out[chave][nome] = r if r is not None else {"erro": "não convergiu"}
            print("2ª ordem %-18s %s" % (nome, "ok" if "erro" not in out["segunda_ordem"][nome] else "FALHOU"), flush=True)
    destino = os.path.join(os.path.dirname(os.path.abspath(caminho)), "opensees.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print("->", destino)


if __name__ == "__main__":
    main()
