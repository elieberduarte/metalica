"""A análise de 2ª ordem da NBR 8800:2008 (4.9.7) nas combinações últimas — etapa 4 do plano da análise estrutural (07/10).

Para cada combinação ELU:

* **imperfeições de material** (4.9.7.1.2): EA e EI × 0,8 em todas as barras;
* **imperfeições geométricas** (4.9.7.1.1) por forças nocionais: 0,3% da carga gravitacional de cálculo de cada nó, na
  horizontal. Nas combinações com vento, no sentido da resultante horizontal da combinação; nas só gravitacionais, na
  direção (X ou Y) em que a estrutura é mais flexível — o teste é a própria força nocional aplicada nas duas — e no
  sentido em que a combinação já desloca a estrutura;
* **P-Δ** pela rigidez geométrica consistente de cada barra (12×12, com a normal do passo anterior), iterando até a
  normal e os deslocamentos pararem de mudar. A rótula é condensada já com a rigidez geométrica (a barra rotulada
  nas duas pontas fica com a rigidez de pêndulo N/L).

Sai, por combinação, o que a 1ª ordem dava — deslocamentos, reações e as forças nas pontas das barras (`pontas`, as
que o diagrama, as reações e a verificação usam) — e a relação Δ2/Δ1 no topo dos pilares, que classifica a
estrutura (4.9.4: pequena ≤ 1,1, média ≤ 1,4, grande acima). Divergir, inverter o deslocamento ou amplificar mais de
10 vezes quer dizer instabilidade global naquela combinação (a carga passou da crítica).

Δ1 é a 1ª ordem com as mesmas cargas (com as nocionais) e a mesma rigidez reduzida: a razão mede só o efeito geométrico.
O P-δ (a curvatura entre as pontas de cada barra) não entra aqui: é o B1 da verificação (nucleo3d/verificacao_pecas.py).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

FATOR_RIGIDEZ = 0.8           # NBR 8800, 4.9.7.1.2
NOCIONAL = 0.003              # NBR 8800, 4.9.7.1.1: 0,3% das cargas gravitacionais de cálculo
MAX_ITERACOES = 30
TOLERANCIA = 1e-3             # da normal (× a maior) e do deslocamento (× o maior): 0,1%
AMPLIFICACAO_LIMITE = 10.0    # Δ2/Δ1 acima disto: tratada como instabilidade global


def _fatorar(K):
    """LU da matriz simétrica (a ordenação de A + Aᵀ e o pivô na diagonal: metade do tempo da padrão)"""
    from scipy.sparse.linalg import splu
    return splu(K, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0, options={"SymmetricMode": True})


def classe_de_deslocabilidade(razao: Optional[float]) -> Optional[str]:
    if razao is None:
        return None
    return "pequena" if razao <= 1.1 else "média" if razao <= 1.4 else "grande"


def _topos_dos_pilares(M: dict) -> List[int]:
    """o nó mais alto de cada pilar (pela base em planta); sem pilares, nenhum (a razão usa todos os nós)"""
    from nucleo3d.analise_estrutural import chave_do_pilar
    nos = M["nos"]
    topo: Dict[str, int] = {}
    for br in M["barras"]:
        if br["papel"] != "pilar":
            continue
        k = chave_do_pilar(nos, br)
        for no in (br["a"], br["b"]):
            if k not in topo or nos[no][2] > nos[topo[k]][2]:
                topo[k] = no
    return sorted(set(topo.values()))


def _horizontal(U: np.ndarray, nos_idx) -> np.ndarray:
    """(len(nos_idx), 2): o deslocamento horizontal dos nós (m)"""
    u = U.reshape(-1, 6)
    return u[nos_idx, :2]


def analisar(M: dict, sol: dict, combs: Dict[str, dict]) -> Dict[str, dict]:
    """a 2ª ordem de cada combinação ELU: {comb: {pontas (n, 12), U (ndof), reacoes {nó: (6,)}, iteracoes, convergiu,
    instavel, delta1_mm, delta2_mm, razao, classe, nocional {dir, H_kN}}}; vazio se a 1ª ordem já é instável"""
    from nucleo3d import analise_estrutural as AE
    ctx = sol.get("_ctx")
    elu = [c for c, cb in combs.items() if cb["tipo"] == "ELU"]
    if ctx is None or sol.get("instavel") or not elu:
        return {}
    lt, mont, livres, ndof = ctx["lote"], ctx["montador"], ctx["livres"], ctx["ndof"]
    n, nn = lt["n"], ndof // 6
    nomes = sol["casos"]
    ke = ctx["k"] * FATOR_RIGIDEZ
    FAT = np.stack([AE.fatores_da(combs[c], nomes) for c in elu], axis=1)          # (casos, ne)
    ne = len(elu)
    Fn = ctx["Fn"] @ FAT                                                             # (ndof, ne)
    f0 = np.einsum("ncj,ce->nej", ctx["f0"], FAT)                                    # (n, ne, 12)
    wx = np.einsum("nc,ce->ne", ctx["w_loc"][:, :, 0], FAT)                          # (n, ne)
    apoiados = sorted({int(ap["no"]) for ap in M["apoios"]})
    # 1ª ordem com a rigidez reduzida: todas as combinações de uma vez
    kc0, f0c0, rec0 = AE._condensar_lote(lt, ke, f0)
    F0 = Fn - AE._somar_nos_graus(lt, ndof, AE._forcas_para_global(lt, f0c0))
    try:
        lu0 = _fatorar(mont.matriz(AE._para_global(lt, kc0)))
    except RuntimeError as e:
        return {c: {"instavel": "matriz singular com a rigidez reduzida (%s)" % e} for c in elu}
    U_sem = np.zeros((ndof, ne))
    U_sem[livres] = lu0.solve(F0[livres])
    # a carga gravitacional de cálculo de cada nó (a componente para baixo, nos nós livres)
    grav = np.clip(-F0[2::6], 0.0, None)                                             # (nn, ne)
    grav[apoiados] = 0.0
    Hres = np.stack([F0[0::6].sum(0), F0[1::6].sum(0)], axis=1)                      # (ne, 2)
    # o teste das gravitacionais: a força nocional da combinação em X e em Y
    teste = np.zeros((ndof, 2 * ne))
    for e in range(ne):
        teste[0::6, 2 * e] = NOCIONAL * grav[:, e]
        teste[1::6, 2 * e + 1] = NOCIONAL * grav[:, e]
    U_teste = np.zeros((ndof, 2 * ne))
    U_teste[livres] = lu0.solve(teste[livres])
    topos = _topos_dos_pilares(M) or list(range(nn))
    peso = lambda e: grav[:, e] / max(float(grav[:, e].sum()), 1e-12)               # noqa: E731
    dirs = np.zeros((ne, 2))
    for e, c in enumerate(elu):
        ventos = any(k.startswith("V") and v for k, v in combs[c]["fatores"].items())
        h = Hres[e]
        if ventos and float(np.hypot(*h)) > 1e-6:
            dirs[e] = h / float(np.hypot(*h))
            continue
        # a mais flexível: o deslocamento médio (pesado pela carga) que a nocional dá em cada direção
        ux = float(peso(e) @ U_teste[0::6, 2 * e])
        uy = float(peso(e) @ U_teste[1::6, 2 * e + 1])
        k = 0 if abs(ux) >= abs(uy) else 1
        lado = float(peso(e) @ U_sem[k::6, e])
        dirs[e, k] = -1.0 if lado < -1e-9 else 1.0
    Fnoc = np.zeros((ndof, ne))
    Fnoc[0::6] = NOCIONAL * grav * dirs[:, 0]
    Fnoc[1::6] = NOCIONAL * grav * dirs[:, 1]
    U_noc = np.zeros((ndof, ne))
    U_noc[livres] = lu0.solve(Fnoc[livres])
    U1 = U_sem + U_noc
    # as normais da 1ª ordem (o ponto de partida)
    ul0 = AE._deslocamentos_locais(lt, U1)
    AE._recuperar_soltos(ul0, f0, rec0)
    p0 = np.einsum("nij,nje->nei", ke, ul0) + f0                                     # (n, ne, 12)
    Nini = -(p0[:, :, 0] + wx * lt["L"][:, None] / 2.0)                              # (n, ne) a normal média
    saida: Dict[str, dict] = {}
    for e, c in enumerate(elu):
        U, N = U1[:, e].copy(), Nini[:, e].copy()
        f0e = f0[:, e:e + 1, :]
        rhs_n = Fn[:, e] + Fnoc[:, e]
        instavel, convergiu, it = None, False, 0
        pontas = None
        for it in range(1, MAX_ITERACOES + 1):
            kt = ke + AE._kg_local_lote(lt, N)
            kc, f0c, rec = AE._condensar_lote(lt, kt, f0e)
            rhs = rhs_n - AE._somar_nos_graus(lt, ndof, AE._forcas_para_global(lt, f0c))[:, 0]
            try:
                lu = _fatorar(mont.matriz(AE._para_global(lt, kc)))
            except RuntimeError:
                instavel = "a matriz de rigidez com o efeito da normal ficou singular (carga crítica atingida)"
                break
            Un = np.zeros(ndof)
            Un[livres] = lu.solve(rhs[livres])
            if AE._sem_limite(Un[:, None]):
                instavel = "os deslocamentos de 2ª ordem cresceram sem limite"
                break
            ul = AE._deslocamentos_locais(lt, Un[:, None])
            AE._recuperar_soltos(ul, f0e, rec)
            pontas = np.einsum("nij,nj->ni", kt, ul[:, :, 0]) + f0e[:, 0, :]
            Nn = -(pontas[:, 0] + wx[:, e] * lt["L"] / 2.0)
            dN = float(np.abs(Nn - N).max(initial=0.0))
            dU = float(np.abs(Un - U).max(initial=0.0))
            U, N = Un, Nn
            if dN <= TOLERANCIA * max(1.0, float(np.abs(Nn).max(initial=0.0))) and dU <= TOLERANCIA * max(float(np.abs(Un).max(initial=0.0)), 1e-6):
                convergiu = True
                break
        r: dict = {"iteracoes": it, "convergiu": convergiu, "instavel": instavel,
                   "nocional": {"dir": [round(float(v), 4) for v in dirs[e]], "H_kN": round(float(NOCIONAL * grav[:, e].sum()), 3)}}
        d1 = np.hypot(*_horizontal(U1[:, e], topos).T)
        d1max = float(d1.max(initial=0.0))
        r["delta1_mm"] = round(d1max * 1000, 2)
        if instavel is None and not convergiu:
            instavel = "a iteração da 2ª ordem não convergiu em %d passos" % MAX_ITERACOES
        if instavel is None and pontas is not None:
            h2 = _horizontal(U, topos)
            d2 = np.hypot(*h2.T)
            d2max = float(d2.max(initial=0.0))
            r["delta2_mm"] = round(d2max * 1000, 2)
            if d1max > 1e-6:
                razao = d2max / d1max
                j = int(np.argmax(d1))
                if float(h2[j] @ _horizontal(U1[:, e], topos)[j]) < 0:
                    instavel = "o deslocamento de 2ª ordem inverteu o sentido (a carga passou da crítica)"
                elif razao > AMPLIFICACAO_LIMITE:
                    instavel = "a 2ª ordem amplifica o deslocamento %.1f vezes (instabilidade global)" % razao
                r["razao"] = round(razao, 3)
                r["classe"] = classe_de_deslocabilidade(razao)
        r["instavel"] = instavel
        if instavel is None and pontas is not None:
            R_all = AE._somar_nos_graus(lt, ndof, AE._forcas_para_global(lt, pontas[:, None, :]))[:, 0] - rhs_n
            wl = np.einsum("nc,c->n", ctx["w_loc"][:, :, 1], FAT[:, e]), np.einsum("nc,c->n", ctx["w_loc"][:, :, 2], FAT[:, e])
            r.update({"pontas": cortantes_na_corda(pontas, lt["L"], *wl), "U": U,
                      "reacoes": {int(ap["no"]): R_all[6 * ap["no"]:6 * ap["no"] + 6] for ap in M["apoios"]}})
        saida[c] = r
    return saida


def cortantes_na_corda(pontas: np.ndarray, L: np.ndarray, wy: np.ndarray, wz: np.ndarray) -> np.ndarray:
    """as forças das pontas para os diagramas: (ke + kg)·u dá as forças nos eixos da barra indeformada, e o cortante leva
    junto a componente N·ψ da normal inclinada pelo giro da corda — o diagrama refeito pela ponta a (N, V e M ao longo
    da barra) somaria N·ψ·x e erraria o momento da outra ponta. Os momentos das pontas são os verdadeiros: o cortante
    da ponta a sai deles (o equilíbrio da barra na corda deformada) e o diagrama fecha nas duas pontas"""
    p = pontas.copy()
    Mz_a, Mz_b, My_a, My_b = p[:, 5], p[:, 11], p[:, 4], p[:, 10]
    p[:, 1] = (Mz_b + Mz_a - wy * L * L / 2.0) / L
    p[:, 2] = -(My_b + My_a + wz * L * L / 2.0) / L
    p[:, 7] = -p[:, 1] - wy * L
    p[:, 8] = -p[:, 2] - wz * L
    return p


def resumo(so2: Dict[str, dict]) -> Optional[dict]:
    """o quadro geral: a maior Δ2/Δ1, a classe da estrutura e as combinações instáveis"""
    if not so2:
        return None
    razoes = [(r["razao"], c) for c, r in so2.items() if r.get("razao") is not None and not r.get("instavel")]
    inst = [c for c, r in so2.items() if r.get("instavel")]
    rz, cm = max(razoes) if razoes else (None, None)
    return {"razao_max": rz, "comb_razao_max": cm, "classe": classe_de_deslocabilidade(rz), "instaveis": inst,
            "fator_rigidez": FATOR_RIGIDEZ, "nocional": NOCIONAL,
            "iteracoes_max": max((r.get("iteracoes") or 0) for r in so2.values())}


def para_json(so2: Dict[str, dict]) -> Dict[str, dict]:
    """o que vai para a tela por combinação (sem as matrizes)"""
    return {c: {k: v for k, v in r.items() if k not in ("pontas", "U", "reacoes")} for c, r in so2.items()}


__all__ = ["analisar", "resumo", "para_json", "classe_de_deslocabilidade", "FATOR_RIGIDEZ", "NOCIONAL"]
